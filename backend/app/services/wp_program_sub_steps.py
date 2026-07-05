"""程序表 content → 父描述 + 子步骤（与 GtAProgramConsole 展开区对齐）"""

from __future__ import annotations

import re

_STEP_LINE = re.compile(r"^[（\(](\d+)[）\)]\s*(.*)")
_STEP_INLINE = re.compile(r"[（\(](\d+)[）\)]\s*")


def parse_sub_steps(content: str) -> tuple[str, list[dict]]:
    """解析程序 content 为父描述 + 子步骤列表。

    支持：
    - 换行分隔：「…以下工作：\\n（1）…\\n（2）…」
    - 同行连续：（1）…（2）…（常见于 xlsx 单元格）
  """
    if not content:
        return "", []

    text = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "", []

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    parent_lines: list[str] = []
    sub_steps: list[dict] = []
    in_steps = False

    for line in lines:
        m = _STEP_LINE.match(line)
        if m:
            in_steps = True
            sub_steps.append({"no": int(m.group(1)), "text": m.group(2)})
        elif in_steps and sub_steps:
            sub_steps[-1]["text"] += line
        else:
            parent_lines.append(line)

    if sub_steps:
        parent_desc = "\n".join(parent_lines).strip() if parent_lines else parent_lines[0] if parent_lines else ""
        if not parent_desc:
            # 首行即「…：（1）…」混排
            first_line = lines[0]
            m0 = _STEP_INLINE.search(first_line)
            if m0:
                parent_desc = first_line[: m0.start()].strip().rstrip("：:").strip()
        return parent_desc or text.split("\n")[0], sub_steps

    # 单行或多行无换行子步骤 → 尝试同行 （N） 切分
    inline_matches = list(_STEP_INLINE.finditer(text))
    if len(inline_matches) >= 1:
        parent_desc = text[: inline_matches[0].start()].strip().rstrip("：:").strip()
        for i, m in enumerate(inline_matches):
            end = inline_matches[i + 1].start() if i + 1 < len(inline_matches) else len(text)
            step_text = text[m.end() : end].strip()
            if step_text:
                sub_steps.append({"no": int(m.group(1)), "text": step_text})
        if sub_steps:
            return parent_desc or text, sub_steps

    return text, []


def enrich_program_row(row: dict) -> dict:
    """为程序行补全 sub_steps，并将 program_desc 收敛为父描述。"""
    if row.get("sub_steps"):
        return row
    desc = (row.get("program_desc") or row.get("content") or "").strip()
    if not desc:
        return row
    parent_desc, sub_steps = parse_sub_steps(desc)
    if not sub_steps:
        return row
    out = dict(row)
    out["program_desc"] = parent_desc
    out["sub_steps"] = sub_steps
    return out
