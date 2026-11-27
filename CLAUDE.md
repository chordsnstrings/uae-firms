# usa farm EB-3 prospects (repo: uae-firms)

Decisions (don't re-derive):
- Purpose: list US farms that may recruit EB-3 workers; dashboard with website, email, phone (HR/owner
  preferred), short profile, shared "contacted" tick + notes.
- Evidence tiers: A = DOL PERM filers in ag NAICS (111/112/1151/1152), FY2024-new-form, FY2025, FY2026.
  B = direct H-2A employers FY2025–26, non-labour-contractor, ≥50 workers or ≥10 in year-round sector.
- Contacts = employer POC on DOL filings; drop emails from domains used by ≥5 unrelated employers (agents).
- Places API (New) Text Search, Enterprise fields only (no Atmosphere), lookups only for tier A + tier B
  without a website. Cached in data/interim/places_cache.jsonl; matcher in enrich_places.score/pick.
- Repo is PUBLIC: never commit data/, dashboard/*.json or any API key. Key comes from env
  GOOGLE_PLACES_API_KEY only.
- EB-3 firms tab: build_firms.py groups ALL-industry PERM cases by attorney/law firm; EB-3 worker-level =
  non-degree SOC groups 31/33/35/37/39/41/43/45/47/49/51/53 (title keywords for FY2024 rows without SOC);
  list firms with >=5 such cases; specialist = >=20 cases and >=50% share. Places only for firms with no
  email-domain website (cache data/interim/firms_places_cache.jsonl).
- Dashboard = private claude.ai artifact (plain page + `db` + `user`); tabs #farms / #firms; ticks in
  collections `outreach` and `firm_outreach`. All dashboard/*.json files hold contacts: gitignored.

Verify: run the touched pipeline step only; `python pipeline/export.py` prints coverage counts.
