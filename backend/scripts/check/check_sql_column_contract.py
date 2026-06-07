"""SQL 列契约检查（独立 CLI 脚本，report 模式）。

扫描 backend/app/ 下 Python 文件中的：
  1. ORM 属性引用：select(Model.column), Model.column（.where/.order_by 等）
  2. 裸 SQL 字符串中的 alias.column 引用

与 ORM 模型 mapped columns 集合比对，输出可疑违规。

用法：
    python backend/scripts/check/check_sql_column_contract.py          # report 模式（默认）
    python backend/scripts/check/check_sql_column_contract.py --strict  # strict 模式（CI 集成）

report 模式：打印违规到 stdout，始终 exit 0
strict 模式：有新增违规时 exit 1

**设计取舍**：
- 使用简单 regex 而非 sqlglot（轻量，无外部依赖）
- 误报可通过 allowlist 过滤
- 无法静态检测所有动态 SQL（f-string 变量部分跳过）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ─── 路径 ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
BACKEND_APP = REPO_ROOT / "backend" / "app"
ALLOWLIST_FILE = SCRIPT_DIR / "sql_column_contract_allowlist.json"

EXCLUDE_DIRS = {"__pycache__", ".hypothesis", "node_modules", ".git", ".venv"}

# ─── SQL 关键字识别 ─────────────────────────────────────────────────────────
_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|JOIN|FROM|SET|ON|ORDER\s+BY|GROUP\s+BY|HAVING)\b",
    re.IGNORECASE,
)

# ─── 提取裸 SQL 字符串 ──────────────────────────────────────────────────────
# 匹配 text( / sa.text( / sql_text( 调用中的三引号/单引号字符串
_TEXT_CALL_RE = re.compile(
    r"""(?:^|[^\w.])(?:sa\.text|sql_text|sa_text|_text|text)\s*\(\s*"""
    r"""(?:"{3}(.*?)"{3}|'{3}(.*?)'{3}|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""",
    re.DOTALL,
)

# ─── 列引用提取（regex 方式）────────────────────────────────────────────────
# alias.column 模式：word.word（排除数字开头、常见非列模式）
_QUALIFIED_COL_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b"
)

# 排除的 "表.列" 模式（非真正列引用）
_SKIP_PREFIXES = {
    "self", "cls", "app", "os", "sys", "re", "json", "datetime",
    "sqlalchemy", "sa", "func", "cast", "type_", "and_", "or_",
    "text", "literal", "column", "table", "select", "insert",
    "update", "delete", "values", "returning", "asc", "desc",
    "null", "true", "false", "not_", "case", "when", "exists",
    "models", "model", "schemas", "schema", "enum", "base",
    "path", "logger", "log", "config", "settings", "request",
    "response", "status", "http", "uuid", "math", "typing",
}

# 排除的列名（SQL 函数 / 保留字 / 常见误判）
_SKIP_COLUMNS = {
    "text", "integer", "varchar", "boolean", "timestamp", "timestamptz",
    "uuid", "jsonb", "json", "float", "numeric", "bigint", "smallint",
    "serial", "bytea", "date", "time", "interval", "array",
    "now", "count", "sum", "avg", "min", "max", "coalesce",
    "nullif", "length", "lower", "upper", "trim", "replace",
    "concat", "cast", "extract", "to_char", "to_timestamp",
    "string_agg", "array_agg", "row_number", "rank", "dense_rank",
    "exists", "not_null", "primary_key", "foreign_key", "unique",
    "index", "default", "null", "true", "false", "cascade",
    "restrict", "set_null", "no_action", "check",
}

# ─── ORM 属性引用扫描 ──────────────────────────────────────────────────────
# 匹配 PascalCase 类名（ORM Model 类）后跟 .attribute 的模式
# 例如: WorkingPaper.id, TrialBalance.audited_amount, WpIndex.wp_code
_ORM_ATTR_RE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]+)\.([a-z_][a-z0-9_]*)\b"
)

# 排除的 ORM 属性（非列引用：方法调用/SQLAlchemy 内部/常见属性）
_SKIP_ORM_ATTRS = {
    # SQLAlchemy ORM 内部属性/方法
    "query", "metadata", "registry", "table", "columns",
    "c", "key", "name", "type", "info", "expression",
    "desc", "asc", "in_", "notin_", "is_", "isnot",
    "like", "ilike", "between", "label", "op", "any_",
    "has", "contains", "startswith", "endswith",
    # 常见方法调用（跟着圆括号的不是列引用，但 regex 无法区分）
    "all", "first", "one", "scalar", "fetchall", "fetchone",
    "filter", "where", "select", "join", "outerjoin",
    "group_by", "order_by", "having", "limit", "offset",
    "distinct", "union", "intersect", "except_",
    "delete", "update", "insert", "values",
    # Python 内建
    "append", "extend", "items", "keys", "values",
    "get", "pop", "update", "format", "encode", "decode",
    "__tablename__", "__table__", "__mapper__",
}

# 排除的 PascalCase 前缀（非 ORM Model 类）
_SKIP_ORM_CLASSES = {
    "UUID", "Path", "List", "Dict", "Optional", "Union", "Tuple", "Set",
    "Type", "Any", "Callable", "Awaitable", "Coroutine", "AsyncGenerator",
    "HTTPException", "JSONResponse", "Response", "Request",
    "Depends", "Query", "Body", "Header", "Cookie",
    "BaseModel", "Field", "BaseSettings",
    "Mapped", "Column", "ForeignKey", "DateTime", "Integer", "String",
    "Boolean", "Text", "Float", "Numeric", "Enum",
    "AsyncSession", "Session", "Engine",
    "Logger", "Decimal", "timedelta",
    "True", "False", "None",
}


# ─── 辅助函数 ───────────────────────────────────────────────────────────────


def _iter_python_files() -> list[Path]:
    """遍历 backend/app/ 下所有 .py 文件。"""
    files: list[Path] = []
    for root, dirs, names in os.walk(BACKEND_APP):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            if n.endswith(".py"):
                files.append(Path(root) / n)
    return sorted(files)


def _extract_sql_strings(source: str) -> list[tuple[str, int]]:
    """提取 text() 调用中的 SQL 字符串及其大致行号。

    返回 [(sql_text, line_number), ...]
    """
    results: list[tuple[str, int]] = []
    for m in _TEXT_CALL_RE.finditer(source):
        sql = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
        if _SQL_KEYWORDS.search(sql):
            # 计算行号
            line_no = source[: m.start()].count("\n") + 1
            results.append((sql, line_no))
    return results


def _extract_column_refs(sql: str) -> list[tuple[str, str]]:
    """从 SQL 字符串中提取 (table_or_alias, column) 引用对。

    只提取 qualified 引用（alias.column），跳过：
    - f-string 插值部分 {xxx}
    - 明确的非列模式
    """
    refs: list[tuple[str, str]] = []

    # 移除 f-string 插值部分（{...}），避免误判 Python 变量
    clean_sql = re.sub(r"\{[^}]*\}", "___INTERPOLATED___", sql)

    for m in _QUALIFIED_COL_RE.finditer(clean_sql):
        prefix = m.group(1).lower()
        col = m.group(2).lower()

        # 跳过非表前缀
        if prefix in _SKIP_PREFIXES:
            continue
        # 跳过非列后缀
        if col in _SKIP_COLUMNS:
            continue
        # 跳过全大写前缀（常量/枚举）
        if m.group(1).isupper() and len(m.group(1)) > 2:
            continue
        # 跳过 :param 绑定参数后的引用
        if re.match(r"^:", m.group(0)):
            continue

        refs.append((prefix, col))

    return refs


def _extract_orm_attr_refs(source: str) -> list[tuple[str, str, int]]:
    """从 Python 源码中提取 ORM 属性引用 (ClassName, attribute, line_no)。

    扫描 PascalCase.snake_case 模式，例如：
    - select(WorkingPaper.id)
    - .where(TrialBalance.project_id == ...)
    - .order_by(WpIndex.wp_code)
    """
    refs: list[tuple[str, str, int]] = []
    lines = source.split("\n")

    # 简易 docstring 区域检测（跳过三引号内的内容）
    in_docstring = False
    docstring_char = ""

    for line_idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # 检测 docstring 开始/结束
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                # 单行 docstring：开头和结尾在同一行
                if stripped.count(docstring_char) >= 2:
                    continue  # 整行是单行 docstring，跳过
                in_docstring = True
                continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue

        # 跳过注释行和 import 行
        if stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from "):
            continue

        for m in _ORM_ATTR_RE.finditer(line):
            cls_name = m.group(1)
            attr_name = m.group(2)

            # 跳过非 ORM 类
            if cls_name in _SKIP_ORM_CLASSES:
                continue
            # 跳过非列属性
            if attr_name in _SKIP_ORM_ATTRS:
                continue
            # 跳过 __dunder__ 属性
            if attr_name.startswith("__"):
                continue
            # 跳过后面紧跟括号的方法调用（如 Model.query(...)）
            after_match = line[m.end():]
            if after_match.startswith("("):
                continue
            # 跳过文件扩展名引用（如 TrialBalance.vue, Model.py）
            if attr_name in ("vue", "py", "js", "ts", "html", "css", "json", "md", "yaml", "yml"):
                continue

            refs.append((cls_name, attr_name, line_idx))

    return refs


def _collect_orm_columns() -> dict[str, set[str]]:
    """通过 import ORM models 收集所有表的列名。

    返回 {table_name: {col1, col2, ...}}
    """
    # 确保 backend 在 sys.path 中
    backend_dir = str(REPO_ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    import importlib
    import pkgutil

    try:
        import app.models as models_pkg
    except ImportError as e:
        print(f"⚠️  无法导入 app.models: {e}", file=sys.stderr)
        print("   提示: 请从仓库根目录运行，或确保 backend/ 在 PYTHONPATH 中", file=sys.stderr)
        return {}

    # 递归 import 所有子模块确保完整
    for mod_info in pkgutil.walk_packages(models_pkg.__path__, prefix="app.models."):
        try:
            importlib.import_module(mod_info.name)
        except Exception:
            pass

    from app.models.base import Base

    columns: dict[str, set[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        columns[table_name.lower()] = {c.name.lower() for c in table.columns}

    return columns


def _collect_orm_class_to_table() -> dict[str, str]:
    """收集 ORM 类名 → 表名 映射。

    返回 {ClassName: table_name}（类名保持原始大小写）
    """
    backend_dir = str(REPO_ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    try:
        from app.models.base import Base
    except ImportError:
        return {}

    class_to_table: dict[str, str] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "__tablename__"):
            class_to_table[cls.__name__] = cls.__tablename__.lower()

    return class_to_table


def _load_allowlist() -> set[str]:
    """加载白名单文件，返回允许的 table.column 集合。"""
    if not ALLOWLIST_FILE.exists():
        return set()
    try:
        data = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
        return {ref.lower() for ref in data.get("allowed_references", [])}
    except (json.JSONDecodeError, KeyError):
        return set()


# ─── FROM/JOIN 别名映射（简易版）────────────────────────────────────────────

_FROM_JOIN_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?\b",
    re.IGNORECASE,
)


def _build_alias_map(sql: str) -> dict[str, str]:
    """从 SQL 的 FROM/JOIN 子句构建 {alias -> real_table} 映射。"""
    alias_map: dict[str, str] = {}
    for m in _FROM_JOIN_ALIAS_RE.finditer(sql):
        table = m.group(1).lower()
        alias = (m.group(2) or m.group(1)).lower()
        alias_map[alias] = table
    return alias_map


# ─── 主逻辑 ─────────────────────────────────────────────────────────────────


def run_check(strict: bool = False) -> int:
    """执行 SQL 列契约检查。

    Returns:
        0 = report 模式或无违规
        1 = strict 模式且有违规
    """
    mode_label = "strict" if strict else "report"
    print(f"=== SQL 列契约检查 ({mode_label} 模式) ===")
    print()

    # 收集 ORM 列
    orm_columns = _collect_orm_columns()
    if not orm_columns:
        print("❌ 无法加载 ORM 模型列信息，检查中止")
        return 1 if strict else 0

    # 收集类名→表名映射
    class_to_table = _collect_orm_class_to_table()

    print(f"ORM 模型: {len(orm_columns)} 张表, {len(class_to_table)} 个映射类")

    # 加载白名单
    allowlist = _load_allowlist()
    print(f"白名单项: {len(allowlist)} 条")
    print()

    # 扫描文件
    py_files = _iter_python_files()
    print(f"扫描文件: {len(py_files)}")

    sql_count = 0
    orm_ref_count = 0
    violations: list[tuple[str, int, str, str, str]] = []  # (file, line, table, column, source_type)
    allowed_hits: list[tuple[str, int, str, str]] = []

    for fpath in py_files:
        try:
            source = fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel_path = str(fpath.relative_to(REPO_ROOT))

        # ── 扫描 1: 裸 SQL 中的 alias.column ──
        sql_strings = _extract_sql_strings(source)
        sql_count += len(sql_strings)

        for sql, line_no in sql_strings:
            alias_map = _build_alias_map(sql)
            col_refs = _extract_column_refs(sql)

            for prefix, col in col_refs:
                # 解析真实表名（通过别名映射）
                real_table = alias_map.get(prefix, prefix)
                ref_key = f"{real_table}.{col}"

                # 检查是否在白名单中
                if ref_key in allowlist or f"{prefix}.{col}" in allowlist:
                    allowed_hits.append((rel_path, line_no, real_table, col))
                    continue

                # 检查列是否存在于 ORM
                if real_table in orm_columns:
                    if col not in orm_columns[real_table]:
                        violations.append((rel_path, line_no, real_table, col, "raw_sql"))

        # ── 扫描 2: ORM 属性引用 Model.column ──
        orm_refs = _extract_orm_attr_refs(source)
        orm_ref_count += len(orm_refs)

        for cls_name, attr_name, line_no in orm_refs:
            # 解析类名到表名
            table_name = class_to_table.get(cls_name)
            if table_name is None:
                continue  # 不是已知 ORM 类，跳过

            ref_key = f"{table_name}.{attr_name}"

            # 白名单检查
            if ref_key in allowlist:
                allowed_hits.append((rel_path, line_no, table_name, attr_name))
                continue

            # 检查列是否存在于 ORM 表
            if table_name in orm_columns:
                if attr_name not in orm_columns[table_name]:
                    violations.append((rel_path, line_no, table_name, attr_name, "orm_attr"))

    # ─── 输出报告 ─────────────────────────────────────────────────────────
    print(f"发现 SQL 字符串: {sql_count}")
    print(f"ORM 属性引用: {orm_ref_count}")
    print(f"已知允许: {len(allowed_hits)}")
    print(f"新增违规: {len(violations)}")
    print()

    if violations:
        print("违规明细:")
        # 去重并按文件排序
        seen: set[str] = set()
        for rel_path, line_no, table, col, source_type in sorted(violations, key=lambda x: (x[0], x[1])):
            key = f"{rel_path}:{line_no}:{table}.{col}"
            if key in seen:
                continue
            seen.add(key)
            tag = "[ORM]" if source_type == "orm_attr" else "[SQL]"
            print(f"  {tag} {rel_path}:{line_no} — 引用 `{table}.{col}`")
        print()
        print("建议: 确认是否为真实违规，如为误报请加入 allowlist")
        print(f"      白名单路径: {ALLOWLIST_FILE.relative_to(REPO_ROOT)}")
    else:
        print("✅ 未发现新增违规")

    print()
    print("─" * 60)

    if strict and violations:
        print("❌ strict 模式: 检测到违规，退出码 1")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SQL 列契约检查：扫描裸 SQL 列引用和 ORM 属性引用，与 ORM 模型列比对"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="strict 模式：有违规时 exit 1（用于 CI 集成）",
    )
    args = parser.parse_args()
    return run_check(strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
