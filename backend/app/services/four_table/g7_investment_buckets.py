"""G7 长期股权投资：叶子科目 → 业务桶 的**单一真源**（纯数据 + 纯函数，零 IO）。

**为什么不能把 `{'1511.01': 'cost'}` 写死在渲染策略里**

`1511` 的二级子科目编码是**客户自定义**的（`account_chart` 里 `source='standard'` 只有一级
`1511`，`.01/.02/.03/.04.01/.04.02` 全是 `source='client'`）。平台已有实证反例：`6403`
的 `.02` 在一家客户是「城市维护建设税」、在另一家是「车船税」 —— 编码语义跨客户冲突，
**只能按科目名称归类**，编码仅作兜底。

**为什么标签要集中在这里**

同一批中文标签原本要在四处出现：后端分类器、后端 `adjudication_prefill` 的行标签、
前端披露模型的列名、附注模板的表头。抄四份必然漂移。本模块是唯一真源：
后端两处直接读，前端经 render 下发的 ``bucket_defs`` 读，附注模板由幂等脚本从源 xlsx 读。

每项都带 :attr:`G7Bucket.source_ref` 指向源模板单元格，守卫用 openpyxl 直读交叉比对
（`backend/tests/four_table/test_g7_account_scope.py`），保证标签可回溯、不是"顺手写顺眼的"。

**变动性质 vs 被投资单位类别（关键区分）**

`损益调整` / `其他综合收益` / `其他权益变动` 描述的是**本期变动的原因**，不是
**被投资单位的类别**（子公司 / 合营 / 联营）。四表库里没有「这笔损益调整属于哪家被投资
单位」的信息，机械摊入前三类就是造假 → 这三个桶标 ``is_movement_nature=True``，
审定表预填时统一落到源模板每块**第 4 行空白可扩行**（合并空单元格
`长期股权投资审定表G7-1!A11:B11` 等本就是可改名占位行）。

spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/
      Requirements 1.5 / 2.3 / 11.3，Property 4 / 6 / 16
"""
from __future__ import annotations

from dataclasses import dataclass

#: 桶键 —— 被投资单位类别（进审定表「一/二/三」分类行）
BUCKET_SUBSIDIARY = "subsidiary"
BUCKET_JV = "jv"
BUCKET_ASSOCIATE = "associate"
#: 桶键 —— 变动性质（进审定表第 4 行「其他」占位行）
BUCKET_EQUITY_PROFIT = "equity_profit"
BUCKET_OCI = "oci"
BUCKET_OTHER_EQUITY = "other_equity"
#: 桶键 —— 备抵（独立段）
BUCKET_IMPAIRMENT = "impairment"

#: 审定表第 4 行占位行的桶键（`is_movement_nature=True` 的桶汇总到此）
BUCKET_OTHER = "other"


@dataclass(frozen=True)
class G7Bucket:
    """一个业务桶的声明。

    Attributes:
        bucket: 桶键（英文，稳定标识；前后端与持久化都用它，不用中文 label 作键）。
        label: 中文标签，**逐字取自源模板**（见 ``source_ref``）。
        source_ref: ``('sheet名!单元格', ...)`` —— 守卫用 openpyxl 直读，
            要求 ``label`` 在其中任一单元格文本（去空白后）中命中。
        name_keywords: 科目名称命中词（任一命中即归本桶）。
        exclude_keywords: 名称否决词（命中任一即**跳过**本桶）。
            🔴 必需：`其他权益变动_不属于其他综合收益` 同时含「其他综合收益」，
            不排除会被误判成 OCI。
        code_fallback: 名称全无命中时的**标准码**兜底前缀（不用客户自定义子科目码）。
        priority: 判定顺序，数字小者先判（先具体后泛化）。
        is_movement_nature: True = 变动性质，不是被投资单位类别（见模块 docstring）。
    """

    bucket: str
    label: str
    source_ref: tuple[str, ...]
    name_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    code_fallback: tuple[str, ...] = ()
    priority: int = 0
    is_movement_nature: bool = False


#: 源模板 sheet 名（守卫解析 ``source_ref`` 用；与源 xlsx tab 名逐字一致）
SHEET_ADJUDICATION = "长期股权投资审定表G7-1"
SHEET_DISCLOSURE_SOE = "附注披露信息（国企）"

#: 🔴 唯一真源。新增桶 / 改标签只改这里；改完守卫会要求 ``source_ref`` 能回溯到源模板。
G7_INVESTMENT_BUCKETS: tuple[G7Bucket, ...] = (
    G7Bucket(
        bucket=BUCKET_OCI,
        label="其他综合收益调整",
        source_ref=(f"{SHEET_DISCLOSURE_SOE}!G211",),
        name_keywords=("其他综合收益",),
        # 「不属于其他综合收益」也含「其他综合收益」→ 必须否决，否则 .04.02 被误判
        exclude_keywords=("不属于其他综合收益",),
        priority=10,
        is_movement_nature=True,
    ),
    G7Bucket(
        bucket=BUCKET_OTHER_EQUITY,
        label="其他权益变动",
        source_ref=(f"{SHEET_DISCLOSURE_SOE}!H211",),
        name_keywords=("其他权益变动", "不属于其他综合收益"),
        priority=20,
        is_movement_nature=True,
    ),
    G7Bucket(
        bucket=BUCKET_EQUITY_PROFIT,
        label="权益法下确认的投资损益",
        source_ref=(f"{SHEET_DISCLOSURE_SOE}!F211",),
        name_keywords=("损益调整", "投资损益"),
        priority=30,
        is_movement_nature=True,
    ),
    G7Bucket(
        bucket=BUCKET_IMPAIRMENT,
        label="长期股权投资减值准备",
        # A207 逐字为「减：长期股权投资减值准备」→ 含 label（守卫按包含判定）
        source_ref=(f"{SHEET_DISCLOSURE_SOE}!A207",),
        name_keywords=("减值准备", "计提减值"),
        code_fallback=("1512",),
        priority=40,
    ),
    G7Bucket(
        bucket=BUCKET_SUBSIDIARY,
        label="对子公司投资",
        source_ref=(
            f"{SHEET_DISCLOSURE_SOE}!A203",
            f"{SHEET_ADJUDICATION}!A8",
        ),
        name_keywords=("子公司",),
        priority=50,
    ),
    G7Bucket(
        bucket=BUCKET_JV,
        label="对合营企业投资",
        source_ref=(
            f"{SHEET_DISCLOSURE_SOE}!A204",
            f"{SHEET_ADJUDICATION}!A9",
        ),
        name_keywords=("合营",),
        priority=60,
    ),
    G7Bucket(
        bucket=BUCKET_ASSOCIATE,
        label="对联营企业投资",
        source_ref=(
            f"{SHEET_DISCLOSURE_SOE}!A205",
            f"{SHEET_ADJUDICATION}!A10",
        ),
        name_keywords=("联营",),
        priority=70,
    ),
)

#: 审定表第 4 行占位行的标签（源模板该行为空白可改名，故标签由平台给，标注来源）
BUCKET_OTHER_LABEL = "四、其他（损益调整 / 其他权益变动，四表带入）"

#: 被投资单位类别桶（审定表「一/二/三」分类行）
CATEGORY_BUCKETS: tuple[str, ...] = (
    BUCKET_SUBSIDIARY,
    BUCKET_JV,
    BUCKET_ASSOCIATE,
)

#: 变动性质桶（汇总进 `other`）
MOVEMENT_NATURE_BUCKETS: tuple[str, ...] = tuple(
    b.bucket for b in G7_INVESTMENT_BUCKETS if b.is_movement_nature
)

_BY_BUCKET: dict[str, G7Bucket] = {b.bucket: b for b in G7_INVESTMENT_BUCKETS}
_ORDERED: tuple[G7Bucket, ...] = tuple(
    sorted(G7_INVESTMENT_BUCKETS, key=lambda b: b.priority)
)


def bucket_def(bucket: str) -> G7Bucket | None:
    """按桶键取声明；未知桶返 ``None``。"""
    return _BY_BUCKET.get((bucket or "").strip())


def bucket_label(bucket: str) -> str:
    """按桶键取中文标签；未知桶返桶键本身（不编造）。"""
    b = bucket_def(bucket)
    return b.label if b else (bucket or "")


def classify_g7_leaf(name: str, code: str = "") -> str | None:
    """把一个叶子科目归入业务桶。**名称优先、编码兜底**，纯函数。

    判定按 :attr:`G7Bucket.priority` 升序，首个「命中 ``name_keywords`` 且不命中
    ``exclude_keywords``」的桶胜出。名称全无命中时才按 ``code_fallback`` 前缀判定
    （要求点号边界，`1512` 只匹配 `1512` 或 `1512.xxx`，不匹配 `15120`）。

    Returns:
        桶键；无法归类返回 ``None``（调用方须放 ``unmapped``，不得塞进任何桶）。

    实证样本（项目 `2aa00f57` / `0ec33ac9` / `c8621493`）::

        长期股权投资_对子公司的投资              → subsidiary
        长期股权投资_联营企业投资成本            → associate
        长期股权投资_损益调整                    → equity_profit
        长期股权投资_其他权益变动_属于其他综合收益   → oci
        长期股权投资_其他权益变动_不属于其他综合收益 → other_equity
        长期股权投资减值准备                     → impairment
    """
    nm = (name or "").strip()
    cd = (code or "").strip()

    if nm:
        for b in _ORDERED:
            if b.exclude_keywords and any(k in nm for k in b.exclude_keywords):
                continue
            if any(k in nm for k in b.name_keywords):
                return b.bucket

    if cd:
        for b in _ORDERED:
            for p in b.code_fallback:
                if cd == p or cd.startswith(p + "."):
                    return b.bucket
    return None


def bucket_defs_payload() -> list[dict]:
    """供 render 下发前端的桶声明（前端**不再抄一份中文标签**）。

    只透出前端需要的字段：桶键 / 标签 / 是否变动性质；关键字与 ``source_ref``
    是后端判定与守卫用的实现细节，不外泄。
    """
    return [
        {
            "bucket": b.bucket,
            "label": b.label,
            "is_movement_nature": b.is_movement_nature,
        }
        for b in _ORDERED
    ] + [
        {"bucket": BUCKET_OTHER, "label": BUCKET_OTHER_LABEL, "is_movement_nature": True}
    ]


__all__ = [
    "BUCKET_ASSOCIATE",
    "BUCKET_EQUITY_PROFIT",
    "BUCKET_IMPAIRMENT",
    "BUCKET_JV",
    "BUCKET_OCI",
    "BUCKET_OTHER",
    "BUCKET_OTHER_EQUITY",
    "BUCKET_OTHER_LABEL",
    "BUCKET_SUBSIDIARY",
    "CATEGORY_BUCKETS",
    "G7Bucket",
    "G7_INVESTMENT_BUCKETS",
    "MOVEMENT_NATURE_BUCKETS",
    "SHEET_ADJUDICATION",
    "SHEET_DISCLOSURE_SOE",
    "bucket_def",
    "bucket_defs_payload",
    "bucket_label",
    "classify_g7_leaf",
]
