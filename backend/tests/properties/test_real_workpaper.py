"""Property 5 PBT: 真假底稿与完成率派生

**Validates: Requirements 3.0.2（真假底稿明确区分 + 完成率铁律）**

五条核心 property：

- Property 5a (确定性映射): 同一 (sheet_name, features) 多次调用
  classify_sheet → derive_is_real_workpaper 结果恒等（纯函数）。
- Property 5b (假底稿判定): class_code 以 ``I-`` / ``H-`` 开头 →
  ``derive_is_real_workpaper`` 返回 ``False``。
- Property 5c (真底稿判定): class_code 以 A/B/C/D/E/F/G 开头 →
  ``derive_is_real_workpaper`` 返回 ``True``。
- Property 5d (完成率分母不被假底稿稀释): 把任意数量假底稿加入 workpapers
  列表，``compute_completion_rate`` 返回值不变（分母仅含真底稿）。
- Property 5e (完成率范围): ``compute_completion_rate`` 始终返回
  ``[0.0, 1.0]`` 区间的 float；无真底稿时返回 ``0.0``。

Spec: ``.kiro/specs/workpaper-html-renderer/`` §3.0.2

铁律：底稿完成率 = 真底稿已完成数 / 真底稿总数，**不含假底稿**。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st

# ─── 让 backend/scripts/analyze_wp_templates.py 可被 import ──────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analyze_wp_templates import classify_sheet  # noqa: E402


# ─── 常量：白名单 class_code 前缀 ────────────────────────────────────────────

# 真底稿 7 类（要渲染 + 编辑 + 归档 + 计入完成率）
REAL_CLASS_PREFIXES: set[str] = {"A-", "B-", "C-", "D-", "E-", "F-", "G-"}

# 假底稿 2 类（不渲染 / 静态 / 跳过 / 不归档 / 不计入完成率）
FAKE_CLASS_PREFIXES: set[str] = {"H-", "I-"}

# 完整 class_code 样本（用于 hypothesis sampled_from）
_REAL_CLASS_CODES: list[str] = [
    # A 程序表
    "A-实质性程序", "A-程序表", "A-替代程序", "A-一般程序表", "A-S 议题程序",
    # B 底稿目录
    "B-底稿目录",
    # C 附注披露
    "C-附注披露",
    # D 检查/政策/业务模式/函证/盘点/访谈/复核
    "D-检查表", "D-政策检查", "D-业务模式", "D-函证", "D-盘点",
    "D-访谈", "D-复核记录", "D-风险评估", "D-业务了解", "D-系统核对",
    # E 控制测试
    "E-控制测试汇总", "E-控制测试单条", "E-评价控制偏差", "E-IT 控制测试",
    # F 数据表
    "F-审定表", "F-明细表", "F-分析表", "F-调整分录",
    "F-汇总表", "F-CFS 编制", "F-数据表", "F-检查数据表",
    # G 测算
    "G-测算",
]

_FAKE_CLASS_CODES: list[str] = [
    "H-辅助说明",
    "I-占位",
]


# 真底稿 sheet_name 样本（classify_sheet 应归到 A-G 类）
_REAL_SHEET_NAMES: list[str] = [
    # A 程序表
    "实质性程序表-应收账款 D2A",
    "实质性程序表-存货 F2A",
    "替代程序-G7A",
    "审计程序",
    # B 底稿目录
    "底稿目录",
    # C 附注披露
    "应收账款附注披露",
    "披露信息汇总",
    # D 检查/政策/函证/盘点/访谈/复核
    "业务模式判断",
    "会计政策检查",
    "函证记录",
    "询证函发函记录",
    "盘点记录",
    "访谈记录",
    "项目经理复核记录",
    "调查问卷",
    # E 控制测试
    "控制测试汇总",
    "应收账款控制测试",
    "评价控制偏差",
    # F 数据表（避免触发 G 的"测算/测试"关键词）
    "应收账款审定表",
    "存货明细表",
    "调整分录",
    "汇总表",
    # G 测算（特意避免与 E 的"控制测试"冲突）
    "ECL 测算",
    "三阶段划分",
    "追溯调整",
]

# 假底稿 sheet_name 样本（classify_sheet 应归到 H-/I- 类）
_FAKE_SHEET_NAMES: list[str] = [
    # I 占位（GT_Custom / Data / List / 参数 / temp_）
    "GT_Custom1",
    "GT_Custom_Helper",
    "Data",
    "Lists",
    "Instructions",
    "temp_calc",
    "参数表",
    "Sheet1",
    "0000",
    # 不归档 / 删除 / 重复
    "选项清单列表（不归档）",
    "示例-评价控制偏差-删除",
    "首发业务解答二-删除",
    "底稿目录 (2)",
    # H 辅助说明
    "修订说明",
    "编制说明",
    "填表说明",
    "文号规则",
    "参考-准则",
    "参考-应用指南",
    "相关资源",
    "IPO 提示",
    "会计监管风险提示第1号",
    "环境法规清单",
    # 准则/指南
    "准则及应用指南",
]


# ─── Domain types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkpaperRecord:
    """单个 sheet 的归类 + 完成状态记录（用于完成率计算）"""

    sheet_name: str
    class_code: str
    completed: bool


# ─── Helper functions（被测对象） ────────────────────────────────────────────


def derive_is_real_workpaper(sheet_name: str, class_code: str | None) -> bool:
    """根据 class_code 派生 is_real_workpaper

    规则（Requirements 3.0.2）：
    - class_code 以 ``H-`` / ``I-`` 开头 → ``False``（假底稿，不计入完成率）
    - class_code 以 ``A-``/``B-``/``C-``/``D-``/``E-``/``F-``/``G-`` 开头 → ``True``
    - class_code 为 ``None`` / 空 / ``_pending`` → ``True``（与 DB 默认一致，
      未明确归类的不应误判为假底稿稀释完成率）
    """
    if not class_code:
        return True
    prefix = class_code[:2]
    if prefix in FAKE_CLASS_PREFIXES:
        return False
    if prefix in REAL_CLASS_PREFIXES:
        return True
    # 兜底（含 ``_pending``）：与 DB ``is_real_workpaper`` server_default=true 对齐
    return True


def compute_completion_rate(workpapers: list[WorkpaperRecord]) -> float:
    """完成率铁律：分母仅含真底稿，假底稿不进分子也不进分母

    Requirements 3.0.2：
        completion_rate = N(real ∧ completed) / N(real)
                          ─────────────────────────────────
                                       排除假底稿

    边界：N(real) == 0 时返回 ``0.0``（无真底稿即 0% 进度，避免 ZeroDivisionError）
    """
    real_total = 0
    real_completed = 0
    for wp in workpapers:
        if derive_is_real_workpaper(wp.sheet_name, wp.class_code):
            real_total += 1
            if wp.completed:
                real_completed += 1
    if real_total == 0:
        return 0.0
    return real_completed / real_total


# ─── Hypothesis Strategies ───────────────────────────────────────────────────

# 假底稿 sheet_name 策略
st_fake_sheet_name = st.sampled_from(_FAKE_SHEET_NAMES)

# 真底稿 sheet_name 策略
st_real_sheet_name = st.sampled_from(_REAL_SHEET_NAMES)

# 任意 sheet_name 策略（混合真假）
st_any_sheet_name = st.one_of(st_fake_sheet_name, st_real_sheet_name)

# 假底稿 class_code 策略
st_fake_class_code = st.sampled_from(_FAKE_CLASS_CODES)

# 真底稿 class_code 策略
st_real_class_code = st.sampled_from(_REAL_CLASS_CODES)

# 默认 features dict（classify_sheet 需要，但本属性不依赖具体特征）
_DEFAULT_FEATURES: dict = {
    "max_row": 50,
    "max_col": 10,
    "merged_count": 0,
    "merged_density": 0.0,
    "long_text_cells": 0,
    "formula_cells": 0,
    "has_step_words": False,
    "has_index_triplet": False,
    "has_assertion_5": False,
    "first_col_samples": [],
}

st_features = st.just(_DEFAULT_FEATURES)

# 完成状态策略（每个 wp 是否完成）
st_completion_status = st.booleans()

# WorkpaperRecord 策略：真底稿
st_real_workpaper_record = st.builds(
    WorkpaperRecord,
    sheet_name=st_real_sheet_name,
    class_code=st_real_class_code,
    completed=st_completion_status,
)

# WorkpaperRecord 策略：假底稿
st_fake_workpaper_record = st.builds(
    WorkpaperRecord,
    sheet_name=st_fake_sheet_name,
    class_code=st_fake_class_code,
    completed=st_completion_status,
)


# ─── Property 5a: 确定性映射（纯函数）─────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_any_sheet_name, completed=st.booleans())
def test_property_5a_classify_to_is_real_is_deterministic(
    sheet_name: str, completed: bool
) -> None:
    """**Validates: Requirements 3.0.2** — sheet_name → is_real_workpaper 确定性

    1. 同一 sheet_name 多次调用 classify_sheet 返回相同 class_code（纯函数）
    2. 同一 class_code 多次调用 derive_is_real_workpaper 返回相同 bool
    3. 不修改输入参数（无副作用）
    """
    features = dict(_DEFAULT_FEATURES)  # copy 防御
    features_snapshot = dict(features)

    code1, _ = classify_sheet(sheet_name, features)
    code2, _ = classify_sheet(sheet_name, features)
    code3, _ = classify_sheet(sheet_name, features)

    assert code1 == code2 == code3, (
        f"classify_sheet 不是纯函数：{code1!r} / {code2!r} / {code3!r} "
        f"(sheet_name={sheet_name!r})"
    )
    # features 不被修改
    assert features == features_snapshot, (
        f"classify_sheet 修改了 features 字典 (sheet_name={sheet_name!r})"
    )

    # derive_is_real_workpaper 多次调用结果恒等
    real1 = derive_is_real_workpaper(sheet_name, code1)
    real2 = derive_is_real_workpaper(sheet_name, code1)
    real3 = derive_is_real_workpaper(sheet_name, code1)
    assert real1 == real2 == real3, (
        f"derive_is_real_workpaper 不幂等：{real1!r} / {real2!r} / {real3!r} "
        f"(sheet_name={sheet_name!r}, class_code={code1!r})"
    )
    assert isinstance(real1, bool)


# ─── Property 5b: I/H 类 → is_real_workpaper = False ────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_fake_sheet_name)
def test_property_5b_fake_class_returns_false(sheet_name: str) -> None:
    """**Validates: Requirements 3.0.2** — H/I 类必为假底稿

    sheet_name 经 classify_sheet 归类为 H-* 或 I-* →
    derive_is_real_workpaper 必返回 ``False``。
    """
    features = dict(_DEFAULT_FEATURES)
    class_code, reason = classify_sheet(sheet_name, features)

    # 归类必落在 H- / I- 前缀（按 _FAKE_SHEET_NAMES 列表精心选择）
    prefix = class_code[:2] if class_code else ""
    assert prefix in FAKE_CLASS_PREFIXES, (
        f"假底稿 sheet_name={sheet_name!r} 应归到 H-/I- 类，"
        f"实际 class_code={class_code!r} (reason={reason!r})"
    )

    # derive 必返回 False
    is_real = derive_is_real_workpaper(sheet_name, class_code)
    assert is_real is False, (
        f"假底稿 sheet_name={sheet_name!r} class_code={class_code!r} "
        f"应返回 is_real_workpaper=False，实际 {is_real!r}"
    )


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(class_code=st_fake_class_code,
       sheet_name=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()))
def test_property_5b_fake_class_code_returns_false_direct(
    class_code: str, sheet_name: str
) -> None:
    """**Validates: Requirements 3.0.2** — class_code 直接判定

    任意 H- / I- 开头的 class_code → derive_is_real_workpaper 返回 ``False``，
    不依赖 sheet_name 内容。
    """
    is_real = derive_is_real_workpaper(sheet_name, class_code)
    assert is_real is False, (
        f"class_code={class_code!r} 应返回 False，实际 {is_real!r}"
    )


# ─── Property 5c: A-G 类 → is_real_workpaper = True ─────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(sheet_name=st_real_sheet_name)
def test_property_5c_real_class_returns_true(sheet_name: str) -> None:
    """**Validates: Requirements 3.0.2** — A-G 类必为真底稿

    sheet_name 经 classify_sheet 归类为 A-G 任一前缀 →
    derive_is_real_workpaper 必返回 ``True``。
    """
    features = dict(_DEFAULT_FEATURES)
    class_code, reason = classify_sheet(sheet_name, features)

    prefix = class_code[:2] if class_code else ""
    assert prefix in REAL_CLASS_PREFIXES, (
        f"真底稿 sheet_name={sheet_name!r} 应归到 A-G 类，"
        f"实际 class_code={class_code!r} (reason={reason!r})"
    )

    is_real = derive_is_real_workpaper(sheet_name, class_code)
    assert is_real is True, (
        f"真底稿 sheet_name={sheet_name!r} class_code={class_code!r} "
        f"应返回 is_real_workpaper=True，实际 {is_real!r}"
    )


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(class_code=st_real_class_code,
       sheet_name=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()))
def test_property_5c_real_class_code_returns_true_direct(
    class_code: str, sheet_name: str
) -> None:
    """**Validates: Requirements 3.0.2** — class_code 直接判定

    任意 A-/B-/C-/D-/E-/F-/G- 开头的 class_code →
    derive_is_real_workpaper 返回 ``True``。
    """
    is_real = derive_is_real_workpaper(sheet_name, class_code)
    assert is_real is True, (
        f"class_code={class_code!r} 应返回 True，实际 {is_real!r}"
    )


# ─── Property 5d: 完成率分母不被假底稿稀释 ────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    real_wps=st.lists(st_real_workpaper_record, min_size=1, max_size=20),
    fake_wps=st.lists(st_fake_workpaper_record, min_size=0, max_size=20),
)
def test_property_5d_fake_workpapers_dont_dilute_rate(
    real_wps: list[WorkpaperRecord],
    fake_wps: list[WorkpaperRecord],
) -> None:
    """**Validates: Requirements 3.0.2** — 假底稿不进分子分母

    rate(real_wps) == rate(real_wps + fake_wps)
    无论加入多少假底稿，完成率永远等于仅真底稿计算的结果。
    """
    rate_only_real = compute_completion_rate(list(real_wps))
    rate_with_fake = compute_completion_rate(list(real_wps) + list(fake_wps))

    assert rate_only_real == rate_with_fake, (
        f"加入假底稿改变了完成率：{rate_only_real!r} → {rate_with_fake!r} "
        f"(real={len(real_wps)}, fake={len(fake_wps)})"
    )

    # 同时验证：仅假底稿时完成率 == 0.0（无真底稿）
    if fake_wps:
        rate_only_fake = compute_completion_rate(list(fake_wps))
        assert rate_only_fake == 0.0, (
            f"仅假底稿时应返回 0.0，实际 {rate_only_fake!r}"
        )


# ─── Property 5e: 完成率范围 ∈ [0.0, 1.0] ──────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    workpapers=st.lists(
        st.one_of(st_real_workpaper_record, st_fake_workpaper_record),
        min_size=0,
        max_size=30,
    ),
)
def test_property_5e_rate_in_unit_interval(
    workpapers: list[WorkpaperRecord],
) -> None:
    """**Validates: Requirements 3.0.2** — 完成率始终在 [0.0, 1.0]

    1. 任意 workpapers 列表（含空列表 / 全假 / 全真）→ rate ∈ [0.0, 1.0]
    2. 空列表 / 无真底稿 → rate == 0.0（边界值定义清楚）
    3. 返回类型必为 float
    """
    rate = compute_completion_rate(list(workpapers))

    assert isinstance(rate, float), (
        f"compute_completion_rate 应返回 float，实际 {type(rate).__name__}: {rate!r}"
    )
    assert 0.0 <= rate <= 1.0, (
        f"完成率超出 [0.0, 1.0]：{rate!r} (workpapers count={len(workpapers)})"
    )

    # 无真底稿时必返回 0.0
    real_count = sum(
        1 for w in workpapers
        if derive_is_real_workpaper(w.sheet_name, w.class_code)
    )
    if real_count == 0:
        assert rate == 0.0, (
            f"无真底稿时应返回 0.0，实际 {rate!r}"
        )


# ─── 单元测试：边界 case（PBT 互补） ───────────────────────────────────────


def test_empty_workpapers_returns_zero() -> None:
    """空 workpapers 列表 → 完成率 0.0（无 ZeroDivisionError）"""
    assert compute_completion_rate([]) == 0.0


def test_only_fake_workpapers_returns_zero() -> None:
    """仅假底稿（H/I）→ 完成率 0.0（分母为 0）"""
    fakes = [
        WorkpaperRecord("修订说明", "H-辅助说明", completed=True),
        WorkpaperRecord("GT_Custom", "I-占位", completed=True),
    ]
    assert compute_completion_rate(fakes) == 0.0


def test_all_real_completed_returns_one() -> None:
    """所有真底稿都完成 → 完成率 1.0"""
    reals = [
        WorkpaperRecord("应收账款审定表", "F-审定表", completed=True),
        WorkpaperRecord("D2A 程序表", "A-程序表", completed=True),
    ]
    assert compute_completion_rate(reals) == 1.0


def test_half_real_completed_with_fakes_returns_half() -> None:
    """混合场景：2 真 1 完成 + 99 假 → 完成率 0.5（不被假底稿稀释）"""
    workpapers = [
        WorkpaperRecord("应收账款审定表", "F-审定表", completed=True),
        WorkpaperRecord("D2A 程序表", "A-程序表", completed=False),
    ]
    # 加 99 个假底稿
    workpapers.extend(
        WorkpaperRecord(f"GT_Custom_{i}", "I-占位", completed=True)
        for i in range(99)
    )
    rate = compute_completion_rate(workpapers)
    assert rate == 0.5, f"期望 0.5，实际 {rate!r}"


def test_pending_class_code_treated_as_real_default() -> None:
    """``_pending`` / None / 空 class_code → 视为真底稿（DB server_default=true）

    与 ``WorkpaperSheetClassification.is_real_workpaper`` server_default 对齐：
    未明确归类的不应误判为假底稿稀释完成率。
    """
    assert derive_is_real_workpaper("某未归类 sheet", None) is True
    assert derive_is_real_workpaper("某未归类 sheet", "") is True
    assert derive_is_real_workpaper("某未归类 sheet", "_pending") is True
