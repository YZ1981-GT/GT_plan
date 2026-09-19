"""K 循环附注结构**三向比对**收口守卫（Requirement 13.7 / Task 16）。

三向 = openpyxl 直读源 xlsx（**唯一裁决者**）
     ↔ `note_template_{listed,soe}.json` 的 headers / columns / rows
     ↔ 前端载荷声明（`k{n}NoteSectionMap.ts` 的披露 sheet 名常量）

判据分两类，失败消息必须写明是哪一类：

- **类 A（判据源自检，必须全绿）**：三向的路径都在、都解析得出东西、K 的 26 个章节
  都定位得到、前端常量抽取器真抓到值。**类 A 一红，类 B 的红就不可解读**
  —— 抓不到东西的比对器永远「零不匹配」，那是最典型的空转形态（本轮写探针时
  真踩过一次：正则只截到行尾 ⇒ 多行常量抓不到 ⇒ 报「不匹配 0 处」）。
- **类 B（三向一致）**：sheet 名逐字、列结构自洽、段首码齐备、可扩位分布。

真源引用（都不重新数一遍）：
- 源侧披露 sheet 名与动态标记 → `tests/test_k_source_template_facts.py` 的
  `DISCLOSURE_SHEETS` / `DISCLOSURE_MARKERS` / `TOTAL_DISCLOSURE_MARKERS` / `TWO_LEVEL_CYCLES`
- 章节号与 owner → `backend/data/note_workpaper_sync_registry.json`
- 段首码计划 → `backend/scripts/fix/fix_note_k_report_row_codes.py` 的 `PLAN`

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 13.7 / 8.x / 9.x / 11.1
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_DATA = _ROOT / "backend/data"
_TPL_DIR = _ROOT / "backend/wp_templates/K"
_FE = _ROOT / "audit-platform/frontend/src/components/workpaper/composables"
_SYNC_REGISTRY = _DATA / "note_workpaper_sync_registry.json"

_CLASS_A = "[类 A 判据源]"
_CLASS_B = "[类 B 三向]"


def _load_by_path(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    assert spec is not None and spec.loader is not None, f"{_CLASS_A} 无法加载 {rel}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(name, None)
    return mod


_FACTS = _load_by_path("_k_src_facts", "backend/tests/test_k_source_template_facts.py")
_ROWCODE = _load_by_path("_k_rowcode", "backend/scripts/fix/fix_note_k_report_row_codes.py")


# ─────────────────────────────────────────────────────────────────────────────
# 载入三向
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def templates() -> dict[str, dict]:
    return {
        v: json.loads((_DATA / f"note_template_{v}.json").read_text(encoding="utf-8"))
        for v in ("listed", "soe")
    }


@pytest.fixture(scope="module")
def k_sections() -> dict[tuple[str, str], str]:
    """``{(wp_code, variant): section_number}``（真源 = 同步登记表）。"""
    doc = json.loads(_SYNC_REGISTRY.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], str] = {}
    for e in doc.get("entries") or []:
        wp = str(e.get("wp_code") or "").upper()
        if not wp.startswith("K"):
            continue
        for variant in ("listed", "soe"):
            num = str(e.get(variant) or "").strip()
            if num:
                out[(wp, variant)] = num
    return out


@pytest.fixture(scope="module")
def registry_sheets() -> dict[tuple[str, str], str]:
    """登记表声明的披露 sheet 名 ``{(wp, variant): sheet}``。"""
    doc = json.loads(_SYNC_REGISTRY.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], str] = {}
    for e in doc.get("entries") or []:
        wp = str(e.get("wp_code") or "").upper()
        if not wp.startswith("K"):
            continue
        for variant, key in (("listed", "sheet_listed"), ("soe", "sheet_soe")):
            name = str(e.get(key) or "").strip()
            if name:
                out[(wp, variant)] = name
    return out


#: 前端披露 sheet 名常量的抽取正则（声明名）
_FE_DECL_RE = re.compile(r"export\s+const\s+([A-Z0-9_]*DISCLOSURE_SHEET_NAME[A-Z0-9_]*)\b")
_FE_STR_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def _const_body(src: str, start: int) -> str:
    """取 ``export const X = <body>``。

    🔴 有 ``{`` 就**花括号配对**截取 —— 常量是多行 ``Record<Variant, string>``
    对象，只截到行尾会一个值都抓不到（判据源为空 ⇒ 恒「零不匹配」）。
    """
    eq = src.find("=", start)
    if eq < 0:
        return ""
    i = eq + 1
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    if i < len(src) and src[i] == "{":
        depth = 0
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    return src[i : j + 1]
        return src[i:]
    nl = src.find("\n", i)
    return src[i : nl if nl > 0 else len(src)]


@pytest.fixture(scope="module")
def fe_sheet_names() -> dict[str, list[str]]:
    """前端各循环声明的披露 sheet 名 ``{wp: [name, ...]}``（按出现序）。"""
    out: dict[str, list[str]] = {}
    for wp in _FACTS.DISCLOSURE_SHEETS:
        path = _FE / f"{wp.lower()}NoteSectionMap.ts"
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        vals: list[str] = []
        for m in _FE_DECL_RE.finditer(src):
            body = _const_body(src, m.start())
            vals += [
                a or b
                for a, b in _FE_STR_RE.findall(body)
                if (a or b).startswith("附注披露信息")
            ]
        out[wp] = vals
    return out


def _section(templates: dict, variant: str, number: str) -> dict | None:
    for sec in templates[variant].get("sections") or []:
        if isinstance(sec, dict) and str(sec.get("section_number") or "").strip() == number:
            return sec
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 类 A：判据源自检
# ─────────────────────────────────────────────────────────────────────────────


def test_class_a_all_three_legs_are_readable(templates, k_sections, registry_sheets):
    assert _TPL_DIR.is_dir(), f"{_CLASS_A} 源模板目录缺失：{_TPL_DIR}"
    assert len(list(_TPL_DIR.glob("*.xlsx"))) >= 13, f"{_CLASS_A} 源 xlsx 数量异常"
    for v in ("listed", "soe"):
        assert templates[v].get("sections"), f"{_CLASS_A} {v} 模板无 sections"
    assert len(k_sections) >= 26, f"{_CLASS_A} 只解析到 {len(k_sections)} 个 K 章节"
    assert len(registry_sheets) >= 26, f"{_CLASS_A} 登记表 sheet 名只有 {len(registry_sheets)} 条"


def test_class_a_every_k_section_resolves(templates, k_sections):
    missing = [
        f"{v} §{num}（{wp}）"
        for (wp, v), num in sorted(k_sections.items())
        if _section(templates, v, num) is None
    ]
    assert not missing, f"{_CLASS_A} 章节在模板里定位不到：{missing}"


def test_class_a_frontend_constant_extractor_really_extracts(fe_sheet_names):
    """🔴 抽取器必须真抓到 26 个值。

    本轮写探针时初版正则只截到行尾 ⇒ 一个值都没抓到 ⇒ 报「不匹配 0 处」。
    抓不到东西的比对器永远全绿，这条就是防它。
    """
    total = sum(len(v) for v in fe_sheet_names.values())
    assert len(fe_sheet_names) >= 13, f"{_CLASS_A} 只读到 {len(fe_sheet_names)} 个前端 map"
    assert total >= 26, f"{_CLASS_A} 只抓到 {total} 个 sheet 名常量值（应 ≥26）"
    empty = sorted(wp for wp, v in fe_sheet_names.items() if not v)
    assert not empty, f"{_CLASS_A} 这些循环的前端常量抓不到值（抽取器与写法脱钩）：{empty}"


def test_class_a_source_facts_are_importable():
    assert len(_FACTS.DISCLOSURE_SHEETS) >= 13
    assert _FACTS.TOTAL_DISCLOSURE_MARKERS >= 20
    assert _FACTS.TWO_LEVEL_CYCLES, f"{_CLASS_A} 两级表头循环清单为空"
    assert len(_ROWCODE.PLAN) >= 4, f"{_CLASS_A} 段首码计划为空"


# ─────────────────────────────────────────────────────────────────────────────
# 类 B①：sheet 名三向逐字
# ─────────────────────────────────────────────────────────────────────────────


def test_class_b_frontend_sheet_names_match_source(fe_sheet_names):
    """前端常量 ↔ 源 xlsx tab 名逐字（6 种括号写法，禁归一）。"""
    bad: list[str] = []
    for wp, vals in sorted(fe_sheet_names.items()):
        real = set(_FACTS.DISCLOSURE_SHEETS[wp].values())
        for v in vals:
            if v not in real:
                bad.append(f"{wp}: 前端 {v!r} 不在源 xlsx {sorted(real)}")
    assert not bad, f"{_CLASS_B} 前端披露 sheet 名与源模板脱钩（推送永不命中）：{bad}"


def test_class_b_frontend_declares_both_variants(fe_sheet_names):
    """每个循环两版都要声明 —— 少一版等于那一版整章不同步。"""
    short = {
        wp: vals
        for wp, vals in fe_sheet_names.items()
        if len(set(vals)) < len(set(_FACTS.DISCLOSURE_SHEETS[wp].values()))
    }
    assert not short, f"{_CLASS_B} 前端声明的变体数少于源 xlsx：{short}"


def test_class_b_registry_sheet_names_match_source(registry_sheets):
    """`note_workpaper_sync_registry.json` ↔ 源 xlsx tab 名逐字。"""
    bad = [
        f"{wp}/{v}: 登记 {name!r} != 源 {_FACTS.DISCLOSURE_SHEETS.get(wp, {}).get(v)!r}"
        for (wp, v), name in sorted(registry_sheets.items())
        if _FACTS.DISCLOSURE_SHEETS.get(wp, {}).get(v) != name
    ]
    assert not bad, f"{_CLASS_B} 同步登记表的 sheet 名与源模板脱钩：{bad}"


# ─────────────────────────────────────────────────────────────────────────────
# 类 B②：模板列结构自洽
# ─────────────────────────────────────────────────────────────────────────────


def _tables(templates, variant, number) -> list[dict]:
    sec = _section(templates, variant, number)
    return [t for t in ((sec or {}).get("tables") or []) if isinstance(t, dict)]


def test_class_b_every_table_has_columns(templates, k_sections):
    bad: list[str] = []
    total = 0
    for (wp, v), num in sorted(k_sections.items()):
        for t in _tables(templates, v, num):
            total += 1
            if not (t.get("columns") or []):
                bad.append(f"{wp}/{v} §{num} / {t.get('name')!r}")
    assert total >= 50, f"{_CLASS_A} 只遍历到 {total} 张表，判据源可疑"
    assert not bad, f"{_CLASS_B} 表缺 columns（前端渲染不出列头）：{bad}"


def test_class_b_headers_align_with_columns(templates, k_sections):
    """`headers` 与 `columns` 的 label 同长同序 —— 两者是同一事实的两种表达。"""
    bad: list[str] = []
    compared = 0
    for (wp, v), num in sorted(k_sections.items()):
        for t in _tables(templates, v, num):
            cols = [str(c.get("label") or "") for c in (t.get("columns") or [])]
            hdrs = [str(h) for h in (t.get("headers") or [])]
            if not hdrs:
                continue  # headers 可缺省（由 columns 派生），但存在时必须一致
            compared += 1
            if hdrs != cols:
                bad.append(f"{wp}/{v} §{num} / {t.get('name')!r}: {hdrs} != {cols}")
    # 🔴 下限自检：`headers` 若全缺省，上面的循环一次都不比 ⇒ 恒绿空转
    assert compared >= 40, f"{_CLASS_A} 只比对了 {compared} 张表的 headers，判据源可疑"
    assert not bad, f"{_CLASS_B} headers 与 columns 不一致：{bad[:6]}"


def test_class_b_exactly_one_label_column(templates, k_sections):
    bad: list[str] = []
    for (wp, v), num in sorted(k_sections.items()):
        for t in _tables(templates, v, num):
            cols = t.get("columns") or []
            if not cols:
                continue
            n = sum(1 for c in cols if c.get("is_label"))
            if n != 1:
                bad.append(f"{wp}/{v} §{num} / {t.get('name')!r}: is_label={n}")
    assert not bad, f"{_CLASS_B} 标签列数不为 1（渲染时行标题错位）：{bad[:8]}"


def test_class_b_two_level_cycles_declare_groups(templates, k_sections):
    """两级表头循环（源 xlsx 实证）至少要有一张表带 `_column_groups`。"""
    for wp in _FACTS.TWO_LEVEL_CYCLES:
        hits = 0
        for v in ("listed", "soe"):
            num = k_sections.get((wp, v))
            if not num:
                continue
            hits += sum(1 for t in _tables(templates, v, num) if t.get("_column_groups"))
        assert hits > 0, (
            f"{_CLASS_B} {wp} 源 xlsx 有两级表头，但模板一张 `_column_groups` 都没有"
            " ⇒ 父表头整行丢失"
        )


def test_class_b_single_level_cycles_have_no_phantom_groups(templates, k_sections):
    """反向自检：单级表头循环不得凭空出现 `_column_groups`（那会渲染出假父表头）。"""
    bad: list[str] = []
    for (wp, v), num in sorted(k_sections.items()):
        if wp in _FACTS.TWO_LEVEL_CYCLES:
            continue
        for t in _tables(templates, v, num):
            if t.get("_column_groups"):
                bad.append(f"{wp}/{v} §{num} / {t.get('name')!r}")
    assert not bad, f"{_CLASS_B} 单级表头循环出现 `_column_groups`：{bad}"


# ─────────────────────────────────────────────────────────────────────────────
# 类 B③：段首码齐备（Requirement 11.1，与 Task 14 同真源）
# ─────────────────────────────────────────────────────────────────────────────


def test_class_b_shared_tables_carry_row_codes(templates):
    bad: list[str] = []
    for entry in _ROWCODE.PLAN:
        tables = _tables(templates, entry["variant"], entry["section"])
        tbl = next((t for t in tables if str(t.get("name") or "") == entry["table"]), None)
        if tbl is None:
            bad.append(f"{entry['variant']} §{entry['section']} 找不到表 {entry['table']!r}")
            continue
        rows = {
            str(r.get("label") or ""): str(r.get("report_row_code") or "")
            for r in (tbl.get("rows") or [])
            if isinstance(r, dict)
        }
        for stamp in entry["stamps"]:
            if rows.get(stamp["label"]) != stamp["row_code"]:
                bad.append(
                    f"{entry['variant']} §{entry['section']} / {stamp['label']}: "
                    f"{rows.get(stamp['label'])!r} != {stamp['row_code']!r}"
                )
    assert not bad, f"{_CLASS_B} 共享表段首码缺失/不符（owner 推送会整表 fail-closed）：{bad}"


# ─────────────────────────────────────────────────────────────────────────────
# 类 B④：可扩位分布（Task 18 的作业面 —— 差额显式登记，两侧都实测）
# ─────────────────────────────────────────────────────────────────────────────

#: 模板侧 K 章节 `row_type='expandable'` 的**当前**行数。
#:
#: 🔴 这是**显式登记的已知差额**，不是「正确值」：源 xlsx 的披露 sheet 内有
#: `TOTAL_DISCLOSURE_MARKERS` 处动态插行标记（Task 3 逐处冻结），而模板侧一处都没标。
#: Task 18 逐处判定「作行 / 作列头」后本数字会变，届时**本条打红**，
#: 必须连同 Task 18 的判定结论一起更新 —— 这样差额不会被静默遗忘，
#: 也不会因为「锁住当前值」而假装已经收口。
#: 2026-08-12：0 → 11 → 17 → **26**（Task 18 收口）。
#:
#: 模板侧 26 行对源侧 29 处标记，差额 3 处**逐处登记**在
#: `fix_note_k_expandable_rows.py` 里，且被它的 `--check` 闭环钉死：
#:   * `COLLAPSED_SOURCE_MARKERS` 2 处 —— 源 xlsx 的「持有待售的处置组」按处置组
#:     逐个重复整块（① 子公司A、② 分公司B），每块资产段末与负债段末各一处标记；
#:     附注模板按平台铁律把示例名收成**一个通用块** ⇒ 4 处源标记落到同 2 处模板行。
#:   * `NO_TEMPLATE_TARGET` 1 处 —— soe 源 xlsx 有「持有待售负债附注」表而附注模板
#:     没有这张表；缺的是整张表（Requirement 8 的表集合作业面），不是标记问题。
TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18 = 26


def _template_expandable_count(templates, k_sections) -> int:
    return sum(
        1
        for (wp, v), num in k_sections.items()
        for t in _tables(templates, v, num)
        for r in (t.get("rows") or [])
        if isinstance(r, dict) and str(r.get("row_type") or "") == "expandable"
    )


def test_class_b_expandable_gap_is_registered(templates, k_sections):
    """源侧标记数 vs 模板侧 expandable 行数 —— 差额必须与登记一致。

    两个数字都**实测**：源侧来自 Task 3 逐处冻结的 `DISCLOSURE_MARKERS`，
    模板侧现扫。任一侧变动都会打红，逼迫更新登记而不是让缺口沉默。
    """
    source_markers = _FACTS.TOTAL_DISCLOSURE_MARKERS
    template_rows = _template_expandable_count(templates, k_sections)
    # 🔴 只比模板侧那一个数（源侧由下一条独立自检）。写成
    #    `assert (src, tpl) == (src, PENDING)` 会让第一项自己跟自己比 = 空断言。
    assert template_rows == TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18, (
        f"{_CLASS_B} 可扩位缺口变了：源侧 {source_markers} 处动态标记 / "
        f"模板侧 {template_rows} 行 expandable（登记值 "
        f"{TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18}）。\n"
        "若这是 Task 18 的成果，请把 TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18 "
        "改成新值并在 tasks.md 写明逐处判定结论（作行 / 作列头）。"
    )


#: 「两写者」——可扩位行由本脚本插入，而占位行删除逻辑在结构脚本里。
#: 两者必须**同时**归零，否则一个插、一个删，永远互相回退。
_BOTH_WRITERS = (
    "backend/scripts/fix/fix_note_k_expandable_rows.py",
    "backend/scripts/fix/fix_note_k_pl_structure.py",
)


@pytest.mark.parametrize("script", _BOTH_WRITERS)
def test_class_b_both_writers_check_zero(script: str) -> None:
    """两写者 `--check` 同时归零（Requirement 9.7）。

    🔴 只比模板数据是查不出这类缺陷的：把结构脚本改回「一刀切删占位行」时，
    **数据没变**（下次 `--apply` 才会删），任何只读模板的断言都全绿。必须真跑
    `--check` 才能抓出「一个插一个删」的对立。可扩位处数的闭环自检
    （本脚本 11 + 结构脚本 18 == 源侧 29）也只在脚本里，同理必须真跑。
    """
    import subprocess

    path = _ROOT / script
    assert path.exists(), f"{_CLASS_A} 写者脚本缺失：{script}"
    r = subprocess.run(
        [sys.executable, str(path), "--check"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, (
        f"{_CLASS_B} {script} --check 未归零（exit={r.returncode}）——"
        "可扩位行与占位行删除逻辑互相回退，或处数不闭环：\n"
        f"{(r.stdout or '')[-1500:]}"
    )


def test_structure_script_keeps_expandable_rows() -> None:
    """结构脚本删占位行时必须**放过**已标 expandable 的可扩位行。

    🔴 为什么要直接调函数而不是看模板数据：删除只发生在 `--apply` 路径上，
    把判据写回「一刀切删」时**当下数据一个字节都不变**（`--check` 的 validator
    走的是另一条分支），任何只读模板的断言都全绿 —— 直到某天有人跑一次 apply，
    11 处加行落点无声消失。故判据必须落在函数行为上。
    """
    pl = _load_by_path("_k_pl_struct", "backend/scripts/fix/fix_note_k_pl_structure.py")
    marker = {"label": "……", "row_type": "expandable"}
    junk = {"label": "……", "row_type": "data"}
    kept = pl._strip_placeholder_rows([marker, junk, {"label": "合计", "row_type": "total"}])
    labels = [(r.get("label"), r.get("row_type")) for r in kept]
    assert ("……", "expandable") in labels, (
        f"可扩位行被结构脚本删掉了（加行落点消失且不报错）：{labels}"
    )
    assert ("……", "data") not in labels, (
        f"占位说明行没被删（会渲染成一行空披露数据）：{labels}"
    )


def test_class_b_source_side_markers_really_exist():
    """反向自检：源侧标记确实存在且逐处有坐标 —— 否则上一条的「缺口」是假的。"""
    total = sum(
        len(v) for variants in _FACTS.DISCLOSURE_MARKERS.values() for v in variants.values()
    )
    assert total == _FACTS.TOTAL_DISCLOSURE_MARKERS, (
        f"{_CLASS_A} 逐处清单 {total} 与总数 {_FACTS.TOTAL_DISCLOSURE_MARKERS} 不符"
    )
    assert total > 0, f"{_CLASS_A} 源侧一个标记都没有 ⇒ 缺口判据空转"
    for wp, variants in _FACTS.DISCLOSURE_MARKERS.items():
        for variant, items in variants.items():
            for entry in items:
                assert len(entry) >= 2 and re.fullmatch(r"[A-Z]+\d+", entry[0]), (
                    f"{_CLASS_A} {wp}/{variant} 标记坐标形态异常：{entry}"
                )


def test_class_b_no_expandable_outside_registered_gap(templates, k_sections):
    """模板侧若已有 expandable 行，必须落在源侧登记过的循环上（防凭空标）。"""
    registered = {wp for wp in _FACTS.DISCLOSURE_MARKERS}
    stray: list[str] = []
    for (wp, v), num in sorted(k_sections.items()):
        for t in _tables(templates, v, num):
            for r in t.get("rows") or []:
                if not isinstance(r, dict):
                    continue
                if str(r.get("row_type") or "") == "expandable" and wp not in registered:
                    stray.append(f"{wp}/{v} §{num} / {t.get('name')!r} / {r.get('label')!r}")
    assert not stray, (
        f"{_CLASS_B} 这些循环源 xlsx 没有动态标记，模板里却标了 expandable：{stray}"
    )
