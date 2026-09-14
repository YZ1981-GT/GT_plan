"""F3 应付票据 —— 票据种类分类桶单一真源（跨前后端共用的唯一声明处）。

**为什么必须按名称归类而不是按编码**

客户科目编码语义在项目间不稳定（平台已在存货 `14xx`、税金及附加 `6403`、营业成本
`6402/6404` 上反复实证）。应付票据虽然目前 9 个在册项目的编码较一致
（`2201.01` 银行承兑 / `2201.02` 商业承兑 / `2201.03` 信用证），但这不是标准科目表
的强制约定，故主判据一律取 ``account_name``，编码只作「名称完全不含任何关键字」时的
最后兜底（``code_hints``）。

**为什么要有「信用证」这一类**

源模板 `审定表F3-1` 只有 A7 银行承兑汇票 / A8 商业承兑汇票两个固定行，第 9~10 行是空白
可扩行；披露 sheet 的 A11 法规括注专门讨论供应链票据。但 DB 只读实证 `2201.03 信用证`
是**活体大额科目**：

    项目 0ec33ac9 / 2025   2201.03 信用证  期末 93,443,600.00（占 2201 的 92%）
    项目 a7fc75e5 / 2025   2201.03 信用证  期末 34,137,381.81
    项目 f064f5e4 / 2024   2201.03 信用证  期末 31,250,000.00

原实现的前端 `F3_CATEGORY_META` 只有 bank / commercial / supplychain / other 四类，
信用证被归入 ``other``，且该行仅在 F3-2 明细录入后才动态出现 → 四表入库后 F3-1
审定表这一大额科目**无处落数**。故本模块把「信用证」提为独立种类。

**顺序即优先级**（``F3_CATEGORIES`` 的声明顺序就是判定顺序）：
``supplychain`` 必须先于 ``bank`` —— 部分客户把供应链票据命名为「银行供应链票据」/
「XX 银行云信」，若先判 ``bank`` 会误归银行承兑汇票。

spec: .kiro/specs/f-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.4 / Property 2, 4
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .leaf_aggregation import LeafRow


@dataclass(frozen=True)
class F3Category:
    """一个票据种类桶的声明（纯数据，无行为）。

    Attributes:
        key: 分类键。**必须与前端 `useF3CrossSheet.F3CategoryKey` 逐字一致**。
        label: 中文标签。**只在此处声明一份**，前端经 render 下发的
            :func:`f3_category_payload` 消费，不得抄第二份。
        keywords: 名称匹配关键字（命中任一即归本桶）。
        exclude_keywords: 否决词 —— 名称含其中任一则本桶**不**命中，
            即便 ``keywords`` 已命中。
        code_hints: 编码兜底前缀，仅当名称完全不含任何桶的关键字时启用。
        source_ref: 源 xlsx 单元格（可追溯到运行时权威模板
            ``backend/wp_templates/F/F3 应付票据.xlsx``）。
        always_show: 源模板固定行 —— 无论四表是否有该种类，审定表/披露表恒列示。
        is_catchall: 兜底桶（未命中任何桶的叶子落此）。全表恰有一个。
    """

    key: str
    label: str
    keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    code_hints: tuple[str, ...] = ()
    source_ref: str = ""
    always_show: bool = False
    is_catchall: bool = False


#: 票据种类桶。**顺序即优先级**，改动顺序会改变归类结果（见 Property 4 反向自检）。
F3_CATEGORIES: tuple[F3Category, ...] = (
    F3Category(
        key="supplychain",
        label="供应链票据",
        # 「银行供应链票据」/「XX银行云信」等命名会同时含「银行」→ 必须先于 bank 判定
        keywords=("供应链", "云信", "信单", "秒兑", "e信"),
        source_ref="附注披露信息(上市公司)!A11",  # 法规括注：2023-1-1 起按应付票据处理
    ),
    F3Category(
        key="letter_of_credit",
        label="信用证",
        keywords=("信用证", "国内证", "L/C"),
        code_hints=("2201.03",),
        # 源模板 F3-1 第 9~10 行为空白可扩行，信用证落此区
        source_ref="审定表F3-1!A9",
    ),
    F3Category(
        key="bank",
        label="银行承兑汇票",
        keywords=("银行承兑", "银承", "银行"),
        exclude_keywords=("供应链", "云信", "信用证"),
        code_hints=("2201.01",),
        source_ref="审定表F3-1!A7",
        always_show=True,
    ),
    F3Category(
        key="commercial",
        label="商业承兑汇票",
        keywords=("商业承兑", "商承", "商业"),
        exclude_keywords=("供应链", "云信"),
        code_hints=("2201.02",),
        source_ref="审定表F3-1!A8",
        always_show=True,
    ),
    F3Category(
        key="other",
        label="其他",
        source_ref="审定表F3-1!A10",
        is_catchall=True,
    ),
)

#: 兜底桶 key（唯一）
F3_CATCHALL_KEY = next(c.key for c in F3_CATEGORIES if c.is_catchall)


def _matches(cat: F3Category, name: str) -> bool:
    if any(x in name for x in cat.exclude_keywords):
        return False
    return any(k in name for k in cat.keywords)


def classify_f3_leaf(account_name: str, account_code: str = "") -> str:
    """把 `2201` 的一个叶子科目归入票据种类桶，返回 ``key``。

    判定顺序：名称关键字（按 :data:`F3_CATEGORIES` 声明顺序，含否决词）→
    编码兜底 ``code_hints`` → 兜底桶 ``other``。

    Args:
        account_name: `tb_balance.account_name`（如 ``应付票据_银行承兑汇票``）。
        account_code: `tb_balance.account_code`（仅名称无线索时作兜底）。

    Returns:
        :data:`F3_CATEGORIES` 中某个 ``key``；恒非空（Property 2：不丢科目）。
    """
    name = str(account_name or "")
    for cat in F3_CATEGORIES:
        if _matches(cat, name):
            return cat.key
    code = str(account_code or "").strip()
    if code:
        for cat in F3_CATEGORIES:
            if any(code == h or code.startswith(h + ".") for h in cat.code_hints):
                return cat.key
    return F3_CATCHALL_KEY


def f3_category_payload() -> list[dict]:
    """下发前端的桶定义（中文标签只此一份）。

    前端据此决定审定表 / 披露表列示哪些分类行：``always_show`` 恒列示，
    其余「四表有金额或明细表已录入」才出行。
    """
    return [
        {
            "key": c.key,
            "label": c.label,
            "always_show": c.always_show,
            "is_catchall": c.is_catchall,
            "source_ref": c.source_ref,
        }
        for c in F3_CATEGORIES
    ]


@dataclass(frozen=True)
class F3LeafCategory:
    """一个叶子科目的归类结果（供溯源面板逐叶子展示）。"""

    code: str
    name: str
    bucket: str
    bucket_label: str
    opening: float = 0.0
    closing: float = 0.0
    matched_buckets: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ambiguous(self) -> bool:
        """名称命中多个桶（首个生效）—— 审计师需复核归类是否符合业务实质。"""
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


_LABEL_BY_KEY = {c.key: c.label for c in F3_CATEGORIES}


def _all_matched(name: str) -> tuple[str, ...]:
    """名称命中的**全部**桶（用于标记歧义，不改变归类结果）。"""
    return tuple(c.key for c in F3_CATEGORIES if _matches(c, name))


def build_f3_leaf_categories(
    leaves: list[LeafRow],
    sign_map: dict[str, dict[str, int]] | None = None,
) -> list[F3LeafCategory]:
    """逐叶子归类（纯函数）。

    Args:
        leaves: 已 `select_leaves` 的叶子行。
        sign_map: :func:`four_table.leaf_sign_map` 的输出
            ``{"opening": {code: ±1}, "closing": {code: ±1}}`` —— 让桶聚合与科目族
            聚合采用**同一符号约定**，否则「各桶之和 ≠ 叶子合计」（Property 2 失败）。
            🔴 期初 / 期末必须分别取符号：`tb_balance` 的 `opening_direction` 与
            `closing_direction` 可能不同（实证 `52c04ed1` 的 `2202.04`）。
            缺省视为全 ``+1``（原样求和约定）。
    """
    open_signs = (sign_map or {}).get("opening") or {}
    close_signs = (sign_map or {}).get("closing") or {}
    out: list[F3LeafCategory] = []
    for row in leaves or []:
        key = classify_f3_leaf(row.account_name, row.account_code)
        out.append(
            F3LeafCategory(
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


def build_f3_bucket_prefill(
    categories: list[F3LeafCategory],
) -> dict[str, dict]:
    """按桶聚合为审定表预填（桶合计取 ``abs()`` 归一为正数口径）。

    🔴 `tb_balance` 存在两种符号约定并存，由 `four_table.resolve_leaf_totals`
    自校验择优、`leaf_signs` 下发到每个叶子；此处**先按桶求和再取绝对值**
    （不在行级 abs）—— 同一桶内可能含借方性质叶子（余额相对主体为负），
    行级 abs 会让桶合计虚增、破坏与父科目额的勾稽。

    Returns:
        ``{key: {"opening","closing","label","codes"}}``；只含**实际出现**的桶
        （前端据此「只覆盖出现的类别」）。无叶子返回 ``{}``。
    """
    out: dict[str, dict] = {}
    for c in categories or []:
        bucket = out.setdefault(
            c.bucket,
            {"opening": 0.0, "closing": 0.0, "label": c.bucket_label, "codes": []},
        )
        bucket["opening"] += c.opening
        bucket["closing"] += c.closing
        bucket["codes"].append(c.code)
    for bucket in out.values():
        bucket["opening"] = round(abs(bucket["opening"]), 2)
        bucket["closing"] = round(abs(bucket["closing"]), 2)
        bucket["codes"] = sorted(set(bucket["codes"]))
    return out


__all__ = [
    "F3_CATCHALL_KEY",
    "F3_CATEGORIES",
    "F3Category",
    "F3LeafCategory",
    "build_f3_bucket_prefill",
    "build_f3_leaf_categories",
    "classify_f3_leaf",
    "f3_category_payload",
]
