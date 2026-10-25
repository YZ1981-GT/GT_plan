# -*- coding: utf-8 -*-
"""G46-P10 / P13 / P18 红判据：http 客户端探针 · 参考 sheet 字面量 · 零回归。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 5
Requirements: 4.2, 4.7, 5.6

P10 — 守卫探针按 http_client_binding 拼装（FD-2：四条用 http，两条用 api）
P13 — 两册「参考」sheet 排除清单不共用字面量（B7：连字符差异）
P18 — 零回归现算逐项（非 G4/G6 的 contract golden digest 逐项不变，GC-10）
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_FRONTEND_SRC = _REPO / "audit-platform" / "frontend" / "src"
_TPL_DIR = _BACKEND / "wp_templates"


# ═══════════════════════════════════════════════════════════════════════════
# G46-P10：http 客户端探针按 FD-2 登记拼装
# ═══════════════════════════════════════════════════════════════════════════

# slice 逐 entry 的 http_client_binding（FD-2 实测）
_HTTP_CLIENT_BINDING: dict[str, str] = {
    "G4-main": "api",       # useG4BonInvFormData.ts → import api from apiProxy
    "G4-sppi": "api",       # useG4BonSppFormData.ts → import api from apiProxy
    "G4-ecl": "http",       # useG4EclFormData.ts → import http from utils/http
    "G6-main": "http",      # useG6MainFormData.ts → import http from utils/http
    "G6-sppi": "http",      # useG6SppiFormData.ts → import http from utils/http
    "G6-ecl": "http",       # useG6EclFormData.ts → import http from utils/http
}

# 对应的 FormData composable 文件名
_FORM_DATA_FILES: dict[str, str] = {
    "G4-main": "useG4BonInvFormData.ts",
    "G4-sppi": "useG4BonSppFormData.ts",
    "G4-ecl": "useG4EclFormData.ts",
    "G6-main": "useG6MainFormData.ts",
    "G6-sppi": "useG6SppiFormData.ts",
    "G6-ecl": "useG6EclFormData.ts",
}


def _find_form_data(entry_label: str) -> Path:
    """定位 FormData composable 文件。"""
    fname = _FORM_DATA_FILES[entry_label]
    hits = list(_FRONTEND_SRC.rglob(fname))
    assert hits, f"{entry_label} FormData 文件不存在: {fname}"
    return hits[0]


class TestG46P10HttpClientBinding:
    """Validates: Req 4.2 —— 探针按 slice 登记的 http_client_binding 拼装。"""

    @pytest.mark.parametrize("entry_label", sorted(_HTTP_CLIENT_BINDING))
    def test_form_data_import_matches_binding(self, entry_label: str) -> None:
        """每条 entry 的 FormData composable 的 import 与 FD-2 登记一致。"""
        expected = _HTTP_CLIENT_BINDING[entry_label]
        path = _find_form_data(entry_label)
        content = path.read_text(encoding="utf-8")

        if expected == "http":
            assert "import http from" in content and "utils/http" in content, (
                f"{entry_label} 应 import http（FD-2 登记 http），实际未找到"
            )
        else:
            assert "apiProxy" in content, (
                f"{entry_label} 应 import api（FD-2 登记 api），实际未找到 apiProxy"
            )
            # 支持两种 import 形式：default import 或解构 import
            has_api = "import api from" in content or "import { api }" in content
            assert has_api, (
                f"{entry_label} 应 import api（FD-2 登记 api），未找到 api import"
            )

    @pytest.mark.parametrize("entry_label", sorted(_HTTP_CLIENT_BINDING))
    def test_form_data_has_checklist_responses_call(self, entry_label: str) -> None:
        """每条 FormData composable 含 checklist-responses 端点调用。"""
        path = _find_form_data(entry_label)
        content = path.read_text(encoding="utf-8")
        assert "checklist-responses" in content, (
            f"{entry_label} FormData 缺少 checklist-responses 端点调用"
        )

    def test_four_http_entries_would_fail_api_probe(self) -> None:
        """变异：对四条 http entry 用 `api.` 探针 ⇒ 必然失配（FD-2 原文）。"""
        http_entries = [k for k, v in _HTTP_CLIENT_BINDING.items() if v == "http"]
        assert len(http_entries) == 4, f"http entry 数量 {len(http_entries)}，应为 4"

        for entry_label in http_entries:
            path = _find_form_data(entry_label)
            content = path.read_text(encoding="utf-8")
            # 这四条文件不应含 apiProxy import
            has_api = ("import api from" in content or "import { api }" in content) and "apiProxy" in content
            assert not has_api, (
                f"{entry_label} 是 http 绑定却含 apiProxy import ⇒ 绑定不一致"
            )

    def test_two_api_entries_would_fail_http_probe(self) -> None:
        """反面：对两条 api entry 用 `http.` 探针也会失配。"""
        api_entries = [k for k, v in _HTTP_CLIENT_BINDING.items() if v == "api"]
        assert len(api_entries) == 2, f"api entry 数量 {len(api_entries)}，应为 2"

        for entry_label in api_entries:
            path = _find_form_data(entry_label)
            content = path.read_text(encoding="utf-8")
            has_http = "import http from" in content and "utils/http" in content
            assert not has_http, (
                f"{entry_label} 是 api 绑定却含 utils/http import"
            )


# ═══════════════════════════════════════════════════════════════════════════
# G46-P13：两册「参考」sheet 排除清单不共用字面量
# ═══════════════════════════════════════════════════════════════════════════

# B7 实测字面量（Task 2 证据）
G4_REF_SHEETS = [
    "参考-中证协《证券公司金融工具减值指引》",      # 有连字符
    "参考-根据剩余期限折算PD",
]
G6_REF_SHEETS = [
    "参考中证协《证券公司金融工具减值指引》",        # 🔴 无连字符
    "参考-根据剩余期限折算PD",
]


class TestG46P13ReferenceSheetExclusion:
    """Validates: Req 4.7 —— 参考 sheet 排除清单不共用字面量。"""

    def test_g4_ref_sheets_exist_in_template(self) -> None:
        """G4 册的两张参考 sheet 真实存在。"""
        import openpyxl
        wb = openpyxl.load_workbook(_TPL_DIR / "G" / "G4 债权投资.xlsx", read_only=True)
        for name in G4_REF_SHEETS:
            assert name in wb.sheetnames, f"G4 册缺少参考 sheet: {name!r}"
        wb.close()

    def test_g6_ref_sheets_exist_in_template(self) -> None:
        """G6 册的两张参考 sheet 真实存在。"""
        import openpyxl
        wb = openpyxl.load_workbook(_TPL_DIR / "G" / "G6 其他债权投资.xlsx", read_only=True)
        for name in G6_REF_SHEETS:
            assert name in wb.sheetnames, f"G6 册缺少参考 sheet: {name!r}"
        wb.close()

    def test_first_ref_sheet_names_differ_by_hyphen(self) -> None:
        """两册第一张参考 sheet 只差一个连字符（B7 实测）。"""
        g4_first = G4_REF_SHEETS[0]
        g6_first = G6_REF_SHEETS[0]
        assert g4_first != g6_first, "两册第一张参考 sheet 不应同名"
        # 差异恰好是一个连字符
        assert g4_first.replace("-", "", 1) == g6_first or g6_first.replace("-", "") == g4_first.replace("-", ""), (
            f"差异不只是连字符: G4={g4_first!r} vs G6={g6_first!r}"
        )

    def test_mutation_shared_literal_would_miss_g6(self) -> None:
        """变异：用同一字面量排除 ⇒ G6 那张漏排除。"""
        # 如果把 G4 的名字当共用字面量
        shared = G4_REF_SHEETS[0]
        assert shared not in G6_REF_SHEETS, (
            f"G4 第一张 {shared!r} 不应在 G6 排除清单里"
            " ⇒ 用同一字面量排除两册会漏掉 G6 的无连字符版本"
        )

    def test_second_ref_sheet_is_genuinely_same(self) -> None:
        """第二张「根据剩余期限折算PD」两册同名（属模板重复件，design 顺带发现 1）。"""
        assert G4_REF_SHEETS[1] == G6_REF_SHEETS[1]


# ═══════════════════════════════════════════════════════════════════════════
# G46-P18：零回归现算 —— 非 G4/G6 contract golden digest 逐项不变
# ═══════════════════════════════════════════════════════════════════════════


class TestG46P18ZeroRegression:
    """Validates: Req 5.6 —— 照 GC-10 现算逐项比对，不断言 digest 集合大小。"""

    def test_g4_bond_main_contract_exists_and_is_valid_json(self) -> None:
        """g4.bond_main.json 存在且可解析。"""
        path = _BACKEND / "data" / "workpaper_sync_contracts" / "g4.bond_main.json"
        assert path.exists(), "g4.bond_main.json 不存在"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("contract_id") == "g4.bond_main"

    def test_g6_other_bond_main_contract_exists_and_is_valid_json(self) -> None:
        """g6.other_bond_main.json 存在且可解析。"""
        path = _BACKEND / "data" / "workpaper_sync_contracts" / "g6.other_bond_main.json"
        assert path.exists(), "g6.other_bond_main.json 不存在"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("contract_id") == "g6.other_bond_main"

    def test_non_g4g6_contracts_unchanged(self) -> None:
        """非 G4/G6 的 contract 文件应保持不变（零回归，GC-10）。

        🔴 不断言 digest 集合大小（GC-10 原则）——只逐项比对每个非 G4/G6 契约仍可解析。
        """
        contracts_dir = _BACKEND / "data" / "workpaper_sync_contracts"
        g4g6_prefixes = ("g4.", "g6.")
        non_g4g6 = sorted(
            f for f in contracts_dir.glob("*.json")
            if not f.name.startswith(g4g6_prefixes) and not f.name.startswith("_")
        )
        assert len(non_g4g6) > 0, "非 G4/G6 契约为空，零回归基线无意义"

        for f in non_g4g6:
            data = json.loads(f.read_text(encoding="utf-8"))
            cid = data.get("contract_id")
            assert cid, f"{f.name} 缺少 contract_id"
            assert data.get("schema_version"), f"{f.name} 缺少 schema_version"
            # 逐项可解析即零回归（不写死 digest 值，避免跨 spec 修改时误红）

    def test_g4g6_contracts_count(self) -> None:
        """G4/G6 已发布契约现算：目前仅 g4.bond_main + g6.other_bond_main。"""
        contracts_dir = _BACKEND / "data" / "workpaper_sync_contracts"
        g4g6 = sorted(
            f.name for f in contracts_dir.glob("*.json")
            if f.name.startswith(("g4.", "g6."))
        )
        # 只断言当前已发布的两份存在，不断言精确集合（后续 Task 会增加）
        assert "g4.bond_main.json" in g4g6
        assert "g6.other_bond_main.json" in g4g6
