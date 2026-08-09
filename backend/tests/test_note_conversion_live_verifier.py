"""Property 37 守卫 —— 真实库验收脚本不得改动真实项目口径。

spec: soe-listed-note-conversion-correctness / Requirements 10.6, 10.7, 10.8
被测对象 = ``backend/scripts/diagnose/verify_note_conversion_live.py``（Task 19 交付物）

**Validates: Requirements 10.6, 10.7, 10.8**

------------------------------------------------------------------------------
为什么这个守卫的判据必须是「赋值/UPDATE 形态」而不是裸标识符
------------------------------------------------------------------------------

被测脚本的 docstring 与注释里**必然**原样写出 ``template_type`` /
``report_scope`` / ``applicable_standard_v2``（要说明「为什么禁止写它们」），
所以裸 ``"template_type" in src`` 会把说明文字数成违规 = 假红。

反过来，只断言标识符不出现也挡不住 ``if False:`` 这类空操作绕过
（平台已记「源码守卫的字符串存在判据挡不住 `if False:`」）。

故判据分三层：

1. ``tokenize`` 剥 ``#`` 注释 + ``ast`` 剥 docstring，**保留**普通字符串字面量
   （字面量里可能藏真实的裸 SQL ``UPDATE projects SET template_type=...``）；
2. 「代码形态」判据在**清空字符串字面量内容**后的代码上跑 —— 否则本守卫与被测
   脚本各自的错误消息样例会自匹配（实测踩过：baseline 因消息里写着 ORM update
   形态而打红）；
3. 「裸 SQL 形态」判据只在字符串字面量里跑，且要求 ``UPDATE projects`` 这种真实
   写入语句，不认单纯提到某个符号名。

------------------------------------------------------------------------------
🔴 判据只有一份实现：从被测脚本 import，本文件不得再写第二份
------------------------------------------------------------------------------

上一轮这里自带了一份 ``find_forbidden_writes``，与脚本内运行期自检各写一份 ⇒
**同一不变式两处实现**，改一处另一处不红（本 spec 全程在治的正是这个缺陷模式，
参见 Task 10「v2 删除而非接线」的裁决依据）。现改为：

* 脚本导出模块级纯函数 ``find_forbidden_writes(src) -> list[str]``；
* 脚本的 ``_self_check_no_forbidden_writes`` 调它（运行期兜底）；
* 本守卫用 ``importlib`` 加载脚本模块并 import 同一个函数（测试期）；
* :class:`TestCriteriaSingleSource` 断言「本文件用的确实是脚本导出的那个」。

本文件只保留**双向替身自检**（4 种真写入必抓 / 3 种仅提及不得打红），不再自带
第二份实现。

.. note::
   动态加载脚本当模块时**必须先 ``sys.modules[name] = mod`` 再 ``exec_module``**，
   否则 ``@dataclass`` 在 ``dataclasses._is_type`` 里拿 ``sys.modules.get(
   cls.__module__).__dict__`` 会得到 ``None`` → ``AttributeError: 'NoneType'
   object has no attribute '__dict__'``（与被测代码毫无关系，极易误判成脚本坏了）。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "diagnose" / "verify_note_conversion_live.py"

_MODULE_NAME = "_verify_note_conversion_live_under_test"


def _load_script_module() -> ModuleType:
    """把被测脚本作为模块加载，用于 import 它导出的判据函数。

    脚本内部有 ``sys.path.insert(BACKEND_ROOT)`` 与 ``from app...`` 顶层 import，
    在仓库根跑 pytest 时可用（``app`` 包在 ``backend/`` 下，脚本自己会补路径）。
    """
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    assert spec is not None and spec.loader is not None, f"无法加载被测脚本: {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    # 🔴 必须先注册再 exec —— 见模块 docstring 的 dataclass 陷阱
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


_script = _load_script_module()

#: 判据单一真源：由被测脚本导出，本文件**不得**再实现一份
find_forbidden_writes = _script.find_forbidden_writes
strip_comments_and_docstrings = _script.strip_comments_and_docstrings
blank_string_literal_contents = _script.blank_string_literal_contents

#: 真实项目口径三字段 —— 同样从脚本取，避免两侧字段集漂移
FORBIDDEN_FIELDS: tuple[str, ...] = _script.FORBIDDEN_WRITE_FIELDS


def _call_args(src: str, func: str) -> list[str]:
    """返回 ``func(...)`` 每次调用的完整实参文本（**圆括号配对**，非固定窗口）。

    平台已多次踩「固定字符窗口 / ``[^)]*`` 截实参」的坑：实参里出现任何 ``)``
    （如 ``"\\n".join(x)``）都会让判据提前结束 ⇒ 断言在残缺文本上求值。这里逐字符
    配对，并跳过字符串字面量内的括号。
    """
    out: list[str] = []
    pat = re.compile(rf"\b{re.escape(func)}\s*\(")
    for m in pat.finditer(src):
        i = m.end()  # 左括号之后
        depth = 1
        quote: str | None = None
        while i < len(src) and depth > 0:
            ch = src[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if depth == 0:
            out.append(src[m.end() : i])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Property 37 正向断言
# ─────────────────────────────────────────────────────────────────────────────


class TestScriptExists:
    """验收脚本必须存在 —— 缺失时后面的断言会全部空转（假绿）。"""

    def test_script_file_exists(self) -> None:
        assert SCRIPT.is_file(), (
            f"验收脚本不存在: {SCRIPT}\n"
            "Property 37 的被测对象缺失 ⇒ 本文件其余断言会全部空转（假绿）。"
        )

    def test_script_is_not_trivially_empty(self) -> None:
        """防「建个空壳让守卫转绿」。"""
        src = SCRIPT.read_text(encoding="utf-8")
        assert len(src) > 4000, f"脚本过短({len(src)}B)，疑为占位空壳"


class TestProperty37NoForbiddenWrites:
    """Property 37 主断言：源码级自禁三字段写入。"""

    def test_no_forbidden_write_forms(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        offenders = find_forbidden_writes(src)
        assert offenders == [], (
            "验收脚本出现对真实项目口径字段的写入形态: "
            + "; ".join(offenders)
            + "\n转换会触发 execute_full_chain(force=True) 全链重算 = 破坏性操作，"
            "验收脚本一律不得写这三个字段（需求 10.6）。"
        )

    def test_scan_surface_is_not_empty(self) -> None:
        """反向自检：原文确实提到三字段（证明剥注释没把扫描面清空 = 判据未空转）。

        🔴 判据必须落在**原文**上而不是常量上 —— 断言 ``fld in FORBIDDEN_FIELDS``
        是同义反复（常量自己当然含这些名字），恒真、抓不到任何东西。
        """
        src = SCRIPT.read_text(encoding="utf-8")
        missing = [f for f in FORBIDDEN_FIELDS if f not in src]
        assert missing == [], (
            f"脚本原文未提到 {missing} ⇒ 它大概率没在说明「为什么禁止写这些字段」，"
            "判据可能已空转（或脚本被换成了空壳）。"
        )

    def test_script_has_no_project_insert_path(self) -> None:
        """需求 10.7：禁用新建测试项目冒充通过。"""
        code = strip_comments_and_docstrings(SCRIPT.read_text(encoding="utf-8"))
        code_no_str = blank_string_literal_contents(code)
        bad = [
            pat
            for pat in (r"\bProject\s*\(", r"\binsert\s*\(\s*Project\s*\)")
            if re.search(pat, code_no_str)
        ]
        assert bad == [], f"脚本出现新建项目形态 {bad}（需求 10.7 禁 fixture/新建项目冒充）"


class TestProperty37HonestSkip:
    """需求 10.7：无合法对象时必须「无法验收」+ 显式 SKIP + 非零退出码。"""

    def test_has_unverifiable_message(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert "无法验收" in src, "缺少「无法验收」诚实输出（需求 10.7）"

    def test_has_explicit_skip_marker(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert "[SKIP]" in src or "SKIP" in src, "缺少显式 SKIP 标记（需求 10.7）"

    def test_no_candidate_exits_nonzero(self) -> None:
        """无合法对象 ⇒ 非零退出码。"""
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(r"sys\.exit\(", src), "脚本未显式设置退出码"

    def test_default_is_dry_run(self) -> None:
        """默认 dry-run：``--apply`` 必须是显式 opt-in 的 store_true。"""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--apply" in src, "缺少 --apply 开关"
        assert "--i-authorize-apply" in src, (
            "缺少用户显式授权开关 --i-authorize-apply（需求 10.8）"
        )
        m = re.search(r'add_argument\(\s*["\']--apply["\'][^)]*\)', src, re.S)
        assert m and "store_true" in m.group(0), "--apply 必须是 store_true（默认 dry-run）"


class TestProperty37StateNamesDerived:
    """铁律 4：多态诊断的态名从枚举 ``.value`` 派生 + 入口自检。"""

    def test_verdicts_derived_from_enum(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(r"tuple\(\s*\w+\.value\s+for\s+\w+\s+in\s+\w+\s*\)", src), (
            "态名未从枚举 .value 派生（大小写不一致会让分布统计静默返 0）"
        )

    def test_has_state_name_selfcheck(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert "_assert_state_names_are_derived" in src, "缺少态名派生入口自检"


class TestProperty37ReusesProductionPaths:
    """需求 10.5：复用生产预览/回滚，不另写一份映射逻辑（防第二真源）。"""

    @pytest.mark.parametrize(
        "symbol",
        ["preview_note_conversion", "_create_snapshot", "rollback_conversion"],
    )
    def test_reuses_production_symbol(self, symbol: str) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert symbol in src, (
            f"脚本未复用生产路径 {symbol} —— Task 15/16 已交付预览与回滚，"
            "另写一份会造第二真源（预览说改 N 个、实际改 M 个，两边单测都绿）"
        )


class TestProperty37OneShotEngine:
    """铁律 1/2：一次性 engine + NullPool + 单次 asyncio.run。"""

    def test_uses_nullpool_one_shot_engine(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert "NullPool" in src and "create_async_engine" in src, (
            "必须自建一次性 engine（NullPool），借用共享 async_session 会双向污染连接池"
        )

    def test_does_not_borrow_shared_session(self) -> None:
        code = strip_comments_and_docstrings(SCRIPT.read_text(encoding="utf-8"))
        code_no_str = blank_string_literal_contents(code)
        assert not re.search(
            r"from\s+app\.core\.database\s+import[^\n]*\basync_session\b", code_no_str
        ), "不得借用 app.core.database.async_session（会污染共享连接池）"

    def test_single_asyncio_run(self) -> None:
        code = strip_comments_and_docstrings(SCRIPT.read_text(encoding="utf-8"))
        code_no_str = blank_string_literal_contents(code)
        n = len(re.findall(r"asyncio\.run\s*\(", code_no_str))
        assert n == 1, f"asyncio.run 出现 {n} 次；两次必炸（连接池绑定首个事件循环）"

    def test_disposes_engine(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(r"await\s+\w*engine\w*\.dispose\(\)", src), (
            "必须在同一 loop 内 await engine.dispose()"
        )


class TestProperty37NoEmoji:
    """铁律 5：GBK 控制台禁 emoji（print 会抛 UnicodeEncodeError）。"""

    def test_no_emoji_in_printed_output(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        # 只查会被 print 的字符串字面量；docstring 里的 🔴 是说明文字不进 stdout
        code = strip_comments_and_docstrings(src)
        emoji = re.findall(r"[\U0001F300-\U0001FAFF\u2705\u274C\u2B55]", code)
        assert emoji == [], f"输出层出现 emoji {set(emoji)}（GBK 控制台会 UnicodeEncodeError）"

    def test_writes_report_with_utf8(self) -> None:
        """报告写盘必须显式 ``encoding='utf-8'``。

        🔴 判据不能用 ``write_text\\([^)]*encoding=`` —— ``[^)]*`` 遇到实参里的
        第一个 ``)`` 就断了。脚本的真实写法是::

            Path(out).write_text("\\n".join(report.lines) + "\\n", encoding="utf-8")

        ``"\\n".join(...)`` 的右括号让 ``[^)]*`` 提前结束 ⇒ 正则匹配不到 encoding
        ⇒ **在正确实现上打红**（上一轮的红 1 正是此因，不是脚本缺陷）。
        正解 = 先定位 ``write_text(`` 再做**括号配对**取完整实参区。
        """
        src = SCRIPT.read_text(encoding="utf-8")
        calls = _call_args(src, "write_text")
        assert calls, "脚本未见 write_text 调用（报告不写盘？）"
        bad = [a for a in calls if not re.search(r"encoding\s*=\s*['\"]utf-8", a)]
        assert bad == [], (
            "以下 write_text 调用未显式 encoding='utf-8'（控制台可能是 GBK，"
            f"中文会被腌成乱码）: {bad}"
        )

    def test_utf8_criteria_rejects_a_stub_without_encoding(self) -> None:
        """反向自检：对不含 encoding 的替身必须打红。

        没有这一条，判据被改弱（或括号配对写错取到空串）时会静默失效。
        """
        stub_bad = 'Path(out).write_text("\\n".join(lines) + "\\n")\n'
        stub_good = 'Path(out).write_text("\\n".join(lines) + "\\n", encoding="utf-8")\n'

        bad_calls = _call_args(stub_bad, "write_text")
        good_calls = _call_args(stub_good, "write_text")
        assert len(bad_calls) == 1 and len(good_calls) == 1, (
            f"括号配对取实参失效: bad={bad_calls} good={good_calls}"
        )
        assert not re.search(r"encoding\s*=\s*['\"]utf-8", bad_calls[0]), (
            "判据放过了「不含 encoding 的 write_text」⇒ 判据已失效"
        )
        assert re.search(r"encoding\s*=\s*['\"]utf-8", good_calls[0]), (
            "判据误伤了「含 encoding 且实参里有嵌套括号」的正确写法"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 双向自检 —— 判据必须既抓真违规、又不误伤说明文字
# ─────────────────────────────────────────────────────────────────────────────


_FIXTURE_HEAD = '"""模块 docstring。"""\n\nimport sqlalchemy as sa\n\n\n'


class TestCriteriaSingleSource:
    """判据必须只有一份实现 —— 本文件用的就是被测脚本导出的那个函数。

    上一轮这里自带一份 ``find_forbidden_writes``，与脚本内运行期自检各写一份 ⇒
    改一处另一处不红（正是本 spec 一直在治的「同一不变式两处实现」缺陷模式，
    见 Task 10 的删除裁决）。这三条断言把「单一真源」钉死。
    """

    def test_criteria_func_is_the_one_exported_by_script(self) -> None:
        """函数对象同一性：不是同名副本，而是脚本模块里那一个。"""
        assert find_forbidden_writes is _script.find_forbidden_writes
        assert find_forbidden_writes.__module__ == _MODULE_NAME, (
            f"判据函数来自 {find_forbidden_writes.__module__}，"
            f"应为被测脚本模块 {_MODULE_NAME} ⇒ 本文件疑似又抄了一份实现"
        )
        assert Path(find_forbidden_writes.__code__.co_filename).resolve() == SCRIPT.resolve()

    def test_this_file_does_not_redefine_criteria(self) -> None:
        """本文件源码不得再出现判据实现的 ``def``（只许 import）。"""
        own = Path(__file__).read_text(encoding="utf-8")
        redefined = [
            name
            for name in (
                "find_forbidden_writes",
                "strip_comments_and_docstrings",
                "blank_string_literal_contents",
                "collect_string_literals",
            )
            if re.search(rf"^def {name}\b", own, re.M)
        ]
        assert redefined == [], (
            f"本守卫又实现了一份判据 {redefined} ⇒ 双真源。"
            "判据只许从被测脚本 import（脚本是运行期与测试期共用的单一真源）。"
        )

    def test_script_self_check_delegates_to_the_same_func(self) -> None:
        """脚本的运行期自检必须调这个纯函数，不得自带第二份。"""
        code = blank_string_literal_contents(
            strip_comments_and_docstrings(SCRIPT.read_text(encoding="utf-8"))
        )
        body_start = code.find("def _self_check_no_forbidden_writes")
        assert body_start >= 0, "脚本缺少运行期自检函数"
        next_def = code.find("\ndef ", body_start + 1)
        body = code[body_start : next_def if next_def > 0 else len(code)]
        assert "find_forbidden_writes(" in body, (
            "脚本的 _self_check_no_forbidden_writes 未调用 find_forbidden_writes ⇒ "
            "它大概率又自带了一份判据实现（双真源）"
        )


class TestCriteriaAreTwoWayValid:
    """替身反向自检：注入真实写入必打红、仅提及不得打红。

    没有这一组，「判据被改弱」会静默失效（平台已记：只做正向断言的守卫
    在变异检验里全部 GREEN）。
    """

    @pytest.mark.parametrize(
        "label,body",
        [
            ("属性赋值", "    proj.template_type = 'listed'\n"),
            ("setattr", "    setattr(proj, 'report_scope', 'consolidated')\n"),
            (
                "ORM update",
                "    sa.update(Project).values(applicable_standard_v2={})\n",
            ),
            (
                "裸 SQL",
                "    conn.execute(\"UPDATE projects SET template_type = 'listed'\")\n",
            ),
        ],
    )
    def test_real_write_is_detected(self, label: str, body: str) -> None:
        fake = _FIXTURE_HEAD + "def mutate(proj, conn):\n" + body
        assert find_forbidden_writes(fake) != [], (
            f"判据放过了真实写入形态「{label}」⇒ 判据已失效"
        )

    @pytest.mark.parametrize(
        "label,body",
        [
            (
                "仅注释提及",
                "    # proj.template_type = 'listed' 是被禁形态，仅说明\n    pass\n",
            ),
            (
                "仅 docstring 提及",
                '    """禁止 proj.template_type = \'x\'；也禁 setattr(proj, \'report_scope\', y)。"""\n    pass\n',
            ),
            (
                "只读回显进报告 dict",
                '    return {"template_type": proj.template_type, "report_scope": proj.report_scope}\n',
            ),
        ],
    )
    def test_mention_only_is_not_flagged(self, label: str, body: str) -> None:
        fake = _FIXTURE_HEAD + "def readonly(proj):\n" + body
        assert find_forbidden_writes(fake) == [], (
            f"判据误伤「{label}」⇒ 会逼人删掉正是下个会话需要的说明文字"
        )
