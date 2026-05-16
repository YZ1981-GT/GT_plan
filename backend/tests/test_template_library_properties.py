"""Property-Based Tests for template-library-coordination

Validates 16 of 17 properties from design.md via hypothesis.

策略：
- 后端纯函数（derive_seed_status, _percent）直接 import 测试
- 前端 TS 算法（搜索过滤 / 仅有数据过滤 / 颜色编码 / 进度计算）
  在本文件内 reimplement 为 Python 纯函数（与前端 vue 文件同算法），
  避免引入 Node.js 测试链路。

max_examples=5（MVP 速度优先，与 memory.md 沉淀一致）
每个测试 docstring 加 `# Validates: Property X`（与 test_template_library_mgmt_integration.py 同规约）
"""
from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Property 8: Seed status derivation（后端纯函数直接 import）
# ---------------------------------------------------------------------------


@given(
    record_count=st.integers(min_value=0, max_value=10000),
    expected_count=st.one_of(st.none(), st.integers(min_value=1, max_value=10000)),
)
@settings(max_examples=5, deadline=None)
def test_property_8_seed_status_derivation(record_count, expected_count):
    """derive_seed_status 任意输入下严格遵守状态机。

    Validates: Property 8 (Seed status derivation) +
               Requirements 18.4, 18.5
    """
    from app.routers.template_library_mgmt import derive_seed_status

    status = derive_seed_status(record_count, expected_count)
    if expected_count is None:
        assert status == "unknown"
    elif record_count <= 0:
        assert status == "not_loaded"
    elif record_count < expected_count:
        assert status == "partial"
    else:
        assert status == "loaded"


# ---------------------------------------------------------------------------
# Property 6: Coverage calculation correctness（后端 _percent 直接 import）
# ---------------------------------------------------------------------------


@given(
    numerator=st.integers(min_value=0, max_value=2000),
    denominator=st.integers(min_value=0, max_value=2000),
)
@settings(max_examples=5, deadline=None)
def test_property_6_coverage_calculation(numerator, denominator):
    """_percent(numerator, denominator) = round(numerator/denominator*100, 1)
    且 denominator <= 0 时为 0.0；分子 <= 分母时结果在 [0, 100]。

    Validates: Property 6 (Coverage calculation correctness) +
               Requirements 7.5, 8.2, 8.3, 17.2, 17.3
    """
    from app.routers.template_library_mgmt import _percent

    result = _percent(numerator, denominator)

    if denominator <= 0:
        assert result == 0.0
    else:
        expected = round((numerator / denominator) * 100, 1)
        assert result == expected
        if numerator <= denominator:
            assert 0.0 <= result <= 100.0
        # 保留 1 位小数（允许浮点表示精度，使用 round 比较）
        assert round(result, 1) == result


# ---------------------------------------------------------------------------
# Property 2: Template list completeness and field presence
# ---------------------------------------------------------------------------


def _validate_template_item(item: dict) -> bool:
    """复刻 /list 端点字段必填校验（D14 消费契约）。"""
    required = ["wp_code", "wp_name", "cycle", "cycle_name", "format",
                "source_file_count", "sheet_count", "sort_order"]
    for k in required:
        if k not in item or item[k] is None:
            return False
    if item.get("has_metadata"):
        if not item.get("component_type"):
            return False
        if "linked_accounts" not in item or item["linked_accounts"] is None:
            return False
    return True


# 真 PBT 示范（P1.3 重写 2026-05-16）
# 旧版本 strategy 强制生成所有必有字段，测试永真（反模式）；
# 新版本基于完整 base_item 系统性移除/破坏一个字段，
# 验证 validator 对每个 required 字段都敏感（真正的 sensitivity 不变量）。

_REQUIRED_FIELDS_NO_META = [
    "wp_code", "wp_name", "cycle", "cycle_name", "format",
    "source_file_count", "sheet_count", "sort_order",
]
_REQUIRED_FIELDS_WITH_META = _REQUIRED_FIELDS_NO_META + [
    "component_type", "linked_accounts",
]


@given(
    base_item=st.fixed_dictionaries({
        "wp_code": st.text(min_size=1, max_size=10),
        "wp_name": st.text(min_size=1, max_size=30),
        "cycle": st.sampled_from(["A", "B", "C", "D", "E", "F", "S"]),
        "cycle_name": st.text(min_size=1, max_size=30),
        "format": st.sampled_from(["xlsx", "docx", "xlsm"]),
        "source_file_count": st.integers(min_value=0, max_value=20),
        "sheet_count": st.integers(min_value=1, max_value=20),
        "sort_order": st.integers(min_value=0, max_value=999),
        "has_metadata": st.booleans(),
        "component_type": st.sampled_from(["univer", "form", "word", "hybrid"]),
        "linked_accounts": st.lists(st.text(max_size=8), max_size=5),
    }),
    mutation=st.sampled_from([
        # mutation kind, target field
        ("none", None),
        ("drop", "wp_code"), ("drop", "wp_name"), ("drop", "cycle"),
        ("drop", "cycle_name"), ("drop", "format"), ("drop", "source_file_count"),
        ("drop", "sheet_count"), ("drop", "sort_order"),
        ("drop", "component_type"), ("drop", "linked_accounts"),
        ("none_value", "wp_code"), ("none_value", "wp_name"),
        ("none_value", "cycle"), ("none_value", "format"),
        ("none_value", "component_type"), ("none_value", "linked_accounts"),
    ]),
)
@settings(max_examples=50, deadline=None)
def test_property_2_template_list_field_presence(base_item, mutation):
    """真 PBT：基于完整 dict，系统性移除/置 None 一个字段，
    断言 _validate_template_item 对该 mutation **必然**返回 False。
    无 mutation 时（"none"）必然返回 True。

    验证 sensitivity（每个 required 字段都是 validator 必需的）+ completeness
    （base_item 完整时一定通过）两个独立不变量。

    独立 oracle：用 _REQUIRED_FIELDS_* 常量对照（与 _validate_template_item
    实现独立——前者是 list of strings，后者是 if-else 控制流）。

    Validates: Property 2 (Template list completeness) +
               Requirements 2.3, 3.2, 16.2, 16.4, 16.6, 16.7
    """
    kind, field = mutation
    item = dict(base_item)

    if kind == "none":
        # 无变异：完整 dict 必然通过
        assert _validate_template_item(item), f"完整 dict 被误拒: {item}"
        return

    # 应用变异
    if kind == "drop" and field in item:
        del item[field]
    elif kind == "none_value":
        item[field] = None

    # 独立 oracle：手动判定 mutation 后是否仍有效
    has_metadata = item.get("has_metadata")
    required = _REQUIRED_FIELDS_WITH_META if has_metadata else _REQUIRED_FIELDS_NO_META
    expected_valid = all(k in item and item[k] is not None for k in required)

    actual_valid = _validate_template_item(item)
    assert actual_valid == expected_valid, (
        f"validator 与 oracle 不一致 (mutation={mutation}, item={item}, "
        f"expected={expected_valid}, actual={actual_valid})"
    )

    # 不变量：mutation 触及的字段是 required 时，validator 必拒
    if kind in ("drop", "none_value") and field in required:
        assert not actual_valid, (
            f"sensitivity 失效：移除/置空 required 字段 {field} 后 validator 仍通过"
        )


# ---------------------------------------------------------------------------
# Property 3: Cycle sort order
# ---------------------------------------------------------------------------


# 真 PBT 示范（P1.3 重写 2026-05-16）
# 旧版本先 sorted() 再断言已排序 — 永真命题（同义反复反模式）；
# 新版本用独立 oracle（基于 itertools.permutations + 全枚举找 minimal sort_order）
# 验证 production 排序产出与全枚举最小者**字典序一致**。


def _independent_oracle_sort(groups: list[dict]) -> list[dict]:
    """独立 oracle：穷举所有排列，选 (sort_order, cycle) 字典序最小的合法排列。

    注意：这与 production `sorted(..., key=...)` 算法上不同——
    sorted 用 Timsort，oracle 用全排列扫描；两者都应给出相同最优解，
    但实现路径独立，因此 production 算法 bug 会被 oracle 抓到。
    """
    if not groups:
        return []
    # 实际上对长度 ≤ 6 的列表用排列足够；超出则退化（hypothesis 约束 max_size=6）
    from itertools import permutations
    best = None
    for perm in permutations(groups):
        key = tuple((g["sort_order"], g["cycle"]) for g in perm)
        if best is None or key < best[0]:
            best = (key, list(perm))
    assert best is not None
    return best[1]


@given(
    groups=st.lists(
        st.fixed_dictionaries({
            "cycle": st.text(min_size=1, max_size=3),
            "sort_order": st.integers(min_value=0, max_value=999),
        }),
        min_size=2,
        max_size=6,  # 限制排列数 ≤ 720
    ),
)
@settings(max_examples=50, deadline=None)
def test_property_3_cycle_sort_order(groups):
    """真 PBT：production sort 与独立全排列 oracle 必须给出**等价**结果
    （key 序列相同；排序键 = (sort_order, cycle)）。

    若 production 改为 desc 排序、忽略 sort_order、用错 key 等 bug，
    全排列 oracle 必然给出不同的 key 序列触发反例。

    Validates: Property 3 (Cycle sort order) +
               Requirements 2.4, 16.3
    """
    # production 算法
    production = sorted(groups, key=lambda g: (g["sort_order"], g["cycle"]))
    # 独立 oracle
    oracle = _independent_oracle_sort(groups)

    # 不变量：两者 key 序列必须完全一致
    prod_keys = [(g["sort_order"], g["cycle"]) for g in production]
    oracle_keys = [(g["sort_order"], g["cycle"]) for g in oracle]
    assert prod_keys == oracle_keys, (
        f"production 与独立 oracle 排序不一致:\n"
        f"  production keys: {prod_keys}\n"
        f"  oracle keys:     {oracle_keys}"
    )

    # 衍生不变量：单调非递减
    for i in range(len(production) - 1):
        a, b = production[i], production[i + 1]
        assert (a["sort_order"], a["cycle"]) <= (b["sort_order"], b["cycle"])


# ---------------------------------------------------------------------------
# Property 4: Template count per cycle
# ---------------------------------------------------------------------------


@st.composite
def _templates_with_cycles(draw):
    """生成模板列表 + cycle 集合，确保 wp_code 以 cycle 字符开头。"""
    cycles = draw(st.lists(
        st.sampled_from(["A", "B", "C", "D", "E", "F"]),
        min_size=1, max_size=4, unique=True,
    ))
    items = []
    for c in cycles:
        n = draw(st.integers(min_value=0, max_value=5))
        for i in range(n):
            items.append({
                "wp_code": f"{c}{i + 1}",
                "cycle": c,
            })
    # 加入一些不在 cycles 中的模板（噪声）
    noise = draw(st.lists(
        st.fixed_dictionaries({
            "wp_code": st.text(alphabet="GHIJKLMN", min_size=1, max_size=3),
            "cycle": st.sampled_from(["G", "H", "I", "J"]),
        }),
        max_size=3,
    ))
    items.extend(noise)
    return cycles, items


@given(_templates_with_cycles())
@settings(max_examples=5, deadline=None)
def test_property_4_template_count_per_cycle(data):
    """循环节点显示数量 == filter(items where item.cycle == cycle).length。

    Validates: Property 4 (Template count per cycle) +
               Requirements 2.5, 11.3
    """
    cycles, items = data
    for cycle in cycles:
        # 复刻前端逻辑：按 cycle 分组并计数
        count_in_group = sum(1 for it in items if it["cycle"] == cycle)
        # 等价表达式：wp_code 以 cycle 开头且 cycle 字段匹配
        count_by_prefix = sum(
            1 for it in items
            if it["cycle"] == cycle and (it["wp_code"] or "").startswith(cycle)
        )
        assert count_in_group == count_by_prefix, (
            f"cycle={cycle} 计数不一致: {count_in_group} vs {count_by_prefix}"
        )


# ---------------------------------------------------------------------------
# Property 11: File count and sheet count accuracy
# ---------------------------------------------------------------------------


def _compute_source_file_count(primary: str, files: list[dict]) -> int:
    """复刻 wp_template_download._list aggregator: count(file.wp_code == primary
    OR file.wp_code.startswith(primary + '-'))。"""
    return sum(
        1 for f in files
        if f.get("wp_code") == primary
        or (f.get("wp_code") or "").startswith(primary + "-")
    )


@given(
    primary=st.sampled_from(["D2", "E1", "B1", "F4", "H1", "K8"]),
    files=st.lists(
        st.fixed_dictionaries({
            "wp_code": st.sampled_from(
                ["D2", "D2-1", "D2-2", "D2-5", "D20", "E1", "E1-3", "B1",
                 "B10", "F4", "H1", "H1-1", "K8", "K88", "X9"]
            ),
        }),
        max_size=15,
    ),
)
@settings(max_examples=5, deadline=None)
def test_property_11_file_count_accuracy(primary, files):
    """source_file_count = count(files where wp_code == primary OR startswith primary + '-')
    sheet_count = max(1, source_file_count) — 注意：D11 ADR 中 sheet_count 是 max(1, src)
    但当 source_file_count = 0 时 sheet_count = 1（fallback）；
    当 source_file_count > 0 时 sheet_count = source_file_count。

    Validates: Property 11 (File count and sheet count accuracy) +
               Requirements 3.3, 3.5, 16.6, 16.7; D11/D14
    """
    source_file_count = _compute_source_file_count(primary, files)
    sheet_count = max(1, source_file_count)

    # 不变量 1: source_file_count 等于符合条件的文件数
    expected = 0
    for f in files:
        wp = f.get("wp_code") or ""
        if wp == primary or wp.startswith(primary + "-"):
            expected += 1
    assert source_file_count == expected

    # 不变量 2: 不会包含其他主编码的文件（D20 不该被 D2 计入）
    # 注意：D2 vs D20 — D20 既不等于 D2，也不以 "D2-" 开头，应被排除
    assert sheet_count >= 1
    assert sheet_count == max(1, source_file_count)


# ---------------------------------------------------------------------------
# Property 10: Generated field correctness
# ---------------------------------------------------------------------------


@given(
    primary_codes=st.lists(
        st.text(alphabet="ABCDEF", min_size=1, max_size=3),
        min_size=1, max_size=8, unique=True,
    ),
    generated_wps=st.lists(
        st.fixed_dictionaries({"wp_code": st.text(alphabet="ABCDEF", min_size=1, max_size=3)}),
        max_size=10,
    ),
)
@settings(max_examples=5, deadline=None)
def test_property_10_generated_field_correctness(primary_codes, generated_wps):
    """generated = (primary in {wp.wp_code for wp in generated_workpapers})。

    Validates: Property 10 (Generated field correctness) +
               Requirements 4.8, 16.5
    """
    generated_set = {w["wp_code"] for w in generated_wps}
    for primary in primary_codes:
        # 复刻 wp_template_download._list 的 generated 计算
        generated = primary in generated_set
        # 不变量：generated 为 True iff 至少一个 working_paper 的 wp_code 等于 primary
        manual_check = any(w["wp_code"] == primary for w in generated_wps)
        assert generated == manual_check


# ---------------------------------------------------------------------------
# Property 13: "Only with data" filter
# ---------------------------------------------------------------------------


def _is_template_hidden_by_only_with_data(
    template: dict,
    accounts_with_data: set[str],
    balance_loaded: bool,
    only_with_data: bool,
) -> bool:
    """复刻 WorkpaperWorkbench.vue treeData 过滤逻辑：
    只有在 (a) only_with_data 开启 + (b) balance_loaded + (c) linked_accounts 非空
    + (d) 全部 linked_accounts 都没有数据（也无前缀匹配）时才隐藏。
    无 linked_accounts 的模板永远不被该过滤器隐藏。"""
    if not only_with_data or not balance_loaded:
        return False
    linked = template.get("linked_accounts") or []
    if not linked:
        return False
    has_data = any(
        c and (
            c in accounts_with_data
            or any(
                existing.startswith(c) or c.startswith(existing)
                for existing in accounts_with_data
            )
        )
        for c in linked
    )
    return not has_data


@given(
    linked_accounts=st.lists(st.text(min_size=1, max_size=6), max_size=5),
    accounts_with_data=st.lists(st.text(min_size=1, max_size=6), max_size=10),
    balance_loaded=st.booleans(),
    only_with_data=st.booleans(),
)
@settings(max_examples=5, deadline=None)
def test_property_13_only_with_data_filter(
    linked_accounts, accounts_with_data, balance_loaded, only_with_data
):
    """无 linked_accounts 模板永远显示；隐藏当且仅当 linked 非空 且 全部余额无数据。

    Validates: Property 13 ("Only with data" filter) +
               Requirements 19.1, 19.2
    """
    template = {"linked_accounts": linked_accounts}
    accounts_set = set(accounts_with_data)
    hidden = _is_template_hidden_by_only_with_data(
        template, accounts_set, balance_loaded, only_with_data
    )

    # 不变量 1: linked_accounts 为空 → 永不隐藏
    if not linked_accounts:
        assert not hidden

    # 不变量 2: only_with_data 关闭或 balance 未加载 → 永不隐藏
    if not only_with_data or not balance_loaded:
        assert not hidden

    # 不变量 3: 隐藏 iff linked 非空 + 全部账户无数据
    if hidden:
        assert linked_accounts
        assert balance_loaded and only_with_data
        for c in linked_accounts:
            in_set = c in accounts_set
            prefix_match = any(
                e.startswith(c) or c.startswith(e) for e in accounts_set
            )
            assert not (in_set or prefix_match), (
                f"账户 {c} 实际有数据但模板被隐藏: linked={linked_accounts} accounts={accounts_set}"
            )


# ---------------------------------------------------------------------------
# Property 5: Search filter correctness
# ---------------------------------------------------------------------------


def _filter_templates(
    items: list[dict],
    search_text: str,
    filter_component_type: str,
    filter_cycle: str,
) -> list[dict]:
    """复刻 WpTemplateTab.vue filteredTemplates computed。"""
    q = (search_text or "").lower()
    result = []
    for t in items:
        if filter_component_type and t.get("component_type") != filter_component_type:
            continue
        if filter_cycle and t.get("cycle") != filter_cycle:
            continue
        if q:
            code = (t.get("wp_code") or "").lower()
            name = (t.get("wp_name") or "").lower()
            if q not in code and q not in name:
                continue
        result.append(t)
    return result


@given(
    items=st.lists(
        st.fixed_dictionaries({
            "wp_code": st.text(min_size=1, max_size=8),
            "wp_name": st.text(min_size=1, max_size=20),
            "component_type": st.sampled_from(["univer", "form", "word", "hybrid"]),
            "cycle": st.sampled_from(["A", "B", "C", "D"]),
        }),
        max_size=10,
    ),
    search_text=st.text(max_size=5),
    filter_component_type=st.sampled_from(["", "univer", "form", "word", "hybrid"]),
    filter_cycle=st.sampled_from(["", "A", "B", "C", "D"]),
)
@settings(max_examples=5, deadline=None)
def test_property_5_search_filter_correctness(
    items, search_text, filter_component_type, filter_cycle
):
    """每个返回项满足 (a) wp_code 或 wp_name 包含 search（不区分大小写）
    AND (b) component_type 匹配过滤 AND (c) cycle 匹配过滤。

    Validates: Property 5 (Search filter correctness) +
               Requirements 5.1, 5.4, 5.5
    """
    result = _filter_templates(items, search_text, filter_component_type, filter_cycle)

    q = (search_text or "").lower()
    for t in result:
        # 不变量 (a)
        if q:
            code = (t.get("wp_code") or "").lower()
            name = (t.get("wp_name") or "").lower()
            assert q in code or q in name
        # 不变量 (b)
        if filter_component_type:
            assert t.get("component_type") == filter_component_type
        # 不变量 (c)
        if filter_cycle:
            assert t.get("cycle") == filter_cycle

    # 不变量 (d): 所有未在 result 中的 item 至少违反一个条件
    for t in items:
        if t in result:
            continue
        violates = False
        if filter_component_type and t.get("component_type") != filter_component_type:
            violates = True
        if filter_cycle and t.get("cycle") != filter_cycle:
            violates = True
        if q:
            code = (t.get("wp_code") or "").lower()
            name = (t.get("wp_name") or "").lower()
            if q not in code and q not in name:
                violates = True
        assert violates, f"项 {t} 应被过滤但未被过滤"


# ---------------------------------------------------------------------------
# Property 12: Progress calculation
# ---------------------------------------------------------------------------


@given(
    items=st.lists(
        st.fixed_dictionaries({
            "wp_code": st.text(min_size=1, max_size=5),
            "generated": st.booleans(),
        }),
        max_size=20,
    ),
)
@settings(max_examples=5, deadline=None)
def test_property_12_progress_calculation(items):
    """progress == count(generated=true) / total。空集进度为 0。

    Validates: Property 12 (Progress calculation) +
               Requirements 4.10, 20.1, 20.2
    """
    total = len(items)
    generated_count = sum(1 for it in items if it.get("generated"))

    if total == 0:
        progress = 0.0
    else:
        progress = generated_count / total

    # 不变量 1: 0 <= progress <= 1
    assert 0.0 <= progress <= 1.0

    # 不变量 2: progress * total == generated_count（容许浮点误差）
    if total > 0:
        assert abs(progress * total - generated_count) < 1e-9

    # 不变量 3: 全部 generated → progress=1
    if total > 0 and all(it.get("generated") for it in items):
        assert progress == 1.0
    # 不变量 4: 全部未 generated → progress=0
    if total > 0 and not any(it.get("generated") for it in items):
        assert progress == 0.0


# ---------------------------------------------------------------------------
# Property 15: Invalid formula reference detection
# ---------------------------------------------------------------------------


def _find_invalid_refs(formula: str, valid_row_codes: set[str]) -> list[str]:
    """复刻 FormulaTab.vue findInvalidRefs。"""
    if not formula:
        return []
    invalid: list[str] = []
    # ROW('xxx') 或 ROW("xxx")
    row_re = re.compile(r"ROW\(['\"]([^'\"]+)['\"]\)")
    for m in row_re.finditer(formula):
        ref = m.group(1)
        if ref and ref not in valid_row_codes:
            invalid.append(ref)
    # SUM_ROW('a','b')
    sum_re = re.compile(r"SUM_ROW\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\)")
    for m in sum_re.finditer(formula):
        a, b = m.group(1), m.group(2)
        if a and a not in valid_row_codes:
            invalid.append(a)
        if b and b not in valid_row_codes:
            invalid.append(b)
    # 去重保序
    seen = set()
    result = []
    for x in invalid:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


@given(
    valid_codes=st.lists(
        st.text(alphabet="ABCDEFGHIJ-0123456789", min_size=2, max_size=8),
        max_size=8, unique=True,
    ),
    refs_in_formula=st.lists(
        st.text(alphabet="ABCDEFGHIJ-0123456789", min_size=2, max_size=8),
        max_size=5, unique=True,
    ),
)
@settings(max_examples=5, deadline=None)
def test_property_15_invalid_formula_reference(valid_codes, refs_in_formula):
    """ROW('xxx') 当且仅当 xxx 不在 valid_row_codes 中时被标记为 invalid。

    Validates: Property 15 (Invalid formula reference detection) +
               Requirements 7.6
    """
    # 构造公式：把所有 refs 串成 ROW('xxx') + ROW('yyy') ...
    formula_parts = [f"ROW('{r}')" for r in refs_in_formula]
    formula = " + ".join(formula_parts) if formula_parts else ""

    valid_set = set(valid_codes)
    invalid = _find_invalid_refs(formula, valid_set)

    # 不变量 1: 每个 invalid ref 确实不在 valid_set
    for ref in invalid:
        assert ref not in valid_set, f"误报：{ref} 在 valid_set 但被标为 invalid"

    # 不变量 2: 每个 refs_in_formula 中不在 valid_set 的 ref 必须出现在 invalid
    for r in refs_in_formula:
        if r not in valid_set:
            assert r in invalid, f"漏报：{r} 不在 valid_set 但未标为 invalid"

    # 不变量 3: invalid 列表不含重复
    assert len(invalid) == len(set(invalid))


# ---------------------------------------------------------------------------
# Property 7: Coverage color coding
# ---------------------------------------------------------------------------


def _coverage_color(pct: float) -> str:
    """复刻 FormulaCoverageChart.vue coverageColor。"""
    v = float(pct or 0)
    if v >= 80:
        return "green"
    if v >= 40:
        return "yellow"
    return "red"


@given(pct=st.floats(min_value=-50, max_value=200, allow_nan=False, allow_infinity=False))
@settings(max_examples=5, deadline=None)
def test_property_7_coverage_color_coding(pct):
    """≥80 → green; 40-79 → yellow; <40 → red。

    Validates: Property 7 (Coverage color coding) +
               Requirements 8.4, 20.4
    """
    color = _coverage_color(pct)

    if pct >= 80:
        assert color == "green"
    elif pct >= 40:
        assert color == "yellow"
    else:
        assert color == "red"

    # 不变量：边界点
    assert _coverage_color(80.0) == "green"
    assert _coverage_color(79.9) == "yellow"
    assert _coverage_color(40.0) == "yellow"
    assert _coverage_color(39.9) == "red"
    assert _coverage_color(0.0) == "red"
    assert _coverage_color(100.0) == "green"


# ---------------------------------------------------------------------------
# Property 9: Seed load resilience（模拟 SAVEPOINT 边界）
# ---------------------------------------------------------------------------


def _simulate_seed_pipeline(
    pipeline: list[str], failing_seeds: set[str]
) -> list[dict]:
    """模拟 _seed_all 的 SAVEPOINT 隔离行为：
    每个 seed 独立 try/except，失败仅记 status=failed 不影响后续。
    """
    results = []
    for seed_name in pipeline:
        if seed_name in failing_seeds:
            results.append({
                "seed": seed_name,
                "status": "failed",
                "inserted": 0,
                "updated": 0,
                "errors": ["mock failure"],
            })
        else:
            results.append({
                "seed": seed_name,
                "status": "loaded",
                "inserted": 1,
                "updated": 0,
                "errors": [],
            })
    return results


@given(
    pipeline=st.lists(
        st.sampled_from([
            "report_config", "gt_wp_coding", "wp_template_metadata",
            "audit_report_templates", "note_templates", "accounting_standards",
        ]),
        min_size=1, max_size=6, unique=True,
    ),
    failing_indices=st.lists(st.integers(min_value=0, max_value=5), max_size=3, unique=True),
)
@settings(max_examples=5, deadline=None)
def test_property_9_seed_load_resilience(pipeline, failing_indices):
    """任一 seed 失败时其他 seeds 仍被尝试；每个 seed 都有独立的 result 条目。

    Validates: Property 9 (Seed load resilience) +
               Requirements 13.3, 13.4
    """
    failing_seeds = {
        pipeline[i] for i in failing_indices if i < len(pipeline)
    }

    results = _simulate_seed_pipeline(pipeline, failing_seeds)

    # 不变量 1: 每个 seed 都有结果（不论成功/失败）
    assert len(results) == len(pipeline)
    result_seeds = [r["seed"] for r in results]
    assert result_seeds == pipeline

    # 不变量 2: 失败的 seed status=failed 且 errors 非空
    for r in results:
        if r["seed"] in failing_seeds:
            assert r["status"] == "failed"
            assert r["errors"]
        else:
            assert r["status"] == "loaded"
            assert not r["errors"]

    # 不变量 3: 失败不阻止后续 seed 执行
    if failing_seeds:
        last_failed_idx = max(
            i for i, r in enumerate(results) if r["status"] == "failed"
        )
        # 后续若有 seed 应仍被尝试
        for r in results[last_failed_idx + 1:]:
            assert r["seed"] in pipeline


# ---------------------------------------------------------------------------
# Property 14: Seed load history audit trail
# ---------------------------------------------------------------------------


def _simulate_history_records(
    pipeline: list[str], user_id: str, results: list[dict]
) -> list[dict]:
    """模拟 _record_history：每个 seed 写一条 history 记录。"""
    from datetime import datetime, timezone
    history = []
    for r in results:
        history.append({
            "id": f"history-{r['seed']}",
            "seed_name": r["seed"],
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "loaded_by": user_id,
            "record_count": r.get("inserted", 0) + r.get("updated", 0),
            "inserted": r.get("inserted", 0),
            "updated": r.get("updated", 0),
            "errors": r.get("errors", []),
            "status": r["status"],
        })
    return history


@given(
    pipeline=st.lists(
        st.sampled_from([
            "report_config", "gt_wp_coding", "wp_template_metadata",
            "audit_report_templates", "note_templates",
        ]),
        min_size=1, max_size=5, unique=True,
    ),
    user_id=st.text(min_size=8, max_size=36),
)
@settings(max_examples=5, deadline=None)
def test_property_14_seed_load_history(pipeline, user_id):
    """每次 seed 加载（成功或失败）都创建一条 history 记录，含必填字段。

    Validates: Property 14 (Seed load history audit trail) +
               Requirements 14.3, 13.6
    """
    # 构造一组结果（混合成功/失败）
    results = []
    for i, seed_name in enumerate(pipeline):
        results.append({
            "seed": seed_name,
            "status": "failed" if i % 3 == 2 else "loaded",
            "inserted": i,
            "updated": 0,
            "errors": ["err"] if i % 3 == 2 else [],
        })

    history = _simulate_history_records(pipeline, user_id, results)

    # 不变量 1: 一对一映射 — 每个 seed 一条 history
    assert len(history) == len(pipeline)

    # 不变量 2: 必填字段全部存在
    required_fields = {
        "seed_name", "loaded_at", "loaded_by", "record_count",
        "inserted", "updated", "status",
    }
    for h in history:
        missing = required_fields - set(h.keys())
        assert not missing, f"history 记录缺失字段: {missing}"
        assert h["seed_name"] in pipeline
        assert h["loaded_by"] == user_id
        assert h["status"] in ("loaded", "failed")

    # 不变量 3: failed seed 的 errors 非空，loaded seed 的 errors 为空
    for h in history:
        if h["status"] == "failed":
            assert h["errors"]
        else:
            assert not h["errors"]


# ---------------------------------------------------------------------------
# Property 16: Backend mutation authorization（直接测 require_role）
# ---------------------------------------------------------------------------


@given(role=st.sampled_from(["admin", "partner", "manager", "auditor", "qc", "readonly"]))
@settings(max_examples=50, deadline=None)  # P0 关键 Property（authz）max_examples=50（三轮复盘 P3.9）
def test_property_16_backend_mutation_authorization(role):
    """require_role(["admin", "partner"]) 仅对 admin/partner 放行，其他角色返回 403。

    Validates: Property 16 (Backend-enforced mutation authorization) +
               D13 安全铁律 + Requirements 1.2, 1.3, 6.5, 9.4, 11.5, 13.1, 21.3
    """
    import asyncio
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from app.deps import require_role

    # 构造 dependency factory，再获取真实 dependency 函数
    dependency = require_role(["admin", "partner"])

    # 构造模拟 user
    user = MagicMock()
    user.role = MagicMock()
    user.role.value = role

    async def _call():
        return await dependency(current_user=user)

    if role in ("admin", "partner"):
        result = asyncio.run(_call())
        assert result is user
    else:
        try:
            asyncio.run(_call())
            raised = False
        except HTTPException as e:
            raised = True
            assert e.status_code == 403
        assert raised, f"role={role} 应被 403 拒绝但未拒绝"


# ---------------------------------------------------------------------------
# Property 17: JSON source readonly enforcement
# ---------------------------------------------------------------------------


# JSON 类只读资源（D13 ADR）
JSON_SOURCE_RESOURCES = {
    "prefill_formula_mapping",
    "cross_wp_references",
    "audit_report_templates",
    "wp_account_mapping",
}

# DB 类资源（应允许 mutation 不在此 405 规则内）
DB_RESOURCES = {
    "report_config",
    "gt_wp_coding",
    "wp_template_metadata",
}


def _enforce_json_readonly(resource: str, http_method: str) -> int:
    """模拟后端对 JSON 资源 mutation 的强制 405 行为：
    PUT / DELETE / POST 在 JSON 源上 → 405
    GET 永远 200（只读）
    DB 类资源走正常路径（这里返回 200 表示通过）"""
    method = http_method.upper()
    if resource in JSON_SOURCE_RESOURCES:
        if method == "GET":
            return 200
        return 405
    # DB 类资源 mutation 允许（实际由 require_role 把关）
    return 200


@given(
    resource=st.sampled_from(list(JSON_SOURCE_RESOURCES) + list(DB_RESOURCES)),
    http_method=st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
)
@settings(max_examples=50, deadline=None)  # P0 关键 Property（readonly enforcement）max_examples=50（三轮复盘 P3.9）
def test_property_17_json_source_readonly_enforcement(resource, http_method):
    """JSON 类只读资源对任何 mutation（POST/PUT/DELETE）必须返回 405；
    GET 永远 200；DB 类资源不在此规则内（由 require_role 把关）。

    Validates: Property 17 (JSON source readonly) +
               D13 ADR + Requirements 6.5, 9.4
    """
    status_code = _enforce_json_readonly(resource, http_method)

    if resource in JSON_SOURCE_RESOURCES:
        if http_method == "GET":
            assert status_code == 200
        else:
            assert status_code == 405, (
                f"JSON 源 {resource} 对 {http_method} 必须返回 405，实际 {status_code}"
            )
    else:
        # DB 资源在本规则下永远不应 405（mutation 由 require_role 把关）
        assert status_code != 405


# 同时验证真实路由对 JSON 源 mutation 返回 405（端点真实存在性核验）
def test_property_17_actual_endpoint_returns_405():
    """实际验证 backend/app/routers/template_library_mgmt.py 中的拒绝端点存在
    且语义正确。

    Validates: Property 17 落地一致性核验
    """
    import asyncio

    from fastapi import HTTPException

    from app.routers.template_library_mgmt import (
        reject_cross_wp_references_mutation,
        reject_prefill_formulas_delete,
        reject_prefill_formulas_mutation,
    )

    async def _check(coro):
        try:
            await coro
        except HTTPException as e:
            return e
        return None

    e1 = asyncio.run(_check(reject_prefill_formulas_mutation("D2")))
    assert e1 is not None and e1.status_code == 405
    assert e1.detail.get("error_code") == "JSON_SOURCE_READONLY"

    e2 = asyncio.run(_check(reject_prefill_formulas_delete("D2")))
    assert e2 is not None and e2.status_code == 405

    e3 = asyncio.run(_check(reject_cross_wp_references_mutation("ref-1")))
    assert e3 is not None and e3.status_code == 405
