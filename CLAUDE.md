# usa farm EB-3 prospects (repo: uae-firms)

Decisions (don't re-derive):
- Purpose: list US farms that may recruit EB-3 workers; dashboard with website, email, phone (HR/owner
  preferred), short profile, shared "contacted" tick + notes.
- Evidence tiers: A = DOL PERM filers in ag NAICS (111/112/1151/1152), FY2024-new-form, FY2025, FY2026.
  B = direct H-2A employers FY2025–26, non-labour-contractor, ≥50 workers or ≥10 in year-round sector.
- Contacts = employer POC on DOL filings; drop emails from domains used by ≥5 unrelated employers (agents).
- Places API (New) Text Search, Enterprise fields only (no Atmosphere), lookups only for tier A + tier B
  without a website. Cached in data/interim/places_cache.jsonl; matcher in enrich_places.score/pick.
- Repo is PUBLIC: never commit data/, dashboard/farms.json or any API key. Key comes from env
  GOOGLE_PLACES_API_KEY only.
- Dashboard = claude.ai artifact (plain page + `db` + `user` capabilities); ticks in collection `outreach`.

Verify: run the touched pipeline step only; `python pipeline/export.py` prints coverage counts.
