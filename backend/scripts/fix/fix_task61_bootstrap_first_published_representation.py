# -*- coding: utf-8 -*-
"""在一次性夹具项目上产出平台**第一份** published representation（解除 BP-61-1）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 61
Requirements: 2.2, 2.3, 2.11, 3.1, 6.19, 12.6
Properties: **P4 / P5 / P50 / P64**

═══ 为什么需要这个宿主 ═══

Task 61 的三臂反事实实测把绑定约束钉在 **BP-61-1**：`working_paper_sync_entry_state` /
`working_paper_content_version` / `working_paper_content_representation` 三表实测
`0 / 0 / 0`，186 个 planned entry 一个都注册不上 —— 连供给最完整的 Excel pilot 也一样。
它是**平台级**的，不是 F2 特有的。

首版供给在 DB 外键层面是个环：`representation_upgrade_candidate` 的
`content_version_id` / `source_representation_id` 都是 NOT NULL FK，指向的两张表是空的
⇒ `finalize_candidate` 只能加 generation，产不出第一代。唯一的首版生产者是
`ContentMutationService.commit()`，而它的 projection lane 又要 adapter，adapter 注册
又要 published representation。

环的出口在 **opaque/custom lane**：`_stage_authoritative` 不 materialize、不反读、
**不需要 adapter**（`adapter=None`），权威 OOXML 字节本身就是内容。生产侧的装配面已经
存在 —— `writer_migration.AuthoritativeContentWriter.commit_bytes(..., lane_id=...)`，
lane 真源是 `opaque_entry_gate.OPAQUE_AUTHORITY_LANES`。所以本脚本**不新增一行生产
代码**，只做「选目标 + 取真字节 + 调生产 writer + 回读校验」。

═══ 为什么走 writer 而不是 WpUploadService.upload_file ═══

`offline_upload` lane 登记的 writer 是 `WpUploadService.upload_file`，它内部调的正是
本脚本调的 `commit_bytes`（同一 lane、同一 authority model）。不走它是因为它在 commit
之后还串了四件与 BP-61-1 无关的事：云端双写、`parse_workpaper_real` 回写 parsed_data、
version-line stamp、`WORKPAPER_SAVED` 级联（会去动试算表与报表）。那些副作用把写入面
扩大到本次授权范围之外。本脚本的写入面因此**恰好**是：canonical artifact 行 +
content_version + representation + entry pointer + outbox 一行，加上夹具底稿自己的
`working_paper.content_revision` / `current_content_version_id` 两列。

注：`opaque_entry_gate.discover_commit_bytes_lane_arguments()` 只扫
`PRODUCTION_SOURCE_ROOTS = ("app",)`，脚本调用点不在它的分母里，故本脚本不会让
`assert_commit_bytes_lane_arguments_match_registry` 漂移。

═══ 夹具门（fail closed，不提供绕过开关）═══

用户授权范围是「只限测试夹具项目」。这一句被做成可执行判据
:func:`assert_fixture_only`：`client_name == 测试客户` **且** `status == created`
**且** 该项目未删除底稿数 <= 5 **且** 目标底稿 `content_revision == 0`。四条任一不满足
即 :class:`FixtureGuardError`，脚本非零退出、一行不写。它是**纯函数**（吃一个 mapping），
所以守卫可以喂合成的「真实客户项目」行去证明它真的拒绝 —— 只在真数据上断言等于等价
变异（本 spec 的 M15 教训）。

═══ 权威字节从哪来（不 glob、不猜）═══

不按文件名 glob 模板。字节身份走**已 approved 的契约**这一条真源：读库里
`kind=contract, state=approved, logical_id=<--contract>` 的那行 → 按 `sha256` 定位
definition store 里的 blob → 校验 blob 字节的 sha256 与库行相等 → 取
`review.authority_root` + `template.relative_path` + `template.template_sha256` →
读运行时权威模板库的真实文件 → **再**校验其 sha256 与契约冻结值逐字相等。任一环不等
即报错退出。契约的 logical_id 前缀还必须与目标底稿的 wp_code 相等（`d2.*` 对 `D2`），
避免拿一份不相干的模板当上传件。

用法（仓库根）::

    python backend/scripts/fix/fix_task61_bootstrap_first_published_representation.py --check
    python backend/scripts/fix/fix_task61_bootstrap_first_published_representation.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

#: 夹具项目的四条判据取值（唯一真源；守卫 import 它们比对，不抄字面量）。
FIXTURE_CLIENT_NAME: str = "测试客户"
FIXTURE_PROJECT_STATUS: str = "created"
FIXTURE_MAX_WORKPAPERS: int = 5
FIXTURE_REQUIRED_REVISION: int = 0

#: 用哪条已登记 lane 提交。真源 = opaque_entry_gate.OPAQUE_AUTHORITY_LANES，
#: 脚本启动时现算校验它的 authority model 与 entry_id 口径。
LANE_ID: str = "offline_upload"

#: 契约默认取哪一条（可 --contract 覆盖）。前缀必须与目标底稿 wp_code 对齐。
DEFAULT_CONTRACT_LOGICAL_ID: str = "d2.receivable_detail"

#: 权威模板库目录名（与 wp_template_finder / ExcelInstrumentationUpgrader 同一处）。
AUTHORITY_ROOT_NAME: str = "wp_templates"

#: definition blob 落盘根（与 definitions.definition_store_relative_path 同域）。
DEFINITION_STORE: Path = _BACKEND / "definition_store"

#: 目标选取排序（确定性：重跑必选同一条）。
TARGET_ORDER_SQL: str = "p.created_at, wp.id"


class BootstrapScriptError(RuntimeError):
    """脚本自身失败。禁 fail-open —— 一律非零退出，不降级成「本库无此数据」。"""


class FixtureGuardError(BootstrapScriptError):
    """目标不是一次性夹具项目。**不提供**绕过开关。"""


class FrozenIdentityError(BootstrapScriptError):
    """权威字节与契约冻结的 digest 不一致（模板漂移 / 拿错文件）。"""

# ═══════════════════════════════════════════════════════════════════════════
# 1. lane 真源自检
# ═══════════════════════════════════════════════════════════════════════════


def lane_facts(lane_id: str = LANE_ID) -> dict[str, Any]:
    """从 lane 登记表现算本次要用的 lane 事实，并锁死两条前提。

    判据落在**登记表的列**上而不是脚本里的字面量：有人把 offline_upload 的 authority
    model 改成 projection、或把 entry_id 口径从 wp_id 改成 wp_code，这里立刻抛，而不是
    静默产出一个身份错位的 representation。
    """
    from app.services.workpaper_sync.models import AuthorityModel
    from app.services.workpaper_sync.opaque_entry_gate import (
        EntryIdSource,
        authority_model_for_lane,
        lane_for,
    )

    lane = lane_for(lane_id)
    model = authority_model_for_lane(lane_id)
    if model is AuthorityModel.projection_contract:
        raise BootstrapScriptError(
            f"lane {lane_id!r} 的 authority model 已变成 projection_contract —— "
            "那条路径必须走 adapter 全量协议（materialize → 反读等值 → 未管理区域比对），"
            "不得用 opaque 装配跳过"
        )
    if lane.entry_id_source is not EntryIdSource.wp_id:
        raise BootstrapScriptError(
            f"lane {lane_id!r} 的 entry_id 口径已改为 {lane.entry_id_source.value} —— "
            "本脚本按 wp_id 构造 entry_id，口径漂移会让 representation generation 互相顶掉"
        )
    return {
        "lane_id": lane.lane_id,
        "authority_model": model.value,
        "entry_id_source": lane.entry_id_source.value,
        "writer_ref": lane.writer_ref,
        "document_type": lane.document_type,
        "instrumentation_required": lane.instrumentation_required,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威字节（契约 → definition blob → 运行时模板库，三段 digest 全对齐）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrozenTemplate:
    contract_logical_id: str
    contract_definition_sha256: str
    wp_code: str
    authority_root: str
    relative_path: str
    template_sha256: str
    absolute_path: Path
    payload: bytes
    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_logical_id": self.contract_logical_id,
            "contract_definition_sha256": self.contract_definition_sha256,
            "wp_code": self.wp_code,
            "authority_root": self.authority_root,
            "relative_path": self.relative_path,
            "template_sha256": self.template_sha256,
            "absolute_path": str(self.absolute_path),
            "payload_bytes": len(self.payload),
        }


def wp_code_of_contract(contract_logical_id: str) -> str:
    """d2.receivable_detail 换算成 D2。契约 id 与底稿编码的唯一换算处。"""
    head = (contract_logical_id or "").split(".", 1)[0].strip()
    if not head:
        raise BootstrapScriptError(f"契约 logical_id 形态非法: {contract_logical_id!r}")
    return head.upper()


async def load_frozen_template(session: Any, *, contract_logical_id: str) -> FrozenTemplate:
    """按已 approved 契约把权威模板字节取出来，并三段 digest 逐段对齐。"""
    rows = (
        await session.execute(
            sa.text(
                "SELECT id, sha256 FROM working_paper_sync_definition_artifact "
                "WHERE kind = 'contract' AND logical_id = :lid AND state = 'approved'"
            ),
            {"lid": contract_logical_id},
        )
    ).mappings().all()
    if len(rows) != 1:
        raise BootstrapScriptError(
            f"approved 契约 {contract_logical_id!r} 在库里命中 {len(rows)} 行（要求恰 1 行）"
            " —— 先跑 fix_task76_provision_projection_definitions.py --apply"
        )
    sha = str(rows[0]["sha256"]).strip()
    blob = DEFINITION_STORE / "contracts" / f"{sha}.json"
    if not blob.is_file():
        raise BootstrapScriptError(f"契约 blob 不在 definition store: {blob}")
    raw = blob.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != sha:
        raise FrozenIdentityError(
            f"契约 blob 字节 digest 与库行不符: blob={observed} row={sha} —— "
            "内容寻址被破坏，不可用它推导模板身份"
        )
    doc = json.loads(raw.decode("utf-8"))
    review = doc.get("review") or {}
    template = doc.get("template") or {}
    authority_root = str(review.get("authority_root") or "").strip()
    relative_path = str(template.get("relative_path") or "").strip()
    template_sha = str(template.get("template_sha256") or "").strip()
    if not (authority_root and relative_path and template_sha):
        raise BootstrapScriptError(
            "契约缺 review.authority_root / template.relative_path / "
            "template.template_sha256 三者之一: "
            f"root={authority_root} rel={relative_path} sha={template_sha}"
        )
    expected_root = "backend/" + AUTHORITY_ROOT_NAME
    if authority_root != expected_root:
        raise BootstrapScriptError(
            f"契约声明的 authority_root={authority_root} 不是运行时权威模板库 "
            f"{expected_root} —— 参考副本已落后，不得用它当上传件"
        )
    absolute = (_REPO_ROOT / authority_root / relative_path).resolve()
    if not absolute.is_file():
        raise BootstrapScriptError(f"权威模板文件不存在: {absolute}")
    payload = absolute.read_bytes()
    if not payload:
        raise BootstrapScriptError(f"权威模板为空文件: {absolute}")
    observed_template = hashlib.sha256(payload).hexdigest()
    if observed_template != template_sha:
        raise FrozenIdentityError(
            f"权威模板 {relative_path} 的 sha256={observed_template} 与契约冻结值 "
            f"{template_sha} 不符 —— 模板已改版，本次提交会把一份契约没见过的字节"
            "当成它的权威内容"
        )
    return FrozenTemplate(
        contract_logical_id=contract_logical_id,
        contract_definition_sha256=sha,
        wp_code=wp_code_of_contract(contract_logical_id),
        authority_root=authority_root,
        relative_path=relative_path,
        template_sha256=template_sha,
        absolute_path=absolute,
        payload=payload,
    )

# ═══════════════════════════════════════════════════════════════════════════
# 3. 夹具门（纯函数，可喂合成的非夹具行证明它真的拒绝）
# ═══════════════════════════════════════════════════════════════════════════


#: 夹具门的四条判据 id（封闭词表；守卫按 id 逐条构造反例）。
FIXTURE_CRITERIA: tuple[str, ...] = (
    "client_name_is_fixture",
    "project_status_is_created",
    "project_workpaper_count_within_cap",
    "target_revision_is_zero",
)


def fixture_violations(row: Mapping[str, Any]) -> tuple[str, ...]:
    """返回该行**违反**了哪几条夹具判据（空元组 = 是夹具）。

    只吃 mapping、不碰 DB —— 守卫因此可以喂「真实客户项目」的合成行，证明拒绝分支
    真的会走到；只在真夹具数据上断言等价于什么都没测。
    """
    bad: list[str] = []
    if str(row.get("client_name") or "").strip() != FIXTURE_CLIENT_NAME:
        bad.append("client_name_is_fixture")
    if str(row.get("project_status") or "").strip() != FIXTURE_PROJECT_STATUS:
        bad.append("project_status_is_created")
    try:
        count = int(row.get("project_workpaper_count"))
    except (TypeError, ValueError):
        count = -1
    if count < 1 or count > FIXTURE_MAX_WORKPAPERS:
        bad.append("project_workpaper_count_within_cap")
    try:
        revision = int(row.get("content_revision") or 0)
    except (TypeError, ValueError):
        revision = -1
    if revision != FIXTURE_REQUIRED_REVISION:
        bad.append("target_revision_is_zero")
    return tuple(bad)

def assert_fixture_only(row: Mapping[str, Any]) -> None:
    """不是一次性夹具就抛。**没有** --force 开关。"""
    bad = fixture_violations(row)
    if bad:
        raise FixtureGuardError(
            "目标不在授权范围内（只允许一次性测试夹具项目）。违反判据: "
            + ", ".join(bad)
            + f"；实得 client_name={row.get('client_name')} "
            + f"status={row.get('project_status')} "
            + f"wp_count={row.get('project_workpaper_count')} "
            + f"content_revision={row.get('content_revision')}"
        )


@dataclass(frozen=True)
class FixtureTarget:
    project_id: uuid.UUID
    wp_id: uuid.UUID
    wp_code: str
    project_name: str
    client_name: str
    project_status: str
    project_workpaper_count: int
    content_revision: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": str(self.project_id),
            "wp_id": str(self.wp_id),
            "wp_code": self.wp_code,
            "project_name": self.project_name,
            "client_name": self.client_name,
            "project_status": self.project_status,
            "project_workpaper_count": self.project_workpaper_count,
            "content_revision": self.content_revision,
        }

_TARGET_SQL = (
    "SELECT wp.id AS wp_id, wp.project_id AS project_id, "
    "COALESCE(wp.content_revision, 0) AS content_revision, "
    "wi.wp_code AS wp_code, p.name AS project_name, "
    "p.client_name AS client_name, p.status AS project_status, "
    "(SELECT count(*) FROM working_paper w2 WHERE w2.project_id = p.id "
    " AND w2.is_deleted = false) AS project_workpaper_count "
    "FROM working_paper wp "
    "JOIN projects p ON p.id = wp.project_id "
    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
    "WHERE wp.is_deleted = false AND wi.wp_code = :code "
    "  AND p.client_name = :client AND p.status = :status "
)

async def resolve_fixture_target(
    session: Any, *, wp_code: str, project_id: uuid.UUID | None = None
) -> FixtureTarget:
    """按 wp_code 在夹具项目里取一条确定性目标；查不到给显式原因。"""
    sql = _TARGET_SQL
    params: dict[str, Any] = {
        "code": wp_code,
        "client": FIXTURE_CLIENT_NAME,
        "status": FIXTURE_PROJECT_STATUS,
    }
    if project_id is not None:
        sql += "AND p.id = :pid "
        params["pid"] = str(project_id)
    sql += "ORDER BY " + TARGET_ORDER_SQL + " LIMIT 1"
    hit = (await session.execute(sa.text(sql), params)).mappings().first()
    if hit is None:
        raise BootstrapScriptError(
            f"夹具项目里没有 wp_code={wp_code} 的未删除底稿"
            f"（client_name={FIXTURE_CLIENT_NAME} status={FIXTURE_PROJECT_STATUS}）"
            " —— 不得改用真实客户项目"
        )
    assert_fixture_only(hit)
    return FixtureTarget(
        project_id=uuid.UUID(str(hit["project_id"])),
        wp_id=uuid.UUID(str(hit["wp_id"])),
        wp_code=str(hit["wp_code"]),
        project_name=str(hit["project_name"]),
        client_name=str(hit["client_name"]),
        project_status=str(hit["project_status"]),
        project_workpaper_count=int(hit["project_workpaper_count"]),
        content_revision=int(hit["content_revision"]),
    )

# ═══════════════════════════════════════════════════════════════════════════
# 4. 快照与不变量（apply 前后各取一次，差值即写入面）
# ═══════════════════════════════════════════════════════════════════════════


#: 本脚本**允许**新增行的 sync 域表（写入面的封闭清单）。
SYNC_DOMAIN_TABLES: tuple[str, ...] = (
    "working_paper_sync_entry_state",
    "working_paper_content_version",
    "working_paper_content_representation",
    "working_paper_artifact",
)

#: 只读观测、本脚本不应改变的 sync 域表（差值必须为 0）。
UNTOUCHED_TABLES: tuple[str, ...] = (
    "working_paper_sync_definition_artifact",
    "working_paper_sync_definition_bundle",
    "working_paper_representation_upgrade_candidate",
    "working_paper_oo_room",
    "working_paper_content_application",
)

async def snapshot(session: Any) -> dict[str, Any]:
    """sync 域行数 + 业务行不变量的一次现算快照。"""
    counts: dict[str, int] = {}
    for table in SYNC_DOMAIN_TABLES + UNTOUCHED_TABLES:
        value = (
            await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
        ).scalar_one()
        counts[table] = int(value)
    touched = (
        await session.execute(
            sa.text(
                "SELECT wp.id AS wp_id, p.client_name AS client_name, "
                "COALESCE(wp.content_revision, 0) AS content_revision, "
                "(wp.current_content_version_id IS NOT NULL) AS has_cv "
                "FROM working_paper wp JOIN projects p ON p.id = wp.project_id "
                "WHERE wp.is_deleted = false AND ("
                "  COALESCE(wp.content_revision, 0) <> 0 "
                "  OR wp.current_content_version_id IS NOT NULL) "
                "ORDER BY wp.id"
            )
        )
    ).mappings().all()
    return {
        "counts": counts,
        "business_rows_touched": [
            {
                "wp_id": str(r["wp_id"]),
                "client_name": r["client_name"],
                "content_revision": int(r["content_revision"]),
                "has_current_content_version": bool(r["has_cv"]),
                "is_fixture_client": r["client_name"] == FIXTURE_CLIENT_NAME,
            }
            for r in touched
        ],
    }

def verdict_of(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    target: FixtureTarget,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """apply 后的判据集合。任一 False 即整体失败（写入面越界或首版没成）。"""
    b = before["counts"]
    a = after["counts"]
    touched = list(after["business_rows_touched"])
    non_fixture = [r for r in touched if not r["is_fixture_client"]]
    rows = [r for r in touched if r["wp_id"] == str(target.wp_id)]
    checks = {
        "representation_supply_now_nonzero": a["working_paper_content_representation"] >= 1,
        "content_version_created": a["working_paper_content_version"]
        == b["working_paper_content_version"] + 1,
        "entry_pointer_created": a["working_paper_sync_entry_state"]
        == b["working_paper_sync_entry_state"] + 1,
        "representation_created": a["working_paper_content_representation"]
        == b["working_paper_content_representation"] + 1,
        "artifact_row_added": a["working_paper_artifact"] > b["working_paper_artifact"],
        "no_untouched_table_moved": all(a[t] == b[t] for t in UNTOUCHED_TABLES),
        "only_fixture_business_row_touched": len(non_fixture) == 0,
        "fixture_row_is_the_target": len(rows) == 1,
    }
    return {"checks": checks, "_rows": rows, "_non_fixture": non_fixture, "_b": b, "_a": a}

def extend_verdict(verdict: dict[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """把 receipt 侧四条判据并进 verdict，并结算 failed 清单。"""
    rows = verdict.pop("_rows")
    non_fixture = verdict.pop("_non_fixture")
    verdict.pop("_b")
    verdict.pop("_a")
    checks = verdict["checks"]
    checks["fixture_revision_is_one"] = bool(rows) and rows[0]["content_revision"] == 1
    checks["fixture_has_current_content_version"] = bool(rows) and rows[0][
        "has_current_content_version"
    ]
    checks["receipt_revision_is_one"] = int(receipt.get("revision") or 0) == 1
    checks["receipt_generation_is_one"] = (
        int(receipt.get("representation_generation") or 0) == 1
    )
    checks["receipt_commit_count_is_one"] = int(receipt.get("commit_count") or 0) == 1
    checks["receipt_single_transaction"] = (
        len(set(receipt.get("transaction_ids") or [])) == 1
    )
    verdict["failed"] = sorted(k for k, v in checks.items() if not v)
    verdict["non_fixture_business_rows"] = non_fixture
    return verdict

def already_bootstrapped(counts: Mapping[str, Any]) -> bool:
    """供给是否已存在（首版已产出）。

    做成纯函数是为了让「已引导」这条短路可被守卫喂合成计数验证 —— 否则它只能靠
    「库里恰好有行」来触发，等于没判据。
    """
    return int(counts.get("working_paper_content_representation") or 0) >= 1


async def bootstrapped_report(session: Any, *, mode: str) -> dict[str, Any] | None:
    """已引导时返回 no-op 报告；否则返回 None（继续正常流程）。

    有它之后 --check 才是真健康检查、--apply 才是幂等的：本脚本只产**首版**，
    夹具底稿一旦 content_revision=1，夹具门的 target_revision_is_zero 就会拒绝它，
    没有这条短路就会把「已经成功过」误报成「越权」。
    """
    snap = await snapshot(session)
    if not already_bootstrapped(snap["counts"]):
        return None
    return {
        "mode": mode,
        "binding_constraint": "BP-61-1",
        "already_bootstrapped": True,
        "supply": snap,
        "note": (
            "平台已存在 published representation —— 本脚本只产首版，此次为 no-op。"
            "要给**别的 entry** 建供给请走该 entry 自己的 lane，不要复用本宿主。"
        ),
        "errors": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. 两种模式
# ═══════════════════════════════════════════════════════════════════════════


async def run_check(session: Any, *, contract_logical_id: str,
                    project_id: uuid.UUID | None) -> dict[str, Any]:
    """只读：把 apply 会做的每一步前置都真跑一遍，一行不写。"""
    from app.services.workpaper_sync.writer_migration import opaque_entry_id

    done = await bootstrapped_report(session, mode="check")
    if done is not None:
        return done
    facts = lane_facts()
    template = await load_frozen_template(session, contract_logical_id=contract_logical_id)
    target = await resolve_fixture_target(
        session, wp_code=template.wp_code, project_id=project_id
    )
    before = await snapshot(session)
    entry_id = opaque_entry_id(wp_code=None, wp_id=target.wp_id)
    return {
        "mode": "check",
        "binding_constraint": "BP-61-1",
        "lane": facts,
        "template": template.as_dict(),
        "target": target.as_dict(),
        "entry_id": entry_id,
        "expected_revision": target.content_revision,
        "before": before,
        "would_write": {
            "sync_domain_rows": list(SYNC_DOMAIN_TABLES),
            "business_columns": [
                "working_paper.content_revision",
                "working_paper.current_content_version_id",
            ],
        },
        "errors": [],
    }

async def run_apply(
    Session: Any, *, contract_logical_id: str, project_id: uuid.UUID | None
) -> dict[str, Any]:
    """真提交一次首版。commit 由 ContentMutationService 内部单次执行。"""
    from app.services.workpaper_sync.content_mutation import UPLOAD
    from app.services.workpaper_sync.writer_migration import (
        build_content_mutation_service_writer,
        opaque_entry_id,
    )

    async with Session() as session:
        done = await bootstrapped_report(session, mode="apply")
        if done is not None:
            return done
    facts = lane_facts()
    async with Session() as session:
        template = await load_frozen_template(
            session, contract_logical_id=contract_logical_id
        )
        target = await resolve_fixture_target(
            session, wp_code=template.wp_code, project_id=project_id
        )
        before = await snapshot(session)
    receipt_dict: dict[str, Any] = {}
    async with Session() as session:
        writer = build_content_mutation_service_writer(session)
        expected = await writer.current_revision(target.wp_id)
        if expected != FIXTURE_REQUIRED_REVISION:
            raise FixtureGuardError(
                f"目标底稿 content_revision={expected} 已非 0 —— 本脚本只产首版，"
                "不在已有版本上追加"
            )
        entry_id = opaque_entry_id(wp_code=None, wp_id=target.wp_id)
        receipt = await writer.commit_bytes(
            project_id=target.project_id,
            wp_id=target.wp_id,
            entry_id=entry_id,
            source=UPLOAD,
            payload=template.payload,
            document_type="xlsx",
            expected_revision=expected,
            substrate_path=template.absolute_path,
            lane_id=LANE_ID,
        )
        receipt_dict = receipt.as_dict()
        receipt_dict["representation_generation"] = receipt.representation_generation
        receipt_dict["commit_count"] = receipt.commit_count
        receipt_dict["transaction_ids"] = list(receipt.transaction_ids)
        await writer.publish_committed_events(receipt)
    async with Session() as session:
        after = await snapshot(session)
    verdict = extend_verdict(
        verdict_of(before, after, target, receipt_dict), receipt_dict
    )
    return {
        "mode": "apply",
        "binding_constraint": "BP-61-1",
        "lane": facts,
        "template": template.as_dict(),
        "target": target.as_dict(),
        "entry_id": entry_id,
        "expected_revision": expected,
        "before": before,
        "after": after,
        "receipt": receipt_dict,
        "verification": verdict,
        "errors": [f"判据未通过: {name}" for name in verdict["failed"]],
    }

# ═══════════════════════════════════════════════════════════════════════════
# 6. CLI
# ═══════════════════════════════════════════════════════════════════════════


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 61 首版 published representation 引导")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读预演（默认）")
    mode.add_argument("--apply", action="store_true", help="真提交一次首版")
    parser.add_argument("--contract", default=DEFAULT_CONTRACT_LOGICAL_ID)
    parser.add_argument("--project-id", default=None, help="限定夹具 project")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise BootstrapScriptError(
            "本脚本写 V151/V153 的真实表（含 CHECK/trigger），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project_filter = uuid.UUID(args.project_id) if args.project_id else None
    try:
        if args.apply:
            report = await run_apply(
                Session, contract_logical_id=args.contract, project_id=project_filter
            )
        else:
            async with Session() as session:
                report = await run_check(
                    session, contract_logical_id=args.contract, project_id=project_filter
                )
    finally:
        await engine.dispose()

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)
    if report["errors"]:
        raise BootstrapScriptError(
            f"{len(report['errors'])} 条判据未通过 —— 不降级为成功"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
