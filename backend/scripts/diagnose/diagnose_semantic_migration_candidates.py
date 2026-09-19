"""诊断：语义科目解析迁移的**定向名单**。

spec: semantic-account-resolver-full-rollout（Task 9/10/14/15/18/21/22/25 的定名单前置）

背景：2026-08-03 复盘判定「剩余 31 个策略不该机械迁移」——
这些科目的标准码在项目间基本一致，语义解析买不到东西，而迁移有两类已实证风险
（丢变体行号 / 下游属性不兼容）。**真该迁的是「码在项目间不一致 / 客户仍用旧准则科目」那些**。

本脚本做两件事（只读）：
  1. 扫 render 策略，列出「未真实消费 `resolve_semantic_accounts`」的四表取数策略，
     并从**生产代码**里抽出硬编码的科目码前缀（不是 spec 声明的码 —— 上一轮只对了后者）。
  2. 拿这些码去 `account_chart` 双向对账，判定每个码是否「项目间不一致」，输出分级名单。

用法：
    python backend/scripts/diagnose/diagnose_semantic_migration_candidates.py            # 仅静态扫描
    python backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db       # 连库对账
    python backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db --out tmp.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

RENDER_DIR = BACKEND / "app" / "routers" / "wp_render_strategies"

SKIP_PATTERNS = (
    "_ai", "_import_export", "_service", "_validate", "_ocr", "_engine",
    "_sync", "_export", "_disclosure_io", "_contract_ocr", "_stocktake",
    "_special", "_valuation", "_derecognition", "_peer_policies",
    "_depreciation", "_amortization", "_capitalization", "_dcf",
    "_interest_cap", "_transfer", "_property_ocr", "_plan_sync", "_summary_sync",
)

CONSUME_MARKERS = ("codes_of", "standard_codes_of", "slots", "as_dict",
                   "conflicts", "chart_available")

#: 科目码字面量：4 位起（`1001`），允许 `1231-03` / `1511.01` 形态
_CODE_RE = re.compile(r"""["'](\d{4}(?:[-.]\d{1,3})*)["']""")

#: 明显不是科目码的 4 位数字（年份/尺寸等）
_NOT_CODE = {"2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027",
             "1000", "0000", "9999"}

#: 区间端点常量名（`_F2_INVENTORY_CODE_HI = "1499"` 这类不是真实科目码，
#: 只是 `SUM_TB('1401~1499')` 的边界 → 拿去查 `account_chart` 必然零命中，是假阳性）
_RANGE_BOUND_RE = re.compile(
    r"""(?:_(?:HI|LO|HIGH|LOW|MAX|MIN|BOUND|END|START)\s*[:=][^\n]*|~)\s*["']?(\d{4})""")


def _strip_comments_and_docstrings(src: str) -> str:
    """去注释与三引号串 —— 踩坑说明里常写反例码，不去掉会把说明数成真实引用。"""
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    src = re.sub(r"(?m)#.*$", "", src)
    return src


def _really_consumes(src: str) -> bool:
    recv = re.findall(r"(\w+)\s*=\s*await resolve_semantic_accounts\(", src)
    for var in recv:
        for kw in CONSUME_MARKERS:
            if re.search(rf"\b{re.escape(var)}\s*\.\s*{re.escape(kw)}", src):
                return True
        if re.search(rf"\(\s*{re.escape(var)}\s*[,)]", src):
            return True
    return False


def scan() -> tuple[list[dict], list[str]]:
    """返回 (未迁移策略明细, 已真实迁移的文件名)。"""
    pending, migrated = [], []
    for f in sorted(RENDER_DIR.iterdir()):
        if not (f.name.startswith("_") and f.name.endswith(".py")):
            continue
        if any(x in f.name for x in SKIP_PATTERNS):
            continue
        m = re.match(r"_([a-z]\d+)_", f.name)
        if not m or m.group(1).upper()[0] not in "DEFGHIJKLMN":
            continue
        raw = f.read_text(encoding="utf-8")
        if not any(k in raw for k in ("_fetch_tb", "TbBalance", "ReportLineAccountSpec",
                                      "resolve_report_line_accounts")):
            continue
        wp = m.group(1).upper()
        if "await resolve_semantic_accounts(" in raw and _really_consumes(raw):
            migrated.append(f.name)
            continue
        body = _strip_comments_and_docstrings(raw)
        bounds = set(_RANGE_BOUND_RE.findall(body))
        codes = sorted({c for c in _CODE_RE.findall(body)
                        if c not in _NOT_CODE and c not in bounds})
        pending.append({
            "wp_code": wp,
            "file": f.name,
            "codes": codes,
            "uses_rla": "report_line_accounts import" in body,
            "is_pl": bool(re.search(r"pl_occurrence|debit_amount|credit_amount", body)),
        })
    return pending, migrated


# ---------------------------------------------------------------- DB 对账

async def reconcile(codes: set[str]) -> dict[str, dict]:
    """对每个码做双向对账：它在各项目 client/standard 表里各叫什么名、覆盖几个项目。"""
    import sqlalchemy as sa

    from app.core.database import async_session

    heads = sorted({c.split(".")[0].split("-")[0] for c in codes})
    out: dict[str, dict] = {}
    async with async_session() as db:
        # 🔴 分母必须**按 source 各算** —— client 表只有 8 个项目、standard 有 10 个。
        # 用全局 10 当分母会把「8 个 client 项目全都有」误判成「覆盖残缺 8/10」。
        base = {
            src: n for src, n in (await db.execute(sa.text(
                "SELECT source, COUNT(DISTINCT project_id) FROM account_chart GROUP BY source"
            ))).all()
        }
        rows = (await db.execute(sa.text("""
            SELECT account_code, source,
                   COUNT(DISTINCT project_id) AS projects,
                   ARRAY_AGG(DISTINCT account_name) AS names
              FROM account_chart
             WHERE account_code = ANY(:codes)
             GROUP BY account_code, source
             ORDER BY account_code, source
        """), {"codes": heads})).all()
    blank = lambda: {"base": dict(base), "client": None, "standard": None}
    for code, source, projects, names in rows:
        rec = out.setdefault(code, blank())
        rec[source] = {"projects": projects, "names": sorted(n for n in names if n)}
    for code in heads:
        out.setdefault(code, blank())
    return out


async def reconcile_names(names: set[str]) -> dict[str, list[tuple[str, str, int]]]:
    """**反向**对账：每个语义名称实际挂在哪些码上。

    memory 铁律：「判某码是什么科目必须双向查（① 该码实际叫什么名 ② 该名实际挂哪个码）」。
    正向（码→名）抓不到 F5 的 `6404` 那种「同一名称在不同项目挂不同码」——
    实证 `其他业务成本` 在 6 个项目是 `6402`、在 1 个项目是 `6404`
    → 硬编码任一单码在另一批项目必取空。
    """
    import sqlalchemy as sa

    from app.core.database import async_session

    out: dict[str, list[tuple[str, str, int]]] = {}
    async with async_session() as db:
        rows = (await db.execute(sa.text("""
            SELECT account_name, account_code, source,
                   COUNT(DISTINCT project_id) AS projects
              FROM account_chart
             WHERE account_name = ANY(:names)
             GROUP BY account_name, account_code, source
             ORDER BY account_name, account_code, source
        """), {"names": sorted(names)})).all()
    for name, code, source, projects in rows:
        out.setdefault(name, []).append((code, source, projects))
    return out


def collect_spec_names() -> dict[str, set[str]]:
    """{wp_code: 语义名称集合}，取自各 per-cycle `_specs.py`（gross 槽）。"""
    import importlib

    acc: dict[str, set[str]] = {}
    for mod in ("d_cycle_specs", "f_cycle_specs", "g_cycle_specs", "h_cycle_specs",
                "i_cycle_specs", "l_cycle_specs", "m_cycle_specs", "n_cycle_specs"):
        try:
            m = importlib.import_module(f"app.services.four_table.{mod}")
        except Exception:  # noqa: BLE001 — 缺模块不阻断诊断
            continue
        table = next((getattr(m, a) for a in dir(m)
                      if a.endswith("_CYCLE_SPECS") and isinstance(getattr(m, a), dict)), None)
        if not table:
            continue
        for wp, spec in table.items():
            for slot in getattr(spec, "slots", ()):
                acc.setdefault(wp, set()).update(slot.names)
    return acc


def classify(code: str, rec: dict) -> tuple[str, str]:
    """(等级, 理由)。等级 ∈ {MIGRATE, WATCH, SKIP}。"""
    base = rec.get("base") or {}
    cl, st = rec.get("client"), rec.get("standard")
    cl_names = set(cl["names"]) if cl else set()
    st_names = set(st["names"]) if st else set()

    if not cl and not st:
        return "MIGRATE", "全库 account_chart 零命中 —— 硬编码码在任何项目都取不到数"

    # 一码两义：client 与 standard 名称完全不相交
    if cl_names and st_names and not (cl_names & st_names):
        return "MIGRATE", (
            f"一码两义：client={sorted(cl_names)} vs standard={sorted(st_names)}"
            " —— 走错表会取到完全不同的科目"
        )

    # 同一 source 内出现多个不同名称
    for src, names in (("client", cl_names), ("standard", st_names)):
        if len(names) > 1:
            n = {nm: None for nm in sorted(names)}
            return "MIGRATE", f"{src} 表内一码多名（项目间不一致）：{sorted(n)}"

    # 覆盖率残缺：按 source **各自的**项目基数判定
    frags = []
    worst = 1.0
    for src in ("client", "standard"):
        info = rec.get(src)
        tot = base.get(src) or 0
        if not info or not tot:
            continue
        ratio = info["projects"] / tot
        frags.append(f"{src} {info['projects']}/{tot}")
        worst = min(worst, ratio)
    detail = " · ".join(frags) or "无数据"
    if worst < 1.0:
        lvl = "MIGRATE" if worst < 0.5 else "WATCH"
        return lvl, f"科目覆盖残缺（{detail}）—— 缺失项目取数为空"

    return "SKIP", f"码↔名在全部项目一致（{detail}），语义解析买不到东西"


def split_names(name_recon: dict[str, list[tuple[str, str, int]]],
                spec_names: dict[str, set[str]],
                pending_wps: set[str]) -> list[tuple[str, list[str], list[str]]]:
    """名→码一名多码的名称清单：(名称, 认领它的 wp_code, 码明细)。"""
    owner: dict[str, list[str]] = defaultdict(list)
    for wp, names in spec_names.items():
        if wp not in pending_wps:
            continue
        for n in names:
            owner[n].append(wp)

    out = []
    for name, hits in sorted(name_recon.items()):
        if name not in owner:
            continue
        codes = {c for c, _s, _p in hits}
        if len(codes) < 2:
            continue
        detail = [f"`{c}`({s} {p}项目)" for c, s, p in hits]
        out.append((name, sorted(owner[name]), detail))
    return out


def render_report(pending: list[dict], migrated: list[str],
                  recon: dict[str, dict] | None,
                  name_split: list[tuple[str, list[str], list[str]]] | None = None) -> str:
    L: list[str] = []
    L.append("# 语义科目解析迁移 — 定向名单\n")
    L.append(f"- 已真实迁移（消费解析结果）：**{len(migrated)}** 个策略")
    L.append(f"- 未迁移的四表取数策略：**{len(pending)}** 个\n")

    if recon is None:
        L.append("> 未连库（加 `--db` 做码↔名双向对账）\n")

    L.append("## 一、未迁移策略与其生产代码硬编码码\n")
    L.append("| wp_code | 文件 | 硬编码码 | 用 RLA | 损益类 |")
    L.append("|---|---|---|---|---|")
    for p in pending:
        codes = ", ".join(f"`{c}`" for c in p["codes"]) or "—"
        L.append(f"| {p['wp_code']} | `{p['file']}` | {codes} "
                 f"| {'是' if p['uses_rla'] else '否'} | {'是' if p['is_pl'] else '否'} |")

    if recon is None:
        return "\n".join(L) + "\n"

    # 码 → 认领它的 wp_code 列表
    claimers: dict[str, list[str]] = defaultdict(list)
    for p in pending:
        for c in p["codes"]:
            head = c.split(".")[0].split("-")[0]
            if p["wp_code"] not in claimers[head]:
                claimers[head].append(p["wp_code"])

    buckets: dict[str, list[tuple[str, str, list[str]]]] = defaultdict(list)
    for head in sorted(claimers):
        rec = recon.get(head)
        if not rec:
            continue
        lvl, why = classify(head, rec)
        buckets[lvl].append((head, why, claimers[head]))

    L.append("\n## 二、码↔名双向对账结论\n")
    titles = {
        "MIGRATE": "### 🔴 应迁移（码在项目间不一致 / 零命中 / 一码两义）",
        "WATCH": "### 🟡 需复核（覆盖残缺但过半项目有）",
        "SKIP": "### ⚪ 不必迁移（码在项目间一致，语义解析无收益）",
    }
    for lvl in ("MIGRATE", "WATCH", "SKIP"):
        rows = buckets.get(lvl, [])
        L.append(f"{titles[lvl]}（{len(rows)} 个码）\n")
        if not rows:
            L.append("（无）\n")
            continue
        L.append("| 码 | 认领方 | 判定依据 |")
        L.append("|---|---|---|")
        for head, why, wps in rows:
            L.append(f"| `{head}` | {', '.join(sorted(wps))} | {why} |")
        L.append("")

    hot = {w for _, _, wps in buckets.get("MIGRATE", []) for w in wps}
    warm = {w for _, _, wps in buckets.get("WATCH", []) for w in wps}

    L.append("\n## 三、反向对账（名→码）：同一名称挂在多个码上\n")
    L.append("> 正向（码→名）抓不到这类 —— 硬编码任一单码在另一批项目必取空。\n")
    if not name_split:
        L.append("（无）\n")
    else:
        L.append("| 语义名称 | 认领方 | 实际挂载的码 |")
        L.append("|---|---|---|")
        for name, wps, detail in name_split:
            L.append(f"| {name} | {', '.join(wps)} | {' · '.join(detail)} |")
            hot.update(wps)
        L.append("")

    L.append("\n## 四、按策略汇总\n")
    L.append(f"- 🔴 **应迁移**（{len(hot)}）：{', '.join(sorted(hot)) or '—'}")
    L.append(f"- 🟡 **需复核**（{len(warm - hot)}）：{', '.join(sorted(warm - hot)) or '—'}")
    rest = {p["wp_code"] for p in pending} - hot - warm
    L.append(f"- ⚪ **可不迁移**（{len(rest)}）：{', '.join(sorted(rest)) or '—'}")
    L.append("\n> 🟡「覆盖残缺」**不是迁移理由** —— 部分项目没有某科目多半是业务事实"
             "（该公司确实没有应付票据）。它要求的是策略正确呈现「本项目无此科目」"
             "而不是取 0，属 `isAccountAbsent()` 的活。\n")
    return "\n".join(L) + "\n"


async def _reconcile_all(pending: list[dict]):
    """单事件循环内跑完正向 + 反向两轮对账。"""
    codes = {c for p in pending for c in p["codes"]}
    recon = await reconcile(codes)

    spec_names = collect_spec_names()
    pending_wps = {p["wp_code"] for p in pending}
    wanted = {n for wp, ns in spec_names.items() if wp in pending_wps for n in ns}
    name_split = None
    if wanted:
        name_split = split_names(await reconcile_names(wanted), spec_names, pending_wps)
    return recon, name_split


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="连库做码↔名双向对账")
    ap.add_argument("--out", help="报告写盘路径（默认打印到 stdout）")
    args = ap.parse_args()

    pending, migrated = scan()
    recon = None
    name_split = None
    if args.db:
        os.environ.setdefault("DB_DISABLE_SSL", "True")
        # 🔴 两次查询必须在**同一个** asyncio.run 内 —— 连接池绑定首个事件循环，
        # 第二次 asyncio.run 会拿到已关闭的 transport（AttributeError: NoneType.send）。
        recon, name_split = asyncio.run(_reconcile_all(pending))

    report = render_report(pending, migrated, recon, name_split)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
