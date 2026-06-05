"""
Wellfound (formerly AngelList Talent) scraper.

https://wellfound.com

Wellfound uses DataDome bot protection. Plain HTTP requests are blocked.
This scraper uses Playwright (real Chromium) to load pages and parse the
embedded Next.js __NEXT_DATA__ / Apollo cache.

Setup:
  pip install playwright
  python -m playwright install chromium

Config (config.yaml → sources.wellfound):
  use_playwright: true   # required for Wellfound
  headless: false        # false is more reliable; DataDome often blocks headless
  headed_fallback: true  # retry with a visible browser if headless is blocked
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from scrapers.base import BaseScraper, Job


WELLFOUND_BASE = "https://wellfound.com"

WELLFOUND_SEARCHES = {
    "engineering": [
        ("software-engineer", "united-states"),
        ("backend-engineer", "united-states"),
        ("frontend-engineer", "united-states"),
        ("data-engineer", "united-states"),
        ("machine-learning-engineer", "united-states"),
    ],
    "product_management": [
        ("product-manager", "united-states"),
    ],
    "finance": [
        ("finance", "united-states"),
    ],
    "business": [
        ("business-analyst", "united-states"),
        ("operations", "united-states"),
        ("marketing", "united-states"),
        ("sales", "united-states"),
        ("consulting", "united-states"),
        ("accounting", "united-states"),
        ("human-resources", "united-states"),
        ("strategy", "united-states"),
        ("supply-chain", "united-states"),
        ("customer-success", "united-states"),
        ("project-management", "united-states"),
        ("data-analyst", "united-states"),
        ("product-manager", "united-states"),
        ("finance", "united-states"),
        ("business-development", "united-states"),
        ("revenue-operations", "united-states"),
        ("growth", "united-states"),
        ("partnerships", "united-states"),
        ("recruiting", "united-states"),
        ("legal", "united-states"),
    ],
    "general": [
        ("software-engineer", "united-states"),
        ("product-manager", "united-states"),
        ("data-engineer", "united-states"),
        ("finance", "united-states"),
    ],
}

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WellfoundScraper(BaseScraper):

    source_name = "wellfound"

    def scrape(self) -> list[Job]:
        source_cfg = self.config.get("sources", {}).get("wellfound", {})
        searches = WELLFOUND_SEARCHES.get(self.niche, WELLFOUND_SEARCHES["general"])
        max_pages = (
            self.niche_config.get("wellfound_max_pages")
            or source_cfg.get("max_pages", 3)
        )
        use_playwright = source_cfg.get("use_playwright", True)

        if not use_playwright:
            return self._scrape_http(searches, max_pages)

        headless = source_cfg.get("headless", False)
        headed_fallback = source_cfg.get("headed_fallback", True)
        timeout_ms = source_cfg.get("page_timeout_ms", 45000)
        wait_ms = source_cfg.get("page_wait_ms", 12000)

        self.log(
            f"Fetching {len(searches)} Wellfound pages via Playwright "
            f"(headless={headless})"
        )

        html_pages, blocked = self._fetch_pages_playwright(
            searches,
            max_pages,
            headless=headless,
            headed_fallback=headed_fallback,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
        )

        if blocked and not html_pages:
            self.log(
                "  Wellfound blocked browser access (DataDome). "
                "Try headless: false in config, or run: "
                "python -m playwright install chromium"
            )
            return []

        all_postings = []
        seen_ids = set()
        for html in html_pages:
            for posting in self._parse_next_data(html):
                job_id = posting.get("id")
                if job_id and job_id not in seen_ids:
                    seen_ids.add(job_id)
                    all_postings.append(posting)

        jobs = []
        for posting in all_postings:
            job = self._to_job(posting)
            if job:
                jobs.append(job)

        self.log(f"  → {len(all_postings)} fetched, {len(jobs)} matched after filters")
        return jobs

    def _fetch_pages_playwright(
        self,
        searches: list[tuple[str, str]],
        max_pages: int,
        *,
        headless: bool,
        headed_fallback: bool,
        timeout_ms: int,
        wait_ms: int,
    ) -> tuple[list[str], bool]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.log(
                "  Playwright not installed. Run: pip install playwright && "
                "python -m playwright install chromium"
            )
            return [], True

        modes: list[bool] = []
        if headless:
            modes.append(True)
            if headed_fallback:
                modes.append(False)
        else:
            modes.append(False)

        html_pages = []
        blocked = False

        for idx, use_headless in enumerate(modes):
            if idx > 0:
                self.log("  Retrying with headed (visible browser)…")

            pages, was_blocked = self._run_browser_session(
                searches,
                max_pages,
                sync_playwright,
                headless=use_headless,
                timeout_ms=timeout_ms,
                wait_ms=wait_ms,
            )
            if pages:
                return pages, False
            blocked = was_blocked

        return html_pages, blocked

    def _run_browser_session(
        self,
        searches: list[tuple[str, str]],
        max_pages: int,
        sync_playwright,
        *,
        headless: bool,
        timeout_ms: int,
        wait_ms: int,
    ) -> tuple[list[str], bool]:
        html_pages = []
        blocked = False

        source_cfg = self.config.get("sources", {}).get("wellfound", {})
        storage_state = source_cfg.get("storage_state")
        warmup_homepage = source_cfg.get("warmup_homepage", False)

        with sync_playwright() as playwright:
            launch_kwargs = {
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            try:
                browser = playwright.chromium.launch(**launch_kwargs)
            except Exception as e:
                self.log(f"  Browser launch failed: {e}")
                return [], True

            context_kwargs = {
                "viewport": {"width": 1440, "height": 900},
                "user_agent": BROWSER_HEADERS["User-Agent"],
                "locale": "en-US",
            }
            if storage_state:
                if Path(storage_state).exists():
                    context_kwargs["storage_state"] = storage_state
                    self.log(f"  Using saved session: {storage_state}")

            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.add_init_script(STEALTH_INIT_SCRIPT)

            if warmup_homepage:
                try:
                    page.goto(
                        WELLFOUND_BASE,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    page.wait_for_timeout(4000)
                except Exception as e:
                    self.log(f"  Homepage load failed: {e}")

            for role, location in searches:
                base_url = self._build_search_url(role, location)
                self.log(f"  {base_url}")

                for page_num in range(1, max_pages + 1):
                    url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
                    try:
                        response = page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                        page.wait_for_timeout(wait_ms)
                        html = page.content()
                    except Exception as e:
                        self.log(f"    Page load failed: {e}")
                        break

                    if self._is_blocked_page(html, response):
                        blocked = True
                        self.log(
                            f"    Blocked on {url} "
                            f"(size={len(html)}, status={response.status if response else 'n/a'})"
                        )
                        break

                    if "__NEXT_DATA__" not in html:
                        self.log(f"    No job data in page (page {page_num})")
                        break

                    html_pages.append(html)
                    parsed_count = len(self._parse_next_data(html))
                    self.log(f"    Loaded {parsed_count} listings (page {page_num})")
                    if page_num == 1 and parsed_count == 0:
                        break

                # Extra pause between searches to reduce DataDome rate limits
                self.sleep()
                page.wait_for_timeout(2000)

            browser.close()

        return html_pages, blocked

    @staticmethod
    def _is_blocked_page(html: str, response) -> bool:
        # Wellfound may return 403 while still serving SSR job data — trust page content.
        if "__NEXT_DATA__" in html and len(html) > 50000:
            return False
        if len(html) < 5000:
            return True
        lower = html.lower()
        markers = ("please enable javascript", "just a moment", 'id="cmsg"')
        return any(m in lower for m in markers)

    def _scrape_http(
        self,
        searches: list[tuple[str, str]],
        max_pages: int,
    ) -> list[Job]:
        """Legacy HTTP fallback (usually blocked by DataDome)."""
        self.log("HTTP mode (no Playwright) — likely to be blocked")
        session = requests.Session()
        all_postings = []
        seen_ids = set()

        for role, location in searches:
            base_url = self._build_search_url(role, location)
            for page_num in range(1, max_pages + 1):
                url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
                try:
                    resp = session.get(url, headers=BROWSER_HEADERS, timeout=25)
                except Exception:
                    break
                if resp.status_code != 200:
                    break
                postings = self._parse_next_data(resp.text)
                if not postings:
                    break
                for posting in postings:
                    jid = posting.get("id")
                    if jid and jid not in seen_ids:
                        seen_ids.add(jid)
                        all_postings.append(posting)
            self.sleep()

        jobs = [j for p in all_postings if (j := self._to_job(p))]
        return jobs

    @staticmethod
    def _build_search_url(role: str, location: str) -> str:
        if location:
            return f"{WELLFOUND_BASE}/role/l/{role}/{location}"
        return f"{WELLFOUND_BASE}/role/r/{role}"

    def _parse_next_data(self, html_text: str) -> list[dict]:
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html_text,
            re.DOTALL,
        )
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        page_props = data.get("props", {}).get("pageProps", {})
        apollo = page_props.get("apolloState") or page_props.get("apolloCache") or {}

        if isinstance(apollo, dict) and "data" in apollo:
            apollo_data = apollo["data"]
        elif isinstance(apollo, dict):
            apollo_data = apollo
        else:
            apollo_data = {}

        return self._extract_jobs_from_apollo(apollo_data)

    @staticmethod
    def _resolve_ref(apollo_data: dict, ref) -> dict | None:
        if isinstance(ref, dict):
            if "__ref" in ref:
                return apollo_data.get(ref["__ref"])
            return ref
        if isinstance(ref, str):
            return apollo_data.get(ref)
        return None

    def _extract_jobs_from_apollo(self, apollo_data: dict) -> list[dict]:
        # Map job listing id → startup from StartupResult.highlightedJobListings
        job_to_startup: dict[str, dict] = {}
        for key, value in apollo_data.items():
            if not key.startswith("StartupResult:") or not isinstance(value, dict):
                continue
            company_name = value.get("name", "")
            company_slug = value.get("slug", "")
            for listing_ref in value.get("highlightedJobListings", []):
                resolved = self._resolve_ref(apollo_data, listing_ref)
                if not resolved:
                    ref_key = listing_ref.get("__ref") if isinstance(listing_ref, dict) else None
                    if ref_key:
                        resolved = apollo_data.get(ref_key)
                if resolved:
                    job_to_startup[str(resolved.get("id", ""))] = {
                        "name": company_name,
                        "slug": company_slug,
                        "highConcept": value.get("highConcept", ""),
                    }

        results = []
        for key, value in apollo_data.items():
            if not isinstance(value, dict):
                continue
            if "JobListingSearchResult" not in key and not key.startswith("Job:"):
                continue

            job_id = str(value.get("id", ""))
            startup = job_to_startup.get(job_id, {})
            normalized = self._normalize_apollo_job(value, startup)
            if normalized:
                results.append(normalized)

        return results

    def _normalize_apollo_job(self, job: dict, startup: dict) -> dict | None:
        job_id = job.get("id")
        title = job.get("title")
        if not job_id or not title:
            return None

        company_name = startup.get("name") or job.get("startupName") or job.get("companyName", "")
        company_slug = startup.get("slug") or job.get("startupSlug") or job.get("companySlug", "")
        location = self._extract_locations(job)
        compensation = job.get("compensation", "") or ""
        description = (
            job.get("description")
            or job.get("descriptionSnippet")
            or startup.get("highConcept")
            or ""
        )
        if isinstance(description, dict):
            description = description.get("text", "") or str(description)

        slug = job.get("slug", "")
        if slug:
            apply_url = f"{WELLFOUND_BASE}/jobs/{slug}"
        else:
            apply_url = f"{WELLFOUND_BASE}/jobs/{job_id}"

        posted = job.get("liveStartAt") or job.get("postedAt")
        date_posted = ""
        if posted:
            try:
                ts = int(posted)
                if ts > 1_000_000_000_000:
                    ts = ts // 1000
                date_posted = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass

        job_type_raw = job.get("jobType", "") or job.get("job_type", "")
        remote = job.get("remote", False)
        department_parts = [str(job_type_raw), compensation]
        if remote:
            department_parts.append("Remote")
        department = "; ".join(p for p in department_parts if p)

        return {
            "id": str(job_id),
            "title": title,
            "company": company_name or "Unknown",
            "location": location,
            "department": department,
            "description": description,
            "apply_url": apply_url,
            "date_posted": date_posted,
            "job_type_raw": job_type_raw,
        }

    @staticmethod
    def _extract_locations(job: dict) -> str:
        locs = job.get("locationNames")
        if isinstance(locs, dict) and "json" in locs:
            locs = locs["json"]
        if isinstance(locs, list):
            return "; ".join(str(x) for x in locs if x)
        if isinstance(locs, str):
            return locs
        return job.get("location", "") or ""

    def _to_job(self, posting: dict) -> Job | None:
        title = posting.get("title", "")
        if not title:
            return None

        company = posting.get("company", "Unknown")
        location = posting.get("location", "")
        department = posting.get("department", "")
        description = posting.get("description", "")

        job_type = self.infer_job_type(title, description)
        raw_type = str(posting.get("job_type_raw", "")).lower()
        if "intern" in raw_type:
            job_type = "internship"

        if not self.matches_keywords(title, department, description):
            return None
        if not self.is_us_location(location):
            return None

        date_posted = posting.get("date_posted", "")
        if not self.passes_filters(title, job_type, date_posted, description):
            return None

        apply_url = posting.get("apply_url", "")
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
