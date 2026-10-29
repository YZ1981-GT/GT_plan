"""T31 守卫：外部命名空间的中文原因与下一步、多命中的可解释字段。

判据（design §12.2~§12.5 / 需求 12）：
1. grammar_v1.json 里**每个**标了 external_module 的命名空间都必须有 label_zh 与
   next_step_zh —— 遍历 grammar 现算，不写死 6 个名字；缺一个即红。
2. 这六类引用经 full_resolve 返回 found=False + error=external_module_not_resolved
   + 中文 reason + 中文 next_step，且 reason 里带 grammar 的 label_zh。
3. 界面不出现英文错误码：reason / next_step 不含 ASCII 字母串形态的错误码。
4. 多命中（表内多格 / 裸编码多底稿 / 运行时多格）都给 reason + required_context
   + next_step，且候选项带 display_label。
5. 中文文案只有一处来源：resolver 不自带文案字面量，必须经 reasons 模块。

变异要求（tasks.md T31）：删一个命名空间的 label_zh → 本文件遍历用例红。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.acnr import reasons
from app.services.acnr.grammar import (
    external_namespace_meta,
    external_namespace_names,
    index_namespaces,
)
from app.services.acnr.resolver import ResolveResult, full_resolve

_RESOLVER = Path(__file__).resolve().parents[2] / "app" / "services" / "acnr" / "resolver.py"


# ─── 1. grammar 现算：外部命名空间文案完备 ────────────────────────────────


def test_external_namespaces_are_discovered_from_grammar() -> None:
    """外部命名空间来自 grammar 现算，且与 index_namespaces 自洽。"""
    names = external_namespace_names()
    assert names, "grammar_v1.json 里没有任何 external_module 命名空间"
    ns_all = index_namespaces()
    for name in names:
        assert ns_all[name].get("external_module") is True, name
    # 非外部命名空间不得被误判
    for name, meta in ns_all.items():
        if not meta.get("external_module"):
            assert external_namespace_meta(name) is None, name


@pytest.mark.parametrize("ns", external_namespace_names())
def test_every_external_namespace_has_chinese_label_and_next_step(ns: str) -> None:
    """每个外部命名空间都必须有中文标签与下一步（缺一个即红）。"""
    meta = external_namespace_meta(ns)
    assert meta is not None, f"{ns} 未被识别为外部命名空间"
    assert meta["label_zh"], f"{ns} 缺 label_zh"
    assert meta["next_step_zh"], f"{ns} 缺 next_step_zh"
    # 文案是中文，不是把英文名抄一遍
    assert re.search(r"[\u4e00-\u9fff]", meta["label_zh"]), meta["label_zh"]
    assert re.search(r"[\u4e00-\u9fff]", meta["next_step_zh"]), meta["next_step_zh"]


def test_namespace_lookup_is_case_insensitive() -> None:
    for ns in external_namespace_names():
        assert external_namespace_meta(ns.lower())["name"] == ns
        assert external_namespace_meta(ns.upper())["name"] == ns


# ─── 2~3. full_resolve 行为：中文原因 + 下一步，且不露英文错误码 ──────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ns", external_namespace_names())
async def test_external_reference_returns_chinese_reason_and_next_step(ns: str) -> None:
    result = await full_resolve(index_ref=f"{ns}:123")

    assert result.found is False
    assert result.error == "external_module_not_resolved"

    meta = external_namespace_meta(ns)
    assert result.reason == reasons.external_namespace_reason(meta["label_zh"])
    assert meta["label_zh"] in result.reason
    assert "暂不支持定位到物理地址" in result.reason
    assert result.next_step == meta["next_step_zh"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ns", external_namespace_names())
async def test_user_facing_text_has_no_error_code(ns: str) -> None:
    """面向用户的两句话里不得出现英文错误码（如 external_module_not_resolved）。"""
    result = await full_resolve(index_ref=f"{ns}:123")
    for text in (result.reason, result.next_step):
        assert text
        assert result.error not in text
        # 下划线连写的小写英文串即错误码形态
        assert not re.search(r"[a-z]+_[a-z_]+", text), text


# ─── 4. 多命中：reason + required_context + next_step ─────────────────────


def test_resolve_result_carries_explainable_fields() -> None:
    fields = ResolveResult.__dataclass_fields__
    for name in ("reason", "required_context", "next_step", "deprecated", "replaced_by"):
        assert name in fields, f"ResolveResult 缺字段 {name}"


@pytest.mark.parametrize("kind", reasons.AMBIGUOUS_KINDS)
def test_ambiguous_fields_are_complete(kind: str) -> None:
    got = reasons.ambiguous_fields(kind, text="X1")
    assert set(got) == {"reason", "required_context", "next_step"}, got
    assert re.search(r"[\u4e00-\u9fff]", str(got["reason"])), got
    assert re.search(r"[\u4e00-\u9fff]", str(got["next_step"])), got
    assert got["required_context"], kind
    assert all(isinstance(c, str) and c for c in got["required_context"]), got
    # 不得把模板占位符原样露出
    assert "{text}" not in str(got["reason"])


def test_ambiguous_fields_rejects_unknown_kind() -> None:
    with pytest.raises(KeyError):
        reasons.ambiguous_fields("不存在的类型")


def test_every_ambiguous_return_in_resolver_carries_reason() -> None:
    """语法树：resolver 里每个 error="ambiguous" 的构造都必须带可解释字段。

    文案只能经 reasons.ambiguous_fields 展开（**调用），不许在 resolver 里写字面量。
    """
    tree = ast.parse(_RESOLVER.read_text(encoding="utf-8"))
    sites: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "ResolveResult"):
            continue
        for kw in node.keywords:
            if (kw.arg == "error" and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "ambiguous"):
                sites.append(node)
    assert sites, "resolver 里没有找到 ambiguous 的构造点"
    for call in sites:
        starred = [kw for kw in call.keywords if kw.arg is None]
        assert starred, f"第 {call.lineno} 行的 ambiguous 构造没有展开 ambiguous_fields"
        ok = any(
            isinstance(kw.value, ast.Call)
            and isinstance(kw.value.func, ast.Name)
            and kw.value.func.id == "ambiguous_fields"
            for kw in starred
        )
        assert ok, f"第 {call.lineno} 行展开的不是 ambiguous_fields"


def test_resolver_does_not_inline_external_namespace_text() -> None:
    """resolver 不得自带外部命名空间文案字面量（单一来源在 reasons + grammar）。"""
    text = _RESOLVER.read_text(encoding="utf-8")
    assert "暂不支持定位到物理地址" not in text
    for ns in external_namespace_names():
        label = external_namespace_meta(ns)["label_zh"]
        assert label not in text, f"resolver 内联了 {ns} 的中文标签 {label}"
