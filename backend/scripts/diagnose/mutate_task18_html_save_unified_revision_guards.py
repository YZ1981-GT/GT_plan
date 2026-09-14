# -*- coding: utf-8 -*-
"""Task 18 变异检验：普通 HTML save + orchestrator 迁入统一 revision 域的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 18
Requirements: 2.1, 2.2, 2.12, 3.1, 13.4
Properties: **P4**（业务版本与 representation generation 正交）/ **P54**（after-save
失败可重试）/ **P61**（所有 writer 进入唯一 revision 域）

═══ 变异改的是**生产代码**，不是守卫 ═══

落点三处：

* `app/routers/wp_html_save.py` —— 把 `parsed_data['_version']` 写回去、把乐观锁比对
  目标退回 `_version`、加回一个裸 `db.commit()`、删掉 stage/commit 接线、把 stage 挪到
  commit 之后、不再把 `content_revision` 传给 after_save、把 CAS 冲突吞成宽泛 except
* `app/services/workpaper_save_orchestrator.py` —— 注入 `file_version += 1`（Task 18
  刚搬走的那一行）、把允许写入集合偷偷放宽
* `app/services/workpaper_sync/content_mutation.py` —— 让 html-only lane 复用
  bidirectional 的必需步骤元组、去掉 capability 归一（`is` 比较对裸 str 恒 False）、
  放行 bidirectional、删掉数据库事实判据、把 CAS 换成无谓词 UPDATE、注入第二次
  revision bump、让 lane 自己写 entry pointer
* 三条 `file_version` 新所有者路径 —— 删掉各自的递增（证明"零 version 写"这条否定式
  承诺没有把行为退化一起放过）

═══ 判定四态 ═══

打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 本任务的判据设计教训 ═══

1. **否定式承诺只能靠注入 falsify**。「不再写 `parsed_data['_version']`」「after_save 零
   version 写」「lane 不产生 representation」都是"不存在某结构"，短路式变异改不动它们
   —— M01 / M07 / M13 全是 insert 型反例注入。
2. **改判据值必须与生产所有者同批搬**。Task 16 的
   `test_the_version_write_is_confined_to_the_pre_commit_half` 期望值从 1 降到 0 是合法
   的，**因为** `file_version` 的所有者搬到了三条真正写文件的路径。M14~M16 就是这三处
   的 falsifier：只要有人把期望值改成 0 而不搬生产，这三条会全部 GREEN（因为没有东西
   可删），从而暴露"只改数字"。
3. **`str` Enum 的 `is` 比较是隐蔽失效点**。`Capability` 是 `str, Enum`，
   `"bidirectional" == Capability.bidirectional` 为真但 `is` 为假。M09 去掉构造点的
   `Capability(...)` 归一，用来证明守卫真的覆盖了"调用方传裸字符串"这条路径。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task18_html_save_unified_revision_guards.py --list
    python backend/scripts/diagnose/mutate_task18_html_save_unified_revision_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task18_html_save_unified_revision_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task18-html-save-unified-revision/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

HTML = "backend/app/routers/wp_html_save.py"
ORCH = "backend/app/services/workpaper_save_orchestrator.py"
CM = "backend/app/services/workpaper_sync/content_mutation.py"
REPO_PY = "backend/app/services/workpaper_sync/repository.py"
UNIVER = "backend/app/routers/wp_editor_router.py"
OO = "backend/app/routers/wp_onlyoffice_router.py"
SNAPSHOT = "backend/app/services/custom_query/snapshot_writer.py"

#: 覆盖面分母：Task 18 新建 / 改造的守卫文件。
GUARD_FILES = {
    "test_task18_html_save_unified_revision.py":
        "Task 18 新建：AST 结构判据（不再写 parsed_data._version、乐观锁读 "
        "content_revision、零裸 commit、stage→commit 次序、after_save 收 "
        "content_revision、两条 lane 步骤元组互不重叠、DB 事实判据早于 CAS）"
        "+ 真实执行判据（bidirectional/single_onlyoffice/unreachable 构造即拒、"
        "capability 裸字符串归一、entry_id 命名空间）",
    "test_task18_html_save_unified_revision_pg.py":
        "Task 18 新建：真库行为（恰一次 revision、xmin 四表全等 + 恰一次数据库提交、"
        "零 representation/entry pointer、状态与 file_version 变化零 revision、"
        "CAS 冲突零移动 + 不可见 orphan、耐久入队失败整笔回滚且可重试恰一次）",
    "test_workpaper_save_orchestrator.py":
        "既有单测，被 Task 18 翻面：从『递增 file_version』改为『零版本写』"
        "（逐字段记录写入的替身 + 任意 trigger/revision/重放次数的 PBT）",
    "test_task16_durable_outbox_wiring.py":
        "Task 16 守卫，被 Task 18 同批搬动：version 写期望值 1→0，并新增 "
        "`file_version` 三所有者的双向判据",
    "test_wp_html_save.py":
        "既有 characterization，被 Task 18 加固：断言恰一次 commit_html_projection、"
        "plan 的 expected_revision 取自 content_revision、CAS 冲突 → 409",
}

T18 = "test_task18_html_save_unified_revision"
T18PG = "test_task18_html_save_unified_revision_pg"
W16 = "test_task16_durable_outbox_wiring"
ORCH_UT = "test_workpaper_save_orchestrator"
HTML_UT = "test_wp_html_save"

MUTATIONS: list[Mutation] = [
    # ══ 一、`parsed_data._version` 不可复活（Requirement 2.1）══════════════
    Mutation(
        id="M01", side="be", path=HTML, kind="insert",
        anchor='    parsed_data["last_modified_at"] = now.isoformat()',
        new='    parsed_data["_version"] = server_version + 1',
        want=f"{T18}.py::test_html_save_never_writes_the_parsed_data_version",
        why="把第二个真源写回去。「不再写 parsed_data['_version']」是否定式承诺，"
            "短路式变异改不动「不存在」，只能注入反例。这条同时是 Task 3 headline "
            "finding（一次保存移动两个计数器）的 falsifier",
    ),
    Mutation(
        id="M02", side="be", path=HTML, kind="replace",
        anchor='    server_version: int = int(getattr(working_paper, "content_revision", 0) or 0)',
        new='    server_version: int = int((parsed_data or {}).get("_version", 0) or 0)',
        want=f"{T18}.py::test_html_save_reads_the_business_revision_as_its_optimistic_lock",
        wants=(f"{HTML_UT}.py::test_save_409_data_version_conflict",),
        why="把乐观锁比对目标退回 `parsed_data['_version']` ⇒ 与真正推进的 "
            "`content_revision` 是两个计数器，客户端拿到的 server_version 与下次要提交的"
            "expected 不是同一个数。单测那条刻意让两者不同值（99 vs 3），所以「读错域」"
            "会直接从回传值上暴露",
    ),

    # ══ 二、统一提交边界（Requirement 2.2 / Property 61）═══════════════════
    Mutation(
        id="M03", side="be", path=HTML, kind="insert",
        anchor="    await DurableEventOutboxService.publish_pending(db)",
        new="    await db.commit()",
        want=f"{T18}.py::test_html_save_owns_no_direct_commit",
        why="给 router 加回一个裸 `db.commit()` ⇒ 「业务内容的唯一提交出口在 "
            "ContentMutationService」这条承诺失效。它是 Task 16 放宽 "
            "`_CONTENT_COMMIT_LEAVES`（允许把 content commit 认成 "
            "commit_html_projection）的补偿判据，必须可被单点变异 falsify",
    ),
    Mutation(
        id="M04", side="be", path=HTML, kind="replace",
        anchor="        receipt = await mutation_service.commit_html_projection(",
        new="        receipt = await _mut_absent_commit(",
        want=f"{T18}.py::test_html_save_routes_the_business_content_through_the_unified_service",
        wants=(
            f"{HTML_UT}.py::test_save_200_success",
            f"{T18}.py::test_the_revision_conflict_is_translated_not_swallowed",
        ),
        why="拆掉业务 commit 接线（结构保留、名字换掉）⇒ 内容根本不再进入统一 revision "
            "域。上一条是否定式的（没有裸 commit），把整个提交删掉也满足，所以必须有这条"
            "正面接线判据配对",
    ),
    Mutation(
        id="M05", side="be", path=HTML, kind="replace",
        anchor="    staged_projection = mutation_service.stage_html_projection(",
        new="    staged_projection = _mut_stage_after_commit(",
        want=f"{T18}.py::test_html_save_routes_the_business_content_through_the_unified_service",
        why="让 stage 不再是那次真实发布 ⇒ Requirement 2.4 的 staged artifact 协议"
            "（artifact 先耐久校验，再开短数据库事务写 pointer）失去落点",
    ),
    Mutation(
        id="M06", side="be", path=HTML, kind="replace",
        anchor="        content_revision=commit_plan.target_revision,",
        new="        content_revision=None,",
        want=f"{T18}.py::test_after_save_receives_the_business_revision_read_only",
        wants=(f"{T18PG}.py::test_the_outbox_row_carries_the_business_revision",),
        why="不再把本次预定 revision 传给 after_save ⇒ 审计日志与耐久 payload 里的版本"
            "变成 None，下游「按返回的新版本刷新」失去依据（真库那条断言两条耐久事件"
            "携带同一个 revision，会直接红）",
    ),

    # ══ 三、orchestrator 零版本写（Requirement 2.12 / Property 4）══════════
    Mutation(
        id="M07", side="be", path=ORCH, kind="insert",
        anchor="        wp.prefill_stale = True",
        new="        wp.file_version = (wp.file_version or 0) + 1",
        want=f"{W16}.py::test_the_version_write_is_confined_to_the_pre_commit_half",
        wants=(
            f"{ORCH_UT}.py::TestAfterSaveWritesNoVersionField"
            "::test_after_save_writes_no_version_field",
            f"{W16}.py::test_the_file_lifecycle_version_has_three_named_owners",
        ),
        why="把 Task 18 搬走的那一行注入回共享副作用 handler ⇒ 一个必须可重放的 handler "
            "又成了版本所有者，重放一次就多一个伪版本。「零 version 写」是否定式承诺，"
            "只能靠注入 falsify",
    ),
    Mutation(
        id="M08", side="be", path=ORCH, kind="replace",
        anchor='SIDE_EFFECT_WRITABLE_FIELDS: frozenset[str] = frozenset({"prefill_stale", "updated_at"})',
        new='SIDE_EFFECT_WRITABLE_FIELDS: frozenset[str] = frozenset({"prefill_stale", "updated_at", "file_version"})',
        want=f"{ORCH_UT}.py::TestAfterSaveWritesNoVersionField"
             "::test_the_allowed_write_set_is_exactly_the_two_side_effect_fields",
        why="偷偷放宽允许写入集合 ⇒ 「逐字段核对实际写入」那条判据会被自己的白名单满足。"
            "这是**改判据而不是改行为**的典型形态，必须有一条专门钉住白名单本身",
    ),

    # ══ 四、两条 lane 不可混淆（Requirement 3.1 / 3.9）════════════════════
    Mutation(
        id="M09", side="be", path=CM, kind="replace",
        anchor="        object.__setattr__(self, \"capability\", capability)",
        new="        pass  # mutation: skip Capability normalisation",
        want=f"{T18}.py::test_plan_accepts_the_capability_as_a_plain_string_too",
        why="去掉构造点的 `Capability(...)` 归一 ⇒ 调用方传裸字符串时 "
            "`capability is Capability.bidirectional` 恒为 False（`str` Enum 的 `==` 通过"
            "但 `is` 不通过），整条禁令静默失效。这是最隐蔽的一类：结构、日志、"
            "只传枚举的单测全都正常",
    ),
    Mutation(
        id="M10", side="be", path=CM, kind="replace",
        anchor="        if capability is Capability.bidirectional:",
        new="        if False:",
        want=f"{T18}.py::test_only_single_html_may_use_the_projection_only_lane[bidirectional]",
        wants=(
            f"{T18PG}.py::test_a_bidirectional_entry_cannot_use_the_projection_only_lane",
        ),
        why="放行 bidirectional ⇒ 恢复 design 明确拒绝的方案 #20（先提交 projection-only "
            "revision 再补 artifact）。三个 capability 分开参数化正是为了让这条只打红"
            "第一个实例，而不是被第二个 `if` 遮蔽",
    ),
    Mutation(
        id="M11", side="be", path=CM, kind="replace",
        anchor="HTML_ONLY_COMMIT_STEPS: tuple[str, ...] = (",
        new="HTML_ONLY_COMMIT_STEPS: tuple[str, ...] = CONTENT_COMMIT_STEPS + (",
        want=f"{T18}.py::test_the_two_lanes_have_disjoint_required_step_tuples",
        wants=(f"{T18PG}.py::test_plain_single_html_save_advances_the_business_revision_exactly_once",),
        why="让 html-only lane 复用 bidirectional 的必需步骤元组 ⇒ 两条 lane 的判据互相"
            "污染：bidirectional 的「representation 必须同事务写」多出一个可绕过分支，"
            "而 html-only 反过来会因为缺 representation 见证而在真库上直接失败",
    ),
    Mutation(
        id="M12", side="be", path=CM, kind="replace",
        anchor="            await self._assert_entry_has_no_representation(plan)",
        new="            pass  # mutation: drop the database-fact lane check",
        want=f"{T18}.py::test_the_database_fact_check_runs_before_the_revision_cas",
        why="删掉数据库事实判据 ⇒ 只剩「调用方声明的 capability」这一条来源。某个 entry "
            "日后真被接上 OO 而调用方仍传 single_html 时，会静默让 HTML 与 OO 分叉 —— "
            "两条判据来源不同，必须各自可 falsify",
    ),
    Mutation(
        id="M13", side="be", path=CM, kind="insert",
        anchor="            await witness.stamp(self._session, \"current_pointer\")",
        new="            await self._repo.set_entry_pointer(\n"
            "                wp_id=plan.wp_id, entry_id=plan.entry_id,\n"
            "                representation_id=uuid.uuid4(), generation=1,\n"
            "            )",
        want=f"{T18}.py::test_html_only_lane_bumps_the_revision_exactly_once_in_source",
        wants=(
            f"{T18PG}.py::test_the_single_html_lane_creates_no_representation_and_no_entry_pointer",
        ),
        why="让 html-only lane 写 entry pointer ⇒ 给一个没有 OO artifact 的入口造出"
            "「指向不存在 representation」的指针，正是 Requirement 3.9 禁止的。"
            "「零 entry pointer」是否定式承诺，只能靠注入 falsify",
    ),

    # ══ 五、`file_version` 三个新所有者必须真的还在（配对反证）══════════════
    Mutation(
        id="M14", side="be", path=UNIVER, kind="replace",
        anchor="    wp.file_version = old_version + 1",
        new="    pass  # mutation: univer save stops advancing the file lifecycle version",
        want=f"{W16}.py::test_the_file_lifecycle_version_has_three_named_owners",
        why="删掉 univer 保存路径的文件版本递增 ⇒ 版本快照名、doc_key 与前端 `v{n}` 全部"
            "凝固。这条与 M07 成对：只把 after_save 的期望值改成 0 而不搬生产，本条会 "
            "GREEN（没有东西可删），从而暴露「只改数字」",
    ),
    Mutation(
        id="M15", side="be", path=OO, kind="replace",
        anchor="            wp.file_version = (wp.file_version or 0) + 1",
        new="            pass  # mutation: OO callback stops advancing the file version",
        want=f"{W16}.py::test_the_file_lifecycle_version_has_three_named_owners",
        why="删掉 OO callback 写盘后的文件版本递增 ⇒ 同 M14。这三条一起把「所有者搬走了」"
            "变成可观测事实，而不是 docstring 里的说法",
    ),
    Mutation(
        id="M16", side="be", path=SNAPSHOT, kind="replace",
        anchor="                wp_obj.file_version = (wp_obj.file_version or 0) + 1",
        new="                pass  # mutation: custom writeback stops advancing the file version",
        want=f"{W16}.py::test_the_file_lifecycle_version_has_three_named_owners",
        why="删掉 custom 回写路径的文件版本递增 ⇒ 同 M14/M15",
    ),

    # ══ 六、CAS 与失败语义（Requirement 13.4 / Property 54）═══════════════
    Mutation(
        id="M17", side="be", path=HTML, kind="replace",
        anchor="    except RevisionConflictError as exc:",
        new="    except Exception as exc:  # noqa: BLE001",
        want=f"{T18}.py::test_the_revision_conflict_is_translated_not_swallowed",
        why="把 CAS 冲突的窄捕获放宽成 `except Exception` ⇒ 「artifact 发布失败」"
            "「事务分裂」「步骤缺失」全被吞成一句 409「其他用户已修改」，用户看到的原因"
            "是错的，而真正的故障在日志里也不再是 ERROR（Requirement 5.12 禁止的宽泛"
            "except 降级）",
    ),
    # 🔴 首轮这里注入的是「去掉 `bump_content_revision` 的 CAS 谓词」，实测 GREEN。
    #    归因：那不是守卫缺陷，是**无效变异** —— `assert_expected_revision` 先在
    #    advisory + 行锁下比过一次 expected，同 wp 的第二个事务在锁上排队、拿到的是已
    #    经推进后的值，所以 `WHERE content_revision = :expected` 在本 spec 的锁设计下
    #    是纵深防御，不在本任务任何场景里独立可观测。它的行为判据属于 Task 10 的多
    #    worker 用例（`test_task10_repository_pg.py`），本脚本不冒领。
    #    改成注入「跳过 expected 比对」——那一条是真实可观测的：陈旧 expected 会被放行，
    #    CAS 用实际 current 递增，随后 `RevisionTargetError` 取代 `RevisionConflictError`，
    #    真库守卫因此打红。
    Mutation(
        id="M18", side="be", path=REPO_PY, kind="replace",
        anchor="        if current != expected_revision:",
        new="        if False:",
        want=f"{T18PG}.py::test_a_lost_cas_race_moves_nothing_and_leaves_only_an_invisible_orphan",
        why="跳过 expected revision 比对 ⇒ 陈旧客户端的保存被放行（last-write-wins），"
            "Requirement 6.7 明令禁止。判据是真库行为（陈旧 expected 必须抛 "
            "RevisionConflictError 且一行都不动），不是「源码里有没有 WHERE」",
    ),
    Mutation(
        id="M19", side="be", path=CM, kind="insert",
        anchor='            await witness.stamp(self._session, "outbox")',
        scope="            payload = self._html_only_event_payload(",
        offset=9,
        new="            await self._session.commit()",
        want=f"{T18PG}.py::test_the_business_commit_is_one_transaction_and_one_database_commit",
        wants=(
            f"{T18PG}.py::test_plain_single_html_save_advances_the_business_revision_exactly_once",
        ),
        why="在唯一提交出口之前偷偷提交一次 ⇒ 一次业务保存变成两次数据库提交，"
            "四张表的 xmin 不再全等。xmin 是 PostgreSQL 自己记的事实，不依赖 "
            "`_TransactionWitness`，所以「见证逻辑被改坏」也躲不过这条。锚点用相对定位："
            "`witness.stamp(..., \"outbox\")` 在两条 lane 各出现一次",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task18_html_save_unified_revision.py",
            "backend/tests/workpaper_sync/test_task18_html_save_unified_revision_pg.py",
            "backend/tests/workpaper_sync/test_task16_durable_outbox_wiring.py",
            "backend/tests/test_workpaper_save_orchestrator.py",
            "backend/tests/test_wp_html_save.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider", "-p", "no:randomly",
        ],
        # 冻结基线来源：Task 18 收口实测（仓库根执行）
        #   test_task18_html_save_unified_revision.py       16 passed
        #   test_task18_html_save_unified_revision_pg.py    10 passed
        #   test_task16_durable_outbox_wiring.py            26 passed
        #   test_workpaper_save_orchestrator.py             13 passed
        #   test_wp_html_save.py                            17 passed
        baseline_backend_passed=82,
    ))
