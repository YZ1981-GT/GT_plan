from app.services.g7_consol_linkage_service import (
    assert_expected_versions,
    build_company_lookup,
    build_linkage_candidates,
    merge_target_rows,
    G7LinkageConflictError,
    _ratio_to_percent,
)


def test_ratio_scales_are_explicit_per_source():
    assert _ratio_to_percent(0.8, scale="fraction") == 80
    assert _ratio_to_percent(80, scale="percent") == 80
    # G7-4 的 1 表示 1%，不得误判为 100%
    assert _ratio_to_percent(1, scale="percent") == 1
    assert _ratio_to_percent(1, scale="fraction") == 100


def test_build_linkage_candidates_maps_core_g7_sheets():
    payloads = {
        "G7-4-rows": [
            {
                "id": "b1",
                "groupType": "subsidiary",
                "investeeName": "子公司甲",
                "directHoldingRatio": 80,
                "indirectHoldingRatio": 5,
                "newlyConsolidated": "是",
                "acquisitionMethod": "非同一控制",
                "accountingMethod": "成本法",
            },
            {
                "id": "b2",
                "groupType": "associate",
                "investeeName": "联营乙",
                "directHoldingRatio": 30,
                "accountingMethod": "权益法",
            },
        ],
        "G7-2-rows": [
            {
                "id": "c1",
                "section": "cost",
                "investeeName": "子公司甲",
                "auditedOpeningRatio": 0.8,
                "auditedOpeningAmount": 100,
                "auditedIncreaseAmount": 20,
                "cashDividend": 6,
            },
            {
                "id": "e1",
                "section": "equity",
                "investeeName": "联营乙",
                "auditedOpeningRatio": 0.3,
                "auditedOpeningAmount": 40,
                "auditedProfitLoss": 5,
            },
        ],
        "G7-14-rows": [
            {
                "id": "m1",
                "investeeName": "联营乙",
                "equityShare": 8,
                "ociShare": 2,
                "dividendDistributed": 1,
                "auditedNetAssets": 200,
                "otherAdj": 80,
                "internalTransactionAdj": 12,
                "accountingPolicyAdj": 3,
            }
        ],
        "G7-16-rows": [
            {
                "id": "u1",
                "investeeName": "联营乙",
                "excessLoss": 50,
                "unrecognizedLoss": 20,
                "priorCumulative": 5,
                "currentChange": 15,
            }
        ],
        "G7-13-rows": [
            {
                "id": "c1",
                "investeeName": "联营乙",
                "investeeId": "b2",
                "initialCost": 120,
                "netAssetFairValue": 500,
                "shareOfNetAssets": 150,
                "difference": -30,
                "differenceNature": "营业外收入",
                "investmentRatio": 0.3,
            }
        ],
        "G7-15-rows": [
            {
                "id": "t1",
                "investeeId": "b2",
                "investeeName": "联营乙-旧名",
                "currentChange": 30,
                "eliminationAmount": 100,
            },
            {
                "id": "t2",
                "investeeId": "b2",
                "investeeName": "联营乙-旧名",
                "currentChange": 20,
                "eliminationAmount": 50,
            },
        ],
        "G7-17-rows": [
            {
                "id": "i1",
                "investeeName": "子公司甲",
                "impairmentAmount": 3,
                "openingImpairment": 1.5,
                "recoverableAmount": 117,
            }
        ],
    }
    companies = [
        {
            "company_code": "S001",
            "company_name": "子公司甲",
            "parent_code": "P001",
        },
        {
            "company_code": "A001",
            "company_name": "联营乙",
            "parent_code": "P001",
        },
    ]

    result = build_linkage_candidates(payloads, {}, companies=companies)

    assert result["unresolved_companies"] == []
    assert result["ambiguous_companies"] == []
    assert result["counts"]["info"] == {"candidate": 2, "importable": 2}
    assert result["counts"]["net_asset"] == {"candidate": 0, "importable": 0}
    assert result["importable"]["cost"][0]["open_ratio"] == 80
    assert result["importable"]["cost"][0]["add_impairment"] == 3
    assert result["importable"]["cost"][0]["open_impairment"] == 1.5
    assert result["importable"]["equity_inv"][0]["open_ratio"] == 30
    assert result["importable"]["equity_inv"][0]["add_income_adj"] == 8
    assert result["importable"]["equity_inv"][0]["add_oci"] == 2
    assert result["importable"]["equity_inv"][0]["_g7_other_adj"] == 80
    assert result["importable"]["equity_inv"][0]["_g7_internal_transaction_adj"] == 12
    assert result["importable"]["equity_inv"][0]["_g7_accounting_policy_adj"] == 3
    assert result["importable"]["equity_inv"][0]["_g7_unrecognized_loss"] == 20
    assert result["importable"]["equity_inv"][0]["_g7_excess_loss"] == 50
    assert result["importable"]["equity_inv"][0]["_g7_current_change"] == 15
    assert result["importable"]["equity_inv"][0]["_g7_prior_cumulative"] == 5
    # G7-13：初始成本 / 差额结构化字段 + 廉价购买建议
    assert result["importable"]["equity_inv"][0]["add_cost"] == 120
    assert result["importable"]["equity_inv"][0]["_g7_initial_cost"] == 120
    assert result["importable"]["equity_inv"][0]["_g7_difference"] == -30
    assert result["importable"]["equity_inv"][0]["_g7_difference_nature"] == "营业外收入"
    assert result["importable"]["equity_inv"][0]["_g7_investment_ratio"] == 30
    # G7-15：按 investeeId→G7-4 名称对齐并汇总本年变动 30+20=50
    assert result["importable"]["equity_inv"][0]["_g7_internal_elim_change"] == 50
    assert result["importable"]["equity_inv"][0]["_g7_g7_15_txn_count"] == 2
    assert result["importable"]["info"][0]["non_common_ratio"] == 85
    assert any(s.get("source_sheet") == "G7-16" for s in result["suggestions"])
    assert any(s.get("source_sheet") == "G7-15" for s in result["suggestions"])
    assert any(s.get("source_sheet") == "G7-13" for s in result["suggestions"])
    g713 = next(s for s in result["suggestions"] if s.get("source_sheet") == "G7-13")
    assert g713["type"] == "investment_cost_bargain"
    assert g713["difference"] == -30
    g715 = next(s for s in result["suggestions"] if s.get("source_sheet") == "G7-15")
    assert g715["type"] == "internal_transaction_elim"
    assert g715["current_change"] == 50
    assert g715["company_code"] == "A001"
    g716 = next(s for s in result["suggestions"] if s.get("source_sheet") == "G7-16")
    assert g716["type"] == "unrecognized_loss"
    assert g716["unrecognized_loss"] == 20
    assert g716["company_code"] == "A001"

def test_g714_net_asset_adjustments_pivot_to_matrix():
    from app.services.g7_consol_linkage_service import (
        build_field_diffs,
        apply_selected_diffs,
        merge_net_asset_rows,
    )

    payloads = {
        "G7-14-equity-method-calc": {
            "netAssetAdjustments": [{
                "investeeName": "子公司甲",
                "shareCapital": {"begin": 100, "increase": 10, "decrease": 0},
                "retainedEarnings": {"begin": 50, "increase": 20, "decrease": 5},
                "treasuryStock": {"begin": 8, "increase": 0, "decrease": 0},
                "fvDiffAtAcquisition": {"begin": 12, "increase": 0, "decrease": 0},
            }],
        },
        "G7-9-rows": [{
            "id": "m1",
            "section": "merger",
            "investeeName": "子公司甲",
            "ownershipRatio": 0.8,
            "initialInvestmentCost": 200,
            "acquireeIdentifiableNetAssetsFV": 180,
            "goodwill": 56,
            "nonControllingInterestShare": 36,
        }],
    }
    companies = [{
        "company_code": "S001",
        "company_name": "子公司甲",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    assert result["counts"]["net_asset"]["importable"] == 1
    na = result["importable"]["net_asset"][0]
    assert na["company_order"] == ["S001"]
    opening_sc = next(
        r for r in na["rows"]
        if r.get("section") == "opening" and r.get("item") == "实收资本（或股本）"
    )
    assert opening_sc["values"] == [100]
    closing_re = next(
        r for r in na["rows"]
        if r.get("section") == "closing" and r.get("item") == "未分配利润"
    )
    assert closing_re["values"] == [65]
    treasury = next(
        r for r in na["rows"]
        if r.get("section") == "opening" and r.get("item") == "减：库存股"
    )
    assert treasury["values"] == [-8]
    assert any(
        s["field"] == "fvDiffAtAcquisition"
        for s in result["skipped_net_asset_fields"]
    )

    merged = merge_net_asset_rows(
        [],
        na,
        ["S001"],
        overwrite=False,
    )
    opening_sc2 = next(
        r for r in merged
        if r.get("section") == "opening" and r.get("item") == "实收资本（或股本）"
    )
    assert opening_sc2["values"][0] == 100

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["parent_share_ratio"] == 80
    assert result["suggestions"][0]["goodwill_amount"] == 56

    existing = {
        "cost": [{"company_code": "S001", "company_name": "甲", "open_cost": 999}],
    }
    importable = {
        "cost": [{
            "company_code": "S001",
            "company_name": "子公司甲",
            "open_cost": 100,
            "add_cost": 20,
        }],
        "info": [],
        "equity_inv": [],
    }
    diffs = build_field_diffs(existing, importable)
    statuses = {(d["field"], d["status"]) for d in diffs if d["sheet_key"] == "cost"}
    assert ("open_cost", "conflict") in statuses
    assert ("add_cost", "changed") in statuses

    selected = {("S001", "add_cost")}
    applied = apply_selected_diffs(
        existing["cost"],
        importable["cost"],
        selected,
    )
    assert applied[0]["open_cost"] == 999
    assert applied[0]["add_cost"] == 20


def test_g710_and_g73_suggestions_and_info_share_change():
    payloads = {
        "G7-4-rows": [{
            "groupType": "subsidiary",
            "investeeName": "子公司甲",
            "directHoldingRatio": 80,
            "acquisitionMethod": "非同一控制",
        }],
        "G7-10-rows": [
            {
                "id": "n1",
                "section": "nci",
                "companyName": "子公司甲",
                "originalRatio": 0.8,
                "addedRatio": 0.1,
                "purchaseCost": 50,
                "equityAdjustment": 12,
                "adjCapitalReserve": 12,
            },
            {
                "id": "d1",
                "section": "dividend",
                "companyName": "子公司甲",
                "declaredAmount": 10,
                "shareholdingRatio": 0.8,
            },
        ],
        "G7-3-rows": [{
            "id": "a1",
            "entryType": "AJE",
            "accountCode": "1511",
            "accountName": "长期股权投资",
            "debitAmount": 5,
            "creditAmount": 0,
            "description": "权益法差异调整",
            "sourceKind": "g7-14-suggested",
        }],
        "G7-9-rows": [{
            "id": "m1",
            "section": "merger",
            "investeeName": "子公司甲",
            "ownershipRatio": 0.8,
            "goodwill": 56,
        }],
    }
    companies = [{
        "company_code": "S001",
        "company_name": "子公司甲",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    info = result["importable"]["info"][0]
    assert info["share_changed"] == "是"
    assert info["change_times"] >= 1
    assert info["_g7_ratio_before"] == 80
    assert info["_g7_ratio_after"] == 90

    types = {s["type"] for s in result["suggestions"]}
    assert "goodwill_nci" in types
    assert "share_change_capital" in types
    assert "consol_adjustment_draft" in types
    g710 = next(s for s in result["suggestions"] if s["type"] == "share_change_capital")
    assert g710["before_ratio"] == 80
    assert g710["after_ratio"] == 90
    assert g710["equity_adjustment"] == 12
    g73 = next(s for s in result["suggestions"] if s["type"] == "consol_adjustment_draft")
    assert g73["debit_amount"] == 5
    assert "G7-3" in result["sources_used"]
    assert "G7-10" in result["sources_used"]


def test_g710_dividend_uses_recorded_or_entitled_fields():
    payloads = {
        "G7-2-rows": [{
            "id": "c1",
            "section": "cost",
            "investeeName": "子公司甲",
            "auditedOpeningRatio": 0.8,
            "auditedOpeningAmount": 100,
        }],
        "G7-10-rows": [{
            "id": "div1",
            "section": "dividend",
            "companyName": "子公司甲",
            "shareholdingRatio": 0.8,
            "declaredAmount": 100,
            "entitledDividend": 80,
            "recordedDividend": 75,
        }],
    }
    companies = [{
        "company_code": "S001",
        "company_name": "子公司甲",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    assert result["importable"]["cost"][0]["current_dividend"] == 75


def test_g74_legacy_fraction_payload_honors_ratio_scale():
    payloads = {
        "G7-4-rows": {
            "ratioScale": "fraction",
            "rows": [{
                "groupType": "subsidiary",
                "investeeName": "子公司甲",
                "directHoldingRatio": 0.6,
                "acquisitionMethod": "同一控制",
            }],
        }
    }
    companies = [{
        "company_code": "S001",
        "company_name": "子公司甲",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    assert result["importable"]["info"][0]["common_ratio"] == 60


def test_unresolved_company_requires_explicit_mapping():
    payloads = {
        "G7-4-rows": [{
            "groupType": "subsidiary",
            "investeeName": "名称有差异",
            "directHoldingRatio": 60,
        }]
    }
    companies = [{
        "company_code": "S001",
        "company_name": "正式名称",
        "parent_code": "P001",
    }]

    preview = build_linkage_candidates(payloads, {}, companies=companies)
    assert preview["unresolved_companies"] == ["名称有差异"]
    assert preview["importable"]["info"] == []

    confirmed = build_linkage_candidates(
        payloads, {}, {"名称有差异": "S001"}, companies=companies
    )
    assert confirmed["unresolved_companies"] == []
    assert confirmed["importable"]["info"][0]["company_code"] == "S001"


def test_ambiguous_company_name_is_not_auto_matched():
    payloads = {
        "G7-4-rows": [{
            "groupType": "subsidiary",
            "investeeName": "同名公司",
            "directHoldingRatio": 70,
        }]
    }
    companies = [
        {"company_code": "A1", "company_name": "同名公司", "parent_code": "P"},
        {"company_code": "A2", "company_name": "同名公司", "parent_code": "P"},
    ]
    preview = build_linkage_candidates(payloads, {}, companies=companies)
    assert preview["ambiguous_companies"] == ["同名公司"]
    assert preview["importable"]["info"] == []

    confirmed = build_linkage_candidates(
        payloads, {}, {"同名公司": "A2"}, companies=companies
    )
    assert confirmed["ambiguous_companies"] == []
    assert confirmed["importable"]["info"][0]["company_code"] == "A2"


def test_build_company_lookup_marks_duplicates():
    by_code, unique, ambiguous = build_company_lookup([
        {"company_code": "A1", "company_name": "甲"},
        {"company_code": "A2", "company_name": "甲"},
        {"company_code": "B1", "company_name": "乙"},
    ])
    assert "A1" in by_code and "A2" in by_code
    assert len(unique) == 1
    assert list(unique.values())[0]["company_code"] == "B1"
    assert len(ambiguous) == 1


def test_merge_target_rows_is_fill_only_and_idempotent_by_default():
    existing = [{
        "company_code": "S001",
        "company_name": "人工名称",
        "open_cost": 999,
        "add_cost": None,
    }]
    incoming = [{
        "company_code": "S001",
        "company_name": "G7名称",
        "open_cost": 100,
        "add_cost": 20,
        "_source": {"sheet": "G7-2"},
    }]

    merged = merge_target_rows(existing, incoming)
    assert len(merged) == 1
    assert merged[0]["company_name"] == "人工名称"
    assert merged[0]["open_cost"] == 999
    assert merged[0]["add_cost"] == 20
    assert merged[0]["_source"]["sheet"] == "G7-2"

    overwritten = merge_target_rows(existing, incoming, overwrite=True)
    assert overwritten[0]["company_name"] == "G7名称"
    assert overwritten[0]["open_cost"] == 100


def test_assert_expected_versions_detects_stale():
    assert_expected_versions(
        {"G7-2-rows": "2026-01-01T00:00:00"},
        {"G7-2-rows": "2026-01-01T00:00:00"},
    )
    try:
        assert_expected_versions(
            {"G7-2-rows": "2026-01-02T00:00:00"},
            {"G7-2-rows": "2026-01-01T00:00:00"},
        )
        assert False, "should raise"
    except G7LinkageConflictError as exc:
        assert exc.stale_keys == ["G7-2-rows"]

def test_g7_12_maps_frontend_field_aliases_into_info():
    """G7-12 前端字段 lossOfControlDate/transactionPrice 应写入合并 info。"""
    payloads = {
        "G7-4-rows": [{
            "id": "b1",
            "groupType": "subsidiary",
            "investeeName": "子公司甲",
            "directHoldingRatio": 80,
            "accountingMethod": "成本法",
        }],
        "G7-2-rows": [{
            "id": "c1",
            "section": "cost",
            "investeeName": "子公司甲",
            "auditedOpeningAmount": 100,
        }],
        "G7-12-rows": [{
            "investeeName": "子公司甲",
            "lossOfControlDate": "2025-06-15",
            "transactionDate": "2024-01-01",
            "transactionPrice": 900,
            "disposalRatio": 0.5,
        }],
    }
    companies = [{
        "company_code": "S001",
        "company_name": "子公司甲",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    info = result["importable"]["info"][0]
    assert info["disposal_date"] == "2025-06-15"
    assert info["disposal_amount"] == 900
    assert info["disposal_ratio"] == 50


def test_g79_step_suggestions_and_add_cost_from_parent_initial():
    """分步合并按公司汇总进商誉建议，并以⑦写入 add_cost。"""
    from app.services.g7_consol_linkage_service import build_linkage_candidates

    payloads = {
        "G7-4-rows": [{
            "id": "b1",
            "groupType": "subsidiary",
            "investeeName": "分步乙",
            "directHoldingRatio": 60,
            "accountingMethod": "成本法",
        }],
        "G7-2-rows": [{
            "id": "c1",
            "section": "cost",
            "investeeName": "分步乙",
            "auditedOpeningAmount": 50,
        }],
        "G7-9-rows": [
            {
                "id": "s1",
                "section": "step",
                "companyId": "c-乙",
                "companyName": "分步乙",
                "transactionNo": 1,
                "purchaseRatio": 0.4,
                "considerationFV": 40,
                "shareOfFVAtTxn": 36,
                "goodwillAtTxn": 4,
                "priorEquityMethodAdjustments": 5,
            },
            {
                "id": "s2",
                "section": "step",
                "companyId": "c-乙",
                "companyName": "分步乙",
                "transactionNo": 2,
                "purchaseRatio": 0.2,
                "considerationFV": 25,
                "shareOfFVAtTxn": 18,
                "goodwillAtTxn": 7,
                "priorEquityMethodAdjustments": None,
            },
        ],
    }
    companies = [{
        "company_code": "S002",
        "company_name": "分步乙",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    suggestions = [s for s in result["suggestions"] if s.get("source_sheet") == "G7-9"]
    assert len(suggestions) == 1
    assert suggestions[0]["type"] == "goodwill_nci"
    assert suggestions[0]["acquisition_cost"] == 70  # 40+25+5
    assert suggestions[0]["goodwill_amount"] == 11
    assert suggestions[0]["parent_share_ratio"] == 60
    cost = result["importable"]["cost"][0]
    assert cost["add_cost"] == 70


def test_g76_policy_aggregation_into_equity_inv():
    """G7-6 仅聚合不一致调整，写入 _g7_g7_6_policy_adj。"""
    from app.services.g7_consol_linkage_service import build_linkage_candidates

    payloads = {
        "G7-4-rows": [{
            "id": "e1",
            "groupType": "associate",
            "investeeName": "联营丙",
            "directHoldingRatio": 30,
            "accountingMethod": "权益法",
        }],
        "G7-2-rows": [{
            "id": "eq1",
            "section": "equity",
            "investeeName": "联营丙",
            "auditedOpeningAmount": 100,
        }],
        "G7-6-rows": {
            "groups": [{
                "investeeName": "联营丙",
                "rows": [
                    {"isConsistent": "不一致", "adjustmentAmount": 40, "policyItem": "收入确认"},
                    {"isConsistent": "一致", "adjustmentAmount": 999, "policyItem": "折旧"},
                    {"isConsistent": "不一致", "adjustmentAmount": 10, "policyItem": "存货"},
                ],
            }],
            "rows": [],
        },
    }
    companies = [{
        "company_code": "A003",
        "company_name": "联营丙",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    equity = result["importable"]["equity_inv"][0]
    assert equity["_g7_g7_6_policy_adj"] == 50
    assert equity["_g7_g7_6_inconsistent_count"] == 2
    assert "G7-6" in result["sources_used"]
    g76_sug = [s for s in result["suggestions"] if s.get("source_sheet") == "G7-6"]
    assert len(g76_sug) == 1
    assert g76_sug[0]["type"] == "accounting_policy_adj"
    assert g76_sug[0]["policy_adj_amount"] == 50


def test_g7_8_step_uses_cumulative_initial_cost_not_single_consideration():
    """G7-8 分步应写入累计初始成本⑤，且合并日回填 info.first_consol_date。"""
    from app.services.g7_consol_linkage_service import build_linkage_candidates

    payloads = {
        "G7-4-rows": [{
            "id": "b1",
            "groupType": "subsidiary",
            "investeeName": "P公司",
            "directHoldingRatio": 80,
            "accountingMethod": "成本法",
        }],
        "G7-2-rows": [{
            "id": "c1",
            "section": "cost",
            "investeeName": "P公司",
            "auditedOpeningAmount": 10,
        }],
        "G7-8-rows": [
            {
                "id": "s1",
                "section": "step",
                "companyId": "p",
                "companyName": "P公司",
                "transactionNo": 1,
                "transactionDate": "2024-01-01",
                "purchaseRatio": 0.01,
                "consideration": 1,
                "netAssetsBookValue": 22,
                "priorInvestmentAdjustments": 22,
            },
            {
                "id": "s2",
                "section": "step",
                "companyId": "p",
                "companyName": "P公司",
                "transactionNo": 2,
                "transactionDate": "2024-06-30",
                "acquisitionDate": "2024-06-30",
                "purchaseRatio": 0.02,
                "consideration": 3,
                "netAssetsBookValue": 44,
                "priorInvestmentAdjustments": 4,
            },
        ],
    }
    companies = [{
        "company_code": "S001",
        "company_name": "P公司",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    cost = result["importable"]["cost"][0]
    # ⑤ = 44 × 0.03 = 1.32；旧逻辑会误用单笔 consideration=1 或 3
    assert cost["add_cost"] == 1.32
    info = result["importable"]["info"][0]
    assert info["first_consol_date"] == "2024-06-30"

def test_g75_financial_aggregation_prefers_audited_and_writes_structured():
    """G7-5 按公司汇总净利润/净资产；已审优先；多行不互相覆盖。"""
    from app.services.g7_consol_linkage_service import (
        _aggregate_g75_financial,
        build_linkage_candidates,
    )

    rows = [
        {
            "investeeName": "联营丁",
            "reportItem": "总资产",
            "currentAmount": 1000,
            "priorAmount": 900,
            "auditStatus": "已审",
        },
        {
            "investeeName": "联营丁",
            "reportItem": "净利润",
            "currentAmount": 50,
            "priorAmount": 40,
            "auditStatus": "未审",
        },
        {
            "investeeName": "联营丁",
            "reportItem": "净利润（归属于母公司）",
            "currentAmount": 80,
            "priorAmount": 70,
            "auditStatus": "已审",
        },
        {
            "investeeName": "联营丁",
            "reportItem": "所有者权益（净资产）",
            "currentAmount": 500,
            "priorAmount": 450,
            "auditStatus": "待确认",
        },
        {
            "investeeName": "联营丁",
            "reportItem": "净资产",
            "currentAmount": 520,
            "priorAmount": 460,
            "auditStatus": "已审",
        },
    ]
    agg = _aggregate_g75_financial(rows)
    assert agg["联营丁"]["net_profit"] == 80
    assert agg["联营丁"]["prior_net_profit"] == 70
    assert agg["联营丁"]["net_assets"] == 520
    assert agg["联营丁"]["prior_net_assets"] == 460
    assert agg["联营丁"]["item_count"] == 5
    assert agg["联营丁"]["unaudited_count"] == 2

    payloads = {
        "G7-4-rows": [{
            "id": "e1",
            "groupType": "associate",
            "investeeName": "联营丁",
            "directHoldingRatio": 30,
            "accountingMethod": "权益法",
        }],
        "G7-2-rows": [{
            "id": "eq1",
            "section": "equity",
            "investeeName": "联营丁",
            "auditedOpeningAmount": 100,
        }],
        "G7-5-rows": {"rows": rows},
    }
    companies = [{
        "company_code": "A004",
        "company_name": "联营丁",
        "parent_code": "P001",
    }]
    result = build_linkage_candidates(payloads, {}, companies=companies)
    equity = result["importable"]["equity_inv"][0]
    assert equity["_g7_reported_net_profit"] == 80
    assert equity["_g7_net_assets"] == 520
    assert equity["_g7_prior_net_profit"] == 70
    assert equity["_g7_g7_5_item_count"] == 5
    assert equity["_g7_g7_5_unaudited_count"] == 2
    assert equity["_g7_g7_5"]["net_profit"] == 80
    assert "G7-5" in result["sources_used"]
