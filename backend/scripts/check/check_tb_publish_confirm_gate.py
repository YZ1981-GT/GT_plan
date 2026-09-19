# -*- coding: utf-8 -*-
"""publish-to-tb 显式确认门禁 —— 断言新端点不被「无确认」或「自动」调用。

spec: tb-writeback-explicit-publish-gate 复盘补强 6 / Req 1, 2（Property 1 + 2）。

兄弟守卫 check_tb_writeback_no_direct_call.py 只断言「不再直调旧端点」（Property 5）。
但本 spec 的核心正确性是 Property 1（普通保存/数据变化绝不写 TB）+ Property 2（回写必经
显式确认）——这两条此前只有各循环 gate 单测保护，而单测不约束未来新增组件。若有人新写
组件直调 publish-to-tb 却忘了二次确认，或在 watch/onMounted 里自动调 publishToTb，
旧守卫全绿放行，Req 1/2 静默破掉。本守卫补这个缺口。

判据 A（确认门配对）：任何调 POST .../audit-determination/publish-to-tb 的源文件须满足其一：
  A1 直接门 —— 同文件含 ElMessageBox.confirm / confirmDangerous（现状 46 个走这条）；
  A2 间接门 —— 同审计循环存在含 confirm 的 *Adjudication* 文件（现状 29 个走这条：
     useLxFormData 只负责 post，confirm 在 useLxAdjudication.publishToTb / LxTabAdjudication.vue）。
  A2 只认文件名含 Adjudication 的 confirm —— 实证若放宽到「同循环任意 confirm」，
  useK1FormData 会误配到 useK1AiGenerate / useK1VoucherOcr 的 AI/OCR 确认（非发布门）。

判据 B（禁自动调用）：watch / watchEffect / onMounted / setTimeout / setInterval 的回调体内
不得出现 publishToTb( 调用或 publish-to-tb post —— 那是 Req 1 明令消除的自动回写反模式
（改造前 N1 debounce watcher / M watcher / H3 debounce / H10 mount 自动写皆属此类）。

判据精度：只扫 .ts/.vue 源码、排除测试；先剥注释再匹配；回调体范围用跳字符串的括号配平提取。
命中即 exit 1。自测：backend/tests/scripts/test_check_tb_publish_confirm_gate.py。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from check_tb_writeback_no_direct_call import (  # noqa: E402
    _rel,
    iter_source_files,
    strip_comments,
)
# probe

# 引号字符类用十六进制转义（\x22=" \x27=' \x60=`），避免源码里三种引号嵌套
_Q = r"[\x22\x27\x60]"
_NQ = r"[^\x22\x27\x60]"

PUBLISH_CALL_RE = re.compile(
    r"\.\s*post\s*(?:<[^>]*>)?\s*\(\s*" + _Q + _NQ + r"*audit-determination/publish-to-tb"
)
CONFIRM_RE = re.compile(r"ElMessageBox\s*\.\s*confirm|confirmDangerous")
CYCLE_RE = re.compile(r"(?:use|Gt)?([A-N]\d{1,2})", re.IGNORECASE)
AUTO_HOSTS = ("watchEffect", "watch", "onMounted", "setTimeout", "setInterval")
AUTO_PUBLISH_RE = re.compile(
    r"publishToTb\s*\(|\.\s*post\s*(?:<[^>]*>)?\s*\(\s*" + _Q + _NQ
    + r"*audit-determination/publish-to-tb"
)
_QUOTE_CHARS = ("\x27", "\x22", "\x60")


def cycle_of(path: Path) -> str | None:
    """从文件名提取审计循环码（useL2FormData -> L2 / GtK6HeldForSale -> K6）。"""
    m = CYCLE_RE.search(path.stem)
    return m.group(1).upper() if m else None


def _balanced_end(text: str, open_idx: int) -> int:
    """从 text[open_idx] 的左括号起括号配平，跳过字符串字面量，返回配平下标。"""
    depth = 0
    i, n = open_idx, len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in _QUOTE_CHARS:
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def auto_publish_hits(stripped: str) -> list[tuple[str, int]]:
    """判据 B：返回 [(host, line)] —— 自动触发宿主回调体内出现发布动作的位置。"""
    hits: list[tuple[str, int]] = []
    for host in AUTO_HOSTS:
        for m in re.finditer(r"\b" + host + r"\s*\(", stripped):
            open_idx = stripped.index("(", m.start())
            end = _balanced_end(stripped, open_idx)
            inner = AUTO_PUBLISH_RE.search(stripped[open_idx:end])
            if inner:
                line = stripped[: open_idx + inner.start()].count("\n") + 1
                hits.append((host, line))
    return hits


def build_adjudication_confirm_index(files: list[Path]) -> dict[str, list[str]]:
    """循环码 -> 含 confirm 的 Adjudication 文件名（判据 A2 的配对源）。"""
    idx: dict[str, list[str]] = {}
    for p in files:
        if "adjudication" not in p.stem.lower():
            continue
        if CONFIRM_RE.search(strip_comments(p.read_text(encoding="utf-8", errors="replace"))):
            cyc = cycle_of(p)
            if cyc:
                idx.setdefault(cyc, []).append(p.name)
    return idx


def scan(files: list[Path]) -> list[dict[str, Any]]:
    """扫描全部源文件：判据 B（自动发布）+ 判据 A（无确认发布）。"""
    adj_idx = build_adjudication_confirm_index(files)
    violations: list[dict[str, Any]] = []
    for path in files:
        raw = path.read_text(encoding="utf-8", errors="replace")
        stripped = strip_comments(raw)
        lines = raw.splitlines()
        for host, line in auto_publish_hits(stripped):
            snip = lines[line - 1].strip()[0:200] if line - 1 < len(lines) else str()
            violations.append(dict(kind="auto_publish", file=_rel(path),
                                   line=line, host=host, snippet=snip))
        pub = PUBLISH_CALL_RE.search(stripped)
        if not pub:
            continue
        if CONFIRM_RE.search(stripped):
            continue
        cyc = cycle_of(path)
        if cyc and adj_idx.get(cyc):
            continue
        line = stripped[0:pub.start()].count(chr(10)) + 1
        snip = lines[line - 1].strip()[0:200] if line - 1 < len(lines) else str()
        violations.append(dict(kind="unconfirmed_publish", file=_rel(path),
                               line=line, cycle=cyc, snippet=snip))
    return violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="publish-to-tb 显式确认门禁（禁无确认发布 + 禁自动发布）"
    )
    ap.add_argument("--json", dest="json_path", default=None, help="把 JSON 报告写到此路径")
    args = ap.parse_args(argv)

    files = iter_source_files()
    violations = scan(files)
    unconf = [v for v in violations if v["kind"] == "unconfirmed_publish"]
    auto = [v for v in violations if v["kind"] == "auto_publish"]
    report = {
        "gate": "tb-publish-confirm-gate/1",
        "spec": "tb-writeback-explicit-publish-gate 复盘补强 6 / Req 1,2（Property 1+2）",
        "source_files_scanned": len(files),
        "unconfirmed_publish_hits": len(unconf),
        "auto_publish_hits": len(auto),
        "violations": violations,
        "verdict": "passed" if not violations else "failed",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_path:
        Path(args.json_path).write_text(text, encoding="utf-8")
    print(text)
    if violations:
        print(chr(10) + "检测到 publish-to-tb 发布门违规：")
        for v in auto:
            print("  [自动发布 " + v["host"] + " 回调内] " + v["file"]
                  + ":" + str(v["line"]) + "  " + v["snippet"])
        for v in unconf:
            print("  [无二次确认] " + v["file"] + ":" + str(v["line"]) + "  " + v["snippet"])
        print(
            chr(10) + "修复：①自动发布 —— 回调体内改为仅 emit 通知下游，TB 回写只走用户点击的 "
            "publishToTb（Req 1）；②无二次确认 —— 加 ElMessageBox.confirm 中文二次确认，"
            "或把发布收敛到同循环 Adjudication 的 publishToTb（Req 2）。"
        )
        return 1

    print(chr(10) + "通过：publish-to-tb 全部经显式确认门，且无自动发布路径")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
