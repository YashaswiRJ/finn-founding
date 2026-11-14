"""Name normalisation for people and organisations. Pure functions, no database.

Matching a name in a filing ("Ms Rashmi Joshi", "Shri Diwakar Nath Misra", "Dr. C Jayakumar") to a person
in the investor's network starts here: strip honorifics and punctuation so equal names compare equal,
and build an initials key so "K. Krithivasan" and "Krithivasan K" can be offered as a *possible* match.
"""
import hashlib
import re
import unicodedata

HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "shri", "sri", "smt", "kum", "prof", "ca", "cs", "cma", "adv",
              "capt", "col", "gen", "lt", "er", "late", "sh"}
ORG_SUFFIXES = {"limited", "ltd", "pvt", "private", "plc", "inc", "incorporated", "corporation", "corp", "company",
                "co", "llp", "llc", "the"}


def _ascii(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_person(name: str) -> str:
    """'Ms. Rashmi  Joshi' -> 'rashmi joshi'; "Mr. Sanjay D'Souza" -> 'sanjay dsouza'."""
    s = _ascii(name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)              # '(DIN: 06641898)'
    s = s.replace("'", "")
    s = re.sub(r"[^a-z ]+", " ", s)
    tokens = [t for t in s.split() if t not in HONORIFICS]
    return " ".join(tokens)


def initials_key(name_norm: str) -> str:
    """Longest token as the surname-ish anchor plus the sorted first letters of the rest.
    'k krithivasan' and 'krithivasan k' share 'krithivasan|k'; so do 'c jayakumar' and 'jayakumar c'."""
    toks = name_norm.split()
    if not toks:
        return ""
    anchor = max(toks, key=len)
    rest = sorted(t[0] for t in toks if t is not anchor)
    return anchor + "|" + "".join(rest)


def norm_org(name: str) -> str:
    """'Larsen & Toubro Limited' -> 'larsen and toubro'; 'Castrol India Ltd.' -> 'castrol india'."""
    s = _ascii(name or "").lower().replace("&", " and ")
    s = re.sub(r"'s\b", "", s)               # "Cipla's new CFO" -> cipla
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = s.split()
    while toks and toks[-1] in ORG_SUFFIXES:
        toks.pop()
    while toks and toks[0] == "the":
        toks.pop(0)
    return " ".join(toks)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def public_person_id(name_norm: str, symbol: str) -> str:
    """Deterministic id for a person disclosed in a filing, so re-reading the filing never duplicates them."""
    return "pf:" + hashlib.sha1(f"{name_norm}|{symbol}".encode()).hexdigest()[:16]
