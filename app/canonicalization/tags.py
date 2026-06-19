"""
Tag canonicalizer for Project Pulse Knowledge Graph.

Resolves tag aliases to stable canonical Tag node IDs across all sources
that reference tags: dim_tags, dim_posts, dim_news, and dim_ai_articles.

Tags appear across sources in three distinct alias forms:
- Integer tag_id (the warehouse primary key)
- tag_name string (may vary in casing and whitespace: "Premier League",
  "premier league", "Premier  League")
- tag_url slug (URL path: "/tags/premier-league", "/premier-league",
  "premier-league")

URL slug resolution applies a dedicated extraction step: the path is stripped
of its leading slash, split on "/", and the last segment is taken. The segment
is then treated as a hyphenated slug and normalized by replacing hyphens with
spaces before the shared normalize_alias() call — matching the same pattern
used for topic slugs.

The is_trending flag requires a separate data source: the alias_data dict
carries only alias strings, not boolean properties. The factory accepts an
optional trending_ids set so the trending list can be populated when the
loader provides it. If not provided, list_trending_tags() returns an empty
list — this is correct for bootstrap scenarios where trending metadata is
not yet available.
"""

from __future__ import annotations

import re

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias

# Matches one or more hyphens or underscores — used for slug-to-space conversion
# in URL segment normalization.
_SLUG_SEPARATOR_RE: re.Pattern[str] = re.compile(r"[-_]+")



# URL slug extraction



def _extract_slug_segment(url: str) -> str:
    """
    Extract the final path segment from a tag URL slug.

    Rules:
    1. Strip outer whitespace.
    2. Strip leading slash(es).
    3. Split on "/" and take the last non-empty segment.
    4. Replace hyphens and underscores with spaces.
    5. Apply normalize_alias() for lowercase, whitespace collapse, and
       punctuation stripping.

    Args:
        url: Raw tag URL string (e.g. "/tags/premier-league",
             "premier-league", "/tags/champions_league/").

    Returns:
        Normalized segment string suitable for AliasMap lookup.

    Examples:
        >>> _extract_slug_segment("/tags/premier-league")
        'premier league'
        >>> _extract_slug_segment("/premier-league")
        'premier league'
        >>> _extract_slug_segment("premier-league")
        'premier league'
        >>> _extract_slug_segment("/tags/champions_league/")
        'champions league'
    """
    stripped = url.strip().lstrip("/")

    # Take the last non-empty segment when the URL contains path components
    segments = [s for s in stripped.split("/") if s.strip()]
    segment = segments[-1] if segments else stripped

    # Replace slug separators with space before normalization
    with_spaces = _SLUG_SEPARATOR_RE.sub(" ", segment)

    return normalize_alias(with_spaces)



# TagCanonicalizer



class TagCanonicalizer(BaseCanonicalizer):
    """
    Resolves tag aliases to canonical Tag node IDs.

    Alias types handled:
    - tag_id (integer, stringified and registered as-is)
    - tag_name (normalized via normalize_alias)
    - tag_url slug (last path segment extracted, then normalized)

    Trending tag support:
        list_trending_tags() returns CanonicalForm instances for all canonical
        IDs in the trending_ids set provided at construction time. If no
        trending_ids were provided, the method returns an empty list.
    """

    def __init__(
        self,
        alias_map: AliasMap,
        trending_ids: frozenset[str] | None = None,
    ) -> None:
        """
        Initialise with a pre-built AliasMap and optional trending ID set.

        Args:
            alias_map:    AliasMap populated by build_tag_canonicalizer().
            trending_ids: Optional set of canonical IDs for trending tags.
                          If None or empty, list_trending_tags() returns [].
        """
        self._alias_map = alias_map
        self._trending_ids: frozenset[str] = trending_ids or frozenset()

    # BaseCanonicalizer interface

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw tag alias to its canonical form.

        The value is normalized via normalize_alias() before lookup.
        Numeric strings (e.g. "42") are handled because tag IDs are
        registered as their stringified form.

        Args:
            raw_value: Raw alias string — a name, stringified ID, or URL slug.

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """
        return self._alias_map.resolve(raw_value)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered tag.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable, False otherwise.
        """
        return self._alias_map.is_known(raw_value)

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical Tag node IDs registered in this canonicalizer.

        Returns:
            List of canonical ID strings in registration order.
        """
        return self._alias_map.all_canonical_ids()

    # Domain-specific resolution methods

    def resolve_tag_id(self, tag_id: int) -> CanonicalForm | None:
        """
        Resolve a tag by integer tag_id.

        tag_id values are registered as their stringified form ("42").
        The integer is stringified here before lookup — normalize_alias()
        is applied internally by AliasMap, which is a no-op for clean
        numeric strings.

        Args:
            tag_id: Integer warehouse tag ID.

        Returns:
            CanonicalForm if the tag_id is registered, None otherwise.
        """
        return self._alias_map.resolve(str(tag_id))

    def resolve_tag_name(self, name: str) -> CanonicalForm | None:
        """
        Resolve a tag by name with full normalization.

        The name passes through normalize_alias() which handles casing,
        whitespace collapse, and punctuation stripping.

        Args:
            name: Raw tag name string (e.g. "Premier League",
                  "premier league", "PREMIER LEAGUE").

        Returns:
            CanonicalForm if the normalized name is registered, None otherwise.
        """
        return self._alias_map.resolve(name)

    def resolve_tag_url(self, url: str) -> CanonicalForm | None:
        """
        Resolve a tag by URL slug.

        Extracts the final path segment from the URL, replaces hyphens and
        underscores with spaces, then normalizes via normalize_alias(). The
        resulting string is looked up in the AliasMap.

        This means "/tags/premier-league" resolves to the same canonical as
        "Premier League" because both produce the normalized form "premier league".

        Args:
            url: Raw tag URL string (e.g. "/tags/premier-league",
                 "/premier-league", "premier-league").

        Returns:
            CanonicalForm if the extracted segment is registered, None otherwise.
        """
        if not url or not url.strip():
            return None
        try:
            segment = _extract_slug_segment(url)
        except Exception:  # noqa: BLE001
            return None
        return self._alias_map.resolve(segment)

    def list_trending_tags(self) -> list[CanonicalForm]:
        """
        Return canonical forms for all tags marked is_trending.

        Returns only tags whose canonical IDs were present in the trending_ids
        set provided at construction time. If no trending_ids were provided,
        returns an empty list.

        Trending tags whose canonical ID is not registered in the AliasMap
        (data inconsistency) are silently skipped.

        Returns:
            List of CanonicalForm objects for trending tags.
        """
        result: list[CanonicalForm] = []
        for canonical_id in self._trending_ids:
            form = self._alias_map.resolve_by_id(canonical_id)
            if form is not None:
                result.append(form)
        return result

    # Convenience helpers

    def get_all_forms(self) -> list[CanonicalForm]:
        """
        Return all registered CanonicalForm instances for all tags.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return self._alias_map.all_forms()

    def trending_count(self) -> int:
        """Return the number of tags marked as trending."""
        return len(self._trending_ids)

    def size(self) -> int:
        """Return the number of registered canonical tags."""
        return self._alias_map.size()



# Factory



def build_tag_canonicalizer(
    alias_data: dict[str, list[str]],
    *,
    trending_ids: set[str] | None = None,
) -> TagCanonicalizer:
    """
    Build a TagCanonicalizer from pre-loaded alias data.

    The alias_data dict is produced by CanonicalRegistryLoader.load_tag_aliases()
    or StaticSeedLoader.load("tags"). It maps canonical_id to a flat list of
    raw alias strings covering all known alias types: tag_name, tag_url, and
    stringified tag_id.

    URL slug aliases (e.g. "/tags/premier-league") are expanded at registration
    time: the slug segment is extracted and registered as an additional alias
    alongside the raw URL. This means both the full URL path and the bare
    segment ("premier league") are discoverable.

    Stringified tag IDs (e.g. "42") are included in the alias list by the loader
    and registered without additional transformation beyond normalize_alias()
    (which is a no-op for clean numeric strings).

    Args:
        alias_data:   Dict mapping canonical_id to list of raw alias strings.
        trending_ids: Optional set of canonical IDs for trending tags. When
                      provided, list_trending_tags() will return their forms.

    Returns:
        Populated TagCanonicalizer.
    """
    alias_map = AliasMap(source_name="TagCanonicalizer")

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)

        # Expand aliases with URL slug extractions where applicable
        expanded = _expand_with_slug_segments(aliases)
        alias_map.register(canonical_id, canonical_name, expanded)

    return TagCanonicalizer(
        alias_map,
        trending_ids=frozenset(trending_ids) if trending_ids else None,
    )



# Internal helpers



def _expand_with_slug_segments(aliases: list[str]) -> list[str]:
    """
    Expand an alias list by adding normalized slug segments for URL aliases.

    For each alias that looks like a URL path (contains "/" or "-" suggesting
    a slug), the extracted segment is added alongside the original. This
    ensures both "/tags/premier-league" and "premier league" are registered.

    Args:
        aliases: List of raw alias strings.

    Returns:
        Expanded list including extracted slug segment variants.
    """
    expanded: list[str] = []
    seen: set[str] = set()

    for alias in aliases:
        stripped = alias.strip()
        if not stripped or stripped in seen:
            continue

        expanded.append(stripped)
        seen.add(stripped)

        # Attempt slug extraction for URL-like or hyphenated aliases
        if "/" in stripped or "-" in stripped or "_" in stripped:
            try:
                segment = _extract_slug_segment(stripped)
                if segment and segment not in seen:
                    expanded.append(segment)
                    seen.add(segment)
            except Exception:  # noqa: BLE001
                pass

    return expanded


def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from a tag alias list.

    Preference order:
    1. First alias that contains a space and is not a URL path (most likely
       the human-readable tag name, e.g. "Premier League").
    2. First alias that is not a URL path and not purely numeric.
    3. First non-empty alias that is not a URL path.
    4. canonical_id as last resort.

    URL paths (containing "/") are always skipped as display names.

    Args:
        canonical_id: Canonical ID for fallback.
        aliases:      List of raw alias strings.

    Returns:
        Selected display name string.
    """
    first_non_url: str | None = None
    first_non_url_non_numeric: str | None = None

    for alias in aliases:
        stripped = alias.strip()
        if not stripped:
            continue

        # Skip URL paths as display names
        if "/" in stripped:
            continue

        if first_non_url is None:
            first_non_url = stripped

        if not stripped.isdigit():
            if first_non_url_non_numeric is None:
                first_non_url_non_numeric = stripped

            # Prefer spaced multi-word names
            if " " in stripped:
                return stripped

    return first_non_url_non_numeric or first_non_url or canonical_id