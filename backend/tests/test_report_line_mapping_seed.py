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


# ===================================================================
# 递减项(contra)机制：备抵科目映射 sign + 新补科目路由
# 报表映射递减项修复（2026-06-10）
# ===================================================================


class TestContraSignDerivation:
    """验证备抵科目通过 direction_resolver 被判定为 contra_account（→ mapping_sign=subtract）。

    ai_suggest_mappings 的 _derive_sign 闭包用 resolve_account_direction 的
    source=='contra_account' 信号给 mapping_sign 赋 'subtract'，本测试守护该信号源。
    """

    def test_累计折旧类_判为contra(self):
        from app.services.ledger_import.direction_resolver import resolve_account_direction
        for code, name in [
            ("1602", "固定资产累计折旧"),
            ("1602", "累计折旧"),
            ("1702", "累计摊销"),
            ("1525", "投资性房地产累计折旧"),
            ("1526", "投资性房地产累计摊销"),
            ("1642", "使用权资产累计折旧"),
            ("1632", "累计折耗"),
        ]:
            _dir, source = resolve_account_direction(code, name)
            assert source == "contra_account", f"{code} {name} 应判为 contra_account"

    def test_减值跌价坏账类_判为contra(self):
        from app.services.ledger_import.direction_resolver import resolve_account_direction
        for code, name in [
            ("1231", "坏账准备"),
            ("1416", "存货跌价准备"),
            ("1461", "存货跌价准备"),
            ("1603", "固定资产减值准备"),
            ("1703", "无形资产减值准备"),
            ("1512", "长期股权投资减值准备"),
        ]:
            _dir, source = resolve_account_direction(code, name)
            assert source == "contra_account", f"{code} {name} 应判为 contra_account"

    def test_库存股_判为contra(self):
        from app.services.ledger_import.direction_resolver import resolve_account_direction
        _dir, source = resolve_account_direction("4201", "库存股")
        assert source == "contra_account"

    def test_普通科目_非contra(self):
        """正常科目(非备抵)不应判为 contra → mapping_sign=add。"""
        from app.services.ledger_import.direction_resolver import resolve_account_direction
        for code, name in [
            ("1521", "投资性房地产"),
            ("1601", "固定资产"),
            ("1701", "无形资产"),
            ("1452", "低值易耗品"),
            ("1001", "库存现金"),
        ]:
            _dir, source = resolve_account_direction(code, name)
            assert source != "contra_account", f"{code} {name} 不应判为 contra_account"


class TestSeedContraGapFill:
    """验证 seed 补全了低值易耗品/存货跌价/投资性房地产备抵科目路由（4 维度）。"""

    def setup_method(self):
        svc._load_seed.cache_clear()

    def test_低值易耗品_路由到存货(self):
        """1452 低值易耗品 → 存货（国企 BS-018 / 上市 BS-012）。"""
        soe = svc._lookup_report_line_from_seed("1452", "soe_standalone")
        listed = svc._lookup_report_line_from_seed("1452", "listed_standalone")
        assert soe is not None and soe[1] == "存货"
        assert listed is not None and listed[1] == "存货"
        assert soe[0] == "BS-018"
        assert listed[0] == "BS-012"

    def test_存货跌价准备_路由到存货(self):
        """1416 存货跌价准备 → 存货（备抵，sign 由代码判 subtract）。"""
        for dim in ("soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"):
            hit = svc._lookup_report_line_from_seed("1416", dim)
            assert hit is not None and hit[1] == "存货", f"{dim} 1416 应路由存货"

    def test_投资性房地产备抵_路由到投资性房地产(self):
        """1525/1526 投资性房地产累计折旧/摊销 → 投资性房地产（备抵）。"""
        for code in ("1525", "1526"):
            soe = svc._lookup_report_line_from_seed(code, "soe_standalone")
            listed = svc._lookup_report_line_from_seed(code, "listed_standalone")
            assert soe is not None and soe[1] == "投资性房地产"
            assert listed is not None and listed[1] == "投资性房地产"
            assert soe[0] == "BS-036"
            assert listed[0] == "BS-027"


# ===================================================================
# 编码+名称双保险：同编码不同含义(4101 制造费用 vs 盈余公积)防错配
# 2026-06-10，用户要求"科目类别判断按编码+名称双保险"
# ===================================================================


class TestSeedNameAwareGuard:
    """验证 _lookup_report_line_from_seed 的名称类别一致性闸。

    seed 把 4101→存货(标准表制造费用理解)。客户用 4xxx 作权益体系时
    4101=盈余公积(equity)，纯编码会错配存货(asset)。传入名称后类别冲突被拦截。
    """

    def setup_method(self):
        svc._load_seed.cache_clear()

    def test_4101_制造费用_仍命中存货(self):
        """名称=制造费用(expense，损益类不参与 BS 侧校验) → 编码命中放行(存货)。"""
        hit = svc._lookup_report_line_from_seed("4101", "soe_standalone", "制造费用")
        assert hit is not None
        assert hit[1] == "存货"

    def test_4101_盈余公积_被拦截不进存货(self):
        """名称=盈余公积(equity) 但编码 4101 命中存货(asset 侧) → 冲突拦截返回 None。"""
        hit = svc._lookup_report_line_from_seed("4101", "soe_standalone", "盈余公积")
        assert hit is None, "equity 科目不应被错配到存货行次"

    def test_4001_实收资本_被拦截不进存货(self):
        """名称=实收资本(equity) 但 4001 命中存货 → 拦截。"""
        hit = svc._lookup_report_line_from_seed("4001", "soe_standalone", "实收资本")
        assert hit is None

    def test_4001_生产成本_仍命中存货(self):
        """名称=生产成本(expense) → 放行存货(在产品归存货合理)。"""
        hit = svc._lookup_report_line_from_seed("4001", "soe_standalone", "生产成本")
        assert hit is not None
        assert hit[1] == "存货"

    def test_无名称_保持原编码命中(self):
        """不传名称 → 不做校验，保持旧行为(向后兼容)。"""
        hit = svc._lookup_report_line_from_seed("4101", "soe_standalone")
        assert hit is not None
        assert hit[1] == "存货"

    def test_正常资产科目_名称一致放行(self):
        """1521 投资性房地产(asset) 名称一致 → 正常放行。"""
        hit = svc._lookup_report_line_from_seed("1521", "soe_standalone", "投资性房地产")
        assert hit is not None
        assert hit[1] == "投资性房地产"

    def test_负债科目_名称一致放行(self):
        """2202 应付账款(liability) 名称一致 → 放行。"""
        hit = svc._lookup_report_line_from_seed("2202", "soe_standalone", "应付账款")
        assert hit is not None
        assert hit[1] == "应付账款"

    def test_损益类科目不受BS侧校验影响(self):
        """6001 主营业务收入(revenue) → 利润表行次，不参与 BS 侧校验，放行。"""
        hit = svc._lookup_report_line_from_seed("6001", "soe_standalone", "主营业务收入")
        assert hit is not None
        assert hit[2] == "income_statement"


class TestBsLineSide:
    """验证 _bs_line_side 行次侧别判定(纯函数)。"""

    def test_equity_lines(self):
        for name in ("实收资本", "资本公积", "盈余公积", "未分配利润", "库存股", "其他综合收益"):
            assert svc._bs_line_side(name) == "equity", f"{name} 应判 equity"

    def test_liability_lines(self):
        for name in ("短期借款", "应付账款", "合同负债", "递延所得税负债", "租赁负债"):
            assert svc._bs_line_side(name) == "liability", f"{name} 应判 liability"

    def test_asset_lines_default(self):
        for name in ("货币资金", "存货", "固定资产", "投资性房地产", "应收账款"):
            assert svc._bs_line_side(name) == "asset", f"{name} 应判 asset"


class TestSeed2705LongTermSalary:
    """2705 长期应付职工薪酬 — 标准表+seed 原缺，国企版报表模板有此行次(2026-06-10 补)。"""

    def setup_method(self):
        svc._load_seed.cache_clear()

    def test_2705_soe_映射长期应付职工薪酬(self):
        hit = svc._lookup_report_line_from_seed("2705", "soe_standalone", "长期应付职工薪酬")
        assert hit is not None
        assert hit[0] == "BS-093"
        assert hit[1] == "长期应付职工薪酬"

    def test_2705_listed_映射长期应付职工薪酬(self):
        hit = svc._lookup_report_line_from_seed("2705", "listed_standalone", "长期应付职工薪酬")
        assert hit is not None
        assert hit[0] == "BS-067"

    def test_2705_四维度全覆盖(self):
        for dim in ("soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated"):
            hit = svc._lookup_report_line_from_seed("2705", dim, "长期应付职工薪酬")
            assert hit is not None and hit[1] == "长期应付职工薪酬", f"{dim} 缺 2705"

    def test_2705_子科目走4位前缀(self):
        """客户二级科目 2705.01 → 规范化 4 位前缀 2705 命中。"""
        hit = svc._lookup_report_line_from_seed("2705.01", "soe_standalone", "长期应付职工薪酬_设定受益计划")
        assert hit is not None
        assert hit[1] == "长期应付职工薪酬"
