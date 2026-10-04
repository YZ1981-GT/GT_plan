"""
PBT P4 (private docs never leak) + 单元用例。

Validates: Requirements 10.4

2026-09-29（spec knowledge-base-retrieval-and-authz-closure Req 3.9）：原被测对象
``KnowledgeIndexService._user_can_access_doc`` 已删除（它对 project_group 恒返回 True，
且与 ``KnowledgeAccessPolicy`` 是两套判定）。本文件原有的五条性质原样保留，改为针对
**单一判定面** ``KnowledgeAccessPolicy.can_retrieve``；全组合等价见
``test_knowledge_retrieval_visibility_pbt.py``。
"""

from __future__ import annotations

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.knowledge_models import KnowledgeAccessLevel
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
    KnowledgeResource,
    KnowledgeRetrievalMode,
)

_PROJECT = uuid.uuid4()


def _res(level, owner=None, pids=()):
    return KnowledgeResource(access_level=level, project_ids=frozenset(pids), created_by=owner)


def _can(user_id, doc, folder, mode=KnowledgeRetrievalMode.browse):
    subject = KnowledgeAccessSubject(user_id=user_id, project_ids=frozenset())
    project = _PROJECT if mode is KnowledgeRetrievalMode.project else None
    return KnowledgeAccessPolicy.can_retrieve(mode, subject, project, doc, folder)


# ─── PBT P4: Private docs never leak ─────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(
    querying_user_id=st.uuids(),
    doc_owner_id=st.uuids(),
    mode=st.sampled_from(list(KnowledgeRetrievalMode)),
)
def test_private_docs_never_leak(
    querying_user_id: uuid.UUID, doc_owner_id: uuid.UUID, mode: KnowledgeRetrievalMode
):
    """
    **Validates: Requirements 10.4**

    PBT P4: 生效 access_level=private 且查询者 ≠ 创建者 ⇒ 任何检索模式下都不可见。
    """
    can_access = _can(
        querying_user_id, _res(KnowledgeAccessLevel.private, doc_owner_id), _res(KnowledgeAccessLevel.public), mode
    )
    if querying_user_id != doc_owner_id:
        assert can_access is False, (
            f"Private doc leaked! user={querying_user_id} != owner={doc_owner_id}"
        )
    else:
        assert can_access is True


# ─── Unit tests for permission logic ─────────────────────────────────────────


def test_public_doc_accessible_by_anyone():
    """Public docs are accessible by any authenticated user."""
    assert _can(uuid.uuid4(), _res(KnowledgeAccessLevel.public, uuid.uuid4()), None) is True


def test_private_doc_accessible_by_owner():
    """Private docs are accessible by owner（hypothesis 5 例几乎抽不到 owner==user，单独钉住）。"""
    owner_id = uuid.uuid4()
    for mode in KnowledgeRetrievalMode:
        assert _can(owner_id, _res(KnowledgeAccessLevel.private, owner_id), None, mode) is True


def test_private_doc_inaccessible_by_other():
    """Private docs are NOT accessible by non-owner."""
    assert _can(uuid.uuid4(), _res(KnowledgeAccessLevel.private, uuid.uuid4()), None) is False


def test_folder_level_private_inherited():
    """文档 access_level 为空时**完整继承**文件夹三元组（含文件夹的创建者）。"""
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    inherited_doc = _res(None, other_id)  # 文档自身创建者不参与继承判定
    private_folder = _res(KnowledgeAccessLevel.private, owner_id)

    assert _can(owner_id, inherited_doc, private_folder) is True
    assert _can(other_id, inherited_doc, private_folder) is False
