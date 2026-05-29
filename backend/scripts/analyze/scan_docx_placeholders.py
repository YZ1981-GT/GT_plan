"""扫描 docx 模板占位符 — Sprint 4 Task 4.1

扫描 backend/wp_templates/ 目录下所有 docx 文件，
使用 mammoth 提取文本，识别占位符（{{...}} 和 【...】 格式），
输出 docx_placeholder_registry.json。

用法：
    python backend/scripts/scan_docx_placeholders.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 确保 backend 在 sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

WP_TEMPLATES_DIR = BACKEND_DIR / "wp_templates"
OUTPUT_PATH = BACKEND_DIR / "data" / "docx_placeholder_registry.json"

# 占位符正则：{{xxx}} 和 【xxx】
PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{([^}]+)\}\}"),          # {{company_name}}
    re.compile(r"【([^】]+)】"),              # 【公司名称】
    re.compile(r"\[\[([^\]]+)\]\]"),          # [[field_name]]
    re.compile(r"\$\{([^}]+)\}"),             # ${variable}
]


def extract_text_from_docx(file_path: Path) -> str:
    """使用 mammoth 提取 docx 文本内容。"""
    try:
        import mammoth
        with open(file_path, "rb") as f:
            result = mammoth.extract_raw_text(f)
            return result.value
    except Exception as e:
        # mammoth 失败时尝试 python-docx
        try:
            from docx import Document
            doc = Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception:
            print(f"  [WARN] Cannot read {file_path.name}: {e}")
            return ""


def find_placeholders(text: str, filename: str) -> list[dict]:
    """从文本中提取所有占位符及其上下文。"""
    results = []
    lines = text.split("\n")

    for line_idx, line in enumerate(lines):
        for pattern in PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(line):
                placeholder = match.group(1).strip()
                # 提取上下文（前后各 30 字符）
                start = max(0, match.start() - 30)
                end = min(len(line), match.end() + 30)
                context = line[start:end].strip()

                results.append({
                    "placeholder": placeholder,
                    "context": context,
                    "line": line_idx + 1,
                    "pattern": match.group(0),
                })

    return results


def derive_uri(filename: str, placeholder: str) -> str:
    """从文件名和占位符生成统一 URI。

    格式：WP:{wp_code}::docx:{placeholder}
    """
    # 从文件名提取 wp_code（如 "A16 管理层声明书.docx" → "A16"）
    stem = Path(filename).stem
    wp_code_match = re.match(r"([A-Z]\d+(?:-\d+)?)", stem)
    wp_code = wp_code_match.group(1) if wp_code_match else stem.split()[0] if stem else "UNKNOWN"

    return f"WP:{wp_code}::docx:{placeholder}"


def scan_all_docx() -> list[dict]:
    """扫描所有 docx 文件并提取占位符。"""
    all_entries: list[dict] = []

    if not WP_TEMPLATES_DIR.exists():
        print(f"[ERROR] wp_templates directory not found: {WP_TEMPLATES_DIR}")
        return all_entries

    # 递归查找所有 docx 文件
    docx_files = sorted(WP_TEMPLATES_DIR.rglob("*.docx"))
    print(f"Found {len(docx_files)} docx files in {WP_TEMPLATES_DIR}")

    for docx_path in docx_files:
        # 跳过临时文件
        if docx_path.name.startswith("~$"):
            continue

        relative_path = docx_path.relative_to(WP_TEMPLATES_DIR)
        print(f"  Scanning: {relative_path}")

        text = extract_text_from_docx(docx_path)
        if not text:
            continue

        placeholders = find_placeholders(text, docx_path.name)
        for ph in placeholders:
            uri = derive_uri(docx_path.name, ph["placeholder"])
            all_entries.append({
                "file": str(relative_path).replace("\\", "/"),
                "placeholder": ph["placeholder"],
                "uri": uri,
                "context": ph["context"],
                "line": ph["line"],
                "pattern": ph["pattern"],
            })

    return all_entries


def main():
    """主入口：扫描并输出 JSON。"""
    print("=" * 60)
    print("Scanning docx placeholders in wp_templates/")
    print("=" * 60)

    entries = scan_all_docx()

    # 去重（同文件同占位符只保留一条）
    seen = set()
    unique_entries = []
    for entry in entries:
        key = (entry["file"], entry["placeholder"])
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)

    # 输出 JSON
    registry = {
        "version": "1.0",
        "total_files_scanned": len(list(WP_TEMPLATES_DIR.rglob("*.docx"))),
        "total_placeholders": len(unique_entries),
        "placeholders": unique_entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(f"Done! {len(unique_entries)} unique placeholders found.")
    print(f"Output: {OUTPUT_PATH}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
