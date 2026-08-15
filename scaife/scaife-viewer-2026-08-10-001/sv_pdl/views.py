import os
from typing import Any
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render

import requests
from scaife_viewer.atlas.models import Repo
from scaife_viewer.core import cts
from scaife_viewer.core.utils import apify, get_pagination_info

from .changelog.keyfile import cachekeys
from .search import SearchQuery
from .stats import get_library_stats


CACHE_FOREVER = None
LATEST_RELEASE_KEY = cachekeys["LATEST_RELEASE"]


def morpheus_local(request):
    """
    Replacement for scaife_viewer.core.views.morpheus that hits our in-cluster
    Perseids Morpheus service (MORPHEUS_LOCAL_URL) instead of services.perseids.org.

    Response shape matches the upstream view so the Vue frontend needs no changes.
    """
    if ("word" not in request.GET) or ("lang" not in request.GET):
        return HttpResponseBadRequest(
            content='Error when processing morpheus request: "word" and "lang" parameters are required'
        )
    word = request.GET["word"]
    lang = request.GET["lang"]
    if lang not in ("grc", "lat"):
        return HttpResponseBadRequest(
            content='"lang" must be one of: grc, lat'
        )
    base = os.environ.get("MORPHEUS_LOCAL_URL", "http://morpheus:1500")
    qs = urlencode({"word": word, "lang": lang, "engine": f"morpheus{lang}"})
    url = f"{base}/analysis/word?{qs}"
    try:
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        r.raise_for_status()
    except requests.RequestException:
        return JsonResponse({"Body": []})

    body = r.json().get("RDF", {}).get("Annotation", {}).get("Body", [])
    if body in (None, {}, []):
        return JsonResponse({"Body": []})
    if not isinstance(body, list):
        body = [body]

    data_body = []
    for item in body:
        entry_root = item.get("rest", {}).get("entry", {})
        dictd = entry_root.get("dict", {}) or {}
        hdwd = (dictd.get("hdwd") or {}).get("$", "")
        pofs = (dictd.get("pofs") or {}).get("$", "")
        entry = {"uri": entry_root.get("uri"), "hdwd": hdwd, "pofs": pofs}
        if "decl" in dictd:
            entry["decl"] = dictd["decl"].get("$", "")

        infl_body = entry_root.get("infl", [])
        if not isinstance(infl_body, list):
            infl_body = [infl_body]
        infl_list = []
        for infl_item in infl_body:
            infl_entry = {}
            term = infl_item.get("term", {}) or {}
            stem = term.get("stem") or {}
            suff = term.get("suff") or {}
            infl_entry["stem"] = stem.get("$", "")
            if "$" in suff:
                infl_entry["suff"] = suff.get("$", "")
            for key in ("pofs", "case", "mood", "tense", "voice", "gend",
                        "num", "pers", "comp", "dial", "stemtype",
                        "derivtype", "morph"):
                if key in infl_item and isinstance(infl_item[key], dict):
                    infl_entry[key] = infl_item[key].get("$", "")
            infl_list.append(infl_entry)
        entry["infl"] = infl_list
        data_body.append(entry)

    return JsonResponse({"Body": data_body})


def _latest_release():
    # Offline build: the upstream implementation calls github.com to display
    # the latest scaife-viewer release on the home page. Return an empty
    # dict so the template renders normally without an external request.
    return {}


def home(request):
    release = cache.get(LATEST_RELEASE_KEY, None)
    if not release:
        release = _latest_release()
        cache.set(LATEST_RELEASE_KEY, release, CACHE_FOREVER)
    return render(
        request,
        "homepage.html",
        {
            "stats": get_library_stats(),
            "release": release,
        },
    )


def about(request):
    repos = Repo.objects.annotate(version_count=Count("urns")).order_by(
        "-version_count"
    )
    return render(request, "about.html", {"repos": repos})


# The upstream `commentaries`, `dictionary_entries` and `dictionaries` views
# proxied to settings.SV_NEW_ATLAS_API_URL (atlas.perseus.tufts.edu). They are
# removed here; sv_pdl.localcomm and sv_pdl.localdict serve the same routes
# from Postgres. See README "Local dictionaries app" / "Local commentaries app".


SEARCH_TYPES = ("library", "reader")


def _positive_int(request, name, default):
    """Read a query parameter that must be a positive integer.

    Raises ValueError, which the caller turns into a 400. Previously these
    were parsed with a bare `int()`, so `?size=abc` raised straight out of
    the view and became a 500 — a client error reported as a server one.

    The lower bound is not cosmetic. `size` is now the page stride, so
    `size=0` would divide by zero when computing the page count, and
    `page_num=0` would ask the search backend for a negative offset.
    """
    value = int(request.GET.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be >= 1")
    return value


def search_json(request):
    # get params from query string
    search_type = request.GET.get("type")
    q = request.GET.get("q", "")
    kind = request.GET.get("kind", "form")
    text_group_urn = request.GET.get("text_group")
    work_urn = request.GET.get("work")

    # validate params
    #
    # `type` is checked against the known values rather than merely for
    # being non-empty. It used to be the latter, so any unrecognised value
    # fell through to the reader branch and returned 200 — while the error
    # message for a *missing* type promised 'library' or 'reader'.
    if search_type not in SEARCH_TYPES:
        return JsonResponse(
            {"error": "Provide a search type - 'library' or 'reader'."}, status=400
        )
    if not q:
        return JsonResponse({"error": "Provide a search query."}, status=400)
    try:
        size = _positive_int(request, "size", "10")
    except ValueError:
        return JsonResponse(
            {"error": "'size' must be a positive integer."}, status=400
        )

    scope = {}
    data: dict[str, Any] = {"results": []}

    # conduct search
    if search_type == "library":
        try:
            page_num = _positive_int(request, "page_num", "1")
        except ValueError:
            return JsonResponse(
                {"error": "'page_num' must be a positive integer."}, status=400
            )
        aggregate_fields = {
            "filtered_text_group": {"terms": {"field": "text_group", "size": 300}}
        }

        data.update({"q": q, "kind": kind, "page_num": page_num, "type": search_type})

        if text_group_urn:
            scope["text_group"] = text_group_urn
            aggregate_fields["filtered_work"] = {
                "terms": {"field": "work", "size": 300}
            }

        if work_urn:
            scope = {}
            scope["work"] = work_urn

        # The page stride is `size`, not a hardcoded 10.
        #
        # It used to be 10 in all three places below while `size` stayed
        # caller-controlled, so the two disagreed whenever a caller asked
        # for anything else: with size=5, page 2 began at result 11 and
        # results 6-10 could not be reached from any page.
        #
        # This is invisible to the frontend, which is why it went unnoticed
        # and why fixing it is safe: static/src/js/library/search/Search.vue
        # never sends `size`, so it gets the default 10 and the arithmetic
        # is unchanged. The reader widget does send `size`, but it also
        # sends an explicit `offset` and does not use this branch.
        offset = (page_num - 1) * size
        kwargs = {
            "search_type": search_type,
            "scope": scope,
            "aggregate_fields": aggregate_fields,
            "kind": kind,
            "offset": offset,
        }
        try:
            sq = SearchQuery(q, **kwargs)
        except Exception:
            return JsonResponse({"error": "Something went wrong."}, status=500)
        total_count = sq.count()
        page = get_pagination_info(total_count, page_num, per_page=size)
        results = sq.search_window(size=size, offset=offset)

        for result in results:
            r = {"passage": apify(result["passage"], with_content=False)}
            if kind == "form":
                r["content"] = result["raw_content"]
            else:
                r["content"] = result["content"]
            data["results"].append(r)

        data.update(
            {
                "text_groups": results.filtered_aggs("filtered_text_group"),
                "works": results.filtered_aggs("filtered_work")
                if text_group_urn
                else None,
                "total_count": total_count,
                "page": page,
            }
        )

    else:
        offset = int(request.GET.get("offset", "0"))
        pivot = request.GET.get("pivot")
        work_urn = request.GET.get("work")
        text_urn = request.GET.get("text")
        passage_urn = request.GET.get("passage")

        if text_group_urn:
            scope["text_group"] = text_group_urn
        elif work_urn:
            scope["work"] = work_urn
        elif text_urn:
            scope["text.urn"] = text_urn
        elif passage_urn:
            scope["urn"] = passage_urn

        query_kwargs = {
            "search_type": search_type,
            "scope": scope,
            "sort_by": "document",
            "kind": kind,
        }
        sq = SearchQuery(q, **query_kwargs)

        if "text.urn" in scope and pivot:
            urn = cts.URN(pivot)
            urn_start = f"{urn.upTo(cts.URN.NO_PASSAGE)}:{urn.reference.start}"
            for doc_offset, doc in enumerate(sq.scan()):
                if doc["_id"] == urn_start:
                    start_offset = max(0, doc_offset - (size // 2))
                    data["pivot"] = {
                        "offset": doc_offset,
                        "start_offset": start_offset,
                        "end_offset": start_offset + size - 1,
                    }
                    offset = start_offset
                    break

        data["total_count"] = sq.count()
        fields = set(request.GET.get("fields", "content,highlights").split(","))

        for result in sq.search_window(size=size, offset=offset):
            r = {"passage": apify(result["passage"], with_content=False)}
            if "content" in fields:
                r["content"] = result["content"]
            if "highlights" in fields:
                r["highlights"] = [dict(w=w, i=i) for w, i in result["highlights"]]
            data["results"].append(r)

    return JsonResponse(data)


def profile(request):
    return render(request, "profile.html", {})


def app(request, *args, **kwargs):
    return render(request, "app.html", {})


def openapi_json(request):
    from .openapi_spec import SPEC
    return JsonResponse(SPEC)


def swagger_ui(request):
    return render(request, "swagger.html", {})


def licenses(request):
    return render(request, "licenses.html", {})
