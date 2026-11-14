"""Who joined or left, read from the filing text by rules. No model.

SEBI's Schedule III disclosure for a management change has a fixed shape: an honorific and a name
("Ms Rashmi Joshi", "Shri Diwakar Nath Misra"), a change verb (appointment, resignation, cessation,
superannuation), an effective date, and a "Brief Profile" for appointees. Company press releases say
"<Company> appoints <Name> as <Role>". These rules read both shapes. When an API key is configured,
the cheap model's reading of the same filing (enrich.py) is used instead; this keeps the people layer
working without one.

Everything returned is a span of the filing itself, so nothing here can invent a background.
"""
import re
from datetime import date, datetime

from app.network.names import initials_key, norm_person

HON = r"(?:Mr|Mrs|Ms|Miss|Dr|Shri|Smt|Sri|Prof)"
NAME_TOKEN = r"(?:[A-Z][a-zA-Z'’]+(?:-[A-Z][a-zA-Z'’]+)?|[A-Z]\.?(?=\s))"
HON_NAME = re.compile(rf"\b{HON}\.?\s+({NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,4}})")
# Capitalised words that end a name in table layouts ("Ms Rashmi Joshi Reason for change ...")
NOT_NAME = {"Reason", "Senior", "Additional", "Executive", "Director", "Chairman", "Chairperson", "Company", "Bank",
            "Limited", "Ltd", "Group", "Global", "Chief", "The", "Date", "Brief", "Profile", "Name", "Appointment",
            "Independent", "Whole", "President", "Vice", "Head", "Managing", "Non", "Government", "Ministry", "Board",
            "IC", "Sr", "DIN", "Is", "Has", "Was", "As", "In", "Of", "And", "On", "For", "To", "With", "Secretary",
            "Officer", "Nominee", "Govt", "Member", "Partner", "Joint", "Deputy", "General", "Manager", "CEO", "CFO",
            "MD", "COO", "CTO", "Prior", "During", "Under", "He", "She", "His", "Her", "Annexure", "Disclosure",
            "Details", "Terms", "Particulars", "Description", "Promoted", "Re", "Approval", "Resignation", "Cessation"}
PRESS_APPOINT = re.compile(r"\bappoint(?:s|ed|ment of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+as\s+")
CHANGE_VERBS = re.compile(r"resign|superannuat|retire|ceas|cessation|relinquish|re-?appoint|promot|categori[sz]ed|"
                          r"appoint|joins\b|join the|elevat|nominat", re.I)
TOP_ROLE = re.compile(r"chair(?:man|person)|chief executive|\bceo\b|managing director|\bmd\b|chief financial|\bcfo\b|"
                      r"chief operating|\bcoo\b|chief [a-z]+(?: [a-z]+)? officer|whole[- ]time director|"
                      r"executive director|president", re.I)
# SEBI table headers list every change type; they must not be read as what happened.
BOILERPLATE = [
    re.compile(r"reason for change\s*viz\.?(?:[\s,/;]|appointment|re-?appointment|resignation|removal|death|"
               r"cessation|or|otherwise)*", re.I),
    re.compile(r"date\s+of\s+appointment\s*/[^&]{0,120}&\s*term\s+of\s+appointment(?:\s*/\s*re-?appointment)?;?", re.I),
    re.compile(r"date\s+of\s+appointment\s*&\s*term\s+of\s+appointment", re.I),
    re.compile(r"\(in case of appointment(?: of a director)?\)", re.I),
    re.compile(r"details of events that needs? to be provided", re.I),
    re.compile(r"disclosure of relationships? between\s+directors", re.I),
]

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
DATE_DMY = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(\d{4})")
DATE_MDY = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})")
DATE_NUM = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})")
EFFECTIVE = re.compile(r"(?:with effect from|w\.?\s?e\.?\s?f\.?|effective(?: from)?|on or after)\s+(?:the\s+)?"
                       r"(?:close of business hours on\s+|date of [a-z ]{0,40}?(?=\d))?", re.I)
PROFILE_START = re.compile(r"brief profile", re.I)
PROFILE_END = re.compile(r"disclosure of relationships?|information as required|\bannexure\b|yours faithfully|"
                         r"not debarred|\b\d\s+disclosure", re.I)
CAREER_CUE = re.compile(r"prior to|previously|years|joined|served|serves|holds|degree|alumn|graduate|experience|"
                        r"career|association|boards?|chartered|engineer|mba|ph\.?d|doctorate|worked|qualified", re.I)
LETTERHEAD = re.compile(r"scrip|listing department|dalal street|\bcin\b|regd\.? office|bandra|exchange plaza|"
                        r"phiroze|tel[.:]|fax|e-?mail", re.I)
ROLE_TAIL = re.compile(r"\s+(?:Dear|Pursuant|We\b|Sir|Madam|This\b|Kindly|In terms|The Board|subject to|w\.?e\.?f|"
                       r"with effect|effective|for a period|till\b|on the Board|of the Company|of the Bank|"
                       r"designated as Senior|and a Senior).*$", re.I)


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _clean(text: str) -> str:
    t = _collapse(text).replace("Govt.", "Government").replace("Non-Executive, Independent", "Non-Executive Independent")
    for rx in BOILERPLATE:
        t = rx.sub(" ", t)
    return _collapse(t)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<!\b[A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bLtd\.)(?<!\bNo\.)(?<!\bSr\.)"
                     r"(?<!\bCo\.)(?<!\bSt\.)(?<!\bvs\.)(?<=[.;])\s+(?=[A-Z(“\"])", text)
    return [p.strip() for p in parts if p.strip()]


def _clean_name(raw: str) -> str | None:
    toks = []
    for t in raw.split():
        t = t.rstrip(",;:")
        if t.rstrip(".") in NOT_NAME:
            break
        toks.append(t)
    if not any(len(t.rstrip(".")) > 1 for t in toks):
        return None
    while toks and len(toks[-1].rstrip(".")) == 1 and len(toks) > 2:
        toks.pop()  # a stray trailing initial from the next column
    return " ".join(toks).strip() or None


def _month(word: str) -> int | None:
    w = word.lower()[:3]
    return next((i for i, m in enumerate(MONTHS, 1) if m.startswith(w)), None) if len(w) == 3 else None


def parse_date(s: str) -> str | None:
    """'27th October, 2026' | 'October 31, 2026' | '23.10.2026' -> ISO date. None if unreadable."""
    s = s.strip()
    for rx, order in ((DATE_DMY, "dmy"), (DATE_MDY, "mdy"), (DATE_NUM, "num")):
        m = rx.match(s)
        if not m:
            continue
        if order == "dmy":
            d, mo, y = int(m.group(1)), _month(m.group(2)), int(m.group(3))
        elif order == "mdy":
            d, mo, y = int(m.group(2)), _month(m.group(1)), int(m.group(3))
        else:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            if mo:
                return date(y, mo, d).isoformat()
        except ValueError:
            continue
    return None


def _change_from_verb(v: str) -> str:
    v = v.lower()
    if v.startswith("resign"):
        return "resigned"
    if v.startswith(("superannuat", "retire")):
        return "retired"
    if v.startswith(("ceas", "cessation", "relinquish")):
        return "ceased"
    if v.startswith(("re-appoint", "reappoint", "promot", "categori")):
        return "other"
    return "appointed"


def _windows(name: str, text: str, radius: int = 260) -> list[tuple[int, str]]:
    """(name position, surrounding text) for every mention of the person's surname (or first name)."""
    toks = [t.rstrip(".") for t in name.split() if len(t.rstrip(".")) > 1]
    keys = [toks[-1]] + ([toks[0]] if len(toks) > 1 else [])
    out = []
    for k in keys:
        for m in re.finditer(rf"\b{re.escape(k)}\b", text):
            out.append((m.start(), text[max(0, m.start() - radius): m.end() + radius]))
        if out:
            break
    return out


def _nearest_change(name: str, text: str) -> str | None:
    best: tuple[int, str] | None = None
    for pos, _ in _windows(name, text):
        lo = max(0, pos - 260)
        for m in CHANGE_VERBS.finditer(text[lo: pos + 260]):
            dist = abs(lo + m.start() - pos)
            if best is None or dist < best[0]:
                best = (dist, m.group(0))
    return _change_from_verb(best[1]) if best else None


def _role(name: str, text: str) -> str | None:
    """Most specific designation stated next to the person's name."""
    last = re.escape([t for t in name.split() if len(t.rstrip(".")) > 1][-1].rstrip("."))
    cands: list[tuple[int, str]] = []
    m = re.search(rf"{last}[^.]{{0,160}}?\bto the post of\s+([A-Z][A-Za-z ]{{2,40}})", text)
    if m:
        return _tidy_role(m.group(1))
    pats = [
        rf"{last}(?:\s*\(DIN[^)]*\))?[^.]{{0,150}}?\b(?:re-?appointed |appointed |resignation |)as\s+(?:the |an |a |its )?"
        rf"([A-Za-z][^.;()]{{3,140}})",
        rf"{last}[^.]{{0,220}}?ceased to (?:be|hold)\s+(?:the |a |an )?([A-Za-z][^.;()]{{3,140}})",
        rf"{last}\s*,\s*((?:Senior |Additional |Joint |Executive |Group |Chief |Vice |Independent |Managing |President)"
        rf"[^.;()]{{3,140}})",
    ]
    for p in pats:
        for mm in re.finditer(p, text):
            role = _tidy_role(mm.group(1))
            if role:
                cands.append((mm.start(), role))
                break
    return min(cands)[1] if cands else None


def _tidy_role(raw: str) -> str | None:
    role = ROLE_TAIL.sub("", _collapse(raw)).strip(" ,-–&")
    role = re.sub(r"\s+(?:of|and|\d+|[a-z])$", "", role).strip(" ,-–&")
    if not 3 <= len(role) <= 110 or role.lower().startswith(("per ", "the company", "a result", "under ")):
        return None
    return role[0].upper() + role[1:]


def _effective(name: str, text: str) -> str | None:
    for pos, win in _windows(name, text, 400):
        for m in EFFECTIVE.finditer(win):
            d = parse_date(win[m.end(): m.end() + 40])
            if d:
                return d
    return None


def _profile_block(text: str) -> str | None:
    m = PROFILE_START.search(text)
    if not m:
        return None
    rest = text[m.end():]
    e = PROFILE_END.search(rest)
    block = _collapse(rest[: e.start()] if e else rest[:2500]).lstrip(" :.-")
    return block or None


def _bio_from_sentences(name: str, pool: str) -> str | None:
    toks = [t.rstrip(".") for t in name.split() if len(t.rstrip(".")) > 1]
    first, last = toks[0], toks[-1]
    out: list[str] = []
    follow = False
    for s in _sentences(pool):
        if (len(s) > 700 or LETTERHEAD.search(s) or re.search(r"[“”\"]|\bsaid\b", s)
                or re.search(r"approved the (?:re-?)?appointment|has appointed|brief profile", s, re.I)):
            follow = False
            continue
        if re.search(rf"\b({re.escape(last)}|{re.escape(first)})\b", s) and CAREER_CUE.search(s):
            out.append(s)
            follow = True
        elif follow and re.search(r"\b(he|she|his|her)\b", s, re.I) and CAREER_CUE.search(s):
            out.append(s)
        else:
            follow = False
    bio = _collapse(" ".join(out))
    return bio[:1500] if len(bio) >= 40 else None


def extract(text: str, title: str = "", detail: str = "") -> list[dict]:
    """People whose role changes in this filing: name, role, change, effective (ISO date), background."""
    body = _clean(" ".join(x for x in (title, detail) if x) + " . " + (text or ""))
    raw_names: list[str] = []
    for line in (text or "").splitlines() + [title or "", detail or ""]:
        raw_names += [m.group(1) for m in HON_NAME.finditer(line.replace("Govt.", "Government"))]
    raw_names += [m.group(1) for m in PRESS_APPOINT.finditer(body)]

    # Fold variants: 'T. Sriraman' = 'Sriraman T'; 'Piyush' and 'Mr. Narang' are parts of longer names.
    people: list[str] = []
    for raw in raw_names:
        name = _clean_name(raw)
        if not name:
            continue
        n = norm_person(name)
        dup = False
        for i, kept in enumerate(people):
            k = norm_person(kept)
            if n == k or initials_key(n) == initials_key(k):
                dup = True
                if len(n.split()) > len(k.split()) and len(name) > len(kept):
                    people[i] = name
                break
            if set(n.split()) <= set(k.split()):
                dup = True
                break
            if set(k.split()) <= set(n.split()):
                people[i] = name
                dup = True
                break
        if not dup:
            people.append(name)

    out = []
    appointees = []
    for name in people:
        change = _nearest_change(name, body)
        if change is None:
            continue  # named, but nothing happens to them (a signatory, a quoted executive)
        out.append({"name": name, "role": _role(name, body) or "Role not stated in the filing", "change": change,
                    "effective": _effective(name, body), "background": None, "background_source": "not_disclosed",
                    "method": "rules"})
        if change in ("appointed", "other"):
            appointees.append(name)
    profile = _profile_block(body)
    for p in out:
        if profile and len(profile) >= 60 and len(appointees) == 1 and p["name"] == appointees[0]:
            bio = profile[:1500]
        else:
            bio = _bio_from_sentences(p["name"], profile or body)
        if bio:
            p["background"], p["background_source"] = bio, "filing"
    return out


def is_top_role(text: str) -> bool:
    return bool(TOP_ROLE.search(text or ""))


def year_of(iso: str | None) -> int | None:
    try:
        return datetime.fromisoformat(iso).year if iso else None
    except ValueError:
        return None
