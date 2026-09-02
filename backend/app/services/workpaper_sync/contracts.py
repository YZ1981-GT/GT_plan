"""`SyncContract` —— per-entry 语义契约的强校验器（Task 13）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
Requirements 1.4 / 6.1 / 6.2 / 6.3 / 6.10 / 6.14 / 6.20 / 9.8 / 12.1
Property 3（未注册 adapter 不得宣称双向）/ 20（generated col 占位不可注册生产
adapter）/ 21（contract 字段完整）/ 28（immutable definition 漂移 fail closed）。

## 与 Task 12 的分工（**本模块不重写任何已有判据**）

`definitions.py` 已经拥有下列单一真源，本模块一律 import 复用：

* `canonical_json_bytes` / `canonical_digest` —— canonical bytes 与 digest；
* `validate_contract_payload` —— payload 级判据（`schema_version` 前缀、禁自引用
  artifact UUID/hash、必须单向引用 template + instrumentation digests、禁前向
  引用 bundle digest）；
* `PublishStage` / `assert_publish_order` —— 发布 DAG。

本模块**只**补 `definitions.validate_contract_payload` 拿不到的那一层：**字段级
语义**（stable key / JSON Pointer / cell / mode / value_type / source_ref /
row identity / 动态列 / footer anchor / formula mask / delete policy / identity
载体）。两侧刻意不重合 —— 重合的实现会让任一侧被短路都不改变行为，变异检验判
GREEN（Task 10~12 已实测过这个坑）。

## identity 载体不硬编码

允许进入生产契约的 identity 载体与结构锚点，真源是 Task 5 / Task 6 的**真实
OnlyOffice 9.4 黑盒探针裁决**：

* `backend/data/onlyoffice_excel_identity_carrier_contract.json`
  → `gate_for_downstream_tasks.task_17_instrumentation_definition`
* `backend/data/onlyoffice_word_sdt_carrier_contract.json`
  → `downstream_gate`

本模块从这两份 JSON 读取 allowlist/blocklist 与逐条 `probe_verdict`，**不在代码
里复制载体名单**。因此 `row_sdt`（Word row 级 SDT）在 OO 9.4 上 `failed`，任何
声明它的契约都会被拒 —— 即使 design.md 的 Word 契约示例写的正是
`repeaters[].row_tag = "gt:row:..."`。Word 行身份只能走探针实测通过的
`cell_level_field_sdt_tag_carrying_row_uuid`（单元格内 inline field SDT 的 tag
携带 row_uuid）。

## 失败模式清册（守卫逐条要有反例）

======  ===========================================  ==========================
编号    反例                                          判据
======  ===========================================  ==========================
CS-1    `review_status != "reviewed"`                 生成器候选不得注册生产
CS-2    `contract_id` ≠ 文件名/adapter_id              契约身份与 adapter 未锁死
CS-3    `col_a` / `col_bc` 形态出现在 stable key       generated 占位当写格契约
CS-4    field 缺 `source_ref`                          无来源自造字段
CS-5    field 缺 stable key / pointer / mode / type    contract 字段不完整
CS-6    xlsx editable/formula field 缺 `cell`          缺 OO 位置
CS-7    JSON Pointer 非 RFC 6901                       pointer 形态非法
CS-8    row 域 field pointer 缺 `{row_uuid}`           行字段未绑定行身份
CS-9    非 row field pointer 含 `{row_uuid}`/`*`       非行字段冒充行字段
CS-10   `row_identity.kind` ∈ index/ordinal/position   用下标当持久化身份
CS-11   `dynamic_columns.identity` ≠ `{slot}_{seq}`     可改 label 当 identity
CS-12   `footer_anchor` 用行号而非 marker               位置猜测
CS-13   formula 模式 field 的列不在 `formula_mask`       受保护单元格未声明只读
CS-14   动态行表缺 `delete_policy` / `row_identity`      删除策略未裁决
CS-15   stable key / sdt_tag 含非 ASCII（中文 label）    identity 依赖中文标签
CS-16   sheet locator anchor ∈ probe blocklist          未过 probe gate 的锚点
CS-17   identity carrier ∈ probe blocklist              未过 probe gate 的载体
CS-18   identity carrier 未在 probe 契约登记             未登记载体
CS-19   `document_type` 与载体/字段形态不符              文档类型串用
CS-20   extract 既无 instrumented identity 也无锚点      必须 fail closed，禁降级
======  ===========================================  ==========================

CS-3 与 CS-4 必须是**两条独立判据**：Property 20 的原文是「含无语义
`col_[a-z]+` **且**无人工 stable key/source_ref 时校验失败」，但两者合成一条
之后，把 `col_` 形态检查删掉仍会被 `source_ref` 缺失挡住 ⇒ 变异 GREEN。故本模块
对 `col_[a-z]+` 形态**无条件**拒绝（有 source_ref 也不放行：占位键本身不可作
写格身份），并单独要求 `source_ref`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.canonical_interop import assert_cross_language_safe
from app.services.workpaper_sync.definitions import (
    canonical_digest,
    canonical_json_bytes,
    validate_contract_payload,
)
from app.services.workpaper_sync.models import (
    BundleSlot,
    BundleSlotSpec,
    IdentityError,
    SyncDomainError,
    is_digest,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 路径与常量
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND: Final[Path] = Path(__file__).resolve().parents[3]

#: per-entry contract 的真源目录（design §Contract schema）。文件名 = `{adapter_id}.json`。
CONTRACTS_DIR: Final[Path] = _BACKEND / "data" / "workpaper_sync_contracts"

#: Task 5 / Task 6 的 probe gate 真源。允许载体/锚点**只**从这两份读，不在代码里复制。
EXCEL_CARRIER_CONTRACT_PATH: Final[Path] = (
    _BACKEND / "data" / "onlyoffice_excel_identity_carrier_contract.json"
)
WORD_CARRIER_CONTRACT_PATH: Final[Path] = (
    _BACKEND / "data" / "onlyoffice_word_sdt_carrier_contract.json"
)

#: contract canonical payload 的 schema version 前缀（与 `definitions._require_schema_version`
#: 的 `contract-definition:` 约定一致；具体版本号由 payload 自带）。
CONTRACT_SCHEMA_VERSION: Final[str] = "contract-definition:v1"

#: 支持的文档类型（与 `working_paper_content_representation.document_type` 同域）。
DOCUMENT_TYPES: Final[frozenset[str]] = frozenset({"xlsx", "docx"})

#: generated YAML 的无语义列占位形态（Requirement 6.1 / Property 20）。
#: `col_a` / `col_b` / `col_aa` 都是 openpyxl 导出骨架的产物，永不可作写格身份。
_GENERATED_COLUMN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"^col_[a-z]+$")

#: stable field key 允许的字符：小写 ASCII + 数字 + `_` `-` `.` `/` 与模板占位 `{}`。
#: 刻意不允许中文/空格/大写 —— Requirement 6.14「identity 不得依赖……中文 label」。
_STABLE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_.\-/{}]*$")

#: 动态列 identity 的**唯一**合法模板（Requirement 6.4 / 平台 H7 范式）。
DYNAMIC_COLUMN_IDENTITY_TEMPLATE: Final[str] = "{slot}_{seq}"

#: 行身份占位符。field pointer 里出现且仅出现一次表示「该字段按行展开」。
ROW_UUID_PLACEHOLDER: Final[str] = "{row_uuid}"

#: A1 列名（最多三字母，Excel 上限 XFD）。
_A1_COLUMN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{1,3}$")

#: A1 区域，如 `I8:I200`。单格形态 `I8` 亦允许（视作 1×1 区域）。
_A1_RANGE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<c1>[A-Z]{1,3})(?P<r1>[1-9][0-9]*)(?::(?P<c2>[A-Z]{1,3})(?P<r2>[1-9][0-9]*))?$"
)

#: RFC 6901 转义：`~` 只能以 `~0` / `~1` 出现。
_BAD_TILDE_RE: Final[re.Pattern[str]] = re.compile(r"~(?![01])")

#: Word SDT tag 形态：`gt:{kind}:{contract_id}:{stable_key}`。
_SDT_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"^gt:(?P<kind>field|block):(?P<contract>[a-z0-9][a-z0-9_.\-]*):(?P<key>[A-Za-z0-9_.\-/{}]+)$"
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 枚举
# ═══════════════════════════════════════════════════════════════════════════


class ContractReviewStatus(str, Enum):
    """契约审核态。生成器只能产 `candidate`；只有 `reviewed` 可注册生产 adapter。"""

    candidate = "candidate"
    reviewed = "reviewed"


class FieldMode(str, Enum):
    """字段模式（design §Merge Algorithm 的 `FieldValue.mode` 同域）。"""

    editable = "editable"
    formula = "formula"
    auto_source = "auto_source"
    word_only = "word_only"


#: 受保护模式：默认只读，OO 侧修改 SHALL 产生受保护字段冲突（Requirement 6.6）。
PROTECTED_MODES: Final[frozenset[FieldMode]] = frozenset(
    {FieldMode.formula, FieldMode.auto_source}
)


class ValueType(str, Enum):
    """值类型封闭枚举。merge 的类型规范化按此分派，禁自由文本。"""

    text = "text"
    amount = "amount"
    integer = "integer"
    rate = "rate"
    ratio = "ratio"
    date = "date"
    datetime = "datetime"
    boolean = "boolean"
    enum = "enum"
    json = "json"


class RowIdentityKind(str, Enum):
    """行身份来源。刻意**不**提供 index/ordinal/position（Requirement 6.5）。"""

    field = "field"
    template_row_key = "template_row_key"


#: 明确拒绝的行身份写法。单独列出来是为了给出可操作的错误文案，而不是只报「未登记枚举」。
FORBIDDEN_ROW_IDENTITY_KINDS: Final[frozenset[str]] = frozenset(
    {"index", "ordinal", "position", "row_number", "array_index"}
)


class DeletePolicy(str, Enum):
    """动态行删除策略（Requirement 6.9 / 6.15）。"""

    tombstone = "tombstone"
    reject = "reject"


class ExtractCarrierTier(str, Enum):
    """extract 载体优先级（Requirement 6.20）。"""

    instrumented_identity = "instrumented_identity"
    native_structural_anchor = "native_structural_anchor"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 异常
# ═══════════════════════════════════════════════════════════════════════════


class ContractError(SyncDomainError):
    error_code = "sync_contract_invalid"


class ContractSchemaError(ContractError):
    """字段级语义不合法（CS-1 ~ CS-15、CS-19）。"""

    error_code = "sync_contract_schema_invalid"


class ContractCarrierGateError(ContractError):
    """identity 载体/结构锚点未通过真实 OO probe gate（CS-16 ~ CS-18）。"""

    error_code = "sync_contract_carrier_not_gated"


class ContractCarrierUnavailableError(ContractError):
    """extract 既无 instrumented identity 也无已验证原生锚点（CS-20 / Requirement 6.20）。

    🔴 与 :class:`ContractCarrierGateError` 分成两类：前者是「契约声明了不该用的载体」
    （契约错），后者是「运行时两级载体都不存在」（运行态错）。共用一个类型时，把
    gate 判据短路掉之后运行态分支会抛同一类型把它遮蔽 ⇒ 只断言类型的守卫判 GREEN。
    """

    error_code = "sync_contract_extract_carrier_unavailable"


class ContractDriftError(ContractError):
    """契约声明的受管 identity 与实测结构不一致（Requirement 6.10 / Property 28）。"""

    error_code = "sync_contract_structure_drift"


# ═══════════════════════════════════════════════════════════════════════════
# 3. probe gate 真源加载
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CarrierGate:
    """一个文档类型的 probe gate 裁决快照（从 Task 5/6 契约 JSON 读出，不含代码常量）。"""

    document_type: str
    source_path: Path
    source_digest: str
    allowed_carriers: frozenset[str]
    blocked_carriers: frozenset[str]
    allowed_anchors: frozenset[str]
    blocked_anchors: frozenset[str]
    verdicts: Mapping[str, str]

    def assert_carrier(self, carrier: str, *, location: str) -> None:
        """载体必须已登记且在 allowlist 内（CS-17 / CS-18）。"""
        if carrier not in self.verdicts:
            raise ContractCarrierGateError(
                f"{location}: identity 载体 {carrier!r} 未在 {self.source_path.name} 登记 —— "
                f"未过真实 OO probe gate 的载体不得进入生产契约"
                f"（已登记 {sorted(self.verdicts)}）"
            )
        if carrier in self.blocked_carriers:
            raise ContractCarrierGateError(
                f"{location}: identity 载体 {carrier!r} 的真实 OO 9.4 探针裁决为 "
                f"{self.verdicts[carrier]!r}，已被 {self.source_path.name} 列入 blocklist；"
                "必须先经 design 换稳定载体，禁止降级使用"
            )
        if carrier not in self.allowed_carriers:
            raise ContractCarrierGateError(
                f"{location}: identity 载体 {carrier!r} 不在 probe gate allowlist "
                f"{sorted(self.allowed_carriers)} 内"
            )

    def assert_anchor(self, anchor: str, *, location: str) -> None:
        """结构锚点必须已登记且在 allowlist 内（CS-16）。"""
        if anchor not in self.verdicts:
            raise ContractCarrierGateError(
                f"{location}: 结构锚点 {anchor!r} 未在 {self.source_path.name} 登记"
                f"（已登记 {sorted(self.verdicts)}）"
            )
        if anchor in self.blocked_anchors:
            raise ContractCarrierGateError(
                f"{location}: 结构锚点 {anchor!r} 的真实 OO 9.4 探针裁决为 "
                f"{self.verdicts[anchor]!r}，已被 {self.source_path.name} 列入 blocklist"
            )
        if anchor not in self.allowed_anchors:
            raise ContractCarrierGateError(
                f"{location}: 结构锚点 {anchor!r} 不在 probe gate allowlist "
                f"{sorted(self.allowed_anchors)} 内"
            )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractCarrierGateError(
            f"probe gate 真源缺失: {path} —— 没有真实 OO 探针裁决时不得注册任何生产 adapter"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContractCarrierGateError(f"probe gate 真源不是合法 JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractCarrierGateError(f"probe gate 真源根必须是对象: {path}")
    return payload


def _section_verdicts(
    payload: Mapping[str, Any], *, section: str, key: str
) -> dict[str, str]:
    """读 `carriers[]` 或 `anchors[]` 的逐条 `probe_verdict`。

    载体与锚点**分开返回**：合成一张表之后 `sheet_id`（一个 failed 的锚点）会同时
    被算进 blocked_carriers，虽然拒绝行为正确但诊断文案会指错类别。
    """
    out: dict[str, str] = {}
    for item in payload.get(section) or []:
        if not isinstance(item, Mapping):
            raise ContractCarrierGateError(f"probe gate 的 {section}[] 元素必须是对象")
        name = item.get(key)
        verdict = item.get("probe_verdict")
        if not isinstance(name, str) or not name.strip():
            raise ContractCarrierGateError(f"probe gate 的 {section}[] 缺 {key!r}")
        if not isinstance(verdict, str) or not verdict.strip():
            raise ContractCarrierGateError(
                f"probe gate 的 {section}[{name}] 缺 `probe_verdict` —— "
                "载体裁决必须是机器可读值，不能靠自由文本"
            )
        out[name.strip()] = verdict.strip()
    if not out:
        raise ContractCarrierGateError(f"probe gate 真源的 {section}[] 没有任何裁决")
    return out


@lru_cache(maxsize=None)
def load_excel_carrier_gate() -> CarrierGate:
    """Excel identity 载体 gate（Task 5 真值表）。"""
    payload = _read_json(EXCEL_CARRIER_CONTRACT_PATH)
    gate = payload.get("gate_for_downstream_tasks") or {}
    node = gate.get("task_17_instrumentation_definition") or {}
    carrier_verdicts = _section_verdicts(payload, section="carriers", key="carrier")
    anchor_verdicts = _section_verdicts(payload, section="anchors", key="anchor")
    allowed_carriers = frozenset(node.get("allowed_carriers") or ())
    allowed_anchors = frozenset(node.get("allowed_anchors") or ())
    forbidden_anchors = frozenset(node.get("forbidden_anchors") or ())
    if not allowed_carriers or not allowed_anchors:
        raise ContractCarrierGateError(
            f"{EXCEL_CARRIER_CONTRACT_PATH.name} 的 "
            "`gate_for_downstream_tasks.task_17_instrumentation_definition` 缺 "
            "allowed_carriers/allowed_anchors —— gate 为空等于放行一切"
        )
    return CarrierGate(
        document_type="xlsx",
        source_path=EXCEL_CARRIER_CONTRACT_PATH,
        source_digest=canonical_digest(payload),
        allowed_carriers=allowed_carriers,
        blocked_carriers=frozenset(carrier_verdicts) - allowed_carriers,
        allowed_anchors=allowed_anchors,
        blocked_anchors=forbidden_anchors | (frozenset(anchor_verdicts) - allowed_anchors),
        verdicts={**carrier_verdicts, **anchor_verdicts},
    )


@lru_cache(maxsize=None)
def load_word_carrier_gate() -> CarrierGate:
    """Word tagged SDT 载体 gate（Task 6 真值表）。

    `row_sdt` 在 OO 9.4 上 `failed`，故它落在 `carriers_blocked`：任何声明 row 级
    SDT 的契约都会被拒。行身份改用探针实测通过的
    `row_identity_fallback_measured.candidate`（单元格内 inline field SDT tag）。
    """
    payload = _read_json(WORD_CARRIER_CONTRACT_PATH)
    node = payload.get("downstream_gate") or {}
    carrier_verdicts = _section_verdicts(payload, section="carriers", key="carrier")
    anchor_verdicts = _section_verdicts(payload, section="anchors", key="anchor")
    fallback = payload.get("row_identity_fallback_measured") or {}
    fallback_name = fallback.get("candidate")
    fallback_verdict = fallback.get("probe_verdict")
    allowed_carriers = set(node.get("carriers_allowed_into_word_engine") or ())
    if isinstance(fallback_name, str) and fallback_verdict == "passed":
        # row 级 SDT 被 OO 9.4 剥掉，行身份改由实测通过的单元格内 field SDT tag 承载。
        allowed_carriers.add(fallback_name.strip())
        carrier_verdicts[fallback_name.strip()] = str(fallback_verdict)
    blocked_carriers = frozenset(node.get("carriers_blocked") or ())
    allowed_anchors = frozenset(node.get("anchors_allowed") or ())
    blocked_anchors = frozenset(node.get("anchors_blocked") or ())
    if not allowed_carriers or not allowed_anchors:
        raise ContractCarrierGateError(
            f"{WORD_CARRIER_CONTRACT_PATH.name} 的 `downstream_gate` 缺 "
            "carriers_allowed_into_word_engine/anchors_allowed —— gate 为空等于放行一切"
        )
    return CarrierGate(
        document_type="docx",
        source_path=WORD_CARRIER_CONTRACT_PATH,
        source_digest=canonical_digest(payload),
        allowed_carriers=frozenset(allowed_carriers),
        blocked_carriers=blocked_carriers | (frozenset(carrier_verdicts) - allowed_carriers),
        allowed_anchors=allowed_anchors,
        blocked_anchors=blocked_anchors | (frozenset(anchor_verdicts) - allowed_anchors),
        verdicts={**carrier_verdicts, **anchor_verdicts},
    )


def carrier_gate_for(document_type: str) -> CarrierGate:
    if document_type == "xlsx":
        return load_excel_carrier_gate()
    if document_type == "docx":
        return load_word_carrier_gate()
    raise ContractSchemaError(
        f"document_type 未登记: {document_type!r}（封闭域 {sorted(DOCUMENT_TYPES)}）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 形态判据（逐条可单独变异）
# ═══════════════════════════════════════════════════════════════════════════


def assert_json_pointer(pointer: Any, *, location: str, allow_wildcard: bool = False) -> str:
    """RFC 6901 JSON Pointer 形态（CS-7）。

    额外允许两种契约模板形态，各有独立判据：

    * `{row_uuid}` —— 行域字段的行身份占位（由 :func:`assert_row_scope` 单独校验出现次数）；
    * `*` —— **仅** `row_identity.json_pointer` 可用的行集合通配（`allow_wildcard`）。
    """
    if not isinstance(pointer, str) or not pointer:
        raise ContractSchemaError(f"{location}: JSON Pointer 缺失或为空")
    if not pointer.startswith("/"):
        raise ContractSchemaError(
            f"{location}: JSON Pointer 必须以 `/` 开头（RFC 6901），实得 {pointer!r}"
        )
    if pointer.endswith("/"):
        raise ContractSchemaError(f"{location}: JSON Pointer 不得以 `/` 结尾: {pointer!r}")
    if _BAD_TILDE_RE.search(pointer):
        raise ContractSchemaError(
            f"{location}: JSON Pointer 的 `~` 只能以 `~0`/`~1` 出现（RFC 6901 转义）: {pointer!r}"
        )
    tokens = pointer.split("/")[1:]
    if any(token == "" for token in tokens):
        raise ContractSchemaError(f"{location}: JSON Pointer 含空 token: {pointer!r}")
    wildcards = [token for token in tokens if token == "*"]
    if wildcards and not allow_wildcard:
        raise ContractSchemaError(
            f"{location}: 只有 `row_identity.json_pointer` 可使用 `*` 行集合通配，"
            f"字段 pointer 必须用 {ROW_UUID_PLACEHOLDER} 绑定具体行: {pointer!r}"
        )
    if allow_wildcard and len(wildcards) != 1:
        raise ContractSchemaError(
            f"{location}: `row_identity.json_pointer` 必须含恰好一个 `*` 段，"
            f"实得 {len(wildcards)} 个: {pointer!r}"
        )
    return pointer


def assert_row_scope(pointer: str, *, row_scoped: bool, location: str) -> None:
    """行域字段必须绑定行身份占位；非行域字段不得含占位（CS-8 / CS-9）。"""
    occurrences = pointer.count(ROW_UUID_PLACEHOLDER)
    if row_scoped and occurrences != 1:
        raise ContractSchemaError(
            f"{location}: 行域字段的 JSON Pointer 必须含恰好一个 {ROW_UUID_PLACEHOLDER} "
            f"段（禁用数组下标作持久化身份），实得 {occurrences} 个: {pointer!r}"
        )
    if not row_scoped and occurrences != 0:
        raise ContractSchemaError(
            f"{location}: 非行域字段的 JSON Pointer 不得含 {ROW_UUID_PLACEHOLDER}: {pointer!r}"
        )


def assert_stable_key(value: Any, *, location: str) -> str:
    """stable field key 形态 + generated 占位拒绝（CS-3 / CS-5 / CS-15）。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractSchemaError(f"{location}: stable_field_key 缺失或为空")
    key = value.strip()
    if not key.isascii():
        raise ContractSchemaError(
            f"{location}: stable_field_key 含非 ASCII 字符 —— identity 不得依赖中文 label"
            f"（Requirement 6.14）: {key!r}"
        )
    if not _STABLE_KEY_RE.match(key):
        raise ContractSchemaError(
            f"{location}: stable_field_key 形态非法（只允许小写字母/数字/`_`/`-`/`.`/`/` 与 "
            f"`{{}}` 占位）: {key!r}"
        )
    for segment in key.split("/"):
        if _GENERATED_COLUMN_PLACEHOLDER.match(segment):
            raise ContractSchemaError(
                f"{location}: stable_field_key 段 {segment!r} 是 generated YAML 的无语义列占位 "
                f"`col_[a-z]+`，永不可作生产写格身份（Requirement 6.1 / Property 20）"
            )
    return key


def assert_column_key(value: Any, *, location: str) -> str:
    """列 key 形态 + generated 占位拒绝（CS-3）。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractSchemaError(f"{location}: column_key 缺失或为空")
    key = value.strip()
    if _GENERATED_COLUMN_PLACEHOLDER.match(key):
        raise ContractSchemaError(
            f"{location}: column_key {key!r} 是 generated YAML 的无语义列占位 `col_[a-z]+`，"
            "必须替换为人工审核的语义列名（Requirement 6.1 / Property 20）"
        )
    if not key.isascii() or not _STABLE_KEY_RE.match(key):
        raise ContractSchemaError(f"{location}: column_key 形态非法: {key!r}")
    return key


def assert_source_ref(value: Any, *, location: str) -> str:
    """`source_ref` 必填且非空（CS-4）——「禁止无来源自造字段」。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractSchemaError(
            f"{location}: 缺 `source_ref` —— 每个受管字段必须指向权威源 xlsx/docx 的具体位置，"
            "禁止无来源自造字段（design §Contract schema）"
        )
    return value.strip()


def parse_a1_range(value: Any, *, location: str) -> tuple[str, int, str, int]:
    """把 `I8:I200` / `I8` 解析成 `(col_from, row_from, col_to, row_to)`。"""
    if not isinstance(value, str) or not _A1_RANGE_RE.match(value.strip()):
        raise ContractSchemaError(f"{location}: A1 区域形态非法: {value!r}")
    match = _A1_RANGE_RE.match(value.strip())
    assert match is not None  # 上一行已校验
    c1 = match.group("c1")
    r1 = int(match.group("r1"))
    c2 = match.group("c2") or c1
    r2 = int(match.group("r2") or r1)
    return c1, r1, c2, r2


def _column_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def column_in_ranges(column: str, ranges: Sequence[str]) -> bool:
    """列是否落在任一 A1 区域的列跨度内（CS-13 用）。"""
    target = _column_index(column)
    for raw in ranges:
        c1, _r1, c2, _r2 = parse_a1_range(raw, location="formula_mask")
        low, high = sorted((_column_index(c1), _column_index(c2)))
        if low <= target <= high:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 5. 解析结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CellMapping:
    """受管字段在 Excel 中的位置。行由 row identity 决定，不写死行号。"""

    column: str
    row_from: str
    static_row: int | None = None


@dataclass(frozen=True)
class FieldSpec:
    """一个受管字段的完整语义（Property 21 的判据对象）。"""

    stable_field_key: str
    json_pointer: str
    mode: FieldMode
    value_type: ValueType
    source_ref: str
    row_scoped: bool
    column_key: str | None = None
    cell: CellMapping | None = None
    sdt_tag: str | None = None
    instances: str = "one"

    @property
    def is_protected(self) -> bool:
        return self.mode in PROTECTED_MODES


@dataclass(frozen=True)
class RowIdentitySpec:
    kind: RowIdentityKind
    json_pointer: str | None = None
    template_row_key: str | None = None


@dataclass(frozen=True)
class DynamicColumnSpec:
    identity: str
    source_ref: str


@dataclass(frozen=True)
class FooterAnchorSpec:
    marker: str
    search_column: str


@dataclass(frozen=True)
class TableSpec:
    table_key: str
    anchor: str
    header_rows: int
    fields: tuple[FieldSpec, ...]
    row_identity: RowIdentitySpec | None = None
    dynamic_columns: DynamicColumnSpec | None = None
    footer_anchor: FooterAnchorSpec | None = None
    formula_mask: tuple[str, ...] = ()
    delete_policy: DeletePolicy | None = None

    @property
    def has_dynamic_rows(self) -> bool:
        return self.row_identity is not None

    @property
    def two_level_header(self) -> bool:
        return self.header_rows >= 2


@dataclass(frozen=True)
class SheetSpec:
    sheet_key: str
    excel_name: str
    locator_anchor: str
    tables: tuple[TableSpec, ...]


@dataclass(frozen=True)
class TemplateRef:
    relative_path: str
    sha256: str
    structure_hash: str


@dataclass(frozen=True)
class SyncContract:
    """一份已强校验的 per-entry 语义契约。

    `canonical_payload` 保留原始 payload（未加工），`canonical_sha256` 是它经
    `definitions.canonical_json_bytes` 的 SHA-256 —— 与 `DefinitionPublisher`
    发布时算出的 `definition_sha256` 必须逐字节一致。
    """

    contract_id: str
    semantic_version: str
    document_type: str
    review_status: ContractReviewStatus
    template: TemplateRef
    template_definition_sha256: str
    instrumentation_definition_sha256: str
    identity_carriers: tuple[str, ...]
    sheets: tuple[SheetSpec, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    repeaters: tuple[FieldSpec, ...] = ()
    canonical_payload: Mapping[str, Any] = dataclass_field(default_factory=dict)
    carrier_gate_digest: str = ""

    # ─────────────────────────────────────────────────────────────────
    @property
    def canonical_sha256(self) -> str:
        return canonical_digest(self.canonical_payload)

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_payload)

    def all_fields(self) -> tuple[FieldSpec, ...]:
        nested = tuple(
            field
            for sheet in self.sheets
            for table in sheet.tables
            for field in table.fields
        )
        return nested + self.fields + self.repeaters

    def field_by_stable_key(self, stable_key: str) -> FieldSpec:
        for field in self.all_fields():
            if field.stable_field_key == stable_key:
                return field
        raise ContractSchemaError(
            f"contract {self.contract_id}: 未登记 stable_field_key {stable_key!r}"
        )

    def editable_field_keys(self) -> tuple[str, ...]:
        return tuple(
            field.stable_field_key
            for field in self.all_fields()
            if field.mode is FieldMode.editable
        )

    def protected_field_keys(self) -> tuple[str, ...]:
        return tuple(
            field.stable_field_key for field in self.all_fields() if field.is_protected
        )

    # ─────────────────────────────────────────────────────────────────
    def assert_matches_bundle_slots(
        self, slots: Mapping[BundleSlot, BundleSlotSpec]
    ) -> None:
        """契约声明的 template/instrumentation digests 必须与 frozen bundle child 一致。

        Property 28 的 contract 侧：只改 registry alias 不得改变历史 retry，因此
        「契约 payload 里写的 digest」与「bundle typed slot 的 digest」必须双向锁死；
        任一漂移都在写入前 fail closed。
        """
        template = slots.get(BundleSlot.template)
        instrumentation = slots.get(BundleSlot.instrumentation)
        if template is None or instrumentation is None:
            raise ContractDriftError(
                f"contract {self.contract_id}: bundle 缺 template/instrumentation typed slot，"
                "无法与契约声明的 digests 比对"
            )
        if not template.is_definition or template.slot_digest != self.template_definition_sha256:
            raise ContractDriftError(
                f"contract {self.contract_id}: 契约声明 template_definition_sha256="
                f"{self.template_definition_sha256!r}，bundle template slot="
                f"({template.slot_type!r}, {template.slot_digest!r}) —— definition 漂移，"
                "必须按 `template → instrumentation → contract → bundle → representation` "
                "重新发布"
            )
        if (
            not instrumentation.is_definition
            or instrumentation.slot_digest != self.instrumentation_definition_sha256
        ):
            raise ContractDriftError(
                f"contract {self.contract_id}: 契约声明 instrumentation_definition_sha256="
                f"{self.instrumentation_definition_sha256!r}，bundle instrumentation slot="
                f"({instrumentation.slot_type!r}, {instrumentation.slot_digest!r}) —— "
                "definition 漂移"
            )

    def resolve_extract_carrier(
        self,
        *,
        instrumented_identity_present: bool,
        native_anchors_present: bool,
    ) -> ExtractCarrierTier:
        """extract 载体优先级（Requirement 6.20 / CS-20）。

        instrumented stable identity 优先；其次是契约中**已验证**的原生结构锚点；
        两者均不存在时 fail closed —— 不得降级到中文标题或位置猜测。
        """
        if instrumented_identity_present:
            return ExtractCarrierTier.instrumented_identity
        if native_anchors_present:
            return ExtractCarrierTier.native_structural_anchor
        raise ContractCarrierUnavailableError(
            f"contract {self.contract_id}: instrumented stable identity 与已验证原生结构锚点"
            "均不存在 ⇒ extract fail closed；禁止降级到中文标题或单元格位置猜测"
            "（Requirement 6.20）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 强校验器
# ═══════════════════════════════════════════════════════════════════════════


def _enum(value: Any, enum_cls: type[Enum], *, location: str, label: str) -> Any:
    try:
        return enum_cls(value)
    except (ValueError, TypeError) as exc:
        raise ContractSchemaError(
            f"{location}: {label} 未登记: {value!r}"
            f"（封闭枚举 {sorted(item.value for item in enum_cls)}）"
        ) from exc


def _parse_field(
    raw: Any,
    *,
    document_type: str,
    contract_id: str,
    row_scoped: bool,
    gate: CarrierGate,
    location: str,
) -> FieldSpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: field 必须是对象，实得 {type(raw).__name__}")
    stable_key = assert_stable_key(raw.get("stable_field_key"), location=location)
    where = f"{location}[{stable_key}]"
    mode: FieldMode = _enum(raw.get("mode"), FieldMode, location=where, label="mode")
    value_type: ValueType = _enum(
        raw.get("value_type"), ValueType, location=where, label="value_type"
    )
    pointer = assert_json_pointer(raw.get("json_pointer"), location=where)
    assert_row_scope(pointer, row_scoped=row_scoped, location=where)
    source_ref = assert_source_ref(raw.get("source_ref"), location=where)

    column_key: str | None = None
    cell: CellMapping | None = None
    sdt_tag: str | None = None

    if document_type == "xlsx":
        if raw.get("sdt_tag") is not None:
            raise ContractSchemaError(
                f"{where}: xlsx 契约不得声明 `sdt_tag`（文档类型串用，CS-19）"
            )
        if "column_key" in raw:
            column_key = assert_column_key(raw.get("column_key"), location=where)
        if mode is FieldMode.word_only:
            raise ContractSchemaError(
                f"{where}: mode=word_only 只适用于 docx 契约（CS-19）"
            )
        cell_raw = raw.get("cell")
        if not isinstance(cell_raw, Mapping):
            raise ContractSchemaError(
                f"{where}: xlsx 受管字段必须声明 `cell`（OO 位置），实得 {cell_raw!r}"
                "（Property 21）"
            )
        column = cell_raw.get("column")
        if not isinstance(column, str) or not _A1_COLUMN_RE.match(column):
            raise ContractSchemaError(f"{where}: cell.column 形态非法: {column!r}")
        row_from = cell_raw.get("row_from")
        if row_from == "row_identity":
            if not row_scoped:
                raise ContractSchemaError(
                    f"{where}: cell.row_from=row_identity 只能用于行域字段"
                )
            cell = CellMapping(column=column, row_from="row_identity")
        elif isinstance(row_from, int) and row_from >= 1:
            if row_scoped:
                raise ContractSchemaError(
                    f"{where}: 行域字段的 cell.row_from 不得写死行号 {row_from}，"
                    "必须为 `row_identity`（Requirement 6.5）"
                )
            cell = CellMapping(column=column, row_from="static", static_row=row_from)
        else:
            raise ContractSchemaError(
                f"{where}: cell.row_from 必须是 `row_identity` 或 >=1 的静态行号，"
                f"实得 {row_from!r}"
            )
    else:
        if raw.get("cell") is not None:
            raise ContractSchemaError(
                f"{where}: docx 契约不得声明 Excel `cell`（文档类型串用，CS-19）"
            )
        sdt_tag = raw.get("sdt_tag")
        if not isinstance(sdt_tag, str) or not sdt_tag.strip():
            raise ContractSchemaError(
                f"{where}: docx 受管字段必须声明 `sdt_tag`（tagged SDT 是唯一载体，"
                "Requirement 7.2）"
            )
        sdt_tag = sdt_tag.strip()
        if not sdt_tag.isascii():
            raise ContractSchemaError(
                f"{where}: sdt_tag 含非 ASCII 字符 —— identity 不得依赖中文 label: {sdt_tag!r}"
            )
        match = _SDT_TAG_RE.match(sdt_tag)
        if match is None:
            raise ContractSchemaError(
                f"{where}: sdt_tag 形态非法，必须为 `gt:field|block:{{contract_id}}:{{stable_key}}`"
                f"，实得 {sdt_tag!r}"
            )
        if match.group("contract") != contract_id:
            raise ContractSchemaError(
                f"{where}: sdt_tag 的 contract 段 {match.group('contract')!r} 与 "
                f"contract_id {contract_id!r} 不符"
            )
        if row_scoped and ROW_UUID_PLACEHOLDER not in sdt_tag:
            raise ContractSchemaError(
                f"{where}: 行域 docx 字段的 sdt_tag 必须携带 {ROW_UUID_PLACEHOLDER} —— "
                "row 级 SDT 在 OO 9.4 上不保留，行身份只能由单元格内 field SDT tag 承载"
                f"（{gate.source_path.name}）"
            )

    instances = raw.get("instances", "one")
    if instances not in {"one", "many"}:
        raise ContractSchemaError(
            f"{where}: instances 只能是 'one' 或 'many'，实得 {instances!r}"
        )
    return FieldSpec(
        stable_field_key=stable_key,
        json_pointer=pointer,
        mode=mode,
        value_type=value_type,
        source_ref=source_ref,
        row_scoped=row_scoped,
        column_key=column_key,
        cell=cell,
        sdt_tag=sdt_tag,
        instances=str(instances),
    )


def _parse_row_identity(raw: Any, *, location: str) -> RowIdentitySpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: row_identity 必须是对象")
    kind_raw = raw.get("kind")
    if isinstance(kind_raw, str) and kind_raw in FORBIDDEN_ROW_IDENTITY_KINDS:
        raise ContractSchemaError(
            f"{location}: row_identity.kind={kind_raw!r} 用位置/下标作持久化身份 —— "
            "删除、重排、再新增之后旧身份会被复用并把数据串到新行"
            f"（Requirement 6.5 / Property 23）；合法取值 "
            f"{sorted(item.value for item in RowIdentityKind)}"
        )
    kind: RowIdentityKind = _enum(
        kind_raw, RowIdentityKind, location=location, label="row_identity.kind"
    )
    if kind is RowIdentityKind.field:
        pointer = assert_json_pointer(
            raw.get("json_pointer"), location=f"{location}.row_identity", allow_wildcard=True
        )
        return RowIdentitySpec(kind=kind, json_pointer=pointer)
    template_row_key = raw.get("template_row_key")
    if not isinstance(template_row_key, str) or not template_row_key.strip():
        raise ContractSchemaError(
            f"{location}: row_identity.kind=template_row_key 必须声明非空 `template_row_key`"
        )
    return RowIdentitySpec(kind=kind, template_row_key=template_row_key.strip())


def _parse_dynamic_columns(raw: Any, *, location: str) -> DynamicColumnSpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: dynamic_columns 必须是对象")
    identity = raw.get("identity")
    if identity != DYNAMIC_COLUMN_IDENTITY_TEMPLATE:
        raise ContractSchemaError(
            f"{location}: dynamic_columns.identity 必须恰为 "
            f"{DYNAMIC_COLUMN_IDENTITY_TEMPLATE!r}（稳定 key = slot + 序号），"
            f"实得 {identity!r} —— 可改 label 不得作 identity，也不得写死列数"
            "（Requirement 6.4 / Property 22）"
        )
    return DynamicColumnSpec(
        identity=identity,
        source_ref=assert_source_ref(raw.get("source_ref"), location=f"{location}.dynamic_columns"),
    )


def _parse_footer_anchor(raw: Any, *, location: str) -> FooterAnchorSpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: footer_anchor 必须是对象")
    for forbidden in ("row", "row_index", "row_number"):
        if forbidden in raw:
            raise ContractSchemaError(
                f"{location}: footer_anchor 不得用 {forbidden!r} 写死行号 —— footer 会随行"
                "新增下移，只能用 marker + search_column 定位（Requirement 6.9）"
            )
    marker = raw.get("marker")
    if not isinstance(marker, str) or not marker.strip():
        raise ContractSchemaError(f"{location}: footer_anchor.marker 缺失或为空")
    search_column = raw.get("search_column")
    if not isinstance(search_column, str) or not _A1_COLUMN_RE.match(search_column):
        raise ContractSchemaError(
            f"{location}: footer_anchor.search_column 形态非法: {search_column!r}"
        )
    return FooterAnchorSpec(marker=marker.strip(), search_column=search_column)


def _parse_table(
    raw: Any, *, contract_id: str, gate: CarrierGate, location: str
) -> TableSpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: table 必须是对象")
    table_key = assert_stable_key(raw.get("table_key"), location=f"{location}.table_key")
    where = f"{location}[{table_key}]"
    anchor = raw.get("anchor")
    if not isinstance(anchor, str) or not _A1_RANGE_RE.match(anchor.strip()):
        raise ContractSchemaError(f"{where}: table anchor 必须是 A1 单元格，实得 {anchor!r}")
    header_rows = raw.get("header_rows")
    if not isinstance(header_rows, int) or isinstance(header_rows, bool) or not 1 <= header_rows <= 3:
        raise ContractSchemaError(
            f"{where}: header_rows 必须是 1..3 的整数（两级表头 = 2），实得 {header_rows!r}"
            "（Requirement 6.3）"
        )
    formula_mask = raw.get("formula_mask") or []
    if not isinstance(formula_mask, list):
        raise ContractSchemaError(f"{where}: formula_mask 必须是数组")
    for item in formula_mask:
        parse_a1_range(item, location=f"{where}.formula_mask")

    row_identity = (
        _parse_row_identity(raw["row_identity"], location=where)
        if raw.get("row_identity") is not None
        else None
    )
    dynamic_columns = (
        _parse_dynamic_columns(raw["dynamic_columns"], location=where)
        if raw.get("dynamic_columns") is not None
        else None
    )
    footer_anchor = (
        _parse_footer_anchor(raw["footer_anchor"], location=where)
        if raw.get("footer_anchor") is not None
        else None
    )
    delete_policy = (
        _enum(raw["delete_policy"], DeletePolicy, location=where, label="delete_policy")
        if raw.get("delete_policy") is not None
        else None
    )

    raw_fields = raw.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ContractSchemaError(f"{where}: table 必须声明至少一个 field")
    fields = tuple(
        _parse_field(
            item,
            document_type=gate.document_type,
            contract_id=contract_id,
            row_scoped=row_identity is not None,
            gate=gate,
            location=f"{where}.fields",
        )
        for item in raw_fields
    )

    # CS-14：动态行表必须同时给出行身份与删除策略。
    if row_identity is not None and delete_policy is None:
        raise ContractSchemaError(
            f"{where}: 声明了 row_identity 的动态行表必须同时声明 `delete_policy`"
            f"（{sorted(item.value for item in DeletePolicy)}）—— 删除语义不得留给运行时猜测"
            "（Requirement 6.9 / 6.15）"
        )
    if delete_policy is not None and row_identity is None:
        raise ContractSchemaError(
            f"{where}: 声明了 delete_policy 却没有 row_identity —— 无行身份时删除策略无处施加"
        )

    # CS-13：formula 模式字段的列必须落在已声明的 formula_mask 内。
    for spec in fields:
        if spec.mode is not FieldMode.formula or spec.cell is None:
            continue
        if not formula_mask:
            raise ContractSchemaError(
                f"{where}: 字段 {spec.stable_field_key!r} 声明 mode=formula，但 table 未声明 "
                "`formula_mask` —— 受保护单元格必须显式登记只读区域（Requirement 6.6）"
            )
        if not column_in_ranges(spec.cell.column, formula_mask):
            raise ContractSchemaError(
                f"{where}: 字段 {spec.stable_field_key!r} 的列 {spec.cell.column} 不在 "
                f"formula_mask {list(formula_mask)} 覆盖的列跨度内 —— formula 字段必须被"
                "只读区域覆盖，否则 OO 侧修改会覆盖公式结果（Requirement 6.6）"
            )

    seen: set[str] = set()
    for spec in fields:
        if spec.stable_field_key in seen:
            raise ContractSchemaError(
                f"{where}: stable_field_key 重复: {spec.stable_field_key!r}"
            )
        seen.add(spec.stable_field_key)

    return TableSpec(
        table_key=table_key,
        anchor=anchor.strip(),
        header_rows=header_rows,
        fields=fields,
        row_identity=row_identity,
        dynamic_columns=dynamic_columns,
        footer_anchor=footer_anchor,
        formula_mask=tuple(formula_mask),
        delete_policy=delete_policy,
    )


def _parse_sheet(
    raw: Any, *, contract_id: str, gate: CarrierGate, location: str
) -> SheetSpec:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: sheet 必须是对象")
    sheet_key = assert_stable_key(raw.get("sheet_key"), location=f"{location}.sheet_key")
    where = f"{location}[{sheet_key}]"
    excel_name = raw.get("excel_name")
    if not isinstance(excel_name, str) or not excel_name.strip():
        raise ContractSchemaError(f"{where}: excel_name 缺失或为空（仅供人读，不作定位）")
    locator = raw.get("locator")
    if not isinstance(locator, Mapping):
        raise ContractSchemaError(
            f"{where}: sheet 必须声明 `locator`（含已过 probe gate 的 `anchor`）"
        )
    anchor = locator.get("anchor")
    if not isinstance(anchor, str) or not anchor.strip():
        raise ContractSchemaError(f"{where}: locator.anchor 缺失或为空")
    gate.assert_anchor(anchor.strip(), location=where)

    raw_tables = raw.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ContractSchemaError(f"{where}: sheet 必须声明至少一个 table")
    tables = tuple(
        _parse_table(item, contract_id=contract_id, gate=gate, location=f"{where}.tables")
        for item in raw_tables
    )
    return SheetSpec(
        sheet_key=sheet_key,
        excel_name=excel_name.strip(),
        locator_anchor=anchor.strip(),
        tables=tables,
    )


def _parse_template(raw: Any, *, location: str) -> TemplateRef:
    """解析 `template` 引用块。

    🔴 字段名刻意用 `template_sha256` / `normalized_structure_hash`，**不是** design.md
    示例里的 `sha256` / `structure_hash`。原因是 Task 12 的
    `definitions._SELF_REFERENCE_KEYS` 把裸键 `sha256` 列为「自身 artifact hash」并递归
    拒绝（`_walk_keys` 遍历全部嵌套键），而 AC 6.2 禁的是内嵌**自身**的 hash，引用
    template blob 的 hash 恰恰是它要求的。两个替代名都是 requirements 的原文用词：
    AC 6.14 写 `template_sha256`，AC 6.2 写 `normalized_structure_hash`。
    把它们改回裸 `sha256` 会让整份契约在 payload 级校验就被拒。
    """
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(f"{location}: template 必须是对象")
    relative_path = raw.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ContractSchemaError(f"{location}: template.relative_path 缺失或为空")
    if relative_path.startswith(("/", "\\")) or ".." in Path(relative_path).parts:
        raise ContractSchemaError(
            f"{location}: template.relative_path 必须是 `backend/wp_templates/` 下的相对路径，"
            f"不得绝对或含 `..`: {relative_path!r}"
        )
    for name in ("template_sha256", "normalized_structure_hash"):
        if not is_digest(raw.get(name)):
            raise IdentityError(
                f"{location}: template.{name} 必须是非空非全零的 64 位小写 hex，"
                f"实得 {raw.get(name)!r}"
            )
    return TemplateRef(
        relative_path=relative_path.strip(),
        sha256=str(raw["template_sha256"]).strip(),
        structure_hash=str(raw["normalized_structure_hash"]).strip(),
    )


def parse_contract(payload: Mapping[str, Any], *, adapter_id: str | None = None) -> SyncContract:
    """把 canonical contract payload 强校验成 :class:`SyncContract`。

    顺序刻意固定：payload 级（复用 Task 12）→ 身份/审核态 → 文档类型与 gate →
    template → identity carriers → 结构（sheet/table/field）。每一步都在下一步
    之前失败，因此错误码总是指向真正的第一个原因。
    """
    if not isinstance(payload, Mapping):
        raise ContractSchemaError(f"contract payload 必须是对象，实得 {type(payload).__name__}")

    # ── ① payload 级判据（schema_version 前缀、禁自引用、单向引用两个 digest、禁 bundle 前向引用）
    #     🔴 单一真源在 `definitions.validate_contract_payload`，本模块不复制。
    validate_contract_payload(payload)

    # ── ①.5 跨语言 canonical 安全（AC 6.2「同一 semantic payload 在不同环境必须得到相同 SHA」）
    #     contract payload 是唯一会被 Python 与 TypeScript 同时算 digest 的载荷，
    #     因此 XL-1~XL-6（NaN/Inf、负零、超安全整数、孤立代理项、非字符串键、浮点）
    #     必须在 canonicalization 之前拒掉。
    assert_cross_language_safe(payload)

    schema_version = payload.get("schema_version")
    if schema_version != CONTRACT_SCHEMA_VERSION:
        raise ContractSchemaError(
            f"contract schema_version 必须是 {CONTRACT_SCHEMA_VERSION!r}，实得 {schema_version!r}"
        )

    # ── ② 契约身份与审核态
    contract_id = payload.get("contract_id")
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise ContractSchemaError("contract payload 缺 `contract_id`")
    contract_id = contract_id.strip()
    if not contract_id.isascii() or not _STABLE_KEY_RE.match(contract_id):
        raise ContractSchemaError(f"contract_id 形态非法: {contract_id!r}")
    if adapter_id is not None and contract_id != adapter_id:
        raise ContractSchemaError(
            f"contract_id {contract_id!r} 与 adapter_id/文件名 {adapter_id!r} 不符 —— "
            "契约身份与 adapter 身份必须双向锁死（CS-2）"
        )
    semantic_version = payload.get("semantic_version")
    if not isinstance(semantic_version, str) or not semantic_version.strip():
        raise ContractSchemaError("contract payload 缺 `semantic_version`")
    review_status: ContractReviewStatus = _enum(
        payload.get("review_status"),
        ContractReviewStatus,
        location=f"contract[{contract_id}]",
        label="review_status",
    )
    if review_status is not ContractReviewStatus.reviewed:
        raise ContractSchemaError(
            f"contract {contract_id}: review_status={review_status.value} —— generator 只产候选，"
            "未经人工审核的骨架不得注册生产 adapter（design §Contract schema / CS-1）"
        )

    # ── ③ 文档类型与 probe gate
    document_type = payload.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        raise ContractSchemaError(
            f"contract {contract_id}: document_type 未登记: {document_type!r}"
            f"（封闭域 {sorted(DOCUMENT_TYPES)}）"
        )
    gate = carrier_gate_for(str(document_type))

    # ── ④ template
    template = _parse_template(payload.get("template"), location=f"contract[{contract_id}]")

    # ── ⑤ identity carriers（逐条过 probe gate）
    raw_carriers = payload.get("identity_carriers")
    if not isinstance(raw_carriers, list) or not raw_carriers:
        raise ContractSchemaError(
            f"contract {contract_id}: 必须声明非空 `identity_carriers` —— "
            "extract 的首选载体不得留给运行时推断（Requirement 6.20）"
        )
    carriers: list[str] = []
    for item in raw_carriers:
        if not isinstance(item, str) or not item.strip():
            raise ContractSchemaError(f"contract {contract_id}: identity_carriers 含空项")
        name = item.strip()
        gate.assert_carrier(name, location=f"contract[{contract_id}].identity_carriers")
        carriers.append(name)

    # ── ⑥ 结构
    sheets: tuple[SheetSpec, ...] = ()
    fields: tuple[FieldSpec, ...] = ()
    repeaters: tuple[FieldSpec, ...] = ()
    if document_type == "xlsx":
        raw_sheets = payload.get("sheets")
        if not isinstance(raw_sheets, list) or not raw_sheets:
            raise ContractSchemaError(
                f"contract {contract_id}: xlsx 契约必须声明至少一个 sheet"
            )
        if payload.get("fields") is not None or payload.get("repeaters") is not None:
            raise ContractSchemaError(
                f"contract {contract_id}: xlsx 契约的字段只能挂在 `sheets[].tables[].fields`，"
                "不得同时使用 docx 的顶层 `fields`/`repeaters`（CS-19）"
            )
        sheets = tuple(
            _parse_sheet(
                item, contract_id=contract_id, gate=gate, location=f"contract[{contract_id}].sheets"
            )
            for item in raw_sheets
        )
        sheet_keys = [sheet.sheet_key for sheet in sheets]
        if len(set(sheet_keys)) != len(sheet_keys):
            raise ContractSchemaError(f"contract {contract_id}: sheet_key 重复: {sheet_keys}")
    else:
        if payload.get("sheets") is not None:
            raise ContractSchemaError(
                f"contract {contract_id}: docx 契约不得声明 Excel `sheets`（CS-19）"
            )
        raw_fields = payload.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ContractSchemaError(
                f"contract {contract_id}: docx 契约必须声明至少一个顶层 field"
            )
        fields = tuple(
            _parse_field(
                item,
                document_type="docx",
                contract_id=contract_id,
                row_scoped=False,
                gate=gate,
                location=f"contract[{contract_id}].fields",
            )
            for item in raw_fields
        )
        repeaters = tuple(
            _parse_field(
                item,
                document_type="docx",
                contract_id=contract_id,
                row_scoped=True,
                gate=gate,
                location=f"contract[{contract_id}].repeaters",
            )
            for item in payload.get("repeaters") or []
        )

    all_keys = [
        spec.stable_field_key
        for spec in (
            *(f for sheet in sheets for table in sheet.tables for f in table.fields),
            *fields,
            *repeaters,
        )
    ]
    if not all_keys:
        raise ContractSchemaError(f"contract {contract_id}: 没有任何受管字段")
    if len(set(all_keys)) != len(all_keys):
        duplicates = sorted({key for key in all_keys if all_keys.count(key) > 1})
        raise ContractSchemaError(
            f"contract {contract_id}: stable_field_key 跨 sheet/table 重复: {duplicates}"
        )

    return SyncContract(
        contract_id=contract_id,
        semantic_version=semantic_version.strip(),
        document_type=str(document_type),
        review_status=review_status,
        template=template,
        template_definition_sha256=str(payload["template_definition_sha256"]).strip(),
        instrumentation_definition_sha256=str(
            payload["instrumentation_definition_sha256"]
        ).strip(),
        identity_carriers=tuple(carriers),
        sheets=sheets,
        fields=fields,
        repeaters=repeaters,
        canonical_payload=dict(payload),
        carrier_gate_digest=gate.source_digest,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 契约目录加载
# ═══════════════════════════════════════════════════════════════════════════


def contract_path_for(adapter_id: str) -> Path:
    if not adapter_id or "/" in adapter_id or "\\" in adapter_id or ".." in adapter_id:
        raise ContractSchemaError(f"adapter_id 形态非法（不得含路径分隔或 `..`）: {adapter_id!r}")
    return CONTRACTS_DIR / f"{adapter_id}.json"


def load_contract(adapter_id: str) -> SyncContract:
    """从 `backend/data/workpaper_sync_contracts/{adapter_id}.json` 读并强校验。"""
    path = contract_path_for(adapter_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractSchemaError(
            f"adapter {adapter_id!r} 缺 per-entry contract 文件: "
            f"{path.relative_to(_BACKEND.parent) if path.is_absolute() else path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContractSchemaError(f"contract 文件不是合法 JSON: {path}: {exc}") from exc
    return parse_contract(payload, adapter_id=adapter_id)


def available_contract_ids() -> tuple[str, ...]:
    """契约目录中现存的生产 adapter_id（不解析内容，供 registry 做清册比对）。

    以 `_` 开头的文件是 schema 文档与**候选**示例（`review_status="candidate"`，会被
    :func:`parse_contract` 拒绝），不参与生产清册 —— 否则它们会被 registry 报成
    「有契约文件但没有 adapter」的伪欠账。
    """
    if not CONTRACTS_DIR.is_dir():
        return ()
    return tuple(
        sorted(
            path.stem
            for path in CONTRACTS_DIR.glob("*.json")
            if not path.stem.startswith("_")
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 结构漂移定位（Requirement 6.10）
# ═══════════════════════════════════════════════════════════════════════════


def declared_structure_inventory(contract: SyncContract) -> tuple[tuple[str, str, str, str], ...]:
    """契约声明的受管结构清册：`(sheet_key, table_key, stable_field_key, locator)`。

    `locator` 对 xlsx 是 `列+行来源`，对 docx 是 sdt tag —— 两者都不含展示名/中文
    label，因此可直接与实测清册逐项比对。顺序确定（按三元组字典序），保证「首个
    漂移位置」是可复现的同一条。
    """
    rows: list[tuple[str, str, str, str]] = []
    for sheet in contract.sheets:
        for table in sheet.tables:
            for spec in table.fields:
                cell = spec.cell
                locator = (
                    f"{cell.column}:{cell.row_from}"
                    + (f":{cell.static_row}" if cell.static_row is not None else "")
                    if cell is not None
                    else ""
                )
                rows.append((sheet.sheet_key, table.table_key, spec.stable_field_key, locator))
    for spec in (*contract.fields, *contract.repeaters):
        rows.append(("", "", spec.stable_field_key, spec.sdt_tag or ""))
    return tuple(sorted(rows))


def first_structure_drift(
    contract: SyncContract, observed: Sequence[tuple[str, str, str, str]]
) -> tuple[str, str, str, str] | None:
    """返回首个漂移项；完全一致返回 `None`。"""
    declared = declared_structure_inventory(contract)
    observed_sorted = tuple(sorted(tuple(item) for item in observed))
    for expected, actual in zip(declared, observed_sorted):
        if expected != actual:
            return expected
    if len(declared) != len(observed_sorted):
        longer = declared if len(declared) > len(observed_sorted) else observed_sorted
        return longer[min(len(declared), len(observed_sorted))]
    return None


def assert_no_structure_drift(
    contract: SyncContract, observed: Sequence[tuple[str, str, str, str]]
) -> None:
    """契约声明与实测结构不一致时 fail closed 并指出首个漂移位置（Property 28）。"""
    drift = first_structure_drift(contract, observed)
    if drift is None:
        return
    sheet_key, table_key, stable_key, locator = drift
    raise ContractDriftError(
        f"contract {contract.contract_id}: 结构漂移，首个不一致位置 "
        f"sheet={sheet_key!r} table={table_key!r} field={stable_key!r} locator={locator!r} —— "
        "不得继续按旧坐标写格；必须按 `template → instrumentation → contract → bundle → "
        "representation` 显式发布新 definitions（Requirement 6.10）"
    )


__all__ = [
    # 路径与常量
    "CONTRACTS_DIR", "EXCEL_CARRIER_CONTRACT_PATH", "WORD_CARRIER_CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION", "DOCUMENT_TYPES", "DYNAMIC_COLUMN_IDENTITY_TEMPLATE",
    "ROW_UUID_PLACEHOLDER", "PROTECTED_MODES", "FORBIDDEN_ROW_IDENTITY_KINDS",
    # 枚举
    "ContractReviewStatus", "FieldMode", "ValueType", "RowIdentityKind",
    "DeletePolicy", "ExtractCarrierTier",
    # 异常
    "ContractError", "ContractSchemaError", "ContractCarrierGateError",
    "ContractCarrierUnavailableError", "ContractDriftError",
    # probe gate
    "CarrierGate", "load_excel_carrier_gate", "load_word_carrier_gate", "carrier_gate_for",
    # 形态判据
    "assert_json_pointer", "assert_row_scope", "assert_stable_key", "assert_column_key",
    "assert_source_ref", "parse_a1_range", "column_in_ranges",
    # 解析结果
    "CellMapping", "FieldSpec", "RowIdentitySpec", "DynamicColumnSpec",
    "FooterAnchorSpec", "TableSpec", "SheetSpec", "TemplateRef", "SyncContract",
    # 入口
    "parse_contract", "load_contract", "contract_path_for", "available_contract_ids",
    # 漂移
    "declared_structure_inventory", "first_structure_drift", "assert_no_structure_drift",
]
