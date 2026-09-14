#!/usr/bin/env python
"""零回归基线快照 + 共享文件争用核查（spec `x3-adjustment-entry-import-export` 任务 1.8）。

R10.9 的三步法是「**当前态快照** → 施加改动 → 对照」；本脚本负责第一步与第三步，
第二步由 Wave 1~8 的施工任务完成。

三类快照（design §Testing Strategy「零回归判定」）
--------------------------------------------------
① **16 个短前缀「已有的非 X-3 sheet」的导出字节**（R1.6）。两条通路各自快照：
   - `factory_adapter_path`：`IE_ADAPTER_REGISTRY[短前缀].export_fn(...)` —— bulk 批量
     通路今天的真实入口，目标模块是工厂 `_{x}_import_export`。
   - `shape_b_host_path`：`/api/{长前缀}/{wp_id}/{三态}` —— 界面今天的真实入口，
     宿主是专属 router。**这条是 R1.6 / R11.2 真正要求逐字节不变的那条。**
② `test_ie_route_inventory` 的**全部基线数字**（声明值 + 运行期实测值 + 施加后目标态）。
③ `IE_ADAPTER_REGISTRY` 键集与每键解析出的目标模块（任务 6.1 改指前后的对照物）。

探测面（哪些 sheet 会被探）的来源（任务 17.3 修）
------------------------------------------------
- `--snapshot`：从各**显式真源**派生 —— 宿主模块 `IE_SHEETS`（R4.4 白名单）+ `sheet`
  Query 的 default / description + adapter 目标模块内**全部** sheet 声明常量（按父
  wp_code 过滤）。原实现取「模块内**首个** `*_SPECS`」，那是位置性猜测：任务 6.1 把
  adapter 改指专属 router 后首个命中变成 import 进来的 `X3_SHEET_SPECS`（全 16 张
  X-3 码），探测面整体换了一批键。
- `--compare`：**按基线里记下的键重放**（`shape_b_host_path[*].probed[后缀].by_sheet`
  的键即权威作业面）。判据函数与口径不变，换的只是探哪些键。

追加：**两列 CI 快照**（裁决 2 的义务「不让红的规模变大」）—— 两个已红 CI 脚本的
退出码与 drift 条目数。退出码走 `check_x3_deviation_registry.run_ci_probe`（不另写
第二份口径）；条目数按脚本自身的判据复算。

模式
----
| 模式 | 作用 | 写盘 |
|---|---|---|
| `--snapshot` | 采集三类快照 + 两列 CI 快照 | `evidence/baseline_snapshot_x3.json` + `evidence/route_matrix_x3.json` |
| `--compare` | 按**基线记下的键**重放一次并逐项对照（任务 15.3 用） | 不写盘（`--out-compare` 才写） |
| `--contention` | 扫其他 active spec 是否也在碰 design §R11.3 的十项共享文件 | `evidence/shared_file_contention.md` |

退出码：`0` 一切符合预期 / `2` 缺基线或缺可用对象（未收口，非回归）/ `3` 检出回归
/ `1` 脚本自身异常。**判成败查数据不看 exit code**（落盘的 JSON 才是结论）。

只读边界
--------
- 只调 `export-template` / `export-data`；**从不调 `import-data`**（那会写库），
  由 `_ALLOWED_SUFFIXES` + 断言钉死。
- 不碰 `backend/wp_templates/`（R11.1）。
- 除三个 evidence 产物外不写任何文件。
- **禁用 HEAD-swap**（R10.9）：本文件不得有 `git` 加 `stash` / `checkout` / `reset`
  的可执行行。判据见 `assert_no_head_swap()` —— 两条独立判据 + 五条正/负对照，
  刻意把「解释这条禁令的注释与 docstring」判为**不违规**（父 spec 曾两次因
  「只查子串」把说明文字误判成违规）。

Windows 约定：`python` 不用 `python3`；子进程捕获中文一律 `PYTHONIOENCODING=utf-8`；
落盘一律 `Path.write_text(encoding="utf-8")`（PS 的 `>` 会把中文腌成乱码）。
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import difflib
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import sys
import time
import tokenize
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:  # PS 下中文/箱线字符会 GBK 崩
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[3]                       # backend/scripts/diagnose → GT_plan
BACKEND = ROOT / "backend"
SPECS_DIR = ROOT / ".kiro" / "specs"
SELF_SPEC = "x3-adjustment-entry-import-export"
SPEC_DIR = SPECS_DIR / SELF_SPEC
EVIDENCE_DIR = SPEC_DIR / "evidence"
DESIGN_MD = SPEC_DIR / "design.md"

SNAPSHOT_PATH = EVIDENCE_DIR / "baseline_snapshot_x3.json"
MATRIX_PATH = EVIDENCE_DIR / "route_matrix_x3.json"
CONTENTION_PATH = EVIDENCE_DIR / "shared_file_contention.md"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET_KEY", "x3-baseline-snapshot-read-only")

#: 本脚本允许触达的三态后缀 —— `import-data` **不在其中**（它会写库）
_ALLOWED_SUFFIXES: tuple[str, ...] = ("export-template", "export-data")
_IMPORT_SUFFIX = "import-data"

#: 快照①里「这一次没给 `sheet` 实参」的键名（= HTTP 省略 `?sheet=`）。
#: 采集侧与 `--compare` 的基线重放侧共用这一份常量 —— 写死两处就会在改键名那天
#: 让重放静默落空（基线键全变 MISSING = 假红），而两边的字面量各自看起来都对。
_HANDLER_DEFAULT_KEY = "<handler-default>"

#: openpyxl 产出的 xlsx 里唯一随时间变化的 zip 成员（`docProps/core.xml` 内嵌
#: created/modified 时间戳，秒级）。上一轮探针实测：同秒内建两次字节相同、
#: 隔 1.6 秒后仅该成员不同。⇒ 快照①的比对基准必须是「排除易变成员后的逐成员
#: 摘要」，否则 `--compare` 恒 MISMATCH = 假红。
#: `selfcheck_volatile_members()` 每次运行都实测复核这个名单（新增易变成员即打红）。
_VOLATILE_ZIP_MEMBERS: frozenset[str] = frozenset({"docProps/core.xml"})

#: 施加后目标态（design §施加后的目标态：16 前缀 × 3 态 = 48 条路由 / 16 组）
_TARGET_DELTAS: dict[str, Any] = {
    "three_state_routes": 48,
    "groups": 16,
    "full3_prefixes": 16,
    "shape_a_prefixes": 16,
    "shape_b_prefixes": 0,
    "route_kinds": {"export-template": 16, "export-data": 16, "import-data": 16},
    "ie_module_files": 0,
    "factory_api_prefixes": 0,
    "adapter_registry_keys": 0,
}

#: 两个已红 CI 脚本（裁决 2；G2 / G3 的 `reproduce_cmd` 同源）
_CI_JOBS: dict[str, str] = {
    "acnr-ie-catalog-sync": "python backend/scripts/acnr/check_ie_catalog_sync.py",
    "check-acnr-catalog-drift": "python backend/scripts/acnr/check_catalog_drift.py",
}

#: 任务简报给出的 active spec 名单 —— **只作交叉核对提示**，真源是磁盘实扫
#: （`discover_active_specs()`）。两者不一致时如实登记差集，不静默取其一。
_ACTIVE_SPEC_HINT: tuple[str, ...] = (
    "k-cycle-extraction-formula-and-disclosure-closure",
    "l-cycle-extraction-formula-and-disclosure-completion",
    "i-cycle-extraction-formula-and-disclosure-closure",
    "g7-column-alignment-and-extraction-closure",
    "workpaper-import-export-lifecycle-closure",
)

#: 未完成任务的行首锚定正则（memory 铁律：判 spec 进度一律用它，别信旧数）
_TASK_BOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]")
_UNCHECKED_MARKS = frozenset({" ", "-", "~"})

_SHARED_LIST_ANCHOR = "已知需核查清单："
#: 行内 code span。**不得跨行**（`[^`\n]+`）：跨行会把 ``` 围栏当成普通反引号，
#: 令其后所有配对整体错位一格 —— 症状是「解析出上千个 token，却几乎没有文件名」
#: （本脚本首版即因此把补充核查面解析成 0 项）。
_BACKTICKED = re.compile(r"`([^`\n]+)`")
#: 围栏代码块（tasks.md 的 `Task Dependency Graph` 就是一块 ```json）
_CODE_FENCE = re.compile(r"^```.*?^```", re.S | re.M)

_CN_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _short(digest: str) -> str:
    return digest[:16]


def _jsonable(value: Any) -> Any:
    """把 frozenset / set / tuple / Path 归一成可序列化形态（保持确定性排序）。"""
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, Path):
        return value.relative_to(ROOT).as_posix() if value.is_absolute() else str(value)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HEAD-swap 自检（R10.9）—— 两条独立判据 + 正/负对照
# ═══════════════════════════════════════════════════════════════════════════════

_FORBIDDEN_VERBS: tuple[str, ...] = ("stash", "checkout", "reset")
#: `git` 与禁用动词之间允许出现引号/逗号/括号/空白 —— 这样 `["git", "stash"]`
#: 这种把命令拆成多个字符串字面量的写法同样命中（只查 `"git stash"` 会漏掉它）。
_GIT_VERB_RE = re.compile(
    r"\bgit\b[\s'\",\[\]()]*\b(?:" + "|".join(_FORBIDDEN_VERBS) + r")\b"
)
#: 判据 A 用的进程派生标志（AST 层已定位到 Call，这里只用于消息可读性）
_SPAWN_HINTS: tuple[str, ...] = (
    "subprocess", "Popen", "os.system", "check_output", "check_call", "run", "shell",
)


def _flatten_call_strings(node: ast.AST) -> list[str]:
    """取一个 AST 节点内所有字符串字面量（含 f-string 的字面片段）。"""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def head_swap_violations_ast(src: str) -> list[dict[str, Any]]:
    """判据 A（结构判据）：任何**函数调用**的实参里拼出 `git <禁用动词>` 即违规。

    docstring / 注释 / 模块级说明常量都不是 Call 实参 ⇒ 结构上不可能被误判。
    """
    tree = ast.parse(src)
    hits: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        pieces = _flatten_call_strings(node)
        if not pieces:
            continue
        joined = " ".join(pieces)
        if _GIT_VERB_RE.search(joined):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None) or "?"
            hits.append(
                {
                    "criterion": "ast_call_arg",
                    "line": node.lineno,
                    "callee": str(name),
                    "joined_args": joined[:160],
                    "spawn_hint": any(h in str(name) for h in _SPAWN_HINTS),
                }
            )
    return hits


_TRIPLE_QUOTE_PREFIX = re.compile(r"^[rRbBuUfF]{0,3}(\"\"\"|''')")


def mask_docs_and_comments(src: str) -> list[str]:
    """把**注释**与**三引号字符串**（docstring / 多行说明块）整段涂白，其余原样保留。

    🔴 这一步是「说明 ≠ 执行」的判据核心，也是父 spec 两次踩坑的修法：
    - 只查子串 ⇒ 把「解释这条禁令的注释与 docstring」误判成违规；
    - 反过来把**所有**字符串 token 都涂白 ⇒ `["git", "stash"]` 这种把命令拆成
      多个普通字面量的写法会被漏掉，判据变成恒绿（假绿）。
    故只涂白「注释 + 三引号块」，普通单/双引号字面量保留下来接受检查。
    单行三引号（`\"\"\"一句话 docstring\"\"\"`）同样按块涂白 —— 按「跨行才算块」
    判会让单行 docstring 落回代码面（本脚本首版即因此把负对照判成违规）。
    """
    lines = src.splitlines()
    grid = [list(line) for line in lines]

    def blank(row: int, col_from: int, col_to: int | None) -> None:
        if not (1 <= row <= len(grid)):
            return
        chars = grid[row - 1]
        end = len(chars) if col_to is None else min(col_to, len(chars))
        for col in range(max(col_from, 0), end):
            chars[col] = " "

    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                blank(tok.start[0], tok.start[1], None)
            elif tok.type == tokenize.STRING and _TRIPLE_QUOTE_PREFIX.match(tok.string):
                if tok.start[0] == tok.end[0]:
                    blank(tok.start[0], tok.start[1], tok.end[1])
                else:
                    blank(tok.start[0], tok.start[1], None)
                    for row in range(tok.start[0] + 1, tok.end[0]):
                        blank(row, 0, None)
                    blank(tok.end[0], 0, tok.end[1])
    except (tokenize.TokenError, IndentationError):  # pragma: no cover
        pass
    return ["".join(chars) for chars in grid]


def _inside_backticks(line: str, start: int) -> bool:
    """匹配片段是否被反引号包裹（= 说明性引用，不是可执行代码）。"""
    return line.count("`", 0, start) % 2 == 1 and "`" in line[start:]


def head_swap_violations_line(src: str) -> list[dict[str, Any]]:
    """判据 B（行级判据）：涂白注释与三引号块、排除反引号包裹后仍命中即违规。

    比判据 A 覆盖面大（能抓到 `_CMD = ["git", "stash"]` 这种先赋值后调用的写法），
    代价是可能对行内说明字符串误报 ⇒ 故意保留反引号豁免，让「说明」与「执行」可分。
    """
    hits: list[dict[str, Any]] = []
    for lineno, text in enumerate(mask_docs_and_comments(src), 1):
        for m in _GIT_VERB_RE.finditer(text):
            if _inside_backticks(text, m.start()):
                continue
            hits.append(
                {
                    "criterion": "code_line",
                    "line": lineno,
                    "fragment": text.strip()[:160],
                }
            )
    return hits


def selfcheck_head_swap_criteria() -> dict[str, Any]:
    """变异检验：逐条对照**期望命中的判据集合**（不是只看「有没有红」）。

    只断言「flagged / 不 flagged」会漏掉一整类缺陷：判据 A 与判据 B 互相兜底时，
    其中一条坏掉（例如涂白函数把普通字面量也涂了）照样全绿。故每条对照都指名
    期望的检测通道，实测集合与期望集合不等即判**判据有缺陷**并直接抛。

    `POS-assign-then-call` 是隔离判据 B 的那条（AST 侧看不到字符串实参）；
    `NEG-docstring-*` 两条分别覆盖单行与跨行三引号块。
    禁用动词不在本函数源码里内联（用变量拼），否则本脚本自查会命中自己。
    """
    verb_a, verb_b, verb_c = _FORBIDDEN_VERBS
    ast_and_line = {"ast_call_arg", "code_line"}
    cases: list[tuple[str, str, set[str]]] = [
        (
            "POS-subprocess-list",
            f'import subprocess\nsubprocess.run(["git", "{verb_a}"], check=True)\n',
            ast_and_line,
        ),
        (
            "POS-os-system-string",
            f'import os\nos.system("git {verb_b} -- .")\n',
            ast_and_line,
        ),
        (
            # 隔离判据 B：命令先存进常量，AST 侧的 Call 实参里没有字符串字面量
            "POS-assign-then-call",
            f'CMD = ["git", "{verb_c}", "--hard"]\nimport subprocess\nsubprocess.run(CMD)\n',
            {"code_line"},
        ),
        (
            "NEG-comment",
            f"x = 1  # 禁用 git {verb_a}，会破坏并发会话未提交成果\n",
            set(),
        ),
        (
            "NEG-docstring-single-line",
            f'"""本脚本禁用 HEAD-swap：不得 git {verb_b} / git {verb_c}。"""\nx = 1\n',
            set(),
        ),
        (
            "NEG-docstring-multi-line",
            f'"""禁区说明。\n\n不得 git {verb_a}，也不得 git {verb_b}。\n"""\nx = 1\n',
            set(),
        ),
        (
            "NEG-backticked-literal",
            f'MSG = "源码不得出现 `git {verb_a}` 的可执行行"\n',
            set(),
        ),
    ]
    results: dict[str, Any] = {}
    problems: list[str] = []
    for name, snippet, expected in cases:
        hits = head_swap_violations_ast(snippet) + head_swap_violations_line(snippet)
        observed = {h["criterion"] for h in hits}
        ok = observed == expected
        results[name] = {
            "expected_criteria": sorted(expected),
            "observed_criteria": sorted(observed),
            "verdict": "PASS" if ok else "FAIL",
        }
        if not ok:
            problems.append(
                f"{name}: 期望命中 {sorted(expected)} 实测 {sorted(observed)}"
            )
    if problems:
        raise SystemExit(
            "HEAD-swap 判据自检失败（判据本身有缺陷，不是被测源码有问题）:\n  "
            + "\n  ".join(problems)
        )
    return results


def assert_no_head_swap(path: Path) -> dict[str, Any]:
    """对给定源码文件跑两条判据；任一命中即抛。返回自检实录。"""
    controls = selfcheck_head_swap_criteria()
    src = path.read_text(encoding="utf-8")
    hits = head_swap_violations_ast(src) + head_swap_violations_line(src)
    report = {
        "target": path.relative_to(ROOT).as_posix(),
        "forbidden_verbs": list(_FORBIDDEN_VERBS),
        "criteria": ["ast_call_arg", "code_line"],
        "violations": hits,
        "controls": controls,
        "verdict": "CLEAN" if not hits else "HEAD_SWAP_DETECTED",
    }
    if hits:
        raise SystemExit(
            "检出 HEAD-swap 可执行行（R10.9 禁用）:\n"
            + json.dumps(hits, ensure_ascii=False, indent=2)
        )
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 作业面与前缀（一律引既有真源，不在本文件留第二份表）
# ═══════════════════════════════════════════════════════════════════════════════


def load_work_surface() -> dict[str, Any]:
    """16 张作业面 + 长/短前缀映射，全部取自 Wave 0 已交付的真源。"""
    from tests.test_ie_prefix_reachability import (
        _X3_DEDICATED_LONG_PREFIXES,
        _x3_code,
        _x3_short_prefix,
    )
    from tests.test_x3_catalog_registration import _TARGET_SHEETS

    long_prefixes = tuple(_X3_DEDICATED_LONG_PREFIXES)
    short_of_long = {lp: _x3_short_prefix(lp) for lp in long_prefixes}
    code_of_long = {lp: _x3_code(lp) for lp in long_prefixes}

    # 反空转：两份真源必须描述同一批 16 张（任一被改小即打红，而不是静默缩小作业面）
    if sorted(code_of_long.values()) != sorted(_TARGET_SHEETS):
        raise SystemExit(
            "作业面真源不一致 —— `_X3_DEDICATED_LONG_PREFIXES` 派生 "
            f"{sorted(code_of_long.values())} 与 `_TARGET_SHEETS` "
            f"{sorted(_TARGET_SHEETS)} 不等"
        )
    if len(long_prefixes) != 16:
        raise SystemExit(f"作业面应为 16 张，实测 {len(long_prefixes)}")

    return {
        "target_sheets": list(_TARGET_SHEETS),
        "long_prefixes": list(long_prefixes),
        "short_by_long": short_of_long,
        "code_by_long": code_of_long,
        "long_by_short": {v: k for k, v in short_of_long.items()},
        "code_by_short": {short_of_long[lp]: code_of_long[lp] for lp in long_prefixes},
        "parent_wp_codes": sorted({c.split("-", 1)[0] for c in _TARGET_SHEETS}),
    }


def _codes_of_parent(values: Any, parent: str) -> list[str]:
    """从任意字符串容器里取出形如 `{parent}-{序号}` 的 sheet 码，其余一律丢弃。

    父 wp_code 用 `^{parent}-\\d+$` 全匹配 ⇒ `M1` **不会**吃到 `M10-2`（`M1` 后必须紧跟
    `-`），这是 16 张里 m1/m10 同时在册时唯一会咬人的一处。
    """
    rx = re.compile(rf"^{re.escape(parent)}-\d+$")
    if isinstance(values, dict):
        items: list[Any] = list(values)
    elif isinstance(values, (set, frozenset, list, tuple)):
        items = list(values)
    else:
        return []
    return sorted({v for v in items if isinstance(v, str) and rx.match(v)})


def collect_sheet_declarations(module: Any, parent: str) -> dict[str, Any]:
    """扫模块内**全部** sheet 声明常量，按父 wp_code 过滤后取并集（非位置性）。

    🔴 任务 17.3 修的第一条缺陷就在这里。原实现是「取模块内**首个** `*_SPECS` 属性就
    `break`」——一个纯位置性猜测：
    - 基线时 adapter 目标模块是工厂 `_{x}_import_export`，其 `_SPECS` = `{X}-2` + `{X}-3`；
    - 任务 6.1 把 adapter 改指专属 router 后，`dir()` 里首个 `*_SPECS` 变成从共享实现
      import 进来的 `X3_SHEET_SPECS`（**全 16 张 X-3 码**）⇒ 每个前缀的 `declared_sheets`
      由 2 项漂成 16 项，`spec_attr` 由 `_SPECS` 变成 `X3_SHEET_SPECS`；
    - 这份集合又被并进形态 B 的候选 sheet ⇒ `--compare` 的探测面整体换了一批键，
      基线原键全成 `MISSING`（26 条 hard 假红）、别家 X-3 码涌入成 `NEW=960`。

    修法两条同时施加，都不含「第几个」这种位置语义：
    ① **扫全部**属性而不是首个（`break` 删掉），逐个记 provenance；
    ② 按**本短前缀的父 wp_code** 过滤 ⇒ `X3_SHEET_SPECS` 对 l2 只能贡献 `L2-3`，
       结构上不可能再把别家 15 张 X-3 码带进来。

    扫描面刻意取「模块的全部属性」而非白名单属性名：`_SPECS` / `X3_SHEET_SPECS` /
    `IE_SHEETS` / `_LEGACY_SHEETS` / `_SHEET_CONFIGS` / `_SUPPORTED_SHEETS` 这些名字在 16 个
    模块里各不相同，白名单必漏；父 wp_code 过滤已经把不相干常量挡在外面。
    """
    contributions: dict[str, list[str]] = {}
    for attr in sorted(dir(module)):
        if attr.startswith("__"):
            continue
        try:
            value = getattr(module, attr)
        except Exception:  # noqa: BLE001 —— 取不到就当没声明，不让扫描整体崩
            continue
        codes = _codes_of_parent(value, parent)
        if codes:
            contributions[attr] = codes
    union = sorted({c for codes in contributions.values() for c in codes})
    return {
        "declared_sheets": union,
        "spec_attr": sorted(contributions),
        "declared_sheets_provenance": contributions,
        "parent_filter": parent,
        "derivation": (
            "扫模块全部属性 → 逐个筛出 `^{父 wp_code}-\\d+$` 的 sheet 码 → 取并集"
            "（**不取「首个 `*_SPECS`」**，那是任务 17.3 修掉的位置性猜测）"
        ),
    }


def factory_specs_by_short_prefix(
    shorts: list[str], code_by_short: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """每个短前缀今天的 adapter 目标模块 + 该模块声明的 sheet 集合。

    目标模块从**已注册闭包**实取（口径与任务 1.3 的 `_adapter_target_module_name`
    一致 —— 直接 import 那一份，不抄第二份解析规则）。

    `code_by_short` 提供每个短前缀的 X-3 码（`work_surface` 真源），父 wp_code 由它派生 ——
    不用 `sp.upper()` 反推，免得哪天短前缀与 wp_code 的大小写/连字符约定变了才发现。
    `spec_attr` 自任务 17.3 起是**贡献属性名的有序列表**（原来是「首个命中的那一个」字符串）。
    """
    from tests.test_x3_catalog_registration import (
        _adapter_target_module_name,
        _trigger_adapter_registration,
    )
    from tests.test_x3_adapter_host_same_module import resolve_target_module_path
    from app.services.bulk_tab._kfgh_cycle_adapters import _endpoint_for

    registry = _trigger_adapter_registration()
    out: dict[str, dict[str, Any]] = {}
    for sp in shorts:
        raw = _adapter_target_module_name(sp, registry)
        parent = str(code_by_short[sp]).split("-", 1)[0]
        entry: dict[str, Any] = {
            "adapter_value": raw,
            "target_module": resolve_target_module_path(str(raw)) if raw else None,
            "declared_sheets": [],
            "spec_attr": None,
            "three_state_resolved": {},
            "error": None,
        }
        if not raw:
            entry["error"] = "adapter 目标模块判定不出（闭包与映射表均无）"
            out[sp] = entry
            continue
        try:
            module = importlib.import_module(entry["target_module"])
        except Exception as exc:  # noqa: BLE001 —— import 失败是硬失败，记明成因
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            out[sp] = entry
            continue
        entry.update(collect_sheet_declarations(module, parent))
        entry["three_state_resolved"] = {
            suffix: _endpoint_for(module, sp, suffix) is not None
            for suffix in ("export-template", "export-data", _IMPORT_SUFFIX)
        }
        entry["ie_sheets_declared"] = _jsonable(getattr(module, "IE_SHEETS", None))
        out[sp] = entry
    return out


_SHEET_CODE_RE = re.compile(r"\b([A-Z]\d{0,2}-\d{1,2})\b")


def shape_b_endpoints(app, long_prefixes: list[str]) -> dict[str, dict[str, Any]]:
    """`/api/{长前缀}/{wp_id}/{三态}` 的端点对象 + `sheet` 参数形态与候选 sheet。

    候选 sheet 的来源逐条留痕（`sheet` Query 的 default / description）——
    这 16 个模块今天没有统一白名单（正是 R4.4 要收敛成 `IE_SHEETS` 的理由）。
    """
    out: dict[str, dict[str, Any]] = {}
    for route in app.routes:
        segs = (getattr(route, "path", "") or "").strip("/").split("/")
        if len(segs) != 4 or segs[0] != "api":
            continue
        if segs[1] not in long_prefixes or segs[2] != "{wp_id}":
            continue
        suffix = segs[-1]
        if suffix not in ("export-template", "export-data", _IMPORT_SUFFIX):
            continue
        entry = out.setdefault(
            segs[1],
            {"endpoints": {}, "methods": {}, "host_modules": {}, "accepts_sheet": {},
             "sheet_default": {}, "sheet_candidates": [], "candidate_provenance": {}},
        )
        endpoint = getattr(route, "endpoint", None)
        entry["endpoints"][suffix] = endpoint
        entry["methods"][suffix] = sorted(getattr(route, "methods", None) or [])
        entry["host_modules"][suffix] = getattr(endpoint, "__module__", None)
        params = inspect.signature(endpoint).parameters if endpoint else {}
        accepts = "sheet" in params
        entry["accepts_sheet"][suffix] = accepts
        if accepts:
            raw = params["sheet"].default
            default = raw if isinstance(raw, str) else getattr(raw, "default", None)
            desc = getattr(raw, "description", None)
            entry["sheet_default"][suffix] = default if isinstance(default, str) else None
            found: set[str] = set()
            if isinstance(default, str):
                found.update(_SHEET_CODE_RE.findall(default))
                entry["candidate_provenance"].setdefault("query_default", []).append(default)
            if isinstance(desc, str):
                hit = _SHEET_CODE_RE.findall(desc)
                if hit:
                    found.update(hit)
                    entry["candidate_provenance"].setdefault("query_description", []).append(desc)
            # 宿主模块自己声明的白名单（R4.4 的 `IE_SHEETS`）—— 端点校验读的就是它，
            # 是这一层唯一的**显式**声明；任务 17.3 起把它并进候选来源，替掉原先
            # 「借 adapter 目标模块内首个 `*_SPECS`」那条位置性猜测。
            host_declared = _host_ie_sheets(entry["host_modules"].get(suffix))
            if host_declared:
                found.update(host_declared)
                entry["candidate_provenance"].setdefault("host_ie_sheets", []).append(
                    {"module": entry["host_modules"].get(suffix), "sheets": host_declared}
                )
            entry["sheet_candidates"] = sorted(set(entry["sheet_candidates"]) | found)
    return out


def _host_ie_sheets(module_name: str | None) -> list[str]:
    """宿主模块的 `IE_SHEETS` 里的 sheet 码（取不到就空列表，不抛）。"""
    if not module_name:
        return []
    try:
        module = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 —— 宿主 import 不动是别的问题，这里只作候选来源
        return []
    declared = getattr(module, "IE_SHEETS", None)
    if not isinstance(declared, (set, frozenset, list, tuple, dict)):
        return []
    return sorted(
        {v for v in declared if isinstance(v, str) and _SHEET_CODE_RE.fullmatch(v)}
    )


# ═══════════════════════════════════════════════════════════════════════════════
# xlsx 摘要（排除易变成员）
# ═══════════════════════════════════════════════════════════════════════════════


def zip_member_digests(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: _short(_sha(zf.read(name))) for name in sorted(zf.namelist())}


def artifact_fingerprint(data: bytes) -> dict[str, Any]:
    """xlsx 产物的可复现指纹。

    `stable_digest` = 排除易变成员后的「成员名 + 成员摘要」有序拼接的 sha256。
    另留 `raw_sha`（含易变成员）供人工核 —— 但**不作为**零回归判据。
    """
    info: dict[str, Any] = {"bytes": len(data), "raw_sha": _short(_sha(data))}
    try:
        members = zip_member_digests(data)
    except zipfile.BadZipFile:
        info["is_zip"] = False
        info["stable_digest"] = _short(_sha(data))
        return info
    info["is_zip"] = True
    info["member_count"] = len(members)
    stable = {k: v for k, v in members.items() if k not in _VOLATILE_ZIP_MEMBERS}
    info["excluded_volatile"] = sorted(set(members) & _VOLATILE_ZIP_MEMBERS)
    payload = "\n".join(f"{k}={v}" for k, v in sorted(stable.items()))
    info["stable_digest"] = _short(_sha(payload.encode("utf-8")))
    info["members"] = stable
    return info


def selfcheck_volatile_members() -> dict[str, Any]:
    """实测复核 `_VOLATILE_ZIP_MEMBERS`：隔 >1 秒建两次同样的 workbook。

    - 差异成员 ⊄ 名单 ⇒ 抛（出现新的易变成员，快照①的判据会失真）
    - 排除易变成员后 `stable_digest` 必须相等（否则判据本身不可复现）
    - 若两次原始字节恰好相同（同秒内），标 `inconclusive` 但仍校验 stable_digest
    """
    from app.routers.wp_render_strategies._cycle_import_export_common import (
        build_workbook_template,
    )

    def once() -> bytes:
        wb = build_workbook_template("X-3", ["a", "b", "c"], title="t")
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    first = once()
    time.sleep(1.2)
    second = once()
    m1, m2 = zip_member_digests(first), zip_member_digests(second)
    differing = sorted(k for k in set(m1) | set(m2) if m1.get(k) != m2.get(k))
    f1, f2 = artifact_fingerprint(first), artifact_fingerprint(second)
    report = {
        "declared_volatile": sorted(_VOLATILE_ZIP_MEMBERS),
        "observed_differing_members": differing,
        "raw_bytes_equal": first == second,
        "stable_digest_equal": f1["stable_digest"] == f2["stable_digest"],
        "inconclusive": first == second,
        "note": "同秒内建两次会字节相同 ⇒ 该轮无法证伪易变名单，但 stable_digest 仍须相等",
    }
    unexpected = [m for m in differing if m not in _VOLATILE_ZIP_MEMBERS]
    if unexpected:
        raise SystemExit(
            f"出现名单外的易变 zip 成员 {unexpected} —— 快照①判据会失真，先扩名单再跑"
        )
    if not report["stable_digest_equal"]:
        raise SystemExit("排除易变成员后 stable_digest 仍不等 —— 判据不可复现，拒绝出快照")
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 快照①（连库；全部 async 工作收在一次 asyncio.run 内）
# ═══════════════════════════════════════════════════════════════════════════════


class _SentinelDB:
    """任何属性访问都炸 —— 用来实证「这条导出路径到底碰不碰 db」。"""

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        raise RuntimeError(f"DB_TOUCHED:{name}")


async def _drain_response(resp: Any) -> bytes:
    if hasattr(resp, "body_iterator"):
        return b"".join([chunk async for chunk in resp.body_iterator])
    body = getattr(resp, "body", b"") or b""
    return bytes(body)


async def _find_wp_ids(parent_codes: list[str]) -> dict[str, Any]:
    """真实库里逐 parent wp_code 取一个底稿对象。

    - 过滤用 `working_paper.is_deleted = false`（`get_active_filter` 的作用域是
      `tb_*` 四表的数据集版本治理，对 `working_paper` 不适用 —— 这点如实登记，
      免得下一轮以为漏用了统一入口）。
    - 取 `min(id::text)` 保证同一库上可复现，`--compare` 复用快照里记下的 id。
    """
    import sqlalchemy as sa

    from app.core.database import async_session

    result: dict[str, Any] = {
        "available": False,
        "filter": "working_paper.is_deleted = false JOIN wp_index ON wp_index.id = working_paper.wp_index_id",
        "wp_ids": {},
        "counts": {},
        "missing": [],
        "error": None,
    }
    try:
        async with async_session() as db:
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT wi.wp_code, count(*)::int AS n, min(wp.id::text) AS wp_id "
                        "FROM working_paper wp "
                        "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                        "WHERE wp.is_deleted = false AND wi.wp_code = ANY(:codes) "
                        "GROUP BY wi.wp_code ORDER BY wi.wp_code"
                    ),
                    {"codes": parent_codes},
                )
            ).fetchall()
    except Exception as exc:  # noqa: BLE001 —— 连不上库是硬失败，记 ERROR 态并如实回报
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
        result["missing"] = list(parent_codes)
        return result
    result["available"] = True
    for code, count, wp_id in rows:
        result["counts"][code] = int(count)
        result["wp_ids"][code] = wp_id
    result["missing"] = [c for c in parent_codes if c not in result["wp_ids"]]
    return result


_NO_OBJECT = {
    "status": "no_usable_object",
    "note": "真实库中未找到该 parent wp_code 的合法底稿对象",
    "followup_task": "15.1（真实库 16 张往返验收脚本）—— 禁用 fixture 冒充真实对象",
}


async def _call_factory_export(
    export_fn: Callable[..., Any], *, db: Any, wp_id: str, sheet: str, mode: str
) -> dict[str, Any]:
    try:
        data = await export_fn(db, wp_id, sheet, mode)
    except Exception as exc:  # noqa: BLE001 —— 失败也是基线的一部分，逐条记明成因
        return {
            "ok": False,
            "error_class": type(exc).__name__,
            "error": f"{type(exc).__name__}: {exc}"[:260],
        }
    out = {"ok": True}
    out.update(artifact_fingerprint(bytes(data)))
    return out


async def _call_shape_b_endpoint(
    endpoint: Callable[..., Any], *, db: Any, wp_id: str, sheet: str | None
) -> dict[str, Any]:
    """直调形态 B 端点（绕 FastAPI DI），返回产物指纹或失败成因。

    🔴 `sheet` **一律显式传，含 `None`** —— 任务 17.3 修的第二条缺陷就在这一行。
    原实现写的是 `if sheet is not None and "sheet" in params`，`sheet is None` 时**不传**
    该参数；直调没有 DI 兜底 ⇒ 形参拿到的是 `Query(None)` 这个 `FieldInfo` **对象本身**，
    端点的 `sheet not in IE_SHEETS` 于是成立、按「未登记 sheet」抛 400：
    `不支持的sheet: annotation=Union[str, NoneType] required=False default=None …`。
    Checkpoint 7 里 `l2` / `m1` 那 4 条 `BROKEN` / `ERROR_CLASS_CHANGED` 全是这么来的（假红）。
    `sheet=None` 才是「HTTP 请求省略 `?sheet=`」的真值。
    """
    params = inspect.signature(endpoint).parameters
    kwargs: dict[str, Any] = {}
    if "wp_id" in params:
        kwargs["wp_id"] = wp_id
    if "sheet" in params:
        kwargs["sheet"] = sheet
    elif sheet is not None:
        # fail-loud：要探的 sheet 实参喂不进去时**不许静默丢参** —— 丢了就会拿「不传 sheet」
        # 的产物去比「传了 sheet」的基线摘要，得出假 SAME 或假 DIGEST_MISMATCH，
        # 两种都比一条 400 难查一个量级。
        return {
            "ok": False,
            "sheet_arg": sheet,
            "error_class": "SheetArgUnsupported",
            "error": (
                f"端点 {getattr(endpoint, '__qualname__', endpoint)!r} 无 `sheet` 形参，"
                f"无法重放 sheet={sheet!r}（基线该键是带 sheet 实参探到的）"
            ),
        }
    if "db" in params:
        kwargs["db"] = db
    if "current_user" in params:
        from app.services.bulk_tab._d_cycle_adapters import _DUMMY_USER

        kwargs["current_user"] = _DUMMY_USER
    if "user" in params:
        from app.services.bulk_tab._d_cycle_adapters import _DUMMY_USER

        kwargs["user"] = _DUMMY_USER
    if "include_guidance" in params:
        kwargs["include_guidance"] = False
    try:
        body = await _drain_response(await endpoint(**kwargs))
    except Exception as exc:  # noqa: BLE001 —— 存量缺陷要如实进基线，不能吞
        return {
            "ok": False,
            "sheet_arg": sheet,
            "error_class": type(exc).__name__,
            "error": f"{type(exc).__name__}: {exc}"[:260],
        }
    out: dict[str, Any] = {"ok": True, "sheet_arg": sheet}
    out.update(artifact_fingerprint(body))
    return out


async def collect_export_snapshot(
    surface: dict[str, Any],
    factory: dict[str, dict[str, Any]],
    shape_b: dict[str, dict[str, Any]],
    *,
    reuse_wp_ids: dict[str, str] | None = None,
    replay_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """快照① —— 两条通路 × {export-template, export-data}。**从不调 import-data。**

    `replay_surface`（任务 17.3 新增，`--compare` 必传）= 基线记下的探测面：
    `{"factory": {短前缀: [sheet…]}, "shape_b": {长前缀: {后缀: [sheet 实参|None…]}}}`。
    给了就**按基线原键重放**，不给才回退到本轮派生的候选（`--snapshot` 走这条）。
    两种模式下判据函数（`_call_shape_b_endpoint` / `_call_factory_export` /
    `artifact_fingerprint`）是同一份，探测面换了、口径没换。
    """
    from app.core.database import async_session

    # 用显式 raise 而不是 `assert`：`python -O` 会把 assert 整条剥掉，只读边界不能靠
    # 一个可被优化掉的语句守着。
    if _IMPORT_SUFFIX in _ALLOWED_SUFFIXES:
        raise SystemExit(
            f"只读边界被破坏：`{_IMPORT_SUFFIX}` 不得进作业集（它会写库），"
            f"当前 _ALLOWED_SUFFIXES={_ALLOWED_SUFFIXES}"
        )

    parents = surface["parent_wp_codes"]
    db_info = await _find_wp_ids(parents)
    if reuse_wp_ids:
        db_info["reused_from_baseline"] = sorted(reuse_wp_ids)
        for code, wp_id in reuse_wp_ids.items():
            db_info["wp_ids"].setdefault(code, wp_id)
        db_info["missing"] = [c for c in parents if c not in db_info["wp_ids"]]

    out: dict[str, Any] = {
        "criterion": (
            "stable_digest = 排除易变 zip 成员后的逐成员摘要（R1.6 的「逐字节不变」"
            "落到可复现的产物结构上；raw_sha 含时间戳，只作人工核）"
        ),
        "allowed_suffixes": list(_ALLOWED_SUFFIXES),
        "never_invoked": [_IMPORT_SUFFIX],
        "db": db_info,
        "probe_surface_mode": (
            "baseline_replay（按基线记下的键逐条重放）"
            if replay_surface
            else "derived（本轮从各真源派生候选 sheet）"
        ),
        "factory_adapter_path": {},
        "shape_b_host_path": {},
    }
    replay_factory: dict[str, list[str]] = dict((replay_surface or {}).get("factory") or {})
    replay_shape_b: dict[str, dict[str, list[Any]]] = dict(
        (replay_surface or {}).get("shape_b") or {}
    )

    from tests.test_x3_catalog_registration import _trigger_adapter_registration

    registry = _trigger_adapter_registration()

    # ── 通路 A：短前缀 → adapter → 工厂模块（bulk 今天的真实入口）────────────
    for long_prefix in surface["long_prefixes"]:
        short = surface["short_by_long"][long_prefix]
        x3_code = surface["code_by_short"][short]
        parent = x3_code.split("-", 1)[0]
        wp_id = db_info["wp_ids"].get(parent)
        spec = registry.get(short)
        declared = list(factory.get(short, {}).get("declared_sheets", []))
        replayed = replay_factory.get(short)
        sheets_to_probe = list(replayed) if replayed is not None else declared
        node: dict[str, Any] = {
            "adapter_target_module": factory.get(short, {}).get("target_module"),
            "declared_sheets": declared,
            "probe_surface": {
                "source": "baseline_replay" if replayed is not None else "derived",
                "sheets": sheets_to_probe,
                # 派生值即使不驱动探测也照记 —— 漂移要看得见，不能被重放掩掉
                "derived_declared_sheets": declared,
            },
            "wp_id": wp_id,
            "sheets": {},
        }
        export_fn = getattr(spec, "export_fn", None) if spec is not None else None
        if export_fn is None:
            node["error"] = f"`{short}` 不在 IE_ADAPTER_REGISTRY 或无 export_fn"
            out["factory_adapter_path"][short] = node
            continue
        for sheet in sheets_to_probe:
            is_x3 = sheet == x3_code
            leaf: dict[str, Any] = {
                "is_x3_work_surface": is_x3,
                "zero_regression_scope": (
                    "work_surface（本 spec 作业面，施加后由专属模块接管）"
                    if is_x3
                    else "informational（该短前缀在 catalog 零启用 ⇒ bulk 今天从不取数；"
                    "施加后 adapter 改指专属模块，此 sheet 经短前缀不再可达，"
                    "但它今天也不可达 ⇒ 非 R1.6 意义上的回归）"
                ),
                "actions": {},
            }
            # export-template：用哨兵 db 实证是否 DB-free
            leaf["actions"]["export-template"] = await _call_factory_export(
                export_fn, db=_SentinelDB(), wp_id=wp_id or "probe-wp-id",
                sheet=sheet, mode="template",
            )
            leaf["actions"]["export-template"]["db_free_probe"] = "SentinelDB"
            if wp_id is None:
                leaf["actions"]["export-data"] = dict(_NO_OBJECT)
            else:
                async with async_session() as db:  # 每调用一个新 session：防事务中毒级联
                    leaf["actions"]["export-data"] = await _call_factory_export(
                        export_fn, db=db, wp_id=wp_id, sheet=sheet, mode="data"
                    )
            node["sheets"][sheet] = leaf
        out["factory_adapter_path"][short] = node

    # ── 通路 B：长前缀形态 B 端点（界面今天的真实入口，R1.6 / R11.2 的判据面）──
    for long_prefix in surface["long_prefixes"]:
        short = surface["short_by_long"][long_prefix]
        x3_code = surface["code_by_short"][short]
        parent = x3_code.split("-", 1)[0]
        wp_id = db_info["wp_ids"].get(parent)
        info = shape_b.get(long_prefix, {})
        node = {
            "short_prefix": short,
            "wp_id": wp_id,
            "methods": info.get("methods", {}),
            "host_modules": info.get("host_modules", {}),
            "accepts_sheet": info.get("accepts_sheet", {}),
            "sheet_default": info.get("sheet_default", {}),
            "candidate_provenance": info.get("candidate_provenance", {}),
            "probed": {},
        }
        # 非 X-3 候选 sheet = 端点自报候选（Query default/description + 宿主 `IE_SHEETS`）
        # ∪ adapter 目标模块按父 wp_code 过滤后的声明 sheet，去掉 X-3 本身
        candidates = set(info.get("sheet_candidates") or [])
        candidates |= set(factory.get(short, {}).get("declared_sheets", []))
        non_x3 = sorted(c for c in candidates if c != x3_code)
        node["non_x3_candidates"] = non_x3
        for suffix in _ALLOWED_SUFFIXES:
            endpoint = (info.get("endpoints") or {}).get(suffix)
            if endpoint is None:
                # 端点整条消失 ⇒ 本轮探不到 ⇒ 基线里的那些键在 `--compare` 里落成
                # `MISSING`（hard）。这条是 MISSING 仍然承重的通道，不能因为重放而当它不存在。
                node["probed"][suffix] = {"error": f"无 {suffix} 形态 B 端点"}
                continue
            accepts = bool((info.get("accepts_sheet") or {}).get(suffix))
            replayed_args = (replay_shape_b.get(long_prefix) or {}).get(suffix)
            if replayed_args is not None:
                sheet_args: list[str | None] = list(replayed_args)
                surface_source = "baseline_replay"
            else:
                sheet_args = list(non_x3) if accepts else [None]
                if not sheet_args:
                    sheet_args = [None]
                surface_source = "derived"
            per_sheet: dict[str, Any] = {}
            for sheet in sheet_args:
                key = sheet or _HANDLER_DEFAULT_KEY
                if suffix == "export-template":
                    per_sheet[key] = await _call_shape_b_endpoint(
                        endpoint, db=_SentinelDB(), wp_id=wp_id or "probe-wp-id", sheet=sheet
                    )
                    per_sheet[key]["db_free_probe"] = "SentinelDB"
                    if not per_sheet[key]["ok"] and "DB_TOUCHED" in str(
                        per_sheet[key].get("error", "")
                    ):
                        # 该端点确实要 db ⇒ 换真 session 重跑（记明两次都跑过）
                        if wp_id is None:
                            per_sheet[key] = dict(_NO_OBJECT)
                            per_sheet[key]["needs_db"] = True
                        else:
                            async with async_session() as db:
                                retried = await _call_shape_b_endpoint(
                                    endpoint, db=db, wp_id=wp_id, sheet=sheet
                                )
                            retried["db_free_probe"] = "SentinelDB→真 session（该端点需 db）"
                            per_sheet[key] = retried
                elif wp_id is None:
                    per_sheet[key] = dict(_NO_OBJECT)
                else:
                    async with async_session() as db:
                        per_sheet[key] = await _call_shape_b_endpoint(
                            endpoint, db=db, wp_id=wp_id, sheet=sheet
                        )
            node["probed"][suffix] = {
                "zero_regression_scope": "must_be_stable（R1.6 / R11.2：非 X-3 产物不得变）",
                "probe_surface": {
                    "source": surface_source,
                    "sheet_args": [s if s is not None else _HANDLER_DEFAULT_KEY for s in sheet_args],
                    "derived_non_x3_candidates": non_x3,
                    "accepts_sheet": accepts,
                },
                "by_sheet": per_sheet,
            }
        out["shape_b_host_path"][long_prefix] = node

    # 🔴 反空转：探测面塌掉时「无差异」会变成假绿 ⇒ 覆盖面不足即打红
    probed_pairs = sum(
        len(leaf.get("actions") or {})
        for node in out["factory_adapter_path"].values()
        for leaf in (node.get("sheets") or {}).values()
    ) + sum(
        len((block.get("by_sheet") or {}))
        for node in out["shape_b_host_path"].values()
        for block in (node.get("probed") or {}).values()
    )
    out["probed_pair_count"] = probed_pairs
    covered = {
        "factory_prefixes": len(out["factory_adapter_path"]),
        "shape_b_prefixes": len(out["shape_b_host_path"]),
        "probed_pairs": probed_pairs,
    }
    out["scan_surface_selfcheck"] = covered
    if covered["factory_prefixes"] != 16 or covered["shape_b_prefixes"] != 16 or probed_pairs < 60:
        raise SystemExit(f"快照①探测面异常: {covered}（应 16/16 且 ≥60 对）")
    if replay_surface:
        out["replay_coverage"] = _replay_coverage(out, replay_surface)
    return out


def _replay_coverage(exports: dict[str, Any], replay_surface: dict[str, Any]) -> dict[str, Any]:
    """重放模式的覆盖自检：基线要求的每个键，本轮到底探到没探到。

    🔴 「按基线键重放」最容易滑成的假绿是**请求了却没探**（端点没了、sheet 实参喂不进去、
    循环被 continue 跳过）—— 那些键在 `--compare` 里会落成 `MISSING`，看起来像判据面被砍。
    故这里把「要求探的」与「真探到的」逐条对差，未探到的键**指名列出**；
    要求面为空直接抛（基线解析成空集时「零差异」是最贵的那种假绿）。
    """
    requested: list[str] = []
    for short, sheets in sorted((replay_surface.get("factory") or {}).items()):
        for sheet in sheets:
            for action in _ALLOWED_SUFFIXES:
                requested.append(f"factory/{short}/{sheet}/{action}")
    for long_prefix, per_suffix in sorted((replay_surface.get("shape_b") or {}).items()):
        for suffix, args in sorted(per_suffix.items()):
            for sheet in args:
                key = sheet if sheet is not None else _HANDLER_DEFAULT_KEY
                requested.append(f"shapeB/{long_prefix}/{key}/{suffix}")
    if not requested:
        raise SystemExit(
            "重放面解析为空 —— 基线里一个键都没取到（`--compare` 会因此把全部基线键报成 "
            "MISSING）。先核 baseline_snapshot_x3.json 的 "
            "`snapshot_1_export_artifacts.{factory_adapter_path,shape_b_host_path}` 结构"
        )
    probed = set(_walk_export_leaves(exports))
    unprobed = [k for k in requested if k not in probed]
    return {
        "criterion": "基线键 → 本轮实际探到的键，逐条对差（未探到的指名列出）",
        "requested": len(requested),
        "probed": len(probed),
        "unprobed_keys": unprobed,
        "extra_keys_not_in_baseline": sorted(probed - set(requested)),
        "verdict": "FULL" if not unprobed else "PARTIAL",
        "note": (
            "`PARTIAL` 不自动等于回归 —— 端点整条消失也会落在这里，"
            "由 `--compare` 按 `MISSING`（hard）判"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 快照② / ③（纯运行期结构，不连库）
# ═══════════════════════════════════════════════════════════════════════════════


def collect_route_inventory(app) -> dict[str, Any]:
    """快照② —— `test_ie_route_inventory` 全部基线数字（声明 + 实测 + 目标）。"""
    import tests.test_ie_route_inventory as inv

    declared = {
        name: _jsonable(value)
        for name, value in sorted(vars(inv).items())
        if name.startswith("_BASE_") or name == "_TRULY_DEAD_FACTORY_PREFIXES"
    }

    groups = inv.group_ie_routes(app)
    shape_a, shape_b = inv.classify_route_shapes(app)
    counts = inv._count_ie_routes(app)
    ie_module_files = sorted(inv._STRATEGIES.glob("*_import_export.py"))
    # 这两项测试内是行内计算、未抽成 helper ⇒ 只能镜像同一算法；`--compare`
    # 两侧都走本函数，口径自洽。
    no_decorator = [
        p.name
        for p in ie_module_files
        if not re.search(r"@router\.(get|post|put|delete)", p.read_text(encoding="utf-8"))
    ]
    factory_prefixes = inv._factory_api_prefixes(ie_module_files)

    live = {
        "groups": len(groups),
        "full3_prefixes": len({k for k, v in groups.items() if len(v) == 3}),
        "shape_a_prefixes": len(shape_a),
        "shape_b_prefixes": len(shape_b),
        "route_kinds": dict(sorted(counts.items())),
        "three_state_routes": sum(counts.values()),
        "ie_module_files": len(ie_module_files),
        "no_decorator_modules": len(no_decorator),
        "factory_api_prefixes": len(factory_prefixes),
        "app_routes_total": len(app.routes),
    }

    # 反空转：扫描面塌掉时数字会「好看地变小」，必须在这一步就打红
    surface_ok = {
        "app_routes_gt_1000": live["app_routes_total"] > 1000,
        "groups_gt_50": live["groups"] > 50,
        "ie_modules_gt_50": live["ie_module_files"] > 50,
    }
    if not all(surface_ok.values()):
        raise SystemExit(f"扫描面自检失败（快照会失真）: {surface_ok}")

    target = {
        key: (
            {k: live["route_kinds"][k] + v for k, v in delta.items()}
            if isinstance(delta, dict)
            else live[key] + delta
        )
        for key, delta in _TARGET_DELTAS.items()
        if key in live
    }

    return {
        "declared_baselines": declared,
        "live": live,
        "scan_surface_selfcheck": surface_ok,
        "target_after_spec": target,
        "target_deltas": _TARGET_DELTAS,
        "x3_short_prefixes_in_groups": sorted(
            p for p in groups if p in set(_short_prefix_set())
        ),
        "note": (
            "16 个短前缀今天在运行期零形态 A 路由（`_TRULY_DEAD_FACTORY_PREFIXES` 覆盖），"
            "故 `x3_short_prefixes_in_groups` 现为空；施加后应恰好变成 16 个"
        ),
    }


def _short_prefix_set() -> list[str]:
    from tests.test_ie_prefix_reachability import (
        _X3_DEDICATED_LONG_PREFIXES,
        _x3_short_prefix,
    )

    return [_x3_short_prefix(p) for p in _X3_DEDICATED_LONG_PREFIXES]


def collect_adapter_registry(surface: dict[str, Any]) -> dict[str, Any]:
    """快照③ —— `IE_ADAPTER_REGISTRY` 键集 + 每键解析出的目标模块。"""
    from tests.test_ie_route_inventory import _adapter_registry_keys
    from tests.test_x3_catalog_registration import (
        _adapter_target_module_name,
        _trigger_adapter_registration,
    )
    from tests.test_x3_adapter_host_same_module import resolve_target_module_path

    registry = _trigger_adapter_registration()
    keys = sorted(_adapter_registry_keys())
    per_key: dict[str, Any] = {}
    for key in keys:
        raw = _adapter_target_module_name(key, registry)
        dotted = resolve_target_module_path(str(raw)) if raw else None
        importable = None
        if dotted:
            try:
                importlib.import_module(dotted)
                importable = True
            except Exception as exc:  # noqa: BLE001 —— import 失败要记明，不静默
                importable = f"{type(exc).__name__}: {exc}"[:160]
        per_key[key] = {
            "adapter_value": raw,
            "target_module": dotted,
            "importable": importable,
            "is_x3_short_prefix": key in set(surface["long_by_short"]),
        }
    x3 = {k: v for k, v in per_key.items() if v["is_x3_short_prefix"]}
    return {
        "key_count": len(keys),
        "keys": keys,
        "by_key": per_key,
        "x3_short_prefixes": sorted(x3),
        "x3_targets_today": {k: v["target_module"] for k, v in sorted(x3.items())},
        "x3_targets_after_spec": {
            short: f"app.routers.{surface['long_by_short'][short].replace('-', '_')}"
            for short in sorted(x3)
        },
        "expected_after_spec": (
            "键集规模不变（97）；仅这 16 键的 target_module 从工厂 "
            "`_{x}_import_export` 改指专属 router 模块（任务 6.1）"
        ),
        "note": (
            "`x3_targets_after_spec` 是**按 design §C3 规则派生的预期值**，"
            "长前缀连字符换下划线即专属模块名；任务 6.1 施加后由 `--compare` 逐键核对"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 两列 CI 快照（裁决 2）
# ═══════════════════════════════════════════════════════════════════════════════


def _count_ie_sync_drift() -> dict[str, Any]:
    """`check_ie_catalog_sync.py` 的不一致条目数 —— 读该脚本自己的判定输出。

    双判据交叉：表头自报的 N 与 `✗` 行数必须一致（不一致说明解析口径漂了，打红）。
    """
    import subprocess

    cmd = _CI_JOBS["acnr-ie-catalog-sync"]
    proc = subprocess.run(  # noqa: S603 —— 命令来自本文件常量
        cmd.split(),
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    marks = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("✗")]
    header = re.search(r"发现\s*(\d+)\s*处不一致", text)
    declared = int(header.group(1)) if header else None
    out: dict[str, Any] = {
        "metric": "manifest↔catalog 不一致条目数",
        "counted_marker_lines": len(marks),
        "declared_in_header": declared,
        "agree": declared is None or declared == len(marks),
        "entries": marks,
        "method": (
            f"`{cmd}` 全量捕获输出；条目数 = 以 ✗ 起头的行数，"
            "并与表头「发现 N 处不一致」交叉核对"
        ),
    }
    if not out["agree"]:
        out["warning"] = (
            "表头自报数与 ✗ 行数不一致 —— 解析口径可能已漂，条目数不可作基线"
        )
    return out


def _count_catalog_drift() -> dict[str, Any]:
    """`check_catalog_drift.py` 的 drift 条目数。

    该脚本为控制 CI 日志长度会**截断** diff 输出（「... (N more lines omitted)」），
    故条目数不解析 stdout，改按它自身的判据在进程内复算一次：
    committed 文本 vs `_deterministic_json(generate_catalog(offline=True, 同版本号))`。
    条目数取「sheets 里逐 `addr_id` 比较后不相等的条目数」——比 diff 行数稳定，
    且直接对应「本 spec 不得新增 drift 条目」这条义务。
    """
    from scripts.acnr.generate_catalog import _deterministic_json, generate_catalog

    committed_path = BACKEND / "data" / "acnr" / "global_catalog.json"
    committed = committed_path.read_text(encoding="utf-8")
    doc = json.loads(committed)
    version = doc.get("registry_version")
    catalog, _report, _blocked = generate_catalog(offline=True, registry_version=version)
    generated = _deterministic_json(catalog)

    diff = list(difflib.unified_diff(committed.splitlines(True), generated.splitlines(True), n=3))
    left = {s.get("addr_id"): s for s in (doc.get("sheets") or [])}
    right = {s.get("addr_id"): s for s in (catalog.get("sheets") or [])}
    differing = [k for k in sorted(set(left) | set(right)) if left.get(k) != right.get(k)]

    out: dict[str, Any] = {
        "metric": "committed catalog 与离线重生成结果不一致的 sheet 条目数",
        "registry_version": version,
        "byte_equal": committed == generated,
        "differing_entry_count": len(differing),
        "differing_addr_ids": differing,
        "diff_hunks": sum(1 for ln in diff if ln.startswith("@@")),
        "diff_changed_lines": sum(
            1
            for ln in diff
            if (ln.startswith("-") or ln.startswith("+")) and not ln.startswith(("---", "+++"))
        ),
        "sheets_committed": len(left),
        "sheets_generated": len(right),
        "method": (
            "进程内复算（脚本 stdout 会截断 diff，解析不可靠）："
            "`generate_catalog(offline=True, registry_version=<committed 值>)` → "
            "`_deterministic_json` → 与 committed 文本比对；条目数按 sheets[].addr_id 逐条比较"
        ),
    }
    # 反空转：条目数为 0 却 byte_equal=False（或反之）说明复算口径错了
    if out["byte_equal"] != (len(differing) == 0 and out["diff_changed_lines"] == 0):
        out["warning"] = (
            "byte_equal 与结构化差异不自洽 —— 差异可能落在 sheets 之外的字段，"
            "条目数须结合 diff_changed_lines 一起读"
        )
    if len(left) < 1000:
        raise SystemExit(f"catalog sheets 异常少（{len(left)}）—— drift 复算面失真")
    return out


def collect_ci_red_jobs(*, run_probe: bool = True) -> dict[str, Any]:
    """两列 CI 快照 —— 退出码走 `run_ci_probe`（唯一口径），条目数按上面两个复算。"""
    out: dict[str, Any] = {
        "verdict_2_duty": "本 spec 不修这两个红，只保证红的规模不变大",
        "jobs": {},
    }
    if not run_probe:
        out["skipped"] = "--no-ci-probe"
        return out

    from scripts.check.check_x3_deviation_registry import run_ci_probe

    for job, cmd in _CI_JOBS.items():
        probe = run_ci_probe(cmd)
        node: dict[str, Any] = dict(probe)
        node["reused_helper"] = (
            "backend/scripts/check/check_x3_deviation_registry.py::run_ci_probe"
        )
        if job == "acnr-ie-catalog-sync":
            node["drift"] = _count_ie_sync_drift()
        else:
            node["drift"] = _count_catalog_drift()
        out["jobs"][job] = node
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 逐张两列实测值矩阵（design §逐张两列实测值（R1.2））
# ═══════════════════════════════════════════════════════════════════════════════


_DESIGN_TABLE_HEADING = "### 逐张两列实测值（R1.2）"
_DESIGN_ROW_RE = re.compile(r"^\|\s*([A-Z]\d{0,2}-\d{1,2})\s*\|(.*)$")
_DESIGN_SHAPE_RE = re.compile(r"（\s*([AB])\s*/\s*([^/）]+?)\s*(?:/\s*`?([\w.]+)`?\s*)?）")


def parse_design_method_column() -> dict[str, dict[str, Any]]:
    """解析 design §逐张两列实测值（R1.2）表里「形态 / 方法 / 宿主模块」那一格。

    方法列的书写约定（design 表注）：按 `export-template, export-data, import-data`
    顺序；`POST×3` = 三态皆 POST。解析出来供 `build_route_matrix` 与运行期实测
    **交叉对照** —— 这样 design 表若与实测不符，是被机器抓出来的，不靠人眼。
    """
    text = DESIGN_MD.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, ln in enumerate(text) if ln.strip() == _DESIGN_TABLE_HEADING)
    except StopIteration:
        raise SystemExit(f"design.md 找不到标题 `{_DESIGN_TABLE_HEADING}` —— 锚点失效")
    out: dict[str, dict[str, Any]] = {}
    for line in text[start + 1:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        m = _DESIGN_ROW_RE.match(line.strip())
        if not m:
            continue
        code, rest = m.group(1), m.group(2)
        shape_m = _DESIGN_SHAPE_RE.search(rest)
        if not shape_m:
            continue
        shape, methods_raw, host = shape_m.group(1), shape_m.group(2), shape_m.group(3)
        if "×3" in methods_raw:
            verb = methods_raw.split("×")[0].strip()
            methods = [verb, verb, verb]
        else:
            methods = [p.strip() for p in methods_raw.split(",")]
        out[code] = {
            "shape": shape,
            "methods_raw": methods_raw,
            "methods": methods,
            "host_module_suffix": host,
        }
    if len(out) != 16:
        raise SystemExit(
            f"design 逐张两列表解析出 {len(out)} 行（应 16 行）—— 锚点或表格式变了"
        )
    return out


def build_route_matrix(
    surface: dict[str, Any],
    shape_b: dict[str, dict[str, Any]],
    adapter: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    """逐 sheet 两列：谁提供运行期三态端点 / 谁命中 `IE_ADAPTER_REGISTRY`（R1.2）。"""
    from tests.test_x3_adapter_host_same_module import strict_shape_a_endpoints
    from app.main import app
    from app.services.acnr.catalog import list_sheets

    strict_a = strict_shape_a_endpoints(app)
    catalog_ie: dict[str, dict[str, Any]] = {}
    for sheet in list_sheets():
        code = sheet.get("sheet_code")
        ie = sheet.get("import_export") or {}
        if code in surface["target_sheets"]:
            catalog_ie[code] = {
                "state": (
                    "missing(键缺失)"
                    if "import_export" not in sheet
                    else ("null" if sheet.get("import_export") is None else
                          ("enabled" if ie.get("enabled") else "disabled"))
                ),
                "api_prefix": ie.get("api_prefix"),
                "sheet_name": sheet.get("sheet_name"),
                "addr_id": sheet.get("addr_id"),
                "class_code": sheet.get("class_code"),
            }

    design_rows = parse_design_method_column()
    ordered = ("export-template", "export-data", "import-data")

    rows: list[dict[str, Any]] = []
    design_mismatch: dict[str, Any] = {}
    for long_prefix in surface["long_prefixes"]:
        short = surface["short_by_long"][long_prefix]
        code = surface["code_by_short"][short]
        info = shape_b.get(long_prefix, {})
        methods = info.get("methods", {})
        hosts = sorted({m for m in (info.get("host_modules") or {}).values() if m})
        measured_seq = [
            (methods.get(s) or ["<无端点>"])[0] if methods.get(s) else "<无端点>"
            for s in ordered
        ]
        design_row = design_rows.get(code, {})
        if design_row and design_row.get("methods") != measured_seq:
            design_mismatch[code] = {
                "design_says": design_row.get("methods_raw"),
                "design_parsed": design_row.get("methods"),
                "measured": measured_seq,
                "order": list(ordered),
            }
        rows.append(
            {
                "sheet_code": code,
                "design_declared": design_row,
                "measured_method_sequence": measured_seq,
                "catalog": catalog_ie.get(code, {"state": "not_in_catalog"}),
                "runtime_three_state": {
                    "api_prefix": long_prefix,
                    "shape": "B（/api/{prefix}/{wp_id}/{三态}）",
                    "methods": {k: methods.get(k) for k in sorted(methods)},
                    "host_modules": hosts,
                    "accepts_sheet": info.get("accepts_sheet", {}),
                    "sheet_default": info.get("sheet_default", {}),
                },
                "shape_a_today": {
                    "short_prefix_has_strict_shape_a": short in strict_a,
                    "suffixes": sorted(strict_a.get(short, {})),
                },
                "adapter_hit": {
                    "api_prefix": short,
                    "in_registry": short in set(adapter["keys"]),
                    "target_module": adapter["by_key"].get(short, {}).get("target_module"),
                },
                "target_after_spec": {
                    "api_prefix": short,
                    "shape": "A（/api/workpapers/{wp_id}/{短前缀}/{三态}，POST×3）",
                    "host_module": f"app.routers.{long_prefix.replace('-', '_')}",
                    "adapter_target_module": adapter["x3_targets_after_spec"].get(short),
                    "verdict": "两路同源（single api_prefix, single implementation）",
                },
            }
        )

    conclusions = {
        "short_prefixes_with_shape_a_today": sorted(
            r["adapter_hit"]["api_prefix"]
            for r in rows
            if r["shape_a_today"]["short_prefix_has_strict_shape_a"]
        ),
        "catalog_enabled_today": sorted(
            r["sheet_code"] for r in rows if r["catalog"].get("state") == "enabled"
        ),
        "adapter_hit_count": sum(1 for r in rows if r["adapter_hit"]["in_registry"]),
        "reading": (
            "①16 个短前缀在运行期零形态 A 路由（无路径冲突，新增即可）；"
            "②16 张在 catalog 零启用条目 ⇒ bulk 今天从不向这 16 个短前缀取数 ⇒ "
            "任务 6.1 的 adapter 改指在施加当刻行为中性"
        ),
    }
    design_cross_check = {
        "criterion": (
            "运行期实测的 (export-template, export-data, import-data) 方法序列 "
            "== design §逐张两列实测值（R1.2）表里那一格声明的方法列"
        ),
        "rows_parsed_from_design": len(design_rows),
        "mismatch_count": len(design_mismatch),
        "mismatches": design_mismatch,
        "verdict": "ALIGNED" if not design_mismatch else "DESIGN_TABLE_STALE",
        "handling": (
            "不一致时以**运行期实测**为准（本表即实测），design 表的方法列须按本表更正；"
            "方法基线对任务 5.2「既有形态 B 端点的方法逐字不动」是必要前置"
        ),
    }
    return {
        "_meta": {
            "spec": SELF_SPEC,
            "task": "1.8",
            "requirement": "1.2（逐张两列实测值）· 1.1/1.3~1.7 · 10.9",
            "written_at": _now(),
            "generated_by": SCRIPT_PATH.relative_to(ROOT).as_posix() + " --snapshot",
        },
        "rows": rows,
        "conclusions": conclusions,
        "design_cross_check": design_cross_check,
        "route_inventory_baselines": {
            "declared": inventory["declared_baselines"],
            "live": inventory["live"],
            "target_after_spec": inventory["target_after_spec"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# `--contention` 共享文件争用核查（R11.3）
# ═══════════════════════════════════════════════════════════════════════════════


def load_shared_files_from_design() -> dict[str, Any]:
    """从 design.md §边界与禁区 R11.3 行解析十项共享文件清单（单一真源）。"""
    text = DESIGN_MD.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if "R11.3" in ln and _SHARED_LIST_ANCHOR in ln]
    if len(lines) != 1:
        raise SystemExit(
            f"design.md 中 R11.3 + 「{_SHARED_LIST_ANCHOR}」的行命中 {len(lines)} 条"
            "（应恰好 1 条）—— 锚点失效，拒绝按残缺清单出结论"
        )
    tail = lines[0].split(_SHARED_LIST_ANCHOR, 1)[1]
    names = [m.group(1).strip() for m in _BACKTICKED.finditer(tail)]
    names = [n for n in names if n and "/" not in n or n.endswith((".py", ".json", ".ts", ".yml"))]
    if len(names) != 10:
        raise SystemExit(
            f"R11.3 共享文件清单解析出 {len(names)} 项（design 声明十项）: {names}"
        )
    return {
        "source": "design.md §边界与禁区 R11.3 行",
        "anchor": _SHARED_LIST_ANCHOR,
        "names": names,
    }


def resolve_shared_file_paths(names: list[str]) -> dict[str, list[str]]:
    """把清单里的文件名解析到仓库真实路径（rglob 实搜，不写死路径表）。"""
    search_roots = [
        BACKEND / "app",
        BACKEND / "data",
        BACKEND / "scripts",
        BACKEND / "tests",
        ROOT / "audit-platform" / "frontend" / "src",
        ROOT / ".github",
    ]
    out: dict[str, list[str]] = {}
    for name in names:
        hits: list[str] = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob(name):
                if path.is_file():
                    hits.append(path.relative_to(ROOT).as_posix())
        out[name] = sorted(set(hits))
    return out


def discover_active_specs() -> dict[str, Any]:
    """磁盘实扫 active spec（真源）：有 tasks.md 且存在未完成复选框。"""
    active: dict[str, dict[str, Any]] = {}
    shells: list[str] = []
    for spec_dir in sorted(p for p in SPECS_DIR.iterdir() if p.is_dir()):
        tasks = spec_dir / "tasks.md"
        if not tasks.exists():
            shells.append(spec_dir.name)
            continue
        marks = [
            m.group(1)
            for m in (_TASK_BOX_RE.match(ln) for ln in tasks.read_text(encoding="utf-8").splitlines())
            if m
        ]
        unchecked = [m for m in marks if m in _UNCHECKED_MARKS]
        if unchecked and spec_dir.name != SELF_SPEC:
            active[spec_dir.name] = {
                "checkbox_total": len(marks),
                "unchecked": len(unchecked),
                "tasks_mtime": datetime.fromtimestamp(
                    tasks.stat().st_mtime, _CN_TZ
                ).isoformat(timespec="seconds"),
            }
    discovered = sorted(active)
    hint = sorted(_ACTIVE_SPEC_HINT)
    # 🔴 反空转：复选框正则一旦失配，`discovered` 会静默变空 ⇒ 争用核查得出
    # 「无命中」这种假绿。故实扫面为空/异常小即打红，而不是照样出报告。
    all_specs = [p.name for p in SPECS_DIR.iterdir() if p.is_dir()]
    if len(all_specs) < 10 or len(discovered) < 3:
        raise SystemExit(
            f"active spec 实扫面异常（spec 目录 {len(all_specs)} 个 / 实扫 active "
            f"{len(discovered)} 个）—— 复选框正则或目录结构变了，拒绝按空集出争用结论"
        )
    return {
        "criterion": r"有 tasks.md 且存在 `^\s*-\s\[([ x~-])\]` 中标记为 ' ' / '-' / '~' 的行",
        "active": active,
        "discovered": discovered,
        "briefing_hint": hint,
        "hint_only_in_briefing": [s for s in hint if s not in discovered],
        "hint_missing_from_briefing": [s for s in discovered if s not in hint],
        "shell_dirs_without_tasks_md": shells,
    }


_FILENAME_TOKEN = re.compile(r"^[\w./{}-]+\.(?:py|ts|vue|json|ya?ml)$")


def self_spec_change_set_files(exclude: set[str]) -> list[str]:
    """本 spec `tasks.md` 里点名的其他文件（`Change_Set` 的实际作业面）。

    R11.3 的字面清单是十项，但本 spec 的 `Change_Set` 不止这十项（例如
    `l2_interest_payable.py` / `l6_special_payables.py` 落在 active spec
    `l-cycle-…-completion` 的半径内）。故补扫这一层，判据取自**本 spec 自己的
    tasks.md**（作业面真源），不另写第二份文件清单。
    """
    raw = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
    text = _CODE_FENCE.sub("", raw)
    names: set[str] = set()
    for m in _BACKTICKED.finditer(text):
        token = m.group(1).strip()
        base = token.rsplit("/", 1)[-1]
        if _FILENAME_TOKEN.match(base) and base not in exclude and "*" not in base:
            names.add(base)
    # 🔴 反空转：本 spec tasks.md 明确点名了几十个文件（新建守卫、专属 router、
    #    composable…）⇒ 解析出个位数说明 code span 配对错位（围栏反引号那个坑），
    #    此时「补充核查面无命中」是假绿。
    if len(names) < 20:
        raise SystemExit(
            f"本 spec tasks.md 解析出的文件名只有 {len(names)} 个 —— code span 解析"
            "疑似错位（围栏 ``` 会让配对整体偏一格），拒绝按残缺清单出补充核查结论"
        )
    return sorted(names)


def _grep_specs(
    spec_names: list[str], needles: list[str]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    findings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for spec_name in spec_names:
        for doc_name in ("tasks.md", "design.md"):
            doc = SPECS_DIR / spec_name / doc_name
            if not doc.exists():
                continue
            for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for needle in needles:
                    if needle in line:
                        findings.setdefault(needle, {}).setdefault(
                            f"{spec_name}/{doc_name}", []
                        ).append({"line": lineno, "text": line.strip()[:220]})
    return findings


def scan_sibling_sheet_intersection(spec_names: list[str]) -> dict[str, Any]:
    """R11.2 的**sheet 级**交集：别的 active spec 是否在碰同一底稿的非 X-3 sheet。

    文件级 grep 抓不到这一层 —— `l-cycle-…-completion` 从不提 `l2_interest_payable.py`，
    但它在改 `明细表L2-2` / `useL2Disclosure` / L2 披露 Tab，正是 R11.2 点名要保住的
    那些非 X-3 业务表。判据：扫 `{父 wp_code}-{数字}` 且数字 != 3 的 sheet 码。
    """
    surface = load_work_surface()
    parents = surface["parent_wp_codes"]
    per_parent = {
        parent: re.compile(rf"(?<![A-Za-z0-9]){parent}-(\d+)(?![0-9])")
        for parent in parents
    }
    hits: dict[str, dict[str, dict[str, list[int]]]] = {}
    for spec_name in spec_names:
        for doc_name in ("tasks.md", "design.md", "requirements.md"):
            doc = SPECS_DIR / spec_name / doc_name
            if not doc.exists():
                continue
            for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for parent, rx in per_parent.items():
                    for m in rx.finditer(line):
                        if m.group(1) == "3":
                            continue  # X-3 本体属本 spec 作业面，不算「非 X-3 交集」
                        code = f"{parent}-{m.group(1)}"
                        hits.setdefault(parent, {}).setdefault(code, {}).setdefault(
                            f"{spec_name}/{doc_name}", []
                        ).append(lineno)
    return {
        "criterion": (
            r"在其他 active spec 的 tasks/design/requirements.md 里扫 `{父 wp_code}-{数字}`，"
            "数字为 3 的（= X-3 本体）不计"
        ),
        "parents_scanned": parents,
        "by_parent": hits,
        "parents_with_intersection": sorted(hits),
        "note": (
            "有交集 ⇒ R11.2「L2 / L6 非 X-3 业务表逐字节不变」不是形式条款；"
            "本 spec 对这些底稿只许在专属 router 内**追加**形态 A 端点与 IE_SHEETS 常量"
        ),
    }


def scan_contention() -> dict[str, Any]:
    """逐 active spec × 逐共享文件，扫 tasks.md / design.md 的提及（带 文件:行号）。"""
    shared = load_shared_files_from_design()
    resolved = resolve_shared_file_paths(shared["names"])
    specs = discover_active_specs()

    findings = _grep_specs(specs["discovered"], shared["names"])
    extra_names = self_spec_change_set_files(exclude=set(shared["names"]))
    extra_findings = _grep_specs(specs["discovered"], extra_names)
    sheet_level = scan_sibling_sheet_intersection(specs["discovered"])

    return {
        "shared_files": shared,
        "resolved_paths": resolved,
        "active_specs": specs,
        "findings": findings,
        "supplementary_surface": {
            "criterion": "本 spec tasks.md 里反引号包裹的文件名，减去 R11.3 十项",
            "names": extra_names,
            "findings": extra_findings,
            "note": (
                "这一层不属 R11.3 字面清单，但同样会被并发会话回退 —— "
                "命中项在改动前须同样核 mtime 与 git status"
            ),
        },
        "sibling_sheet_intersection": sheet_level,
        "reproduce": {
            "script": SCRIPT_PATH.relative_to(ROOT).as_posix() + " --contention",
            "per_file_grep": (
                'rg -n --fixed-strings "{name}" '
                + " ".join(
                    f".kiro/specs/{s}/tasks.md .kiro/specs/{s}/design.md"
                    for s in specs["discovered"]
                )
            ),
            "note": "把 {name} 换成清单里的文件名即可复算；行号与本文件所记一致",
        },
    }


def render_contention_md(scan: dict[str, Any]) -> str:
    shared = scan["shared_files"]["names"]
    specs = scan["active_specs"]
    findings = scan["findings"]
    lines: list[str] = []
    lines.append("# 共享文件争用核查（R11.3）")
    lines.append("")
    lines.append(f"- spec：`{SELF_SPEC}` · 任务 1.8 · 生成时间 {_now()}")
    lines.append(
        f"- 生成脚本：`{SCRIPT_PATH.relative_to(ROOT).as_posix()} --contention`"
        "（结果可复算，逐条给 文件:行号）"
    )
    lines.append(
        "- 清单真源：`design.md` §边界与禁区 R11.3 行的「"
        f"{scan['shared_files']['anchor']}」，实解析 {len(shared)} 项"
    )
    lines.append("")
    lines.append("## 一、active spec 实扫结果（真源 = 磁盘复选框，非 memory 旧数）")
    lines.append("")
    lines.append(f"判据：{specs['criterion']}")
    lines.append("")
    lines.append("| active spec | 复选框总数 | 未完成 | tasks.md mtime |")
    lines.append("|---|---:|---:|---|")
    for name in specs["discovered"]:
        meta = specs["active"][name]
        lines.append(
            f"| `{name}` | {meta['checkbox_total']} | {meta['unchecked']} | {meta['tasks_mtime']} |"
        )
    lines.append("")
    if specs["hint_only_in_briefing"]:
        lines.append(
            "> ⚠️ 任务简报点名、但实扫**不在** active 集：`"
            + "` · `".join(specs["hint_only_in_briefing"])
            + "`（多半已收口或无未完成复选框）"
        )
    if specs["hint_missing_from_briefing"]:
        lines.append("")
        lines.append(
            "> ⚠️ 实扫为 active、简报未点名：`"
            + "` · `".join(specs["hint_missing_from_briefing"])
            + "` —— 它们也在核查面内"
        )
    lines.append("")
    lines.append("## 二、十项共享文件 × 争用命中")
    lines.append("")
    lines.append("| # | 共享文件 | 仓库路径 | 命中的 active spec 文档 | 命中行数 |")
    lines.append("|---:|---|---|---|---:|")
    for idx, name in enumerate(shared, 1):
        paths = scan["resolved_paths"].get(name) or []
        hits = findings.get(name) or {}
        total = sum(len(v) for v in hits.values())
        docs = "、".join(f"`{k}`" for k in sorted(hits)) if hits else "—"
        path_cell = "<br>".join(f"`{p}`" for p in paths) if paths else "（未解析到）"
        lines.append(f"| {idx} | `{name}` | {path_cell} | {docs} | {total} |")
    lines.append("")
    lines.append("## 三、逐条命中明细（文件:行号 + 原文）")
    lines.append("")
    any_hit = False
    for name in shared:
        hits = findings.get(name) or {}
        if not hits:
            continue
        any_hit = True
        lines.append(f"### `{name}`")
        lines.append("")
        for doc in sorted(hits):
            for hit in hits[doc]:
                lines.append(f"- `.kiro/specs/{doc}:{hit['line']}` — {hit['text']}")
        lines.append("")
    if not any_hit:
        lines.append("（无命中：其他 active spec 的 tasks.md / design.md 均未提及这十项）")
        lines.append("")
    supp = scan.get("supplementary_surface") or {}
    supp_hits = {k: v for k, v in (supp.get("findings") or {}).items() if v}
    lines.append("## 四、补充核查面（本 spec tasks.md 点名、但不在 R11.3 十项内）")
    lines.append("")
    lines.append(f"判据：{supp.get('criterion')}；共 {len(supp.get('names') or [])} 项，命中 {len(supp_hits)} 项。")
    lines.append("")
    if supp_hits:
        lines.append("| 文件 | 命中的 active spec 文档 | 行号 |")
        lines.append("|---|---|---|")
        for name in sorted(supp_hits):
            for doc in sorted(supp_hits[name]):
                nums = ", ".join(str(h["line"]) for h in supp_hits[name][doc])
                lines.append(f"| `{name}` | `.kiro/specs/{doc}` | {nums} |")
    else:
        lines.append("（无命中）")
    lines.append("")
    lines.append(f"> {supp.get('note')}")
    lines.append("")
    sib = scan.get("sibling_sheet_intersection") or {}
    lines.append("## 五、sheet 级交集（R11.2 —— 文件级 grep 抓不到的那一层）")
    lines.append("")
    lines.append(f"判据：{sib.get('criterion')}")
    lines.append("")
    by_parent = sib.get("by_parent") or {}
    if by_parent:
        lines.append("| 父底稿 | 被别的 active spec 提及的非 X-3 sheet | 命中位置（文档:行号） |")
        lines.append("|---|---|---|")
        for parent in sorted(by_parent):
            for code in sorted(by_parent[parent]):
                locs = "；".join(
                    f"`{doc}`:{','.join(str(n) for n in sorted(set(nums))[:6])}"
                    for doc, nums in sorted(by_parent[parent][code].items())
                )
                lines.append(f"| `{parent}` | `{code}` | {locs} |")
    else:
        lines.append("（无 sheet 级交集）")
    lines.append("")
    lines.append(f"> {sib.get('note')}")
    lines.append("")
    lines.append("## 六、处置")
    lines.append("")
    lines.append(
        "- 有命中的文件：本 spec 的破坏性任务（2.1 / 6.1 / 9.1 / 14.2）在改动前**再跑一次本脚本**"
        "并核 mtime；若 mtime 为秒/分钟级说明并发会话正在写，**暂缓改动**。"
    )
    lines.append(
        "- 无命中不等于无风险：并发会话可能改了文件却没在 spec 文档里写。故改动前另查 "
        "`git status --porcelain <file>` 与 mtime，两条都干净才动手。"
    )
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 采集 / 对照
# ═══════════════════════════════════════════════════════════════════════════════


def replay_surface_from_baseline(baseline: dict[str, Any]) -> dict[str, Any]:
    """从已落盘基线里取出**权威探测面** —— 基线当轮真正探过的那些键。

    任务 17.3 的修法主线：`--compare` 的候选 sheet 不再由「adapter 目标模块内首个
    `*_SPECS`」猜（那个猜测在任务 6.1 改指后整体漂了一批键 ⇒ 26 条 hard `MISSING` 假红），
    而是重放基线记下的 (短前缀, sheet) 与 (长前缀, 后缀, sheet 实参) 三元组。

    `<handler-default>` 是「不给 `sheet` 实参」的键名 ⇒ 还原成 `None`
    （= HTTP 省略 `?sheet=` 的真值，配合 `_call_shape_b_endpoint` 的显式 `sheet=None`）。

    🔴 这不是放宽口径：每个基线键仍逐条比 `stable_digest`（同一个 `artifact_fingerprint`），
    `DIGEST_MISMATCH` / `BROKEN` / `ERROR_CLASS_CHANGED` 的判法一字未动；连 `MISSING` 也仍然
    承重 —— 端点整条消失、或 sheet 实参喂不进去时，那个键照样探不到、照样报 `MISSING`。
    去掉的只有「本轮压根没试过这个键」这一种无信息量的 MISSING。
    """
    exports = baseline.get("snapshot_1_export_artifacts") or {}
    factory: dict[str, list[str]] = {}
    for short, node in (exports.get("factory_adapter_path") or {}).items():
        factory[short] = sorted((node.get("sheets") or {}).keys())
    shape_b: dict[str, dict[str, list[str | None]]] = {}
    for long_prefix, node in (exports.get("shape_b_host_path") or {}).items():
        per_suffix: dict[str, list[str | None]] = {}
        for suffix, block in (node.get("probed") or {}).items():
            keys = list((block.get("by_sheet") or {}).keys())
            if not keys:
                continue
            per_suffix[suffix] = [
                None if k == _HANDLER_DEFAULT_KEY else k for k in sorted(keys)
            ]
        if per_suffix:
            shape_b[long_prefix] = per_suffix
    # 反空转：基线结构一变（或读错文件）就会解析成空/残缺，此时「零差异」是假绿
    if len(factory) != 16 or len(shape_b) != 16:
        raise SystemExit(
            f"基线探测面解析异常：factory {len(factory)} 个短前缀 / shape_b "
            f"{len(shape_b)} 个长前缀（各应 16）—— 拒绝按残缺重放面出对照结论"
        )
    return {
        "source": "baseline_snapshot_x3.json 的 snapshot_1_export_artifacts 逐键",
        "handler_default_key": _HANDLER_DEFAULT_KEY,
        "factory": factory,
        "shape_b": shape_b,
        "pair_count": sum(len(v) for v in factory.values()) * len(_ALLOWED_SUFFIXES)
        + sum(len(a) for b in shape_b.values() for a in b.values()),
    }


def collect_all(
    *,
    run_ci: bool,
    reuse_wp_ids: dict[str, str] | None = None,
    replay_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    head_swap = assert_no_head_swap(SCRIPT_PATH)
    volatile = selfcheck_volatile_members()

    surface = load_work_surface()
    from app.main import app

    factory = factory_specs_by_short_prefix(
        list(surface["long_by_short"]), surface["code_by_short"]
    )
    shape_b = shape_b_endpoints(app, surface["long_prefixes"])

    exports = asyncio.run(
        collect_export_snapshot(
            surface,
            factory,
            shape_b,
            reuse_wp_ids=reuse_wp_ids,
            replay_surface=replay_surface,
        )
    )
    inventory = collect_route_inventory(app)
    adapter = collect_adapter_registry(surface)
    ci = collect_ci_red_jobs(run_probe=run_ci)

    # shape_b 里存了 endpoint 对象（不可序列化）⇒ 落盘前剔掉
    shape_b_serializable = {
        lp: {k: v for k, v in node.items() if k != "endpoints"}
        for lp, node in shape_b.items()
    }

    return {
        "_meta": {
            "spec": SELF_SPEC,
            "task": "1.8",
            "requirement": "1.1~1.7, 10.9, 11.3",
            "written_at": _now(),
            "generated_by": SCRIPT_PATH.relative_to(ROOT).as_posix() + " --snapshot",
            "three_step_method": "当前态快照 → 施加改动 → 对照（R10.9；HEAD-swap 禁用）",
            "read_only_boundary": {
                "invoked_suffixes": list(_ALLOWED_SUFFIXES),
                "never_invoked": [_IMPORT_SUFFIX],
                "wp_templates_touched": False,
            },
        },
        "selfchecks": {"head_swap": head_swap, "volatile_zip_members": volatile},
        "work_surface": surface,
        "factory_modules": factory,
        "shape_b_endpoints": shape_b_serializable,
        "snapshot_1_export_artifacts": exports,
        "snapshot_2_route_inventory": inventory,
        "snapshot_3_adapter_registry": adapter,
        "snapshot_ci_red_jobs": ci,
    }


def _walk_export_leaves(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把快照①摊平成 {可比键: 结果}，便于逐项对照。"""
    flat: dict[str, dict[str, Any]] = {}
    for short, node in (snap.get("factory_adapter_path") or {}).items():
        for sheet, leaf in (node.get("sheets") or {}).items():
            for action, res in (leaf.get("actions") or {}).items():
                flat[f"factory/{short}/{sheet}/{action}"] = {
                    "result": res,
                    "scope": leaf.get("zero_regression_scope"),
                    "is_x3": leaf.get("is_x3_work_surface"),
                }
    for long_prefix, node in (snap.get("shape_b_host_path") or {}).items():
        for action, block in (node.get("probed") or {}).items():
            for sheet, res in (block.get("by_sheet") or {}).items():
                flat[f"shapeB/{long_prefix}/{sheet}/{action}"] = {
                    "result": res,
                    "scope": block.get("zero_regression_scope"),
                    "is_x3": False,
                }
    return flat


def compare(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """三类快照 + CI 两列逐项对照。判据落在数据上，退出码只作提示。"""
    report: dict[str, Any] = {
        "_meta": {
            "spec": SELF_SPEC,
            "task": "1.8（--compare，由任务 15.3 消费）",
            "compared_at": _now(),
            "baseline_written_at": (baseline.get("_meta") or {}).get("written_at"),
        },
        "snapshot_1": {},
        "snapshot_2": {},
        "snapshot_3": {},
        "ci_red_jobs": {},
        "verdict": "UNKNOWN",
    }

    # ── ① 导出产物 ────────────────────────────────────────────────────────────
    base_flat = _walk_export_leaves(baseline.get("snapshot_1_export_artifacts") or {})
    cur_flat = _walk_export_leaves(current.get("snapshot_1_export_artifacts") or {})
    per_key: dict[str, Any] = {}
    for key in sorted(set(base_flat) | set(cur_flat)):
        b, c = base_flat.get(key), cur_flat.get(key)
        if b is None:
            per_key[key] = {"state": "NEW", "scope": c["scope"]}
            continue
        if c is None:
            per_key[key] = {"state": "MISSING", "scope": b["scope"]}
            continue
        bd, cd = b["result"].get("stable_digest"), c["result"].get("stable_digest")
        bok, cok = b["result"].get("ok"), c["result"].get("ok")
        be, ce = b["result"].get("error_class"), c["result"].get("error_class")
        if bok != cok:
            # 从失败转成功不是回归（是修好了）；从成功转失败才是
            state = "FIXED" if cok else "BROKEN"
        elif bok:
            state = "SAME" if bd == cd else "DIGEST_MISMATCH"
        else:
            # 两侧都失败 ⇒ 失败必须是**同一类**存量缺陷，换了异常类型说明性质变了
            state = "SAME_FAILURE" if be == ce else "ERROR_CLASS_CHANGED"
        per_key[key] = {
            "state": state,
            "scope": b["scope"],
            "is_x3": b.get("is_x3"),
            "baseline": {
                "ok": bok, "stable_digest": bd,
                "error_class": be, "error": b["result"].get("error"),
            },
            "current": {
                "ok": cok, "stable_digest": cd,
                "error_class": ce, "error": c["result"].get("error"),
            },
        }
    _REGRESSION_STATES = ("DIGEST_MISMATCH", "BROKEN", "ERROR_CLASS_CHANGED", "MISSING")
    hard = [
        k
        for k, v in per_key.items()
        if str(v.get("scope") or "").startswith("must_be_stable")
        and v["state"] in _REGRESSION_STATES
    ]

    def _scope_bucket(scope: str) -> str:
        for name in ("must_be_stable", "work_surface", "informational"):
            if str(scope or "").startswith(name):
                return name
        return "unscoped"

    by_scope: dict[str, dict[str, int]] = {}
    for value in per_key.values():
        bucket = by_scope.setdefault(_scope_bucket(value.get("scope") or ""), {})
        bucket[value["state"]] = bucket.get(value["state"], 0) + 1
    report["snapshot_1"] = {
        "compared": len(per_key),
        "probe_surface_mode": {
            "baseline": (baseline.get("snapshot_1_export_artifacts") or {}).get(
                "probe_surface_mode"
            ),
            "current": (current.get("snapshot_1_export_artifacts") or {}).get(
                "probe_surface_mode"
            ),
        },
        "replay_coverage": (current.get("snapshot_1_export_artifacts") or {}).get(
            "replay_coverage"
        ),
        "by_key": per_key,
        "state_counts": {
            s: sum(1 for v in per_key.values() if v["state"] == s)
            for s in sorted({v["state"] for v in per_key.values()})
        },
        # 🔴 判据面就是 `must_be_stable` 那一桶 —— 全局计数把「本 spec 有意重建的 X-3
        #    产物」（`work_surface`）和「短前缀本来就不可达的非 X-3」（`informational`）
        #    混在一起读，会把设计内的变化误读成回归。分桶只是**把同一批数据摊开**，
        #    hard 的判法（下面 `hard`）一字未动。
        "state_counts_by_scope": {k: dict(sorted(v.items())) for k, v in sorted(by_scope.items())},
        "hard_regressions": hard,
        "note": (
            "`informational` 作用域的差异不判回归（那些 sheet 在 catalog 零启用、"
            "bulk 改指前后都不取数）；判回归只看 `must_be_stable` 作用域"
        ),
    }

    # ── 候选 sheet 派生面的漂移（只登记、不判回归）──────────────────────────
    # 重放驱动探测面之后，「本轮派生出的候选」不再影响判读 ⇒ 但它是否漂了仍要看得见，
    # 否则下一轮重新出基线时会悄悄换一批键。此处逐前缀对差，纯登记。
    drift: dict[str, Any] = {}
    b_shape_b = (baseline.get("snapshot_1_export_artifacts") or {}).get("shape_b_host_path") or {}
    c_shape_b = (current.get("snapshot_1_export_artifacts") or {}).get("shape_b_host_path") or {}
    for long_prefix in sorted(set(b_shape_b) | set(c_shape_b)):
        before = sorted((b_shape_b.get(long_prefix) or {}).get("non_x3_candidates") or [])
        after = sorted((c_shape_b.get(long_prefix) or {}).get("non_x3_candidates") or [])
        if before != after:
            drift[long_prefix] = {
                "baseline_derived": before,
                "current_derived": after,
                "only_in_baseline": [c for c in before if c not in after],
                "only_in_current": [c for c in after if c not in before],
            }
    report["candidate_surface_drift"] = {
        "criterion": "两侧**派生**出的非 X-3 候选 sheet 逐前缀对差（探测面本身按基线键重放）",
        "judged": False,
        "prefixes_with_drift": sorted(drift),
        "detail": drift,
        "note": (
            "派生面变化不判回归（R1.6 判的是产物字节，不是脚本的候选推导）；"
            "但下一轮重出基线前须先看这一块，免得静默换一批键"
        ),
    }

    # ── ② 台账基线 ────────────────────────────────────────────────────────────
    b_inv = (baseline.get("snapshot_2_route_inventory") or {})
    c_inv = (current.get("snapshot_2_route_inventory") or {})
    live_diff: dict[str, Any] = {}
    for key, target in (b_inv.get("target_after_spec") or {}).items():
        before, after = (b_inv.get("live") or {}).get(key), (c_inv.get("live") or {}).get(key)
        live_diff[key] = {
            "baseline_live": before,
            "current_live": after,
            "target_after_spec": target,
            "reached_target": after == target,
            "unchanged": after == before,
        }
    report["snapshot_2"] = {
        "declared_baselines_changed": {
            k: {"baseline": v, "current": (c_inv.get("declared_baselines") or {}).get(k)}
            for k, v in (b_inv.get("declared_baselines") or {}).items()
            if (c_inv.get("declared_baselines") or {}).get(k) != v
        },
        "live": live_diff,
        "note": (
            "施加完 Wave 3 后 `reached_target` 应全 True；Wave 0 阶段应全 `unchanged=True`"
        ),
    }

    # ── ③ adapter 注册表 ─────────────────────────────────────────────────────
    b_ad, c_ad = baseline.get("snapshot_3_adapter_registry") or {}, current.get(
        "snapshot_3_adapter_registry"
    ) or {}
    b_keys, c_keys = set(b_ad.get("keys") or []), set(c_ad.get("keys") or [])
    changed = {
        k: {
            "baseline": (b_ad.get("by_key") or {}).get(k, {}).get("target_module"),
            "current": (c_ad.get("by_key") or {}).get(k, {}).get("target_module"),
            "expected_after_spec": (b_ad.get("x3_targets_after_spec") or {}).get(k),
            "is_x3_short_prefix": k in set(b_ad.get("x3_short_prefixes") or []),
        }
        for k in sorted(b_keys & c_keys)
        if (b_ad.get("by_key") or {}).get(k, {}).get("target_module")
        != (c_ad.get("by_key") or {}).get(k, {}).get("target_module")
    }
    report["snapshot_3"] = {
        "key_count": {"baseline": len(b_keys), "current": len(c_keys)},
        "keys_added": sorted(c_keys - b_keys),
        "keys_removed": sorted(b_keys - c_keys),
        "target_module_changed": changed,
        "unexpected_changes": {
            k: v for k, v in changed.items() if not v["is_x3_short_prefix"]
        },
        "note": "键集应恒定；只有 16 个 X-3 短前缀的 target_module 允许变（任务 6.1）",
    }

    # ── CI 两列 ──────────────────────────────────────────────────────────────
    b_ci, c_ci = (baseline.get("snapshot_ci_red_jobs") or {}).get("jobs") or {}, (
        current.get("snapshot_ci_red_jobs") or {}
    ).get("jobs") or {}
    ci_rows: dict[str, Any] = {}
    for job in sorted(set(b_ci) | set(c_ci)):
        b, c = b_ci.get(job) or {}, c_ci.get(job) or {}
        bd, cd = b.get("drift") or {}, c.get("drift") or {}
        b_count = bd.get("differing_entry_count", bd.get("counted_marker_lines"))
        c_count = cd.get("differing_entry_count", cd.get("counted_marker_lines"))
        ci_rows[job] = {
            "exit_code": {"baseline": b.get("observed_exit_code"), "current": c.get("observed_exit_code")},
            "drift_entries": {"baseline": b_count, "current": c_count},
            "increased": (
                None if b_count is None or c_count is None else c_count > b_count
            ),
        }
    ci_skipped = bool(
        (current.get("snapshot_ci_red_jobs") or {}).get("skipped")
    ) or any(v["exit_code"]["current"] is None for v in ci_rows.values())
    report["ci_red_jobs"] = {
        "duty": "裁决 2：本 spec 不修红，但红的规模不得变大",
        "probe_skipped": ci_skipped,
        "probe_skipped_note": (
            "本次未真跑 CI（--no-ci-probe）⇒ `increased=None` 表示**未核**，"
            "不等于「未增加」；任务 15.3 的正式对照必须不带 --no-ci-probe"
            if ci_skipped
            else None
        ),
        "jobs": ci_rows,
        "increased_jobs": [j for j, v in ci_rows.items() if v["increased"]],
    }

    regressions = (
        report["snapshot_1"]["hard_regressions"]
        + sorted(report["snapshot_3"]["unexpected_changes"])
        + report["ci_red_jobs"]["increased_jobs"]
        + sorted(report["snapshot_3"]["keys_added"] + report["snapshot_3"]["keys_removed"])
    )
    report["verdict"] = "ZERO_REGRESSION" if not regressions else "REGRESSION_DETECTED"
    report["regressions"] = regressions
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _summarize(snapshot: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    exports = snapshot["snapshot_1_export_artifacts"]
    flat = _walk_export_leaves(exports)
    ok = sum(1 for v in flat.values() if v["result"].get("ok"))
    no_obj = sum(1 for v in flat.values() if v["result"].get("status") == "no_usable_object")
    lines.append(
        f"快照① 导出产物：{len(flat)} 项（成功 {ok} / 失败 {len(flat) - ok - no_obj} / 无可用对象 {no_obj}）"
    )
    db = exports["db"]
    lines.append(
        f"  真实底稿对象：available={db['available']} · 取到 {len(db['wp_ids'])}/16 · 缺 {db['missing']}"
        + (f" · error={db['error']}" if db.get("error") else "")
    )
    inv = snapshot["snapshot_2_route_inventory"]
    lines.append(
        f"快照② 台账：{len(inv['declared_baselines'])} 个声明基线 · 实测 groups={inv['live']['groups']}"
        f" / 三态路由={inv['live']['three_state_routes']} / 形态A={inv['live']['shape_a_prefixes']}"
        f" ⇒ 目标 groups={inv['target_after_spec']['groups']}"
        f" / 三态路由={inv['target_after_spec']['three_state_routes']}"
    )
    ad = snapshot["snapshot_3_adapter_registry"]
    lines.append(
        f"快照③ adapter：{ad['key_count']} 键 · 其中 X-3 短前缀 {len(ad['x3_short_prefixes'])} 个今天指向工厂模块"
    )
    ci = snapshot["snapshot_ci_red_jobs"].get("jobs") or {}
    for job, node in ci.items():
        drift = node.get("drift") or {}
        count = drift.get("differing_entry_count", drift.get("counted_marker_lines"))
        lines.append(
            f"CI 两列 `{job}`：exit={node.get('observed_exit_code')} · drift 条目数={count}"
        )
    if not ci:
        lines.append("CI 两列：已跳过（--no-ci-probe）")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="x3 零回归基线快照与共享文件争用核查（任务 1.8）"
    )
    parser.add_argument("--snapshot", action="store_true", help="采集三类快照并落盘")
    parser.add_argument("--compare", action="store_true", help="重采一次并与基线对照")
    parser.add_argument("--contention", action="store_true", help="共享文件争用核查")
    parser.add_argument(
        "--no-ci-probe", action="store_true", help="跳过两个 CI 脚本的真跑（快速模式）"
    )
    parser.add_argument(
        "--out-compare", type=str, default=None, help="把 --compare 结果另存到该路径"
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not (args.snapshot or args.compare or args.contention):
        parser.error("至少给一个模式：--snapshot / --compare / --contention")

    exit_code = 0

    if args.contention:
        scan = scan_contention()
        CONTENTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTENTION_PATH.write_text(render_contention_md(scan), encoding="utf-8")
        _write_json(EVIDENCE_DIR / "shared_file_contention.json", scan)
        if not args.quiet:
            total = sum(len(v) for hits in scan["findings"].values() for v in hits.values())
            print(
                f"[contention] active spec {len(scan['active_specs']['discovered'])} 个 · "
                f"十项共享文件命中 {len(scan['findings'])} 项 / {total} 行 → "
                f"{CONTENTION_PATH.relative_to(ROOT).as_posix()}"
            )

    if args.snapshot:
        snapshot = collect_all(run_ci=not args.no_ci_probe)
        # 🔴 先把两份产物都算出来再写盘：任何一步抛异常都不留「半更新」的 evidence
        #    （首版把 `_write_json(SNAPSHOT_PATH)` 放在 build_route_matrix 之前，
        #     变异检验时 design 锚点一坏就只更新了其中一份，两份产物不同源）。
        matrix = build_route_matrix(
            snapshot["work_surface"],
            snapshot["shape_b_endpoints"],
            snapshot["snapshot_3_adapter_registry"],
            snapshot["snapshot_2_route_inventory"],
        )
        _write_json(SNAPSHOT_PATH, snapshot)
        _write_json(MATRIX_PATH, matrix)
        if not args.quiet:
            for line in _summarize(snapshot):
                print(line)
            print(f"→ {SNAPSHOT_PATH.relative_to(ROOT).as_posix()}")
            print(f"→ {MATRIX_PATH.relative_to(ROOT).as_posix()}")
        db = snapshot["snapshot_1_export_artifacts"]["db"]
        if not db["available"] or db["missing"]:
            exit_code = max(exit_code, 2)

    if args.compare:
        if not SNAPSHOT_PATH.exists():
            print(
                f"[compare] 缺基线 {SNAPSHOT_PATH.relative_to(ROOT).as_posix()} —— 先跑 --snapshot",
                file=sys.stderr,
            )
            return 2
        baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        reuse = ((baseline.get("snapshot_1_export_artifacts") or {}).get("db") or {}).get(
            "wp_ids"
        ) or {}
        # 探测面按**基线记下的键**重放（任务 17.3）——「模块内首个 `*_SPECS`」那条
        # 位置性猜测在任务 6.1 改指后会整体换一批键，令 26 条基线键恒报 MISSING（假红）。
        replay = replay_surface_from_baseline(baseline)
        current = collect_all(
            run_ci=not args.no_ci_probe, reuse_wp_ids=reuse, replay_surface=replay
        )
        result = compare(current, baseline)
        out_path = Path(args.out_compare) if args.out_compare else EVIDENCE_DIR / "zero_regression_compare_x3.json"
        _write_json(out_path if out_path.is_absolute() else ROOT / out_path, result)
        if not args.quiet:
            print(f"[compare] verdict={result['verdict']}")
            print(f"  ① {result['snapshot_1']['state_counts']}")
            for bucket, counts in result["snapshot_1"]["state_counts_by_scope"].items():
                print(f"     ├ {bucket}: {counts}")
            cov = result["snapshot_1"].get("replay_coverage") or {}
            print(
                f"     └ 重放覆盖 {cov.get('probed')}/{cov.get('requested')}"
                f" verdict={cov.get('verdict')} 未探到={cov.get('unprobed_keys')}"
            )
            print(f"  ③ 键集 {result['snapshot_3']['key_count']}")
            for job, node in result["ci_red_jobs"]["jobs"].items():
                print(f"  CI `{job}` exit={node['exit_code']} drift={node['drift_entries']}")
            if result["regressions"]:
                print(f"  回归项: {result['regressions']}")
        if result["verdict"] != "ZERO_REGRESSION":
            exit_code = max(exit_code, 3)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
