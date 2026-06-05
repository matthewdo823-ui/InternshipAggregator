"""
Ashby ATS scraper.

Ashby is used by many startups (Notion, Linear, OpenAI, etc.)
Public job board API (no auth):
  https://api.ashbyhq.com/posting-api/job-board/{slug}

Find a company's slug at https://jobs.ashbyhq.com/{slug}
"""
import requests

from scrapers.base import BaseScraper, Job


ENGINEERING_COMPANIES = [
    # AI / ML
    "openai", "cohere", "elevenlabs", "harvey", "perplexity", "sierra",
    "cursor", "replit", "langchain", "runway",
    # Cloud / Infrastructure
    "snowflake", "confluent", "supabase", "docker", "modal", "render",
    "runpod", "workos", "neon", "railway", "stytch", "prefect", "airbyte",
    # Defense / Aerospace / Hardware
    "crusoe", "saronic", "skydio", "aerovect", "logos-space",
    "iambic-therapeutics", "harmattan-ai",
    # Fintech / Payments
    "airwallex", "deel", "hopper", "nerdwallet", "plaid", "ramp",
    "sydecar", "wayflyer", "zayzoon",
    # Productivity / SaaS
    "notion", "linear", "clickup", "merge", "posthog", "zapier",
    "honeybook", "kiddom", "benevity", "tremendous", "expensify", "clerky",
    # Biotech / Health
    "benchling", "insitro", "relay", "sardine", "semperis",
    # Security / Other
    "opensea", "oyster", "sifflet",
]

PM_COMPANIES = [
    "notion", "linear", "openai", "ramp", "perplexity", "supabase",
    "cursor", "merge", "deel", "harvey", "sierra", "cohere", "plaid",
    "hopper", "clickup", "posthog", "replit", "nerdwallet", "honeybook",
    "wayflyer", "kiddom", "tremendous", "benevity",
]

FINANCE_COMPANIES = [
    "ramp", "deel", "openai", "airwallex", "plaid", "sydecar",
    "nerdwallet", "opensea", "zayzoon", "benevity", "hopper", "wayflyer",
]

_EXTRA_BUSINESS_ASHBY = [
    # Fintech / HR / Ops
    "column", "unit", "increase", "moderntreasury", "lithic", "falconx",
    "sydecar", "angellist", "pulley", "carta", "rippling", "deel", "oyster",
    "gusto", "justworks", "lattice", "remote", "oyster", "multiplier",
    # AI / SaaS
    "anthropic", "mistral", "together", "fireworks", "anyscale", "weights-biases",
    "langchain", "arize", "helicone", "braintrust", "humanloop", "promptlayer",
    # Productivity / Collaboration
    "figma", "miro", "loom", "around", "tandem", "tuple", "pop", "mult",
    "arc", "browsercompany", "raycast", "warp", "fig", "vercel", "netlify",
    # Sales / Marketing / Data
    "gong", "6sense", "qualified", "drift", "clay", "apollo", "commonroom",
    "pocus", "warmly", "default", "relevance", "unify", "twelve", "mutiny",
    # Security / Compliance
    "vanta", "drata", "secureframe", "zip", "kandji", "jumpcloud", "tailscale",
    "1password", "bitwarden", "dashlane", "keeper", "nordsecurity",
    # Healthcare / Benefits
    "headway", "springhealth", "lyrahealth", "modernhealth", "cerebral",
    "alma", "growtherapy", "sondermind", "talkiatry", "done",
    # Logistics / Marketplaces
    "flexport", "project44", "fourkites", "shipbob", "stord", "deliverr",
    "faire", "tundra", "bulletin", "joor", "nuorder", "brandboom",
    # Other high-growth
    "ramp", "brex", "mercury", "arc", "pilot", "bench", "inDinero",
    "puzzle", "digits", "finaloop", "zeni", "kick", "layer",
    "opensea", "blur", "magic-eden", "tensor", "hyperspace",
    "dune", "nansen", "arkham", "chainalysis", "elliptic", "trmlabs",
    "meshy", "base-power", "saronic", "skydio", "anduril", "shield-ai",
    "vannevar", "palantir", "scale", "labelbox", "snorkel", "surge",
]

BUSINESS_COMPANIES = sorted(set(
    ENGINEERING_COMPANIES + PM_COMPANIES + FINANCE_COMPANIES + _EXTRA_BUSINESS_ASHBY
))

NICHE_COMPANIES = {
    "engineering": ENGINEERING_COMPANIES,
    "product_management": PM_COMPANIES,
    "finance": FINANCE_COMPANIES,
    "business": BUSINESS_COMPANIES,
    "general": sorted(set(
        ENGINEERING_COMPANIES + PM_COMPANIES + FINANCE_COMPANIES + BUSINESS_COMPANIES
    )),
}


class AshbyScraper(BaseScraper):

    source_name = "ashby"
    API_BASE = "https://api.ashbyhq.com/posting-api/job-board"

    def scrape(self) -> list[Job]:
        companies = NICHE_COMPANIES.get(self.niche, ENGINEERING_COMPANIES)
        all_jobs = []

        for slug in companies:
            if not self.should_include_company(slug):
                continue
            self.log(f"Fetching: {slug}")
            jobs = self._fetch_company(slug)
            matched = self._filter_jobs(jobs, slug)
            self.log(f"  → {len(jobs)} total, {len(matched)} matched")
            all_jobs.extend(matched)
            self.sleep()

        return all_jobs

    def _fetch_company(self, slug: str) -> list[dict]:
        url = f"{self.API_BASE}/{slug}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 404:
                self.log(f"  Slug '{slug}' not found — skipping")
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("jobs", []) if isinstance(data, dict) else []
        except Exception as e:
            self.log(f"  Error fetching {slug}: {e}")
            return []

    def _extract_date(self, rj: dict) -> str:
        published = rj.get("publishedAt", "")
        if published and isinstance(published, str) and len(published) >= 10:
            return published[:10]
        return ""

    def _extract_location(self, rj: dict) -> str:
        parts = []
        primary = rj.get("location", "")
        if primary:
            parts.append(primary)

        for loc in rj.get("secondaryLocations") or []:
            if isinstance(loc, dict):
                name = loc.get("location") or loc.get("name", "")
            else:
                name = str(loc)
            if name:
                parts.append(name)

        address = rj.get("address") or {}
        if isinstance(address, dict):
            postal = address.get("postalAddress") or {}
            country = postal.get("addressCountry", "")
            region = postal.get("addressRegion", "")
            if country and country not in " ".join(parts):
                parts.append(country)
            elif region and region not in " ".join(parts):
                parts.append(region)

        if rj.get("isRemote"):
            parts.append("Remote")

        return "; ".join(parts)

    def _extract_department(self, rj: dict) -> str:
        parts = []
        for key in ("department", "team", "workplaceType", "employmentType"):
            value = rj.get(key)
            if value:
                parts.append(str(value))
        return "; ".join(parts)

    def _filter_jobs(self, raw_jobs: list[dict], slug: str) -> list[Job]:
        matched = []
        company = slug.replace("-", " ").title()

        for rj in raw_jobs:
            if rj.get("isListed") is False:
                continue

            title = rj.get("title", "")
            description = rj.get("descriptionPlain", "") or rj.get("descriptionHtml", "") or ""
            department = self._extract_department(rj)

            if not title or not self.matches_keywords(title, department, description):
                continue

            location = self._extract_location(rj)
            if not self.is_us_location(location):
                continue

            date_posted = self._extract_date(rj)
            job_type = self.infer_job_type(title, description)

            if not self.passes_filters(title, job_type, date_posted, description):
                continue

            apply_url = rj.get("applyUrl", "") or rj.get("jobUrl", "")
            if not apply_url:
                continue

            matched.append(Job(
                title=title.strip(),
                company=company,
                location=location,
                department=department,
                type=job_type,
                date_posted=date_posted,
                apply_url=apply_url,
                source="ashby",
                niche=self.niche,
            ))

        return matched
