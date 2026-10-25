"""检索可见性 / 管理权判定面：与独立参考模型**逐格**等价。

spec: knowledge-base-retrieval-and-authz-closure（Property P2 / P11，Requirement 3 / 6）

判定面是全平台知识检索（词法层、向量命中过滤、索引源、知识库页面搜索）的唯一真源，
任何一格判错都会变成「越权注入」或「用户上传的文档永远检索不到」。hypothesis
``max_examples=5`` 覆盖不了这张表，所以主守卫是**有限网格穷举**（约 3.6 万格，<1s），
PBT 只作为补充的随机抽样。参考模型刻意用与生产不同的写法（查表 + 显式分支），
避免「把同一个 bug 写两遍」。
"""
from __future__ import annotations

import itertools
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.knowledge_models import KnowledgeAccessLevel as L
from app.services.knowledge_access_policy import (
    ANONYMOUS_SUBJECT,
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
    KnowledgeResource,
    KnowledgeRetrievalMode as M,
    KnowledgeWritePolicy,
)

ME, OTHER = uuid.UUID(int=1), uuid.UUID(int=2)
P, Q = uuid.UUID(int=101), uuid.UUID(int=102)

SUBJECTS: dict[str, KnowledgeAccessSubject | None] = {
    "system": None,
    "anonymous": ANONYMOUS_SUBJECT,
    "me_no_projects": KnowledgeAccessSubject(user_id=ME, project_ids=frozenset()),
    "me_in_P": KnowledgeAccessSubject(user_id=ME, project_ids=frozenset({P})),
    "me_in_Q": KnowledgeAccessSubject(user_id=ME, project_ids=frozenset({Q})),
    "me_in_PQ": KnowledgeAccessSubject(user_id=ME, project_ids=frozenset({P, Q})),
}
DOC_LEVELS = [None, L.public, L.project_group, L.private]
FOLDER_LEVELS = [L.public, L.project_group, L.private]
PID_SETS = [frozenset(), frozenset({P}), frozenset({Q})]
OWNERS = [ME, OTHER, None]
CURRENT_PROJECTS = [P, None]

_ERROR = "error"


def _res(level, pids, owner) -> KnowledgeResource:
    return KnowledgeResource(access_level=level, project_ids=pids, created_by=owner)


def _reference(mode, subject, current, doc, folder):
    """独立参考模型（查表写法）。"""
    if mode is M.project and current is None:
        return _ERROR
    if mode is not M.project and subject is None:
        return _ERROR
    eff = folder if doc.access_level is None else doc
    if eff is None or eff.access_level is None:
        return False
    lvl, pids, owner = eff.access_level, eff.project_ids, eff.created_by
    in_current = current is not None and current in pids
    if subject is None:
        return {L.public: True, L.project_group: in_current, L.private: False}[lvl]
    readable = {
        L.public: True,
        L.project_group: bool(subject.project_ids & pids),
        L.private: subject.user_id is not None and owner == subject.user_id,
    }[lvl]
    if mode is M.browse:
        return readable
    if mode is M.global_:
        return readable and lvl is not L.project_group
    return readable and (lvl is not L.project_group or in_current)


def _actual(mode, subject, current, doc, folder):
    try:
        return KnowledgeAccessPolicy.can_retrieve(mode, subject, current, doc, folder)
    except ValueError:
        return _ERROR


def _grid():
    folders = [None] + [
        _res(level, pids, owner)
        for level, pids, owner in itertools.product(FOLDER_LEVELS, PID_SETS, OWNERS)
    ]
    docs = [
        _res(level, pids, owner)
        for level, pids, owner in itertools.product(DOC_LEVELS, PID_SETS, OWNERS)
    ]
    for mode, (skey, subject), current, doc, folder in itertools.product(
        list(M), SUBJECTS.items(), CURRENT_PROJECTS, docs, folders
    ):
        yield mode, skey, subject, current, doc, folder


def test_can_retrieve_matches_reference_model_on_full_grid():
    mismatches = []
    total = 0
    for mode, skey, subject, current, doc, folder in _grid():
        total += 1
        expected = _reference(mode, subject, current, doc, folder)
        actual = _actual(mode, subject, current, doc, folder)
        if expected != actual:
            mismatches.append((mode.value, skey, current, doc, folder, expected, actual))
    assert total > 30000, total  # 网格没被意外裁小（否则等价断言空转）
    assert mismatches == [], mismatches[:5]


def test_grid_exercises_every_outcome():
    """反空转：网格里三种结果（可见 / 不可见 / 非法组合）都真实出现过。"""
    outcomes = {_actual(*(g[0], g[2], g[3], g[4], g[5])) for g in _grid()}
    assert outcomes == {True, False, _ERROR}


def test_system_caller_never_sees_private_documents():
    """P10 的纯函数面：无用户调用（后台/系统）在任何项目下都看不到 private。"""
    for pids, owner in itertools.product(PID_SETS, OWNERS):
        private = _res(L.private, pids, owner)
        assert KnowledgeAccessPolicy.can_retrieve(M.project, None, P, private, None) is False
        inherited = _res(None, frozenset(), None)
        assert KnowledgeAccessPolicy.can_retrieve(M.project, None, P, inherited, private) is False


def test_project_group_document_not_injected_into_other_project():
    """跨客户注入：用户同时属于 P、Q，Q 的项目组资料不得出现在 P 的 RAG 里。"""
    subject = SUBJECTS["me_in_PQ"]
    q_doc = _res(L.project_group, frozenset({Q}), OTHER)
    assert KnowledgeAccessPolicy.can_retrieve(M.browse, subject, None, q_doc, None) is True
    assert KnowledgeAccessPolicy.can_retrieve(M.project, subject, P, q_doc, None) is False
    assert KnowledgeAccessPolicy.can_retrieve(M.project, subject, Q, q_doc, None) is True
    assert KnowledgeAccessPolicy.can_retrieve(M.global_, subject, None, q_doc, None) is False


@settings(max_examples=5, deadline=None)
@given(
    mode=st.sampled_from(list(M)),
    skey=st.sampled_from(sorted(SUBJECTS)),
    current=st.sampled_from(CURRENT_PROJECTS),
    doc_level=st.sampled_from(DOC_LEVELS),
    doc_pids=st.sampled_from(PID_SETS),
    doc_owner=st.sampled_from(OWNERS),
    folder_level=st.sampled_from(FOLDER_LEVELS),
    folder_pids=st.sampled_from(PID_SETS),
    folder_owner=st.sampled_from(OWNERS),
)
def test_pbt_can_retrieve_matches_reference(
    mode, skey, current, doc_level, doc_pids, doc_owner, folder_level, folder_pids, folder_owner
):
    doc = _res(doc_level, doc_pids, doc_owner)
    folder = _res(folder_level, folder_pids, folder_owner)
    subject = SUBJECTS[skey]
    assert _actual(mode, subject, current, doc, folder) == _reference(mode, subject, current, doc, folder)


# ---------------------------------------------------------------------------
# P11：管理权（删除 / 重命名 / 移动）
# ---------------------------------------------------------------------------

ROLES = ["admin", "partner", "manager", "auditor", "qc", "eqcr", "readonly", None, "weird_role"]
_WRITE_ROLES = {"admin", "partner", "manager", "auditor", "qc", "eqcr"}


def _reference_manage(subject, visible, owner, role):
    if not visible or subject.user_id is None:
        return False
    if role not in _WRITE_ROLES:
        return False  # readonly / None / 未知角色 → fail-closed
    return role == "admin" or owner == subject.user_id


def test_can_manage_matches_reference_on_full_grid():
    subjects = [SUBJECTS["me_in_P"], ANONYMOUS_SUBJECT]
    mismatches = []
    for subject, visible, owner, role in itertools.product(subjects, [True, False], OWNERS, ROLES):
        expected = _reference_manage(subject, visible, owner, role)
        actual = KnowledgeWritePolicy.can_manage(subject, visible=visible, owner_id=owner, role=role)
        if expected != actual:
            mismatches.append((subject.user_id, visible, owner, role, expected, actual))
    assert mismatches == []


def test_can_manage_accepts_enum_roles_and_string_owner():
    from app.models.base import UserRole

    subject = SUBJECTS["me_no_projects"]
    assert KnowledgeWritePolicy.can_manage(subject, visible=True, owner_id=str(ME), role=UserRole.auditor)
    assert not KnowledgeWritePolicy.can_manage(subject, visible=True, owner_id=str(OTHER), role=UserRole.auditor)
    assert KnowledgeWritePolicy.can_manage(subject, visible=True, owner_id=None, role=UserRole.admin)
    assert not KnowledgeWritePolicy.can_manage(subject, visible=True, owner_id=str(ME), role=UserRole.readonly)


def test_can_create_requires_write_role_and_folder_visibility():
    subject = SUBJECTS["me_in_P"]
    public = _res(L.public, frozenset(), None)
    other_private = _res(L.private, frozenset(), OTHER)
    assert KnowledgeWritePolicy.can_create(subject, public, "auditor") is True
    assert KnowledgeWritePolicy.can_create(subject, public, "readonly") is False
    assert KnowledgeWritePolicy.can_create(subject, other_private, "admin") is False  # admin 不绕过可见性
    assert KnowledgeWritePolicy.can_create(ANONYMOUS_SUBJECT, public, "admin") is False
