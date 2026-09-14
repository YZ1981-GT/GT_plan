# -*- coding: utf-8 -*-
"""粗裁理由码真源统一与 additive 零回归守卫。

Feature: procedure-trimming-and-delegation-intelligence — Task 12
Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.7, 8.8, 8.9, 14.5

═══ 本任务要解决的既有缺陷 ═══

改造前**粗裁与细裁各有一套理由体系**：

| 层 | 载体 | 形态 |
|---|---|---|
| 粗裁（`ProcedureTrimming.vue` → canonical trim） | `skip_reason` | **自由文本** |
| 细裁（`procedure_trim_engine`） | `TrimReasonCode` | **枚举** |

两套并存的后果不是「不好看」，而是**无法按理由码做全项目统计与复核** ——
裁剪充分性复核视图（Task 20）要回答「因重要性原因裁掉的科目金额合计是多少」，
自由文本答不了；而这正是准则要求的汇总考虑。

═══ 为什么 `reason_code` 必须 additive 扩在 canonical scope entry 上 ═══

实测 canonical trim 的 scope entry 只有
`{kind, cycle, wp_index_code, target_status, skip_reason}` 五个字段（前端
`commonApi.canonicalTrimPreview/Apply` 与后端 `TrimSchemeEntry` 双侧一致），
理由码**无处可落**。三条约束由此而来：

1. **必须与 `target_status` 同一次请求提交**。canonical trim 是
   preview → apply 两阶段 + 一次性凭证：凭证只覆盖本次 payload，
   「先 apply 状态再补写理由码」的第二次写入**没有凭证可消费**，且会留下
   「状态已改、理由码未写」的中间态（复核视图会把它算成「缺理由的裁剪」）。
2. **必须参与 request payload 归一**。preview 与 apply 的 payload 必须逐字节
   一致，否则触发防篡改校验 409。故 `reason_code` 必须进 `_normalize_entry`
   的返回 dict，不能只在写库时旁路读原始 entry。
3. **不得编码进 `skip_reason` 文本**。那样等于没有结构化字段，统计仍要靠
   字符串匹配；且会污染面向审计师的理由文案。

═══ additive 零回归的结构性保证 ═══

`_normalize_entry` **条件性**写入 `reason_code` 键（`if reason_code:`）而非
无条件写 `None`。这一行的取舍决定了整个扩展能否安全落地：

- 条件写入 ⇒ 不传该字段时 canonical payload 的键集与扩展前**完全相同**
  ⇒ payload hash 不变 ⇒ 存量 preview 凭证与既有测试零影响。
- 若改成无条件 `"reason_code": reason_code or None` ⇒ 所有存量 payload 多一个键
  ⇒ hash 全变 ⇒ 既有 canonical trim 测试与在途 preview 凭证全部 409。

:class:`TestAdditiveZeroRegression` 双向锁死这一点，Task 22 有对应变异。

═══ 断言分类 ═══

本任务实现与守卫同轮交付，故**全部应绿**。失败消息区分两类：
- 派生/扫描器自检失败 ⇒ 守卫坏了
- 契约比对失败 ⇒ 代码漂移
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

ENGINE_PY = BACKEND / "app" / "services" / "procedure_trim_engine.py"
SERVICE_PY = BACKEND / "app" / "services" / "procedure_trim_service.py"
ROUTER_PY = BACKEND / "app" / "routers" / "procedure_trim.py"
FE_MIRROR = (
    REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "composables"
    / "trimReasonCodes.ts"
)
FE_COMMON_API = (
    REPO / "audit-platform" / "frontend" / "src" / "services" / "commonApi.ts"
)

# 本 spec 新增的四个取值（R8.1）。
_NEW_CODES = {
    "no_data": "NO_DATA",
    "below_trivial": "BELOW_TRIVIAL",
    "below_materiality": "BELOW_MATERIALITY",
    "covered_elsewhere": "COVERED_ELSEWHERE",
}

# 改造前既有的四个取值 —— 必须逐个保留（R8.9：additive 扩展，不得删既有取值，
# 否则细裁存量数据的理由码会变成非法值）。
_LEGACY_CODES = {
    "no_related_business": "NO_RELATED_BUSINESS",
    "low_risk_assessment": "LOW_RISK_ASSESSMENT",
    "control_test_effective": "CONTROL_TEST_EFFECTIVE",
    "other": "OTHER",
}


# ══════════════════════════════════════════════════════════════════════════
# 源码读取工具（剥注释 + 剥 docstring）
# ══════════════════════════════════════════════════════════════════════════


def _ts_function_body(src: str, name: str) -> str:
    """取 TS 具名函数的**函数体**（花括号配对）。

    🔴 不能用 ``rf"function {name}[\\s\\S]*?\\n\\}}"`` 这类正则：平台已多次踩到
    「声明后第一个 ``{`` 命中的是**参数的内联类型字面量**」——
    ``function formatTrimReason(args: { reasonCode?: string })`` 的第一个 ``{``
    属于参数类型，按它截出来的"函数体"只有签名，随后 ``assert xxx in body``
    会在**正确实现**上打红（本守卫首版即因此假红）。

    正解 = 先用**圆括号配对**跳过整个参数列表，再从那之后找函数体的 ``{``
    并做花括号配对。
    """
    m = re.search(rf"function\s+{re.escape(name)}\s*\(", src)
    assert m, f"未找到函数 `{name}`（守卫自身缺陷或该函数已改名）"

    # ① 圆括号配对跳过参数列表
    i = m.end() - 1
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    assert depth == 0, f"`{name}` 参数列表括号未配平（守卫自身缺陷）"

    # ② 从参数列表之后找函数体起始 `{`（跳过返回类型注解）
    j = src.find("{", i)
    assert j != -1, f"`{name}` 未找到函数体起始花括号"
    depth = 0
    k = j
    while k < len(src):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j : k + 1]
        k += 1
    raise AssertionError(f"`{name}` 函数体花括号未配平（守卫自身缺陷）")


def test_ts_function_body_skips_parameter_type_literal():
    """反向自检：提取器必须跳过参数的内联类型字面量，否则守卫恒假红。

    🔴 fixture 的参数类型字面量必须**跨行**才能复现缺陷 —— 这正是被测的
    `formatTrimReason` 的真实写法。参数写成单行时朴素正则的第一个 ``\\n}``
    恰好就是函数真正的结尾，缺陷不出现，自检会失去意义（本自检首版即因此
    自打红：它报的不是提取器坏了，而是「fixture 选得不对」）。
    """
    fixture = (
        "export function f(args: {\n"
        "  a?: string | null\n"
        "  b?: string | null\n"
        "}): string {\n"
        "  const marker = 1\n"
        "  return String(marker)\n"
        "}\n"
    )
    body = _ts_function_body(fixture, "f")
    assert "const marker" in body, "提取器仍命中参数类型字面量（首版缺陷形态复现）"
    assert "a?: string" not in body, "参数类型被误当函数体"

    # 朴素正则在同一 fixture 上必须真的失败，否则本自检是空转
    naive = re.search(r"function\s+f[\s\S]*?\n\}", fixture)
    assert naive is not None
    assert "const marker" not in naive.group(0), (
        "朴素正则在本 fixture 上未复现缺陷 ⇒ 本自检失去意义，需换成跨行参数类型的 fixture"
    )


def _read(path: Path) -> str:
    assert path.exists(), f"守卫依赖的文件不存在：{path}（守卫自身缺陷或文件被移动）"
    return path.read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """剥 `#` 注释 + 剥 docstring，保留普通字符串字面量。

    🔴 必须剥：本文件与被测文件的注释里大量写着 `reason_code` / `skip_reason`
    作为**说明文字**，裸子串扫描会把说明数成真实代码（平台已多次踩此坑）。
    普通字符串字面量**不剥** —— 枚举取值本身就是字符串字面量。
    """
    # 1) 剥 `#` 注释（tokenize 能正确跳过字符串内的 `#`）
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok.line if False else "")
        # tokenize 逐 token 重建过于脆弱，改用行级：先定位注释起始列
        lines = src.splitlines()
        comment_cols: dict[int, int] = {}
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                comment_cols.setdefault(row, col)
        stripped = [
            (ln[: comment_cols[i + 1]] if (i + 1) in comment_cols else ln)
            for i, ln in enumerate(lines)
        ]
        src_no_comment = "\n".join(stripped)
    except tokenize.TokenError:
        src_no_comment = src

    # 2) 剥 docstring（AST 定位行号后置空）
    try:
        tree = ast.parse(src_no_comment)
    except SyntaxError:
        return src_no_comment
    lines = src_no_comment.splitlines()
    blank: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    kept = [("" if (i + 1) in blank else ln) for i, ln in enumerate(lines)]
    return "\n".join(kept)


def _func_span(src: str, name: str) -> tuple[int, int]:
    """返回函数体行号区间（1-based，闭区间）。"""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node.lineno, (node.end_lineno or node.lineno)
    pytest.fail(f"未在源码中找到函数 `{name}`（守卫自身缺陷或函数已改名）")


def _func_code(src: str, name: str) -> str:
    """取某函数的**代码**（已剥注释与 docstring）。"""
    start, end = _func_span(src, name)
    code = _code_only(src)
    return "\n".join(code.splitlines()[start - 1 : end])


# ══════════════════════════════════════════════════════════════════════════
# 类 A：扫描器自检（失败 ⇒ 守卫坏了）
# ══════════════════════════════════════════════════════════════════════════


class TestScannerSelfCheck:
    """判据基础设施有效性 —— 这些绿了才说明后面的比对不是空转。"""

    def test_strip_comments_removes_说明文字_but_keeps_string_literals(self):
        sample = (
            'CODE = "below_materiality"  # 这里提到 reason_code 只是说明\n'
            "def f():\n"
            '    """docstring 里提到 skip_reason 也是说明"""\n'
            '    return "no_data"\n'
        )
        code = _code_only(sample)
        assert "只是说明" not in code, "剥注释失效"
        assert "也是说明" not in code, "剥 docstring 失效"
        assert '"below_materiality"' in code, "误剥了字符串字面量（枚举取值会消失）"
        assert '"no_data"' in code, "误剥了字符串字面量"

    def test_engine_source_has_comment_mentions(self):
        """反向自检：被测文件的注释里确实含目标字样，证明剥注释这一步不是空操作。"""
        raw = _read(ENGINE_PY)
        code = _code_only(raw)
        # 注释里必然提到本 spec 名，剥后应消失
        assert "procedure-trimming-and-delegation-intelligence" in raw, (
            "engine 未留 spec 溯源注释；若确已移除，请同步调整本自检"
        )
        assert "procedure-trimming-and-delegation-intelligence" not in code, (
            "剥注释未生效 —— 后续所有源码断言都可能被说明文字骗过"
        )

    def test_func_code_extraction_skips_return_type_annotation(self):
        """反向自检：截函数体不得命中返回类型注解里的花括号（平台已踩此坑）。"""
        sample = (
            "def g(a: int) -> dict:\n"
            "    x = 1\n"
            "    return {'k': x}\n"
        )
        body = _func_code(sample, "g")
        assert "x = 1" in body
        assert "def g" in body


# ══════════════════════════════════════════════════════════════════════════
# 类 B：契约比对（失败 ⇒ 代码漂移）
# ══════════════════════════════════════════════════════════════════════════


def _backend_enum_members() -> dict[str, str]:
    """从后端 `TrimReasonCode` 抽 `{value: MEMBER_NAME}`（AST 派生，不用正则）。"""
    src = _read(ENGINE_PY)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TrimReasonCode":
            out: dict[str, str] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target = stmt.targets[0]
                    if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant):
                        if isinstance(stmt.value.value, str):
                            out[stmt.value.value] = target.id
            assert out, "TrimReasonCode 类体内未抽到任何取值（守卫自身缺陷）"
            return out
    pytest.fail("未找到 `class TrimReasonCode`（守卫自身缺陷或类已改名）")


def _frontend_mirror_values() -> list[str]:
    """从前端镜像抽 `TRIM_REASON_CODES` 数组的取值（顺序保留）。"""
    src = _code_only_ts(_read(FE_MIRROR))
    m = re.search(r"TRIM_REASON_CODES\s*(?::[^=]*)?=\s*\[(.*?)\]", src, re.S)
    assert m, "前端镜像未找到 `TRIM_REASON_CODES` 数组（守卫自身缺陷或已改名）"
    return re.findall(r"['\"]([a-z_]+)['\"]", m.group(1))


def _frontend_label_keys() -> set[str]:
    src = _code_only_ts(_read(FE_MIRROR))
    m = re.search(r"TRIM_REASON_LABELS\s*(?::[^=]*)?=\s*\{(.*?)\n\}", src, re.S)
    assert m, "前端镜像未找到 `TRIM_REASON_LABELS`（守卫自身缺陷或已改名）"
    return set(re.findall(r"([a-z_]+)\s*:", m.group(1)))


def _code_only_ts(src: str) -> str:
    """剥 TS 的 `//` 与 `/* */` 注释（带字符串状态，不被 `accept="image/*"` 骗）。"""
    out: list[str] = []
    i = 0
    n = len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


class TestBackendEnumAdditive:
    """后端枚举：新增四个取值，且既有四个逐个保留。"""

    def test_new_codes_present(self):
        members = _backend_enum_members()
        for value, name in _NEW_CODES.items():
            assert value in members, (
                f"后端 TrimReasonCode 缺取值 `{value}`（R8.1）"
            )
            assert members[value] == name, (
                f"取值 `{value}` 的成员名应为 `{name}`，实际 `{members[value]}`"
            )

    def test_legacy_codes_preserved(self):
        """R8.9：additive —— 删既有取值会让细裁存量数据的理由码变成非法值。"""
        members = _backend_enum_members()
        for value, name in _LEGACY_CODES.items():
            assert value in members, (
                f"既有取值 `{value}` 被删除 —— 这不是 additive 扩展，"
                "细裁存量记录的理由码会变成非法值"
            )
            assert members[value] == name

    def test_no_unexpected_values(self):
        """取值域必须恰为「既有 4 + 新增 4」，防悄悄塞第九个取值绕过标签要求。"""
        members = _backend_enum_members()
        expected = set(_LEGACY_CODES) | set(_NEW_CODES)
        assert set(members) == expected, (
            f"TrimReasonCode 取值域与预期不符。"
            f"多出 {sorted(set(members) - expected)}，缺少 {sorted(expected - set(members))}。"
            "新增取值必须同步：①本守卫的预期集合 ②前端 trimReasonCodes.ts 的数组与标签表"
        )


class TestFrontendMirrorCrossLock:
    """跨前后端交叉锁死：一侧新增另一侧未跟进即红。"""

    def test_mirror_values_equal_backend_enum(self):
        backend = set(_backend_enum_members())
        frontend = set(_frontend_mirror_values())
        assert frontend == backend, (
            "前端 `TRIM_REASON_CODES` 与后端 `TrimReasonCode` 取值域不等。"
            f"前端多出 {sorted(frontend - backend)}，前端缺少 {sorted(backend - frontend)}。"
            "🔴 两侧必须逐值相等 —— 前端多出会让 UI 显示后端拒绝的理由码，"
            "前端缺少会让后端已写入的理由码在界面上显示为空。"
        )

    def test_every_value_has_chinese_label(self):
        """R8.5：每个取值都有中文标签（UI 全中文化）。"""
        values = set(_frontend_mirror_values())
        labels = _frontend_label_keys()
        assert labels == values, (
            f"标签表与取值域不等：缺标签 {sorted(values - labels)}，"
            f"多余标签 {sorted(labels - values)}"
        )

    def test_labels_are_chinese_and_not_placeholder(self):
        src = _code_only_ts(_read(FE_MIRROR))
        m = re.search(r"TRIM_REASON_LABELS\s*(?::[^=]*)?=\s*\{(.*?)\n\}", src, re.S)
        assert m
        pairs = re.findall(r"([a-z_]+)\s*:\s*['\"]([^'\"]+)['\"]", m.group(1))
        assert len(pairs) >= 8, f"标签条目过少（{len(pairs)}），疑抽取失效"
        for key, label in pairs:
            assert re.search(r"[\u4e00-\u9fff]", label), (
                f"理由码 `{key}` 的标签 `{label}` 不含中文（违反 UI 全中文化铁律）"
            )
            assert label.strip() not in {"TODO", "待补充", "-", "未知"}, (
                f"理由码 `{key}` 的标签是占位符 `{label}`"
            )

    def test_mirror_declares_backend_source_of_truth(self):
        """镜像文件必须写明后端是真源，防后续会话把它当独立真源改。"""
        raw = _read(FE_MIRROR)
        assert "procedure_trim_engine" in raw, (
            "前端镜像未指明后端真源文件路径 —— 后续会话会把它当独立真源"
        )


class TestCanonicalEntryReasonCode:
    """canonical scope entry 的 `reason_code` additive 扩展。"""

    def test_router_model_has_optional_reason_code(self):
        code = _code_only(_read(ROUTER_PY))
        m = re.search(r"class\s+TrimSchemeEntry\b(.*?)(?=\nclass\s)", code, re.S)
        assert m, "未找到 `class TrimSchemeEntry`（守卫自身缺陷或已改名）"
        body = m.group(1)
        assert "reason_code" in body, (
            "`TrimSchemeEntry` 缺 `reason_code` 字段 —— 理由码无处可落（R8.7）"
        )
        assert re.search(r"reason_code\s*:\s*str\s*\|\s*None", body), (
            "`reason_code` 必须是可选（`str | None`）—— 必填会打断全部存量调用方"
        )

    def test_normalize_entry_carries_reason_code(self):
        """R8.8：`reason_code` 必须进归一结果，才能参与 preview/apply payload 一致性。"""
        code = _func_code(_read(SERVICE_PY), "_normalize_entry")
        assert "reason_code" in code, (
            "`_normalize_entry` 未处理 `reason_code` —— 它不会进 canonical payload，"
            "preview 与 apply 的 payload 会不一致（防篡改校验 409），"
            "或写库时只能旁路读原始 entry（绕过归一）"
        )

    def test_reason_code_validated_against_enum(self):
        """非法理由码必须在归一阶段拒绝，不能静默写进 JSONB。"""
        code = _func_code(_read(SERVICE_PY), "_normalize_entry")
        assert "_VALID_TRIM_REASON_CODES" in code, (
            "`_normalize_entry` 未校验 `reason_code` 取值域 —— "
            "拼错的理由码会静默落库，复核视图按理由码统计时该条被漏掉"
        )

    def test_write_path_persists_reason_code_in_same_transaction(self):
        """R8.8：理由码与 `skip_reason` 同事务写入，禁两次写入。"""
        src = _read(SERVICE_PY)
        code = _code_only(src)
        assert "_write_suggestion_reason_code" in code, (
            "未找到理由码写入 helper —— 理由码不会落库"
        )
        # apply 主流程里必须调用它
        apply_code = _func_code(src, "apply_scheme")
        assert "_write_suggestion_reason_code" in apply_code, (
            "`apply_scheme` 未调用理由码写入 —— 理由码只在请求里、不落库"
        )

    def test_no_second_write_endpoint_for_reason_code(self):
        """禁「先 apply 状态再补写理由码」的第二个写入入口。"""
        router_code = _code_only(_read(ROUTER_PY))
        forbidden = re.findall(r'@router\.(?:post|put|patch)\("([^"]*reason[^"]*)"', router_code)
        assert not forbidden, (
            f"新增了理由码专用写入端点 {forbidden} —— "
            "一次性 preview 凭证不覆盖第二次写入，会产生「状态已改、理由码未写」中间态"
        )

    def test_reason_code_not_encoded_into_skip_reason_text(self):
        """R8.3：理由码不得编码进自由文本字段。"""
        code = _func_code(_read(SERVICE_PY), "_normalize_entry")
        # 形态：skip_reason = f"[{reason_code}] ..." 或 skip_reason + reason_code 拼接
        assert not re.search(r"skip_reason\s*=\s*f?['\"].*reason_code", code), (
            "把理由码拼进 `skip_reason` 文本 —— 统计仍要靠字符串匹配，"
            "且污染面向审计师的理由文案"
        )


class TestAdditiveZeroRegression:
    """不传 `reason_code` 时 payload 与扩展前逐字节相同（R8.9 / R14.1）。"""

    def test_normalize_entry_writes_key_conditionally(self):
        """🔴 本 spec 最关键的零回归保证。

        条件写入 ⇒ 存量 payload 键集不变 ⇒ hash 不变 ⇒ 在途 preview 凭证与
        既有测试零影响。无条件写 `None` ⇒ 所有存量 payload 多一键 ⇒ 全部 409。
        """
        code = _func_code(_read(SERVICE_PY), "_normalize_entry")
        # 必须存在「条件性塞键」的形态
        assert re.search(r"if\s+reason_code\b", code), (
            "`reason_code` 未做条件写入 —— 若无条件写入 `None`，"
            "存量 canonical payload 会多出一个键 ⇒ hash 全变 ⇒ "
            "在途 preview 凭证与既有 canonical trim 测试全部 409"
        )
        # 且不得出现无条件把该键放进返回 dict 字面量的形态
        assert not re.search(r'"reason_code":\s*reason_code\s*(?:or\s+None)?\s*,?\s*\n\s*\}', code), (
            "在返回 dict 字面量里无条件写 `reason_code` —— 破坏 additive 零回归"
        )

    def test_real_normalize_entry_payload_unchanged_without_reason_code(self):
        """真跑归一函数：不传理由码时键集恰为扩展前的五个键。"""
        try:
            from app.services.procedure_trim_service import ProcedureTrimService
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"无法导入 ProcedureTrimService：{exc}")

        entry = {
            "kind": "scope",
            "cycle": "D",
            "wp_index_code": "D2-1",
            "target_status": "not_applicable",
            "skip_reason": "本期无该类交易或余额",
        }
        out = ProcedureTrimService._normalize_entry(dict(entry))
        assert set(out) == {
            "kind",
            "key",
            "cycle",
            "wp_index_code",
            "target_status",
            "skip_reason",
        }, (
            f"不传 `reason_code` 时归一结果键集为 {sorted(out)}，"
            "与扩展前不同 ⇒ payload hash 变化 ⇒ 存量 preview 凭证全部失效"
        )

    def test_real_normalize_entry_carries_reason_code_when_given(self):
        from app.services.procedure_trim_service import ProcedureTrimService

        entry = {
            "kind": "scope",
            "cycle": "D",
            "wp_index_code": "D2-1",
            "target_status": "not_applicable",
            "skip_reason": "本期余额低于实际执行重要性",
            "reason_code": "below_materiality",
        }
        out = ProcedureTrimService._normalize_entry(dict(entry))
        assert out.get("reason_code") == "below_materiality"

    def test_real_normalize_entry_rejects_invalid_reason_code(self):
        from fastapi import HTTPException

        from app.services.procedure_trim_service import ProcedureTrimService

        entry = {
            "kind": "scope",
            "cycle": "D",
            "wp_index_code": "D2-1",
            "target_status": "not_applicable",
            "reason_code": "totally_made_up",
        }
        with pytest.raises(HTTPException) as ei:
            ProcedureTrimService._normalize_entry(dict(entry))
        assert ei.value.status_code == 422

    def test_execute_target_drops_reason_code(self):
        """恢复 execute 时理由码应与 `skip_reason` 一同清空（语义一致）。"""
        from app.services.procedure_trim_service import ProcedureTrimService

        entry = {
            "kind": "scope",
            "cycle": "D",
            "wp_index_code": "D2-1",
            "target_status": "execute",
            "skip_reason": "不应保留",
            "reason_code": "no_data",
        }
        out = ProcedureTrimService._normalize_entry(dict(entry))
        assert out.get("skip_reason") is None
        assert "reason_code" not in out, (
            "恢复 execute 时仍带理由码 —— 会让已恢复的程序在复核视图里"
            "仍按「因某原因被裁」统计"
        )


class TestLegacyFreeTextStillReadable:
    """R8.4：存量仅有 `skip_reason` 自由文本的记录保持可读。"""

    def test_frontend_mirror_echoes_unregistered_code_verbatim(self):
        """未登记理由码必须原样回显，不得显示空白或「未知理由」。

        后端先行新增取值、前端镜像尚未跟进时会走到这条路径。回显原值让审计师
        至少看得见发生了什么；显示「未知理由」会让人以为数据坏了。
        """
        src = _code_only_ts(_read(FE_MIRROR))
        assert re.search(r"export\s+function\s+reasonCodeLabel", src), (
            "前端镜像缺 `reasonCodeLabel` —— 无从把理由码翻成中文标签"
        )
        body = _ts_function_body(src, "reasonCodeLabel")
        assert "return text" in body, (
            "`reasonCodeLabel` 未原样回显未登记理由码 —— 后端先行新增取值时会显示空白"
        )
        assert not re.search(r"未知理由|unknown", body), (
            "`reasonCodeLabel` 出现「未知理由」兜底 —— R8.4 明确禁止（会掩盖真实取值）"
        )

    def test_frontend_mirror_composes_legacy_free_text(self):
        """存量「只有 `skip_reason` 自由文本、无理由码」必须原文可读。

        🔴 承载该语义的是 `formatTrimReason` 而非 `reasonCodeLabel` —— 后者只做
        「码 → 标签」单向翻译，不接触自由文本。判据落错函数会在正确实现上打红。
        """
        src = _code_only_ts(_read(FE_MIRROR))
        assert re.search(r"export\s+function\s+formatTrimReason", src), (
            "前端镜像缺 `formatTrimReason` —— 存量仅有自由文本的裁剪记录"
            "会显示为空或「未知理由」"
        )
        body = _ts_function_body(src, "formatTrimReason")
        assert re.search(r"skipReason", body), (
            "`formatTrimReason` 未消费 `skipReason` —— 存量自由文本无处显示"
        )
        # 无理由码时必须仍返回自由文本（而不是 null / 空串）
        assert re.search(r"if\s*\(\s*!\s*label\s*\)|label\s*===?\s*null|!label", body), (
            "`formatTrimReason` 未处理「无理由码」分支 —— 存量记录会丢掉理由原文"
        )

    def test_frontend_commonapi_declares_optional_reason_code(self):
        src = _code_only_ts(_read(FE_COMMON_API))
        m = re.search(r"interface\s+CanonicalTrimScopeEntry\s*\{(.*?)\n\}", src, re.S)
        assert m, "`commonApi.ts` 未声明 `CanonicalTrimScopeEntry`"
        body = m.group(1)
        assert re.search(r"reason_code\?\s*:", body), (
            "`reason_code` 在前端类型里必须是可选字段（additive）"
        )
