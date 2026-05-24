"""测试 report_line_mapping_service 的 seed 数据驱动逻辑

仅测纯函数,不依赖 DB,绕开 SQLite ARRAY 不兼容问题。
"""

import pytest
from app.services import report_line_mapping_service as svc


class TestDeriveApplicableStandard:
    """验证项目维度派生 applicable_standard"""

    def test_default_is_soe_standalone(self):
        """无 template_type / report_scope 时默认国企单体"""
        assert svc._derive_applicable_standard(None, None) == "soe_standalone"
        assert svc._derive_applicable_standard("", "") == "soe_standalone"

    def test_soe_consolidated(self):
        assert svc._derive_applicable_standard("soe", "consolidated") == "soe_consolidated"

    def test_listed_standalone(self):
        assert svc._derive_applicable_standard("listed", "standalone") == "listed_standalone"

    def test_listed_consolidated(self):
        assert svc._derive_applicable_standard("listed", "consolidated") == "listed_consolidated"

    def test_invalid_template_type_falls_back_to_soe(self):
        """非法 template_type 降级到 soe"""
        assert svc._derive_applicable_standard("xyz", "standalone") == "soe_standalone"

    def test_invalid_report_scope_falls_back_to_standalone(self):
        """非法 report_scope 降级到 standalone"""
        assert svc._derive_applicable_standard("listed", "xyz") == "listed_standalone"

    def test_case_insensitive(self):
        assert svc._derive_applicable_standard("LISTED", "CONSOLIDATED") == "listed_consolidated"


class TestSeedLoading:
    """验证 seed 文件加载与查表"""

    def setup_method(self):
        # 清缓存,避免被其他测试污染
        svc._load_seed.cache_clear()

    def test_seed_loads_4_dimensions(self):
        seed = svc._load_seed()
        assert "soe_standalone" in seed
        assert "soe_consolidated" in seed
        assert "listed_standalone" in seed
        assert "listed_consolidated" in seed
        # 每套维度应有 100+ 条映射
        for std, mappings in seed.items():
            assert len(mappings) > 100, f"{std} 映射数过少: {len(mappings)}"


class TestLookupReportLineFromSeed:
    """验证标准科目→报表行 查表逻辑(国企/上市差异)"""

    def setup_method(self):
        svc._load_seed.cache_clear()

    # ── 关键差异验证: 同科目国企 vs 上市 row_code 不同 ──

    def test_使用权资产_soe_vs_listed_行号差异(self):
        """1641 使用权资产: 国企 BS-044 vs 上市 BS-032"""
        soe_hit = svc._lookup_report_line_from_seed("1641", "soe_standalone")
        listed_hit = svc._lookup_report_line_from_seed("1641", "listed_standalone")
        assert soe_hit is not None
        assert listed_hit is not None
        assert soe_hit[0] == "BS-044"  # 国企单体
        assert listed_hit[0] == "BS-032"  # 上市单体
        assert soe_hit[0] != listed_hit[0]  # 必须不同

    def test_存货_soe_vs_listed_行号差异(self):
        """1405 库存商品: 国企 BS-018 vs 上市 BS-012"""
        soe_hit = svc._lookup_report_line_from_seed("1405", "soe_standalone")
        listed_hit = svc._lookup_report_line_from_seed("1405", "listed_standalone")
        assert soe_hit[0] == "BS-018"
        assert listed_hit[0] == "BS-012"

    def test_商誉_soe_vs_listed_行号差异(self):
        """1711 商誉: 国企 BS-047 vs 上市 BS-037"""
        soe_hit = svc._lookup_report_line_from_seed("1711", "soe_standalone")
        listed_hit = svc._lookup_report_line_from_seed("1711", "listed_standalone")
        assert soe_hit[0] == "BS-047"
        assert listed_hit[0] == "BS-037"

    # ── 之前完全没覆盖的科目验证 ──

    def test_使用权资产组_全部覆盖(self):
        """1641-1643 使用权资产组,旧硬编码字典完全没覆盖"""
        for code in ("1641", "1642", "1643"):
            hit = svc._lookup_report_line_from_seed(code, "soe_standalone")
            assert hit is not None, f"{code} 在 seed 中应能查到"
            assert hit[0].startswith("BS-")

    def test_租赁负债_覆盖(self):
        """2601 租赁负债 旧硬编码字典完全没覆盖"""
        hit = svc._lookup_report_line_from_seed("2601", "soe_standalone")
        assert hit is not None
        assert hit[0].startswith("BS-")

    def test_累计折旧_覆盖(self):
        """1602 累计折旧 旧硬编码字典完全没覆盖,应归到固定资产行"""
        hit = svc._lookup_report_line_from_seed("1602", "soe_standalone")
        assert hit is not None
        assert hit[1] == "固定资产"

    def test_减值损失_覆盖(self):
        """6701 资产减值损失 / 6702 信用减值损失 旧硬编码字典完全没覆盖"""
        for code in ("6701", "6702"):
            hit = svc._lookup_report_line_from_seed(code, "soe_standalone")
            assert hit is not None
            assert hit[0].startswith("IS-")

    # ── row_code 格式验证: 必须是 BS-XXX / IS-XXX(带连字符),与 report_config seed 一致 ──

    def test_row_code_格式带连字符(self):
        """旧硬编码用 BS001,seed 真实是 BS-001,必须修正"""
        hit = svc._lookup_report_line_from_seed("1001", "soe_standalone")
        assert hit is not None
        assert "-" in hit[0], f"row_code 必须带连字符: {hit[0]}"
        # 不应再有 "BS001" 这种格式
        assert hit[0] != "BS001"

    # ── 坏账分项 1231-0x 验证 ──

    def test_坏账准备分项_应收票据(self):
        """1231-01 坏账准备-应收票据 应映射到对应的应收票据行"""
        hit = svc._lookup_report_line_from_seed("1231-01", "soe_standalone")
        assert hit is not None
        assert hit[1] == "应收票据"

    def test_坏账准备分项_应收账款(self):
        hit = svc._lookup_report_line_from_seed("1231-02", "soe_standalone")
        assert hit is not None
        assert hit[1] == "应收账款"

    def test_坏账准备分项_其他应收款(self):
        hit = svc._lookup_report_line_from_seed("1231-03", "soe_standalone")
        assert hit is not None
        assert hit[1] == "其他应收款"

    def test_坏账准备分项_预付账款(self):
        hit = svc._lookup_report_line_from_seed("1231-04", "soe_standalone")
        assert hit is not None
        assert hit[1] == "预付款项"

    def test_坏账准备分项_合同资产(self):
        hit = svc._lookup_report_line_from_seed("1231-05", "soe_standalone")
        assert hit is not None
        assert hit[1] == "合同资产"

    def test_坏账分项_国企vs上市行号不同(self):
        """1231-02 坏账准备-应收账款: 国企 BS-008 vs 上市 BS-006"""
        soe = svc._lookup_report_line_from_seed("1231-02", "soe_standalone")
        listed = svc._lookup_report_line_from_seed("1231-02", "listed_standalone")
        assert soe[0] != listed[0]

    # ── 4 位前缀匹配验证 (客户带分隔符的二级科目) ──

    def test_客户子科目_点分隔(self):
        """6401.01 → 4 位前缀 6401 → 营业成本"""
        hit = svc._lookup_report_line_from_seed("6401.01", "soe_standalone")
        assert hit is not None
        assert hit[1] == "营业成本"

    def test_客户子科目_连字符分隔(self):
        """6401-01 → 4 位前缀 6401 → 营业成本"""
        hit = svc._lookup_report_line_from_seed("6401-01", "soe_standalone")
        assert hit is not None
        assert hit[1] == "营业成本"

    def test_客户子科目_直接拼接(self):
        """640101 → 4 位前缀 6401 → 营业成本"""
        hit = svc._lookup_report_line_from_seed("640101", "soe_standalone")
        assert hit is not None
        assert hit[1] == "营业成本"

    # ── 不存在的科目编码兜底 ──

    def test_不存在的科目返回None(self):
        """完全不存在的编码返回 None,不再走错误的关键词兜底"""
        hit = svc._lookup_report_line_from_seed("9999", "soe_standalone")
        assert hit is None

    def test_未配置的维度降级到soe_standalone(self):
        """非法维度 key 降级到 soe_standalone"""
        hit = svc._lookup_report_line_from_seed("1001", "invalid_dimension")
        assert hit is not None  # 降级后能查到货币资金



# ===================================================================
# 测试 mapping_service 中 1231 系列优先匹配二级分项
# ===================================================================


class TestMappingServiceBadDebtPriority:
    """验证 mapping_service._match_single 对 1231 系列科目优先按名称匹配二级"""

    def setup_method(self):
        from app.services import mapping_service
        # 清缓存
        mapping_service._BAD_DEBT_KEYWORD_MAP  # 触发加载

    def test_客户码1231_01应收票据_优先匹配1231_01(self):
        """1231.01 (坏账准备_应收票据) 不应被 1231 总分类抢走,应匹配 1231-01"""
        from app.services import mapping_service
        from app.models.audit_platform_models import AccountChart

        client = AccountChart(
            account_code='1231.01', account_name='坏账准备_应收票据',
        )
        # 模拟 std_by_code 含被污染的 1231 总分类(关键!这是真实环境陷阱)
        sub_01 = AccountChart(account_code='1231-01', account_name='坏账准备-应收票据')
        sub_02 = AccountChart(account_code='1231-02', account_name='坏账准备-应收账款')
        sub_03 = AccountChart(account_code='1231-03', account_name='坏账准备-其他应收款')
        polluted_total = AccountChart(account_code='1231', account_name='坏账准备_应收票据')
        std_by_code = {
            '1231': polluted_total,  # ← 被污染的总分类(优先级陷阱)
            '1231-01': sub_01,
            '1231-02': sub_02,
            '1231-03': sub_03,
        }

        result = mapping_service._match_single(client, std_by_code, {}, [])
        assert result is not None
        assert result.suggested_standard_code == '1231-01', \
            f"必须匹配 1231-01,而不是被 1231 总分类抢走 (得到 {result.suggested_standard_code})"
        assert result.match_method == 'bad_debt_sub_account'

    def test_客户码1231_02应收账款_匹配1231_02(self):
        from app.services import mapping_service
        from app.models.audit_platform_models import AccountChart

        client = AccountChart(account_code='1231.02', account_name='坏账准备_应收账款')
        sub_02 = AccountChart(account_code='1231-02', account_name='坏账准备-应收账款')
        polluted_total = AccountChart(account_code='1231', account_name='坏账准备')
        std_by_code = {'1231': polluted_total, '1231-02': sub_02}

        result = mapping_service._match_single(client, std_by_code, {}, [])
        assert result is not None
        assert result.suggested_standard_code == '1231-02'

    def test_客户码1231_03其他应收款_匹配1231_03(self):
        from app.services import mapping_service
        from app.models.audit_platform_models import AccountChart

        client = AccountChart(account_code='1231.03', account_name='坏账准备_其他应收款')
        sub_03 = AccountChart(account_code='1231-03', account_name='坏账准备-其他应收款')
        polluted_total = AccountChart(account_code='1231', account_name='坏账准备')
        std_by_code = {'1231': polluted_total, '1231-03': sub_03}

        result = mapping_service._match_single(client, std_by_code, {}, [])
        assert result is not None
        assert result.suggested_standard_code == '1231-03'

    def test_客户码1231无后缀总分类_无关键词时fallback到1231(self):
        """如果客户用 1231 无后缀且名称就叫"坏账准备",回退到 1231 总分类是 OK 的"""
        from app.services import mapping_service
        from app.models.audit_platform_models import AccountChart

        client = AccountChart(account_code='1231', account_name='坏账准备')
        total = AccountChart(account_code='1231', account_name='坏账准备')
        std_by_code = {'1231': total}

        result = mapping_service._match_single(client, std_by_code, {}, [])
        assert result is not None
        # 名称无关键词,_match_bad_debt_sub_account 返 None,落 Priority 0 完整码匹配
        assert result.suggested_standard_code == '1231'
