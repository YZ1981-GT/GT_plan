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
            }
        ],
        "G7-17-rows": [
            {
                "id": "i1",
                "investeeName": "子公司甲",
                "impairmentAmount": 3,
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
    assert result["importable"]["equity_inv"][0]["open_ratio"] == 30
    assert result["importable"]["equity_inv"][0]["add_income_adj"] == 8
    assert result["importable"]["equity_inv"][0]["add_oci"] == 2
    assert result["importable"]["info"][0]["non_common_ratio"] == 85
    assert result["suggestions"] == []


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
