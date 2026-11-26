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

## Run

```bash
pip install -r requirements.txt
# 1. download disclosure files into data/raw/ (links: https://www.dol.gov/agencies/eta/foreign-labor/performance)
python pipeline/load_dol.py        # xlsx -> data/interim/*_ag.parquet (agriculture rows only)
python pipeline/build_dataset.py   # one row per employer, scored; picks the dashboard set -> data/interim/
GOOGLE_PLACES_API_KEY=... python pipeline/enrich_places.py   # cached; reruns never re-bill
python pipeline/export.py          # -> dashboard/farms.json + data/out/farms.csv
```

The dashboard (`dashboard/index.html` + `farms.json`) is published as a claude.ai artifact. Ticks and
notes are stored in the artifact's shared database (`outreach/<employer id>`).

## Costs

Google Places Text Search with website/phone fields bills at the Enterprise SKU (~$35 per 1,000 requests
after the monthly free allowance). Results are cached in `data/interim/places_cache.jsonl`.
