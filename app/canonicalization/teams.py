"""
Team canonicalizer for Project Pulse Knowledge Graph.

Resolves team references to stable canonical Team node IDs across all
sources that reference teams: dim_teams, dim_teams_enhanced, fct_predictions,
fct_team_affinity, fct_team_daily_growth, dim_tags, dim_fixtures, dim_leagues.

Sources may reference teams by:
- integer team_id (the warehouse primary key)
- team_name string (may vary in casing and spacing)
- team_code (short 2–4 character code, e.g. "MCI", "ARS")
- known alternate names (e.g. "Man City", "Manchester City FC")

All three specialized resolve methods (resolve_team_id, resolve_team_name,
resolve_team_code) ultimately delegate to the shared AliasMap, which means
all alias types are registered in one place and looked up via the same
normalized path.
"""

from __future__ import annotations

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias



# TeamCanonicalizer



class TeamCanonicalizer(BaseCanonicalizer):
    """
    Resolves team references to canonical Team node IDs.

    Alias types handled:
    - integer team_id (stringified, registered and looked up as-is)
    - team_name (registered and looked up via normalize_alias)
    - team_code (registered uppercased, looked up uppercased)
    - known alternate names (normalized via normalize_alias)

    All resolution paths delegate to the underlying AliasMap so that a single
    registration covers all alias types for a given team.
    """

    def __init__(self, alias_map: AliasMap) -> None:
        """
        Initialise with a pre-built AliasMap.

        Args:
            alias_map: AliasMap populated by build_team_canonicalizer().
        """
        self._alias_map = alias_map

    # ------------------------------------------------------------------
    # BaseCanonicalizer interface
    # ------------------------------------------------------------------

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw team alias to its canonical form.

        The value is normalized via normalize_alias() before lookup, matching
        the normalization applied at registration time. Numeric strings
        (e.g. "13") are also handled because team IDs are registered as
        their stringified form.

        Args:
            raw_value: Raw alias string — a name, code, or stringified ID.

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """
        return self._alias_map.resolve(raw_value)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered team.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable, False otherwise.
        """
        return self._alias_map.is_known(raw_value)

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical Team node IDs registered in this canonicalizer.

        Returns:
            List of canonical ID strings in registration order.
        """
        return self._alias_map.all_canonical_ids()

    # ------------------------------------------------------------------
    # Domain-specific resolution methods
    # ------------------------------------------------------------------

    def resolve_team_id(self, team_id: int) -> CanonicalForm | None:
        """
        Resolve a team by integer team_id.

        team_id values are registered as their stringified form ("13", "42").
        The integer is stringified here before lookup — no normalization is
        applied beyond str() since numeric IDs have no casing or whitespace.

        Args:
            team_id: Integer warehouse team ID.

        Returns:
            CanonicalForm if the team_id is registered, None otherwise.
        """
        return self._alias_map.resolve(str(team_id))

    def resolve_team_name(self, name: str) -> CanonicalForm | None:
        """
        Resolve a team by name with full normalization.

        The name is passed through normalize_alias() which handles casing,
        whitespace, and punctuation — matching the normalization applied at
        registration time.

        Args:
            name: Raw team name string (e.g. "Man City", "MANCHESTER CITY").

        Returns:
            CanonicalForm if the normalized name is registered, None otherwise.
        """
        return self._alias_map.resolve(name)

    def resolve_team_code(self, code: str) -> CanonicalForm | None:
        """
        Resolve a team by short team code.

        Team codes are registered uppercased and stripped. The lookup mirrors
        that: the input is uppercased and stripped before querying the AliasMap.
        normalize_alias() is not used here because it lowercases the input,
        which would prevent matching the uppercase-registered codes.

        Args:
            code: Short team code (e.g. "MCI", "ARS", "LIV").

        Returns:
            CanonicalForm if the code is registered, None otherwise.
        """
        if not code or not code.strip():
            return None
        normalized_code = code.strip().upper()
        return self._alias_map.resolve(normalized_code)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_all_forms(self) -> list[CanonicalForm]:
        """
        Return all registered CanonicalForm instances for all teams.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return self._alias_map.all_forms()

    def size(self) -> int:
        """Return the number of registered canonical teams."""
        return self._alias_map.size()



# Factory



def build_team_canonicalizer(
    alias_data: dict[str, list[str]],
) -> TeamCanonicalizer:
    """
    Build a TeamCanonicalizer from pre-loaded alias data.

    The alias_data dict is produced by CanonicalRegistryLoader.load_team_aliases()
    or StaticSeedLoader.load("teams"). It maps canonical_id to a flat list of
    raw alias strings (names, codes, and stringified IDs).

    Alias registration rules applied here:
    - All aliases are passed to AliasMap.register() as-is. AliasMap applies
      normalize_alias() internally at registration time, so names and codes
      are both stored in their normalized form.
    - Team codes are expected to be included in the alias list already
      uppercased by the loader (the graph node stores them uppercased).
      resolve_team_code() uppercases at lookup time to match.
    - Stringified team IDs (e.g. "13") are included in the alias list by the
      loader. They are registered normalized (which for numeric strings is a
      no-op beyond stripping).

    The canonical_name for each entry is derived from the first non-empty alias
    in the list that does not look like a numeric ID. If no suitable name is
    found, the canonical_id itself is used as the display name.

    Args:
        alias_data: Dict mapping canonical_id to list of raw alias strings.

    Returns:
        Populated TeamCanonicalizer.
    """
    alias_map = AliasMap(source_name="TeamCanonicalizer")

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)
        alias_map.register(canonical_id, canonical_name, aliases)

    return TeamCanonicalizer(alias_map)



# Internal helpers



def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from an alias list.

    Preference order:
    1. First alias that is not purely numeric (a name string, not an ID).
    2. First alias that is purely numeric (last resort if only IDs are present).
    3. canonical_id itself if the alias list is empty.

    Args:
        canonical_id: Canonical ID for fallback.
        aliases:      List of raw alias strings.

    Returns:
        Selected display name string.
    """
    first_numeric: str | None = None

    for alias in aliases:
        stripped = alias.strip()
        if not stripped:
            continue
        if stripped.isdigit():
            if first_numeric is None:
                first_numeric = stripped
        else:
            return stripped

    return first_numeric or canonical_id