"""生成 Spec 功能域目录（.kiro/specs/CATALOG.md）。

用法：
    python backend/scripts/analyze/build_spec_catalog.py            # 生成并打印统计
    python backend/scripts/analyze/build_spec_catalog.py --check    # 只校验，漂移 exit 2

设计（承接 2026-11-25 讨论）：
- 多维归属：一个 spec 可属多个功能域（spec 名模式匹配，规则表 DOMAINS）；
- 代码锚点：每个域登记真实代码模块，生成时核验存在（目录/文件锚点，读盘即可）；
- 幂等输出：无时间戳，内容不变则产物不变（--check 才有意义）；
- 归档区不动：只读 `.kiro/specs`，链接指向现有 `_archive/...` 路径。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / ".kiro" / "specs"
ARCHIVE = SPECS / "_archive"
CATALOG = SPECS / "CATALOG.md"

TASK_LINE = re.compile(r"^[ \t]*- \[([ x~])\]", re.MULTILINE)
SPEC_DOCS = ("requirements.md", "design.md", "tasks.md")


def iter_spec_dirs() -> list[Path]:
    """收集全部 spec 目录：活跃区一级 + _archive 两层（自身含任一件套即 spec）。"""
    out: list[Path] = []
    for d in sorted(SPECS.iterdir()):
        if not d.is_dir() or d.name == "_archive":
            continue
        if any((d / f).exists() for f in SPEC_DOCS):
            out.append(d)
    for a in sorted(ARCHIVE.iterdir()):
        if not a.is_dir():
            continue
        if any((a / f).exists() for f in SPEC_DOCS):
            out.append(a)
            continue
        for sub in sorted(a.iterdir()):
            if sub.is_dir() and any((sub / f).exists() for f in SPEC_DOCS):
                out.append(sub)
    return out


def parse_tasks(d: Path) -> tuple[int, int]:
    p = d / "tasks.md"
    if not p.exists():
        return 0, 0
    marks = TASK_LINE.findall(p.read_text(encoding="utf-8", errors="replace"))
    return sum(1 for m in marks if m == "x"), len(marks)


def first_title(d: Path) -> str:
    for f in SPEC_DOCS:
        p = d / f
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").split("\n"):
            s = line.strip()
            if s.startswith("#"):
                t = s.lstrip("#").strip()
                if t:
                    return t[:90]
    return ""


# ---------------------------------------------------------------------------
# 功能域定义：每个域 = 展示名 + 匹配规则（spec 名正则）+ 代码锚点（经 codegraph 验证）
# 锚点相对仓库根；目录存在性在 build 时核验。
# ---------------------------------------------------------------------------
DOMAINS: list[dict] = [
    {
        "name": "公式管理 / 公式推送 / 取数链",
        "key": "formula",
        "patterns": [
            r"^formula", r"formula-push", r"formula-settings", r"formula-management",
            r"formula-global", r"formula-grammar", r"formula-registry", r"formula-execution",
            r"formula-input", r"formula-provenance", r"formula-e2e", r"formula-template",
            r"formula-fetch", r"formula-hub", r"formula-integrity", r"formula-writer",
            r"unified-formula", r"tb-detail-formulas", r"^s[1-9]-", r"chain-closure-phase2",
            r"fill-all-formulas", r"check-contract-and-note-executor",
        ],
        "anchor": "backend/app/services/formula_push",
        "anchor_alt": "backend/app/routers/formula_push.py",
        "frontend": "audit-platform/frontend/src/components/formula/",
    },
    {
        "name": "附注 / 披露表 / 底稿→附注同步",
        "key": "note",
        "patterns": [
            r"disclosure", r"^note", r"-note-", r"notes-", r"note_", r"soe-listed-note",
            r"parent-company-note", r"restricted-assets", r"semantic-account-resolver",
            r"applicable-standards", r"four-panel-note", r"backend-disclosure-payload",
            r"^d[1-9]-disclosure", r"^s[1-9]", r"^chain-closure-phase",
        ],
        "anchor": "backend/app/routers/disclosure_notes.py",
        "anchor_alt": "backend/app/services/note_table_enrichment.py",
        "frontend": "audit-platform/frontend/src/views/composables/noteDisclosureReverseJump.ts",
    },
    {
        "name": "合并 / 集团 / 三码企业树",
        "key": "consol",
        "patterns": [
            r"^consol", r"consolidat", r"group-tree", r"group-import", r"enterprise-linkage",
            r"tb-reclass", r"partner-manager", r"batch-project",
        ],
        "anchor": "backend/app/routers/consolidation.py",
        "anchor_alt": "backend/app/routers/consol_worksheet.py",
        "frontend": "audit-platform/frontend/src/views/ConsolidationIndex.vue",
    },
    {
        "name": "底稿双向回写 / OO 在线编辑",
        "key": "writeback",
        "patterns": [
            r"workpaper-sync", r"workpaper-sync-cycle", r"bidirectional", r"writeback",
            r"^oo-", r"oo-html", r"oo-formula", r"oo-return", r"oo-writeback", r"oo-single",
            r"onlyoffice", r"published-representation", r"online-edit", r"dual-mode",
            r"d4-bidirectional", r"m-cycle-bidirectional", r"sheet-granularity",
            r"row-table-engine", r"managed-row", r"static-cell", r"materialize",
            r"stored-identity", r"excel-structural", r"excel-template-override",
            r"excel-workbook-wide", r"sync-editor-host", r"frozen-contract",
            r"multi-sheet-materialize", r"static-sheet", r"^wp-sync", r"adjustment-and-analysis",
            r"cycle-lane", r"cycle-sync", r"sync-foundation", r"lanes", r"-lane",
            r"canary", r"variant-axis", r"cross-reference-lane", r"host-inline",
            r"orphan-cleanup", r"orphan-twins", r"carrier", r"composition-closure",
        ],
        "anchor": "backend/app/services/workpaper_sync",
        "anchor_alt": "audit-platform/frontend/src/components/workpaper/sync/",
    },
]


DOMAINS += [
    {
        "name": "A~S 循环底稿业务（科目/程序/检查表）",
        "key": "cycle",
        "patterns": [
            r"^wp-cycle", r"^workpaper-", r"^cycle-", r"-cycle-", r"adjustment-", r"^adj-",
            r"^b[0-9]", r"^c[0-9]", r"^d[0-9]", r"^e[0-9]", r"^f[0-9]", r"^g[0-9]",
            r"^h[0-9]", r"^i[0-9]", r"^j[0-9]", r"^k[0-9]", r"^l[0-9]", r"^m[0-9]",
            r"^n[0-9]", r"^s[0-9]", r"goodwill", r"impairment", r"confirmation-",
            r"cut-off", r"cutoff", r"sampling-", r"voucher-", r"ledger-",
            r"bad-debt", r"aging", r"trial-balance", r"tb-", r"four-table",
            r"extraction", r"prefill", r"endloss", r"endbalance", r"financ", r"bond",
            r"equity", r"payroll", r"tax", r"receivable", r"payable", r"inventory",
            r"fixed-assets", r"intangible", r"lease", r"revenue", r"contract-asset",
            r"misstatement", r"representation", r"analytical", r"going-concern",
            r"subsequent-events", r"related-party", r"estimates", r"fraud",
            r"itgc", r"process-control", r"risk-assessment", r"entity-level",
            r"journal-entry", r"internal-audit", r"deficiency", r"segment",
            r"cash-flow", r"cas-flow", r"audit-summary", r"checklist", r"review-",
            r"evidence-collection", r"wp-locate", r"wp-traceability", r"multi-standard",
            r"cycle-palette", r"cycle-orchestration", r"financial-assets", r"financial-liabilities",
        ],
        "anchor": "backend/app/services/auto_data_resolvers",
        "anchor_alt": "backend/app/services/procedure_trim_engine.py",
    },
    {
        "name": "凭证 / 序时账 / 抽样审计",
        "key": "voucher",
        "patterns": [
            r"^voucher", r"voucher-", r"^ledger", r"ledger-", r"sampling", r"vouching",
        ],
        "anchor": "backend/app/services/voucher_identity.py",
        "anchor_alt": "backend/app/services/voucher_sampling",
        "frontend": "audit-platform/frontend/src/components/workpaper/voucher-sampling/",
    },
    {
        "name": "附件 / 证据 / 归档与交付件",
        "key": "attachment",
        "patterns": [
            r"^attachment", r"attachment-", r"evidence", r"archive", r"deliverable",
            r"word-export", r"signature", r"signoff", r"audit-report", r"report-template",
        ],
        "anchor": "backend/app/services/attachment_service.py",
        "anchor_alt": "backend/app/services/archive_package_builder.py",
        "frontend": "audit-platform/frontend/src/components/deliverable/",
    },
    {
        "name": "知识库 / AI / LLM / OCR",
        "key": "ai",
        "patterns": [
            r"knowledge", r"^llm", r"llm-", r"^ai-", r"-ai-", r"ai-chat", r"ai-task",
            r"ai-review", r"ai-content", r"ai-model", r"dsh", r"ocr", r"vllm",
            r"embedding", r"rerank", r"retrieval", r"chat-", r"doc-level-ai",
        ],
        "anchor": "backend/app/services/ai_chat",
        "anchor_alt": "backend/app/services/knowledge_ocr_worker.py",
        "frontend": "audit-platform/frontend/src/composables/useKnowledge.ts",
    },
    {
        "name": "ACNR 地址坐标名称库 / 交叉引用",
        "key": "acnr",
        "patterns": [r"^acnr", r"acnr-", r"address-registry", r"cross-workpaper", r"deeplink", r"locate"],
        "anchor": "backend/app/services/acnr",
        "anchor_alt": "backend/app/services/address_registry.py",
        "frontend": "audit-platform/frontend/src/components/formula/CellSelector.vue",
    },
    {
        "name": "程序裁剪 / 生成 / 委派 / 权限",
        "key": "procedure",
        "patterns": [
            r"^procedure", r"procedure-", r"trim", r"delegat", r"visibility",
            r"authorization", r"authz", r"rbac", r"role", r"permission", r"identity-only",
            r"project-creation", r"project-pid", r"work-hours", r"workhour",
        ],
        "anchor": "backend/app/services/procedure_trim_engine.py",
        "anchor_alt": "backend/app/services/delegation_guard.py",
    },
    {
        "name": "平台基建 / 性能 / 治理 / 发布",
        "key": "platform",
        "patterns": [
            r"^platform", r"backend-startup", r"runtime-performance", r"reload", r"hotspot",
            r"frontend-prod", r"white-screen", r"release-blocker", r"heavy-jobs", r"capacity",
            r"zero-downtime", r"pg-pooling", r"migration", r"dev-tooling", r"test-",
            r"preexisting", r"guard", r"multi-worker", r"readiness", r"startup-prewarm",
            r"event-loop", r"sse", r"frontend-consistency", r"repo-", r"unification",
            r"drift", r"enum", r"raw-sql", r"workspace", r"maintenance", r"governance",
            r"table-unification", r"display", r"excel-style", r"multi-window", r"editing-lock",
            r"stash", r"recovery", r"api-prefix", r"lan-http", r"insecure-context",
        ],
        "anchor": "backend/app/core/startup_registry.py",
        "anchor_alt": "backend/app/router_registry",
    },
    {
        "name": "高级查询 / 全局 7 横切",
        "key": "global-modules",
        "patterns": [
            r"advanced-query", r"custom-query", r"query-builder", r"enum-dict", r"dictionary",
            r"template-library", r"report-template-library", r"address-library",
        ],
        "anchor": "backend/app/routers/custom_query.py",
        "anchor_alt": "backend/app/routers/advanced_query.py",
    },
]


# 优先级越靠前越先吃独占（首个命中的域作为 primary）；其余命中进 secondary。
PRIMARY_ORDER = ["formula", "consol", "acnr", "ai", "voucher", "attachment", "procedure", "global-modules", "writeback", "note", "cycle", "platform"]

# 逐 spec 覆盖（正则 → 域 key 列表，优先级最高）。用于模式表判不准的少数特例。
OVERRIDES: list[tuple[str, list[str]]] = [
    (r"^24-consol-note-and-key-isolation", ["consol", "writeback"]),
    (r"^40-consol-note-defect-closure", ["consol", "note"]),
    (r"^41-formula-push-note-skip", ["formula", "note"]),
    (r"^55-batch-2026-10-21", ["writeback", "formula", "ai", "note"]),
    (r"^99-superseded", ["platform"]),
    (r"^112-stash", ["platform"]),
    (r"^109-excel-style", ["platform"]),
    (r"^121-formula-provenance", ["formula", "note"]),
    (r"^151-audit-log-chain", ["platform"]),
    (r"^157-check-contract", ["formula", "note"]),
    (r"^158-consol-note-save", ["consol", "note"]),
    (r"^168-note-disclosure-formula-and-consolidation", ["note", "consol", "formula"]),
    (r"^169-note-table-structure", ["note", "formula", "consol"]),
    (r"^174-wp-sync-conflict", ["writeback"]),
    (r"^177-chat-host", ["ai"]),
    (r"^178-advanced-query", ["global-modules"]),
    (r"^179-advanced-query", ["global-modules"]),
    (r"^189-b22a-whole-workbook", ["writeback", "cycle"]),
    (r"^100-s-cycle", ["cycle", "writeback"]),
    (r"^101-note-chain", ["note", "formula"]),
    (r"^102-wp-deeplink", ["acnr"]),
    (r"^103-note-pull", ["note", "consol", "formula"]),
    (r"^104-tb-reclass", ["consol", "cycle"]),
    (r"^114-backend-startup", ["platform"]),
    (r"^117-consol-note-formula", ["consol", "formula"]),
    (r"^119-note-pull", ["note", "formula"]),
    (r"^122-runtime", ["platform"]),
    (r"^123-trim", ["procedure"]),
    (r"^124-trim", ["procedure"]),
    (r"^134-attachment-contract", ["attachment", "cycle"]),
    (r"^136-wp-deeplink", ["acnr"]),
    (r"^137-wp-deeplink", ["acnr"]),
    (r"^141-income-statement", ["formula", "cycle"]),
    (r"^145-formula-e2e", ["formula", "platform"]),
    (r"^152-enterprise-embedding", ["ai"]),
    (r"^160-frontend-prod", ["platform"]),
    (r"^161-note-disclosure-pull", ["note", "formula"]),
    (r"^163-trim", ["procedure"]),
    (r"^164-api-prefix", ["platform"]),
    (r"^165-consol-group-code", ["consol"]),
    (r"^166-consol-status", ["consol"]),
    (r"^170-d2-voucher", ["voucher", "writeback"]),
    (r"^171-batch-project", ["consol"]),
    (r"^172-llm-linkage", ["ai"]),
    (r"^173-voucher-runtime", ["voucher"]),
    (r"^175-adjustment-practice", ["cycle"]),
    (r"^176-adjustment-client", ["cycle"]),
    (r"^185-frozen-contract", ["writeback"]),
    (r"^186-platform-release", ["platform"]),
    (r"^187-platform-performance", ["platform"]),
    (r"^188-platform-heavy", ["platform"]),
]


# 第二轮补充覆盖（phase 泛名 / v3 / a17 / 零散项），基于 requirements 标题与批次语境。
OVERRIDES += [
    (r"^phase0-|^phase1-experience|^phase1a-core|^phase1b-workpaper|^phase1c-report|^phase3-", ["platform"]),
    (r"^phase11-|^phase15-|^phase5-operational|^phase6-|^phase7-|^phase8$|^phase4-ai|^phase12-|^phase4-long-term|^phase5-extension", ["platform"]),
    (r"^phase4-ai", ["ai", "platform"]),
    (r"^refinement-round", ["platform"]),
    (r"^endpoint-fuzz", ["platform"]),
    (r"^global-", ["global-modules", "platform"]),
    (r"^global-modules", ["global-modules", "platform"]),
    (r"^report-config", ["formula", "cycle"]),
    (r"^v3-", ["platform"]),
    (r"^xlsx-read", ["platform"]),
    (r"^adjudication-export", ["cycle", "attachment"]),
    (r"^audit-chain-generation", ["platform"]),
    (r"^balance-import", ["voucher"]),
    (r"^fghi-sheet", ["cycle"]),
    (r"^partner-dashboard", ["platform"]),
    (r"^proposal-remaining", ["platform"]),
    (r"^report-module", ["cycle"]),
    (r"^s-estimate|^s-special", ["cycle"]),
    (r"^stale-propagation", ["platform"]),
    (r"^wp-frontend|^wp-functional|^wp-generation|^wp-performance", ["platform", "cycle"]),
    (r"^frontend-excel-io", ["platform", "writeback"]),
    (r"^audit-sheet-editable", ["platform", "cycle"]),
    (r"^custom-workpaper-formula", ["cycle", "formula"]),
    (r"^custom-workpaper-template", ["cycle", "writeback"]),
    (r"^report-view-slimdown", ["platform"]),
    (r"^A0[0-9]-|^X0[0-9]-", ["cycle"]),
    (r"^grid-sheet-inline", ["platform"]),
    (r"^a17-|^a18-|^a12-|^a1-11|^a1-dashboard|^a5-1|^a27-", ["cycle"]),
    (r"^qc-python", ["platform"]),
    (r"^report-cache", ["platform"]),
    (r"^single-source-cleanup", ["platform"]),
    (r"^162-platform", ["platform"]),
    (r"^environment-hygiene", ["platform"]),
    (r"^27-consol-tree", ["consol"]),
    (r"^45-d2-inspection", ["writeback", "cycle"]),
    (r"^72-consol|^73-consol", ["consol"]),
    (r"^74-audit-year", ["platform", "cycle"]),
    (r"^79-post-push", ["platform"]),
    (r"^linkage-panorama", ["global-modules", "platform"]),
    (r"^post-enhancement", ["platform"]),
    (r"^operation-log", ["platform"]),
]


def classify(name: str) -> tuple[str | None, list[str]]:
    for pat, keys in OVERRIDES:
        if re.search(pat, name):
            primary = keys[0]
            return primary, keys
    hits: list[str] = []
    for dom in DOMAINS:
        if any(re.search(p, name) for p in dom["patterns"]):
            hits.append(dom["key"])
    if not hits:
        return None, []
    hits.sort(key=PRIMARY_ORDER.index)
    return hits[0], hits


def rel_link(d: Path) -> str:
    """相对 CATALOG.md 的链接（CATALOG 在 .kiro/specs/ 下），指向实际存在的第一件套。"""
    rel = d.relative_to(SPECS).as_posix()
    for f in SPEC_DOCS:
        if (d / f).exists():
            return f"{rel}/{f}"
    return rel


def anchor_ok(rel: str) -> bool:
    return (ROOT / rel).exists()


def render() -> tuple[str, dict]:
    specs = iter_spec_dirs()
    rows = []
    for d in specs:
        done, total = parse_tasks(d)
        is_active = d.parent == SPECS
        primary, keys = classify(d.name)
        rows.append(
            {
                "dir": d,
                "name": d.name,
                "link": rel_link(d),
                "active": is_active,
                "done": done,
                "total": total,
                "primary": primary,
                "keys": keys,
                "title": first_title(d),
            }
        )

    by_key: dict[str, list[dict]] = {dom["key"]: [] for dom in DOMAINS}
    unclassified: list[dict] = []
    for r in rows:
        if not r["keys"]:
            unclassified.append(r)
        for k in r["keys"]:
            by_key[k].append(r)

    dom_names = {dom["key"]: dom["name"] for dom in DOMAINS}
    lines: list[str] = []
    lines.append("# Spec 功能域目录（CATALOG）")
    lines.append("")
    lines.append("> 本项目 `_archive/` 按开发时间批次归档（append-only 审计轨迹），")
    lines.append("> 本目录提供**按功能域的多维视图**：一个 spec 可同属多个域。")
    lines.append(">")
    lines.append("> 本文件由 `backend/scripts/analyze/build_spec_catalog.py` 生成，**请勿手工编辑**。")
    lines.append("> 改域规则：分类模式 → `DOMAINS`；特例逐 spec 覆盖 → `OVERRIDES`；版式 → `render()`。")
    lines.append("> 重新生成：`python backend/scripts/analyze/build_spec_catalog.py`")
    lines.append("> 漂移校验：`python backend/scripts/analyze/build_spec_catalog.py --check`（不一致 exit 2，可入 CI）")
    lines.append(">")
    active_n = sum(1 for r in rows if r["active"])
    archived_n = len(rows) - active_n
    lines.append(f"> **统计**：全部 spec **{len(rows)}** = 活跃 **{active_n}** + 已归档 **{archived_n}**；")
    lines.append(f"> 功能域 **{len(DOMAINS)}**；未归类 **{len(unclassified)}**。")
    lines.append("")

    # 域概览：域名列是 #domain-{key} 跳转链（各节 HTML 锚点，渲染器无关）
    lines.append('<a id="top"></a>')
    lines.append("## 一、功能域概览")
    lines.append("")
    lines.append("| 功能域 | spec 数 | 代码锚点 | 前端位置 |")
    lines.append("| --- | --- | --- | --- |")
    for dom in DOMAINS:
        items = by_key[dom["key"]]
        anchor = f"`{dom['anchor']}`"
        if not anchor_ok(dom["anchor"]) and anchor_ok(dom.get("anchor_alt", "")):
            anchor = f"`{dom['anchor_alt']}`"
        fe = f"`{dom['frontend']}`" if dom.get("frontend") else "—"
        lines.append(
            f"| **[{dom['name']}](#domain-{dom['key']})** | {len(items)} | {anchor} | {fe} |"
        )
    lines.append(f"| [（未归类）](#domain-unclassified) | {len(unclassified)} | — | — |")
    lines.append("")

    return "\n".join(lines) + "\n", {"rows": rows, "by_key": by_key, "unclassified": unclassified, "dom_names": dom_names}


def render_domain_sections(ctx: dict) -> str:
    lines: list[str] = []
    for dom in DOMAINS:
        items = ctx["by_key"][dom["key"]]
        if not items:
            continue
        lines.append(f'<a id="domain-{dom["key"]}"></a>')
        lines.append(f"## {dom['name']}（{len(items)} 个）")
        lines.append("")
        lines.append("| 状态 | Spec | 进度 | 需求标题 |")
        lines.append("| --- | --- | --- | --- |")
        for r in sorted(items, key=lambda x: x["name"]):
            state = "🟢活跃" if r["active"] else "📦已归档"
            prog = f"{r['done']}/{r['total']}" if r["total"] else "—"
            title = r["title"].replace("|", "\\|")
            multi = ""
            if len(r["keys"]) > 1:
                multi = " ⧉" + "+".join(r["keys"][1:])
            lines.append(f"| {state} | [`{r['name']}`]({r['link']}){multi} | {prog} | {title} |")
        lines.append("")
        lines.append("[↑ 返回概览](#top)")
        lines.append("")
    if ctx["unclassified"]:
        lines.append('<a id="domain-unclassified"></a>')
        lines.append(f"## 未归类（{len(ctx['unclassified'])} 个）")
        lines.append("")
        lines.append("| 状态 | Spec | 需求标题 |")
        lines.append("| --- | --- | --- |")
        for r in sorted(ctx["unclassified"], key=lambda x: x["name"]):
            state = "🟢活跃" if r["active"] else "📦已归档"
            title = r["title"].replace("|", "\\|")
            lines.append(f"| {state} | [`{r['name']}`]({r['link']}) | {title} |")
        lines.append("")
        lines.append("[↑ 返回概览](#top)")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    check = "--check" in sys.argv
    body, ctx = render()
    full = body + render_domain_sections(ctx)

    old = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else None
    if check:
        if old != full:
            print("CATALOG.md 与生成结果不一致（漂移）。重新生成：python backend/scripts/analyze/build_spec_catalog.py")
            return 2
        print("CATALOG.md 校验通过（无漂移）。")
        return 0

    CATALOG.write_text(full, encoding="utf-8", newline="\n")
    active_n = sum(1 for r in ctx["rows"] if r["active"])
    print(f"已生成 {CATALOG}")
    print(f"  spec 总数 {len(ctx['rows'])}（活跃 {active_n} / 归档 {len(ctx['rows']) - active_n}）")
    print("  域分布: " + ", ".join(f"{k}={len(v)}" for k, v in ctx['by_key'].items()))
    if ctx["unclassified"]:
        print(f"  ! 未归类 {len(ctx['unclassified'])}: " + ", ".join(r["name"] for r in ctx["unclassified"][:10]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
