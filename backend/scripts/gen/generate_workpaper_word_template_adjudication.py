# -*- coding: utf-8 -*-
"""生成 **Word 模板裁决清册** —— 每行的裁决由源侧事实 + 真实 resolver 调用派生。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 58
Requirements: 7.7, 9.1, 9.2, 9.4, 9.5, 9.11, 12.5
Properties: P40 / P41

═══ 一、分母从真源实测，不手抄 ═══

Requirement 7.7 写的是「18 个可正确解析 DOCX、9 个误解析为父级 XLSX 的 B 子码、
缺失的 `S33-REV` 及 A16/A17 专用链」。这些数字**不作为输入**：本生成器从两份真源
重新算，再与 requirements.md 里的数字对账（守卫 `test_ledger_counts_match_requirement_7_7`）。

真源只有两份：

* `backend/app/data/wp_code_overrides.json` —— `wp_code → componentType`（哪些
  wp_code 是 Word 入口）；
* `backend/wp_templates/` 及其 `_index.json` —— 载体真源（运行时权威；
  `基础数据/致同通用审计程序及底稿模板…` 是已落后的参考副本，禁作取值来源）。

═══ 二、裁决不是手写标签，而是「源侧事实 + 真实 resolver 调用」的函数 ═══

每行的 `unified_verdict` 由**真的调用一次**
`word_resolution.resolve_word_template(wp_code)` 得到（resolved_docx /
document_type_mismatch / template_missing），不是查表。

`legacy_verdict` 由**真的调用一次未改动的** `wp_template_finder.find_template_file()`
得到 —— 那正是存量 `find_template_file_any` 在「非 A 子码」上落进的分支
（A-only 正则 `^A\\d+-\\d+` 不匹配 ⇒ 走主码分支 ⇒ 「终极回退：用主表」抢父级 XLSX）。
用真实函数而不是抄一份复现器：抄的那份会随存量演进静默失真。

`adjudication` = 两个 verdict + 载体清册的**纯函数**（:func:`derive_adjudication`），
守卫对它的真值表逐条断言，因此「某行的裁决」不可能靠改一个字符串蒙过去。

═══ 三、为什么载体清册与 resolver 是两条独立推导 ═══

`own_docx_carriers` 等列由「按派生 wp_code 归属 + 精确相等」得到；
`unified_verdict` 由 `pick_most_specific` 的具体度排序 + 类型门得到。两者读同一批
文件，但**语义不同**，因此可以互相校验：清册说「有自有 DOCX」而 resolver 说
`template_missing` 就是接线错误（守卫 `test_carrier_inventory_and_resolver_agree`）。

用法（仓库根）::

    py -3 backend/scripts/gen/generate_workpaper_word_template_adjudication.py --check
    py -3 backend/scripts/gen/generate_workpaper_word_template_adjudication.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Final

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 老 Python / 非 tty
        pass

from app.services.wp_template_finder import find_template_file  # noqa: E402
from app.services.workpaper_sync.canonical_paths import (  # noqa: E402
    TEMPLATE_ROOT,
    DocumentTypeMismatchError,
    TemplateMissingError,
    document_type_of,
    is_sub_code,
    parent_code_of,
)
from app.services.workpaper_sync.word_resolution import (  # noqa: E402
    REFERENCE_WP_CODE,
    WORD_DOCUMENT_TYPE,
    collect_template_carriers,
    derive_wp_code_from_filename,
    own_template_carriers,
    resolve_own_docx_or_none,
    resolve_word_template,
    template_carriers,
)

_OVERRIDES = _BACKEND / "app" / "data" / "wp_code_overrides.json"
_TEMPLATE_INDEX = TEMPLATE_ROOT / "_index.json"
_LEDGER = _BACKEND / "data" / "workpaper_word_template_adjudication.json"
_REQUIREMENTS = (
    _REPO
    / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md"
)

SCHEMA_VERSION: Final[str] = "word-template-adjudication:v1"

#: Word 入口的 componentType（真源里表示「这份底稿走 Word 编辑器」的唯一取值）。
WORD_COMPONENT_TYPE: Final[str] = "word-template"

#: A16/A17 专用链的 wp_code 前缀（Requirement 7.7 点名）。
DEDICATED_CHAIN_PREFIXES: Final[tuple[str, ...]] = ("A16", "A17")

#: **存量缺陷判据**：`find_template_file_any` 原来只把 A 类子码当子码。
#: 保留它只为把「哪些行受该缺陷影响」算出来；生产代码已不再用它做子码判断
#: （见 `wp_template_finder._LEGACY_A_ONLY_SUB_CODE_RE` 的说明）。
LEGACY_A_ONLY_SUB_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^A\d+-\d+")

#: 裁决取值域（封闭）。守卫按它断言无「未裁决」行。
ADJUDICATIONS: Final[tuple[str, ...]] = (
    # 18：已能正确解析自己的 DOCX，无存量缺陷
    "generic_docx_direct",
    # 9：有自有 DOCX，但存量 resolver 抢到父级 XLSX（Requirement 7.7 点名）
    "subcode_docx_recovered",
    # 1：模板库无任何载体（S33-REV）
    "template_missing_adjudicated",
    # A16/A17 专用链：子码有自有 DOCX
    "dedicated_chain_child_docx",
    # A16/A17 专用链：只有工作簿载体（父码程序表 / A17-5-x 核对表）⇒ 非 Word lane
    "dedicated_chain_workbook_only",
)

#: 裁决 → 下游责任任务（tasks.md 原文归属）。
OWNER_TASK: Final[dict[str, str]] = {
    "generic_docx_direct": "62",
    "subcode_docx_recovered": "63",
    "template_missing_adjudicated": "63",
    "dedicated_chain_child_docx": "64",
    "dedicated_chain_workbook_only": "64",
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真源读取
# ═══════════════════════════════════════════════════════════════════════════


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_overrides() -> dict[str, str]:
    if not _OVERRIDES.is_file():
        raise SystemExit(f"缺少 componentType 真源: {_OVERRIDES}")
    payload = json.loads(_OVERRIDES.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise SystemExit(f"componentType 真源形态非法或为空: {_OVERRIDES}")
    return payload


def ledger_wp_codes(overrides: dict[str, str]) -> list[tuple[str, str]]:
    """清册分母：`(wp_code, ledger_class)`。

    两个来源并集，去重保序：

    * `componentType == word-template` → `generic_word_template`
    * wp_code 以 `A16`/`A17` 开头 → `dedicated_chain_a16` / `dedicated_chain_a17`

    分母**不含**手写清单。若某天新增一个 `word-template` wp_code 而没人裁决，它会
    自动进清册并因裁决派生失败被守卫打红 —— 这正是 Requirement 1.8「新增入口未登记
    时 CI 打红」的同一形态。
    """
    out: list[tuple[str, str]] = []
    for code in sorted(overrides):
        if overrides[code] == WORD_COMPONENT_TYPE:
            out.append((code, "generic_word_template"))
    for code in sorted(overrides):
        for prefix in DEDICATED_CHAIN_PREFIXES:
            if code.upper().startswith(prefix) and overrides[code] != WORD_COMPONENT_TYPE:
                out.append((code, f"dedicated_chain_{prefix.lower()}"))
                break
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. 逐行事实
# ═══════════════════════════════════════════════════════════════════════════


def unified_verdict(wp_code: str) -> tuple[str, str | None]:
    """真跑一次统一 Word resolver。返回 `(verdict, relative_path | None)`。

    🔴 判据落在**真实执行**上，不是「某 wp_code 出现在清册里」——后者在裁决逻辑被
    删掉之后仍然绿（memory 记的假绿第②源，清册守卫尤其易犯）。
    """
    try:
        path = resolve_word_template(wp_code)
    except TemplateMissingError:
        return "template_missing", None
    except DocumentTypeMismatchError:
        return "document_type_mismatch", None
    return "resolved_docx", path.relative_to(TEMPLATE_ROOT).as_posix()


def legacy_verdict(wp_code: str) -> tuple[str, str | None]:
    """存量主码分支的实际去向（调用**未改动的** `find_template_file()`）。

    返回：
    * `("parent_workbook", rel)` —— 命中的工作簿**不属于**这个 wp_code（父级抢占）；
    * `("own_workbook", rel)` —— 命中自己的工作簿（合法，桥不接管）；
    * `("none", None)` —— 主码分支不命中（存量会继续试 docx 尾部回退）。
    """
    hit = find_template_file(wp_code)
    if hit is None:
        return "none", None
    rel = Path(hit).relative_to(TEMPLATE_ROOT).as_posix()
    hit_code = derive_wp_code_from_filename(Path(hit).name)
    if hit_code and hit_code.upper() == wp_code.upper():
        return "own_workbook", rel
    return "parent_workbook", rel


def derive_adjudication(
    *,
    ledger_class: str,
    unified: str,
    legacy: str,
    own_docx: int,
    affected_by_legacy_a_only_defect: bool,
) -> str:
    """裁决 = 事实的**纯函数**（守卫对真值表逐条断言）。

    提成纯函数的理由与 `generate_workpaper_resolver_migration_matrix.derive_status`
    同源：内联在循环里时，若当前数据恰好没有某一分支的行，把那段判断短路成
    `if False:` 输出完全不变、digest 不变、守卫全绿 ⇒ 该判据不可达。抽出来之后守卫
    可以直接对输入组合断言，不依赖「清册里恰好存在一个反例行」这个偶然条件。
    """
    if unified == "template_missing":
        return "template_missing_adjudicated"
    if ledger_class.startswith("dedicated_chain"):
        if unified == "resolved_docx" and own_docx > 0:
            return "dedicated_chain_child_docx"
        return "dedicated_chain_workbook_only"
    if unified != "resolved_docx":
        # generic Word 入口却解析不到 DOCX（只有异类型载体）—— 与「完全没有载体」
        # 分开记：前者要换载体，后者要补载体。
        return "template_missing_adjudicated"
    if affected_by_legacy_a_only_defect and legacy == "parent_workbook":
        return "subcode_docx_recovered"
    return "generic_docx_direct"


def build_row(wp_code: str, ledger_class: str, overrides: dict[str, str]) -> dict[str, Any]:
    own_docx = [c.relative_path for c in own_template_carriers(wp_code, document_type=WORD_DOCUMENT_TYPE)]
    own_xlsx = [c.relative_path for c in own_template_carriers(wp_code, document_type="xlsx")]
    ancestors = [
        {"wp_code": c.wp_code, "document_type": c.document_type, "relative_path": c.relative_path}
        for c in collect_template_carriers(wp_code)
        if c.wp_code.upper() != wp_code.upper()
    ]
    uni, uni_path = unified_verdict(wp_code)
    leg, leg_path = legacy_verdict(wp_code)
    affected = not bool(LEGACY_A_ONLY_SUB_CODE_RE.match(wp_code)) and is_sub_code(wp_code)
    bridge = resolve_own_docx_or_none(wp_code)
    adjudication = derive_adjudication(
        ledger_class=ledger_class,
        unified=uni,
        legacy=leg,
        own_docx=len(own_docx),
        affected_by_legacy_a_only_defect=affected,
    )
    return {
        "wp_code": wp_code,
        "component_type": overrides.get(wp_code),
        "ledger_class": ledger_class,
        "is_sub_code": is_sub_code(wp_code),
        "parent_code": parent_code_of(wp_code),
        "affected_by_legacy_a_only_defect": affected,
        "own_docx_carriers": sorted(own_docx),
        "own_xlsx_carriers": sorted(own_xlsx),
        "ancestor_carriers": sorted(ancestors, key=lambda a: a["relative_path"]),
        "carrier_ambiguity": len(own_docx) > 1,
        "unified_verdict": uni,
        "unified_relative_path": uni_path,
        "legacy_verdict": leg,
        "legacy_relative_path": leg_path,
        "legacy_bridge_takes_over": bridge is not None,
        "adjudication": adjudication,
        "owner_task": OWNER_TASK[adjudication],
        # 源侧坐标：裁决的每一项事实都能回到 `backend/wp_templates/` 的具体文件
        "source_refs": sorted(own_docx + own_xlsx + [a["relative_path"] for a in ancestors]),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. requirements.md 对账
# ═══════════════════════════════════════════════════════════════════════════

_AC_7_7_RE: Final[re.Pattern[str]] = re.compile(
    r"7\.7\.\s*(?P<generic>\d+)\s*个可正确解析\s*DOCX、(?P<subcode>\d+)\s*个误解析为父级"
    r"\s*XLSX\s*的\s*B\s*子码"
)


def requirement_7_7_counts() -> dict[str, int]:
    """从 requirements.md 的 AC 7.7 原文抠出声明数字（对账用，不作输入）。"""
    if not _REQUIREMENTS.is_file():
        raise SystemExit(f"缺少 requirements.md: {_REQUIREMENTS}")
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    match = _AC_7_7_RE.search(text)
    if match is None:
        raise SystemExit(
            "requirements.md 的 AC 7.7 原文形态变了，抠不出声明数字 —— "
            "清册与需求的双向锁死失效，必须先修正则或需求文本"
        )
    return {
        "declared_generic_docx": int(match.group("generic")),
        "declared_subcode_wrong_type": int(match.group("subcode")),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 清册构建
# ═══════════════════════════════════════════════════════════════════════════


def build_ledger() -> dict[str, Any]:
    overrides = load_overrides()
    denominator = ledger_wp_codes(overrides)
    rows = [build_row(code, klass, overrides) for code, klass in denominator]

    by_adjudication: dict[str, int] = {}
    for row in rows:
        by_adjudication[row["adjudication"]] = by_adjudication.get(row["adjudication"], 0) + 1

    unattributed = sorted(
        {
            entry["relative_path"].replace("\\", "/")
            for entry in json.loads(_TEMPLATE_INDEX.read_text(encoding="utf-8"))["files"]
            if derive_wp_code_from_filename(Path(entry["filename"]).name) is None
        }
    )

    stats = {
        "row_count": len(rows),
        "carrier_count": len(template_carriers()),
        "by_ledger_class": {},
        "by_adjudication": by_adjudication,
        "by_unified_verdict": {},
        "generic_docx_direct": by_adjudication.get("generic_docx_direct", 0),
        "subcode_docx_recovered": by_adjudication.get("subcode_docx_recovered", 0),
        "template_missing_adjudicated": by_adjudication.get("template_missing_adjudicated", 0),
        "unadjudicated": sum(1 for r in rows if r["adjudication"] not in ADJUDICATIONS),
        "carrier_ambiguity_rows": sorted(r["wp_code"] for r in rows if r["carrier_ambiguity"]),
        "legacy_bridge_takeover_rows": sorted(
            r["wp_code"] for r in rows if r["legacy_bridge_takes_over"]
        ),
        # 派生失败的索引文件（`_ref` 参考示例）——显式登记让分母闭合，不静默丢文件
        "unattributed_index_files": unattributed,
    }
    for row in rows:
        stats["by_ledger_class"][row["ledger_class"]] = (
            stats["by_ledger_class"].get(row["ledger_class"], 0) + 1
        )
        stats["by_unified_verdict"][row["unified_verdict"]] = (
            stats["by_unified_verdict"].get(row["unified_verdict"], 0) + 1
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": "Wave 5 Task 58",
        "requirements": ["7.7", "9.1", "9.2", "9.4", "9.5", "9.11", "12.5"],
        "properties": [40, 41],
        "sources": {
            "component_overrides": {
                "path": _OVERRIDES.relative_to(_REPO).as_posix(),
                "sha256": _sha256(_OVERRIDES),
            },
            "template_index": {
                "path": _TEMPLATE_INDEX.relative_to(_REPO).as_posix(),
                "sha256": _sha256(_TEMPLATE_INDEX),
            },
        },
        "word_component_type": WORD_COMPONENT_TYPE,
        "dedicated_chain_prefixes": list(DEDICATED_CHAIN_PREFIXES),
        "adjudications": list(ADJUDICATIONS),
        "owner_task": dict(OWNER_TASK),
        "requirement_7_7": requirement_7_7_counts(),
        "stats": stats,
        "rows": rows,
    }
    payload["ledger_digest"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in payload.items() if k != "ledger_digest"},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="写入清册 JSON")
    ap.add_argument("--check", action="store_true", help="只校验磁盘与真源一致")
    args = ap.parse_args()

    payload = build_ledger()
    stats = payload["stats"]
    declared = payload["requirement_7_7"]

    if args.apply:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        _LEDGER.write_text(_dump(payload), encoding="utf-8")
        print(f"[apply] {_LEDGER.relative_to(_REPO).as_posix()}")
        print(json.dumps(stats, ensure_ascii=False, indent=1))
        return 0

    if not _LEDGER.is_file():
        print(f"[check] 清册不存在: {_LEDGER}")
        return 1
    on_disk = json.loads(_LEDGER.read_text(encoding="utf-8"))
    if on_disk.get("ledger_digest") != payload["ledger_digest"]:
        print("[check] 清册与真源不一致，请重跑 --apply")
        print(f"  on_disk={on_disk.get('ledger_digest')}")
        print(f"  from_source={payload['ledger_digest']}")
        return 1
    if stats["unadjudicated"]:
        print(f"[check] 有 {stats['unadjudicated']} 行未裁决")
        return 2
    if stats["generic_docx_direct"] != declared["declared_generic_docx"]:
        print(
            f"[check] 实测 generic_docx_direct={stats['generic_docx_direct']} 与 AC 7.7 "
            f"声明的 {declared['declared_generic_docx']} 不符 —— 载体或需求二者之一要改"
        )
        return 3
    if stats["subcode_docx_recovered"] != declared["declared_subcode_wrong_type"]:
        print(
            f"[check] 实测 subcode_docx_recovered={stats['subcode_docx_recovered']} 与 AC 7.7 "
            f"声明的 {declared['declared_subcode_wrong_type']} 不符"
        )
        return 3
    print(f"[check] OK: {json.dumps(stats, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
