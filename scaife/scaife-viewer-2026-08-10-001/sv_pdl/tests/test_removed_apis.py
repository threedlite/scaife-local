"""Static scan for Django APIs that later versions remove.

The Django upgrade (`DJANGO-UPGRADE.md` §10) is blocked less by hard
problems than by a long tail of small ones, each of which fails only once
the framework has already moved. Finding them by running Django 5.2 and
reading tracebacks is the expensive order; finding them by grep while still
on 2.2 is the cheap one.

Two categories, deliberately treated differently:

`REMOVED_NOW_FIXABLE` — APIs whose modern spelling already exists in Django
2.2, so the rename is behaviour-preserving and can be done today. These must
stay at zero. `ugettext*` was the whole of this category and was cleared on
2026-08-14; the entries remain so a re-import, or an upstream re-sync of the
vendored packages, fails here rather than at Django 4.0.

`DEFERRED` — items that cannot be changed yet because the replacement does
not exist in 2.2, or because changing them now would alter behaviour. These
are pinned to an exact expected set rather than forbidden: a new occurrence
fails the test, and so does removing one without updating the table, which
keeps the list honest as the upgrade proceeds.

The scan covers `sv_pdl/` and the vendored `packages/`, since those are now
equally ours to fix.
"""
import io
import os
import re
import tokenize

from django.test import SimpleTestCase

# The application root inside the image: .../src/sv_pdl/tests -> .../src
SRC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_ROOTS = ["sv_pdl", "packages"]

# This module necessarily contains every pattern it searches for.
SELF = os.path.basename(__file__)

# Files exempt from the scan because their *purpose* is to define these
# names. sv_pdl/django_compat.py restores the handful of APIs that
# unmaintained dependencies still import; flagging it would be flagging the
# fix. Everything else in the tree is still checked, including whether the
# shim is still needed — see test_django_compat.py.
EXEMPT = {
    SELF,
    "django_compat.py",
    # Exercises the shim by calling the restored names directly.
    "test_django_compat.py",
}

# pattern -> (removed in Django, replacement / note)
REMOVED_NOW_FIXABLE = {
    r"\bugettext\b": ("4.0", "gettext"),
    r"\bugettext_lazy\b": ("4.0", "gettext_lazy"),
    r"\bugettext_noop\b": ("4.0", "gettext_noop"),
    r"\bungettext\b": ("4.0", "ngettext"),
    r"\bforce_text\b": ("4.0", "force_str"),
    r"\bsmart_text\b": ("4.0", "smart_str"),
    r"\bis_ajax\b": ("4.0", "check the Accept header explicitly"),
    r"\bproviding_args\b": ("4.0", "drop the argument; it was documentation only"),
    r"\bNullBooleanField\b": ("4.0", "BooleanField(null=True)"),
    # Matches any import list containing `url`, not just a bare
    # `import url` — the vendored core's test URLconf writes
    # `from django.conf.urls import include, url`, which the narrower
    # pattern missed entirely.
    r"from django\.conf\.urls import [^\n]*\burl\b": (
        "4.0",
        "django.urls.re_path",
    ),
    r"\brender_to_response\b": ("3.0", "render()"),
    r"\bindex_together\b": ("5.1", "Meta.indexes"),
}

# pattern -> (removed in Django, expected occurrences as "relpath:line", note)
# Both former entries — USE_L10N and STATICFILES_STORAGE — were resolved on
# 2026-08-14 when the stack reached Django 5.2, so the table is empty. It is
# kept rather than deleted because the next framework move will need it, and
# because an empty expected-set is itself meaningful: nothing is currently
# waiting on a future Django version.
DEFERRED = {}


# Directories that are never source. `build/` matters specifically: pip
# builds the vendored packages in place inside the image, leaving a complete
# second copy of each tree at packages/<pkg>/build/lib/. Scanning it doubles
# every hit and reports paths that do not exist in the repository, which
# makes a failure here actively misleading.
SKIP_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    "build",
    "dist",
    ".eggs",
    ".tox",
}


def _python_files():
    for scan_root in SCAN_ROOTS:
        root = os.path.join(SRC_ROOT, scan_root)
        if not os.path.isdir(root):  # packages/ absent in a partial checkout
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in SKIP_DIRS and not d.endswith(".egg-info")
            ]
            for name in filenames:
                if not name.endswith(".py") or name in EXEMPT:
                    continue
                path = os.path.join(dirpath, name)
                yield os.path.relpath(path, SRC_ROOT), path


def _mask_comments_and_strings(source):
    """Blank out comments and string literals, preserving line/column layout.

    The scan must flag *use* of a removed API, not *mention* of one. This
    file, the vendored packages' comments and several docstrings all discuss
    `ugettext_lazy` and friends by name — matching those is a false positive
    that trains people to ignore the canary. Replacing the offending regions
    with spaces rather than deleting them keeps line numbers and offsets
    accurate for reporting.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source  # unparseable: fall back to matching raw text

    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(row, col):
        return starts[row - 1] + col

    masked = list(source)
    for tok_type, _, (srow, scol), (erow, ecol), _ in tokens:
        if tok_type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        for i in range(offset(srow, scol), min(offset(erow, ecol), len(masked))):
            if masked[i] != "\n":
                masked[i] = " "
    return "".join(masked)


def _scan(pattern):
    """Return ["relpath:line: text", ...] for every match of ``pattern``."""
    regex = re.compile(pattern, re.MULTILINE)
    hits = []
    for relpath, path in _python_files():
        try:
            with open(path, encoding="utf-8") as fp:
                source = fp.read()
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        masked = _mask_comments_and_strings(source)
        raw_lines = source.splitlines()
        for lineno, line in enumerate(masked.splitlines(), 1):
            if regex.search(line):
                hits.append(f"{relpath}:{lineno}: {raw_lines[lineno - 1].strip()}")
    return sorted(hits)


class RemovedApiTests(SimpleTestCase):
    def test_no_apis_that_can_already_be_replaced(self):
        offenders = []
        for pattern, (removed_in, replacement) in REMOVED_NOW_FIXABLE.items():
            for hit in _scan(pattern):
                offenders.append(f"[removed in Django {removed_in}] {hit}")
                offenders.append(f"    use: {replacement}")
        self.assertEqual(
            offenders,
            [],
            "Django APIs that later versions remove, whose replacements "
            "already work on 2.2:\n" + "\n".join(offenders),
        )

    def test_deferred_items_match_the_expected_set(self):
        """Pinned rather than forbidden — see this module's docstring."""
        for pattern, (removed_in, expected_files, note) in DEFERRED.items():
            with self.subTest(pattern=pattern):
                found_files = {hit.split(":", 1)[0] for hit in _scan(pattern)}
                self.assertEqual(
                    found_files,
                    expected_files,
                    f"\n{pattern} (removed in Django {removed_in})\n"
                    f"  expected in: {sorted(expected_files)}\n"
                    f"  found in:    {sorted(found_files)}\n"
                    f"  {note}\n"
                    f"  If this was resolved, update DEFERRED in {SELF}.",
                )


class ScanSanityTests(SimpleTestCase):
    """The scan is only meaningful if it is actually reading the tree."""

    def test_scan_covers_both_roots(self):
        seen = {relpath.split(os.sep)[0] for relpath, _ in _python_files()}
        self.assertIn("sv_pdl", seen)
        self.assertIn(
            "packages",
            seen,
            "the vendored packages were not scanned; SCAN_ROOTS or the image "
            "layout has changed",
        )

    def test_scan_finds_a_known_present_string(self):
        """Guards against a regex/encoding change silently matching nothing."""
        self.assertTrue(
            _scan(r"^DEFAULT_AUTO_FIELD\b"),
            "scan found no DEFAULT_AUTO_FIELD, but settings.py sets it",
        )

    def test_mentions_in_comments_and_docstrings_are_not_flagged(self):
        """The scan must catch use, not discussion. Several files in this
        repo name these APIs in prose while explaining why they were
        removed."""
        source = (
            '"""A docstring mentioning ugettext_lazy and force_text."""\n'
            "# a comment mentioning NullBooleanField\n"
            "x = 1  # and is_ajax here too\n"
        )
        masked = _mask_comments_and_strings(source)
        for token in ("ugettext_lazy", "force_text", "NullBooleanField", "is_ajax"):
            self.assertNotIn(token, masked)
        self.assertEqual(len(masked.splitlines()), len(source.splitlines()))

    def test_real_usage_is_still_flagged(self):
        """The masking must not hide actual code."""
        source = "from django.utils.translation import ugettext_lazy as _\n"
        self.assertIn("ugettext_lazy", _mask_comments_and_strings(source))

    def test_build_artifacts_are_not_scanned(self):
        """pip leaves a full second copy of each vendored package under
        packages/<pkg>/build/lib/ inside the image. Reporting a hit there
        would point at a path that does not exist in the repository."""
        offenders = [r for r, _ in _python_files() if f"{os.sep}build{os.sep}" in r]
        self.assertEqual(
            offenders[:5],
            [],
            f"{len(offenders)} build-artifact files were scanned; SKIP_DIRS "
            f"is not doing its job",
        )
