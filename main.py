"""
Main runner — orchestrates all scrapers and writes output.

Usage:
  python main.py                        # Use niche from config.yaml
  python main.py --niche pm             # Same as product_management
  python main.py --niche engineering --dry-run   # Preview without saving
  python main.py --sources greenhouse lever      # Only specific sources
"""
import argparse
import csv
import yaml
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from scrapers.base import Job, NICHE_ALIASES
from scrapers.filters import (
    format_active_filters,
    resolve_active_industries,
    resolve_company_types,
    resolve_keywords,
    source_is_enabled_for_company_types,
)
from scrapers.greenhouse import GreenhouseScraper
from scrapers.lever import LeverScraper
from scrapers.ashby import AshbyScraper
from scrapers.workday import WorkdayScraper
from scrapers.github_lists import JobrightGitHubScraper, SimplifyGitHubScraper
from scrapers.yc_jobs import YCJobsScraper
from scrapers.wellfound import WellfoundScraper

# Optional — uncomment if you want Indeed (heavier, more likely to get blocked)
# from scrapers.indeed import IndeedScraper

DEFAULT_OUTPUT = "output/jobs_output.csv"
DEFAULT_COLUMNS = [
    "title", "company", "location", "department", "type",
    "date_posted", "apply_url", "source", "niche", "id",
]


def load_config(path="config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_niche(niche: str, config: dict) -> tuple[str, dict]:
    """Map CLI aliases (e.g. pm) to canonical config keys."""
    canonical = NICHE_ALIASES.get(niche, niche)
    niches = config.get("niches", {})

    if canonical in niches:
        return canonical, niches[canonical]

    if niche in niches:
        return niche, niches[niche]

    print(f"⚠️  Unknown niche '{niche}', falling back to 'general'")
    return "general", niches.get("general", {})


def resolve_output_path(filename: str | None, override: str | None) -> str:
    if override:
        path = override
    elif filename:
        path = filename
    else:
        path = DEFAULT_OUTPUT

    path_obj = Path(path)
    if not path_obj.is_absolute() and path_obj.parent == Path("."):
        return str(Path("output") / path_obj.name)
    return path


def dedup(jobs: list[Job]) -> list[Job]:
    """Remove duplicate jobs by ID (company + title + url hash)."""
    seen = set()
    unique = []
    for job in jobs:
        if job.id not in seen:
            seen.add(job.id)
            unique.append(job)
    return unique


def sort_jobs(jobs: list[Job]) -> list[Job]:
    """Sort by date posted descending (newest first)."""
    def date_key(job):
        try:
            return datetime.strptime(job.date_posted, "%Y-%m-%d")
        except Exception:
            return datetime.min
    return sorted(jobs, key=date_key, reverse=True)


def get_csv_columns(config: dict) -> list[str]:
    columns = config.get("output", {}).get("columns") or DEFAULT_COLUMNS
    if "id" not in columns:
        columns = list(columns) + ["id"]
    return columns


def write_csv(jobs: list[Job], path: str, config: dict):
    """Write jobs to CSV using columns from config."""
    if not jobs:
        print("No jobs to write.")
        return

    fieldnames = get_csv_columns(config)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            row = job.to_dict()
            writer.writerow({col: row.get(col, "") for col in fieldnames})

    print(f"\n✅ Saved {len(jobs)} jobs → {path}")


def print_summary(jobs: list[Job]):
    """Print a summary breakdown."""
    print("\n─── SUMMARY ──────────────────────────────")
    by_source = defaultdict(int)
    by_type = defaultdict(int)
    by_niche = defaultdict(int)

    for job in jobs:
        by_source[job.source] += 1
        by_type[job.type] += 1
        by_niche[job.niche] += 1

    print(f"Total jobs: {len(jobs)}")
    print("\nBy source:")
    for s, count in sorted(by_source.items()):
        print(f"  {s:20s} {count}")
    print("\nBy type:")
    for t, count in sorted(by_type.items()):
        print(f"  {t:20s} {count}")
    print("──────────────────────────────────────────\n")


def get_scrapers(config: dict, niche_config: dict, enabled_sources: list[str] | None):
    """Instantiate enabled scrapers."""
    sources_cfg = config.get("sources", {})
    filters = config.get("filters", {})
    runtime = filters.get("_runtime", {})
    active_types = frozenset(
        runtime.get("active_company_types") or resolve_company_types(filters)
    )

    all_scrapers = {
        "greenhouse": GreenhouseScraper,
        "lever": LeverScraper,
        "ashby": AshbyScraper,
        "workday": WorkdayScraper,
        "jobright_github": JobrightGitHubScraper,
        "simplify_github": SimplifyGitHubScraper,
        "yc_jobs": YCJobsScraper,
        "wellfound": WellfoundScraper,
        # "indeed": IndeedScraper,  # Uncomment to enable
    }

    scrapers = []
    for name, cls in all_scrapers.items():
        if enabled_sources and name not in enabled_sources:
            continue
        source_cfg = sources_cfg.get(name, {})
        if not source_cfg.get("enabled", True):
            continue
        if not source_is_enabled_for_company_types(name, source_cfg, active_types):
            continue
        scrapers.append(cls(config, niche_config))

    return scrapers


def main():
    parser = argparse.ArgumentParser(description="Job scraper for LinkedIn lead magnet")
    parser.add_argument(
        "--niche",
        type=str,
        help="Override active niche (pm = product_management, biz = business)",
    )
    parser.add_argument("--sources", nargs="+", help="Only run specific sources (e.g. greenhouse lever)")
    parser.add_argument(
        "--industries",
        nargs="+",
        help="Only search these industry groups (e.g. mechanical software for engineering)",
    )
    parser.add_argument(
        "--company-types",
        nargs="+",
        choices=["startups", "fortune_500"],
        help="Include only these company types (default: both)",
    )
    parser.add_argument(
        "--startups-only",
        action="store_true",
        help="Shortcut for --company-types startups",
    )
    parser.add_argument(
        "--fortune-500-only",
        action="store_true",
        help="Shortcut for --company-types fortune_500",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print results, don't save")
    parser.add_argument("--output", type=str, help="Override output file path")
    args = parser.parse_args()

    if args.startups_only and args.fortune_500_only:
        print("Choose --startups-only or --fortune-500-only, not both.")
        sys.exit(1)

    config = load_config()

    raw_niche = args.niche or config.get("active_niche", "general")
    niche, niche_config = resolve_niche(raw_niche, config)
    config["active_niche"] = niche

    filters = config.setdefault("filters", {})
    active_industries = resolve_active_industries(
        niche_config, filters, args.industries
    )
    if active_industries is not None and not active_industries:
        print("No industries enabled. Enable at least one in config or pass --industries.")
        sys.exit(1)

    if args.company_types:
        active_company_types = resolve_company_types(filters, args.company_types)
    elif args.startups_only:
        active_company_types = frozenset({"startups"})
    elif args.fortune_500_only:
        active_company_types = frozenset({"fortune_500"})
    else:
        active_company_types = resolve_company_types(filters)

    if not active_company_types:
        print("No company types enabled. Enable startups and/or fortune_500 in config.")
        sys.exit(1)

    filters["_runtime"] = {
        "active_industries": sorted(active_industries) if active_industries else None,
        "active_company_types": sorted(active_company_types),
    }

    posted_days = filters.get("posted_within_days", 30)
    print(f"🔍 Scraping niche: '{niche}'")
    print(f"   {format_active_filters(active_industries, active_company_types)}")
    keywords = niche_config.get("keywords", [])
    if active_industries is not None:
        keywords = resolve_keywords(niche_config, active_industries)
    preview = ", ".join(keywords[:3])
    if len(keywords) > 3:
        preview += "..."
    print(f"   Keywords: {preview}")
    print(f"   Posted within: {posted_days} days (jobs with unknown dates are kept)")
    print()

    scrapers = get_scrapers(config, niche_config, args.sources)
    if not scrapers:
        print("No scrapers enabled. Check config.yaml sources section.")
        sys.exit(1)

    all_jobs = []
    for scraper in scrapers:
        print(f"\n{'='*50}")
        print(f"Running: {scraper.source_name.upper()}")
        print(f"{'='*50}")
        jobs = scraper.scrape()
        all_jobs.extend(jobs)

    jobs = dedup(all_jobs)
    jobs = sort_jobs(jobs)

    print_summary(jobs)

    if args.dry_run:
        print("DRY RUN — not saving. First 5 results:")
        for job in jobs[:5]:
            print(f"  [{job.source}] {job.title} @ {job.company} — {job.location}")
        return

    output_path = resolve_output_path(
        config.get("output", {}).get("filename"),
        args.output,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    write_csv(jobs, output_path, config)


if __name__ == "__main__":
    main()
