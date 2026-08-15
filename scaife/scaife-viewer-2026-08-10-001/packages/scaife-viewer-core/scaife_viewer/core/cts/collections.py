from functools import lru_cache, partial

from django.conf import settings

from MyCapytain.common.constants import RDF_NAMESPACES
from rdflib.namespace import RDFS
from MyCapytain.resources.collections.cts import XmlCtsTextInventoryMetadata
from MyCapytain.resources.prototypes.cts import inventory as cts

from ..hooks import hookset
from .capitains import default_resolver
from .exceptions import InvalidPassageReference
from .passage import Passage
from .reference import URN
from .toc import RefTree
from .typing import CtsCollectionMetadata


@lru_cache(maxsize=1)
def load_text_inventory_metadata() -> cts.CtsTextInventoryMetadata:
    resolver_type = settings.CTS_RESOLVER["type"]
    resolver = default_resolver()
    if resolver_type == "api":
        if getattr(settings, "CTS_LOCAL_TEXT_INVENTORY", None) is not None:
            with open(settings.CTS_LOCAL_TEXT_INVENTORY, "r") as fp:
                ti_xml = fp.read()
        else:
            ti_xml = resolver.endpoint.getCapabilities()
        return XmlCtsTextInventoryMetadata.parse(ti_xml)
    elif resolver_type == "local":
        return resolver.getMetadata()["default"]


class TextInventory:
    @classmethod
    def load(cls):
        return cls(load_text_inventory_metadata())

    def __init__(self, metadata: cts.CtsTextInventoryMetadata):
        self.metadata = metadata

    def __repr__(self):
        return f"<cts.TextInventory at {hex(id(self))}>"

    def text_groups(self):
        text_group_urns = self.metadata.textgroups.keys()
        text_groups = []
        for urn in text_group_urns:
            text_group = TextGroup(urn, self.metadata.textgroups[urn])
            if next(text_group.works(), None) is None:
                continue
            text_groups.append(text_group)
        yield from hookset.sort_text_groups(text_groups)



def deterministic_label(metadata, lang="eng", predicate=None):
    """Pick one label for ``lang`` deterministically.

    LOCAL CHANGE (2026-08-14). MyCapytain's ``get_label`` iterates
    ``graph.objects(...)`` and returns the *first* match. rdflib gives no
    ordering guarantee, so when a collection carries several labels in the
    same language the winner depends on the store's internal iteration —
    which changed between Python 3.9 and 3.12. 56 collections in the Perseus
    corpora have more than one English label, and the side-by-side
    comparison in DJANGO-UPGRADE.md §11 found 34 work titles flipping
    between e.g. "Olynthiac 1" and "First Olynthiac" purely as a result.

    The rule is **shortest, then alphabetical**. Shortest is what makes the
    choice useful rather than merely stable: for the New Testament books it
    yields "Matthew", "Mark", "Romans", "1 Corinthians" rather than
    alphabetical's inconsistent mix of "Gospel according to Matthew" and
    "Ephesians"; for Demosthenes it keeps a series consistent
    ("Olynthiac 1/2/3" rather than "First Olynthiac" beside "Olynthiac 2").
    Alphabetical order breaks exact length ties so the result is total.

    Falls back to ``get_label`` when nothing matches ``lang``, preserving
    the previous behaviour for collections that have no label in it.
    """
    if predicate is None:
        predicate = RDFS.label
    try:
        candidates = [
            obj
            for obj in metadata.graph.objects(metadata.asNode(), predicate)
            if getattr(obj, "language", None) == lang
        ]
    except Exception:  # pragma: no cover - defensive; malformed metadata
        candidates = []
    if not candidates:
        return metadata.get_label(lang=lang)
    return min(candidates, key=lambda obj: (len(str(obj)), str(obj)))

class Collection:
    def __init__(self, urn: URN, metadata: CtsCollectionMetadata):
        self.urn = urn
        self.metadata = metadata

    def __repr__(self):
        return f"<cts.Collection {self.urn} at {hex(id(self))}>"

    def __eq__(self, other):
        if type(other) is type(self):
            return self.urn == other.urn
        return NotImplemented

    def __hash__(self):
        return hash(str(self.urn))

    @property
    def label(self):
        # LOCAL CHANGE (2026-08-14): was self.metadata.get_label(lang="eng"),
        # which is non-deterministic when several English labels exist.
        return deterministic_label(self.metadata, lang="eng")

    def ancestors(self):
        for metadata in list(reversed(self.metadata.parents))[1:]:
            cls = resolve_collection(metadata.TYPE_URI)
            # the local resolver returns the text inventory from parents
            # this is isn't a proper ancestor here so we'll ignore it.
            if issubclass(cls, TextInventory):
                continue
            yield cls(metadata.urn, metadata)


class TextGroup(Collection):
    def __repr__(self):
        return f"<cts.TextGroup {self.urn} at {hex(id(self))}>"

    def works(self):
        children = self.metadata.works
        works = []
        for urn in children.keys():
            work = Work(urn, children[urn])
            if next(work.texts(), None) is None:
                continue
            works.append(work)
        yield from hookset.sort_works(works)

    def as_json(self, **kwargs) -> dict:
        return {
            "urn": str(self.urn),
            "label": str(self.label),
            "works": [
                {
                    "urn": str(work.urn),
                    "texts": [{"urn": str(text.urn)} for text in work.texts()],
                }
                for work in self.works()
            ],
        }


class Work(Collection):
    def __repr__(self):
        return f"<cts.Work {self.urn} at {hex(id(self))}>"

    def texts(self):
        children = self.metadata.texts
        texts = []
        for urn in children.keys():
            metadata = children[urn]
            if metadata.citation is None:
                continue
            texts.append(resolve_collection(metadata.TYPE_URI)(urn, metadata))
        yield from hookset.sort_texts(texts)

    def as_json(self, **kwargs) -> dict:
        return {
            "urn": str(self.urn),
            "label": str(self.label),
            "texts": [dict(urn=str(text.urn)) for text in self.texts()],
        }


class Text(Collection):
    def __init__(self, kind, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind

    def __repr__(self):
        return f"<cts.Text {self.urn} kind={self.kind} at {hex(id(self))}>"

    @property
    def description(self):
        return self.metadata.get_description(lang="eng")

    @property
    def lang(self):
        return self.metadata.lang

    @property
    def human_lang(self):
        lang = self.metadata.lang
        return {
            "grc": "Greek",
            "lat": "Latin",
            "heb": "Hebrew",
            "fa": "Farsi",
            "eng": "English",
            "ger": "German",
            "fre": "French",
        }.get(lang, lang)

    @property
    def rtl(self):
        return self.lang in {"heb", "fa"}

    def versions(self):
        for edition in self.metadata.editions():
            yield Text("edition", edition.urn, edition)
        for translation in self.metadata.translations():
            yield Text("translation", translation.urn, translation)

    @lru_cache()
    def toc(self):
        citation = self.metadata.citation
        depth = citation.depth
        tree = RefTree(self.urn, citation)
        try:
            reffs = default_resolver().getReffs(self.urn, level=depth)
            for reff in reffs:
                tree.add(reff)
            return tree
        except InvalidPassageReference as e:
            raise e
        except Exception:
            raise ValueError(f"{self.urn} has an invalid refsDecl")

    def first_passage(self):
        chunk = next(self.toc().chunks(), None)
        if chunk is not None:
            return Passage(self, URN(chunk.urn).reference)

    def as_json(self, **kwargs) -> dict:
        with_toc = kwargs.pop("with_toc", False)
        payload = {
            "urn": str(self.urn),
            "label": str(self.label),
            "description": str(self.description),
            "kind": self.kind,
            "lang": self.lang,
            "rtl": self.rtl,
            "human_lang": self.human_lang,
        }
        if with_toc:
            toc = self.toc()
            payload.update(
                {
                    "first_passage": dict(urn=str(self.first_passage().urn)),
                    "ancestors": [
                        {"urn": str(ancestor.urn), "label": ancestor.label}
                        for ancestor in self.ancestors()
                    ],
                    "toc": [
                        {
                            "urn": next(toc.chunks(ref_node), None).urn,
                            "label": ref_node.label.title(),
                            "num": ref_node.num,
                        }
                        for ref_node in toc.num_resolver.glob(toc.root, "*")
                    ],
                }
            )
        return payload


def resolve_collection(type_uri):
    return {
        RDF_NAMESPACES.CTS.term("TextInventory"): TextInventory,
        RDF_NAMESPACES.CTS.term("textgroup"): TextGroup,
        RDF_NAMESPACES.CTS.term("work"): Work,
        RDF_NAMESPACES.CTS.term("edition"): partial(Text, "edition"),
        RDF_NAMESPACES.CTS.term("translation"): partial(Text, "translation"),
        RDF_NAMESPACES.CTS.term("commentary"): partial(Text, "commentary"),
    }[type_uri]
