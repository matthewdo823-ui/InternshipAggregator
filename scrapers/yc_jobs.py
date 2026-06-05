"""
Y Combinator Work at a Startup scraper.

https://www.workatastartup.com

Job listings are embedded in Inertia.js `data-page` JSON on role category pages.
We fetch each niche-relevant /jobs/l/{role} page and parse the SSR job list.
(~30 jobs per page, ~200+ unique across all role categories)
"""
import html
import json
import re
import requests
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Job


YC_BASE = "https://www.workatastartup.com"

# All role category paths from the /jobs page
ALL_ROLE_PATHS = [
    "/jobs/l/software-engineer",
    "/jobs/l/designer",
    "/jobs/l/recruiting",
    "/jobs/l/science",
    "/jobs/l/product-manager",
    "/jobs/l/operations",
    "/jobs/l/sales-manager",
    "/jobs/l/marketing",
    "/jobs/l/legal",
    "/jobs/l/finance",
]

YC_ROLE_PATHS = {
    "engineering": [
        "/jobs/l/software-engineer",
        "/jobs/l/science",
    ],
    "product_management": [
        "/jobs/l/product-manager",
    ],
    "finance": [
        "/jobs/l/finance",
    ],
    "business": ALL_ROLE_PATHS,
    "general": ALL_ROLE_PATHS,
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class YCJobsScraper(BaseScraper):

    source_name = "yc_jobs"

    def scrape(self) -> list[Job]:
        role_paths = YC_ROLE_PATHS.get(self.niche, ALL_ROLE_PATHS)
        self.log(f"Fetching {len(role_paths)} role categories from workatastartup.com")

        raw_jobs = []
        seen_ids = set()

        for path in role_paths:
            self.log(f"  Category: {path}")
            for posting in self._fetch_role_page(path):
                job_id = posting.get("id")
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                raw_jobs.append(posting)
            self.sleep()

        jobs = []
        for posting in raw_jobs:
            job = self._to_job(posting)
            if job:
                jobs.append(job)

        self.log(f"  → {len(raw_jobs)} fetched, {len(jobs)} matched after filters")
        return jobs

    def _fetch_role_page(self, path: str) -> list[dict]:
        url = f"{YC_BASE}{path}"
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            self.log(f"    Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        node = soup.find(attrs={"data-page": True})
        if not node:
            self.log("    No data-page payload found")
            return []

        try:
            page = json.loads(html.unescape(node["data-page"]))
            return page.get("props", {}).get("jobs", [])
        except json.JSONDecodeError as e:
            self.log(f"    JSON parse error: {e}")
            return []

    @staticmethod
    def _parse_active_date(text: str) -> str:
        if not text:
            return ""
        text = text.lower().strip()
        today = datetime.now().date()
        try:
            if "today" in text or "just" in text:
                return today.strftime("%Y-%m-%d")
            if "yesterday" in text:
                return (today - timedelta(days=1)).strftime("%Y-%m-%d")
            if "day" in text:
                days = int(re.search(r"(\d+)", text).group(1))
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            if "week" in text:
                weeks = int(re.search(r"(\d+)", text).group(1))
                return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
            if "month" in text:
                months = int(re.search(r"(\d+)", text).group(1))
                return (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        return ""

    @staticmethod
    def _normalize_job_type(job_type: str, title: str) -> str:
        combined = f"{job_type} {title}".lower()
        if "intern" in combined or "co-op" in combined or "coop" in combined:
            return "internship"
        if "contract" in combined:
            return "co-op"
        return "full-time"

    def _to_job(self, posting: dict) -> Job | None:
        title = posting.get("title", "")
        if not title:
            return None

        company = posting.get("companyName", "Unknown")
        location = posting.get("location", "")
        role_type = posting.get("roleType", "")
        salary = posting.get("salary", "")
        department = "; ".join(p for p in [role_type, salary] if p)

        description = posting.get("companyOneLiner", "")
        job_type = self._normalize_job_type(posting.get("jobType", ""), title)

        if not self.matches_keywords(title, department, description):
            return None
        if not self.is_us_location(location):
            return None

        date_posted = self._parse_active_date(posting.get("companyLastActiveAt", ""))

        if not self.passes_filters(title, job_type, date_posted, description):
            return None

        job_id = posting.get("id")
        apply_url = posting.get("applyUrl") or f"{YC_BASE}/jobs/{job_id}"
        if not apply_url:
            return None

        return Job(
            title=title.strip(),
            company=company,
            location=location,
            department=department,
            type=job_type,
            date_posted=date_posted,
            apply_url=apply_url,
            source=self.source_name,
            niche=self.niche,
        )
