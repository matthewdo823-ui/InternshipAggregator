"""
Greenhouse ATS scraper.

Greenhouse is used by 1000s of companies (Airbnb, Dropbox, Figma, etc.)
Their job board API is public and doesn't require auth:
  https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs

We maintain a list of company slugs. You can add more from:
  https://boards.greenhouse.io/{company_slug}
"""
import requests

from scrapers.base import BaseScraper, Job


ENGINEERING_COMPANIES = [
    # AI / ML / Data
    "anthropic", "andurilindustries", "databricks", "datadog", "labelbox",
    "relativity", "waymo", "motional", "nuro",
    # Aerospace / Defense
    "rocketlab", "spacex",
    # Automotive / Mobility / IoT
    "bird", "geotab", "lyft", "motive", "samsara", "via",
    # Cloud / Infrastructure / Security
    "cloudflare", "cockroachlabs", "commvault", "fastly", "mongodb",
    "newrelic", "okta", "pagerduty", "planetscale", "rubrik",
    "vercel", "zscaler",
    # Data / Analytics / DevTools
    "amplitude", "circleci", "elastic", "fivetran", "gitlab",
    "launchdarkly", "mixpanel", "starburst", "webflow",
    # Consumer / E-commerce / Gaming
    "airbnb", "airtable", "calendly", "discord", "dropbox",
    "duolingo", "instacart", "intercom", "pinterest", "reddit",
    "roblox", "scopely", "toast", "udemy", "coursera",
    # Fintech / Payments
    "adyen", "affirm", "block", "brex", "chime", "coinbase",
    "gemini", "marqeta", "mercury", "robinhood", "sofi", "stripe",
    # HR / Workplace SaaS
    "asana", "faire", "gusto", "justworks", "lattice", "salesloft",
    # Logistics / Supply Chain
    "flexport", "fourkites", "project44",
    # Design / Productivity
    "figma",
    # Trading / Quant
    "imc", "optiver", "point72",
    # Other
    "hubspot", "masterclass", "momentus", "netlify", "remote",
    "spire", "twilio",
]

PM_COMPANIES = [
    "airbnb", "airtable", "asana", "calendly", "discord", "duolingo",
    "figma", "instacart", "intercom", "lattice", "lyft", "pinterest",
    "reddit", "robinhood", "stripe", "toast", "udemy", "coursera",
    "affirm", "amplitude", "brex", "chime", "dropbox", "faire",
    "gusto", "justworks", "mercury", "mixpanel", "sofi", "webflow",
]

FINANCE_COMPANIES = [
    "adyen", "affirm", "block", "brex", "chime", "coinbase", "gemini",
    "imc", "marqeta", "mercury", "optiver", "point72", "robinhood",
    "sofi", "stripe", "flexport", "gusto", "lattice",
]

_EXTRA_BUSINESS_GREENHOUSE = [
    # Fintech / Banking / Insurance
    "scale", "abridge", "falconx", "lithic", "column", "moderntreasury",
    "increase", "ocrolus", "blend", "better", "current", "dave", "albert",
    "brigit", "empower", "moneylion", "varo", "greenlight", "nova", "unit",
    "bluevine", "lili", "synapse", "treasuryprime", "lead", "fundbox",
    # Health / Benefits / HR
    "oscar", "collectivehealth", "cloverhealth", "flatironhealth", "tempus",
    "color", "guardanthealth", "natera", "grail", "heartflow", "veracyte",
    "goodrx", "hims", "ro", "agiletherapeutics", "cerebral", "headway",
    "springhealth", "lyrahealth", "modernhealth", "ginger", "calm",
    # Sales / Marketing / RevOps
    "braze", "iterable", "customerio", "attentive", "postscript", "yotpo",
    "recharge", "boldcommerce", "bigcommerce", "optimizely", "unbounce",
    "crazyegg", "hotjar", "fullstory", "logrocket", "sproutsocial",
    "hootsuite", "buffer", "later", "canva",
    # Real estate / Travel / Marketplaces
    "cargurus", "carvana", "carmax", "vroom", "shift", "expedia", "tripadvisor",
    "booking", "kayak", "hopper", "kiwi", "getyourguide", "vacasa",
    # Security / Compliance (business roles)
    "vanta", "drata", "secureframe", "zip", "lacework", "snyk", "wiz",
    "orca-security", "axonius", "cybereason", "coalfire", "onetrust",
    # Enterprise SaaS
    "box", "dropbox", "evernote", "coda", "retool", "airbyte", "dbt",
    "preset", "lightdash", "mode", "looker", "sisense", "thoughtspot",
    "domo", "alation", "collibra", "atlan", "montecarlo", "bigeye",
    # Logistics / Supply chain
    "convoy", "uberfreight", "loadsmart", "freightwaves", "project44",
    "shipbob", "deliverr", "stord", "logiwa", "fishbowl",
    # Consulting / Services / Staffing
    "mckinsey", "bcg", "bain", "deloitte", "accenture", "kpmg", "ey", "pwc",
    "roberthalf", "randstad", "adecco", "manpower", "kellyservices",
    # Consumer / Retail / CPG
    "warbyparker", "allbirds", "glossier", "away", "casper", "purple",
    "bombas", "quip", "ritual", "hims", "athleticgreens", "liquiddeath",
    "impossiblefoods", "beyondmeat", "sweetgreen", "chipotle",
    # Media / Entertainment
    "vimeo", "buzzfeed", "vox", "spotify", "soundcloud", "wattpad",
    "medium", "substack", "patreon", "onlyfans",
    # Analytics / Data (business-facing)
    "cresta", "zone5technologies", "gelbergroup", "alteryx", "sisense",
    "thoughtspot", "domo", "amplitude", "heap", "mixpanel", "pendo",
    "smartlyio", "billiontoone", "iherb", "strivr", "connectprep", "ispottv",
    # Trading / Finance
    "akuna", "hrt", "jumptrading", "sig", "virtu", "citsec", "tudor",
    "millennium", "twosigma", "deshaw", "citadel", "bridgewater",
    # Aerospace / Defense / Industrial (business ops)
    "appliedintuition", "aurora", "cruise", "nuro", "motional", "waymo",
    "andurilindustries", "relativity", "rocketlab", "spacex", "momentus",
    # Misc tech with business teams
    "palantir", "databricks", "snowflake", "confluent", "hashicorp",
    "gitlab", "github", "atlassian", "zoom", "slack", "asana", "notion",
    "linear", "figma", "canva", "miro", "loom", "airtable", "calendly",
    "gong", "6sense", "qualified", "drift", "salesloft", "hubspot",
    "zendesk", "freshworks", "intercom", "front", "kustomer", "gladly",
    "servicetitan", "procore", "buildertrend", "jobber", "housecallpro",
    "opendoor", "compass", "zillow", "redfin", "opendoor", "offerpad",
    "sofi", "chime", "affirm", "klarna", "afterpay", "sezzle",
]

BUSINESS_COMPANIES = sorted(set(
    ENGINEERING_COMPANIES + PM_COMPANIES + FINANCE_COMPANIES + _EXTRA_BUSINESS_GREENHOUSE
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


class GreenhouseScraper(BaseScraper):

    source_name = "greenhouse"
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

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
        url = f"{self.API_BASE}/{slug}/jobs?content=true"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                self.log(f"  Slug '{slug}' not found — skipping")
                return []
            resp.raise_for_status()
            return resp.json().get("jobs", [])
        except Exception as e:
            self.log(f"  Error fetching {slug}: {e}")
            return []

    def _extract_date(self, rj: dict) -> str:
        for field in ("first_published", "updated_at", "created_at"):
            value = rj.get(field)
            if value and isinstance(value, str) and len(value) >= 10:
                return value[:10]
        return ""

    def _extract_location(self, rj: dict) -> str:
        offices = rj.get("offices", [])
        if not offices:
            return ""
        names = [o.get("name", "") for o in offices if o.get("name")]
        return "; ".join(names)

    def _extract_department(self, rj: dict) -> str:
        departments = rj.get("departments", [])
        if not departments:
            return ""
        names = [d.get("name", "") for d in departments if d.get("name")]
        return "; ".join(names)

    def _extract_company(self, rj: dict, slug: str, apply_url: str) -> str:
        company = rj.get("company", {})
        if isinstance(company, dict) and company.get("name"):
            return company["name"]
        if apply_url and "greenhouse.io/" in apply_url:
            try:
                slug_from_url = apply_url.split("greenhouse.io/")[1].split("/")[0]
                return slug_from_url.replace("-", " ").title()
            except Exception:
                pass
        return slug.replace("-", " ").title()

    def _filter_jobs(self, raw_jobs: list[dict], slug: str) -> list[Job]:
        matched = []
        for rj in raw_jobs:
            title = rj.get("title", "")
            description = rj.get("content", "") or ""
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

            apply_url = rj.get("absolute_url", "")
            company = self._extract_company(rj, slug, apply_url)

            matched.append(Job(
                title=title,
                company=company,
                location=location,
                department=department,
                type=job_type,
                date_posted=date_posted,
                apply_url=apply_url,
                source="greenhouse",
                niche=self.niche,
            ))

        return matched
