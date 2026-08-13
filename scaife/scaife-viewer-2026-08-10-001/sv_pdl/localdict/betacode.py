"""Minimal TLG-style Beta Code -> polytonic Greek Unicode converter."""

BASE = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ", "h": "η",
    "q": "θ", "i": "ι", "k": "κ", "l": "λ", "m": "μ", "n": "ν", "c": "ξ",
    "o": "ο", "p": "π", "r": "ρ", "s": "σ", "t": "τ", "u": "υ", "f": "φ",
    "x": "χ", "y": "ψ", "w": "ω",
}

CAPS = {
    "a": "Α", "b": "Β", "g": "Γ", "d": "Δ", "e": "Ε", "z": "Ζ", "h": "Η",
    "q": "Θ", "i": "Ι", "k": "Κ", "l": "Λ", "m": "Μ", "n": "Ν", "c": "Ξ",
    "o": "Ο", "p": "Π", "r": "Ρ", "s": "Σ", "t": "Τ", "u": "Υ", "f": "Φ",
    "x": "Χ", "y": "Ψ", "w": "Ω",
}

# Combining marks
COMBINE = {
    ")": "̓",   # smooth breathing
    "(": "̔",   # rough breathing
    "/": "́",   # acute
    "\\": "̀",  # grave
    "=": "͂",   # circumflex (perispomeni)
    "|": "ͅ",   # iota subscript
    "+": "̈",   # diaeresis
}

DIACRITICS = set(COMBINE.keys()) | {"_", "^"}


def beta_to_unicode(s: str) -> str:
    """Convert a single beta-code token (typically a headword) to Unicode."""
    if not s:
        return ""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        # Uppercase marker
        if ch == "*":
            i += 1
            # Uppercase may be followed by diacritics before the letter
            leading_marks = []
            while i < len(s) and s[i] in DIACRITICS:
                if s[i] not in ("_", "^"):
                    leading_marks.append(COMBINE[s[i]])
                i += 1
            if i >= len(s):
                break
            letter = s[i].lower()
            base = CAPS.get(letter, s[i])
            i += 1
            # Trailing diacritics (rare after *)
            trailing_marks = []
            while i < len(s) and s[i] in DIACRITICS:
                if s[i] not in ("_", "^"):
                    trailing_marks.append(COMBINE[s[i]])
                i += 1
            out.append(base + "".join(leading_marks) + "".join(trailing_marks))
            continue

        letter = ch.lower()
        base = BASE.get(letter, ch)
        i += 1
        marks = []
        while i < len(s) and s[i] in DIACRITICS:
            if s[i] not in ("_", "^"):
                marks.append(COMBINE[s[i]])
            i += 1
        out.append(base + "".join(marks))

    import unicodedata
    result = unicodedata.normalize("NFC", "".join(out))
    # Final sigma: σ -> ς at end of word or before non-alphabetic
    fixed = []
    for i, ch in enumerate(result):
        if ch == "σ":
            j = i + 1
            # skip combining marks after
            while j < len(result) and unicodedata.combining(result[j]):
                j += 1
            # if next char isn't a Greek letter, use final sigma
            greek_letters = "άέήίόύώϊϋΐΰἀἁἂἃἄἅἆἇἐἑἒἓἔἕἠἡἢἣἤἥἦἧἰἱἲἳἴἵἶἷὀὁὂὃὄὅὐὑὒὓὔὕὖὗὠὡὢὣὤὥὦὧᾀᾁᾂᾃᾄᾅᾆᾇᾐᾑᾒᾓᾔᾕᾖᾗᾠᾡᾢᾣᾤᾥᾦᾧὰάᾳᾶᾴᾷὲέὴήῂῃῄῆῇὶίϊῒΐῐῑῖὸόὺύϋΰῠῡῦὼώῲῳῴῶῷῤῥῬ"  # noqa: E501
            next_is_greek = j < len(result) and ("α" <= result[j].lower() <= "ω" or result[j].lower() in greek_letters)
            if not next_is_greek:
                fixed.append("ς")
                continue
        fixed.append(ch)
    return "".join(fixed)
