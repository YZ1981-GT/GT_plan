# -*- coding: utf-8 -*-
"""Task 101 上游就绪门守卫的变异检验（W spec 的 X1 产物，走 `_mutation_kit` 共享件）。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 101（判据本体）
      + Wave 6 Task 26（X1 变异脚本，本文件）
Requirements: 7.5, 7.6 · Property 27

═══ 归属与交接（2026-09-04）═══

W spec 的 Task 26 正文明写：

> ⚠ **X1 文件归 E**（分工书 §2：`backend/scripts/diagnose/mutate_*.py` 由 E 统一写，
> 四态判读标准统一）。C 的交付物是**变异清单 + 每条的预期态**，交 E 落成脚本

C 已交出清单（Task 26 正文的「已交付的 T5 变异清单（6/6 RED，可直接并入 X1）」六条）。
本文件是把那份清单落成**可复现产物**：交接前它只是 tasks.md 里的散文 —— W spec 目录下
实测只有三件套、无 evidence 目录、全仓无任何变异脚本引用该门 ⇒ 「6/6 RED」当时无法在
干净 checkout 下复算，而 Task 26 自己要求「CI job 在干净 checkout 下可跑」。

🔴 **本文件不代表 Task 26 已完成。** Task 26 在 Wave 6（`depends_on: [5]`），而 Wave 5 的
Task 25 / 29 现读均为 `[ ]`、Task 101 自身为 `[~]`。本文件只交付其中**判据已就位、基线已绿**
的那一部分（Wave 0 门的六条变异）。Task 26 的另外两项（范围边界判据、产物入库核查）
与门后各 Wave 的变异，等 C 推进到位后再补。复选框由 C 或 A 裁决，E 不擅自勾。

═══ 为什么只改守卫文件、不碰生产文件 ═══

六条变异全部落在 `test_workbook_row_change_upstream_gate.py` 自身 —— 该文件同时承载
**检测器**（`read_checkbox_occurrences` / `has_propagate_sheets_param` / `a1_rewrite_owners`）
与**测试**。改检测器、看它自己的反向自检是否打红，正是这类守卫唯一可被证伪的形态。

因此本文件与 B / C 共改的三个生产文件（`excel_row_shift.py` / `excel_materialize.py` /
`excel_extract.py`）**零交集**，不受 Task 101 的门约束（门约束的是改那三个文件的行为）。

═══ 避开 C 实测出的两类无效变异用例 ═══

Task 26 正文列了两类，本文件逐条对应处理：

1. **被收敛语义掩盖** —— 「同编号保留最后一次」会让行首锚定变异结果不变。
   守卫已改成收集**全部出现次数** + 重复即 fail-closed，故 M01 敏感。
2. **被第二道防线挡住** —— 正则里的 `^` 与调用侧的 `.match` **互为冗余**
   （`re.match` 自身锚定位置 0；`^` 在无 MULTILINE 时同样只匹配串首），单点变异必 GREEN。
   ⇒ M01 做**组合变异**：把 `^\\s*-\\s` 换成 `.*-\\s`，前导 `.*` 让 `.match` 的位置锚定
   一并失效 —— 一行之内同时击穿两道防线。实测：原正则 `{'16': [' ']}`，变异后
   `{'16': [' ', 'x']}`（叙述句里的 `- [x] 16.` 被当成真复选框）。

═══ 四态 ═══
RED=守卫有效 · GREEN=守卫缺陷（不是「代码没问题」）· WRONG-TEST=红了但不是预期项 ·
ANCHOR-MISS=脚本缺陷。**退出码不作判据**，判定只看失败测试名集合的差集。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_workbook_row_change_upstream_gate_guards.py --list
    python backend/scripts/diagnose/mutate_workbook_row_change_upstream_gate_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_workbook_row_change_upstream_gate_guards.py --run all
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 被变异的守卫文件。
GUARD = "backend/tests/workpaper_sync/test_workbook_row_change_upstream_gate.py"
SCOPE = "backend/tests/workpaper_sync/test_workbook_row_change_scope_boundary.py"

#: 可达性清册守卫。2026-09-05 C 收口后基线转绿（三文件合计 49 passed / 1 skipped），
#: 遂把它加进分母并补上 C 清单第 6 条「分母期望值改错」（M07）。
REACH = "backend/tests/workpaper_sync/test_workbook_row_change_reachability.py"

GUARD_FILES = {
    "test_workbook_row_change_upstream_gate.py":
        "Task 101 上游就绪门：复选框解析器正确（行首锚定、`*` 子任务不被截断、形态分母）、"
        "门的行为（`[x]` 外一律拦，含 `~` 进行中与 `-` 阻塞、子任务未完成也拦）、"
        "fail-closed 兜底（重复 id / 任务号消失）、反向判据（门关着时门后产物必须不存在）、"
        "Property 27 基线（A1 改写入口唯一）",
    "test_workbook_row_change_scope_boundary.py":
        "范围边界（Requirement 9.1–9.6）：行变更词表恰 insert/delete（不做 reorder、不做列"
        "方向）+ 元判据锁住该断言的 `==` 不被降级、OOXML 安全策略三个开关不放宽、"
        "跨工作簿/图表/透视登记而非传播且两词表不相交、N1 无模板目录写入调用"
        "（含经变量传递形态，双向：漏报与误报各一条变异）",
    "test_workbook_row_change_reachability.py":
        "可达性清册守卫 + design.md 分母表三向锁：D2 的 52 处传播需求等 Wave 0 复算值必须与"
        "清册 JSON、design.md 分母表、现算三方逐一相等（C 清单第 6 条「分母期望值改错」的落点）",
}

MUTATIONS: list[Mutation] = [
    # ═══ ① 行首锚定 —— 必须是组合变异（C 实测：单点必 GREEN）═══════════════
    Mutation(
        id="M01", side="be", path=GUARD, kind="replace",
        anchor=r'_CHECKBOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")',
        new=r'_CHECKBOX_RE = re.compile(r".*-\s\[([ x~\-])\]\*?\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")',
        want="test_checkbox_scan_is_line_anchored",
        why="🔴 组合变异：把 `^\\s*-\\s` 换成 `.*-\\s` —— 前导 `.*` 让调用侧 `.match` 的位置"
            "锚定同时失效，一行内击穿两道冗余防线。于是正文叙述句里的 `- [x] 16.` 被当成"
            "真复选框（实测 `{'16': [' ']}` → `{'16': [' ', 'x']}`）⇒ 门会读到错的上游状态。"
            "单独去掉 `^` 或单独把 `.match` 改 `.search` 都必 GREEN，那是 C 记录的第二类无效用例",
    ),
    # ═══ ② `*` 子任务被截断 ⇒ 分母缩水（实测 27 → 22）════════════════════
    Mutation(
        id="M02", side="be", path=GUARD, kind="replace",
        anchor=r'_CHECKBOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]\*?\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")',
        new=r'_CHECKBOX_RE = re.compile(r"^\s*-\s\[([ x~\-])\]\s+(\d+(?:\.\d+)*)\.?(?=\s|$)")',
        want="test_star_marked_subtasks_are_read_and_not_collapsed",
        wants=("test_whole_upstream_file_parses_to_expected_shape",),
        why="去掉 `\\]\\*?` 的 `\\*?` ⇒ 上游写成 `- [ ]* 2.1 …` 的可选子任务全部读不到，"
            "分母由 27 缩到 22。而「optional(*) 也要做完」是平台既定要求 ⇒ 接线勾了但其属性"
            "测试还空着时门会误判为就绪 —— 那正是共用文件已被改过却没有判据护着的最危险时点",
    ),
    # ═══ ③ 重复编号不再 fail-closed ═══════════════════════════════════════
    Mutation(
        id="M03", side="be", path=GUARD, kind="replace",
        anchor="    ambiguous = {n: found[n] for n in wanted if len(found[n]) != 1}",
        new="    ambiguous = {}  # mutated: 不再检测重复编号",
        want="test_duplicate_checkbox_is_fail_closed",
        why="同一编号出现多次时不再 fail-closed ⇒ 取哪一次都是猜。它还是行首锚定的**第二层"
            "保护**：锚定一旦失效会让编号重复出现，本判据本该立刻拦下；摘掉它，M01 那类"
            "错状态就能一路走到「就绪」",
    ),
    # ═══ ④ `~` 进行中被当成就绪 ═══════════════════════════════════════════
    Mutation(
        id="M04", side="be", path=GUARD, kind="replace",
        anchor='    pending = {n: s for n, s in states.items() if s != "x"}',
        new='    pending = {n: s for n, s in states.items() if s not in ("x", "~")}',
        want="test_gate_behaviour_on_synthetic_states",
        why="把 `~`（进行中）当成已完成 ⇒ 上游正在改那三个共用文件的**当下**，门反而放行，"
            "并行编辑互相回退的窗口被精确地开在最危险的时刻。注意本条不动 `-`（阻塞），"
            "故只有 `~` 那一组参数化用例会红 —— 判据必须能分辨两者",
    ),
    # ═══ ⑤ 门后产物检测器短路（fail-open）════════════════════════════════
    Mutation(
        id="M05", side="be", path=GUARD, kind="replace",
        anchor='        if "propagate_sheets" in params:',
        new="        if False:  # mutated: 检测器短路",
        want="test_propagate_sheets_detector_fires_on_synthetic_violation",
        wants=("test_wave2_artifacts_absent_while_gate_closed",),
        why="`has_propagate_sheets_param` 恒返回 False ⇒ 有人无视门、已经给 "
            "`_rewrite_formula_refs` 加了 `propagate_sheets`，反向判据也看不见。"
            "这条是那条反向判据的**唯一保护**：真实源码里今天该参数确实不存在，"
            "光跑真实源码永远绿，分不清「产物确实不存在」与「检测器根本没在看」",
    ),
    # ═══ ⑥ A1 owner 检测器掩盖第二入口（Property 27）══════════════════════
    Mutation(
        id="M06", side="be", path=GUARD, kind="replace",
        anchor="                owners.add(owner)",
        new='                owners.add("_rewrite_formula_refs")  # mutated: 恒报唯一 owner',
        want="test_a1_owner_detector_fires_on_second_entrypoint",
        why="🔴 把 owner 钉成恒为 `_rewrite_formula_refs` ⇒ 真实源码那条判据**照样绿**"
            "（今天确实只有一个入口），但有人另造第二个 A1 改写入口时检测器再也报不出来。"
            "Property 27 由此退化成恒真重言式 —— 只有「喂一份有第二入口的合成源」这条反向"
            "自检能抓到它，所以本条同时证明了那条反向自检是承重的",
    ),
    # ═══ ⑦ 分母期望值改错（C 清单第 6 条）══════════════════════════════════
    #
    # ═══ ⑦ 分母期望值改错（C 清单第 6 条）══════════════════════════════════
    #
    # 🔴 **本条锚点换过一次，教训留档。** 首版锚在
    # `assert row["propagation_demand_sites"] == 52, (`（当时探测到 L305）。实测判 GREEN，
    # 排查发现 C 在会话期间**重写了本守卫文件**，那行连同 `len(affected) == 136` 一并不存在，
    # L305 已是别的断言。而 `--check-anchors` **报了 OK** —— kit 拿「去行尾整行文本」在
    # **当前**文件里查唯一命中，我给的文本恰好与另一处同内容的行匹配上 ⇒ 锚点自检通过，
    # 但打的不是我以为的那处。
    # ⇒ **锚点必须按内容现查，不得沿用早先探测的行号。**「锚点命中」与「命中我想要的那一处」
    #    是两件事。这也正是 GREEN 这一态的价值：按退出码判定会把「锚点漂移」记成 RED。
    #
    # 现锚（2026-09-05 按内容现查，文件已 542 行）落在 C 新版的
    # `test_d2_is_the_only_entry_with_propagation_demand` 内，整行唯一。
    # 该守卫基线此前一度为红（清册 D2 已 `propagated`、守卫仍断言 `blocked`），
    # C 于 09-05 收口后转绿（三文件合计 49 passed / 1 skipped），故本条得以入清单。
    Mutation(
        id="M07", side="be", path=REACH, kind="replace",
        anchor='    assert with_demand == {"d2.receivable_detail": 52}, (',
        new='    assert with_demand == {"d2.receivable_detail": 999}, (',
        want="test_d2_is_the_only_entry_with_propagation_demand",
        why="把 D2 的传播需求处数（Wave 0 复算值 **52**）改成 999 ⇒ 分母断言必须打红。"
            "🔴 注意方向：把分母改**宽松**（`>= 0` 那类）不会有任何测试失败 ⇒ GREEN ⇒ "
            "那是无效变异。只有改成「更严格且不成立」才能证明该断言真的在跑、不是一行装饰。"
            "design.md 分母表、清册 JSON、现算三方互锁，任一侧漂移都该红",
    ),
    # ═══ ⑧⑨⑩ 范围边界（Requirement 9.1–9.6）══════════════════════════════
    # 🔴 M08「把 == 降级成 >=」与 M09「摘掉登记那半边断言」两条在首轮实测**均为 GREEN**，
    #    已从清单移除，原因不同且都不是「守卫缺陷」那么简单：
    #
    #    · M08 是**我设计错了**。kit 的语义里 GREEN 恒等于「守卫有缺陷」，无法表达「本条预期
    #      不红」。而「等值断言被降级成子集断言」这件事，在真实枚举仍只有两个成员时**没有任何
    #      测试能观察到** —— 它要的是「判据自身的运算符不许被改弱」，属**判据的判据**，
    #      正确的落法是元判据（读自身 AST 断言用的是 `Eq` 而非 `GtE`），不是变异。
    #      硬留在清单里只会让「全 RED」永远达不到，逼后来者去改本来正确的守卫。
    #
    #    · M09 揭示我的判据里真有**第二道防线**（C 记录的第二类无效用例）：摘掉
    #      `reason in UNPROPAGATED_REASONS` 后，紧随的 `reason not in PROPAGATION_CARRIERS`
    #      与 `test_..._are_disjoint` 仍然成立 ⇒ 不红。这不是守卫缺陷，是**该断言在当前
    #      词表形态下不承重**。按 C 的方法论，正解是改成能单点击穿的表达或删掉冗余断言，
    #      而不是把它记成 GREEN 挂着。已在守卫侧保留该断言（它对**将来**词表变化仍有意义），
    #      但不为它编一条注定 GREEN 的变异。
    Mutation(
        id="M08", side="be", path=SCOPE, kind="replace",
        anchor="        direct = any(marker in dumped for marker in _TEMPLATE_MARKERS)",
        new="        direct = True  # mutated: 模板写入检测器恒命中",
        want="test_no_template_directory_write_in_production_module",
        why="把 AC 9.6 检测器改成**恒命中** ⇒ 正向判据（真实 N1 不写模板目录）必须打红。"
            "它与 M10（恒不命中）成对：M10 证明「漏报会被反向自检抓到」，本条证明"
            "「误报会被正向判据抓到」。只做一个方向时，另一向的漂移会静默通过 —— "
            "与 Task 7 的 M4+M5 同型（那两条合起来才证明「双向」）",
    ),
    # ═══ ⑪ 元判据自身必须可被证伪 ═════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=SCOPE, kind="replace",
        anchor='    assert members == {"INSERT", "DELETE"}, (',
        new='    assert members >= {"INSERT", "DELETE"}, (',
        want="test_boundary_equality_assertions_are_not_downgraded_to_subset",
        why="🔴 把词表判据的 `==` 降级成 `>=` ⇒ **元判据**必须打红。这正是首轮那条 GREEN 变异"
            "（当时编号 M08）暴露的缺口：降级后真实枚举仍只有两个成员，常规判据观察不到，"
            "于是「有人往 `RowChangeKind` 加 REORDER 也不会红」这件事无人看守。补了读自身 AST "
            "的元判据之后，同一个变异从 GREEN 转 RED —— 变异检验的正确用法是据此**补强判据**，"
            "而不是把 GREEN 记在清单上当既成事实",
    ),
    Mutation(
        id="M10", side="be", path=SCOPE, kind="replace",
        anchor="        direct = any(marker in dumped for marker in _TEMPLATE_MARKERS)",
        new="        direct = False  # mutated: 模板写入检测器短路",
        want="test_template_write_detector_fires_on_synthetic_violation",
        why="把 AC 9.6 的模板目录写入检测器短路 ⇒ 有人往 `backend/wp_templates/` 写字节也"
            "看不见。真实 N1 今天确实不写模板目录，所以正向判据**照样绿** —— 只有那条"
            "「喂合成违规源」的反向自检能抓到。它与 M06 同型：正向判据在真实源上恒绿时，"
            "反向自检是唯一的承重件",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 101 上游就绪门守卫变异检验（W spec X1）",
            backend_args=[
                GUARD,
                SCOPE,
                REACH,
                "-q",
                "--no-header",
                "-p",
                "no:randomly",
                "--tb=no",
                "-rfE",
            ],
            # 实测基线（2026-09-05，干净工作树）：49 passed, 1 skipped。
            # 1 skipped = `test_wave2_artifacts_absent_while_gate_closed` 在门**已开**时
            # 自行 skip；今天门是关的（上游 Task 16/17/18 未全 [x]）故它真实执行。
            baseline_backend_passed=49,
        )
    )
