"""A normalised, version-portable snapshot of the ATLAS GraphQL schema.

The GraphQL schema is the contract between the Django backend and the Vue
frontend. Nothing else in the test suite covers it, and the planned
graphene 2 -> 3 migration rewrites the layer that produces it (see
`DJANGO-UPGRADE.md` §2.3). A schema change is therefore the most likely
shape for a silent functionality regression: the frontend asks for a field
that quietly stopped existing, and the reader renders blank rather than
raising.

Why a normalised structure rather than the printed SDL
------------------------------------------------------
`graphql.print_schema` output is not stable across the graphql-core 2 -> 3
boundary that comes with graphene 3 — ordering, description quoting and
whitespace all differ. Diffing raw SDL across that upgrade would produce
hundreds of lines of noise and hide the handful of real changes. The
structure below is what actually constitutes the contract: which types
exist, which fields they expose, and the type of each field and argument.

The extraction deliberately avoids graphql-core-version-specific APIs.
Both the 2.x and 3.x versions of every accessor used here are handled, so
this module keeps working after the upgrade and the two snapshots stay
directly comparable.
"""
from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLUnionType,
)

# Schema format version. Bump if the shape of the emitted dict changes, so a
# stale golden file fails loudly instead of comparing unlike structures.
SNAPSHOT_VERSION = 1


def _type_name(gql_type):
    """SDL spelling of a type reference, e.g. ``[TokenNode!]!``.

    ``__str__`` renders wrapper types this way in both graphql-core 2 and 3.
    """
    return str(gql_type)


def _iter_args(field):
    """Yield ``(name, type_string)`` for a field's arguments.

    graphene 2 builds ``args`` as an OrderedDict; graphql-core 3 uses a plain
    dict; hand-built graphql-core 2 fields use a list of ``GraphQLArgument``
    carrying its own ``name``. Accept all three.
    """
    args = getattr(field, "args", None) or ()
    if isinstance(args, dict):
        items = args.items()
    else:
        items = ((getattr(a, "name", None), a) for a in args)
    for name, arg in items:
        yield name, _type_name(arg.type)


def _fields(gql_type):
    out = {}
    for name, field in (getattr(gql_type, "fields", None) or {}).items():
        entry = {"type": _type_name(field.type)}
        args = dict(_iter_args(field))
        if args:
            entry["args"] = dict(sorted(args.items()))
        # Deprecation is part of the contract: the frontend may still be
        # selecting a deprecated field, so losing it is a regression.
        reason = getattr(field, "deprecation_reason", None)
        if reason:
            entry["deprecated"] = reason
        out[name] = entry
    return dict(sorted(out.items()))


def _enum_values(gql_type):
    values = getattr(gql_type, "values", None) or ()
    if isinstance(values, dict):  # graphql-core 3
        names = list(values)
    else:  # graphql-core 2: list of GraphQLEnumValue
        names = [getattr(v, "name", str(v)) for v in values]
    return sorted(names)


def _interfaces(gql_type):
    return sorted(i.name for i in (getattr(gql_type, "interfaces", None) or ()))


def core_schema(schema):
    """Return the underlying graphql-core schema.

    graphene 2 *is* the graphql-core 2 schema for these purposes. graphene 3
    wraps a graphql-core 3 schema and exposes it as `.graphql_schema`, and
    its `Schema.__getattr__` resolves unknown names as *type lookups* —
    `schema.get_type_map()` raises `AttributeError: Type "get_type_map" not
    found in the Schema` rather than falling through. Normalising here keeps
    the rest of this module version-agnostic.
    """
    return getattr(schema, "graphql_schema", None) or schema


def _root_name(schema, attr_2x, attr_3x):
    """Root type name, tolerating the 2.x method / 3.x attribute split."""
    core = core_schema(schema)
    root = getattr(core, attr_3x, None)
    if root is None:
        getter = getattr(core, attr_2x, None)
        root = getter() if callable(getter) else getter
    return root.name if root is not None else None


def _type_map(schema):
    core = core_schema(schema)
    tm = getattr(core, "type_map", None)
    if tm is None:
        tm = core.get_type_map()
    return tm


def snapshot(schema):
    """Return a deterministic, JSON-serialisable view of ``schema``."""
    types = {}
    for name, gql_type in _type_map(schema).items():
        if name.startswith("__"):  # introspection machinery, not our contract
            continue
        if isinstance(gql_type, GraphQLScalarType):
            types[name] = {"kind": "SCALAR"}
        elif isinstance(gql_type, GraphQLEnumType):
            types[name] = {"kind": "ENUM", "values": _enum_values(gql_type)}
        elif isinstance(gql_type, GraphQLUnionType):
            member_types = getattr(gql_type, "types", None) or ()
            types[name] = {
                "kind": "UNION",
                "types": sorted(t.name for t in member_types),
            }
        elif isinstance(gql_type, GraphQLInputObjectType):
            types[name] = {"kind": "INPUT_OBJECT", "fields": _fields(gql_type)}
        elif isinstance(gql_type, GraphQLInterfaceType):
            types[name] = {"kind": "INTERFACE", "fields": _fields(gql_type)}
        elif isinstance(gql_type, GraphQLObjectType):
            types[name] = {
                "kind": "OBJECT",
                "interfaces": _interfaces(gql_type),
                "fields": _fields(gql_type),
            }
        else:  # pragma: no cover - defensive; a new graphql-core kind
            types[name] = {"kind": type(gql_type).__name__}

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "query": _root_name(schema, "get_query_type", "query_type"),
        "mutation": _root_name(schema, "get_mutation_type", "mutation_type"),
        "subscription": _root_name(
            schema, "get_subscription_type", "subscription_type"
        ),
        "types": dict(sorted(types.items())),
    }


def load_schema():
    """Import the configured schema the same way the GraphQL view does."""
    from django.conf import settings
    from django.utils.module_loading import import_string

    path = settings.GRAPHENE["SCHEMA"]
    return import_string(path)


def diff(golden, current):
    """Human-readable differences between two snapshots.

    Reported at the granularity a reviewer needs during the upgrade: which
    types vanished, which fields vanished, and which field/argument types
    changed shape.
    """
    lines = []

    for key in ("snapshot_version", "query", "mutation", "subscription"):
        if golden.get(key) != current.get(key):
            lines.append(f"{key}: {golden.get(key)!r} -> {current.get(key)!r}")

    gt, ct = golden.get("types", {}), current.get("types", {})

    for name in sorted(set(gt) - set(ct)):
        lines.append(f"type REMOVED: {name} ({gt[name].get('kind')})")
    for name in sorted(set(ct) - set(gt)):
        lines.append(f"type added:   {name} ({ct[name].get('kind')})")

    for name in sorted(set(gt) & set(ct)):
        g, c = gt[name], ct[name]
        if g.get("kind") != c.get("kind"):
            lines.append(f"{name}: kind {g.get('kind')} -> {c.get('kind')}")
            continue
        if g.get("interfaces") != c.get("interfaces"):
            lines.append(
                f"{name}: interfaces {g.get('interfaces')} -> {c.get('interfaces')}"
            )
        if g.get("values") != c.get("values"):
            lines.append(f"{name}: enum values {g.get('values')} -> {c.get('values')}")
        if g.get("types") != c.get("types"):
            lines.append(f"{name}: union members {g.get('types')} -> {c.get('types')}")

        gf, cf = g.get("fields", {}), c.get("fields", {})
        for f in sorted(set(gf) - set(cf)):
            lines.append(f"{name}.{f}: FIELD REMOVED ({gf[f]['type']})")
        for f in sorted(set(cf) - set(gf)):
            lines.append(f"{name}.{f}: field added ({cf[f]['type']})")
        for f in sorted(set(gf) & set(cf)):
            if gf[f].get("type") != cf[f].get("type"):
                lines.append(
                    f"{name}.{f}: type {gf[f]['type']} -> {cf[f]['type']}"
                )
            ga, ca = gf[f].get("args", {}), cf[f].get("args", {})
            for a in sorted(set(ga) - set(ca)):
                lines.append(f"{name}.{f}({a}): ARG REMOVED ({ga[a]})")
            for a in sorted(set(ca) - set(ga)):
                lines.append(f"{name}.{f}({a}): arg added ({ca[a]})")
            for a in sorted(set(ga) & set(ca)):
                if ga[a] != ca[a]:
                    lines.append(f"{name}.{f}({a}): arg type {ga[a]} -> {ca[a]}")

    return lines
