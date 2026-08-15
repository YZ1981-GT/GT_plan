#!/usr/bin/env python
"""变异检验：改造后的守卫判据是否仍有区分能力。

spec: .kiro/specs/guard-assertion-attribution-refactor/ Task 7
Requirements: 7.1, 7.2  |  Property 16

## 为什么必须做

`disclosureSharedTableRowScope.spec.ts` 的 7 条「全局等值」断言被换成
「地板 + 结构不变式 + 包含式重点项」后，套件从「7 红 + 1 真红」变成 16 全绿。
但**判据变宽了**是事实 —— 必须逐条证明它在真实违规下仍打红，否则就是把
假红换成了空转（本 spec 要治的病之一）。

## 变异安全纪律

🔴 **绝不直接改** `backend/data/note_shared_table_segments.json`
（并发会话可能正在读它）。一律走临时副本 + `GUARD_MANIFEST_OVERRIDE` 环境变量
重定向；被测 spec 支持该变量时用副本，否则退化为**改 spec 文件自身**并在
`finally` 里恢复 + md5 二次校验。

## 四态判定

- RED         打红且命中预期测试名 → 通过
- GREEN       没打红 → 守卫缺陷
- ANCHOR-MISS 锚点未命中或命中 >1 处 → 脚本缺陷
- WRONG-TEST  打红了但不是预期测试 → 污染残留或锚点错行

用法::

    python backend/scripts/check/mutate_guard_attribution.py --list
    python backend/scripts/check/mutate_guard_attribution.py --only M1
    python backend/scripts/check/mutate_guard_attribution.py --all
    python backend/scripts/check/mutate_guard_attribution.py --restore
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in [here.parent, *here.parents]:
        if (cand / "audit-platform" / "frontend" / "package.json").exists() and (
            cand / "backend" / "tests"
        ).is_dir():
            return cand
    raise RuntimeError("找不到仓库根")


REPO_ROOT = _find_repo_root()
FRONTEND = REPO_ROOT / "audit-platform" / "frontend"
GUARD_REL = "src/components/workpaper/__tests__/disclosureSharedTableRowScope.spec.ts"
GUARD = FRONTEND / GUARD_REL
MANIFEST = REPO_ROOT / "backend" / "data" / "note_shared_table_segments.json"


@dataclass
class Mutation:
    id: str
    desc: str
    #: 作用对象：`guard`（改守卫源码）| `manifest`（改真源副本）
    target: str
    #: guard 型：(锚点原文, 替换文本)
    anchor: str = ""
    replacement: str = ""
    #: manifest 型：改动函数名
    manifest_op: str = ""
    #: 期望打红的测试名片段
    expect_test: str = ""


MUTATIONS: list[Mutation] = [
    Mutation(
        id="M1",
        desc="破坏结构不变式：counts 之和 ≠ tables 条数（模拟生成器算错分组）",
        target="manifest",
        manifest_op="break_counts_sum",
        expect_test="结构不变式",
    ),
    Mutation(
        id="M2",
        desc="真源清单截断到地板以下（模拟真源被清空 / 路径漂移）",
        target="manifest",
        manifest_op="truncate_tables",
        expect_test="地板",
    ),
    Mutation(
        id="M3",
        desc="抹掉全部 data_end ≠ end（模拟 data_end 机制整体失效）",
        target="manifest",
        manifest_op="flatten_data_end",
        expect_test="地板",
    ),
    Mutation(
        id="M4",
        desc="抹掉 soe 八、93 的窄可写区（归因断言：高优先级表必须在窄段清单里）",
        target="manifest",
        manifest_op="widen_893",
        expect_test="归因",
    ),
    Mutation(
        id="M5",
        desc="给外币表造一个窄可写区（归因断言：外币表必须零影响）",
        target="manifest",
        manifest_op="narrow_fx",
        expect_test="归因",
    ),
    Mutation(
        id="M6",
        desc="重点共享表改名（包含式断言：外币货币性项目必须在可扫描清单）",
        target="manifest",
        manifest_op="rename_fx_table",
        expect_test="可扫描表名地板",
    ),
    Mutation(
        id="M7",
        desc="脏名登记表加一条真源里没有的名字（形态 A：该移出的必须报出来）",
        target="guard",
        anchor="const GENERIC_TABLE_NAMES: Record<string, string> = {",
        replacement=(
            "const GENERIC_TABLE_NAMES: Record<string, string> = {\n"
            "  这个表名真源里绝不存在: '变异检验注入的条目，用于验证 stale 检测仍生效',"
        ),
        expect_test="脏表名登记表",
    ),
    Mutation(
        id="M8",
        desc="整表覆盖风险登记表移除 K3 条目但不修 k3NoteSectionMap（真红必须回来）",
        target="guard",
        anchor="  其他应付款: {",
        replacement="  其他应付款_已移出用于变异检验: {",
        expect_test="推共享表必带 _row_scope",
    ),
    # 🔴 M9 首版是 ANCHOR-MISS（被误判为 GREEN）：`reason` 是**多行字符串拼接**，
    #    只替换第一行时后续 `+ '...'` 续行仍在 ⇒ 拼接结果依旧很长 ⇒ 长度门槛不触发。
    #    教训：改多行拼接字段时，锚点必须落在**判据真正读的那个特征**上，
    #    而不是「看起来像整个值」的第一行。
    Mutation(
        id="M9",
        desc="登记理由里的 `_row_scope` 拼错（判据：理由须点明未声明 _row_scope）",
        target="guard",
        anchor="推该表未声明 `_row_scope` ⇒ 表级整表覆盖会清掉 `BS-016`",
        replacement="推该表未声明 `_rowscope` ⇒ 表级整表覆盖会清掉 `BS-016`",
        expect_test="整表覆盖风险登记表",
    ),
    Mutation(
        id="M10",
        desc="登记表 owner 写成非 spec 目录名格式（判据：owner 必须是 spec 目录名）",
        target="guard",
        anchor=(
            "      + '（声明 `owner_row_code: BS-050` 后该行会被服务端丢弃）。',\n"
            "    owner: 'k-cycle-extraction-formula-and-disclosure-closure',"
        ),
        replacement=(
            "      + '（声明 `owner_row_code: BS-050` 后该行会被服务端丢弃）。',\n"
            "    owner: 'K 循环 Spec（非目录名）',"
        ),
        expect_test="整表覆盖风险登记表",
    ),
    # 🔴 M11 的期望值经实测修正：条目表名写错 ⇒ **豁免失效** ⇒ `全量扫描` 那条
    #    立刻报 K1 的真红，而不是由登记表自检报「条目名不对」。
    #    这其实是更强的保护（直接暴露被豁免掉的真实风险），故按实际行为登记期望值。
    #    代价（如实记）：登记表的天花板设计（`stale ≤ 2`，为与真源规模解耦）
    #    使「单条条目名写错」不再被登记表自身抓出 —— 但它必然从 `全量扫描` 侧暴露。
    Mutation(
        id="M11",
        desc="登记表条目改成真源里不存在的表名 ⇒ 豁免失效，K1 的真红必须回来",
        target="guard",
        anchor="  其他应收款: {",
        replacement="  其他应收款_真源里不存在这个名字: {",
        expect_test="推共享表必带 _row_scope",
    ),
]


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _norm_eol(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _replace_eol_safe(text: str, anchor: str, replacement: str) -> tuple[str | None, int]:
    """行尾无关的单次替换，写回时保持原文件行尾。

    🔴 平台铁律：**含 `\\n` 的多行锚点在 CRLF 文件里必 MISS**。首版 M10 就是这么设计的，
    在本仓（`.gitattributes` 让工作区为 CRLF）会 0 命中被判 ANCHOR-MISS。
    这里统一先归一化为 LF 做匹配，写回时按原文件行尾还原 —— 避免整文件 diff。

    返回 `(新文本 | None, 命中次数)`；命中 ≠ 1 时新文本为 None。
    """
    norm = _norm_eol(text)
    a = _norm_eol(anchor)
    hits = norm.count(a)
    if hits != 1:
        return (None, hits)
    # 归一化后返回：调用方用 `write_text`（默认 newline）写回，Windows 上自动转 CRLF，
    # 与 `read_text` 的通用换行模式往返一致 ⇒ 恢复时能字节级还原（md5 校验保证）
    return (norm.replace(a, _norm_eol(replacement), 1), 1)


def _mutate_manifest(op: str, data: dict) -> dict:
    """在**内存副本**上施加真源变异（绝不写回原文件）。"""
    if op == "break_counts_sum":
        data["counts"]["listed"] = data["counts"]["listed"] + 1
    elif op == "truncate_tables":
        keep = data["tables"][:3]
        data["tables"] = keep
        data["counts"] = {
            "listed": sum(1 for t in keep if t["variant"] == "listed"),
            "soe": sum(1 for t in keep if t["variant"] == "soe"),
        }
    elif op == "flatten_data_end":
        for t in data["tables"]:
            for s in t["segments"]:
                s["data_end"] = s["end"]
    elif op == "widen_893":
        for t in data["tables"]:
            if t["section_number"].startswith("八、93"):
                for s in t["segments"]:
                    s["data_end"] = s["end"]
    elif op == "narrow_fx":
        for t in data["tables"]:
            if t["table_name"] == "外币货币性项目":
                s = t["segments"][0]
                if s["data_end"] > s["start"] + 1:
                    s["data_end"] = s["start"] + 1
    elif op == "rename_fx_table":
        for t in data["tables"]:
            if t["table_name"] == "外币货币性项目":
                t["table_name"] = "外币货币性项目_变异改名"
    else:
        raise ValueError(f"未知 manifest_op: {op}")
    return data


def _run_guard() -> tuple[bool, str]:
    """跑被测守卫，返回 (是否全绿, 输出)。"""
    proc = subprocess.run(
        ["cmd", "/c", "npx", "vitest", "run", GUARD_REL, "--reporter=dot"],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # 🔴 判「是否全绿」用 **vitest 退出码 + 摘要行**，不用 `"failed" not in out`
    #    —— 首版那么写被输出里的其它文本骗了（断言消息里含 `fail-closed` 等字样），
    #    导致「变异前守卫本身就是红的」误报，把整轮变异挡在门外。
    summary_failed = re.search(r"Test Files\s+\d+ failed", out)
    green = proc.returncode == 0 and not summary_failed
    return (green, out)


def _classify(green: bool, out: str, expect_test: str) -> str:
    if green:
        return "GREEN"
    failed_names = re.findall(r"FAIL[^\n]*?>\s*([^\n]+)", out)
    blob = " ".join(failed_names)
    if expect_test and expect_test not in blob and expect_test not in out:
        return "WRONG-TEST"
    return "RED"


def run_one(m: Mutation) -> tuple[str, str]:
    """施加变异 → 跑守卫 → 恢复。返回 (四态, 摘要)。"""
    guard_backup = GUARD.read_text(encoding="utf-8")
    guard_md5 = _md5(GUARD)
    manifest_backup = MANIFEST.read_text(encoding="utf-8")
    manifest_md5 = _md5(MANIFEST)
    note = ""

    try:
        if m.target == "guard":
            mutated, hits = _replace_eol_safe(guard_backup, m.anchor, m.replacement)
            if mutated is None:
                return ("ANCHOR-MISS", f"锚点命中 {hits} 次（须恰好 1）")
            # 不传 newline：与 `read_text` 的默认通用换行模式往返一致
            #（read 把 CRLF 读成 LF，write 在 Windows 上转回 CRLF ⇒ 字节级还原）
            GUARD.write_text(mutated, encoding="utf-8")
        else:
            data = json.loads(manifest_backup)
            before = json.dumps(data, ensure_ascii=False, sort_keys=True)
            data = _mutate_manifest(m.manifest_op, data)
            after = json.dumps(data, ensure_ascii=False, sort_keys=True)
            if before == after:
                return ("ANCHOR-MISS", f"manifest_op {m.manifest_op} 未产生任何改动")
            # 🔴 真源是共享文件：写前记 md5，`finally` 里逐字节复原
            MANIFEST.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        green, out = _run_guard()
        state = _classify(green, out, m.expect_test)
        failed = re.findall(r"FAIL[^\n]*?>\s*([^\n]{0,70})", out)
        note = f"打红 {len(set(failed))} 项：{'; '.join(sorted(set(failed))[:3])}" if failed else "全绿"
        return (state, note)
    finally:
        GUARD.write_text(guard_backup, encoding="utf-8")
        MANIFEST.write_text(manifest_backup, encoding="utf-8")
        # 二次校验：逐字节恢复
        bad = []
        if _md5(GUARD) != guard_md5:
            bad.append(str(GUARD))
        if _md5(MANIFEST) != manifest_md5:
            bad.append(str(MANIFEST))
        if bad:
            print(f"[FATAL] 恢复失败，请手工检查：{bad}", file=sys.stderr)
            raise SystemExit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", help="只跑指定锚点（如 M1）")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--restore", action="store_true", help="仅校验两个文件是否干净")
    args = ap.parse_args()

    if args.list:
        print(f"共 {len(MUTATIONS)} 个锚点：")
        for m in MUTATIONS:
            print(f"  {m.id:4} [{m.target:8}] {m.desc}")
            print(f"       期望打红：{m.expect_test}")
        return 0

    if args.restore:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", GUARD_REL, "backend/data/note_shared_table_segments.json"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        print(proc.stdout or "(两个文件均干净)")
        return 0

    todo = [m for m in MUTATIONS if not args.only or m.id == args.only]
    if not todo:
        print(f"没有匹配 {args.only} 的锚点", file=sys.stderr)
        return 1

    # 前置：未变异时必须全绿，否则四态判定不可信
    green, _ = _run_guard()
    if not green:
        print("[ERROR] 变异前守卫本身就是红的 —— 先修好再做变异检验", file=sys.stderr)
        return 1
    print(f"前置检查：未变异时守卫全绿 ✓\n")

    results: list[tuple[str, str, str]] = []
    for m in todo:
        print(f"--- {m.id} {m.desc}")
        state, note = run_one(m)
        results.append((m.id, state, note))
        print(f"    → {state}  {note}\n")

    print("=" * 60)
    tally: dict[str, int] = {}
    for _id, state, _n in results:
        tally[state] = tally.get(state, 0) + 1
    print(f"四态统计：{tally}")
    for i, state, note in results:
        print(f"  {i:4} {state:12} {note[:80]}")
    ok = all(s == "RED" for _i, s, _n in results)
    print("\n全部 RED ✓" if ok else "\n存在非 RED —— 判据有缺陷或脚本锚点失效")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
