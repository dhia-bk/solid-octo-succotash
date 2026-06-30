"""
Runtime loader for canonicalization registries.

This is the only module that queries Neo4j to build canonical alias data.
Domain canonicalizers never query the graph themselves — they receive
pre-built AliasMap objects from this loader.

Loading strategy:
- Primary path: query Neo4j for nodes that are already loaded into the graph.
- Fallback path: read static YAML seed files when the graph is empty or
  unavailable (bootstrap, first backfill, CI environments).

The factory function build_canonicalizer_registry() handles both paths and
returns the full set of six domain canonicalizers ready for use.

Design rules:
- All Cypher in this module is read-only (fetch_all / fetch_one only).
- No Cypher query in this module uses string formatting for values —
  all variable data is passed via the params dict.
- Domain canonicalizer modules are imported at call time inside
  build_canonicalizer_registry() to avoid circular imports at module level.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.canonicalization.base import BaseCanonicalizer
from app.core.constants import LMS_COMPETITION, SUPER6_ROUND
from app.core.exceptions import CanonicalizationError, ConfigurationError
from app.core.logging import get_logger
from app.db.neo4j_client import Neo4jClient

logger = get_logger(__name__)


# Supported static seed domains


SUPPORTED_SEED_DOMAINS: frozenset[str] = frozenset(
    {
        "teams",
        "topics",
        "tags",
        "partners",
        "vouchers",
        "competitions",
    }
)

# Expected YAML seed file names per domain
_SEED_FILENAMES: dict[str, str] = {
    "teams": "teams.yaml",
    "topics": "topics.yaml",
    "tags": "tags.yaml",
    "partners": "partners.yaml",
    "vouchers": "vouchers.yaml",
    "competitions": "competitions.yaml",
}


# Cypher queries

# All queries are read-only MATCH statements.
# No query uses f-strings or string concatenation for values.

_QUERY_TEAM_ALIASES = """
MATCH (t:Team)
RETURN
    t.id            AS canonical_id,
    t.team_name     AS team_name,
    t.team_code     AS team_code,
    t.alternate_names AS alternate_names
"""

_QUERY_TOPIC_ALIASES = """
MATCH (t:Topic)
RETURN
    t.id            AS canonical_id,
    t.topic_label   AS topic_label,
    t.slug          AS slug
"""

_QUERY_TAG_ALIASES = """
MATCH (t:Tag)
RETURN
    t.id            AS canonical_id,
    t.tag_name      AS tag_name,
    t.tag_url       AS tag_url,
    t.tag_id        AS tag_id
"""

_QUERY_PARTNER_ALIASES = """
MATCH (p:PartnerReward)
RETURN
    p.id            AS canonical_id,
    p.partner_name  AS partner_name
"""

_QUERY_VOUCHER_ALIASES = """
MATCH (v:Voucher)
RETURN
    v.id                AS canonical_id,
    v.voucher_key       AS voucher_key,
    v.voucher_title     AS voucher_title,
    v.advertiser_name   AS advertiser_name
"""

_QUERY_COMPETITION_ALIASES = """
MATCH (n)
WHERE n:Super6Round OR n:LMSCompetition
RETURN
    n.id            AS canonical_id,
    labels(n)[0]    AS node_label,
    n.name          AS name,
    n.round_id      AS round_id,
    n.competition_id AS competition_id
"""



# CanonicalRegistryLoader



class CanonicalRegistryLoader:
    """
    Loads canonical registry data from Neo4j for all six canonicalization domains.

    Each load_* method executes a read-only Cypher query and returns the alias
    data in the standard {canonical_id: [alias_strings]} format consumed by
    domain canonicalizer factory functions.

    Competition aliases additionally carry node label information via
    load_competition_node_labels() so that CompetitionCanonicalizer can
    distinguish Super6Round from LMSCompetition canonical IDs.
    """

    def __init__(self, neo4j_client: Neo4jClient) -> None:
        self._client = neo4j_client

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    def load_team_aliases(self) -> dict[str, list[str]]:
        """
        Query Team nodes and return {canonical_id: [alias strings]}.

        Alias sources per team node:
        - team_name (primary display name)
        - team_code (short code, e.g. "MCI", "ARS")
        - team_id stringified (the integer warehouse ID)
        - entries from alternate_names list property, if present

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_TEAM_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []

            _append_if_present(aliases, row.get("team_name"))
            _append_if_present(aliases, row.get("team_code"))
            # canonical_id is the stringified warehouse team_id — register it
            # as an alias so resolve_team_id(int) can find it
            _append_if_present(aliases, canonical_id)

            # alternate_names may be stored as a list property on the node
            alt = row.get("alternate_names")
            if isinstance(alt, list):
                for name in alt:
                    _append_if_present(aliases, name)
            elif isinstance(alt, str) and alt.strip():
                aliases.append(alt.strip())

            result[canonical_id] = aliases

        logger.info(
            "Loaded team aliases from graph",
            extra={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------

    def load_topic_aliases(self) -> dict[str, list[str]]:
        """
        Query Topic nodes and return {canonical_id: [alias strings]}.

        Alias sources per topic node:
        - topic_label (canonical label string)
        - slug (URL slug variant)

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_TOPIC_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []
            _append_if_present(aliases, row.get("topic_label"))
            _append_if_present(aliases, row.get("slug"))

            result[canonical_id] = aliases

        logger.info(
            "Loaded topic aliases from graph",
            extra={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def load_tag_aliases(self) -> dict[str, list[str]]:
        """
        Query Tag nodes and return {canonical_id: [alias strings]}.

        Alias sources per tag node:
        - tag_name (primary display name)
        - tag_url (URL slug, e.g. "/tags/premier-league")
        - tag_id stringified (integer warehouse ID)

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_TAG_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []
            _append_if_present(aliases, row.get("tag_name"))
            _append_if_present(aliases, row.get("tag_url"))

            # Integer tag_id stringified for numeric lookup
            tag_id = row.get("tag_id")
            if tag_id is not None:
                _append_if_present(aliases, str(tag_id))

            result[canonical_id] = aliases

        logger.info(
            "Loaded tag aliases from graph",
            extra={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Partners
    # ------------------------------------------------------------------

    def load_partner_aliases(self) -> dict[str, list[str]]:
        """
        Query PartnerReward nodes and return {canonical_id: [alias strings]}.

        Alias sources per partner node:
        - partner_name (display name, may have casing/spacing variants in
          the warehouse; normalization handles collapse at lookup time)

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_PARTNER_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []
            _append_if_present(aliases, row.get("partner_name"))

            result[canonical_id] = aliases

        logger.info(
            "Loaded partner aliases from graph",
            extra={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Vouchers
    # ------------------------------------------------------------------

    def load_voucher_aliases(self) -> dict[str, list[str]]:
        """
        Query Voucher nodes and return {canonical_id: [alias strings]}.

        Alias sources per voucher node:
        - voucher_key (stable catalog key, e.g. "NIKE_10_OFF")
        - voucher_title (human-readable title)
        - advertiser_name (partner/brand name on the voucher)

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_VOUCHER_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []
            _append_if_present(aliases, row.get("voucher_key"))
            _append_if_present(aliases, row.get("voucher_title"))
            _append_if_present(aliases, row.get("advertiser_name"))

            result[canonical_id] = aliases

        logger.info(
            "Loaded voucher aliases from graph",
            extra={"count": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Competitions
    # ------------------------------------------------------------------

    def load_competition_aliases(self) -> dict[str, list[str]]:
        """
        Query Super6Round and LMSCompetition nodes and return
        {canonical_id: [alias strings]}.

        Alias sources per competition node:
        - name (display name)
        - round_id / competition_id stringified (integer warehouse ID)

        Returns:
            Dict mapping canonical_id to a flat list of alias strings.
        """
        records = self._client.fetch_all(_QUERY_COMPETITION_ALIASES)
        result: dict[str, list[str]] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            if not canonical_id:
                continue

            aliases: list[str] = []
            _append_if_present(aliases, row.get("name"))

            # Numeric ID as string alias
            round_id = row.get("round_id")
            competition_id = row.get("competition_id")
            if round_id is not None:
                _append_if_present(aliases, str(round_id))
            if competition_id is not None:
                _append_if_present(aliases, str(competition_id))

            result[canonical_id] = aliases

        logger.info(
            "Loaded competition aliases from graph",
            extra={"count": len(result)},
        )
        return result

    def load_competition_node_labels(self) -> dict[str, str]:
        """
        Query Super6Round and LMSCompetition nodes and return
        {canonical_id: node_label}.

        This is the label index consumed by CompetitionCanonicalizer.get_node_label()
        to distinguish Super6Round from LMSCompetition canonical IDs at transformer
        time — required before writing PARTICIPATED_IN edges.

        Returns:
            Dict mapping canonical_id to "Super6Round" or "LMSCompetition".
        """
        records = self._client.fetch_all(_QUERY_COMPETITION_ALIASES)
        result: dict[str, str] = {}

        for row in records:
            canonical_id = _require_str(row, "canonical_id")
            node_label = _require_str(row, "node_label")
            if canonical_id and node_label:
                result[canonical_id] = node_label

        return result



# StaticSeedLoader



class StaticSeedLoader:
    """
    Loads canonical alias data from static YAML seed files.

    Used during bootstrap or when the graph is not yet populated. Seed files
    live in a directory (default: configs/canonicalization/seeds/) with one
    file per domain.

    Expected YAML structure per file:

        - canonical_id: "team:13"
          canonical_name: "Manchester City"
          aliases:
            - "Man City"
            - "MCFC"
            - "13"
            - "Manchester City FC"

    For competition seeds, an additional `node_label` field is required:

        - canonical_id: "super6round:3"
          canonical_name: "Super 6 Round 3"
          node_label: "Super6Round"
          aliases:
            - "3"
            - "Super 6 Round 3"
    """

    def __init__(self, seed_dir: Path) -> None:
        """
        Initialise the loader pointing at a seed directory.

        Args:
            seed_dir: Path to the directory containing seed YAML files.

        Raises:
            ConfigurationError: If seed_dir does not exist.
        """
        self._seed_dir = Path(seed_dir)

        if not self._seed_dir.exists() or not self._seed_dir.is_dir():
            raise ConfigurationError(
                "StaticSeedLoader seed_dir does not exist or is not a directory",
                seed_dir=str(self._seed_dir),
            )

    def load(self, domain: str) -> dict[str, list[str]]:
        """
        Load alias data for a domain from its seed YAML file.

        Args:
            domain: One of: teams, topics, tags, partners, vouchers, competitions.

        Returns:
            Dict mapping canonical_id to a list of alias strings.

        Raises:
            ConfigurationError: If the domain is unsupported or the seed file
                is missing or malformed.
        """
        if domain not in SUPPORTED_SEED_DOMAINS:
            raise ConfigurationError(
                "Unsupported canonicalization seed domain",
                domain=domain,
                supported=sorted(SUPPORTED_SEED_DOMAINS),
            )

        filename = _SEED_FILENAMES[domain]
        path = self._seed_dir / filename

        if not path.exists():
            raise ConfigurationError(
                "Seed file does not exist for domain",
                domain=domain,
                path=str(path),
            )

        entries = self._read_yaml(path)
        result: dict[str, list[str]] = {}

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ConfigurationError(
                    "Seed entry must be a mapping",
                    domain=domain,
                    entry_index=i,
                )

            canonical_id = str(entry.get("canonical_id", "")).strip()
            if not canonical_id:
                raise ConfigurationError(
                    "Seed entry missing canonical_id",
                    domain=domain,
                    entry_index=i,
                )

            raw_aliases = entry.get("aliases", [])
            if not isinstance(raw_aliases, list):
                raise ConfigurationError(
                    "Seed entry 'aliases' must be a list",
                    domain=domain,
                    canonical_id=canonical_id,
                )

            aliases = [str(a).strip() for a in raw_aliases if str(a).strip()]
            result[canonical_id] = aliases

        logger.info(
            "Loaded static seed aliases",
            extra={"domain": domain, "count": len(result)},
        )
        return result

    def load_competition_node_labels(self) -> dict[str, str]:
        """
        Load the competition node label index from the competitions seed file.

        Returns:
            Dict mapping canonical_id to "Super6Round" or "LMSCompetition".

        Raises:
            ConfigurationError: If the seed file is missing or entries lack
                a node_label field.
        """
        path = self._seed_dir / _SEED_FILENAMES["competitions"]

        if not path.exists():
            raise ConfigurationError(
                "Competition seed file not found",
                path=str(path),
            )

        entries = self._read_yaml(path)
        result: dict[str, str] = {}

        valid_labels = {SUPER6_ROUND, LMS_COMPETITION}

        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue

            canonical_id = str(entry.get("canonical_id", "")).strip()
            node_label = str(entry.get("node_label", "")).strip()

            if not canonical_id or not node_label:
                continue

            if node_label not in valid_labels:
                raise ConfigurationError(
                    "Competition seed entry has invalid node_label",
                    canonical_id=canonical_id,
                    node_label=node_label,
                    valid_labels=sorted(valid_labels),
                    entry_index=i,
                )

            result[canonical_id] = node_label

        return result

    @staticmethod
    def _read_yaml(path: Path) -> list[Any]:
        """
        Read and parse a YAML file, returning the root list.

        Raises:
            ConfigurationError: If the file cannot be read or is not a list.
        """
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except OSError as exc:
            raise ConfigurationError(
                "Failed to read seed YAML file",
                path=str(path),
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                "Invalid YAML in seed file",
                path=str(path),
            ) from exc

        if data is None:
            return []

        if not isinstance(data, list):
            raise ConfigurationError(
                "Seed YAML root must be a list of entries",
                path=str(path),
                received_type=type(data).__name__,
            )

        return data



# Factory function



def build_canonicalizer_registry(
    neo4j_client: Neo4jClient | None = None,
    *,
    seed_dir: Path | None = None,
    use_static_seeds: bool = False,
) -> dict[str, BaseCanonicalizer]:
    """
    Build and return all six domain canonicalizers.

    Loading strategy:
    - If use_static_seeds=True or neo4j_client is None: load from YAML seeds.
    - Otherwise: query Neo4j via CanonicalRegistryLoader.
    - If Neo4j query fails and a seed_dir is available: fall back to seeds
      automatically and log a warning.

    Args:
        neo4j_client:     Connected Neo4j client. Required unless use_static_seeds=True.
        seed_dir:         Path to YAML seed directory. Required when use_static_seeds=True
                          or as fallback when the graph is unavailable.
        use_static_seeds: Force static seed loading regardless of Neo4j availability.

    Returns:
        Dict keyed by domain name:
        {
            "teams":        TeamCanonicalizer,
            "topics":       TopicCanonicalizer,
            "partners":     PartnerCanonicalizer,
            "vouchers":     VoucherCanonicalizer,
            "tags":         TagCanonicalizer,
            "competitions": CompetitionCanonicalizer,
        }

    Raises:
        ConfigurationError: If neither a neo4j_client nor a seed_dir is provided,
            or if seed loading fails.
        CanonicalizationError: If alias data cannot be loaded from either source.
    """
    # Validate that at least one source is available
    if neo4j_client is None and not use_static_seeds:
        if seed_dir is not None:
            logger.warning(
                "neo4j_client is None and use_static_seeds=False — "
                "falling back to static seeds automatically",
                extra={"seed_dir": str(seed_dir)},
            )
            use_static_seeds = True
        else:
            raise ConfigurationError(
                "build_canonicalizer_registry requires either a neo4j_client "
                "or use_static_seeds=True with a seed_dir",
            )

    if use_static_seeds and seed_dir is None:
        raise ConfigurationError(
            "use_static_seeds=True requires seed_dir to be provided",
        )

    # Attempt graph load, fall back to seeds on failure
    if not use_static_seeds and neo4j_client is not None:
        try:
            return _build_from_graph(neo4j_client)
        except Exception as exc:  # noqa: BLE001
            if seed_dir is not None:
                logger.warning(
                    "Failed to load canonicalizer registry from graph — "
                    "falling back to static seeds",
                    extra={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "seed_dir": str(seed_dir),
                    },
                )
                return _build_from_seeds(seed_dir)
            raise CanonicalizationError(
                "Failed to load canonicalizer registry from graph and no seed_dir provided",
                error_type=type(exc).__name__,
                error=str(exc),
            ) from exc

    return _build_from_seeds(seed_dir)  # type: ignore[arg-type]



# Internal builders



def _build_from_graph(neo4j_client: Neo4jClient) -> dict[str, BaseCanonicalizer]:
    """
    Build all six canonicalizers from Neo4j graph data.

    Imported here at call time to avoid circular imports at module level,
    since domain canonicalizer modules import from base.py.
    """
    from app.canonicalization.competitions import build_competition_canonicalizer
    from app.canonicalization.partners import build_partner_canonicalizer
    from app.canonicalization.tags import build_tag_canonicalizer
    from app.canonicalization.teams import build_team_canonicalizer
    from app.canonicalization.topics import build_topic_canonicalizer
    from app.canonicalization.vouchers import build_voucher_canonicalizer

    loader = CanonicalRegistryLoader(neo4j_client)

    team_aliases = loader.load_team_aliases()
    topic_aliases = loader.load_topic_aliases()
    tag_aliases = loader.load_tag_aliases()
    partner_aliases = loader.load_partner_aliases()
    voucher_aliases = loader.load_voucher_aliases()
    competition_aliases = loader.load_competition_aliases()
    competition_labels = loader.load_competition_node_labels()

    builders = {
        "teams": lambda: build_team_canonicalizer(team_aliases),
        "topics": lambda: build_topic_canonicalizer(topic_aliases),
        "partners": lambda: build_partner_canonicalizer(partner_aliases),
        "vouchers": lambda: build_voucher_canonicalizer(voucher_aliases),
        "tags": lambda: build_tag_canonicalizer(tag_aliases),
        "competitions": lambda: build_competition_canonicalizer(
            competition_aliases,
            node_labels=competition_labels,
        ),
    }

    registry: dict[str, BaseCanonicalizer] = {}
    for domain, build_fn in builders.items():
        try:
            registry[domain] = build_fn()
        except Exception as exc:
            logger.warning(
                "Failed to build %s canonicalizer — domain will be skipped",
                domain,
                extra={"error": str(exc)},
            )

    logger.info(
        "Canonicalizer registry built from graph",
        extra={
            domain: len(canon.get_all_canonical_ids())
            for domain, canon in registry.items()
        },
    )
    return registry


def _build_from_seeds(seed_dir: Path) -> dict[str, BaseCanonicalizer]:
    """
    Build all six canonicalizers from static YAML seed files.
    """
    from app.canonicalization.competitions import build_competition_canonicalizer
    from app.canonicalization.partners import build_partner_canonicalizer
    from app.canonicalization.tags import build_tag_canonicalizer
    from app.canonicalization.teams import build_team_canonicalizer
    from app.canonicalization.topics import build_topic_canonicalizer
    from app.canonicalization.vouchers import build_voucher_canonicalizer

    seed_loader = StaticSeedLoader(seed_dir)

    team_aliases = seed_loader.load("teams")
    topic_aliases = seed_loader.load("topics")
    tag_aliases = seed_loader.load("tags")
    partner_aliases = seed_loader.load("partners")
    voucher_aliases = seed_loader.load("vouchers")
    competition_aliases = seed_loader.load("competitions")
    competition_labels = seed_loader.load_competition_node_labels()

    registry = {
        "teams": build_team_canonicalizer(team_aliases),
        "topics": build_topic_canonicalizer(topic_aliases),
        "partners": build_partner_canonicalizer(partner_aliases),
        "vouchers": build_voucher_canonicalizer(voucher_aliases),
        "tags": build_tag_canonicalizer(tag_aliases),
        "competitions": build_competition_canonicalizer(
            competition_aliases,
            node_labels=competition_labels,
        ),
    }

    logger.info(
        "Canonicalizer registry built from static seeds",
        extra={
            domain: len(canon.get_all_canonical_ids())
            for domain, canon in registry.items()
        },
    )
    return registry



# Internal helpers



def _require_str(row: dict[str, Any], key: str) -> str:
    """
    Extract a string value from a graph record row.

    Returns empty string if the value is None or not a string.
    """
    val = row.get(key)
    if val is None:
        return ""
    return str(val).strip()


def _append_if_present(aliases: list[str], value: Any) -> None:
    """
    Append a string value to the aliases list if it is non-null and non-empty.
    """
    if value is None:
        return
    text = str(value).strip()
    if text:
        aliases.append(text)