import os
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render

import requests
from scaife_viewer.atlas.models import Repo

from .changelog.keyfile import cachekeys
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
