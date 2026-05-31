"""自动生成 docs/README.md 索引。

每次新增 / 删除 / 重命名 docs/ 下文档后跑：
    python backend/scripts/regen_docs_index.py

策略：
- 扫描 docs/ 真实文件结构 + 按子目录分类
- 自动统计每个子目录的文件数
- 输出有"用途/文件清单"的 markdown 索引
- 顶部自动加 "auto-generated" 警告，避免手动改

为了"工具化保活"，这是一个永久工具（无 `_` 前缀），按需跑。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"

# 子目录用途说明（手动维护，新加子目录时补）
SUBDIR_DESC = {
    "adr": "架构决策记录（ADR）",
    "architecture": "系统架构与模块设计",
    "deployment": "部署与运维手册",
    "frontend": "前端专项指南",
    "i18n": "国际化与术语表",
    "operations": "运维剧本（健康度/降级/工作流）",
    "proposals": "设计建议书（含历史版本）",
    "reference": "参考手册（变更日志/配置/对齐/DSL）",
    "templates": "文档/代码模板",
    "uat": "UAT 验收报告与产物",
}


def list_md_files(d: Path) -> list[Path]:
    """列出目录下所有 .md（含子目录如 phase8/），按文件名排序。"""
    if not d.is_dir():
        return []
    return sorted(d.rglob("*.md"))


def list_other_files(d: Path) -> list[Path]:
    """列出非 .md 文件（如 docx）。"""
    if not d.is_dir():
        return []
    result = []
    for f in d.rglob("*"):
        if f.is_file() and f.suffix.lower() not in (".md",):
            result.append(f)
    return sorted(result)


def get_first_heading(p: Path) -> str:
    """读 markdown 文件第 1 个 # 标题作为说明。"""
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[:30]:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return p.stem


def fmt_file_line(f: Path, base: Path) -> str:
    rel = f.relative_to(base).as_posix()
    title = get_first_heading(f) if f.suffix == ".md" else f.name
    # 截断过长标题
    if len(title) > 70:
        title = title[:67] + "..."
    return f"- `{rel}` — {title}"


def gen_subdir_section(name: str, base: Path) -> str:
    """生成单个子目录段落。"""
    d = base / name
    md_files = list_md_files(d)
    other_files = list_other_files(d)
    desc = SUBDIR_DESC.get(name, "")
    total = len(md_files) + len(other_files)

    lines = []
    lines.append(f"### `{name}/` — {desc}（{total} 个）")
    lines.append("")
    if not md_files and not other_files:
        lines.append("（空）")
        lines.append("")
        return "\n".join(lines)

    for f in md_files:
        lines.append(fmt_file_line(f, d.parent))
    for f in other_files:
        lines.append(fmt_file_line(f, d.parent))
    lines.append("")
    return "\n".join(lines)


def gen_top_files_section(base: Path) -> str:
    """生成顶层非子目录文件段落（除 README.md 自身）。"""
    files = sorted([
        f for f in base.iterdir()
        if f.is_file() and f.suffix == ".md" and f.name != "README.md"
    ])
    if not files:
        return ""
    lines = ["## 顶层文件", ""]
    for f in files:
        title = get_first_heading(f)
        lines.append(f"- `{f.name}` — {title}")
    lines.append("")
    return "\n".join(lines)


def gen_index_table(base: Path) -> str:
    """子目录概览表。"""
    lines = []
    lines.append("| 子目录 | 用途 | 文件数 |")
    lines.append("|--------|------|-------|")
    for name in sorted(SUBDIR_DESC.keys()):
        d = base / name
        if not d.is_dir():
            continue
        count = len(list_md_files(d)) + len(list_other_files(d))
        desc = SUBDIR_DESC[name]
        lines.append(f"| [`{name}/`](./{name}/) | {desc} | {count} |")
    return "\n".join(lines)


def main() -> int:
    out = []
    out.append("<!-- 自动生成 by backend/scripts/regen_docs_index.py，请勿手动编辑 -->")
    out.append("<!-- 改文件后跑：python backend/scripts/regen_docs_index.py -->")
    out.append("")
    out.append("# 文档索引")
    out.append("")
    out.append(f"按用途分类，统一查阅入口。最后生成：**{date.today().isoformat()}**")
    out.append("")
    out.append("## 目录概览")
    out.append("")
    out.append(gen_index_table(DOCS))
    out.append("")

    # 顶层文件
    top = gen_top_files_section(DOCS)
    if top:
        out.append(top)

    # 各子目录详情
    out.append("## 各子目录详情")
    out.append("")
    for name in sorted(SUBDIR_DESC.keys()):
        if (DOCS / name).is_dir():
            out.append(gen_subdir_section(name, DOCS))

    # 维护规约
    out.append("## 维护规约")
    out.append("")
    out.append("- 新增文档放对应子目录，不要平铺到 `docs/` 根（仅 `requirements.md` / `README.md` 例外）")
    out.append("- 文件名：英文小写 + 连字符（如 `event-cascade-health.md`）")
    out.append("- 文档头部加 `# 标题` 一级标题（脚本提取作为索引说明）")
    out.append("- 新增子目录后在 `regen_docs_index.py` 的 `SUBDIR_DESC` 字典补用途")
    out.append("- 改完跑 `python backend/scripts/regen_docs_index.py` 重生成索引")
    out.append("")

    output = "\n".join(out)
    target = DOCS / "README.md"
    target.write_text(output, encoding="utf-8")

    # 统计输出
    total_files = sum(
        len(list_md_files(DOCS / n)) + len(list_other_files(DOCS / n))
        for n in SUBDIR_DESC if (DOCS / n).is_dir()
    )
    print(f"[OK] 已生成 {target.relative_to(ROOT)}")
    print(f"     子目录: {len([n for n in SUBDIR_DESC if (DOCS / n).is_dir()])}")
    print(f"     文件总数（不含 README/requirements）: {total_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
