"""Reading people out of real exchange filings by rules (no model)."""
from conftest import FIXTURES

from app.network import filing_people as fp
from app.network.names import initials_key, norm_org, norm_person


def read(name, title="", detail=""):
    return {p["name"]: p for p in fp.extract((FIXTURES / name).read_text(), title, detail)}


def test_names_normalise_honorifics_initials_and_possessives():
    assert norm_person("Ms. Rashmi  Joshi (DIN: 06641898)") == "rashmi joshi"
    assert norm_person("Mr. Sanjay D’Souza") == "sanjay dsouza"
    assert norm_person("Shri Diwakar Nath Misra") == "diwakar nath misra"
    assert initials_key(norm_person("Dr. C Jayakumar")) == initials_key(norm_person("Jayakumar C"))
    assert norm_org("Larsen & Toubro Limited") == "larsen and toubro"
    assert norm_org("Castrol India Ltd.") == "castrol india"
    assert norm_org("Cipla's") == "cipla"


def test_sebi_disclosure_appointment_with_profile():
    p = read("CIPLA.txt")["Rashmi Joshi"]
    assert p["change"] == "appointed"  # the table header lists 'resignation' too; it must not win
    assert "independent director" in p["role"].lower()
    assert p["effective"] == "2026-10-27"
    assert "Castrol India Limited" in p["background"] and p["background_source"] == "filing"


def test_outside_hire_and_press_release_shapes():
    cto = read("CIPLA_cto.txt")["Vikram Janakiraman"]
    assert cto["change"] == "appointed" and cto["effective"] == "2026-12-07"
    assert "Global Chief Technical Operating Officer" in cto["role"]
    assert "Boston Consulting Group" in cto["background"]
    wipro = read("WIPRO.txt", "Press Release",
                 "Wipro Appoints Angan Guha as President and Chief Executive Officer for Americas 2 Strategic Market Unit")
    g = wipro["Angan Guha"]
    assert g["change"] == "appointed" and g["effective"] == "2026-12-08"
    assert "Birlasoft" in g["background"] and "said" not in g["background"]  # quotes are not background
    assert "Srini Pallia" not in wipro  # a quoted executive is not a management change


def test_exits_and_signatories():
    hdfc = read("HDFCBANK.txt")
    assert set(hdfc) == {"Sanjay D’Souza"}  # the company secretary who signed is not a change
    assert hdfc["Sanjay D’Souza"]["change"] == "retired" and hdfc["Sanjay D’Souza"]["effective"] == "2026-10-31"
    piyush = read("NTPC_cess.txt")
    assert list(piyush) == ["Piyush Singh"] and piyush["Piyush Singh"]["change"] == "ceased"
    sun = read("SUN.txt")["Gautam Doshi"]
    assert sun["change"] == "resigned" and sun["effective"] == "2026-10-12"


def test_multi_person_promotions_and_internal_chairman():
    lt = read("LT.txt")
    assert {"C Jayakumar", "Suresh Kumar Narang", "S Ramkumar"} <= set(lt)
    assert all(p["change"] == "other" for p in lt.values())  # promotions, not new appointments
    assert len([n for n in lt if "Sriraman" in n]) == 1  # 'T. Sriraman' and 'Sriraman T' fold together
    ongc = read("ONGC.txt")["Sunil Kumar"]
    assert ongc["change"] == "appointed" and ongc["role"] == "Chairman"


def test_dates():
    assert fp.parse_date("27th October, 2026") == "2026-10-27"
    assert fp.parse_date("October 31, 2026") == "2026-10-31"
    assert fp.parse_date("23.10.2026") == "2026-10-23"
    assert fp.parse_date("sometime soon") is None
