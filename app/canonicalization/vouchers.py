"""
Voucher canonicalizer for Project Pulse Knowledge Graph.

Resolves voucher aliases to stable canonical Voucher node IDs across all
sources that reference vouchers: dim_voucher_catalog and fct_voucher_purchases.

The key challenge in voucher canonicalization is that fct_voucher_purchases
carries a voucher_id that may differ from the voucher_key in the catalog. For
example, the catalog may use "NIKE_10_OFF" as the voucher_key while the
purchase table stores a numeric or UUID voucher_id. Both must resolve to the
same canonical Voucher node.

All three alias types — voucher_key, voucher_title, and purchase-side
voucher_id — are registered in the same AliasMap, so any of them resolve to
the same CanonicalForm via a single lookup path.

resolve_voucher_key() performs a direct lookup without title normalization
(catalog keys are stable identifiers, not display strings). However, they
still pass through normalize_alias() so that minor whitespace or casing
differences in the source are absorbed.

resolve_voucher_title() applies full normalize_alias() so that title variants
("10% Off Nike", "10 % Off  Nike") collapse to the same key.

resolve_purchase_voucher_id() is the cross-source bridge: it first attempts
a direct AliasMap lookup (covers the case where the purchase voucher_id was
registered as an alias), then falls through to a title match if needed.
"""

from __future__ import annotations

from app.canonicalization.base import AliasMap, BaseCanonicalizer, CanonicalForm, normalize_alias



# VoucherCanonicalizer



class VoucherCanonicalizer(BaseCanonicalizer):
    """
    Resolves voucher aliases to canonical Voucher node IDs.

    Alias types handled:
    - voucher_key (stable catalog key, e.g. "NIKE_10_OFF")
    - voucher_title (human-readable title, normalized)
    - voucher_id from fct_voucher_purchases (may differ from catalog key)
    - advertiser_name (brand name on the voucher, if registered)

    All alias types are stored in a single AliasMap so that any of them
    resolve to the same canonical entry via one lookup.
    """

    def __init__(self, alias_map: AliasMap) -> None:
        """
        Initialise with a pre-built AliasMap.

        Args:
            alias_map: AliasMap populated by build_voucher_canonicalizer().
        """
        self._alias_map = alias_map

    # ------------------------------------------------------------------
    # BaseCanonicalizer interface
    # ------------------------------------------------------------------

    def resolve(self, raw_value: str) -> CanonicalForm | None:
        """
        Resolve a raw voucher alias to its canonical form.

        The value is normalized via normalize_alias() before lookup,
        which handles casing, whitespace, and punctuation.

        Args:
            raw_value: Raw alias string — a key, title, or ID.

        Returns:
            CanonicalForm if a mapping exists, None otherwise.
        """
        return self._alias_map.resolve(raw_value)

    def is_known(self, raw_value: str) -> bool:
        """
        Return True if the raw value resolves to any registered voucher.

        Args:
            raw_value: Raw alias string.

        Returns:
            True if resolvable, False otherwise.
        """
        return self._alias_map.is_known(raw_value)

    def get_all_canonical_ids(self) -> list[str]:
        """
        Return all canonical Voucher node IDs registered in this canonicalizer.

        Returns:
            List of canonical ID strings in registration order.
        """
        return self._alias_map.all_canonical_ids()

    # ------------------------------------------------------------------
    # Domain-specific resolution methods
    # ------------------------------------------------------------------

    def resolve_voucher_key(self, key: str) -> CanonicalForm | None:
        """
        Resolve by voucher_key from the catalog.

        Voucher keys are stable identifiers (e.g. "NIKE_10_OFF"). They are
        passed through normalize_alias() to absorb minor casing or whitespace
        differences in source data, but are not subject to any additional
        transformation.

        Args:
            key: Raw voucher_key string from dim_voucher_catalog.

        Returns:
            CanonicalForm if the key is registered, None otherwise.
        """
        return self._alias_map.resolve(key)

    def resolve_voucher_title(self, title: str) -> CanonicalForm | None:
        """
        Resolve by voucher title with full normalization.

        Voucher titles are display strings ("10% Off Nike", "Free Delivery")
        that may vary in whitespace and punctuation across sources. Full
        normalize_alias() normalization is applied before lookup.

        Args:
            title: Raw voucher title string.

        Returns:
            CanonicalForm if the normalized title is registered, None otherwise.
        """
        return self._alias_map.resolve(title)

    def resolve_purchase_voucher_id(self, voucher_id: str) -> CanonicalForm | None:
        """
        Resolve a voucher_id from fct_voucher_purchases to a canonical Voucher.

        fct_voucher_purchases may carry a voucher_id that differs from the
        voucher_key in dim_voucher_catalog. This method uses a two-step
        resolution strategy:

        Step 1 — Direct alias lookup:
            The voucher_id is looked up as-is via AliasMap (with normalize_alias
            applied). This covers the case where the purchase voucher_id was
            explicitly registered as an alias during factory construction (e.g.
            when the loader includes the numeric purchase ID in the alias list
            alongside the voucher_key).

        Step 2 — Key fallback:
            If step 1 returns None, the voucher_id is tried as a voucher_key.
            In many catalogs the purchase voucher_id and the catalog voucher_key
            are the same string — this step handles that without requiring
            callers to know which field they're holding.

        Both steps normalize the input before lookup, so minor casing or
        whitespace differences are absorbed.

        Args:
            voucher_id: Raw voucher_id from fct_voucher_purchases.

        Returns:
            CanonicalForm if resolved by either strategy, None otherwise.
        """
        # Step 1 — direct alias lookup (covers explicitly registered purchase IDs)
        result = self._alias_map.resolve(voucher_id)
        if result is not None:
            return result

        # Step 2 — try as voucher_key (covers when purchase_id == catalog key)
        return self.resolve_voucher_key(voucher_id)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_all_forms(self) -> list[CanonicalForm]:
        """
        Return all registered CanonicalForm instances for all vouchers.

        Returns:
            List of CanonicalForm objects in registration order.
        """
        return self._alias_map.all_forms()

    def size(self) -> int:
        """Return the number of registered canonical vouchers."""
        return self._alias_map.size()



# Factory



def build_voucher_canonicalizer(
    alias_data: dict[str, list[str]],
) -> VoucherCanonicalizer:
    """
    Build a VoucherCanonicalizer from pre-loaded alias data.

    The alias_data dict is produced by CanonicalRegistryLoader.load_voucher_aliases()
    or StaticSeedLoader.load("vouchers"). It maps canonical_id to a flat list
    of raw alias strings covering all known alias types for each voucher:
    voucher_key, voucher_title, advertiser_name, and any purchase-side
    voucher_id values that differ from the catalog key.

    The loader is responsible for including purchase-side voucher_id values
    in the alias list when they are known to differ from the voucher_key.
    This canonicalizer registers everything it receives without distinguishing
    alias type — all aliases point to the same canonical entry.

    Args:
        alias_data: Dict mapping canonical_id to list of raw alias strings.

    Returns:
        Populated VoucherCanonicalizer.
    """
    alias_map = AliasMap(source_name="VoucherCanonicalizer")

    for canonical_id, aliases in alias_data.items():
        if not canonical_id or not canonical_id.strip():
            continue

        canonical_name = _pick_canonical_name(canonical_id, aliases)
        alias_map.register(canonical_id, canonical_name, aliases)

    return VoucherCanonicalizer(alias_map)



# Internal helpers



def _pick_canonical_name(canonical_id: str, aliases: list[str]) -> str:
    """
    Select the best display name from a voucher alias list.

    For vouchers the display name should be the human-readable title, not the
    catalog key or numeric ID. Preference order:

    1. First alias that contains a space (most likely the title, e.g.
       "10% Off Nike Footwear").
    2. First alias that looks like a catalog key (contains underscore or
       uppercase letters) — better than a bare numeric ID.
    3. First non-empty alias.
    4. canonical_id as last resort.

    Args:
        canonical_id: Canonical ID for fallback.
        aliases:      List of raw alias strings.

    Returns:
        Selected display name string.
    """
    first_non_empty: str | None = None
    first_key_like: str | None = None

    for alias in aliases:
        stripped = alias.strip()
        if not stripped:
            continue

        if first_non_empty is None:
            first_non_empty = stripped

        # Prefer aliases with spaces — most likely a human-readable title
        if " " in stripped:
            return stripped

        # Track catalog-key-like values (underscores or mixed case)
        if ("_" in stripped or stripped != stripped.lower()) and first_key_like is None:
            first_key_like = stripped

    return first_key_like or first_non_empty or canonical_id