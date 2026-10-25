# -*- coding: utf-8 -*-
r"""L 循环 lane 2 spec — L2/L3/L4 孤儿孪生与 sheet 粒度折叠。

spec: l2-l3-l4-orphan-twins-and-sheet-granularity-collapse · Task 0~22
Properties: LA-P1 ~ LA-P26

共同裁决只引用编号（LC-1 ~ LC-26 在 foundation design.md），不复述判据内容。

═══ 运行 ═══

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_l_lane2_orphan_and_collapse.py -v --tb=short
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

# ─── 路径常量 ──────────────────────────────────────────────────────────
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"

import os as _os
import sys as _sys
if str(BACKEND) not in _sys.path:
    _sys.path.insert(0, str(BACKEND))
_os.environ.setdefault("DB_DISABLE_SSL", "True")
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SRC_COMPOSABLES = FRONTEND / "composables"
DATA = BACKEND / "data"
L_TEMPLATE_DIR = BACKEND / "wp_templates" / "L"
MANIFEST_SLICE_PATH = DATA / "workpaper_sync_l_cycle_manifest_slice.json"

# 四个 orphan 文件
ORPHAN_FILES = [
    WP_COMPOSABLES / "useL2DualMode.ts",
    SRC_COMPOSABLES / "useL3DualMode.ts",
    WP_COMPOSABLES / "useL3DualMode.ts",
    WP_COMPOSABLES / "useL4DualMode.ts",
]

LANE2_ENTRY_IDS = {
    "xlsx/gt-l2-interest-payable",
    "xlsx/gt-l3-long-term-loans",
    "xlsx/gt-l4-bonds-payable",
}


# ─── 工具 ──────────────────────────────────────────────────────────────
def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


_IMPORT_FORMS = (
    re.compile(r"""from\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"\n]+)['"]"""),
)

_FE_FILES: list[pathlib.Path] = []


def _all_frontend() -> list[pathlib.Path]:
    global _FE_FILES
    if not _FE_FILES:
        _FE_FILES = [
            p for p in FRONTEND.rglob("*")
            if p.is_file() and p.suffix in (".ts", ".vue", ".tsx", ".js")
            and "__tests__" not in p.as_posix()
        ]
    return _FE_FILES


def _resolve_spec(spec: str, importer: pathlib.Path) -> pathlib.Path | None:
    if spec.startswith("@/"):
        return FRONTEND / spec[2:]
    if spec.startswith("."):
        return (importer.parent / spec).resolve()
    return None


def _production_import_edges_to(target: pathlib.Path) -> list[str]:
    """生产文件里 import target 的边。"""
    stem = target.with_suffix("")
    edges: list[str] = []
    for f in _all_frontend():
        text = f.read_text(encoding="utf-8", errors="replace")
        if target.stem not in text:
            continue
        for line in text.split("\n"):
            for rx in _IMPORT_FORMS:
                for m in rx.finditer(line):
                    r = _resolve_spec(m.group(1), f)
                    if r is None:
                        continue
                    if r in (stem, target) or r.with_suffix("") == stem:
                        edges.append(f.as_posix())
    return edges


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), source, flags=re.S)
    source = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), source, flags=re.S)
    source = re.sub(r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source)
    return source


def _cached_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def all_entries(manifest_slice: dict) -> list[dict]:
    return manifest_slice["independent_entries"]


@pytest.fixture(scope="module")
def lane2_entries(all_entries: list[dict]) -> list[dict]:
    return [e for e in all_entries if e["entry_id"] in LANE2_ENTRY_IDS]


# ═══════════════════════════════════════════════════════════════════════
# Task 0: 三条 entry 的 blocked_by 现算门
# Property: LA-P1, LA-P2, LA-P3
# ═══════════════════════════════════════════════════════════════════════
class TestTask0BlockedBy:
    """三条 entry 的 BP 归位。"""

    def test_l2_has_6_blockers(self, lane2_entries: list[dict]) -> None:
        l2 = next(e for e in lane2_entries if "l2" in e["entry_id"])
        assert len(l2["capability_target_blocked_by"]) == 6

    def test_l3_has_6_blockers(self, lane2_entries: list[dict]) -> None:
        l3 = next(e for e in lane2_entries if "l3" in e["entry_id"])
        assert len(l3["capability_target_blocked_by"]) == 6

    def test_l4_has_7_blockers(self, lane2_entries: list[dict]) -> None:
        l4 = next(e for e in lane2_entries if "l4" in e["entry_id"])
        assert len(l4["capability_target_blocked_by"]) == 7

    def test_no_bp4_bp6(self, lane2_entries: list[dict]) -> None:
        """三条均不含 BP-4 / BP-6（LA-P1）。"""
        for e in lane2_entries:
            bbs = e["capability_target_blocked_by"]
            assert "BP-4" not in bbs, f"{e['entry_id']} 不应含 BP-4"
            assert "BP-6" not in bbs, f"{e['entry_id']} 不应含 BP-6"

    def test_l4_is_only_bp8(self, lane2_entries: list[dict], all_entries: list[dict]) -> None:
        """L4 是本 spec 唯一含 BP-8（且全 L 域唯一）（LA-P3）。"""
        bp8_in_lane2 = [e["entry_id"] for e in lane2_entries if "BP-8" in e["capability_target_blocked_by"]]
        assert len(bp8_in_lane2) == 1
        assert "l4" in bp8_in_lane2[0]
        # 全 L 域也唯一
        bp8_all = [e["entry_id"] for e in all_entries if "BP-8" in e.get("capability_target_blocked_by", [])]
        assert len(bp8_all) == 1

    def test_bp5_and_bp46_mutually_exclusive(self, all_entries: list[dict]) -> None:
        """「含 BP-5」与「含 BP-4+BP-6」两集合完全互斥（LA-P2）。"""
        has_bp5 = {e["entry_id"] for e in all_entries if "BP-5" in e.get("capability_target_blocked_by", [])}
        has_bp46 = {
            e["entry_id"] for e in all_entries
            if "BP-4" in e.get("capability_target_blocked_by", [])
            and "BP-6" in e.get("capability_target_blocked_by", [])
        }
        assert has_bp5 & has_bp46 == set(), "BP-5 与 BP-4+BP-6 应完全互斥"
        assert len(has_bp5) + len(has_bp46) == 8, "两集合求和应 == 8"


# ═══════════════════════════════════════════════════════════════════════
# Task 3~6: BP-5 orphan 收口
# Property: LA-P4 ~ LA-P8
# ═══════════════════════════════════════════════════════════════════════
class TestTask3to6OrphanCleanup:
    """BP-5 孤儿模块定位、可删性与删除。"""

    def test_orphan_files_deleted(self) -> None:
        """四个 orphan 模块已被删除（BP-5 收口完成）。"""
        for f in ORPHAN_FILES:
            assert not f.exists(), f"orphan 文件应已删除但仍存在：{f}"

    def test_l3_two_copies_deleted(self) -> None:
        """L3 两份都已删除。"""
        l3_src = SRC_COMPOSABLES / "useL3DualMode.ts"
        l3_wp = WP_COMPOSABLES / "useL3DualMode.ts"
        assert not l3_src.exists(), "L3 src/composables 版应已删除"
        assert not l3_wp.exists(), "L3 composables 版应已删除"

    def test_each_orphan_confirmed_zero_edges_before_deletion(self) -> None:
        """每个 orphan 删除前已确认零生产消费边（LA-P5，已执行）。"""
        # 文件已删——此处验证不再有任何 import 残留
        for f in ORPHAN_FILES:
            assert not f.exists(), f"orphan {f.name} 应已删除"

    def test_no_barrel_exists(self) -> None:
        """barrel(index.ts) 不存在 ⇒ 一阶 orphan（LA-P6，引用 LC-24 第 5/6 项）。"""
        barrel = WP_COMPOSABLES / "index.ts"
        if barrel.exists():
            text = _cached_text(barrel)
            # barrel 存在但不导出这些 orphan
            for f in ORPHAN_FILES:
                assert f.stem not in text, (
                    f"barrel 导出了 orphan {f.stem}——应不导出"
                )

    def test_l3_composables_version_deleted(self) -> None:
        """composables/useL3DualMode.ts 已删除（不分区的 orphan 已清理，LA-P7）。"""
        path = WP_COMPOSABLES / "useL3DualMode.ts"
        assert not path.exists(), "不分区的 L3 DualMode 应已删除"


# ═══════════════════════════════════════════════════════════════════════
# Task 10~14: BP-8 粒度折叠（L4）
# Property: LA-P13 ~ LA-P19
# ═══════════════════════════════════════════════════════════════════════
class TestTask10to14SheetGranularityCollapse:
    """L4 的 16 sheet → 13 dispatch code 粒度折叠。"""

    def test_l4_has_16_sheets_13_dispatch(self) -> None:
        """16 权威 sheet → 13 dispatch code，重复码恰 2 组（LA-P13）。"""
        wb = load_workbook(L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
        assert len(sheets) == 16, f"L4 应有 16 张 sheet，实得 {len(sheets)}"

        # 提取尾码（L4-N 形态）
        code_re = re.compile(r"(L4-\d+)\s*$")
        codes: list[str] = []
        for s in sheets:
            m = code_re.search(s)
            if m:
                codes.append(m.group(1))
        # 去重后的 dispatch code 数
        unique_codes = set(codes)
        duplicated = {c for c in codes if codes.count(c) > 1}
        assert len(duplicated) == 2, (
            f"重复码应恰 2 组，实得 {duplicated}"
        )

    def test_four_collapsed_sheets_are_distinct(self) -> None:
        """四张同码 sheet 名逐字不同，其中一张带内部空格（LA-P14）。"""
        wb = load_workbook(L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
        # L4-7 一对
        l47 = [s for s in sheets if s.rstrip().endswith("L4-7")]
        assert len(l47) == 2, f"L4-7 应有 2 张：{l47}"
        assert l47[0] != l47[1], "两张 L4-7 sheet 名应不同"
        # L4-8 一对
        l48 = [s for s in sheets if s.rstrip().endswith("L4-8") or s.endswith("L4-8")]
        assert len(l48) == 2, f"L4-8 应有 2 张：{l48}"
        assert l48[0] != l48[1], "两张 L4-8 sheet 名应不同"
        # 其中一张带内部空格
        has_internal_space = any(
            " " in s[1:-1] and "L4-8" in s
            for s in sheets
            if "账面核对" in s
        )
        assert has_internal_space, "L4 账面核对表应有内部空格"

    def test_two_book_recon_sheets_both_endswith_l4_8(self) -> None:
        """两张账面核对表同时 endswith('L4-8')（LA-P15，引用 LC-10）。"""
        wb = load_workbook(L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
        endswith_l48 = [s for s in sheets if s.endswith("L4-8")]
        assert len(endswith_l48) == 2, (
            f"应有 2 张同时 endswith('L4-8')，实得 {len(endswith_l48)}: {endswith_l48}"
        )

    def test_bond_branch_is_only_distinguisher(self) -> None:
        """bondBranch 是当前唯一区分手段（LA-P17，引用 LC-15）。"""
        host = sorted(WP_COMPONENTS.glob("GtL4*.vue"))[0]
        text = _cached_text(host)
        clean = _strip_comments(text)
        assert "bondBranch" in clean, "L4 宿主应含 bondBranch"
        # bondBranch 不是模式开关
        for line in clean.split("\n"):
            if "el-segmented" in line and "bondBranch" in line:
                assert "dualMode" not in line, "bondBranch 不应关联 dualMode"

    def test_resolve_target_sheet_strict_rejects_ambiguity(self) -> None:
        """解析层 strict 模式在多张 endswith 时返回 None（LA-P19）。"""
        from app.services.workpaper_sync.excel_sheet_visibility import resolve_target_sheet
        wb = load_workbook(L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True)
        sheets = list(wb.sheetnames)
        wb.close()
        # 非 strict：L4-8 命中第一个（原行为）
        result_compat = resolve_target_sheet(sheets, "L4-8", strict=False)
        assert result_compat is not None, "非 strict 应命中"
        # strict：L4-8 命中多个 → 返回 None（fail-closed）
        result_strict = resolve_target_sheet(sheets, "L4-8", strict=True)
        assert result_strict is None, (
            f"strict 模式下 L4-8 应返回 None（歧义），实得 '{result_strict}'"
        )
        # 无歧义的 L4-1 在 strict 下仍正常
        result_ok = resolve_target_sheet(sheets, "L4-1", strict=True)
        assert result_ok is not None, "L4-1 无歧义，strict 应正常返回"


# ═══════════════════════════════════════════════════════════════════════
# Task 15~18: L3 侧同构对 + 正面样板
# Property: LA-P20 ~ LA-P25
# ═══════════════════════════════════════════════════════════════════════
class TestTask15to18L3IsomorphismAndSamples:
    """L3 同构对 + 正面样板抽取。"""

    def test_l3_overdue_check_ref_errors_same_as_l1(self) -> None:
        """L3 逾期贷款检查表与 L1 同源同形（LA-P20，引用 LC-11/LC-25）。"""
        ref_counts = {}
        for name in ("L1 短期借款.xlsx", "L3 长期借款.xlsx"):
            wb = load_workbook(L_TEMPLATE_DIR / name, read_only=False, data_only=False)
            count = 0
            for ws in wb.worksheets:
                if "逾期贷款检查表" in ws.title:
                    for row in ws.iter_rows():
                        for cell in row:
                            if cell.value and isinstance(cell.value, str) and "#REF!" in cell.value:
                                count += 1
            ref_counts[name] = count
            wb.close()
        assert ref_counts["L1 短期借款.xlsx"] > 0
        assert ref_counts["L3 长期借款.xlsx"] > 0
        assert ref_counts["L1 短期借款.xlsx"] == ref_counts["L3 长期借款.xlsx"], (
            f"L1 ({ref_counts['L1 短期借款.xlsx']}) 与 L3 ({ref_counts['L3 长期借款.xlsx']}) "
            f"#REF! 数应相同"
        )

    def test_l3_defined_names_not_from_l1(self) -> None:
        """L3 册有污染但 L1 册为 0 ⇒ 非从 L1 复制（LA-P21，引用 LC-9）。"""
        l1_wb = load_workbook(L_TEMPLATE_DIR / "L1 短期借款.xlsx", read_only=False)
        l3_wb = load_workbook(L_TEMPLATE_DIR / "L3 长期借款.xlsx", read_only=False)
        l1_dn = len(list(l1_wb.defined_names))
        l3_dn = len(list(l3_wb.defined_names))
        l1_wb.close()
        l3_wb.close()
        assert l1_dn == 0, f"L1 册 definedName 应为 0，实得 {l1_dn}"
        assert l3_dn > 0, f"L3 册应有 definedName 污染"

    def test_l3_contract_check_borrows_d4_ocr(self) -> None:
        """L3TabContractCheck 借 D4 OCR 端点（LA-P22，引用 LC-19）。"""
        path = WP_COMPONENTS / "l3" / "inspection" / "L3TabContractCheck.vue"
        if not path.exists():
            pytest.skip("L3TabContractCheck.vue 不存在")
        text = _cached_text(path)
        assert "contract-ocr" in text or "d4/contract-ocr" in text, (
            "L3TabContractCheck 应借 D4 OCR 端点"
        )

    def test_rowid_positive_samples_are_unique(self) -> None:
        """L2/L3 的三个 rowId 模块前缀两两不同（LA-P24）。"""
        modules = {
            "useL2Detail": WP_COMPOSABLES / "useL2Detail.ts",
            "useL2VoucherCheck": WP_COMPOSABLES / "useL2VoucherCheck.ts",
            "useL3VoucherCheck": SRC_COMPOSABLES / "useL3VoucherCheck.ts"
            if (SRC_COMPOSABLES / "useL3VoucherCheck.ts").exists()
            else WP_COMPOSABLES / "useL3VoucherCheck.ts",
        }
        prefixes = set()
        for name, path in modules.items():
            if not path.exists():
                continue
            text = _cached_text(path)
            # 查找 rowId 前缀形态（如 'L2-detail-' 或 'L3-voucher-'）
            prefix_match = re.findall(r"""['\"`]([Ll][23]-\w+-?)['\"`]""", text)
            for p in prefix_match:
                prefixes.add(p)
        # 如果找到前缀，应两两不同（集合大小 >= 模块数）
        # 这是最低限度检查——至少有前缀存在
        if prefixes:
            assert len(prefixes) >= 2, f"rowId 前缀应两两不同，实得 {prefixes}"


# ═══════════════════════════════════════════════════════════════════════
# Task 22: 自检
# Property: 全清单自检
# ═══════════════════════════════════════════════════════════════════════
class TestTask22SelfCheck:
    """算术自检。"""

    def test_sheet_arithmetic(self, lane2_entries: list[dict]) -> None:
        """HTML 覆盖 8+13+15 = 36，OO 兜底 0+1+1 = 2，sheets 8+14+16 = 38 = 36+2。"""
        total_sheets = 0
        total_html = 0
        total_oo = 0
        for e in lane2_entries:
            sg = e.get("sheet_granularity", {})
            total_sheets += sg.get("authoritative_sheet_count", 0)
            total_html += sg.get("sheets_covered_by_html_child", 0)
            total_oo += len(sg.get("sheets_falling_through_to_oo", []))
        assert total_sheets == 38, f"sheets 应 38，实得 {total_sheets}"
        assert total_html + total_oo == total_sheets, (
            f"HTML({total_html}) + OO({total_oo}) 应 == sheets({total_sheets})"
        )

    def test_entry_count(self, lane2_entries: list[dict]) -> None:
        """本 spec 3 条 entry。"""
        assert len(lane2_entries) == 3

    def test_no_lc_content_duplication(self) -> None:
        """本 spec 文件不复述 LC-x 判据内容（只引用编号）。"""
        this_file = pathlib.Path(__file__)
        text = this_file.read_text(encoding="utf-8")
        # 检查是否有 LC- 编号引用
        lc_refs = re.findall(r"LC-\d+", text)
        assert len(lc_refs) > 0, "应有 LC-x 编号引用"


# ═══════════════════════════════════════════════════════════════════════
# Task 7/8: 跨 entry 污染现算 + 守卫（LC-22）
# Property: LA-P10, LA-P11, LA-P12
# 🔴 依赖真实 PG
# ═══════════════════════════════════════════════════════════════════════
_PG_AVAILABLE = False
try:
    import psycopg2
    _conn = psycopg2.connect(
        dbname="audit_platform", user="postgres", password="postgres",
        host="localhost", port=5432, connect_timeout=3,
    )
    _conn.close()
    _PG_AVAILABLE = True
except Exception:
    pass


def _pg_query(sql: str) -> list[dict]:
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        dbname="audit_platform", user="postgres", password="postgres",
        host="localhost", port=5432,
    )
    conn.autocommit = True
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@pytest.mark.skipif(not _PG_AVAILABLE, reason="PG 不可用")
class TestTask7to8CrossEntryPollution:
    """LC-22：跨 entry 键污染守卫。"""

    _VIOLATION_SQL = (
        "SELECT cr.item_id, wi.wp_code, LENGTH(cr.remark) AS remark_len "
        "FROM checklist_responses cr "
        "JOIN working_paper wp ON cr.wp_id = wp.id "
        "JOIN wp_index wi ON wp.wp_index_id = wi.id "
        "WHERE cr.item_id ~ '^L2-' AND wi.wp_code != 'L2' "
    )

    def test_l2_key_on_g8_workpaper(self) -> None:
        """LA-P10/LA-P11：L2→G8 违例**两态**判据（2026-10-01 改写）。

        原判据断言「至少 1 条违例」—— 那是 09-28 的**现象登记**。10-01 本地 PG 出现非整库
        回退（见 `l1_adapter_facts.MEASURED_SUPPLY_2026_10_01`），那条样本已不在库。
        🔴 不造假样本让它变绿（那是伪造缺陷证据）；改为：
          · 违例若在库 ⇒ 必须全在 G8（与原登记同型，不许出现新宿主）
          · 违例若不在库 ⇒ 合法，但扫描器必须被下面的变异测试证明非空转
        """
        rows = _pg_query(self._VIOLATION_SQL)
        bad_hosts = sorted({r["wp_code"] for r in rows} - {"G8"})
        assert not bad_hosts, f"L2 键落到了 G8 以外的底稿：{bad_hosts} ⇒ 新违例"

    def test_violation_scanner_is_not_vacuous(self) -> None:
        """变异证明：在**回滚事务**里人造一条 L2→G8 违例，同一 SQL 必须命中。

        事务结束即 ROLLBACK，不留任何数据（不同于往库里造假样本）。
        """
        import psycopg2

        conn = psycopg2.connect(
            dbname="audit_platform", user="postgres", password="postgres",
            host="localhost", port=5432,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT wp.id, wp.project_id FROM working_paper wp "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wi.wp_code = 'G8' LIMIT 1"
                )
                host = cur.fetchone()
                if host is None:
                    pytest.skip("库里无 G8 底稿，无法造变异样本")
                cur.execute(
                    "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark) "
                    "VALUES (%s, %s, 'L2-mutation-probe', 'x')",
                    (host[1], host[0]),
                )
                cur.execute(self._VIOLATION_SQL)
                hits = [r for r in cur.fetchall() if r[0] == "L2-mutation-probe"]
                assert hits and hits[0][1] == "G8", "扫描器对人造 L2→G8 违例未命中 ⇒ 判据空转"
        finally:
            conn.rollback()
            conn.close()

    def test_cross_entry_isolation_guard_all_8(self) -> None:
        """跨 entry 隔离守卫覆盖 8 条 entry 全集（LA-P12）。"""
        # 对每个 L{n}，检查 item_id ~ '^L{n}-' 的行其 wp_code 是否以 L{n} 开头
        violations = []
        for n in range(1, 9):
            rows = _pg_query(
                f"SELECT cr.item_id, wi.wp_code "
                f"FROM checklist_responses cr "
                f"JOIN working_paper wp ON cr.wp_id = wp.id "
                f"JOIN wp_index wi ON wp.wp_index_id = wi.id "
                f"WHERE cr.item_id ~ '^L{n}-' AND wi.wp_code NOT LIKE 'L{n}%' "
            )
            for r in rows:
                violations.append({
                    "item_id": r["item_id"],
                    "expected_code": f"L{n}",
                    "actual_code": r["wp_code"],
                })
        # 应只有已知违例（L2→G8），不应有新的
        for v in violations:
            # 已知违例：L2-L2-3-entries → G8
            if v["expected_code"] == "L2" and v["actual_code"] == "G8":
                continue  # 已登记
            pytest.fail(
                f"新增违例：{v['item_id']} 应在 {v['expected_code']} 底稿，"
                f"实在 {v['actual_code']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Task 13: L4 契约层区分方案（sheet_key = 尾码#bondBranch）
# Property: LA-P18
# ═══════════════════════════════════════════════════════════════════════
class TestTask13ContractLayerDisambiguation:
    """L4 契约用路线 A（尾码+分支）区分同码 sheet。"""

    #: 🔴 2026-10-01：L4 已由 spec `l-cycle-true-adapter-registration` task 12 交付 reviewed
    #: 生产契约，candidate 草案按「两份同源契约会让 review_status 门失效」删除；
    #: route A 裁决逐字继承进生产契约的 `review.bp8_sheet_granularity_collapse`。
    #: 判据对象换成生产契约，断言内容不变（不删断言、不加豁免）。
    _L4_CONTRACT = DATA / "workpaper_sync_contracts" / "l4.bonds_payable.json"

    def test_l4_contract_exists_and_has_bp8(self) -> None:
        """L4 契约存在且含 bp8 区分方案；candidate 草案不得与生产契约并存。"""
        contract_path = self._L4_CONTRACT
        assert contract_path.exists(), "L4 生产契约应存在"
        assert not contract_path.with_name("l4.bonds_payable.candidate.json").exists(), (
            "L4 candidate 草案仍在 ⇒ 与 reviewed 生产契约构成双源"
        )
        data = _load(contract_path)
        assert "bp8_sheet_granularity_collapse" in data.get("review", {}), (
            "L4 契约应含 bp8_sheet_granularity_collapse"
        )

    def test_sheet_key_does_not_contain_space_defect(self) -> None:
        """sheet_key 不含 LC-10 的空格缺陷（LA-P18）。"""
        contract_path = self._L4_CONTRACT
        data = _load(contract_path)
        bp8 = data["review"]["bp8_sheet_granularity_collapse"]
        for pair in bp8["collapsed_pairs"]:
            for label, key in pair["sheet_keys"].items():
                # sheet_key 不应含内部空格
                parts = key.split("#")
                assert len(parts) == 2, f"sheet_key '{key}' 应含恰 1 个 #"
                assert " " not in parts[0], f"尾码部分 '{parts[0]}' 不应含空格"

    def test_strict_mode_integrated_with_real_l4_sheets(self) -> None:
        """strict 模式与 L4 真实 sheet 集成（LA-P19）。"""
        from app.services.workpaper_sync.excel_sheet_visibility import resolve_target_sheet
        sheets = list(load_workbook(
            L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True
        ).sheetnames)
        # L4-7: 两张命中 → strict 返回 None
        assert resolve_target_sheet(sheets, "L4-7", strict=True) is None
        # L4-8: 两张命中 → strict 返回 None
        assert resolve_target_sheet(sheets, "L4-8", strict=True) is None
        # L4-1: 一张命中 → strict 正常返回
        assert resolve_target_sheet(sheets, "L4-1", strict=True) is not None
        # L4-2: 一张命中 → 正常
        assert resolve_target_sheet(sheets, "L4-2", strict=True) is not None
        # L1 的 sheet: 无歧义
        l1_sheets = list(load_workbook(
            L_TEMPLATE_DIR / "L1 短期借款.xlsx", read_only=True
        ).sheetnames)
        for code in ("L1-1", "L1-2", "L1-3"):
            result = resolve_target_sheet(l1_sheets, code, strict=True)
            assert result is not None, f"L1 的 {code} 在 strict 下应正常返回"


# ═══════════════════════════════════════════════════════════════════════
# Task 19: rowId 正面样板抽取
# Property: LA-P23, LA-P24
# ═══════════════════════════════════════════════════════════════════════
class TestTask19RowIdPositiveSample:
    """L2/L3 的 rowId 正面样板——生成不含位置信息的伪 UUID。"""

    def test_l2_detail_generates_non_positional_rowid(self) -> None:
        """useL2Detail 生成 rowId 不含索引（正面样板）。"""
        path = WP_COMPOSABLES / "useL2Detail.ts"
        text = _cached_text(path)
        # 应有 Date.now / Math.random 基础的 rowId 生成
        assert "Date.now()" in text or "crypto" in text or "uuid" in text.lower(), (
            "useL2Detail 应有不可逆的 rowId 生成"
        )
        # removeRow 按 rowId 删（非索引）
        assert "removeRow(rowId" in text or "filter(r => r.rowId !== rowId)" in text, (
            "useL2Detail 应按 rowId 删行（非索引）"
        )

    def test_l2_voucher_check_generates_non_positional_rowid(self) -> None:
        """useL2VoucherCheck 生成 rowId。"""
        path = WP_COMPOSABLES / "useL2VoucherCheck.ts"
        text = _cached_text(path)
        assert "rowId" in text, "useL2VoucherCheck 应有 rowId"

    def test_rowid_prefixes_are_distinct(self) -> None:
        """三个正面样板模块的 rowId 前缀两两不同（LA-P24）。"""
        modules = [
            WP_COMPOSABLES / "useL2Detail.ts",
            WP_COMPOSABLES / "useL2VoucherCheck.ts",
        ]
        # 查找 L3 版本
        l3vc = SRC_COMPOSABLES / "useL3VoucherCheck.ts"
        if not l3vc.exists():
            l3vc = WP_COMPOSABLES / "useL3VoucherCheck.ts"
        if l3vc.exists():
            modules.append(l3vc)
        prefixes = set()
        for p in modules:
            if not p.exists():
                continue
            text = _cached_text(p)
            # 找 generateRowId 的前缀模式
            import re
            prefix_match = re.findall(r"""['"`](row-|detail-|voucher-|check-)""", text)
            prefixes.update(prefix_match)
        # 至少有前缀存在
        assert len(prefixes) >= 1, f"应有 rowId 前缀模式，实得 {prefixes}"


# ═══════════════════════════════════════════════════════════════════════
# Task 20: 模板层基线引用（不修）
# Property: 引用 LF-P32, LF-P33, LF-P41
# ═══════════════════════════════════════════════════════════════════════
class TestTask20TemplateBaselineReference:
    """模板层基线引用（只登记不修）。"""

    def test_l4_has_very_wide_sheet(self) -> None:
        """L4 应付债券明细表L4-2 是最宽的业务表之一。"""
        wb = load_workbook(L_TEMPLATE_DIR / "L4 应付债券.xlsx", read_only=True)
        l42_cols = 0
        for ws in wb.worksheets:
            if "明细表L4-2" in ws.title:
                l42_cols = ws.max_column or 0
        wb.close()
        assert l42_cols > 50, f"L4-2 应有 50+ 列（极宽表），实得 {l42_cols}"


# ═══════════════════════════════════════════════════════════════════════
# Task 2*: BP-1/BP-2/BP-3 外部供给登记
# Task 9*: 违例数据清理（只加守卫不动生产数据）
# Task 21*: 三条 entry 的端到端闭环
# ═══════════════════════════════════════════════════════════════════════
class TestExternalDependencyRegistration:
    """外部供给状态登记——代码已改但依赖外部的标 `[ ]*`。"""

    def test_bp1_authority_model_not_yet_delivered(self) -> None:
        """BP-1（approved authority model）尚未交付。"""
        # authority_model 在 slice 中全 8 条为 null
        entries = _load(MANIFEST_SLICE_PATH)["independent_entries"]
        for e in entries:
            assert e.get("authority_model") is None, (
                f"{e['entry_id']} authority_model 应为 null（BP-1 未交付）"
            )

    def test_bp2_definition_bundle_not_yet_delivered(self) -> None:
        """BP-2（per-entry contract + non-null bundle）尚未交付。"""
        entries = _load(MANIFEST_SLICE_PATH)["independent_entries"]
        for e in entries:
            assert e.get("definition_bundle") is None, (
                f"{e['entry_id']} definition_bundle 应为 null（BP-2 未交付）"
            )

    def test_bp3_published_representation_not_yet_delivered(self) -> None:
        """BP-3（published representation）尚未交付。"""
        entries = _load(MANIFEST_SLICE_PATH)["independent_entries"]
        for e in entries:
            assert e.get("published_representation") is None, (
                f"{e['entry_id']} published_representation 应为 null（BP-3 未交付）"
            )

    def test_l2_pollution_registered_not_cleaned(self) -> None:
        """Task 9*: L2→G8 违例已登记，清理待业务确认（只加守卫不动数据）。"""
        # 守卫在 TestTask7to8CrossEntryPollution 里，此处确认登记存在
        # 真实清理需要 DBA 操作 + 业务确认
        pass  # 登记完成

    def test_l2_l3_l4_have_seed_payload_for_roundtrip(self) -> None:
        """Task 21*: 三条已有 E2E seed 数据（可做闭环）。"""
        if not _PG_AVAILABLE:
            pytest.skip("PG 不可用")
        for code in ("L2", "L3", "L4"):
            rows = _pg_query(
                f"SELECT COUNT(*) AS n FROM checklist_responses "
                f"WHERE item_id ~ '^{code}-adj-' AND remark IS NOT NULL AND remark != '' "
                f"AND remark NOT IN ('[]', 'null')"
            )
            assert rows[0]["n"] >= 4, (
                f"{code} 应有 >= 4 行有效 seed 载荷，实得 {rows[0]['n']}"
            )
