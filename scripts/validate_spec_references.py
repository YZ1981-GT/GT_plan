"""
验证 spec 文档中引用的函数名/类名/端点路径是否在代码中真实存在。

用法：
    python scripts/validate_spec_references.py .kiro/specs/ledger-import-view-refactor/design.md

输出：
    表格形式展示每个引用的状态（✅ found / ❌ not found / ⚠️ ambiguous）
"""
import re
import sys
import os
from pathlib import Path


def extract_backtick_identifiers(spec_path: str) -> list[str]:
    """从 spec 文件中提取所有反引号包裹的标识符。"""
    content = Path(spec_path).read_text(encoding="utf-8")
    # 只匹配单行内的单反引号（排除代码块 ```...```）
    # 先移除代码块
    content_no_blocks = re.sub(r"```[\s\S]*?```", "", content)
    # 匹配单反引号内容
    matches = re.findall(r"`([^`\n]+)`", content_no_blocks)
    identifiers = []
    for m in matches:
        m = m.strip()
        if not m or m.isdigit() or len(m) < 3:
            continue
        # 排除多行内容（不应出现但防御性检查）
        if "\n" in m:
            continue
        # 排除纯描述性文本（含中文且无标识符特征）
        if re.search(r"[\u4e00-\u9fff]", m) and not re.search(r"[a-zA-Z_/]", m):
            continue
        # 排除赋值语句片段
        if "=" in m and " " in m:
            continue
        # 排除 markdown 格式
        if m.startswith("#") or m.startswith("--"):
            continue
        identifiers.append(m)
    return list(dict.fromkeys(identifiers))  # 去重保序


def grep_in_directory(pattern: str, directory: str) -> list[str]:
    """在目录中递归搜索 pattern，返回匹配的文件路径列表。"""
    matches = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return matches
    for py_file in dir_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if re.search(pattern, content):
                matches.append(str(py_file))
        except (OSError, UnicodeDecodeError):
            continue
    return matches


def check_python_identifier(name: str) -> tuple[str, list[str]]:
    """检查 Python 标识符（函数名/类名）是否存在于 backend/app/。"""
    backend_app = "backend/app"
    # 搜索 def name 或 class name
    pattern = rf"\b(def|class)\s+{re.escape(name)}\b"
    matches = grep_in_directory(pattern, backend_app)
    if len(matches) == 0:
        return "❌ not found", []
    elif len(matches) == 1:
        return "✅ found", matches
    else:
        return "⚠️ ambiguous", matches


def check_api_path(path: str) -> tuple[str, list[str]]:
    """检查 API 路径是否存在于 backend/app/routers/。"""
    routers_dir = "backend/app/routers"
    # 搜索路径字符串（可能带引号）
    escaped = re.escape(path)
    pattern = rf"""['"]{escaped}['"&]|prefix\s*=\s*['"]{escaped}"""
    matches = grep_in_directory(escaped.replace(r"\/", "/"), routers_dir)
    if not matches:
        # 也搜索 services 目录
        matches = grep_in_directory(escaped.replace(r"\/", "/"), "backend/app")
    if len(matches) == 0:
        return "❌ not found", []
    elif len(matches) == 1:
        return "✅ found", matches
    else:
        return "⚠️ ambiguous", matches


def classify_identifier(name: str) -> str:
    """分类标识符类型：api_path / python_id / skip。"""
    if name.startswith("/api") or name.startswith("/"):
        if re.match(r"^/[a-z]", name):
            return "api_path"
    # 跳过明显的文件路径（含扩展名）
    if re.search(r"\.\w{2,4}$", name) and "/" in name:
        return "skip"
    # 跳过 SQL 片段、shell 命令等
    if any(kw in name.upper() for kw in ["SELECT", "FROM", "WHERE", "INSERT", "DELETE"]):
        return "skip"
    # 含点号的可能是 module.function 格式
    if "." in name:
        parts = name.split(".")
        last = parts[-1]
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", last):
            return "python_id"
        return "skip"
    # snake_case 或 CamelCase 标识符
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        return "python_id"
    # CamelCase 类名
    if re.match(r"^[A-Z][a-zA-Z0-9]+$", name):
        return "python_id"
    return "skip"


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/validate_spec_references.py <spec_file_path>")
        print("示例: python scripts/validate_spec_references.py .kiro/specs/ledger-import-view-refactor/design.md")
        sys.exit(1)

    spec_path = sys.argv[1]
    if not os.path.exists(spec_path):
        print(f"错误: 文件不存在 - {spec_path}")
        sys.exit(1)

    identifiers = extract_backtick_identifiers(spec_path)
    print(f"\n从 {spec_path} 提取到 {len(identifiers)} 个标识符\n")
    print(f"{'标识符':<45} {'类型':<12} {'状态':<15} {'位置'}")
    print("-" * 110)

    stats = {"found": 0, "not_found": 0, "ambiguous": 0, "skipped": 0}

    for ident in identifiers:
        id_type = classify_identifier(ident)

        if id_type == "skip":
            stats["skipped"] += 1
            continue

        if id_type == "api_path":
            status, locations = check_api_path(ident)
        else:
            # Python identifier - 如果含点号取最后一段
            check_name = ident.split(".")[-1] if "." in ident else ident
            status, locations = check_python_identifier(check_name)

        loc_str = locations[0] if len(locations) == 1 else f"{len(locations)} files" if locations else ""
        print(f"{ident:<45} {id_type:<12} {status:<15} {loc_str}")

        if "found" in status and "not" not in status:
            stats["found"] += 1
        elif "ambiguous" in status:
            stats["ambiguous"] += 1
        else:
            stats["not_found"] += 1

    print(f"\n{'='*60}")
    print(f"汇总: ✅ {stats['found']} found | ❌ {stats['not_found']} not found | ⚠️ {stats['ambiguous']} ambiguous | ⏭️ {stats['skipped']} skipped")


if __name__ == "__main__":
    main()
