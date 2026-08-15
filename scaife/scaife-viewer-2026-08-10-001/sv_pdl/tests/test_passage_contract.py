"""Characterisation tests for CTS passage rendering.

See `passage_snapshot.py` for why these exist: `scaife_viewer.core` renders
the reader and has essentially no tests, so an upgrade can change the text,
the tokenisation or the annotation offsets without anything failing.

Tagged `integration` because they read the mounted Perseus corpora. Run:

    bash scripts/run-tests.sh --integration

Regenerating the snapshot
-------------------------
    bash scripts/capture-golden.sh passages

Only for an intended change, and read the diff. A changed `text` is a
changed reading; a changed `word_tokens` offset silently misplaces every
annotation highlight in that passage.
"""
import json
import os

from django.test import SimpleTestCase, tag

from .passage_snapshot import GOLDEN_URNS, capture_one, diff_payload

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "passages.json")


def _load_golden():
    with open(GOLDEN_PATH, encoding="utf-8") as fp:
        raw = fp.read()
    try:
        return json.loads(raw)
    except ValueError as exc:
        # A malformed golden file is a capture problem, not a data problem,
        # and the bare JSONDecodeError does not say so. This has happened:
        # the app writes to stdout during CTS resolution ("Unable to parse
        # <file>" for corpus files with a bad refsDecl), and an early
        # version of scripts/capture-golden.sh redirected stdout straight
        # into this file.
        raise AssertionError(
            f"{GOLDEN_PATH} is not valid JSON ({exc}). It starts:\n"
            f"    {raw[:200]!r}\n"
            f"Regenerate it with: bash scripts/capture-golden.sh passages"
        ) from exc


@tag("integration")
class PassageCharacterisationTests(SimpleTestCase):
    def test_golden_covers_the_configured_urn_set(self):
        """A URN added to GOLDEN_URNS without a re-capture would otherwise
        silently go untested."""
        golden = _load_golden()
        missing = [urn for urn in GOLDEN_URNS if urn not in golden]
        self.assertEqual(
            missing,
            [],
            f"golden/passages.json is missing {missing}; regenerate with "
            f"bash scripts/capture-golden.sh passages",
        )

    def test_passages_render_identically(self):
        golden = _load_golden()
        failures = []
        for urn in GOLDEN_URNS:
            expected = golden.get(urn)
            if expected is None:
                continue  # reported by the coverage test above
            with self.subTest(urn=urn):
                try:
                    current = capture_one(urn)
                except Exception as exc:
                    self.fail(
                        f"{urn} no longer resolves at all: "
                        f"{type(exc).__name__}: {exc}"
                    )
                if expected != current:
                    report = "\n".join(diff_payload(urn, expected, current))
                    failures.append(report)
                    self.fail(
                        f"CTS rendering changed for {urn}:\n{report}\n\n"
                        f"If intended, regenerate with:\n"
                        f"  bash scripts/capture-golden.sh passages"
                    )


@tag("integration")
class PassageInvariantTests(SimpleTestCase):
    """Properties that must hold regardless of what the golden file says.

    These survive a careless golden refresh, so they still catch an upgrade
    that empties the reader and gets the snapshot regenerated along with it.
    """

    def test_every_passage_has_text_and_tokens(self):
        for urn in GOLDEN_URNS:
            with self.subTest(urn=urn):
                payload = capture_one(urn)
                self.assertTrue(
                    payload.get("text_html"), f"{urn} rendered no HTML"
                )
                self.assertTrue(
                    payload.get("word_tokens"), f"{urn} produced no word tokens"
                )

    def test_token_offsets_are_monotonic(self):
        """Annotation highlighting indexes into the text by these offsets, so
        a non-increasing sequence means misplaced highlights rather than an
        obvious error."""
        for urn in GOLDEN_URNS:
            with self.subTest(urn=urn):
                offsets = [t["o"] for t in capture_one(urn)["word_tokens"]]
                bad = [
                    i
                    for i in range(1, len(offsets))
                    if offsets[i] < offsets[i - 1]
                ]
                self.assertEqual(
                    bad,
                    [],
                    f"{urn}: token offsets decrease at indices {bad[:5]}",
                )
