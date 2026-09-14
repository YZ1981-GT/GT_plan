"""裸 SQL 绑定参数 cast 写法契约：禁止 `:name::type`，必须用 `CAST(:name AS type)`。

**为什么需要**：`:name::type` 这个写法在本项目（SQLAlchemy + asyncpg）下**必然失败**，
但它看起来完全正常，是极易反复引入的一类缺陷。

真库实测判据（2026-09-06）：
    SELECT :payload::jsonb          -> asyncpg.exceptions.PostgresSyntaxError
    SELECT CAST(:payload AS jsonb)  -> OK，返回 {'a': 1}

根因：SQLAlchemy 的 `text()` 按 `:name` 识别绑定参数，而 `::` 是 PG 的 cast 语法。
两者相邻时 `::type` 抢先被当成 cast 处理，`:name` 没被识别成绑定参数就原样发给
PG ⇒ PG 见到裸的 `:` 直接报语法错。表现为「这条 SQL 从未成功执行过」。

发现代价：本次一次性清出 **15 处 / 11 个文件**，全是写路径（UPDATE/INSERT），
命中即 500 且数据写不进去；逐条真库验证「改前 14/14 语法失败 → 改后 14/14 可执行」。
其中 `app_audit_log` 的审计写入有 4 处（eqcr_judgment / project_wizard /
qc_report_export / signoff_checklist）—— 审计日志写不进去且无人发现，
因为多数调用点把异常吞掉了。

本守卫只查**静态写法**，不连库，因此可在 CI 无 PG 时运行。

**Validates**: 裸 SQL 契约（与 test_raw_sql_schema_contract.py 同族）
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_APP = REPO_ROOT / "backend" / "app"

EXCLUDE_DIRS = {"__pycache__", ".venv", "node_modules", "migrations", "tests"}

# 已知 PG 类型名 —— 只有冒号后跟这些才判定为「绑定参数 + cast」，
# 从而排除 URI 字面量（`:1122::期末余额`）与 pytest nodeid（`TestX::test_y`）等误报。
PG_TYPES = {
    "jsonb", "json", "text", "uuid", "int", "integer", "bigint", "smallint",
    "numeric", "decimal", "boolean", "bool", "date", "timestamptz", "timestamp",
    "float", "real", "double", "interval", "bytea", "inet",
}

# text() / sa.text() / sql_text() 的字符串实参（含 f/r/b 前缀 —— 漏了前缀会让
# f-string 写的 SQL 整段逃过扫描，那正是 report_rows 长期隐形的原因）
_CALL_RE = re.compile(
    r"""(?:^|[^\w.])(?:sa\.text|sql_text|sa_text|_text|text)\s*\(\s*"""
    r"""(?:[frbFRB]{1,2})?"""
    r"""("{3}.*?"{3}|'{3}.*?'{3}|(?:(?:[frbFRB]{1,2})?"(?:[^"\\]|\\.)*"\s*)+"""
    r"""|(?:(?:[frbFRB]{1,2})?'(?:[^'\\]|\\.)*'\s*)+)""",
    re.DOTALL,
)
_STR_RE = re.compile(r"""["']((?:[^"'\\]|\\.)*)["']""")
_BIND_CAST_RE = re.compile(r":(\w+)::(\w+)\b")


def _iter_app_files() -> list[Path]:
    out: list[Path] = []
    for p in BACKEND_APP.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _sql_blocks(src: str) -> list[str]:
    """取出传给 text() 的 SQL 字符串（三引号原样；拼接式拼回一整串）。"""
    blocks: list[str] = []
    for m in _CALL_RE.finditer(src):
        raw = m.group(1).strip()
        if raw.startswith(('"""', "'''")):
            blocks.append(raw[3:-3])
        else:
            blocks.append("".join(_STR_RE.findall(raw)))
    return blocks


def _collect_violations() -> list[tuple[str, str, str]]:
    """返回 [(相对路径, ":name::type", 该 SQL 片段), ...]。"""
    violations: list[tuple[str, str, str]] = []
    for p in _iter_app_files():
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "::" not in src:
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        for sql in _sql_blocks(src):
            for m in _BIND_CAST_RE.finditer(sql):
                if m.group(2).lower() in PG_TYPES:
                    violations.append(
                        (rel, f":{m.group(1)}::{m.group(2)}", " ".join(sql.split())[:120])
                    )
    return violations


def test_no_bind_param_double_colon_cast():
    """裸 SQL 里不得出现 `:name::type` —— 该写法在 asyncpg 下必然语法错。"""
    violations = _collect_violations()
    assert not violations, (
        "发现 `:name::type` 写法（SQLAlchemy + asyncpg 下必然 PostgresSyntaxError，"
        "该 SQL 从未成功执行过）：\n"
        + "\n".join(f"  {rel}: {frag}\n      {sql}" for rel, frag, sql in violations)
        + "\n\n修复：改成 CAST(:name AS type)。"
        "\n真库判据：SELECT :x::jsonb → PostgresSyntaxError；"
        "SELECT CAST(:x AS jsonb) → OK。"
    )


def test_scanner_actually_sees_sql():
    """反向自检：扫描器必须真的能取到 SQL，否则上面那条会变成永真。

    没有这条，`_CALL_RE` 一旦写错（例如漏掉 f-string 前缀、或 text( 的匹配失效）
    会让 `_collect_violations()` 恒返回空集 ⇒ 守卫静默失效。
    """
    total = 0
    with_bind = 0
    for p in _iter_app_files():
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for sql in _sql_blocks(src):
            if not sql.strip():
                continue
            total += 1
            if re.search(r":\w+", sql):
                with_bind += 1

    assert total > 200, f"仅取到 {total} 段 SQL —— 扫描器疑似失效（本仓库远多于此）"
    assert with_bind > 100, f"仅 {with_bind} 段含绑定参数 —— 扫描器疑似失效"


def test_detects_injected_violation():
    """反向自检：给扫描器喂一段已知违规 SQL，它必须能识别出来。

    这条锁死「判定逻辑本身有效」，与上面那条（能取到 SQL）互补：
    前者防"取不到内容"，本条防"取到了但判不出"。
    """
    sample = '''
        stmt = sa.text("UPDATE t SET c = :payload::jsonb WHERE id = :i")
        other = sa.text(f"SELECT {col} FROM t WHERE d = :d::timestamptz")
        legit = sa.text("SELECT CAST(:payload AS jsonb) FROM t")
        not_a_cast = sa.text("SELECT * FROM t WHERE uri = ':1122::期末余额'")
    '''
    found: list[str] = []
    for sql in _sql_blocks(sample):
        for m in _BIND_CAST_RE.finditer(sql):
            if m.group(2).lower() in PG_TYPES:
                found.append(f":{m.group(1)}::{m.group(2)}")

    assert ":payload::jsonb" in found, f"未识别普通字面量里的违规：{found}"
    assert ":d::timestamptz" in found, f"未识别 f-string 里的违规：{found}"
    # CAST 正确写法与 URI 字面量都不该被算成违规
    assert len(found) == 2, f"出现误报：{found}"
