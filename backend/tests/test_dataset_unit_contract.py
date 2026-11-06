"""
数据集单位合同分类器 classify_dataset_unit 的全分支覆盖测试。

覆盖：None、空 dict、只有 amount_unit、有 unit_normalization 但无 contract、
有 unit_normalization 但 contract 无效（缺 digest / digest 格式错误）、
有完整有效 contract（normalized_v1）。
"""

from app.services.dataset_unit_contract import classify_dataset_unit


class TestClassifyDatasetUnit:
    """classify_dataset_unit 全分支覆盖。"""

    # ── legacy_unknown：None / 空 dict / 非 dict ─────────────────────

    def test_none_returns_legacy_unknown(self):
        assert classify_dataset_unit(None) == "legacy_unknown"

    def test_empty_dict_returns_legacy_unknown(self):
        assert classify_dataset_unit({}) == "legacy_unknown"

    def test_non_dict_returns_legacy_unknown(self):
        # type: ignore[arg-type] — 故意传非法类型
        assert classify_dataset_unit("not a dict") == "legacy_unknown"  # type: ignore[arg-type]

    # ── legacy_declared：只有 amount_unit ────────────────────────────

    def test_amount_unit_yuan_returns_legacy_declared(self):
        assert classify_dataset_unit({"amount_unit": "元"}) == "legacy_declared"

    def test_amount_unit_wan_returns_legacy_declared(self):
        assert classify_dataset_unit({"amount_unit": "万元"}) == "legacy_declared"

    def test_amount_unit_qian_returns_legacy_declared(self):
        assert classify_dataset_unit({"amount_unit": "千元"}) == "legacy_declared"

    def test_amount_unit_empty_string_returns_legacy_unknown(self):
        """空字符串不算有效声明。"""
        assert classify_dataset_unit({"amount_unit": ""}) == "legacy_unknown"

    def test_amount_unit_whitespace_only_returns_legacy_unknown(self):
        """纯空白不算有效声明。"""
        assert classify_dataset_unit({"amount_unit": "   "}) == "legacy_unknown"

    def test_amount_unit_none_returns_legacy_unknown(self):
        """amount_unit 为 None 不算有效声明。"""
        assert classify_dataset_unit({"amount_unit": None}) == "legacy_unknown"

    def test_amount_unit_non_string_returns_legacy_unknown(self):
        """amount_unit 非字符串不算有效声明。"""
        assert classify_dataset_unit({"amount_unit": 123}) == "legacy_unknown"

    # ── unit_normalization 存在但无效 → fail-closed legacy_unknown ───

    def test_unit_normalization_no_contract_returns_legacy_unknown(self):
        """有 unit_normalization 但没有 contract。"""
        summary = {"unit_normalization": {"version": "v1"}}
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_contract_no_digest_returns_legacy_unknown(self):
        """contract 存在但缺 contract_digest。"""
        summary = {"unit_normalization": {"contract": {"source_unit": "yuan"}}}
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_contract_digest_wrong_format_returns_legacy_unknown(self):
        """contract_digest 格式错误（非 64 位十六进制）。"""
        summary = {
            "unit_normalization": {
                "contract": {"contract_digest": "abc123"}
            }
        }
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_contract_digest_uppercase_returns_legacy_unknown(self):
        """contract_digest 是大写十六进制 → 无效（规范要求小写）。"""
        summary = {
            "unit_normalization": {
                "contract": {"contract_digest": "A" * 64}
            }
        }
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_non_dict_returns_legacy_unknown(self):
        """unit_normalization 不是 dict。"""
        summary = {"unit_normalization": "invalid"}
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_contract_non_dict_returns_legacy_unknown(self):
        """contract 不是 dict。"""
        summary = {"unit_normalization": {"contract": "not-a-dict"}}
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_unit_normalization_contract_digest_none_returns_legacy_unknown(self):
        """contract_digest 为 None。"""
        summary = {
            "unit_normalization": {
                "contract": {"contract_digest": None}
            }
        }
        assert classify_dataset_unit(summary) == "legacy_unknown"

    # ── unit_normalization 存在且有旧 amount_unit → 仍按 normalization 判 ─

    def test_unit_normalization_invalid_with_amount_unit_returns_legacy_unknown(self):
        """同时有 amount_unit 和无效 unit_normalization → fail-closed 为 legacy_unknown，
        而不是回退到 legacy_declared。"""
        summary = {
            "amount_unit": "万元",
            "unit_normalization": {"contract": {}},
        }
        assert classify_dataset_unit(summary) == "legacy_unknown"

    # ── normalized_v1：完整有效 contract ─────────────────────────────

    def test_valid_contract_returns_normalized_v1(self):
        """有效的 64 位小写十六进制 digest → normalized_v1。"""
        digest = "a" * 64
        summary = {
            "unit_normalization": {
                "contract": {
                    "source_unit": "wan",
                    "storage_unit": "yuan",
                    "factor": "10000",
                    "contract_digest": digest,
                }
            }
        }
        assert classify_dataset_unit(summary) == "normalized_v1"

    def test_valid_contract_mixed_hex_returns_normalized_v1(self):
        """contract_digest 混合小写十六进制字符 → normalized_v1。"""
        digest = "0123456789abcdef" * 4
        summary = {
            "unit_normalization": {
                "contract": {"contract_digest": digest}
            }
        }
        assert classify_dataset_unit(summary) == "normalized_v1"

    def test_valid_contract_with_legacy_amount_unit_returns_normalized_v1(self):
        """同时有 amount_unit 和有效 normalization → 优先认 normalized_v1。"""
        digest = "b" * 64
        summary = {
            "amount_unit": "万元",
            "unit_normalization": {
                "contract": {"contract_digest": digest}
            },
        }
        assert classify_dataset_unit(summary) == "normalized_v1"

    # ── 其他字段不干扰分类 ───────────────────────────────────────────

    def test_unrelated_fields_do_not_affect_classification(self):
        """只有不相关字段时 → legacy_unknown。"""
        summary = {"files": ["a.xlsx"], "file_count": 1}
        assert classify_dataset_unit(summary) == "legacy_unknown"

    def test_other_fields_with_amount_unit(self):
        """有 amount_unit 加其他字段 → legacy_declared。"""
        summary = {"amount_unit": "元", "files": ["a.xlsx"]}
        assert classify_dataset_unit(summary) == "legacy_declared"
