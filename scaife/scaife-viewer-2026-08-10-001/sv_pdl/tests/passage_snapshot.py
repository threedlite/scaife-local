"""Characterisation snapshot of CTS passage rendering.

`scaife_viewer.core` is 3,274 lines covering CTS resolution, reference
healing and tokenisation, and it ships essentially no tests of its own
(`core/tests/tests.py` is 42 lines). The reader renders whatever this code
returns. A Django, MyCapytain or lxml upgrade that subtly changes
tokenisation, offsets or reference expansion therefore has nothing standing
in its way — and the resulting damage is silent, because the page still
renders, just with different words or misaligned annotation offsets.

The payload captured here is `Passage.as_json()`, which is what the reader
actually consumes, plus the navigation links around it. In particular
`word_tokens` carries each token's index and character offset; annotation
highlighting is positioned from those numbers, so an off-by-one is a real
user-visible defect that no other test would catch.

These are characterisation tests, not correctness tests: they assert that
behaviour is *unchanged*, and they take today's behaviour as correct by
definition. That is the appropriate instrument for an upgrade whose goal is
"no functionality regressions".
"""

# A deliberately small set that spans the structural variety of the corpus,
# because the code paths differ by shape rather than by author: line-based
# verse vs. section-based prose, Greek vs. Latin (different tokenisation and
# normalisation), a range vs. a single reference, and a translation (whose
# reference scheme does not align with its edition's).
GOLDEN_URNS = [
    # Greek verse, multi-line range: the reader's most common shape.
    "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1-1.5",
    # Greek prose, three-level reference (book.chapter.section).
    "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2:1.1.1",
    # Greek drama: line numbering without a book level.
    "urn:cts:greekLit:tlg0006.tlg001.perseus-grc2:1-5",
    # Latin verse: different tokenisation and no final sigma handling.
    "urn:cts:latinLit:phi0690.phi003.perseus-lat2:1.1-1.5",
    # Latin prose, single reference rather than a range.
    "urn:cts:latinLit:phi0474.phi013.perseus-lat2:1.1",
    # Latin verse, second work: guards against a corpus-specific fluke.
    "urn:cts:latinLit:phi0959.phi006.perseus-lat2:1.1-1.5",
    # English translation. Its reference scheme does not match the Greek
    # edition's: "1.1" here is a ~350-token block, not one line, and
    # "1.1-1.10" does not resolve at all. That mismatch is exactly what
    # breaks when reference handling or range expansion changes.
    "urn:cts:greekLit:tlg0012.tlg001.perseus-eng3:1.1",
]


def capture_one(urn):
    """Return the JSON-serialisable characterisation payload for ``urn``.

    The result is round-tripped through JSON before being returned. That is
    not cosmetic: `as_json()` embeds `rdflib.term.Literal` objects for
    collection labels, and although those serialise to ordinary strings,
    `Literal("Iliad", lang="eng") == "Iliad"` is False — a language-tagged
    literal does not compare equal to a bare string. Without the round-trip
    every comparison against the stored golden file would fail on labels
    that are in fact identical.
    """
    import json

    from scaife_viewer.core.cts import passage

    p = passage(urn)
    payload = p.as_json()

    # Navigation is part of the reading experience and is computed
    # separately from as_json(); a broken next/prev strands the reader at
    # the end of a passage.
    def _nav(getter):
        try:
            node = getter()
        except Exception as exc:  # a raising next/prev is itself the finding
            return f"ERROR: {type(exc).__name__}"
        return str(node.urn) if node is not None else None

    payload["_next"] = _nav(p.next)
    payload["_prev"] = _nav(p.prev)
    return json.loads(json.dumps(payload, ensure_ascii=False))


def capture(urns=None):
    """Capture every URN in ``urns`` (default: :data:`GOLDEN_URNS`)."""
    return {urn: capture_one(urn) for urn in (urns or GOLDEN_URNS)}


def diff_payload(urn, golden, current):
    """Human-readable differences for a single passage.

    Token lists are compared element-wise and reported by index, because a
    whole-list diff of several hundred tokens is unreadable and the
    interesting case is almost always a handful of shifted offsets.
    """
    lines = []

    for key in sorted(set(golden) | set(current)):
        g, c = golden.get(key), current.get(key)
        if g == c:
            continue
        if key == "word_tokens" and isinstance(g, list) and isinstance(c, list):
            if len(g) != len(c):
                lines.append(f"{urn}: word_tokens count {len(g)} -> {len(c)}")
            for i, (gt, ct) in enumerate(zip(g, c)):
                if gt != ct:
                    lines.append(f"{urn}: word_tokens[{i}] {gt} -> {ct}")
                    if len([x for x in lines if "word_tokens[" in x]) >= 10:
                        lines.append(f"{urn}: ... further token differences elided")
                        break
        elif isinstance(g, str) and isinstance(c, str):
            lines.append(f"{urn}: {key} changed\n    golden:  {g[:200]!r}\n    current: {c[:200]!r}")
        else:
            lines.append(f"{urn}: {key} {g!r} -> {c!r}")

    return lines
