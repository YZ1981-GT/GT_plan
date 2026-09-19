"""Task 21 变异检验：程序裁剪 → 附注不适用联动守卫是否**真的承重**。

## 为什么必须做

平台铁律：写完守卫必做变异检验，**没打红 = 守卫有缺陷，不是代码没问题**。本任务的
核心守卫 bullet 是「不存在第二套不适用标注字段（只写 ``is_empty``，判定只调既有共享
helper）」—— 那是一条源码级约束，最容易写成「字符是否出现」而被一个改名绕过。故 M1
专门施加"新增第二个不适用字段"这个变异，必须打红。

## 判定：按**失败测试名集合求差集**，不看退出码

基线本身可能有红（本轮无，但判据不能依赖这一点）。显式区分五态：

- ``RED``        —— 新增失败非空 ⇒ 守卫承重
- ``GREEN``      —— 新增失败为空 ⇒ **守卫缺陷**（不是代码没问题）
- ``ANCHOR-MISS``—— 锚点未命中或命中 > 1 ⇒ **脚本缺陷**，变异根本没施加，
                     此时"测试仍绿"不能作为任何结论
- ``WRONG-TEST`` —— 打红了但不含预期测试 ⇒ 判据锚错行或有污染残留
- ``COLLECT-ERR``—— 整文件 collection error（零断言执行）⇒ 变异体非法，也不算 RED

## 锚点规则（踩过的坑）

- **行级唯一**：``splitlines()`` + 行内 needle 匹配 + ``hits == 1`` + 相对 ``offset``
- **禁含 ``\\n`` 的跨行字面量**：本工作树是 CRLF，跨行锚点必 MISS
- 变异后**断言字节确实变了**（未变则"测试仍绿"无意义）
- ``.bak`` + ``try/finally`` 无条件写回 + md5 核验字节级还原

Usage::

    python backend/scripts/check/mutate_task21_note_linkage_guards.py
    python backend/scripts/check/mutate_task21_note_linkage_guards.py --restore
    python backend/scripts/check/mutate_task21_note_linkage_guards.py --only M1,M5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE_DIR = ROOT / "audit-platform" / "frontend"

LINKAGE_PY = ROOT / "backend" / "app" / "services" / "procedure_trim_note_linkage.py"
ROUTER_PY = ROOT / "backend" / "app" / "routers" / "procedure_trim.py"
TRIM_VUE = FE_DIR / "src" / "views" / "ProcedureTrimming.vue"

BE_GUARD = "backend/tests/procedure_trim/test_note_linkage_single_source.py"
FE_GUARD = "src/views/__tests__/noteLinkageHost.spec.ts"
FE_JSON = ROOT / "tmp_t21_mutate_fe.json"
REPORT = ROOT / "tmp_t21_mutate_report.txt"

# 🔴 白名单：只允许动这三个文件的 .bak。别的会话的 `*.bak` 是它们变异脚本的**活体备份**，
#    误删会让它的 --restore 失败并把变异体留在工作树（平台已登记的一次事故）。
OWNED = (LINKAGE_PY, ROUTER_PY, TRIM_VUE)


@dataclass
class Mutation:
    mid: str
    desc: str
    path: Path
    anchor: str
    old: str
    new: str
    expect: str
    offset: int = 0
    suites: tuple[str, ...] = ("be", "fe")


MUTATIONS: list[Mutation] = [
    # ── 主判据：第二套不适用字段 ─────────────────────────────────────────
    Mutation(
        "M1", "新增第二套不适用字段（note.trim_not_applicable = True）",
        LINKAGE_PY,
        anchor="            note.is_empty = True",
        old="note.is_empty = True",
        new="note.is_empty = True; note.trim_not_applicable = True",
        expect="test_a1_only_is_empty_and_lineage_are_ever_assigned",
    ),
    Mutation(
        "M2", "改走删章节路径（note.is_deleted = True）",
        LINKAGE_PY,
        anchor="            note.is_empty = True",
        old="note.is_empty = True",
        new="note.is_deleted = True",
        expect="test_a3_does_not_use_note_trim_service_deleting_or_replacing_paths",
    ),
    # ── 判定真源 ────────────────────────────────────────────────────────
    Mutation(
        "M3", "内容判定不再绕开 is_empty 短路（已标章节恒判无内容）",
        LINKAGE_PY,
        anchor="        is_empty=False,",
        old="is_empty=False,",
        new="is_empty=getattr(note, \"is_empty\", False),",
        expect="test_b4_content_probe_bypasses_the_is_empty_short_circuit",
    ),
    Mutation(
        "M4", "内容判定自己遍历 table_data（第二份判定口径）",
        LINKAGE_PY,
        anchor="    return bool(note_has_data(probe))",
        old="return bool(note_has_data(probe))",
        new=(
            "td = getattr(note, \"table_data\", None) or {}\n"
            "    for _r in (td.get(\"rows\") or []):\n"
            "        if any(_r.get(\"values\") or []):\n"
            "            return True\n"
            "    return bool(getattr(note, \"text_content\", None))"
        ),
        expect="test_b3_no_own_table_data_traversal",
    ),
    # ── 判定规则两个合取项 ──────────────────────────────────────────────
    Mutation(
        "M5", "去掉 all-owners 合取项（跨循环共有章节被误标）",
        LINKAGE_PY,
        anchor="        if all_owners_trimmed and all_cycles_fully_trimmed:",
        old="if all_owners_trimmed and all_cycles_fully_trimmed:",
        new="if all_cycles_fully_trimmed:",
        expect="test_d1_cross_cycle_section_needs_all_owners_trimmed",
    ),
    Mutation(
        "M6", "去掉 cycle-fully-trimmed 合取项（未达整体裁剪也标注）",
        LINKAGE_PY,
        anchor="        if all_owners_trimmed and all_cycles_fully_trimmed:",
        old="if all_owners_trimmed and all_cycles_fully_trimmed:",
        new="if all_owners_trimmed:",
        expect="test_d3_owner_trimmed_but_cycle_not_fully_trimmed_is_not_marked",
    ),
    Mutation(
        "M7", "同一 wp_code 多条程序按 OR 合并（有程序在做也算已裁）",
        LINKAGE_PY,
        anchor="        if prev is None or (prev.trimmed and not row.trimmed):",
        old="if prev is None or (prev.trimmed and not row.trimmed):",
        new="if prev is None or (not prev.trimmed and row.trimmed):",
        expect="test_d4_multiple_instances_per_wp_code_merge_as_and",
    ),
    Mutation(
        "M8", "已裁取值域少一个（被 skip 的底稿不算已裁）",
        LINKAGE_PY,
        anchor="TRIMMED_SCOPE_STATUSES = frozenset({\"skip\", \"not_applicable\"})",
        old="frozenset({\"skip\", \"not_applicable\"})",
        new="frozenset({\"not_applicable\"})",
        expect="test_d5_trimmed_statuses_match_the_platform_definition",
    ),
    # ── provenance 不是判据 ─────────────────────────────────────────────
    Mutation(
        "M9", "把 provenance 变成不适用判据（标注分支读面包屑）",
        LINKAGE_PY,
        anchor="            if note_has_manual_content(note):",
        old="if note_has_manual_content(note):",
        new="if note_has_manual_content(note) or was_marked_by_linkage(note):",
        expect="test_c2_provenance_reader_used_only_on_the_revoke_side",
    ),
    Mutation(
        "M10", "撤销不检查归属（清掉审计师手工标注）",
        LINKAGE_PY,
        anchor="        if not was_marked_by_linkage(note):",
        old="if not was_marked_by_linkage(note):",
        new="if False:",
        expect="test_f5_does_not_revoke_a_user_marked_section",
    ),
    # ── R13.4 / R13.6 ───────────────────────────────────────────────────
    Mutation(
        "M11", "有内容仍自动标注（覆盖人工录入）",
        LINKAGE_PY,
        anchor="            if note_has_manual_content(note):",
        old="if note_has_manual_content(note):",
        new="if False:",
        expect="test_f3_note_with_content_is_only_reported_never_touched",
    ),
    Mutation(
        "M12", "定位不到章节时抛异常（阻断裁剪保存）",
        LINKAGE_PY,
        anchor="                out.unlocatable.append({**item, \"reason\": \"no_disclosure_note_row\"})",
        old="out.unlocatable.append({**item, \"reason\": \"no_disclosure_note_row\"})",
        new="raise RuntimeError(\"note section not found\")",
        expect="test_f6_unlocatable_section_is_skipped_without_raising",
    ),
    # ── 映射真源 ────────────────────────────────────────────────────────
    Mutation(
        "M13", "自读 registry JSON（第二份解析口径）",
        LINKAGE_PY,
        anchor="        section_wp_map = section_workpaper_map()",
        old="section_wp_map = section_workpaper_map()",
        new=(
            "import json as _j\n"
            "        _p = Path(__file__).resolve().parent.parent.parent / \"data\" / \"note_workpaper_sync_registry.json\"\n"
            "        _doc = _j.loads(_p.read_text(encoding=\"utf-8\"))\n"
            "        section_wp_map = {\n"
            "            str(e.get(\"listed\") or \"\"): [str(e.get(\"wp_code\") or \"\")]\n"
            "            for e in (_doc.get(\"entries\") or [])\n"
            "        }"
        ),
        expect="test_e2_does_not_read_the_registry_json_directly",
    ),
    # ── router ──────────────────────────────────────────────────────────
    Mutation(
        "M14", "GET 端点摘掉项目级 Delegator 守卫（越权改附注标记）",
        ROUTER_PY,
        anchor="async def trim_note_linkage_preview(",
        offset=5,
        old="    _guard: DelegatorContext = Depends(require_project_delegator_pid),",
        new="",
        expect="test_g2_endpoints_are_delegator_gated",
    ),
    Mutation(
        "M15", "apply 请求体让前端传章节清单（第二份判定口径）",
        ROUTER_PY,
        anchor="    year: int = Field(ge=1900, le=2999)",
        old="    year: int = Field(ge=1900, le=2999)",
        new="    year: int = Field(ge=1900, le=2999)\n    sections: list[str] = Field(default_factory=list)",
        expect="test_g4_get_requires_year_and_apply_takes_year_from_body",
    ),
    # ── 前端 ────────────────────────────────────────────────────────────
    Mutation(
        "M16", "面板 v-model 改绑别的 ref（渲染宿主实际不存在）",
        TRIM_VUE,
        anchor="      v-model=\"noteLinkagePanelVisible\"",
        old="v-model=\"noteLinkagePanelVisible\"",
        new="v-model=\"showOverviewDrawer\"",
        expect="面板本体是 el-dialog 且绑在 noteLinkagePanelVisible 上",
    ),
    Mutation(
        "M17", "五个桶塌成一个（没标的看起来像已标）",
        TRIM_VUE,
        anchor="    { key: 'to_mark', label: '将标注为本期不适用', tag: 'warning', items: v.to_mark,",
        old="items: v.to_mark,",
        new="items: [...v.to_mark, ...v.conflicts, ...v.unlocatable],",
        expect="noteLinkageBuckets 只做分组展示，不判定该不该标注",
    ),
    Mutation(
        "M18", "加载失败退化成空对象（技术故障显示成实质结论）",
        TRIM_VUE,
        anchor="    noteLinkageError.value = e?.message || '附注联动预览读取失败'",
        offset=-1,
        old="    noteLinkage.value = null",
        new="    noteLinkage.value = { to_mark: [], already_marked: [], conflicts: [], to_revoke: [], unlocatable: [], skipped_foreign_mark: [], degradations: [], cycles_fully_trimmed: [], summary: { to_mark: 0, already_marked: 0, conflicts: 0, to_revoke: 0, unlocatable: 0 } }",
        expect="noteLinkage 是三态 ref，加载失败置 null 并记 error",
    ),
    Mutation(
        "M19", "裁剪保存后不再触发联动（服务变死代码）",
        TRIM_VUE,
        anchor="    //    阻断裁剪保存。裁剪本身已 commit，此处失败只是少提示一次。",
        offset=1,
        old="    void loadNoteLinkage()",
        new="",
        expect="loadNoteLinkage 既被模板重试按钮消费、也被裁剪保存路径调用",
    ),
    Mutation(
        "M20", "删掉一个 scoped CSS 类（面板无视觉分层）",
        TRIM_VUE,
        anchor=".gt-proc-nlink__hint { font-size: 12px; color: var(--gt-color-text-tertiary); line-height: 1.6; }",
        old=".gt-proc-nlink__hint",
        new=".gt-proc-nlink__hintX",
        expect="模板用到的 scoped 类必须真有样式（缺类不报错、只表现为无视觉分层）",
    ),
]


# ───────────────────────────── 运行器 ─────────────────────────────


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@dataclass
class SuiteResult:
    failed: set[str] = field(default_factory=set)
    total: int = 0
    collect_error: bool = False
    raw_tail: str = ""


def run_backend() -> SuiteResult:
    cp = subprocess.run(
        [sys.executable, "-m", "pytest", BE_GUARD, "-q", "--no-header",
         "-p", "no:cacheprovider", "--tb=no", "-rf"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (cp.stdout or "") + (cp.stderr or "")
    res = SuiteResult(raw_tail=out[-1500:])
    if "error during collection" in out or "ERROR collecting" in out:
        res.collect_error = True
        return res
    for line in out.splitlines():
        m = re.match(r"FAILED\s+(\S+)", line.strip())
        if m:
            res.failed.add("be::" + m.group(1).split("::", 1)[-1])
    m = re.search(r"(\d+) passed", out)
    res.total = int(m.group(1)) if m else 0
    res.total += len(res.failed)
    return res


def run_frontend() -> SuiteResult:
    if FE_JSON.exists():
        FE_JSON.unlink()  # 防解析到陈旧 JSON（那会让结论完全错但看不出来）
    # 🔴 `npx vitest` 直调，不经 `npm exec`：后者传 flag 必须加 `--` 分隔符，
    #    否则 npm 把 `--reporter` 当自己的 cli config 并 warn，**JSON 根本不生成而退出码仍 0**。
    # 跨平台：Windows 的 npx 实为 npx.cmd（须经 cmd /c），POSIX 上 shell=True + 列表参数
    #  只会执行 npx 本身、不带任何参数 ⇒ JSON 不生成 ⇒ NO-JSON（Task 24 实证）。
    _npx = ["cmd", "/c", "npx"] if os.name == "nt" else ["npx"]
    cp = subprocess.run(
        [*_npx, "vitest", "run", FE_GUARD, "--reporter=json",
         f"--outputFile={FE_JSON}"],
        cwd=str(FE_DIR), capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    out = (cp.stdout or "") + (cp.stderr or "")
    res = SuiteResult(raw_tail=out[-1500:])
    if not FE_JSON.exists():
        res.collect_error = True
        return res
    try:
        doc = json.loads(FE_JSON.read_text(encoding="utf-8"))
    except Exception:
        res.collect_error = True
        return res
    for suite in doc.get("testResults") or []:
        if suite.get("status") == "failed" and not (suite.get("assertionResults") or []):
            res.collect_error = True
        for a in suite.get("assertionResults") or []:
            res.total += 1
            if a.get("status") == "failed":
                res.failed.add("fe::" + str(a.get("title") or a.get("fullName")))
    return res


def run_suites(which: tuple[str, ...]) -> SuiteResult:
    agg = SuiteResult()
    for name in which:
        r = run_backend() if name == "be" else run_frontend()
        agg.failed |= r.failed
        agg.total += r.total
        agg.collect_error = agg.collect_error or r.collect_error
        agg.raw_tail += f"\n--- {name} ---\n{r.raw_tail}"
    return agg


def apply_mutation(m: Mutation) -> tuple[bool, str]:
    """行级唯一锚点定位 + 定向替换。返回 (是否成功, 说明)。"""
    src = m.path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if m.anchor in ln]
    if len(hits) != 1:
        return False, f"ANCHOR-MISS: 锚点命中 {len(hits)} 次（须恰 1）: {m.anchor[:70]!r}"
    idx = hits[0] + m.offset
    if not (0 <= idx < len(lines)):
        return False, f"ANCHOR-MISS: offset 越界 (line {idx})"
    target = lines[idx]
    if m.old not in target:
        return False, f"ANCHOR-MISS: 目标行不含 old ({target.strip()[:80]!r})"
    if m.new == "":
        lines[idx] = ""
    else:
        lines[idx] = target.replace(m.old, m.new, 1)
    new_src = "".join(lines)
    if new_src == src:
        return False, "ANCHOR-MISS: 替换后字节未变（变异未施加）"
    m.path.write_text(new_src, encoding="utf-8", newline="")
    return True, "ok"


def classify(base: SuiteResult, after: SuiteResult, m: Mutation) -> tuple[str, str]:
    if after.collect_error:
        return "COLLECT-ERR", "整文件 collection error（零断言执行）—— 变异体非法，不算 RED"
    new_fails = after.failed - base.failed
    fixed = base.failed - after.failed
    if not new_fails:
        return "GREEN", f"新增失败为空 ⇒ **守卫缺陷**（消失 {sorted(fixed)}）"
    if not any(m.expect in name for name in new_fails):
        return "WRONG-TEST", (
            f"打红了但不含预期项 {m.expect!r}；新增={sorted(new_fails)}"
        )
    return "RED", f"新增 {len(new_fails)} 条：{sorted(new_fails)}"


def restore_all() -> list[str]:
    msgs = []
    for p in OWNED:
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            shutil.copy2(bak, p)
            bak.unlink()
            msgs.append(f"restored {p.name}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    if args.restore:
        for msg in restore_all():
            print(msg)
        return 0

    selected = [m for m in MUTATIONS if not args.only or m.mid in args.only.split(",")]
    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    pre_md5 = {p: md5(p) for p in OWNED}
    for p in OWNED:
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            raise SystemExit(f"拒绝运行：{bak} 已存在（可能是别的会话的活体备份）")
        shutil.copy2(p, bak)

    try:
        base = run_suites(("be", "fe"))
        emit(f"BASELINE total={base.total} failed={len(base.failed)}")
        if base.failed:
            emit(f"  预存在失败: {sorted(base.failed)}")
        emit()

        tally: dict[str, int] = {}
        for m in selected:
            ok, why = apply_mutation(m)
            if not ok:
                verdict, detail = "ANCHOR-MISS", why
            else:
                after = run_suites(m.suites)
                verdict, detail = classify(base, after, m)
            # 无条件还原（下一个变异必须从干净基线出发）
            shutil.copy2(m.path.with_suffix(m.path.suffix + ".bak"), m.path)
            tally[verdict] = tally.get(verdict, 0) + 1
            emit(f"{m.mid:>4}  {verdict:<12} {m.desc}")
            emit(f"      {detail}")
        emit()
        emit("TALLY: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    finally:
        restore_all()
        post = {p: md5(p) for p in OWNED}
        emit()
        for p in OWNED:
            same = pre_md5[p] == post[p]
            emit(f"RESTORE {'OK ' if same else 'FAIL'} {p.name} {pre_md5[p][:12]} -> {post[p][:12]}")
        leftovers = [
            str(p.with_suffix(p.suffix + '.bak'))
            for p in OWNED if p.with_suffix(p.suffix + ".bak").exists()
        ]
        emit(f"LEFTOVER .bak: {leftovers or 'none'}")
        if FE_JSON.exists():
            FE_JSON.unlink()
        REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
