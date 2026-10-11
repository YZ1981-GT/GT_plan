"""骨架无关业务身份（spec workpaper-sync-switch-performance · P1 / 需求 2）。

═══ 为什么需要 ═══

HTML→OO 的幂等复用（AC 3.6）原先只认 ``projection_sha256`` 逐字节相等。真库实测
（和平药房 / 重药安徽 D2 的每一对 OO 版本 → HTML 版本）业务字段 **0 处差异**，摘要却恒不等，
差的全是模板骨架行（``GTROW-*``）：

* OO 侧 extract 把模板受管区里每一行带 UUID 的骨架行都读回来（materialize 永不收敛它们）；
* HTML 侧 overlay 以 store 行集合为准，store 不认领的骨架行连同其值一律不进投影（有意决策）；
* 两侧都有的骨架行**位置不同**（OO 物理序在表头，store 序在表尾），而 materialize 按身份落位、
  不按投影序搬行（HTML 全量物化后 OO 侧骨架行仍在原位，实测）。

于是「从 OO 保存回来、什么都没改、再进在线编辑」每次都走 9~15 s 全量物化，还多生成一个版本。

═══ 规范形 ═══

对 ``content_mutation._projection_payload`` 形态的载荷（落盘工件 / 现算两侧同构）：

1. 契约身份四项原样；
2. 每张表 T：非骨架行**保序**；骨架行只保留 HTML 侧（incoming）在 T 里声明的那些，按**集合**比较；
3. values：丢弃「row_key 是骨架身份 ∧ HTML 侧未在该 key 的表段声明该行 ∧ HTML 侧也没携带该 key」的值；
   其余（含 value / value_type / mode / row_key）原样严格比较。

═══ 正确性（命中 ⇒ 复用与全量物化等价）═══

全量物化只写投影里声明的行与携带的字段、永不收敛骨架身份、按身份落位 ⇒ 被本规范形忽略的
内容（HTML 侧既不声明也不携带的骨架行）在全量物化后**原样留在 OO 文件里**；其余部分严格相等 ⇒
物化产物在受管格上与当前 representation 相同。复用路径另行校验表示腿（当前 representation 挂在
基线 content version 上），bundle / substrate 身份不变。

🔴 只用于**复用判定**：不改任何落盘摘要（content version / pending / settlement 三处同源口径一字不动），
不进 extract / materialize / roundtrip 判据。骨架身份的唯一真源是 ``contracts.is_template_skeleton_identity``
（与 roundtrip 豁免、物化收敛豁免同源）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.services.workpaper_sync.contracts import is_template_skeleton_identity
from app.services.workpaper_sync.definitions import canonical_json_bytes

#: 规范形 schema（结构变化必须 +1，旧缓存/证据不得与新口径混比）。
BUSINESS_IDENTITY_SCHEMA = "wp-sync-business-identity:v1"

_IDENTITY_FIELDS = ("schema_version", "contract_id", "semantic_version", "document_type")


def _table_segment(stable_key: str) -> str | None:
    segment, sep, _rest = str(stable_key).partition("/")
    return segment if sep else None


def _declared_sets(declared: Mapping[str, Any] | None) -> dict[str, frozenset[str]]:
    return {
        str(table): frozenset(str(row) for row in (rows or ()))
        for table, rows in (declared or {}).items()
    }


@dataclass(frozen=True)
class IdentityComparison:
    """一次比较的结论 + 被忽略的骨架行 / 字段计数（判词说明用）。"""

    equal: bool
    ignored_skeleton_rows: int
    ignored_skeleton_values: int
    position_free_skeleton_rows: int

    def note(self) -> str:
        return (
            "template_skeleton_equivalent: 业务内容相同；忽略 HTML 侧未声明的模板骨架行 "
            f"{self.ignored_skeleton_rows} 行 / {self.ignored_skeleton_values} 个字段，"
            f"两侧都有的骨架行 {self.position_free_skeleton_rows} 行按集合比较（位置无关）"
        )


def skeleton_insensitive_identity(
    payload: Mapping[str, Any],
    *,
    declared: Mapping[str, Any] | None,
    carried_keys: frozenset[str] | None = None,
) -> tuple[dict[str, Any], int, int]:
    """返回 ``(规范形, 被丢弃的骨架行数, 被丢弃的骨架字段数)``。

    ``declared`` / ``carried_keys`` 都取自 **HTML 侧**（incoming）载荷：它声明了哪些行、携带了哪些键。
    ``carried_keys`` 为 ``None`` 时视为「全部携带」（即对 incoming 自身求规范形，什么都不丢）。
    """
    sets = _declared_sets(declared)
    dropped_rows = 0
    out_rows: dict[str, Any] = {}
    for table, rows in sorted((payload.get("row_keys") or {}).items()):
        allowed = sets.get(str(table), frozenset())
        order: list[str] = []
        skeletons: set[str] = set()
        for raw in rows or ():
            row = str(raw)
            if not is_template_skeleton_identity(row):
                order.append(row)
            elif row in allowed:
                skeletons.add(row)
            else:
                dropped_rows += 1
        out_rows[str(table)] = {"order": order, "skeletons": sorted(skeletons)}

    dropped_values = 0
    values: dict[str, Any] = {}
    for key, entry in (payload.get("values") or {}).items():
        stable_key = str(key)
        row_key = (entry or {}).get("row_key") if isinstance(entry, Mapping) else None
        if (
            carried_keys is not None
            and row_key is not None
            and is_template_skeleton_identity(str(row_key))
            and stable_key not in carried_keys
        ):
            table = _table_segment(stable_key)
            if table is None or str(row_key) not in sets.get(table, frozenset()):
                dropped_values += 1
                continue
        values[stable_key] = entry

    canonical = {
        "business_identity_schema": BUSINESS_IDENTITY_SCHEMA,
        **{name: payload.get(name) for name in _IDENTITY_FIELDS},
        "values": values,
        "row_keys": out_rows,
    }
    return canonical, dropped_rows, dropped_values


def compare_business_identity(
    base_payload: Mapping[str, Any], incoming_payload: Mapping[str, Any]
) -> IdentityComparison:
    """基线（当前 content version 落盘载荷）与 HTML 侧本次载荷是否骨架无关地相同。"""
    declared = incoming_payload.get("row_keys") or {}
    carried = frozenset(str(k) for k in (incoming_payload.get("values") or {}))
    base_form, dropped_rows, dropped_values = skeleton_insensitive_identity(
        base_payload, declared=declared, carried_keys=carried
    )
    incoming_form, _, _ = skeleton_insensitive_identity(
        incoming_payload, declared=declared, carried_keys=None
    )
    equal = canonical_json_bytes(base_form) == canonical_json_bytes(incoming_form)
    position_free = sum(len(t["skeletons"]) for t in incoming_form["row_keys"].values())
    return IdentityComparison(
        equal=equal,
        ignored_skeleton_rows=dropped_rows,
        ignored_skeleton_values=dropped_values,
        position_free_skeleton_rows=position_free,
    )


def business_identity_equal(
    base_payload: Mapping[str, Any], incoming_payload: Mapping[str, Any]
) -> bool:
    return compare_business_identity(base_payload, incoming_payload).equal


__all__ = [
    "BUSINESS_IDENTITY_SCHEMA",
    "IdentityComparison",
    "business_identity_equal",
    "compare_business_identity",
    "skeleton_insensitive_identity",
]
