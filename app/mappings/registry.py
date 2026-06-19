"""
Central aggregation point for the mapping layer.

This module ties together all static mapping declarations into a single
runtime registry that transformers, validators, and later pipeline code can
query uniformly.

It aggregates:

- source artifact routing declarations
- endpoint resolution rules
- merge key strategies
- property ownership rules
- node mapping specs
- relationship mapping specs

Design rules:
- This file is the single executable source-of-truth for source-to-graph
  mapping access.
- Higher layers should import MappingRegistry rather than querying individual
  mapping modules directly whenever possible.
- build_mapping_registry() must validate the full mapping layer before
  returning a registry instance.
- This module does not define mapping behavior itself; it aggregates and
  validates behavior declared elsewhere.

Primary outputs:
- MappingRegistry: central lookup interface over all mapping specs
- build_mapping_registry(): validated registry factory

This module allows future transformers to answer, from one place:

- what a source emits
- how its endpoints resolve
- which merge key it uses
- which source owns which property
- what node/relationship mapping spec applies
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import SchemaMappingError
from app.mappings.base import (
    NodeMappingSpec,
    RelationshipMappingSpec,
    validate_node_mapping_spec,
    validate_relationship_mapping_spec,
)
from app.mappings.endpoint_resolution import (
    DynamicLabelResolution,
    ENDPOINT_SPECS,
    DYNAMIC_LABEL_RESOLUTIONS,
    get_dynamic_label_resolution,
    get_endpoint_spec,
    validate_endpoint_specs,
)
from app.mappings.merge_keys import (
    MERGE_KEY_SPECS,
    MergeKeySpec,
    get_merge_key_spec,
    validate_merge_key_specs,
)
from app.mappings.property_ownership import (
    PROPERTY_OWNERSHIP_SPECS,
    PropertyOwnershipSpec,
    get_property_owner,
    validate_property_ownership_specs,
)
from app.mappings.source_to_graph import (
    SOURCE_ARTIFACT_DECLARATIONS,
    SourceArtifactDeclaration,
    get_source_artifacts,
    validate_source_artifact_declarations,
)


NODE_MAPPING_SPECS: tuple[NodeMappingSpec, ...] = ()
RELATIONSHIP_MAPPING_SPECS: tuple[RelationshipMappingSpec, ...] = ()

_NODE_MAPPING_INDEX: dict[tuple[str, str], NodeMappingSpec] = {
    (spec.source_name, spec.target_label): spec for spec in NODE_MAPPING_SPECS
}
_RELATIONSHIP_MAPPING_INDEX: dict[tuple[str, str], RelationshipMappingSpec] = {
    (spec.source_name, spec.rel_type): spec for spec in RELATIONSHIP_MAPPING_SPECS
}


@dataclass(frozen=True)
class MappingRegistry:
    """
    Central access point for all mapping specs.

    Provides lookup methods for:
    - source artifact declarations
    - node mapping specs
    - relationship mapping specs
    - endpoint specs
    - dynamic label rules
    - merge key specs
    - property ownership rules
    """

    source_artifact_declarations: tuple[SourceArtifactDeclaration, ...]
    node_mapping_specs: tuple[NodeMappingSpec, ...]
    relationship_mapping_specs: tuple[RelationshipMappingSpec, ...]
    merge_key_specs: tuple[MergeKeySpec, ...]
    property_ownership_specs: tuple[PropertyOwnershipSpec, ...]
    dynamic_label_resolutions: dict[tuple[str, str, str], DynamicLabelResolution]

    def get_source_artifacts(self, source_name: str) -> list[SourceArtifactDeclaration]:
        """
        Return all artifact declarations for a source.
        """
        return get_source_artifacts(source_name)

    def get_node_mapping(self, source_name: str, target_label: str) -> NodeMappingSpec | None:
        """
        Return the node mapping spec for a source/target label pair, if one is registered.
        """
        return _NODE_MAPPING_INDEX.get((source_name, target_label))

    def get_relationship_mapping(
        self,
        source_name: str,
        rel_type: str,
    ) -> RelationshipMappingSpec | None:
        """
        Return the relationship mapping spec for a source/relationship pair, if registered.
        """
        return _RELATIONSHIP_MAPPING_INDEX.get((source_name, rel_type))

    def get_endpoint_spec(self, rel_type: str, endpoint_name: str, source_name: str):
        """
        Return the endpoint spec for a relationship/source/endpoint triple.
        """
        return get_endpoint_spec(rel_type, endpoint_name, source_name)

    def get_dynamic_label_resolution(
        self,
        rel_type: str,
        endpoint_name: str,
        source_name: str,
    ) -> DynamicLabelResolution | None:
        """
        Return the dynamic label resolution rule for a relationship endpoint, if any.
        """
        return get_dynamic_label_resolution(rel_type, endpoint_name, source_name)

    def get_merge_key(self, source_name: str, target_name: str) -> MergeKeySpec | None:
        """
        Return the merge-key spec for a source/target pair, if registered.
        """
        try:
            return get_merge_key_spec(source_name, target_name)
        except KeyError:
            return None

    def get_property_owner(
        self,
        target_label_or_rel: str,
        property_name: str,
    ) -> PropertyOwnershipSpec | None:
        """
        Return the highest-priority property ownership rule for a target/property pair.
        """
        return get_property_owner(target_label_or_rel, property_name)

    def validate_all(self) -> list[str]:
        """
        Validate the full mapping layer.

        Aggregates:
        - source artifact declaration validation
        - endpoint resolution validation
        - merge-key validation
        - property ownership validation
        - every node mapping spec validation
        - every relationship mapping spec validation

        Returns:
            Flat list of validation errors. Empty list means valid.
        """
        errors: list[str] = []

        errors.extend(validate_source_artifact_declarations())
        errors.extend(validate_endpoint_specs())
        errors.extend(validate_merge_key_specs())
        errors.extend(validate_property_ownership_specs())

        for idx, spec in enumerate(self.node_mapping_specs):
            node_errors = validate_node_mapping_spec(spec)
            errors.extend(
                f"NODE_MAPPING_SPECS[{idx}] (source={spec.source_name!r}, target={spec.target_label!r}): {error}"
                for error in node_errors
            )

        for idx, spec in enumerate(self.relationship_mapping_specs):
            rel_errors = validate_relationship_mapping_spec(spec)
            errors.extend(
                f"RELATIONSHIP_MAPPING_SPECS[{idx}] (source={spec.source_name!r}, rel_type={spec.rel_type!r}): {error}"
                for error in rel_errors
            )

        errors.extend(self._validate_cross_module_consistency())

        return errors

    def _validate_cross_module_consistency(self) -> list[str]:
        """
        Validate consistency across mapping submodules.

        Checks:
        - graph-emitting source declarations have merge-key specs for each target
        - relationship-emitting source declarations have endpoint specs
        - dynamic label rules refer to declared relationship sources
        - node/relationship mapping specs, when present, correspond to declared sources
        """
        errors: list[str] = []

        for declaration in self.source_artifact_declarations:
            if not declaration.emits_records:
                continue

            merge_key = self.get_merge_key(
                declaration.source_name,
                declaration.target_label_or_rel,
            )
            if merge_key is None:
                errors.append(
                    "Missing merge-key spec for graph-emitting declaration: "
                    f"source={declaration.source_name!r}, "
                    f"target={declaration.target_label_or_rel!r}"
                )

            if declaration.artifact_kind == "relationship":
                start_key = (
                    declaration.target_label_or_rel,
                    "start",
                    declaration.source_name,
                )
                end_key = (
                    declaration.target_label_or_rel,
                    "end",
                    declaration.source_name,
                )

                if start_key not in ENDPOINT_SPECS:
                    errors.append(
                        "Missing start endpoint spec for relationship declaration: "
                        f"rel_type={declaration.target_label_or_rel!r}, "
                        f"source={declaration.source_name!r}"
                    )

                if end_key not in ENDPOINT_SPECS:
                    errors.append(
                        "Missing end endpoint spec for relationship declaration: "
                        f"rel_type={declaration.target_label_or_rel!r}, "
                        f"source={declaration.source_name!r}"
                    )

        for (source_name, target_label), spec in _NODE_MAPPING_INDEX.items():
            matching_declarations = [
                decl
                for decl in self.source_artifact_declarations
                if decl.source_name == source_name
                and decl.target_label_or_rel == target_label
                and decl.emits_records
            ]
            if not matching_declarations:
                errors.append(
                    "Node mapping spec has no corresponding source artifact declaration: "
                    f"source={source_name!r}, target_label={target_label!r}"
                )

        for (source_name, rel_type), spec in _RELATIONSHIP_MAPPING_INDEX.items():
            matching_declarations = [
                decl
                for decl in self.source_artifact_declarations
                if decl.source_name == source_name
                and decl.target_label_or_rel == rel_type
                and decl.emits_records
            ]
            if not matching_declarations:
                errors.append(
                    "Relationship mapping spec has no corresponding source artifact declaration: "
                    f"source={source_name!r}, rel_type={rel_type!r}"
                )

        for (rel_type, endpoint_name, source_name), dynamic_rule in self.dynamic_label_resolutions.items():
            matching_declarations = [
                decl
                for decl in self.source_artifact_declarations
                if decl.source_name == source_name
                and decl.target_label_or_rel == rel_type
                and decl.emits_records
            ]
            if not matching_declarations:
                errors.append(
                    "Dynamic label resolution has no corresponding relationship declaration: "
                    f"rel_type={rel_type!r}, endpoint={endpoint_name!r}, source={source_name!r}"
                )

        return errors


def build_mapping_registry() -> MappingRegistry:
    """
    Build and validate the full mapping registry.

    Returns:
        Validated MappingRegistry.

    Raises:
        SchemaMappingError: If any mapping spec is inconsistent.
    """
    registry = MappingRegistry(
        source_artifact_declarations=SOURCE_ARTIFACT_DECLARATIONS,
        node_mapping_specs=NODE_MAPPING_SPECS,
        relationship_mapping_specs=RELATIONSHIP_MAPPING_SPECS,
        merge_key_specs=MERGE_KEY_SPECS,
        property_ownership_specs=PROPERTY_OWNERSHIP_SPECS,
        dynamic_label_resolutions=DYNAMIC_LABEL_RESOLUTIONS,
    )

    errors = registry.validate_all()
    if errors:
        raise SchemaMappingError(
            "Mapping registry validation failed",
            errors=errors,
        )

    return registry