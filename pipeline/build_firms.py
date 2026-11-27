"""Immigration law firms / agents that file EB-3 worker-level PERM cases, from DOL PERM disclosure data.

EB-3 worker roles = PERM cases whose occupation is not a professional/degree occupation: SOC major groups
31,33,35,37,39,41,43,45,47,49,51,53 (care aides, food, cleaning, farm, construction, production, drivers...).
Those cases go to EB-3 (skilled / other workers), not EB-2. FY2024 new-form rows have no SOC, so job-title
keywords stand in.  Output: dashboard/firms.json + data/out/firms.csv
"""
import csv, glob, hashlib, json, math, os, re, sys
from collections import Counter
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from load_dol import read, RAW
from build_dataset import FREEMAIL, phone, clean_name, domain
from enrich_places import pick

ROOT = os.path.join(os.path.dirname(__file__), "..")
I = os.path.join(ROOT, "data", "interim")
COLS = ["CASE_NUMBER", "CASE_STATUS", "DECISION_DATE", "EMP_BUSINESS_NAME", "EMP_NAICS", "EMP_STATE",
    "ATTY_AG_REP_TYPE", "ATTY_AG_LAST_NAME", "ATTY_AG_FIRST_NAME", "ATTY_AG_ADDRESS1", "ATTY_AG_CITY", "ATTY_AG_STATE",
    "ATTY_AG_POSTAL_CODE", "ATTY_AG_PHONE", "ATTY_AG_EMAIL", "ATTY_AG_LAW_FIRM_NAME", "PWD_SOC_CODE", "PWD_SOC_TITLE",
    "JOB_TITLE", "PRIMARY_WORKSITE_STATE", "JOB_OPP_WAGE_FROM", "JOB_OPP_WAGE_PER", "ATTY_AG_STATE_BAR_NUMBER",
    "ATTY_AG_GOOD_STANDING_STATE"]
H2A_COLS = ["CASE_NUMBER", "CASE_STATUS", "EMPLOYER_NAME", "TYPE_OF_REPRESENTATION", "ATTORNEY_AGENT_LAST_NAME",
    "ATTORNEY_AGENT_FIRST_NAME", "ATTORNEY_AGENT_STATE", "LAWFIRM_NAME_BUSINESS_NAME", "TOTAL_WORKERS_H2A_CERTIFIED",
    "ATTORNEY_AGENT_EMAIL"]
EMAIL_OK = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)*\.[a-z]{2,}$")
PER_YEAR = {"hour": 2080, "week": 52, "bi-weekly": 26, "month": 12, "year": 1}
WORKER_SOC = ("31", "33", "35", "37", "39", "41", "43", "45", "47", "49", "51", "53")
SOC_GROUP = {"31": "Healthcare support", "33": "Protective service", "35": "Food prep & serving", "37": "Cleaning & grounds",
    "39": "Personal care", "41": "Sales", "43": "Office support", "45": "Farming", "47": "Construction",
    "49": "Installation & repair", "51": "Production & processing", "53": "Transport & warehousing"}
WORKER_TITLE = re.compile(r"farm|labor|packer|packag|cook|housekeep|cleaner|janitor|caregiver|\baide\b|nursing assist|driver|"
    r"meat|poultry|cutter|butcher|trimmer|construction|carpenter|mason|welder|mechanic|operator|assembler|warehouse|forklift|"
    r"dishwash|food|server|landscap|painter|plumber|roofer|production|sewing|baker|groundskeep|maid|nanny|child ?care|"
    r"helper|installer|technician|machinist|stock|cashier|attendant|dairy|milker|harvest|nursery|greenhouse", re.I)
SECTOR = {"11": "Agriculture", "21": "Mining & oil", "22": "Utilities", "23": "Construction", "31": "Manufacturing",
    "32": "Manufacturing", "33": "Manufacturing", "42": "Wholesale", "44": "Retail", "45": "Retail", "48": "Transport & warehousing",
    "49": "Transport & warehousing", "51": "Information", "52": "Finance", "53": "Real estate", "54": "Professional services",
    "55": "Management", "56": "Staffing & facility services", "61": "Education", "62": "Health care & senior care",
    "71": "Recreation", "72": "Hotels & restaurants", "81": "Other services", "92": "Government"}
SUB = {"3116": "Meat & poultry processing", "311": "Food manufacturing", "623": "Nursing & residential care",
    "6216": "Home health care", "721": "Hotels", "722": "Restaurants", "5613": "Staffing agencies"}
FIRM_STOP = r"\b(THE|LAW|LAWS|OFFICES?|OF|FIRM|GROUP|PLLC|PLC|LLC|LLP|LTD|PC|P C|PA|P A|INC|CORP|ATTORNEYS?|AT|COUNSELORS?|AND|ASSOCIATES|IMMIGRATION|LEGAL|SERVICES?)\b"


def load():
    cache = os.path.join(I, "perm_all_v2.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    frames = []
    for f in sorted(glob.glob(os.path.join(RAW, "PERM_Disclosure_Data*.xlsx"))):
        df = read(f, COLS)
        df["SOURCE_FILE"] = os.path.basename(f)
        frames.append(df)
        print(f"{os.path.basename(f)}: {len(df):,} rows", file=sys.stderr)
    df = pd.concat(frames, ignore_index=True).fillna("")
    df.to_parquet(cache, index=False)
    return df


def make_key(firm, first, last, state):
    f = re.sub(r"[^A-Z0-9 ]", " ", str(firm).upper())
    f = re.sub(r"\s+", " ", re.sub(FIRM_STOP, " ", f)).strip()
    if f:
        return f
    who = f"{first} {last}".strip().upper()
    return f"ATTY {who} {str(state).upper().strip()}" if who else ""


def firm_key(r):
    return make_key(r.ATTY_AG_LAW_FIRM_NAME, r.ATTY_AG_FIRST_NAME, r.ATTY_AG_LAST_NAME, r.ATTY_AG_STATE)


def load_h2a():
    """H-2A filings per representative: cases, workers certified, employers (FY2025-26)."""
    cache = os.path.join(I, "h2a_reps_v2.parquet")
    if not os.path.exists(cache):
        frames = [read(f, H2A_COLS) for f in sorted(glob.glob(os.path.join(RAW, "H-2A_Disclosure_Data*.xlsx")))]
        pd.concat(frames, ignore_index=True).fillna("").to_parquet(cache, index=False)
    h = pd.read_parquet(cache)
    h = h[(h.ATTORNEY_AGENT_LAST_NAME.str.strip() != "") & ~h.CASE_STATUS.str.contains("Withdrawn|Denied")]
    h["key"] = [make_key(*t) for t in zip(h.LAWFIRM_NAME_BUSINESS_NAME, h.ATTORNEY_AGENT_FIRST_NAME, h.ATTORNEY_AGENT_LAST_NAME, h.ATTORNEY_AGENT_STATE)]
    h["workers"] = pd.to_numeric(h.TOTAL_WORKERS_H2A_CERTIFIED, errors="coerce").fillna(0)
    h["dom"] = h.ATTORNEY_AGENT_EMAIL.map(domain)
    h.loc[h.dom.isin(FREEMAIL), "dom"] = ""
    out = {}
    for col in ("key", "dom"):  # match by firm name, or by the agent's email domain (same firm, different entity name)
        agg = h[h[col] != ""].groupby(col).agg(cases=("CASE_NUMBER", "nunique"), workers=("workers", "sum"), employers=("EMPLOYER_NAME", "nunique"))
        out[col] = {k: {"cases": int(r.cases), "workers": int(r.workers), "employers": int(r.employers)} for k, r in agg.iterrows()}
    return out


def annual(wage, per):
    try:
        w = float(str(wage).replace(",", "").replace("$", ""))
    except ValueError:
        return None
    m = PER_YEAR.get(str(per).strip().lower())
    return w * m if m and 10_000 <= w * m <= 400_000 else None


def fiscal_year(d):
    return f"FY{d.year + 1 if d.month >= 10 else d.year}" if pd.notna(d) else ""


def sector(naics):
    n = re.sub(r"\D", "", re.sub(r"\.0$", "", str(naics)))
    for k in (n[:4], n[:3]):
        if k in SUB:
            return SUB[k]
    return SECTOR.get(n[:2], "Other")


def nice(s):
    s = clean_name(s)
    return s.title() if s.isupper() or s.islower() else s


def main():
    df = load()
    df = df[df.ATTY_AG_LAST_NAME.str.strip() != ""].copy()
    soc = df.PWD_SOC_CODE.str.strip()
    df["worker"] = soc.str[:2].isin(WORKER_SOC) | ((soc == "") & df.JOB_TITLE.str.contains(WORKER_TITLE))
    df["role"] = df.PWD_SOC_TITLE.where(df.PWD_SOC_TITLE.str.strip() != "", df.JOB_TITLE).map(clean_name)
    df["cert"] = df.CASE_STATUS.str.startswith("Certified")
    df["denied"] = df.CASE_STATUS.str.startswith("Denied")
    df["date"] = pd.to_datetime(df.DECISION_DATE, errors="coerce")
    df["key"] = df.apply(firm_key, axis=1)
    df = df[df.key != ""]
    print(f"PERM cases with a representative: {len(df):,} | EB-3 worker-role cases: {int(df.worker.sum()):,}", file=sys.stderr)
    totals = df.groupby("key").size()
    h2a = load_h2a()
    w = df[df.worker]
    out = []
    for key, g in w.groupby("key"):
        n = len(g)
        if n < 5:
            continue
        cert, den = int(g.cert.sum()), int(g.denied.sum())
        office = g[["ATTY_AG_ADDRESS1", "ATTY_AG_CITY", "ATTY_AG_STATE", "ATTY_AG_POSTAL_CODE"]].astype(str).agg("|".join, axis=1).value_counts().index[0].split("|")
        names = g.ATTY_AG_LAW_FIRM_NAME.map(clean_name)
        name = nice(names[names != ""].value_counts().index[0]) if (names != "").any() else nice(f"{g.ATTY_AG_FIRST_NAME.iloc[0]} {g.ATTY_AG_LAST_NAME.iloc[0]}")
        people = []
        for (first, last), pg in g.groupby([g.ATTY_AG_FIRST_NAME.str.strip().str.upper(), g.ATTY_AG_LAST_NAME.str.strip().str.upper()]):
            em = pg.ATTY_AG_EMAIL.str.strip().str.lower()
            bar_no = pg.ATTY_AG_STATE_BAR_NUMBER.str.strip()
            bar_st = pg.ATTY_AG_GOOD_STANDING_STATE.str.strip()
            people.append({"name": nice(f"{first} {last}"), "email": em[em != ""].value_counts().index[0] if (em != "").any() else "",
                           "phone": phone(pg.ATTY_AG_PHONE.value_counts().index[0]), "cases": len(pg),
                           "bar": " ".join(x for x in [bar_st[bar_st != ""].value_counts().index[0] if (bar_st != "").any() else "",
                                   ("#" + re.sub(r"\.0$", "", bar_no[bar_no != ""].value_counts().index[0])) if (bar_no != "").any() else ""] if x)})
        people.sort(key=lambda p: -p["cases"])
        doms = Counter(domain(p["email"]) for p in people for _ in range(p["cases"]))
        web = next((d for d, _ in doms.most_common() if d and d not in FREEMAIL and not d.endswith((".gov", ".edu"))), "")
        g_sec = g.EMP_NAICS.map(sector)
        ag = int(g.EMP_NAICS.astype(str).str.match(r"^11[125]").sum())
        clients = g.EMP_BUSINESS_NAME.map(clean_name).value_counts()
        share = n / totals[key]
        score = math.log10(n) * 30 + share * 30 + (cert / max(cert + den, 1)) * 15 + (10 if ag else 0) + min(clients.size, 50) * 0.3
        roles = [[r, c] for r, c in g.role.value_counts().head(5).items() if r]
        groups = [[SOC_GROUP.get(s, ""), c] for s, c in g.PWD_SOC_CODE.str[:2].value_counts().items() if s in SOC_GROUP][:4]
        rec = {"id": hashlib.md5(key.encode()).hexdigest()[:12], "name": name, "type": g.ATTY_AG_REP_TYPE.value_counts().index[0] or "Attorney",
            "address": nice(office[0]), "city": nice(office[1]), "state": office[2].upper().strip(), "zip": office[3][:5],
            "phone": people[0]["phone"] if people else "", "website": f"https://{web}" if web else "",
            "websiteSource": "attorney email domain" if web else "", "eb3": n, "eb3Cert": cert, "eb3Denied": den,
            "approval": round(cert / (cert + den), 3) if cert + den else None, "totalPerm": int(totals[key]), "eb3Share": round(share, 3),
            "clients": int(clients.size), "agClients": int(g[g.EMP_NAICS.astype(str).str.match(r"^11[125]")].EMP_BUSINESS_NAME.nunique()),
            "agCases": ag, "roles": roles, "roleGroups": groups,
            "industries": [[s, c] for s, c in g_sec.value_counts().head(4).items()],
            "clientStates": [s for s, _ in g.PRIMARY_WORKSITE_STATE.str.upper().str.strip().value_counts().head(6).items() if s],
            "sampleClients": [nice(c) for c in clients.head(5).index], "attorneys": people[:5],
            "lastFiling": str(g.date.max().date()) if pd.notna(g.date.max()) else "", "score": round(score, 1)}
        rec["specialist"] = bool(n >= 20 and share >= 0.5)
        yrs = g.date.map(fiscal_year).value_counts()
        rec["byYear"] = {fy: int(yrs.get(fy, 0)) for fy in ("FY2024", "FY2025", "FY2026")}
        wages = [x for x in (annual(a, b) for a, b in zip(g.JOB_OPP_WAGE_FROM, g.JOB_OPP_WAGE_PER)) if x]
        rec["medianWage"] = int(pd.Series(wages).median()) if wages else None
        rec["attorneyCount"] = len(people)
        rec["h2a"] = h2a["key"].get(key) or (h2a["dom"].get(web) if web else None)
        top_inds = ", ".join(s for s, _ in rec["industries"][:3])
        rec["summary"] = (f"{rec['type']} representative based in {rec['city']}, {rec['state']}. Filed {n:,} EB-3 worker-level PERM cases "
            f"FY2024–26 ({share:.0%} of their {rec['totalPerm']:,} PERM filings) for {rec['clients']:,} employers, mainly in {top_inds}. "
            + (f"Approval rate {rec['approval']:.0%} ({cert:,} certified, {den:,} denied). " if rec["approval"] is not None else "")
            + (f"Agriculture clients: {rec['agClients']} ({ag} cases). " if ag else "")
            + (f"Also files H-2A seasonal farm visas: {rec['h2a']['cases']:,} cases, {rec['h2a']['workers']:,} workers for {rec['h2a']['employers']:,} farms (FY2025–26)." if rec.get("h2a") else ""))
        out.append(rec)
    out.sort(key=lambda r: -r["score"])
    # Google Places for firms without a website (python pipeline/enrich_places.py --input dashboard/firms.json
    #   --ids-file data/interim/firms_enrich_ids.json --cache data/interim/firms_places_cache.jsonl)
    json.dump([r["id"] for r in out if not r["website"]], open(os.path.join(I, "firms_enrich_ids.json"), "w"))
    cache_path = os.path.join(I, "firms_places_cache.jsonl")
    cache = {}
    if os.path.exists(cache_path):
        for line in open(cache_path):
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "candidates" in c:
                cache[c["id"]] = c
    for r in out:
        c = cache.get(r["id"])
        conf, _, p = pick(r, c["candidates"]) if c else ("", 0, None)
        r["google"] = None
        if p:
            r["google"] = {"name": p.get("displayName", {}).get("text", ""), "phone": p.get("nationalPhoneNumber", ""),
                "rating": p.get("rating"), "userRatingCount": p.get("userRatingCount", 0), "maps": p.get("googleMapsUri", ""), "match": conf,
                "summary": (p.get("editorialSummary") or {}).get("text", "")}
            if not r["website"] and p.get("websiteUri"):
                r["website"] = re.sub(r"[?#].*$", "", p["websiteUri"]).rstrip("/").replace("http://", "https://")
                r["websiteSource"] = "Google Places"
    # Facts from the firm's own website (python pipeline/scrape_firm_sites.py)
    sites = {}
    sp = os.path.join(I, "firm_sites.jsonl")
    if os.path.exists(sp):
        for line in open(sp):
            try:
                x = json.loads(line)
            except json.JSONDecodeError:
                continue
            if x.get("ok"):
                x["emails"] = [e for e in x["emails"] if EMAIL_OK.match(e)]
                for k in ("title", "description", "about"):  # pages served in a mislabelled charset
                    x[k] = re.sub(r"\s+", " ", x[k].replace("\ufffd", " ")).strip()
                sites[x["id"]] = {k: x[k] for k in ("title", "description", "about", "languages", "countries", "social",
                                                    "emails", "phones", "founded", "mentions")}
    for r in out:
        r["site"] = sites.get(r["id"])
    with open(os.path.join(ROOT, "dashboard", "firms.json"), "w") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False, default=lambda o: o.item()) for r in out) + "\n]\n")
    os.makedirs(os.path.join(ROOT, "data", "out"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "out", "firms.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        cols = ["name", "type", "address", "city", "state", "zip", "phone", "website", "eb3", "eb3Cert", "eb3Denied", "approval",
                "totalPerm", "eb3Share", "clients", "agClients", "specialist", "lastFiling", "summary"]
        wr.writerow(cols + [f"attorney{i}_{k}" for i in (1, 2, 3) for k in ("name", "email", "phone", "cases")])
        for r in out:
            ats = (r["attorneys"] + [{}] * 3)[:3]
            wr.writerow([r[c] for c in cols] + [a.get(k, "") for a in ats for k in ("name", "email", "phone", "cases")])
    print(f"{len(out):,} firms with >=5 EB-3 worker cases | specialists {sum(r['specialist'] for r in out):,} | "
          f"ag clients {sum(r['agClients'] > 0 for r in out):,} | with website {sum(bool(r['website']) for r in out):,} | "
          f"with attorney email {sum(any(a['email'] for a in r['attorneys']) for r in out):,} | H-2A too {sum(bool(r['h2a']) for r in out):,} | "
          f"site profile {sum(bool(r['site']) for r in out):,} | wage {sum(r['medianWage'] is not None for r in out):,}")
    for r in out[:8]:
        print(f"  {r['name'][:40]:40} {r['state']} eb3={r['eb3']:5} share={r['eb3Share']:.0%} appr={r['approval']} ag={r['agClients']} {r['website']}")


if __name__ == "__main__":
    main()
