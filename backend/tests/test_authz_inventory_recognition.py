# Feature: partner-manager-edit-permission, Property 16: 识别结果不受注释与字符串影响
# Validates: Requirements 1.8, 9.1
"""识别器对注释 / docstring / 字符串的免疫性，以及条件分支只多出「条件执行」标注的性质测试。

两份清单（附注写端点清册与影响清单）共用 ``gates`` 识别器，因此以同一组合成源码测试即覆盖两者。

**测试策略**：
- 取需求 1.6 的 9 个自检样例与需求 9.8 的 10 个自检样例的源码；
- 对每个样例，先在干净源码上用 ``recognize_source`` / ``summarize`` 计算基线结果；
- 在注释、docstring、字符串三处分别插入 **所有已登记门禁名**，识别结果不变；
- 选取函数体内有门禁调用（非签名依赖、非桩端点、非仅登录）的样例，把门禁调用移入
  ``if`` / ``try`` / ``for`` 块，验证只有 ``conditional`` 标注改变。
- hypothesis 只控制「要注入哪些门禁名」的组合，固定样例覆盖全部自检样例。
"""
from __future__ import annotations

import re
import sys
import textwrap
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

# ─── 让 backend/scripts/gen 可 import ───────────────────────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "gen"))
from authz_inventory import classify, gates, selfcheck  # noqa: E402

# 同时加载影响清单的样例源码（它们定义在脚本文件里）
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "gen"))
from gen_edit_level_impact_inventory import (  # noqa: E402
    _IMPACT_HEAD,
    _S1, _S2, _S3, _S4, _S5, _S7, _S8,
)

# ─── 辅助常量与函数 ─────────────────────────────────────────────────────────

# 所有已登记门禁名（用于注入噪声）
ALL_GATE_NAMES: tuple[str, ...] = tuple(gates.REGISTRY.keys())

# 需求 1.6 的 9 个自检样例（取自 selfcheck.py 的源码片段 + 公用头部）
_NOTE_HEAD = selfcheck._NOTE_HEAD  # type: ignore[attr-defined]
_NOTE_SNIPPETS: dict[str, str] = {
    "无任何鉴权依赖": selfcheck._NO_AUTH,  # type: ignore[attr-defined]
    "只依赖登录": selfcheck._LOGIN_ONLY,  # type: ignore[attr-defined]
    "docstring与注释里写有edit": selfcheck._TEXT_ONLY_EDIT,  # type: ignore[attr-defined]
    "签名依赖edit": selfcheck._SIGNATURE_EDIT,  # type: ignore[attr-defined]
    "辅助函数edit": selfcheck._HELPER_EDIT,  # type: ignore[attr-defined]
    "附注编辑门禁": selfcheck._NOTE_GATE,  # type: ignore[attr-defined]
    "签名readonly": selfcheck._SIGNATURE_READONLY,  # type: ignore[attr-defined]
    "未实现": selfcheck._NOT_IMPLEMENTED,  # type: ignore[attr-defined]
    "未登记依赖": selfcheck._UNREGISTERED,  # type: ignore[attr-defined]
}

# 需求 9.8 的 10 个自检样例中，识别层面有实质内容的样例源码（_S9/_S10/_S11 由影响清单独有逻辑处理，
# 识别器层面它们的门禁识别仍适用 Property 16，但需要 impact 专用 head）
_IMPACT_SNIPPETS: dict[str, tuple[str, str]] = {
    "签名edit(影响)": (_S1, "s1_endpoint"),
    "body位置参数edit(影响)": (_S2, "s2_endpoint"),
    "body关键字edit(影响)": (_S3, "s3_endpoint"),
    "常量edit(影响)": (_S4, "s4_endpoint"),
    "if分支edit(影响)": (_S5, "s5_endpoint"),
    "review不计(影响)": (_S7, "s7_endpoint"),
    "注释字符串不计(影响)": (_S8, "s8_endpoint"),
}


def _note_source(snippet: str) -> str:
    """拼出完整的附注清册样例源码。"""
    return textwrap.dedent(_NOTE_HEAD) + textwrap.dedent(snippet)


def _impact_source(snippet: str) -> str:
    """拼出完整的影响清单样例源码。"""
    return textwrap.dedent(_IMPACT_HEAD) + textwrap.dedent(snippet)


def _recognize(full_source: str, function: str = "endpoint") -> dict[str, Any]:
    """对合成源码做识别，返回 summarize 的比对视图。"""
    result = selfcheck.recognize_source(full_source, function)
    return selfcheck.summarize(result)


def _note_classify(full_source: str) -> dict[str, Any]:
    """附注清册维度：类别 + 最高级别 + 问题。"""
    result = selfcheck.recognize_source(full_source, "endpoint")
    return {
        "category": classify.classify(selfcheck.SAMPLE_FILE, result).category,
        "max_level": gates.max_level(result.uses),
        "issues": tuple(sorted((i.kind, i.name) for i in result.issues)),
    }


# ─── 注入辅助函数 ────────────────────────────────────────────────────────────

def _inject_comment(source: str, gate_names: list[str]) -> str:
    """在源码每个函数体的 ``return`` 之前插入包含门禁名的注释。"""
    lines = source.splitlines(True)
    injected: list[str] = []
    for line in lines:
        if line.strip().startswith("return"):
            indent = " " * (len(line) - len(line.lstrip()))
            for name in gate_names:
                injected.append(f'{indent}# 噪声: {name}("edit") 这是注释\n')
        injected.append(line)
    return "".join(injected)


def _inject_docstring(source: str, gate_names: list[str]) -> str:
    """在每个 ``async def`` 函数的 docstring 中插入门禁名。

    如果函数没有 docstring，在函数头部后插入一个。
    """
    lines = source.splitlines(True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        result.append(lines[i])
        if re.match(r"^\s*(async\s+)?def\s+\w+", lines[i]) and lines[i].rstrip().endswith(":"):
            indent = " " * (len(lines[i]) - len(lines[i].lstrip()) + 4)
            # 检查下一行是否已有 docstring
            next_i = i + 1
            if next_i < len(lines) and ('"""' in lines[next_i] or "'''" in lines[next_i]):
                # 已有 docstring，在其后追加门禁名
                result.append(lines[next_i])
                noise = " ".join(f'{n}("edit")' for n in gate_names)
                result.append(f'{indent}# （docstring 内）{noise}\n')
                i = next_i + 1
                continue
            else:
                # 插入新 docstring
                noise = " ".join(f'Depends({n}("edit"))' for n in gate_names)
                result.append(f'{indent}"""{noise}"""\n')
        i += 1
    return "".join(result)


def _inject_string(source: str, gate_names: list[str]) -> str:
    """在源码每个函数体的 ``return`` 之前插入包含门禁名的字符串赋值。"""
    lines = source.splitlines(True)
    injected: list[str] = []
    for line in lines:
        if line.strip().startswith("return"):
            indent = " " * (len(line) - len(line.lstrip()))
            for name in gate_names:
                injected.append(f'{indent}_noise_{name} = \'Depends({name}("edit"))\'\n')
        injected.append(line)
    return "".join(injected)


def _wrap_in_if(source: str) -> str:
    """将函数体内的 ``await`` 门禁调用移入 ``if True:`` 块。"""
    lines = source.splitlines(True)
    result: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("await ") and any(g in stripped for g in ALL_GATE_NAMES):
            indent = " " * (len(line) - len(line.lstrip()))
            result.append(f"{indent}if True:\n")
            result.append(f"{indent}    {stripped}")
        else:
            result.append(line)
    return "".join(result)


def _wrap_in_try(source: str) -> str:
    """将函数体内的 ``await`` 门禁调用移入 ``try:`` 块。"""
    lines = source.splitlines(True)
    result: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("await ") and any(g in stripped for g in ALL_GATE_NAMES):
            indent = " " * (len(line) - len(line.lstrip()))
            result.append(f"{indent}try:\n")
            result.append(f"{indent}    {stripped}")
            result.append(f"{indent}except Exception:\n")
            result.append(f"{indent}    pass\n")
        else:
            result.append(line)
    return "".join(result)


def _wrap_in_loop(source: str) -> str:
    """将函数体内的 ``await`` 门禁调用移入 ``for _ in [1]:`` 块。"""
    lines = source.splitlines(True)
    result: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("await ") and any(g in stripped for g in ALL_GATE_NAMES):
            indent = " " * (len(line) - len(line.lstrip()))
            result.append(f"{indent}for _ in [1]:\n")
            result.append(f"{indent}    {stripped}")
        else:
            result.append(line)
    return "".join(result)


def _set_conditional(view: dict[str, Any], to: bool) -> dict[str, Any]:
    """复制 summarize 视图，把所有 forms 条目的 conditional 标志改为 ``to``。"""
    new_forms = []
    for name, via, level, _cond, chain, param, params in view["forms"]:
        # 只改 body 来源的（签名 / router / route / registration 不受 if/try/loop 影响）
        if via == "body":
            new_forms.append((name, via, level, to, chain, param, params))
        else:
            new_forms.append((name, via, level, _cond, chain, param, params))
    return {**view, "forms": tuple(sorted(new_forms, key=repr))}


# ─── hypothesis 策略 ──────────────────────────────────────────────────────────

gate_name_subset = st.lists(
    st.sampled_from(ALL_GATE_NAMES),
    min_size=1,
    max_size=min(5, len(ALL_GATE_NAMES)),
    unique=True,
)


# ─── Property 16a：注释 / docstring / 字符串中插入门禁名不改变识别结果 ──────────

class TestCommentDocstringStringImmunity:
    """在注释、docstring、字符串中插入任意门禁名后，识别结果不变。

    **Validates: Requirements 1.8, 9.1**
    """

    # ── 附注清册样例（需求 1.6）──────────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet", list(_NOTE_SNIPPETS.items()), ids=list(_NOTE_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_note_samples_comment_immune(self, label: str, snippet: str, names: list[str]) -> None:
        """附注样例：注释中插入门禁名不影响归类与识别。"""
        clean = _note_source(snippet)
        baseline = _note_classify(clean)
        injected = _inject_comment(clean, names)
        assert _note_classify(injected) == baseline

    @pytest.mark.parametrize("label,snippet", list(_NOTE_SNIPPETS.items()), ids=list(_NOTE_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_note_samples_docstring_immune(self, label: str, snippet: str, names: list[str]) -> None:
        """附注样例：docstring 中插入门禁名不影响归类与识别。"""
        clean = _note_source(snippet)
        baseline = _note_classify(clean)
        injected = _inject_docstring(clean, names)
        assert _note_classify(injected) == baseline

    @pytest.mark.parametrize("label,snippet", list(_NOTE_SNIPPETS.items()), ids=list(_NOTE_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_note_samples_string_immune(self, label: str, snippet: str, names: list[str]) -> None:
        """附注样例：字符串中插入门禁名不影响归类与识别。"""
        clean = _note_source(snippet)
        baseline = _note_classify(clean)
        injected = _inject_string(clean, names)
        assert _note_classify(injected) == baseline

    # ── 影响清单样例（需求 9.8）──────────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet_func", list(_IMPACT_SNIPPETS.items()),
                             ids=list(_IMPACT_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_impact_samples_comment_immune(self, label: str, snippet_func: tuple[str, str],
                                           names: list[str]) -> None:
        """影响清单样例：注释中插入门禁名不影响识别。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        injected = _inject_comment(clean, names)
        assert _recognize(injected, func) == baseline

    @pytest.mark.parametrize("label,snippet_func", list(_IMPACT_SNIPPETS.items()),
                             ids=list(_IMPACT_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_impact_samples_docstring_immune(self, label: str, snippet_func: tuple[str, str],
                                             names: list[str]) -> None:
        """影响清单样例：docstring 中插入门禁名不影响识别。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        injected = _inject_docstring(clean, names)
        assert _recognize(injected, func) == baseline

    @pytest.mark.parametrize("label,snippet_func", list(_IMPACT_SNIPPETS.items()),
                             ids=list(_IMPACT_SNIPPETS.keys()))
    @given(names=gate_name_subset)
    @settings(max_examples=5)
    @example(names=list(ALL_GATE_NAMES)[:5])
    def test_impact_samples_string_immune(self, label: str, snippet_func: tuple[str, str],
                                          names: list[str]) -> None:
        """影响清单样例：字符串中插入门禁名不影响识别。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        injected = _inject_string(clean, names)
        assert _recognize(injected, func) == baseline


# ─── Property 16b：门禁调用移入 if / try / 循环后只多出「条件执行」───────────────

# 选取函数体内有 await 门禁调用的样例（签名依赖和桩端点不适用）
_BODY_CALL_NOTE_SAMPLES = {
    "辅助函数edit": selfcheck._HELPER_EDIT,  # type: ignore[attr-defined]
    "附注编辑门禁": selfcheck._NOTE_GATE,  # type: ignore[attr-defined]
}

_BODY_CALL_IMPACT_SAMPLES: dict[str, tuple[str, str]] = {
    "body位置参数edit(影响)": (_S2, "s2_endpoint"),
    "body关键字edit(影响)": (_S3, "s3_endpoint"),
}

# _S5 已经在 if 分支内，基线 conditional 已为 True；用于验证 try/loop 同理
_ALREADY_CONDITIONAL_IMPACT: dict[str, tuple[str, str]] = {
    "if分支edit(影响)": (_S5, "s5_endpoint"),
}


class TestConditionalExecutionFlag:
    """门禁调用移入 if / try / 循环后，只有 ``conditional`` 标志变为 True，其余不变。

    **Validates: Requirements 1.8, 9.1**
    """

    # ── 附注样例：if ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet", list(_BODY_CALL_NOTE_SAMPLES.items()),
                             ids=list(_BODY_CALL_NOTE_SAMPLES.keys()))
    def test_note_body_call_if_only_conditional_changes(self, label: str, snippet: str) -> None:
        """附注样例：await 门禁调用移入 if True 块后只多出条件执行标注。"""
        clean = _note_source(snippet)
        baseline = _recognize(clean)
        wrapped = _wrap_in_if(clean)
        actual = _recognize(wrapped)
        expected = _set_conditional(baseline, True)
        assert actual == expected, f"差异：baseline={baseline}, actual={actual}"

    # ── 附注样例：try ────────────────────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet", list(_BODY_CALL_NOTE_SAMPLES.items()),
                             ids=list(_BODY_CALL_NOTE_SAMPLES.keys()))
    def test_note_body_call_try_only_conditional_changes(self, label: str, snippet: str) -> None:
        """附注样例：await 门禁调用移入 try 块后只多出条件执行标注。"""
        clean = _note_source(snippet)
        baseline = _recognize(clean)
        wrapped = _wrap_in_try(clean)
        actual = _recognize(wrapped)
        expected = _set_conditional(baseline, True)
        assert actual == expected

    # ── 附注样例：for 循环 ───────────────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet", list(_BODY_CALL_NOTE_SAMPLES.items()),
                             ids=list(_BODY_CALL_NOTE_SAMPLES.keys()))
    def test_note_body_call_loop_only_conditional_changes(self, label: str, snippet: str) -> None:
        """附注样例：await 门禁调用移入 for 循环后只多出条件执行标注。"""
        clean = _note_source(snippet)
        baseline = _recognize(clean)
        wrapped = _wrap_in_loop(clean)
        actual = _recognize(wrapped)
        expected = _set_conditional(baseline, True)
        assert actual == expected

    # ── 影响清单样例：if / try / loop ────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet_func", list(_BODY_CALL_IMPACT_SAMPLES.items()),
                             ids=list(_BODY_CALL_IMPACT_SAMPLES.keys()))
    def test_impact_body_call_if_only_conditional_changes(self, label: str, snippet_func: tuple[str, str]) -> None:
        """影响清单样例：await 门禁调用移入 if True 块后只多出条件执行标注。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        wrapped = _wrap_in_if(clean)
        actual = _recognize(wrapped, func)
        expected = _set_conditional(baseline, True)
        assert actual == expected

    @pytest.mark.parametrize("label,snippet_func", list(_BODY_CALL_IMPACT_SAMPLES.items()),
                             ids=list(_BODY_CALL_IMPACT_SAMPLES.keys()))
    def test_impact_body_call_try_only_conditional_changes(self, label: str, snippet_func: tuple[str, str]) -> None:
        """影响清单样例：await 门禁调用移入 try 块后只多出条件执行标注。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        wrapped = _wrap_in_try(clean)
        actual = _recognize(wrapped, func)
        expected = _set_conditional(baseline, True)
        assert actual == expected

    @pytest.mark.parametrize("label,snippet_func", list(_BODY_CALL_IMPACT_SAMPLES.items()),
                             ids=list(_BODY_CALL_IMPACT_SAMPLES.keys()))
    def test_impact_body_call_loop_only_conditional_changes(self, label: str, snippet_func: tuple[str, str]) -> None:
        """影响清单样例：await 门禁调用移入 for 循环后只多出条件执行标注。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        wrapped = _wrap_in_loop(clean)
        actual = _recognize(wrapped, func)
        expected = _set_conditional(baseline, True)
        assert actual == expected

    # ── 已在条件分支内的样例保持不变 ──────────────────────────────────────────

    @pytest.mark.parametrize("label,snippet_func", list(_ALREADY_CONDITIONAL_IMPACT.items()),
                             ids=list(_ALREADY_CONDITIONAL_IMPACT.keys()))
    def test_already_conditional_stays_conditional(self, label: str, snippet_func: tuple[str, str]) -> None:
        """已在 if 块里的门禁调用再包 try/loop，conditional 仍为 True（幂等）。"""
        snippet, func = snippet_func
        clean = _impact_source(snippet)
        baseline = _recognize(clean, func)
        # 已经 conditional，包 try 后仍是 conditional
        for wrapper in (_wrap_in_try, _wrap_in_loop):
            wrapped = wrapper(clean)
            actual = _recognize(wrapped, func)
            assert actual == baseline, f"wrapper={wrapper.__name__}, diff: {actual} vs {baseline}"


# ─── 固定样例：self-check 验证（覆盖全部 19 个自检样例的基线正确性）────────────

class TestSelfCheckSamplesBaseline:
    """验证自检样例本身的基线结果与 selfcheck.py 的期望一致。

    这确保 Property 16 的基线正确（不是用错误基线比对注入后的结果）。
    """

    def test_note_inventory_selfcheck_passes(self) -> None:
        """附注清册 9 个自检样例全部通过。"""
        failures = selfcheck.run_samples(selfcheck.NOTE_INVENTORY_SAMPLES)
        assert not failures, "\n".join(f.message() for f in failures)

    def test_impact_inventory_selfcheck_passes(self) -> None:
        """影响清单全部自检样例通过（含 note-pull-followup-closure R20 的「同函数同门禁两处」）。"""
        from gen_edit_level_impact_inventory import IMPACT_INVENTORY_SAMPLES as samples
        failures = selfcheck.run_samples(samples)
        assert not failures, "\n".join(f.message() for f in failures)


# ─── Property 17: 清册归类唯一且计数守恒 ──────────────────────────────────────
# Feature: partner-manager-edit-permission, Property 17: 清册归类唯一且计数守恒


class _SourceSnippets:
    """各类别的最小合成源码片段（拼到 _NOTE_HEAD 之后形成完整模块）。

    每个片段产出恰好一个写端点，其识别结果无 issue，因此 classify 能归类。
    """

    # S：函数体只抛 501，签名无 db / upload / background_tasks
    S = '''
@router.post("/stub")
async def ep_s(project_id: str):
    raise HTTPException(status_code=501, detail="尚未实现")
'''

    # C：所在文件名以 consol_ 开头（classify 只看文件名，识别结果与 E 相同也行）
    #    —— 用 signature edit 让它能正常识别
    C_EDIT = '''
@router.post("/consol-edit")
async def ep_c(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("edit"))):
    return None
'''

    # G：已走交付中心门禁
    G_HEAD = '''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access
from app.services.note_edit_gate import assert_note_edit_access
from app.routers.deliverable import _guard_action, DeliverableAction

router = APIRouter(prefix="/api/selfcheck/{project_id}")
'''
    G = '''
@router.post("/deliverable-action")
async def ep_g(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await _guard_action(db, user, project_id, action=DeliverableAction.generate)
    return None
'''

    # E：签名依赖 edit 级
    E = '''
@router.post("/edit-level")
async def ep_e(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("edit"))):
    return None
'''

    # E（附注编辑门禁形态）
    E_NOTE_GATE = '''
@router.post("/note-edit-gate")
async def ep_e_gate(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await assert_note_edit_access(db, user, project_id, consol_lock=False)
    return None
'''

    # E（review 级也归 E）
    E_REVIEW = '''
@router.post("/review-level")
async def ep_e_review(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("review"))):
    return None
'''

    # R：readonly 级
    R = '''
@router.post("/readonly-level")
async def ep_r(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_project_access("readonly"))):
    return None
'''

    # X：全局角色，无项目级判定
    X_HEAD = '''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user, require_project_access, require_role
from app.services.note_edit_gate import assert_note_edit_access

router = APIRouter(prefix="/api/selfcheck/{project_id}")
'''
    X = '''
@router.post("/global-role-only")
async def ep_x(project_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_role(["admin"]))):
    return None
'''

    # I（无任何鉴权）
    I_NONE = '''
@router.post("/no-auth")
async def ep_i(project_id: str, db: AsyncSession = Depends(get_db)):
    return None
'''

    # I（仅登录）
    I_LOGIN = '''
@router.post("/login-only")
async def ep_i_login(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return None
'''


def _model_classify(file: str, result: gates.EndpointGates) -> str | None:
    """独立模型：按 S → C → G → E → R → X → I 取第一个满足的类别。

    与 classify.classify 完全独立实现，作为对拍参照。
    """
    if result.issues:
        return None

    uses = [u for u in result.uses if u.category != "neutral"]
    found = {u.category for u in uses}
    levels = [u.level for u in uses if u.category in gates.LEVELLED and u.level]
    level = max(levels, key=gates.LEVEL_RANK.__getitem__) if levels else None

    # S：函数体只抛已废弃/未实现错误，签名无 db_session/upload_file/background_tasks
    if result.stub and set(result.stub) <= classify.STUB_ERRORS \
            and not result.signature_kinds & classify.STUB_SIGNATURE_KINDS:
        return "S"

    # C：文件名以 consol_ 开头
    from pathlib import PurePosixPath
    if PurePosixPath(file).name.startswith(classify.CONSOL_PREFIX):
        return "C"

    # G：已走交付中心门禁
    if "deliverable" in found:
        return "G"

    # E：已走附注编辑门禁，或项目级最高级别为 edit / review
    if "note_edit" in found:
        return "E"
    if level in ("edit", "review"):
        return "E"

    # R：readonly
    if level == "readonly":
        return "R"

    # X：有全局角色判定，无项目级判定
    if "global_role" in found:
        return "X"

    # I：仅登录或无鉴权
    if found <= {"identity"}:
        return "I"

    return None


# ─── 固定样例集合 ──────────────────────────────────────────────────────────────

# 每个类别一份合成源码 + 文件名 + 函数名 + 期望类别
_FIXED_SAMPLES: list[tuple[str, str, str, str]] = [
    # (label, full_source, function, expected_category)
    ("S_stub", _note_source(_SourceSnippets.S), "ep_s", "S"),
    ("C_consol", textwrap.dedent(_NOTE_HEAD) + textwrap.dedent(_SourceSnippets.C_EDIT), "ep_c", "C"),
    ("G_deliverable", textwrap.dedent(_SourceSnippets.G_HEAD) + textwrap.dedent(_SourceSnippets.G), "ep_g", "G"),
    ("E_edit", _note_source(_SourceSnippets.E), "ep_e", "E"),
    ("E_note_gate", _note_source(_SourceSnippets.E_NOTE_GATE), "ep_e_gate", "E"),
    ("E_review", _note_source(_SourceSnippets.E_REVIEW), "ep_e_review", "E"),
    ("R_readonly", _note_source(_SourceSnippets.R), "ep_r", "R"),
    ("X_global_role", textwrap.dedent(_SourceSnippets.X_HEAD) + textwrap.dedent(_SourceSnippets.X), "ep_x", "X"),
    ("I_no_auth", _note_source(_SourceSnippets.I_NONE), "ep_i", "I"),
    ("I_login", _note_source(_SourceSnippets.I_LOGIN), "ep_i_login", "I"),
]

# C 类使用 consol_ 前缀文件名
_CONSOL_FILE = "backend/app/routers/consol_selfcheck.py"


# ─── hypothesis 策略：随机选一组门禁形态的源码片段 ──────────────────────────────

# 可用片段按类别组织（片段, 文件, 函数名）
_SNIPPET_POOL: list[tuple[str, str, str, str]] = [
    ("S", _note_source(_SourceSnippets.S), selfcheck.SAMPLE_FILE, "ep_s"),
    ("C", textwrap.dedent(_NOTE_HEAD) + textwrap.dedent(_SourceSnippets.C_EDIT), _CONSOL_FILE, "ep_c"),
    ("G", textwrap.dedent(_SourceSnippets.G_HEAD) + textwrap.dedent(_SourceSnippets.G), selfcheck.SAMPLE_FILE, "ep_g"),
    ("E", _note_source(_SourceSnippets.E), selfcheck.SAMPLE_FILE, "ep_e"),
    ("E", _note_source(_SourceSnippets.E_NOTE_GATE), selfcheck.SAMPLE_FILE, "ep_e_gate"),
    ("E", _note_source(_SourceSnippets.E_REVIEW), selfcheck.SAMPLE_FILE, "ep_e_review"),
    ("R", _note_source(_SourceSnippets.R), selfcheck.SAMPLE_FILE, "ep_r"),
    ("X", textwrap.dedent(_SourceSnippets.X_HEAD) + textwrap.dedent(_SourceSnippets.X), selfcheck.SAMPLE_FILE, "ep_x"),
    ("I", _note_source(_SourceSnippets.I_NONE), selfcheck.SAMPLE_FILE, "ep_i"),
    ("I", _note_source(_SourceSnippets.I_LOGIN), selfcheck.SAMPLE_FILE, "ep_i_login"),
]

# hypothesis 策略：从池中随机选 1~7 个片段（每个端点代表一个独立的写端点）
endpoint_set = st.lists(
    st.sampled_from(_SNIPPET_POOL),
    min_size=1,
    max_size=len(_SNIPPET_POOL),
    unique_by=lambda x: x[2] + "/" + x[3],  # 按函数名去重（同源码不重复选）
)


class TestClassificationUniqueAndConserved:
    """清册归类唯一且计数守恒。

    **Validates: Requirements 1.2, 1.5**

    由登记门禁形态随机组合的合成写端点集合，每个端点恰归一类且等于「S → C → G → E → R → X → I
    取第一个满足」的模型，各类计数之和等于总数，（方法，完整路径）各出现一次；每类一个固定样例。
    """

    # ── 固定样例：每类一个 ──────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "label,source,func,expected",
        _FIXED_SAMPLES,
        ids=[s[0] for s in _FIXED_SAMPLES],
    )
    def test_fixed_sample_category(self, label: str, source: str, func: str, expected: str) -> None:
        """每类一个固定样例：归类结果等于期望。"""
        # C 类用 consol_ 前缀文件名
        file = _CONSOL_FILE if expected == "C" else selfcheck.SAMPLE_FILE
        result = selfcheck.recognize_source(source, func, file=file)
        verdict = classify.classify(file, result)
        assert verdict.category == expected, (
            f"[{label}] 期望 {expected}，实际 {verdict.category}（原因：{verdict.reason}）"
        )

    @pytest.mark.parametrize(
        "label,source,func,expected",
        _FIXED_SAMPLES,
        ids=[s[0] for s in _FIXED_SAMPLES],
    )
    def test_fixed_sample_model_agrees(self, label: str, source: str, func: str, expected: str) -> None:
        """每个固定样例：模型与生产 classify 一致。"""
        file = _CONSOL_FILE if expected == "C" else selfcheck.SAMPLE_FILE
        result = selfcheck.recognize_source(source, func, file=file)
        model_cat = _model_classify(file, result)
        prod_cat = classify.classify(file, result).category
        assert model_cat == prod_cat == expected, (
            f"[{label}] model={model_cat}, prod={prod_cat}, expected={expected}"
        )

    # ── 固定样例覆盖检查：全部 7 个类别都有 ────────────────────────────────

    def test_fixed_samples_cover_all_categories(self) -> None:
        """固定样例至少覆盖全部 7 个类别。"""
        covered = {s[3] for s in _FIXED_SAMPLES}  # expected category
        assert covered == set(classify.CATEGORY_ORDER), (
            f"固定样例覆盖 {sorted(covered)}，需要 {sorted(classify.CATEGORY_ORDER)}"
        )

    # ── Property 17：随机端点集合的归类性质 ──────────────────────────────────

    @given(endpoints=endpoint_set)
    @settings(max_examples=5)
    @example(endpoints=_SNIPPET_POOL[:7])  # 覆盖全部类别的组合
    def test_each_endpoint_gets_exactly_one_category(
        self, endpoints: list[tuple[str, str, str, str]]
    ) -> None:
        """每个端点恰归一类（category 非 None）。"""
        for expected_cat, source, file, func in endpoints:
            result = selfcheck.recognize_source(source, func, file=file)
            verdict = classify.classify(file, result)
            assert verdict.category is not None, (
                f"端点 {func} 未归类：{verdict.reason}"
            )
            assert verdict.category in classify.CATEGORY_ORDER, (
                f"端点 {func} 归类为 {verdict.category}，不在 {classify.CATEGORY_ORDER} 中"
            )

    @given(endpoints=endpoint_set)
    @settings(max_examples=5)
    @example(endpoints=_SNIPPET_POOL[:7])
    def test_model_and_production_agree(
        self, endpoints: list[tuple[str, str, str, str]]
    ) -> None:
        """独立模型与生产 classify 对每个端点给出相同归类。"""
        for expected_cat, source, file, func in endpoints:
            result = selfcheck.recognize_source(source, func, file=file)
            prod = classify.classify(file, result).category
            model = _model_classify(file, result)
            assert prod == model, (
                f"端点 {func}：生产 {prod} ≠ 模型 {model}"
            )

    @given(endpoints=endpoint_set)
    @settings(max_examples=5)
    @example(endpoints=_SNIPPET_POOL[:7])
    def test_category_counts_sum_to_total(
        self, endpoints: list[tuple[str, str, str, str]]
    ) -> None:
        """各类计数之和等于端点总数。"""
        from collections import Counter
        categories: list[str] = []
        for _exp, source, file, func in endpoints:
            result = selfcheck.recognize_source(source, func, file=file)
            cat = classify.classify(file, result).category
            assert cat is not None
            categories.append(cat)
        counts = Counter(categories)
        assert sum(counts.values()) == len(endpoints), (
            f"计数之和 {sum(counts.values())} ≠ 端点数 {len(endpoints)}；分布：{dict(counts)}"
        )

    @given(endpoints=endpoint_set)
    @settings(max_examples=5)
    @example(endpoints=_SNIPPET_POOL[:7])
    def test_method_path_uniqueness(
        self, endpoints: list[tuple[str, str, str, str]]
    ) -> None:
        """（方法，完整路径）在合成端点集内不重复（策略已去重）。"""
        seen: set[tuple[str, str]] = set()
        for _exp, source, file, func in endpoints:
            result = selfcheck.recognize_source(source, func, file=file)
            info = gates.analyze_module(file, textwrap.dedent(source))
            declared = [d for d in info.declared_routes() if d.function == func]
            assert declared, f"端点 {func} 没有路由声明"
            for d in declared:
                key = (d.method, d.path)
                assert key not in seen, f"重复的（方法，路径）：{key}"
                seen.add(key)

    # ── 归类结果等于池中期望的类别（交叉验证固定期望）────────────────────

    @given(endpoints=endpoint_set)
    @settings(max_examples=5)
    @example(endpoints=_SNIPPET_POOL[:7])
    def test_classification_matches_expected(
        self, endpoints: list[tuple[str, str, str, str]]
    ) -> None:
        """每个端点的归类结果等于池中标注的期望类别。"""
        for expected_cat, source, file, func in endpoints:
            result = selfcheck.recognize_source(source, func, file=file)
            actual = classify.classify(file, result).category
            assert actual == expected_cat, (
                f"端点 {func}：期望 {expected_cat}，实际 {actual}"
            )
