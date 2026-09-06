"""BP-61-1：行域字段 stable key 必须在载荷期归一化成**实例化**形态。

背景（实测复现，2026-09-06）
────────────────────────────
D2 HTML→Excel 双向回写的 `POST /materialize` 报
``roundtrip_projection_mismatch``：

    staged representation 反读后缺少受管字段
    ['receivable_detail_rows/{row_uuid}/remark']（共 1 个）

报错点与真因相距四个阶段。真因是**约定分裂**，不是「载荷写错了」：

* 契约侧登记的 `stable_field_key` 是**模板**（含 `{row_uuid}` 占位）；
* `Projection.assert_matches_contract` 明文约定「行域 key 允许行实例化 …
  projection 里是具体行值」，`extract`/`merge` 产出的都是实例化 key；
* `plan_managed_writes._emit` 取值用 ``_instantiate(spec.stable_field_key, identity)``
  ⇒ **引擎只消费实例化 key**；
* 但 `build_projection` 直接把 payload 的 key 原样写进 `values` ⇒ 提交模板字面量时
  `projection.get(实例化key)` 永远取不到 ⇒ 一个受管字段都没写进 OOXML。

第一版修复曾试图「拒绝占位 key」，被本文件的测试推翻：`field_by_stable_key`
只认模板，拒绝占位等于把契约唯一可查的写法也拒了，**什么载荷都过不了**。
正解是把两种客户端写法（模板 key + `row_key` / 已实例化 key）都归一成实例化 key。

本文件的判据一律是**行为**（projection 的键形态、是否抛出、error_code），
不是字符串存在 —— 变异结论：删掉归一化调用回退「原样写 values」时
``test_template_key_is_instantiated_into_the_projection`` 立即打红。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workpaper_sync import endpoint_payloads as EP
from app.services.workpaper_sync.adapters.base import _matches_any_template
from app.services.workpaper_sync.contracts import (
    ROW_UUID_PLACEHOLDER,
    ContractSchemaError,
    load_contract,
)

CONTRACT_ID = "d2.receivable_detail"
ROWS = "receivable_detail_rows"
PLACEHOLDER_KEY = f"{ROWS}/{{row_uuid}}/remark"
INSTANTIATED_KEY = f"{ROWS}/dr-mtl5bqmm-mvbu910/remark"
ROW_ID = "dr-mtl5bqmm-mvbu910"
OTHER_ROW_ID = "dr-mtl5bqmm-otherrow"


@pytest.fixture(scope="module")
def contract() -> Any:
    return load_contract(CONTRACT_ID)


def _values(items: dict[str, Any]) -> dict[str, Any]:
    return {"values": items}


class TestTemplateKeyIsInstantiated:
    """契约模板 key + `row_key` ⇒ 实例化写进 `values`，且不丢值、不丢身份。"""

    def test_template_key_is_instantiated_into_the_projection(self, contract: Any) -> None:
        projection = EP.build_projection(
            payload=_values({PLACEHOLDER_KEY: {"value": "双向回写实测", "row_key": ROW_ID}}),
            contract=contract,
        )
        # 🔴 引擎只消费实例化 key：模板字面量留在 values 里等于一个字段都不会写。
        assert INSTANTIATED_KEY in projection.values
        assert PLACEHOLDER_KEY not in projection.values
        value = projection.values[INSTANTIATED_KEY]
        assert value.value == "双向回写实测"
        assert value.row_key == ROW_ID
        assert value.stable_key == INSTANTIATED_KEY

    def test_spec_still_comes_from_the_registered_template(self, contract: Any) -> None:
        """spec 按模板取，不因 payload 写成实例化 key 而绕过契约语义。

        `field_by_stable_key` 是等值匹配 —— 拿实例化 key 去查会
        `ContractSchemaError`。这条判据守的是「spec 必须来自契约唯一真源」。
        """
        template_spec = contract.field_by_stable_key(PLACEHOLDER_KEY)
        projection = EP.build_projection(
            payload=_values({PLACEHOLDER_KEY: {"value": "x", "row_key": ROW_ID}}),
            contract=contract,
        )
        value = projection.values[INSTANTIATED_KEY]
        assert value.value_type is template_spec.value_type
        assert value.mode is template_spec.mode

    def test_row_keys_are_collected_under_the_table_key(self, contract: Any) -> None:
        projection = EP.build_projection(
            payload=_values({PLACEHOLDER_KEY: {"value": "x", "row_key": ROW_ID}}),
            contract=contract,
        )
        assert projection.row_keys[ROWS] == (ROW_ID,)


class TestAlreadyInstantiatedKeyIsAccepted:
    """已实例化 key：内嵌身份与 `row_key` 一致 ⇒ 通过；不一致 ⇒ 报错。"""

    def test_instantiated_key_with_matching_row_key_passes(self, contract: Any) -> None:
        projection = EP.build_projection(
            payload=_values({INSTANTIATED_KEY: {"value": "已实例化", "row_key": ROW_ID}}),
            contract=contract,
        )
        assert INSTANTIATED_KEY in projection.values
        assert projection.values[INSTANTIATED_KEY].value == "已实例化"
        assert projection.values[INSTANTIATED_KEY].row_key == ROW_ID

    def test_instantiated_key_still_needs_row_key_for_three_way_merge(self, contract: Any) -> None:
        """已实例化 key 也必须带 `row_key` —— 这是 AC 6.4 的硬要求，不例外。

        `row_key` 不是「身份冗余」：三方 merge 按 `(stable_field_key, row_key,
        oo_location)` 去重（`endpoint_payloads` 模块头注释第 2 条），projection 的
        `row_keys` 是 merge 域的行集合真源。允许「自带身份就不填」会让同一行的字段
        以无身份形态进入 merge，而 `Projection.assert_matches_contract` 的
        `_matches_any_template(..., has_row_key=...)` 会按身份有无分域匹配 ——
        无身份的行域字段会被判成 contract 未登记。便利性换不回合并正确性。
        """
        with pytest.raises(EP.RepeaterRowKeyRequiredError):
            EP.build_projection(
                payload=_values({INSTANTIATED_KEY: {"value": "自带身份"}}),
                contract=contract,
            )

    def test_instantiated_key_with_mismatched_row_key_is_rejected(self, contract: Any) -> None:
        payload = _values({INSTANTIATED_KEY: {"value": "x", "row_key": OTHER_ROW_ID}})
        with pytest.raises(EP.UninstantiatedRowKeyError) as excinfo:
            EP.build_projection(payload=payload, contract=contract)
        assert excinfo.value.error_code == "projection_row_uuid_not_instantiated"
        message = str(excinfo.value)
        assert ROW_ID in message
        assert OTHER_ROW_ID in message

    def test_instantiated_key_of_unknown_table_is_unknown_not_mismatch(self, contract: Any) -> None:
        """未登记表的实例化 key ⇒ `UnknownStableFieldKeyError`，不冒充身份不一致。"""
        key = f"no_such_table/{ROW_ID}/remark"
        with pytest.raises(EP.UnknownStableFieldKeyError) as excinfo:
            EP.build_projection(
                payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
                contract=contract,
            )
        assert excinfo.value.error_code == "projection_unknown_stable_field_key"

    def test_unregistered_template_key_is_unknown_not_mismatch(self, contract: Any) -> None:
        """带 `row_key` 的未登记占位 key ⇒ 归一化后查不到契约 ⇒ Unknown。

        没有 `row_key` 时先被前置判据拦（`RepeaterRowKeyRequiredError`）—— 本判据
        要验证的是「归一化不会把未登记 key 猜成某个已登记字段」。
        """
        with pytest.raises(EP.UnknownStableFieldKeyError) as excinfo:
            EP.build_projection(
                payload=_values({
                    f"{ROWS}/{{row_uuid}}/no_such_field": {"value": "x", "row_key": ROW_ID}
                }),
                contract=contract,
            )
        assert excinfo.value.error_code == "projection_unknown_stable_field_key"

    def test_unknown_key_is_not_swallowed_by_a_guess(self, contract: Any) -> None:
        """未登记字段名不得被「前缀/后缀巧合」猜成同表的另一个字段（AC 6.20）。

        🔴 这是 fail-open 的守卫判据（不是字符串判据）：若归一化退化成
        `startswith(head) + endswith(tail) + 长度比较`，下列每一条都会静默通过 ——
        `remark_typo` 的尾段以 `remark` 结尾，`aging_audited_over50` 以
        `aging_audited_over5` 结尾。必须逐条断言它们被拒。
        """
        for field_name in (
            "remark_typo",
            "remark_typo2",
            "aging_audited_over50",
            "aging_audited_within1",  # 已登记：对照组，必须能过
        ):
            key = f"{ROWS}/{{row_uuid}}/{field_name}"
            if field_name == "aging_audited_within1":
                projection = EP.build_projection(
                    payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
                    contract=contract,
                )
                assert f"{ROWS}/{ROW_ID}/aging_audited_within1" in projection.values
                continue
            with pytest.raises(EP.UnknownStableFieldKeyError) as excinfo:
                EP.build_projection(
                    payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
                    contract=contract,
                )
            assert excinfo.value.error_code == "projection_unknown_stable_field_key"

    def test_segment_count_mismatch_is_rejected(self, contract: Any) -> None:
        """分段数不同的 key 不得被归一化（与 `_matches_any_template` 口径对齐）。"""
        for key in (
            f"{ROWS}/{ROW_ID}/remark/more",
            f"{ROWS}/{ROW_ID}",
        ):
            with pytest.raises(EP.UnknownStableFieldKeyError):
                EP.build_projection(
                    payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
                    contract=contract,
                )

    def test_matching_is_segment_level_not_prefix_suffix(self, contract: Any) -> None:
        """归一化的匹配必须**段级**，不是「前缀 + 后缀 + 长度」（fail-open 判据）。

        🔴 行为判据，不做字符串断言。对四条 key 逐一验证「段级判据」与「前后缀 +
        长度判据」的结论差异 —— 这是被拦下的缺口：

        * `remark`：契约已登记 ⇒ 两条判据都 True（无差别样本）；
        * `remark_typo` / `aging_audited_over50`：契约**未登记**
          ⇒ 段级判据 False，而「段前缀重合」判据 True（`remark_typo`.startswith
          (`remark`)、`aging_audited_over50`.startswith(`aging_audited_over5`)）。
          若归一化用后者，这两条会被静默挂到错误的契约字段上，错列且无报错。

        断言形态：`contract_verdict`（`_matches_any_template`，段级）必须与
        `segment_verdict`（`_segments_match` 对契约全量模板，段级）逐条一致；
        而 `regex_verdict` 在未登记样本上必须给出**相反**结论。
        """
        templates = [
            (s.stable_field_key, s.row_scoped)
            for s in contract.all_fields()
            if s.row_scoped
        ]
        # 变异护栏：把「段级等值」换成「段前缀重合」（占位段通配 + 其余段
        # startswith）。这个变体在 `remark_typo` 上会命中 `remark` 的模板 ——
        # 若归一化用后者，字段会被挂到错误的契约列上，且无报错。
        plain_templates = {t for t, _scoped in templates}
        variant_hit = EP._prefix_suffix_match_all(plain_templates, f"{ROWS}/{ROW_ID}/remark_typo")
        assert variant_hit is True, "变异判据对 remark_typo 必须命中（否则本护栏失去意义）"
        # 而段级判据对同一个 key 必须不命中 —— 两条口径的分叉点是守卫的价值所在
        assert EP._segments_match_all(plain_templates, f"{ROWS}/{ROW_ID}/remark_typo") is False

        for key, expected in (
            (f"{ROWS}/{ROW_ID}/remark", True),
            (f"{ROWS}/{ROW_ID}/remark_typo", False),
            (f"{ROWS}/{ROW_ID}/aging_audited_over50", False),
        ):
            contract_verdict = _matches_any_template(
                key, templates, has_row_key=True
            )
            assert contract_verdict is expected, key
            # 段级判据跑在契约全量模板上，结论必须与契约比对完全一致
            assert EP._segments_match_all(plain_templates, key) is contract_verdict, key
            # 前后缀判据跑在同一批模板上；未登记样本必须给出错误（fail-open）结论
            regex_verdict = EP._prefix_suffix_match_all(plain_templates, key)
            assert regex_verdict is True, key
            if expected is False:
                assert regex_verdict is not contract_verdict, key




class TestSameRowDuplicateFormsCollapse:
    """模板 key 与实例化 key 同批指向同一行 ⇒ 归一成一条，不丢值、不重复计数。"""

    def test_duplicate_forms_collapse_to_one_instantiated_entry(self, contract: Any) -> None:
        payload = _values({
            PLACEHOLDER_KEY: {"value": "占位写法", "row_key": ROW_ID},
            INSTANTIATED_KEY: {"value": "实例化写法", "row_key": ROW_ID},
        })
        projection = EP.build_projection(payload=payload, contract=contract)
        assert projection.values[INSTANTIATED_KEY].value == "实例化写法"
        assert len(projection.values) == 1
        assert projection.row_keys[ROWS].count(ROW_ID) == 2

    def test_two_rows_collapse_independently(self, contract: Any) -> None:
        """两行的同一字段各提交一次 ⇒ 两条独立实例化 key，行集合完整。"""
        other = f"{ROWS}/{OTHER_ROW_ID}/remark"
        payload = _values({
            f"{ROWS}/{{row_uuid}}/remark": {"value": "v1", "row_key": ROW_ID},
            other: {"value": "v2", "row_key": OTHER_ROW_ID},
        })
        projection = EP.build_projection(payload=payload, contract=contract)
        assert projection.values[INSTANTIATED_KEY].value == "v1"
        assert projection.values[other].value == "v2"
        assert len(projection.values) == 2


class TestRowScopedCoverage:
    """逐字段遍历：契约声明的**每一个**行域字段都必须实例化成功。

    只测 `remark` 一个字段会在「归一化按字段名硬编码」时静默假绿。
    """

    def test_every_row_scoped_template_key_instantiates(self, contract: Any) -> None:
        template_keys = sorted(
            spec.stable_field_key
            for spec in contract.all_fields()
            if spec.row_scoped
        )
        assert template_keys, "契约里没有行域字段"
        for key in template_keys:
            projection = EP.build_projection(
                payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
                contract=contract,
            )
            expected = key.replace(ROW_UUID_PLACEHOLDER, ROW_ID)
            assert expected in projection.values, f"未实例化: {key}"
            assert ROW_UUID_PLACEHOLDER not in expected
            assert projection.values[expected].row_key == ROW_ID

    def test_every_row_scoped_field_requires_a_row_identity(self, contract: Any) -> None:
        """行域 key 缺行身份 ⇒ 必须报错，不能静默按无身份字段处理。

        `build_projection` 的前置判据按**表名前缀**先拦截（fail fast，错误信息里
        直接点出字段名）；即使前置判据被删，`_resolve_stable_key` 也会按占位符
        兜住 —— 两条路径任一在位，本判据都不会假绿。
        """
        template_keys = sorted(
            spec.stable_field_key
            for spec in contract.all_fields()
            if spec.row_scoped
        )
        for key in template_keys:
            with pytest.raises(EP.RepeaterRowKeyRequiredError):
                EP.build_projection(
                    payload=_values({key: {"value": "x"}}),
                    contract=contract,
                )

    def test_contract_has_only_row_scoped_fields(self, contract: Any) -> None:
        """d2.receivable_detail 全部字段都是行域 —— 记录这个事实，防止误读。

        本契约 39 个字段无一个非行域；非行域字段的归一化路径由
        ``TestResolutionShape`` 用另一个契约覆盖。
        """
        assert contract.all_fields(), "契约无字段"
        assert all(spec.row_scoped for spec in contract.all_fields())


class TestResolutionShape:
    """`_resolve_stable_key` 的返回形态与错误家族 —— 归一化是唯一收敛点。"""

    def test_resolution_carries_both_forms(self, contract: Any) -> None:
        templates = {
            spec.stable_field_key for spec in contract.all_fields() if spec.row_scoped
        }
        resolved = EP._resolve_stable_key(
            PLACEHOLDER_KEY, contract=contract, row_key=ROW_ID, row_scoped_templates=templates
        )
        assert resolved.resolved_key == INSTANTIATED_KEY
        assert resolved.template_key == PLACEHOLDER_KEY

        resolved_back = EP._resolve_stable_key(
            INSTANTIATED_KEY,
            contract=contract,
            row_key=ROW_ID,
            row_scoped_templates=templates,
        )
        assert resolved_back.resolved_key == INSTANTIATED_KEY
        assert resolved_back.template_key == PLACEHOLDER_KEY


class TestNonRowScopedFieldsAreUnaffected:
    """非行域字段不带占位，归一化不得改变它们的 key 或要求 `row_key`。"""

    @pytest.mark.parametrize(
        "contract_id",
        [
            "b60.hour_budget",
            "g7.soe_subsidiary_disclosure",
        ],
    )
    def test_non_row_scoped_key_passes_without_row_key(self, contract_id: str) -> None:
        contract = load_contract(contract_id)
        non_row = [
            spec.stable_field_key
            for spec in contract.all_fields()
            if not spec.row_scoped
        ]
        if not non_row:
            pytest.skip(f"{contract_id} 无非行域字段")
        key = non_row[0]
        assert ROW_UUID_PLACEHOLDER not in key
        projection = EP.build_projection(
            payload=_values({key: {"value": "非行域值"}}),
            contract=contract,
        )
        assert key in projection.values
        assert projection.values[key].row_key is None

    def test_non_row_scoped_key_ignores_a_stale_row_key(self) -> None:
        """残留的 `row_key` 不得让非行域字段被误判成行域。

        客户端复用同一个 payload 构造器时会顺手带上 `row_key`；非行域字段
        必须原样通过，不能被占位判据牵连。
        """
        contract = load_contract("b60.hour_budget")
        non_row = [spec for spec in contract.all_fields() if not spec.row_scoped]
        if not non_row:
            pytest.skip("b60.hour_budget 无非行域字段")
        key = non_row[0].stable_field_key
        projection = EP.build_projection(
            payload=_values({key: {"value": "x", "row_key": ROW_ID}}),
            contract=contract,
        )
        assert key in projection.values


class TestErrorFamilyIsDisjoint:
    """三个载荷期错误必须两两可分辨 —— 共用类型会让其中两个被遮蔽。"""

    def test_three_error_codes_are_pairwise_distinct(self) -> None:
        codes = {
            EP.ProjectionPayloadError.error_code,
            EP.UnknownStableFieldKeyError.error_code,
            EP.RepeaterRowKeyRequiredError.error_code,
            EP.UninstantiatedRowKeyError.error_code,
        }
        assert len(codes) == 4
        assert EP.UninstantiatedRowKeyError.error_code == "projection_row_uuid_not_instantiated"

    def test_missing_row_key_uses_its_own_error_code(self, contract: Any) -> None:
        """模板 key + 缺 `row_key` ⇒ 报的是身份缺失，不是身份不一致。

        两者的运维处置不同（补身份 vs 对齐 key），混淆会让调用方按错的方式修。
        """
        with pytest.raises(EP.RepeaterRowKeyRequiredError) as excinfo:
            EP.build_projection(
                payload=_values({PLACEHOLDER_KEY: {"value": "x"}}),
                contract=contract,
            )
        assert excinfo.value.error_code == "projection_repeater_row_key_required"

    def test_mismatch_is_not_the_unknown_key_error(self) -> None:
        assert not issubclass(
            EP.UninstantiatedRowKeyError, EP.UnknownStableFieldKeyError
        )
        assert not issubclass(
            EP.UnknownStableFieldKeyError, EP.UninstantiatedRowKeyError
        )
        assert not issubclass(
            EP.UninstantiatedRowKeyError, EP.RepeaterRowKeyRequiredError
        )


class TestMutationResistance:
    """变异检验的落地：归一化被删弱时本文件必须打红。

    变异 1（`build_projection` 回退成「原样写 values」）
        ⇒ ``test_template_key_is_instantiated_into_the_projection`` 红；
    变异 2（spec 改按实例化 key 查契约）
        ⇒ ``test_spec_still_comes_from_the_registered_template`` 红；
    变异 3（归一化按字段名硬编码，只为 remark 生效）
        ⇒ ``test_every_row_scoped_template_key_instantiates`` 红；
    变异 4（删掉内嵌身份一致性校验）
        ⇒ ``test_instantiated_key_with_mismatched_row_key_is_rejected`` 红；
    变异 5（改成 fail-open，未登记 key 直接放行）
        ⇒ ``test_instantiated_key_of_unknown_table_is_unknown_not_mismatch`` 红。
    """

    def test_the_gate_source_is_present_in_the_payload_builder(self) -> None:
        """结构判据：归一化必须真的挂在 ``build_projection`` 函数体内。

        字符串判据本文件其余部分刻意不用（行为判据优先），这里只用于**定位**：
        证明归一化挂在正确的函数里，而不是挂在模块级常量上自证。
        """
        import inspect

        source = inspect.getsource(EP.build_projection)
        assert "_resolve_stable_key" in source
        assert "field_by_stable_key(resolved.template_key)" in source
        assert "resolved.resolved_key" in source

    def test_contract_lookup_is_equality_only(self) -> None:
        """回归护栏：`field_by_stable_key` 只认模板 —— 这是必须走模板取 spec 的原因。"""
        contract_lookup = load_contract(CONTRACT_ID)
        with pytest.raises(ContractSchemaError):
            contract_lookup.field_by_stable_key(INSTANTIATED_KEY)


class TestSegmentLevelMatcherIsTheOnlyOne:
    """M7 变异护栏：段级判据必须是 ``_resolve_stable_key`` 的**唯一**匹配口径。

    上一轮变异检验里 M7（把段级等值换成「段前缀重合」）被判为 GREEN —— 那不是守卫
    缺口的证据，而是**下游兜底**的证据：段前缀判据确实会让 `remark_typo` 命中
    `remark` 的模板，但紧接着的内嵌身份一致性检查（``embedded != row_key``）把它拦下，
    因为段前缀重合必然使 key 变长、``embedded`` 变成 `dr-xxx/rema` 而不再等于
    `row_key`。所以 M7 从**外部行为**看不出来。

    这仍然是一个真实的覆盖缺口：段级判据本身没有任何直接守卫，若日后身份一致性检查
    被弱化（例如为了兼容另一类客户端写法放宽），段前缀重合会立刻变成静默挂错字段。
    因此这里把「两判据必须逐模板分叉」固化成可测投影 —— 直接对**判定函数本身**断言，
    而不是绕道 ``build_projection`` 的行为。

    变异 M7 若被引入，
    ``test_segment_level_and_prefix_suffix_criterion_disagree_on_every_ambiguous_key``
    会打红（因为生产判据退化后，`EP._segments_match` 的行为判据与
    ``_prefix_suffix_match_all`` 不再分叉）。
    """

    @pytest.fixture(scope="class")
    def templates(self) -> set[str]:
        contract = load_contract(CONTRACT_ID)
        return {spec.stable_field_key for spec in contract.all_fields() if spec.row_scoped}

    def test_segment_level_and_prefix_suffix_criterion_disagree_on_every_ambiguous_key(
        self, templates: set[str]
    ) -> None:
        """对契约里**每一个**行域模板构造段前缀重合变体，两判据结论必须相反。

        构造方式：取模板的最后一节（字段名），在其后追加一个**新的字符**（不删除原字符），
        得到段前缀重合但段级不等价的 key。这类 key 对任何非平凡字段名都存在，因此
        遍历 39 个模板逐一断言，而不是只挑 `remark` 一个 —— 后者会在「判据只对 remark
        生效」时假绿。
        """
        assert len(templates) >= 10, f"行域模板过少（{len(templates)}），覆盖面不足"
        checked = 0
        for template in sorted(templates):
            parts = template.split("/")
            table, field = parts[0], parts[-1]
            # 段前缀重合变体：字段名 + 一个后缀字符。段数不变、段前缀重合、段级不等价。
            mutated_field = field + "x"
            key = f"{table}/{ROW_ID}/{mutated_field}"

            assert not EP._template_matches(template, key), (
                f"段级判据必须拒绝段前缀重合: {template!r} vs {key!r}"
            )
            assert EP._prefix_suffix_match_all({template}, key), (
                f"反例判据必须接受段前缀重合，否则本测试无分叉点: {template!r} vs {key!r}"
            )
            checked += 1
        assert checked >= 10, f"实际分叉点仅 {checked} 个，覆盖面不足"

    def test_production_resolver_uses_the_segment_level_criterion(self, templates: set[str]) -> None:
        """段前缀重合 key 经生产路径必须 fail closed（报 Unknown），不能被静默归一。

        这是 M7 从**外部行为**侧的第二道守卫：即使下游身份检查兜不住（例如未来为了
        兼容某类客户端把内嵌身份校验放宽），这里也会打红。
        """
        contract = load_contract(CONTRACT_ID)
        for template in sorted(templates):
            parts = template.split("/")
            table, field = parts[0], parts[-1]
            key = f"{table}/{ROW_ID}/{field}x"
            with pytest.raises(EP.UnknownStableFieldKeyError):
                EP._resolve_stable_key(
                    key,
                    contract=contract,
                    row_key=ROW_ID,
                    row_scoped_templates=templates,
                )

    def test_the_divergence_is_not_paper_thin(self, templates: set[str]) -> None:
        """两判据的差异必须是**逐模板普遍**的，不是某几个特殊字段名的巧合。

        若 39 个模板里只有极少数出现分叉，说明段前缀重合在实际契约里几乎不触发，
        M7 的危害被高估；反之若全部触发，则段级判据是必需的。这里记录实测分布，
        防止后人按「反正不会碰到」把判据弱化。
        """
        contract = load_contract(CONTRACT_ID)
        divergent = 0
        total = 0
        for template in sorted(templates):
            parts = template.split("/")
            table, field = parts[0], parts[-1]
            key = f"{table}/{ROW_ID}/{field}x"
            total += 1
            if (
                EP._prefix_suffix_match_all(templates, key)
                and not EP._segments_match_all(templates, key)
            ):
                divergent += 1
        assert divergent == total, (
            f"段前缀判据在 {total - divergent}/{total} 个模板上未与段级判据分叉 —— "
            "要么两判据口径已趋同（段级判据被弱化），要么反例判据被改错"
        )
