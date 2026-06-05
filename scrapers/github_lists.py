"""
Scrapers for curated internship lists hosted as GitHub README files.

  - jobright-ai/2026-Product-Management-Internship (markdown table)
  - SimplifyJobs/Summer2026-Internships (HTML tables in README)
"""
import re
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Job


def fetch_github_readme(owner: str, repo: str, branch: str) -> str:
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_md_link(cell: str) -> tuple[str, str]:
    """Return (label, url) from **[Label](url)** or plain text."""
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", cell)
    if match:
        return _clean_text(match.group(1)), match.group(2).strip()
    return _clean_text(cell), ""


def _parse_relative_age(age: str) -> str:
    """Convert Simplify '3d' / '1w' style ages to YYYY-MM-DD."""
    age = (age or "").strip().lower()
    if not age:
        return ""

    today = datetime.now().date()
    try:
        if age.endswith("d"):
            days = int(age[:-1])
            return (today - timedelta(days=days)).strftime("%Y-%m-%d")
        if age.endswith("w"):
            weeks = int(age[:-1])
            return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        if age.endswith("mo"):
            months = int(age[:-2])
            return (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    except ValueError:
        pass
    return ""


def _parse_jobright_date(text: str) -> str:
    """Parse Jobright table dates like 'Jun 04'."""
    text = (text or "").strip()
    if not text:
        return ""
    for fmt in ("%b %d", "%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _first_apply_url_from_html(html: str) -> str:
    """Prefer direct employer apply links over Simplify tracking links."""
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith("http"):
            continue
        host = urlparse(href).netloc.lower()
        if "simplify.jobs" in host or "imgur.com" in host:
            continue
        return href
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith("http"):
            return href
    return ""


def _location_from_simplify_cell(cell_html: str) -> str:
    soup = BeautifulSoup(cell_html, "html.parser")
    details = soup.find("details")
    if details:
        summary = details.find("summary")
        parts = [_clean_text(summary.get_text()) if summary else ""]
        for br_loc in details.find_all("br"):
            if br_loc.next_sibling:
                parts.append(_clean_text(str(br_loc.next_sibling)))
        text = "; ".join(p for p in parts if p)
        return text.replace("4 locations", "").strip(" ;")
    return _clean_text(soup.get_text())


def parse_jobright_readme(markdown: str) -> list[dict]:
    """Parse Jobright markdown pipe tables into raw job dicts."""
    rows = []
    last_company = ""

    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        if "Company" in line and "Job Title" in line:
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue

        company_cell, title_cell, location, work_model, date_cell = cells[:5]
        if company_cell.startswith("↳"):
            company_name = last_company
        else:
            company_name, _ = _extract_md_link(company_cell)
            if company_name:
                last_company = company_name

        title, apply_url = _extract_md_link(title_cell)
        if not title:
            continue

        rows.append({
            "company": company_name or "Unknown",
            "title": title,
            "location": _clean_text(location),
            "department": _clean_text(work_model),
            "apply_url": apply_url,
            "date_posted": _parse_jobright_date(date_cell),
        })

    return rows


def _section_names_for_niche(niche: str) -> list[str] | None:
    """Return Simplify README section substrings to scrape; None = all sections."""
    mapping = {
        "engineering": [
            "Software Engineering Internship Roles",
            "Hardware Engineering Internship Roles",
            "Data Science, AI & Machine Learning Internship Roles",
        ],
        "product_management": ["Product Management Internship Roles"],
        "finance": ["Quantitative Finance Internship Roles"],
        "business": None,  # business roles scattered across sections; filter by keywords
        "general": None,
    }
    return mapping.get(niche, mapping["general"])


def parse_simplify_readme(markdown: str, section_names: list[str] | None = None) -> list[dict]:
    """Parse Simplify HTML tables from README markdown."""
    rows = []
    parts = re.split(r"(?=^## )", markdown, flags=re.MULTILINE)
    last_company = ""

    for part in parts:
        header_match = re.match(r"^##\s+(.+)$", part, re.MULTILINE)
        if not header_match:
            continue
        header = header_match.group(1).strip()

        if section_names is not None:
            if not any(name in header for name in section_names):
                continue

        for table_html in re.findall(r"<table>.*?</table>", part, flags=re.DOTALL | re.IGNORECASE):
            soup = BeautifulSoup(table_html, "html.parser")
            for tr in soup.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) < 4:
                    continue

                company_html = str(cells[0])
                role = _clean_text(cells[1].get_text())
                location = _location_from_simplify_cell(str(cells[2]))
                application_html = str(cells[3])
                age = _clean_text(cells[4].get_text()) if len(cells) > 4 else ""

                if not role or role.lower() == "role":
                    continue
                if "🔒" in company_html or "🔒" in role or "Internship application is closed" in application_html:
                    continue

                company_soup = BeautifulSoup(company_html, "html.parser")
                company_anchor = company_soup.find("a")
                company_text = _clean_text(cells[0].get_text())
                if company_text == "↳":
                    company_name = last_company
                else:
                    if company_anchor:
                        company_name = _clean_text(company_anchor.get_text())
                    else:
                        company_name, _ = _extract_md_link(company_html)
                    if not company_name:
                        company_name = re.sub(r"^[🔥🛂🇺🇸🎓↳\s]+", "", company_text).strip()
                    if company_name:
                        last_company = company_name

                apply_url = _first_apply_url_from_html(application_html)
                rows.append({
                    "company": company_name or "Unknown",
                    "title": role,
                    "location": location,
                    "department": header,
                    "apply_url": apply_url,
                    "date_posted": _parse_relative_age(age),
                })

    return rows


class JobrightGitHubScraper(BaseScraper):
    """
    https://github.com/jobright-ai/2026-Product-Management-Internship
    """

    source_name = "jobright_github"
    OWNER = "jobright-ai"
    REPO = "2026-Product-Management-Internship"
    BRANCH = "master"

    def scrape(self) -> list[Job]:
        if self.niche not in ("product_management", "general"):
            self.log("Skipping — repo is product-management only")
            return []

        self.log(f"Fetching README: {self.OWNER}/{self.REPO} ({self.BRANCH})")
        try:
            markdown = fetch_github_readme(self.OWNER, self.REPO, self.BRANCH)
        except Exception as e:
            self.log(f"Failed to fetch README: {e}")
            return []

        raw_rows = parse_jobright_readme(markdown)
        self.log(f"Parsed {len(raw_rows)} listings from README table")

        jobs = []
        for row in raw_rows:
            job = self._row_to_job(row)
            if job:
                jobs.append(job)

        self.log(f"  → {len(jobs)} matched after filters")
        return jobs

    def _row_to_job(self, row: dict) -> Job | None:
        title = row["title"]
        department = row.get("department", "")
        location = row.get("location", "")

        if not self.matches_keywords(title, department):
            return None
        company = row.get("company", "Unknown")
        if not self.should_include_company(company):
            return None
        if not self.is_us_location(location):
            return None

        job_type = self.infer_job_type(title)
        date_posted = row.get("date_posted", "")

        if not self.passes_filters(title, job_type, date_posted):
            return None

        apply_url = row.get("apply_url", "")
        if not apply_url:
            return None

        return Job(
            title=title,
            company=company,
            location=location,
            department=department,
            type=job_type,
            date_posted=date_posted,
            apply_url=apply_url,
            source=self.source_name,
            niche=self.niche,
        )


class SimplifyGitHubScraper(BaseScraper):
    """
    https://github.com/SimplifyJobs/Summer2026-Internships
    """

    source_name = "simplify_github"
    OWNER = "SimplifyJobs"
    REPO = "Summer2026-Internships"
    BRANCH = "dev"

    def scrape(self) -> list[Job]:
        sections = _section_names_for_niche(self.niche)
        label = "all sections" if sections is None else ", ".join(sections)
        self.log(f"Fetching README: {self.OWNER}/{self.REPO} ({self.BRANCH})")
        self.log(f"  Sections: {label}")

        try:
            markdown = fetch_github_readme(self.OWNER, self.REPO, self.BRANCH)
        except Exception as e:
            self.log(f"Failed to fetch README: {e}")
            return []

        raw_rows = parse_simplify_readme(markdown, sections)
        self.log(f"Parsed {len(raw_rows)} listings from README tables")

        jobs = []
        for row in raw_rows:
            job = self._row_to_job(row)
            if job:
                jobs.append(job)

        self.log(f"  → {len(jobs)} matched after filters")
        return jobs

    def _row_to_job(self, row: dict) -> Job | None:
        title = row["title"]
        department = row.get("department", "")
        location = row.get("location", "")

        if not self.matches_keywords(title, department):
            return None
        company = row.get("company", "Unknown")
        if not self.should_include_company(company):
            return None
        if not self.is_us_location(location):
            return None

        job_type = self.infer_job_type(title)
        date_posted = row.get("date_posted", "")

        if not self.passes_filters(title, job_type, date_posted):
            return None

        apply_url = row.get("apply_url", "")
        if not apply_url:
            return None

        return Job(
            title=title,
            company=company,
            location=location,
            department=department,
            type=job_type,
            date_posted=date_posted,
            apply_url=apply_url,
            source=self.source_name,
            niche=self.niche,
        )
