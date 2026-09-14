"""变异检验：mention 字段契约与状态语义守卫是否真能打红

## 背景

`@` 引用（mention）功能此前实际不可用，根因两层：

1. `mention_service.py` 引用了 **9 个不存在的 ORM 属性**
   （`DisclosureNote.section_number` / `FinancialReport.report_name` /
   `KnowledgeDocument.title|project_id|content` / `KnowledgeFolder.project_id` /
   `WorkingPaper.content` / `DisclosureNote.content`）⇒ 7 类里 4 类恒 `error`，
   底稿正文恒进不了上下文。
2. 受限全局知识模式（无项目绑定）下四类项目资源返回空集却标 `empty`，
   前端又把单类型 `error` 吞成 `success` ⇒ 界面统一显示"无匹配结果"。

修复前 **13 条 vitest 守卫 + 508 条 pytest 守卫全绿** —— 它们只断言
"empty 与 error 用不同 DOM"、"source 里有 authorize 字样"这类字符串/结构判据，
从不断言单类失败会不会被吞，也从不真挂载组件看 tab 可点性。

## 本脚本

对修复后新增的守卫逐条注入变异，确认每条都能打红。四态判定：

    RED          打红且命中预期测试   ⇒ 守卫有效
    GREEN        没打红              ⇒ 守卫缺陷（本脚本首轮即抓出过一条）
    ANCHOR-MISS  锚点未命中或命中 >1  ⇒ 脚本缺陷
    WRONG-TEST   打红了但不是预期项   ⇒ 锚点错行或污染残留

用法::

    python backend/scripts/diagnose/mutate_mention_field_and_status_guards.py
    python backend/scripts/diagnose/mutate_mention_field_and_status_guards.py --check-anchors

``--check-anchors`` 只校验锚点仍唯一命中（只读、秒级），用于判断"本次修复的结构
是否还在"，不必重跑全量变异 —— 在有并发会话在途改动时尤其有用。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "audit-platform" / "frontend"

COMPOSABLE = FRONTEND / "src" / "composables" / "useAiMention.ts"
PICKER = FRONTEND / "src" / "components" / "ai" / "ChatMentionPicker.vue"
SERVICE = ROOT / "backend" / "app" / "services" / "ai_chat" / "mention_service.py"

FE_SPEC = "src/components/ai/__tests__/ChatMentionPicker.spec.ts"
BE_SPEC = "backend/tests/dsh_agent_panel/test_mention_orm_field_contract.py"
#: 地址坐标表级粒度守卫（与 BE_SPEC 分开跑，便于定位）
ADDR_SPEC = "backend/tests/dsh_agent_panel/test_mention_address_table_level.py"


@dataclass(frozen=True)
class Mutation:
    name: str
    target: Path
    anchor: str
    replacement: str
    #: 期望在失败输出中出现的测试名片段
    wants: str
    #: 不打红意味着什么真实缺陷会溜过去
    why: str
    #: "fe" 走 vitest，"be" 走 pytest
    suite: str


MUTATIONS: tuple[Mutation, ...] = (
    # ── 前端：状态语义 ────────────────────────────────────────────────────
    Mutation(
        "FE1 单类失败退回旧的 every-unavailable 逻辑",
        COMPOSABLE,
        "if (items.value.length === 0 && failed.length > 0 && failed.length === participating.length) {",
        "if (items.value.length === 0 && failed.length > 0 && failed.length === participating.length && false) {",
        "单类型 error",
        "这正是历史缺陷本身：单个类型失败被吞成 success ⇒ 界面显示「无匹配结果」",
        "fe",
    ),
    Mutation(
        "FE2 project_required 不再给可操作指引",
        COMPOSABLE,
        "return `${detail}。请先从某个项目的底稿或报表页打开 AI 对话。`",
        "return `${detail}。`",
        "全部 project_required",
        "只说不行、不说怎么办，用户仍然卡在原地",
        "fe",
    ),
    Mutation(
        "FE3 降级提示恒空",
        COMPOSABLE,
        "    if (failed.length === 0) return ''",
        "    if (failed.length === 0) return ''\n    return ''",
        "有结果 + 部分类型失败",
        "有结果时部分类型失败被静默吞掉（用户以为搜全了）",
        "fe",
    ),
    Mutation(
        "FE4 取值域漂移（把知识文档也算作需要项目）",
        COMPOSABLE,
        "export const PROJECT_REQUIRED_MENTION_TYPES: readonly MentionType[] = [\n  'workpaper',",
        "export const PROJECT_REQUIRED_MENTION_TYPES: readonly MentionType[] = [\n  'knowledge_doc',\n  'workpaper',",
        "取值域对账",
        "前后端取值域不一致 ⇒ 可跨项目共享的知识资产被误置灰",
        "fe",
    ),
    # ── 前端：渲染层（composable 级守卫看不见）──────────────────────────────
    Mutation(
        "FE5 tab 置灰失效（disabled 恒 false）",
        PICKER,
        "    const disabled = needsProject && projectBindingMissing.value",
        "    const disabled = false",
        "tab 置灰",
        "置灰是渲染层行为；没有真挂载组件的 DOM 守卫就查不出",
        "fe",
    ),
    Mutation(
        "FE6 置灰 tab 仍可点击发请求",
        PICKER,
        "  if (filter.disabled) return\n  setTypeFilter(filter.value)",
        "  setTypeFilter(filter.value)",
        "点击不发请求",
        "点了注定为空的往返 ⇒ 用户又看到「无匹配结果」",
        "fe",
    ),
    # ── 后端：ORM 字段契约 ────────────────────────────────────────────────
    Mutation(
        "FE7 空态退回硬编码「无匹配结果」",
        COMPOSABLE,
        "    return hint ? `未搜到匹配项。${hint}` : '无匹配结果'",
        "    return '无匹配结果'",
        "空态点明原因",
        "本次修复的原始症状：四类需要项目 + 两类真空时，用户只看到「无匹配结果」",
        "fe",
    ),
    Mutation(
        "FE8 类型名退回后端字母序",
        COMPOSABLE,
        "  return [...types]\n    .sort((a, b) => rank(a) - rank(b))",
        "  return [...types]",
        "业务顺序",
        "文案读成「地址坐标、附注、报表、底稿」，不符合审计师的阅读习惯",
        "fe",
    ),
    Mutation(
        "BE1 附注章节号退回历史错误字段",
        SERVICE,
        "DisclosureNote.note_section,",
        "DisclosureNote.section_number,",
        "test_all_referenced_orm_attributes_exist",
        "附注 mention 恒 AttributeError ⇒ 整类不可用（本次修复的原始缺陷之一）",
        "be",
    ),
    Mutation(
        "BE2 知识文档名字段退回 title",
        SERVICE,
        "                KnowledgeDocument.name,",
        "                KnowledgeDocument.title,",
        "test_all_referenced_orm_attributes_exist",
        "知识文档 mention 恒 AttributeError",
        "be",
    ),
    Mutation(
        "BE3 知识库按不存在的 project_id 过滤",
        SERVICE,
        "                KnowledgeFolder.is_deleted == sa.false(),",
        "                KnowledgeFolder.project_id == project_id,",
        "test_all_referenced_orm_attributes_exist",
        "知识库 mention 在有项目时恒 error；且公共文件夹会被整体排除",
        "be",
    ),
    # ── 后端：状态语义 ────────────────────────────────────────────────────
    Mutation(
        "BE4 project_required 前置判断失效（退回 empty 语义）",
        SERVICE,
        "            if host_decision.project_id is None and rt in PROJECT_REQUIRED_MENTION_TYPES:",
        "            if False:",
        "test_unbound_project_reports_project_required_without_querying",
        "「未绑定项目」重新显示成「无匹配结果」，且白跑一轮注定为空的查询",
        "be",
    ),
    Mutation(
        "BE5 报表 label 漏出英文字面量（不走中文真源）",
        SERVICE,
        "            label = REPORT_LABELS.get(report_type, report_type)",
        "            label = report_type",
        "test_report_candidates_come_from_enum_with_chinese_labels",
        "候选列表显示 balance_sheet 而不是「资产负债表」，违反全中文 UI",
        "be",
    ),
    Mutation(
        "BE6 未生成的报表也进候选",
        SERVICE,
        "                continue  # 未生成 ⇒ 不进候选",
        "                pass  # 未生成 ⇒ 不进候选",
        "test_report_candidates_come_from_enum_with_chinese_labels",
        "用户能引用一张从未生成的空报表，AI 拿到空上下文却照常作答",
        "be",
    ),
    # ── 后端：地址坐标表级粒度 ─────────────────────────────────────────────
    Mutation(
        "AD1 地址坐标退回单元格级（cell 进聚合键）",
        SERVICE,
        '    "tb": ("source",),          # tb://1001            一个科目的全部列',
        '    "tb": ("source", "cell"),          # tb://1001            一个科目的全部列',
        "test_search_aggregates_cells_into_one_candidate_per_table",
        "又变成逐单元格列出：同一坐标重复多条，审计师要在几十条里挑一个数",
        "be",
    ),
    Mutation(
        "AD2 表级 label 未去掉列名",
        SERVICE,
        "    return _ADDRESS_LABEL_SEP.join(parts[:-1])",
        "    return _ADDRESS_LABEL_SEP.join(parts)",
        "test_table_level_label_drops_trailing_column",
        "候选 label 仍显示到列（「试算表 > 1001 库存现金 > 审定数」），与表级语义矛盾",
        "be",
    ),
    Mutation(
        "AD3 year 缺失时仍拿 0 去查 registry",
        SERVICE,
        "        if project_id is None or year is None:",
        "        if project_id is None:",
        "test_search_without_year_returns_empty_and_skips_registry",
        "四表域按 year 过滤业务表 ⇒ year=0 时恒空，白跑一轮全域构建",
        "be",
    ),
    Mutation(
        "AD4 正文退回坐标元信息（无真实金额）",
        SERVICE,
        '        lines.append(f"{column_label}: {_fmt_amount(getattr(row, attr, None))}")',
        '        lines.append(f"{column_label}: (略)")',
        "test_trial_balance_table_content_carries_real_amounts",
        "AI 只拿到列名清单没有数字 —— 引用了等于没引用（原缺陷正是如此）",
        "be",
    ),
    Mutation(
        "AD5 地址坐标域范围扩回 report（与「报表」类型重复）",
        SERVICE,
        '    "aux": ("source", "path"),  # aux://1001/成本中心   科目 × 辅助维度',
        '    "aux": ("source", "path"),  # aux://1001/成本中心   科目 × 辅助维度\n    "report": ("source",),',
        "test_address_domains_exclude_types_covered_by_dedicated_mentions",
        "同一张资产负债表在候选里出现两次（一次「报表」、一次「地址坐标」）",
        "be",
    ),
    Mutation(
        "AD6 域优先级顺序被颠倒",
        SERVICE,
        "        domain_rank = {d: i for i, d in enumerate(_ADDRESS_MENTION_DOMAINS)}",
        "        domain_rank = {d: i for i, d in enumerate(reversed(list(_ADDRESS_MENTION_DOMAINS)))}",
        "test_search_orders_trial_balance_before_aux",
        "上万个辅助维度组合会把试算表科目挤出前 10 条候选",
        "be",
    ),
)


def run_suite(suite: str) -> tuple[bool, str]:
    if suite == "fe":
        proc = subprocess.run(
            ["npx", "vitest", "run", FE_SPEC, "--reporter=dot"],
            cwd=FRONTEND, capture_output=True, text=True,
            encoding="utf-8", errors="replace", shell=True,
        )
    else:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", BE_SPEC, ADDR_SPEC, "-q", "--tb=line"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def check_anchors() -> int:
    print("=== 锚点唯一性核查（只读）===")
    bad = 0
    for m in MUTATIONS:
        text = m.target.read_text(encoding="utf-8")
        hits = text.count(m.anchor)
        flag = "OK" if hits == 1 else f"MISS({hits})"
        if hits != 1:
            bad += 1
        print(f"  [{flag:8s}] {m.name}")
    print(f"\n{len(MUTATIONS) - bad}/{len(MUTATIONS)} 个锚点唯一命中")
    if bad:
        print("锚点漂移 ⇒ 本次修复的结构已变，需要重新校准变异脚本")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-anchors", action="store_true",
        help="只校验锚点仍唯一命中（只读、秒级），不注入变异",
    )
    args = parser.parse_args()

    if args.check_anchors:
        return check_anchors()

    print("=== 基线 ===")
    for suite, label in (("fe", "vitest"), ("be", "pytest")):
        ok, out = run_suite(suite)
        if not ok:
            print(f"{label} 基线未通过，变异检验无意义：\n{out[-2500:]}")
            return 1
        print(f"  {label} 基线全绿")

    verdicts: list[tuple[str, str]] = []
    for m in MUTATIONS:
        original = m.target.read_text(encoding="utf-8")
        hits = original.count(m.anchor)
        if hits != 1:
            verdicts.append((m.name, f"ANCHOR-MISS({hits})"))
            print(f"[ANCHOR-MISS] {m.name} — 锚点命中 {hits} 次")
            continue

        m.target.write_text(original.replace(m.anchor, m.replacement), encoding="utf-8")
        try:
            passed, out = run_suite(m.suite)
        finally:
            m.target.write_text(original, encoding="utf-8")

        if passed:
            verdicts.append((m.name, "GREEN"))
            print(f"[GREEN] {m.name}\n         守卫没打红 ⇒ {m.why}")
        elif m.wants in out:
            verdicts.append((m.name, "RED"))
            print(f"[RED] {m.name}")
        else:
            verdicts.append((m.name, "WRONG-TEST"))
            print(f"[WRONG-TEST] {m.name} — 期望失败项含 {m.wants!r}")

    print("\n=== 还原后复核 ===")
    all_restored = True
    for suite, label in (("fe", "vitest"), ("be", "pytest")):
        ok, _ = run_suite(suite)
        print(f"  {label}: {'全绿' if ok else '未还原干净'}")
        all_restored = all_restored and ok

    reds = sum(1 for _, v in verdicts if v == "RED")
    print("\n" + "=" * 72)
    print(f"{reds}/{len(MUTATIONS)} 条变异被守卫打红")
    for name, verdict in verdicts:
        print(f"  {verdict:14s} {name}")

    return 0 if (reds == len(MUTATIONS) and all_restored) else 1


if __name__ == "__main__":
    sys.exit(main())
