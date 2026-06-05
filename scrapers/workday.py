"""
Workday ATS scraper.

Each company hosts its own Workday careers site. This scraper uses the
semi-public Candidate Experience Service (CXS) API:

  POST https://{tenant}.{server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

Board config is a list of (tenant, server, site, company name) tuples per niche.
Find careers URLs at https://{tenant}.{server}.myworkdayjobs.com/
"""
import re
import time
import requests
from datetime import datetime, timedelta

from scrapers.base import BaseScraper, Job


# (tenant, wd_server, site_slug, display_name)
WORKDAY_BOARDS = {
    "engineering": [
        # Aerospace / Defense
        ("boeing", "wd1", "EXTERNAL_CAREERS", "Boeing"),
        ("leidos", "wd5", "External", "Leidos"),
        # Automotive
        ("generalmotors", "wd5", "Careers_GM", "General Motors"),
        ("cat", "wd5", "CaterpillarCareers", "Caterpillar"),
        # Semiconductors / Hardware
        ("intel", "wd1", "External", "Intel"),
        ("micron", "wd1", "External", "Micron"),
        ("nvidia", "wd5", "NVIDIAExternalCareerSite", "NVIDIA"),
        ("analogdevices", "wd1", "External", "Analog Devices"),
        # Industrial / Manufacturing
        ("3m", "wd1", "Search", "3M"),
        ("hitachi", "wd1", "Hitachi", "Hitachi"),
        ("medtronic", "wd1", "MedtronicCareers", "Medtronic"),
        ("novartis", "wd3", "Novartis_Careers", "Novartis"),
        ("pfizer", "wd1", "PfizerCareers", "Pfizer"),
        ("ptc", "wd1", "PTC", "PTC"),
        # Tech
        ("adobe", "wd5", "external_experienced", "Adobe"),
        ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
        ("workday", "wd5", "Workday", "Workday"),
        ("zoom", "wd5", "Zoom", "Zoom"),
        ("paypal", "wd1", "jobs", "PayPal"),
        ("tmobile", "wd1", "External", "T-Mobile"),
    ],
    "product_management": [
        ("adobe", "wd5", "external_experienced", "Adobe"),
        ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
        ("target", "wd5", "targetcareers", "Target"),
        ("walmart", "wd5", "WalmartExternal", "Walmart"),
        ("nvidia", "wd5", "NVIDIAExternalCareerSite", "NVIDIA"),
        ("zoom", "wd5", "Zoom", "Zoom"),
        ("paypal", "wd1", "jobs", "PayPal"),
        ("workday", "wd5", "Workday", "Workday"),
    ],
    "finance": [
        ("mastercard", "wd1", "CorporateCareers", "Mastercard"),
        ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
        ("ghr", "wd1", "Lateral-US", "Bank of America"),
        ("visa", "wd5", "Visa", "Visa"),
        ("paypal", "wd1", "jobs", "PayPal"),
        ("pnc", "wd5", "External", "PNC"),
        ("travelers", "wd5", "External", "Travelers"),
        ("allstate", "wd5", "Allstate_Careers", "Allstate"),
        ("unum", "wd1", "External", "Unum"),
        ("conocophillips", "wd1", "External", "ConocoPhillips"),
    ],
    "business": [
        # Consulting / Professional Services (verified boards)
        ("accenture", "wd103", "AccentureCareers", "Accenture"),
        ("mmc", "wd1", "mmc", "Marsh McLennan"),
        ("roberthalf", "wd1", "roberthalfcareers", "Robert Half"),
        # Retail
        ("target", "wd5", "targetcareers", "Target"),
        ("walmart", "wd5", "WalmartExternal", "Walmart"),
        ("homedepot", "wd5", "CareerDepot", "Home Depot"),
        # Financial Services
        ("ghr", "wd1", "Lateral-US", "Bank of America"),
        ("mastercard", "wd1", "CorporateCareers", "Mastercard"),
        ("visa", "wd5", "Visa", "Visa"),
        ("capitalone", "wd12", "Capital_One", "Capital One"),
        ("pnc", "wd5", "External", "PNC"),
        ("statestreet", "wd1", "Global", "State Street"),
        ("travelers", "wd5", "External", "Travelers"),
        ("allstate", "wd5", "Allstate_Careers", "Allstate"),
        ("unum", "wd1", "External", "Unum"),
        ("paypal", "wd1", "jobs", "PayPal"),
        # Tech
        ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
        ("adobe", "wd5", "external_experienced", "Adobe"),
        ("workday", "wd5", "Workday", "Workday"),
        ("zoom", "wd5", "Zoom", "Zoom"),
        ("nvidia", "wd5", "NVIDIAExternalCareerSite", "NVIDIA"),
        ("alteryx", "wd108", "AlteryxCareers", "Alteryx"),
        ("liveramp", "wd5", "LiveRampCareers", "LiveRamp"),
        ("redhat", "wd5", "jobs", "Red Hat"),
        ("osv-rubicon", "wd5", "MagniteCareers", "Magnite"),
        # Industrial / Manufacturing
        ("generalmotors", "wd5", "Careers_GM", "General Motors"),
        ("cat", "wd5", "CaterpillarCareers", "Caterpillar"),
        ("3m", "wd1", "Search", "3M"),
        ("generac", "wd5", "external", "Generac"),
        ("hitachi", "wd1", "Hitachi", "Hitachi"),
        ("boeing", "wd1", "EXTERNAL_CAREERS", "Boeing"),
        ("leidos", "wd5", "External", "Leidos"),
        ("ptc", "wd1", "PTC", "PTC"),
        ("analogdevices", "wd1", "External", "Analog Devices"),
        ("imerys", "wd3", "imerys_career2", "Imerys"),
        # Pharma / Healthcare
        ("pfizer", "wd1", "PfizerCareers", "Pfizer"),
        ("novartis", "wd3", "Novartis_Careers", "Novartis"),
        ("medtronic", "wd1", "MedtronicCareers", "Medtronic"),
        ("sarepta", "wd5", "sarepta_external", "Sarepta"),
        ("ensemblehp", "wd5", "ensemblehealthpartnerscareers", "Ensemble Health Partners"),
        # Energy
        ("conocophillips", "wd1", "External", "ConocoPhillips"),
        # Telecom / Semiconductors
        ("tmobile", "wd1", "External", "T-Mobile"),
        ("intel", "wd1", "External", "Intel"),
        ("micron", "wd1", "External", "Micron"),
        ("dickssportinggoods", "wd1", "DSG", "Dick's Sporting Goods"),
    ],
    "general": [
        ("boeing", "wd1", "EXTERNAL_CAREERS", "Boeing"),
        ("leidos", "wd5", "External", "Leidos"),
        ("adobe", "wd5", "external_experienced", "Adobe"),
        ("intel", "wd1", "External", "Intel"),
        ("micron", "wd1", "External", "Micron"),
        ("generalmotors", "wd5", "Careers_GM", "General Motors"),
        ("salesforce", "wd12", "External_Career_Site", "Salesforce"),
        ("target", "wd5", "targetcareers", "Target"),
        ("walmart", "wd5", "WalmartExternal", "Walmart"),
        ("mastercard", "wd1", "CorporateCareers", "Mastercard"),
        ("nvidia", "wd5", "NVIDIAExternalCareerSite", "NVIDIA"),
        ("cat", "wd5", "CaterpillarCareers", "Caterpillar"),
        ("ghr", "wd1", "Lateral-US", "Bank of America"),
        ("visa", "wd5", "Visa", "Visa"),
        ("paypal", "wd1", "jobs", "PayPal"),
        ("pnc", "wd5", "External", "PNC"),
        ("hitachi", "wd1", "Hitachi", "Hitachi"),
        ("tmobile", "wd1", "External", "T-Mobile"),
        ("medtronic", "wd1", "MedtronicCareers", "Medtronic"),
        ("novartis", "wd3", "Novartis_Careers", "Novartis"),
        ("pfizer", "wd1", "PfizerCareers", "Pfizer"),
        ("3m", "wd1", "Search", "3M"),
        ("allstate", "wd5", "Allstate_Careers", "Allstate"),
        ("analogdevices", "wd1", "External", "Analog Devices"),
        ("workday", "wd5", "Workday", "Workday"),
        ("travelers", "wd5", "External", "Travelers"),
        ("zoom", "wd5", "Zoom", "Zoom"),
        ("ptc", "wd1", "PTC", "PTC"),
        ("unum", "wd1", "External", "Unum"),
        ("conocophillips", "wd1", "External", "ConocoPhillips"),
    ],
}


class WorkdayScraper(BaseScraper):

    source_name = "workday"
    PAGE_SIZE = 20
    MAX_KEYWORDS_PER_BOARD = 6

    def scrape(self) -> list[Job]:
        boards = WORKDAY_BOARDS.get(self.niche, WORKDAY_BOARDS["general"])
        source_cfg = self.config.get("sources", {}).get("workday", {})
        max_per_keyword = (
            self.niche_config.get("workday_max_results_per_keyword")
            or source_cfg.get("max_results_per_keyword", 50)
        )
        fetch_details = source_cfg.get("fetch_details", False)

        all_jobs = []
        search_keywords = list(self.niche_config.get("workday_search_keywords") or self.keywords)
        max_kw = self.niche_config.get("workday_max_keywords", self.MAX_KEYWORDS_PER_BOARD)
        keywords = search_keywords[:max_kw]
        if self.niche_config.get("workday_browse_all") and "" not in keywords:
            keywords.append("")

        for tenant, server, site, company in boards:
            if not self.should_include_company(tenant):
                continue
            self.log(f"Fetching: {company} ({tenant}/{site})")
            postings = self._fetch_board_postings(
                tenant, server, site, keywords, max_per_keyword
            )
            matched = self._filter_postings(
                postings, tenant, server, site, company, fetch_details
            )
            self.log(f"  → {len(postings)} fetched, {len(matched)} matched")
            all_jobs.extend(matched)
            self.sleep()

        return all_jobs

    def _base_url(self, tenant: str, server: str) -> str:
        return f"https://{tenant}.{server}.myworkdayjobs.com"

    def _headers(self, tenant: str, server: str, site: str) -> dict:
        base = self._base_url(tenant, server)
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Language": "en-US",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{base}/en-US/{site}",
        }

    def _fetch_board_postings(
        self,
        tenant: str,
        server: str,
        site: str,
        keywords: list[str],
        max_per_keyword: int,
    ) -> list[dict]:
        """Search by niche keywords and dedupe by externalPath."""
        base = self._base_url(tenant, server)
        url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
        headers = self._headers(tenant, server, site)

        seen_paths = set()
        postings = []

        search_terms = keywords or [""]
        for keyword in search_terms:
            offset = 0
            while offset < max_per_keyword:
                payload = {
                    "appliedFacets": {},
                    "limit": self.PAGE_SIZE,
                    "offset": offset,
                    "searchText": keyword,
                }
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=20)
                    if resp.status_code == 404:
                        self.log(f"  Board not found ({tenant}/{site})")
                        return postings
                    if resp.status_code == 422:
                        self.log(f"  Board rejected request ({tenant}/{site}) — skipping")
                        return postings
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    self.log(f"  Request failed for '{keyword}': {e}")
                    break

                batch = data.get("jobPostings", [])
                if not batch:
                    break

                for posting in batch:
                    path = posting.get("externalPath", "")
                    if path and path not in seen_paths:
                        seen_paths.add(path)
                        postings.append(posting)

                total = data.get("total", 0)
                offset += self.PAGE_SIZE
                if offset >= total or offset >= max_per_keyword:
                    break

            if len(search_terms) > 1:
                time.sleep(0.3)

        return postings

    def _fetch_job_detail(
        self, tenant: str, server: str, site: str, external_path: str
    ) -> dict:
        base = self._base_url(tenant, server)
        url = f"{base}/wday/cxs/{tenant}/{site}{external_path}"
        try:
            resp = requests.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self._headers(tenant, server, site)["User-Agent"],
                    "Referer": self._headers(tenant, server, site)["Referer"],
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("jobPostingInfo", {})
        except Exception:
            return {}

    @staticmethod
    def _parse_posted_on(text: str) -> str:
        if not text or not str(text).strip():
            return ""
        text = str(text).lower()
        today = datetime.now().date()
        try:
            if "today" in text or "just" in text:
                return today.strftime("%Y-%m-%d")
            if "yesterday" in text:
                return (today - timedelta(days=1)).strftime("%Y-%m-%d")
            if "day" in text:
                days = int(re.search(r"(\d+)", text).group(1)) if re.search(r"(\d+)", text) else 1
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            if "week" in text:
                weeks = int(re.search(r"(\d+)", text).group(1)) if re.search(r"(\d+)", text) else 1
                return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
            if "month" in text:
                months = int(re.search(r"(\d+)", text).group(1)) if re.search(r"(\d+)", text) else 1
                return (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        return ""

    def _build_apply_url(
        self, tenant: str, server: str, site: str, external_path: str, detail: dict
    ) -> str:
        if detail.get("externalUrl"):
            return detail["externalUrl"]
        base = self._base_url(tenant, server)
        return f"{base}/en-US/{site}{external_path}"

    def _filter_postings(
        self,
        postings: list[dict],
        tenant: str,
        server: str,
        site: str,
        company: str,
        fetch_details: bool,
    ) -> list[Job]:
        matched = []

        for posting in postings:
            title = posting.get("title", "")
            if not title:
                continue

            location = posting.get("locationsText", "")
            date_posted = self._parse_posted_on(posting.get("postedOn", ""))
            external_path = posting.get("externalPath", "")

            description = ""
            department = ""
            detail = {}
            if fetch_details and external_path:
                detail = self._fetch_job_detail(tenant, server, site, external_path)
                description = detail.get("jobDescription", "") or ""
                department = detail.get("timeType", "") or ""

            if not self.matches_keywords(title, department, description):
                continue
            if not self.is_us_location(location):
                continue

            job_type = self.infer_job_type(title, description)
            if not self.passes_filters(title, job_type, date_posted, description):
                continue

            apply_url = self._build_apply_url(
                tenant, server, site, external_path, detail
            )
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
                source="workday",
                niche=self.niche,
            ))

        return matched
