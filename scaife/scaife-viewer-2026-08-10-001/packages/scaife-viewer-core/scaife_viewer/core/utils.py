import logging
import math

from django.urls import reverse

from . import cts
from .conf import settings


logger = logging.getLogger(__name__)


def link_collection(urn) -> dict:
    return {
        "url": reverse("library_collection", kwargs={"urn": urn}),
        "json_url": reverse("api:library_collection", kwargs={"urn": urn}),
        "text_url": reverse("api:library_passage_text", kwargs={"urn": urn}),
    }


def link_passage(urn) -> dict:
    return {
        "url": reverse("reader", kwargs={"urn": urn}),
        "json_url": reverse("api:library_passage", kwargs={"urn": urn}),
        "text_url": reverse("api:library_passage_text", kwargs={"urn": urn}),
    }


def apify(obj, **kwargs):
    remaining = obj.as_json(**kwargs)
    rels = {}
    if isinstance(obj, cts.TextGroup):
        works = remaining.pop("works")
        rels = {
            "works": [
                {
                    **link_collection(work["urn"]),
                    **work,
                    "texts": [
                        {**link_collection(text["urn"]), **text}
                        for text in work["texts"]
                    ],
                }
                for work in works
            ]
        }
    if isinstance(obj, cts.Work):
        texts = remaining.pop("texts")
        rels = {"texts": [{**link_collection(text["urn"]), **text} for text in texts]}
    if isinstance(obj, cts.Text):
        if kwargs.get("with_toc", False):
            first_passage = remaining.pop("first_passage")
            ancestors = remaining.pop("ancestors")
            toc = remaining.pop("toc")
            rels = {
                "first_passage": {
                    **link_passage(first_passage["urn"]),
                    **first_passage,
                },
                "ancestors": [
                    {**link_collection(ancestor["urn"]), **ancestor}
                    for ancestor in ancestors
                ],
                "toc": [{**link_passage(entry["urn"]), **entry} for entry in toc],
            }
        else:
            rels = {}
    if isinstance(obj, cts.Collection):
        links = link_collection(str(obj.urn))
        if isinstance(obj, cts.Text):
            links.update(
                {
                    "reader_url": reverse(
                        "library_text_redirect", kwargs={"urn": obj.urn}
                    )
                }
            )
    if isinstance(obj, cts.Passage):
        links = link_passage(str(obj.urn))
        text = remaining.pop("text")
        text_ancestors = text.pop("ancestors")
        rels = {
            "text": {
                **link_collection(text["urn"]),
                "ancestors": [
                    {**link_collection(ancestor["urn"]), **ancestor}
                    for ancestor in text_ancestors
                ],
                **text,
            }
        }
    return {**links, **rels, **remaining}


def encode_link_header(lo: dict):
    links = []
    for rel, attrs in lo.items():
        link = []
        link.append(f"<{attrs.pop('target')}>")
        for k, v in {"rel": rel, **attrs}.items():
            link.append(f'{k}="{v}"')
        links.append("; ".join(link))
    return ", ".join(links)


def get_pagination_info(total_count, page_num, per_page=10):
    """Pagination metadata for the search JSON API.

    LOCAL CHANGE (see packages/README.md). Two fixes over upstream:

    * `per_page` was hardcoded to 10 in all five expressions below, while
      the caller's `size` was free to differ. Callers passing any other
      size got page boundaries that did not line up with the results they
      received. It defaults to 10, so callers that do not pass it — the
      Vue frontend, and core's own search view — are unaffected.

    * An empty result set reported `num_pages: 0`, because the count was
      computed arithmetically rather than through Django's Paginator.
      Paginator yields one (empty) page instead, and reports start and end
      indices of 0 rather than pointing at a range of rows that do not
      exist. Both are matched here: previously a search with no hits
      returned "showing 1-10 of 0, page 1 of 0".
    """
    num_pages = max(1, int(math.ceil(total_count / per_page)))
    has_previous = page_num > 1
    has_next = page_num < num_pages
    if total_count == 0:
        start_index = 0
        end_index = 0
    else:
        start_index = ((page_num - 1) * per_page) + 1
        end_index = min(page_num * per_page, total_count)
    return {
        "number": page_num,
        "start_index": start_index,
        "end_index": end_index,
        "has_previous": has_previous,
        "has_next": has_next,
        "num_pages": num_pages,
    }


def normalize_urn(urn):
    if not settings.SCAIFE_VIEWER_CORE_ALLOW_TRAILING_COLON and urn.endswith(":"):
        new_urn = urn[:-1]
        msg = f'Normalized "{urn}" to "{new_urn}"'
        logger.info(msg)
        return new_urn
    return urn
