"""Enrich employers with Google Places API (New) Text Search: website, phone, rating, status, maps link.

Needs GOOGLE_PLACES_API_KEY in the environment. Results are cached in data/interim/places_cache.jsonl
so a rerun never bills the same employer twice. Usage: enrich_places.py [--limit N] [--ids-file f] [--input records.json] [--cache f.jsonl]
"""
import argparse, json, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import requests

D = os.path.join(os.path.dirname(__file__), "..", "data", "interim")
CACHE = os.path.join(D, "places_cache.jsonl")
URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join("places." + f for f in ["id", "displayName", "formattedAddress", "nationalPhoneNumber",
    "websiteUri", "rating", "userRatingCount", "businessStatus", "googleMapsUri", "primaryTypeDisplayName"])
STOP = r"\b(LLC|LLP|INC|CO|CORP|CORPORATION|COMPANY|LTD|LP|PLLC|THE|DBA|FARMS?|DAIRY|RANCH|AND)\b"
lock = threading.Lock()


def norm(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper())
    return re.sub(r"\s+", " ", re.sub(STOP, " ", s)).strip()


def score(emp, place):
    """Return (confidence, similarity). Confidence is 'high', 'medium' or '' (rejected)."""
    a, b = norm(emp["name"]), norm(place.get("displayName", {}).get("text", ""))
    sim = SequenceMatcher(None, a, b).ratio() if a and b else 0
    ta, tb = {t for t in a.split() if len(t) >= 3}, {t for t in b.split() if len(t) >= 3}
    if emp.get("dba"):
        d = norm(emp["dba"])
        sim = max(sim, SequenceMatcher(None, d, b).ratio())
        ta |= {t for t in d.split() if len(t) >= 3}
    shared = len(ta & tb)
    contained = shared > 0 and shared == min(len(ta), len(tb))
    addr = place.get("formattedAddress", "")
    if not re.search(rf",\s*{emp['state']}\s+\d{{5}}", addr):
        return "", sim
    same_city = bool(emp["city"]) and emp["city"].lower() in addr.lower()
    web = (place.get("websiteUri") or "").lower()
    people = emp.get("contacts") or emp.get("attorneys") or []
    dom_match = any(c["email"].split("@")[-1] in web for c in people if "@" in c.get("email", ""))
    if dom_match or sim >= 0.85 or (contained and same_city):
        return "high", sim
    if sim >= 0.7 or contained or shared >= 2:
        return "medium", sim
    return "", sim


def lookup(emp, key):
    q = f"{emp['name']} {emp['city']} {emp['state']}"
    for attempt in range(6):  # back off on the per-minute quota (HTTP 429)
        r = requests.post(URL, timeout=30, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS},
                          json={"textQuery": q, "pageSize": 3, "regionCode": "US"})
        if r.status_code != 429:
            break
        time.sleep(10 * (attempt + 1))
    if r.status_code != 200:
        return {"id": emp["id"], "error": r.status_code, "detail": r.text[:200]}
    places = r.json().get("places", [])
    conf, sim, best = pick(emp, places)
    return {"id": emp["id"], "query": q, "match": conf, "similarity": round(sim, 2), "place": best, "candidates": places}


def pick(emp, places):
    """Best accepted candidate: prefer high over medium, then similarity."""
    best, rank = ("", 0, None), (-1, 0)
    for p in places:
        c, s = score(emp, p)
        r = ({"high": 2, "medium": 1}.get(c, -1), s)
        if c and r > rank:
            best, rank = (c, s, p), r
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids-file", default=os.path.join(D, "enrich_ids.json"))
    ap.add_argument("--input", default=os.path.join(D, "employers.json"), help="JSON array of records with id/name/city/state")
    ap.add_argument("--cache", default=CACHE)
    a = ap.parse_args()
    key = os.environ["GOOGLE_PLACES_API_KEY"]
    emps = {str(e["id"]): e for e in json.load(open(a.input))}
    ids = [str(i) for i in json.load(open(a.ids_file))]
    done = set()
    if os.path.exists(a.cache):
        done = {str(json.loads(l)["id"]) for l in open(a.cache) if '"candidates"' in l}
    todo = [emps[i] for i in ids if i not in done and i in emps]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(done)} cached, {len(todo)} to look up")
    stats = {"high": 0, "medium": 0, "": 0, "error": 0}
    with open(a.cache, "a") as f, ThreadPoolExecutor(4) as ex:
        for res in ex.map(lambda e: lookup(e, key), todo):
            with lock:
                f.write(json.dumps(res) + "\n")
                stats["error" if "error" in res else res["match"]] += 1
    print("results:", stats)


if __name__ == "__main__":
    main()
