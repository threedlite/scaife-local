"""Execute GraphQL queries, not just inspect the schema.

`test_schema_contract.py` pins the *shape* of the schema — which types and
fields exist, and their signatures. That is necessary and it is not
sufficient, as the graphene-django 2.6 → 2.16 bump demonstrated:

    connection_resolver() missing 1 required positional argument: 'info'

`atlas.schema.LimitedConnectionField` overrode `connection_resolver` with
the 2.6 signature. graphene-django 2.16 changed it. The schema built
perfectly, the snapshot was byte-identical for every field involved, and
every paginated query failed **at execution**. In the browser that is a
reader with no text in it and no error anywhere the tests could see.

These tests execute queries against the schema and assert that no GraphQL
error is returned. They deliberately run against the *test* database, which
is empty: the point is to exercise resolver plumbing — connection
resolution, relay wiring, filter argument handling — which breaks
independently of whether rows come back. Empty `edges` is a pass; an entry
in `errors` is not.

Add a query here whenever a new connection field or resolver shape is
introduced, and especially before touching graphene versions again.
"""
from django.test import TestCase

from .schema_snapshot import load_schema

# Each entry is (label, query). Keep them small and shape-focused.
QUERIES = [
    # The exact shape that broke: a LimitedConnectionField invoked with
    # neither `first` nor `last`, which routes through the overridden
    # connection_resolver and its max_limit default.
    (
        "connection without first/last",
        "{ versions { edges { node { urn label } } } }",
    ),
    (
        "connection with first",
        "{ versions(first: 2) { edges { node { urn } } } }",
    ),
    (
        "connection with a filter argument",
        '{ textParts(urn_Startswith: "urn:cts:greekLit:tlg0012", first: 2)'
        " { edges { node { ref } } } }",
    ),
    (
        "nested connections",
        "{ textGroups(first: 1) { edges { node { urn tokens(first: 1)"
        " { edges { node { value } } } } } } }",
    ),
    (
        "relay pageInfo",
        "{ versions(first: 1) { pageInfo { hasNextPage endCursor } edges { cursor } } }",
    ),
    (
        "dictionary connection",
        "{ dictionaries { edges { node { urn label } } } }",
    ),
    (
        "token connection with filter",
        '{ tokens(textPart_Urn: "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1")'
        " { edges { node { value } } } }",
    ),
    (
        "enum-typed filter argument",
        "{ namedEntities(kind: PERSON, first: 1) { edges { node { title } } } }",
    ),
    (
        "introspection",
        "{ __schema { queryType { name } } }",
    ),
]


class GraphQLExecutionTests(TestCase):
    # The ATLAS models live in their own database; without this the test
    # runner does not create it and every query fails on a missing table.
    databases = {"default", "atlas"}

    def test_queries_execute_without_errors(self):
        schema = load_schema()
        for label, query in QUERIES:
            with self.subTest(query=label):
                result = schema.execute(query)
                errors = [str(e) for e in (result.errors or [])]
                self.assertEqual(
                    errors,
                    [],
                    f"GraphQL execution failed for {label!r}:\n"
                    f"  query: {query}\n"
                    f"  errors: {errors}\n"
                    f"An error here means the schema still *builds* but "
                    f"queries do not run — see this module's docstring.",
                )
                self.assertIsNotNone(
                    result.data, f"{label!r} returned no data payload at all"
                )

    def test_a_deliberately_invalid_query_is_reported(self):
        """Guards the guard: if execute() stopped surfacing errors, every
        test above would pass vacuously."""
        result = load_schema().execute("{ thisFieldDoesNotExist }")
        self.assertTrue(
            result.errors, "invalid query produced no error; the check is inert"
        )
