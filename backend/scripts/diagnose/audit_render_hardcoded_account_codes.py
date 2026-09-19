"""扫描 render 策略生产代码里的**硬编码科目码**，并按 `account_chart` 双向对账。

**为什么需要这个（spec 判定的真待办）**

`.kiro/specs/semantic-account-resolver-full-rollout/tasks.md` 底部实证结论：
机械迁移 70 个策略「买不到东西」（大多数标准码在项目间一致），
**真该迁的是「码在项目间不一致 / 客户仍用旧准则科目」那些**。
定这个名单的前提 = 把各策略**生产代码里的硬编码前缀**逐个按 `account_chart` 双向对账
—— 此前只对过 `*_cycle_specs.py` 里声明的码，生产代码的前缀没对过。

**已知候选信号**（spec 记录）：`4001`/`4101`/`4401`/`4301` 一码两义
（client = 会计口径 / standard = 成本类口径），5 个项目走 standard 会取到
生产成本 / 制造费用 / 工程施工 / 研发支出。

**输出**（只读，不改任何代码）::

    python backend/scripts/diagnose/audit_render_hardcoded_account_codes.py --scan
        仅静态扫描：每个策略文件里的硬编码码 + 出现位置

    python backend/scripts/diagnose/audit_render_hardcoded_account_codes.py --reconcile
        连库双向对账：每个码在 client / standard 科目表里各叫什么名、
        跨项目是否一致、是否一码两义 → 产出「真该迁」名单

spec: .kiro/specs/semantic-account-resolver-full-rollout/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
STRATEGY_DIR = BACKEND / "app" / "routers" / "wp_render_strategies"

#: 科目码字面量：4~6 位纯数字，或带点号/横杠的层级码
_CODE_RE = re.compile(r"""['"](\d{4}(?:[.\-]\d{1,3})*)['"]""")

#: 明显不是科目码的 4 位数字（年份 / 端口 / HTTP 码 / 像素）
_NOT_CODE = {
    "1000", "2000", "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    "2027", "2028", "2029", "2030", "3000", "4000", "5000", "8000", "9980",
    "1024", "1200", "1080", "1920",
}

#: 注释/docstring 里的码不算生产代码
def strip_py(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    return src


def scan_file(path: Path) -> dict[str, list[int]]:
    """返回 ``{科目码: [行号...]}``（已剥注释与 docstring）。"""
    raw = path.read_text(encoding="utf-8")
    stripped = strip_py(raw)
    # 用剥后文本判定「是否生产代码」，用原文本定行号
    prod_codes: set[str] = {
        c for c in _CODE_RE.findall(stripped)
        if c.split(".")[0].split("-")[0] not in _NOT_CODE
    }
    out: dict[str, list[int]] = defaultdict(list)
    for i, line in enumerate(raw.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for c in _CODE_RE.findall(line):
            if c in prod_codes:
                out[c].append(i)
    return dict(out)


def cmd_scan() -> dict[str, dict[str, list[int]]]:
    result: dict[str, dict[str, list[int]]] = {}
    for path in sorted(STRATEGY_DIR.glob("_*.py")):
        hits = scan_file(path)
        if hits:
            result[path.name] = hits
    return result


async def cmd_reconcile(scan: dict[str, dict[str, list[int]]]) -> int:
    sys.path.insert(0, str(BACKEND))
    import sqlalchemy as sa
    from app.core.database import async_session

    all_codes = sorted({c for hits in scan.values() for c in hits})
    # 只对一级码（4 位）做科目表对账；子科目按前缀继承
    top_codes = sorted({c.split(".")[0].split("-")[0] for c in all_codes})

    async with async_session() as db:
        rows = (await db.execute(sa.text(
            "SELECT project_id, source, account_code, account_name "
            "FROM account_chart WHERE account_code = ANY(:codes)"
        ), {"codes": top_codes})).all()

    # {code: {source: {name: {project_id}}}}
    by_code: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    for pid, source, code, name in rows:
        by_code[code][source or "?"][(name or "").strip()].add(str(pid))

    print("=" * 100)
    print("硬编码科目码 × account_chart 双向对账")
    print("=" * 100)
    print(f"策略文件 {len(scan)} 个 / 硬编码码 {len(all_codes)} 个 / 一级码 {len(top_codes)} 个")
    print()

    dual_meaning: list[str] = []
    client_only: list[str] = []
    absent: list[str] = []
    inconsistent: list[str] = []

    for code in top_codes:
        entry = by_code.get(code)
        if not entry:
            absent.append(code)
            continue
        client_names = set(entry.get("client", {}).keys())
        std_names = set(entry.get("standard", {}).keys())
        # 一码两义：client 与 standard 名称集合完全不相交
        if client_names and std_names and not (client_names & std_names):
            dual_meaning.append(code)
        if client_names and not std_names:
            client_only.append(code)
        # 同一 source 下多个不同名 = 跨项目不一致
        for src, names in entry.items():
            if len(names) > 1:
                inconsistent.append(f"{code}[{src}]")

    def show(title: str, codes: list[str], detail: bool = True) -> None:
        print("-" * 100)
        print(f"{title}（{len(codes)} 个）")
        print("-" * 100)
        if not codes:
            print("  （无）")
            return
        for code in codes:
            base = code.split("[")[0]
            print(f"  {code}")
            if not detail:
                continue
            for src, names in sorted(by_code.get(base, {}).items()):
                for name, pids in sorted(names.items()):
                    print(f"      {src:9s} {name!r:40s} ×{len(pids)} 项目")
            users = [f"{f}:{sorted(h[c] for c in h if c.split('.')[0].split('-')[0] == base)[:1]}"
                     for f, h in scan.items()
                     if any(c.split(".")[0].split("-")[0] == base for c in h)]
            print(f"      ← 消费方: {', '.join(u.split(':')[0] for u in users)}")
        print()

    show("[P0] 一码两义（client 与 standard 名称完全不相交 → 按标准码硬查会取到别的科目）", dual_meaning)
    show("[WARN] 跨项目同源不同名（码在项目间语义漂移）", sorted(set(inconsistent)))
    show("[WARN] 只有客户科目表有（标准表无 → 语义定位是唯一可靠途径）", client_only)
    show("[INFO] 两张科目表都没有（宁缺勿造，取数恒空）", absent, detail=False)

    print("=" * 100)
    print("结论：真该迁移的策略 = 消费了上面「一码两义 / 跨项目不同名 / 仅客户表」类码的策略")
    print("=" * 100)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="仅静态扫描")
    ap.add_argument("--reconcile", action="store_true", help="连库双向对账")
    ap.add_argument("--json", type=str, default="", help="扫描结果写盘")
    args = ap.parse_args()

    scan = cmd_scan()

    if args.json:
        Path(args.json).write_text(
            json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[WRITE] {args.json}")

    if args.scan or not args.reconcile:
        total = sum(len(v) for v in scan.values())
        print(f"策略文件 {len(scan)} 个，硬编码科目码出现 {total} 处")
        for name, hits in scan.items():
            codes = ", ".join(f"{c}(L{h[0]})" for c, h in sorted(hits.items()))
            print(f"  {name}: {codes}")

    if args.reconcile:
        return asyncio.run(cmd_reconcile(scan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
