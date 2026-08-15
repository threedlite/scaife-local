"""The GraphQL schema is a contract with the frontend; pin it.

Everything the reader, library and dictionary widgets display arrives over
`/graphql/`. Until now nothing in the suite covered that surface, so a
change to it — deliberate or incidental — produced no test failure. The
planned graphene 2 -> 3 migration rewrites exactly this layer
(`DJANGO-UPGRADE.md` §2.3), and its most likely failure mode is not an
import error but a quietly altered schema: a renamed field, a dropped
argument, a scalar that changed type. The frontend then renders nothing
where it used to render text, and no test notices.

These tests compare the live schema against a committed snapshot. They need
no database and no network, so they run in the default (non-integration)
suite.

Regenerating the snapshot
-------------------------
    bash scripts/capture-golden-schema.sh

Do that only for an *intended* change, and review the reported diff field by
field. During the graphene upgrade specifically:

  * "field added" is usually benign.
  * "FIELD REMOVED" / "ARG REMOVED" / a changed field type is a regression
    until proven otherwise — check whether the frontend selects it before
    accepting the change.
  * graphene 3 requires every `DjangoObjectType.Meta` to declare `fields`
    or `exclude`; all 17 of them currently rely on the implicit all-fields
    behaviour that 3.x removed. `golden/atlas_schema.json` is the record of
    what those implicit lists resolve to today, and is the correct source
    for writing the explicit ones.
"""
import json
import os

from django.test import SimpleTestCase

from .schema_snapshot import SNAPSHOT_VERSION, diff, load_schema, snapshot

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "atlas_schema.json")

# Root fields the frontend cannot render the core reading experience
# without. Spelled out separately from the snapshot so that a careless
# regeneration of the golden file still fails here.
REQUIRED_QUERY_FIELDS = [
    "passageTextParts",
    "textParts",
    "versions",
    "dictionaries",
    "dictionaryEntries",
    "tokens",
]


def _load_golden():
    with open(GOLDEN_PATH) as fp:
        return json.load(fp)


class SchemaContractTests(SimpleTestCase):
    def test_schema_matches_golden_snapshot(self):
        golden = _load_golden()
        current = snapshot(load_schema())
        if golden != current:
            report = "\n".join(f"  {line}" for line in diff(golden, current))
            self.fail(
                "The GraphQL schema no longer matches "
                "sv_pdl/tests/golden/atlas_schema.json:\n"
                f"{report}\n\n"
                "If every change above is intended, regenerate with:\n"
                "  bash scripts/capture-golden-schema.sh\n"
                "See this module's docstring before accepting removals."
            )

    def test_golden_snapshot_version_is_current(self):
        """A stale golden file must fail loudly, not compare unlike shapes."""
        self.assertEqual(
            _load_golden().get("snapshot_version"),
            SNAPSHOT_VERSION,
            "golden/atlas_schema.json was written by a different version of "
            "schema_snapshot.py; regenerate it with "
            "scripts/capture-golden-schema.sh",
        )


class SchemaSanityTests(SimpleTestCase):
    """Assertions that hold independently of the snapshot's contents.

    These survive a regeneration of the golden file, so they still catch an
    upgrade that guts the schema and gets the snapshot refreshed along with
    it.
    """

    def test_query_root_exposes_reader_entry_points(self):
        current = snapshot(load_schema())
        query_type = current["query"]
        self.assertIsNotNone(query_type, "schema has no Query root")
        fields = current["types"][query_type]["fields"]
        missing = [f for f in REQUIRED_QUERY_FIELDS if f not in fields]
        self.assertEqual(
            missing,
            [],
            f"Query root lost reader entry points: {missing}. The reader and "
            f"dictionary widgets query these directly.",
        )

    def test_every_object_type_exposes_fields(self):
        """graphene 3's explicit-fields requirement is easy to get wrong in a
        way that yields a type with no fields rather than an error."""
        current = snapshot(load_schema())
        composite = {"OBJECT", "INTERFACE", "INPUT_OBJECT"}
        empty = sorted(
            name
            for name, spec in current["types"].items()
            if spec["kind"] in composite and not spec.get("fields")
        )
        self.assertEqual(empty, [], f"types with no fields: {empty}")

    def test_relay_node_interface_is_intact(self):
        """Every paginated list the frontend renders goes through relay."""
        current = snapshot(load_schema())
        self.assertIn("Node", current["types"], "relay Node interface is gone")
        implementers = [
            name
            for name, spec in current["types"].items()
            if "Node" in spec.get("interfaces", [])
        ]
        self.assertGreater(
            len(implementers),
            10,
            f"only {len(implementers)} types implement Node; the relay layer "
            f"is probably half-migrated",
        )
