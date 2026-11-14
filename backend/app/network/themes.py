"""Expertise themes: the vocabulary for "who are my go-to people for X".

Themes come from two places: what the investor declares about a contact, and what FINN derives from
the contact's employment history (years at organisations whose sector maps to a theme, weighted by seniority).
"""
import re

THEMES: dict[str, str] = {
    "it_services": "IT services",
    "banking": "Banking",
    "rural_lending": "Rural & micro lending",
    "nbfc": "NBFCs & consumer finance",
    "capital_markets": "Capital markets",
    "insurance": "Insurance",
    "oil_gas": "Oil & gas",
    "power_utilities": "Power & utilities",
    "renewables": "Renewables",
    "auto_ev": "Automobiles & EVs",
    "auto_components": "Auto components",
    "fmcg": "FMCG",
    "consumer_retail": "Consumer & retail",
    "pharma_generics": "Pharma",
    "specialty_chemicals": "Specialty chemicals",
    "infrastructure_epc": "Infrastructure & EPC",
    "telecom": "Telecom",
    "defence_aerospace": "Defence & aerospace",
    "semiconductors": "Semiconductors & electronics",
    "mining_metals": "Mining & metals",
    "public_policy": "Government & policy",
    "corporate_finance": "CFO / corporate finance",
}

# companies.sector vocabulary (portfolio_seed.py) and organizations.sector -> themes
SECTOR_TO_THEMES: dict[str, list[str]] = {
    "IT": ["it_services"],
    "Banking": ["banking"],
    "NBFC": ["nbfc"],
    "Microfinance": ["rural_lending", "nbfc"],
    "Insurance": ["insurance"],
    "Capital Markets": ["capital_markets"],
    "Energy": ["oil_gas", "power_utilities"],
    "Oil & Gas": ["oil_gas"],
    "Power": ["power_utilities"],
    "Utilities": ["power_utilities"],
    "Renewables": ["renewables", "power_utilities"],
    "Automobile": ["auto_ev"],
    "Auto Components": ["auto_components"],
    "FMCG": ["fmcg"],
    "Consumer": ["consumer_retail"],
    "Pharma": ["pharma_generics"],
    "Chemicals": ["specialty_chemicals"],
    "Infrastructure": ["infrastructure_epc"],
    "Telecom": ["telecom"],
    "Defence & Aerospace": ["defence_aerospace"],
    "Electronics": ["semiconductors"],
    "Semiconductors": ["semiconductors"],
    "Mining": ["mining_metals"],
    "Metals": ["mining_metals"],
    "Government": ["public_policy"],
    "Lubricants": ["specialty_chemicals"],
}

# Words an investor might use -> theme. Longest phrases are tried first.
SYNONYMS: dict[str, str] = {
    "semiconductor manufacturing": "semiconductors", "semiconductor": "semiconductors", "semiconductors": "semiconductors",
    "chip": "semiconductors", "chips": "semiconductors", "fab": "semiconductors", "electronics": "semiconductors",
    "osat": "semiconductors",
    "specialty chemicals": "specialty_chemicals", "speciality chemicals": "specialty_chemicals",
    "chemicals": "specialty_chemicals", "agrochemicals": "specialty_chemicals",
    "rural lending": "rural_lending", "rural credit": "rural_lending", "microfinance": "rural_lending",
    "mfi": "rural_lending", "nbfc": "nbfc", "consumer finance": "nbfc",
    "banking": "banking", "banks": "banking", "bank": "banking", "lending": "banking",
    "automobile": "auto_ev", "automobiles": "auto_ev", "automotive": "auto_ev", "auto": "auto_ev", "cars": "auto_ev",
    "car": "auto_ev", "ev": "auto_ev", "evs": "auto_ev", "electric vehicles": "auto_ev",
    "auto components": "auto_components", "auto ancillary": "auto_components",
    "pharma": "pharma_generics", "pharmaceutical": "pharma_generics", "pharmaceuticals": "pharma_generics",
    "generics": "pharma_generics", "us generics": "pharma_generics", "healthcare": "pharma_generics",
    "it services": "it_services", "software services": "it_services", "outsourcing": "it_services", "it": "it_services",
    "oil and gas": "oil_gas", "oil": "oil_gas", "gas": "oil_gas", "refining": "oil_gas", "upstream": "oil_gas",
    "power": "power_utilities", "utilities": "power_utilities", "thermal power": "power_utilities",
    "renewables": "renewables", "renewable": "renewables", "solar": "renewables", "wind": "renewables",
    "fmcg": "fmcg", "consumer goods": "fmcg", "consumer": "consumer_retail", "retail": "consumer_retail",
    "jewellery": "consumer_retail",
    "infrastructure": "infrastructure_epc", "infra": "infrastructure_epc", "epc": "infrastructure_epc",
    "construction": "infrastructure_epc",
    "telecom": "telecom", "telecommunications": "telecom",
    "defence": "defence_aerospace", "defense": "defence_aerospace", "aerospace": "defence_aerospace",
    "mining": "mining_metals", "metals": "mining_metals", "steel": "mining_metals", "coal": "mining_metals",
    "government": "public_policy", "policy": "public_policy", "regulation": "public_policy",
    "cfo": "corporate_finance", "corporate finance": "corporate_finance", "treasury": "corporate_finance",
    "insurance": "insurance", "capital markets": "capital_markets", "broking": "capital_markets",
}

SENIORITY_MULT = {"board": 1.2, "cxo": 1.2, "vp": 1.0, "manager": 0.8, "ic": 0.6}


def themes_for_sector(sector: str | None) -> list[str]:
    return list(SECTOR_TO_THEMES.get(sector or "", []))


def themes_in_text(text: str) -> list[str]:
    """Themes named in free text, in order of appearance, longest phrase first so
    'semiconductor manufacturing' doesn't also count as plain 'manufacturing'."""
    low = " " + re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()) + " "
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for phrase in sorted(SYNONYMS, key=len, reverse=True):
        for m in re.finditer(rf" {re.escape(phrase)} ", low):
            span = (m.start(), m.end())
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            taken.append(span)
            found.append((m.start(), SYNONYMS[phrase]))
    out: list[str] = []
    for _, t in sorted(found):
        if t not in out:
            out.append(t)
    return out


def derive(employments: list[dict], current_year: int) -> dict[str, tuple[float, str]]:
    """theme -> (weight 0..1, evidence). employments rows need org_name, sector, start_year, end_year,
    seniority, title, function. A CFO anywhere also earns corporate_finance."""
    acc: dict[str, list[tuple[float, str]]] = {}
    for e in employments:
        start = e.get("start_year")
        if not start:
            continue
        end = e.get("end_year") or current_year
        years = max(0.5, end - start)
        mult = SENIORITY_MULT.get(e.get("seniority") or "", 0.8)
        themes = themes_for_sector(e.get("sector"))
        if (e.get("function") == "finance") and (e.get("seniority") in ("cxo", "vp", "board")):
            themes = themes + ["corporate_finance"]
        for t in themes:
            span = f"{start}–{e['end_year'] or 'now'}"
            acc.setdefault(t, []).append((years * mult, f"{e.get('title') or 'Worked'} at {e['org_name']} ({span})"))
    out: dict[str, tuple[float, str]] = {}
    for t, items in acc.items():
        total = sum(w for w, _ in items)
        best = max(items, key=lambda x: x[0])[1]
        out[t] = (round(min(1.0, total / 10.0), 2), best)
    return out
