"""
Indeed scraper — uses requests + BeautifulSoup.
Indeed has decent HTML structure and doesn't require JS rendering.
"""
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from datetime import datetime, timedelta

from scrapers.base import BaseScraper, Job


class IndeedScraper(BaseScraper):

    source_name = "indeed"
    BASE_URL = "https://www.indeed.com/jobs"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def scrape(self) -> list[Job]:
        all_jobs = []
        max_per_kw = (
            self.niche_config.get("indeed_max_results_per_keyword")
            or self.config["sources"]["indeed"].get("max_results_per_keyword", 50)
        )
        location = self.filters.get("location", "United States")

        for keyword in self.keywords:
            self.log(f"Searching: '{keyword}'")
            jobs = self._scrape_keyword(keyword, location, max_per_kw)
            self.log(f"  → Found {len(jobs)} jobs")
            all_jobs.extend(jobs)
            self.sleep()

        return all_jobs

    def _scrape_keyword(self, keyword: str, location: str, max_results: int) -> list[Job]:
        jobs = []
        start = 0
        per_page = 15

        while start < max_results:
            params = {
                "q": keyword,
                "l": location,
                "fromage": self.filters.get("posted_within_days", 30),
                "start": start,
            }
            url = f"{self.BASE_URL}?{urlencode(params)}"

            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                self.log(f"  Request failed: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.find_all("div", class_="job_seen_beacon")
            if not cards:
                cards = soup.find_all("li", attrs={"class": lambda c: c and "JobCard" in " ".join(c)})

            if not cards:
                self.log("  No cards found — Indeed may have changed structure or blocked request")
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)

            if len(cards) < per_page:
                break

            start += per_page
            time.sleep(self.delay)

        return jobs

    def _parse_card(self, card) -> Job | None:
        try:
            title_el = card.find("span", {"id": lambda x: x and "jobTitle" in x})
            if not title_el:
                title_el = card.find("a", class_=lambda c: c and "jobTitle" in " ".join(c))
            title = title_el.get_text(strip=True) if title_el else ""

            if not title:
                return None

            company_el = card.find("span", {"data-testid": "company-name"})
            if not company_el:
                company_el = card.find("a", {"data-testid": "company-name"})
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = card.find("div", {"data-testid": "text-location"})
            location = loc_el.get_text(strip=True) if loc_el else ""

            if not self.is_us_location(location):
                return None

            date_el = card.find("span", {"data-testid": "myJobsStateDate"})
            if not date_el:
                date_el = card.find("span", class_=lambda c: c and "date" in " ".join(c).lower())
            date_text = date_el.get_text(strip=True) if date_el else ""
            date_posted = self._parse_date(date_text)

            link_el = card.find("a", href=True)
            href = link_el["href"] if link_el else ""
            if href.startswith("/"):
                href = f"https://www.indeed.com{href}"
            apply_url = href.split("&tk=")[0] if "&tk=" in href else href

            if not self.matches_keywords(title, department=location):
                return None

            job_type = self.infer_job_type(title)
            if not self.passes_filters(title, job_type, date_posted):
                return None

            return Job(
                title=title,
                company=company,
                location=location,
                type=job_type,
                date_posted=date_posted,
                apply_url=apply_url,
                source="indeed",
                niche=self.niche,
            )
        except Exception as e:
            self.log(f"  Parse error: {e}")
            return None

    def _parse_date(self, text: str) -> str:
        """Convert relative date text → YYYY-MM-DD, or '' if unknown."""
        if not text or not text.strip():
            return ""

        text = text.lower()
        today = datetime.today()
        try:
            if "just" in text or "today" in text:
                return today.strftime("%Y-%m-%d")
            if "day" in text:
                days = int("".join(filter(str.isdigit, text)) or "1")
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            if "month" in text:
                months = int("".join(filter(str.isdigit, text)) or "1")
                return (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        except Exception:
            pass
        return ""
