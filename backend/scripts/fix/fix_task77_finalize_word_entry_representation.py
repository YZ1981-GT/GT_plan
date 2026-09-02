"""Word per-entry gate 与 candidate finalize gate 的幂等消费宿主（`--check` / `--apply`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 4 Task 77
Requirements: 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.10, 12.5
Properties: **P28 / P30 / P31 / P32 / P34 / P67**

═══ 这个脚本是 `word_entry_gate` 的**唯一消费宿主** ═══

`app.services.workpaper_sync.word_entry_gate` 是纯服务层：它不开事务、不 commit、
不选目标底稿。没有宿主时它就是 additive 死代码（本 spec 反复实测过的假绿第①源），
所以判「Task 77 接上了没有」的判据落在这里：

* `--check` 只读：按 Task 60 的发布记录 × 真实 `working_paper` 现算「哪些 Word lane
  entry 有可 finalize 的目标」，并在**临时目录**里用权威模板现造一份 throwaway
  candidate，真跑一遍四条 tagged-SDT 判据（tag 集合 / SDT 层级 / 实例计数 /
  Word-only 等值）与载体门、锚点门。一行库都不写。
* `--apply` 真发布：只对**库里已存在**的 `ready` candidate（Task 59 产出、Task 76 的
  受控 attach 绑上 approved contract/bundle 的那个）调
  `WordEntryFinalizeGate.finalize_candidate`，出口是 Task 25 的
  `finalize_definition_upgrade`。逐 entry 一个事务，失败只回滚它自己并以非零退出码报
  ERROR —— **不**降级成「本项目无此数据」。

═══ 🔴 `--apply` 绝不重生成 docx ═══

`run_check` 会 `instrument_docx_bytes(权威模板)` —— 那是**只读预演**的 fixture，写在
系统临时目录、跑完即删，既不进 artifact store 也不进库。
`run_apply` **完全不碰模板**：它的字节来源只有 candidate 自己登记的 staged artifact。
两者的差别是可断言的结构事实（守卫在 `run_apply` 的 AST 上断言
`instrument_docx_bytes` / `wp_templates` / `TEMPLATE_ROOT` 零引用）—— 这就是
Task 77 正文「**不得**用模板重生成覆盖审计师已编辑的 Word-only 正文」的落点。

═══ 目标怎么选（不写第二份清单）═══

Word lane 在 `workpaper_sync_entry_manifest.json` 里 **0 条 entry**（Task 60 发布记录
`manifest_entry_state = absent_from_source_manifest`，现算 docx entry 7 条、F 前缀 0 条），
因此这里没有 manifest slice 可冻结。唯一真源是 Task 60 的发布记录
`workpaper_sync_f2_word_lane_publication.json` 的 `entries[]`：
`contract.contract_id` / `wp_code` / `template_ref` 全部从它现读，
instrumentation 声明从 Task 60 的**生成器**现算（`generate_task60_f2_word_contracts`），
本脚本不抄任何字段表。`entry_id` 取 `contract_id` —— 与 Task 59 的
`WordInstrumentationSpec.entry_id` 同一取值，candidate 行里存的就是它。

用法（Windows PowerShell，仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task77_finalize_word_entry_representation.py --check
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task77_finalize_word_entry_representation.py --apply
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task77_finalize_word_entry_representation.py --check --json tmp_task77_check.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
_GEN_DIR = _BACKEND / "scripts" / "gen"
if str(_GEN_DIR) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_GEN_DIR))

#: Task 60 的 Word lane 发布记录 —— 本脚本的**唯一** entry 真源。
PUBLICATION_PATH: Path = _BACKEND / "data" / "workpaper_sync_f2_word_lane_publication.json"

#: `--check` / `--apply` 共用的目标选取排序（确定性：重跑必选同一条底稿）。
TARGET_ORDER_SQL: str = "wi.wp_code, wp.created_at, wp.id"

#: 一个 entry 在 `--check` 里的封闭结算词表（自由文本会让守卫只能比字符串）。
CHECK_ENTRY_STATES: tuple[str, ...] = (
    "ready_to_finalize",
    "blocked_missing_approved_bundle",
    "blocked_missing_candidate",
    "already_finalized",
)


#: Task 60 发布的 Word per-entry 契约**暂存**目录。
#:
#: 🔴 定位这两份契约的代码刻意放在**脚本**里，而不是 `backend/app/**`：
#: `test_task60_f2_word_adapter.py::test_the_staged_contract_dir_has_no_production_consumer`
#: 要求暂存目录名在 `backend/app/**` 里出现 **0 次** —— 那是「candidate/未装清册的契约
#: 不入运行态」最直接的结构判据。`word_entry_gate` 因此只接受**已解析**的
#: `SyncContract`，一个文件都不定位；本脚本是唯一定位处。
#:
#: 暂存不等于放宽审核：解析仍走 `contracts.parse_contract`（`review_status != reviewed`
#: 的单点拒绝处），而「这份契约能否放行」由 DB 里的 approved contract definition child
#: 决定（gate 的 `_assert_contract_child_approved` + Task 13 的
#: `assert_contract_identity_frozen` 把磁盘 canonical digest 锁到 bundle slot digest）。
STAGED_WORD_CONTRACT_DIR: Path = _BACKEND / "data" / "workpaper_sync_word_contracts"


class WordFinalizeScriptError(RuntimeError):
    """脚本自身失败（禁 fail-open：让退出码非零，而不是降级成「无数据」）。"""


def load_word_lane_contract(contract_id: str) -> tuple[Any, str]:
    """读并强校验一份 Word per-entry 契约；返回 `(SyncContract, 来源)`。

    来源取值 `production_inventory` | `staged_word_lane`（生产清册优先）。解析一律走
    `contracts.parse_contract`，本函数只负责**定位文件**，不放宽任何判据；
    非 docx 契约直接拒（那是 Task 36 的 Excel 域）。
    """
    from app.services.workpaper_sync.contracts import contract_path_for, parse_contract

    if not contract_id or "/" in contract_id or "\\" in contract_id or ".." in contract_id:
        raise WordFinalizeScriptError(
            f"contract_id 形态非法（不得含路径分隔或 `..`）: {contract_id!r}"
        )
    production = contract_path_for(contract_id)
    staged = STAGED_WORD_CONTRACT_DIR / f"{contract_id}.json"
    for path, origin in ((production, "production_inventory"), (staged, "staged_word_lane")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WordFinalizeScriptError(
                f"Word 契约读不到或不是合法 JSON: {path} ({exc})"
            ) from exc
        contract = parse_contract(payload, adapter_id=contract_id)
        if contract.document_type != "docx":
            raise WordFinalizeScriptError(
                f"contract {contract_id} 的 document_type={contract.document_type!r} —— "
                "Word entry gate 只受理 docx，xlsx 走 Task 36"
            )
        return contract, origin
    raise WordFinalizeScriptError(
        f"contract {contract_id!r} 在生产清册与 Word 暂存目录里都不存在"
        f"（查过 {production.name} / {staged.name}）—— 缺契约时不得回退到"
        "「按 wp_code 猜」或「用别的 entry 的契约」"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 目标解析
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class WordFinalizeTarget:
    lane_entry_key: str
    entry_id: str
    contract_id: str
    wp_code: str
    template_ref: str
    project_id: uuid.UUID | None = None
    wp_id: uuid.UUID | None = None
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.wp_id is not None and self.project_id is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_entry_key": self.lane_entry_key,
            "entry_id": self.entry_id,
            "contract_id": self.contract_id,
            "wp_code": self.wp_code,
            "template_ref": self.template_ref,
            "project_id": None if self.project_id is None else str(self.project_id),
            "wp_id": None if self.wp_id is None else str(self.wp_id),
            "resolved": self.resolved,
            "unresolved_reason": self.unresolved_reason,
        }


def lane_entries() -> list[dict[str, Any]]:
    """从 Task 60 发布记录现读 lane entry（不抄第二份清单）。"""
    try:
        record = json.loads(PUBLICATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WordFinalizeScriptError(
            f"Word lane 发布记录读不到或不是合法 JSON: {PUBLICATION_PATH} ({exc})"
        ) from exc
    entries = record.get("entries") or []
    if not entries:
        raise WordFinalizeScriptError(
            f"{PUBLICATION_PATH.name} 的 `entries[]` 为空 —— 空清单会让本脚本恒成功（假绿）"
        )
    return list(entries)


async def resolve_targets(
    session: Any,
    *,
    entry_filter: str | None = None,
    project_filter: uuid.UUID | None = None,
) -> list[WordFinalizeTarget]:
    """按发布记录 × 真实底稿现算目标（缺目标时给显式原因，不静默跳过）。"""
    targets: list[WordFinalizeTarget] = []
    for row in lane_entries():
        contract_id = str(((row.get("contract") or {}).get("contract_id")) or "").strip()
        wp_code = str(row.get("wp_code") or "").strip()
        target = WordFinalizeTarget(
            lane_entry_key=str(row.get("lane_entry_key") or ""),
            entry_id=contract_id,
            contract_id=contract_id,
            wp_code=wp_code,
            template_ref=str(row.get("template_ref") or ""),
        )
        if entry_filter and target.entry_id != entry_filter:
            continue
        if not contract_id or not wp_code:
            target.unresolved_reason = (
                "发布记录里该 lane entry 缺 contract_id 或 wp_code —— 无法定位目标底稿"
            )
            targets.append(target)
            continue
        params: dict[str, Any] = {"code": wp_code}
        if project_filter is not None:
            params["pid"] = str(project_filter)
        sql = sa.text(
            "SELECT wp.id AS wp_id, wp.project_id AS project_id "
            "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
            "WHERE wi.wp_code = :code AND wp.is_deleted = false "
            + ("AND wp.project_id = :pid " if project_filter is not None else "")
            + f"ORDER BY {TARGET_ORDER_SQL} LIMIT 1"
        )
        hit = (await session.execute(sql, params)).mappings().first()
        if hit is None:
            target.unresolved_reason = (
                f"库里没有 wp_code={wp_code!r} 的未删除底稿"
                + (f"（且限定 project={project_filter}）" if project_filter else "")
                + " —— 该 Word lane entry 在本库没有承载它的业务底稿实例；这不是 gate 的"
                "缺陷，而是没有目标"
            )
            targets.append(target)
            continue
        target.project_id = uuid.UUID(str(hit["project_id"]))
        target.wp_id = uuid.UUID(str(hit["wp_id"]))
        targets.append(target)
    return targets


# ═══════════════════════════════════════════════════════════════════════════
# 2. 冻结声明（契约 + instrumentation payload；从 Task 60 生成器现算）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LaneDeclaration:
    entry_id: str
    contract: Any
    contract_origin: str
    spec: Any
    instrumentation_payload: dict[str, Any]
    template_bytes: bytes
    template_sha256: str


def load_lane_declaration(*, contract_id: str) -> LaneDeclaration:
    """现算该 lane entry 的契约 + instrumentation 声明（三边锁的前两边）。

    `import generate_task60_f2_word_contracts` 是刻意的：字段表、token 事实、
    payload 构造全部只有 Task 60 那一份实现。本脚本抄一份的后果不是「更独立」，
    而是任一侧改动都不打红。
    """
    import generate_task60_f2_word_contracts as gen

    from app.services.workpaper_sync import word_instrumentation as wi

    decls = [e for e in gen.ENTRIES if e.contract_id == contract_id]
    if len(decls) != 1:
        raise WordFinalizeScriptError(
            f"Task 60 生成器里 contract_id={contract_id!r} 现算到 {len(decls)} 条声明 —— "
            "一个 lane entry 只能有唯一声明"
        )
    decl = decls[0]
    contract, origin = load_word_lane_contract(contract_id)
    data = decl.template_path.read_bytes()
    facts = gen.token_facts(data)
    spec = gen.build_instrumentation_spec(decl, facts)
    payload = wi.build_word_instrumentation_payload(
        spec=spec,
        template_definition_sha256=contract.template_definition_sha256,
        template_sha256=hashlib.sha256(data).hexdigest(),
        gate=wi.WordSdtCarrierGate.load(),  # 注入侧投影；见 `run_offline_criteria` 的说明
    )
    return LaneDeclaration(
        entry_id=contract_id,
        contract=contract,
        contract_origin=origin,
        spec=spec,
        instrumentation_payload=dict(payload),
        template_bytes=data,
        template_sha256=hashlib.sha256(data).hexdigest(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. `--check`（只读；真跑四条判据）
# ═══════════════════════════════════════════════════════════════════════════


async def probe_candidate_state(
    session: Any, *, wp_id: uuid.UUID, entry_id: str
) -> dict[str, Any]:
    """只读探测该 entry 的 candidate / pointer / representation 现状。"""
    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperRepresentationUpgradeCandidate,
        WorkpaperSyncEntryState,
    )

    rows = (
        (
            await session.execute(
                sa.select(
                    WorkpaperRepresentationUpgradeCandidate.id,
                    WorkpaperRepresentationUpgradeCandidate.state,
                    WorkpaperRepresentationUpgradeCandidate.target_contract_definition_id,
                    WorkpaperRepresentationUpgradeCandidate.target_definition_bundle_id,
                )
                .where(
                    WorkpaperRepresentationUpgradeCandidate.wp_id == wp_id,
                    WorkpaperRepresentationUpgradeCandidate.entry_id == entry_id,
                )
                .order_by(WorkpaperRepresentationUpgradeCandidate.created_at)
            )
        )
        .mappings()
        .all()
    )
    pointer = (
        (
            await session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.wp_id == wp_id,
                    WorkpaperSyncEntryState.entry_id == entry_id,
                )
            )
        )
        .scalars()
        .first()
    )
    representations = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(WorkpaperContentRepresentation)
            .where(
                WorkpaperContentRepresentation.wp_id == wp_id,
                WorkpaperContentRepresentation.entry_id == entry_id,
            )
        )
    ).scalar_one()
    return {
        "candidates": [
            {
                "candidate_id": str(r["id"]),
                "state": str(r["state"]),
                "target_contract_definition_id": (
                    None
                    if r["target_contract_definition_id"] is None
                    else str(r["target_contract_definition_id"])
                ),
                "target_definition_bundle_id": (
                    None
                    if r["target_definition_bundle_id"] is None
                    else str(r["target_definition_bundle_id"])
                ),
            }
            for r in rows
        ],
        "current_representation_id": None if pointer is None else str(pointer),
        "representation_count": int(representations or 0),
    }


def run_offline_criteria(declaration: LaneDeclaration) -> dict[str, Any]:
    """在临时目录里现造 throwaway candidate，真跑四条 tagged-SDT 判据 + 两道门。

    这是 `--check` 的核心：判据必须**真的执行过**才算「接上了」。产物写系统临时目录、
    跑完即删；既不进 artifact store 也不进库。
    """
    from app.services.workpaper_sync import word_entry_gate as wg
    from app.services.workpaper_sync import word_instrumentation as wi
    from app.services.workpaper_sync.contracts import load_word_carrier_gate
    from app.services.workpaper_sync.word_sdt_engine import (
        WordEngineBinding,
        WordEngineMode,
    )

    # 🔴 两个 gate 类**不是**一回事，也不是第二真源：`contracts.CarrierGate`
    #    （`load_word_carrier_gate()`）是契约/engine 侧的裁决快照，
    #    `word_instrumentation.WordSdtCarrierGate` 是注入侧的同一份 JSON 的另一个投影
    #    （多带 `assert_evidence_fresh` 的 Tier A stale 门）。两者都从
    #    `onlyoffice_word_sdt_carrier_contract.json` 现读，谁都没有第二份清单。
    engine_gate = load_word_carrier_gate()
    inject_gate = wi.WordSdtCarrierGate.load()
    anchor = wg.assert_only_tag_anchor_is_usable(
        gate=engine_gate, entry_id=declaration.entry_id
    )
    blocked = wg.assert_blocked_carriers_have_no_exemption(
        gate=engine_gate, entry_id=declaration.entry_id, contract=declaration.contract
    )
    instrumented = wi.instrument_docx_bytes(
        declaration.template_bytes, declaration.spec, gate=inject_gate
    )
    readback = wi.read_back_word_tags(
        instrumented=instrumented, spec=declaration.spec, gate=inject_gate
    )
    inventory = wg.declared_tag_inventory(
        contract=declaration.contract,
        instrumentation_payload=declaration.instrumentation_payload,
        readback=readback,
        entry_id=declaration.entry_id,
    )
    binding = WordEngineBinding(
        contract=declaration.contract,
        entry_id=declaration.entry_id,
        mode=WordEngineMode.offline_candidate_validation,
        carrier_gate=engine_gate,
    )
    scratch = Path(tempfile.mkdtemp(prefix="tmp_task77_check_"))
    try:
        candidate = scratch / "candidate.docx"
        candidate.write_bytes(instrumented.instrumented_bytes)
        roundtrip = wg.verify_candidate_tag_roundtrip(
            candidate_path=candidate,
            binding=binding,
            scratch_dir=scratch,
            entry_id=declaration.entry_id,
        )
        wg.assert_tag_set_matches(
            inventory, roundtrip.observation, entry_id=declaration.entry_id
        )
        wg.assert_sdt_hierarchy_intact(
            inventory, roundtrip.observation, entry_id=declaration.entry_id
        )
        wg.assert_field_instance_counts(
            inventory, roundtrip.observation, entry_id=declaration.entry_id
        )
        return {
            "anchor": anchor,
            "blocked_carriers": list(blocked),
            "contract_origin": declaration.contract_origin,
            "inventory": inventory.as_dict(),
            "roundtrip": roundtrip.as_dict(),
            "structure_hash": wg.word_entry_structure_hash(
                contract=declaration.contract, inventory=inventory
            ),
            "criteria_executed": [
                "assert_only_tag_anchor_is_usable",
                "assert_blocked_carriers_have_no_exemption",
                "assert_word_only_equivalent",
                "assert_tag_set_matches",
                "assert_sdt_hierarchy_intact",
                "assert_field_instance_counts",
            ],
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


async def run_check(session: Any, targets: list[WordFinalizeTarget]) -> dict[str, Any]:
    from app.services.workpaper_sync.projection_provisioning import count_supply_rows
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(BACKEND_ROOT))
    report: dict[str, Any] = {
        "mode": "check",
        "supply_rows": await count_supply_rows(session),
        "entries": [],
        "errors": [],
    }
    for target in targets:
        item: dict[str, Any] = {"target": target.as_dict()}
        try:
            declaration = load_lane_declaration(contract_id=target.contract_id)
            item["offline_criteria"] = run_offline_criteria(declaration)
        except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并在收尾抛出（禁 fail-open）
            item["status"] = "error"
            item["error"] = f"{type(exc).__name__}: {exc}"
            report["entries"].append(item)
            report["errors"].append({"entry_id": target.entry_id, "error": item["error"]})
            continue
        if not target.resolved:
            item["status"] = "unresolved"
            report["entries"].append(item)
            continue
        state = await probe_candidate_state(
            session, wp_id=target.wp_id, entry_id=target.entry_id  # type: ignore[arg-type]
        )
        item["db_state"] = state
        ready = [
            c
            for c in state["candidates"]
            if c["target_definition_bundle_id"] and c["state"] in ("awaiting_contract", "ready")
        ]
        if state["representation_count"] and not ready:
            item["settlement"] = CHECK_ENTRY_STATES[3]
        elif not state["candidates"]:
            item["settlement"] = CHECK_ENTRY_STATES[2]
            item["settlement_reason"] = (
                f"entry {target.entry_id!r} 在 wp={target.wp_id} 上没有任何 upgrade "
                "candidate —— Task 59 的 versioned upgrader 尚未在本库对该底稿跑过"
            )
        elif not ready:
            item["settlement"] = CHECK_ENTRY_STATES[1]
            item["settlement_reason"] = (
                "candidate 存在但没有 approved definition bundle（Task 76 的受控 attach "
                "尚未绑定）—— `assert_candidate_finalizable` 会停在「缺 approved "
                "per-entry contract / bundle」"
            )
        else:
            item["settlement"] = CHECK_ENTRY_STATES[0]
            verdicts: list[dict[str, Any]] = []
            for cand in ready:
                try:
                    await resolution.assert_candidate_finalizable(
                        uuid.UUID(cand["candidate_id"])
                    )
                except Exception as exc:  # noqa: BLE001 - 记 ERROR 态，禁 fail-open
                    verdicts.append(
                        {
                            "candidate_id": cand["candidate_id"],
                            "finalizable": False,
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                verdicts.append({"candidate_id": cand["candidate_id"], "finalizable": True})
            item["finalizable_verdicts"] = verdicts
        item["status"] = "ok"
        report["entries"].append(item)
    report["ready_total"] = sum(
        1 for e in report["entries"] if e.get("settlement") == CHECK_ENTRY_STATES[0]
    )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# 4. `--apply`（真发布；字节只来自 candidate 自己）
# ═══════════════════════════════════════════════════════════════════════════


async def finalize_one(
    session: Any, *, target: WordFinalizeTarget, candidate_id: uuid.UUID, scratch_dir: Path
) -> dict[str, Any]:
    """对一个已 ready 的 candidate 跑 `finalizeCandidate(entry)`。

    🔴 字节来源只有 candidate 自己登记的 staged artifact —— 本函数没有任何模板入口，
    也没有 `instrument_docx_bytes`：审计师在 SDT 外编辑过的正文只可能被逐块保留。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperArtifact,
        WorkpaperRepresentationUpgradeCandidate,
    )
    from app.services.workpaper_sync.artifacts import (
        CanonicalArtifactRepository,
        StagedCandidate,
    )
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
    from app.services.workpaper_sync.materialize_coordinator import (
        build_materialize_coordinator,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService
    from app.services.workpaper_sync.word_entry_gate import (
        WordEntryDefinitionLoader,
        WordEntryFinalizeGate,
    )

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    resolution = CanonicalResolutionService(session, artifacts)
    declaration = load_lane_declaration(contract_id=target.contract_id)
    candidate = (
        await session.execute(
            sa.select(WorkpaperRepresentationUpgradeCandidate).where(
                WorkpaperRepresentationUpgradeCandidate.id == candidate_id
            )
        )
    ).scalar_one()
    artifact = (
        await session.execute(
            sa.select(WorkpaperArtifact).where(
                WorkpaperArtifact.id == candidate.staged_artifact_id
            )
        )
    ).scalar_one()
    candidate_path = artifacts.resolve_relative_path(str(artifact.relative_path))
    eq_path, eq_bytes = locate_candidate_evidence(
        candidate_path=candidate_path,
        expected_sha256=str(candidate.visible_equivalence_report_sha256 or ""),
    )
    staged = StagedCandidate(
        candidate_id=candidate.id,
        project_id=target.project_id,  # type: ignore[arg-type]
        wp_id=candidate.wp_id,
        entry_id=str(candidate.entry_id),
        path=candidate_path,
        relative_path=str(artifact.relative_path),
        sha256=str(artifact.sha256),
        size_bytes=int(artifact.size_bytes),
        document_type=str(artifact.document_type),
        # 由 DB 里登记的 artifact relative_path 的**目录部分** + 实际找到的文件名拼出。
        # 不引用任何 layout 常量（`.upgrade-candidates/` 的布局真源在
        # `CanonicalArtifactRepository`），因此这里不是第二真源。
        equivalence_relative_path=(
            str(artifact.relative_path).rsplit("/", 1)[0] + "/" + eq_path.name
        ),
        equivalence_sha256=hashlib.sha256(eq_bytes).hexdigest(),
        verified_before_move=True,
        verified_after_move=True,
    )
    bundle_id = candidate.target_definition_bundle_id
    if bundle_id is None:
        raise WordFinalizeScriptError(
            f"candidate {candidate_id} 没有 approved definition bundle —— 受控 attach "
            "（Task 76）尚未绑定，本脚本不代它绑"
        )
    bundle_sha = (
        await session.execute(
            sa.text(
                "SELECT canonical_payload_sha256 FROM working_paper_sync_definition_bundle "
                "WHERE id = :b"
            ),
            {"b": str(bundle_id)},
        )
    ).scalar_one()
    gate = WordEntryFinalizeGate(
        loader=WordEntryDefinitionLoader(session=session, resolution=resolution),
        resolution=resolution,
        coordinator=build_materialize_coordinator(session),
    )
    outcome = await gate.finalize_candidate(
        project_id=target.project_id,  # type: ignore[arg-type]
        entry_id=target.entry_id,
        candidate_id=candidate_id,
        staged_candidate=staged,
        contract=declaration.contract,
        contract_origin=declaration.contract_origin,
        instrumentation_payload=declaration.instrumentation_payload,
        frozen_bundle_sha256=str(bundle_sha),
        scratch_dir=scratch_dir,
        equivalence_report_bytes=eq_bytes,
    )
    return outcome.as_dict()


def locate_candidate_evidence(
    *, candidate_path: Path, expected_sha256: str
) -> tuple[Path, bytes]:
    """在 candidate 目录里按**内容寻址**找它自己的证据报告。

    按 digest 找而不是按文件名模板拼 —— `equivalence-{sha12}.json` 那条命名规则的单一
    真源是 `CanonicalArtifactRepository.stage_upgrade_candidate`，在这里再写一遍就是
    第二真源（改名时任一侧被短路都不打红）。找不到即 fail closed：没有反读等值证据
    不得 finalize（Requirement 6.18）。
    """
    if len(expected_sha256) != 64:
        raise WordFinalizeScriptError(
            f"candidate 登记的 visible_equivalence_report_sha256 非法: {expected_sha256!r}"
        )
    for path in sorted(candidate_path.parent.glob("*.json")):
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == expected_sha256:
            return path, data
    raise WordFinalizeScriptError(
        f"candidate 目录 {candidate_path.parent} 里找不到 digest={expected_sha256} 的证据"
        "报告 —— 证据缺失时不得 finalize，也不得用别的 candidate 的证据顶替"
    )


async def run_apply(session_factory: Any, targets: list[WordFinalizeTarget]) -> dict[str, Any]:
    from app.services.workpaper_sync.projection_provisioning import count_supply_rows

    report: dict[str, Any] = {"mode": "apply", "entries": [], "errors": []}
    async with session_factory() as probe:
        report["supply_rows_before"] = await count_supply_rows(probe)
    scratch_root = Path(tempfile.mkdtemp(prefix="tmp_task77_apply_"))
    try:
        for target in targets:
            item: dict[str, Any] = {"target": target.as_dict()}
            if not target.resolved:
                item["status"] = "unresolved"
                report["entries"].append(item)
                continue
            async with session_factory() as probe:
                state = await probe_candidate_state(
                    probe, wp_id=target.wp_id, entry_id=target.entry_id  # type: ignore[arg-type]
                )
            ready = [
                c
                for c in state["candidates"]
                if c["target_definition_bundle_id"]
                and c["state"] in ("awaiting_contract", "ready")
            ]
            if not ready:
                item["status"] = "blocked"
                item["db_state"] = state
                item["blocked_reason"] = (
                    f"entry {target.entry_id!r} 在 wp={target.wp_id} 上没有绑定 approved "
                    "bundle 的 candidate —— 前置是 Task 59 的 upgrader 产出 candidate + "
                    "Task 76 的受控 attach 绑定 approved contract/bundle。**不**为凑数造假"
                )
                report["entries"].append(item)
                continue
            # 一 entry 一事务：失败只回滚它自己。
            async with session_factory() as session:
                try:
                    item["outcome"] = await finalize_one(
                        session,
                        target=target,
                        candidate_id=uuid.UUID(ready[0]["candidate_id"]),
                        scratch_dir=scratch_root / target.entry_id.replace("/", "_"),
                    )
                    await session.commit()
                except Exception as exc:  # noqa: BLE001 - 记 ERROR 态并在收尾抛出
                    await session.rollback()
                    item["status"] = "error"
                    item["error"] = f"{type(exc).__name__}: {exc}"
                    report["entries"].append(item)
                    report["errors"].append(
                        {"entry_id": target.entry_id, "error": item["error"]}
                    )
                    continue
            item["status"] = "ok"
            report["entries"].append(item)
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
    async with session_factory() as probe:
        report["supply_rows_after"] = await count_supply_rows(probe)
    report["finalized_total"] = sum(1 for e in report["entries"] if e.get("status") == "ok")
    return report


# ═══════════════════════════════════════════════════════════════════════════
# 5. CLI
# ═══════════════════════════════════════════════════════════════════════════


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读预演（默认）")
    mode.add_argument("--apply", action="store_true", help="真 finalize 已 ready 的 candidate")
    parser.add_argument("--entry", default=None, help="只处理这一个 entry_id")
    parser.add_argument("--project-id", default=None, help="限定 project")
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    args = parser.parse_args(argv)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise WordFinalizeScriptError(
            "本脚本读写 V151 的真实表（含 CHECK/trigger），必须真实 PostgreSQL；"
            f"当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project_filter = uuid.UUID(args.project_id) if args.project_id else None
    try:
        async with Session() as session:
            targets = await resolve_targets(
                session, entry_filter=args.entry, project_filter=project_filter
            )
        if args.apply:
            report = await run_apply(Session, targets)
        else:
            async with Session() as session:
                report = await run_check(session, targets)
    finally:
        await engine.dispose()

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)
    if report["errors"]:
        raise WordFinalizeScriptError(
            f"{len(report['errors'])} 个 entry 失败（详见报告 errors）—— 不降级为成功"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
