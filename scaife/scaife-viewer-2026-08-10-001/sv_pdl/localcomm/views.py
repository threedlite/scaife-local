from django.core.paginator import Paginator
from django.http import JsonResponse

from .models import CommentaryEntry
from .refs import parse_urn, ref_key, split_range


PAGE_SIZE = 25


def commentaries_json(request, urn):
    """Return commentary entries whose target passage overlaps `urn`.

    Frontend shape:
      { "results": [{"id","urn","corresp","lemma","content"}, ...],
        "current_page", "total_pages" }
    """
    target_key, ref = parse_urn(urn)
    if not target_key:
        return JsonResponse({"results": [], "current_page": 1, "total_pages": 1})

    q_start, q_end = split_range(ref)
    q_start_k = ref_key(q_start)
    q_end_k = ref_key(q_end) or q_start_k

    qs = CommentaryEntry.objects.filter(commentary__isnull=False, target_key=target_key)
    if q_start_k:
        # Overlap: entry.ref_start <= q_end AND entry.ref_end >= q_start
        qs = qs.filter(ref_start__lte=q_end_k, ref_end__gte=q_start_k)

    qs = qs.select_related("commentary").order_by("ref_start", "id")

    page = int(request.GET.get("page", 1) or 1)
    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(page)

    results = [
        {
            "id": e.id,
            "urn": e.citation_urn or f"local:{e.commentary.slug}:{e.id}",
            "corresp": e.target_urn,
            "lemma": e.lemma,
            "content": e.content_html,
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
