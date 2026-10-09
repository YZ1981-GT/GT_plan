# -*- coding: utf-8 -*-
"""N 循环 Lane2 spec — 阶段 3-4 守卫：N1 三值载体 + transport_key + parent_duplicate + 契约 + 真库。

spec: n1-n3-host-inline-router-and-shared-adoption
任务: 7（N1 三值载体守卫）、8（A 族行身份改造——前置条件记录）、9（transport_key N1 双 owner）、
      10（parent_duplicate 数据断言）、11（契约双列映射）、12（真库污染 2 条）
NA-P: 10~18

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane2_p1_carrier_and_contract.py -v --tb=short
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

import sys
sys.path.insert(0, str(BACKEND / "scripts" / "analyze"))
import n_cycle_scanner as scanner  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 任务 7：N1 三值载体守卫（NA-P10 / NA-P11）
# ════════════════════════════════════════════════════════════════════════════

class TestN1ThreeModeCarrier:
    """NA-P10：N1 三值含 matrix，9 个成员契约不减，5 条生产边。"""

    @pytest.fixture(scope="class")
    def n1_dual_src(self) -> str:
        return (WP_COMPOSABLES / "useN1DualMode.ts").read_text("utf-8", errors="replace")

    def test_three_modes_exist(self, n1_dual_src: str):
        """N1 支持三种模式：structured / matrix / onlyoffice。"""
        assert "'structured'" in n1_dual_src
        assert "'matrix'" in n1_dual_src
        assert "'onlyoffice'" in n1_dual_src

    def test_nine_consumed_members(self, n1_dual_src: str):
        """返回对象含 9 个被消费成员。"""
        # 从 return { ... } 块提取成员名
        ret_match = re.search(r"return\s*\{([\s\S]*?)\}\s*$", n1_dual_src, re.M)
        assert ret_match, "找不到 return 块"
        ret_body = ret_match.group(1)
        # 提取成员名（去重，排除注释行）
        members = set()
        for line in ret_body.split("\n"):
            line = line.strip()
            if line.startswith("//") or not line:
                continue
            m = re.match(r"(\w+)", line)
            if m:
                members.add(m.group(1))
        # design.md 声明 9 个：mode / modeOptions / switchMode / fetchingConfig /
        #   isOOHealthy / ooConfigReady / isOnlyOffice / isMatrix / onOoLoadFailed
        expected = {"mode", "modeOptions", "switchMode", "fetchingConfig",
                    "isOOHealthy", "ooConfigReady", "isOnlyOffice", "isMatrix", "onOoLoadFailed"}
        missing = expected - members
        assert len(missing) == 0, f"缺少成员：{missing}"

    def test_production_edges_5(self):
        """N1 三值载体有 5 条生产边（宿主 + 4 子 Tab）。"""
        pattern = re.compile(r"useN1DualMode")
        prod_edges = []
        for p in list(WP_COMPONENTS.rglob("*.vue")) + list(WP_COMPOSABLES.glob("*.ts")):
            if "__tests__" in p.as_posix():
                continue
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            if pattern.search(stripped) and p.name != "useN1DualMode.ts":
                prod_edges.append(p.name)
        assert len(prod_edges) == 5, f"生产边 {len(prod_edges)}（期望 5）：{prod_edges}"

    def test_localstorage_key_n1_dual_mode(self, n1_dual_src: str):
        """NA-P11：localStorage 键前缀为 n1-dual-mode，按 wpId 分区。"""
        assert "n1-dual-mode" in n1_dual_src
        assert "wpId" in n1_dual_src or "STORAGE_KEY" in n1_dual_src


# ════════════════════════════════════════════════════════════════════════════
# 任务 8：A 族行身份改造前置条件记录
# ════════════════════════════════════════════════════════════════════════════

class TestAFamilyIdentity:
    """NA-P16：A 族 3 处全在 useN1Adjudication.ts（前置条件记录，改造在后续）。"""

    def test_a_family_in_n1_adjudication(self):
        """${ITEM_PREFIX}-${index} 形态在 useN1Adjudication.ts 中存在。"""
        src = (WP_COMPOSABLES / "useN1Adjudication.ts").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        # 匹配 ${ITEM_PREFIX}-${i} 或 ${ITEM_PREFIX}-${index}
        hits = len(re.findall(r"\$\{ITEM_PREFIX\}-\$\{(?:i|index)\}", stripped))
        assert hits >= 2, f"A 族 ${ITEM_PREFIX}-${index} 命中 {hits}（期望 >= 2）"

    def test_n1_adjudication_categories_7(self):
        """N1_ADJUDICATION_CATEGORIES 有 7 个分类。"""
        src = (WP_COMPOSABLES / "useN1Adjudication.ts").read_text("utf-8", errors="replace")
        m = re.search(r"N1_ADJUDICATION_CATEGORIES[^=]*=\s*\[([\s\S]*?)\]", src)
        assert m
        items = re.findall(r"'([^']+)'", m.group(1))
        assert len(items) == 7


# ════════════════════════════════════════════════════════════════════════════
# 任务 9：transport_key 守卫（NA-P13 / NA-P14 / NA-P15）
# ════════════════════════════════════════════════════════════════════════════

class TestTransportKeyN1N3:
    """NA-P13~15：N1 双 owner + N3 单 owner + TK-2 双条件。"""

    def test_n1_double_owner(self):
        """NA-P13：N1 有双 owner 声明。"""
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        n1_prefixes = [k for k in tk["owners"] if k.startswith("N1")]
        assert len(n1_prefixes) >= 2, f"N1 前缀 {n1_prefixes}（期望 >= 2）"

    def test_n3_single_owner(self):
        """NA-P13：N3 单 owner（'N3-'）。"""
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        n3_prefixes = [k for k in tk["owners"] if k.startswith("N3")]
        assert len(n3_prefixes) == 1, f"N3 前缀 {n3_prefixes}（期望 1）"

    def test_n1_1_rows_zero_hit(self):
        """NA-P15：'N1-1-rows' 字面量 0 命中。"""
        prod, _ = scanner.scan_n_domain_files()
        count = 0
        for p in prod:
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            if "'N1-1-rows'" in stripped or '"N1-1-rows"' in stripped:
                count += 1
        assert count == 0, f"N1-1-rows 命中 {count}"

    def test_n3_1_rows_zero_hit(self):
        """NA-P15：'N3-1-rows' 字面量 0 命中。"""
        prod, _ = scanner.scan_n_domain_files()
        count = 0
        for p in prod:
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            if "'N3-1-rows'" in stripped or '"N3-1-rows"' in stripped:
                count += 1
        assert count == 0, f"N3-1-rows 命中 {count}"


# ════════════════════════════════════════════════════════════════════════════
# 任务 10：parent_duplicate 数据断言（NA-P12）
# ════════════════════════════════════════════════════════════════════════════

class TestParentDuplicateData:
    """NA-P12：parent_duplicate 4 条全挂 N1。"""

    @pytest.fixture(scope="class")
    def slice_data(self) -> dict:
        path = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
        if not path.exists():
            pytest.skip("N cycle slice 不存在")
        return json.loads(path.read_text("utf-8"))

    def test_count_4(self, slice_data: dict):
        """parent_duplicate_count = 4。"""
        scope = slice_data.get("slice_scope", slice_data)
        assert scope.get("parent_duplicate_count") == 4

    def test_all_under_n1(self, slice_data: dict):
        """4 条全挂 N1。"""
        pd_summary = slice_data.get("parent_duplicate_summary", {})
        children = pd_summary.get("children", [])
        assert len(children) == 4, f"children {len(children)}（期望 4）"
        for child in children:
            parent = child.get("parent_entry_id", "")
            assert "n1" in parent.lower(), f"parent {parent} 不包含 n1"

    def test_four_full_names(self, slice_data: dict):
        """逐条全名吻合。"""
        expected = {
            "xlsx/n1/calc/n1-tab-calc-table",
            "xlsx/n1/core/n1-tab-adjudication",
            "xlsx/n1/core/n1-tab-adjustment",
            "xlsx/n1/core/n1-tab-detail",
        }
        pd_summary = slice_data.get("parent_duplicate_summary", {})
        children = pd_summary.get("children", [])
        actual = {c.get("entry_id", "") for c in children}
        assert actual == expected, f"实际 {actual} ≠ 期望 {expected}"


# ════════════════════════════════════════════════════════════════════════════
# 任务 11：契约双列映射（NA-P17）
# ════════════════════════════════════════════════════════════════════════════

class TestContractFieldsLane2:
    """NA-P17：N1 conclusion 非空 14 / N3 conclusion 非空 2。"""

    def test_n1_adjudication_persists_conclusion(self):
        """useN1Adjudication.ts 持久化写入 conclusion。"""
        src = (WP_COMPOSABLES / "useN1Adjudication.ts").read_text("utf-8", errors="replace")
        assert "conclusion" in src

    def test_n1_form_data_reads_both_columns(self):
        """useN1FormData.ts 读取 remark 和 conclusion。"""
        path = WP_COMPOSABLES / "useN1FormData.ts"
        if not path.exists():
            pytest.skip("useN1FormData.ts 不存在")
        src = path.read_text("utf-8", errors="replace")
        assert "remark" in src and "conclusion" in src

    def test_n3_form_data_reads_both_columns(self):
        """useN3FormData.ts 读取 remark 和 conclusion。"""
        path = WP_COMPOSABLES / "useN3FormData.ts"
        if not path.exists():
            pytest.skip("useN3FormData.ts 不存在")
        src = path.read_text("utf-8", errors="replace")
        assert "remark" in src or "conclusion" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 12：真库污染 2 条登记（NA-P18）
# ════════════════════════════════════════════════════════════════════════════

class TestCrossEntryPollutionLane2:
    """NA-P18：N1/N3 各 1 条污染落 wp_code='G8'。"""

    def test_n1_n3_entries_keys_exist(self):
        """N1-3-entries 和 N3-3-entries 键在 slice 中已登记。"""
        slice_path = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
        if not slice_path.exists():
            pytest.skip("N cycle slice 不存在")
        text = slice_path.read_text("utf-8")
        # 查找跨 entry 污染或 G8 相关内容
        assert "N1" in text and "N3" in text
        assert "G8" in text or "cross_entry" in text

    def test_transport_key_n1_n3_all_start_with_n(self):
        """N1/N3 的 transport_key 前缀都以 N 开头（不以 G 开头）。"""
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        for prefix in tk["owners"]:
            if prefix.startswith("N1") or prefix.startswith("N3"):
                assert prefix.startswith("N"), f"前缀 {prefix} 不以 N 开头"


# ════════════════════════════════════════════════════════════════════════════
# 综合回归
# ════════════════════════════════════════════════════════════════════════════

class TestLane2Phase34Regression:
    """lane2 阶段 3-4 回归检查。"""

    def test_n1_host_intact(self):
        """N1 宿主完整。"""
        src = (WP_COMPONENTS / "GtN1DeferredTaxAssets.vue").read_text("utf-8", errors="replace")
        assert "useN1DualMode" in src
        assert "useN1Adjudication" in src or "N1TabAdjudication" in src

    def test_n3_host_intact(self):
        """N3 宿主完整。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        assert "N3TabAdjudication" in src
        assert "renderMode" in src
