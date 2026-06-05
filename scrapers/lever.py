"""
Lever ATS scraper.

Lever is used by companies like Netflix, GitHub, Shopify, etc.
Their public API:
  https://api.lever.co/v0/postings/{company_slug}?mode=json
"""
import requests
from datetime import datetime

from scrapers.base import BaseScraper, Job


LEVER_COMPANIES = {
    "engineering": [
        "gopuff", "palantir", "veeva", "zoox", "spotify",
        "hermeus", "mistral", "appen", "neon",
        "netflix", "atlassian", "anchorage", "outreach",
        "labelbox", "kraken", "plaid", "kpmg",
    ],
    "product_management": [
        "gopuff", "palantir", "spotify", "netflix", "atlassian",
        "outreach", "veeva", "zoox",
    ],
    "finance": [
        "anchorage", "palantir", "veeva", "kraken", "plaid",
        "kpmg", "spotify",
    ],
    "business": sorted(set([
        # Core lever boards
        "kpmg", "palantir", "veeva", "gopuff", "spotify", "netflix",
        "atlassian", "outreach", "anchorage", "plaid", "kraken", "zoox",
        "hermeus", "mistral", "appen", "neon", "voltus", "altaml", "lendbuzz",
        "field-ai", "fluxergy", "plus-2", "genbio", "liveperson", "segment",
        "coupa", "databricks", "hashicorp", "figma", "rippling", "carta",
        "checkr", "gusto", "lattice", "brex", "mercury", "ramp", "deel",
        # Expanded lever boards
        "github", "twitch", "box", "optimizely", "lacework", "snyk", "wiz",
        "orca-security", "axonius", "cybereason", "vanta", "drata",
        "secureframe", "zip", "coalition", "snyk", "labelbox", "scale",
        "abridge", "falconx", "unit", "column", "moderntreasury", "increase",
        "blend", "better", "current", "dave", "albert", "brigit", "varo",
        "greenlight", "moneylion", "empower", "oscar", "collectivehealth",
        "flatironhealth", "tempus", "color", "natera", "grail", "goodrx",
        "hims", "ro", "cerebral", "headway", "springhealth", "lyrahealth",
        "braze", "iterable", "customerio", "attentive", "yotpo", "bigcommerce",
        "retool", "coda", "dbt", "preset", "mode", "sisense", "thoughtspot",
        "convoy", "loadsmart", "shipbob", "stord", "appliedintuition", "aurora",
        "cruise", "nuro", "motional", "relativity", "rocketlab", "akuna",
        "hrt", "jumptrading", "sig", "virtu", "citsec", "tudor", "millennium",
        "servicetitan", "procore", "jobber", "housecallpro", "offerpad",
        "opendoor", "compass", "carvana", "cargurus", "vroom", "shift",
        "expedia", "tripadvisor", "hopper", "getaround", "turo", "bird",
        "lime", "spin", "tier", "bolt", "grab", "gojek", "careem",
        "instacart", "doordash", "uber", "lyft", "postmates", "grubhub",
        "deliveroo", "justeat", "wolt", "rappi", "ifood", "swiggy",
        "shopify", "bigcommerce", "woocommerce", "magento", "squarespace",
        "wix", "webflow", "framer", "bubble", "airtable", "notion", "coda",
        "slack", "asana", "monday", "clickup", "basecamp", "teamwork",
        "smartsheet", "wrike", "jira", "confluence", "miro", "mural",
        "loom", "vidyard", "wistia", "vimeo", "brightcove", "kaltura",
        "hubspot", "marketo", "pardot", "eloqua", "salesforce", "pipedrive",
        "close", "copper", "nutshell", "insightly", "capsule", "streak",
        "gong", "chorus", "clari", "aviso", "peopleai", "revenuegrid",
        "6sense", "demandbase", "zoominfo", "clearbit", "apollo", "lusha",
        "seamless", "rocketreach", "hunter", "snov", "lemlist", "instantly",
        "smartlead", "mailshake", "woodpecker", "reply", "outplay", "amplemarket",
    ])),
    "general": [
        "gopuff", "palantir", "veeva", "zoox", "spotify",
        "hermeus", "mistral", "appen", "neon",
        "netflix", "atlassian", "anchorage", "outreach",
        "labelbox", "kraken", "plaid", "kpmg",
    ],
}


class LeverScraper(BaseScraper):

    source_name = "lever"
    API_BASE = "https://api.lever.co/v0/postings"

    def scrape(self) -> list[Job]:
        companies = LEVER_COMPANIES.get(self.niche, LEVER_COMPANIES["general"])
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
        url = f"{self.API_BASE}/{slug}?mode=json"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                self.log(f"  Slug '{slug}' not found — skipping")
                return []
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.log(f"  Error fetching {slug}: {e}")
            return []

    def _extract_date(self, rj: dict) -> str:
        created_at = rj.get("createdAt") or rj.get("updatedAt")
        if created_at:
            try:
                return datetime.fromtimestamp(created_at / 1000).strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass
        return ""

    def _extract_department(self, categories: dict) -> str:
        parts = []
        for key in ("team", "department", "commitment"):
            value = categories.get(key)
            if value:
                parts.append(str(value))
        return "; ".join(parts)

    def _filter_jobs(self, raw_jobs: list[dict], slug: str) -> list[Job]:
        matched = []
        for rj in raw_jobs:
            title = rj.get("text", "")
            categories = rj.get("categories", {}) or {}
            department = self._extract_department(categories)
            description = rj.get("description", "") or rj.get("descriptionPlain", "") or ""
            if not title or not self.matches_keywords(title, department, description):
                continue

            location = categories.get("location", "")
            if not self.is_us_location(location):
                continue

            date_posted = self._extract_date(rj)
            job_type = self.infer_job_type(title, description)

            if not self.passes_filters(title, job_type, date_posted, description):
                continue

            apply_url = rj.get("hostedUrl", "") or rj.get("applyUrl", "")
            company = categories.get("company") or slug.replace("-", " ").title()

            matched.append(Job(
                title=title,
                company=company,
                location=location,
                department=department,
                type=job_type,
                date_posted=date_posted,
                apply_url=apply_url,
                source="lever",
                niche=self.niche,
            ))

        return matched
