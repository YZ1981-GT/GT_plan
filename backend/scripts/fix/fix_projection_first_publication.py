#!/usr/bin/env python
"""`projection_contract` lane 首版 published representation 的**唯一**幂等宿主。

**Spec: published-representation-production-path-and-lane-adjudication**
Requirements: 6.1~6.11（宿主）、11.1~11.7（真实环境验证）
Tasks: 6.1（`--check` 只读预演）、6.3（`--apply` 逐 entry 独立事务）

═══ 为什么需要这个脚本 ════════════════════════════════════════════════════════

`working_paper_sync_entry_state` / `working_paper_content_representation` 里
`projection_contract` lane 的行数实测为 **0**，导致：

* 四个 Excel pilot 的 `adapter_registered` 恒 `False`；
* manifest 186 条 entry 的 `adapter_id` 恒 `null`；
* 前端 `SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 恒为空集合，于是每个宿主都必须显示
  「两侧数据未互通」（AC 1.4 的诚实标识）。

它们不是三个独立缺陷，是同一条供给链的同一个断点。本脚本就是那条链的生产入口。

═══ 用法 ════════════════════════════════════════════════════════════════════

    # 只读预演（一行库都不写）
    python backend/scripts/fix/fix_projection_first_publication.py --check
    python backend/scripts/fix/fix_projection_first_publication.py --check --json out.json

    # 真发布（逐 entry 独立事务）
    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/fix/fix_projection_first_publication.py --apply
    python backend/scripts/fix/fix_projection_first_publication.py --apply --entry xlsx/gt-h1-fixed-assets

🔴 **判成败一律查数据，不看退出码** —— `--apply` 可能被 Ctrl+C 中断而部分 entry 已提交。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.services.workpaper_sync import (  # noqa: E402
    projection_target_resolution as _TARGET_RESOLUTION,
)

logger = logging.getLogger("fix_projection_first_publication")


# ═══════════════════════════════════════════════════════════════════════════
# 封闭结算词表（Requirement 6.3）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 必须是封闭集。自由文本会让守卫只能比字符串，而「结算落在哪一格」正是本脚本
#    唯一对外承诺的东西 —— 它必须可枚举、可断言、可在 CI 里当基线。

CHECK_ENTRY_STATES: Final[tuple[str, ...]] = (
    "ready_to_publish",
    "blocked_missing_approved_bundle",
    "blocked_ooxml_gate",
    "blocked_contract_not_reviewed",
    "blocked_lane_undecided",
    "already_published",
    # ── 2026-09-04 扩：`--check` 补跑 materialize / roundtrip / 未管理区域三段后
    #    才暴露出来的三类真实阻塞（此前它们全部落进 `blocked_contract_not_reviewed`，
    #    那是**误导性结算** —— 契约明明已 reviewed，报告却说「契约未复核」，
    #    读报告的人会被送到错的解除方）──────────────────────────────────
    "blocked_row_insertion_required",
    "blocked_template_contract_drift",
    "blocked_roundtrip_divergence",
    "blocked_unmanaged_region_drift",
    # ── 2026-09-05 扩：store 空且该 pilot 没有「空载荷」合法状态 ──────────
    #
    # 🔴 这一格**不是** blocked_*，因为它不是阻塞：它说的是「审计师还没在 HTML 侧
    #    录内容，因此还没到可发布的时候」。归进 `blocked_*` 会让运维去找解除方，
    #    而这里没有任何东西需要被解除 —— 要做的只是先录数据。
    #    起因：宿主曾用单一 `"[]"` 喂所有 provider，G7 的根形态是对象 ⇒ 必然
    #    `StorePayloadError` ⇒ 落进兜底格，把「还没录」误报成「词表要扩」。
    "store_empty_nothing_to_publish",
    # store 里**有**内容但形态不符（`sync_pilot_store_payload_invalid`）。
    # 与上一格严格区分：这里数据真的坏了或版本对不上，有明确解除方。
    "blocked_store_payload_shape",
    # 🔴 兜底格，语义 = **词表要扩**（不是「某种已知阻塞」）。它必须长得一眼就不对劲，
    #    才不会像 `blocked_contract_not_reviewed` 那样被当成一个正常结论读过去。
    "blocked_unregistered_failure_shape",
)

#: `error_code` → 结算格。**不**用 `except Exception` 兜底成某一格：未登记的
#: error_code 会让 `_settle_for` 抛，而不是静默落进 `blocked_*` 里某一格。
#:
#: materialize 侧的取值域是 `excel_materialize.FAILURE_KINDS` 的 10 个键 —— 那是权威
#: 登记表，本表按「解除方是谁」把它们归成两格，不逐条另起一格：
#:   * `row_set_divergence` 只能由**结构性插行**解除（另一条泳道的能力）；
#:   * 其余七条都是**契约声明与权威模板不一致**，解除动作是裁决契约或模板。
_ERROR_CODE_TO_STATE: Final[Mapping[str, str]] = {
    "projection_bundle_not_provisioned": "blocked_missing_approved_bundle",
    "ooxml_security_rejected": "blocked_ooxml_gate",
    "contract_not_reviewed": "blocked_contract_not_reviewed",
    "lane_undecided": "blocked_lane_undecided",
    "lane_is_opaque": "blocked_lane_undecided",
    "first_publication_already_done": "already_published",
    # ── materialize：需要结构性插行 ────────────────────────────────
    "excel_materialize_row_set_divergence": "blocked_row_insertion_required",
    # ── materialize：契约 ↔ 权威模板漂移 ──────────────────────────
    "excel_materialize_editable_write_failed": "blocked_template_contract_drift",
    "excel_materialize_protected_region_violation": "blocked_template_contract_drift",
    "excel_materialize_shared_formula_master_write": "blocked_template_contract_drift",
    "excel_materialize_row_identity_write_failed": "blocked_template_contract_drift",
    "excel_materialize_dynamic_column_binding_unusable": (
        "blocked_template_contract_drift"
    ),
    "excel_materialize_footer_anchor_drift": "blocked_template_contract_drift",
    "excel_materialize_footer_formula_range_stale": "blocked_template_contract_drift",
    "excel_materialize_write_strategy_forbidden": "blocked_template_contract_drift",
    "excel_materialize_template_library_write": "blocked_template_contract_drift",
    "value_normalization_failed": "blocked_template_contract_drift",
    # ── 反读等值 / 未管理区域 ─────────────────────────────────────
    "roundtrip_projection_mismatch": "blocked_roundtrip_divergence",
    "excel_extract_roundtrip_not_equivalent": "blocked_roundtrip_divergence",
    "adapter_unmanaged_region_drift": "blocked_unmanaged_region_drift",
    # ── store 空且该 pilot 无「空载荷」合法状态（不是阻塞）────────────
    "store_payload_empty_and_not_publishable": "store_empty_nothing_to_publish",
    # 🔴 provider 的载荷形态不符 —— 此前**未登记**，于是它落进兜底格
    #    `blocked_unregistered_failure_shape`，把一个有明确解除方的情形报成
    #    「词表要扩」。它与「还没录」是两件事：这里是**数据真的坏了或形态不对**。
    "sync_pilot_store_payload_invalid": "blocked_store_payload_shape",
}

#: 结算格 → 解除方与解除动作。报告里必须写出来 —— 「卡住了」不带「谁能解」的
#: 结论会让每次复盘都要重新查一遍。
_STATE_UNBLOCK_OWNER: Final[Mapping[str, str]] = {
    "blocked_missing_approved_bundle": (
        "先跑 backend/scripts/fix/fix_task76_provision_projection_definitions.py"
    ),
    "blocked_ooxml_gate": "解除条件属安全策略裁决，不在首版发布 spec 范围内放宽",
    "blocked_contract_not_reviewed": (
        "契约复核方：把该 per-entry 契约的 `review_status` 推到 `reviewed`"
        "（本入口不放宽该准入）"
    ),
    "blocked_lane_undecided": (
        "lane 裁决真源 `projection_lane_registry.adjudicate_lane`（L1~L5）—— "
        "判 opaque 说明该 entry 不走 projection lane；判 undecided 时诊断已点名"
        "首个不成立判据与其真源文件；另一种成因是裁决码族下没有存活底稿"
    ),
    "blocked_row_insertion_required": (
        "结构性插行泳道（excel-structural-row-insertion-and-shift-aware-verification "
        "的 Wave 4：plan_managed_writes 接 RowShiftPlan）"
    ),
    "blocked_template_contract_drift": (
        "契约/模板裁决：受管区行列范围或字段 value_type 与权威模板不一致"
    ),
    "blocked_roundtrip_divergence": (
        "materialize/extract 两侧口径裁决（写进去的与反读出来的不等值）"
    ),
    "blocked_unmanaged_region_drift": (
        "未管理区域策略裁决（本次写入动到了被逐字节锁死的部件）"
    ),
    "store_empty_nothing_to_publish": (
        "🔴 无需解除 —— 这不是阻塞。该 entry 的 HTML store 还没有内容，"
        "而它的 provider 没有「空载荷」合法状态（如 G7：动态列数量必须由实测实体"
        "列表决定，空列表被 `iter_store_entities` 故意拒绝）。"
        "要做的是先在 HTML 侧录入数据，之后首版即可发布"
    ),
    "blocked_store_payload_shape": (
        "store 载荷形态裁决：`remark` 里有内容但不符合该 pilot 的 store schema"
        "（根形态错 / state version 对不上 / 必填结构缺失）—— "
        "解除方是前端 store 写入侧或数据修复，**不是**放宽 provider 的校验"
    ),
    "blocked_unregistered_failure_shape": (
        "🔴 词表要扩：把该 error_code 登记进 `_ERROR_CODE_TO_STATE` 并给出解除方"
    ),
}

#: 目标底稿的全序 —— 真源在生产模块，本宿主只**转引**。
#:
#: 🔴 BP-24：这里原来是本脚本自己的一份字面量，而 Task 76 的 provisioner 另有一份
#:    （没有 `has_store_payload` 那一项）。两份全序读同一张裁决表却选出不同底稿，
#:    实测 D2 / B60 两个 entry 分歧 ⇒ 已收敛到
#:    `app.services.workpaper_sync.projection_target_resolution`，理由与实证写在那里。
TARGET_ORDER_SQL: Final[str] = _TARGET_RESOLUTION.TARGET_ORDER_SQL


class HostError(RuntimeError):
    """宿主自身的装配/判据失败（与被调用服务层的域异常区分开）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 结算记录
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class EntrySettlement:
    entry_id: str
    contract_id: str = ""
    #: 裁决表给出的目标码族（可能多于一个）
    adjudicated_wp_codes: list[str] = field(default_factory=list)
    #: 实际选中的那个底稿的 wp_code（解析成功后才有值）
    wp_code: str = ""
    project_id: str = ""
    wp_id: str = ""
    store_bytes: int = 0
    state: str = ""
    error_code: str = ""
    diagnosis: str = ""
    #: 链路各阶段是否真的跑到（`--check` 的「跑完全链」判据落点）
    stages: dict[str, bool] = field(default_factory=dict)
    #: 现算 projection 的规模（字段数 / 每张表行数）—— 用来分辨「空首版」与「要插行」
    projection_facts: dict[str, Any] = field(default_factory=dict)
    #: 发布成功后的产出身份
    published: dict[str, Any] = field(default_factory=dict)


def _settle_for(error_code: str) -> str:
    """把服务层 error_code 映射到封闭结算格；未登记即抛（不静默归类）。"""
    if error_code not in _ERROR_CODE_TO_STATE:
        raise HostError(
            f"未登记的 error_code {error_code!r} —— 结算词表是封闭集，"
            f"新增失败形态必须显式登记进 `_ERROR_CODE_TO_STATE`，"
            f"不得让它静默落进某个 blocked 格"
        )
    return _ERROR_CODE_TO_STATE[error_code]


def _settle_exception(
    settlement: EntrySettlement, exc: BaseException, *, phase: str
) -> None:
    """把一个真实异常落成结算格 + 带解除方的诊断。

    🔴 **绝不**把未登记形态伪装成某个已知格。此前 `--check` 与 `--apply` 都写着
    ``settlement.state = "blocked_contract_not_reviewed"`` 作为 `except` 兜底，后果是
    H1 的「A27 的 `……` 无法按 integer 规范化」和 D2 的「729 个行身份需要结构性插行」
    双双被报成「契约未复核」—— 而两份契约都是 reviewed 的。读报告的人会去查契约复核
    状态，而真正的解除方一个是模板裁决、一个是另一条泳道的插行能力。
    """
    code = str(getattr(exc, "error_code", "") or type(exc).__name__)
    settlement.error_code = code
    try:
        settlement.state = _settle_for(code)
    except HostError:
        settlement.state = "blocked_unregistered_failure_shape"
    owner = _STATE_UNBLOCK_OWNER.get(settlement.state, "")
    settlement.diagnosis = (
        f"{phase} 阶段失败: {type(exc).__name__}: {str(exc)[:320]}"
        + (f"｜解除方：{owner}" if owner else "")
    )


# ═══════════════════════════════════════════════════════════════════════════
# 现算目标清单（不写第二份 entry 清单）
# ═══════════════════════════════════════════════════════════════════════════


#: entry → wp_code 的**唯一** reviewed 真源（路径与读取规则都在生产模块里）。
_WP_CODE_ADJUDICATION: Final[Path] = _TARGET_RESOLUTION.WP_CODE_ADJUDICATION


def _adjudicated_wp_codes(entry_id: str) -> tuple[str, ...]:
    """转引生产侧的裁决表读取（BP-24：本宿主不再自留第二份实现）。

    只把域异常翻成本宿主的 :class:`HostError`，让 `--check` / `--apply` 的结算词表不变。
    """
    try:
        return _TARGET_RESOLUTION.adjudicated_wp_codes(entry_id)
    except _TARGET_RESOLUTION.ProjectionTargetResolutionError as exc:
        raise HostError(str(exc)) from exc


async def _resolve_target(
    session: Any, *, wp_codes: Sequence[str], store_item_id: str
) -> Any | None:
    """转引生产侧的目标解析（BP-24）。返回行含 `store_bytes`，全序第一项就是它。"""
    return await _TARGET_RESOLUTION.resolve_projection_target(
        session, wp_codes=wp_codes, store_item_id=store_item_id
    )


async def _no_target_diagnosis(session: Any, *, wp_codes: Sequence[str]) -> str:
    """无目标时的诊断文案。**必须**区分「一条都没有」与「有但都不可见」（BP-26）。

    这两种情形的解除动作完全不同：前者要建底稿，后者要恢复项目或换目标项目。
    统一报「没有存活底稿」会把读报告的人导向错误的动作 —— 与本脚本删掉那两处
    `blocked_contract_not_reviewed` 误导性兜底是同一类问题。
    """
    hidden = await _TARGET_RESOLUTION.count_candidates_hidden_by_visibility(
        session, wp_codes=list(wp_codes)
    )
    if hidden:
        return (
            f"裁决码族 {list(wp_codes)} 下有 {hidden} 条底稿，但**全部不可见**"
            "（所在项目已删除 / 索引行已删除 / 底稿本身已删除）—— 前端 render-config "
            "对这类底稿返回 404，发在它们上面的 representation 审计师打不开。"
            "解除动作是恢复项目或改裁决表指向可见项目，不是新建底稿"
        )
    return f"裁决码族 {list(wp_codes)} 下没有存活底稿，无目标可发布"


class EmptyStoreNotPublishableError(HostError):
    """该 entry 的 store 是空的，而它的 provider 没有「空载荷」这个合法状态。

    🔴 这不是错误处理的兜底，而是一个**独立的业务结论**：
    「审计师还没在 HTML 侧录任何内容，因此没有可发布的首版」。

    只有当 provider 的 :data:`EMPTY_STORE_PAYLOAD` 是 `None` 时才会抛（当前仅 G7）。
    它的动态列数量由实测实体列表决定，而空列表是被 `iter_store_entities` 故意拒绝的
    状态 —— 不存在「既是空的、又能产出合法 projection」的载荷。
    """

    error_code = "store_payload_empty_and_not_publishable"


def _empty_store_payload_for(provider: Any, *, entry_id: str) -> str:
    """取该 provider 自己声明的空 store 载荷。

    🔴 **问 provider，不用通用常量。**
    2026-09-05 实测：宿主此前用单一 `_EMPTY_STORE_PAYLOAD = "[]"` 喂全部四个 pilot，
    而 G7 的载荷根形态是**对象**不是数组 ⇒ 它必然 `StorePayloadError`，且该 error_code
    未登记进 `_ERROR_CODE_TO_STATE` ⇒ 落进 `blocked_unregistered_failure_shape` 兜底格。
    这条路径此前从未被走到，因为真库上 G7 已发布 ⇒ 判据 ③ 在 `_read_store_payload`
    **之前**就拦住了它（`resolve_plan` L731 vs 本函数 L752）；干净库上就会崩。

    「空载荷长什么样」由各 pilot 的 store schema 决定，只有 provider 自己知道。
    未声明即抛 —— 不猜一个形状（猜错会把「数据形态不符」伪装成「还没录」）。
    """
    if not hasattr(provider, "EMPTY_STORE_PAYLOAD"):
        raise HostError(
            f"{entry_id} 的 provider {provider.__name__} 未声明 `EMPTY_STORE_PAYLOAD` "
            "—— 空载荷的形态由各 pilot 的 store schema 决定，宿主不替它猜。"
            "请在 provider 里显式声明（无空载荷状态的写 `None`）"
        )
    payload = getattr(provider, "EMPTY_STORE_PAYLOAD")
    if payload is None:
        raise EmptyStoreNotPublishableError(
            f"{entry_id} 的 store 无记录，而该 pilot 没有「空载荷」这个合法状态"
            f"（`{provider.__name__}.EMPTY_STORE_PAYLOAD is None`）—— "
            "首版需要 HTML 侧先录入内容；这不是阻塞，是还没到可发布的时候"
        )
    return str(payload)


async def _read_store_payload(
    session: Any,
    *,
    wp_id: uuid.UUID,
    store_item_id: str,
    provider: Any,
    entry_id: str,
) -> str:
    """读该 entry 的 HTML store 载荷；无记录/空白时取 provider 声明的空载荷。

    只有「记录不存在」或「remark 全空白」才归一成 provider 的空载荷表示。
    非空但非法的 JSON **不**在这里兜底 —— 那是真实的数据损坏，必须让 provider 的
    `StorePayloadError` 响亮抛出，而不是被我们悄悄换成空行集（那会把「数据坏了」
    伪装成「还没录」，首版就发布出一份内容错误的 representation）。
    """
    row = (
        await session.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
            ),
            {"wp": str(wp_id), "item": store_item_id},
        )
    ).scalar_one_or_none()
    if row is None:
        return _empty_store_payload_for(provider, entry_id=entry_id)
    text = str(row)
    if text.strip():
        return text
    return _empty_store_payload_for(provider, entry_id=entry_id)


def _build_plan_rows() -> list[Mapping[str, Any]]:
    """从 `DELIVERED_PER_ENTRY_CONTRACTS` × provider 常量现算目标清单。"""
    import importlib

    from app.services.workpaper_sync.adapters import registry as registry_module

    rows: list[Mapping[str, Any]] = []
    for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        module_path = str(row["provider_module"])
        if module_path not in registry_module._ALLOWED_PROVIDER_MODULES:
            raise HostError(
                f"provider_module {module_path!r} 不在 registry 白名单内 —— "
                "宿主不放宽该判据"
            )
        provider = importlib.import_module(module_path)
        entry_id = str(row["entry_id"])
        rows.append(
            {
                "entry_id": entry_id,
                "contract_id": str(row["contract_id"]),
                "provider": provider,
                "wp_codes": _adjudicated_wp_codes(entry_id),
                "store_item_id": str(getattr(provider, "STORE_ITEM_ID", "") or ""),
            }
        )
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 引擎
# ═══════════════════════════════════════════════════════════════════════════


def _engine():
    """独立 `NullPool` 引擎。

    🔴 判据是**实参** `poolclass=NullPool`：复用 `app.core.database.async_session` 会把
    连接留在共享池里，而那些连接绑定在已关闭的 event loop 上 —— 第二次 `asyncio.run`
    取到它就报 `'NoneType' object has no attribute 'send'`（Task 61 实测踩过）。
    """
    from app.core.config import settings

    return create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
        echo=False,
    )


def _artifacts():
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    # 🔴 BP-29：根必须是 `BACKEND_ROOT`（= `backend/`），**不是** `storage_root()`
    #    （= `backend/storage`）。artifact 的 `relative_path` 自带 `storage/` 前缀 ⇒
    #    用 `storage_root()` 会写出双层 `backend/storage/storage/...`，而全平台其余
    #    10 处读取方（含生产请求路径 `wp_sync_router`）都用 `BACKEND_ROOT`
    #    ⇒ 发布出来的 representation 一律读不到（实测 142 : 4）。
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    return CanonicalArtifactRepository(BACKEND_ROOT)


# ═══════════════════════════════════════════════════════════════════════════
# --check（Task 6.1 / Requirement 6.2：只读且跑完全链）
# ═══════════════════════════════════════════════════════════════════════════

#: 链路阶段。`--check` 必须**每一个都真的执行到**，只断言「没写库」会让
#: 「什么都没跑」也通过（Property 22 的双侧判据）。
#:
#: 🔴 2026-09-04 从 6 阶段扩到 10 阶段。此前止步于 `adapter_built`，于是 H1 / D2 双双
#:    报 `ready_to_publish` 而 `--apply` 双双失败（H1 撞 A27 的 `……` 无法按 integer
#:    规范化、D2 撞 729 个行身份需要结构性插行）—— 预演说能发、真发发不出，这就是
#:    **假绿**：Requirement 6.2 要的「跑完全链」，链条的后四段一段都没跑。
#:    这四段全在文件侧（临时目录），仍然零 DB 写入。
CHECK_STAGES: Final[tuple[str, ...]] = (
    "lane_adjudicated",
    "supply_observed",
    "plan_resolved",
    "substrate_instrumented",
    "ooxml_gate_passed",
    "adapter_built",
    "projection_composed",
    "materialized",
    "roundtrip_verified",
    "unmanaged_regions_verified",
)


async def run_check(
    *, only_entry: str | None = None
) -> list[EntrySettlement]:
    """只读预演。逐 entry 跑完六个阶段，**一行库都不写**。"""
    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync import projection_lane_registry as REG
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.content_mutation import ContentMutationService
    from app.services.workpaper_sync.excel_entry_gate import (
        AdapterBuild,
        ExcelEntryDefinitionLoader,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    artifacts = _artifacts()
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    results: list[EntrySettlement] = []

    try:
        for row in _build_plan_rows():
            entry_id = row["entry_id"]
            if only_entry and entry_id != only_entry:
                continue
            settlement = EntrySettlement(
                entry_id=entry_id,
                contract_id=row["contract_id"],
                adjudicated_wp_codes=list(row["wp_codes"]),
                stages={name: False for name in CHECK_STAGES},
            )
            results.append(settlement)
            provider = row["provider"]

            async with Session() as session:
                resolution = CanonicalResolutionService(session, artifacts)

                # ── 阶段 1：lane 裁决 ──────────────────────────────
                verdict = REG.adjudicate_lane(entry_id)
                settlement.stages["lane_adjudicated"] = True
                if verdict is not REG.LaneVerdict.projection:
                    settlement.state = "blocked_lane_undecided"
                    settlement.error_code = (
                        "lane_is_opaque"
                        if verdict is REG.LaneVerdict.opaque
                        else "lane_undecided"
                    )
                    settlement.diagnosis = f"lane 裁决为 {verdict.value}"
                    continue

                target = await _resolve_target(
                    session,
                    wp_codes=row["wp_codes"],
                    store_item_id=row["store_item_id"],
                )
                if target is None:
                    settlement.state = "blocked_lane_undecided"
                    settlement.error_code = "lane_undecided"
                    settlement.diagnosis = await _no_target_diagnosis(
                        session, wp_codes=row["wp_codes"]
                    )
                    continue
                settlement.project_id = str(target.project_id)
                settlement.wp_id = str(target.wp_id)
                settlement.wp_code = str(target.wp_code)
                settlement.store_bytes = int(target.store_bytes or 0)

                # ── 阶段 2：供给四条判据 ───────────────────────────
                facts = await REG.observe_lane_supply(
                    session=session,
                    project_id=target.project_id,
                    wp_id=target.wp_id,
                    entry_id=entry_id,
                )
                settlement.stages["supply_observed"] = True

                # ── 阶段 3：五条准入 ──────────────────────────────
                try:
                    plan = await F2.resolve_plan(
                        session=session,
                        resolution=resolution,
                        project_id=target.project_id,
                        wp_id=target.wp_id,
                        entry_id=entry_id,
                    )
                    settlement.stages["plan_resolved"] = True
                except (F2.FirstPublicationError, REG.LaneRegistryError) as exc:
                    _settle_exception(settlement, exc, phase="五条准入")
                    continue

                # ── 阶段 4/5：instrumentation + OOXML 安全门 ──────
                with tempfile.TemporaryDirectory(prefix="tmp_fpcheck_") as td:
                    try:
                        staged = F2.stage_instrumented_substrate(
                            entry_id=entry_id,
                            staging_dir=Path(td),
                            contract=plan.contract,
                        )
                        settlement.stages["substrate_instrumented"] = True
                        settlement.stages["ooxml_gate_passed"] = True
                    except F2.FirstPublicationError as exc:
                        settlement.error_code = str(getattr(exc, "error_code", ""))
                        settlement.state = _settle_for(settlement.error_code)
                        gate = str(getattr(exc, "gate", "") or "")
                        settlement.diagnosis = (
                            f"{str(exc)[:300]}"
                            + (
                                f"｜解除条件属安全策略裁决（gate={gate}），"
                                "不在本 spec 范围内放宽"
                                if gate
                                else ""
                            )
                        )
                        continue

                    # ── 阶段 6：loader + adapter（仍不写库）──────
                    try:
                        loader = ExcelEntryDefinitionLoader(
                            session=session, resolution=resolution
                        )
                        adapter_build = AdapterBuild(
                            adapter_id=plan.contract_id,
                            adapter_build_digest=F2._adapter_build_digest(
                                plan.contract_id
                            ),
                            document_type=plan.document_type,
                            contract_version=str(plan.contract.semantic_version),
                        )
                        definitions = await loader.load(
                            entry_id=entry_id,
                            frozen_bundle_id=plan.bundle.bundle_id,
                            frozen_bundle_sha256=plan.bundle.bundle_sha256,
                            adapter_build=adapter_build,
                            identity_inventory=staged.identity_inventory,
                            observed_structure=staged.observed_structure,
                            observed_business_sheets=staged.observed_business_sheets,
                            observed_dynamic_columns=staged.observed_dynamic_columns,
                        )
                        adapter = build_excel_adapter(
                            definitions=definitions,
                            binding=F2._identity_binding(
                                provider=provider,
                                staged=staged,
                                contract=plan.contract,
                            ),
                            direction=F2.FIRST_PUBLICATION_DIRECTION,
                        )
                        settlement.stages["adapter_built"] = True
                    except Exception as exc:
                        _settle_exception(settlement, exc, phase="loader/adapter")
                        continue

                    # ── 阶段 7~10：materialize → 反读等值 → 未管理区域 ──
                    #
                    # 🔴 这四段与 `--apply` 走**同一条**代码路径（同一个 projection
                    #    构造、同一个 adapter.materialize、同一个反读比对函数），
                    #    唯一差别是产物落在临时目录且不进事务。不同路径的预演等于
                    #    没有预演 —— 那正是此前 `ready_to_publish` 假绿的成因。
                    try:
                        store_payload = await _read_store_payload(
                            session,
                            wp_id=target.wp_id,
                            store_item_id=row["store_item_id"],
                            provider=provider,
                            entry_id=entry_id,
                        )
                        projection = F2._overlay_store_on_substrate_baseline(
                            adapter=adapter,
                            contract=plan.contract,
                            substrate=staged.staged_path,
                            store_projection=provider.build_store_projection(
                                store_payload, contract=plan.contract
                            ),
                        )
                        settlement.stages["projection_composed"] = True
                        settlement.projection_facts = {
                            "value_count": len(projection.values),
                            "row_keys": {
                                key: len(keys)
                                for key, keys in sorted(projection.row_keys.items())
                            },
                        }

                        output = Path(td) / f"materialized.{plan.document_type}"
                        materialized = adapter.materialize(
                            substrate=staged.staged_path,
                            projection=projection,
                            output=output,
                            contract=plan.contract,
                        )
                        settlement.stages["materialized"] = True

                        # 反读等值判据**复用**生产实现，不在宿主抄第二份比对口径
                        # （抄一份的后果不是更安全，而是任一侧被短路都不改变行为）。
                        ContentMutationService(
                            session=session,
                            repository=WorkpaperSyncRepository(session),
                            artifacts=artifacts,
                            resolution=resolution,
                        )._assert_roundtrip_equivalent(
                            intended=projection,
                            extracted=adapter.extract(
                                artifact=output, contract=plan.contract
                            ),
                            contract=plan.contract,
                        )
                        settlement.stages["roundtrip_verified"] = True

                        # 🔴 BP-23：三个结构性声明必须喂进去，否则插行 entry 必判漂移。
                        #    与 `ContentMutationService._stage_projection` 传的是**同一组**
                        #    值（都取自 materialize 返回的 `MaterializeResult`）——
                        #    宿主与生产 commit 路径不同参数就会造出「--check 绿而 --apply 红」
                        #    的假绿，那正是本宿主 docstring 反复警告的形态。
                        adapter.verify_unmanaged_regions(
                            before=staged.staged_path,
                            after=output,
                            contract=plan.contract,
                            row_shift=materialized.row_shift,
                            total_formula_rows=materialized.total_formula_rows,
                            propagation=materialized.workbook_row_change,
                        ).assert_equivalent()
                        settlement.stages["unmanaged_regions_verified"] = True
                    except Exception as exc:
                        _settle_exception(
                            settlement, exc, phase="materialize/roundtrip"
                        )
                        continue

                settlement.state = "ready_to_publish"
                settlement.diagnosis = (
                    f"全链十阶段通过；store 载荷 {settlement.store_bytes} 字节"
                    f"（0 字节仍是合法首版：空 projection + instrumented 载体）"
                )

            # session 结束即释放；--check 不 commit，任何隐式写入都会被回滚
    finally:
        await engine.dispose()

    return results


# ═══════════════════════════════════════════════════════════════════════════
# --apply（Task 6.3 / Requirements 6.6~6.8、6.11）
# ═══════════════════════════════════════════════════════════════════════════


async def run_apply(*, only_entry: str | None = None) -> list[EntrySettlement]:
    """只对 `--check` 结算为 `ready_to_publish` 的 entry 发布首版。

    🔴 **逐 (wp_id, entry_id) 独立事务**：绝不共用一个 `engine.begin()`。共用时一处失败
    会把前面已成功的 entry 一起回滚 —— 那是本仓库已踩过的坑（复原脚本第 3 步抛错把前两
    步撤回）。单 entry 失败只回滚它自己、继续后续 entry，最终以非零退出码报 ERROR。
    """
    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync import projection_lane_registry as REG
    from app.services.workpaper_sync.outbox import DurableEventOutboxService
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    artifacts = _artifacts()
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    results: list[EntrySettlement] = []

    try:
        for row in _build_plan_rows():
            entry_id = row["entry_id"]
            if only_entry and entry_id != only_entry:
                continue
            settlement = EntrySettlement(
                entry_id=entry_id,
                contract_id=row["contract_id"],
                adjudicated_wp_codes=list(row["wp_codes"]),
                stages={},
            )
            results.append(settlement)
            provider = row["provider"]

            # ── 每个 entry 一个独立 session/事务 ────────────────────
            async with Session() as session:
                try:
                    resolution = CanonicalResolutionService(session, artifacts)
                    repository = WorkpaperSyncRepository(session)

                    target = await _resolve_target(
                        session,
                        wp_codes=row["wp_codes"],
                        store_item_id=row["store_item_id"],
                    )
                    if target is None:
                        settlement.state = "blocked_lane_undecided"
                        settlement.error_code = "lane_undecided"
                        settlement.diagnosis = await _no_target_diagnosis(
                            session, wp_codes=row["wp_codes"]
                        )
                        continue
                    settlement.project_id = str(target.project_id)
                    settlement.wp_id = str(target.wp_id)
                    settlement.wp_code = str(target.wp_code)
                    settlement.store_bytes = int(target.store_bytes or 0)

                    plan = await F2.resolve_plan(
                        session=session,
                        resolution=resolution,
                        project_id=target.project_id,
                        wp_id=target.wp_id,
                        entry_id=entry_id,
                    )

                    staging_dir = (
                        artifacts.resolve_within_project(
                            target.project_id, ".staging"
                        )
                        / str(target.wp_id)
                        / f"first-publication-{uuid.uuid4().hex[:12]}"
                    )
                    staged = F2.stage_instrumented_substrate(
                        entry_id=entry_id,
                        staging_dir=staging_dir,
                        contract=plan.contract,
                    )

                    store_payload = await _read_store_payload(
                        session,
                        wp_id=target.wp_id,
                        store_item_id=row["store_item_id"],
                        provider=provider,
                        entry_id=entry_id,
                    )

                    receipt = await F2.publish_first_generation(
                        session=session,
                        resolution=resolution,
                        artifacts=artifacts,
                        repository=repository,
                        plan=plan,
                        staged=staged,
                        store_payload=store_payload,
                    )
                    await session.commit()
                    try:
                        await DurableEventOutboxService.publish_pending(session)
                    except Exception as exc:  # noqa: BLE001
                        # 事件发布失败已落成耐久 outbox 行，由 replay worker 重放。
                        # 内容已提交，这里不得把它翻成整体失败。
                        logger.error(
                            "outbox publish_pending 失败（内容已提交）entry=%s: %s",
                            entry_id,
                            exc,
                        )

                    settlement.state = "ready_to_publish"
                    settlement.published = _receipt_facts(receipt)
                    settlement.diagnosis = (
                        f"首版已发布；store 载荷 {settlement.store_bytes} 字节"
                    )
                except (F2.FirstPublicationError, REG.LaneRegistryError) as exc:
                    await session.rollback()
                    _settle_exception(settlement, exc, phase="首版发布（已回滚本 entry）")
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    _settle_exception(settlement, exc, phase="首版发布（已回滚本 entry）")
                    logger.error(
                        "首版发布失败 entry=%s: %s", entry_id, exc, exc_info=True
                    )
    finally:
        await engine.dispose()

    return results


def _receipt_facts(receipt: Any) -> dict[str, Any]:
    """从 commit receipt 摘出可复算身份（不保存整个对象）。"""
    out: dict[str, Any] = {}
    for name in (
        "revision",
        "content_version_id",
        "representation_id",
        "representation_generation",
        "artifact_sha256",
        "projection_sha256",
        "structure_hash",
        "identity_inventory_sha256",
    ):
        value = getattr(receipt, name, None)
        if value is not None:
            out[name] = str(value)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def _render(results: Sequence[EntrySettlement], *, mode: str) -> str:
    lines: list[str] = [f"=== fix_projection_first_publication --{mode} ==="]
    buckets: dict[str, int] = {}
    for item in results:
        buckets[item.state] = buckets.get(item.state, 0) + 1
        lines.append("")
        lines.append(f"  {item.entry_id}")
        lines.append(
            f"    state={item.state}"
            + (f" error_code={item.error_code}" if item.error_code else "")
        )
        lines.append(
            f"    裁决码族={item.adjudicated_wp_codes} 选中={item.wp_code or '—'} "
            f"wp_id={item.wp_id[:8] if item.wp_id else '—'} store={item.store_bytes}B"
        )
        if item.stages:
            done = [k for k, v in item.stages.items() if v]
            stalled = [k for k, v in item.stages.items() if not v]
            lines.append(f"    stages 已执行 {len(done)}/{len(item.stages)}")
            if stalled:
                lines.append(f"      止步于 {stalled[0]}（未执行 {stalled}）")
        if item.projection_facts:
            lines.append(f"    projection {item.projection_facts}")
        if item.published:
            for k, v in item.published.items():
                shown = v if len(v) <= 40 else v[:12] + "…"
                lines.append(f"      {k} = {shown}")
        if item.diagnosis:
            lines.append(f"    {item.diagnosis}")
    lines.append("")
    lines.append(f"  结算分布: {dict(sorted(buckets.items()))}")
    unknown = sorted(set(buckets) - set(CHECK_ENTRY_STATES))
    if unknown:
        lines.append(f"  🔴 出现封闭词表外的结算: {unknown}")
    if "blocked_unregistered_failure_shape" in buckets:
        lines.append(
            "  🔴 有 entry 的失败形态未登记进 `_ERROR_CODE_TO_STATE` —— "
            "词表必须扩，不得让它继续落在兜底格里"
        )
    owners = {
        state: _STATE_UNBLOCK_OWNER[state]
        for state in sorted(buckets)
        if state in _STATE_UNBLOCK_OWNER
    }
    if owners:
        lines.append("  解除方：")
        for state, owner in owners.items():
            lines.append(f"    {state} → {owner}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="projection lane 首版 published representation 宿主"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只读预演（不写库）")
    group.add_argument("--apply", action="store_true", help="真发布（逐 entry 独立事务）")
    parser.add_argument("--entry", default=None, help="只处理该 entry_id")
    parser.add_argument("--json", dest="json_path", default=None, help="结算快照落盘路径")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    mode = "check" if args.check else "apply"
    runner = run_check if args.check else run_apply
    results = asyncio.run(runner(only_entry=args.entry))

    report = _render(results, mode=mode)
    print(report)

    if args.json_path:
        # 🔴 脚本内写文件，**不**用 PowerShell 重定向：`>` / `Out-File` 会把 python 的
        #    UTF-8 中文腌成乱码。
        Path(args.json_path).write_text(
            json.dumps(
                {
                    "mode": mode,
                    "closed_vocabulary": list(CHECK_ENTRY_STATES),
                    "check_stages": list(CHECK_STAGES),
                    "error_code_to_state": dict(_ERROR_CODE_TO_STATE),
                    "state_unblock_owner": dict(_STATE_UNBLOCK_OWNER),
                    "target_order_sql": TARGET_ORDER_SQL,
                    "entries": [asdict(item) for item in results],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # 退出码只是提示；判成败一律查数据（`--apply` 可能被中断而部分已提交）
    blocked = [r for r in results if r.state != "ready_to_publish"]
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
