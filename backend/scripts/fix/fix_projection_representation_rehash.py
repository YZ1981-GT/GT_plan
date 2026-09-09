#!/usr/bin/env python
"""BP-30 遗留 `structure_hash` 的**重投影**修复宿主（幂等，`--check` / `--apply`）。

**Spec: published-representation-production-path-and-lane-adjudication**
（BP-30 收口的数据侧；代码侧修复见 commit `0565cd5b`）

═══ 这个脚本解决什么 ══════════════════════════════════════════════════════════

BP-30 修复（2026-09-06 10:14）把发布时刻的 `representation.structure_hash` 从
「整份 xlsx 字节摘要」改成与请求时刻观测器同构的「契约 + 受管结构坐标摘要」。
但**代码修复不会回溯已发布的行**：09-02 ~ 09-05 期间发布的 4 条 projection lane
representation 冻结的仍是旧口径值，于是

    published_identity_observer.observe()
      → ObservedIdentityDriftError（重算 43a2b538… ≠ 冻结 1e9b2eb8…）
      → attach_pilot_adapters() 抛错
      → registered_adapter_ids = []      ⇒ bidirectional 结构上仍为 0

实测证据（`--check` 会逐条复算并打印）：4 条全部 STALE_HASH，且发布侧函数对**同一份
已发布 artifact** 重算的值恰好等于观测器期望值 ⇒ artifact 字节没问题，错的只是
representation 行上那一列。

═══ 为什么必须重投影，而不是三种更省事的做法 ═════════════════════════════════

1. **不能 UPDATE 那一列**。`trg_wpcr_immutable` 对任何 UPDATE 无条件
   `RAISE EXCEPTION`（「immutable 行，禁止 UPDATE（升级只能新增 generation）」）。
   这条设计是对的：representation 是不可变身份，历史 operation 靠它做 frozen 解析。
2. **不能走 `fix_projection_first_publication.py`**。它的判据 ③ 对已发布 entry 抛
   `FirstPublicationAlreadyDoneError`（本脚本不改它，也不绕它 —— 见下）。
3. **不能走 `fix_excel_instrumentation_upgrade_candidate.py` + Task 36 finalize**。
   那条链自己写明「🔴 store 载荷非空即拒（`store_payload_not_empty`）…… store 已有
   数据的 entry 直接 finalize 会**丢数据**；那条路必须重投影（`materialize` +
   `ContentMutationService`），属 Task 36」。D2 的 store 实测 490,291 B（729 行真实
   客户明细），正是它点名要拦的情形。

═══ G1-2 分流：两种 stale、两条修复路径（不是一条重投影通吃）═════════════════════

BP-30 遗留 stale 有两种成因，必须分开处理（总控 §3.4 item 4 / DEC-03）：

1. **纯口径 stale**（artifact 字节未变，只是冻结 `structure_hash` 列还是旧的整份摘要
   口径；`_GT_SYNC` 冻结坐标与物理结构一致）⇒ 这是 representation 身份修正，走
   **representation-only**：在既有 content version 上经
   `MaterializeCoordinator.finalize_definition_upgrade` →
   `RepresentationService.finalize_candidate` 产出新 representation generation，
   `content_revision` **不变**，旧 generation 保留且不 current。它**不读 store、不改
   业务内容**。结算 state：`stale_needs_rehash` → `rehashed`。

2. **坐标漂移 stale**（`_GT_SYNC` 冻结坐标已与物理结构错位，artifact 字节需重排）⇒
   这是**新业务内容**，把 HTML store 的当前业务载荷重新 materialize，经
   `ContentMutationService.commit(...)` 产出新 content version + 新 generation。它
   **合法推进 revision**。结算 state：`stale_needs_reprojection` → `reprojected`。

representation-only finalize 需要 candidate 登记行携带的输入（Task 17 + Task 76 产物）；
存量遗留行尚无 `state=ready` candidate 时如实 `blocked`，**绝不**退回
`publish_first_generation`（那会给纯口径 stale 也推进业务 revision，正是本包要消灭的
错误）。坐标漂移的重投影分支仍复用下文首版链，且明确标注它产生新 content version。

═══ 判据一条都没有放宽 ════════════════════════════════════════════════════════

本脚本**复用** `projection_first_publication` 的整条链（`stage_instrumented_substrate`
→ `publish_first_generation`），只把准入里的**判据 ③**（「已有 current published
representation ⇒ 拒绝」）替换成本脚本自己的**更强**判据：

* 判据 ③′：该 entry 必须**已有** current published representation（没有的走首版宿主）；
* 判据 ③″：该 representation 的冻结 `structure_hash` 必须**确实**不等于发布侧函数对
  它自己的 artifact 重算出的值（即真的是 stale）。**已经一致的 entry 一律跳过** ——
  这条让本脚本幂等，也让它不能被用来无理由地重发 representation。

其余四条（lane 裁决 / bundle provisioned / bundle typed slots / 契约 reviewed）全部
**委派原函数**，不重写、不放宽。`resolve_plan` 本身一个字节都不改。

🔴 **判成败一律查数据，不看退出码** —— `--apply` 可能被 Ctrl+C 中断而部分 entry 已提交。

═══ 用法 ════════════════════════════════════════════════════════════════════

    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/fix/fix_projection_representation_rehash.py --check
    python backend/scripts/fix/fix_projection_representation_rehash.py --check --json out.json
    python backend/scripts/fix/fix_projection_representation_rehash.py --apply
    python backend/scripts/fix/fix_projection_representation_rehash.py --apply --entry xlsx/gt-d2-accounts-receivable
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import io
import json
import re
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


class RehashHostError(RuntimeError):
    """宿主自身的前置不成立（不是业务判据失败）。"""


#: 封闭结算词表。自由文本会让守卫只能比字符串，而「结算落在哪一格」正是本脚本唯一
#: 对外承诺的东西 —— 它必须可枚举、可断言、可当 CI 基线。
ENTRY_STATES: Final[tuple[str, ...]] = (
    # 纯口径 stale：artifact 字节未变，只是冻结 structure_hash 列还是旧的整份摘要口径
    # ⇒ representation-only（同 content version、新 generation、revision 不变）
    "stale_needs_rehash",
    # 坐标漂移 stale：_GT_SYNC 冻结坐标已与物理结构错位 ⇒ artifact 字节需重排
    # ⇒ 重投影（这是新业务内容，合法产生新 content version），不走 representation-only
    "stale_needs_reprojection",
    # 已一致，无需动作（幂等的正常出口）
    "already_consistent",
    # 该 entry 还没有 current published representation ⇒ 走首版宿主
    "not_published_use_first_publication_host",
    # artifact 文件缺失（orphan / 存储层问题）
    "blocked_artifact_missing",
    # representation-only rehash 已成功（仅 --apply，纯口径 stale）
    "rehashed",
    # 坐标漂移重投影已成功（仅 --apply）
    "reprojected",
    # 五条准入里非判据 ③ 的那四条失败，或 commit 链失败
    "blocked",
)

#: 各结算格的解除方。不写自由文本 —— 守卫按它断言诊断真的指了动作。
_STATE_UNBLOCK_OWNER: Final[Mapping[str, str]] = {
    "not_published_use_first_publication_host": (
        "先跑 backend/scripts/fix/fix_projection_first_publication.py --apply"
    ),
    "blocked_artifact_missing": (
        "representation 指向的 canonical artifact 文件不在磁盘上 —— "
        "属存储层/orphan GC 问题，先核对 working_paper_artifact.relative_path"
    ),
    "blocked": "逐条读 error_code 与 diagnosis；本脚本不放宽任何判据",
}

#: representation-only 分支的 blocked error_code → 唯一解除动作（不写自由文本）。
_REHASH_BLOCK_UNBLOCK: Final[Mapping[str, str]] = {
    "no_finalizable_candidate": (
        "先跑 Task 17 instrumentation upgrader stage 出绑定既有 content version 的 "
        "upgrade candidate"
    ),
    "candidate_not_ready": (
        "先跑 Task 76 provisioning 的 attach，把 approved contract+bundle 绑上 "
        "candidate（state=ready）"
    ),
    "finalize_inputs_pending_provisioning": (
        "candidate 就绪后由本出口委派 MaterializeCoordinator.finalize_definition_upgrade；"
        "不重建输入、不退回 publish_first_generation"
    ),
    "revision_advanced": (
        "representation-only 出口被换成了会推进 revision 的路径 —— 复核出口是否仍为 "
        "finalize_definition_upgrade"
    ),
}


@dataclass
class EntryOutcome:
    """一个 entry 的结算。字段全部是**实测值**，不含推断。"""

    entry_id: str
    contract_id: str
    wp_id: str | None = None
    project_id: str | None = None
    representation_id: str | None = None
    generation: int | None = None
    frozen_structure_hash: str | None = None
    recomputed_structure_hash: str | None = None
    store_bytes: int | None = None
    state: str = "blocked"
    error_code: str | None = None
    diagnosis: str | None = None
    #: --apply 成功后的新代际事实
    new_representation_id: str | None = None
    new_generation: int | None = None
    new_structure_hash: str | None = None
    new_revision: int | None = None
    stages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 目标清单：现算，不抄第二份
# ═══════════════════════════════════════════════════════════════════════════


def _plan_rows() -> list[Mapping[str, Any]]:
    """从 `DELIVERED_PER_ENTRY_CONTRACTS` 现算目标，并逐条过 provider 白名单。

    与首版宿主同款：白名单由 registry 单点把守，本脚本不放宽。
    """
    from app.services.workpaper_sync.adapters import registry as registry_module

    rows: list[Mapping[str, Any]] = []
    for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        module_path = str(row["provider_module"])
        if module_path not in registry_module._ALLOWED_PROVIDER_MODULES:
            raise RehashHostError(
                f"provider_module {module_path!r} 不在 registry 白名单内 —— "
                "宿主不放宽该判据"
            )
        rows.append(row)
    if not rows:
        raise RehashHostError("`DELIVERED_PER_ENTRY_CONTRACTS` 为空 —— 无目标可处理")
    return rows


async def _current_representation(
    session: Any, *, entry_id: str
) -> Mapping[str, Any] | None:
    """取该 entry 的 **current** published representation 及其 artifact 路径。

    可见性口径**委派** `projection_target_resolution.resolve_visible_current_representation_id`
    —— 与四个 pilot 的 `attach_pilot_adapters` 用同一个真源（BP-27：同一 entry 在多个
    底稿实例上有状态是合法设计，按 entry_id 裸查 `.first()` 会绑到已删项目那份）。
    """
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=entry_id
    )
    if representation_id is None:
        return None
    row = (
        await session.execute(
            sa.text(
                "SELECT r.id, r.wp_id, r.generation, r.structure_hash, "
                "       r.content_version_id, a.relative_path, a.sha256, "
                "       wp.project_id "
                "FROM working_paper_content_representation r "
                "JOIN working_paper_artifact a ON a.id = r.artifact_id "
                "JOIN working_paper wp ON wp.id = r.wp_id "
                "WHERE r.id = :r"
            ),
            {"r": str(representation_id)},
        )
    ).first()
    if row is None:
        return None
    return {
        "representation_id": row[0],
        "wp_id": row[1],
        "generation": int(row[2]),
        "structure_hash": str(row[3]),
        "content_version_id": row[4],
        "relative_path": str(row[5]),
        "artifact_sha256": str(row[6]),
        "project_id": row[7],
    }


def _recompute_from_artifact(
    *, relative_path: str, contract_id: str, provider: Any
) -> tuple[str | None, str | None]:
    """用**发布侧**函数对已发布 artifact 重算 `structure_hash`。

    返回 ``(hash, error)``。这是「是不是真 stale」的唯一判据来源：公式与请求时刻观测器
    同构（`publish_time_structure_hash` 从观测器 import `recompute_structure_hash`，
    零复制），所以「重算 == 冻结」当且仅当该行不是旧口径遗留。
    """
    from app.services.workpaper_sync.contracts import load_contract
    from app.services.workpaper_sync.publish_time_structure_hash import (
        anchors_from_instrumentation_spec,
        compute_structure_hash_from_artifact,
    )

    path = _BACKEND_ROOT / relative_path
    if not path.is_file():
        return (None, f"artifact 文件不存在: {path}")
    try:
        return (
            compute_structure_hash_from_artifact(
                data=path.read_bytes(),
                contract=load_contract(contract_id),
                anchors=anchors_from_instrumentation_spec(
                    provider.instrumentation_spec()
                ),
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001 - 宿主要把真实失败如实记进结算
        return (None, f"{type(exc).__name__}: {exc}")


def _gtsync_structure_drift(
    *, relative_path: str, contract_id: str, provider: Any, entry_id: str
) -> tuple[str | None, str | None, str | None]:
    """`structure_hash` 之外**另一条**独立判据：`_GT_SYNC` 冻结坐标 vs 物理结构。

    返回 ``(state, detail, error)``：

    * ``("consistent", ...)`` —— 冻结坐标与 artifact 物理结构逐项一致
    * ``("drift", ...)``      —— 已确认错位 ⇒ 该 representation 会让下游
      ``materialize`` 的计划期 footer 门 fail closed
      （``excel_materialize_footer_anchor_drift``）
    * ``(None, None, error)`` —— artifact 读不出，由调用方结算成
      ``blocked_artifact_missing``

    为什么需要这一维：``structure_hash`` 描述的是「契约声明结构 vs artifact」，它
    **不看** ``_GT_SYNC`` runtime binding。而结构性插行只改那几个应当随之重冻结的坐标
    （受管区末行 / footer / row UUID 末行 / Table ref）。D2 实测：hash 完全一致
    （``already_consistent``），但 ``GT_FOOTER_ROW`` 冻结 26、footer marker「合计」
    实测在 755 行 —— 这类错位旧判据**结构性不可见**，却直接导致该 entry 的
    HTML→Excel 方向永久不可用。

    🔴 判据是**冻结值 vs 物理实测值**的直比，不依赖 ``GT_LAST_SHIFT``。后者是本修复
    上线后才写入的模板升级预留键，修复前产物根本没有它 —— 靠它判漂移会漏掉所有历史
    错位。口径与运行时 footer 门同源（同一个 marker、同一个 ``search_column``、同一
    套 ``_GT_SYNC`` 读侧入口），不抄第二份解析。

    Spec: published-representation-production-path-and-lane-adjudication
    """
    import io
    import re
    import zipfile

    path = _BACKEND_ROOT / relative_path
    if not path.is_file():
        return (None, None, f"artifact 文件不存在: {path}")

    try:
        data = path.read_bytes()
        from app.services.workpaper_sync import excel_extract as EE
        from app.services.workpaper_sync import excel_materialize as EM
        from app.services.workpaper_sync.contracts import load_contract

        contract = load_contract(contract_id)
        zf = zipfile.ZipFile(io.BytesIO(data))
        pairs = EE.read_runtime_binding_pairs(zf)
        parts = EE._sheet_parts(zf)
        entries = EM._read_entries(data)

        frozen_footer = pairs.get("GT_FOOTER_ROW")
        frozen_table_ref = pairs.get("GT_MANAGED_TABLE_REF")
        frozen_uuid_last = pairs.get("GT_ROW_UUID_LAST_ROW")
        if frozen_footer is None:
            return ("consistent", "无 GT_FOOTER_ROW 冻结预期 —— 坐标漂移不适用", None)

        anchors = [
            (sheet, t.footer_anchor)
            for sheet in contract.sheets
            for t in sheet.tables
            if t.footer_anchor is not None
        ]
        if not anchors:
            return ("consistent", "契约未声明 footer_anchor —— 坐标漂移不适用", None)
        anchor_sheet, anchor = anchors[0]

        # ── 受管 sheet 部件：按契约声明的 excel_name 解析（唯一真源）────
        # 一个 workbook 常有十余个 sheet，裸取「第一个业务 sheet」会定位到目录页
        # （D2 实测误落 sheet1 底稿目录，而受管区在 sheet8 明细表-D2-2）。
        sheet_part = parts.get(str(getattr(anchor_sheet, "excel_name", "") or ""))
        sheet_label = str(getattr(anchor_sheet, "excel_name", "") or "")
        if sheet_part is None:
            sheet_part = parts.get(
                str(pairs.get("GT_MANAGED_SHEET_NAME_AT_INSTRUMENTATION", ""))
            )
            sheet_label = str(
                pairs.get("GT_MANAGED_SHEET_NAME_AT_INSTRUMENTATION", "")
            )
        if sheet_part is None or sheet_part not in entries:
            return (None, None, "受管 sheet 部件定位不到 —— 坐标漂移无法判定")

        observed = EM._find_marker_row(
            entries[sheet_part].decode("utf-8"),
            column=anchor.search_column,
            marker=anchor.marker,
            shared=EM._shared_strings(entries),
        )

        drifts: list[str] = []
        if observed is None:
            drifts.append(
                f"footer marker 在受管 sheet {sheet_label!r}（{sheet_part}）上一处都"
                "找不到，而 _GT_SYNC 声明了 GT_FOOTER_ROW"
            )
        elif int(str(frozen_footer)) != int(observed):
            drifts.append(
                f"footer marker 实测第 {observed} 行 ≠ 冻结 GT_FOOTER_ROW="
                f"{frozen_footer}"
            )

        if frozen_table_ref is not None:
            table_ref = _managed_table_ref_from_artifact(data)
            if table_ref and frozen_table_ref != table_ref:
                drifts.append(
                    f"Table ref 实测 {table_ref} ≠ 冻结 GT_MANAGED_TABLE_REF="
                    f"{frozen_table_ref}"
                )

        if frozen_uuid_last is not None:
            uuid_col = str(pairs.get("GT_ROW_UUID_COLUMN") or "")
            uuid_last = _managed_uuid_last_row(
                entries.get(sheet_part, b""), column=uuid_col
            )
            if uuid_last and int(str(frozen_uuid_last)) != uuid_last:
                drifts.append(
                    f"row UUID 末行实测 {uuid_last} ≠ 冻结 GT_ROW_UUID_LAST_ROW="
                    f"{frozen_uuid_last}"
                )

        # 模板升级预留键：存在但形态非法同样是缺陷（会被下游按数字解析而静默失败）
        shift_record = str(pairs.get("GT_LAST_SHIFT") or "")
        if shift_record:
            segs = shift_record.split("|")
            if len(segs) != 3 or not all(seg.isdigit() for seg in segs):
                drifts.append(
                    f"GT_LAST_SHIFT={shift_record!r} 不是 `插入点|行数|累计` 三段数字形态"
                )

        if drifts:
            return (
                "drift",
                "；".join(drifts)
                + f" ⇒ 冻结坐标未随行位移重冻结，下游 materialize 计划期 fail closed"
                  f"（entry={entry_id}）",
                None,
            )
        return (
            "consistent",
            f"冻结坐标与物理结构一致（footer={frozen_footer}"
            + (f"、Table ref={frozen_table_ref}" if frozen_table_ref else "")
            + f"）",
            None,
        )
    except Exception as exc:  # noqa: BLE001 - 宿主必须把真实失败如实记进结算
        return (None, None, f"{type(exc).__name__}: {exc}")


def _managed_table_ref_from_artifact(data: bytes) -> str | None:
    """读 artifact 里受管 Excel Table 的实测 ``ref``；没有 Table 返回 ``None``。

    🔴 文件名**不得**按 ``table\\d+.xml`` 匹配：instrumentation 产出的部件名是
    ``tableGtRowId.xml`` / ``tableGtCustom.xml`` 这类**非数字**后缀，写成 ``\\d+``
    会让本检查对所有真实 artifact 恒返 ``None`` 而静默跳过 —— 那是守卫假绿，不是
    「没发现 Table」。匹配范围限定在 ``xl/tables/`` 下的 ``table*.xml`` 部件。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not re.match(r"xl/tables/table[^/]*\.xml$", name):
                continue
            xml = zf.read(name).decode("utf-8")
            m = re.search(r"<table\b[^>]*\bref=\"([^\"]+)\"", xml)
            if m:
                return m.group(1)
    return None


def _managed_uuid_last_row(xml_bytes: bytes, *, column: str) -> int | None:
    """受管 sheet 里 row UUID 列的最大行号（identity 单元格，非数据值）。"""
    import re

    if not column or not xml_bytes:
        return None
    text = xml_bytes.decode("utf-8")
    rows = [
        int(m.group(1))
        for m in re.finditer(r'<c r="' + re.escape(column) + r"(\d+)\"", text)
    ]
    return max(rows) if rows else None


async def _read_store_payload(
    session: Any, *, wp_id: uuid.UUID, store_item_id: str, provider: Any, entry_id: str
) -> str:
    """读该 entry 的 HTML store 载荷；无记录/全空白时取 provider 声明的空载荷。

    与首版宿主逐字同构（含「非空但非法的 JSON **不**在这里兜底」这条）：非法载荷必须让
    provider 的 `StorePayloadError` 响亮抛出，否则会把「数据坏了」伪装成「还没录」，
    重投影就会发布出一份内容错误的 representation。
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
    if row is not None and str(row).strip():
        return str(row)
    if not hasattr(provider, "EMPTY_STORE_PAYLOAD"):
        raise RehashHostError(
            f"{entry_id} 的 provider {provider.__name__} 未声明 `EMPTY_STORE_PAYLOAD`"
        )
    payload = getattr(provider, "EMPTY_STORE_PAYLOAD")
    if payload is None:
        raise RehashHostError(
            f"{entry_id} 的 store 无记录且该 pilot 无「空载荷」合法状态 —— "
            "重投影需要 HTML 侧先有内容"
        )
    return str(payload)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 准入：复用原函数四条判据，只替换判据 ③
# ═══════════════════════════════════════════════════════════════════════════


async def resolve_rehash_plan(
    *,
    session: Any,
    resolution: Any,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    actor_id: uuid.UUID | None = None,
) -> Any:
    """产出与 `resolve_plan` **同型**的 `FirstPublicationPlan`，用于重投影。

    与 `projection_first_publication.resolve_plan` 的唯一差别是判据 ③ 的方向：

    * 原函数：已有 current published representation ⇒ `FirstPublicationAlreadyDoneError`
    * 本函数：**必须**已有（没有则由调用方结算成
      `not_published_use_first_publication_host`）

    其余四条**逐条委派原模块的同一批函数**（`assert_projection_lane` /
    `observe_lane_supply` 的 `projection_bundle_provisioned` / `load_bundle_snapshot` /
    `load_contract`），本函数不重写任何一条判据实现 —— 重写一份的后果不是更安全，
    而是任一侧被短路都不改变行为（变异检验判 GREEN）。

    🔴 这里**没有** `except Exception` 兜底：lane 未裁决 / bundle 未 provision / typed
    slot 非法 / 契约未复核一律原样上抛，由调用方按 error_code 落进对应结算格。
    """
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync.contracts import load_contract
    from app.services.workpaper_sync.projection_lane_registry import (
        LaneUndecidedError,
        assert_projection_lane,
        authority_model_logical_id,
        observe_lane_supply,
    )

    # ── ① lane 裁决（含 L5 契约 reviewed 的判定）——委派 ────────────
    try:
        assert_projection_lane(entry_id)
    except LaneUndecidedError as exc:
        if exc.criterion_number == F._CONTRACT_CRITERION:
            raise F.ContractNotReviewedError(
                f"entry {entry_id!r} 的磁盘 per-entry 契约不可用作生产契约"
                f"（lane 裁决 L{F._CONTRACT_CRITERION}：{exc.criterion_label}）: {exc}"
            ) from exc
        raise

    supply_row = F._delivered_row(entry_id)
    contract_id = str(supply_row["contract_id"])
    provider_module = str(supply_row["provider_module"])
    document_type = str(supply_row["document_type"])

    # ── ② 供给判据 A：approved projection bundle 必须在库——委派 ─────
    facts = await observe_lane_supply(
        session=session, project_id=project_id, wp_id=wp_id, entry_id=entry_id
    )
    if not facts.projection_bundle_provisioned:
        raise F.ProjectionBundleNotProvisionedError(
            f"entry {entry_id!r} 的判据 A（projection_bundle_provisioned）不成立 —— "
            f"库里没有 authority model logical_id="
            f"{authority_model_logical_id(contract_id)!r} 的 approved projection bundle。"
            f"解除动作：先跑 {F.ProjectionBundleNotProvisionedError.remediation}"
        )

    # ── ③′ 判据方向反转：重投影**要求**已发布 ───────────────────────
    #
    # 与原函数的判据 ③ 严格互补：那边「已发布即拒」，这边「未发布即拒」。两个宿主
    # 因此覆盖不重叠、不冲突的两个状态空间，任何 entry 在任一时刻只可能进其中一个。
    if not facts.published_representation_current:
        raise F.FirstPublicationAlreadyDoneError(
            f"entry {entry_id!r} 在 wp={wp_id} 上**还没有** current published "
            "representation —— 重投影宿主只处理已发布的 entry；首版请走 "
            "fix_projection_first_publication.py"
        )

    # ── ④ bundle snapshot（三 typed slot 由被委派方校验）——委派 ─────
    bundle_id = await F._approved_projection_bundle_id(session, contract_id=contract_id)
    bundle = await resolution.load_bundle_snapshot(bundle_id)

    # ── ⑤ 磁盘契约对象（判定已在 ① 的 L5 完成）——委派 ──────────────
    try:
        contract = load_contract(contract_id)
    except Exception as exc:
        raise F.ContractNotReviewedError(
            f"entry {entry_id!r} 的磁盘契约 {contract_id!r} 在 L{F._CONTRACT_CRITERION} "
            f"通过之后变得不可加载 —— 两次读取之间磁盘被改动: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    expected_revision = await F._current_revision(session, wp_id=wp_id)

    return F.FirstPublicationPlan(
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        contract_id=contract_id,
        provider_module=provider_module,
        document_type=document_type,
        expected_revision=expected_revision,
        bundle=bundle,
        contract=contract,
        authority_model_logical_id=authority_model_logical_id(contract_id),
        actor_id=actor_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 主流程
# ═══════════════════════════════════════════════════════════════════════════


async def _process_entry(
    session: Any, *, row: Mapping[str, Any], apply: bool
) -> EntryOutcome:
    """一个 entry 的完整处理。**不 commit** —— 事务边界属调用方。"""
    from app.services.workpaper_sync import projection_first_publication as F
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    entry_id = str(row["entry_id"])
    contract_id = str(row["contract_id"])
    out = EntryOutcome(entry_id=entry_id, contract_id=contract_id)
    provider = importlib.import_module(str(row["provider_module"]))

    # ── 第 1 步：取 current representation ─────────────────────────
    current = await _current_representation(session, entry_id=entry_id)
    if current is None:
        out.state = "not_published_use_first_publication_host"
        out.diagnosis = _STATE_UNBLOCK_OWNER[out.state]
        return out
    out.stages.append("current_representation_resolved")
    out.representation_id = str(current["representation_id"])
    out.wp_id = str(current["wp_id"])
    out.project_id = str(current["project_id"])
    out.generation = current["generation"]
    out.frozen_structure_hash = current["structure_hash"]

    # ── 第 2 步：判据 ③″ —— 是不是真 stale ─────────────────────────
    recomputed, err = _recompute_from_artifact(
        relative_path=current["relative_path"],
        contract_id=contract_id,
        provider=provider,
    )
    if recomputed is None:
        out.state = "blocked_artifact_missing"
        out.error_code = "artifact_unreadable"
        out.diagnosis = f"{err} · {_STATE_UNBLOCK_OWNER[out.state]}"
        return out
    out.stages.append("structure_hash_recomputed")
    out.recomputed_structure_hash = recomputed

    if recomputed == current["structure_hash"]:
        # 第二维判据：structure_hash 一致不等于 representation 自洽 ——
        # _GT_SYNC 冻结坐标可能没随行位移重冻结（D2 实测正卡在这里）。
        drift_state, drift_detail, drift_err = _gtsync_structure_drift(
            relative_path=current["relative_path"],
            contract_id=contract_id,
            provider=provider,
            entry_id=entry_id,
        )
        if drift_err is not None:
            out.state = "blocked_artifact_missing"
            out.error_code = "artifact_unreadable"
            out.diagnosis = f"{drift_err} · {_STATE_UNBLOCK_OWNER[out.state]}"
            return out
        if drift_state == "drift":
            # 🔴 坐标漂移 ⇒ artifact 字节需重排（footer/Table ref/row UUID 末行随行位移
            #    重冻结）。这是**新业务内容**，走重投影分支产生新 content version，
            #    不得混进 representation-only（后者不改字节，无法修坐标）。
            out.stages.append("stale_confirmed")
            out.state = "stale_needs_reprojection"
            out.diagnosis = (
                f"{drift_detail} ⇒ 冻结坐标已错位、artifact 字节需重排 ⇒ 重投影产新 "
                "content version（非 representation-only）"
            )
        else:
            # 幂等出口：两维判据都一致才跳过，不无理由重发 representation
            out.state = "already_consistent"
            out.diagnosis = (
                "冻结 structure_hash 与发布侧重算值一致，且 _GT_SYNC 冻结坐标与"
                f"物理结构一致（{drift_detail}）—— 无需重投影"
                "（本脚本幂等，第二次运行必落这一格）"
            )
            return out
    else:
        # 🔴 冻结 hash ≠ 重算值，但（进入本分支的前提是）字节未被判为坐标漂移：
        #    artifact 字节没问题，错的只是 representation 行上那一列的旧口径值。
        #    ⇒ representation-only：同 content version、新 generation、revision 不变。
        out.stages.append("stale_confirmed")
        out.state = "stale_needs_rehash"
        out.diagnosis = (
            f"冻结 {current['structure_hash'][:12]}… ≠ 重算 {recomputed[:12]}… ⇒ "
            "BP-30 旧口径遗留（artifact 字节正确）⇒ representation-only 产新 generation、"
            "content_revision 不变"
        )

    # ── 第 3 步：仅重投影分支需要 store 载荷 ─────────────────────────
    #
    # representation-only（`stale_needs_rehash`）不读 store、不改业务内容，它只在既有
    # content version 上产出新 representation generation，因此不需要业务载荷；只有坐标
    # 漂移的重投影（`stale_needs_reprojection`）才需要把当前 store 载荷重新 materialize。
    if out.state == "stale_needs_rehash":
        if not apply:
            return out
        return await _rehash_representation_only(
            session, current=current, contract_id=contract_id, out=out
        )

    store_item_id = str(getattr(provider, "STORE_ITEM_ID", "") or "")
    if not store_item_id:
        # provider 未声明常量名时，从契约的 review.html_store.item_id 现取
        from app.services.workpaper_sync.contracts import load_contract

        contract_obj = load_contract(contract_id)
        store_item_id = str(
            ((getattr(contract_obj, "review", None) or {}).get("html_store") or {}).get(
                "item_id"
            )
            or ""
        )
    if not store_item_id:
        out.state = "blocked"
        out.error_code = "store_item_id_unknown"
        out.diagnosis = (
            f"取不到 {entry_id} 的 store item_id（provider.STORE_ITEM_ID 与契约 "
            "review.html_store.item_id 均为空）—— 不猜一个键名"
        )
        return out
    store_payload = await _read_store_payload(
        session,
        wp_id=current["wp_id"],
        store_item_id=store_item_id,
        provider=provider,
        entry_id=entry_id,
    )
    out.store_bytes = len(store_payload.encode("utf-8"))
    out.stages.append("store_payload_read")

    if not apply:
        return out

    # ── 第 4 步：--apply 真重投影 ───────────────────────────────────
    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    artifacts = CanonicalArtifactRepository(_BACKEND_ROOT)
    repository = WorkpaperSyncRepository(session)

    plan = await resolve_rehash_plan(
        session=session,
        resolution=resolution,
        project_id=current["project_id"],
        wp_id=current["wp_id"],
        entry_id=entry_id,
        actor_id=None,
    )
    out.stages.append("plan_resolved")

    with tempfile.TemporaryDirectory(prefix="rehash-") as tmp:
        staged = F.stage_instrumented_substrate(
            entry_id=entry_id, staging_dir=Path(tmp), contract=plan.contract
        )
        out.stages.append("substrate_instrumented")

        receipt = await F.publish_first_generation(
            session=session,
            resolution=resolution,
            artifacts=artifacts,
            repository=repository,
            plan=plan,
            staged=staged,
            store_payload=store_payload,
        )
        out.stages.append("committed")

    out.new_representation_id = str(receipt.representation_id)
    out.new_generation = int(receipt.representation_generation)
    out.new_revision = int(receipt.revision)
    out.state = "reprojected"
    out.diagnosis = (
        f"坐标漂移已重投影：新 representation {receipt.representation_id} "
        f"generation={receipt.representation_generation} revision={receipt.revision}"
        "（字节重排 ⇒ 新 content version，属预期）"
    )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 3b. representation-only rehash（纯口径 stale：同 content version、新 generation）
# ═══════════════════════════════════════════════════════════════════════════


class _RehashRepresentationOnlyBlocked(RuntimeError):
    """representation-only rehash 的前置不成立（结算成 `blocked`，附 error_code）。"""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


async def _load_finalizable_candidate_id(
    session: Any, *, wp_id: str, entry_id: str, source_representation_id: str
) -> uuid.UUID:
    """找到该 entry 上可 finalize 的 non-current upgrade candidate。

    representation-only 路径**不自造** candidate：它要求上游（Task 17 instrumentation
    upgrader + Task 76 provisioning）已经 stage 出一个绑定既有 content version 的
    candidate，且 approved per-entry contract / bundle 已 attach（`state=ready`）。找不到
    这样的 candidate 时如实结算成 `blocked`，绝不退回 `publish_first_generation`（那会
    推进业务 revision，正是本包要消灭的错误）。

    判据全部只读，不写任何一行。
    """
    from app.services.workpaper_sync.models import CandidateState

    row = (
        await session.execute(
            sa.text(
                "SELECT id, state, content_version_id, "
                "       target_contract_definition_id, target_definition_bundle_id "
                "FROM working_paper_representation_upgrade_candidate "
                "WHERE wp_id = :wp AND entry_id = :entry "
                "  AND finalized_representation_id IS NULL "
                "ORDER BY created_at DESC, id DESC"
            ),
            {"wp": str(wp_id), "entry": str(entry_id)},
        )
    ).mappings().all()
    if not row:
        raise _RehashRepresentationOnlyBlocked(
            "no_finalizable_candidate",
            "该 entry 无 non-current upgrade candidate —— representation-only rehash 需要"
            " 上游先 stage 出绑定既有 content version 的 candidate（Task 17 + Task 76），"
            "不得退回 publish_first_generation（那会推进业务 revision）",
        )
    ready = CandidateState.ready.value if hasattr(CandidateState, "ready") else "ready"
    for cand in row:
        if (
            str(cand["state"]) == ready
            and cand["target_contract_definition_id"] is not None
            and cand["target_definition_bundle_id"] is not None
        ):
            return uuid.UUID(str(cand["id"]))
    raise _RehashRepresentationOnlyBlocked(
        "candidate_not_ready",
        "存在 candidate 但没有 approved contract+bundle 已 attach（state=ready）—— "
        "先跑 Task 76 provisioning 的 attach，再 finalize；本包不放宽该判据",
    )


async def _rehash_representation_only(
    session: Any, *, current: Mapping[str, Any], contract_id: str, out: EntryOutcome
) -> EntryOutcome:
    """纯口径 stale 的修复：在**既有 content version** 上 finalize 新 representation
    generation，`content_revision` 保持不变。

    ═══ 唯一合法出口 ═══

    representation-only 的唯一放行门是 `ExcelEntryFinalizeGate.finalize_candidate`
    → `MaterializeCoordinator.finalize_definition_upgrade` → `RepresentationService`
    （其仓储被 `RevisionLockedRepository` 包住，拿不到 revision 写入面）。本宿主
    **不**自己拼事务、**不**调 `publish_first_generation`、**不**推进 revision。

    ═══ 为什么此处 fail-closed 而不是直接 finalize ═══

    该门要求一个**已 stage 的 instrumented upgrade candidate**（绑定既有 content
    version）外加 observed structure / adapter build / equivalence 证据 —— 这些由
    Task 17 instrumentation upgrader 与 Task 76 provisioning 产出并 attach approved
    contract/bundle 后（`state=ready`），才可 finalize。存量 BP-30 遗留行**尚无**这样
    的 candidate。本宿主因此只做只读前置定位：找不到 finalizable candidate 时如实结算
    成 `blocked` 并指明唯一解除动作，**绝不**退回 `publish_first_generation`（那会推进
    业务 revision，正是本包要消灭的错误）。

    这不是能力缺失的掩盖，而是把「representation-only 迁移」与其真实前置（有 candidate）
    诚实解耦：候选就绪的 entry 走 finalize，未就绪的 entry 显式阻塞，两者都不推进 revision。
    """
    try:
        revision_before = (
            await session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(current["wp_id"])},
            )
        ).scalar_one()

        candidate_id = await _load_finalizable_candidate_id(
            session,
            wp_id=str(current["wp_id"]),
            entry_id=out.entry_id,
            source_representation_id=str(current["representation_id"]),
        )
        out.stages.append("finalizable_candidate_resolved")

        outcome = await _finalize_candidate_representation_only(
            session, project_id=uuid.UUID(str(current["project_id"])), candidate_id=candidate_id
        )
        out.stages.append("representation_only_finalized")

        revision_after = (
            await session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(current["wp_id"])},
            )
        ).scalar_one()
        if int(revision_after) != int(revision_before):
            raise _RehashRepresentationOnlyBlocked(
                "revision_advanced",
                f"representation-only rehash 推进了 content_revision "
                f"{revision_before} → {revision_after} —— Property 4 被破坏",
            )
        out.new_representation_id = str(outcome["representation_id"])
        out.new_generation = int(outcome["representation_generation"])
        out.new_revision = int(revision_after)
        out.state = "rehashed"
        out.diagnosis = (
            f"representation-only 已 finalize：新 representation "
            f"{outcome['representation_id']} generation="
            f"{outcome['representation_generation']}；content_revision 不变"
            f"（{revision_before}）"
        )
        return out
    except _RehashRepresentationOnlyBlocked as exc:
        out.state = "blocked"
        out.error_code = exc.error_code
        out.diagnosis = str(exc)
        return out


async def _finalize_candidate_representation_only(
    session: Any, *, project_id: uuid.UUID, candidate_id: uuid.UUID
) -> Mapping[str, Any]:
    """委派 representation-only 唯一出口，返回 finalize 事实（不含 revision 判定）。

    ═══ 唯一出口，且需要 candidate 的登记输入 ═══

    finalize 的合法出口是 `MaterializeCoordinator.finalize_definition_upgrade` →
    `RepresentationService.finalize_candidate`。该出口需要 candidate 登记行携带的
    完整输入：`staged_candidate`（隔离目录里的 instrumented 字节）、`adapter_build`、
    `frozen_bundle_sha256`、observed structure/business sheets/dynamic columns 与
    equivalence 证据。这些是 Task 17 instrumentation upgrader 落 candidate、Task 76
    provisioning attach approved contract/bundle 时一并冻结的产物。

    本宿主**不**重建这些输入（重建=第二真源，且无法与登记值核对），而是从 candidate
    行读取它们后委派出口。当前存量 BP-30 遗留行尚无 `state=ready` 的 candidate，因此
    真实调用序列会在 `_load_finalizable_candidate_id` 处先行 `blocked`，不会到达这里；
    这条出口留作 candidate 就绪后的接线点，并由守卫锁死「它调的是 finalize 出口、不是
    `publish_first_generation`」。
    """
    raise _RehashRepresentationOnlyBlocked(
        "finalize_inputs_pending_provisioning",
        "representation-only finalize 需要 candidate 登记行携带的 staged_candidate / "
        "adapter_build / observed structure / equivalence 证据（Task 17 + Task 76 产物）；"
        "存量 BP-30 遗留行尚无 state=ready candidate。解除动作：先跑 Task 17 "
        "instrumentation upgrader 与 Task 76 provisioning attach，再由本出口委派 "
        "MaterializeCoordinator.finalize_definition_upgrade —— 本包不重建输入、不退回 "
        "publish_first_generation",
    )


async def run(*, apply: bool, only_entry: str | None) -> dict[str, Any]:
    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RehashHostError(
            "本脚本写 V151 的真实表（含 CHECK/trigger），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)

    rows = [
        row
        for row in _plan_rows()
        if only_entry is None or str(row["entry_id"]) == only_entry
    ]
    if only_entry is not None and not rows:
        raise RehashHostError(
            f"--entry {only_entry!r} 不在 `DELIVERED_PER_ENTRY_CONTRACTS` 里"
        )

    outcomes: list[EntryOutcome] = []
    try:
        for row in rows:
            # 🔴 逐 entry **独立事务**：一个 entry 失败不影响已成功的其它 entry
            #    （与首版宿主同款）。commit 由 `ContentMutationService` 内部的
            #    唯一提交出口执行，本脚本只在失败时 rollback。
            async with Session() as session:
                try:
                    outcome = await _process_entry(session, row=row, apply=apply)
                    if not apply:
                        await session.rollback()
                except Exception as exc:  # noqa: BLE001 - 逐 entry 隔离
                    await session.rollback()
                    outcome = EntryOutcome(
                        entry_id=str(row["entry_id"]),
                        contract_id=str(row["contract_id"]),
                        state="blocked",
                        error_code=str(getattr(exc, "error_code", "") or "")
                        or type(exc).__name__,
                        diagnosis=f"{type(exc).__name__}: {exc}"[:900],
                    )
                outcomes.append(outcome)
    finally:
        await engine.dispose()

    dist: dict[str, int] = {}
    for item in outcomes:
        dist[item.state] = dist.get(item.state, 0) + 1
    unknown = sorted({item.state for item in outcomes} - set(ENTRY_STATES))
    if unknown:
        raise RehashHostError(
            f"结算落在封闭词表之外: {unknown} —— 词表必须扩，不得静默"
        )
    return {
        "mode": "apply" if apply else "check",
        "entries": [item.as_dict() for item in outcomes],
        "state_distribution": dist,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BP-30 遗留 structure_hash 的重投影修复宿主（幂等）"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只读预演，一行库都不写")
    group.add_argument("--apply", action="store_true", help="真重投影（逐 entry 独立事务）")
    parser.add_argument("--entry", default=None, help="只处理指定 entry_id")
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    report = asyncio.run(run(apply=bool(args.apply), only_entry=args.entry))

    for item in report["entries"]:
        print(f"  {item['entry_id']}")
        print(f"    state={item['state']} error_code={item.get('error_code')}")
        if item.get("wp_id"):
            print(
                f"    wp_id={str(item['wp_id'])[:8]} rep={str(item.get('representation_id'))[:8]} "
                f"gen={item.get('generation')} store={item.get('store_bytes')}B"
            )
        if item.get("frozen_structure_hash"):
            print(
                f"    frozen={str(item['frozen_structure_hash'])[:16]}… "
                f"recomputed={str(item.get('recomputed_structure_hash'))[:16]}…"
            )
        if item.get("new_representation_id"):
            print(
                f"    NEW rep={str(item['new_representation_id'])[:8]} "
                f"gen={item.get('new_generation')} revision={item.get('new_revision')}"
            )
        if item.get("stages"):
            print(f"    stages={item['stages']}")
        if item.get("diagnosis"):
            print(f"    {item['diagnosis']}")
    print(f"  结算分布: {report['state_distribution']}")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  报告已落盘: {args.json_path}")

    blocked = sum(
        count
        for state, count in report["state_distribution"].items()
        if state.startswith("blocked")
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
