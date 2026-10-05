"""spec: formula-push-all-subjects-rollout · Task 5 · 需求 2.3 / 5.6

PushBinding 协议注册校验的负例与边界：缺方法 / 属性为空或类型错 / wp_code 与注册键不符 /
load_sources 非 async / 方法 arity 不符 / paper_codes 缺省与非法 / 工厂形态（字面量成功、展开与
任意表达式拒绝）。正向「E1 可注册、Z9 可临时注册」由 e1_binding / endpoints 测试覆盖。
"""
from __future__ import annotations

import pytest

from app.services.formula_push.bindings import (
    PushBinding,
    _validate_binding,
    get_binding,
    register_binding,
)
from tests._formula_push_binding import DummyPushBinding, make_dummy_binding


def _binding(wp_code="Z9", **over):
    """以协议完整的 Dummy 为基，按需覆盖属性 / 方法后返回实例。"""
    binding = DummyPushBinding()
    binding.wp_code = wp_code
    for name, value in over.items():
        setattr(binding, name, value)
    return binding


# ── 协议完整的 Dummy 本身可通过（守卫的锚点：下面的负例只改一处就该红）──────


def test_dummy_binding_passes_validation_and_defaults_paper_codes():
    binding = _validate_binding("Z9", _binding())
    assert isinstance(binding, PushBinding)
    assert binding.paper_codes == ("Z9",), "缺省 paper_codes 应回落到主编码单册"


# ── 缺方法 / 方法不可调用 ──────────────────────────────────────────────────


@pytest.mark.parametrize("method", ["load_sources", "workpaper_targets", "apply", "note_rows", "entry_warnings"])
def test_missing_method_is_rejected(method):
    binding = _binding()
    # 用实例属性 None 遮蔽类方法即可，不能 delattr 类（会影响后续测试实例）
    setattr(binding, method, None)
    with pytest.raises(ValueError, match=f"缺少可调用方法 {method}"):
        _validate_binding("Z9", binding)


# ── 必需属性为空 / 缺失 / 类型错 ───────────────────────────────────────────


@pytest.mark.parametrize("attr, bad", [
    ("account_prefixes", ()),            # 非空 tuple → 空被拒
    ("account_prefixes", ("", "x")),     # 含空串
    ("account_prefixes", ["1001"]),      # list 不是 tuple
    ("tb_columns", frozenset()),         # 非空 frozenset → 空被拒
    ("tb_columns", {"期末余额"}),         # set 不是 frozenset
    ("four_table_slots", {"cash"}),      # set 不是 frozenset（可空但类型须 frozenset）
])
def test_required_attribute_shape_is_enforced(attr, bad):
    with pytest.raises(ValueError, match=attr):
        _validate_binding("Z9", _binding(**{attr: bad}))


def test_four_table_slots_may_be_empty_frozenset():
    # 可空：E1 以外无四表的科目合法
    _validate_binding("Z9", _binding(four_table_slots=frozenset()))


# ── wp_code 与注册键 ───────────────────────────────────────────────────────


def test_wp_code_must_equal_registry_key():
    with pytest.raises(ValueError, match="binding 编码与注册键不一致"):
        _validate_binding("Z9", _binding(wp_code="Z8"))


@pytest.mark.parametrize("key", ["z9", "Z9-1", "Z", "9Z", ""])
def test_registry_key_must_be_main_code(key):
    with pytest.raises(ValueError, match="注册键必须是主编码"):
        _validate_binding(key, _binding(wp_code=key))


# ── load_sources 必须 async ────────────────────────────────────────────────


def test_load_sources_must_be_coroutine():
    def sync_load(self, db, project_id, year, wp_id):
        return None

    with pytest.raises(ValueError, match="load_sources 必须是异步方法"):
        _validate_binding("Z9", _binding(load_sources=sync_load.__get__(_binding())))


# ── 方法 arity 不符 ────────────────────────────────────────────────────────


def test_method_arity_mismatch_is_rejected():
    def bad_targets(self, rule):  # 协议要求 3 个位置参（self, rule, overlay, sources）
        return [], []

    binding = _binding()
    binding.workpaper_targets = bad_targets.__get__(binding)
    with pytest.raises(ValueError, match="workpaper_targets 签名不符合协议"):
        _validate_binding("Z9", binding)


# ── paper_codes ────────────────────────────────────────────────────────────


def test_paper_codes_explicit_main_and_subcode_pass():
    binding = _validate_binding("Z9", _binding(paper_codes=("Z9", "Z9-1")))
    assert binding.paper_codes == ("Z9", "Z9-1")


@pytest.mark.parametrize("papers, fragment", [
    (("Z9", "Z9"), "无重复"),                 # 重复
    (("Z9", "Z8-1"), "本 binding"),           # 跨 binding 分册
    (("Z9", "Y1"), "本 binding"),             # 跨 binding 主册
    ((), "paper_codes"),                       # 空
])
def test_paper_codes_illegal_declarations_rejected(papers, fragment):
    with pytest.raises(ValueError, match=fragment):
        _validate_binding("Z9", _binding(paper_codes=papers))


# ── 多缺陷同时报出（加载即校验，列出全部问题）──────────────────────────────


def test_all_problems_are_reported_together():
    binding = _binding(wp_code="Z8", account_prefixes=(), tb_columns=frozenset())
    binding.apply = None
    with pytest.raises(ValueError) as exc:
        _validate_binding("Z9", binding)
    msg = str(exc.value)
    for fragment in ("binding 编码与注册键不一致", "account_prefixes", "tb_columns", "缺少可调用方法 apply"):
        assert fragment in msg


# ── 工厂形态：字面量成功 / 展开 / 任意表达式拒绝 ───────────────────────────


def test_registry_literal_factory_registration_and_revoke():
    revoke = register_binding("Z7", "tests._formula_push_binding:make_dummy_binding('Z7', '7001')")
    try:
        binding = get_binding("Z7")
        assert binding.wp_code == "Z7" and binding.account_prefixes == ("7001",)
    finally:
        revoke()
    with pytest.raises(KeyError, match="尚未接入"):
        get_binding("Z7")


def test_registry_callable_factory_registration():
    revoke = register_binding("Z6", lambda: make_dummy_binding("Z6"))
    try:
        assert get_binding("Z6").wp_code == "Z6"
    finally:
        revoke()


@pytest.mark.parametrize("entry", [
    "tests._formula_push_binding:make_dummy_binding(*['Z5'])",   # 展开参数
    "tests._formula_push_binding:make_dummy_binding('Z5') or 1",  # 任意表达式
    "tests._formula_push_binding:1 + 1",                          # 非名称 / 调用
    "tests._formula_push_binding",                                # 缺 ":名称"
])
def test_registry_illegal_factory_expressions_rejected(entry):
    with pytest.raises(ValueError, match="不合法"):
        register_binding("Z5", entry)
