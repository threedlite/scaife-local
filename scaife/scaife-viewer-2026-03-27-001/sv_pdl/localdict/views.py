from django.core.paginator import Paginator
from django.http import JsonResponse

from .models import Dictionary, DictionaryEntry


PAGE_SIZE = 50


def dictionaries_json(request):
    results = []
    for d in Dictionary.objects.all().order_by("id"):
        results.append(
            {
                "id": d.id,
                "label": d.label,
                "data": {},
                "slug": d.slug,
                "urn": d.urn,
                "lang": d.lang,
            }
        )
    return JsonResponse({"results": results})


def dictionary_entries(request, slug):
    try:
        d = Dictionary.objects.get(slug=slug)
    except Dictionary.DoesNotExist:
        return JsonResponse(
            {"results": [], "current_page": 1, "total_pages": 1}, status=404
        )

    q = (request.GET.get("q") or "").strip()
    page = int(request.GET.get("page", 1) or 1)

    qs = DictionaryEntry.objects.filter(dictionary=d)
    if q:
        # normalized-stripped matches lemma (accent/diacritic-agnostic)
        from .normalize import strip_diacritics
        needle = strip_diacritics(q).lower()
        # exact match first; fall back to prefix
        exact = qs.filter(headword_normalized_stripped=needle)
        if exact.exists():
            qs = exact
        else:
            qs = qs.filter(headword_normalized_stripped__startswith=needle)

    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(page)
    results = [
        {
            "id": e.id,
            "headword": e.headword,
            "headword_normalized": e.headword_normalized,
            "headword_normalized_stripped": e.headword_normalized_stripped,
            "intro_text": e.intro_text,
        }
        for e in page_obj
    ]
    return JsonResponse(
        {
            "results": results,
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
        }
    )
