"""
Shared base classes and utilities for entity canonicalization.

This module provides the foundation that every domain canonicalizer builds on:

- CanonicalForm: the typed result of a successful alias resolution
- AliasMap: the bidirectional lookup structure that maps raw aliases to
  canonical IDs
- BaseCanonicalizer: the abstract base class all domain canonicalizers inherit
- normalize_alias: the single normalization function used at both registration
  and lookup time, ensuring consistency across all canonicalizers

Design rules:
- normalize_alias() must be called on every alias at both registration time
  (inside AliasMap.register) and at lookup time (inside AliasMap.resolve).
  This guarantees that lookup behaviour is identical regardless of how the
  alias was registered.
- No canonicalizer may query Neo4j directly. Graph queries belong in
  registry_loader.py. Domain canonicalizers receive pre-built AliasMap objects.
- assert_resolvable() is the strict resolution path. resolve() is the soft
  path. Transformers that require a canonical form must use assert_resolvable().
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

from app.core.exceptions import CanonicalizationError
from app.core.time import format_iso_timestamp, utc_now



# Normalization


# Matches one or more whitespace characters (including unicode whitespace).
_WHITESPACE_RE: re.Pattern[str] = re.compile(r"\s+")

# Matches one or more leading/trailing punctuation characters.
# Unicode category P = punctuation, S = symbols.
_LEADING_PUNCT_RE: re.Pattern[str] = re.compile(r"^[\W_]+", re.UNICODE)
_TRAILING_PUNCT_RE: re.Pattern[str] = re.compile(r"[\W_]+$", re.UNICODE)


def normalize_alias(value: str) -> str:
    """
    Normalize a raw alias string for consistent lookup.

    This function is the single normalization path for all canonicalizers.
    It must be called on every alias at registration time and at lookup time.

    Normalization rules (applied in order):
    1. Unicode NFC normalization — decomposed characters (e.g. e + combining
       accent) are composed into their canonical precomposed form.
    2. Strip outer whitespace.
    3. Lowercase.
    4. Collapse internal whitespace runs (spaces, tabs, newlines) to a single
       ASCII space.
    5. Strip leading and trailing punctuation and symbol characters.

    Args:
        value: Raw alias string to normalize.

    Returns:
        Normalized alias string.

    Raises:
        CanonicalizationError: If the value is empty after normalization,
            indicating the input was whitespace or punctuation only.

    Examples:
        >>> normalize_alias("  Manchester City  ")
        'manchester city'
        >>> normalize_alias("PREMIER-LEAGUE")
        'premier-league'
        >>> normalize_alias("  !!Nike UK!!  ")
        'nike uk'
        >>> normalize_alias("café")
        'café'
        >>> normalize_alias("naïve")
        'naïve'
    """
    if not isinstance(value, str):
        raise CanonicalizationError(
            "normalize_alias requires a string input",
            received_type=type(value).__name__,
        )

    # Step 1 — NFC normalization
    normalized = unicodedata.normalize("NFC", value)

    # Step 2 — strip outer whitespace
    normalized = normalized.strip()

    # Step 3 — lowercase
    normalized = normalized.lower()

    # Step 4 — collapse internal whitespace
    normalized = _WHITESPACE_RE.sub(" ", normalized)

    # Step 5 — strip leading/trailing punctuation and symbols
    # We strip characters whose Unicode category starts with P (punctuation)
    # or S (symbol) but preserve hyphens, underscores, and letters/digits
    # that are part of legitimate alias text.
    normalized = _strip_outer_punctuation(normalized)

    if not normalized:
        raise CanonicalizationError(
            "Alias is empty after normalization",
            raw_value=value,
        )

    return normalized


def _strip_outer_punctuation(value: str) -> str:
    """
    Strip leading and trailing characters whose Unicode category is
    punctuation (P*) or symbol (S*), but not hyphens or letters/digits.

    A hyphen surrounded by alphanumerics (e.g. "premier-league") is preserved.
    A leading or trailing hyphen or exclamation mark is stripped.
    """
    chars = list(value)

    # Strip from left
    while chars:
        cat = unicodedata.category(chars[0])
        if cat.startswith(("P", "S")) and chars[0] not in ("-", "_"):
            chars.pop(0)
        else:
            break

    # Strip from right
    while chars:
        cat = unicodedata.category(chars[-1])
        if cat.startswith(("P", "S")) and chars[-1] not in ("-", "_"):
            chars.pop()
        else:
            break

    return "".join(chars).strip()



# CanonicalForm



@dataclass(frozen=True)
class CanonicalForm:
    """
    The typed result of a successful alias resolution.

    Attributes:
        canonical_id:    Stable graph node identifier for this entity.
        canonical_name:  Normalized display name for this entity.
        aliases:         All known aliases that resolve to this canonical entry.
        source:          Name of the canonicalizer class that resolved this.
        resolved_at:     ISO UTC timestamp of the resolution.
    """

    canonical_id: str
    canonical_name: str
    aliases: frozenset[str]
    source: str
    resolved_at: str

    def __post_init__(self) -> None:
        if not self.canonical_id or not self.canonical_id.strip():
            raise CanonicalizationError(
                "CanonicalForm.canonical_id cannot be empty",
                field="canonical_id",
            )
        if not self.canonical_name or not self.canonical_name.strip():
            raise CanonicalizationError(
                "CanonicalForm.canonical_name cannot be empty",
                field="canonical_name",
            )
        if not self.source or not self.source.strip():
            raise CanonicalizationError(
                "CanonicalForm.source cannot be empty",
                field="source",
            )

    def matches_alias(self, raw_value: str) -> bool:
        """
        Return True if the given raw value normalizes to a known alias.

        Args:
            raw_value: Raw string to check.

        Returns:
            True if the normalized value is in this form's alias set.
        """
        try:
            return normalize_alias(raw_value) in self.aliases
        except CanonicalizationError:
            return False

    def alias_count(self) -> int:
        """Return the number of registered aliases for this canonical form."""
        return len(self.aliases)



# AliasMap



class AliasMap:
    """
    Bidirectional lookup map from normalized aliases to canonical IDs.

    AliasMap is the core data structure for every domain canonicalizer. It
    stores:
    - a forward map: normalized_alias → canonical_id
    - a reverse map: canonical_id → CanonicalForm

    All aliases are normalized via normalize_alias() at registration time.
    All lookups normalize the input before querying, so raw and pre-normalized
    values are handled identically.

    Usage:
        alias_map = AliasMap()
        alias_map.register("team:13", "Manchester City", ["Man City", "MCFC", "13"])
        form = alias_map.resolve("man city")   # returns CanonicalForm
        form = alias_map.resolve("mcfc")       # same CanonicalForm
        form = alias_map.resolve("Unknown")    # returns None
    """

    def __init__(self, source_name: str = "AliasMap") -> None:
        """
        Initialise an empty AliasMap.

        Args:
            source_name: Name used as the `source` field on resolved
                CanonicalForm instances. Typically the canonicalizer class name.
        """
        self._source_name = source_name

        # normalized_alias -> canonical_id
        self._forward: dict[str, str] = {}

        # canonical_id -> CanonicalForm
        self._reverse: dict[str, CanonicalForm] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        canonical_id: str,
        canonical_name: str,
        aliases: list[str],
    ) -> None:
        """
        Register a canonical entry and its aliases.

        All alias strings are normalized before storage. The canonical_name
        is also registered as an alias automatically.

        If the same canonical_id is registered more than once, the new aliases
        are merged into the existing entry. This allows incremental registration
        from multiple sources.

        Args:
            canonical_id:   Stable graph node identifier.
            canonical_name: Normalized display name.
            aliases:        List of raw alias strings (name variants, codes, IDs).

        Raises:
            CanonicalizationError: If canonical_id or canonical_name is empty,
                or if an alias already maps to a different canonical_id.
        """
        if not canonical_id or not canonical_id.strip():
            raise CanonicalizationError(
                "AliasMap.register: canonical_id cannot be empty",
                field="canonical_id",
            )
        if not canonical_name or not canonical_name.strip():
            raise CanonicalizationError(
                "AliasMap.register: canonical_name cannot be empty",
                field="canonical_name",
                canonical_id=canonical_id,
            )

        # Build the full alias set: provided aliases + canonical_name itself
        all_raw_aliases = list(aliases) + [canonical_name]
        normalized_aliases: set[str] = set()

        for raw in all_raw_aliases:
            if not raw or not str(raw).strip():
                continue
            try:
                norm = normalize_alias(str(raw))
            except CanonicalizationError:
                # Skip aliases that normalize to nothing
                continue

            # Collision check: same alias pointing to a different canonical_id
            existing_id = self._forward.get(norm)
            if existing_id is not None and existing_id != canonical_id:
                raise CanonicalizationError(
                    "Alias collision: normalized alias already maps to a different canonical ID",
                    normalized_alias=norm,
                    existing_canonical_id=existing_id,
                    incoming_canonical_id=canonical_id,
                )

            normalized_aliases.add(norm)
            self._forward[norm] = canonical_id

        # Merge with existing entry if canonical_id already registered
        if canonical_id in self._reverse:
            existing = self._reverse[canonical_id]
            merged_aliases = existing.aliases | frozenset(normalized_aliases)
            merged_form = CanonicalForm(
                canonical_id=canonical_id,
                canonical_name=existing.canonical_name,
                aliases=merged_aliases,
                source=self._source_name,
                resolved_at=existing.resolved_at,
            )
            self._reverse[canonical_id] = merged_form
        else:
            form = CanonicalForm(
                canonical_id=canonical_id,
                canonical_name=canonical_name,
                aliases=frozenset(normalized_aliases),
                source=self._source_name,
                resolved_at=format_iso_timestamp(utc_now()),
            )
            self._reverse[canonical_id] = form

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw alias to its CanonicalForm.

        The input is normalized before lookup. Returns None if no mapping
        exists for the normalized alias.

        Args:
            raw_value: Raw alias string.

        Returns:
            CanonicalForm if found, None otherwise.
        """
        try:
            normalized = normalize_alias(raw_value)
        except CanonicalizationError:
            return None

        canonical_id = self._forward.get(normalized)
        if canonical_id is None:
            return None

        return self._reverse.get(canonical_id)

    def resolve_by_id(self, canonical_id: str) -> CanonicalForm | None:
        """
        Resolve directly by canonical ID, bypassing alias lookup.

        Useful when a transformer already holds a canonical_id and needs
        the full CanonicalForm for display name or alias inspection.

        Args:
            canonical_id: Exact canonical ID string.

        Returns:
            CanonicalForm if registered, None otherwise.
        """
        return self._reverse.get(canonical_id)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered canonical entry.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if a canonical mapping exists, False otherwise.
        """
        return self.resolve(raw_value) is not None

    def all_canonical_ids(self) -> list[str]:
        """
        Return all registered canonical IDs in registration order.

        Returns:
            List of canonical ID strings.
        """
        return list(self._reverse.keys())

    def all_forms(self) -> list[CanonicalForm]:
        """
        Return all registered CanonicalForm instances.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return list(self._reverse.values())

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Return the number of registered canonical entries."""
        return len(self._reverse)

    def alias_count(self) -> int:
        """Return the total number of registered normalized aliases."""
        return len(self._forward)

    def is_empty(self) -> bool:
        """Return True if no canonical entries have been registered."""
        return len(self._reverse) == 0

    def __contains__(self, raw_value: str) -> bool:
        """Support `alias in alias_map` syntax."""
        return self.is_known(raw_value)

    def __iter__(self) -> Iterator[CanonicalForm]:
        """Iterate over all registered CanonicalForm instances."""
        return iter(self._reverse.values())

    def __len__(self) -> int:
        """Return the number of registered canonical entries."""
        return self.size()

    def __repr__(self) -> str:
        return (
            f"AliasMap(source={self._source_name!r}, "
            f"entries={self.size()}, aliases={self.alias_count()})"
        )



# BaseCanonicalizer



class BaseCanonicalizer(ABC):
    """
    Abstract base class for all domain canonicalizers.

    Every domain canonicalizer (TeamCanonicalizer, TopicCanonicalizer, etc.)
    inherits from this class and implements the three abstract methods.

    The concrete assert_resolvable() method is inherited and must not be
    overridden — it provides the strict resolution path used by transformers
    that require a canonical form and must fail hard on unknown input.

    Subclasses receive a pre-built AliasMap from the registry loader and use
    it to implement resolve(), is_known(), and get_all_canonical_ids().
    """

    @abstractmethod
    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw alias to its canonical form.

        Args:
            raw_value: Raw alias string (name, ID, code, slug, etc.).

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """

    @abstractmethod
    def is_known(self, raw_value: str) -> bool:
        """
        Return True if raw_value maps to any known canonical entry.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable, False otherwise.
        """

    @abstractmethod
    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical IDs registered in this canonicalizer.

        Returns:
            List of canonical ID strings.
        """

    def assert_resolvable(self, raw_value: str) -> CanonicalForm:
        """
        Resolve or raise CanonicalizationError if not resolvable.

        This is the strict resolution path. Transformers that must have a
        canonical form — and should fail rather than silently skip — must
        call this method instead of resolve().

        Args:
            raw_value: Raw alias string to resolve.

        Returns:
            CanonicalForm for the resolved alias.

        Raises:
            CanonicalizationError: If no canonical mapping exists for the value.
        """
        result = self.resolve(raw_value)
        if result is None:
            raise CanonicalizationError(
                "Could not resolve value to canonical form",
                raw_value=raw_value,
                canonicalizer=type(self).__name__,
            )
        return result

    def resolve_many(self, raw_values: list[str]) -> dict[str, CanonicalForm | None]:
        """
        Resolve a list of raw values, returning a mapping of input to result.

        Values that do not resolve return None in the output dict. No exception
        is raised for unresolvable values in this method.

        Args:
            raw_values: List of raw alias strings.

        Returns:
            Dict mapping each input string to its CanonicalForm or None.
        """
        return {value: self.resolve(value) for value in raw_values}

    def assert_resolvable_many(self, raw_values: list[str]) -> dict[str, CanonicalForm]:
        """
        Resolve a list of raw values, raising on the first unresolvable input.

        Args:
            raw_values: List of raw alias strings.

        Returns:
            Dict mapping each input string to its CanonicalForm.

        Raises:
            CanonicalizationError: On the first value that cannot be resolved.
        """
        results: dict[str, CanonicalForm] = {}
        for value in raw_values:
            results[value] = self.assert_resolvable(value)
        return results

    def filter_known(self, raw_values: list[str]) -> list[str]:
        """
        Return only the values from the input list that are resolvable.

        Args:
            raw_values: List of raw alias strings.

        Returns:
            Filtered list containing only resolvable values.
        """
        return [v for v in raw_values if self.is_known(v)]

    def __repr__(self) -> str:
        count = len(self.get_all_canonical_ids())
        return f"{type(self).__name__}(entries={count})"