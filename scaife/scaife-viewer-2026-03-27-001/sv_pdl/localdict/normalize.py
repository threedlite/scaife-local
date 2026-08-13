import unicodedata


def strip_diacritics(s: str) -> str:
    # NFD, drop combining marks, keep base letters
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", s)
        if not unicodedata.combining(ch)
    )


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)
