# -*- coding: utf-8 -*-
"""发布时刻的 ``structure_hash``（BP-30）—— `published_identity_observer` 的伴生模块。

spec: published-representation-production-path-and-lane-adjudication / BP-30

═══ 为什么单独一个模块，而不是塞回观测器 ═════════════════════════════════════════

观测器 `published_identity_observer` 已在行数门禁 whitelist 上（基线 1341），而
whitelist 的语义是「打磨应让文件变小不变大」。本模块的三个函数是**发布时刻**才用的
新能力，与观测器的**请求时刻**职责可以干净切开，因此抽伴生模块 —— 这正是门禁提示的
首选做法（「请拆分文件或抽伴生模块（优先）」）。

🔴 **公式与实测原语一律从观测器 import，本模块零复制**：
`recompute_structure_hash` / `observe_structure_inventory` / `parse_identity_inventory`
/ `_frozen_anchors` 全部沿用它那一份。抽模块的目的是分职责，不是分真源 ——
复制一份公式就等于把 BP-30 的「两种语义」换成「两份实现」，迟早再漂一次。

═══ BP-30 是什么（一句话）═══════════════════════════════════════════════════════

修复前 `representation.structure_hash` 被两条路径写成两个**不可比**的量：发布时刻写
「整份 xlsx 字节摘要」，请求时刻按「契约 + 受管结构坐标」重算 ⇒ 刚发布的 entry 也判
`ObservedIdentityDriftError`，adapter 组装必失败，`bidirectional` 结构上永为 0。
本模块让发布时刻改用与请求时刻**同一个**公式。
"""

from __future__ import annotations

from typing import Any, Final, Mapping, Sequence

from app.services.excel_structure_fingerprint import (
    FingerprintError,
    identity_inventory,
    structure_fingerprint,
)
from app.services.workpaper_sync.contracts import SyncContract, assert_no_structure_drift
from app.services.workpaper_sync.published_identity_observer import (
    ArtifactUnreadableError,
    FrozenChildUnusableError,
    ObservationStage,
    ObservedIdentityDriftError,
    _frozen_anchors,
    _frozen_sheet_anchors,
    observe_structure_inventory,
    parse_identity_inventory,
    recompute_structure_hash,
)

__all__: Final = [
    "anchors_from_instrumentation_spec",
    "anchors_from_instrumentation_specs",
    "compute_structure_hash_from_artifact",
    "frozen_anchors_from_instrumentation",
]


def frozen_anchors_from_instrumentation(
    instrumentation: Mapping[str, Any],
) -> dict[str, str] | None:
    """公开的锚点提取入口（请求时刻口径）。

    发布时刻与请求时刻**必须**用同一套锚点定义，因此两边都经这里，而不是各自从
    payload 里挑字段。返回 ``None`` 表示 payload 不含完整锚点（调用方自行 fail closed）。
    """
    return _frozen_anchors(instrumentation)


def anchors_from_instrumentation_spec(spec: Any) -> dict[str, str]:
    """把 ``ExcelInstrumentationSpec`` 投影成与冻结 payload **同值**的四个锚点。

    请求时刻的锚点来自**已发布的** instrumentation definition payload（嵌套结构，经
    :func:`frozen_anchors_from_instrumentation` 提取）；而**首版发布时刻**那份 definition
    还没发布（它与 representation 在同一次事务里才成形），此刻只有 provider 的扁平输入
    规格。两者必须给出**同一组值**，否则两个时刻算出的 ``structure_hash`` 又不可比 ——
    那正是 BP-30 本身。取值逐项对应 ``build_instrumentation_payload``：

    ``sheet_key`` ← ``f"{template_id.lower()}-managed"`` ·
    ``table_name`` ← ``spec.table_name`` · ``uuid_column_letter`` ← ``spec.uuid_col`` ·
    ``metadata_sheet`` ← ``GT_SYNC_SHEET_NAME``（import 真源常量，不抄第二份：它同时被
    instrumentation 写进工作簿、被 gate 从业务枚举排除、被契约声明）。

    判据 ``TestBp30AnchorsAgreeAcrossMoments`` 用真实 pilot 的 spec 与
    ``build_instrumentation_payload`` 产出做逐键比对 —— 任一侧改构造式即打红。
    """
    from app.services.workpaper_sync.excel_instrumentation import GT_SYNC_SHEET_NAME

    template_id = str(getattr(spec, "template_id", "") or "").strip()
    table_name = str(getattr(spec, "table_name", "") or "").strip()
    uuid_col = str(getattr(spec, "uuid_col", "") or "").strip()
    if not (template_id and table_name and uuid_col):
        raise FrozenChildUnusableError(
            "instrumentation spec 缺 template_id / table_name / uuid_col —— "
            "发布时刻算 structure_hash 的锚点无从确定",
            stage=ObservationStage.observe_workbook,
            context={"stage": ObservationStage.observe_workbook.value},
        )
    return {
        "sheet_key": (
            str(getattr(spec, "resolved_sheet_key", "") or "").strip()
            or f"{template_id.lower()}-managed"
        ),
        "table_name": table_name,
        "uuid_column_letter": uuid_col,
        "metadata_sheet": GT_SYNC_SHEET_NAME,
    }


def anchors_from_instrumentation_specs(specs: Sequence[Any]) -> tuple[dict[str, str], ...]:
    """多受管 sheet：每张 spec 投影一组锚点（顺序与 instrumentation_specs / sheets 对齐）。"""
    anchors = [anchors_from_instrumentation_spec(spec) for spec in specs]
    for spec in specs:
        anchors.extend(_frozen_sheet_anchors({"transposed_sheets": getattr(spec, "transposed_sheets", ())}))
        anchors.extend(_frozen_sheet_anchors({"static_sheets": getattr(spec, "static_sheets", ())}))
    return tuple(anchors)


def compute_structure_hash_from_artifact(
    *,
    data: bytes,
    contract: SyncContract,
    instrumentation: Mapping[str, Any] | None = None,
    anchors: Mapping[str, str] | Sequence[Mapping[str, str]] | None = None,
) -> str:
    """**发布时刻**用与请求时刻观测器同一条链算 ``representation.structure_hash``。

    与 :func:`recompute_structure_hash` 共用同一个公式，且「从 artifact 字节实测受管
    结构」这段也复用观测器的同一批原语（``structure_fingerprint`` /
    ``identity_inventory`` / ``observe_structure_inventory``），不另写一份。

    🔴 **必须喂最终要发布的字节**，不是 instrumented substrate 的字节：materialize 会
    插行（D2 首版实测插 729 行），受管结构随之变化。喂 substrate 就等于冻结了一份
    materialize 之前的结构 ⇒ 请求时刻照样判漂移，BP-30 换个位置复发。

    锚点两条来源（**二选一，必须给一个**）：``instrumentation`` = 已发布的冻结
    definition payload（请求时刻口径）；``anchors`` = 由
    :func:`anchors_from_instrumentation_spec` / ``anchors_from_instrumentation_specs``
    从 provider spec 投影（首版发布时刻）。多 sheet 时 ``anchors`` 可为序列。

    失败一律抛，**不**回退到字节摘要：回退等于让「同构」这条承诺在出错时静默失效，
    而调用方拿到的仍是一个看起来正常的 64 位 hex。
    """
    if anchors is None:
        if instrumentation is None:
            raise FrozenChildUnusableError(
                "compute_structure_hash_from_artifact 必须给 instrumentation 或 anchors "
                "之一 —— 两者都缺时无从反读受管结构",
                stage=ObservationStage.observe_workbook,
                context={"stage": ObservationStage.observe_workbook.value},
            )
        sheet_anchors = _frozen_sheet_anchors(instrumentation)
        if not sheet_anchors:
            raise FrozenChildUnusableError(
                "冻结 instrumentation payload 缺 managed_sheets/table/uuid 列锚点 —— "
                "发布时刻算 structure_hash 的反读参数只能来自它，不得按 sheet 展示名猜",
                stage=ObservationStage.observe_workbook,
                context={"stage": ObservationStage.observe_workbook.value},
            )
    elif isinstance(anchors, Mapping):
        sheet_anchors = [dict(anchors)]
    else:
        sheet_anchors = [dict(item) for item in anchors]
        if not sheet_anchors:
            raise FrozenChildUnusableError(
                "compute_structure_hash_from_artifact 收到空 anchors 序列 —— "
                "无从反读受管结构",
                stage=ObservationStage.observe_workbook,
                context={"stage": ObservationStage.observe_workbook.value},
            )
    from app.services.workpaper_sync.published_identity_observer import collect_workbook_structure
    _, _, _, structure = collect_workbook_structure(
        data=data, contract=contract, sheet_anchors=sheet_anchors
    )
    assert_no_structure_drift(contract, structure)
    return recompute_structure_hash(contract=contract, observed_structure=structure)


async def load_frozen_structure_anchors(
    *, session: Any, resolution: Any, bundle: Any, document_type: str,
) -> tuple[dict[str, str], ...] | None:
    """Read only the supplied frozen bundle; Word/opaque keep their own identity.

    返回**全部**受管 sheet 锚点（多 sheet entry 时 structure_hash 必须覆盖 sibling）。
    """
    from app.services.workpaper_sync.definitions import BundleSlot, DefinitionKind, DefinitionState
    from app.services.workpaper_sync.published_identity_observer import (
        PublishedIdentityObserver,
        _frozen_sheet_anchors,
    )

    if document_type == "docx" or bundle.authority_model.value != "projection_contract":
        return None
    observer = PublishedIdentityObserver(session=session, resolution=resolution)
    context = {"definition_bundle_id": str(bundle.bundle_id)}
    child = await observer._load_child_row(
        slot=BundleSlot.instrumentation, bundle=bundle, context=context,
    )
    if child.kind != DefinitionKind.instrumentation.value or child.state != DefinitionState.approved.value:
        raise FrozenChildUnusableError(
            "Frozen instrumentation must be approved",
            stage=ObservationStage.frozen_children, context=context,
        )
    payload = await observer._read_definition_payload(child=child, context=context)
    sheet_anchors = tuple(_frozen_sheet_anchors(payload))
    if not sheet_anchors:
        raise FrozenChildUnusableError(
            "Frozen instrumentation is missing structure anchors",
            stage=ObservationStage.frozen_children, context=context,
        )
    return sheet_anchors
