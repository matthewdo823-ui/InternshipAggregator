"""
Runtime filter resolution for industries and company types.
"""
from scrapers.companies import COMPANY_TYPE_LABELS, source_company_types


def resolve_active_industries(
    niche_config: dict,
    filters_config: dict,
    cli_industries: list[str] | None = None,
) -> set[str] | None:
    """
    Return active industry keys for the niche, or None if the niche has no industry groups.
    CLI --industries overrides config toggles.
    """
    industries_cfg = niche_config.get("industries", {})
    if not industries_cfg:
        return None

    if cli_industries:
        unknown = set(cli_industries) - set(industries_cfg)
        if unknown:
            print(f"⚠️  Unknown industries {sorted(unknown)} — ignoring")
        return set(cli_industries) & set(industries_cfg)

    toggles = filters_config.get("industries", {})
    active = set()
    for name, cfg in industries_cfg.items():
        enabled = cfg.get("enabled", True)
        if name in toggles:
            enabled = bool(toggles[name])
        if enabled:
            active.add(name)
    return active


def resolve_keywords(niche_config: dict, active_industries: set[str] | None) -> list[str]:
    """Build keyword list from enabled industry groups, or fall back to flat keywords."""
    industries_cfg = niche_config.get("industries", {})
    if industries_cfg and active_industries is not None:
        keywords = []
        # Preserve config.yaml industry order (sets are unordered).
        for name in industries_cfg:
            if name in active_industries:
                keywords.extend(industries_cfg.get(name, {}).get("keywords", []))
        return keywords
    return niche_config.get("keywords", [])


def resolve_company_types(
    filters_config: dict,
    cli_types: list[str] | None = None,
) -> frozenset[str]:
    """Return enabled company types. Defaults to both startups and fortune_500."""
    if cli_types is not None:
        return frozenset(cli_types)

    cfg = filters_config.get("company_types", {})
    active = set()
    if cfg.get("startups", True):
        active.add("startups")
    if cfg.get("fortune_500", True):
        active.add("fortune_500")
    return frozenset(active) or frozenset({"startups", "fortune_500"})


def source_is_enabled_for_company_types(
    source_name: str,
    source_cfg: dict,
    active_types: frozenset[str],
) -> bool:
    """Skip a source when it cannot satisfy any active company-type filter."""
    if len(active_types) >= 2:
        return True
    source_types = source_company_types(source_name, source_cfg)
    return bool(source_types & active_types)


def format_active_filters(
    active_industries: set[str] | None,
    active_company_types: frozenset[str],
) -> str:
    parts = []
    if active_industries is not None:
        parts.append(f"industries: {', '.join(sorted(active_industries))}")
    type_labels = [COMPANY_TYPE_LABELS.get(t, t) for t in sorted(active_company_types)]
    parts.append(f"company types: {', '.join(type_labels)}")
    return " | ".join(parts)
