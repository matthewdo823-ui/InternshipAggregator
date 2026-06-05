"""
Company type classification for startup vs Fortune 500 filtering.

Companies not in FORTUNE_500_SLUGS are treated as startups in mixed ATS sources.
Workday boards and startup-only sources (yc_jobs, wellfound) are classified at the source level.
"""

FORTUNE_500_SLUGS = frozenset({
    # Workday enterprise boards
    "boeing", "leidos", "adobe", "intel", "micron", "generalmotors",
    "salesforce", "target", "walmart", "mastercard", "nvidia", "cat",
    "ghr", "visa", "paypal", "pnc", "hitachi", "tmobile", "medtronic",
    "novartis", "pfizer", "3m", "allstate", "analogdevices", "workday",
    "travelers", "zoom", "ptc", "unum", "conocophillips",
    # Consulting / Professional Services
    "deloitte", "accenture", "ey", "pwc", "kpmg", "cognizant", "capgemini",
    "mmc", "aon",
    # Retail / CPG
    "pg", "pepsico", "coca-cola", "colgate", "generalmills", "kellogg",
    "nestle", "unilever", "mars", "estee", "nike", "costco", "homedepot",
    "lowes", "starbucks", "mcdonalds",
    # Financial Services
    "capitalone", "discover", "synchrony", "americanexpress",
    # Tech / Industrial
    "cisco", "ibm", "oracle", "ford", "honeywell", "deere", "cummins",
    "ge", "lockheedmartin", "rtx",
    # Pharma / Healthcare
    "jnj", "abbvie", "merck", "lilly",
    # Energy
    "chevron", "exxonmobil", "shell",
    # Logistics / Transportation / Hospitality
    "fedex", "ups", "delta", "united", "marriott", "hilton", "disney",
    # Telecom
    "att", "verizon",
    # Verified business Workday boards
    "capitalone", "statestreet", "alteryx", "liveramp", "ensemblehp", "sarepta",
    "generac", "redhat", "roberthalf", "homedepot", "osv-rubicon", "imerys",
    "dickssportinggoods",
    # Large public / enterprise on Greenhouse
    "airbnb", "stripe", "databricks", "cloudflare", "reddit", "discord",
    "lyft", "spacex", "coinbase", "robinhood", "samsara", "duolingo",
    "waymo", "datadog", "mongodb", "okta", "zscaler", "toast", "twilio",
    "instacart", "pinterest", "roblox", "asana", "dropbox", "intercom",
    "gitlab", "elastic", "block", "adyen", "affirm", "sofi", "andurilindustries",
    "rocketlab", "relativity", "rubrik", "commvault", "geotab", "point72",
    "imc", "hubspot",
    # Large public / enterprise on Lever
    "netflix", "atlassian", "palantir", "spotify", "zoox", "gopuff", "veeva",
    "anchorage", "kraken", "kpmg", "plaid",
    # Large public / enterprise on Ashby
    "openai", "snowflake", "confluent", "notion", "plaid", "benchling",
    "cohere", "elevenlabs", "docker", "hopper", "nerdwallet",
})

# Default company-type affinity per source (when not overridden in config.yaml)
SOURCE_COMPANY_TYPES = {
    "yc_jobs": frozenset({"startups"}),
    "wellfound": frozenset({"startups"}),
    "workday": frozenset({"fortune_500"}),
    "greenhouse": frozenset({"startups", "fortune_500"}),
    "lever": frozenset({"startups", "fortune_500"}),
    "ashby": frozenset({"startups", "fortune_500"}),
    "jobright_github": frozenset({"startups", "fortune_500"}),
    "simplify_github": frozenset({"startups", "fortune_500"}),
    "indeed": frozenset({"startups", "fortune_500"}),
    "linkedin": frozenset({"startups", "fortune_500"}),
}

COMPANY_TYPE_LABELS = {
    "startups": "Startups",
    "fortune_500": "Fortune 500",
}


def _normalize_slug(value: str) -> str:
    return value.lower().strip().replace(" ", "-").replace("_", "-")


def classify_company(slug_or_name: str) -> str:
    """Return 'fortune_500' or 'startups' for a company slug or display name."""
    normalized = _normalize_slug(slug_or_name)
    if normalized in FORTUNE_500_SLUGS:
        return "fortune_500"
    # Also match slug prefixes (e.g. "archer-aviation" won't match "archer")
    for slug in FORTUNE_500_SLUGS:
        if normalized.startswith(slug + "-") or normalized.endswith("-" + slug):
            return "fortune_500"
    return "startups"


def source_company_types(source_name: str, source_cfg: dict | None = None) -> frozenset[str]:
    """Company types a source can provide."""
    if source_cfg and source_cfg.get("company_types"):
        return frozenset(source_cfg["company_types"])
    return SOURCE_COMPANY_TYPES.get(source_name, frozenset({"startups", "fortune_500"}))
