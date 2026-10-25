"""真实 PostgreSQL 守卫：知识库文档词法检索 + 检索内核会话安全 + 单一判定面。

spec: knowledge-base-retrieval-and-authz-closure（P1 / P3 / P4 / P5 / P6 / P8 / P9 / P10）

═══ 为什么必须真库 ═══

* P1 的判据是 PostgreSQL「语句失败 → 事务 aborted → 后续语句全部拒绝」语义；mock / SQLite
  都不会进入 aborted，修没修都绿。故带**反向对照**：同一夹具里旧式查询（SELECT 含
  ``embedding_vec``、无 SAVEPOINT）必须真的把会话毒化，对照不红说明夹具没复现缺陷。
* P3/P4/P5/P6 的判据落在 SQL 上（ILIKE ESCAPE、NOT EXISTS 最新版本、递归 CTE 子树、
  范围下推），只有真库执行才能证明。

═══ 数据 ═══

一个 scratch schema（``tmp_kbsearch_*``），表由 ORM 派生（去外键、去 ``embedding_vec``）。
用户 ME 是项目 P、Q 的成员，OTHER 不属于任何项目；各级别文件夹 / 文档见 ``_seed``。
全部场景在一次 ``asyncio.run`` 中执行落快照，结束 ``DROP SCHEMA CASCADE``。
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from tests._kb_pg_scratch import scratch_schema  # noqa: E402

TOKEN = "独特词甲"
ME = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
OTHER = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
P = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
Q = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
FILLERS = 12


@dataclasses.dataclass
class _User:
    id: uuid.UUID
    role: str = "auditor"


def _ids(hits) -> list[str]:
    return [str(h.meta.doc_id) for h in hits]


async def _seed(Session) -> dict[str, uuid.UUID]:
    from app.models.base import ProjectUserRole
    from app.models.core import ProjectUser
    from app.models.knowledge_models import (
        KnowledgeAccessLevel as L,
        KnowledgeDocument,
        KnowledgeFolder,
    )

    ids: dict[str, uuid.UUID] = {}
    base_time = datetime(2026, 9, 1, 8, 0, 0)

    def folder(key, name, level, *, parent=None, pids=None, owner=None, deleted=False, category=None):
        ids[key] = uuid.uuid4()
        return KnowledgeFolder(
            id=ids[key], name=name, access_level=level, parent_id=ids.get(parent) if parent else None,
            project_ids=[str(p) for p in pids] if pids else None, created_by=owner,
            is_deleted=deleted, category=category,
        )

    minute = [0]

    def doc(key, folder_key, name, content, *, level=None, owner=None, deleted=False,
            version=1, prev=None):
        ids[key] = uuid.uuid4()
        minute[0] += 1
        return KnowledgeDocument(
            id=ids[key], folder_id=ids[folder_key], name=name, content_text=content,
            file_size=len(content.encode("utf-8")), access_level=level, created_by=owner,
            is_deleted=deleted, version=version, previous_version_id=ids.get(prev) if prev else None,
            updated_at=base_time + timedelta(minutes=minute[0]),
        )

    folders = [
        folder("F_pub", "公开", L.public),
        folder("F_pub_sub", "子目录", L.public, parent="F_pub"),
        folder("F_pgP", "P项目组", L.project_group, pids=[P]),
        folder("F_pgQ", "Q项目组", L.project_group, pids=[Q]),
        folder("F_priv_me", "我的私有", L.private, owner=ME),
        folder("F_priv_other", "他人私有", L.private, owner=OTHER),
        folder("F_deleted", "已删除目录", L.public, deleted=True),
        folder("F_cat", "会计准则库", L.public, category="accounting_standards"),
        folder("F_cat_sub", "收入", L.public, parent="F_cat"),
    ]
    docs = [
        doc("d_pub", "F_pub", "收入确认指引.md", f"{TOKEN} 收入确认的五步法模型"),
        doc("d_pub_sub", "F_pub_sub", "子目录文档.md", f"{TOKEN} 仅一次"),
        doc("d_pgP", "F_pgP", "P底稿说明.md", f"{TOKEN} P 项目组资料"),
        doc("d_pgQ", "F_pgQ", "Q底稿说明.md", f"{TOKEN} Q 项目组资料"),
        doc("d_priv_me", "F_priv_me", "我的笔记.md", f"{TOKEN} 我的私有笔记", owner=ME),
        doc("d_priv_other", "F_priv_other", "他人笔记.md", f"{TOKEN} 他人私有", owner=OTHER),
        doc("d_in_deleted_folder", "F_deleted", "孤儿.md", f"{TOKEN} 目录已删"),
        doc("d_deleted", "F_pub", "已删文档.md", f"{TOKEN} 文档已删", deleted=True),
        doc("d_doclevel_private_other", "F_pub", "文档级私有.md", f"{TOKEN} 文档级私有",
            level=L.private, owner=OTHER),
        doc("d_v1", "F_pub", "制度.md", f"{TOKEN} 旧版制度", version=1),
        doc("d_percent", "F_pub", "字面量.md", "完成率 100% 达标 a_b 字面量"),
        # 只含 axb（下划线若被当成单字符通配就会命中它）；正文里不得出现字面量 a_b
        doc("d_axb", "F_pub", "近似.md", "axb 近似写法"),
        doc("d_cat", "F_cat_sub", "收入准则.md", f"{TOKEN} 准则条文"),
        doc("d_long", "F_pub", "长文.md", "前言" * 400 + f"{TOKEN}核心段落" + "尾注" * 400),
    ]
    docs.append(doc("d_v2", "F_pub", "制度.md", f"{TOKEN} 新版制度", version=2, prev="d_v1"))
    for i in range(FILLERS):
        docs.append(doc(f"filler_{i}", "F_pub", f"{TOKEN}高频{i}.md", f"{TOKEN} {TOKEN} {TOKEN} 高频{i}"))

    async with Session() as s:
        s.add_all(folders)
        await s.flush()
        s.add_all(docs)
        for project in (P, Q):
            s.add(ProjectUser(project_id=project, user_id=ME, role=ProjectUserRole.auditor))
        await s.commit()
    return ids


async def _lexical_scenarios(Session, ids: dict[str, uuid.UUID], snap: dict[str, Any]) -> None:
    from app.services.knowledge_access_policy import (
        KnowledgeAccessPolicy,
        KnowledgeRetrievalMode as M,
    )
    from app.services.knowledge_doc_search import DocSearchRequest, KnowledgeDocSearch

    async with Session() as s:
        me = await KnowledgeAccessPolicy.resolve_subject(s, _User(ME))
        snap["me_projects"] = sorted(str(p) for p in me.project_ids)
        search = KnowledgeDocSearch(s)

        async def run(**kw):
            base = dict(query=TOKEN, mode=M.project, subject=me, project_id=P, top_k=100)
            base.update(kw)
            return await search.search(DocSearchRequest(**base))

        snap["proj_me_P"] = _ids(await run())
        snap["proj_system_P"] = _ids(await run(subject=None))
        snap["browse_me"] = _ids(await run(mode=M.browse, project_id=None))
        snap["global_me"] = _ids(await run(mode=M.global_, project_id=None))
        snap["restrict_v1"] = _ids(await run(restrict_to=(ids["d_v1"],)))
        snap["top3"] = _ids(await run(top_k=3))
        snap["restrict_sub_top3"] = _ids(await run(top_k=3, restrict_to=(ids["F_pub_sub"],)))
        snap["restrict_root"] = _ids(await run(restrict_to=(ids["F_pub"],)))
        snap["restrict_missing"] = _ids(await run(restrict_to=(uuid.uuid4(),)))
        snap["restrict_union"] = _ids(await run(restrict_to=(ids["d_pgP"], ids["F_pub_sub"])))
        snap["wildcard_query"] = _ids(await run(query="%"))
        first = await run(top_k=10)
        second = await run(top_k=10)
        snap["determinism"] = (_ids(first), _ids(second), [h.score for h in first])
        long_hit = [h for h in await run(restrict_to=(ids["d_long"],))]
        snap["snippet_long"] = [
            (len(h.snippet), TOKEN in h.snippet, h.chunk_index, h.score) for h in long_hit
        ]
        with_cat = {str(h.meta.doc_id): h.score for h in await run(category="accounting_standards")}
        without_cat = {str(h.meta.doc_id): h.score for h in await run()}
        snap["category_scores"] = (with_cat.get(str(ids["d_cat"])), without_cat.get(str(ids["d_cat"])))
        listed = await run(query="", top_k=5)
        snap["list_mode"] = ([str(h.meta.doc_id) for h in listed], [h.score for h in listed])
        snap["scores_in_range"] = all(0.0 <= h.score <= 1.0 for h in await run())
        snap["snippets_bounded"] = all(len(h.snippet) <= 500 for h in await run())

        # P6：LIKE 通配符必须按字面量匹配（直接驱动 SQL 层，与分词器无关）
        snap["like_percent"] = sorted(str(m.doc_id) for m in await search._candidates(["%"], (), ()))
        snap["like_underscore"] = sorted(str(m.doc_id) for m in await search._candidates(["a_b"], (), ()))
        subtree = await search.folder_subtree([ids["F_pub"]])
        snap["subtree_root"] = sorted(str(f) for f in subtree)
        paths = await search.folder_paths([ids["F_pub_sub"], ids["F_cat_sub"]])
        snap["folder_paths"] = {str(k): (v.path, [str(a) for a in v.ancestor_ids]) for k, v in paths.items()}


async def _session_alive(s) -> str:
    try:
        await s.execute(sa.text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return type(getattr(exc, "orig", exc)).__name__ or type(exc).__name__


async def _kernel_scenarios(Session, ids: dict[str, uuid.UUID], snap: dict[str, Any]) -> None:
    from app.models.ai_models import KnowledgeIndex
    from app.services.knowledge_index_service import KnowledgeIndexService

    # ── P1 反向对照：旧式查询（SELECT 含 embedding_vec、无 SAVEPOINT）必须毒化会话 ──
    async with Session() as s:
        legacy_error = None
        try:
            await s.execute(sa.select(KnowledgeIndex).where(KnowledgeIndex.project_id == P))
        except Exception as exc:  # noqa: BLE001
            legacy_error = type(exc).__name__
        snap["legacy_query_error"] = legacy_error
        snap["legacy_session_after"] = await _session_alive(s)

    # ── resolve_subject 的 fail-closed 必须是真的：成员查询失败后会话仍可用 ──
    # 事务内把 project_users 改名制造查询失败，结束时回滚（改名随之撤销）
    from app.models.core import ProjectUser
    from app.services.knowledge_access_policy import KnowledgeAccessPolicy

    async with Session() as s:
        await s.execute(sa.text("ALTER TABLE project_users RENAME TO project_users_hidden"))
        subject = await KnowledgeAccessPolicy.resolve_subject(s, _User(ME))
        snap["subject_on_failure"] = {
            "user": str(subject.user_id), "projects": sorted(str(p) for p in subject.project_ids),
            "alive": await _session_alive(s),
        }
        await s.rollback()
    async with Session() as s:  # 反向对照：同样的查询不包 SAVEPOINT → 会话被毒化
        await s.execute(sa.text("ALTER TABLE project_users RENAME TO project_users_hidden"))
        try:
            await s.execute(sa.select(ProjectUser.project_id).where(ProjectUser.user_id == ME))
        except Exception:  # noqa: BLE001
            pass
        snap["subject_legacy_alive"] = await _session_alive(s)
        await s.rollback()

    # ── P1 正向：embedding 可用但无 pgvector 列 → 内存向量路径 + 词法层；会话仍可用 ──
    async with Session() as s:
        svc = KnowledgeIndexService(s)
        with patch.object(svc._ai_svc, "embedding", new=AsyncMock(return_value=[0.1] * 1024)):
            hits = await svc.semantic_search(P, TOKEN, top_k=5, user=_User(ME))
        snap["p1_vector_path"] = {"alive": await _session_alive(s), "n": len(hits),
                                  "retrieval": sorted({h["retrieval"] for h in hits})}

    # ── P1 注入：词法层内部 SQL 失败 → 只回滚它自己的 SAVEPOINT ──
    async with Session() as s:
        svc = KnowledgeIndexService(s)

        async def _boom(*_a, **_k):
            await s.execute(sa.text("SELECT * FROM kb_no_such_table"))

        with patch.object(svc._ai_svc, "embedding", new=AsyncMock(side_effect=RuntimeError("down"))), \
                patch.object(svc._doc_search, "_candidates", new=_boom):
            hits = await svc.semantic_search(P, TOKEN, top_k=5, user=_User(ME))
        snap["p1_injected"] = {"alive": await _session_alive(s), "n": len(hits)}

    # ── 词法层经内核：结果字段、folder_path、用户 / 无用户 ──
    async with Session() as s:
        svc = KnowledgeIndexService(s)
        with patch.object(svc._ai_svc, "embedding", new=AsyncMock(side_effect=RuntimeError("down"))):
            with_user = await svc.semantic_search(P, TOKEN, top_k=100, user=_User(ME), scope="knowledge_doc")
            no_user = await svc.semantic_search(P, TOKEN, top_k=100, user=None, scope="knowledge_doc")
        snap["kernel_me"] = [(h["source_id"], h["retrieval"], h.get("document_name"), h.get("folder_path"),
                              h.get("folder_ancestor_ids")) for h in with_user]
        snap["kernel_system"] = [h["source_id"] for h in no_user]
        snap["kernel_alive"] = await _session_alive(s)

    # ── P9：向量层注入的 knowledge_doc 命中必须经单一判定面 ──
    async with Session() as s:
        svc = KnowledgeIndexService(s)
        injected = [
            {"source_type": "knowledge_doc", "source_id": str(ids[k]), "content": k, "score": 0.9,
             "chunk_index": 0, "doc_version": None, "is_stale": False, "retrieval": "vector"}
            for k in ("d_pub", "d_priv_other", "d_pgQ", "d_v1", "d_deleted", "d_in_deleted_folder",
                      "d_doclevel_private_other", "d_priv_me")
        ]
        with patch.object(svc, "_vector_search", new=AsyncMock(side_effect=lambda *a, **k: [dict(r) for r in injected])):
            vec_me = await svc.semantic_search(P, "查不到的词汇ＸＹＺ", top_k=50, user=_User(ME), scope="knowledge_doc")
            vec_sys = await svc.semantic_search(P, "查不到的词汇ＸＹＺ", top_k=50, user=None, scope="knowledge_doc")
            vec_restrict = await svc.semantic_search(
                P, "查不到的词汇ＸＹＺ", top_k=50, user=_User(ME), scope="knowledge_doc", restrict_to=[ids["d_v1"]]
            )
        snap["vector_me"] = sorted(h["source_id"] for h in vec_me)
        snap["vector_system"] = sorted(h["source_id"] for h in vec_sys)
        snap["vector_restrict"] = sorted(h["source_id"] for h in vec_restrict)
        snap["vector_names"] = sorted(h.get("document_name") or "" for h in vec_me)

    # ── 全局知识 / 按 ID 读文档 ──
    async with Session() as s:
        svc = KnowledgeIndexService(s)
        glob = await svc.search_global_knowledge(TOKEN, user=_User(ME), top_k=100)
        snap["global_kernel"] = [h["source_id"] for h in glob]
        loaded = await svc.load_documents(
            [ids["d_priv_other"], ids["d_pub"], ids["d_v1"], ids["d_pgQ"]], user=_User(ME), project_id=P
        )
        snap["load_documents"] = [(d["source_id"], bool(d["content"]), d["document_name"]) for d in loaded]


async def _collect() -> dict[str, Any]:
    errors: list[str] = []
    snap: dict[str, Any] = {"harness_errors": errors}
    try:
        async with scratch_schema("kbsearch", errors) as Session:
            ids = await _seed(Session)
            snap["ids"] = {k: str(v) for k, v in ids.items()}
            await _lexical_scenarios(Session, ids, snap)
            await _kernel_scenarios(Session, ids, snap)
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        import traceback

        errors.append(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def _names(snap, keys) -> set[str]:
    return {snap["ids"][k] for k in keys}


FILLER_KEYS = [f"filler_{i}" for i in range(FILLERS)]
ALWAYS_VISIBLE_P = ["d_pub", "d_pub_sub", "d_pgP", "d_v2", "d_cat", "d_long", *FILLER_KEYS]
NEVER_VISIBLE = ["d_priv_other", "d_in_deleted_folder", "d_deleted", "d_doclevel_private_other", "d_v1"]


def test_harness_ran_without_errors(snap):
    assert snap["harness_errors"] == []
    assert snap["me_projects"] == sorted([str(P), str(Q)])


# ── P3 / P10：检索可见集合 ─────────────────────────────────────────────────────


def test_p3_project_mode_with_user(snap):
    got = set(snap["proj_me_P"])
    assert got == _names(snap, ALWAYS_VISIBLE_P + ["d_priv_me"])
    assert not got & _names(snap, NEVER_VISIBLE + ["d_pgQ"]), "他项目组/私有/已删/旧版泄露"


def test_p10_project_mode_without_user_never_returns_private(snap):
    got = set(snap["proj_system_P"])
    assert got == _names(snap, ALWAYS_VISIBLE_P)
    assert snap["ids"]["d_priv_me"] not in got


def test_browse_mode_includes_all_member_project_groups(snap):
    got = set(snap["browse_me"])
    assert _names(snap, ["d_pgP", "d_pgQ", "d_priv_me"]) <= got
    assert not got & _names(snap, NEVER_VISIBLE)


def test_global_mode_excludes_project_group_documents(snap):
    got = set(snap["global_me"])
    assert not got & _names(snap, ["d_pgP", "d_pgQ"])
    assert _names(snap, ["d_pub", "d_priv_me"]) <= got


# ── P4：最新版本 ──────────────────────────────────────────────────────────────


def test_p4_superseded_version_hidden_unless_named(snap):
    v1, v2 = snap["ids"]["d_v1"], snap["ids"]["d_v2"]
    assert v2 in snap["proj_me_P"] and v1 not in snap["proj_me_P"]
    assert snap["restrict_v1"] == [v1]


# ── P5：restrict_to 并集、子树、截断前生效 ─────────────────────────────────────


def test_p5_restriction_applies_before_top_k(snap):
    sub = snap["ids"]["d_pub_sub"]
    assert len(snap["top3"]) == 3 and sub not in snap["top3"], "夹具失效：子目录文档本就进了 top3"
    assert snap["restrict_sub_top3"] == [sub]


def test_p5_restriction_is_union_and_expands_subtree(snap):
    assert set(snap["restrict_union"]) == _names(snap, ["d_pgP", "d_pub_sub"])
    assert snap["ids"]["d_pub_sub"] in snap["restrict_root"]
    assert set(snap["subtree_root"]) == _names(snap, ["F_pub", "F_pub_sub"])
    assert snap["restrict_missing"] == [], "点名的范围不存在时退化成了全库检索"


# ── P6：LIKE 通配符字面量匹配 ──────────────────────────────────────────────────


def test_p6_like_wildcards_are_literal(snap):
    assert snap["like_percent"] == [snap["ids"]["d_percent"]]
    assert snap["like_underscore"] == [snap["ids"]["d_percent"]], "'_' 被当成单字符通配"
    assert snap["wildcard_query"] == [], "纯通配符查询不得退化成列表模式"


# ── P7 / P8：片段、分数、确定性、加分、列表模式 ────────────────────────────────


def test_p7_snippet_window_and_scores(snap):
    (length, has_token, chunk_index, score), = snap["snippet_long"]
    assert length <= 500 and has_token and chunk_index >= 1 and 0 < score <= 1
    assert snap["scores_in_range"] and snap["snippets_bounded"]


def test_p8_search_is_deterministic(snap):
    first, second, scores = snap["determinism"]
    assert first == second and len(first) == 10
    assert scores == sorted(scores, reverse=True)


def test_category_is_a_bonus_not_a_filter(snap):
    with_cat, without_cat = snap["category_scores"]
    assert with_cat is not None and without_cat is not None
    assert with_cat > without_cat
    # 分类不做硬过滤：非分类子树的文档照样返回
    assert snap["ids"]["d_pub"] in snap["proj_me_P"]


def test_list_mode_orders_by_recency(snap):
    listed, scores = snap["list_mode"]
    assert len(listed) == 5 and all(s == 0.0 for s in scores)
    assert listed[0] == snap["ids"][f"filler_{FILLERS - 1}"], "列表模式未按更新时间倒序"


def test_folder_paths_are_full_paths(snap):
    paths = snap["folder_paths"]
    path, ancestors = paths[snap["ids"]["F_pub_sub"]]
    assert path == "/公开/子目录"
    assert ancestors == [snap["ids"]["F_pub"], snap["ids"]["F_pub_sub"]]
    assert paths[snap["ids"]["F_cat_sub"]][0] == "/会计准则库/收入"


# ── P1：会话安全（含反向对照）─────────────────────────────────────────────────


def test_p1_negative_control_legacy_query_poisons_session(snap):
    assert snap["legacy_query_error"] is not None, "夹具没复现：旧式查询竟然成功（真库应无 embedding_vec）"
    assert snap["legacy_session_after"] != "ok", "夹具没复现 aborted 语义，下方正向断言会空转"


def test_resolve_subject_failure_is_really_fail_closed(snap):
    """成员关系查询失败 → 空项目集主体（fail-closed），且会话仍可继续执行语句。"""
    assert snap["subject_legacy_alive"] != "ok", "反向对照未复现：裸查询失败应毒化会话"
    assert snap["subject_on_failure"] == {"user": str(ME), "projects": [], "alive": "ok"}


def test_p1_semantic_search_keeps_session_usable(snap):
    assert snap["p1_vector_path"]["alive"] == "ok"
    assert snap["p1_vector_path"]["n"] > 0 and snap["p1_vector_path"]["retrieval"] == ["lexical"]
    assert snap["p1_injected"] == {"alive": "ok", "n": 0}
    assert snap["kernel_alive"] == "ok"


# ── P9：内核结果（词法 + 注入的向量命中）全部过判定面 ─────────────────────────


def test_p9_kernel_lexical_results_and_enrichment(snap):
    rows = snap["kernel_me"]
    assert {r[0] for r in rows} == set(snap["proj_me_P"])
    assert all(r[1] == "lexical" for r in rows)
    sub = next(r for r in rows if r[0] == snap["ids"]["d_pub_sub"])
    assert sub[2] == "子目录文档.md" and sub[3] == "/公开/子目录"
    assert sub[4] == [snap["ids"]["F_pub"], snap["ids"]["F_pub_sub"]]
    assert set(snap["kernel_system"]) == set(snap["proj_system_P"])


def test_p9_injected_vector_hits_are_filtered(snap):
    assert snap["vector_me"] == sorted(_names(snap, ["d_pub", "d_priv_me"]))
    assert snap["vector_system"] == sorted(_names(snap, ["d_pub"]))
    assert snap["vector_restrict"] == [snap["ids"]["d_v1"]], "点名的旧版本应放行、范围外的应剔除"
    assert "收入确认指引.md" in snap["vector_names"]


def test_global_knowledge_and_load_documents(snap):
    glob = set(snap["global_kernel"])
    assert not glob & _names(snap, ["d_pgP", "d_pgQ"]) and snap["ids"]["d_pub"] in glob
    loaded = snap["load_documents"]
    assert [d[0] for d in loaded] == [snap["ids"]["d_pub"], snap["ids"]["d_v1"]]
    assert all(d[1] for d in loaded)
