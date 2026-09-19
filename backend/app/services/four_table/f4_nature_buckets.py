"""F4 应付账款 —— 款项性质分类桶单一真源（跨前后端共用的唯一声明处）。

**桶定义取自源模板**（`backend/wp_templates/F/F4 应付账款.xlsx` → `审定表F4-1`
「一、按照性质分类」）::

    A8  货款      A9  工程款      A10 设备款      A11 服务费      A12 其他
    A13 合计 = SUM(A8:A12)

源模板该区**没有空白可扩行**（A8~A12 五行后直接是 A13 合计），故五桶是闭集；
上市披露 sheet 的 A9「可无限量添加行」是**披露表**侧的动态区，与审定表分类不同层。

**为什么按名称归类**

DB 只读实证 `2202` 的客户子科目命名（9 个在册项目）::

    2202.01 应付账款_应付货款          → goods
    2202.02 应付账款_暂估应付款        → other   （核算科目，非采购性质分类）
    2202.03 应付账款_红字信息表        → other
    2202.04 应付账款_预提供应商返利    → other
    2202.11 应付账款_工程设备款        → construction  ⚠ 见下方「已知歧义」
    2202.96 应付账款_门店统购款        → goods   （「统购」= 集中采购货款）
    2202.97 应付账款_进项税            → other
    2202.98 应付账款_商务系统          → other

编码与性质无稳定对应关系（`2202.11` 在另一变体是「自营拉新BD」），故只能按名称。

**已知歧义（须留证，不得静默）**

``2202.11 应付账款_工程设备款`` 同时含「工程」与「设备」，而源模板 A9 工程款、A10 设备款
是两个独立行，该叶子无法拆分。本模块把 ``construction`` 声明在 ``equipment`` **之前**
（依据 = 源模板行序 A9 先于 A10），故归「工程款」，并在归类结果上标 ``ambiguous`` →
溯源面板黄色提示，审计师可在审定表手工调整（预填只在无持久化时套用）。

**「其他」不是垃圾桶而是设计如此**：暂估应付款 / 红字信息表 / 预提返利 / 进项税 /
商务系统都是客户内部核算科目，不是采购性质分类，把它们塞进「货款」会让按性质分析失真。

**桶 key 与前端逐字一致**：``useF4Adjudication.F4_NATURE_DEFAULTS`` 用
``goods / construction / equipment / service / other``（同 F1 的
`F1_NATURE_ROW_KEYS`），本模块沿用，不另起 `project` 之类的新名。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 2.3, 2.4, 2.5 / Property 2, 4
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .leaf_aggregation import LeafRow


@dataclass(frozen=True)
class F4Bucket:
    """一个款项性质桶的声明（纯数据）。

    Attributes:
        key: 分类键，与前端 ``F4_NATURE_DEFAULTS`` 的 rowKey 逐字一致。
        label: 中文标签，只在此处声明一份。
        keywords: 名称匹配关键字。
        exclude_keywords: 否决词。
        source_ref: 源 xlsx 单元格。
        is_catchall: 兜底桶。
    """

    key: str
    label: str
    keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ""
    is_catchall: bool = False


#: 款项性质桶。**顺序即优先级** —— `construction` 必须先于 `equipment`
#: （`2202.11 工程设备款` 按源模板行序 A9 < A10 归工程款）。
F4_NATURE_BUCKETS: tuple[F4Bucket, ...] = (
    F4Bucket(
        key="construction",
        label="工程款",
        keywords=("工程", "施工", "基建", "安装"),
        source_ref="审定表F4-1!A9",
    ),
    F4Bucket(
        key="equipment",
        label="设备款",
        keywords=("设备", "器具", "固定资产", "长期资产"),
        source_ref="审定表F4-1!A10",
    ),
    F4Bucket(
        key="service",
        label="服务费",
        keywords=("服务", "劳务", "运费", "运输", "保养", "维修", "咨询", "租金"),
        source_ref="审定表F4-1!A11",
    ),
    F4Bucket(
        key="goods",
        label="货款",
        # 「统购」= 门店集中采购货款（实证 2202.96 应付账款_门店统购款）
        keywords=("货款", "货物", "材料", "商品", "采购", "统购", "药品", "存货"),
        # 「预提供应商返利」含「供应商」但不是货款；「进项税」含「税」不含货款关键字
        exclude_keywords=("返利", "暂估"),
        source_ref="审定表F4-1!A8",
    ),
    F4Bucket(
        key="other",
        label="其他",
        source_ref="审定表F4-1!A12",
        is_catchall=True,
    ),
)

F4_CATCHALL_KEY = next(b.key for b in F4_NATURE_BUCKETS if b.is_catchall)

#: 源模板行序（供审定表 / 披露表按此序列示，与 `F4_NATURE_BUCKETS` 的判定序不同）
F4_DISPLAY_ORDER: tuple[str, ...] = ("goods", "construction", "equipment", "service", "other")


def _matches(bucket: F4Bucket, name: str) -> bool:
    if any(x in name for x in bucket.exclude_keywords):
        return False
    return any(k in name for k in bucket.keywords)


def classify_f4_leaf(account_name: str, account_code: str = "") -> str:
    """把 `2202` 的一个叶子科目归入款项性质桶，返回 ``key``。

    只按名称判定（编码与性质无稳定对应，见模块 docstring）；``account_code``
    仅为签名对称保留，当前不参与判定。未命中一律归 ``other``（不丢科目）。
    """
    name = str(account_name or "")
    for bucket in F4_NATURE_BUCKETS:
        if _matches(bucket, name):
            return bucket.key
    return F4_CATCHALL_KEY


def f4_bucket_payload() -> list[dict]:
    """下发前端的桶定义（中文标签只此一份，按源模板行序）。"""
    by_key = {b.key: b for b in F4_NATURE_BUCKETS}
    return [
        {
            "key": k,
            "label": by_key[k].label,
            "is_catchall": by_key[k].is_catchall,
            "source_ref": by_key[k].source_ref,
            "keywords": list(by_key[k].keywords),
        }
        for k in F4_DISPLAY_ORDER
        if k in by_key
    ]


@dataclass(frozen=True)
class F4LeafNature:
    """一个叶子科目的性质归类结果（供溯源面板逐叶子展示）。"""

    code: str
    name: str
    bucket: str
    bucket_label: str
    opening: float = 0.0
    closing: float = 0.0
    matched_buckets: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ambiguous(self) -> bool:
        return len(self.matched_buckets) > 1

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "bucket": self.bucket,
            "bucket_label": self.bucket_label,
            "opening": round(self.opening, 2),
            "closing": round(self.closing, 2),
            "ambiguous": self.ambiguous,
            "matched_buckets": list(self.matched_buckets),
        }


_LABEL_BY_KEY = {b.key: b.label for b in F4_NATURE_BUCKETS}


def _all_matched(name: str) -> tuple[str, ...]:
    return tuple(b.key for b in F4_NATURE_BUCKETS if _matches(b, name))


def build_f4_leaf_natures(
    leaves: list[LeafRow],
    sign_map: dict[str, dict[str, int]] | None = None,
) -> list[F4LeafNature]:
    """逐叶子归类（纯函数）。

    Args:
        leaves: 已 `select_leaves` 的叶子行。
        sign_map: :func:`four_table.leaf_sign_map` 的输出（与科目族聚合同一符号约定）。
            🔴 期初 / 期末分别取符号 —— 实证 `52c04ed1` 的 `2202.04 预提供应商返利`
            期初方向 debit / 期末方向 credit，用单一方向算期初会多 2,116,034.22。
    """
    open_signs = (sign_map or {}).get("opening") or {}
    close_signs = (sign_map or {}).get("closing") or {}
    out: list[F4LeafNature] = []
    for row in leaves or []:
        key = classify_f4_leaf(row.account_name, row.account_code)
        out.append(
            F4LeafNature(
                code=row.account_code,
                name=row.account_name,
                bucket=key,
                bucket_label=_LABEL_BY_KEY.get(key, key),
                opening=row.opening * open_signs.get(row.account_code, 1),
                closing=row.closing * close_signs.get(row.account_code, 1),
                matched_buckets=_all_matched(row.account_name),
            )
        )
    return out


def build_f4_nature_prefill(natures: list[F4LeafNature]) -> dict[str, dict]:
    """按性质桶聚合为 F4-1 预填（桶合计取 ``abs()`` 归一为正数口径）。

    🔴 `2202` 在 `tb_balance` 存在两种存储约定并存，符号由
    `four_table.leaf_signs` 统一下发（见 `resolve_leaf_totals` 的实证表）。

    ⚠️ **先按桶求和再取绝对值**：同一桶内可能同时含借方性质叶子
    （`2202.03 红字信息表` 相对贷方主体为负）与贷方叶子，行级 abs 会让桶合计虚增
    并破坏与父科目额的勾稽（实证 `0ec33ac9`：232,903,579.67 + 24,864,901.78 −
    482,915.48 − 3,096,093.59 = 254,189,472.38 = 父额）。

    Returns:
        ``{key: {"opening","closing","label","codes"}}``；只含实际出现的桶。
    """
    out: dict[str, dict] = {}
    for n in natures or []:
        bucket = out.setdefault(
            n.bucket,
            {"opening": 0.0, "closing": 0.0, "label": n.bucket_label, "codes": []},
        )
        bucket["opening"] += n.opening
        bucket["closing"] += n.closing
        bucket["codes"].append(n.code)
    for bucket in out.values():
        bucket["opening"] = round(abs(bucket["opening"]), 2)
        bucket["closing"] = round(abs(bucket["closing"]), 2)
        bucket["codes"] = sorted(set(bucket["codes"]))
    return out


__all__ = [
    "F4_CATCHALL_KEY",
    "F4_DISPLAY_ORDER",
    "F4_NATURE_BUCKETS",
    "F4Bucket",
    "F4LeafNature",
    "build_f4_leaf_natures",
    "build_f4_nature_prefill",
    "classify_f4_leaf",
    "f4_bucket_payload",
]
