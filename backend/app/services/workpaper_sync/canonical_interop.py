"""canonical bytes 的跨语言互操作约束与 golden 用例（Task 13）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
Requirements 6.2（「同一 semantic payload 在不同环境必须得到相同 SHA」）
Property 21 / 28

## 为什么需要这一层

`definitions.canonical_json_bytes` 用
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"), allow_nan=False)`。
TypeScript 侧的 `JSON.stringify` 在**大多数**输入上得到同样的字节，但有五处会分叉：

======  ==========================  ====================  ====================
编号    输入                        Python                JavaScript
======  ==========================  ====================  ====================
XL-1    `float("nan")` / `inf`      `allow_nan=False` 抛   `JSON.stringify` 出 `null`
XL-2    `-0.0`                      `-0.0`                `0`
XL-3    `2**53` 以上的整数           精确十进制             双精度丢精度
XL-4    孤立代理项（lone surrogate） UTF-8 编码报错          well-formed 转 `\\udXXX`
XL-5    非字符串 dict 键             强转成 `"1"`           对象键本来就是字符串
XL-6    任意非整数浮点               `repr` 规则不同         见下
======  ==========================  ====================  ====================

XL-6 是最隐蔽的一类，实测两处反例：

* `1e-7` → Python `1e-07`（指数补两位），JS `1e-7`；
* `1e16` → Python `1e+16`（1e16 起转指数），JS `10000000000000000`（1e21 起才转）。

想在 Python 侧判断「这个浮点的 JS repr 是否相同」需要一个 JS 引擎，不可行。因此
canonical payload **一律不允许 `float`**：小数/金额用字符串承载。这与平台的金额纪律
一致（金额走 Decimal/字符串，从不用 float），也让 XL-2 成为该规则的子情形。
contract payload 本身没有浮点需求 —— `header_rows` 是整数，digest/版本号都是字符串。

因此「同一 semantic payload → 同一 SHA」不是自动成立的，必须把这五类输入在**进入
canonicalizer 之前**就拒掉。:func:`assert_cross_language_safe` 做这件事，并被
`contracts.parse_contract` 在 payload 级校验之后立即调用 —— contract payload 是
唯一会被两侧同时计算 digest 的载荷。

第六处分叉在**键序**上：Python 的 `sort_keys=True` 按 **Unicode code point** 排序，
而 JS 的 `Array.prototype.sort()` 默认按 **UTF-16 code unit** 排序。对于星平面字符
（如 U+1D400 𝐀）两者结果相反。TS 侧因此必须自己实现 code-point 排序，不能用默认
`sort()` —— golden 用例 `astral_key_order` 就是这条的反例锚点。

## golden 用例

真源 = `backend/data/workpaper_sync_canonical_golden.json`，由
`backend/scripts/gen/generate_workpaper_sync_canonical_golden.py --apply` 生成。
期望字节以 **hex** 存放（`canonical_utf8_hex`），避免「把期望字节再经一次 JSON 转义」
带来的二次歧义。Python 与 TypeScript 两侧读同一份文件、各自算、各自比。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.definitions import canonical_json_bytes
from app.services.workpaper_sync.models import SyncDomainError

_BACKEND: Final[Path] = Path(__file__).resolve().parents[3]

#: golden 用例真源。
CANONICAL_GOLDEN_PATH: Final[Path] = _BACKEND / "data" / "workpaper_sync_canonical_golden.json"

#: JS `Number.MAX_SAFE_INTEGER`。超过它的整数在 TS 侧丢精度（XL-3）。
MAX_SAFE_INTEGER: Final[int] = 2**53 - 1


class CrossLanguageCanonicalError(SyncDomainError):
    """payload 含在 Python/TypeScript 之间会分叉的值（XL-1 ~ XL-5）。"""

    error_code = "canonical_cross_language_unsafe"


def _describe(path: Sequence[str | int]) -> str:
    return "$" + "".join(f"[{part!r}]" for part in path)


def _assert_string_safe(value: str, path: Sequence[str | int]) -> None:
    """XL-4：孤立代理项。

    `str.encode("utf-8")` 对孤立代理项会抛 `UnicodeEncodeError`，因此这里直接试编码
    —— 判据落在**真实编码行为**上，而不是自己写一遍代理项区间判断（后者与
    `canonical_json_bytes` 的 `.encode("utf-8")` 重合，改坏任一侧都不改变行为）。
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CrossLanguageCanonicalError(
            f"{_describe(path)}: 字符串含孤立代理项（lone surrogate），Python 侧无法 UTF-8 "
            f"编码而 TS 侧会转义成 \\udXXX ⇒ 两侧 digest 必然不同（XL-4）: {exc}"
        ) from exc


def _assert_number_safe(value: int | float, path: Sequence[str | int]) -> None:
    """XL-1 / XL-2 / XL-3 / XL-6。

    三条 float 子判据的顺序是刻意的，且各有**可区分的文案**：NaN/Infinity（最常见的
    误输入）→ 负零（语义上等价于 0，值得单独提示）→ 通用「禁 float」。合成一条之后
    删掉前两条不会改变行为 ⇒ 变异检验判 GREEN。
    """
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CrossLanguageCanonicalError(
                f"{_describe(path)}: NaN/Infinity 不是合法 JSON —— Python 侧 "
                f"`allow_nan=False` 抛错，TS 侧 `JSON.stringify` 输出 `null`（XL-1）"
            )
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise CrossLanguageCanonicalError(
                f"{_describe(path)}: 负零 `-0.0` 在 Python 序列化为 `-0.0`、在 TS 为 `0` "
                "⇒ 两侧 digest 不同（XL-2）。语义上负零与零等价，请写整数 `0`"
            )
        raise CrossLanguageCanonicalError(
            f"{_describe(path)}: canonical payload 不允许 `float`（实得 {value!r}）—— "
            "Python 与 JS 的浮点 repr 在 `1e-7`（`1e-07` vs `1e-7`）与 `1e16`"
            "（`1e+16` vs `10000000000000000`）等处分叉，无法在 Python 侧判定（XL-6）。"
            "小数/金额请以字符串承载，与平台金额用 Decimal/字符串的纪律一致"
        )
    if abs(value) > MAX_SAFE_INTEGER:
        raise CrossLanguageCanonicalError(
            f"{_describe(path)}: 整数 {value} 超出 JS `Number.MAX_SAFE_INTEGER` "
            f"({MAX_SAFE_INTEGER})，TS 侧会丢精度（XL-3）。大整数请以字符串承载"
        )


def assert_cross_language_safe(payload: Any, *, path: Sequence[str | int] = ()) -> None:
    """递归拒绝 XL-1 ~ XL-5；通过后 Python 与 TS 的 canonical bytes 必然一致。"""
    if payload is None or isinstance(payload, bool):
        return
    if isinstance(payload, str):
        _assert_string_safe(payload, path)
        return
    if isinstance(payload, (int, float)):
        _assert_number_safe(payload, path)
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise CrossLanguageCanonicalError(
                    f"{_describe(path)}: 对象键 {key!r} 不是字符串 —— Python 会强转成 "
                    f"{str(key)!r} 而 TS 侧根本无此形态，两侧语义不可对齐（XL-5）"
                )
            _assert_string_safe(key, (*path, key))
            assert_cross_language_safe(value, path=(*path, key))
        return
    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_cross_language_safe(item, path=(*path, index))
        return
    raise CrossLanguageCanonicalError(
        f"{_describe(path)}: 类型 {type(payload).__name__} 不是 JSON 基本类型 —— "
        "canonical payload 只允许 null/bool/str/int/float/list/dict"
    )


# ═══════════════════════════════════════════════════════════════════════════
# golden 用例
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    note: str
    payload: Mapping[str, Any]


#: 必须两侧字节相同的用例。每条都针对一个具体的「可能分叉但实际不分叉」点。
GOLDEN_CASES: Final[tuple[GoldenCase, ...]] = (
    GoldenCase("empty_object", "空对象", {}),
    GoldenCase(
        "key_order_perturbation",
        "键序扰动：输入顺序 z<a<m，canonical 必须按 code point 升序输出",
        {"z": 1, "a": 2, "m": 3},
    ),
    GoldenCase(
        "nested_key_order",
        "嵌套对象的键序同样递归排序",
        {"outer": {"b": {"y": 1, "x": 2}, "a": 3}, "arr": [{"q": 1, "p": 2}]},
    ),
    GoldenCase(
        "array_order_preserved",
        "数组顺序是语义，不排序",
        {"items": [3, 1, 2, "c", "a", "b"]},
    ),
    GoldenCase(
        "chinese_not_escaped",
        "ensure_ascii=False：中文原样输出，两侧一致",
        {"label": "披露表（本年）", "unit": "元"},
    ),
    GoldenCase(
        "astral_pair",
        "合法代理对（emoji / 星平面字符）原样输出",
        {"emoji": "📊", "math": "𝐀"},
    ),
    GoldenCase(
        "astral_key_order",
        "星平面键排序：code point 序（Ｚ U+FF3A < 𝐀 U+1D400）与 UTF-16 code unit 序相反，"
        "TS 侧用默认 sort() 会得到不同字节",
        {"\uff3a": 1, "\U0001d400": 2, "a": 3},
    ),
    GoldenCase(
        "line_separators",
        "U+2028 / U+2029：JSON 字符串里合法，两侧都不转义",
        {"sep": "a\u2028b\u2029c"},
    ),
    GoldenCase(
        "json_escapes",
        "必须转义的控制字符与引号/反斜杠",
        {"s": 'quote:" back:\\ tab:\t nl:\n cr:\r ctrl:\u0001'},
    ),
    GoldenCase(
        "integers_only",
        "只允许整数；小数/金额以字符串承载（XL-6）",
        {
            "zero": 0,
            "neg": -42,
            "max_safe": MAX_SAFE_INTEGER,
            "min_safe": -MAX_SAFE_INTEGER,
            "amount_as_string": "1234567.50",
            "rate_as_string": "0.0425",
        },
    ),
    GoldenCase(
        "booleans_and_null",
        "true/false/null 字面量",
        {"t": True, "f": False, "n": None},
    ),
    GoldenCase(
        "empty_string_key",
        "空字符串键合法且排在最前",
        {"": 1, "a": 2},
    ),
    GoldenCase(
        "definition_bundle_shape",
        "definition bundle canonical payload 的真实形态（含 typed null marker）",
        {
            "schema_version": "definition-bundle:v1",
            "authority_model": {"type": "definition", "sha256": "a" * 64},
            "template": {"type": "definition", "sha256": "b" * 64},
            "instrumentation": {"type": "instrumentation:none:v1", "sha256": "c" * 64},
            "contract": {"type": "contract:none:v1", "sha256": "d" * 64},
        },
    ),
)

#: 必须**两侧都拒绝**的用例。`kind` 由各语言自行构造对应值（有些形态只存在于一侧）。
REJECT_KINDS: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("nan", "XL-1 NaN", ("python", "typescript")),
    ("positive_infinity", "XL-1 +Infinity", ("python", "typescript")),
    ("negative_infinity", "XL-1 -Infinity", ("python", "typescript")),
    ("negative_zero", "XL-2 负零", ("python", "typescript")),
    ("unsafe_integer", "XL-3 超出 MAX_SAFE_INTEGER 的整数", ("python", "typescript")),
    ("lone_surrogate", "XL-4 孤立代理项", ("python", "typescript")),
    ("non_string_key", "XL-5 非字符串对象键（只存在于 Python）", ("python",)),
    ("undefined_value", "undefined（只存在于 TypeScript）", ("typescript",)),
    ("non_json_type", "非 JSON 基本类型（Python: set / TS: Date）", ("python", "typescript")),
    ("plain_float", "XL-6 普通非整数浮点", ("python", "typescript")),
    ("exponential_float", "XL-6 指数浮点 1e-7（Python `1e-07` vs JS `1e-7`）", ("python", "typescript")),
)


def build_golden_document() -> dict[str, Any]:
    """构造 golden 文档（期望字节以 hex 存放）。"""
    cases = []
    for case in GOLDEN_CASES:
        raw = canonical_json_bytes(case.payload)
        cases.append(
            {
                "case_id": case.case_id,
                "note": case.note,
                "payload": case.payload,
                "canonical_utf8_hex": raw.hex(),
                "canonical_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            }
        )
    return {
        "schema_version": 1,
        "generator": "backend/scripts/gen/generate_workpaper_sync_canonical_golden.py",
        "python_canonicalizer": "app.services.workpaper_sync.definitions.canonical_json_bytes",
        "typescript_canonicalizer": (
            "audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts"
        ),
        "max_safe_integer": MAX_SAFE_INTEGER,
        "cases": cases,
        "reject_cases": [
            {"case_id": kind, "note": note, "languages": list(languages)}
            for kind, note, languages in REJECT_KINDS
        ],
    }


def render_golden_document() -> str:
    return json.dumps(build_golden_document(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_golden_document() -> Mapping[str, Any]:
    try:
        payload = json.loads(CANONICAL_GOLDEN_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CrossLanguageCanonicalError(
            f"golden 用例缺失: {CANONICAL_GOLDEN_PATH} —— 跨语言 canonical 一致性无判据"
        ) from exc
    if not isinstance(payload, dict) or not payload.get("cases"):
        raise CrossLanguageCanonicalError(f"golden 用例结构非法: {CANONICAL_GOLDEN_PATH}")
    return payload


def build_reject_payload(kind: str) -> Any:
    """按 `kind` 构造 Python 侧的反例值。TS 侧有自己的同名构造。"""
    if kind == "nan":
        return {"v": float("nan")}
    if kind == "positive_infinity":
        return {"v": float("inf")}
    if kind == "negative_infinity":
        return {"v": float("-inf")}
    if kind == "negative_zero":
        return {"v": -0.0}
    if kind == "unsafe_integer":
        return {"v": MAX_SAFE_INTEGER + 1}
    if kind == "lone_surrogate":
        return {"v": "\ud800"}
    if kind == "non_string_key":
        return {1: "one"}
    if kind == "non_json_type":
        return {"v": {"a"}}
    if kind == "plain_float":
        return {"v": 1.5}
    if kind == "exponential_float":
        return {"v": 1e-7}
    raise CrossLanguageCanonicalError(f"未登记的 reject kind: {kind!r}")


__all__ = [
    "CANONICAL_GOLDEN_PATH", "MAX_SAFE_INTEGER",
    "CrossLanguageCanonicalError", "assert_cross_language_safe",
    "GoldenCase", "GOLDEN_CASES", "REJECT_KINDS",
    "build_golden_document", "render_golden_document", "load_golden_document",
    "build_reject_payload",
]
