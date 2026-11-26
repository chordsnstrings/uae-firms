"""Build the dashboard dataset (dashboard/farms.json) and a flat CSV (data/out/farms.csv)."""
import csv, json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from enrich_places import pick

ROOT = os.path.join(os.path.dirname(__file__), "..")
I = os.path.join(ROOT, "data", "interim")
EB3_ROLE = re.compile(r"farmworker|laborer|packer|equipment operator|meat|poultry|cutter|supervisor|mechanic|truck driver|grader|sorter|animal caretaker|nursery|greenhouse|milker", re.I)


def clean_url(u):
    u = re.sub(r"[?#].*$", "", (u or "").strip())
    return u.rstrip("/").replace("http://", "https://")


def dedupe(contacts):
    """One entry per person: the same contact often appears with a typo'd second email."""
    seen, out = set(), []
    for c in contacts:
        k = (c.get("name") or c["email"]).lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def summary(e, g):
    parts = [f"{e['sector'] or 'Agricultural employer'} based in {e['city']}, {e['state']}."]
    size = []
    if e["employees"]:
        size.append(f"about {e['employees']:,} employees")
    if e["founded"]:
        size.append(f"operating since {e['founded']}")
    if size:
        parts.append(" and ".join(size).capitalize() + ".")
    if e["perm_cases"]:
        roles = ", ".join(e["perm_jobs"][:3]) or "farm roles"
        parts.append(f"{e['perm_cases']} certified PERM green-card labour certification{'s' if e['perm_cases'] != 1 else ''} "
                     f"(FY2024–26) for {roles}.")
    if e["h2a_workers"]:
        parts.append(f"{e['h2a_workers']:,} H-2A seasonal workers certified across {e['h2a_cases']} filing{'s' if e['h2a_cases'] != 1 else ''} (FY2025–26).")
    if e["other_states"]:
        parts.append("Also hires in " + ", ".join(e["other_states"]) + ".")
    if g and g.get("rating"):
        parts.append(f"Google rating {g['rating']} ({g.get('userRatingCount', 0)} reviews).")
    return " ".join(parts)


def main():
    emps = {str(e["id"]): e for e in json.load(open(os.path.join(I, "employers.json")))}
    ids = json.load(open(os.path.join(I, "dashboard_ids.json")))
    cache = {}
    if os.path.exists(os.path.join(I, "places_cache.jsonl")):
        for line in open(os.path.join(I, "places_cache.jsonl")):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:  # a line still being written by enrich_places
                continue
            if "candidates" in r:
                cache[str(r["id"])] = r
    out, stats = [], {"places_match": 0, "web_places": 0}
    for i in ids:
        e = emps[i]
        for k in ("zip", "founded", "fein", "naics"):
            e[k] = str(e[k] or "")
        c = cache.get(i)
        conf, _, p = pick(e, c["candidates"]) if c else ("", 0, None)
        g = None
        if p:
            stats["places_match"] += 1
            g = {"name": p.get("displayName", {}).get("text", ""), "address": p.get("formattedAddress", ""),
                 "phone": p.get("nationalPhoneNumber", ""), "rating": p.get("rating"), "userRatingCount": p.get("userRatingCount", 0),
                 "status": p.get("businessStatus", ""), "maps": p.get("googleMapsUri", ""),
                 "type": (p.get("primaryTypeDisplayName") or {}).get("text", ""), "match": conf}
        web, src = e["website"], e["website_source"]
        if p and p.get("websiteUri"):
            web, src = clean_url(p["websiteUri"]), "Google Places"
            stats["web_places"] += 1
        out.append({"id": i, "tier": e["tier"], "name": e["name"], "dba": e["dba"], "address": e["address"],
            "city": e["city"], "state": e["state"], "zip": e["zip"], "phone": e["phone"] or (g or {}).get("phone", ""),
            "naics": e["naics"], "sector": e["sector"], "yearRound": e["year_round_sector"], "employees": e["employees"],
            "founded": e["founded"], "perm": e["perm_cases"], "permJobs": e["perm_jobs"],
            "eb3Roles": bool(e["perm_cases"]) and any(EB3_ROLE.search(j) for j in e["perm_jobs"]),
            "h2aCases": e["h2a_cases"], "h2aWorkers": e["h2a_workers"], "jobs": e["jobs"], "otherStates": e["other_states"],
            "lawFirm": e["law_firm"], "website": web, "websiteSource": src, "contacts": dedupe(e["contacts"]),
            "lastFiling": e["last_filing"], "score": e["score"], "google": g, "summary": summary(e, g)})
    out.sort(key=lambda r: -r["score"])
    with open(os.path.join(ROOT, "dashboard", "farms.json"), "w") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) for r in out) + "\n]\n")
    os.makedirs(os.path.join(ROOT, "data", "out"), exist_ok=True)
    cols = ["tier", "score", "name", "dba", "sector", "naics", "address", "city", "state", "zip", "phone", "website",
            "websiteSource", "employees", "founded", "perm", "h2aWorkers", "lastFiling", "lawFirm", "summary"]
    with open(os.path.join(ROOT, "data", "out", "farms.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols + [f"contact{n}_{k}" for n in (1, 2, 3) for k in ("name", "title", "email", "phone")] + ["google_maps", "google_rating"])
        for r in out:
            cs = (r["contacts"] + [{}] * 3)[:3]
            w.writerow([r[c] for c in cols] + [c.get(k, "") for c in cs for k in ("name", "title", "email", "phone")]
                       + [(r["google"] or {}).get("maps", ""), (r["google"] or {}).get("rating", "")])
    n = len(out)
    print(f"{n:,} farms | tier A {sum(r['tier'] == 'A' for r in out):,} | email {sum(bool(r['contacts']) for r in out):,} "
          f"| website {sum(bool(r['website']) for r in out):,} | places matched {stats['places_match']:,} (websites {stats['web_places']:,}) "
          f"| looked up {len(cache):,}")


if __name__ == "__main__":
    main()
