# -*- coding: utf-8 -*-
"""前端 TB 回写直调门禁 —— 断言无绕过显式发布门的直调（旧端点 + G6 变体端点）。

spec: tb-writeback-explicit-publish-gate Task 18 / Req 9.1, 9.2。

方案 B（逐组件改走显式发布端点 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`）
收口后，前端源码里**任何活代码 HTTP 调用**都不得再直调这两类绕过端点：

1. **旧端点**：`PUT|POST /api/projects/{pid}/trial-balance/writeback`（无二次确认/无幂等/
   无 publish_confirmed）—— 字面量 `trial-balance/writeback`。
2. **G6 变体端点**：`POST /api/projects/{pid}/trial_balance`（集合 POST，census 实证零消费死代码，
   task 17 已清）—— 字面量以 `/trial_balance` 结尾的端点段。

🔴 为什么不能用「字面量出现即失败」的粗匹配：改造后各组件保留了**收口注释**（描述性文字
「此前直调旧端点 PUT trial-balance/writeback…」），且测试文件里有 `expect(...).not.toContain(
'trial-balance/writeback')` 这类**守卫断言**。二者都合法引用了字面量，粗匹配会把注释/测试误报成违规。

本门禁的判据精度：
* **只看 .vue / .ts 源码，排除测试**（`__tests__/` 目录、`*.spec.*`、`*.test.*`）—— 测试断言不是调用。
* **先剥注释再匹配** —— 逐字符状态机剥掉 `// 行注释`、`/* 块注释 */`、`<!-- vue 注释 -->`，
  同时保留字符串字面量原样（端点 URL 在字符串里）。收口注释里的字面量因此不再被看见。
* **匹配「HTTP 调用点」而非「字面量出现」** —— 形如 `.put(...trial-balance/writeback...)` /
  `.post(...trial-balance/writeback...)`（api / http / httpApi 任意调用者），即 URL 出现在
  `.put(` / `.post(` 的实参串首段。变体端点同理匹配 `.post(...projects/.../trial_balance)`。

命中即 exit 1，逐条打印 `文件:行`。产出 JSON 报告。stdlib-only，秒级。

自测：`backend/tests/scripts/test_check_tb_writeback_no_direct_call.py`。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Windows 控制台/重定向到文件时默认 GBK，会在打印 ✅/❌ 时抛 UnicodeEncodeError。
# 统一把 stdout/stderr 重配为 UTF-8（CI 上 Linux 本就是 UTF-8，此步幂等无害）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 老 Python / 非 TextIO
        pass

_REPO = Path(__file__).resolve().parents[3]
FRONTEND_SRC = _REPO / "audit-platform" / "frontend" / "src"

#: 旧端点字面量（连字符）。命中即绕过显式发布门。
LEGACY_LITERAL = "trial-balance/writeback"

#: 违规调用点：任意调用者(api/http/httpApi/this.$http 等).put|post( ... '<url 含 LEGACY_LITERAL>' ...
#: 允许调用者前有 `await `、`return ` 等；URL 用反引号/单引号/双引号任一包裹，可有模板插值。
_LEGACY_CALL_RE = re.compile(
    r"\.\s*(?:put|post)\s*(?:<[^>]*>)?\s*\(\s*[`'\"][^`'\"]*" + re.escape(LEGACY_LITERAL)
)

#: G6 变体端点：`.post( ... '/trial_balance'>`（下划线，作为端点路径末段，非 `trial_balance.updated`
#: 事件名、非 `trial_balance` 作为 table/module/source 字符串值）。要求前面是 `projects/.../`
#: 形态的 REST 集合路径且 `/trial_balance` 后紧跟引号或反引号（路径结束）。
_VARIANT_CALL_RE = re.compile(
    r"\.\s*post\s*(?:<[^>]*>)?\s*\(\s*[`'\"][^`'\"]*/trial_balance(?=[`'\"])"
)


def _is_test_file(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if "__tests__" in parts or "__mocks__" in parts:
        return True
    name = path.name.lower()
    return (
        ".spec." in name
        or ".test." in name
        or name.endswith(".stories.ts")
    )


def strip_comments(text: str) -> str:
    """剥掉 JS 行/块注释与 vue `<!-- -->` 注释，保留字符串字面量原样。

    逐字符状态机：识别 `'` `"` 反引号 三种字符串（含 `\\` 转义），字符串内不剥注释；
    字符串外遇 `//` 剥到行尾、遇 `/* */` 剥到块尾、遇 `<!-- -->` 剥到块尾。
    被剥处替换为等量空格（保留行号/列，便于回报精确行）。
    """
    out: list[str] = []
    i, n = 0, len(text)
    quote: str | None = None  # 当前字符串定界符
    while i < n:
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:  # 转义：原样保留下一个字符
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        # 不在字符串内
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            # 行注释：剥到行尾
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            # 块注释：剥到 */
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")  # 吃掉 */
                i += 2
            continue
        if ch == "<" and text.startswith("<!--", i):
            # vue/html 注释：剥到 -->
            while i < n and not text.startswith("-->", i):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("   ")  # 吃掉 -->
                i += 3
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def iter_source_files() -> list[Path]:
    if not FRONTEND_SRC.is_dir():
        raise RuntimeError(
            f"缺前端源码目录 {FRONTEND_SRC} —— 门禁无法判定（禁 fail-open）"
        )
    files: list[Path] = []
    for p in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.vue")):
        if p.is_file() and not _is_test_file(p):
            files.append(p)
    return files


def _rel(path: Path) -> str:
    """相对仓库根的 posix 路径；path 不在仓库下时退回文件名（测试 tmp_path 场景）。"""
    try:
        return str(path.relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return path.name


def scan_file(path: Path) -> list[dict[str, Any]]:
    """返回该文件的违规调用点（已剥注释、排除字符串外的注释误报）。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    stripped = strip_comments(raw)
    raw_lines = raw.splitlines()
    hits: list[dict[str, Any]] = []
    for kind, rx in (("legacy", _LEGACY_CALL_RE), ("variant", _VARIANT_CALL_RE)):
        for m in rx.finditer(stripped):
            line = stripped[: m.start()].count("\n") + 1
            # 回报原始行内容（去首尾空白，便于人读）
            src_line = raw_lines[line - 1].strip() if line - 1 < len(raw_lines) else ""
            hits.append({
                "kind": kind,
                "file": _rel(path),
                "line": line,
                "snippet": src_line[:200],
            })
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="前端 TB 回写直调门禁（旧端点 trial-balance/writeback + G6 变体 trial_balance）"
    )
    parser.add_argument("--json", dest="json_path", default=None,
                        help="把 JSON 报告写到此路径")
    args = parser.parse_args(argv)

    files = iter_source_files()
    violations: list[dict[str, Any]] = []
    for path in files:
        violations.extend(scan_file(path))

    legacy = [v for v in violations if v["kind"] == "legacy"]
    variant = [v for v in violations if v["kind"] == "variant"]

    report = {
        "gate": "tb-writeback-no-direct-call/1",
        "spec": "tb-writeback-explicit-publish-gate Task 18 / Req 9.1, 9.2",
        "source_files_scanned": len(files),
        "legacy_endpoint_hits": len(legacy),   # trial-balance/writeback
        "variant_endpoint_hits": len(variant),  # projects/.../trial_balance
        "violations": violations,
        "verdict": "passed" if not violations else "failed",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)

    if violations:
        print("\n❌ 检测到前端 TB 回写直调（绕过显式发布门 publish-to-tb）：")
        for v in violations:
            label = "旧端点 trial-balance/writeback" if v["kind"] == "legacy" else "G6 变体端点 trial_balance"
            print(f"  [{label}] {v['file']}:{v['line']}  {v['snippet']}")
        print(
            "\n修复：改走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`"
            "（显式二次确认 + writeback_rows + publish_confirmed）。零消费死代码应直接删除。"
        )
        return 1

    print("\n✅ 前端零 TB 回写直调（旧端点 + G6 变体端点均 0 命中）")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
