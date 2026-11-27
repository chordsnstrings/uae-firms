# US farm EB-3 prospects

Finds US farms likely to recruit EB-3 immigrant workers and lists them in a dashboard with
website, contact email and phone (the HR/owner contact named on federal filings), a short company
profile, and a shared **contacted** tick plus notes.

## How farms are found

| Tier | Evidence | Source |
|---|---|---|
| **A: filed PERM** | The farm filed a PERM labour certification, the first step of an EB-2/EB-3 green card, FY2024–FY2026. Direct evidence they sponsor. | DOL OFLC PERM disclosure data |
| **B: H-2A user** | Direct farm employer (not a labour contractor) certified for H-2A seasonal workers FY2025–26, already working with foreign labour. Included if ≥50 workers, or ≥10 in a year-round sector. | DOL OFLC H-2A disclosure data |

Agriculture = NAICS 111 (crops), 112 (animal production), 1151/1152 (farm support). Withdrawn and denied
cases are dropped; H-2A labour contractors are excluded.

Each filing names an employer point of contact (name, job title, email, phone), and those become the
contacts. Contact emails from agent or law-firm domains that file for 5+ unrelated farms are dropped.
Websites come from Google Places (API "New" Text Search), the H-2A "website to apply" field, or the contact's
company email domain. The `websiteSource` field says which.

## EB-3 immigration firms

`pipeline/build_firms.py` reads every PERM case (all industries) and groups them by the attorney/agent on the
filing. A case counts as **EB-3 worker-level** when its occupation is a non-degree SOC group (31, 33, 35, 37, 39,
41, 43, 45, 47, 49, 51, 53: care aides, food, cleaning, farm, construction, production, drivers…); those file
under EB-3 skilled/other workers, not EB-2. FY2024 new-form rows have no SOC code, so job-title keywords stand in.
Firms with ≥5 such cases are listed with case counts, share of their PERM work, approval rate, client
industries and states, largest clients, farm clients, and the attorneys on those filings.
"EB-3 specialist" = ≥20 EB-3 worker cases and ≥50% of the firm's PERM filings.

## Run

```bash
pip install -r requirements.txt
# 1. download disclosure files into data/raw/ (links: https://www.dol.gov/agencies/eta/foreign-labor/performance)
python pipeline/load_dol.py        # xlsx -> data/interim/*_ag.parquet (agriculture rows only)
python pipeline/build_dataset.py   # one row per employer, scored; picks the dashboard set -> data/interim/
GOOGLE_PLACES_API_KEY=... python pipeline/enrich_places.py   # cached; reruns never re-bill
python pipeline/export.py          # -> dashboard/farms.json + data/out/farms.csv
python pipeline/build_firms.py     # -> dashboard/firms.json + data/out/firms.csv (EB-3 law firms)
GOOGLE_PLACES_API_KEY=... python pipeline/enrich_places.py --input dashboard/firms.json \
  --ids-file data/interim/firms_enrich_ids.json --cache data/interim/firms_places_cache.jsonl
python pipeline/build_firms.py     # rerun to merge firm websites from Places
```

The dashboard (`dashboard/index.html` + `farms.json` + `firms.json`) is published as a claude.ai artifact. Ticks and
notes are stored in the artifact's shared database (`outreach/<employer id>`, `firm_outreach/<firm id>`).

## Costs

Google Places Text Search with website/phone fields bills at the Enterprise SKU (~$35 per 1,000 requests
after the monthly free allowance). Results are cached in `data/interim/places_cache.jsonl`.
