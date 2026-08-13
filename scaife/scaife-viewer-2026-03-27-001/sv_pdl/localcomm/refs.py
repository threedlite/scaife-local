"""URN + reference helpers for commentary passage matching."""
import re


def parse_urn(urn):
    """Return (target_key, ref) or (None, None).

    target_key normalizes to "ns:textgroup.work" (without version) so a
    commentary that cites "tlg0012.tlg001" matches a passage under
    "tlg0012.tlg001.perseus-grc2".
    """
    if not urn or not urn.startswith("urn:cts:"):
        return None, None
    body = urn[len("urn:cts:"):].strip()
    # Optional passage ref after the last colon
    parts = body.split(":", 2)
    if len(parts) < 2:
        return None, None
    ns = parts[0]
    work_full = parts[1]
    ref = parts[2] if len(parts) >= 3 else ""
    # Canonical work is at most 2 dotted parts (textgroup.work). A 3rd part
    # is the version (edition) which we drop for cross-edition matching.
    dotted = work_full.split(".")
    work = ".".join(dotted[:2]) if dotted else work_full
    return f"{ns}:{work}", ref


# Match "1.1@προΐαψεν" -> ("1.1", "@προΐαψεν"); we drop the @word portion
# for passage-range comparison but keep the raw target_urn as-is.
_TOKEN_RE = re.compile(r"^([^@]+?)(?:@.*)?$")


def _clean_token(tok):
    m = _TOKEN_RE.match(tok.strip())
    return m.group(1) if m else tok.strip()


def split_range(ref):
    """"1.1-1.12" -> ("1.1", "1.12"); "1.1" -> ("1.1", "1.1")."""
    if not ref:
        return "", ""
    if "-" in ref:
        a, b = ref.split("-", 1)
        return _clean_token(a), _clean_token(b)
    return _clean_token(ref), _clean_token(ref)


def ref_key(ref):
    """Convert "1.11" to a lexicographically-sortable zero-padded string:
    "000001.000011". Strips any "@word" suffix on the last token."""
    if not ref:
        return ""
    ref = _clean_token(ref)
    parts = []
    for token in ref.split("."):
        m = re.match(r"^(\d+)(.*)$", token)
        if m:
            num = int(m.group(1))
            tail = m.group(2)
            parts.append(f"{num:06d}{tail}")
        else:
            parts.append(token)
    return ".".join(parts)
