from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from infrahub.core.constants import SYSTEM_USER_ID
from infrahub.core.query.relationship import (
    RelationshipBatchCreateData,
    RelationshipBatchCreateQuery,
    RelationshipBatchCreateResult,
)

if TYPE_CHECKING:
    from infrahub.core.branch import Branch
    from infrahub.core.relationship.model import Relationship
    from infrahub.core.timestamp import Timestamp
    from infrahub.database import InfrahubDatabase


class RelationshipBatchCreator:
    """Creates multiple relationships in batched database queries for efficiency."""

    DEFAULT_BATCH_SIZE = 100

    def __init__(self, db: InfrahubDatabase, branch: Branch, batch_size: int | None = None) -> None:
        self.db = db
        self.branch = branch
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE

    async def save(
        self,
        relationships: list[Relationship],
        at: Timestamp,
        user_id: str = SYSTEM_USER_ID,
    ) -> None:
        """Batch create the given relationships in the database.

        Relationships are processed in batches of `batch_size` to avoid
        overwhelming the database with large queries.

        Args:
            relationships: List of Relationship objects to create (must not have an id set)
            at: Timestamp for the creation
            user_id: User ID for audit trail
        """
        if not relationships:
            return

        # Process relationships in batches
        for i in range(0, len(relationships), self.batch_size):
            batch_rels = relationships[i : i + self.batch_size]
            await self._save_batch(batch_rels, at=at, user_id=user_id)

    async def _save_batch(
        self,
        relationships: list[Relationship],
        at: Timestamp,
        user_id: str,
    ) -> None:
        """Create a single batch of relationships."""
        # Build batch create data
        batch_data: list[RelationshipBatchCreateData] = []
        for rel in relationships:
            # Set metadata on the relationship
            rel._set_created_by(value=user_id)
            rel._set_created_at(value=at)
            rel._set_updated_by(value=user_id)
            rel._set_updated_at(value=at)

            batch_data.append(
                RelationshipBatchCreateData(
                    identifier=rel.get_peer_id(),
                    source_id=rel.node_id,
                    destination_id=rel.get_peer_id(),
                    name=rel.schema.get_identifier(),
                    branch_support=rel.schema.branch.value if rel.schema.branch else "",
                    is_protected=rel.is_protected,
                    direction=rel.schema.direction,
                    hierarchical=rel.schema.hierarchical,
                    source_prop_id=str(rel.source_id) if hasattr(rel, "source_id") and rel.source_id else None,
                    owner_prop_id=str(rel.owner_id) if hasattr(rel, "owner_id") and rel.owner_id else None,
                )
            )

        # Execute batch query
        batch_query = await RelationshipBatchCreateQuery.init(
            db=self.db,
            branch=self.branch,
            at=at,
            relationships=batch_data,
            user_id=user_id,
        )
        await batch_query.execute(db=self.db)

        # Map results back to relationships
        results_by_identifier: dict[str, RelationshipBatchCreateResult] = {
            result.identifier: result for result in batch_query.get_created_relationships()
        }
        for rel in relationships:
            if rel.peer_id in results_by_identifier:
                result = results_by_identifier[rel.peer_id]
                rel.id = UUID(result.rel_uuid)
                rel.db_id = result.element_id
