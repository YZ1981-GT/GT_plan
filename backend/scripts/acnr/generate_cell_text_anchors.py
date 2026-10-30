"""ACNR 目录单元格 → 网页文字锚点对照（spec wp-deeplink-locate-coverage-closure 需求 2.2，design §3）。

读已提交目录，取未停用、purpose=conclusion、语义标签为「审计结论」的单元格（模板核对后的「审计结论」标签格），
按所属 sheet 的 sheet_code 写出 `audit-platform/frontend/src/generated/catalogTextAnchors.ts`：
`{ [sheet_code]: { [A1]: '审计结论' } }`。渲染器在组件钩子与 `[data-cell-ref]` 都找不到时，按它在本渲染器根元素内找
唯一、可见的同名标题。目录变了须重新生成。只依赖标准库。

用法（cwd 任意）：
    python backend/scripts/acnr/generate_cell_text_anchors.py --write   # 写出（内容不变不写）
    python backend/scripts/acnr/generate_cell_text_anchors.py --check   # 与已提交文件比对，不同退出 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
CATALOG = _REPO / "backend" / "data" / "acnr" / "global_catalog.json"
OUTPUT = _REPO / "audit-platform" / "frontend" / "src" / "generated" / "catalogTextAnchors.ts"
#: 目录 cell 的语义标签 → 网页标题文字（目前只有审计结论区）
ANCHOR_TEXTS = {"审计结论": "审计结论"}


def build(catalog: dict) -> dict[str, dict[str, str]]:
    sheets = {s["addr_id"]: s for s in catalog.get("sheets", [])}
    out: dict[str, dict[str, str]] = {}
    for c in catalog.get("cells", []):
        text = ANCHOR_TEXTS.get(c.get("semantic_label") or "")
        if c.get("deprecated") or c.get("purpose") != "conclusion" or not text or not c.get("cell_address"):
            continue
        sheet = sheets.get(c.get("parent_addr_id", "")) or {}
        if sheet.get("deprecated") or not sheet.get("sheet_code"):
            continue
        out.setdefault(sheet["sheet_code"], {})[c["cell_address"]] = text
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def _q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def render(anchors: dict[str, dict[str, str]]) -> str:
    lines = [
        "/**",
        " * ACNR 目录单元格 → 网页文字锚点（spec wp-deeplink-locate-coverage-closure 需求 2）。",
        " *",
        " * @generated 由 backend/scripts/acnr/generate_cell_text_anchors.py 从 backend/data/acnr/global_catalog.json 生成，勿手改；",
        " * 校验：python backend/scripts/acnr/generate_cell_text_anchors.py --check（目录里结论格变了须重新生成）",
        " */",
        "",
        "export const CATALOG_TEXT_ANCHORS: Readonly<Record<string, Readonly<Record<string, string>>>> = {",
    ]
    for code, cells in anchors.items():
        body = ", ".join(f"{a1}: {_q(text)}" for a1, text in cells.items())
        lines.append(f"  {_q(code)}: {{ {body} }},")
    lines += [
        "}",
        "",
        "/** sheet 编码 + A1 → 锚点文字（编码与 A1 都去空白、不分大小写）；没有登记返回 null */",
        "export function catalogTextAnchor(sheetCode: string | null | undefined, cellRef: string | null | undefined): string | null {",
        "  if (!sheetCode || !cellRef) return null",
        "  return CATALOG_TEXT_ANCHORS[sheetCode.trim().toUpperCase()]?.[cellRef.trim().toUpperCase()] ?? null",
        "}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACNR 单元格文字锚点对照（写出 / 比对）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    anchors = build(catalog)
    text = render(anchors)
    current = OUTPUT.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") if OUTPUT.exists() else None
    n = sum(len(v) for v in anchors.values())
    if args.write:
        if current == text:
            print(f"[text-anchors] 内容未变化，不写文件（{len(anchors)} 张表 / {n} 格）")
            return 0
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"[text-anchors] 已写出 {len(anchors)} 张表 / {n} 格")
        return 0
    if current != text:
        print("[text-anchors] 漂移：catalogTextAnchors.ts 与目录现算不一致（目录变了未重新生成，或被手改）", file=sys.stderr)
        return 2
    print(f"[text-anchors] OK — {len(anchors)} 张表 / {n} 格，与目录一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
