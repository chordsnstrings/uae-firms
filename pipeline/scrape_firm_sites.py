"""Visit each EB-3 firm's website (homepage + one About page) and pull public profile facts.

Extracts: site title/description, about text, languages spoken, whether the site mentions EB-3 / H-2A /
H-2B / PERM, worker source countries mentioned, social links, emails and phones published on the site, and
a founding year. Cached per firm in data/interim/firm_sites.jsonl (rerun only fetches missing firms).
"""
import json, os, re, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = os.path.join(os.path.dirname(__file__), "..")
CACHE = os.path.join(ROOT, "data", "interim", "firm_sites.jsonl")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
LANGS = ["Spanish", "Español", "Portuguese", "Mandarin", "Cantonese", "Chinese", "Korean", "Vietnamese", "Hindi", "Punjabi",
         "Gujarati", "Urdu", "Arabic", "Russian", "Ukrainian", "Tagalog", "Filipino", "French", "Haitian Creole", "Polish",
         "Turkish", "Japanese", "Thai", "Nepali", "Bengali", "Farsi", "Persian", "Amharic", "Telugu", "Tamil", "Indonesian", "German", "Italian"]
LANG_NORM = {"Español": "Spanish", "Filipino": "Tagalog", "Persian": "Farsi"}
COUNTRIES = ["Philippines", "Vietnam", "Mexico", "Guatemala", "Honduras", "El Salvador", "Nicaragua", "Colombia", "Peru", "Brazil",
             "Dominican Republic", "Jamaica", "Haiti", "India", "Nepal", "Sri Lanka", "Bangladesh", "Pakistan", "China", "Korea",
             "Thailand", "Indonesia", "Nigeria", "Ghana", "Kenya", "Ethiopia", "Egypt", "Ukraine", "Turkey", "Dubai", "UAE",
             "United Arab Emirates", "South Africa", "Zimbabwe", "Uganda", "Taiwan", "Japan", "Mongolia", "Uzbekistan", "Kazakhstan"]
SOCIAL = {"linkedin": r"linkedin\.com/(company|in|school)/[^\s\"'?#]+", "facebook": r"facebook\.com/[^\s\"'?#]+",
          "instagram": r"instagram\.com/[^\s\"'?#]+", "youtube": r"youtube\.com/(@|channel/|c/|user/)[^\s\"'?#]+",
          "x": r"(?:twitter|x)\.com/[A-Za-z0-9_]+", "tiktok": r"tiktok\.com/@[^\s\"'?#]+"}
JUNK_EMAIL = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp)$|example\.|sentry|wixpress|godaddy|domain\.com|yourdomain|email\.com", re.I)
lock = threading.Lock()


def get(url, budget=20):
    """Fetch up to ~1.5 MB of HTML with curl; --max-time is a hard wall clock (covers proxy tunnel hangs)."""
    try:
        p = subprocess.run(["curl", "-sL", "--compressed", "--max-time", str(budget), "--max-redirs", "5",
                            "-A", UA["User-Agent"], "-H", "Accept-Language: en-US,en;q=0.9",
                            "-w", "\n@@META@@%{url_effective} %{http_code} %{content_type}", url],
                           capture_output=True, timeout=budget + 5)
    except subprocess.TimeoutExpired:
        return url, None
    body, _, meta = p.stdout.rpartition(b"\n@@META@@")
    parts = meta.decode(errors="replace").split(" ", 2)
    if len(parts) < 2 or parts[1] != "200" or (len(parts) == 3 and parts[2] and "html" not in parts[2]):
        return (parts[0] if parts else url), None
    return parts[0], body[:1_500_000].decode("utf-8", errors="replace")


def text_of(soup):
    for t in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def about_snippet(soup):
    best = ""
    for p in soup.find_all(["p", "li"]):
        t = re.sub(r"\s+", " ", p.get_text(" ")).strip()
        if 120 <= len(t) <= 900 and not re.search(r"cookie|privacy|©|all rights reserved|disclaimer|attorney advertising", t, re.I):
            if re.search(r"\b(we|our|firm|founded|immigration|attorney|lawyer)\b", t, re.I):
                return t[:600]
            best = best or t[:600]
    return best


def analyse(firm):
    url = firm["website"]
    final, html = get(url)
    if not html:
        return {"id": firm["id"], "ok": False}
    soup = BeautifulSoup(html, "lxml")
    meta = lambda **kw: (soup.find("meta", attrs=kw) or {}).get("content", "") if soup.find("meta", attrs=kw) else ""
    title = re.sub(r"\s+", " ", soup.title.get_text()).strip()[:160] if soup.title else ""
    desc = (meta(name="description") or meta(property="og:description")).strip()[:400]
    links = [urljoin(final, a.get("href", "")) for a in soup.find_all("a", href=True)]
    host = urlparse(final).netloc
    about_url = next((l for l in links if urlparse(l).netloc == host and re.search(r"/(about|our-firm|firm|who-we-are|attorneys|our-team)", l, re.I)), "")
    raw = html
    pages_text = text_of(BeautifulSoup(html, "lxml"))
    about = ""
    if about_url:
        _, ah = get(about_url)
        if ah:
            raw += ah
            asoup = BeautifulSoup(ah, "lxml")
            about = about_snippet(asoup)
            pages_text += " " + text_of(asoup)
    about = about or about_snippet(soup)
    pages_text = re.sub(r"\S{200,}", " ", pages_text[:400_000])
    langs = []
    if re.search(r"speak|language|habla|idioma|fluent|bilingual", pages_text, re.I):
        langs = sorted({LANG_NORM.get(l, l) for l in LANGS if re.search(rf"\b{l}\b", pages_text)})
    countries = sorted({c for c in COUNTRIES if re.search(rf"\b{re.escape(c)}\b", pages_text)})
    # Drop inline data URIs / giant tokens first: regexes over megabytes of base64 go quadratic.
    raw = re.sub(r"data:[^\"'\s)]+|\S{400,}", " ", raw[:2_000_000])
    pages_text = pages_text[:400_000]
    social = {}
    for k, pat in SOCIAL.items():
        m = re.search(pat, raw, re.I)
        if m:
            social[k] = "https://" + m.group(0).rstrip("/\\")
    emails = sorted({e.lower() for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw) if not JUNK_EMAIL.search(e)})[:6]
    phones = sorted({re.sub(r"\D", "", t)[-10:] for t in re.findall(r'tel:([+\d\-\s().]{7,})', raw)})[:4]
    founded = re.search(r"\b(?:since|founded in|established in|est\.?)\s+((?:19[4-9]|20[0-2])\d)\b", pages_text, re.I)
    count = lambda pat: len(re.findall(pat, pages_text, re.I))
    return {"id": firm["id"], "ok": True, "url": final, "title": title, "description": desc, "about": about,
            "languages": langs, "countries": countries, "social": social, "emails": emails,
            "phones": [f"({p[:3]}) {p[3:6]}-{p[6:]}" for p in phones if len(p) == 10],
            "founded": founded.group(1) if founded else "",
            "mentions": {"eb3": count(r"\bEB-?3\b|unskilled worker|other workers?\b"), "h2a": count(r"\bH-?2A\b"),
                         "h2b": count(r"\bH-?2B\b"), "perm": count(r"\bPERM\b|labor certification")}}


def main():
    firms = [f for f in json.load(open(os.path.join(ROOT, "dashboard", "firms.json"))) if f.get("website")]
    done = {json.loads(l)["id"] for l in open(CACHE)} if os.path.exists(CACHE) else set()
    todo = [f for f in firms if f["id"] not in done]
    print(f"{len(done)} cached, {len(todo)} sites to visit")
    ok = 0
    ex = ThreadPoolExecutor(16)
    futs = {ex.submit(analyse, f): f for f in todo}
    with open(CACHE, "a") as fh:
        try:
            for fut in as_completed(futs, timeout=60 + 4 * len(todo)):
                f = futs.pop(fut)
                try:
                    res = fut.result()
                except Exception:  # a page that breaks the parser counts as unreadable
                    res = {"id": f["id"], "ok": False}
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                fh.flush()
                ok += res["ok"]
        except FutTimeout:
            for f in futs.values():  # still hanging: record as unreadable and move on
                fh.write(json.dumps({"id": f["id"], "ok": False, "timeout": True}) + "\n")
    print(f"read {ok} of {len(todo)} sites")
    os._exit(0)  # don't wait for threads stuck on dead connections


if __name__ == "__main__":
    main()
