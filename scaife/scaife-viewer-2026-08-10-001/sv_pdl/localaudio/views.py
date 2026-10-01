"""JSON lookup of clips for a passage, and a byte-range-capable clip server.

The clip view serves only paths recorded by `ingest_audio` (package
directory + relative clip path, both from the database), never a path
from the request, and it answers `Range` requests with 206: Django's
FileResponse ignores the header, browsers send `Range: bytes=0-` for every
media load, and Safari documents byte ranges as required for playback.
The response is streaming, which also keeps it out of the site-wide cache
middleware (Django never caches streaming responses).
"""
import os
import re

from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404

from sv_pdl.localcomm.refs import ref_key, split_range

from .models import AudioClip, AudioPackage
from .urns import split_passage_urn


CONTENT_TYPE = "audio/mp4"
CHUNK = 64 * 1024
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _package_json(package):
    return {
        "slug": package.slug,
        "label": package.label,
        "license": package.license,
        "attribution": package.attribution,
        "source": package.source_url,
    }


def audio_json(request, urn):
    version_urn, ref = split_passage_urn(urn)
    if not version_urn:
        return JsonResponse({"error": "not a CTS passage URN"}, status=404)

    first = (
        AudioClip.objects.filter(version_urn=version_urn)
        .order_by("package_id")
        .values_list("package_id", flat=True)
        .first()
    )
    if first is None:
        return JsonResponse({"package": None, "clips": []})
    package = AudioPackage.objects.get(pk=first)

    start, end = split_range(ref)
    qs = AudioClip.objects.filter(
        package=package,
        version_urn=version_urn,
        ref_key__gte=ref_key(start),
        ref_key__lte=ref_key(end),
    ).order_by("ref_key", "id")
    clips = [{"ref": c.ref, "url": clip_url(package.slug, c.version_urn, c.ref)} for c in qs]
    return JsonResponse({"package": _package_json(package), "clips": clips})


def clip_url(slug, version_urn, ref):
    """Natural-key URL: stable across re-ingests, so a cached JSON response
    never points at an id that no longer exists."""
    return f"/library/audio/clip/{slug}/{version_urn}/{ref}/"


def _file_iter(path, start, length):
    """Generator over a byte range. Django calls `.close()` on a streaming
    response's iterator when the response is closed, which runs the
    `finally` and closes the file."""
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            data = fh.read(min(CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def audio_clip(request, slug, urn, ref):
    clip = get_object_or_404(
        AudioClip.objects.select_related("package"),
        package__slug=slug, version_urn=urn, ref=ref,
    )
    root = os.path.realpath(clip.package.root_dir)
    path = os.path.realpath(os.path.join(root, clip.path))
    if not path.startswith(root + os.sep) or not os.path.isfile(path):
        raise Http404("clip file missing")
    size = os.path.getsize(path)

    common = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
    }
    range_header = request.META.get("HTTP_RANGE", "")
    m = _RANGE_RE.match(range_header.strip()) if range_header else None
    if range_header and not m:
        # Multi-range or malformed: fall back to the whole file (RFC 9110
        # allows ignoring an unparseable Range).
        m = None

    if m:
        first, last = m.group(1), m.group(2)
        if first == "" and last == "":
            return _unsatisfiable(size, common)
        if first == "":
            # suffix range: last N bytes
            length = min(int(last), size)
            start = size - length
            end = size - 1
        else:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        if start >= size or start > end:
            return _unsatisfiable(size, common)
        length = end - start + 1
        status, headers = 206, {
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        }
    else:
        start, length = 0, size
        status, headers = 200, {"Content-Length": str(size)}

    if request.method == "HEAD":
        response = HttpResponse(status=status, content_type=CONTENT_TYPE)
    else:
        response = StreamingHttpResponse(
            _file_iter(path, start, length), status=status, content_type=CONTENT_TYPE
        )
    for k, v in headers.items():
        response[k] = v
    for k, v in common.items():
        response[k] = v
    return response


def _unsatisfiable(size, common):
    response = HttpResponse(status=416, content_type=CONTENT_TYPE)
    response["Content-Range"] = f"bytes */{size}"
    for k, v in common.items():
        response[k] = v
    return response
