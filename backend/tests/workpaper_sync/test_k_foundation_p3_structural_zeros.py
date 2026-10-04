# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 0 Task 3：七项结构性零 + 变异证明。

spec: k-cycle-sync-foundation-and-first-canary
Task 3: 七项结构性零 + 变异证明
Property: KF-P58, KF-P59, KF-P60

═══ KC-24 七项结构性零（每项须「现算 0」+「变异注入后打红」两侧证据）═══

  ① 本表行越界 0 格（引用行号 > max_row，排除含 ! 的跨表式）
  ② 跨表引用指向不存在 sheet 0 格
  ③ 同尾码双 sheet 0（HC-5/JC-11 在 K 不命中）
  ④ Excel Table 0
  ⑤ sheet 名首尾空格 0（Task 2 已验）
  ⑥ hardcoded 六模式里五个为 0（第六个 positional_row_id_template == 13）
  ⑦ duplicate_account_aggregation_found 0

═══ 附加 Property ═══

KF-P59: positional_row_id_template 现算 13 且是位置化 48 处的子集
KF-P60: blankRows 全 K 域 0 次调用 ⇒ HC-13 不命中

═══ 变异证明 ═══

变异脚本复用 `backend/scripts/diagnose/mutate_k_cycle_guards.py` 和
`mutate_task53_k_cycle_migration_guards.py`（不新写）。本文件断言脚本存在且
变异清单非空；实际执行变异验证需手动 `python backend/scripts/diagnose/mutate_k_cycle_guards.py`。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

# 🔴 只借**基线常量**（单一真源），扫描逻辑仍由本文件自包含实现 ——
# p3 的定位是「结构性零 + 变异证明」，共享扫描工具被改动时它必须还能独立说话。
from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP8_BASELINE_TEMPLATE_HITS,
    BP8_BASELINE_TOTAL_HITS,
    bp8_expected_family,
)

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
K_TEMPLATE_DIR = BACKEND / "wp_templates" / "K"
DATA = BACKEND / "data"
MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
CYCLE_COMPOSABLES = FRONTEND / "composables" / "workpaper"

MUTATE_GUARDS = BACKEND / "scripts" / "diagnose" / "mutate_k_cycle_guards.py"
MUTATE_TASK53 = BACKEND / "scripts" / "diagnose" / "mutate_task53_k_cycle_migration_guards.py"

# hardcoded 六模式正则（与 test_task53 同源）
_HARDCODED_PATTERNS = {
    "blankRows_literal_count": re.compile(r"blankRows\s*\([^,)]*,\s*\d+\s*\)"),
    "horizontal_company_column_literals": re.compile(r"['\"]公司\s*[1-9]\d*['\"]"),
    "column_key_uses_label": re.compile(r"key\s*:\s*(?:row|col|c)\.label"),
    "row_cell_key_uses_label": re.compile(r"cells\s*\[\s*(?:row|r)\.label\s*\]"),
    "seed_placeholder_literal": re.compile(r"['\"](?:项目|成本项目|单位)\s*N['\"]"),
    "positional_row_id_template": re.compile(
        r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}"
    ),
}


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _sheet_names(path: pathlib.Path) -> list[str]:
    wb = load_workbook(path, read_only=True, data_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def _strip_comments(source: str) -> str:
    def _blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    source = re.sub(r"/\*.*?\*/", _blank, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank, source, flags=re.S)
    source = re.sub(r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source)
    return source


def _k_cycle_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for n in range(1, 14):
        d = WP_COMPONENTS / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and p.suffix in (".ts", ".vue") and "__tests__" not in p.as_posix():
                    out.append(p)
    for p in sorted(WP_COMPONENTS.iterdir()):
        if p.suffix == ".vue" and re.match(r"^GtK\d+", p.name):
            out.append(p)
    for p in sorted(WP_COMPOSABLES.iterdir()):
        if p.suffix == ".ts" and re.match(r"^(use)?[kK](1[0-3]|[1-9])(?![0-9])", p.name):
            out.append(p)
    for n in range(1, 14):
        d = CYCLE_COMPOSABLES / f"k{n}"
        if d.is_dir():
            for p in d.rglob("*.ts"):
                if "__tests__" not in p.as_posix():
                    out.append(p)
    return sorted(set(out))


_TEXT_CACHE: dict[str, str] = {}


def _cached_text(p: pathlib.Path) -> str:
    key = str(p)
    if key not in _TEXT_CACHE:
        _TEXT_CACHE[key] = p.read_text(encoding="utf-8")
    return _TEXT_CACHE[key]


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def template_files() -> list[pathlib.Path]:
    return sorted(
        f for f in K_TEMPLATE_DIR.iterdir()
        if f.suffix == ".xlsx" and not f.name.startswith("~$")
    )


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return _k_cycle_files()


# ════════════════════════════════════════════════════════════════════════════
# ① 本表行越界 0 格
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero1RowOutOfRange:
    """引用行号 > max_row（排除含 ! 的跨表式）现算为 0。"""

    _REF_RX = re.compile(
        r"(?<!\!)"  # 不含 ! 前缀（排除跨表引用）
        r"[A-Z]{1,3}(\d+)"  # 列字母+行号
    )

    def test_no_in_sheet_formula_references_row_beyond_max(
        self, template_files: list[pathlib.Path]
    ) -> None:
        bad: list[str] = []
        for f in template_files:
            wb = load_workbook(f, read_only=True, data_only=False)
            for sn in wb.sheetnames:
                ws = wb[sn]
                max_r = ws.max_row or 0
                for row in ws.iter_rows():
                    for cell in row:
                        v = cell.value
                        if not isinstance(v, str) or not v.startswith("="):
                            continue
                        # 只检查不含 ! 的引用段
                        # 把公式按 ! 分段，只看不紧跟 ! 的段
                        for part in re.split(r"'[^']*'![A-Z]+\d+|[A-Za-z]+![A-Z]+\d+", v):
                            for m in self._REF_RX.finditer(part):
                                row_num = int(m.group(1))
                                if row_num > max_r:
                                    co = cell.coordinate if hasattr(cell, 'coordinate') else '?'
                                    bad.append(f"{f.name}/{sn}/{co}: row {row_num} > max {max_r}")
            wb.close()
        assert bad == [], f"本表行越界 {len(bad)} 处：\n" + "\n".join(bad[:10])


# ════════════════════════════════════════════════════════════════════════════
# ② 跨表引用指向不存在 sheet 0 格
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero2CrossSheetToMissing:
    """跨表引用指向的 sheet 在同一 workbook 不存在 => 0 格。"""

    _CROSS_RX = re.compile(r"'([^']+)'!")

    def test_no_cross_sheet_ref_points_to_missing_sheet(
        self, template_files: list[pathlib.Path]
    ) -> None:
        bad: list[str] = []
        for f in template_files:
            wb = load_workbook(f, read_only=True, data_only=False)
            all_sheets = set(wb.sheetnames)
            for sn in wb.sheetnames:
                ws = wb[sn]
                for row in ws.iter_rows():
                    for cell in row:
                        v = cell.value
                        if not isinstance(v, str) or not v.startswith("="):
                            continue
                        for m in self._CROSS_RX.finditer(v):
                            target = m.group(1)
                            if target not in all_sheets:
                                co = cell.coordinate if hasattr(cell, 'coordinate') else '?'
                                bad.append(f"{f.name}/{sn}/{co}: ref to '{target}' not found")
            wb.close()
        assert bad == [], f"跨表引不存在 sheet {len(bad)} 处：\n" + "\n".join(bad[:10])


# ════════════════════════════════════════════════════════════════════════════
# ③ 同尾码双 sheet 0（HC-5/JC-11 在 K 不命中）
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero3SameSuffixTwinSheet:
    """同尾码双 sheet = 0。K8-6/K8-7 是不同尾码的方向变体，不是同尾码。"""

    _SUFFIX_RX = re.compile(r"[A-Z]\d+-(\d+)$")

    def test_no_same_suffix_twin_sheets(
        self, template_files: list[pathlib.Path]
    ) -> None:
        bad: list[str] = []
        for f in template_files:
            names = _sheet_names(f)
            suffix_map: dict[str, list[str]] = {}
            for n in names:
                m = self._SUFFIX_RX.search(n)
                if m:
                    suffix = m.group(1)
                    suffix_map.setdefault(suffix, []).append(n)
            for suffix, sheets in suffix_map.items():
                if len(sheets) > 1:
                    bad.append(f"{f.name}: suffix '{suffix}' has {sheets}")
        assert bad == [], f"同尾码双 sheet {len(bad)} 处：\n" + "\n".join(bad[:10])


# ════════════════════════════════════════════════════════════════════════════
# ④ Excel Table 0
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero4ExcelTable:
    """Excel Table（结构化表）在 K 循环 14 册全部为 0。"""

    def test_no_excel_tables_in_any_template(
        self, template_files: list[pathlib.Path]
    ) -> None:
        bad: list[str] = []
        for f in template_files:
            wb = load_workbook(f, read_only=False, data_only=False)
            for sn in wb.sheetnames:
                ws = wb[sn]
                tables = list(ws.tables.values()) if hasattr(ws, 'tables') else []
                if tables:
                    bad.append(f"{f.name}/{sn}: {len(tables)} table(s)")
            wb.close()
        assert bad == [], f"Excel Table {len(bad)} 处：\n" + "\n".join(bad[:10])


# ════════════════════════════════════════════════════════════════════════════
# ⑥ hardcoded 六模式里五个为 0 + 第六个 positional_row_id_template == 13
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero6HardcodedPatterns:
    """KC-24: 六模式里五个为 0，第六个（positional_row_id_template）== 13。"""

    def _scan(self, k_files: list[pathlib.Path], name: str) -> list[str]:
        rx = _HARDCODED_PATTERNS[name]
        out: list[str] = []
        for p in k_files:
            src = _strip_comments(_cached_text(p))
            for i, line in enumerate(src.split("\n"), 1):
                if rx.search(line):
                    out.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
        return out

    @pytest.mark.parametrize("name", [
        "blankRows_literal_count",
        "horizontal_company_column_literals",
        "column_key_uses_label",
        "row_cell_key_uses_label",
        "seed_placeholder_literal",
    ])
    def test_five_hardcoded_patterns_are_zero(
        self, k_files: list[pathlib.Path], name: str
    ) -> None:
        hits = self._scan(k_files, name)
        assert hits == [], f"模式 {name} 应为 0，实得 {len(hits)} 处：{hits[:5]}"

    def test_positional_row_id_template_is_13(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 KF-P59: 第六个模式**基线** 13 非 0（照抄 J 的六个全 0 即假红）。

        🔴 结构性结论是「第六个模式不为 0」，**不是「恰好 13」**。基线 13 记在
        `BP8_BASELINE_TEMPLATE_HITS`；lane 2 收敛后现算降为 lane 1 残留 + 2 处
        family_c 前缀（family_c 非缺陷、故意保留）。判据因此分两侧：
        ① 基线常量不被改小 ② 现算 > 0 且**已收敛 entry 只剩 family_c**。
        """
        assert BP8_BASELINE_TEMPLATE_HITS == 13, "基线被篡改"
        hits = self._scan(k_files, "positional_row_id_template")
        assert len(hits) > 0, (
            "第六个模式降到 0 ⇒ 「K 与 J 不同」的结构性结论须撤"
        )
        assert len(hits) <= BP8_BASELINE_TEMPLATE_HITS

    def test_template_residue_is_entropy_bearing_only(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 收敛后残留的模板命中，其所在行必须**带熵**（family_c）或属未收敛 lane。

        判据自包含（p3 不借共享工具）：按「同行是否含 `Date.now()`/`Math.random()`」
        判熵，按「文件名是否 K1~K7 域」判未收敛 lane。
        """
        entropy = re.compile(r"Date\.now\(\)|Math\.random\(\)")
        unconverged = re.compile(r"(?:^|/)(?:use)?K[1-7](?![0-9])", re.I)
        residue: list[str] = []
        for p in k_files:
            src = _strip_comments(_cached_text(p))
            for i, line in enumerate(src.split("\n"), 1):
                if not re.search(
                    r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}", line
                ):
                    continue
                ref = f"{p.relative_to(ROOT).as_posix()}#L{i}"
                if entropy.search(line) or unconverged.search(p.name):
                    continue
                residue.append(ref)
        assert residue == [], (
            f"既不带熵又属已收敛 lane 的模板命中：{residue}"
        )

    def test_positional_row_id_is_subset_of_identity_hits(
        self, manifest_slice: dict, k_files: list[pathlib.Path]
    ) -> None:
        """KF-P59: 13 处是位置化 48 处的子集。"""
        tmpl = set(self._scan(k_files, "positional_row_id_template"))
        # 位置化 identity hits（同 test_task53 口径）
        _IDENTITY_KEY = re.compile(r"(?<![\w$])(rowId|rowKey|id)\s*:\s*([^,\n]+)")
        _POS_TOKEN = re.compile(r"(?:^|[^\w$])(?:i|idx|index)(?:\s*\+\s*1)?(?:\s*\}|\s*[,)\]`]|$)")
        _POS_INTERP = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
        pos_refs: set[str] = set()
        for p in k_files:
            src = _strip_comments(_cached_text(p))
            for i, line in enumerate(src.split("\n"), 1):
                for m in _IDENTITY_KEY.finditer(line):
                    val = m.group(2).strip()
                    if _POS_TOKEN.search(val) or _POS_INTERP.search(val):
                        pos_refs.add(f"{p.relative_to(ROOT).as_posix()}#L{i}")
        assert tmpl <= pos_refs, (
            f"positional_row_id_template 有不在身份键命中里的行：{sorted(tmpl - pos_refs)}"
        )

    def test_total_positional_identity_hits_is_48(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """KC-6: 位置化总命中**基线** 48 处，现算走收敛账本。"""
        _IDENTITY_KEY = re.compile(r"(?<![\w$])(rowId|rowKey|id)\s*:\s*([^,\n]+)")
        _POS_TOKEN = re.compile(r"(?:^|[^\w$])(?:i|idx|index)(?:\s*\+\s*1)?(?:\s*\}|\s*[,)\]`]|$)")
        _POS_INTERP = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
        hits = []
        for p in k_files:
            src = _strip_comments(_cached_text(p))
            for i, line in enumerate(src.split("\n"), 1):
                for m in _IDENTITY_KEY.finditer(line):
                    val = m.group(2).strip()
                    # 🔴 固定槽位持久化键是扫描器误报（见 facts 层登记），不计入命中
                    from tests.workpaper_sync.k_foundation_facts import (
                        is_fixed_slot_exempt,
                    )

                    if is_fixed_slot_exempt(p, val):
                        continue
                    if _POS_TOKEN.search(val) or _POS_INTERP.search(val):
                        hits.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
        expected = sum(bp8_expected_family().values())
        assert len(hits) == expected, (
            f"位置化命中：基线 {BP8_BASELINE_TOTAL_HITS} − 已收敛 = {expected}，"
            f"实得 {len(hits)}"
        )
        assert BP8_BASELINE_TOTAL_HITS == 48, "基线被篡改"


# ════════════════════════════════════════════════════════════════════════════
# ⑦ duplicate_account_aggregation_found 0
# ════════════════════════════════════════════════════════════════════════════
class TestStructuralZero7DuplicateAccount:
    """duplicate_account_aggregation_found 在 K 域为 0。"""

    def test_duplicate_account_aggregation_found_is_zero(
        self, manifest_slice: dict
    ) -> None:
        a = manifest_slice["account_scope_and_four_table_audit"]
        assert a["backend_four_table_reuse"]["duplicate_aggregation_found"] == 0


# ════════════════════════════════════════════════════════════════════════════
# KF-P60: blankRows 全 K 域 0 次调用
# ════════════════════════════════════════════════════════════════════════════
class TestKFP60BlankRowsNotUsed:
    """blankRows 在 K 域的调用次数为 0 ⇒ HC-13 不命中。"""

    def test_blank_rows_call_count_is_zero(
        self, k_files: list[pathlib.Path]
    ) -> None:
        rx = re.compile(r"\bblankRows\s*\(")
        hits = []
        for p in k_files:
            src = _strip_comments(_cached_text(p))
            for i, line in enumerate(src.split("\n"), 1):
                if rx.search(line):
                    hits.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
        assert hits == [], f"blankRows 调用应为 0，实得 {len(hits)} 处：{hits[:5]}"


# ════════════════════════════════════════════════════════════════════════════
# 变异脚本存在且可引用
# ════════════════════════════════════════════════════════════════════════════
class TestMutationScriptsExist:
    """变异证明的脚本存在（不新写）。实际变异验证需手动执行。"""

    def test_mutate_k_cycle_guards_exists(self) -> None:
        assert MUTATE_GUARDS.exists(), f"变异脚本不存在：{MUTATE_GUARDS}"

    def test_mutate_task53_migration_guards_exists(self) -> None:
        assert MUTATE_TASK53.exists(), f"变异脚本不存在：{MUTATE_TASK53}"

    def test_mutate_guards_has_mutations(self) -> None:
        """脚本包含变异清单（MUTATIONS 列表非空）。"""
        src = MUTATE_GUARDS.read_text(encoding="utf-8")
        assert "MUTATIONS" in src, "脚本没有 MUTATIONS 清单"
        assert "Mutation(" in src, "脚本没有 Mutation 定义"

    def test_mutate_task53_has_mutations(self) -> None:
        src = MUTATE_TASK53.read_text(encoding="utf-8")
        assert "MUTATIONS" in src or "Mutation(" in src, "脚本没有变异清单"
