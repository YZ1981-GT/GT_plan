"""
PBT P4 (private docs never leak) + integration test.

Validates: Requirements 10.4
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.knowledge_index_service import KnowledgeIndexService


# ─── PBT P4: Private docs never leak ─────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    querying_user_id=st.uuids(),
    doc_owner_id=st.uuids(),
)
def test_private_docs_never_leak(querying_user_id: uuid.UUID, doc_owner_id: uuid.UUID):
    """
    **Validates: Requirements 10.4**

    PBT P4: For all search results, if a document has effective
    access_level="private" AND the querying user.id != document.created_by,
    THEN that document shall NOT appear in results.
    """
    # Simulate: private doc owned by doc_owner_id, queried by querying_user_id
    can_access = KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(querying_user_id),
        created_by=doc_owner_id,
        doc_access_level="private",
        doc_project_ids=None,
        folder_access_level=None,
        folder_project_ids=None,
    )

    if querying_user_id != doc_owner_id:
        # MUST NOT have access
        assert can_access is False, (
            f"Private doc leaked! user={querying_user_id} != owner={doc_owner_id} "
            f"but got access=True"
        )
    else:
        # Owner CAN access their own private doc
        assert can_access is True


# ─── Unit tests for permission logic ─────────────────────────────────────────


def test_public_doc_accessible_by_anyone():
    """Public docs are accessible by any authenticated user."""
    result = KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(uuid.uuid4()),
        created_by=uuid.uuid4(),
        doc_access_level="public",
        doc_project_ids=None,
        folder_access_level=None,
        folder_project_ids=None,
    )
    assert result is True


def test_private_doc_accessible_by_owner():
    """Private docs are accessible by owner."""
    owner_id = uuid.uuid4()
    result = KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(owner_id),
        created_by=owner_id,
        doc_access_level="private",
        doc_project_ids=None,
        folder_access_level=None,
        folder_project_ids=None,
    )
    assert result is True


def test_private_doc_inaccessible_by_other():
    """Private docs are NOT accessible by non-owner."""
    result = KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(uuid.uuid4()),
        created_by=uuid.uuid4(),
        doc_access_level="private",
        doc_project_ids=None,
        folder_access_level=None,
        folder_project_ids=None,
    )
    assert result is False


def test_folder_level_private_inherited():
    """When doc has no access_level, folder-level private is inherited."""
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()

    # Owner can access via folder inheritance
    assert KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(owner_id),
        created_by=owner_id,
        doc_access_level=None,
        doc_project_ids=None,
        folder_access_level="private",
        folder_project_ids=None,
    ) is True

    # Non-owner cannot
    assert KnowledgeIndexService._user_can_access_doc(
        user_id_str=str(other_id),
        created_by=owner_id,
        doc_access_level=None,
        doc_project_ids=None,
        folder_access_level="private",
        folder_project_ids=None,
    ) is False
