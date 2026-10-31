"""发布记录可见性夹具（spec formula-hub-integrity-closure 任务 5；需求 7.4，ADR-FHIC-20；不被 pytest 收集）。

一组按时间排好的发布记录，覆盖四类目标（全局已发布 / 全局候选 / 项目间应用 / 模板）与候选的两种状态，每条写明九种身份里
谁该看见；PG（经端点）与 SQLite（直调 ``list_publishes``）共用同一组期望。``scope`` 每次随机，查询带 ``scope`` 只看本夹具
的记录（快照库 ``formula_publish`` 现为 0 行，隔离是为将来有数据时期望集合不漂移）。全部写入在调用方的事务里。

项目：A = 目标项目（ro / auditor / manager / qc / eqcr / partner 的成员行所在）；B = non_member 的项目；C = 九种身份都不在。
时间轴（新 → 旧）：
- 最新三条是他人的个人模板记录（只有 admin 可见）。PG 上 SQL 条件挡不住模板记录，第一批会被逐条判定全部剔除，必须按游标
  取下一批 ——「最近 limit 条全不可见时仍返回其后的可见记录」。
- 后两条与一条全员可见的已发布记录同一时刻，id 首位分别为 f / 8 / 0：按 (published_at, id) 倒序时可见记录排在这一刻的
  最后，游标只比时间就会漏掉它。
- 其后是 SQL 条件要挡掉的候选与项目间应用（来源或涉及项目是 C / B），再往后各类可见记录。
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.base import UserRole
from app.models.core import User
from app.models.formula_setting_models import FormulaPublish, FormulaTemplate

A_MEMBERS = frozenset({"ro", "auditor", "manager", "qc", "eqcr", "partner"})
ADMIN = frozenset({"admin"})
LOGGED_IN = A_MEMBERS | {"non_member", "admin"}
#: 互不为子串的说明文字（判「不可见记录的说明不出现在响应里」时不会误命中）
NOTES = {"cand_c": "候选说明-丙", "cand_a": "候选说明-甲", "cand_b": "候选说明-乙", "rejected_a": "驳回说明-甲",
         "cand_own": "候选说明-本人", "promoted_c": "设为全局说明"}
_BASE = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
_CHANGE = [{"slot_key": "balance_sheet:BS-001", "label": "货币资金", "old": {"formula": "TB('1001','期末余额')"},
            "new": {"formula": "TB('1001','期末余额')*2"}, "old_version": 1, "new_version": 2, "deleted": False}]


@dataclass(frozen=True)
class SeededPublish:
    key: str
    id: uuid.UUID
    at: datetime
    target: str
    status: str
    visible_to: frozenset[str]
    source_project_id: uuid.UUID | None
    note: str | None
    summary: dict[str, Any]
    change_set: list[dict[str, Any]]


@dataclass(frozen=True)
class PublishScenario:
    scope: str
    records: tuple[SeededPublish, ...]  # (published_at, id) 倒序

    def expected(self, identity: str, *, status: str | None = None, limit: int | None = None) -> list[SeededPublish]:
        rows = [r for r in self.records if identity in r.visible_to and status in (None, r.status)]
        return rows if limit is None else rows[:limit]

    def key_of(self, record_id: str) -> str:
        return next((r.key for r in self.records if str(r.id) == record_id), f"<夹具外 {record_id}>")


def _lead_id(lead: str | None) -> uuid.UUID:
    """首位十六进制数字固定的 UUID：同一时刻的记录按 id 倒序时位置可控。"""
    raw = uuid.uuid4()
    return raw if lead is None else uuid.UUID(lead + raw.hex[1:])


async def _user(session, label: str, tag: str) -> User:
    user = User(username=f"fh_pub_{label}_{tag}", email=f"fh_pub_{label}_{tag}@example.test", hashed_password="x",
                role=UserRole.auditor, is_active=True)
    session.add(user)
    await session.flush()
    return user


async def seed_publishes(session, *, projects: Mapping[str, uuid.UUID], names: Mapping[uuid.UUID, str],
                         users: Mapping[str, uuid.UUID]) -> PublishScenario:
    """写入 5 个模板与 18 条发布记录；``projects`` 键 A / B / C，``users`` 键 = 身份键 → 用户 id。"""
    a, b, c = projects["A"], projects["B"], projects["C"]
    tag = uuid.uuid4().hex[:8]
    owner, submitter = await _user(session, "owner", tag), await _user(session, "submitter", tag)
    tpl = {key: FormulaTemplate(name=f"fh_pub_{key}_{tag}", share_scope=share, owner_user_id=owner_id,
                                owner_project_id=project, domains=["report"], is_deleted=deleted)
           for key, share, owner_id, project, deleted in (
               ("firm", "firm", owner.id, None, False), ("team_a", "team", owner.id, a, False),
               ("personal", "personal", owner.id, None, False), ("own", "personal", users["auditor"], None, False),
               ("deleted", "firm", owner.id, None, True))}
    session.add_all(tpl.values())
    await session.flush()

    def impact(*pids: uuid.UUID) -> dict[str, Any]:  # 全局 / 模板发布的影响摘要（engine.summarize 的形状）
        return {"counts": {"inherit": len(pids)}, "projects": [
            {"project_id": str(p), "name": names[p], "status": "execution", "frozen": False,
             "counts": {"inherit": 1}, "pending": 0, "changed": True} for p in pids],
            "affected_project_count": len(pids), "conflict_count": 0, "pending_total": 0,
            "changed_projects": [str(p) for p in pids]}

    def applied(*pids: uuid.UUID) -> dict[str, Any]:  # 项目间应用的摘要（apply_ops.apply_to_projects 的形状）
        return {"counts": {"same": len(pids)}, "pending_total": 0, "changed_projects": [str(p) for p in pids],
                "target_count": len(pids)}

    template, candidate, projects_ = ({"target": "template", "source": "template_publish"},
                                      {"target": "global", "source": "candidate", "published_by": submitter.id},
                                      {"target": "projects", "source": "apply_to_projects"})
    published = {"target": "global", "source": "global_edit"}
    # (key, 分钟, id 首位, 状态, 谁可见, 其余列)
    rows: list[tuple[str, int, str | None, str, frozenset[str], dict[str, Any]]] = [
        ("tpl_personal_1", 120, None, "published", ADMIN, {**template, "template_id": tpl["personal"].id}),
        ("tpl_personal_2", 110, "f", "published", ADMIN, {**template, "template_id": tpl["personal"].id}),
        ("tpl_personal_3", 110, "8", "published", ADMIN, {**template, "template_id": tpl["personal"].id}),
        ("global_tie", 110, "0", "published", LOGGED_IN, {**published}),
        ("cand_c", 100, None, "pending", ADMIN, {**candidate, "source_project_id": c}),
        ("proj_c", 95, None, "published", ADMIN, {**projects_, "source_project_id": c, "summary": applied(c)}),
        ("cand_a", 90, None, "pending", A_MEMBERS | ADMIN, {**candidate, "source_project_id": a}),
        ("cand_b", 85, None, "pending", ADMIN | {"non_member"}, {**candidate, "source_project_id": b}),
        ("rejected_a", 80, None, "rejected", A_MEMBERS | ADMIN, {**candidate, "source_project_id": a}),
        ("cand_own", 75, None, "pending", ADMIN | {"auditor"},
         {**candidate, "published_by": users["auditor"], "template_id": tpl["own"].id}),
        ("proj_b_to_ac", 70, None, "published", A_MEMBERS | ADMIN | {"non_member"},
         {**projects_, "source_project_id": b, "summary": applied(a, c), "change_set": _CHANGE}),
        ("tpl_team_a", 65, None, "published", A_MEMBERS | ADMIN,
         {**template, "template_id": tpl["team_a"].id, "summary": impact(a, c)}),
        ("tpl_firm", 60, None, "published", LOGGED_IN,
         {**template, "template_id": tpl["firm"].id, "summary": impact(a, b, c)}),
        ("tpl_own", 55, None, "published", ADMIN | {"auditor"}, {**template, "template_id": tpl["own"].id}),
        ("global_pub", 50, None, "published", LOGGED_IN, {**published, "summary": impact(a, b, c), "change_set": _CHANGE}),
        ("promoted_c", 45, None, "published", LOGGED_IN, {**published, "source": "promote", "source_project_id": c}),
        ("tpl_deleted", 40, None, "published", ADMIN, {**template, "template_id": tpl["deleted"].id}),
        ("proj_a_self", 35, None, "published", A_MEMBERS | ADMIN | {"non_member"},
         {**projects_, "source_project_id": a, "summary": applied(b)}),
    ]
    scope = f"fh5-{tag}"
    seeded: list[SeededPublish] = []
    for key, minute, lead, status, visible, cols in rows:
        record_id, at = _lead_id(lead), _BASE + timedelta(minutes=minute)
        summary, change_set = cols.pop("summary", {}), cols.pop("change_set", [])
        session.add(FormulaPublish(id=record_id, domain="report", scope=scope, status=status, published_at=at,
                                   summary=summary, change_set=change_set, note=NOTES.get(key), **cols))
        seeded.append(SeededPublish(key, record_id, at, cols["target"], status, visible, cols.get("source_project_id"),
                                    NOTES.get(key), summary, change_set))
    await session.flush()
    seeded.sort(key=lambda r: (r.at, r.id.int), reverse=True)
    return PublishScenario(scope, tuple(seeded))


def _without(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in summary.items() if k not in ("projects", "changed_projects")}


def assert_items(scenario: PublishScenario, identity: str, items: list[dict[str, Any]], text: str, *,
                 members: set[uuid.UUID], projects: Mapping[uuid.UUID, str], status: str | None = None,
                 limit: int | None = None) -> None:
    """结果 = 期望的可见记录（顺序、条数）；非 admin 的每条只留本人项目信息，响应全文不含他项目 id / 名称与不可见记录的说明。"""
    want = scenario.expected(identity, status=status, limit=limit)
    got = [scenario.key_of(item["id"]) for item in items]
    assert got == [r.key for r in want], (identity, status, limit, got)
    admin = identity == "admin"
    member_text = {str(p) for p in members}

    def keep(pid: str) -> bool:
        return admin or pid in member_text

    for item, record in zip(items, want):
        source = record.source_project_id
        assert item["source_project_id"] == (str(source) if source and keep(str(source)) else None), record.key
        summary = item["summary"]
        if "changed_projects" in record.summary:
            assert summary["changed_projects"] == [p for p in record.summary["changed_projects"] if keep(p)], record.key
        if "projects" in record.summary:
            assert [p["project_id"] for p in summary["projects"]] == [
                p["project_id"] for p in record.summary["projects"] if keep(p["project_id"])], record.key
        assert _without(summary) == _without(record.summary), record.key
        assert (item["note"], item["change_set"], item["status"], item["target"]) == (
            record.note, record.change_set, record.status, record.target), record.key
    if admin:
        return
    leaked = [secret for pid, name in projects.items() if pid not in members for secret in (str(pid), name)
              if secret in text]
    leaked += [r.note for r in scenario.records if r.note and identity not in r.visible_to and r.note in text]
    assert leaked == [], (identity, leaked)
