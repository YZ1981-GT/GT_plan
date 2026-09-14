# -*- coding: utf-8 -*-
"""Task 16 变异检验：耐久 outbox facade / 提交边界 / 可重放副作用 / payload 保真的
守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 16
Requirements: 2.12, 13.1, 13.2, 13.3, 13.4, 13.9
Properties: P52（outbox 仅 commit 后发布）/ P53（replay 保留完整 payload）/
            P54（after-save 失败可重试）

═══ 变异改的是**生产代码**，不是守卫 ═══

落点六处：

* `workpaper_sync/outbox.py` —— 把 enqueue 的 flush 改成 commit、关掉 project_id
  fail-closed、让待发布句柄不登记、去掉"已 published 不重发"、把"行不存在"当失败、
  不清待发布清单、把失败当成功、退化 handler 幂等键、让 IntegrityError 变成"抢到了"、
  自己造一份重放结果（不再委托旧 service）、往重放路径注入 version 赋值、清空/越界扩张
  fan-out 闸门范围、让闸门只认枚举不认字符串、把归还派发权的 DELETE 改成 SELECT
* `import_event_outbox_service.py` —— 发布失败后把行标成 published（失败不再耐久）、
  关掉 DLQ 升级条件、给 replay_pending 注入第二个内联派发口、把派发挪到闸门之前、
  派发失败不归还派发权、去重不再计数
* `event_bus.py` —— 删掉 Stream 的 payload 载体字段、序列化时排除 extra、replay 强制
  走旧扁平字段、丢弃计数不再自增、丢弃分支不再 ACK
* `workpaper_save_orchestrator.py` —— 注入事务内 publish（幽灵事件）、注入把副作用
  降级成 warning 的 except
* `wp_html_save.py` / `wp_editor_router.py` / `custom_query_writeback.py` —— 恢复跨版本
  域的 expected_version、删掉发布接线、把发布挪到 commit 之前
* `custom_query/snapshot_writer.py` —— 让 after_save 调用消失（第 5 个调用方判据）、
  让耐久失败分支不再 re-raise
* `wp_onlyoffice_router.py` —— 删掉 callback 的发布接线、把豁免分支的 ERROR 降成
  warning、去掉污染事务的回滚

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 本任务实测到的判据设计教训（已固化进守卫）═══

1. **"walk 到"与"直接语句层"必须分清**：OO callback 的豁免 handler 里既有顶层
   `logger.error(...)`，也有嵌套 `try: await db.rollback() except: logger.error(...)`。
   最初的守卫用 `ast.walk` 收集调用名 ⇒ 把顶层那句改成 `logger.warning` 时被嵌套那句
   顶掉，判据无法被单点变异伪造（M27 首轮设计时发现）。故拆成 `_direct_handler_calls`
   与 `_walked_handler_calls` 两个判据。
2. **否定式承诺只能靠注入falsify**：`after_save` 里"没有 publish 调用""没有 except
   分支""重放路径不写 version"这三条都是"不存在某结构"，短路式变异改不动它们 ——
   M17 / M18 / M23 都是 `insert` 型反例注入。
3. **提交顺序判据必须落在行号次序上**：只 grep `publish_pending` 是否出现，把它挪到
   `commit` 之前照样绿。M20 就是往 commit 之前插一次发布来falsify次序判据。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task16_durable_outbox_guards.py --list
    python backend/scripts/diagnose/mutate_task16_durable_outbox_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task16_durable_outbox_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task16-durable-outbox/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

FACADE = "backend/app/services/workpaper_sync/outbox.py"
LEGACY = "backend/app/services/import_event_outbox_service.py"
BUS = "backend/app/services/event_bus.py"
ORCH = "backend/app/services/workpaper_save_orchestrator.py"
HTML = "backend/app/routers/wp_html_save.py"
UNIVER = "backend/app/routers/wp_editor_router.py"
OO = "backend/app/routers/wp_onlyoffice_router.py"
CQ_WB = "backend/app/routers/custom_query_writeback.py"
SNAPSHOT = "backend/app/services/custom_query/snapshot_writer.py"

#: 覆盖面分母：Task 16 新建的两个守卫文件。
GUARD_FILES = {
    "test_task16_durable_outbox_pg.py":
        "Task 16 新建：真实 PG 的 P52 提交边界/回滚零事件/恰一事件、P54 失败耐久与"
        "重放、DLQ 升级、handler 幂等唯一索引、缺 project_id fail closed",
    "test_task16_durable_outbox_wiring.py":
        "Task 16 新建：AST 接线判据（after_save 零 publish/零 except、5 个发布点的"
        "commit→publish 次序、facade 委托而非复制、重放路径零 version 赋值）与"
        "P53 写入侧真实执行",
    "test_wp_html_save.py":
        "既有 characterization，被 Task 16 加固：调用点的 `except Exception → "
        "logger.warning` 移除后，替身补齐 file_version/prefill_stale 并断言这两项真被"
        "写过，使「后处理整段被跳过仍返回 200」不再能满足该测试",
}

PG = "test_task16_durable_outbox_pg"
W = "test_task16_durable_outbox_wiring"

MUTATIONS: list[Mutation] = [
    # ══ 一、Property 52：enqueue 必须留在调用方事务里 ═════════════════════
    Mutation(
        id="M01", side="be", path=FACADE, kind="replace",
        anchor="        await db.flush()",
        new="        await db.commit()",
        want=f"{W}.py::test_enqueue_only_flushes_and_never_commits",
        wants=(
            f"{PG}.py::test_rollback_leaves_no_event_and_no_durable_row",
            f"{PG}.py::test_enqueue_happens_inside_the_caller_transaction",
        ),
        why="enqueue 自己提交 ⇒ 调用方回滚后耐久行仍在、审计日志与版本递增也一起提交，"
            "Property 52「事务 rollback 时无事件」直接失效",
    ),
    Mutation(
        id="M02", side="be", path=FACADE, kind="replace",
        anchor="        if project_id is None:",
        new="        if False:",
        want=f"{PG}.py::test_missing_project_id_fails_closed",
        why="关掉 project_id fail-closed ⇒ 退回旧行为（EventPayload 校验异常被吞成 "
            "warning，表现为「保存成功但下游联动永久静默」）；现在会变成模糊的 "
            "IntegrityError 而不是可定位的 DurableOutboxError",
    ),
    Mutation(
        id="M03", side="be", path=FACADE, kind="replace",
        anchor="        bucket.append(publication)",
        new="        pass",
        want=f"{PG}.py::test_enqueue_happens_inside_the_caller_transaction",
        wants=(f"{PG}.py::test_commit_then_publish_emits_exactly_one_complete_event",),
        why="待发布句柄不登记 ⇒ 调用方 commit 后 publish_pending 找不到任何待发布项，"
            "事件只能等 30s 一轮的 worker 补偿，下游刷新被静默延迟",
    ),
    Mutation(
        id="M04", side="be", path=FACADE, kind="replace",
        anchor="                if row.status == OutboxStatus.published:",
        new="                if False:",
        want=f"{PG}.py::test_republish_and_worker_replay_do_not_duplicate_the_event",
        why="去掉「已 published 不重发」⇒ 重复调用 publish_pending 会把同一事件再派发"
            "一次，Property 52「恰有一个事件、重放不重复副作用」失效",
    ),
    Mutation(
        id="M05", side="be", path=FACADE, kind="replace",
        anchor="                if row is None:",
        new="                if False:",
        want=f"{PG}.py::test_rollback_leaves_no_event_and_no_durable_row",
        why="把「入队事务已回滚（行不存在）」当成普通失败 ⇒ 报告里分不清 rolled_back "
            "与 failed，回滚场景会被当作待重试项反复处理",
    ),
    Mutation(
        id="M06", side="be", path=FACADE, kind="replace",
        anchor="        DurableEventOutboxService.forget_all(db)",
        new="        pass",
        want=f"{PG}.py::test_commit_then_publish_emits_exactly_one_complete_event",
        why="发布后不清待发布清单 ⇒ 同一 session 内下一次 publish_pending 会重复处理"
            "旧句柄，长连接下清单无界增长",
    ),

    # ══ 二、Property 54：失败必须耐久且可重放 ════════════════════════════
    Mutation(
        id="M07", side="be", path=FACADE, kind="replace",
        anchor="                if ok:",
        new="                if True:",
        want=f"{PG}.py::test_publish_failure_is_durable_and_replayable",
        why="把发布失败当成功计数 ⇒ 调用方与 /metrics 都看不到失败，Property 54 的"
            "「不静默丢失」判据失效",
    ),
    Mutation(
        id="M08", side="be", path=LEGACY, kind="replace",
        anchor="            item.status = OutboxStatus.failed",
        new="            item.status = OutboxStatus.published",
        want=f"{PG}.py::test_publish_failure_is_durable_and_replayable",
        why="发布失败后把行标成 published ⇒ 行再也不会被 replay_pending 选出来，"
            "事件永久丢失（正是 Requirement 13.4 禁止的形态）",
    ),
    Mutation(
        id="M09", side="be", path=LEGACY, kind="replace",
        anchor="                    and int(item.attempt_count or 0) >= max_attempts",
        new="                    and False",
        want=f"{PG}.py::test_exhausted_retries_escalate_to_dlq",
        why="关掉 DLQ 升级条件 ⇒ 重试耗尽的事件只留 failed 行，运维看不到死信、"
            "无法手工重投（Requirement 13.4 的 DLQ 分支）",
    ),

    # ══ 三、Requirement 13.3：handler 幂等 ══════════════════════════════
    Mutation(
        id="M10", side="be", path=FACADE, kind="replace",
        anchor="        key = DurableEventOutboxService.handler_key(handler_name, handler_version)",
        scope="        row = ImportEventConsumption(",
        offset=-1,
        new="        key = handler_name",
        want=f"{PG}.py::test_consumption_is_idempotent_per_event_and_handler_version",
        why="幂等键丢掉 handler 版本 ⇒ handler 语义升级后无法按新语义重跑一次"
            "（Requirement 13.3 的 handler version 半边失效）。锚点用 scope 相对定位："
            "`key = ...handler_key(...)` 在 claim / release 两处各出现一次",
    ),
    Mutation(
        id="M11", side="be", path=FACADE, kind="replace",
        anchor="            return False",
        scope="        except IntegrityError:",
        offset=6,
        new="            return True",
        want=f"{PG}.py::test_consumption_is_idempotent_per_event_and_handler_version",
        why="唯一索引冲突后仍返回「抢到了」⇒ 重复投递会重复执行副作用，幂等闸门形同"
            "虚设。锚点用 scope 相对定位：`return False` 在本文件出现两次",
    ),

    # ══ 四、Property 53：Stream payload 保真（修点在写入侧）═══════════════
    Mutation(
        id="M12", side="be", path=BUS, kind="delete",
        anchor="                _STREAM_PAYLOAD_FIELD: serialize_payload_for_stream(payload),",
        want=f"{W}.py::test_persist_to_stream_writes_the_whole_payload",
        wants=(
            f"{W}.py::test_stream_payload_field_is_json_and_self_describing",
            f"{W}.py::test_replay_restores_the_whole_payload_and_counts_dropped_entries",
        ),
        why="删掉 Stream 的 payload 载体字段 ⇒ 退回原缺陷：extra（wp_id/revision/"
            "operation_id/source/adapter_id/artifact_sha256）与 batch_id 在**写入这一步**"
            "就蒸发，replay 侧再怎么读都恢复不出来",
    ),
    Mutation(
        id="M13", side="be", path=BUS, kind="replace",
        anchor="    return payload.model_dump_json()",
        new='    return payload.model_dump_json(exclude={"extra"})',
        want=f"{W}.py::test_persist_to_stream_writes_the_whole_payload",
        wants=(
            f"{W}.py::test_stream_payload_field_is_json_and_self_describing",
            f"{PG}.py::test_stream_entry_preserves_every_payload_field",
        ),
        why="序列化时排除 extra ⇒ 字段还在、内容空了。这条专门检验判据是「逐项相等」"
            "而不是「字段存在」（后者会被空 payload 满足）",
    ),
    Mutation(
        id="M14", side="be", path=BUS, kind="replace",
        anchor="    raw = data.get(_STREAM_PAYLOAD_FIELD)",
        new="    raw = None",
        want=f"{W}.py::test_persist_to_stream_writes_the_whole_payload",
        wants=(
            f"{W}.py::test_replay_restores_the_whole_payload_and_counts_dropped_entries",
            f"{PG}.py::test_stream_entry_preserves_every_payload_field",
        ),
        why="replay 强制走旧扁平字段降级路径 ⇒ 即使写入侧带了完整 payload 也读不出来；"
            "检验「写入 + 读出」两侧各自都有判据，不是只测一半",
    ),
    Mutation(
        id="M15", side="be", path=BUS, kind="replace",
        anchor='                        report["dropped_unparseable_count"] += 1',
        new="                        pass",
        want=f"{W}.py::test_replay_restores_the_whole_payload_and_counts_dropped_entries",
        why="丢弃计数不再自增 ⇒ 「事件被 ACK 丢掉」这件事在日志与 /metrics 里再次"
            "不可见（Requirement 13.9 的告警可见性）",
    ),
    Mutation(
        id="M16", side="be", path=BUS, kind="delete",
        anchor="                        await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)",
        scope='                        report["dropped_unparseable_count"] += 1',
        offset=11,
        new="",
        want=f"{W}.py::test_replay_restores_the_whole_payload_and_counts_dropped_entries",
        why="丢弃分支不再 ACK ⇒ consumer group 队头被这条永久阻塞，后续事件全都读不到。"
            "锚点用 scope 相对定位：xack 在本函数出现两次（成功分支/丢弃分支）",
    ),

    # ══ 五、after_save 的否定式承诺（注入反例）═══════════════════════════
    Mutation(
        id="M17", side="be", path=ORCH, kind="insert",
        anchor="        from app.services.workpaper_sync.outbox import DurableEventOutboxService",
        new="        from app.models.audit_platform_schemas import EventPayload as _EP\n"
            "        from app.services.event_bus import event_bus as _bus\n"
            "        await _bus.publish_immediate(_EP("
            "event_type=EventType.WORKPAPER_SAVED, project_id=wp.project_id))",
        want=f"{W}.py::test_after_save_enqueues_instead_of_publishing_inside_the_transaction",
        wants=(f"{PG}.py::test_enqueue_happens_inside_the_caller_transaction",),
        why="往事务内注入一次 publish ⇒ 恢复幽灵事件（回滚后事件已发出）。"
            "「函数体内没有 publish 调用」是否定式承诺，只能靠注入反例来证明判据可"
            "falsify —— 短路式变异改不动「不存在」",
    ),
    Mutation(
        id="M18", side="be", path=ORCH, kind="insert",
        anchor="        db.add(log)",
        new="        try:\n"
            "            pass\n"
            "        except Exception as exc:\n"
            '            logger.warning("re-introduced best-effort degradation: %s", exc)',
        want=f"{W}.py::test_after_save_no_longer_swallows_its_own_side_effects",
        why="注入一个把副作用降级成 warning 的 except ⇒ 恢复 Requirement 13.4 明令"
            "禁止的形态。同 M17：「零 except 分支」只能靠注入falsify",
    ),
    Mutation(
        # 🔴 Task 18 起 `trigger="html_save",` 在本文件出现两次（`HtmlOnlyCommitPlan`
        #    与 `after_save` 各一处），裸锚点退化成 ANCHOR-MISS ⇒ 改用相对定位。
        id="M19", side="be", path=HTML, kind="insert",
        anchor='        trigger="html_save",',
        scope="    await save_orchestrator.after_save(",
        offset=2,
        new="        expected_version=body.data_version,",
        want=f"{W}.py::test_html_save_no_longer_crosses_the_version_domains",
        why="把跨版本域的 expected_version 加回去 ⇒ `body.data_version`"
            "（parsed_data['_version'] 域）又被拿去和 `wp.file_version` 比，"
            "第二次带 data_version 的保存起必然假冲突；这正是本任务修掉的真实缺陷",
    ),

    # ══ 六、提交顺序与发布接线 ═══════════════════════════════════════════
    Mutation(
        id="M20", side="be", path=CQ_WB, kind="insert",
        anchor='        written.append(result if isinstance(result, dict) else {"result": "ok"})',
        new="        from app.services.workpaper_sync.outbox import "
            "DurableEventOutboxService as _Early\n"
            "        await _Early.publish_pending(db)",
        want=f"{W}.py::test_publish_pending_runs_after_the_content_commit",
        why="在 commit **之前**插一次发布 ⇒ 回滚时事件已经出去了。这条检验次序判据是"
            "「行号次序」而不是「文件里出现过 publish_pending」—— 后者挪不挪都绿",
    ),
    Mutation(
        id="M21", side="be", path=UNIVER, kind="replace",
        anchor="    await DurableEventOutboxService.publish_pending(db)",
        new="    pass",
        want=f"{W}.py::test_publish_pending_runs_after_the_content_commit",
        why="删掉 univer 保存路径的发布接线 ⇒ 耐久行只能等 worker 补偿，"
            "前端保存后 30s 内看不到联动刷新（接线缺失类缺陷）",
    ),
    Mutation(
        id="M22", side="be", path=OO, kind="replace",
        anchor="            await DurableEventOutboxService.publish_pending(db)",
        new="            pass",
        want=f"{W}.py::test_publish_pending_runs_after_the_content_commit",
        why="删掉 OO callback 的发布接线 ⇒ OnlyOffice 回写后的下游联动只能等补偿",
    ),

    # ══ 七、facade 复用而非复制；重放路径零版本移动 ══════════════════════
    Mutation(
        id="M23", side="be", path=FACADE, kind="replace",
        anchor="        return await ImportEventOutboxService.replay_pending(db, **kwargs)",
        new='        return {"read_count": 0, "published_count": 0, "failed_count": 0}',
        want=f"{W}.py::test_facade_delegates_replay_and_dlq_to_the_legacy_service",
        wants=(
            f"{PG}.py::test_publish_failure_is_durable_and_replayable",
            f"{PG}.py::test_exhausted_retries_escalate_to_dlq",
        ),
        why="facade 自己造一份重放结果 ⇒ 违反 design「不新建第二套、复用现有 outbox/DLQ "
            "能力」，DLQ 升级与 FOR UPDATE SKIP LOCKED 的并发安全全部失去",
    ),
    Mutation(
        id="M24", side="be", path=FACADE, kind="insert",
        anchor="                    report.published += 1",
        new="                    row.file_version = 1",
        want=f"{W}.py::test_the_replayable_path_writes_no_version_field",
        why="往重放路径注入 version 赋值 ⇒ Requirement 2.12「handler 重试不得再次递增 "
            "content revision」失效。同 M17/M18 是注入型：「整模块零 version 赋值」"
            "是否定式承诺",
    ),

    # ══ 八、调用方集合与耐久失败的 re-raise ═════════════════════════════
    Mutation(
        id="M25", side="be", path=SNAPSHOT, kind="replace",
        anchor="                await save_orchestrator.after_save(",
        new="                await _absent_after_save(",
        want=f"{W}.py::test_after_save_callers_are_exactly_the_adjudicated_four",
        why="让 custom_query 回写路径不再经统一后处理 ⇒ 该路径的耐久事件整条消失，"
            "而两个 router 的 publish_pending 变成空转（接线断裂但看起来一切正常）",
    ),
    Mutation(
        id="M26", side="be", path=SNAPSHOT, kind="replace",
        anchor="            raise",
        new="            pass",
        want=f"{W}.py::test_after_save_call_sites_do_not_swallow_the_durability_failure",
        why="耐久入队失败不再 re-raise ⇒ 回写落库但下游联动永久断开，只在返回体里留"
            "一条 warning（Requirement 13.4 禁止的 best-effort 形态）",
    ),

    # ══ 九、OO callback 豁免的代价必须被限定 ════════════════════════════
    Mutation(
        id="M27", side="be", path=OO, kind="replace",
        anchor="            logger.error(",
        scope='                "orchestrator.after_save failed in onlyoffice_callback wp=%s "',
        offset=-1,
        new="            logger.warning(",
        want=f"{W}.py::test_after_save_call_sites_do_not_swallow_the_durability_failure",
        why="把 ack-OO 豁免分支的顶层诊断从 ERROR 降回 warning ⇒ 「callback 后处理失败」"
            "在日志里看不见。锚点用 scope 相对定位：`logger.error(` 在本文件出现 4 次，"
            "且判据必须只看 handler **顶层语句**（嵌套 rollback 分支里还有一处 "
            "logger.error 会把 walk 式判据顶掉）",
    ),
    Mutation(
        id="M28", side="be", path=OO, kind="replace",
        anchor="                await db.rollback()",
        new="                pass",
        want=f"{W}.py::test_after_save_call_sites_do_not_swallow_the_durability_failure",
        why="豁免分支不再回滚被污染的事务 ⇒ 后续代码在一个已失效的 session 上继续跑，"
            "错误被放大成难以归因的连锁失败",
    ),

    # ══ 十、Requirement 13.3：fan-out 闸门（重复投递不重复副作用）════════════
    Mutation(
        id="M29", side="be", path=LEGACY, kind="insert",
        anchor="                item.attempt_count = int(item.attempt_count or 0) + 1",
        new="                await event_bus.publish_immediate(EventPayload(\n"
            "                    event_type=EventType(item.event_type),\n"
            "                    project_id=item.project_id,\n"
            "                    year=item.year,\n"
            "                    extra=dict(item.payload or {}),\n"
            "                ))",
        want=f"{W}.py::test_deliver_is_the_only_fanout_site",
        wants=(f"{PG}.py::test_replayed_event_does_not_fan_out_its_side_effects_twice",),
        why="给 replay_pending 加回一处**内联**派发 ⇒ 闸门只管得住 _deliver 那条路径，"
            "worker 重放仍会把整片 handler 再跑一遍。「只有一个派发口」是否定式承诺，"
            "只能靠注入第二个派发口来 falsify",
    ),
    Mutation(
        id="M30", side="be", path=LEGACY, kind="insert",
        anchor="        gated = DurableEventOutboxService.is_fanout_gated(item.event_type)",
        new="        await event_bus.publish_immediate(payload)",
        want=f"{W}.py::test_fanout_gate_precedes_the_dispatch_and_is_released_on_failure",
        wants=(f"{PG}.py::test_replayed_event_does_not_fan_out_its_side_effects_twice",),
        why="把派发挪到闸门**之前** ⇒ 判重发生时副作用已经做完了，闸门只剩装饰作用。"
            "这条检验次序判据落在行号次序上，而不是「文件里出现过 begin_fanout」",
    ),
    Mutation(
        id="M31", side="be", path=LEGACY, kind="replace",
        anchor="                await DurableEventOutboxService.abort_fanout(db, event_id=item.id)",
        new="                pass",
        want=f"{PG}.py::test_fanout_failure_returns_the_ticket_so_replay_can_deliver",
        wants=(f"{W}.py::test_fanout_gate_precedes_the_dispatch_and_is_released_on_failure",),
        why="派发失败不归还派发权 ⇒ 重放被自己的闸门挡下，事件永久静默丢失。这正是"
            "Requirement 13.4 禁止的形态，也是「闸门」与「Property 54 可重放」互相打架"
            "的唯一危险点",
    ),
    Mutation(
        id="M32", side="be", path=FACADE, kind="replace",
        anchor="    {EventType.WORKPAPER_SAVED, EventType.WORKPAPER_CONTENT_UPDATED}",
        new="    set()",
        want=f"{W}.py::test_the_gate_covers_the_two_workpaper_sync_event_types_only",
        wants=(f"{PG}.py::test_replayed_event_does_not_fan_out_its_side_effects_twice",),
        why="闸门范围清空 ⇒ 退回原行为（重放重复刷新）。代码结构、调用点、日志全都还在，"
            "只有行为变了 —— 用来证明判据不是在测「代码里有没有闸门」",
    ),
    Mutation(
        id="M33", side="be", path=FACADE, kind="replace",
        anchor="    {EventType.WORKPAPER_SAVED, EventType.WORKPAPER_CONTENT_UPDATED}",
        new="    {EventType.WORKPAPER_SAVED, EventType.WORKPAPER_CONTENT_UPDATED, "
            "EventType.LEDGER_DATASET_ACTIVATED}",
        want=f"{PG}.py::test_import_domain_replay_semantics_are_untouched",
        wants=(f"{W}.py::test_the_gate_covers_the_two_workpaper_sync_event_types_only",),
        why="闸门**越界**扩到导入域 ⇒ 改掉了 ledger-import spec 拥有的重放语义（那边的"
            "handler 依赖「重放会重新派发」）。范围判据必须双向可 falsify：只测「底稿域"
            "被管住」的话，顺手扩张不会被任何守卫发现",
    ),
    Mutation(
        id="M34", side="be", path=FACADE, kind="replace",
        anchor="        return any(item.value == event_type for item in GATED_FANOUT_EVENT_TYPES)",
        new="        return False",
        want=f"{W}.py::test_the_gate_covers_the_two_workpaper_sync_event_types_only",
        wants=(f"{PG}.py::test_replayed_event_does_not_fan_out_its_side_effects_twice",),
        why="只认枚举、不认字符串 ⇒ `import_event_outbox.event_type` 是 VARCHAR 列，派发口"
            "拿到的永远是 str，闸门在生产里恒为 False。这是**最隐蔽**的一类失效：结构、"
            "单测（若只传枚举）与日志全都正常",
    ),
    Mutation(
        id="M35", side="be", path=FACADE, kind="replace",
        anchor="                sa.delete(ImportEventConsumption).where(",
        new="                sa.select(ImportEventConsumption).where(",
        want=f"{PG}.py::test_fanout_failure_returns_the_ticket_so_replay_can_deliver",
        wants=(f"{W}.py::test_release_consumption_actually_deletes_the_row",),
        why="归还派发权不再真的删行（改成一次 SELECT，rowcount 仍返回真值）⇒ 行为与"
            "「不归还」完全一样。检验判据看的是**DELETE 这个动作**，不是「函数被调用过」",
    ),
    Mutation(
        id="M36", side="be", path=LEGACY, kind="replace",
        anchor='                    report["deduplicated_fanout_count"] += 1',
        new="                    pass",
        want=f"{PG}.py::test_replayed_event_does_not_fan_out_its_side_effects_twice",
        why="去重不再计数 ⇒ 运维看到 published_count 涨了却没有任何下游动作，且分不清"
            "「真派发」与「被闸门跳过」（Requirement 13.9 的可见性）",
    ),
    Mutation(
        id="M37", side="be", path=ORCH, kind="insert",
        anchor="        await db.flush()",
        new="        wp.file_version += 1",
        want=f"{W}.py::test_the_version_write_is_confined_to_the_pre_commit_half",
        wants=(
            f"{W}.py::test_the_file_lifecycle_version_has_three_named_owners",
            "test_workpaper_save_orchestrator.py::TestAfterSaveWritesNoVersionField"
            "::test_after_save_writes_no_version_field",
        ),
        why="往共享副作用 handler 注入一次 version 递增。Task 16 时该守卫的期望值是"
            "「恰一处且在 enqueue 之前」，Task 18 把生产所有者搬到三条真正写文件的路径后"
            "降到 0，本变异随之从「注入第二处」变成「注入唯一一处」——两种期望值下它都是"
            "有效 falsifier，因为「零 version 写」是否定式承诺，只能靠注入反例证明",
    ),
    # ══ 八、普通 HTML save 调用点：结构不变但行为消失 / swallow 复活 ═══════════
    Mutation(
        id="M38", side="be", path=HTML, kind="replace",
        anchor="    await save_orchestrator.after_save(",
        new="    if False: await save_orchestrator.after_save(",
        want="test_wp_html_save.py::test_save_200_success",
        why="让后处理整段不执行，但**语法结构原样保留**（`if False:` 后跟隐式续行的多行"
            "调用是合法 Python，AST 里 after_save 调用节点仍在）。原来这个调用点被 "
            "`except Exception: logger.warning` 包着，替身缺 file_version 抛的 "
            "AttributeError 被吞掉，于是 test_save_200_success 实际断言的是「后处理整段"
            "被跳过后接口仍返回 200」—— 只看状态码的判据在这条变异下照样绿。故该测试"
            "补了 file_version/prefill_stale 两条可观察写入断言，本变异就是它的 falsifier",
    ),
    Mutation(
        # 🔴 Task 18 换锚点：`wp_html_save` 迁入统一 revision 域后自己**不再有**
        #    `await db.commit()`（唯一提交出口在 ContentMutationService 里），原锚点
        #    退化成 ANCHOR-MISS。改锚到 orchestrator 的局部 import 行 —— 它与被注入的
        #    调用同属一处、且在本文件唯一。
        id="M39", side="be", path=HTML, kind="insert",
        anchor="    from app.services.workpaper_save_orchestrator import orchestrator as save_orchestrator",
        new="    try:\n"
            "        await save_orchestrator.after_save(\n"
            "            db, working_paper, current_user, trigger=\"html_save\"\n"
            "        )\n"
            "    except Exception as _mut_exc:\n"
            '        logger.warning("swallowed: %s", _mut_exc)',
        want=f"{W}.py::test_after_save_call_sites_do_not_swallow_the_durability_failure"
             "[app/routers/wp_html_save.py]",
        why="把 Requirement 13.4 明令禁止的 best-effort 形态注入回 html_save 调用点。"
            "「该模块没有 swallowing try」是否定式承诺，短路式变异改不动「不存在」，"
            "只能注入反例。这条同时补上原变异集的一处空白：no-swallow 判据的 "
            "snapshot_writer / OO callback 两个参数化实例有变异（M26/M27/M28），"
            "wp_html_save 那个实例此前无人 falsify",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task16_durable_outbox_pg.py",
            "backend/tests/workpaper_sync/test_task16_durable_outbox_wiring.py",
            "backend/tests/test_wp_html_save.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider", "-p", "no:randomly",
        ],
        # 冻结基线来源：Task 18 收口后重测（仓库根执行；Task 16 时是 55）
        #   test_task16_durable_outbox_pg.py       14 passed
        #     （10 条原有 + 场景 J/K/L 三条 fan-out 闸门行为判据 + 采集完整性 1 条）
        #   test_task16_durable_outbox_wiring.py   26 passed
        #     （25 条原有 + Task 18 新增 `file_version` 三所有者双向判据 1 条）
        #   test_wp_html_save.py                   17 passed
        #     （既有 characterization + Task 18 新增 CAS 冲突 → 409 一条；M38/M39 的
        #      RED 落在这里，故必须进 pytest 范围，否则两条变异会因「预期失败项不在
        #      运行集合内」被判成 GREEN）
        baseline_backend_passed=57,
    ))
