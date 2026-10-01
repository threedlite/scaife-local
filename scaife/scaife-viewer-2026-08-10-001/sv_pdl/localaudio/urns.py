"""URN helpers for audio lookups.

Audio is edition-specific (a clip recorded from perseus-grc3 is not a clip
of perseus-grc4), so unlike `sv_pdl.localcomm.refs.parse_urn` the version
part of the URN is kept.
"""
import os

# Repo directory names under CTS_LOCAL_DATA_PATH, by CTS namespace.
_CORPUS_DIRS = {
    "greekLit": "PerseusDL-canonical-greekLit-local",
    "latinLit": "PerseusDL-canonical-latinLit-local",
    "pdlrefwk": "PerseusDL-canonical-pdlrefwk-local",
}


def split_passage_urn(urn):
    """"urn:cts:greekLit:tlg0020.tlg001.perseus-grc2:1-30"
    -> ("urn:cts:greekLit:tlg0020.tlg001.perseus-grc2", "1-30").

    Returns (None, None) for anything that is not a CTS URN with a version
    and a passage reference.
    """
    if not urn or not urn.startswith("urn:cts:"):
        return None, None
    parts = urn.split(":")
    # urn, cts, namespace, work, ref
    if len(parts) != 5:
        return None, None
    version_urn = ":".join(parts[:4])
    ref = parts[4].strip()
    work = parts[3]
    if not ref or len(work.split(".")) != 3:
        return None, None
    return version_urn, ref


def tei_path_for_version(version_urn, data_path):
    """Best-effort path of the TEI file behind a version URN on the local
    CTS mount, or None. Layout: <data_path>/<repo>/data/<tg>/<work>/<tg>.<work>.<version>.xml
    """
    parts = version_urn.split(":")
    if len(parts) != 4:
        return None
    ns, work = parts[2], parts[3]
    repo = _CORPUS_DIRS.get(ns)
    dotted = work.split(".")
    if not repo or len(dotted) != 3:
        return None
    tg, wk, _version = dotted
    path = os.path.join(data_path, repo, "data", tg, wk, f"{work}.xml")
    return path if os.path.exists(path) else None
