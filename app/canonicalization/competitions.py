"""
Competition canonicalizer for Project Pulse Knowledge Graph.

Resolves competition references to stable canonical node IDs across all
sources that reference competitions: dim_super6_rounds,
dim_super6_round_fixtures, fct_super6_participants, and dim_lms_competitions.

Both Super6 and LMS competitions produce PARTICIPATED_IN edges, but they
target different node labels (Super6Round vs LMSCompetition). This canonicalizer
provides get_node_label() so that transformers can determine the correct target
label before writing a PARTICIPATED_IN edge — without importing constants or
hard-coding label strings at the transformer level.

Two separate AliasMap instances are maintained internally — one per competition
type. This allows resolve_super6_round() and resolve_lms_competition() to
search only their respective registries without risk of a Super6 round ID
accidentally matching an LMS competition ID. resolve_competition_name() and
the base resolve() search both maps in order: Super6 first, then LMS.

The node_labels dict ({canonical_id: "Super6Round"|"LMSCompetition"}) is
provided by the registry loader as a separate argument because the standard
alias_data format (dict[str, list[str]]) cannot carry per-entry metadata.
"""

from __future__ import annotations

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias
from app.core.constants import LMS_COMPETITION, SUPER6_ROUND
from app.core.exceptions import CanonicalizationError



# CompetitionCanonicalizer



class CompetitionCanonicalizer(BaseCanonicalizer):
    """
    Resolves competition aliases to canonical node IDs.

    Covers both Super6Round and LMSCompetition node types. Two internal
    AliasMap instances keep the two competition types isolated so that
    integer IDs from one type never accidentally resolve as the other.

    Alias types handled:
    - super6_round_id (integer, registered as stringified form)
    - lms_competition_id (integer, registered as stringified form)
    - competition_name (normalized via normalize_alias)

    get_node_label() returns the graph node label for a canonical ID,
    enabling transformers to write correctly-labelled PARTICIPATED_IN edges.
    """

    def __init__(
        self,
        super6_map: AliasMap,
        lms_map: AliasMap,
        node_labels: dict[str, str],
    ) -> None:
        """
        Initialise with two pre-built AliasMaps and a node label index.

        Args:
            super6_map:  AliasMap for Super6Round entries.
            lms_map:     AliasMap for LMSCompetition entries.
            node_labels: Dict mapping canonical_id → node label string.
                         Values must be SUPER6_ROUND or LMS_COMPETITION.
        """
        self._super6_map = super6_map
        self._lms_map = lms_map
        self._node_labels: dict[str, str] = node_labels

    # BaseCanonicalizer interface

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw competition alias to its canonical form.

        Searches Super6Round aliases first, then LMSCompetition. Returns the
        first match found. If the same alias string appears in both registries
        (unlikely but possible for competition names), the Super6 result takes
        precedence.

        Args:
            raw_value: Raw alias string — a name or stringified integer ID.

        Returns:
            CanonicalForm if a mapping exists in either registry, None otherwise.
        """
        result = self._super6_map.resolve(raw_value)
        if result is not None:
            return result
        return self._lms_map.resolve(raw_value)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves in either competition registry.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable in either registry, False otherwise.
        """
        return self.resolve(raw_value) is not None

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical IDs from both Super6Round and LMSCompetition
        registries, Super6 entries first.

        Returns:
            Combined list of canonical ID strings.
        """
        return self._super6_map.all_canonical_ids() + self._lms_map.all_canonical_ids()

    # Domain-specific resolution methods

    def resolve_super6_round(self, round_id: int) -> CanonicalForm | None:
        """
        Resolve a Super6 round by integer round_id.

        Looks up only the Super6Round registry, so LMS competition IDs with
        the same numeric value are never returned.

        Args:
            round_id: Integer Super6 round ID from the warehouse.

        Returns:
            CanonicalForm if the round_id is registered, None otherwise.
        """
        return self._super6_map.resolve(str(round_id))

    def resolve_lms_competition(self, competition_id: int) -> CanonicalForm | None:
        """
        Resolve an LMS competition by integer competition_id.

        Looks up only the LMSCompetition registry, so Super6 round IDs with
        the same numeric value are never returned.

        Args:
            competition_id: Integer LMS competition ID from the warehouse.

        Returns:
            CanonicalForm if the competition_id is registered, None otherwise.
        """
        return self._lms_map.resolve(str(competition_id))

    def resolve_competition_name(self, name: str) -> CanonicalForm | None:
        """
        Resolve a competition by name, searching both registries.

        The name is normalized via normalize_alias() before lookup in each
        registry. Super6Round entries are searched first; if no match is found,
        LMSCompetition entries are searched.

        Args:
            name: Raw competition name string.

        Returns:
            CanonicalForm from the first registry that matches, None otherwise.
        """
        result = self._super6_map.resolve(name)
        if result is not None:
            return result
        return self._lms_map.resolve(name)

    def get_node_label(self, canonical_id: str) -> str | None:
        """
        Return the graph node label for a given canonical competition ID.

        Used by transformers before writing PARTICIPATED_IN edges to determine
        whether the target node is a Super6Round or LMSCompetition.

        Args:
            canonical_id: Canonical competition node ID.

        Returns:
            "Super6Round", "LMSCompetition", or None if the ID is not registered.
        """
        return self._node_labels.get(canonical_id)

    def assert_node_label(self, canonical_id: str) -> str:
        """
        Return the graph node label or raise if the ID is not registered.

        The strict variant of get_node_label() for transformers that must have
        a label and should fail hard on unknown input.

        Args:
            canonical_id: Canonical competition node ID.

        Returns:
            "Super6Round" or "LMSCompetition".

        Raises:
            CanonicalizationError: If canonical_id has no registered node label.
        """
        label = self.get_node_label(canonical_id)
        if label is None:
            raise CanonicalizationError(
                "No node label registered for competition canonical_id",
                canonical_id=canonical_id,
                canonicalizer=type(self).__name__,
            )
        return label

    # Type-partitioned accessors

    def get_all_super6_forms(self) -> list[CanonicalForm]:
        """Return all registered CanonicalForm instances for Super6Round entries."""
        return self._super6_map.all_forms()

    def get_all_lms_forms(self) -> list[CanonicalForm]:
        """Return all registered CanonicalForm instances for LMSCompetition entries."""
        return self._lms_map.all_forms()

    def super6_count(self) -> int:
        """Return the number of registered Super6Round canonical entries."""
        return self._super6_map.size()

    def lms_count(self) -> int:
        """Return the number of registered LMSCompetition canonical entries."""
        return self._lms_map.size()

    def size(self) -> int:
        """Return the total number of registered competition canonical entries."""
        return self._super6_map.size() + self._lms_map.size()



# Factory



def build_competition_canonicalizer(
    alias_data: dict[str, list[str]],
    *,
    node_labels: dict[str, str],
) -> CompetitionCanonicalizer:
    """
    Build a CompetitionCanonicalizer from pre-loaded alias data and node labels.

    The alias_data dict is produced by CanonicalRegistryLoader.load_competition_aliases()
    or StaticSeedLoader.load("competitions"). It maps canonical_id to a flat list
    of raw alias strings (competition names and stringified integer IDs).

    The node_labels dict is produced by CanonicalRegistryLoader.load_competition_node_labels()
    or StaticSeedLoader.load_competition_node_labels(). It maps canonical_id to
    either SUPER6_ROUND ("Super6Round") or LMS_COMPETITION ("LMSCompetition").

    Entries in alias_data whose canonical_id has no entry in node_labels are
    skipped with a warning — their node type cannot be determined and they
    cannot be safely written as PARTICIPATED_IN edges.

    Entries in node_labels with an unrecognised label value are also skipped.

    Args:
        alias_data:   Dict mapping canonical_id to list of raw alias strings.
        node_labels:  Dict mapping canonical_id to node label string.
                      Required — competitions cannot be disambiguated without it.

    Returns:
        Populated CompetitionCanonicalizer.

    Raises:
        CanonicalizationError: If node_labels is empty and alias_data is non-empty,
            indicating the label index was not loaded.
    """
    if alias_data and not node_labels:
        raise CanonicalizationError(
            "build_competition_canonicalizer: node_labels is required and cannot be empty "
            "when alias_data is non-empty. Provide the node label index from the registry "
            "loader or static seed loader.",
        )

    valid_labels = {SUPER6_ROUND, LMS_COMPETITION}

    super6_map = AliasMap(source_name="CompetitionCanonicalizer[Super6Round]")
    lms_map = AliasMap(source_name="CompetitionCanonicalizer[LMSCompetition]")
    label_index: dict[str, str] = {}

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        node_label = node_labels.get(canonical_id)

        if node_label is None:
            # Cannot determine competition type — skip this entry
            continue

        if node_label not in valid_labels:
            # Unrecognised label — skip
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)
        label_index[canonical_id] = node_label

        if node_label == SUPER6_ROUND:
            super6_map.register(canonical_id, canonical_name, aliases)
        else:
            lms_map.register(canonical_id, canonical_name, aliases)

    return CompetitionCanonicalizer(super6_map, lms_map, label_index)



# Internal helpers



def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from a competition alias list.

    Preference order:
    1. First alias that contains a space (most likely a full competition name,
       e.g. "Super 6 Round 3", "LMS Premier League Season 2").
    2. First alias that is not purely numeric (e.g. a short name or code).
    3. First non-empty alias.
    4. canonical_id as last resort.

    Args:
        canonical_id: Canonical ID for fallback.
        aliases:      List of raw alias strings.

    Returns:
        Selected display name string.
    """
    first_non_empty: str | None = None
    first_non_numeric: str | None = None

    for alias in aliases:
        stripped = alias.strip()
        if not stripped:
            continue

        if first_non_empty is None:
            first_non_empty = stripped

        if not stripped.isdigit():
            if first_non_numeric is None:
                first_non_numeric = stripped
            if " " in stripped:
                return stripped

    return first_non_numeric or first_non_empty or canonical_id