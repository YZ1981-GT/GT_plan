#!/usr/bin/env python
"""守卫判据形态普查 —— 识别「全局等值型」断言并分级。

spec: .kiro/specs/guard-assertion-attribution-refactor/ Task 1
Requirements: 6.1, 6.2, 6.3, 6.4  |  Property 14, 15

## 要解决的问题

平台有 20+ 处全量扫描型守卫用「某集合总数必须等于硬编码基线」做判据。多 spec 并发下
这类断言必然假红：改动方动了真源、同步了自己视野内的副本，别的 spec 拥有的守卫副本
看不见也跑不到。

实证（2026-08-15）：`disclosureSharedTableRowScope.spec.ts` 7 条断言全 RED，因为
2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 改了真源
`note_shared_table_segments.json`（23/6/29 → 24/8/32），改动方同步了生成器
`EXPECTED_COUNTS` 与后端 `test_note_shared_table_segments.py`（都在后端视野内），
**前端守卫属于另两个 spec，改动方 CI 视野里没有它** ⇒ 3 个 blocking job 干净
checkout 必挂，且一条规模数字打死同 `it` 内 6 条仍然成立的归因断言。

## 判据形态分级

| 级 | 形态 | 并发安全 | 处置 |
|---|---|---|---|
| A | 违规清单为空 `toEqual([])` | 是 | 目标态 |
| B | 地板/天花板 `toBeGreaterThanOrEqual` / `toBeLessThanOrEqual` | 是 | 可用 |
| C | 包含式重点项 `toContain` / `x in inventory` | 是 | 可用 |
| D | 全局等值 `expect(<集合>.length).toBe(<数字>)` | **否** | 禁用 |
| E | 跨文件抠数字再等值（读别的守卫源码 + 数字等值） | **否** | 禁用 |

## 为什么 verdict 不能全自动

「该断言的真源是否被别的 active spec 触及」需要领域判断。脚本做的是
**启发式初判 + 强制人工复核标记**：作用域看起来是跨循环全量扫描的判 `must_fix`，
限定单循环的判 `keep`，两者都带 `needs_human_review` 供逐条确认。
诚实地把不确定性暴露出来，而不是假装能自动定案。

用法::

    python backend/scripts/check/audit_guard_assertion_grades.py            # 人读摘要
    python backend/scripts/check/audit_guard_assertion_grades.py --write    # 落盘 JSON
    python backend/scripts/check/audit_guard_assertion_grades.py --check    # 与落盘比对（CI 用）
    python backend/scripts/check/audit_guard_assertion_grades.py --self-test  # 反向自检
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

def _find_repo_root() -> Path:
    """双哨兵向上查找仓库根 —— 禁写死回退级数（平台铁律）。

    🔴 首版写 `parents[2]` 落在 `backend/` 上，`iter_targets()` 扫到 0 个文件而
    脚本仍以 0 退出（「命中 0 条」看起来像「平台很干净」）—— 正是本 spec 要治的
    「判据空转」形态。故此处加哨兵 + 下方 `build_payload` 加零产出自检。
    """
    here = Path(__file__).resolve()
    for cand in [here.parent, *here.parents]:
        if (cand / "audit-platform" / "frontend" / "package.json").exists() and (
            cand / "backend" / "tests"
        ).is_dir():
            return cand
    raise RuntimeError(f"找不到仓库根（从 {here} 向上找 audit-platform/frontend/package.json + backend/tests）")


REPO_ROOT = _find_repo_root()
FRONTEND_TESTS = REPO_ROOT / "audit-platform" / "frontend" / "src"
BACKEND_TESTS = REPO_ROOT / "backend" / "tests"
OUT_PATH = REPO_ROOT / "backend" / "data" / "guard_assertion_grades.json"

# ─── 形态识别 ────────────────────────────────────────────────────────────────

#: TS 侧不用正则跨 `expect(...)` 匹配 —— 一律**括号配对**扫描（见 `iter_ts_asserts`）。
#:
#: 🔴 首版用 `expect\(...(?P<msg>.*?)\)\s*\.\s*toBe\(\d+\)` + `re.S`，结果命中 **7063 条**
#:    （预期 20+）：DOTALL 下 `.*?` 会把「某个 expect 的开头」与「几十行后另一个 expect
#:    的 `.toBe(数字)`」拼成一条。这正是本 spec design 的 Property 9 明令禁止的
#:    「固定字符窗口 / 跨界正则」形态 —— 不能在治理脚本里自己犯。

#: 规模型 target：`x.length` / `x.size` / `Object.keys(x).length`
TS_SIZE_TARGET = re.compile(r"(?:\.length|\.size)\s*$")
#: matcher 参数是纯数字
NUM_ARG = re.compile(r"^\s*\d+\s*$")
#: matcher 参数是含裸数字的对象字面量（`{ listed: 23, soe: 6 }`）
OBJ_NUM_ARG = re.compile(r"^\s*\{[^{}]*\d+[^{}]*\}\s*$")

#: 形态 D（PY）—— `assert len(x) == 24`（PY 断言不跨行，正则安全；显式不加 re.S）
PY_LEN_EQ = re.compile(r"assert\s+len\(\s*(?P<target>[^()\n]+?)\s*\)\s*==\s*(?P<value>\d+)\b")
#: 形态 D（PY）—— `assert payload["counts"] == {"listed": 24}`
PY_OBJ_EQ = re.compile(
    r"assert\s+(?P<target>[\w\[\]\"'_.]+)\s*==\s*(?P<obj>\{[^{}\n]*?\d+[^{}\n]*?\})"
)

#: 形态 B/C 的标志（用于 self-test 的负样本，确认不误判）
SAFE_MARKERS = (
    "toBeGreaterThanOrEqual", "toBeLessThanOrEqual", "toBeGreaterThan", "toBeLessThan",
    "toContain", "toEqual([])", "toHaveLength(0)",
)

#: 形态 E —— 读别的守卫源码（这些变量名意味着「把另一个 spec 文件读成字符串」）
FOREIGN_SOURCE_HINTS = ("COVERAGE_RAW", "GUARD_RAW", "SPEC_RAW", "OTHER_SRC", "_RAW =")

#: 🔴 **全量扫描型守卫**的信号 —— 只有这类文件里的规模等值才构成形态 D。
#:
#: 首版漏了这层过滤，命中 **6778 条**（预期 20+）：把「纯函数单测断言受控 fixture 的
#: 规模」也算了进去（`expect(plan.writes.length).toBe(2)` —— 造 2 条输入断言 2 条写入，
#: 完全合法，任何 spec 改真源都不会影响它）。
#:
#: 形态 D 的危害**只发生在 target 来自全量扫描或外部真源**时：那时数字是「当下全库
#: 实况的快照」，别人改真源即失效。判据因此收窄为两个必要条件：
#:   ① 文件本身做全量扫描 / 读外部真源
#:   ② target 的根标识符是**模块级**的（不是 it 内部构造的 fixture）
SCAN_SIGNALS_TS = (
    "readFileSync", "readdirSync", "statSync", "import.meta.glob", "globSync",
    "existsSync", "walk(", "walkVue(",
)
SCAN_SIGNALS_PY = (
    ".rglob(", ".glob(", ".iterdir(", ".read_text(", "json.loads(", "json.load(",
    "openpyxl", "load_workbook",
)

#: 模块级常量声明（TS）—— 顶格或一级缩进内的 `const X = ` / `let X = `
MODULE_CONST_TS = re.compile(r"^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*[:=]", re.M)
#: 模块级赋值（PY）—— 顶格 `X = ` / `X: T = `
MODULE_CONST_PY = re.compile(r"^([A-Za-z_][\w]*)\s*(?::[^=\n]+)?=", re.M)

#: 跨循环全量扫描的信号（集合名 / 变量名）⇒ 初判 must_fix
GLOBAL_SCOPE_HINTS = (
    "manifest", "MANIFEST", "ALL_", "TABS", "DISCLOSURE_FILES", "MISSING_",
    "ORPHAN", "SCANNABLE", "payload", "X3_", "PRE_X3_", "MANUAL_OVERRIDES",
    "_TARGETS", "_TYPOS", "codes", "allowed", "SheetNames", "leaky", "narrowed",
    "counts", "tables",
)

#: 单循环作用域的信号（文件名前缀）⇒ 初判 keep
PER_CYCLE_FILE = re.compile(
    r"(?:^|[\\/])(?:[a-z]\d{1,2}|[a-z]Cycle|[a-z]\d{1,2}[A-Z]\w*)[\w.]*\.(?:spec\.ts|py)$"
)


@dataclass
class Item:
    file: str
    line: int
    assertion: str
    current_value: str
    grade: str
    verdict: str
    reason: str
    #: 🔴 分层 —— 语法判据无法区分「真源规模快照」与「合法的局部规模断言」，
    #: 故不假装能全自动分级，改为按可操作性分层：
    #:   P0 = spec 已逐条确认的文件（KNOWN_ANCHORS）—— 确定要改
    #:   P1 = target 是模块级 UPPER_SNAKE 常量（登记表 / 清单，最易被跨 spec 改）
    #:   P2 = 其余（待分批甄别的背景量）
    priority: str = "P2"
    needs_human_review: bool = True
    scope_hints: list[str] = field(default_factory=list)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _match_paren(text: str, open_idx: int) -> int:
    """从 `text[open_idx] == '('` 起做括号配对，返回闭合 `)` 的下标；失败返回 -1。

    跳过字符串字面量与模板串（失败消息里常含 `)`），不跳注释（测试代码里注释含
    `)` 不影响配对且跳注释反而容易误伤模板串里的 `//`）。
    """
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    break
                # 模板串里的 `${...}` 可能含引号与括号 —— 简化处理：只认闭合引号
                i += 1
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def iter_ts_asserts(text: str):
    """产出 (pos, target, matcher, arg) —— 括号配对定位，绝不跨 expect 边界。"""
    for m in re.finditer(r"\bexpect\s*\(", text):
        open_idx = text.index("(", m.start())
        close_idx = _match_paren(text, open_idx)
        if close_idx < 0:
            continue
        inner = text[open_idx + 1 : close_idx]
        # target = 第一个顶层逗号之前的部分（第二参是失败消息）
        depth = 0
        cut = len(inner)
        j = 0
        while j < len(inner):
            c = inner[j]
            if c in "'\"`":
                q = c
                j += 1
                while j < len(inner):
                    if inner[j] == "\\":
                        j += 2
                        continue
                    if inner[j] == q:
                        break
                    j += 1
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == "," and depth == 0:
                cut = j
                break
            j += 1
        target = inner[:cut].strip()

        # 闭合括号后必须紧跟 `.matcher(arg)`
        tail = text[close_idx + 1 :]
        mm = re.match(r"\s*\.\s*(toBe|toEqual|toStrictEqual|toHaveLength)\s*\(", tail)
        if not mm:
            continue
        arg_open = close_idx + 1 + tail.index("(", mm.end() - 1)
        arg_close = _match_paren(text, arg_open)
        if arg_close < 0:
            continue
        arg = text[arg_open + 1 : arg_close]
        yield (m.start(), target, mm.group(1), arg)


def _same_it_block(text: str, pos: int) -> str:
    """取 pos 所在的 `it(...)` / `def test_` 块体（粗略：向前找最近的块首，向后 2000 字符）。

    用于形态 E 判定：同一 `it` 内是否既读别的守卫源码又做数字等值。
    """
    head = max(
        text.rfind("it(", 0, pos),
        text.rfind("def test_", 0, pos),
        text.rfind("it.each(", 0, pos),
    )
    start = head if head >= 0 else max(0, pos - 2000)
    return text[start : pos + 400]


def is_full_scan_guard(text: str, is_py: bool) -> bool:
    """该文件是否是「全量扫描 / 读外部真源」型守卫（形态 D 的必要条件 ①）。"""
    signals = SCAN_SIGNALS_PY if is_py else SCAN_SIGNALS_TS
    return any(s in text for s in signals)


def module_level_names(text: str, is_py: bool) -> set[str]:
    """文件的模块级标识符集合（形态 D 的必要条件 ②）。

    只取顶格声明：`it` / `describe` / `def test_` 内部构造的 fixture 不算
    —— 那类断言是「受控输入 → 受控输出」，改真源不影响它。
    """
    pattern = MODULE_CONST_PY if is_py else MODULE_CONST_TS
    return {m.group(1) for m in pattern.finditer(text)}


def _root_ident(target: str) -> str:
    """取 target 表达式的根标识符：`Object.keys(X).length` → `X`；`a.b.length` → `a`。"""
    inner = re.search(r"\(([^()]*)\)", target)
    base = inner.group(1) if inner and target.lstrip().startswith("Object.") else target
    m = re.search(r"[A-Za-z_$][\w$]*", base)
    return m.group(0) if m else ""


#: 「该变量的值来自全量扫描 / 真源遍历」的信号（出现在赋值右侧）
DERIVED_FROM_SCAN = (
    "iter_", "list(", "readFileSync", "readdirSync", "JSON.parse", "json.loads",
    "walk(", "walkVue(", "glob", "rglob", "flatMap", "map(", "filter(",
    "Object.keys", "Object.values", "new Set", "[...", "read_text",
    "load_workbook", "iterdir",
)


def is_literal_fixture(text: str, ident: str, is_py: bool) -> bool:
    """`ident` 是否由**纯字面量**构造（= 测试自造的受控输入，不是真源规模）。

    这是条件②的最终形态（排除法）。前两版都漏判：
      - v1「必须是模块级」→ 漏掉 `listed = list(iter_shared_tables(...))`（函数内局部）
      - v2「赋值右侧含扫描信号」→ 漏掉 **pytest fixture 参数**（`def test_x(expected)`
        根本没有赋值语句）与私有 helper 调用（`codes = _codes()`）

    形态 D 的本质是「数字锚定了从真源算出的规模」。反过来说，只有
    `const rows = [{...},{...}]` 这类**字面量**才是测试自造的输入，其余
    （函数调用 / fixture 注入 / 模块级常量）都可能承载真源规模 ⇒ 一律纳入待复核。
    """
    if not ident:
        return False
    if is_py:
        pat = re.compile(rf"^\s*{re.escape(ident)}\s*(?::[^=\n]+)?=\s*(?P<rhs>.+)$", re.M)
    else:
        pat = re.compile(
            rf"(?:const|let|var)\s+{re.escape(ident)}\s*(?::[^=\n]+)?=\s*(?P<rhs>.+)$", re.M
        )
    found = False
    for m in pat.finditer(text):
        found = True
        rhs = m.group("rhs").strip()
        # 右侧以字面量开头且不含函数调用 ⇒ 自造 fixture
        if not (rhs[:1] in "[{(" and "(" not in rhs[1:]):
            return False
    # 找不到赋值（fixture 参数 / import 进来的）→ 不算字面量 fixture
    return found


def derives_from_scan(text: str, ident: str, is_py: bool) -> bool:
    """`ident` 的赋值右侧是否来自全量扫描 / 真源遍历。

    🔴 补这一层的原因：条件②首版只认「模块级标识符」，把
    `listed = list(iter_shared_tables(VARIANT_LISTED))` 这类**函数内**的局部变量
    过滤掉了 —— 而 `assert len(listed) == 24` 恰是本 spec 的立项证据之一
    （后端那份 24/8 基线）。

    这个漏洞是靠 spec requirements 里的**已知清单当验收锚点**发现的：19 个已知点
    有 4 个 MISS。没有那份清单，87 条会被当成「全部」。
    """
    if not ident:
        return False
    if is_py:
        pat = re.compile(rf"^\s*{re.escape(ident)}\s*(?::[^=\n]+)?=\s*(?P<rhs>.+)$", re.M)
    else:
        pat = re.compile(
            rf"(?:const|let|var)\s+{re.escape(ident)}\s*(?::[^=\n]+)?=\s*(?P<rhs>.+)$", re.M
        )
    for m in pat.finditer(text):
        rhs = m.group("rhs")
        if any(s in rhs for s in DERIVED_FROM_SCAN):
            return True
    return False


def is_scale_assertion(target: str, matcher: str, arg: str) -> bool:
    """是否为「规模型等值」断言（形态 D 的核心特征）。

    三种命中：
      1. `expect(x.length).toBe(3)` / `.size).toBe(3)`      —— target 是规模表达式 + 数字参
      2. `expect(x).toHaveLength(3)`                        —— 数字参且 **非 0**（0 = 形态 A）
      3. `expect(x).toEqual({ listed: 23 })`                —— 对象字面量含裸数字

    刻意**不**命中：`toBeGreaterThanOrEqual` / `toBeLessThanOrEqual`（形态 B）、
    `toContain`（形态 C）、`toEqual([])` / `toHaveLength(0)`（形态 A）。
    """
    arg_s = arg.strip()
    if matcher == "toHaveLength":
        return bool(NUM_ARG.match(arg_s)) and arg_s.strip() != "0"
    if matcher in ("toBe", "toEqual", "toStrictEqual"):
        if NUM_ARG.match(arg_s):
            # 纯数字：只有 target 是规模表达式才算（`expect(row.count).toBe(3)` 是业务值不算）
            return bool(TS_SIZE_TARGET.search(target))
        if OBJ_NUM_ARG.match(arg_s):
            return True
    return False


def _classify_scope(target: str, rel: str, snippet: str) -> tuple[str, str, list[str]]:
    """初判 verdict。返回 (verdict, reason, hits)。"""
    hits = [h for h in GLOBAL_SCOPE_HINTS if h in target or h in snippet[:200]]
    if hits:
        return (
            "must_fix",
            f"作用域信号 {hits} 指向跨循环全量扫描，真源可能被其它 active spec 触及",
            hits,
        )
    if PER_CYCLE_FILE.search(rel):
        return (
            "keep",
            "文件名表明作用域限于单一循环，硬计数的归因明确 —— 仍需人工确认真源无跨 spec 触及",
            [],
        )
    return ("must_fix", "无法判定作用域，保守判 must_fix 待人工复核", [])


def scan_file(path: Path, rel: str) -> tuple[list[Item], bool]:
    """返回 (items, parsed_ok)。解析异常不吞 —— 记 parsed_ok=False 影响退出码。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - 如实上报，不静默跳过
        print(f"[ERROR] 读取失败 {rel}: {exc}", file=sys.stderr)
        return ([], False)

    items: list[Item] = []
    hits_raw: list[tuple[int, str, str, str]] = []
    is_py = path.suffix == ".py"

    # 必要条件 ①：该文件是全量扫描 / 读外部真源型守卫
    if not is_full_scan_guard(text, is_py):
        return ([], True)
    mod_names = module_level_names(text, is_py)

    if is_py:
        for pattern, kind in ((PY_LEN_EQ, "len"), (PY_OBJ_EQ, "obj")):
            for m in pattern.finditer(text):
                val = m.group("value") if kind == "len" else m.group("obj")
                hits_raw.append((m.start(), m.group("target").strip(), "==", val))
    else:
        for pos, target, matcher, arg in iter_ts_asserts(text):
            if not is_scale_assertion(target, matcher, arg):
                continue
            hits_raw.append((pos, target, matcher, arg))

    # 必要条件 ②（按是否模块级分流）：
    #   模块级         → 纳入（登记表 / 清单常量，字面量也算 —— 它承载全库实况快照）
    #   函数内 + 字面量 → 排除（测试自造的受控输入）
    #   函数内 + 其它   → 纳入（函数调用返回值 / pytest fixture 参数，可能承载真源规模）
    #
    # 🔴 这是条件②的第 4 版。前三版各漏一类：
    #   v1「必须模块级」        → 漏 `listed = list(iter_shared_tables(...))`（函数内局部）
    #   v2「右侧含扫描信号」    → 漏 pytest fixture 参数与私有 helper 调用
    #   v3「排除全部字面量」    → 漏 `MISSING_SYNC_PATH` / `ORPHAN_BASELINE`
    #                             （**模块级登记表本身就是字面量数组**，却是形态 D 的典型）
    # 每一版都是靠 KNOWN_ANCHORS 的 MISS 报警发现的。
    def _keep(target: str) -> bool:
        ident = _root_ident(target)
        if not ident:
            return False
        if ident in mod_names:
            return True
        return not is_literal_fixture(text, ident, is_py)

    hits_raw = [h for h in hits_raw if _keep(h[1])]

    seen: set[int] = set()
    for pos, target, matcher, arg in hits_raw:
        line = _line_of(text, pos)
        if line in seen:
            continue
        seen.add(line)
        snippet = _same_it_block(text, pos)

        # 形态 E：同块内读了别的守卫源码
        grade = "E" if any(h in snippet for h in FOREIGN_SOURCE_HINTS) else "D"
        verdict, reason, scope_hits = _classify_scope(target, rel, snippet)
        if grade == "E":
            verdict = "must_fix"
            reason = "形态 E：从别的守卫源码抠数字再等值 —— 数字被两个 spec 双向锁死"

        assertion = re.sub(r"\s+", " ", f"expect({target}).{matcher}({arg})").strip()
        ident = _root_ident(target)
        if any(a in rel for a in KNOWN_ANCHORS):
            priority = "P0"
        elif ident in mod_names and re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", ident):
            priority = "P1"
        else:
            priority = "P2"
        items.append(
            Item(
                file=rel,
                line=line,
                assertion=assertion[:200],
                current_value=re.sub(r"\s+", " ", str(arg))[:80],
                grade=grade,
                verdict=verdict,
                reason=reason,
                priority=priority,
                scope_hints=scope_hits,
            )
        )
    return (items, True)


def iter_targets() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for p in sorted(FRONTEND_TESTS.rglob("*.spec.ts")):
        if "__tests__" not in p.parts:
            continue
        out.append((p, p.relative_to(REPO_ROOT).as_posix()))
    for p in sorted(FRONTEND_TESTS.rglob("*.test.ts")):
        if "__tests__" not in p.parts:
            continue
        out.append((p, p.relative_to(REPO_ROOT).as_posix()))
    for p in sorted(BACKEND_TESTS.rglob("test_*.py")):
        out.append((p, p.relative_to(REPO_ROOT).as_posix()))
    return out


def build_payload() -> tuple[dict, bool]:
    items: list[Item] = []
    ok = True
    files = iter_targets()
    # 🔴 零产出自检：扫不到文件 = 路径漂移，必须报错而不是安静地说「命中 0 条」
    if len(files) < 200:
        print(
            f"[ERROR] 只扫到 {len(files)} 个测试文件（预期 >200）—— 路径可能漂移：\n"
            f"        FRONTEND_TESTS = {FRONTEND_TESTS}\n"
            f"        BACKEND_TESTS  = {BACKEND_TESTS}",
            file=sys.stderr,
        )
        ok = False
    for path, rel in files:
        got, parsed = scan_file(path, rel)
        items.extend(got)
        ok = ok and parsed

    items.sort(key=lambda i: (i.priority, i.file, i.line))
    by_grade: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for it in items:
        by_grade[it.grade] = by_grade.get(it.grade, 0) + 1
        by_verdict[it.verdict] = by_verdict.get(it.verdict, 0) + 1
        by_priority[it.priority] = by_priority.get(it.priority, 0) + 1

    payload = {
        "scanned_files": len(files),
        "totals": {
            "items": len(items),
            "by_grade": dict(sorted(by_grade.items())),
            "by_verdict": dict(sorted(by_verdict.items())),
            "by_priority": dict(sorted(by_priority.items())),
        },
        "items": [asdict(i) for i in items],
    }
    return payload, ok


def dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ─── 反向自检（Property 14 的判据本身不能空转）───────────────────────────────

SELF_TEST_CASES: list[tuple[str, str, bool]] = [
    # (说明, 代码片段, 是否应被识别为 D/E)
    ("形态 D · length 等值", "expect(ALL_TABLES.length).toBe(16)", True),
    ("形态 D · 带失败消息", "expect(narrowed.length, `变了：${x.join(' / ')}`).toBe(15)", True),
    ("形态 D · toHaveLength", "expect(X3_TARGET_CYCLES).toHaveLength(16)", True),
    ("形态 D · 对象等值", "expect(manifest.counts).toEqual({ listed: 23, soe: 6 })", True),
    ("形态 B · 地板", "expect(TABS.length).toBeGreaterThan(140)", False),
    ("形态 B · 天花板", "expect(Object.keys(X).length).toBeLessThanOrEqual(2)", False),
    ("形态 A · 违规清单为空", "expect(offenders).toEqual([])", False),
    ("形态 A · 空数组长度", "expect(bad).toHaveLength(0)", False),
    ("形态 C · 包含式", "expect(SCANNABLE).toContain('外币货币性项目')", False),
]

PY_SELF_TEST_CASES: list[tuple[str, str, bool]] = [
    ("形态 D · py len", "assert len(listed) == 24", True),
    ("形态 D · py 对象", 'assert payload["counts"] == {"listed": 24, "soe": 8}', True),
    ("形态 C · py 包含", 'assert ("八、92", "外币货币性项目") in soe', False),
    ("形态 B · py 下限", "assert len(codes) >= MIN_SHARED_SEGMENTS", False),
]


def self_test() -> int:
    failures: list[str] = []

    def hit_ts(code: str) -> bool:
        return any(
            is_scale_assertion(target, matcher, arg)
            for _pos, target, matcher, arg in iter_ts_asserts(code)
        )

    def hit_py(code: str) -> bool:
        return bool(PY_LEN_EQ.search(code) or PY_OBJ_EQ.search(code))

    for label, code, should in SELF_TEST_CASES:
        got = hit_ts(code)
        if got != should:
            failures.append(f"[TS] {label}: 期望 {should} 实得 {got} —— {code}")

    for label, code, should in PY_SELF_TEST_CASES:
        got = hit_py(code)
        if got != should:
            failures.append(f"[PY] {label}: 期望 {should} 实得 {got} —— {code}")

    # 🔴 跨界自检：两个 expect 之间不得互相污染（首版 re.S 版在此必败，实测把
    #    「7063 条」灌进结果）。第一个 expect 是形态 B，第二个才是形态 D ⇒ 应恰好命中 1 条。
    cross = (
        "expect(TABS.length).toBeGreaterThan(140)\n"
        "  // 中间隔着注释与别的断言\n"
        "  expect(other).toContain('x')\n"
        "  expect(ALL_TABLES.length).toBe(16)\n"
    )
    n_cross = sum(
        1
        for _p, t, m2, a in iter_ts_asserts(cross)
        if is_scale_assertion(t, m2, a)
    )
    if n_cross != 1:
        failures.append(f"[跨界] 期望恰好 1 条命中，实得 {n_cross} —— 正则跨了 expect 边界")

    # 括号配对自检：失败消息里含 `)` 与模板串不得截断
    tricky = "expect(narrowed.length, `受影响段数变了：${narrowed.join(' / ')}（旧 15）`).toBe(15)"
    if not hit_ts(tricky):
        failures.append("[配对] 失败消息含括号/模板串时漏判")

    # 形态 E 判定自检
    e_snippet = "it('x', () => { const m = /toBe\\((\\d+)\\)/.exec(COVERAGE_RAW); expect(Number(m[1])).toBe(6) })"
    if not any(h in e_snippet for h in FOREIGN_SOURCE_HINTS):
        failures.append("[E] FOREIGN_SOURCE_HINTS 未能识别 COVERAGE_RAW 形态")

    if failures:
        print("反向自检失败：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        f"反向自检通过（TS {len(SELF_TEST_CASES)} 例 / PY {len(PY_SELF_TEST_CASES)} 例 "
        f"/ 跨界 1 例 / 配对 1 例 / E 1 例）"
    )
    return 0


#: 🔴 **覆盖锚点** —— spec requirements 里逐条列出的已知形态 D/E 点。
#:
#: 作用是防「判据收窄过头导致漏报」：本脚本的判据迭代过三轮
#:   7063 条（跨行正则误匹配）→ 6778（括号配对后）→ 87（加两层必要条件）
#: 第三轮曾把 4 个已知点过滤掉（`listed = list(iter_shared_tables(...))` 这类
#: 函数内局部变量），**正是靠这份清单发现的**。没有它，87 条会被当成「全部」。
#:
#: 每个 anchor 至少要命中 1 条，否则判据有漏。
KNOWN_ANCHORS: tuple[str, ...] = (
    "disclosureSharedTableRowScope", "disclosureAutoSyncCoverage", "l2l4DisclosureWiring",
    "ieOrphanBaseline", "cycleImportExportRegistry", "blockColumnAmountRender",
    "nCycleNoteSubtableContract", "iCycleDisclosureWiring", "g7NoteSubtableContract",
    "ieWiringIntegrity", "adjustmentIeContract", "e1BankAccountPrefill", "g0SummaryLowerZone",
    "test_note_shared_table_segments", "test_x3_ie_manifest_registration",
    "test_x3_ie_registrar", "test_note_i_cycle_structure", "test_k0_source_template_facts",
    "test_x3_keyfamily_property",
)


def active_spec_file_touch() -> dict[str, list[str]]:
    """建立「文件 basename → 提及它的 active spec 列表」映射（Property 15 / R6.2）。

    判「keep 是否安全」的唯一硬标准是「该断言的真源不被本 spec 之外的其它 active spec
    触及」。这里用各 active spec 的 `tasks.md` / `design.md` 里出现的文件名做近似
    —— spec 文档会点名它要改的文件，这是当前可得的最直接信号。

    近似而非精确，故结果只用于**给人工复核加权**，不自动定案。
    """
    specs_dir = REPO_ROOT / ".kiro" / "specs"
    touch: dict[str, set[str]] = {}
    if not specs_dir.is_dir():
        return {}
    for spec_dir in sorted(specs_dir.iterdir()):
        if not spec_dir.is_dir() or spec_dir.name.startswith("_"):
            continue  # `_archive` 等归档目录不算 active
        if not (spec_dir / "tasks.md").exists():
            continue  # 空壳目录不算 active
        blob = ""
        for name in ("tasks.md", "design.md", "requirements.md"):
            p = spec_dir / name
            if p.exists():
                try:
                    blob += p.read_text(encoding="utf-8")
                except Exception:  # noqa: BLE001
                    continue
        # 抽形如 `xxx.spec.ts` / `test_xxx.py` / `xxx.json` 的文件名
        for m in re.finditer(r"[\w./\\-]+\.(?:spec\.ts|test\.ts|py|json|yaml|vue|ts)\b", blob):
            base = m.group(0).replace("\\", "/").split("/")[-1]
            touch.setdefault(base, set()).add(spec_dir.name)
    return {k: sorted(v) for k, v in touch.items()}


def annotate_spec_touch(payload: dict) -> None:
    """给每条命中标注「哪些 active spec 提及了它所在文件」。"""
    touch = active_spec_file_touch()
    for it in payload["items"]:
        base = it["file"].split("/")[-1]
        specs = touch.get(base, [])
        it["touched_by_active_specs"] = specs
        # keep 判定的加权：被 2+ 个 active spec 提及 ⇒ 不安全，抬到 must_fix
        if it["verdict"] == "keep" and len(specs) >= 2:
            it["verdict"] = "must_fix"
            it["reason"] = (
                f"原判 keep，但该文件被 {len(specs)} 个 active spec 提及"
                f"（{', '.join(specs[:3])}…）⇒ 真源跨 spec，硬计数不安全"
            )
    payload["totals"]["spec_touch_index_size"] = len(touch)
    by_verdict: dict[str, int] = {}
    for it in payload["items"]:
        by_verdict[it["verdict"]] = by_verdict.get(it["verdict"], 0) + 1
    payload["totals"]["by_verdict"] = dict(sorted(by_verdict.items()))


def check_anchors(payload: dict) -> int:
    """核对已知锚点全部命中（Property 14 的漏报防线）。"""
    files = [i["file"] for i in payload["items"]]
    missing = [a for a in KNOWN_ANCHORS if not any(a in f for f in files)]
    print(f"\n=== 覆盖锚点核对（{len(KNOWN_ANCHORS)} 个）===")
    for a in KNOWN_ANCHORS:
        n = sum(1 for f in files if a in f)
        print(f"  {'OK ' if n else 'MISS'} {n:3d}  {a}")
    if missing:
        print(f"\n[ERROR] {len(missing)} 个已知点未命中 —— 判据收窄过头：{missing}", file=sys.stderr)
        return 1
    print(f"\n全部 {len(KNOWN_ANCHORS)} 个已知锚点命中")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-anchors", action="store_true", help="只核对已知锚点覆盖")
    ap.add_argument("--write", action="store_true", help="落盘 JSON")
    ap.add_argument("--check", action="store_true", help="与落盘内容比对（CI 用）")
    ap.add_argument("--self-test", action="store_true", help="只跑反向自检")
    ap.add_argument("--grade", choices=["D", "E"], help="只列该等级")
    ap.add_argument("--verdict", choices=["must_fix", "keep"], help="只列该判定")
    ap.add_argument("--priority", choices=["P0", "P1", "P2"], help="只列该优先级")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    rc = self_test()
    if rc:
        print("判据自身失效，中止普查", file=sys.stderr)
        return rc

    payload, ok = build_payload()
    if not ok:
        print("有文件解析失败（见上方 ERROR）", file=sys.stderr)

    annotate_spec_touch(payload)
    if payload["totals"].get("spec_touch_index_size", 0) < 50:
        print(
            f"[ERROR] active spec 文件索引只有 "
            f"{payload['totals'].get('spec_touch_index_size')} 条 —— 抽取失效，"
            f"keep 判定失去跨 spec 加权",
            file=sys.stderr,
        )
        ok = False

    if check_anchors(payload):
        ok = False
    if args.check_anchors:
        return 0 if ok else 1

    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(dump(payload), encoding="utf-8")
        print(f"已写入 {OUT_PATH.relative_to(REPO_ROOT)}")
    elif args.check:
        if not OUT_PATH.exists():
            print(f"缺少 {OUT_PATH.relative_to(REPO_ROOT)} —— 请先 --write", file=sys.stderr)
            return 1
        if OUT_PATH.read_text(encoding="utf-8") != dump(payload):
            print("普查结果与落盘不一致 —— 请重跑 --write", file=sys.stderr)
            return 1
        print("普查结果与落盘一致")

    t = payload["totals"]
    print(f"\n扫描 {payload['scanned_files']} 个测试文件，命中 {t['items']} 条")
    print(f"  按等级：{t['by_grade']}")
    print(f"  按判定：{t['by_verdict']}")

    print(f"  按优先级：{t.get('by_priority', {})}")

    items = payload["items"]
    if args.grade:
        items = [i for i in items if i["grade"] == args.grade]
    if args.verdict:
        items = [i for i in items if i["verdict"] == args.verdict]
    if args.priority:
        items = [i for i in items if i["priority"] == args.priority]
    if args.grade or args.verdict or args.priority:
        print(f"\n筛选后 {len(items)} 条：")
        for i in items:
            print(f"  {i['grade']} {i['verdict']:9s} {i['file']}:{i['line']}")
            print(f"      {i['assertion'][:110]}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
