"""OO→HTML 的 store 镜像视图（两层，都只给 store 镜像用、发布的 projection 不变）。

1. :func:`store_view_with_cleared_fields`：把 merge 判为「本次清空」的可编辑行字段补成显式 null（R17）；
2. :func:`store_view_with_recomputed_formulas`：把 merge 采纳的 OO 重算公式值放行进 store
   （spec oo-formula-recompute-not-tamper R3，见该函数）。

以下是第 1 层的说明。

═══ 修的是什么 ═══

OO 里清空一个受管格 ⇒ excel extract 读到空格 ⇒ **键缺失**（`excel_extract._collect_fields`：
「键缺失即 MISSING」）⇒ 三方 merge 走 `c == b ⇒ merged = i`，merged 里该键也缺失。content
version 因此正确地表达了「已清空」（键缺失与空格在 materialize/extract 两侧同口径）。

但 store 镜像（`store_mirror` → 各 provider 的 `merge_projection_into_store_rows`）只遍历
merged 里**存在**的键：被清空的键一次都不会被访问 ⇒ HTML store 原值保留 ⇒ 结构化视图仍显示
旧值；下一次进在线编辑时 HTML lane 把 store 冲刷成新 revision ⇒ **把用户在 OO 里的清空回滚**。
真库实证（重药安徽 D2）：rev6（OO，清空 `company_code`）与 rev5（html）只差这一个键；rev7（html，
下次进在线编辑时的冲刷）与 rev5 的 projection sha256 逐字节相同；store 的 `updated_at` 停在 rev4。

═══ 为什么只在镜像视图里补 ═══

* 发布出去的 projection 不动：在 extract 侧把空格改成显式 null 会让全部 entry 的 projection
  digest 与 roundtrip 等值判据一起变，辐射面是整个平台；
* merge 的真值表本就区分「清空（i=None）」与「载体删除（i=MISSING）」。xlsx 行内的空格不可能是
  载体删除（行身份在、列在），所以在**存活行**里被 merge 判掉的可编辑字段，就是被清空的字段；
* 各 provider 的 store 合并函数本就按「显式 null = 清空」处理（`assign_store_value` 等），在这里
  补一份视图即可让**全部** store-backed entry 同时生效，不必逐个 provider 改合并函数。

═══ 判据（全部同时成立才补 null）═══

1. 该键进过三方 merge（`merge.verdicts` 里有它 —— base/current/incoming 至少一侧有值）；
2. 最终发布的 projection 里没有它；
3. 契约里它是 xlsx **行域、可编辑、未受保护**的字段 —— 静态格清空在 merge 侧另有判定
   （`missing_identity_carrier`）；公式 / auto-source / 只读遮罩格不回写 store；
4. 它所在的行在最终 projection 里仍**存活**（`row_keys`）—— 整行消失是删行，镜像侧不推断删除
   （OO 路径零删除侧，见 `test_aos_oo_path_isolation`）。`row_deleted` verdict 必然落在这一条里
   （被接受的整行删除不留任何存活键），所以不另设 verdict 过滤 —— 那会是一条证伪不了的死分支。
"""

from __future__ import annotations

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, SyncContract
from app.services.workpaper_sync.merge import (
    ContractIndex,
    FieldVerdict,
    MergeInputError,
    MergeOutcome,
    UnknownStableKeyError,
)

__all__ = [
    "RecomputedFieldValue",
    "store_view_with_cleared_fields",
    "store_view_with_recomputed_formulas",
]


def store_view_with_cleared_fields(
    final: Projection,
    *,
    merge: MergeOutcome | None,
    contract: SyncContract | None,
) -> tuple[Projection, tuple[str, ...]]:
    """返回 `(交给 store 镜像的视图, 补了显式 null 的键)`；无可补时原样返回 `final`。"""
    if merge is None or contract is None or contract.document_type != "xlsx":
        return final, ()
    alive = {table: frozenset(rows) for table, rows in (final.row_keys or {}).items()}
    index: ContractIndex | None = None
    added: dict[str, FieldValue] = {}
    for key in merge.verdicts:
        if key in final.values:
            continue
        if index is None:
            index = ContractIndex(contract)
        try:
            locator = index.resolve(key)
        except (UnknownStableKeyError, MergeInputError):
            continue
        if not locator.row_key or locator.mode is not FieldMode.editable or locator.is_protected:
            continue
        if locator.row_key not in alive.get(locator.table_key or "", frozenset()):
            continue
        added[key] = FieldValue(
            stable_key=key,
            value=None,
            value_type=locator.value_type,
            mode=locator.mode,
            row_key=locator.row_key,
        )
    if not added:
        return final, ()
    view = Projection(
        contract_id=final.contract_id,
        semantic_version=final.semantic_version,
        document_type=final.document_type,
        values={**final.values, **added},
        row_keys=final.row_keys,
    )
    return view, tuple(sorted(added))


class RecomputedFieldValue(FieldValue):
    """被三方合并采纳的 OO 重算结果（公式字段）—— 只出现在 store 镜像视图里。

    store 合并函数（22 个模块 27 处）一律按 `fv.is_protected` 跳过公式字段：那条规则的本意是「OO 侧的
    公式缓存值不是权威值」。合并判 `took_recomputed` 时这一前提已经不成立 —— 公式完好、输入与合并
    结果一致，OO 算出的就是公式结果。这里只把「受保护」换成假，mode 仍是 formula：按自身契约
    过滤公式字段的 provider（如 B60 按 `MANAGED_FIELD_SPECS` 的 mode）照旧不写。
    """

    @property
    def is_protected(self) -> bool:  # type: ignore[override]
        return False


def store_view_with_recomputed_formulas(
    view: Projection, *, merge: MergeOutcome | None
) -> tuple[Projection, tuple[str, ...]]:
    """返回 `(交给 store 镜像的视图, 放行的键)`；无可放行时原样返回 `view`（spec R3.1）。

    不放行就会出现真库探针看到的情形：D2 store 存着期末余额 / 期末未审 / 期末审定，OO 改了输入后
    这三列在 store 里一直是旧值，D2-1 审定表按旧的期末未审 SUMIF、发布到试算表。
    """
    if merge is None:
        return view, ()
    keys = sorted(
        key
        for key, verdict in merge.verdicts.items()
        if verdict is FieldVerdict.took_recomputed
        and key in view.values
        and view.values[key].mode is FieldMode.formula
    )
    if not keys:
        return view, ()
    values = dict(view.values)
    for key in keys:
        fv = values[key]
        values[key] = RecomputedFieldValue(
            stable_key=fv.stable_key,
            value=fv.value,
            value_type=fv.value_type,
            mode=fv.mode,
            row_key=fv.row_key,
        )
    return (
        Projection(
            contract_id=view.contract_id,
            semantic_version=view.semantic_version,
            document_type=view.document_type,
            values=values,
            row_keys=view.row_keys,
        ),
        tuple(keys),
    )
