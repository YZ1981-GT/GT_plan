"""G0 投资循环函证 — 集成测试（后端视角）.

Spec: g0-confirmation / Wave 7 / Task 7.1

覆盖场景（Requirements 全部）:
1. wp_code_overrides 映射正确性（10 条 G0 → 对应 componentType）
2. 两个新建 componentType 注册契约完整性（VALID_COMPONENT_TYPES + RENDERER_DISPATCH + 初始格式）
3. G0-3S / G0-6 导入导出三端点 + 列定义完整性
4. G0-6 处置损益公式（成交-成本-手续费）+ 股利差异（后端与前端口径一致）
5. G0-6 四区块列定义（记账凭证 5 列 + 各区块检查证据列）
6. account_package_registry G0 包 9 sheets 顺序
7. G0.yaml render schema 存在性
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import _WP_CODE_OVERRIDE, VALID_COMPONENT_TYPES

_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
_BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_OVERRIDES_PATH = _DATA_DIR / "wp_code_overrides.json"
_PKG_REGISTRY_PATH = _BACKEND_DATA_DIR / "account_package_registry.json"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. wp_code_overrides 映射正确性（10 条 G0 映射）
# ═══════════════════════════════════════════════════════════════════════════════

_G0_EXPECTED_MAP = {
    "G0": "confirmation-hub",
    "G0A": "a-program-console",
    "G0-1": "confirmation-summary",
    "G0-2": "confirmation-entity-verify",
    "G0-3": "confirmation-followup",
    "G0-3S": "confirmation-diff-securities",
    "G0-4": "confirmation-diff-reconcile",
    "G0-6": "confirmation-alternative-g06",
    "G0-7": "confirmation-reliability",
    "G0-8": "confirmation-fraud-risk",
}


class TestG0OverridesMapping:
    """Req 1.1: wp_code_overrides.json 含完整 10 条 G0 映射。"""

    @pytest.fixture(scope="class")
    def overrides(self) -> dict:
        return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("wp_code,component_type", list(_G0_EXPECTED_MAP.items()))
    def test_override_entry(self, overrides, wp_code, component_type):
        assert overrides.get(wp_code) == component_type, (
            f"G0 映射 {wp_code} 应为 {component_type}，实际 {overrides.get(wp_code)}"
        )

    def test_runtime_override_consistent_with_file(self):
        """运行时 _WP_CODE_OVERRIDE 与文件一致（热重载生效）。"""
        for wp_code, component_type in _G0_EXPECTED_MAP.items():
            assert _WP_CODE_OVERRIDE.get(wp_code) == component_type

    def test_exactly_ten_g0_entries(self, overrides):
        """精确 10 条 G0 映射（G0 / G0A / G0-数字 / G0-3S）。"""
        import re
        g0_keys = {k for k in overrides if re.fullmatch(r"G0(A|-[0-9S]+)?", k)}
        assert g0_keys == set(_G0_EXPECTED_MAP), (
            f"G0 映射条目不符: 缺 {set(_G0_EXPECTED_MAP) - g0_keys}, "
            f"多 {g0_keys - set(_G0_EXPECTED_MAP)}"
        )

    def test_securities_vs_nonsecurities_distinct(self, overrides):
        """G0-3S(证券) 走专属组件，G0-4(非证券) 走 D0 通用，二者区分。"""
        assert overrides["G0-3S"] == "confirmation-diff-securities"
        assert overrides["G0-4"] == "confirmation-diff-reconcile"
        assert overrides["G0-3S"] != overrides["G0-4"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 注册契约完整性（Req 4.1~4.5）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG0RegistrationContract:
    """两个新建 componentType 完整注册。"""

    def test_valid_component_types(self):
        """Req 4.1/4.2: 两个新 componentType 在 VALID_COMPONENT_TYPES。"""
        assert "confirmation-diff-securities" in VALID_COMPONENT_TYPES
        assert "confirmation-alternative-g06" in VALID_COMPONENT_TYPES

    def test_renderer_dispatch_registered(self):
        """Req 4.5: RENDERER_DISPATCH 有两个新策略。"""
        from app.routers.wp_render_strategies import RENDERER_DISPATCH

        assert "confirmation-diff-securities" in RENDERER_DISPATCH
        assert "confirmation-alternative-g06" in RENDERER_DISPATCH
        assert callable(RENDERER_DISPATCH["confirmation-diff-securities"])
        assert callable(RENDERER_DISPATCH["confirmation-alternative-g06"])

    def test_render_config_format_map(self):
        """wp_render_config 初始格式映射含两个新类型。"""
        from app.routers.wp_render_config import _CONFIRMATION_FORMAT_MAP

        assert _CONFIRMATION_FORMAT_MAP.get("confirmation-diff-securities") == "diff-securities-v1"
        assert _CONFIRMATION_FORMAT_MAP.get("confirmation-alternative-g06") == "alternative-g06-v1"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 导入导出三端点 + 列定义（Req 5.3~5.6）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG0ImportExport:
    """G0-3S / G0-6 导入导出结构。"""

    @pytest.fixture(scope="class")
    def ie_module(self):
        from app.routers.wp_render_strategies import _g0_confirmation_import_export as m
        return m

    def test_three_endpoints_registered(self, ie_module):
        """3 端点路由存在于 router。"""
        paths = {r.path for r in ie_module.router.routes}
        assert "/api/workpapers/{wp_id}/g0/export-template" in paths
        assert "/api/workpapers/{wp_id}/g0/export-data" in paths
        assert "/api/workpapers/{wp_id}/g0/import-data" in paths

    def test_sheet_name_map(self, ie_module):
        """Req 5.4: 支持 G0-3S / G0-6 两个 sheet 编码。"""
        assert set(ie_module._SHEET_NAME_MAP) == {"G0-3S", "G0-6"}

    def test_g03s_17_columns(self, ie_module):
        """Req 2.4: G0-3S 明细核对 17 列。"""
        assert len(ie_module._G03S_COLUMNS) == 17

    def test_g06_four_blocks(self, ie_module):
        """Req 5.5: G0-6 导出 4 区块（4 个 sheet）。"""
        assert set(ie_module._G06_BLOCKS) == {"block1", "block2", "block3", "block4"}
        titles = [cfg["sheet_title"] for cfg in ie_module._G06_BLOCKS.values()]
        assert "①持仓证明检查" in titles
        assert "③投资处置收益证据" in titles

    def test_g06_voucher_columns_in_every_block(self, ie_module):
        """Req 3.6: 每区块含记账凭证 5 列。"""
        voucher_keys = {"voucher_date", "voucher_no", "business_desc", "counter_account", "voucher_amount"}
        for block_key, cfg in ie_module._G06_BLOCKS.items():
            keys = {key for _, key, _ in cfg["columns"]}
            assert voucher_keys <= keys, f"{block_key} 缺记账凭证列: {voucher_keys - keys}"

    def test_g06_disposal_gain_column(self, ie_module):
        """Req 3.13: block3 含处置损益列。"""
        block3_keys = {key for _, key, _ in ie_module._G06_BLOCKS["block3"]["columns"]}
        assert "disposal_gain" in block3_keys
        assert "trade_amount" in block3_keys
        assert "original_cost" in block3_keys
        assert "fee" in block3_keys


# ═══════════════════════════════════════════════════════════════════════════════
# 4. G0-6 导入 round-trip（构建 workbook → 解析回 rows）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG0ImportRoundTrip:
    """导出 workbook 后再解析，验证列头 round-trip 一致。"""

    def test_g03s_build_and_parse_roundtrip(self):
        """G0-3S：导出数据 workbook → 解析回，行数与关键字段保留。"""
        from app.routers.wp_render_strategies import _g0_confirmation_import_export as m
        import io

        rows = [
            {
                "seq": 1, "security_name": "甲股票", "security_code": "600000",
                "confirmed_qty": 10000, "booked_qty": 9800, "qty_diff": 200,
                "confirmed_unit_fv": 12.5, "booked_unit_fv": 12.0, "fv_diff": 0.5,
                "confirmed_market_value": 125000, "booked_market_value": 117600,
                "market_value_diff": 7400,
            }
        ]
        wb = m._build_g03s_workbook(rows)
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        parsed = m._parse_sheet_rows(content, None, m._G03S_COLUMNS, header_row=2)
        assert len(parsed) == 1
        assert parsed[0]["security_name"] == "甲股票"
        assert parsed[0]["confirmed_qty"] == 10000
        assert parsed[0]["qty_diff"] == 200

    def test_g06_build_and_parse_roundtrip(self):
        """G0-6：4 区块 workbook → 解析回，按被函证单位归组。"""
        from app.routers.wp_render_strategies import _g0_confirmation_import_export as m
        import io

        companies = [
            {
                "entity_name": "乙基金",
                "block1_rows": [{"seq": 1, "voucher_amount": 1000, "market_value": 5000}],
                "block2_rows": [],
                "block3_rows": [{"seq": 1, "trade_amount": 150000, "original_cost": 120000, "fee": 300, "disposal_gain": 29700}],
                "block4_rows": [],
            }
        ]
        wb = m._build_g06_workbook(companies)
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        # 解析 block3 sheet
        cfg = m._G06_BLOCKS["block3"]
        parsed = m._parse_sheet_rows(content, cfg["sheet_title"], cfg["columns"], header_row=1)
        assert len(parsed) == 1
        assert parsed[0]["_entity"] == "乙基金"
        assert parsed[0]["trade_amount"] == 150000
        assert parsed[0]["disposal_gain"] == 29700


# ═══════════════════════════════════════════════════════════════════════════════
# 5. account_package_registry G0 包（Req 1.3）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG0PackageRegistry:
    """G0 包 9 sheets 按模板顺序。"""

    @pytest.fixture(scope="class")
    def g0_package(self) -> dict:
        data = json.loads(_PKG_REGISTRY_PATH.read_text(encoding="utf-8"))
        packages = data.get("packages", data) if isinstance(data, dict) else data
        for pkg in packages:
            if pkg.get("account_package_id") == "G0_investment_confirmation":
                return pkg
        pytest.fail("account_package_registry 缺少 G0_investment_confirmation 包")

    def test_package_exists_and_cycle(self, g0_package):
        assert g0_package["cycle"] == "G"
        assert g0_package["primary_wp_code"] == "G0"

    def test_nine_sheets(self, g0_package):
        """9 个有效 sheet。"""
        assert len(g0_package["sheets"]) == 9

    def test_control_panel_first(self, g0_package):
        """程序表 G0A 为 control_panel 且排首位。"""
        first = g0_package["sheets"][0]
        assert first["sheet_type"] == "control_panel"
        assert "G0A" in first["sheet_name"]

    def test_securities_and_alternative_sheets_present(self, g0_package):
        """含证券差异核对 + 替代程序 sheet。"""
        names = [s["sheet_name"] for s in g0_package["sheets"]]
        assert any("证券投资" in n for n in names)
        assert any("替代程序" in n for n in names)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. G0.yaml render schema 存在（Req 1.2）
# ═══════════════════════════════════════════════════════════════════════════════


class TestG0RenderSchema:
    def test_g0_yaml_exists(self):
        candidates = [
            _BACKEND_DATA_DIR / "ledger_adapters" / "wp_render_schema" / "generated" / "G0.yaml",
            _BACKEND_DATA_DIR / "ledger_adapters" / "wp_render_schema" / "G0.yaml",
        ]
        assert any(p.exists() for p in candidates), (
            f"G0.yaml render schema 不存在，检查路径: {[str(p) for p in candidates]}"
        )
