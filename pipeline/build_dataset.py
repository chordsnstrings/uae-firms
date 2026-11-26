"""Merge agriculture PERM (EB-3 labour certification) + H-2A filings into one row per employer.

Tier A = filed PERM for a farm job (direct evidence of EB-3 sponsorship).
Tier B = direct H-2A farm employer (already uses foreign labour; not a labour contractor).
"""
import json, math, os, re
import pandas as pd

D = os.path.join(os.path.dirname(__file__), "..", "data")
NAICS = {"1111": "Oilseed & grain farming", "111110": "Soybean farming", "111150": "Corn farming",
    "1112": "Vegetable & melon farming", "111211": "Potato farming", "1113": "Fruit & tree nut farming",
    "111310": "Orange groves", "111320": "Citrus groves", "111331": "Apple orchards", "111332": "Vineyards",
    "111333": "Strawberry farming", "111334": "Berry farming", "111335": "Tree nut farming",
    "1114": "Greenhouse, nursery & floriculture", "111411": "Mushroom production",
    "111419": "Greenhouse food crops", "111421": "Nursery & tree production", "111422": "Floriculture",
    "1119": "Other crop farming", "111910": "Tobacco farming", "111920": "Cotton farming",
    "111930": "Sugarcane farming", "111940": "Hay farming", "111991": "Sugar beet farming",
    "111992": "Peanut farming", "1121": "Cattle ranching & farming", "112111": "Beef cattle ranching",
    "112112": "Cattle feedlots", "112120": "Dairy farm (milk production)", "1122": "Hog & pig farming",
    "1123": "Poultry & egg production", "112310": "Chicken egg production", "112320": "Broiler chicken production",
    "112330": "Turkey production", "112340": "Poultry hatchery", "1124": "Sheep & goat farming",
    "1125": "Aquaculture", "1129": "Other animal production", "112920": "Horse & equine farm",
    "1151": "Crop production support", "115111": "Cotton ginning", "115112": "Soil prep, planting & cultivating",
    "115113": "Machine crop harvesting", "115114": "Post-harvest crop processing (packing, shelling)",
    "115115": "Farm labour contractor", "115116": "Farm management services", "1152": "Animal production support",
    "111": "Crop farming", "112": "Animal production", "115": "Agricultural support"}
# Year-round, labour-intensive sectors where EB-3 "other worker" roles are common.
YEAR_ROUND = ("112120", "1122", "1123", "112112", "1114", "111411", "115114", "1125")
FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "live.com",
    "msn.com", "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "bellsouth.net", "me.com",
    "ymail.com", "protonmail.com", "charter.net", "frontier.com", "windstream.net", "centurylink.net"}


def naics(code):
    c = re.sub(r"\.0$", "", str(code)).strip()
    return re.sub(r"\D", "", c)


def naics_title(c):
    for n in range(len(c), 2, -1):
        if c[:n] in NAICS:
            return NAICS[c[:n]]
    return ""


def fein(x):
    d = re.sub(r"\D", "", str(x))
    return d if len(d) == 9 else ""


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


def phone(x):
    d = re.sub(r"\D", "", str(x).split(".")[0])
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else str(x).strip()


def clean_name(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def name_key(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper())
    s = re.sub(r"\b(LLC|LLP|INC|CO|CORP|CORPORATION|COMPANY|LTD|LP|PLLC|THE|DBA)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def domain(email):
    m = re.search(r"@([\w.-]+\.[a-z]{2,})$", str(email).strip().lower())
    return m.group(1) if m else ""


def load():
    p = pd.read_parquet(os.path.join(D, "interim", "perm_ag.parquet")).fillna("")
    h = pd.read_parquet(os.path.join(D, "interim", "h2a_ag.parquet")).fillna("")
    p = pd.DataFrame({
        "src": "PERM", "case": p.CASE_NUMBER, "status": p.CASE_STATUS, "date": p.DECISION_DATE,
        "name": p.EMP_BUSINESS_NAME.map(clean_name), "dba": p.EMP_TRADE_NAME.map(clean_name),
        "addr": p.EMP_ADDR1, "city": p.EMP_CITY.str.title(), "state": p.EMP_STATE.str.upper().str.strip(),
        "zip": p.EMP_POSTCODE.str[:5], "phone": p.EMP_PHONE, "fein": p.EMP_FEIN.map(fein),
        "naics": p.EMP_NAICS.map(naics), "employees": p.EMP_NUM_PAYROLL.map(num),
        "founded": p.EMP_YEAR_COMMENCED.str[:4], "poc_first": p.EMP_POC_FIRST_NAME, "poc_last": p.EMP_POC_LAST_NAME,
        "poc_title": p.EMP_POC_JOB_TITLE, "poc_phone": p.EMP_POC_PHONE, "poc_email": p.EMP_POC_EMAIL.str.strip().str.lower(),
        "job": p.PWD_SOC_TITLE.where(p.PWD_SOC_TITLE != "", p.JOB_TITLE), "workers": 0.0,
        "law_firm": p.ATTY_AG_LAW_FIRM_NAME, "web_apply": "", "work_state": p.PRIMARY_WORKSITE_STATE,
        "is_lc": False})
    h = pd.DataFrame({
        "src": "H-2A", "case": h.CASE_NUMBER, "status": h.CASE_STATUS, "date": h.DECISION_DATE,
        "name": h.EMPLOYER_NAME.map(clean_name), "dba": h.TRADE_NAME_DBA.map(clean_name),
        "addr": h.EMPLOYER_ADDRESS_1, "city": h.EMPLOYER_CITY.str.title(), "state": h.EMPLOYER_STATE.str.upper().str.strip(),
        "zip": h.EMPLOYER_POSTAL_CODE.str[:5], "phone": h.EMPLOYER_PHONE, "fein": h.EMPLOYER_FEIN.map(fein),
        "naics": h.NAICS_CODE.map(naics), "employees": 0.0, "founded": "",
        "poc_first": h.EMPLOYER_POC_FIRST_NAME, "poc_last": h.EMPLOYER_POC_LAST_NAME, "poc_title": h.EMPLOYER_POC_JOB_TITLE,
        "poc_phone": h.EMPLOYER_POC_PHONE, "poc_email": h.EMPLOYER_POC_EMAIL.str.strip().str.lower(),
        "job": h.SOC_TITLE, "workers": h.TOTAL_WORKERS_H2A_CERTIFIED.map(num), "law_firm": "",
        "web_apply": h.WEBSITE_TO_APPLY, "work_state": h.WORKSITE_STATE,
        "is_lc": (h.H2A_LABOR_CONTRACTOR == "Y") | h.NAICS_CODE.map(naics).str.startswith("115115")})
    df = pd.concat([p, h], ignore_index=True)
    df = df[~df.status.str.contains("Withdrawn|Denied", case=False)]
    df["date"] = pd.to_datetime(df.date, errors="coerce")
    df["key"] = df.fein.where(df.fein != "", df.name.map(name_key) + "|" + df.state)
    return df


def employer(key, g, agent_domains):
    g = g.sort_values("date", ascending=False)
    perm, h2a = g[g.src == "PERM"], g[g.src == "H-2A"]
    top = (perm if len(perm) else h2a).iloc[0]
    contacts, seen = [], set()
    for _, r in pd.concat([perm, h2a]).iterrows():
        e = r.poc_email
        if e and e not in seen and domain(e) not in agent_domains:
            seen.add(e)
            contacts.append({"name": clean_name(f"{r.poc_first} {r.poc_last}").title(),
                "title": clean_name(r.poc_title), "email": e, "phone": phone(r.poc_phone)})
        if len(contacts) == 3:
            break
    web = ""
    for w in h2a.web_apply:
        w = str(w).strip().lower()
        if re.match(r"^(https?://)?(www\.)?[\w-]+\.[\w.]+", w) and not re.search(r"dol\.gov|seasonaljobs|n/?a$|none|jobs?\.|indeed|\.state\.|workforce|\.gov", w):
            web = w if w.startswith("http") else "https://" + w
            break
    web_src = "DOL filing" if web else ""
    if not web:
        for c in contacts:
            d = domain(c["email"])
            if d and d not in FREEMAIL and not d.endswith((".gov", ".edu")):
                web, web_src = "https://" + d, "email domain"
                break
    code = top.naics or (h2a.naics.iloc[0] if len(h2a) else "")
    perm_cert = int(perm.status.str.startswith("Certified").sum())
    workers = int(h2a.groupby(h2a.case.str[:14]).workers.max().sum()) if len(h2a) else 0
    emp = int(perm.employees.max()) if len(perm) else 0
    jobs = [j for j, _ in pd.Series([x for x in g.job if x]).value_counts().head(3).items()] if g.job.any() else []
    yr = code.startswith(YEAR_ROUND)
    score = (40 if perm_cert else 0) + min(perm_cert, 20) * 2 + min(math.log10(workers + 1) * 10, 30) + (15 if yr else 0) \
        + (5 if contacts else 0) + (min(math.log10(emp + 1) * 3, 10) if emp else 0)
    states = sorted({s for s in g.work_state if s and s != top.state})[:5]
    return {"id": key, "tier": "A" if len(perm) else "B", "name": top["name"].title() if top["name"].isupper() else top["name"],
        "dba": top.dba if top.dba.lower() not in ("", "n/a", "na", "none") else "",
        "address": clean_name(top.addr).title(), "city": top.city, "state": top.state, "zip": top.zip,
        "phone": phone(top.phone), "fein": top.fein, "naics": code, "sector": naics_title(code),
        "year_round_sector": bool(yr), "employees": emp, "founded": top.founded if top.founded.isdigit() else "",
        "perm_cases": perm_cert, "perm_jobs": sorted({j for j in perm.job if j})[:3],
        "h2a_cases": int(len(h2a)), "h2a_workers": workers, "jobs": jobs, "other_states": states,
        "law_firm": next((x for x in perm.law_firm if x), ""), "website": web, "website_source": web_src,
        "contacts": contacts, "last_filing": str(g.date.max().date()) if pd.notna(g.date.max()) else "",
        "score": round(score, 1)}


def main():
    df = load()
    df = df[~(df.is_lc & (df.src == "H-2A"))]
    d = df.poc_email.map(domain)
    per_dom = df.assign(d=d)[d != ""].groupby("d").key.nunique()
    agent_domains = set(per_dom[per_dom >= 5].index) - FREEMAIL  # agents / law firms filing for many farms
    rows = [employer(k, g, agent_domains) for k, g in df.groupby("key")]
    out = pd.DataFrame(rows).sort_values("score", ascending=False)
    out.to_json(os.path.join(D, "interim", "employers.json"), orient="records")
    # Dashboard set: every PERM filer + bigger / year-round H-2A farms. Places lookups: tier A + anyone without a website.
    sel = out[(out.tier == "A") | (out.h2a_workers >= 50) | (out.year_round_sector & (out.h2a_workers >= 10))]
    enrich = sel[(sel.tier == "A") | (sel.website == "")]
    json.dump([str(i) for i in sel.id], open(os.path.join(D, "interim", "dashboard_ids.json"), "w"))
    json.dump([str(i) for i in enrich.id], open(os.path.join(D, "interim", "enrich_ids.json"), "w"))
    print(f"dashboard set {len(sel):,} | Places lookups needed {len(enrich):,}")
    print(f"{len(out):,} employers | tier A (PERM) {sum(out.tier == 'A'):,} | tier B (H-2A) {sum(out.tier == 'B'):,}")
    print(f"with contact email {sum(out.contacts.str.len() > 0):,} | with website {sum(out.website != ''):,} | agent domains excluded {len(agent_domains)}")
    print("B by h2a_workers>=20:", sum((out.tier == 'B') & (out.h2a_workers >= 20)), ">=50:", sum((out.tier == 'B') & (out.h2a_workers >= 50)),
          "year-round B:", sum((out.tier == 'B') & out.year_round_sector))


if __name__ == "__main__":
    main()
