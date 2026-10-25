"""test_adj_preset_type_guard.py — ADJ() 预设第二参白名单 CI 守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 1 任务 1.6
需求 7.6 · 属性 P3, P12

扫描 prefill_formula_mapping.json 中所有 ADJ() 公式，断言第二参可被
normalize_adj_type 归一（在白名单内）。新增预设若第二参不合法 → CI 失败。

双向变异：故意注入非法字面量应红、现有合法预设应绿。

🔴 复盘重组：本文件曾与 test_adj_formula_resolution.py 内的
`TestAdjPresetSecondParamCIGuard` 重复，那版多「白名单与归一表同源」一致性断言。
现取强版收敛到本文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_PREFILL_FILE = _DATA_DIR / "prefill_formula_mapping.json"
_ADJ_RE = re.compile(r"=ADJ\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)", re.IGNORECASE)


class TestAdjPresetTypeGuard:
    """CI 守卫：ADJ() 预设第二参必在归一白名单内。"""

    # 类级常量（搬移自原内联类，勿改为模块级——成员方法用 self._BACKEND 访问）
    _BACKEND = Path(__file__).resolve().parent.parent
    _MAPPING_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
    _ADJ_RE = re.compile(r"=?ADJ\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")

    @staticmethod
    def _extract_adj_params(mapping_path: Path) -> list[dict[str, str]]:
        """从 prefill_formula_mapping.json 提取所有 ADJ() 第二参。

        Returns:
            每条命中的 {"wp_code", "sheet", "coordinate", "formula", "param2"}。
        """
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
        adj_re = re.compile(r"=?ADJ\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")
        hits: list[dict[str, str]] = []
        for mapping in data.get("mappings", []):
            wp_code = mapping.get("wp_code", "?")
            sheet = mapping.get("sheet") or mapping.get("sheet_name") or "?"
            for cell in mapping.get("cells", []):
                formula = cell.get("formula") or ""
                for m in adj_re.finditer(formula):
                    hits.append({
                        "wp_code": wp_code,
                        "sheet": sheet,
                        "coordinate": cell.get("coordinate") or "?",
                        "formula": formula,
                        "param2": m.group(2),
                    })
        return hits

    def test_ci_guard_all_adj_second_params_in_whitelist(self):
        """P3 + 需求 7.6：所有 ADJ() 第二参必须可被 normalize_adj_type 归一。

        白名单来自 adjustment_amount_source.VALID_ADJ_TYPE_LITERALS（单一来源，
        不在测试里重复维护）。不可归一 → CI 失败。
        """
        from app.services.adjustment_amount_source import VALID_ADJ_TYPE_LITERALS

        assert self._MAPPING_PATH.exists(), (
            f"prefill_formula_mapping.json 不存在: {self._MAPPING_PATH}"
        )
        hits = self._extract_adj_params(self._MAPPING_PATH)

        # 现算 ADJ() 出现次数（禁写死）
        assert len(hits) > 0, (
            "prefill_formula_mapping.json 中未发现任何 ADJ() 公式，"
            "数据可能被清空或正则失配"
        )

        # 逐条校验
        whitelist_lower = {v.lower() for v in VALID_ADJ_TYPE_LITERALS}
        violations = []
        for h in hits:
            if h["param2"].strip().lower() not in whitelist_lower:
                violations.append(
                    f"  {h['wp_code']} {h['sheet']} {h['coordinate']}: "
                    f"'{h['param2']}' not in whitelist"
                )

        assert not violations, (
            f"[CI GUARD FAIL] {len(violations)} 处 ADJ() 第二参不在归一白名单内:\n"
            + "\n".join(violations)
            + f"\n合法值: {sorted(VALID_ADJ_TYPE_LITERALS)}"
        )

    def test_ci_guard_mutation_proof_bad_literal_detected(self):
        """P12 双向变异（正样本）：注入非法字面量 → 守卫必须检出。

        临时构造一份含非法第二参的 JSON，走同样的校验逻辑，
        断言校验能抓到——证明守卫不是恒绿。
        """
        import tempfile

        from app.services.adjustment_amount_source import VALID_ADJ_TYPE_LITERALS

        # 读真实数据，注入一个非法 ADJ() 预设
        data = json.loads(self._MAPPING_PATH.read_text(encoding="utf-8"))
        injected_cell = {
            "coordinate": "Z99",
            "cell_ref": "MUTATION_PROBE",
            "formula": "=ADJ('9999','BOGUS_TYPE')",
        }
        # 往第一个 mapping 的 cells 末尾注入
        data["mappings"][0]["cells"].append(injected_cell)

        # 写到临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False,
        ) as f:
            json.dump(data, f, ensure_ascii=False)
            tmp_path = Path(f.name)

        try:
            hits = self._extract_adj_params(tmp_path)
            whitelist_lower = {v.lower() for v in VALID_ADJ_TYPE_LITERALS}
            violations = [
                h for h in hits
                if h["param2"].strip().lower() not in whitelist_lower
            ]

            # 必须检出至少 1 条（我们注入的 BOGUS_TYPE）
            assert len(violations) >= 1, (
                "变异证明失败：注入了非法 ADJ('9999','BOGUS_TYPE') 但守卫未检出，"
                "说明校验逻辑恒绿"
            )

            # 进一步验证检出的正是我们注入的那条
            bogus_hits = [v for v in violations if v["param2"] == "BOGUS_TYPE"]
            assert len(bogus_hits) == 1, (
                f"注入的 BOGUS_TYPE 应恰好被检出 1 次，实际 {len(bogus_hits)} 次"
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_ci_guard_mutation_proof_current_data_passes(self):
        """P12 双向变异（负样本）：当前真实数据 → 守卫必须通过。

        与 test_ci_guard_mutation_proof_bad_literal_detected 互为正/反样本。
        证明守卫不是恒红。
        """
        from app.services.adjustment_amount_source import VALID_ADJ_TYPE_LITERALS

        hits = self._extract_adj_params(self._MAPPING_PATH)
        assert len(hits) > 0, "无 ADJ() 命中，数据可能被清空"

        whitelist_lower = {v.lower() for v in VALID_ADJ_TYPE_LITERALS}
        violations = [
            h for h in hits
            if h["param2"].strip().lower() not in whitelist_lower
        ]
        assert len(violations) == 0, (
            f"当前数据应全部合法（变异负样本），但发现 {len(violations)} 处违规"
        )

    def test_ci_guard_whitelist_matches_fix_script(self):
        """P3 一致性：测试用的白名单来自 adjustment_amount_source，
        fix 脚本的白名单也应与之一致（两处不同步 → 脚本修了但 CI 不认，或反过来）。

        fix_adj_preset_type_literals.py 自含的 _VALID_LITERALS 必须
        == VALID_ADJ_TYPE_LITERALS（此断言在 normalize_adj_type 守卫中已有，
        这里额外验证 fix 脚本侧，锁死两端口径）。
        """
        from app.services.adjustment_amount_source import VALID_ADJ_TYPE_LITERALS

        # 直接读 fix 脚本的 _VALID_LITERALS（它是模块级常量）
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fix_adj_preset_type_literals",
            self._BACKEND / "scripts" / "fix" / "fix_adj_preset_type_literals.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # fix 脚本的白名单应是 VALID_ADJ_TYPE_LITERALS 的超集或等集（大小写不敏感比较）
        fix_whitelist = {v.lower() for v in mod._VALID_LITERALS}
        source_whitelist = {v.lower() for v in VALID_ADJ_TYPE_LITERALS}
        assert fix_whitelist == source_whitelist, (
            f"fix 脚本 _VALID_LITERALS {fix_whitelist} != "
            f"adjustment_amount_source.VALID_ADJ_TYPE_LITERALS {source_whitelist}；"
            "两端白名单必须同步"
        )
