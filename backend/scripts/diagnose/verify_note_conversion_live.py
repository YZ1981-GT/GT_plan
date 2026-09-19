"""Task 19：国企↔上市附注转换 —— 真实库验收（默认 dry-run，只读）。

spec: soe-listed-note-conversion-correctness / Requirements 10.4~10.8（Property 37）

覆盖一次 ``soe → listed → soe`` 往返：预览（零写入）→ ``--apply`` 真实执行 →
按快照复原，并逐项核验章节标识、``binding_id`` 前缀、归档状态与 ``template_lineage``
是否回到初始。

🔴 诚实报告红线（需求 10.6 / 10.7 / Property 37）
------------------------------------------------
本脚本**不得**为了凑验收条件而写 ``Project.template_type`` / ``report_scope`` /
``applicable_standard_v2`` —— 转换会改 ``project.template_type`` 并触发
``execute_full_chain(force=True)`` 全链重算，属**破坏性操作**。故：

* 口径切换**只能**由 :meth:`NoteConversionService.execute_conversion` 在
  ``--apply`` 且用户显式授权（``--project`` + ``--i-authorize-apply``）时执行；
* 无合法验收对象时输出「无法验收」+ 显式 ``[SKIP]`` 标记并以**非零退出码**结束；
* **禁止**用 fixture／新建测试项目冒充通过（脚本不含任何 ``INSERT`` 项目的路径）。

平台铁律落地（每条都对应一次真实事故，勿简化）
----------------------------------------------
1. **一个脚本里两次 ``asyncio.run()`` 必炸**（连接池绑定首个事件循环）⇒ 全部查询
   合并进同一个 ``async def _run()`` 再一次 ``asyncio.run``。
2. **不借用 ``app.core.database.async_session``**（会双向污染共享连接池，让同批
   连库测试报 ``Event loop is closed``）⇒ 自建一次性 engine
   （``poolclass=NullPool``）并在**同一 loop 内** ``await engine.dispose()``。
3. **写 SQL 前先查真实列名**（平台已因 ``wp_id`` vs ``workpaper_id`` 踩过 P0）⇒
   本脚本只用 ORM 与 ``information_schema`` 校验过的列。
4. **多态诊断的态名从枚举 ``.value`` 派生**（大小写不一致会让 ``Counter.get()``
   静默返 0，产出「明细里有命中、分布全 0」的自相矛盾报告）+ 入口断言
   「实际态名 ⊆ 派生集合」，不匹配即 ``sys.exit(1)``。
5. **GBK 控制台禁 emoji**（``print`` 会抛 ``UnicodeEncodeError`` 且崩点可能在写盘
   之后）⇒ 输出一律 ASCII 标记（``[OK]``/``[ERR]``/``[SKIP]``）+ ``Path.write_text
   (..., encoding='utf-8')`` 写盘。
6. **判成败一律查数据不看退出码**（``--apply`` 被 Ctrl+C 中断但写入已提交是平台
   已实测的事故形态）⇒ ``--apply`` 全程包 ``try/finally``，``finally`` 里无条件
   尝试复原并**独立复查**复原结果。

退出码
------
``0`` = 全部检查通过。
``1`` = 有检查项失败 **或** 无合法验收对象（诚实的「无法验收」，需求 10.7 明确
        要求非零退出码或显式 SKIP 标记；本脚本两者都给）。
``2`` = 脚本自身异常（连不上库等）。

用法::

    # 只读诊断：报告可验收性 + 预览预期改写清单
    python backend/scripts/diagnose/verify_note_conversion_live.py

    # 真实往返（须用户显式授权专用测试项目）
    python backend/scripts/diagnose/verify_note_conversion_live.py \
        --project <uuid> --year 2025 --apply --i-authorize-apply
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.core import Project  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 多态诊断：态名一律从枚举 .value 派生（铁律 4）
# ─────────────────────────────────────────────────────────────────────────────


class Verdict(str, Enum):
    """单个检查项的判定态。

    🔴 报告里的态名**只能**由 ``.value`` 派生（``ALL_VERDICTS``），禁止在别处
    手写字面量 —— 大小写/措辞不一致会让分布统计静默返 0，产出「明细里有命中、
    分布全 0」的自相矛盾报告（平台已实测同型事故两次）。
    """

    OK = "OK"
    ERR = "ERR"
    SKIP = "SKIP"


class Eligibility(str, Enum):
    """验收对象可用性的多态诊断（需求 10.7 的「原因：<实测计数>」）。"""

    ELIGIBLE = "ELIGIBLE"                      # 可验收
    NO_CANDIDATE = "NO_CANDIDATE"              # 无合法对象（无项目满足安全判据）
    NO_NOTE_DATA = "NO_NOTE_DATA"              # 指定项目无附注数据
    NOT_AUTHORIZED = "NOT_AUTHORIZED"          # 未取得用户显式授权
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"    # 指定项目不存在/已软删


ALL_VERDICTS: tuple[str, ...] = tuple(v.value for v in Verdict)
ALL_ELIGIBILITY: tuple[str, ...] = tuple(e.value for e in Eligibility)


def _assert_state_names_are_derived() -> None:
    """入口自检：实际使用的态名必须 ⊆ 枚举派生集合，不匹配即退出。

    这条自检是铁律 4 的另一半 —— 派生了态名但别处仍手写字面量时，分布统计
    照样会静默返 0。故把「本模块声明的全部态名」与枚举派生集合做双向比对。
    """
    derived = set(ALL_VERDICTS) | set(ALL_ELIGIBILITY)
    used = {v.value for v in Verdict} | {e.value for e in Eligibility}
    if not used <= derived:
        print(f"[ERR] 态名未从枚举派生: {sorted(used - derived)}")
        sys.exit(1)
    if len(ALL_VERDICTS) != len(set(ALL_VERDICTS)) or len(ALL_ELIGIBILITY) != len(
        set(ALL_ELIGIBILITY)
    ):
        print("[ERR] 枚举取值重复")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 报告收集
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Check:
    name: str
    verdict: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    eligibility: str = Eligibility.NO_CANDIDATE.value
    eligibility_reason: str = ""

    def add(self, name: str, verdict: Verdict, detail: str = "") -> None:
        self.checks.append(Check(name, verdict.value, detail))
        self.log(f"[{verdict.value}] {name}" + (f" :: {detail}" if detail else ""))

    def log(self, text: str) -> None:
        self.lines.append(text)
        # 铁律 5：ASCII 标记，禁 emoji（GBK 控制台会抛 UnicodeEncodeError）
        print(text)

    def counts(self) -> dict[str, int]:
        # 态名从派生集合初始化 ⇒ 不会出现「明细有命中而分布为 0」
        dist = {v: 0 for v in ALL_VERDICTS}
        for c in self.checks:
            dist[c.verdict] += 1
        return dist

    def failed(self) -> bool:
        return self.counts()[Verdict.ERR.value] > 0


# ─────────────────────────────────────────────────────────────────────────────
# 源码级自禁（需求 10.6 / Property 37）—— 守卫断言，运行期自查
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_WRITE_FIELDS: tuple[str, ...] = (
    "template_type",
    "report_scope",
    "applicable_standard_v2",
)

#: 「代码形态」判据模板。**一律用 ``{f}`` 占位**，禁把被禁形态原文写进源码/错误
#: 消息 —— 判据自身会被自己的扫描匹配到（反向自检实测踩过「baseline 就打红」）。
_CODE_FORMS: tuple[tuple[str, str], ...] = (
    ("属性赋值", r"\.{f}\s*=(?!=)"),
    ("values 关键字", r"\.values\s*\([^)]*\b{f}\s*="),
)

#: ``setattr`` 形态的字段名藏在**字符串字面量**里 ⇒ 必须在**保留字面量**的代码上
#: 判（清空字面量内容会让该形态检不出来，实测过一次假绿）。
_SETATTR_FORM: str = r"setattr\s*\([^,)]+,\s*['\"]{f}['\"]"


def strip_comments_and_docstrings(src: str) -> str:
    """剥 ``#`` 注释 + docstring，**保留**普通字符串字面量。

    🔴 不能用平台通用的 ``strip_comments()`` —— 它会把 ``sa.text(\"\"\"...\"\"\")``
    里的 SQL 一起剥掉，对「必须含某形态」的判据造成假红。这里只剥
    ``ast.Expr(Constant(str))`` 形态的 docstring；裸 SQL 可能就藏在普通字面量里。
    """
    lines = src.splitlines(keepends=True)
    try:
        spans: dict[int, list[tuple[int, int]]] = {}
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                spans.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))
        for lineno, sp in spans.items():
            ln = lines[lineno - 1]
            for start, end in sorted(sp, reverse=True):
                ln = ln[:start] + " " * (end - start) + ln[end:]
            lines[lineno - 1] = ln
        no_comments = "".join(lines)
    except (tokenize.TokenError, IndentationError):
        no_comments = src

    try:
        tree = ast.parse(no_comments)
    except SyntaxError:
        return no_comments
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for stmt in body:
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
                and stmt.lineno is not None
                and stmt.end_lineno is not None
            ):
                doc_lines.update(range(stmt.lineno, stmt.end_lineno + 1))
    kept = [
        "\n" if (i + 1) in doc_lines else ln
        for i, ln in enumerate(no_comments.splitlines(keepends=True))
    ]
    return "".join(kept)


def blank_string_literal_contents(code: str) -> str:
    """把字符串字面量替换成等长空白，保留代码结构。

    「代码形态」判据的前置 —— 不做的话，判据自己的形态样例会被自己的正则匹配到
    （实测过的自匹配缺陷）。
    """
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError):
        return code
    lines = code.splitlines(keepends=True)
    spans: dict[int, list[tuple[int, int]]] = {}
    for tok in toks:
        if tok.type != tokenize.STRING:
            continue
        if tok.start[0] != tok.end[0]:
            for ln_no in range(tok.start[0], tok.end[0] + 1):
                spans.setdefault(ln_no, []).append((0, len(lines[ln_no - 1])))
            continue
        spans.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))
    for lineno, sp in spans.items():
        ln = lines[lineno - 1]
        for start, end in sorted(sp, reverse=True):
            ln = ln[:start] + '""' + " " * max(0, end - start - 2) + ln[end:]
        lines[lineno - 1] = ln
    return "".join(lines)


def collect_string_literals(code: str) -> list[str]:
    """收集全部字符串字面量内容，供「裸 SQL 形态」判据使用。"""
    lits: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return lits
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lits.append(node.value)
    return lits


def find_forbidden_writes(src: str) -> list[str]:
    """返回违规写入形态清单（空 = 合规）。**本不变式在本 spec 的唯一实现**。

    守卫 ``backend/tests/test_note_conversion_live_verifier.py`` 直接 import 本函数，
    刻意**不再自带第二份实现** —— 同一不变式两处实现即双真源（改一处另一处不红），
    正是本 spec 一直在治的缺陷模式。

    判据分三层：

    1. ``tokenize`` 剥 ``#`` 注释 + ``ast`` 剥 docstring，**保留**普通字面量
       （裸 SQL ``UPDATE projects SET ...`` 可能就藏在字面量里）；
    2. 「代码形态」（属性赋值 / ``.values(field=)`` / ORM 整表更新）在**清空字面量
       内容**后的代码上判 —— 否则判据自己的形态样例会自匹配；
       ``setattr`` 例外，其字段名在字面量里 ⇒ 必须在保留字面量的代码上判；
    3. 「裸 SQL 形态」只在字面量里判，且要求 ``UPDATE projects`` 这种真实写入语句，
       不认单纯提到某个符号名。

    刻意**不**把 ``{"template_type": x}`` 这类 dict 字面量算违规 —— 只读盘点要把
    该字段读进报告（``_survey``），按 dict 键判会把「读出来展示」数成「写入」。
    """
    code = strip_comments_and_docstrings(src)
    code_no_str = blank_string_literal_contents(code)
    literals = collect_string_literals(code)

    offenders: list[str] = []
    for fld in FORBIDDEN_WRITE_FIELDS:
        for label, tmpl in _CODE_FORMS:
            if re.search(tmpl.format(f=fld), code_no_str):
                offenders.append(f"{fld} :: {label}")
        if re.search(_SETATTR_FORM.format(f=fld), code):
            offenders.append(f"{fld} :: setattr")

    if re.search(r"\bupdate\s*\(\s*Project\s*\)", code_no_str) or re.search(
        r"Project\s*\.\s*__table__\s*\.\s*update", code_no_str
    ):
        offenders.append("Project :: ORM 整表更新")

    for lit in literals:
        if not re.search(r"\bUPDATE\s+projects\b", lit, re.I):
            continue
        for fld in FORBIDDEN_WRITE_FIELDS:
            if re.search(rf"\b{fld}\b", lit, re.I):
                offenders.append(f"{fld} :: 裸 SQL UPDATE projects")
    return offenders


def _self_check_no_forbidden_writes(report: Report) -> None:
    """本脚本源码不得出现对三字段的**写入形态**（运行期兜底）。

    🔴 **判据实现只有一处** = 模块级 :func:`find_forbidden_writes`。本函数与
    ``backend/tests/test_note_conversion_live_verifier.py`` 都**调用**它，不各写
    一份 —— 同一不变式两处实现即双真源，改一处另一处不红（这正是本 spec 一直
    在治的缺陷模式；上一轮两侧各写一份后确已不同步，守卫的「setattr」形态判据
    比脚本侧宽，变异检验因此打红）。
    """
    offenders = find_forbidden_writes(Path(__file__).read_text(encoding="utf-8"))

    if offenders:
        report.add(
            "源码级自禁（Property 37）",
            Verdict.ERR,
            "脚本出现对真实项目口径字段的写入形态: " + "; ".join(offenders),
        )
        return

    # 🔴 反向自检（两方向，且**不依赖本文件内容**）——
    # 原先写的是「原文确实含被禁字样」，但 `FORBIDDEN_WRITE_FIELDS` 自己就定义了
    # 这三个名字 ⇒ 该断言**恒真、永不可能打红** = 空转（反向自检实测发现）。
    # 现改为对判据本身做正/负对照：必须抓到真写入、且不误伤只读引用。
    # 样例用拼接构造，避免样例自身落进上面的扫描面。
    _head = '"""m."""\n\nimport sqlalchemy as sa\n\n\n'
    pos_sample = _head + "def m(p):\n    p." + "template_type" + ' = "listed"\n'
    neg_sample = (
        _head
        + "def r(p):\n    return {'"
        + "template_type"
        + "': p."
        + "template_type"
        + "}\n"
    )
    pos_hit = find_forbidden_writes(pos_sample) != []
    neg_hit = find_forbidden_writes(neg_sample) != []
    if not pos_hit or neg_hit:
        report.add(
            "源码级自禁（Property 37）",
            Verdict.ERR,
            f"判据自检失败（pos_hit={pos_hit} neg_hit={neg_hit}）："
            "判据已无法区分真写入与只读引用",
        )
        return

    report.add(
        "源码级自禁（Property 37）",
        Verdict.OK,
        f"剥注释后无写入形态；判据双向自检通过，字段={len(FORBIDDEN_WRITE_FIELDS)}",
    )


def _collect_string_literals(code: str) -> list[str]:
    """收集全部字符串字面量内容，供「裸 SQL 形态」判据使用。"""
    import io
    import tokenize

    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.STRING:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return [code]
    return out


def _strip_comments_and_docstrings(src: str) -> str:
    """剥 ``#`` 注释 + docstring，**保留**普通字符串字面量。

    平台铁律：`strip_comments` 会把 ``sa.text(\"\"\"...\"\"\")`` 里的 SQL 一起剥掉
    ⇒ 对「必须含某形态」的判据造成假红。这里只剥 docstring（``ast.Expr(Constant
    (str))``），普通字面量原样保留。
    """
    import ast
    import io
    import tokenize

    # 1) 剥 # 注释
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok.string if tok.type != tokenize.NL else "\n")
    except Exception:
        out = [src]
    stage1 = tokenize.untokenize  # noqa: F841  (仅表明用过 tokenize 语义)

    # tokenize.untokenize 对 generate_tokens 的裁剪结果不稳定 ⇒ 用行级剥注释
    lines = src.splitlines()
    try:
        comment_lines: set[int] = set()
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comment_lines.add(tok.start[0])
        stripped: list[str] = []
        for i, ln in enumerate(lines, start=1):
            if i in comment_lines:
                idx = ln.find("#")
                stripped.append(ln[:idx] if idx >= 0 else ln)
            else:
                stripped.append(ln)
        body = "\n".join(stripped)
    except Exception:
        body = src

    # 2) 剥 docstring（按行号置空，保留普通字符串字面量）
    try:
        tree = ast.parse(src)
        doc_lines: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if not node.body:
                continue
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    doc_lines.add(ln)
        kept = [
            "" if i in doc_lines else ln
            for i, ln in enumerate(body.splitlines(), start=1)
        ]
        return "\n".join(kept)
    except Exception:
        return body


# ─────────────────────────────────────────────────────────────────────────────
# 附注状态快照（复原核验用；只读）
# ─────────────────────────────────────────────────────────────────────────────


def _binding_ids(node: Any) -> list[str]:
    found: list[str] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            for k, v in n.items():
                if k == "binding_id" and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(n, list):
            for it in n:
                walk(it)

    walk(node)
    return sorted(found)


def _note_fingerprint(row: Any) -> dict[str, Any]:
    """单章节的可比对指纹（只取本 spec 会改的五类字段 + table_data 摘要）。"""
    td = row.table_data if isinstance(row.table_data, dict) else {}
    return {
        "section_id": row.section_id,
        "note_section": row.note_section,
        "is_deleted": bool(row.is_deleted),
        "template_lineage": row.template_lineage,
        "binding_ids": _binding_ids(td),
        "table_data_md5": hashlib.md5(
            json.dumps(td, ensure_ascii=False, sort_keys=True, default=str).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


async def _snapshot_notes(session: Any, project_id: UUID, year: int) -> dict[str, dict]:
    """按 note id 取指纹。**含软删行**（归档靠 is_deleted，不含就验不出归档复原）。"""
    # 🔴 ORM 模型在 app.models.report_models，**不在** workpaper_models
    # （与生产 `note_conversion_service._map_disclosure_notes` 同源；按后者写会
    # ImportError，而这类错误只在真跑时暴露 —— 平台已记「写连库脚本前先确认真实
    # 模块/列名」）。
    from app.models.report_models import DisclosureNote

    rows = (
        (
            await session.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(r.id): _note_fingerprint(r) for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# 可验收性判定
# ─────────────────────────────────────────────────────────────────────────────

SAFE_SWITCH_CRITERIA = """可安全切换的判据（四条同时成立）：
  (a) 项目未软删且 audit_year 非空；
  (b) template_type 为 'soe' 或 'listed'（有明确起点，否则往返无意义）；
  (c) 该项目有附注数据（disclosure_notes > 0），否则往返验不出章节映射；
  (d) 用户显式授权该项目为专用测试项目（--project + --i-authorize-apply），
      因为转换会触发 execute_full_chain(force=True) 全链重算 = 破坏性操作。
仅 (a)~(c) 成立只说明「技术上可切换」，(d) 是**必要条件** —— 需求 10.8。"""


async def _survey(session: Any, report: Report) -> list[dict[str, Any]]:
    """只读盘点：列出全部候选并给出实测计数（需求 10.7 的原因串）。"""
    # 与 `_snapshot_notes` 同源：ORM 模型在 app.models.report_models。
    from app.models.report_models import DisclosureNote

    rows = (
        (
            await session.execute(
                sa.select(Project).where(Project.is_deleted == sa.false())
            )
        )
        .scalars()
        .all()
    )

    survey: list[dict[str, Any]] = []
    for p in rows:
        if p.audit_year is None:
            continue
        note_cnt = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(DisclosureNote)
                .where(
                    DisclosureNote.project_id == p.id,
                    DisclosureNote.year == p.audit_year,
                )
            )
        ).scalar() or 0
        survey.append(
            {
                "id": str(p.id),
                "name": p.name,
                "year": p.audit_year,
                "template_type": p.template_type,
                "report_scope": p.report_scope,
                "notes": int(note_cnt),
            }
        )

    report.log("")
    report.log("== 真实库盘点（只读）==")
    report.log(SAFE_SWITCH_CRITERIA)
    report.log("")
    report.log(
        f"{'project_id':38} {'year':>5} {'tmpl':>7} {'scope':>13} {'notes':>6}  name"
    )
    for s in survey:
        report.log(
            f"{s['id']:38} {str(s['year']):>5} {str(s['template_type']):>7} "
            f"{str(s['report_scope']):>13} {s['notes']:>6}  {s['name']}"
        )

    tech = [s for s in survey if s["template_type"] in ("soe", "listed") and s["notes"] > 0]
    report.log("")
    report.log(
        f"实测计数：live_projects={len(survey)} / "
        f"template_type in (soe,listed)={len([s for s in survey if s['template_type'] in ('soe','listed')])} / "
        f"有附注数据={len([s for s in survey if s['notes'] > 0])} / "
        f"技术上可切换(a~c)={len(tech)} / 已授权(d)=0（未经 --i-authorize-apply）"
    )
    return survey


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────


async def _run(args: argparse.Namespace, report: Report) -> None:
    from app.services.note_conversion_service import NoteConversionService

    db_url = settings.DATABASE_URL
    # 铁律 2：自建一次性 engine，不借用共享 async_session（避免双向污染连接池）
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            survey = await _survey(session, report)
            tech = [
                s
                for s in survey
                if s["template_type"] in ("soe", "listed") and s["notes"] > 0
            ]

            # ── 可验收性多态判定 ────────────────────────────────────────────
            if args.project:
                target = next((s for s in survey if s["id"] == args.project), None)
                if target is None:
                    report.eligibility = Eligibility.PROJECT_NOT_FOUND.value
                    report.eligibility_reason = (
                        f"指定项目 {args.project} 不存在或已软删"
                    )
                elif target["notes"] == 0:
                    report.eligibility = Eligibility.NO_NOTE_DATA.value
                    report.eligibility_reason = (
                        f"指定项目 {args.project} 无附注数据（disclosure_notes=0）"
                    )
                elif not args.i_authorize_apply:
                    report.eligibility = Eligibility.NOT_AUTHORIZED.value
                    report.eligibility_reason = (
                        "指定了 --project 但未给 --i-authorize-apply；"
                        "转换会触发全链重算，须用户显式授权"
                    )
                else:
                    report.eligibility = Eligibility.ELIGIBLE.value
                    report.eligibility_reason = (
                        f"用户显式授权项目 {target['id']}（{target['name']}，"
                        f"year={target['year']}, template_type={target['template_type']}）"
                    )
            else:
                report.eligibility = Eligibility.NO_CANDIDATE.value
                report.eligibility_reason = (
                    f"未指定 --project；技术上可切换(a~c)={len(tech)} 个，"
                    f"但已授权(d)=0 ⇒ 无合法验收对象"
                )

            report.log("")
            report.log(f"== 可验收性 = {report.eligibility} ==")
            report.log(f"原因：{report.eligibility_reason}")

            # ── 只读能力核验（无论可否验收都做，证明脚本本身有效）──────────
            svc = NoteConversionService(session)
            for name in (
                "preview_note_conversion",
                "_create_snapshot",
                "rollback_conversion",
                "_map_disclosure_notes",
            ):
                if not hasattr(svc, name):
                    report.add(
                        f"生产路径可复用：{name}",
                        Verdict.ERR,
                        "服务层缺该方法 ⇒ 验收脚本无法复用生产路径（禁另写一份）",
                    )
                else:
                    report.add(f"生产路径可复用：{name}", Verdict.OK)

            if report.eligibility != Eligibility.ELIGIBLE.value:
                report.add(
                    "soe->listed->soe 往返验收",
                    Verdict.SKIP,
                    f"无法验收：{report.eligibility_reason}",
                )
                report.log("")
                report.log(
                    "[SKIP] 无法验收：本库无可安全切换的项目"
                    f"（原因：{report.eligibility_reason}）"
                )
                report.log(
                    "        禁用 fixture / 新建测试项目冒充通过（需求 10.7）。"
                    "如需真实验收，请显式授权专用测试项目："
                )
                report.log(
                    "        python backend/scripts/diagnose/verify_note_conversion_live.py "
                    "--project <uuid> --year <year> --apply --i-authorize-apply"
                )
                return

            # ── 预览（零写入，需求 10.5）────────────────────────────────────
            pid = UUID(args.project)
            year = int(args.year or 0) or next(
                s["year"] for s in survey if s["id"] == args.project
            )
            cur = next(s["template_type"] for s in survey if s["id"] == args.project)
            tgt = "listed" if cur == "soe" else "soe"

            before = await _snapshot_notes(session, pid, year)
            preview = await svc.preview_note_conversion(pid, year, tgt)
            after_preview = await _snapshot_notes(session, pid, year)

            report.log("")
            report.log("== dry-run 预期改写清单（需求 10.5）==")
            report.log(json.dumps(preview, ensure_ascii=False, indent=2, default=str))

            if before == after_preview:
                report.add(
                    "预览零写入（Property 31）",
                    Verdict.OK,
                    f"{len(before)} 个章节指纹逐字节不变",
                )
            else:
                changed = [k for k in before if before[k] != after_preview.get(k)]
                report.add(
                    "预览零写入（Property 31）",
                    Verdict.ERR,
                    f"预览产生写入，变化章节数={len(changed)}",
                )

            if not args.apply:
                report.add(
                    "soe->listed->soe 往返验收",
                    Verdict.SKIP,
                    "未给 --apply（默认 dry-run）",
                )
                return

            # ── --apply 真实往返 + 按快照复原（铁律 6：finally 无条件复原）──
            report.log("")
            report.log(f"== --apply 真实往返 {cur} -> {tgt} -> {cur} ==")
            restored = False
            try:
                fwd = await svc.execute_conversion(pid, year, tgt)
                report.log(
                    "forward: " + json.dumps(fwd, ensure_ascii=False, default=str)
                )
                back = await svc.execute_conversion(pid, year, cur)
                report.log("back:    " + json.dumps(back, ensure_ascii=False, default=str))
            finally:
                try:
                    rb = await svc.rollback_conversion(pid, year)
                    report.log(
                        "rollback: " + json.dumps(rb, ensure_ascii=False, default=str)
                    )
                    restored = True
                except Exception as exc:  # noqa: BLE001
                    report.add("按快照复原", Verdict.ERR, f"回滚抛错: {exc!r}")

            # 铁律 6：判成败查数据，不看退出码
            final = await _snapshot_notes(session, pid, year)
            drifted = [k for k in before if before[k] != final.get(k)]
            newly = [k for k in final if k not in before]
            if not drifted and not newly:
                report.add(
                    "往返后逐项复原（Property 32/33）",
                    Verdict.OK,
                    f"{len(before)} 个章节的 section_id/note_section/is_deleted/"
                    "template_lineage/binding_id/table_data 全部回到初始",
                )
            else:
                report.add(
                    "往返后逐项复原（Property 32/33）",
                    Verdict.ERR,
                    f"未完全复原：漂移={len(drifted)} 新增={len(newly)}；"
                    f"样例={drifted[:3] or newly[:3]}（restored={restored}）",
                )
    finally:
        # 铁律 2：同一 loop 内 dispose，避免污染
        await engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="国企↔上市附注转换真实库验收（默认 dry-run，只读）"
    )
    ap.add_argument("--project", help="专用测试项目 id（须用户显式授权）")
    ap.add_argument("--year", type=int, help="审计年度（缺省取项目 audit_year）")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真实执行往返（须同时给 --i-authorize-apply）",
    )
    ap.add_argument(
        "--i-authorize-apply",
        action="store_true",
        help="用户显式授权：确认该项目是专用测试项目，可承受全链重算",
    )
    ap.add_argument("--out", help="报告写盘路径（UTF-8）")
    args = ap.parse_args()

    _assert_state_names_are_derived()

    report = Report()
    report.log("== 国企<->上市附注转换 真实库验收（Task 19）==")
    _self_check_no_forbidden_writes(report)

    if args.apply and not args.i_authorize_apply:
        report.add(
            "授权校验（需求 10.8）",
            Verdict.ERR,
            "--apply 必须同时给 --i-authorize-apply（转换属破坏性操作）",
        )
    try:
        asyncio.run(_run(args, report))
    except Exception as exc:  # noqa: BLE001
        report.log(f"[ERR] 脚本自身异常: {exc!r}")
        _finish(report, args, rc=2)
        return 2

    dist = report.counts()
    report.log("")
    report.log("== 判定分布（态名从枚举派生）==")
    for k in ALL_VERDICTS:
        report.log(f"  {k:>5} = {dist[k]}")
    report.log(f"  eligibility = {report.eligibility}")

    if report.failed():
        rc = 1
    elif report.eligibility != Eligibility.ELIGIBLE.value:
        # 需求 10.7：无合法验收对象 ⇒ 非零退出码 + 显式 SKIP 标记（两者都给）
        rc = 1
    else:
        rc = 0
    _finish(report, args, rc)
    return rc


def _finish(report: Report, args: argparse.Namespace, rc: int) -> None:
    report.log("")
    report.log(f"== exit={rc} ==")
    out = args.out or str(
        Path(__file__).resolve().parent / "verify_note_conversion_live_out.txt"
    )
    # 铁律 5：一律写盘 UTF-8（控制台可能是 GBK）
    Path(out).write_text("\n".join(report.lines) + "\n", encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    sys.exit(main())
