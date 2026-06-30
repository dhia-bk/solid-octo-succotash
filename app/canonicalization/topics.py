"""
Topic canonicalizer for Project Pulse Knowledge Graph.

Resolves topic label aliases to stable canonical Topic node IDs across all
sources that produce or reference topics: fct_topics, fct_user_behavior
(implicit topic references), and sentiment labels.

The same topic concept appears in many surface forms across sources:
    "Premier League"
    "premier league"
    "premier_league"
    "premier-league"
    "premierleague"
    "EPL"
    "English Premier League"

Topic normalization extends base normalize_alias() with one additional rule:
hyphens and underscores are treated as whitespace equivalents, so slug-style
variants collapse to the same normalized string as space-separated names.
"""

from __future__ import annotations

import re

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias

# Matches hyphens and underscores for slug-to-space conversion.
_SLUG_SEPARATOR_RE: re.Pattern[str] = re.compile(r"[-_]+")



# Topic-specific normalization



def _normalize_topic_alias(value: str) -> str:
    """
    Normalize a topic alias with topic-specific rules applied on top of
    the shared normalize_alias() function.

    Rules applied (in order):
    1. Replace all hyphen and underscore characters with a single space.
       This collapses slug variants before the shared normalization runs,
       so "premier-league", "premier_league", and "premier league" all
       produce the same normalized string.
    2. Apply normalize_alias() for strip, lowercase, whitespace collapse,
       and punctuation stripping.

    Args:
        value: Raw topic alias string.

    Returns:
        Normalized topic alias string.

    Examples:
        >>> _normalize_topic_alias("Premier League")
        'premier league'
        >>> _normalize_topic_alias("premier_league")
        'premier league'
        >>> _normalize_topic_alias("premier-league")
        'premier league'
        >>> _normalize_topic_alias("premierleague")
        'premierleague'
        >>> _normalize_topic_alias("EPL")
        'epl'
    """
    # Step 1 — replace hyphens and underscores with space before normalization
    slug_replaced = _SLUG_SEPARATOR_RE.sub(" ", value)

    # Step 2 — shared normalization (strip, lowercase, collapse whitespace,
    #           strip outer punctuation)
    return normalize_alias(slug_replaced)



# TopicCanonicalizer



class TopicCanonicalizer(BaseCanonicalizer):
    """
    Resolves topic label aliases to canonical Topic node IDs.

    Alias types handled:
    - topic_label (exact and normalized)
    - slug variants with hyphens or underscores ("premier-league",
      "premier_league")
    - known synonym groups ("EPL", "Premier League", "English Premier League")

    Normalization applies topic-specific rules on top of base normalize_alias():
    hyphens and underscores are treated as whitespace equivalents so that
    slug and space-separated forms resolve to the same canonical entry.
    """

    def __init__(self, alias_map: AliasMap) -> None:
        """
        Initialise with a pre-built AliasMap.

        Args:
            alias_map: AliasMap populated by build_topic_canonicalizer().
        """
        self._alias_map = alias_map

    # ------------------------------------------------------------------
    # BaseCanonicalizer interface
    # ------------------------------------------------------------------

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw topic alias to its canonical form.

        Applies topic normalization (hyphen/underscore → space, then shared
        normalize_alias) before lookup.

        Args:
            raw_value: Raw alias string — a label, slug, or synonym.

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """
        return self._resolve_normalized(_normalize_topic_alias, raw_value)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered topic.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable, False otherwise.
        """
        return self.resolve(raw_value) is not None

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical Topic node IDs registered in this canonicalizer.

        Returns:
            List of canonical ID strings in registration order.
        """
        return self._alias_map.all_canonical_ids()

    # ------------------------------------------------------------------
    # Domain-specific resolution methods
    # ------------------------------------------------------------------

    def resolve_label(self, label: str) -> CanonicalForm | None:
        """
        Resolve a topic by label with full topic normalization.

        Equivalent to resolve() but named explicitly for callers that are
        working with topic_label fields from warehouse rows.

        Args:
            label: Raw topic label string (e.g. "Premier League",
                   "premier_league", "EPL").

        Returns:
            CanonicalForm if the normalized label is registered, None otherwise.
        """
        return self.resolve(label)

    def list_canonical_labels(self) -> list[str]:
        """
        Return canonical display names for all registered topics.

        Returns canonical_name values (not canonical_ids) in registration order.
        Used by serving and notification layers that need a human-readable
        list of all active topics.

        Returns:
            List of canonical topic label strings.
        """
        return [form.canonical_name for form in self._alias_map.all_forms()]

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_all_forms(self) -> list[CanonicalForm]:
        """
        Return all registered CanonicalForm instances for all topics.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return self._alias_map.all_forms()

    def size(self) -> int:
        """Return the number of registered canonical topics."""
        return self._alias_map.size()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_normalized(
        self,
        normalizer: object,
        raw_value: str,
    ) -> CanonicalForm | None:
        """
        Apply a normalizer function and look up the result in the AliasMap.

        Separated from resolve() so that the normalization step can be tested
        independently without going through the full AliasMap lookup.

        Args:
            normalizer: Callable[[str], str] normalization function.
            raw_value:  Raw input string.

        Returns:
            CanonicalForm if found, None otherwise.
        """
        try:
            from app.core.exceptions import CanonicalizationError
            normalized = normalizer(raw_value)  # type: ignore[operator]
        except Exception:  # noqa: BLE001
            return None

        # AliasMap.resolve() calls normalize_alias() internally, which would
        # double-normalize. To avoid this we look up the already-normalized
        # key directly via the forward map using resolve_by_id after resolving
        # the forward mapping ourselves.
        #
        # However, AliasMap stores keys via its own normalize_alias() pass.
        # Since _normalize_topic_alias() calls normalize_alias() as its final
        # step, the output is already in the same form AliasMap used at
        # registration. We therefore call _alias_map.resolve() with the
        # pre-normalized value — normalize_alias("already normalized") is
        # idempotent, so the double-pass is safe.
        return self._alias_map.resolve(normalized)



# Factory



def build_topic_canonicalizer(
    alias_data: dict[str, list[str]],
) -> TopicCanonicalizer:
    """
    Build a TopicCanonicalizer from pre-loaded alias data.

    The alias_data dict is produced by CanonicalRegistryLoader.load_topic_aliases()
    or StaticSeedLoader.load("topics"). It maps canonical_id to a flat list of
    raw alias strings (topic labels, slug variants, and synonym strings).

    For each entry, every alias is registered twice via AliasMap.register():
    once as passed (AliasMap normalizes it via normalize_alias internally),
    and once with hyphens and underscores replaced by spaces so that the
    slug variant is also discoverable via direct AliasMap.resolve() calls.

    This double-registration ensures that:
    - "premier_league" registered in seeds resolves even when the caller
      passes "premier league" (the AliasMap normalized form).
    - "premier league" registered in the graph resolves when the caller
      passes "premier_league" or "premier-league".

    Args:
        alias_data: Dict mapping canonical_id to list of raw alias strings.

    Returns:
        Populated TopicCanonicalizer.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    alias_map = AliasMap(source_name="TopicCanonicalizer")

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)

        # Build the expanded alias set: original aliases + slug-expanded forms.
        # Slug expansion converts "premier_league" → "premier league" so both
        # forms are registered as aliases pointing to the same canonical entry.
        expanded_aliases = _expand_aliases(aliases)

        try:
            alias_map.register(canonical_id, canonical_name, expanded_aliases)
        except Exception as exc:
            # Alias collision from duplicate topic labels in the warehouse data.
            # Skip the colliding topic rather than crashing the whole registry.
            _logger.warning(
                "TopicCanonicalizer: skipping topic due to alias collision — %s",
                exc,
            )

    return TopicCanonicalizer(alias_map)



# Internal helpers



def _expand_aliases(aliases: list[str]) -> list[str]:
    """
    Expand an alias list with slug-converted variants.

    For each alias that contains a hyphen or underscore, a space-substituted
    variant is added alongside the original. This ensures both the slug form
    and the space-separated form are registered in the AliasMap.

    Args:
        aliases: List of raw alias strings.

    Returns:
        Expanded list including both original and slug-converted forms.
    """
    expanded: list[str] = []
    seen: set[str] = set()

    for alias in aliases:
        if not alias or not alias.strip():
            continue

        if alias not in seen:
            expanded.append(alias)
            seen.add(alias)

        # If the alias contains a hyphen or underscore, add the space variant
        if _SLUG_SEPARATOR_RE.search(alias):
            space_form = _SLUG_SEPARATOR_RE.sub(" ", alias)
            if space_form not in seen:
                expanded.append(space_form)
                seen.add(space_form)

    return expanded


def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from a topic alias list.

    Preference order:
    1. First alias that contains a space (most likely a readable label like
       "Premier League" rather than a slug or code).
    2. First alias with mixed or title case (e.g. "EPL", not "epl").
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

        # Prefer aliases with spaces (multi-word labels)
        if " " in stripped:
            return stripped

        # Track mixed/title case (e.g. "EPL", "Champions League")
        if stripped != stripped.lower() and first_mixed_case is None:
            first_mixed_case = stripped

    return first_mixed_case or first_non_empty or canonical_id