"""
Partner canonicalizer for Project Pulse Knowledge Graph.

Resolves partner name aliases to stable canonical PartnerReward node IDs across
all sources that reference partners: dim_partner_reward_catalog and
fct_partner_reward_inventory.

The same partner appears in multiple surface forms across sources:
    "Nike UK"
    "NIKE"
    "Nike"
    "Nike Inc"
    "Nike Ltd"

Partner normalization extends base normalize_alias() with one additional rule:
known legal and geographic suffixes are stripped before matching, so that
"Nike UK" and "Nike" resolve to the same canonical entry.

The canonical display name is always preserved as registered — suffix stripping
only affects the alias keys used for lookup, not the stored display name.
"""

from __future__ import annotations

import re

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias


# Legal and geographic suffix registry

# These suffixes are stripped from partner name aliases at both registration
# and lookup time. The set is configurable: callers may pass a custom set to
# build_partner_canonicalizer() to extend or override the defaults.
#
# Suffixes are matched as whole words at the end of the normalized string,
# case-insensitively. "Nike UK" → "nike" (after lowercase + strip "uk").

DEFAULT_STRIP_SUFFIXES: frozenset[str] = frozenset(
    {
        "ltd",
        "llc",
        "inc",
        "plc",
        "corp",
        "co",
        "group",
        "holdings",
        "international",
        "intl",
        "uk",
        "us",
        "usa",
        "eu",
        "global",
    }
)

# Matches a whole word (one of the registered suffixes) at the end of a string.
# Rebuilt whenever the suffix set changes.
def _build_suffix_pattern(suffixes: frozenset[str]) -> re.Pattern[str]:
    escaped = "|".join(re.escape(s) for s in sorted(suffixes, key=len, reverse=True))
    return re.compile(
        r"\s+(?:" + escaped + r")\s*$",
        re.IGNORECASE,
    )


_DEFAULT_SUFFIX_PATTERN: re.Pattern[str] = _build_suffix_pattern(DEFAULT_STRIP_SUFFIXES)



# Partner-specific normalization



def _normalize_partner_alias(
    value: str,
    suffix_pattern: re.Pattern[str] = _DEFAULT_SUFFIX_PATTERN,
) -> str:
    """
    Normalize a partner name alias for consistent lookup.

    Rules applied (in order):
    1. Apply shared normalize_alias() — strip, lowercase, collapse whitespace,
       strip outer punctuation.
    2. Repeatedly strip trailing legal/geographic suffixes until none remain.
       Suffixes are only stripped when preceded by whitespace (whole-word match)
       so "Nike" is never truncated to "Nik".

    The full canonical display name is preserved separately — this normalization
    is only applied to alias lookup keys, not to stored names.

    Args:
        value:          Raw partner name string.
        suffix_pattern: Compiled regex for suffix stripping.

    Returns:
        Normalized partner alias string with suffixes removed.

    Examples:
        >>> _normalize_partner_alias("Nike UK")
        'nike'
        >>> _normalize_partner_alias("NIKE")
        'nike'
        >>> _normalize_partner_alias("Nike Inc")
        'nike'
        >>> _normalize_partner_alias("Adidas Ltd")
        'adidas'
        >>> _normalize_partner_alias("  Puma Global  ")
        'puma'
    """
    # Step 1 — shared normalization
    normalized = normalize_alias(value)

    # Step 2 — iteratively strip trailing suffixes
    # Repeat until no suffix is found — handles "Nike UK Ltd" → "nike uk" → "nike"
    prev = None
    while prev != normalized:
        prev = normalized
        normalized = suffix_pattern.sub("", normalized).strip()

    if not normalized:
        # Entire value was suffix tokens — fall back to base normalized form
        return normalize_alias(value)

    return normalized



# PartnerCanonicalizer



class PartnerCanonicalizer(BaseCanonicalizer):
    """
    Resolves partner name aliases to canonical PartnerReward node IDs.

    Alias types handled:
    - partner_name (exact and normalized)
    - known abbreviations
    - name variants with legal/geographic suffixes ("Nike UK", "Nike Ltd")

    Suffix stripping is applied at both registration and lookup time using the
    same pattern, so aliases registered as "Nike UK" are discoverable by callers
    passing "NIKE" or "Nike Inc".

    The canonical display name preserves the original full form as registered.
    """

    def __init__(
        self,
        alias_map: AliasMap,
        suffix_pattern: re.Pattern[str] = _DEFAULT_SUFFIX_PATTERN,
    ) -> None:
        """
        Initialise with a pre-built AliasMap and suffix pattern.

        Args:
            alias_map:      AliasMap populated by build_partner_canonicalizer().
            suffix_pattern: Compiled suffix-stripping regex. Defaults to the
                            pattern built from DEFAULT_STRIP_SUFFIXES.
        """
        self._alias_map = alias_map
        self._suffix_pattern = suffix_pattern

    # ------------------------------------------------------------------
    # BaseCanonicalizer interface
    # ------------------------------------------------------------------

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw partner name alias to its canonical form.

        Applies partner normalization (shared normalize_alias + suffix
        stripping) before lookup.

        Args:
            raw_value: Raw partner name string.

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """
        try:
            normalized = _normalize_partner_alias(raw_value, self._suffix_pattern)
        except Exception:  # noqa: BLE001
            return None
        return self._alias_map.resolve(normalized)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered partner.

        Args:
            raw_value: Raw partner name string.

        Returns:
            True if resolvable, False otherwise.
        """
        return self.resolve(raw_value) is not None

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical PartnerReward node IDs registered in this
        canonicalizer.

        Returns:
            List of canonical ID strings in registration order.
        """
        return self._alias_map.all_canonical_ids()

    # ------------------------------------------------------------------
    # Domain-specific resolution methods
    # ------------------------------------------------------------------

    def resolve_partner_name(self, name: str) -> CanonicalForm | None:
        """
        Resolve a partner by name with full partner normalization.

        Equivalent to resolve() but named explicitly for callers working
        with partner_name fields from warehouse rows.

        Args:
            name: Raw partner name string (e.g. "Nike UK", "NIKE", "Nike Inc").

        Returns:
            CanonicalForm if the normalized name resolves, None otherwise.
        """
        return self.resolve(name)

    def list_all_partners(self) -> list[CanonicalForm]:
        """
        Return all registered canonical partner forms.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return self._alias_map.all_forms()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Return the number of registered canonical partners."""
        return self._alias_map.size()



# Factory



def build_partner_canonicalizer(
    alias_data: dict[str, list[str]],
    *,
    strip_suffixes: frozenset[str] | None = None,
) -> PartnerCanonicalizer:
    """
    Build a PartnerCanonicalizer from pre-loaded alias data.

    The alias_data dict is produced by CanonicalRegistryLoader.load_partner_aliases()
    or StaticSeedLoader.load("partners"). It maps canonical_id to a flat list
    of raw alias strings (partner name variants and abbreviations).

    Each alias is registered in two forms:
    1. The base-normalized form (via normalize_alias, applied internally by AliasMap).
    2. The suffix-stripped form (via _normalize_partner_alias), registered as an
       additional alias so that "nike" is discoverable from both "Nike UK" and "Nike".

    This double-registration means the AliasMap holds both normalized forms, and
    resolve() — which applies suffix stripping before lookup — will always find
    the right entry regardless of which form the caller provides.

    Args:
        alias_data:     Dict mapping canonical_id to list of raw alias strings.
        strip_suffixes: Optional custom suffix set. Defaults to DEFAULT_STRIP_SUFFIXES.

    Returns:
        Populated PartnerCanonicalizer.
    """
    suffix_set = strip_suffixes if strip_suffixes is not None else DEFAULT_STRIP_SUFFIXES
    suffix_pattern = (
        _build_suffix_pattern(suffix_set)
        if suffix_set is not DEFAULT_STRIP_SUFFIXES
        else _DEFAULT_SUFFIX_PATTERN
    )

    alias_map = AliasMap(source_name="PartnerCanonicalizer")

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)

        # Expand each alias with its suffix-stripped form so both are registered
        expanded = _expand_with_stripped_forms(aliases, suffix_pattern)
        try:
            alias_map.register(canonical_id, canonical_name, expanded)
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "PartnerCanonicalizer: skipping partner due to alias collision — %s", exc
            )

    return PartnerCanonicalizer(alias_map, suffix_pattern)



# Internal helpers



def _expand_with_stripped_forms(
    aliases: list[str],
    suffix_pattern: re.Pattern[str],
) -> list[str]:
    """
    Expand an alias list by adding the suffix-stripped form of each alias.

    For "Nike UK", this adds "Nike" alongside "Nike UK" so that both are
    registered in the AliasMap (both will be further normalized by AliasMap
    internally via normalize_alias).

    Args:
        aliases:        List of raw alias strings.
        suffix_pattern: Compiled suffix-stripping regex.

    Returns:
        Expanded list with suffix-stripped variants included.
    """
    expanded: list[str] = []
    seen: set[str] = set()

    for alias in aliases:
        stripped_alias = alias.strip()
        if not stripped_alias or stripped_alias in seen:
            continue

        expanded.append(stripped_alias)
        seen.add(stripped_alias)

        # Build the suffix-stripped form and add it if distinct
        try:
            stripped_form = _normalize_partner_alias(stripped_alias, suffix_pattern)
        except Exception:  # noqa: BLE001
            continue

        if stripped_form and stripped_form not in seen:
            expanded.append(stripped_form)
            seen.add(stripped_form)

    return expanded


def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from a partner alias list.

    For partners the canonical display name should be the full registered name
    (e.g. "Nike UK"), not the suffix-stripped lookup key. Preference order:

    1. First alias that contains a space (most likely the full business name).
    2. First alias with mixed or title case (e.g. "Nike", not "nike").
    3. First non-empty alias.
    4. canonical_id as last resort.

    Args:
        canonical_id: Canonical ID for fallback.
        aliases:      List of raw alias strings.

    Returns:
        Selected display name string.
    """
    first_non_empty: str | None = None
    first_mixed_case: str | None = None

    for alias in aliases:
        stripped = alias.strip()
        if not stripped:
            continue

        if first_non_empty is None:
            first_non_empty = stripped

        if " " in stripped:
            return stripped

        if stripped != stripped.lower() and first_mixed_case is None:
            first_mixed_case = stripped

    return first_mixed_case or first_non_empty or canonical_id