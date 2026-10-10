from backend.models.breakdown import (
    ComplianceBreakdown,
    FrameworkMetadata,
    FrameworkNode,
    RequirementNode,
    ResourceItem,
    SourceReference,
    TodoItem,
)
from backend.models.document import DocumentStructure


class BreakdownFinalizer:
    def build(
        self,
        profile: dict,
        structure: DocumentStructure,
        requirements: list[dict],
    ) -> ComplianceBreakdown:
        requirement_map = {}

        for requirement in requirements:
            node_id = requirement.get(
                "node_id"
            )

            requirement_map.setdefault(
                node_id,
                []
            ).append(requirement)

        hierarchy = [
            self._build_node(
                node=node,
                requirement_map=requirement_map,
            )
            for node in structure.nodes
        ]

        metadata = FrameworkMetadata(
            title=profile.get(
                "document_title",
                structure.metadata.filename,
            ),
            document_type=profile.get(
                "document_type",
                "Unknown",
            ),
            description=profile.get(
                "description",
                "",
            ),
            hierarchy_description=profile.get(
                "hierarchy_description",
                "",
            ),
        )

        return ComplianceBreakdown(
            metadata=metadata,
            hierarchy=hierarchy,
        )

    def _build_node(
        self,
        node,
        requirement_map,
    ) -> FrameworkNode:
        requirements = [
            self._build_requirement(
                requirement
            )
            for requirement in requirement_map.get(
                node.node_id,
                []
            )
        ]

        children = [
            self._build_node(
                child,
                requirement_map,
            )
            for child in node.children
        ]

        return FrameworkNode(
            node_id=node.node_id,
            title=node.title,
            node_type=node.node_type,
            level=node.level,
            page_start=node.page_start,
            page_end=node.page_end,
            source_description=node.source_text,
            requirements=requirements,
            children=children,
        )

    def _build_requirement(
        self,
        requirement: dict,
    ) -> RequirementNode:
        source_reference = SourceReference(
            page_start=requirement.get(
                "page_start"
            ),
            page_end=requirement.get(
                "page_end"
            ),
            section=requirement.get(
                "source_title"
            ),
            source_text=requirement.get(
                "source_text",
                "",
            ),
        )

        todo = TodoItem(
            name=requirement.get(
                "todo_name",
                "",
            ),
            description=requirement.get(
                "todo_description",
                "",
            ),
            status="AI_GENERATED",
        )

        policies = self._build_resources(
            requirement.get(
                "policies",
                []
            )
        )

        documents = self._build_resources(
            requirement.get(
                "documents",
                []
            )
        )

        evidence = self._build_resources(
            requirement.get(
                "evidence",
                []
            )
        )

        return RequirementNode(
            source_title=requirement.get(
                "source_title",
                "",
            ),
            source_reference=source_reference,
            todo=todo,
            policies=policies,
            documents=documents,
            evidence=evidence,
        )

    def _build_resources(
        self,
        resources,
    ) -> list[ResourceItem]:
        result = []

        if not isinstance(
            resources,
            list,
        ):
            return result

        for resource in resources:
            if isinstance(
                resource,
                str,
            ):
                result.append(
                    ResourceItem(
                        name=resource,
                        status="AI_GENERATED",
                        source_reference="",
                    )
                )
                continue

            if not isinstance(
                resource,
                dict,
            ):
                continue

            name = str(
                resource.get(
                    "name",
                    "",
                )
            ).strip()

            if not name:
                continue

            status = resource.get(
                "status",
                "AI_GENERATED",
            )

            if status not in {
                "SOURCE_DERIVED",
                "AI_GENERATED",
            }:
                status = "AI_GENERATED"

            result.append(
                ResourceItem(
                    name=name,
                    status=status,
                    source_reference=str(
                        resource.get(
                            "source_reference",
                            "",
                        )
                    ).strip(),
                )
            )

        return result