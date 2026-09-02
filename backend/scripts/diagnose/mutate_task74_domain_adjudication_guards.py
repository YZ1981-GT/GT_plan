# -*- coding: utf-8 -*-
"""Task 74（第一半：逐 domain 裁决）守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 7 Task 74
Requirements: 2.1, 2.2, 2.11, 2.12, 9.11, 12.6, 12.7, 13.4 · Property 4, Property 61

═══ 为什么这一批变异必须存在 ═══

「把 236 + 34 行裁决完、门显示 0」这件事本身是**最容易做成假绿的一种交付**：

* 域标签可以被偷偷做成豁免（只要让某条 verdict 顺手看一眼 `adjudication`）；
* 注解可以是模板（写了字、没有信息，复制粘贴 270 份）；
* 规则表可以有 catch-all（「没命中就当 html_save」= 未裁决伪装成已裁决）；
* 门可以干脆**不再计算**这两条准则 —— 归零后「不算」与「算出 0」在报告里逐字相同。

七条变异各打掉其中一条防线。**注意两类落点的区别**（Task 20 的 M06 教训）：读磁盘 overlay /
清册的判据看不见「只改脚本不重生成」的变异，所以针对注解与豁免字段的变异直接落在
`workpaper_writer_domain_overlay.json`，针对判定逻辑的变异落在生成器/门，并且 `want` 一律指向
**现场重推**（`build_inventory` / `evaluate_gate`）的那条判据。

═══ 四态 ═══
RED=守卫有效 · GREEN=守卫缺陷或无效变异（须归因）· WRONG-TEST=红了但不是预期项 ·
ANCHOR-MISS=脚本缺陷（锚点未命中/命中多处）。只看退出码会把后三态误判成 RED。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task74_domain_adjudication_guards.py --list
    python backend/scripts/diagnose/mutate_task74_domain_adjudication_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task74_domain_adjudication_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task74-domain-adjudication/mutation_report.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GEN = "backend/scripts/gen/generate_workpaper_writer_inventory.py"
GATE = "backend/scripts/check/check_workpaper_writer_revision_gate.py"
AUTHOR = "backend/scripts/gen/adjudicate_task74_writer_domains.py"
OVERLAY = "backend/data/workpaper_writer_domain_overlay.json"
T74 = "test_task74_domain_adjudication"
INV = "test_workpaper_writer_inventory"

#: 被裁决行里挑两条做注解对调的对象。两条都在 `checklist_response_store` lane，事实**不同**
#: （一条 remark-only、一条 remark+conclusion+delete），所以对调后「注解引用的事实必须逐条重算」
#: 双向都会红。整行锚点取自 overlay（JSON indent=2，一条注解占一行）。
SWAP_SOURCE = "app.routers.l4_bonds_payable::l4_import_data"

#: 覆盖面分母：本任务新建 / 同批搬动的守卫文件。
GUARD_FILES = {
    "test_task74_domain_adjudication.py":
        "Task 74 新建：两条准则真的归零、域裁决**只**清这两条（行为级，摘掉裁决重推清册逐条比对）、"
        "注解逐条引用该行真实事实（双向，粘贴即红）、注解身份锚在自己那一行、注解两两不同且无占位词、"
        "overlay 无豁免字段、两条新 lane 买不到东西（正向 + `orchestrator_side_effect` 反向对照）、"
        "必需 domain 仍是真子集、规则表 fail-closed 且无 catch-all",
    "test_workpaper_writer_inventory.py":
        "Task 3 清册守卫，随 Task 74 同批搬动两处：`unadjudicated_writer` 由「必须非空」改成「必须为零 + "
        "门点名的每一行都能在 overlay 查到理由」；退役台账反证改在**构造**的清册上做（Task 74 把两条真实"
        "副作用行裁决进 `orchestrator_side_effect` 之后，活体清册里该 domain 不再只有台账一个来源）",
}

MUTATIONS: list[Mutation] = [
    # ═══ ① 规则表：fail-closed 与无 catch-all ═════════════════════════════
    Mutation(
        id="N01", side="be", path=AUTHOR, kind="replace",
        anchor="    raise SystemExit(",
        new='    return ("default", "html_save", "unmatched", "unmatched")  # mutated: 给默认 lane',
        want=f"{T74}.py::test_the_authoring_rules_refuse_an_unmatched_row",
        why="命不中规则时不再抛错而是给一个默认 lane ⇒ 「未裁决伪装成已裁决」：门会显示 0，"
            "而那一行从来没有人看过。这是本任务最贵的一种假绿",
    ),
    Mutation(
        id="N02", side="be", path=AUTHOR, kind="replace",
        anchor="        match=_writes_only_checklist,",
        new="        match=lambda e: True,  # mutated: catch-all 规则",
        want=f"{T74}.py::test_the_rule_table_has_no_catch_all",
        why="把最大的一条规则改成恒真 ⇒ 125 行的 lane 判定退化成「凡是没被前面规则接住的都算"
            "第二权威存储」，等价于默认 lane，只是伪装成一条具体规则",
    ),
    # ═══ ② 注解质量：事实逐条可重算（反模板）════════════════════════════
    Mutation(
        id="N03", side="be", path=OVERLAY, kind="replace",
        anchor=None,  # 运行期由 _swap_note_anchor() 填，见文件末尾
        new="",
        want=f"{T74}.py::test_every_note_cites_exactly_the_facts_that_row_has",
        wants=(
            f"{T74}.py::test_every_note_is_anchored_on_its_own_row",
            f"{T74}.py::test_notes_are_pairwise_distinct_and_carry_no_placeholder",
        ),
        why="把一行的注解原样粘到另一行（复制粘贴的**实际形态**）⇒ 被粘的那行注解引用的事实不再"
            "属于它自己。三条判据都要红：事实双向核算、身份前缀、两两不同",
    ),
    Mutation(
        id="N04", side="be", path=OVERLAY, kind="replace",
        anchor='      "domain": "unified_commit_substrate",',
        new='      "domain": "unified_commit_substrate",\n      "allow_bypass": true,',
        want=f"{T74}.py::test_the_overlay_still_has_no_exemption_field",
        wants=(f"{INV}.py::test_adjudications_are_domain_labels_not_bypass_exemptions",),
        why="往 overlay 里加一个豁免字段（`allow_bypass`）⇒ Task 74 正文四条禁令里的第一条。"
            "overlay 只能回答「属于哪条 lane」，多一个字段就多一条「是否允许绕过」的语义入口",
    ),
    # ═══ ③ 门是否**还在算**这两条准则 ═══════════════════════════════════
    Mutation(
        id="N05", side="be", path=GATE, kind="replace",
        anchor='        if adjudication.get("status") != "adjudicated":',
        new="        if False:  # mutated: 不再计算未裁决准则",
        want=f"{T74}.py::test_adjudicating_clears_exactly_two_criteria",
        why="归零之后「门不再计算这条准则」与「门算出 0」在报告里逐字相同 —— 这是 fail-open 的"
            "教科书形态。判据靠「摘掉裁决必须回到 236 / 34」反向证明门真的在算",
    ),
    # ═══ ④ 域标签不得买到任何豁免 ═══════════════════════════════════════
    Mutation(
        id="N06", side="be", path=GEN, kind="replace",
        anchor="                    and not artifact_snapshot_only",
        new="                    and not artifact_snapshot_only\n"
            "                    and adjudication is None  # mutated: 裁决即豁免",
        want=f"{T74}.py::test_adjudicating_clears_exactly_two_criteria",
        wants=(f"{INV}.py::test_adjudications_are_domain_labels_not_bypass_exemptions",),
        why="让 `bypasses_unified_commit` 看一眼 `adjudication` ⇒ 裁决 270 行的同时把 261 条绕过"
            "全部清掉。这正是「加豁免」的最隐蔽写法：没有豁免列，豁免藏在 verdict 的算式里",
    ),
    # ═══ ⑤ 新 lane 不得变成必需 lane ════════════════════════════════════
    Mutation(
        id="N07", side="be", path=GATE, kind="replace",
        anchor='    "orchestrator_side_effect",',
        new='    "orchestrator_side_effect",\n    "read_only_evaluation",',
        want=f"{T74}.py::test_the_required_domains_stay_a_proper_floor",
        why="把本任务新造的 lane 塞进门的 `_REQUIRED_DOMAINS` ⇒ 「必需 domain 是覆盖地板」这层"
            "语义被本任务自己的新词污染（与 Task 20 的 M19 同型：不改任何计数，只抹掉一层语义）",
    ),
]


def _swap_note_anchor() -> None:
    """N03 的锚点/替换内容在运行期从 overlay 现算 —— 注解太长，写死在脚本里必然与 overlay 分叉。"""
    import json

    overlay = json.loads((REPO / OVERLAY).read_text(encoding="utf-8"))
    adjudications = overlay["adjudications"]
    keys = sorted(adjudications)
    source = SWAP_SOURCE
    # 找一条 lane 相同、事实不同的邻居当粘贴源。
    lane = adjudications[source]["domain"]
    donor = next(
        key
        for key in keys
        if key != source
        and adjudications[key]["domain"] == lane
        and adjudications[key]["version_domain_note"] != adjudications[source]["version_domain_note"]
    )

    def line_for(key: str) -> str:
        note = adjudications[key]["version_domain_note"]
        return f'      "version_domain_note": {json.dumps(note, ensure_ascii=False)}'

    # overlay 以 `sort_keys=True` 写出，`version_domain_note` 是每条裁决的**最后**一个键
    # ⇒ 行尾没有逗号。首版给锚点补了逗号，`--check-anchors` 当场报 MISS（0 次命中）。
    target = next(m for m in MUTATIONS if m.id == "N03")
    target.anchor = line_for(source)
    target.new = line_for(donor)
    target.why += f"（实测把 `{donor}` 的注解粘到 `{source}` 上）"


if __name__ == "__main__":
    _swap_note_anchor()
    raise SystemExit(
        run_cli(
            repo=REPO,
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            backend_args=[
                "backend/tests/workpaper_sync/test_task74_domain_adjudication.py",
                "backend/tests/test_workpaper_writer_inventory.py",
                "-q",
                "--no-header",
                "-p",
                "no:randomly",
            ],
            description="Task 74 逐 domain 裁决守卫变异检验",
        )
    )
