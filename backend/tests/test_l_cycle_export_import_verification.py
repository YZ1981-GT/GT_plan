"""L 类底稿（筹资循环）导入导出完整验证测试。

覆盖:
  P0-P6 综合验证：
  36. L 类 d-form-table 底稿导出为 Excel
  37. L 类 audit-sheet 底稿原生导出
  38. 从 Excel 导入填充 L 类底稿
  39. 批量导出 L 类全量打包 zip
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app.services.wp_classification_service import _WP_CODE_OVERRIDE, VALID_COMPONENT_TYPES

from tests.l_cycle_extraction._l_component_registry import (
    DECLARED_AUDIT_SHEET_CODES,
    DECLARED_FORM_TABLE_CODES,
    DEDICATED_TYPE_RE,
    L0_SHARED_CONFIRMATION_NOTE,
    PRE_MIGRATION_GENERIC_TYPES,
    cycle_of,
    dedicated_owners_by_cycle,
    evaluate_dedicated_ownership,
    evaluate_host_references_code,
    evaluate_no_pre_migration_type,
    load_renderer_registry,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MAPPING_PATH = _DATA_DIR / "wp_account_mapping.json"
_TEMPLATES_PATH = _DATA_DIR / "procedure_table_templates.json"
_ADDR_REGISTRY_PATH = _DATA_DIR / "l_address_registry_seed.json"
_SCHEMA_DIR = _DATA_DIR / "ledger_adapters" / "wp_render_schema"


@pytest.fixture(scope="module")
def wp_mapping() -> list[dict]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def l_class_entries(wp_mapping) -> list[dict]:
    return [e for e in wp_mapping if e.get("cycle") == "L"]


@pytest.fixture(scope="module")
def procedure_templates() -> dict:
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Templates can be in data["tables"] or at root level (newer cycles)
    tables = data.get("tables", {}) if isinstance(data, dict) else {}
    # Merge root-level entries that look like procedure tables (e.g. G0A, H1A, L0A)
    if isinstance(data, dict):
        for key, val in data.items():
            if key not in ("version", "description", "tables") and isinstance(val, dict) and "items" in val:
                tables[key] = val
    return tables


@pytest.fixture(scope="module")
def addr_registry() -> dict:
    with open(_ADDR_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# P0: 注册完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestP0Registration:
    """P0: wp_account_mapping + _WP_CODE_OVERRIDE 完整性。"""

    _ALL_L_SUBCODES = [
        # L0 函证
        "L0-1", "L0-2", "L0-3", "L0-4", "L0-5",
        # L1 短期借款
        "L1-1", "L1-2", "L1-3", "L1-4", "L1-5", "L1-6",
        # L2 应付利息
        "L2-1", "L2-2", "L2-3", "L2-4",
        # L3 长期借款
        "L3-1", "L3-2", "L3-3", "L3-4", "L3-5", "L3-6",
        # L4 应付债券
        "L4-1", "L4-2", "L4-3", "L4-4", "L4-5", "L4-6", "L4-7", "L4-8",
        # L5 长期应付款
        "L5-1", "L5-2", "L5-3", "L5-4",
        # L6 专项应付款
        "L6-1", "L6-2", "L6-3", "L6-4",
        # L7 其他非流动负债
        "L7-1", "L7-2", "L7-3", "L7-4",
        # L8 财务费用
        "L8-1", "L8-2", "L8-3", "L8-4", "L8-5", "L8-6",
    ]

    _PARENT_CODES = ["L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"]

    _PROGRAM_CODES = ["L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A"]

    def test_l_class_count(self, l_class_entries):
        """wp_account_mapping.json 中应有 ≥50 个 cycle='L' 的条目。"""
        assert len(l_class_entries) >= 50, (
            f"L 类底稿应有 ≥50 条注册，实际 {len(l_class_entries)} 条"
        )

    def test_all_l_subcodes_have_override(self):
        """所有 L 类子码在 _WP_CODE_OVERRIDE 中有 componentType 映射。"""
        for code in self._ALL_L_SUBCODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类 wp_code '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_parent_codes_have_override(self):
        """所有 L 类父码在 _WP_CODE_OVERRIDE 中有映射。"""
        for code in self._PARENT_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类父码 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )

    def test_all_program_codes_have_override(self):
        """所有 L 类程序表在 _WP_CODE_OVERRIDE 中有映射。

        🔴 原断言 `== "a-program-console"` 恒红：L1A~L8A 已随各自循环迁到专属组件
        （程序表是该 wp 的一张 sheet，由宿主内部分发），只有 L0A 仍用通用程序台
        —— L0 没有专属宿主可承载程序表（见 L0_SHARED_CONFIRMATION_NOTE）。
        故判据改为「注册 + 归属本循环」，L0A 的通用类型作为登记在案的例外。
        """
        for code in self._PROGRAM_CODES:
            assert code in _WP_CODE_OVERRIDE, (
                f"L 类程序表 '{code}' 未在 _WP_CODE_OVERRIDE 中注册"
            )
        assert _WP_CODE_OVERRIDE["L0A"] == "a-program-console", (
            "L0A 应保持通用程序台：" + L0_SHARED_CONFIRMATION_NOTE
        )
        for code in self._PROGRAM_CODES:
            if code == "L0A":
                continue
            ct = _WP_CODE_OVERRIDE[code]
            m = DEDICATED_TYPE_RE.match(ct)
            assert m and m.group(1) == cycle_of(code)[1:], (
                f"程序表 {code} 的 componentType {ct!r} 未归属本循环的专属组件"
            )

    def test_all_component_types_valid(self):
        """所有 L 类子码 componentType 必须是合法类型。"""
        for code in self._ALL_L_SUBCODES + self._PARENT_CODES + self._PROGRAM_CODES:
            ct = _WP_CODE_OVERRIDE.get(code, "")
            assert ct in VALID_COMPONENT_TYPES, (
                f"L 类 '{code}' componentType '{ct}' 不合法"
            )

    def test_l0_confirmation_hub(self):
        """L0 映射为 confirmation-hub。"""
        assert _WP_CODE_OVERRIDE.get("L0") == "confirmation-hub"

    def test_type_distribution(self):
        """L 类 componentType 分布符合预期。

        🔴 原断言是三条通用类型的地板线（c-note-table ≥8 / d-form-table ≥20 /
        audit-sheet ≥15），迁到专属组件后三者对 L1~L8 全部归零，恒红。
        地板线本身也是坏判据：数字来自当时的人工计数，改一个 override 就漂移。
        改成结构不变式 —— L1~L8 各恰好贡献 1 个专属组件，且计数之和覆盖全部 L 码。
        """
        owners = dedicated_owners_by_cycle(_WP_CODE_OVERRIDE)
        assert set(owners) == {f"L{i}" for i in range(9)}, (
            f"L 循环缺失或多出：{sorted(owners)}"
        )
        dedicated = {c: next(iter(t)) for c, t in owners.items() if c != "L0"}
        assert len(set(dedicated.values())) == 8, (
            f"L1~L8 应各有一个互不相同的专属组件，实际 {sorted(set(dedicated.values()))}"
        )
        # L0 只用共享函证组件 + 通用程序台，不得出现专属 l{n}- 类型
        l0_types = owners["L0"]
        assert not any(DEDICATED_TYPE_RE.match(t) for t in l0_types), (
            f"L0 出现专属组件 {sorted(l0_types)} —— " + L0_SHARED_CONFIRMATION_NOTE
        )

    def test_dedicated_ownership_is_unique_per_cycle(self):
        """判据 1+2：每个 L{n} 归属唯一的专属组件，且组件名编码本循环号。

        可抓出 `== "d-form-table"` 那种写法永远抓不到的接线错误：
        某个 L4-x 误指向 `l3-long-term-loans`。
        """
        problems = evaluate_dedicated_ownership(_WP_CODE_OVERRIDE)
        assert not problems, "专属组件归属违规：\n  " + "\n  ".join(problems)

    def test_no_pre_migration_generic_type_resurrects(self):
        """判据 5（反向）：迁移前的通用类型不得对 L1~L8 复活。

        原判据的本意是防回退，这条把它保住 —— 不再要求「等于某个通用值」，
        而是要求「不得退回通用值」。
        """
        problems = evaluate_no_pre_migration_type(_WP_CODE_OVERRIDE)
        assert not problems, (
            f"L1~L8 出现迁移前的通用 componentType（{sorted(PRE_MIGRATION_GENERIC_TYPES)}）：\n  "
            + "\n  ".join(problems)
        )

    @pytest.mark.parametrize("wp_code", ["L1-1", "L2-1", "L3-1", "L4-1",
                                          "L5-1", "L6-1", "L7-1", "L8-1"])
    def test_audit_determination_tables_owned_by_cycle_component(self, wp_code):
        """L{n}-1 审定表由本循环专属组件承载。

        🔴 原断言 `== "d-form-table"` 恒红。审定表/检查表这个**角色**区分迁移后
        在 override 层已不可表达（一个 wp 的所有 sheet 同一个专属组件），落点是
        宿主内部按 wp_code/sheet 分发，见
        `derive_component_type(ignore_wp_code_override=True)` 的注释。
        故这里断言归属，角色级断言应写在宿主组件的前端测试里。
        """
        ct = _WP_CODE_OVERRIDE.get(wp_code)
        m = DEDICATED_TYPE_RE.match(str(ct))
        assert m and m.group(1) == cycle_of(wp_code)[1:], (
            f"审定表 {wp_code} 的 componentType {ct!r} 未归属本循环专属组件"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P1: 程序表模板
# ═══════════════════════════════════════════════════════════════════════════════


class TestP1ProcedureTables:
    """P1: 程序表模板注册验证。"""

    _EXPECTED_TABLES = [
        "L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A",
    ]

    def test_all_9_procedure_tables_registered(self, procedure_templates):
        """L0A~L8A 共 9 个程序表全部注册。"""
        for table_id in self._EXPECTED_TABLES:
            assert table_id in procedure_templates, (
                f"程序表 '{table_id}' 未注册到 procedure_table_templates.json"
            )

    @pytest.mark.parametrize("table_id", [
        "L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A",
    ])
    def test_procedure_table_has_items(self, procedure_templates, table_id):
        """每个程序表有 items 且步骤数 >= 5。"""
        table = procedure_templates[table_id]
        assert "items" in table, f"{table_id} 缺少 items"
        assert len(table["items"]) >= 5, (
            f"{table_id} 步骤数 {len(table['items'])} < 5"
        )

    def test_procedure_tables_have_risk_source(self, procedure_templates):
        """所有程序表 seq1 应引用 risk_for_cycle。"""
        for table_id in self._EXPECTED_TABLES:
            first_item = procedure_templates[table_id]["items"][0]
            assert first_item.get("auto_data_source") == "risk_for_cycle", (
                f"{table_id} seq1 未引用 risk_for_cycle 数据源"
            )

    def test_procedure_tables_last_step_has_control_test(self, procedure_templates):
        """所有程序表末步引用 control_test_result_for_cycle。"""
        for table_id in self._EXPECTED_TABLES:
            last_item = procedure_templates[table_id]["items"][-1]
            assert last_item.get("auto_data_source") == "control_test_result_for_cycle", (
                f"{table_id} 末步未引用 control_test_result_for_cycle 数据源"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# P2: 审定表 + 回写联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP2AuditDetermination:
    """P2: 审定表 schema + handler 正则。"""

    def test_handler_regex_covers_l_class(self):
        """handler 正则 ^[D-N]\\d+-1$ 匹配所有 L 审定表。"""
        pattern = re.compile(r"^[D-N]\d+-1$")
        for i in range(1, 9):
            code = f"L{i}-1"
            assert pattern.match(code), f"正则不匹配 {code}"

    def test_l4_1_schema_exists(self):
        """L4-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        assert schema_path.exists()

    def test_l8_1_schema_exists(self):
        """L8-1 特殊 YAML schema 文件存在。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        assert schema_path.exists()

    def test_l4_1_has_bond_fields(self):
        """L4-1 schema 包含债券品种字段（面值/票面利率/到期日/摊余成本）。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema.get("dynamic_rows") is True
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "face_value" in field_names
        assert "coupon_rate" in field_names
        assert "maturity_date" in field_names
        assert "audited_amount" in field_names

    def test_l8_1_is_income_statement_type(self):
        """L8-1 schema 标记为损益类。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema.get("income_statement_type") is True
        assert schema.get("amount_source") == "occurrence_amount"

    def test_l4_1_cross_ref_to_g4(self):
        """L4-1 有到 G4 的对称关联引用。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "G4-1" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# P3: address_registry 坐标
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3AddressRegistry:
    """P3: address_registry 坐标注册。"""

    def test_seed_file_exists(self):
        """l_address_registry_seed.json 存在。"""
        assert _ADDR_REGISTRY_PATH.exists()

    def test_seed_has_entries(self, addr_registry):
        """seed 有 entries 数组且 >= 6 条。"""
        assert "entries" in addr_registry
        assert len(addr_registry["entries"]) >= 6

    def test_seed_cycle_is_l(self, addr_registry):
        """seed cycle 标识为 L。"""
        assert addr_registry.get("cycle") == "L"

    def test_l1_3_coordinates(self, addr_registry):
        """L1-3 短期借款利息测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L1-3" in codes

    def test_l3_3_coordinates(self, addr_registry):
        """L3-3 长期借款利息测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L3-3" in codes

    def test_l4_3_coordinates(self, addr_registry):
        """L4-3 实际利率计算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L4-3" in codes

    def test_l4_4_coordinates(self, addr_registry):
        """L4-4 摊余成本摊销表坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L4-4" in codes

    def test_l8_3_coordinates(self, addr_registry):
        """L8-3 利息费用测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L8-3" in codes

    def test_l8_5_coordinates(self, addr_registry):
        """L8-5 汇兑损益测算坐标已注册。"""
        codes = {e["wp_code"] for e in addr_registry["entries"]}
        assert "L8-5" in codes


# ═══════════════════════════════════════════════════════════════════════════════
# P4: 特殊程序
# ═══════════════════════════════════════════════════════════════════════════════


class TestP4SpecialProcedures:
    """P4: 特殊程序 schema 确认。"""

    def test_l4_1_schema_parseable(self):
        """L4-1 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema["component_type"] == "d-form-table"

    def test_l3_4_schema_exists(self):
        """L3-4 一年内到期重分类 YAML schema 存在。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        assert schema_path.exists()

    def test_l3_4_schema_parseable(self):
        """L3-4 schema 可正确解析。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L3-4"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_l3_4_has_loan_fields(self):
        """L3-4 schema 含借款清单字段（银行/金额/利率/到期日/剩余期限）。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        row_fields = schema["row_template"]["fields"]
        field_names = [f["field"] for f in row_fields]
        assert "bank_name" in field_names
        assert "loan_amount" in field_names
        assert "interest_rate" in field_names
        assert "maturity_date" in field_names
        assert "remaining_term_days" in field_names
        assert "is_within_one_year" in field_names
        assert "reclassify_amount" in field_names

    # 🔴 这 5 处原为 `== "audit-sheet"` 的单点断言，迁到专属组件后恒红。
    # 改为「归属本循环专属组件 + 宿主源码真的引用该 wp_code」—— 后者是三向的
    # 第三边，能抓出「override 指向一个并不处理这张表的组件」，而旧写法只要
    # 字面量对得上就过，即便宿主文件根本不存在。
    @pytest.mark.parametrize(
        ("wp_code", "what"),
        [
            ("L4-3", "实际利率计算"),
            ("L4-4", "摊余成本摊销表"),
            ("L1-3", "短期借款利息测算"),
            ("L3-3", "长期借款利息测算"),
            ("L8-5", "汇兑损益测算"),
        ],
    )
    def test_special_procedure_owned_and_handled_by_host(self, wp_code, what):
        """特殊测算表由本循环专属组件承载，且宿主确实处理该 wp_code。"""
        ct = _WP_CODE_OVERRIDE.get(wp_code)
        m = DEDICATED_TYPE_RE.match(str(ct))
        assert m and m.group(1) == cycle_of(wp_code)[1:], (
            f"{wp_code}（{what}）的 componentType {ct!r} 未归属本循环专属组件"
        )
        problems = evaluate_host_references_code(_WP_CODE_OVERRIDE, [wp_code])
        assert not problems, f"{wp_code}（{what}）宿主判定失败：\n  " + "\n  ".join(problems)

    def test_l8_1_schema_has_sections(self):
        """L8-1 schema 有利息/汇兑/手续费等分类行。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        section_names = [s["name"] for s in schema["sections"]]
        assert "利息支出" in section_names
        assert "汇兑损益" in section_names
        assert "手续费" in section_names


# ═══════════════════════════════════════════════════════════════════════════════
# P5: 联动
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5Linkage:
    """P5: 联动绑定验证。"""

    def test_risk_for_cycle_in_procedure_tables(self, procedure_templates):
        """L{n}A 程序表引用 risk_for_cycle。"""
        tables_with_risk = []
        expected = ["L0A", "L1A", "L2A", "L3A", "L4A", "L5A", "L6A", "L7A", "L8A"]
        for key in expected:
            items = procedure_templates[key].get("items", [])
            for item in items:
                if item.get("auto_data_source") == "risk_for_cycle":
                    tables_with_risk.append(key)
                    break
        assert len(tables_with_risk) == 9

    def test_l0_confirmation_hub_route(self):
        """L0→ConfirmationHub 路由正确。"""
        assert _WP_CODE_OVERRIDE["L0"] == "confirmation-hub"

    def test_l4_1_g4_cross_ref(self):
        """L4-1 与 G4 有对称关联。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "G4-1" in targets

    def test_l8_1_interest_ref(self):
        """L8-1 引用 L8-3 利息测算。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "L8-3" in targets

    def test_l8_1_exchange_ref(self):
        """L8-1 引用 L8-5 汇兑损益。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        targets = [r["target_wp"] for r in schema["cross_refs"]]
        assert "L8-5" in targets


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6ExportImport:
    """P6: 导入导出基础设施验证。"""

    # 角色清单的真源下沉到判据层（`_l_component_registry`），此处只做别名，
    # 避免同一份领域数据在仓库里存两份副本。
    _L_FORM_TABLE_CODES = list(DECLARED_FORM_TABLE_CODES)
    _AUDIT_SHEET_CODES = list(DECLARED_AUDIT_SHEET_CODES)

    # 🔴 原两个参数化共 47 条断言写成 `== "d-form-table"` / `== "audit-sheet"`，
    # 迁到专属组件后全红。判据改为「注册 + 可渲染 + 宿主真的引用该 wp_code」，
    # 比旧写法强：旧写法即便 componentType 前端没注册、宿主 .vue 不存在、宿主
    # 根本不处理该子码，也照样通过。
    @pytest.mark.parametrize("wp_code", DECLARED_FORM_TABLE_CODES)
    def test_l_form_table_registered(self, wp_code):
        """检查表类子码：已注册，且其 componentType 可渲染、宿主处理该码。"""
        assert wp_code in _WP_CODE_OVERRIDE, f"{wp_code} 未注册"
        problems = evaluate_host_references_code(_WP_CODE_OVERRIDE, [wp_code])
        assert not problems, "\n  ".join(problems)

    @pytest.mark.parametrize("wp_code", DECLARED_AUDIT_SHEET_CODES)
    def test_l_audit_sheet_registered(self, wp_code):
        """审定/测算类子码：已注册，且其 componentType 可渲染、宿主处理该码。"""
        assert wp_code in _WP_CODE_OVERRIDE, f"{wp_code} 未注册"
        problems = evaluate_host_references_code(_WP_CODE_OVERRIDE, [wp_code])
        assert not problems, "\n  ".join(problems)

    def test_every_l_override_is_renderable(self):
        """全量判据（形态 A：违规清单为空）—— 不止清单里那 47 个子码。

        参数化只覆盖登记在册的子码；这条扫 override 里**全部** L 条目，
        能抓出「新增了一个 L 子码但忘了给它可渲染的 componentType」。
        """
        codes = [c for c in _WP_CODE_OVERRIDE if re.match(r"^L\d", str(c))]
        assert len(codes) >= 60, f"L override 只有 {len(codes)} 条，疑似加载不全"
        problems = evaluate_host_references_code(_WP_CODE_OVERRIDE, codes)
        assert not problems, f"{len(problems)} 处不可渲染：\n  " + "\n  ".join(problems)

    def test_renderer_registry_is_parseable(self):
        """反向自检：registry 解析出足量条目，防判据对着空 dict 空转。

        若正则失配，`load_renderer_registry()` 返回空 dict，则上面所有
        「宿主引用」判据都会退化成恒过 —— 这正是假绿第②源。
        """
        registry = load_renderer_registry()
        assert len(registry) >= 80, (
            f"htmlRendererRegistry 只解析出 {len(registry)} 条，疑似正则失配"
        )
        resolved = [e for e in registry.values() if e.host_exists]
        assert len(resolved) >= 80, (
            f"{len(registry) - len(resolved)} 条宿主 .vue 在磁盘上不存在"
        )

    def test_all_l_codes_in_mapping(self, l_class_entries):
        """所有 L 类 wp_code 在 wp_account_mapping 注册（批量导出可枚举）。"""
        mapping_codes = {e["wp_code"] for e in l_class_entries}
        all_codes = set(self._L_FORM_TABLE_CODES + self._AUDIT_SHEET_CODES)
        missing = all_codes - mapping_codes
        assert not missing, f"L 类缺少: {sorted(missing)}"

    def test_l_class_all_have_wp_code(self, l_class_entries):
        """所有 L 类条目有有效 wp_code。"""
        for entry in l_class_entries:
            assert entry.get("wp_code"), f"缺少 wp_code: {entry}"
            assert entry["wp_code"].startswith("L")

    def test_batch_export_type_distribution(self):
        """批量导出可枚举：全部 L 码都落在 8 个专属组件或 L0 共享函证族里。

        🔴 原断言与 TestP0.test_type_distribution 是同两条通用类型地板线的重复
        副本（d-form-table ≥20 / audit-sheet ≥15），迁移后同样恒红。改成覆盖式
        判据：不留「既不属专属组件也不属 L0 族」的孤儿码 —— 批量导出真正怕的是
        枚举漏掉某张表，而不是某个类型的计数够不够。
        """
        l_codes = {
            code: ct for code, ct in _WP_CODE_OVERRIDE.items()
            if re.match(r"^L\d", str(code))
        }
        orphans = {
            code: ct
            for code, ct in l_codes.items()
            if not DEDICATED_TYPE_RE.match(ct) and cycle_of(code) != "L0"
        }
        assert not orphans, (
            "以下 L 码既不由专属组件承载、也不属 L0 共享函证族，批量导出会漏："
            f"{orphans}"
        )
        covered = {c for c in l_codes if DEDICATED_TYPE_RE.match(l_codes[c])}
        l0 = {c for c in l_codes if cycle_of(c) == "L0"}
        assert covered | l0 == set(l_codes), "覆盖集与全集不等，判据本身有漏洞"

    def test_l4_1_yaml_schema_parseable_for_import(self):
        """L4-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "L4-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L4-1"
        assert schema["component_type"] == "d-form-table"
        assert schema.get("dynamic_rows") is True

    def test_l8_1_yaml_schema_parseable_for_import(self):
        """L8-1 审定表 YAML schema 可正确解析用于导入填充。"""
        schema_path = _SCHEMA_DIR / "L8-1.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L8-1"
        assert schema["component_type"] == "d-form-table"
        assert len(schema["sections"]) >= 5
        first_section = schema["sections"][0]
        assert "fields" in first_section
        field_names = [f["field"] for f in first_section["fields"]]
        assert "account_code" in field_names
        assert "audited_amount" in field_names

    def test_l3_4_yaml_schema_parseable_for_import(self):
        """L3-4 重分类 YAML schema 可正确解析用于导入。"""
        schema_path = _SCHEMA_DIR / "L3-4.yaml"
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        assert schema["wp_code"] == "L3-4"
        assert schema["component_type"] == "d-form-table"
