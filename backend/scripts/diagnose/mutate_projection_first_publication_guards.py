#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""首版 published representation 生产链守卫的变异检验（F5）。

**Spec: published-representation-production-path-and-lane-adjudication** · Task 10.1
Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8

═══ 为什么需要它 ═══════════════════════════════════════════════════════════════

「测试全绿」不证明守卫有效 —— 只证明**当前代码**没触发它们。把生产代码改坏、看守卫是否
打红，才是判据本身有没有承重的唯一检验。本仓库记录的三种假绿全部能被变异抓住：

① additive 死代码       —— 新函数写了但没人调，测试测的是那个不被调用的实现
② 判据落在字符串存在性  —— 源码里有那个名字就算通过，改掉行为照样绿
③ 守卫把恒真值当基线锁死 —— 判据比的是一个永远成立的量

═══ 四态判读（不以退出码代替判读）═══════════════════════════════════════════════

RED          打红了，且新增失败测试**落在** `want` 里 ⇒ 守卫有效
GREEN        改坏了却没红 ⇒ **守卫有缺陷**（不是「代码没问题」）
ANCHOR-MISS  锚点命中次数 ≠ 1 ⇒ **本脚本有缺陷**（锚点写错或代码已重构）
WRONG-TEST   打红了但新增失败与 `want` 无交集 ⇒ 锚点错行，或上一轮污染残留

🔴 WRONG-TEST 的判据是「失败测试名**差集**」，不是「有没有失败」：基线本来就有失败时，
   只看有无失败会把既存红当成变异战果。

═══ 锚点纪律（全部踩过的坑）═══════════════════════════════════════════════════

* 命中次数必须**恰为 1** —— 多处命中时替换会同时改多个位点，判读失去意义
* 锚点**不含 `\\n`** —— 本仓库是 CRLF，跨行锚点在磁盘上是 `\\r\\n`，必 MISS
* 读盘后先 CRLF → LF 归一，写回时按**原样**写（不引入行尾变更）
* 还原后 **sha256 自证**：不等即立刻抛，宁可炸也不留污染的生产文件
* 测试调用走 `subprocess.run([...])` 列表形式，**不经 shell** ——
  `-k "a or b"` 经 shell 会被拆成多个位置参数

用法（仓库根，Windows PowerShell）::

    python backend/scripts/diagnose/mutate_projection_first_publication_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_projection_first_publication_guards.py --run
    python backend/scripts/diagnose/mutate_projection_first_publication_guards.py --run --only M1,M5
    python backend/scripts/diagnose/mutate_projection_first_publication_guards.py --run --json out.json
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Sequence

_REPO: Final[Path] = Path(__file__).resolve().parents[3]

# 被变异的生产文件
LANE: Final[str] = "backend/app/services/workpaper_sync/projection_lane_registry.py"
F2: Final[str] = "backend/app/services/workpaper_sync/projection_first_publication.py"
HOST: Final[str] = "backend/scripts/fix/fix_projection_first_publication.py"

# 靶子测试文件
T_LANE: Final[str] = "backend/tests/workpaper_sync/test_projection_lane_registry.py"
T_PUB: Final[str] = "backend/tests/workpaper_sync/test_projection_first_publication.py"

#: 基线最少通过数 —— 低于它说明测试根本没跑起来（import 错、收集失败），
#: 此时任何「变异未打红」的判读都是无意义的。
#:
#: 🔴 **逐文件**给阈值，不用一个全局数：F6 与 F7 的规模不同（实测 45 / 27），
#: 用一个全局 60 会把「F7 正常通过 27 条」误判成「测试没跑起来」——
#: 首版就是这么写的，第一次 `--run` 即被自己的自检拦住。
#: 阈值取「当前实测条数打八折」，留出增删空间但仍能抓住收集失败（那种情况通常是 0）。
MIN_BASELINE_PASSED: Final[Mapping[str, int]] = {
    T_LANE: 36,
    T_PUB: 20,
}


class MutationHarnessError(RuntimeError):
    """本脚本自身的缺陷（锚点、还原、环境）—— 与「守卫有缺陷」严格区分。"""


@dataclasses.dataclass(frozen=True)
class Mutation:
    """一条变异。

    :param id: 稳定短 id（报告与 `--only` 用）
    :param path: 被改的**生产**文件（仓库相对路径）
    :param anchor: 单行锚点，命中次数必须恰 1，不含换行
    :param new: 替换后的文本
    :param test: 跑哪个测试文件
    :param want: 预期打红的**具体测试名**集合（`want` 空集是不允许的）
    :param why: 它守的假绿形态 —— 变异存在的理由，不是描述改了什么
    """

    id: str
    path: str
    anchor: str
    new: str
    test: str
    want: frozenset[str]
    why: str

    def __post_init__(self) -> None:
        # 🔴 只禁 `\r`，**允许** `\n`。
        #
        # tasks.md 原文要求「锚点不含 `\n`」，理由是「CRLF 下跨行锚点必 MISS」。本脚本
        # 在匹配**之前**已经把读入文本 CRLF → LF 归一（`_read_normalised`），那个失效
        # 原因已经不存在，因此该限制在这里是过紧的。
        #
        # 而它确实**拦住了正确的变异**：三条变异在语法上必须跨行才能成立 ——
        #   * M3：`raise X(...) from exc` 的 `from exc` 子句必须一并替换，
        #         否则残留的 `from exc` 是语法错；
        #   * M6：`adapter=adapter` 全文出现两次，只替换目标那处需要带上下文行；
        #         而在其旁边**新增** `adapter=None` 会构成重复关键字实参（语法错）。
        #   * M8：`async with Session()` 需连同其后一行一起改才能表达「共用外层事务」。
        # 强行改成单行锚点的结果就是首轮那样：语法错 → collection error → 误判 GREEN。
        #
        # 仍然禁 `\r`：锚点一律按 LF 书写，含 `\r` 说明是从磁盘原文直接粘来的，
        # 那会在归一后的文本上必然 MISS。
        if "\r" in self.anchor:
            raise MutationHarnessError(
                f"{self.id}: 锚点含 `\\r` —— 锚点一律按 LF 书写（匹配前已 CRLF 归一）"
            )
        if not self.want:
            raise MutationHarnessError(
                f"{self.id}: `want` 为空 —— 没有预期靶子的变异只会判 WRONG-TEST，"
                "不能证明任何事"
            )


MUTATIONS: Final[tuple[Mutation, ...]] = (
    # ── 1. L1 分支后移 ────────────────────────────────────────────────
    Mutation(
        id="M1",
        path=LANE,
        # 唯一化：`adjudicate_lane` 里的 L1 紧跟 `return LaneVerdict.opaque`，
        # 而 `_adjudicate_with_diagnostic` 里那处紧跟 `lane_id = ...`。
        # 🔴 首版把锚点放在 L1 上方的**注释行**上，替换后 `if False:` 与原 `if` 的缩进
        #    错乱 ⇒ 语法错 ⇒ collection error ⇒ 被误判 GREEN。改为短路 L1 的**判据函数**：
        #    `_is_opaque_entry_id` 恒假 ⇒ L1 分支永不进入，等价于把它排到 L2 之后。
        #    锚点选函数体内那一行 `return entry_id.startswith(...)`（全文唯一）。
        anchor="    return entry_id.startswith(_opaque_entry_prefix())",
        new="    return False and entry_id.startswith(_opaque_entry_prefix())  # ← 变异：L1 恒假",
        test=T_LANE,
        want=frozenset(
            {
                "test_opaque_entry_id_is_adjudicated_opaque",
                "test_opaque_verdict_holds_even_with_an_empty_manifest",
                "test_real_opaque_representation_entry_is_opaque",
                "test_any_entry_id_under_the_opaque_prefix_is_opaque",
                "test_opaque_raises_lane_is_opaque_with_lane_id",
                "test_l1_branch_precedes_the_manifest_lookup_in_source_order",
                "test_every_declared_lane_id_is_reachable_from_an_entry_id",
            }
        ),
        why=(
            "opaque entry_id **永不在 manifest 里** ⇒ L1 后移后它先撞 L2 的 undecided，"
            "L1 成为不可达分支。后果：已有 opaque representation 的底稿被判「判据不足」，"
            "首版入口会拿它去发 projection 首版 —— 那会覆盖用户的权威 OOXML。"
        ),
    ),
    # ── 2. supply_satisfied 只读判据 A ────────────────────────────────
    Mutation(
        id="M2",
        path=LANE,
        anchor="            self.projection_bundle_provisioned",
        new="            self.projection_bundle_provisioned or True  # ← 变异：只读 A",
        test=T_LANE,
        want=frozenset(
            {
                "test_each_single_false_breaks_satisfaction",
                "test_satisfaction_equals_conjunction_over_all_16_states",
                "test_all_sixteen_states_are_actually_exercised",
            }
        ),
        why=(
            "四条判据合成一条 ⇒ 「有 approved bundle」被当成「供给成立」。而 B/C/D 分别管"
            "「有 current representation」「它绑的是 projection_contract bundle」"
            "「磁盘契约 digest 与 slot digest 一致」—— 少任一条都会让首版入口对着一个"
            "身份已漂移的对象动手。"
        ),
    ),
    # ── 3. 观测失败降级 ───────────────────────────────────────────────
    Mutation(
        id="M3",
        path=LANE,
        # 跨行锚点：必须把 `from exc` 一并吃掉，否则残留子句是语法错（首轮实测）。
        anchor=(
            "        raise LaneSupplyObservationError(\n"
            "            f\"供给观测失败（entry_id={entry_id!r} wp_id={wp_id} \"\n"
            "            f\"project_id={project_id}）: {type(exc).__name__}: {exc}\"\n"
            "        ) from exc"
        ),
        new=(
            "        criterion_a = criterion_b = False  # ← 变异：取数失败降级成四条皆假\n"
            "        criterion_c = criterion_d = False"
        ),
        test=T_LANE,
        want=frozenset(
            {
                "test_broken_session_raises_instead_of_returning_false_facts",
                "test_source_reraises_rather_than_returning_a_default",
            }
        ),
        why=(
            "fail-open 掩盖接线错误：「四条皆假」是**已知**供给不足，「查不出来」是**未知**。"
            "把后者伪装成前者，会让权限缺失、schema 漂移、连接故障全部长得像"
            "「这个 entry 还没发首版」，于是首版入口照发 —— 而它其实可能已经有 representation。"
        ),
    ),
    # ── 4. resolve_plan 第 ③ 条期望值取反 ─────────────────────────────
    #
    # 🔴 锚点选的是**判据 B 那一行**，不是 `expected_revision`。任务原文说的「第 ③ 条」
    #    在 `resolve_plan` 的判据表里就是「供给判据 B 必须为 **False**（首版专用）」；
    #    `expected_revision` 是乐观锁基准，属另一件事。
    Mutation(
        id="M4",
        path=F2,
        anchor="    if facts.published_representation_current:",
        new="    if not facts.published_representation_current:  # ← 变异：期望值取反",
        test=T_PUB,
        want=frozenset(
            {
                "test_existing_current_representation_is_rejected",
                "test_absent_current_representation_passes_criterion_three",
            }
        ),
        why=(
            "首版入口被拿去覆盖既有 representation。判据 ③ 要求判据 B 为 **False** ——"
            "取反后，「已经有 current published representation」反而成了准入条件，"
            "而「还没有」被拒。后果：本入口会对着一个用户正在用的 representation 发"
            "「首版」，把它的代际链踩掉；同 content version 的新代际本该走 Task 36/77 "
            "的 finalize gate。"
        ),
    ),
    # ── 5. 删掉 OOXML 安全门 ──────────────────────────────────────────
    Mutation(
        id="M5",
        path=F2,
        anchor="        report = validate_ooxml_artifact(",
        new="        report = _FakeReport() if False else _skip_ooxml_gate(",
        test=T_PUB,
        want=frozenset(
            {
                "test_b60_authoritative_bytes_are_rejected_with_a_named_gate",
            }
        ),
        why=(
            "B60 的 `external_relationships` 静默通过 ⇒ 带外部链接的权威字节被当成 substrate "
            "发布。那是安全策略裁决的对象（`xl/externalLinks/_rels/externalLink1.xml.rels`），"
            "不是可以顺手放宽的技术细节。"
        ),
    ),
    # ── 6. commit 传空 adapter ────────────────────────────────────────
    Mutation(
        id="M6",
        path=F2,
        # 跨行锚点：`adapter=adapter` 全文两处（叠加层调用 + commit 调用），用其上一行
        # 定位到 commit 那一处；**替换**而不是新增，否则重复关键字实参是语法错。
        anchor=(
            "        mutation=BusinessMutation(projection=projection),\n"
            "        adapter=adapter,"
        ),
        new=(
            "        mutation=BusinessMutation(projection=projection),\n"
            "        adapter=None,  # ← 变异：绕开 _assert_authority_shape"
        ),
        test=T_PUB,
        want=frozenset(
            {
                "test_publish_never_passes_a_null_adapter",
            }
        ),
        why=(
            "绕开 `_assert_authority_shape`：它要求 `adapter` / `contract` / "
            "`mutation.projection` 三者非空。以空 adapter 提交等于让 representation 落库时"
            "没有任何授权形态校验 —— 那道门是「不得产出无人能反读的 representation」的唯一保证。"
        ),
    ),
    # ── 7. 第二处 lane 判定点 ─────────────────────────────────────────
    Mutation(
        id="M7",
        path=F2,
        anchor="FIRST_PUBLICATION_DIRECTION: Final[str] = \"html_to_oo\"",
        new=(
            "FIRST_PUBLICATION_DIRECTION: Final[str] = \"html_to_oo\"\n\n\n"
            "def _is_opaque_second_source(entry_id: str) -> bool:\n"
            "    # ← 变异：在本模块另写一处 lane 判定（第二真源）\n"
            "    return entry_id.startswith(\"opaque-\")"
        ),
        test=T_LANE,
        want=frozenset(
            {
                "test_scanner_passes_on_the_current_tree",
            }
        ),
        why=(
            "第二真源：lane 归属一旦有两处判定，两处就会各自演化。本仓库已付过学费 ——"
            "`opaque-` 前缀的唯一构造处是 `writer_migration.opaque_entry_id`，"
            "唯一判定处必须是 `adjudicate_lane`。全仓 AST 扫描器就是为此存在的。"
        ),
    ),
    # ── 8. --apply 共用一个事务 ───────────────────────────────────────
    Mutation(
        id="M8",
        path=HOST,
        # 🔴 首版锚点落在**注释行**上 ⇒ AST 完全不变（空操作）⇒ 判读必然 GREEN 而与
        #    守卫无关。改为把 `async with Session()` 换成**复用外层 session** 的形态：
        #    `contextlib.nullcontext(outer_session)` 让循环体不再各开各的事务。
        #    这才真正表达「共用一个事务」，且语法合法。
        anchor=(
            "            # ── 每个 entry 一个独立 session/事务 ────────────────────\n"
            "            async with Session() as session:"
        ),
        new=(
            "            # ← 变异：共用外层事务（不再逐 entry 独立 session）\n"
            "            async with contextlib.nullcontext(_shared_session) as session:"
        ),
        test=T_PUB,
        want=frozenset(
            {
                "test_apply_uses_one_session_per_entry",
                "test_apply_rolls_back_only_the_failing_entry",
            }
        ),
        why=(
            "一处失败全部回滚：四个 entry 里 H1 与 D2 各自被不同原因挡住（实测），"
            "共用事务时 G7 的成功提交会被它们连带回滚 —— 那正是 2026-09-04 首轮"
            "「四个 entry 一个都发不出去、库里 0 新增行」形态的加剧版。"
        ),
    ),
    # ── 9. 只取引用不调用（additive 死代码）───────────────────────────
    Mutation(
        id="M9",
        path=HOST,
        # 🔴 首版把调用头换成 `_unused = (`，后面残留的 `session=session,` 等具名实参
        #    在裸括号里就是语法错（`--check-anchors` 的语法预检抓到了它）。
        #    改为跨行锚点，把整个 `await` 调用连同实参列表一并换成「只取引用」：
        #    形态与真实事故一致 —— 函数写好了、单测全绿，而宿主一份都不发。
        anchor=(
            "                    receipt = await F2.publish_first_generation(\n"
            "                        session=session,\n"
            "                        resolution=resolution,\n"
            "                        artifacts=artifacts,\n"
            "                        repository=repository,\n"
            "                        plan=plan,\n"
            "                        staged=staged,\n"
            "                        store_payload=store_payload,\n"
            "                    )"
        ),
        new=(
            "                    receipt = F2.publish_first_generation  "
            "# ← 变异：只取引用不调用（additive 死代码）"
        ),
        test=T_PUB,
        want=frozenset(
            {
                "test_apply_actually_awaits_publish_first_generation",
            }
        ),
        why=(
            "假绿第①源（additive 死代码）：`publish_first_generation` 写好了、测试单独测它，"
            "但宿主只是引用而不 await ⇒ `--apply` 什么也不发，而测试全绿。"
            "本仓库这条形态已发生过，不是理论风险。"
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 锚点核对（只读，秒级）
# ═══════════════════════════════════════════════════════════════════════════


def _read_normalised(path: Path) -> str:
    """读盘并把 CRLF 归一成 LF —— 锚点一律按 LF 书写。"""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check_anchors() -> list[dict[str, object]]:
    """逐条核对锚点。只读，不改任何文件。

    三项判据，缺一都会让判读失去意义：

    1. **命中次数恰为 1** —— 多处命中会同时改多个位点
    2. **变异后语法仍合法** —— 语法错时 pytest 报 collection error，
       它不以 `FAILED` 开头 ⇒ 被误判成 GREEN（首轮 M1 / M3 实测踩到）
    3. **变异后 AST 真的变了** —— 只改注释/空白的变异是空操作，
       语义未变而判读却说「守卫没抓住」（首轮 M6 / M8 实测踩到）
    """
    rows: list[dict[str, object]] = []
    for mutation in MUTATIONS:
        path = _REPO / mutation.path
        row: dict[str, object] = {"id": mutation.id, "path": mutation.path}
        if not path.is_file():
            rows.append(
                {**row, "ok": False, "hits": 0, "detail": f"文件不存在: {mutation.path}"}
            )
            continue

        original = _read_normalised(path)
        hits = original.count(mutation.anchor)
        row.update({"hits": hits, "anchor": mutation.anchor[:70]})
        if hits != 1:
            rows.append({**row, "ok": False, "detail": f"命中 {hits} 次（需恰 1）"})
            continue

        mutated = original.replace(mutation.anchor, mutation.new)
        try:
            tree_before = ast.parse(original)
            tree_after = ast.parse(mutated)
        except SyntaxError as exc:
            rows.append(
                {
                    **row,
                    "ok": False,
                    "detail": (
                        f"变异后语法错（line {exc.lineno}: {exc.msg}）—— "
                        "pytest 会报 collection error 而非 FAILED，判读会被误当 GREEN"
                    ),
                }
            )
            continue

        if ast.dump(tree_before) == ast.dump(tree_after):
            rows.append(
                {
                    **row,
                    "ok": False,
                    "detail": (
                        "变异后 AST 与原文**完全相同** —— 这是空操作（只改了注释或空白），"
                        "语义未变，判读必然 GREEN 而那与守卫无关"
                    ),
                }
            )
            continue

        rows.append({**row, "ok": True, "detail": ""})
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 测试执行
# ═══════════════════════════════════════════════════════════════════════════


#: 收集期失败的标志 —— 这些**不以** `FAILED` 开头，只数 FAILED 行会漏掉它们。
_COLLECTION_MARKERS: Final[tuple[str, ...]] = (
    "ERROR collecting",
    "errors during collection",
    "error during collection",
    "INTERNALERROR",
    "SyntaxError",
    "IndentationError",
    "ImportError while loading conftest",
)


def _run_pytest(test_path: str) -> tuple[set[str], int, str, bool]:
    """跑一个测试文件，返回（失败测试名集合, 通过数, 尾部输出, 是否收集期失败）。

    走列表形式的 `subprocess.run`，**不经 shell**。

    🔴 第四个返回值是 2026-09-04 首轮 `--run` 暴露出来的坑：变异若让文件**语法错**，
    pytest 报的是 `ERROR collecting`（collection error），它**不以 `FAILED` 开头** ⇒
    只数 FAILED 行会得到「零新增失败」⇒ 判读成 **GREEN**，即「守卫有缺陷」。
    实际上那是**本脚本**的缺陷：变异根本没被执行到。两者的处置完全相反，必须分开。
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(_REPO),
        capture_output=True,
    )
    text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode(
        "utf-8", "replace"
    )
    failed = {
        line.split("::")[-1].split()[0]
        for line in text.splitlines()
        if line.startswith("FAILED")
    }
    passed = 0
    for line in reversed(text.splitlines()):
        if " passed" in line:
            for token in line.replace("=", " ").split():
                if token.isdigit():
                    passed = int(token)
                    break
            if passed:
                break
    collection_failed = any(marker in text for marker in _COLLECTION_MARKERS)
    return failed, passed, text[-900:], collection_failed


def _baselines(tests: Sequence[str]) -> dict[str, tuple[set[str], int]]:
    """各测试文件的基线失败集与通过数。

    🔴 `passed < MIN_BASELINE_PASSED` 即中止：测试没跑起来时，「变异未打红」这个判读
    是无意义的 —— 它只说明测试根本没执行。
    """
    out: dict[str, tuple[set[str], int]] = {}
    for test in tests:
        failed, passed, tail, collection_failed = _run_pytest(test)
        if collection_failed:
            raise MutationHarnessError(
                f"基线本身就收集失败（{test}）—— 先修测试文件再跑变异:\n{tail}"
            )
        floor = MIN_BASELINE_PASSED.get(test)
        if floor is None:
            raise MutationHarnessError(
                f"{test} 没有登记基线阈值 —— 新增靶子文件必须同时登记 "
                "`MIN_BASELINE_PASSED`，否则「测试没跑起来」这类故障会静默通过"
            )
        if passed < floor:
            raise MutationHarnessError(
                f"基线通过数 {passed} < {floor}（{test}）—— "
                f"测试没有真正跑起来，判读无意义。尾部输出:\n{tail}"
            )
        out[test] = (failed, passed)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 变异执行
# ═══════════════════════════════════════════════════════════════════════════


def run_mutations(only: frozenset[str] | None = None) -> dict[str, object]:
    """逐条执行变异并四态判读。生产文件恒被还原且 sha256 自证。"""
    selected = [m for m in MUTATIONS if only is None or m.id in only]
    if not selected:
        raise MutationHarnessError(f"`--only` 没选到任何变异: {sorted(only or ())}")

    anchor_rows = {str(r["id"]): r for r in check_anchors()}
    tests = sorted({m.test for m in selected})
    started = time.time()
    baseline = _baselines(tests)

    results: list[dict[str, object]] = []
    for mutation in selected:
        anchor_row = anchor_rows[mutation.id]
        record: dict[str, object] = {
            "id": mutation.id,
            "path": mutation.path,
            "test": mutation.test,
            "want": sorted(mutation.want),
            "why": mutation.why,
        }
        if not anchor_row["ok"]:
            record["verdict"] = "ANCHOR-MISS"
            record["detail"] = anchor_row["detail"]
            results.append(record)
            continue

        path = _REPO / mutation.path
        original_bytes = path.read_bytes()
        digest_before = hashlib.sha256(original_bytes).hexdigest()
        normalised = _read_normalised(path)
        try:
            path.write_text(
                normalised.replace(mutation.anchor, mutation.new), encoding="utf-8"
            )
            failed, passed, tail, collection_failed = _run_pytest(mutation.test)
        finally:
            path.write_bytes(original_bytes)
            digest_after = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest_after != digest_before:
                raise MutationHarnessError(
                    f"{mutation.id}: 还原后 sha256 不符（{digest_before[:12]} → "
                    f"{digest_after[:12]}）—— 生产文件 {mutation.path} 已被污染，立即人工检查"
                )

        base_failed, _base_passed = baseline[mutation.test]
        new_failures = failed - base_failed
        hit = new_failures & mutation.want
        if collection_failed:
            # 变异让测试收集不起来 ⇒ **本脚本**缺陷，不是守卫缺陷。
            # `--check-anchors` 的语法预检本该提前拦住它；能走到这里说明预检有漏。
            verdict = "ANCHOR-MISS"
            record["detail"] = (
                "变异后 pytest 收集失败（collection error）—— 变异根本没被执行到，"
                "判读无效。这是脚本缺陷，不是守卫缺陷"
            )
        elif not new_failures:
            verdict = "GREEN"
        elif hit:
            verdict = "RED" if new_failures <= mutation.want else "RED(+其它)"
        else:
            verdict = "WRONG-TEST"

        record.update(
            {
                "verdict": verdict,
                "new_failures": sorted(new_failures),
                "want_hit": sorted(hit),
                "passed_under_mutation": passed,
                "baseline_failures": sorted(base_failed),
            }
        )
        if verdict in {"GREEN", "WRONG-TEST"}:
            record["tail"] = tail
        results.append(record)

    verdicts = [str(r["verdict"]) for r in results]
    return {
        "schema_version": "mutate-projection-first-publication/1",
        "spec": "published-representation-production-path-and-lane-adjudication",
        "task": "10.1",
        "elapsed_sec": round(time.time() - started, 2),
        "baseline": {
            test: {"failures": sorted(f), "passed": p}
            for test, (f, p) in baseline.items()
        },
        "min_baseline_passed": dict(MIN_BASELINE_PASSED),
        "mutation_total": len(results),
        "verdict_counts": {v: verdicts.count(v) for v in sorted(set(verdicts))},
        "all_red": all(v.startswith("RED") for v in verdicts),
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 渲染与入口
# ═══════════════════════════════════════════════════════════════════════════


def _render_anchors(rows: Sequence[dict[str, object]]) -> str:
    lines = ["=== 锚点核对（只读）==="]
    for row in rows:
        mark = "OK " if row["ok"] else "🔴 "
        lines.append(
            f"  {mark} {row['id']:<4} 命中 {row['hits']}  {row.get('anchor', '')}"
        )
        if row["detail"]:
            lines.append(f"        {row['detail']}")
    bad = [r for r in rows if not r["ok"]]
    lines.append(f"  锚点可用 {len(rows) - len(bad)}/{len(rows)}")
    return "\n".join(lines)


def _render_run(report: dict[str, object]) -> str:
    lines = ["=== 变异检验（四态判读）==="]
    for test, info in report["baseline"].items():  # type: ignore[union-attr]
        lines.append(
            f"  基线 {test.rsplit('/', 1)[-1]:<46} passed={info['passed']} "
            f"failures={info['failures'] or '（无）'}"
        )
    lines.append("")
    for row in report["results"]:  # type: ignore[union-attr]
        verdict = str(row["verdict"])
        mark = "OK " if verdict.startswith("RED") else "🔴 "
        lines.append(f"  {mark} {row['id']:<4} {verdict}")
        if not verdict.startswith("RED"):
            lines.append(f"        want        = {row.get('want')}")
            lines.append(f"        new_failures= {row.get('new_failures')}")
            if row.get("detail"):
                lines.append(f"        detail      = {row['detail']}")
            lines.append(f"        守的形态    = {str(row['why'])[:150]}")
    lines.append("")
    lines.append(f"  判读分布: {report['verdict_counts']}")
    lines.append(f"  全部 RED: {report['all_red']}   用时 {report['elapsed_sec']}s")
    if not report["all_red"]:
        lines.append("")
        lines.append("  🔴 处置：GREEN → 补强守卫（**不是**代码没问题）；")
        lines.append("           ANCHOR-MISS → 本脚本缺陷，重指锚点；")
        lines.append("           WRONG-TEST → 锚点错行或污染残留，定位修正。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check-anchors", action="store_true", help="只读核对锚点（秒级）"
    )
    mode.add_argument("--run", action="store_true", help="执行全部变异并四态判读")
    parser.add_argument("--only", default="", help="逗号分隔的变异 id，如 M1,M5")
    parser.add_argument("--json", dest="json_path", default="", help="报告落盘路径")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass

    only = (
        frozenset(part.strip() for part in args.only.split(",") if part.strip())
        or None
    )

    try:
        if args.check_anchors:
            rows = check_anchors()
            print(_render_anchors(rows))
            payload: dict[str, object] = {
                "mode": "check-anchors",
                "rows": rows,
                "all_ok": all(r["ok"] for r in rows),
            }
            exit_code = 0 if payload["all_ok"] else 2
        else:
            payload = run_mutations(only)
            print(_render_run(payload))
            exit_code = 0 if payload["all_red"] else 1
    except MutationHarnessError as exc:
        print(f"[HARNESS-FAIL] {exc}")
        return 2

    if args.json_path:
        # 脚本内写文件，不用 PowerShell 重定向（`>` 会把中文腌成乱码）
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
