"""Generate the synthetic demo network: backend/seed/network_demo.json.

    python scripts/generate_network.py

Every person here is fictional. Their careers are written to overlap the real companies in FINN's
portfolio and the real organisations named in real exchange filings (Cipla's new Chief Technical
Operating Officer came from BCG and Glenmark; its new independent director was CFO of Castrol India
and sits on Bharat Forge's board; Wipro's new Americas CEO ran Birlasoft), so the demo shows what the
Network notices. Synthetic people only ever *know* other synthetic people. Any link to a real executive
is computed by FINN from careers and labelled as an inferred overlap.

Deterministic: a fixed seed, so re-running produces the same file.
"""
import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "seed" / "network_demo.json"
RNG = random.Random(2027)

# Organisations that aren't in FINN's company list, with the sector that drives expertise themes.
ORGS = [
    ("Boston Consulting Group", "private", "Consulting", "large"),
    ("Deloitte", "private", "Consulting", "large"),
    ("McKinsey & Company", "private", "Consulting", "large"),
    ("Glenmark Pharmaceuticals", "listed", "Pharma", "mid"),
    ("Dr. Reddy's Laboratories", "listed", "Pharma", "large"),
    ("Castrol India Limited", "listed", "Lubricants", "mid"),
    ("Bharat Forge Limited", "listed", "Auto Components", "large"),
    ("Rallis India Limited", "listed", "Chemicals", "mid"),
    ("Birlasoft Ltd", "listed", "IT", "mid"),
    ("Tata AutoComp Systems", "private", "Auto Components", "mid"),
    ("Bosch India", "listed", "Auto Components", "large"),
    ("Ola Electric", "listed", "Automobile", "mid"),
    ("Micron Technology", "private", "Semiconductors", "large"),
    ("Tata Electronics", "private", "Semiconductors", "mid"),
    ("SRF Limited", "listed", "Chemicals", "large"),
    ("Aarti Industries", "listed", "Chemicals", "mid"),
    ("Bandhan Bank", "listed", "Microfinance", "mid"),
    ("Ujjivan Small Finance Bank", "listed", "Microfinance", "small"),
    ("Kotak Institutional Equities", "private", "Capital Markets", "mid"),
    ("Ministry of Power", "government", "Government", None),
    ("Ministry of Petroleum & Natural Gas", "government", "Government", None),
    ("Indian Space Research Organisation", "government", "Defence & Aerospace", "large"),
    ("Northfield Capital (demo fund)", "private", "Capital Markets", "small"),
    # universities
    ("IIT Kanpur", "university", None, None), ("IIM Ahmedabad", "university", None, None),
    ("IIM Bangalore", "university", None, None), ("IIT Bombay", "university", None, None),
    ("IIT Madras", "university", None, None), ("Punjab Engineering College", "university", None, None),
    ("University of Pune", "university", None, None), ("NIT Durgapur", "university", None, None),
    ("Shri Ram College of Commerce", "university", None, None), ("Delhi School of Economics", "university", None, None),
    ("Institute of Chartered Accountants of India", "university", None, None),
]

# org, related org, kind ('supplier' = related is a supplier of org). Demo links, labelled synthetic.
ORG_RELATIONS = [
    ("Tata Motors Passenger Vehicles", "Tata AutoComp Systems", "supplier"),
    ("Tata Motors Passenger Vehicles", "Bharat Forge Limited", "supplier"),
    ("Maruti Suzuki India", "Bosch India", "supplier"),
    ("Tata Motors Passenger Vehicles", "Ola Electric", "competitor"),
    ("Hindustan Aeronautics", "MTAR Technologies", "supplier"),
    ("Hindustan Aeronautics", "Bharat Electronics", "supplier"),
    ("Indian Space Research Organisation", "MTAR Technologies", "supplier"),
    ("Cipla", "Glenmark Pharmaceuticals", "competitor"),
    ("Sun Pharmaceutical Industries", "Dr. Reddy's Laboratories", "competitor"),
    ("Wipro", "Birlasoft Ltd", "competitor"),
    ("NTPC", "Larsen & Toubro", "supplier"),
]

SELF = {
    "full_name": "You",
    "employments": [("Deloitte", "Analyst, Financial Advisory", "finance", "ic", 2012, 2014),
                    ("Northfield Capital (demo fund)", "Partner, Public Markets", "finance", "cxo", 2016, None)],
    "educations": [("IIT Kanpur", "B.Tech", 2012), ("IIM Ahmedabad", "PGP", 2016)],
}

# key, name, headline, location, last_interaction, [employments], [educations], [declared expertise], notes
# employment: (org, title, function, seniority, start, end)  end None = current
ANCHORS = [
    ("neha", "Neha Bansal", "COO, Medisphere Labs; ex-BCG operations", "Mumbai", "2026-09-10",
     [("Boston Consulting Group", "Principal, Operations practice", "strategy", "vp", 2013, 2021),
      ("Medisphere Labs", "Chief Operating Officer", "operations", "cxo", 2021, None)],
     [("IIM Ahmedabad", "PGP", 2016)], [("pharma_generics", 0.7)], "IIM-A batchmate. Sharp on pharma plant ops."),
    ("aditya", "Aditya Rao", "Partner, BCG (operations & industrial goods)", "Mumbai", None,
     [("Boston Consulting Group", "Partner, Operations practice", "strategy", "vp", 2015, None)],
     [("IIT Bombay", "B.Tech", 2011)], [("pharma_generics", 0.5), ("auto_ev", 0.5)], "Neha's former team-mate at BCG."),
    ("rahul", "Rahul Deshpande", "Ex-Head of Manufacturing Excellence, Glenmark", "Nashik", "2026-03-18",
     [("Glenmark Pharmaceuticals", "Head of Manufacturing Excellence", "operations", "vp", 2007, 2016),
      ("Cipla", "Plant Head, Goa", "operations", "vp", 2016, 2020)],
     [("IIT Madras", "B.Tech Chemical", 2002)], [("pharma_generics", 0.8)], "USFDA inspections veteran."),
    ("meera", "Meera Krishnan", "Ex-Financial Controller, Castrol India", "Mumbai", "2026-06-02",
     [("Castrol India Limited", "Financial Controller", "finance", "vp", 2011, 2018),
      ("Deloitte", "Manager, Audit", "finance", "manager", 2005, 2011)],
     [("Institute of Chartered Accountants of India", "CA", 2004)], [("corporate_finance", 0.8)],
     "Former Deloitte colleague."),
    ("kabir", "Kabir Shah", "Founder, Pune auto-components SME", "Pune", "2026-10-21",
     [("Tata AutoComp Systems", "Business Head", "sales", "vp", 2009, 2017)],
     [("IIT Kanpur", "B.Tech", 2012)], [("auto_components", 0.8)], "College friend."),
    ("arjun", "Arjun Bhatia", "VP Corporate Strategy, Bharat Forge", "Pune", None,
     [("Bharat Forge Limited", "Vice President, Corporate Strategy", "strategy", "vp", 2019, None),
      ("McKinsey & Company", "Engagement Manager", "strategy", "manager", 2013, 2019)],
     [("IIM Bangalore", "PGP", 2013)], [("auto_components", 0.6)], "Kabir's close friend."),
    ("sunita", "Sunita Iyer", "Ex-VP Delivery, Birlasoft", "Pune", "2025-11-20",
     [("Birlasoft Ltd", "Vice President, Delivery", "technology", "vp", 2018, 2024),
      ("Wipro", "Delivery Manager, BFSI", "technology", "manager", 2009, 2018)],
     [("University of Pune", "B.E. Electronics", 2008)], [], None),
    ("prakash", "Prakash Menon", "Ex-Wipro Americas BFSI account head", "Bengaluru", "2025-08-14",
     [("Wipro", "Client Partner, Americas BFSI", "sales", "vp", 2004, 2019)],
     [("Delhi School of Economics", "MA Economics", 2002)], [("it_services", 0.7)], None),
    ("anil", "Anil Mathur", "Retired IAS; ex-Joint Secretary, Ministry of Power", "New Delhi", "2025-12-04",
     [("Ministry of Power", "Joint Secretary", "government", "vp", 2017, 2021),
      ("Ministry of Petroleum & Natural Gas", "Director", "government", "vp", 2011, 2016)],
     [("Delhi School of Economics", "MA Economics", 1990)], [("power_utilities", 0.7), ("public_policy", 0.9)],
     "Met at a power-sector conference."),
    ("nisha", "Nisha Rawat", "Ex-Chief Geologist, ONGC", "Dehradun", "2025-07-30",
     [("Oil & Natural Gas Corporation", "Chief Geologist", "operations", "vp", 2004, 2019)],
     [("IIT Bombay", "M.Tech", 2003)], [("oil_gas", 0.9)], None),
    ("farhan", "Farhan Qureshi", "Ex-Senior VP, Business Banking, HDFC Bank", "Mumbai", "2025-12-12",
     [("HDFC Bank", "Senior Vice President, Business Banking (SME credit)", "sales", "vp", 2010, 2020)],
     [("Shri Ram College of Commerce", "B.Com", 2004)], [("banking", 0.8)], "Ex-colleague of a friend; great on SME credit."),
    ("vivek", "Vivek Iyer", "Ex-General Manager, L&T Power", "Chennai", "2026-01-25",
     [("Larsen & Toubro", "General Manager, Power EPC", "operations", "vp", 2008, 2016)],
     [("NIT Durgapur", "B.E. Electrical", 1996)], [("infrastructure_epc", 0.8), ("power_utilities", 0.6)], None),
    ("harpreet", "Harpreet Sandhu", "Ex-Executive Director, NTPC", "Chandigarh", "2024-11-02",
     [("NTPC", "Executive Director, Projects", "operations", "cxo", 1990, 2018)],
     [("Punjab Engineering College", "B.E. Electrical", 1989)], [("power_utilities", 0.9)], None),
    ("ritika", "Ritika Menon", "Ex-Head of Treasury, Tata Motors", "Mumbai", "2026-05-02",
     [("Tata Motors Passenger Vehicles", "Head of Treasury", "finance", "vp", 2014, 2021),
      ("Deloitte", "Senior Consultant", "finance", "manager", 2010, 2014)],
     [("IIM Ahmedabad", "PGP", 2009)], [("auto_ev", 0.6), ("corporate_finance", 0.9)], "Former Deloitte colleague."),
    ("rohan", "Rohan Kapoor", "Ex-Maruti supply chain; ex-Ola Electric", "Gurugram", "2026-02-14",
     [("Maruti Suzuki India", "Deputy General Manager, Supply Chain", "operations", "manager", 2010, 2018),
      ("Ola Electric", "Director, Supply Chain", "operations", "vp", 2019, 2023)],
     [("IIT Kanpur", "B.Tech", 2009)], [("auto_ev", 0.9)], None),
    ("kavita", "Dr. Kavita Rao", "Ex-Regulatory Affairs head, Sun Pharma (US generics)", "Vadodara", "2026-04-11",
     [("Sun Pharmaceutical Industries", "Head, US Regulatory Affairs", "operations", "vp", 2009, 2016),
      ("Dr. Reddy's Laboratories", "Director, Regulatory", "operations", "vp", 2016, 2022)],
     [], [("pharma_generics", 0.9)], None),
    ("sameer", "Sameer Kulkarni", "Ex-Business Development, Cipla", "Mumbai", "2026-08-08",
     [("Cipla", "Associate Director, Business Development", "strategy", "manager", 2015, 2022)],
     [("IIM Ahmedabad", "PGP", 2015)], [("pharma_generics", 0.6)], "One year junior at IIM-A."),
    ("lakshmi", "Lakshmi Reddy", "Ex-Programme Manager, MTAR Technologies", "Hyderabad", "2026-07-19",
     [("MTAR Technologies", "Programme Manager, Space & Nuclear", "operations", "manager", 2016, 2023),
      ("Indian Space Research Organisation", "Scientist", "technology", "ic", 2010, 2016)],
     [("IIT Madras", "M.Tech", 2010)], [("defence_aerospace", 0.9)], None),
    ("karan", "Karan Mehta", "Ex-Project Finance, Suzlon", "Ahmedabad", "2025-06-01",
     [("Suzlon Energy", "Manager, Project Finance", "finance", "manager", 2008, 2014)],
     [], [("renewables", 0.7)], None),
    ("prakashn", "Prakash Nair", "Ex-Chief Designer, HAL", "Bengaluru", "2026-01-09",
     [("Hindustan Aeronautics", "Chief Designer, Rotary Wing", "technology", "vp", 2001, 2015)],
     [("IIT Bombay", "M.Tech Aerospace", 2000)], [("defence_aerospace", 0.9)], None),
    ("ananya", "Ananya Sharma", "Ex-BEL radar electronics; chip design consultant", "Bengaluru", "2026-09-28",
     [("Bharat Electronics", "Senior Engineer, Radar", "technology", "ic", 2012, 2019),
      ("Tata Electronics", "Design Lead, OSAT", "technology", "manager", 2023, None)],
     [("NIT Durgapur", "B.Tech ECE", 2012)], [("semiconductors", 0.8), ("defence_aerospace", 0.6)], None),
    ("siddharth", "Siddharth Rao", "Process Engineering Lead, Tata Electronics fab", "Dholera", "2026-10-02",
     [("Micron Technology", "Process Engineer", "technology", "ic", 2015, 2022),
      ("Tata Electronics", "Process Engineering Lead, Fab", "technology", "manager", 2022, None)],
     [("IIT Madras", "B.Tech", 2014)], [("semiconductors", 0.95)], "Best person for fab economics."),
    ("mehul", "Mehul Parikh", "Ex-SRF; now Aarti Industries", "Vadodara", "2026-03-03",
     [("SRF Limited", "Product Manager, Fluorochemicals", "sales", "manager", 2010, 2019),
      ("Aarti Industries", "Business Head, Specialty", "sales", "vp", 2019, None)],
     [], [("specialty_chemicals", 0.95)], None),
    ("ramesh", "Ramesh Pillai", "Retired SBI; rural credit", "Thiruvananthapuram", "2025-09-15",
     [("State Bank of India", "Deputy General Manager, Rural Business", "sales", "vp", 1995, 2020)],
     [], [("rural_lending", 0.9), ("banking", 0.7)], None),
    ("kavya", "Kavya Nair", "Ex-Bandhan Bank microfinance", "Kolkata", "2026-02-20",
     [("Bandhan Bank", "Regional Head, Microfinance", "sales", "vp", 2014, 2021),
      ("Ujjivan Small Finance Bank", "Head, Credit", "finance", "vp", 2021, None)],
     [], [("rural_lending", 0.9)], None),
    ("deepak", "Deepak Malhotra", "Ex-TCS BFSI delivery head", "Mumbai", "2026-07-07",
     [("Tata Consultancy Services", "Delivery Head, BFSI", "technology", "vp", 2006, 2015)],
     [("IIT Kanpur", "B.Tech", 2005)], [("it_services", 0.8)], None),
    ("isha", "Isha Kapoor", "Ex-Brand Manager, Hindustan Unilever", "Mumbai", "2026-05-25",
     [("Hindustan Unilever", "Brand Manager, Home Care", "sales", "manager", 2010, 2018)],
     [("IIM Ahmedabad", "PGP", 2010)], [("fmcg", 0.8)], None),
    ("gaurav", "Gaurav Singh", "Ex-ITC Foods", "Kolkata", "2026-04-04",
     [("ITC", "Category Head, Foods", "sales", "vp", 2012, 2021)],
     [], [("fmcg", 0.8)], None),
    ("pooja", "Pooja Menon", "Ex-Titan jewellery merchandising", "Bengaluru", "2025-10-10",
     [("Titan Company", "Head, Merchandising (Tanishq)", "sales", "vp", 2013, 2020)],
     [], [("consumer_retail", 0.8)], None),
]

# from, to, kind, strength, context. 'self' = the investor.
RELATIONSHIPS = [
    ("self", "neha", "classmate", 4, "IIM Ahmedabad, PGP 2016"),
    ("neha", "aditya", "former_colleague", 4, "BCG operations practice"),
    ("self", "rahul", "friend", 3, "Met through Sameer"),
    ("self", "meera", "former_colleague", 4, "Deloitte 2012-14"),
    ("self", "kabir", "friend", 5, "IIT Kanpur 2012"),
    ("kabir", "arjun", "friend", 4, "Pune circle"),
    ("self", "sunita", "met_at_event", 2, "NASSCOM leadership forum 2024"),
    ("self", "prakash", "knows", 3, "Former portfolio-company client"),
    ("self", "anil", "met_at_event", 3, "Power-sector conference 2023"),
    ("anil", "nisha", "knows", 3, "Inter-ministerial committee"),
    ("prakash", "farhan", "friend", 4, "Neighbours in Mumbai"),
    ("self", "farhan", "knows", 2, "Met through Prakash"),
    ("self", "vivek", "knows", 3, "Infra roadshow 2022"),
    ("anil", "harpreet", "former_colleague", 4, "Power ministry projects"),
    ("self", "ritika", "former_colleague", 5, "Deloitte 2012-14"),
    ("self", "rohan", "classmate", 3, "IIT Kanpur"),
    ("self", "kavita", "knows", 3, "Expert call 2025"),
    ("self", "sameer", "classmate", 4, "IIM Ahmedabad"),
    ("sameer", "rahul", "former_colleague", 4, "Cipla 2016-20"),
    ("self", "lakshmi", "knows", 3, "Plant visit, Hyderabad"),
    ("self", "karan", "knows", 2, "Renewables conference"),
    ("lakshmi", "prakashn", "former_colleague", 4, "HAL-MTAR programme"),
    ("self", "ananya", "friend", 4, "IIT Kanpur alumni network"),
    ("ananya", "siddharth", "friend", 4, "Tata Electronics"),
    ("self", "mehul", "knows", 3, "Specialty chem roundtable"),
    ("self", "ramesh", "knows", 3, "Former SBI branch-banking expert call"),
    ("ramesh", "kavya", "knows", 3, "Microfinance industry body"),
    ("self", "deepak", "classmate", 4, "IIT Kanpur"),
    ("self", "isha", "classmate", 3, "IIM Ahmedabad"),
    ("isha", "gaurav", "former_colleague", 3, "FMCG industry"),
    ("self", "pooja", "knows", 2, "Retail investor day"),
]

FIRST = ["Aarav", "Vihaan", "Ishaan", "Riya", "Ananya", "Diya", "Kabir", "Meher", "Tara", "Arnav", "Nikhil", "Sneha",
         "Varun", "Priya", "Aditi", "Rohit", "Simran", "Yash", "Zoya", "Kunal", "Naina", "Dev", "Ira", "Manav"]
LAST = ["Agarwal", "Bose", "Chatterjee", "Desai", "Fernandes", "Gill", "Hegde", "Jain", "Khanna", "Lal", "Mishra",
        "Narayan", "Oberoi", "Patil", "Qadri", "Rastogi", "Sethi", "Thakur", "Upadhyay", "Venkatesh", "Wadhwa", "Yadav"]
POOL = [("Tata Consultancy Services", "technology"), ("Infosys", "technology"), ("Wipro", "technology"),
        ("HDFC Bank", "sales"), ("ICICI Bank", "finance"), ("State Bank of India", "sales"),
        ("Reliance Industries", "operations"), ("Bharti Airtel", "sales"), ("Maruti Suzuki India", "operations"),
        ("Larsen & Toubro", "operations"), ("Hindustan Unilever", "sales"), ("Asian Paints", "sales"),
        ("Coal India", "operations"), ("Power Grid Corporation of India", "operations"), ("Deloitte", "finance"),
        ("McKinsey & Company", "strategy"), ("Kotak Institutional Equities", "finance"), ("Dr. Reddy's Laboratories",
                                                                                          "operations")]
TITLES = {"technology": ["Engineering Manager", "Architect", "Delivery Lead"],
          "sales": ["Regional Sales Head", "Relationship Manager", "Product Manager"],
          "finance": ["Finance Manager", "Equity Analyst", "Controller"],
          "operations": ["Plant Manager", "Operations Lead", "Project Manager"],
          "strategy": ["Engagement Manager", "Strategy Lead", "Consultant"]}
UNIS = ["IIT Kanpur", "IIM Ahmedabad", "IIM Bangalore", "IIT Bombay", "IIT Madras", "Delhi School of Economics",
        "Shri Ram College of Commerce"]
# Real people named in the filings FINN reads: synthetic names must never collide with them.
REAL_NAMES = {"rashmi joshi", "vikram janakiraman", "angan guha", "sanjay dsouza", "diwakar nath misra", "sunil kumar",
              "suresh kumar narang", "gautam doshi", "piyush singh", "c jayakumar", "s ramkumar", "srinivasa rangan",
              "sriraman t", "srini pallia"}


def background(n: int, used: set[str]) -> tuple[list, list]:
    people, rels = [], []
    anchors = [a[0] for a in ANCHORS]
    for i in range(n):
        while True:
            name = f"{RNG.choice(FIRST)} {RNG.choice(LAST)}"
            if name.lower() not in used and name.lower() not in REAL_NAMES:
                used.add(name.lower())
                break
        jobs = []
        year = RNG.randint(2002, 2014)
        for _ in range(RNG.randint(1, 2)):
            org, fn = RNG.choice(POOL)
            span = RNG.randint(3, 8)
            end = year + span
            current = end >= 2026
            title = RNG.choice(TITLES[fn])
            jobs.append((org, title, fn, "manager" if span > 4 else "ic", year, None if current else end))
            year = end
            if current:
                break
        edu = [(RNG.choice(UNIS), RNG.choice(["B.Tech", "MBA", "B.Com", "PGP"]), jobs[0][4] - 1)]
        last = f"2026-{RNG.randint(1, 10):02d}-{RNG.randint(1, 28):02d}" if RNG.random() < 0.7 else \
            f"2024-{RNG.randint(1, 12):02d}-{RNG.randint(1, 28):02d}"
        key = f"bg{i:02d}"
        people.append((key, name, f"{jobs[-1][1]}, {jobs[-1][0]}", RNG.choice(["Mumbai", "Bengaluru", "Delhi", "Pune"]),
                       last, jobs, edu, [], None))
        if RNG.random() < 0.6:
            rels.append(("self", key, RNG.choice(["knows", "met_at_event", "classmate"]), RNG.randint(1, 4), None))
        else:
            rels.append((RNG.choice(anchors), key, RNG.choice(["knows", "former_colleague", "friend"]),
                         RNG.randint(2, 4), None))
    return people, rels


def main() -> None:
    used = {a[1].lower() for a in ANCHORS}
    clash = {n for n in used if n.replace("dr. ", "").replace(".", "") in REAL_NAMES}
    if clash:
        sys.exit(f"Synthetic names collide with real people in filings: {clash}")
    bg_people, bg_rels = background(30, used)

    def person(t):
        key, name, headline, loc, last, jobs, edus, exp, notes = t
        return {"key": key, "full_name": name, "headline": headline, "location": loc, "last_interaction_at": last,
                "notes": notes,
                "employments": [{"org": o, "title": ti, "function": fn, "seniority": se, "start_year": s,
                                 "end_year": e} for o, ti, fn, se, s, e in jobs],
                "educations": [{"org": o, "degree": d, "end_year": y} for o, d, y in edus],
                "expertise": [{"theme": th, "weight": w} for th, w in exp]}

    data = {
        "_about": "Synthetic demo network for FINN. Every person is fictional; organisations are real so the demo "
                  "can overlap real filings. Generated by scripts/generate_network.py (seed 2027).",
        "investor": {"id": "demo", "display_name": "Demo investor",
                     "self": {"full_name": SELF["full_name"],
                              "employments": [{"org": o, "title": t, "function": f, "seniority": s, "start_year": a,
                                               "end_year": b} for o, t, f, s, a, b in SELF["employments"]],
                              "educations": [{"org": o, "degree": d, "end_year": y} for o, d, y in SELF["educations"]]}},
        "organizations": [{"name": n, "kind": k, "sector": s, "size_bucket": z} for n, k, s, z in ORGS],
        "org_relations": [{"org": a, "related": b, "kind": k} for a, b, k in ORG_RELATIONS],
        "people": [person(t) for t in ANCHORS + bg_people],
        "relationships": [{"from": f, "to": t, "kind": k, "strength": s, "context": c,
                           "last_interaction_at": None} for f, t, k, s, c in RELATIONSHIPS + bg_rels],
    }
    keys = {p["key"] for p in data["people"]} | {"self"}
    bad = [r for r in data["relationships"] if r["from"] not in keys or r["to"] not in keys]
    if bad:
        sys.exit(f"Relationships point at unknown people: {bad[:3]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"wrote {OUT} ({len(data['people'])} people, {len(data['relationships'])} relationships)")


if __name__ == "__main__":
    main()
