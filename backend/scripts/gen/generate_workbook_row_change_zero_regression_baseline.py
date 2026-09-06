# -*- coding: utf-8 -*-
"""冻结 `_rewrite_formula_refs` 的零回归基线。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 6
Requirements: 7.4, 7.7
Properties: **P28**

═══ 为什么这个脚本必须**现在**跑，而不是等门开 ═══

Requirement 7.4 要求「`propagate_sheets` 未声明传播时，行为与**本 spec 前**逐字相同」。
「本 spec 前」是一个**会随时间消失的参照物** —— 上游 spec
（`excel-structural-row-insertion-and-shift-aware-verification`）正在改
`excel_row_shift.py`，一旦落地，当初的行为就再也无法取证，7.4 退化为无法证伪的声明。

所以基线冻结（本脚本）排在 Task 101 的就绪门**之前**（AC 7.7）：它**只读**，不碰任何共改
文件，因此不构成并行编辑风险。

═══ 基线为什么是两层 ═══

🔴 **只存聚合计数不够** —— 两处相反的行为变化会互相抵消（一处多改一个引用、另一处少改一个，
`changed_total` 不变）。因此：

1. **逐模板 digest**：把 `(sheet, 序号, 输入, 输出, 改动数)` 按**文档顺序**滚进 sha256。
   顺序敏感 ⇒ 任何一处输入/输出/顺序的变化都会让 digest 变。
2. **分类样本的完整输入/输出对**：digest 变了只知道「变了」，样本让人立刻知道**哪一类
   误命中回归了**。八类各自取真实样本（3D 全库为 0，用显式登记的合成用例）。

═══ 三个情景 ═══

`propagate_sheets` 会加在 `_rewrite_formula_refs` 上，风险是扰动它的**任一**分支。所以基线
覆盖三组参数组合，而不是只测一种：

| 情景 | remap | current_sheet | freeze_absolute_rows | translate_qualified_rows | 对应真实场景 |
|---|---|---|---|---|---|
| `insert_ctx` | row >= 7 时 +1 | 本 sheet 名 | False | False | 受管 sheet 插行 |
| `insert_no_ctx` | 同上 | None（保守默认） | False | False | 无 sheet 上下文时的插行 |
| `filldown` | 无条件 +1 | 本 sheet 名 | True | **True** | 新行 fill-down |

🔴 **情景的参数必须与真实调用路径逐字一致，否则它冻结的是一条不存在的行为。**
2026-09-05（Task 27）实测踩到这一条：`filldown` 情景原先不传 `translate_qualified_rows`，
而真实入口 `translate_formula_rows` 传了。后果是 Task 27 改完 fill-down 语义后基线
**没有变红** —— 而本文件的 docstring 与守卫都写明「Task 27 落地时 `filldown` 必然变红」。
一条声称在看某个函数、实际参数与它不同的判据 = 判据盲区（守卫在看一条没人走的路）。

⇒ 新增情景或改动被观测函数的签名时，**必须回来核对本表与真实调用点的参数逐字相同**。
核对方法是 `inspect.getsource(真实入口)` 里出现的关键字参数集合 ⊆ 本情景的 kwargs。

用法::

    python backend/scripts/gen/generate_workbook_row_change_zero_regression_baseline.py --check
    python backend/scripts/gen/generate_workbook_row_change_zero_regression_baseline.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    _F_RE,
    _QUALIFIED_PREFIX_RE,
    _REF_TOKEN_RE,
    _STRING_LITERAL_RE,
    _left_boundary_ok,
    _rewrite_formula_refs,
)

TEMPLATE_ROOT: Path = _BACKEND / "wp_templates"
BASELINE_PATH: Path = (
    _BACKEND
    / "tests"
    / "workpaper_sync"
    / "data"
    / "workbook_row_change_zero_regression_baseline.json"
)

#: 冻结的插入点。选 7 是因为 K11 受管区自行 7 起 ⇒ 真实模板里 `>= at` 与 `< at` 两侧都有样本。
CANONICAL_INSERT_AT: int = 7
CANONICAL_COUNT: int = 1

#: 每类样本最多留几条（够诊断即可，不追求穷举）。
SAMPLES_PER_CLASS: int = 6

_A1_LIKE_RE = re.compile(r"(?<![A-Za-z0-9])\$?[A-Z]{1,3}\$?\d+(?![A-Za-z0-9])")
_NUMERIC_FUNC_RE = re.compile(r"\b(?:LOG10|ATAN2|T\.?DIST|CHISQ\.\w+|NORM\.\w+)\s*\(")

#: 3D 引用全库实测 **0** 处 ⇒ 该类只能用**显式登记的合成用例**，否则判据在空集上恒真。
SYNTHETIC_THREE_D: tuple[str, ...] = (
    "=SUM(Sheet1:Sheet3!A20)",
    "='明细表K11-2:明细表K11-3'!F29+G25",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 三个情景
# ═══════════════════════════════════════════════════════════════════════════


def _scenario_kwargs(name: str, sheet_name: str) -> dict[str, Any]:
    if name == "insert_ctx":
        return {
            "remap": _insert_remap,
            "current_sheet": sheet_name,
            "freeze_absolute_rows": False,
        }
    if name == "insert_no_ctx":
        return {
            "remap": _insert_remap,
            "current_sheet": None,
            "freeze_absolute_rows": False,
        }
    if name == "filldown":
        # 🔴 这三个参数必须与 `translate_formula_rows` 实际传的**逐字一致**，
        #    否则本情景冻结的不是任何真实调用路径 —— 详见 SCENARIOS 的说明。
        return {
            "remap": _filldown_remap,
            "current_sheet": sheet_name,
            "freeze_absolute_rows": True,
            "translate_qualified_rows": True,
        }
    raise ValueError(f"未登记的情景: {name!r}")


SCENARIOS: tuple[str, ...] = ("insert_ctx", "insert_no_ctx", "filldown")


def _insert_remap(row: int) -> int:
    return row + CANONICAL_COUNT if row >= CANONICAL_INSERT_AT else row


def _filldown_remap(row: int) -> int:
    return row + CANONICAL_COUNT


# ═══════════════════════════════════════════════════════════════════════════
# 2. 分类（用于样本挑选，与生产分词器同口径）
# ═══════════════════════════════════════════════════════════════════════════


def _qualified_hits(text: str) -> list[tuple[str, str, str]]:
    """`[(kind, sheet_name, token)]`，分支顺序与 `_rewrite_formula_refs` 逐一对应。"""
    out: list[tuple[str, str, str]] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == '"':
            literal = _STRING_LITERAL_RE.match(text, index)
            index = literal.end() if literal else index + 1
            continue
        if _left_boundary_ok(text, index):
            prefix = _QUALIFIED_PREFIX_RE.match(text, index)
            if prefix is not None:
                index = prefix.end()
                target = _REF_TOKEN_RE.match(text, index)
                token = ""
                if target is not None:
                    token = target.group(0)
                    index = target.end()
                if prefix.group("book"):
                    kind = "external"
                elif prefix.group("span"):
                    kind = "three_d"
                else:
                    kind = "sheet"
                raw = prefix.group("first")
                if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
                    raw = raw[1:-1].replace("''", "'")
                out.append((kind, raw, token))
                continue
        index += 1
    return out


def _has_bare_ref(text: str) -> bool:
    """去掉所有限定引用与字符串字面量后是否仍剩 A1 形态（= 存在裸引用）。"""
    stripped = _STRING_LITERAL_RE.sub('""', text)
    stripped = _QUALIFIED_PREFIX_RE.sub("@", stripped)
    # 限定引用的目标 token 紧跟在 `@` 后，一并去掉
    stripped = re.sub(r"@(?:\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)?", "@", stripped)
    return _A1_LIKE_RE.search(stripped) is not None


def classify(text: str, sheet_name: str) -> set[str]:
    """一条公式文本命中的类集合（可多命中）。"""
    classes: set[str] = set()
    hits = _qualified_hits(text)
    kinds = {k for k, _s, _t in hits}
    sheets = {s for k, s, _t in hits if k == "sheet"}

    if "three_d" in kinds:
        classes.add("three_d")
    if "external" in kinds:
        classes.add("external_workbook")
    if sheets - {sheet_name}:
        classes.add("cross_sheet_verbatim")
        if any(_A1_LIKE_RE.search(s) for s in sheets - {sheet_name}):
            classes.add("sheet_name_looks_like_a1")
    if sheet_name in sheets:
        classes.add("self_qualified")
    if _NUMERIC_FUNC_RE.search(text):
        classes.add("numeric_function_name")
    if '"' in text and _A1_LIKE_RE.search(text):
        classes.add("string_literal")
    if (sheets - {sheet_name}) and _has_bare_ref(text):
        classes.add("mixed")
    return classes


ALL_CLASSES: tuple[str, ...] = (
    "cross_sheet_verbatim",
    "sheet_name_looks_like_a1",
    "self_qualified",
    "three_d",
    "external_workbook",
    "numeric_function_name",
    "string_literal",
    "mixed",
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 计算基线
# ═══════════════════════════════════════════════════════════════════════════


def _iter_formulas(path: Path) -> Iterable[tuple[str, int, str]]:
    """按 workbook 顺序、文档顺序产出 `(sheet_name, 序号, 公式文本)`。"""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        sheets, _defined = _parse_workbook_xml(zf)
        for sheet in sheets:
            part = _normalise_part(sheet["rel_target"])
            if part not in names:
                continue
            xml = zf.read(part).decode("utf-8", "replace")
            for seq, match in enumerate(_F_RE.finditer(xml)):
                text = match.group("text")
                if not text:
                    continue
                yield sheet["name"], seq, text


def compute_template(
    path: Path, samples: dict[str, list[dict[str, Any]]] | None = None
) -> dict[str, Any]:
    """单份模板的基线记录。

    拆出来是为了让守卫能只重算一份模板做反向自检（全库重算约 9 秒，重算一份是毫秒级），
    同时保证守卫用的**就是**生成器的算法，不另抄一份。
    """
    rel = str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/")
    hashers = {name: hashlib.sha256() for name in SCENARIOS}
    changed = {name: 0 for name in SCENARIOS}
    formulas = cross_formulas = cross_sites = three_d = external = 0

    for sheet_name, seq, text in _iter_formulas(path):
        formulas += 1
        hits = _qualified_hits(text)
        other = [(k, s, t) for k, s, t in hits if k == "sheet" and s != sheet_name]
        if other:
            cross_formulas += 1
            cross_sites += len(other)
        three_d += sum(1 for k, _s, _t in hits if k == "three_d")
        external += sum(1 for k, _s, _t in hits if k == "external")

        outputs: dict[str, str] = {}
        for name in SCENARIOS:
            new, n = _rewrite_formula_refs(text, **_scenario_kwargs(name, sheet_name))
            outputs[name] = new
            changed[name] += n
            hashers[name].update(
                f"{sheet_name}\x1f{seq}\x1f{text}\x1f{new}\x1f{n}\x1e".encode("utf-8")
            )

        if samples is not None:
            for cls in classify(text, sheet_name):
                bucket = samples[cls]
                if len(bucket) < SAMPLES_PER_CLASS:
                    bucket.append(
                        {
                            "class": cls,
                            "template": rel,
                            "sheet": sheet_name,
                            "formula_index": seq,
                            "input": text,
                            "outputs": outputs,
                            "synthetic": False,
                        }
                    )

    return {
        "formulas": formulas,
        "cross_sheet_formulas": cross_formulas,
        "cross_sheet_sites": cross_sites,
        "three_d_sites": three_d,
        "external_sites": external,
        "changed": changed,
        "digest": {name: hashers[name].hexdigest() for name in SCENARIOS},
    }


def compute_baseline() -> dict[str, Any]:
    """现算基线。纯读：不写任何文件、不碰共改文件。"""
    started = time.perf_counter()
    xlsx = sorted(
        p for p in TEMPLATE_ROOT.rglob("*.xlsx") if not p.name.startswith("~$")
    )

    per_template: dict[str, dict[str, Any]] = {}
    samples: dict[str, list[dict[str, Any]]] = {c: [] for c in ALL_CLASSES}
    totals = {
        "formula_texts": 0,
        "cross_sheet_formulas": 0,
        "cross_sheet_sites": 0,
        "templates_with_cross_sheet": 0,
        "three_d_sites": 0,
        "external_sites": 0,
    }

    for path in xlsx:
        rel = str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/")
        record = compute_template(path, samples)
        per_template[rel] = record
        totals["formula_texts"] += record["formulas"]
        totals["cross_sheet_formulas"] += record["cross_sheet_formulas"]
        totals["cross_sheet_sites"] += record["cross_sheet_sites"]
        totals["three_d_sites"] += record["three_d_sites"]
        totals["external_sites"] += record["external_sites"]
        if record["cross_sheet_sites"]:
            totals["templates_with_cross_sheet"] += 1

    # 3D 全库为 0 ⇒ 用显式登记的合成用例补齐该类，否则判据在空集上恒真
    for text in SYNTHETIC_THREE_D:
        outputs = {
            name: _rewrite_formula_refs(text, **_scenario_kwargs(name, "审定表K11-1"))[0]
            for name in SCENARIOS
        }
        samples["three_d"].append(
            {
                "class": "three_d",
                "template": "<synthetic>",
                "sheet": "审定表K11-1",
                "formula_index": -1,
                "input": text,
                "outputs": outputs,
                "synthetic": True,
            }
        )

    return {
        "spec": "excel-workbook-wide-row-change-propagation",
        "task": "Wave 0 Task 6 (Requirements 7.4, 7.7)",
        "frozen_before": (
            "上游 spec excel-structural-row-insertion-and-shift-aware-verification "
            "改动 excel_row_shift.py 之前"
        ),
        "canonical": {"insert_at": CANONICAL_INSERT_AT, "count": CANONICAL_COUNT},
        "scenarios": list(SCENARIOS),
        "denominators": {"xlsx_total": len(xlsx), **totals},
        "elapsed_sec": round(time.perf_counter() - started, 2),
        "per_template": per_template,
        "class_samples": samples,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 比对
# ═══════════════════════════════════════════════════════════════════════════

#: 不参与比对的字段（每次跑都会变，不是行为）。
_VOLATILE_TOP_LEVEL = frozenset({"elapsed_sec"})


def comparable(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in _VOLATILE_TOP_LEVEL}


def diff_baseline(
    current: dict[str, Any], stored: dict[str, Any]
) -> list[str]:
    """返回人可读的差异清单；空表示逐字相同。"""
    problems: list[str] = []
    cur, old = comparable(current), comparable(stored)

    for key in ("canonical", "scenarios", "denominators"):
        if cur.get(key) != old.get(key):
            problems.append(f"{key} 变了：基线 {old.get(key)!r} → 现算 {cur.get(key)!r}")

    cur_t, old_t = cur.get("per_template", {}), old.get("per_template", {})
    only_cur = sorted(set(cur_t) - set(old_t))
    only_old = sorted(set(old_t) - set(cur_t))
    if only_cur:
        problems.append(f"新增模板 {len(only_cur)} 份（前 5）: {only_cur[:5]}")
    if only_old:
        problems.append(f"基线里有而现算没有的模板 {len(only_old)} 份（前 5）: {only_old[:5]}")
    for rel in sorted(set(cur_t) & set(old_t)):
        if cur_t[rel] != old_t[rel]:
            for field in ("digest", "changed", "formulas", "cross_sheet_sites"):
                if cur_t[rel].get(field) != old_t[rel].get(field):
                    problems.append(
                        f"{rel} 的 {field} 变了：基线 {old_t[rel].get(field)!r}"
                        f" → 现算 {cur_t[rel].get(field)!r}"
                    )

    cur_s, old_s = cur.get("class_samples", {}), old.get("class_samples", {})
    for cls in sorted(set(cur_s) | set(old_s)):
        if cur_s.get(cls) != old_s.get(cls):
            problems.append(f"分类样本 {cls} 变了（逐条对比见基线 JSON）")
    return problems


def load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="现算并与基线比对，不写盘")
    group.add_argument("--apply", action="store_true", help="写基线（首次冻结 / 有意更新）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    current = compute_baseline()
    d = current["denominators"]
    summary = (
        f"xlsx {d['xlsx_total']} 份 / 公式 {d['formula_texts']} 条 / "
        f"含跨 sheet 引用模板 {d['templates_with_cross_sheet']} 份 / "
        f"跨 sheet 引用 {d['cross_sheet_sites']} 处 / "
        f"含跨 sheet 引用的公式 {d['cross_sheet_formulas']} 条 / "
        f"3D {d['three_d_sites']} 处 / 外部工作簿 {d['external_sites']} 处 / "
        f"耗时 {current['elapsed_sec']}s"
    )

    if args.apply:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(comparable(current), ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        print(f"[apply] 基线已写入 {BASELINE_PATH.relative_to(_REPO)}")
        print(f"        {summary}")
        return 0

    if not BASELINE_PATH.is_file():
        print(f"[check] 🔴 基线不存在：{BASELINE_PATH.relative_to(_REPO)} —— 先跑 --apply")
        return 1
    problems = diff_baseline(current, load_baseline())
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems, "summary": summary},
                         ensure_ascii=False, indent=1))
    else:
        print(f"[check] {summary}")
        if problems:
            print(f"[check] 🔴 与基线有 {len(problems)} 处差异：")
            for p in problems[:40]:
                print(f"  - {p}")
            if len(problems) > 40:
                print(f"  …（另有 {len(problems) - 40} 处）")
        else:
            print("[check] ✅ 与冻结基线逐字相同")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
