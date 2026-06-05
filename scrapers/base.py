"""
Base scraper class. All source scrapers inherit from this.
"""
import re
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from scrapers.companies import classify_company
from scrapers.filters import resolve_company_types, resolve_keywords


@dataclass
class Job:
    title: str
    company: str
    location: str
    type: str               # "internship" or "full-time"
    date_posted: str        # YYYY-MM-DD or empty if unknown
    apply_url: str
    source: str
    niche: str
    department: str = ""
    id: str = field(default="")

    def __post_init__(self):
        raw = f"{self.company.lower().strip()}{self.title.lower().strip()}{self.apply_url}"
        self.id = hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self):
        return asdict(self)


# CLI / config shorthand → canonical niche keys in config.yaml
NICHE_ALIASES = {
    "pm": "product_management",
    "product": "product_management",
    "eng": "engineering",
    "biz": "business",
}

# Short tokens use word boundaries so "intern" won't match "internal"
_BOUNDARY_TERMS = frozenset({
    "intern", "interns", "internship", "apm", "analyst", "associate",
    "entry", "grad", "staff", "senior", "lead", "director", "principal",
    "coop", "co-op",
})

_STOP_WORDS = frozenset({"a", "an", "the", "for", "and", "or", "of", "in", "to", "at"})

# Multi-word units kept together when matching config keywords
_COMPOUND_PHRASES = (
    "new grad", "new graduate", "co-op", "co op", "entry level",
    "software engineer", "mechanical engineer", "electrical engineer",
    "civil engineer", "aerospace engineer", "industrial engineer",
    "product manager", "associate product manager", "product analyst",
    "investment banking", "equity research", "associate program",
    "apm program",
    "business analyst", "business operations", "business development",
    "management consulting", "associate consultant", "corporate strategy",
    "supply chain", "people operations", "talent acquisition",
    "project management", "customer success", "revenue operations",
    "financial analyst", "growth marketing", "product marketing",
    "rotational program", "leadership development", "business intelligence",
    "summer intern", "analyst program", "associate analyst", "summer analyst",
    "revenue operations", "business development",
)

# Inferred types that still satisfy config job_types entries
_JOB_TYPE_GROUPS = {
    "internship": frozenset({"internship", "co-op"}),
    "co-op": frozenset({"co-op", "internship"}),
    "full-time": frozenset({"full-time", "early-career", "new-grad"}),
    "early-career": frozenset({"early-career", "new-grad", "internship", "co-op", "full-time"}),
    "new-grad": frozenset({"new-grad", "early-career", "full-time"}),
}

# (regex, job type) — first match wins; order matters
_JOB_TYPE_PATTERNS = [
    (r"\b(internship|interns?)\b", "internship"),
    (r"\bco-?ops?\b", "co-op"),
    (r"\b(new\s*grad(?:uate)?|university\s*grad|college\s*grad|recent\s*grad(?:uate)?)\b", "new-grad"),
    (r"\b(entry[\s-]?level|early\s*career|graduate\s*program|rotational\s*program|"
     r"leadership\s*program|university\s*program|campus\s*recruit|apprentice(?:ship)?)\b", "early-career"),
    (r"\b(summer\s+analyst|analyst\s+program|university\s+analyst)\b", "internship"),
    (r"\bassociate\s+(?:product|program|analyst|banking|consultant)\b", "early-career"),
]

_EARLY_CAREER_RE = re.compile(
    r"\b(internship|interns?|co-?ops?|new\s*grad(?:uate)?|university|college|"
    r"entry[\s-]?level|early\s*career|graduate\s*program|campus|student|apprentice|"
    r"rotational|summer(?:\s+analyst|\s+intern)?|analyst\s+program|associate\s+analyst|"
    r"leadership\s+development|development\s+program|university\s+program|campus\s+program|"
    r"undergraduate|graduate\s+intern)\b",
    re.I,
)

_BUSINESS_EARLY_CAREER_RE = re.compile(
    r"\b(internship|interns?|co-?ops?|new\s*grad(?:uate)?|university|college|"
    r"entry[\s-]?level|early\s*career|graduate\s*program|campus|student|apprentice|"
    r"rotational|summer\s+(?:intern|analyst)|analyst\s+program|leadership\s+development|"
    r"ldp|development\s+program|university\s+program|campus\s+program|"
    r"undergraduate|graduate\s+intern|management\s+trainee|college\s+program|"
    r"associate\s+(?:analyst|consultant|program|banking)|early\s*career\s+associate)\b",
    re.I,
)

_NICHE_PROFILE_RULES = {
    "engineering": (
        re.compile(
            r"\b(engineer(?:ing)?|developer|swe|firmware|hardware|mechanical|electrical|"
            r"civil|aerospace|industrial|structural|manufacturing|process|robotics|"
            r"biomedical|materials\s+science)\b",
            re.I,
        ),
        _EARLY_CAREER_RE,
    ),
    "product_management": (
        re.compile(
            r"\b(product\s+(?:manager|management|analyst|operations|ops)|"
            r"apm|associate\s+product|product\s+marketing)\b",
            re.I,
        ),
        _EARLY_CAREER_RE,
    ),
    "finance": (
        re.compile(
            r"\b(finance|financial|banking|investment|equity|quant(?:itative)?|"
            r"capital\s+markets|treasury|corporate\s+development|analyst)\b",
            re.I,
        ),
        _EARLY_CAREER_RE,
    ),
    "business": (
        re.compile(
            r"\b(business\s+(?:analyst|analytics|intelligence|operations|development|intern|architecture)|"
            r"consult(?:ing|ant)|strategy|corporate\s+strategy|operations(?:\s+analyst|\s+&|\s+and)?|"
            r"marketing|sales|account\s+(?:executive|manager|development|management)|"
            r"human\s+resources|\bhr\b|people\s+operations|talent\s+acquisition|"
            r"recruiting|supply\s+chain|logistics|procurement|accounting|audit|"
            r"tax|project\s+(?:management|coordinator)|program\s+management|"
            r"customer\s+success|client\s+services|commercial|rev(?:enue)?\s*ops|"
            r"partnerships|corporate\s+development|management\s+trainee|rotational|"
            r"leadership\s+development|financial\s+analyst|data\s+analyst|"
            r"business\s+development|\bbdr\b|sdr|controllership|deal\s+desk)\b",
            re.I,
        ),
        _BUSINESS_EARLY_CAREER_RE,
    ),
    "general": (
        re.compile(
            r"\b(intern(?:ship)?|new\s*grad|entry[\s-]?level|associate\s+program|"
            r"early\s*career|university|campus)\b",
            re.I,
        ),
        None,
    ),
}


class BaseScraper(ABC):
    """
    Abstract base class for all job scrapers.

    To add a new source:
      1. Create a file in scrapers/ (e.g. scrapers/mysite.py)
      2. Subclass BaseScraper
      3. Implement the scrape() method — return a list of Job objects
      4. Register it in main.py
    """

    def __init__(self, config: dict, niche_config: dict):
        self.config = config
        self.niche = config.get("active_niche", "general")
        self.niche_config = niche_config
        self.filters = config.get("filters", {})
        runtime = self.filters.get("_runtime", {})
        active_industries = runtime.get("active_industries")
        self.active_industries = set(active_industries) if active_industries is not None else None
        self.active_company_types = frozenset(
            runtime.get("active_company_types")
            or resolve_company_types(self.filters)
        )
        self.keywords = resolve_keywords(niche_config, self.active_industries)
        self.allowed_job_types = self._expand_allowed_job_types(
            niche_config.get("job_types", [])
        )
        self.education_filter = niche_config.get("education_filter", False)
        self.delay = config.get("sources", {}).get(self.source_name, {}).get("delay_seconds", 2)
        self.jobs: list[Job] = []

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source key matching config.yaml (e.g. 'indeed')"""
        pass

    @abstractmethod
    def scrape(self) -> list[Job]:
        """Main scrape method. Returns list of Job objects."""
        pass

    def sleep(self):
        """Polite delay between requests."""
        time.sleep(self.delay)

    def includes_all_company_types(self) -> bool:
        return self.active_company_types >= frozenset({"startups", "fortune_500"})

    def should_include_company(self, slug_or_name: str) -> bool:
        """Filter ATS company lists by startup vs Fortune 500 toggles."""
        if self.includes_all_company_types():
            return True
        return classify_company(slug_or_name) in self.active_company_types

    @staticmethod
    def _expand_allowed_job_types(job_types: list[str]) -> set[str]:
        if not job_types:
            return set()
        expanded = set()
        for job_type in job_types:
            expanded |= _JOB_TYPE_GROUPS.get(job_type, {job_type})
        return expanded

    @staticmethod
    def _term_in_text(term: str, text: str) -> bool:
        """Match a term with word boundaries when needed to avoid false positives."""
        term = term.lower().strip()
        if not term or not text:
            return False
        if term in _BOUNDARY_TERMS or len(term) <= 4:
            return bool(re.search(rf"\b{re.escape(term)}\b", text, re.I))
        return term in text

    @classmethod
    def _keyword_tokens(cls, keyword: str) -> list[str]:
        """Split a config keyword into compound phrases and remaining terms."""
        remaining = keyword.lower().strip()
        tokens = []
        for phrase in sorted(_COMPOUND_PHRASES, key=len, reverse=True):
            if phrase in remaining:
                tokens.append(phrase)
                remaining = remaining.replace(phrase, " ")
        tokens.extend(
            t for t in re.split(r"[\s\-/,]+", remaining)
            if t and t not in _STOP_WORDS
        )
        return tokens

    @classmethod
    def _phrase_matches_keyword(cls, keyword: str, text: str) -> bool:
        kw = keyword.lower().strip()
        if not kw:
            return False

        # Full phrase with flexible whitespace
        phrase = re.escape(kw).replace(r"\ ", r"\s+")
        if re.search(rf"\b{phrase}\b", text, re.I):
            return True

        tokens = cls._keyword_tokens(kw)
        if len(tokens) >= 2:
            return all(cls._term_in_text(token, text) for token in tokens)
        return cls._term_in_text(kw, text)

    def _build_search_text(self, title: str, department: str = "", description: str = "") -> str:
        parts = [title, department, self.strip_html(description)[:800]]
        return " ".join(p for p in parts if p).lower()

    def _matches_niche_profile(self, title: str, department: str = "") -> bool:
        """
        Inclusive fallback using title + department only (avoids description noise).
        Requires a niche role signal and an early-career signal.
        """
        rules = _NICHE_PROFILE_RULES.get(self.niche)
        if not rules:
            return False
        headline = f"{title} {department}".lower()
        role_re, early_re = rules
        if not role_re.search(headline):
            return False
        if early_re is None:
            return True
        return bool(early_re.search(headline))

    @classmethod
    def _keyword_matches_with_title_anchor(
        cls, keyword: str, full_text: str, headline: str
    ) -> bool:
        """
        Keyword must match full text, with an early-career or role signal in the title.
        Prevents description-only false positives (e.g. 'new grad' in body, senior role title).
        """
        if not cls._phrase_matches_keyword(keyword, full_text):
            return False

        tokens = cls._keyword_tokens(keyword)
        early_tokens = [
            t for t in tokens
            if t in {"intern", "internship", "new grad", "new graduate", "co-op", "co op",
                     "entry level", "associate program", "apm program"}
            or "intern" in t
        ]
        if early_tokens:
            return any(cls._term_in_text(t, headline) for t in early_tokens)

        return any(cls._term_in_text(t, headline) for t in tokens)

    def matches_keywords(
        self,
        title: str,
        department: str = "",
        description: str = "",
    ) -> bool:
        """
        Match configured keywords against title, department, and description.
        Uses word boundaries for short terms, compound phrases for multi-word keywords,
        title anchoring to avoid description noise, and niche profile fallback.
        """
        headline = f"{title} {department}".lower()
        text = self._build_search_text(title, department, description)
        if not text.strip():
            return False

        for keyword in self.keywords:
            if self._keyword_matches_with_title_anchor(keyword, text, headline):
                return True

        return self._matches_niche_profile(title, department)

    def should_exclude(self, title: str) -> bool:
        """Filter out senior/irrelevant roles based on config."""
        title_lower = title.lower()
        for kw in self.filters.get("exclude_keywords", []):
            if self._term_in_text(kw, title_lower):
                return True
        return False

    @classmethod
    def infer_job_type(cls, title: str, description: str = "") -> str:
        text = f"{title} {cls.strip_html(description)}".lower()
        for pattern, job_type in _JOB_TYPE_PATTERNS:
            if re.search(pattern, text, re.I):
                return job_type
        return "full-time"

    def matches_job_type(self, job_type: str) -> bool:
        if not self.allowed_job_types:
            return True
        return job_type in self.allowed_job_types

    def within_posted_window(self, date_str: str) -> bool:
        """
        Keep jobs posted within filters.posted_within_days.
        Jobs with missing or unparseable dates are kept (date uncertain).
        """
        if not date_str or not str(date_str).strip():
            return True

        days = self.filters.get("posted_within_days")
        if days is None:
            return True

        try:
            posted = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
            cutoff = (datetime.now() - timedelta(days=int(days))).date()
            return posted >= cutoff
        except (ValueError, TypeError):
            return True

    @staticmethod
    def strip_html(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ")

    def passes_education_filter(self, title: str, description: str = "") -> bool:
        """
        When education_filter is on, favor student/early-career postings and
        drop roles that clearly require extensive senior experience.
        """
        if not self.education_filter:
            return True

        combined = f"{title} {self.strip_html(description)}".lower()

        senior_signals = [
            "10+ years", "15+ years", "20+ years",
            "10 years of", "15 years of", "20 years of",
            "director level", "executive level",
        ]
        if any(s in combined for s in senior_signals):
            return False

        student_patterns = [
            r"\b(internship|interns?|co-?ops?)\b",
            r"\bnew\s*grad(?:uate)?\b",
            r"\brecent\s*grad(?:uate)?\b",
            r"\bentry[\s-]?level\b",
            r"\buniversity\b",
            r"\bcollege\b",
            r"\bbachelor",
            r"\bundergraduate\b",
            r"\bgraduate\s+student\b",
            r"\b0[\s\-–]?2\s+years\b",
            r"\bless\s+than\s+3\s+years\b",
        ]
        if any(re.search(p, combined, re.I) for p in student_patterns):
            return True

        if self.niche == "business":
            return bool(_BUSINESS_EARLY_CAREER_RE.search(combined))

        # Title already matched niche keywords (often intern-focused); allow through
        return True

    def passes_filters(
        self,
        title: str,
        job_type: str,
        date_posted: str,
        description: str = "",
    ) -> bool:
        if self.should_exclude(title):
            return False
        if not self.matches_job_type(job_type):
            return False
        if not self.within_posted_window(date_posted):
            return False
        if not self.passes_education_filter(title, description):
            return False
        if self.niche == "business" and job_type == "full-time":
            return False
        return True

    def is_us_location(self, location: str) -> bool:
        if self.filters.get("location") != "United States":
            return True
        if not location or not location.strip():
            return True

        us_markers = [
            "US", "U.S.", "United States", "USA", "Remote",
            "New York", "San Francisco", "Seattle", "Austin", "Boston",
            "Los Angeles", "Chicago", "Denver", "Atlanta", "Miami",
            "Washington", "Portland", "San Diego", "San Jose",
            ", CA", ", NY", ", TX", ", WA", ", MA", ", CO", ", IL",
            " CA,", " NY,", " TX,", " SF", "NYC", "Bay Area",
        ]
        return any(marker in location for marker in us_markers)

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.source_name.upper()}] {msg}")
