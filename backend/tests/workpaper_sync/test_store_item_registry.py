# -*- coding: utf-8 -*-
"""store item 注册表 Property 5/6/7 判据。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 11/12 · Requirements 3.2/3.4/3.5/8.2
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind
from app.services.workpaper_sync.store_item_registry import (
    STORE_MERGE_REGISTRY,
    StoreItemSpec,
    StoreMergePlan,
    StoreMergePlanNotRegisteredError,
    all_registered_adapter_ids,
    default_payload_for,
    resolve_store_merge_plan,
)


class TestPerItemDefaultNotBlanket:
    """需求 3.2：per-item default 必须按 kind 分派，不得 blanket '[]'。

    事故背书：dict-store 拿列表默认会在 provider 内抛非 domain ValueError，一路冒泡成
    opaque 500（store_projection_response.py:207）。
    """

    def test_rows_default_is_empty_array(self) -> None:
        assert default_payload_for(StoreKind.rows) == "[]"

    def test_dict_default_is_empty_object_not_array(self) -> None:
        # 🔴 这条是事故背书的核心断言：dict 绝不能拿到 "[]"
        assert default_payload_for(StoreKind.dict) == "{}"
        assert default_payload_for(StoreKind.dict) != "[]"

    def test_fixed_text_default_is_empty_string(self) -> None:
        assert default_payload_for(StoreKind.fixed_text) == ""

    def test_per_item_override_takes_precedence_over_kind_default(self) -> None:
        item = StoreItemSpec(item_id="x", kind=StoreKind.rows, default="[{}]")
        assert item.effective_default == "[{}]"

    def test_no_override_falls_back_to_kind_default(self) -> None:
        item = StoreItemSpec(item_id="x", kind=StoreKind.dict)
        assert item.effective_default == "{}"

    def test_dedicated_kind_requires_merge_fn(self) -> None:
        """dedicated 形态必须指名 merge_fn，否则声明本身就该在构造时报错（fail-closed）。"""
        with pytest.raises(ValueError, match="merge_fn"):
            StoreItemSpec(item_id="x", kind=StoreKind.dedicated)  # 缺 merge_fn

    def test_dedicated_kind_with_merge_fn_succeeds(self) -> None:
        item = StoreItemSpec(item_id="x", kind=StoreKind.dedicated, merge_fn="_mirror_x")
        assert item.merge_fn == "_mirror_x"


class TestProperty6ExplicitErrorNotSilentReturn:
    """需求 3.4：注册表未命中必须抛显式错误（含已注册清单），不得静默 return。

    变异反证：改成静默 return ⇒ 必红 —— 那是 D4-35 恒空 / D4-13 正文写不进 OO 的根因形态。
    """

    def test_unregistered_adapter_raises_with_registered_list(self) -> None:
        with pytest.raises(StoreMergePlanNotRegisteredError) as exc_info:
            resolve_store_merge_plan("nonexistent.adapter")
        # 错误消息必须含已注册清单，供排查（不是裸的"未注册"三个字）
        msg = str(exc_info.value)
        assert "d1.notes_receivable_detail" in msg
        assert "nonexistent.adapter" in msg

    def test_error_is_domain_error_not_generic_exception(self) -> None:
        """抛的是 SyncDomainError 子类（可归因为 4xx），不是裸 Exception/KeyError。"""
        assert issubclass(StoreMergePlanNotRegisteredError, SyncDomainError)

    def test_mutation_silent_return_would_hide_missing_registration(self) -> None:
        """反证式：模拟"静默 return None"的错误写法，验证它会让调用方拿到 None 而非报错——
        这正是 D4-35/D4-13 的根因形态；本测试通过证明"正确实现不会退化成这样"。
        """

        def _silently_broken_resolve(adapter_id: str) -> StoreMergePlan | None:
            return STORE_MERGE_REGISTRY.get(adapter_id)  # 变异写法：查不到就返回 None

        # 变异写法对未注册 adapter 静默返回 None（观测不到问题）
        assert _silently_broken_resolve("nonexistent.adapter") is None
        # 而真实实现必须 fail-closed
        with pytest.raises(StoreMergePlanNotRegisteredError):
            resolve_store_merge_plan("nonexistent.adapter")

    def test_mirror_unavailable_reason_also_raises_not_silently_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """命中但标了 `mirror_unavailable_reason` ⇒ 同样显式抛错，不返回一个"看起来正常"的
        plan 让调用方在属性访问处才炸出无来源的 AttributeError。

        🔴 **判据改法**（2026-09-26）：原判据用 b60/g7/h1 三家**恰好坏着**作样本。
        g7/h1 的 merge 门面已于本轮补齐、b60 已正确归类为 `NON_STORE_BACKED_ADAPTERS`
        （契约无 html_store ⇒ 纯 Excel entry，不是缺陷）⇒ 样本消失，原判据必然假红。

        改为**合成 plan** 驱动：机制有效性不该依赖「今天生产代码里恰好还有几家坏着」——
        那正是「判据数的是会被改动的那一侧」这条反复付学费的错法。
        """
        import app.services.workpaper_sync.store_item_registry as REG

        synthetic = dict(REG.STORE_MERGE_REGISTRY)
        synthetic["zz.synthetic_broken"] = StoreMergePlan(
            adapter_id="zz.synthetic_broken",
            provider_module="phase5_d1_notes_receivable",
            mirror_unavailable_reason="合成样本：provider 未提供 merge 门面",
        )
        monkeypatch.setattr(REG, "STORE_MERGE_REGISTRY", synthetic)

        with pytest.raises(StoreMergePlanNotRegisteredError, match="镜像门面不可用"):
            REG.resolve_store_merge_plan("zz.synthetic_broken")
        # 三态入口同样必须抛（不得因为「像 adapter_id」就放行一个坏 plan）
        with pytest.raises(StoreMergePlanNotRegisteredError):
            REG.store_merge_plan_or_skip("zz.synthetic_broken")

    def test_g7_h1_gateways_are_now_available(self) -> None:
        """正向断言本轮修复：g7/h1 的 merge 门面已补齐 ⇒ 能正常 resolve 且 provider 真有该符号。"""
        import importlib

        for adapter_id, attr in (
            ("g7.soe_subsidiary_disclosure", "merge_state_fn"),
            ("h1.disposal_check", "merge_rows_fn"),
        ):
            plan = resolve_store_merge_plan(adapter_id)
            assert not plan.mirror_unavailable_reason
            bridge = importlib.import_module(
                f"app.services.workpaper_sync.{plan.provider_module}"
            )
            fn_name = getattr(plan, attr)
            assert fn_name and hasattr(bridge, fn_name), f"{plan.provider_module} 缺 {fn_name}"

    def test_b60_is_non_store_backed_not_broken(self) -> None:
        """b60 是**形态不同**（纯 Excel entry，契约无 html_store）而非缺陷 ⇒ 走跳过而非抛错。"""
        from app.services.workpaper_sync.store_item_registry import (
            NON_STORE_BACKED_ADAPTERS,
            store_merge_plan_or_skip,
        )

        assert "b60.hour_budget" in NON_STORE_BACKED_ADAPTERS
        assert store_merge_plan_or_skip("b60.hour_budget") is None

    def test_the_eight_delivered_adapters_are_all_registered(self) -> None:
        """8 个已交付 contract 里，除三家 mirror 不可用外，其余 5 家（d1/d3/d4/d5/d6/d7 + d2）
        均能正常 resolve（d2 走独立 bridge，同样登记在注册表内）。
        """
        for adapter_id in (
            "d1.notes_receivable_detail",
            "d2.receivable_detail",
            "d3.prepaid_receipts_detail",
            "d4.revenue_detail",
            "d5.receivables_financing_detail",
            "d6.contract_assets_detail",
            "d7.contract_liabilities_detail",
        ):
            plan = resolve_store_merge_plan(adapter_id)
            assert plan.adapter_id == adapter_id


class TestRegistryStructuralIntegrity:
    def test_all_registered_adapter_ids_is_sorted_and_stable(self) -> None:
        ids = all_registered_adapter_ids()
        assert ids == tuple(sorted(ids))
        assert len(ids) == len(STORE_MERGE_REGISTRY)

    def test_item_lookup_by_id_returns_none_for_missing(self) -> None:
        plan = STORE_MERGE_REGISTRY["d1.notes_receivable_detail"]
        assert plan.item("nonexistent-item-id") is None

    def test_item_lookup_by_id_finds_registered_item(self) -> None:
        plan = STORE_MERGE_REGISTRY["d1.notes_receivable_detail"]
        found = plan.item("D1-cust-rows")
        assert found is not None
        assert found.kind is StoreKind.rows
