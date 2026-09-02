# -*- coding: utf-8 -*-
"""Task 19 变异检验：上传 / WOPI / custom writer 迁入统一 revision 域的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
Requirements: 2.2, 2.11, 9.11, 12.6, 12.7
Properties: **P50**（custom 保持 xlsx 权威且进入统一 representation 协议）/
**P61**（所有 writer 进入唯一 revision 域）

═══ 变异改的是**生产代码**，不是守卫 ═══

落点四处：

* `app/routers/custom_workpaper_cells.py` —— 把 `file_version += 1` 与裸 `db.commit()`
  写回去、把权威载荷换成投影（`grid`）、把 authority model 换成 projection、把窄捕获
  放宽成 `except Exception`
* `app/services/wopi_service.py` —— 写回 `file_version += 1`、把审计日志挪到唯一提交
  出口之后、把快照名换回 `file_version`、拆掉统一入口接线
* `app/services/wp_download_service.py` —— 写回 `file_version += 1`、把冲突早检查换回
  `file_version`、拆掉统一入口接线
* `app/services/workpaper_sync/writer_migration.py` —— 放行 `projection_contract`、
  把 numeric revision 判据挪到查库之后、去掉 entry_id 路径归一、让两条语义拒绝落到
  状态拒绝之后、去掉磁盘 digest 校验、给装配层加一个 `contract` 形参、让 restore 不
  再挂父版本
* `app/models/workpaper_models.py` —— 删掉 V151 的 `content_revision` 列声明（证明
  「ORM 必须声明」这条不是注释里的说法）

═══ 判定四态 ═══

打红=RED（守卫有效）；不红=GREEN（守卫缺陷**或**无效变异，必须逐条归因）；红了但不是
预期项=WRONG-TEST；锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。

═══ 本任务的判据设计教训 ═══

1. **否定式承诺只能靠注入 falsify**。「不再写 `file_version`」「装配层没有 contract
   入口」「restore 不自己动 pointer」都是「不存在某结构」，短路式变异改不动它们 ——
   M01/M02/M05/M06/M09/M14 全是 insert 型反例注入。
2. **每条拒绝一个 error_code**。Task 18 实测过：两条拒绝共用一个码时，短路第一个 `if`
   会被第二个接住并抛同样的码 ⇒ 第一条判据变成不可达分支、变异判 GREEN。M10~M12 逐条
   验证 rollback 的语义/状态拒绝互不遮蔽。
3. **改判据值必须与生产所有者同批搬**。三条已迁移 writer 从
   `test_workpaper_writer_inventory.py` 的 `_LEGACY_VERSION_WRITERS` 期望集合里搬走是
   合法的，**因为它们真的不再写了** —— M01/M05/M09 就是这个"合法"的 falsifier：只把
   期望值改小而不搬生产，这三条会全部 GREEN（没有东西可注入即红）。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task19_writer_migration_guards.py --list
    python backend/scripts/diagnose/mutate_task19_writer_migration_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task19_writer_migration_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task19-writer-migration/mutation_report.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CELLS = "backend/app/routers/custom_workpaper_cells.py"
WOPI = "backend/app/services/wopi_service.py"
UPLOAD = "backend/app/services/wp_download_service.py"
WM = "backend/app/services/workpaper_sync/writer_migration.py"
WP_MODEL = "backend/app/models/workpaper_models.py"
CM = "backend/app/services/workpaper_sync/content_mutation.py"
MIGRATION_SVC = "backend/app/services/wp_migration_service.py"
TRAIL = "backend/app/services/version_trail_service.py"
STORAGE = "backend/app/services/wp_storage_service.py"
F2_PLAN = "backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py"
F2_SUMMARY = "backend/app/routers/wp_render_strategies/_f2_stocktake_summary_sync.py"

T19 = "test_task19_writer_migration"
INV = "test_workpaper_writer_inventory"
CELLS_UT = "test_custom_workpaper_cells"
WOPI_UT = "test_wopi_working_paper_qc_review"
T15 = "test_task15_content_mutation"
T18 = "test_task18_html_save_unified_revision"

#: 覆盖面分母：Task 19 新建 / 改造的守卫文件。
GUARD_FILES = {
    "test_task19_writer_migration.py":
        "Task 19 新建：逐 writer 的 AST 判据（零私有计数器 / 零裸 commit / 真接线 / "
        "custom 权威载荷是 xlsx 本体 / WOPI 审计日志早于唯一提交出口 / 快照名跟随真正在动的"
        "计数器 / 上传冲突检查比 content_revision）+ 装配层真实执行判据（entry_id 路径安全、"
        "projection_contract 被拒、marker 非空、authority payload 无自身身份、"
        "adapter build digest 非全零、装配层无 contract 入口）+ rollback 六条拒绝各自 "
        "error_code、resource key 判据早于查库、语义拒绝早于状态拒绝、磁盘 digest 校验、"
        "restore 形态、ORM 列声明、source 词表与 V152 双向锁死",
    "test_workpaper_writer_inventory.py":
        "Task 3 清册守卫，随 Task 19 同批搬动：`_MIGRATED_TO_UNIFIED_COMMIT` 加 WOPI/上传两行，"
        "`legacy_version_writers` 期望集合减去三条已迁移 writer",
    "test_custom_workpaper_cells.py":
        "既有 characterization，随 Task 19 加固：断言端点零 file_version 写 + 真接线 + "
        "回传 CAS 实际 revision",
    "test_wopi_working_paper_qc_review.py":
        "既有 characterization，随 Task 19 加固：非 OOXML 载荷必须被拒；版本单调契约搬到真库；"
        "保留 put_file 的接线结构判据",
    "test_task15_content_mutation.py":
        "Task 15 守卫，随 Task 19 同批搬动：source 词表判据改为按迁移号取最后一个声明 "
        "`ck_wpcv_source` 的迁移（V152 放宽了它）",
    "test_task18_html_save_unified_revision.py":
        "Task 18 守卫，作为增量二的**反证分母**：projection lane 新增了透传的 `source` 字段，"
        "其默认值必须仍是 `html`，否则每一次普通 HTML 保存都会被记成回滚（M29）",
}

MUTATIONS: list[Mutation] = [
    # ═══ 一、custom lane（Property 50 / Requirement 2.11）═══════════════════
    Mutation(
        id="M01", side="be", path=CELLS, kind="insert",
        anchor="    ctx.wp.updated_by = current_user.id",
        new="    ctx.wp.file_version = int(ctx.wp.file_version or 0) + 1",
        want=f"{T19}.py::test_migrated_writer_owns_no_private_version_counter[update_custom_cells]",
        wants=(
            f"{CELLS_UT}.py::TestEndpointWriteOrder::test_the_business_version_advances_through_the_unified_boundary",
        ),
        why="把私有计数器写回去。「不再推进 file_version」是否定式承诺，短路式变异改不动"
            "「不存在」，只能注入反例。它同时是清册期望值搬动的 falsifier：只把 "
            "`legacy_version_writers` 期望集合改小而不搬生产，本条会 GREEN",
    ),
    Mutation(
        id="M02", side="be", path=CELLS, kind="insert",
        anchor="    await writer.publish_committed_events(receipt)",
        new="    await db.commit()",
        want=f"{T19}.py::test_migrated_writer_owns_no_direct_commit[update_custom_cells]",
        why="加回一个裸 `db.commit()` ⇒「业务内容的唯一提交出口在 ContentMutationService」"
            "失效。第二次提交必然意味着一次业务写入落在两个事务里（Requirement 2.4 / 13.1）",
    ),
    Mutation(
        id="M03", side="be", path=CELLS, kind="replace",
        anchor="            payload=authoritative_bytes,",
        new="            payload=json.dumps(grid).encode(),",
        want=f"{T19}.py::test_the_custom_writer_submits_the_xlsx_body_not_a_json_projection",
        why="把权威载荷换成 JSON 投影 ⇒ 正是 Requirement 2.11 / Property 50 明令禁止的"
            "「custom 底稿被标准结构化 JSON projection writer 改写」。这条是本任务点名的"
            "那条 Property 的直接 falsifier",
    ),
    Mutation(
        id="M04", side="be", path=CELLS, kind="replace",
        anchor="    except RevisionConflictError as exc:",
        new="    except Exception as exc:",
        want=f"{T19}.py::test_the_custom_writer_translates_the_revision_conflict_narrowly",
        why="把窄捕获放宽成 `except Exception` ⇒「artifact 发布失败」「事务分裂」「步骤缺失」"
            "全被吞成一句 409「其他用户已修改」，用户看到的原因是错的，真故障也不再是 ERROR"
            "（Requirement 5.12 禁止宽泛 except 降级）",
    ),
    # ═══ 二、WOPI lane ═══════════════════════════════════════════════════════
    Mutation(
        id="M05", side="be", path=WOPI, kind="insert",
        anchor="        wp.prefill_stale = True",
        new="        wp.file_version += 1",
        want=f"{T19}.py::test_migrated_writer_owns_no_private_version_counter[WOPIHostService.put_file]",
        wants=(f"{INV}.py::test_legacy_version_writers_are_the_enumerated_ones",),
        why="把 WOPI 的私有计数器写回去。同 M01：否定式承诺只能靠注入 falsify，且它同时"
            "验证清册期望集合的搬动是「生产真的搬走了」而不是「只改了数字」",
    ),
    Mutation(
        id="M06", side="be", path=WOPI, kind="insert",
        anchor="        await _writer.publish_committed_events(_receipt)",
        new="        db.add(log)",
        want=f"{T19}.py::test_the_wopi_audit_log_is_written_before_the_only_commit_outlet",
        why="删掉审计留痕入库 ⇒ 判据的正面锚点消失。这条与 M07 成对：只断言「审计日志在"
            "commit 之前」而不断言「审计日志存在」时，把它整段删掉也满足次序断言",
    ),
    Mutation(
        id="M07", side="be", path=WOPI, kind="replace",
        anchor='        snapshot_name = f"{fp.stem}_r{pre_save_revision}{fp.suffix}"',
        new='        snapshot_name = f"{fp.stem}_v{wp.file_version}{fp.suffix}"',
        want=f"{T19}.py::test_the_wopi_snapshot_name_follows_the_counter_that_actually_moves",
        why="把快照名换回已冻结的 `file_version` ⇒ `{stem}_v1.xlsx` 被每次保存覆盖，"
            "`.versions` 备份看着在、实际只剩最后一份。这是「迁移引入的连带缺陷」类判据："
            "它不是 revision 域本身的问题，而是「换了计数器后谁还在读旧的」",
    ),
    Mutation(
        id="M08", side="be", path=WOPI, kind="replace",
        anchor="            _receipt = await _writer.commit_bytes(",
        new="            _receipt = await _mut_absent_commit(",
        want=f"{T19}.py::test_migrated_writer_routes_through_the_unified_entry[WOPIHostService.put_file]",
        wants=(
            f"{WOPI_UT}.py::TestWOPIHostService::test_put_file_version_contract_moved_to_real_postgres",
            f"{T19}.py::test_the_wopi_audit_log_is_written_before_the_only_commit_outlet",
        ),
        why="拆掉统一入口接线（结构保留、名字换掉）⇒ 内容根本不再进入统一 revision 域。"
            "M05 是否定式的（没有私有计数器），把整个提交删掉也满足，所以必须有这条正面"
            "接线判据配对",
    ),
    # ═══ 三、upload lane ═════════════════════════════════════════════════════
    Mutation(
        id="M09", side="be", path=UPLOAD, kind="insert",
        anchor="        wp.prefill_stale = True  # 标记需要重新解析",
        new="        wp.file_version += 1",
        want=f"{T19}.py::test_migrated_writer_owns_no_private_version_counter[WpUploadService.upload_file]",
        wants=(f"{INV}.py::test_legacy_version_writers_are_the_enumerated_ones",),
        why="同 M01/M05。这条 writer 原本与 WOPI、storage 快照、另一条 upload 路径**共用**"
            "同一个 `file_version` 计数器（清册原话），写回去就恢复了那个四方争抢的形态",
    ),
    Mutation(
        id="M10", side="be", path=UPLOAD, kind="replace",
        anchor='        server_content_revision = int(getattr(wp, "content_revision", 0) or 0)',
        new="        server_content_revision = int(wp.file_version or 0)",
        want=f"{T19}.py::test_the_upload_conflict_check_compares_the_business_revision",
        why="把冲突早检查的比对目标退回 `file_version` ⇒ 与真正推进的 `content_revision` "
            "是两个计数器，客户端拿到的 server_version 与下次要提交的 expected 不是同一个数"
            "（跨域比较必然造假冲突，Requirement 2.1）",
    ),
    # ═══ 四、装配层与 rollback 源定位 ════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=WM, kind="replace",
        anchor="        if model not in OPAQUE_AUTHORITY_MODELS:",
        new="        if False:",
        want=f"{T19}.py::test_projection_contract_cannot_use_the_opaque_assembly",
        why="放行 `projection_contract` 走 opaque 装配 ⇒ 标准结构化底稿绕过 "
            "materialize → roundtrip 等值 → 未管理区域比对三步（Property 65 的等值判据"
            "整体失效），且会用 typed null marker 冒充 per-entry contract",
    ),
    Mutation(
        id="M12", side="be", path=WM, kind="replace",
        anchor='    safe = "".join(char if char in _ENTRY_ID_SAFE else "_" for char in stem)',
        new="    safe = stem",
        want=f"{T19}.py::test_opaque_entry_id_is_a_safe_single_path_segment",
        why="去掉 entry_id 的路径片段归一 ⇒ `entry_id` 被 `representation_dir()` 原样当"
            "目录名用，含 `/` 或 `..` 的 wp_code 直接目录穿越（Requirement 9.6），含 `:` "
            "的在 Windows 上 NotADirectoryError（本任务实测 WinError 267）",
    ),
    Mutation(
        id="M13", side="be", path=WM, kind="replace",
        anchor="        resolved_version_id = self._coerce_version_id(version_id)",
        new="        resolved_version_id = version_id",
        want=f"{T19}.py::test_the_resource_key_check_runs_before_any_database_read",
        why="把 numeric revision 判据从 `locate()` 里摘掉 ⇒ 两个 wp 都可以有 revision=1，"
            "第一个匹配到的行就会被当成回滚源 = 跨 scope 数据泄露（Requirement 10.6 明令"
            "禁止 numeric revision 作 resource_id / route key）",
    ),
    Mutation(
        id="M14", side="be", path=WM, kind="replace",
        anchor="        if isinstance(value, bool) or isinstance(value, int):",
        new="        if False:",
        want=f"{T19}.py::test_numeric_revision_is_refused_as_a_rollback_resource_key[1]",
        wants=(
            f"{T19}.py::test_numeric_revision_is_refused_as_a_rollback_resource_key[0]",
            f"{T19}.py::test_numeric_revision_is_refused_as_a_rollback_resource_key[True]",
        ),
        why="短路 numeric 分支 ⇒ `1` 会掉到 `is_uuid_text('1')` 那条上，虽然仍抛同一个类型，"
            "但**诊断信息**从「numeric revision 不是 resource key」退化成「不是 UUID」。"
            "参数化到具体值正是为了让 numeric 与 non-uuid 两条路径各自可 falsify",
    ),
    Mutation(
        id="M15", side="be", path=WM, kind="replace",
        anchor="            raise RollbackSourceCandidateError(",
        new="            raise RollbackSourceNotPublishedError(",
        want=f"{T19}.py::test_every_rollback_refusal_has_its_own_error_code",
        wants=(f"{T19}.py::test_the_semantic_refusals_are_checked_before_the_state_refusal",),
        why="把 candidate（语义禁令）与 not-published（状态禁令）合成一个码 ⇒ 正是 Task 18 "
            "实测到的那类真实缺陷：合成后短路 candidate 分支会被状态分支接住并抛同样的码，"
            "第一条判据变成不可达分支",
    ),
    Mutation(
        id="M16", side="be", path=WM, kind="replace",
        anchor="            raise RollbackSourceIncomingError(",
        new="            raise RollbackSourceNotPublishedError(",
        want=f"{T19}.py::test_the_semantic_refusals_are_checked_before_the_state_refusal",
        wants=(f"{T19}.py::test_every_rollback_refusal_has_its_own_error_code",),
        why="同 M15，另一条语义禁令：incoming 永不 published、永不 resolver-visible，"
            "durable 只证明可恢复而不证明它曾被应用（Requirement 5.6 / Property 65）",
    ),
    Mutation(
        id="M17", side="be", path=WM, kind="replace",
        anchor="        if not is_digest(artifact.sha256) or actual != artifact.sha256:",
        new="        if False:",
        want=f"{T19}.py::test_the_rollback_source_digest_is_verified_against_the_disk",
        why="去掉磁盘 digest 校验 ⇒ DB 说的 sha256 与磁盘内容不符时照搬，把损坏/被替换的"
            "内容发布成新版本。内容寻址不可变承诺一破，历史读取就再也不可信",
    ),
    Mutation(
        id="M18", side="be", path=WM, kind="replace",
        anchor="            parent_version_id=located.version_id,",
        new="            parent_version_id=None,",
        want=f"{T19}.py::test_the_restore_lane_produces_a_new_version_from_the_located_source",
        why="让 restore 产生的新版本不挂在被回滚到的那个版本下 ⇒ forward-only 回滚链断掉，"
            "「回滚过头了还能回滚回去」的可审计轨迹丢失（Requirement 8.9）",
    ),
    Mutation(
        id="M19", side="be", path=WM, kind="insert",
        anchor="        reason: str = \"content_commit\",",
        new="        contract: object | None = None,",
        want=f"{T19}.py::test_the_assembly_layer_cannot_express_a_per_entry_contract",
        why="给装配层加一个 `contract` 形参 ⇒「custom 不得转 JSON 三方 projection」从"
            "「构造上不可表达」退化成「运行时才拒绝」。判据刻意钉在**形参**上，因为运行时"
            "那条（`_assert_authority_shape`）属 Task 15 域，这里要的是更强的形态封闭",
    ),
    Mutation(
        id="M20", side="be", path=WM, kind="replace",
        anchor='    return hashlib.sha256(adapter_id.encode("utf-8")).hexdigest()',
        new='    return "0" * 64',
        want=f"{T19}.py::test_the_adapter_build_digest_is_stable_and_never_all_zero",
        why="把 adapter build digest 换成全零 hash ⇒ 伪身份（在 char(64) 与 hex 正则层面都"
            "合法，Requirement 2.3 单独点名禁止）。opaque 路径没有真 adapter 不等于可以填零",
    ),
    Mutation(
        id="M21", side="be", path=WM, kind="replace",
        anchor='    return {slot: marker_slot_spec(slot) for slot in BundleSlot}',
        new='    return {slot: marker_slot_spec(slot) for slot in list(BundleSlot)[:1]}',
        want=f"{T19}.py::test_the_opaque_bundle_uses_registry_markers_and_never_an_empty_hash",
        why="只给一个 slot ⇒ slot omission。四个 slot 必须全出现是 Requirement 2.3 的原文，"
            "而 DB CHECK/trigger 层的拒绝在 service 层之后 —— 少一层判据就少一次早失败",
    ),
    # ═══ 五、ORM 列声明（本任务实测到的真实缺陷）═════════════════════════════
    Mutation(
        id="M22", side="be", path=WP_MODEL, kind="replace",
        anchor='        sa.BigInteger, server_default=text("0"), nullable=False',
        new="        sa.BigInteger, server_default=text(\"0\"), nullable=False, key=\"_mut_renamed\"",
        want=f"{T19}.py::test_the_orm_declares_the_v151_content_revision_columns",
        why="删掉 ORM 侧的 `content_revision` 声明 ⇒ 任何用 `Base.metadata.create_all` 建库"
            "的环境里这一列根本不存在，读它的代码报 `no such column: content_revision`"
            "（本任务实测）。V151 只在真库上加了列，ORM 不声明就等于半个迁移",
    ),
    Mutation(
        id="M23", side="be", path=WP_MODEL, kind="replace",
        anchor="    current_content_version_id: Mapped[uuid.UUID | None] = mapped_column(",
        new="    current_content_version_id: Mapped[uuid.UUID | None] = mapped_column(\n        ForeignKey(\"working_paper_content_version.id\"),",
        want=f"{T19}.py::test_the_orm_declares_the_v151_content_revision_columns",
        why="给它加上 ORM 级 ForeignKey ⇒ 未 import `workpaper_sync_models` 的 "
            "`create_all` 场景在建表阶段 NoReferencedTableError。真正的 FK 由 V151 在数据库"
            "侧持有；这条证明「刻意不声明 FK」是可 falsify 的决定，不是遗漏",
    ),
    # ═══ 六、source 词表与迁移双向锁死 ═══════════════════════════════════════
    Mutation(
        id="M24", side="be",
        path="backend/app/services/workpaper_sync/content_mutation.py", kind="replace",
        anchor='    {"html", "onlyoffice", "conflict_resolution", "rollback", "custom", "upload", "wopi"}',
        new='    {"html", "onlyoffice", "conflict_resolution", "rollback", "custom", "upload"}',
        want=f"{T19}.py::test_the_content_source_vocabulary_matches_the_migration",
        wants=(f"{T15}.py::TestPlanAndMutationShape::test_source_vocabulary_matches_the_owning_migration",),
        why="让 Python 侧词表少一个值 ⇒ 与 V152 的 `ck_wpcv_source` 漂移。构造点会放行/拒绝"
            "错的集合，被放行的值最终在 DB CHECK 上炸成一个看不出来源的 IntegrityError",
    ),
    # ═══ 七、projection lane：模板迁移回滚 + 历史快照回滚（增量二）═══════════
    Mutation(
        id="M25", side="be", path=MIGRATION_SVC, kind="insert",
        anchor='            logger.warning("底稿不存在或已删除，拒绝回滚: wp=%s", wp_id)',
        new="            await self.db.commit()",
        want=f"{T19}.py::test_migrated_writer_owns_no_direct_commit[WpMigrationService.rollback]",
        why="给失败路径塞一个裸 `db.commit()` ⇒ 回滚的唯一提交出口不再唯一。挑失败分支注入"
            "是刻意的：成功路径的 commit 会被「恰一处 commit_projection」那条顺带发现，而"
            "失败分支的第二次提交只有这条否定式判据能拦（它会把调用方尚未完成的其它写入"
            "一起提交）",
    ),
    Mutation(
        id="M26", side="be", path=MIGRATION_SVC, kind="replace",
        anchor="            capability=Capability.single_html,",
        new="            capability=Capability.custom,",
        want=f"{T19}.py::test_the_projection_lane_capability_is_declared_at_the_call_site[WpMigrationService.rollback]",
        why="把调用点声明的 capability 换掉 ⇒ 声明侧那道拒绝（`HtmlOnlyCommitPlan."
            "__post_init__`）虽然会在运行时抛，但**结构判据**必须先钉住「调用点确实自己"
            "声明」。这条同时证明装配层没有替调用方写死 capability —— 写死了，换调用点的"
            "值就再也影响不到任何东西",
    ),
    Mutation(
        id="M27", side="be", path=MIGRATION_SVC, kind="replace",
        anchor="            source=ROLLBACK,",
        new="            source=ContentSource('html'),",
        want=f"{T19}.py::test_projection_writer_routes_through_the_unified_entry[WpMigrationService.rollback]",
        why="把回滚的 `source` 换回 `html` ⇒ 一次回滚在 evidence 与 timeline 里与一次用户"
            "编辑不可区分（Requirement 2.3 点名 source 必须落库）。这条是 lane 的 source "
            "从写死改成透传之后**唯一**能证明「透传真的被用上了」的判据",
    ),
    Mutation(
        id="M28", side="be", path=CM, kind="replace",
        # 两条 lane 的 `create_content_version(...)` 里这一行逐字相同，连上面那句
        # 「③ immutable content version」注释也一样。唯一命中的近邻是 projection
        # artifact 注册的 `kind=ArtifactKind.projection,`（只有 html-only lane 注册
        # projection artifact），从它相对定位。
        scope="                kind=ArtifactKind.projection,",
        offset=14,
        anchor="                source=str(plan.source),",
        new="                source=str(HTML),",
        want=f"{T19}.py::test_the_projection_lane_records_the_real_source",
        why="把 lane 里 content version 的 source 改回写死 ⇒ 回归到改造前的形态：plan 上带着"
            "`rollback`，落库却是 `html`。判据钉在 `str(plan.source)` 这个表达式上而不是"
            "「有没有 source 参数」—— 后者被写死值满足",
    ),
    Mutation(
        id="M29", side="be", path=CM, kind="replace",
        anchor="    source: ContentSource = HTML",
        new="    source: ContentSource = ROLLBACK",
        want=f"{T19}.py::test_the_projection_lane_records_the_real_source",
        wants=(f"{T18}.py::test_the_html_save_plan_declares_the_single_html_lane",),
        why="把 lane 的**默认** source 从 `html` 改成 `rollback` ⇒ `wp_html_save` 的每一次"
            "普通保存都被记成回滚。新增一个带默认值的字段最容易的假绿方式就是默认值写错，"
            "而只断言「rollback 能传进来」不会发现它",
    ),
    Mutation(
        id="M30", side="be", path=MIGRATION_SVC, kind="replace",
        anchor="        expected_revision = await writer.current_revision(wp_id)",
        new="        expected_revision = 0",
        want=f"{T19}.py::test_the_template_rollback_still_restores_the_snapshot_payload",
        why="把期望 revision 钉死成 0 ⇒ 乐观锁恒不匹配（或在新底稿上恒匹配），CAS 的并发裁决"
            "失效。真实执行判据断言它等于**回滚前**读到的那个值(7)，所以任何常量都打红",
    ),
    Mutation(
        id="M31", side="be", path=MIGRATION_SVC, kind="insert",
        anchor="        receipt = await writer.commit_projection(",
        new="        expected_revision = await writer.current_revision(wp_id)",
        want=f"{T19}.py::test_the_template_rollback_still_restores_the_snapshot_payload",
        why="在写完内容之后再读一次期望 revision ⇒ 拿自己刚写的那一版当期望值，乐观锁恒真"
            "（这正是本 spec 在 `wp_html_save` 里消灭过的形态）。判据必须断言**所有** "
            "revision 读取都早于 UPDATE，只看第一次读取的话这条注入会 GREEN —— 单行锚点，"
            "跨行锚点在 CRLF 工作树上必 ANCHOR-MISS",
    ),
    Mutation(
        id="M32", side="be", path=TRAIL, kind="insert",
        # `create_snapshot` 里也有一处逐字相同的 `return SnapshotMeta(`，相对定位到
        # rollback 那一处。
        scope="        await writer.publish_committed_events(receipt)",
        offset=2,
        anchor="        return SnapshotMeta(",
        new="        db.add(rollback_snapshot)",
        want=f"{T19}.py::test_the_version_trail_rollback_commits_after_its_snapshot_row",
        why="把 rollback 快照行的写入挪到唯一提交出口**之后**（用注入等价形态：多一处 "
            "`db.add` 落在 commit 之后）⇒ 它落到下一个事务，而 router 不一定再提交一次，"
            "「回滚到哪个版本」的审计记录静默丢失（Requirement 13.1）",
    ),
    Mutation(
        id="M33", side="be", path=TRAIL, kind="replace",
        anchor='            html_data={"checklist_responses": data_json or []},',
        new="            html_data={},",
        want=f"{T19}.py::test_the_projection_payload_comes_from_the_restored_snapshot[VersionTrailService.rollback_to_snapshot]",
        why="把恢复内容换成空载荷 ⇒ content version 的 projection digest 与实际落库的"
            "`checklist_responses` 无关，任何两次回滚都算出同一个 hash（内容寻址身份失效，"
            "历史读取再也分不出版本）。🔴 首轮判 GREEN，实测到守卫缺陷：接线判据只断言"
            "`html_data` 这个**关键字在不在**，从不看里面是什么 ⇒ 补 "
            "`test_the_projection_payload_comes_from_the_restored_snapshot` 后转 RED",
    ),
    # ═══ 八、F2 半闭环：版本域统一、capability 与第二套流程都保留 ═════════════
    Mutation(
        id="M34", side="be", path=F2_PLAN, kind="replace",
        anchor="        payload=docx_path.read_bytes(),",
        new="        payload=payload.encode(),",
        want=f"{T19}.py::test_the_f2_writer_submits_the_docx_body_not_the_fields_json[F2-22]",
        why="把权威载荷从 docx 本体换成 fields JSON 串 ⇒ `single_onlyoffice` 的权威内容变成"
            "派生投影（Requirement 2.11 / Property 50 明令禁止），且 representation 指向一个"
            "打不开的「docx」。`payload` 这个局部变量名正好就是 fields 的 JSON —— 这类混用"
            "在评审里极难看出来，必须有判据",
    ),
    Mutation(
        id="M35", side="be", path=F2_SUMMARY, kind="replace",
        anchor='        lane_id="f2_stocktake_summary",',
        new='        lane_id="custom_cells",',
        want=f"{T19}.py::test_the_f2_writer_submits_the_docx_body_not_the_fields_json[F2-23]",
        why="把 authority model 换成 custom ⇒ 两者都是「OOXML 本体即权威」，不会造成数据损坏，"
            "但 evidence 的 authority-model 分桶失真：F2 是纯 OO 入口（没有 HTML 对端），"
            "custom 是平台生成的 xlsx 底稿。分桶错了，「哪些 entry 需要 HTML 对端」这个问题"
            "就再也答不对。🔴 锚点随生产载体迁移（Task 65）：改造前的落点是"
            "`authority_model=AuthorityModel.opaque_single_onlyoffice,`，该参数已被删除 ⇒ "
            "锚点 ANCHOR-MISS。新载体是 `lane_id=` + lane 登记表，改 lane 就等价于改 "
            "authority model（`custom_cells` 登记的正是 `custom_authoritative_ooxml`），"
            "变异语义一字未变",
    ),
    Mutation(
        id="M36", side="be", path=F2_SUMMARY, kind="replace",
        anchor='        entry_id=opaque_entry_id(wp_code=f"{wp_code or wp_id}#{_SHEET_CODE}", wp_id=wp_id),',
        new="        entry_id=opaque_entry_id(wp_code=wp_code, wp_id=wp_id),",
        want=f"{T19}.py::test_the_two_f2_sheets_do_not_share_one_entry_scope",
        why="去掉 entry_id 里的 sheet code ⇒ F2-22 与 F2-23（同一底稿的两份不同 docx）落到"
            "同一个 entry scope，互相顶掉对方的 entry pointer 与 representation generation。"
            "从此按 F2-22 的历史版本下载会拿到 F2-23 的文件 —— 而两边各自的保存都「成功」。"
            "🔴 首轮判 GREEN，实测到守卫缺陷：原判据自己拿 `_SHEET_CODE` 去调构造器，证明的"
            "是「构造器**能**产出两个不同 entry」，从不看 writer 的**调用点**传了什么 ⇒ 补"
            "调用点 AST 断言后转 RED",
    ),
    Mutation(
        id="M37", side="be", path=F2_PLAN, kind="replace",
        anchor="    except RevisionConflictError as exc:",
        new="    except HTTPException as exc:",
        want=f"{T19}.py::test_the_f2_conflict_is_translated_before_the_broad_catch[F2-22]",
        why="把窄捕获换成一个**永不匹配** `_save_fields` 冲突的异常类型 ⇒ `RevisionConflict"
            "Error` 落到下面那条 `except Exception`，用户拿到 500「结构化落库失败」而不是"
            "409「请重新打开再同步」：原因是错的，也无法自助恢复（Requirement 5.12）",
    ),
    Mutation(
        id="M38", side="be", path=F2_SUMMARY, kind="replace",
        anchor="    writer = build_content_mutation_service_writer(db)",
        new="    writer = build_content_mutation_service_writer(db)\n    await db.commit()",
        want=f"{T19}.py::test_migrated_writer_owns_no_direct_commit[_f2_stocktake_summary_sync::_save_fields]",
        wants=(f"{INV}.py::test_only_the_migrated_writers_reach_the_unified_commit_boundary",),
        why="把 F2 原来那个裸 `db.commit()` 写回去 ⇒ fields 行先自己提交一次，随后 docx 的"
            "content version 再提交一次：一次业务写入落在两个事务里，中间崩溃就留下"
            "「结构化视图已更新、权威 docx 没有对应版本」的分叉（Requirement 2.4 / 13.1）",
    ),
    Mutation(
        id="M39", side="be", path=F2_PLAN, kind="replace",
        anchor='_SHEET_CODE = "F2-22"',
        new='_SHEET_CODE = "F2-23"',
        want=f"{T19}.py::test_the_two_f2_sheets_do_not_share_one_entry_scope",
        why="把 F2-22 模块的 sheet code 改成 F2-23 ⇒ 两个模块的 entry_id 与 docx 缓存文件名"
            "全部相同（读的是对方的文件、写的是对方的 entry）。这条同时是「两处共用同一个"
            "常量」的 falsifier：若文件名仍是各写一遍字面量，改常量不会让两者一起变",
    ),
    # ═══ 九、`.versions` 快照不再发明版本号 ═══════════════════════════════════
    Mutation(
        id="M40", side="be", path=STORAGE, kind="insert",
        anchor="        version_path = version_dir / version_name",
        new="        wp.file_version = (wp.file_version or 1) + 1",
        want=f"{T19}.py::test_migrated_writer_owns_no_private_version_counter[WpStorageService.save_version]",
        wants=(f"{INV}.py::test_legacy_version_writers_are_the_enumerated_ones",),
        why="把备份动作自增计数器的行为写回去 ⇒ 「版本 7」与「版本 6」逐字节相同（伪版本），"
            "且第四个写入方回来争抢同一列。它同时是清册期望集合搬动的 falsifier：只把"
            "`save_version` 从 `legacy_version_writers` 里删掉而不搬生产，本条会 GREEN",
    ),
    Mutation(
        id="M41", side="be", path=STORAGE, kind="replace",
        anchor="            f\"v{content_revision}_\"",
        new="            f\"v{wp.file_version}_\"",
        want=f"{T19}.py::test_the_storage_snapshot_no_longer_invents_a_version",
        why="把快照名换回已冻结的 `file_version` ⇒ 计数器不动了，`{stem}_v11_*.xlsx` 每次保存"
            "都在同一个前缀下堆积、时间戳成为唯一区分，且与真正在动的 `content_revision` "
            "对不上号：拿到一份备份也说不出它是哪个业务版本",
    ),
    Mutation(
        id="M42", side="be", path=STORAGE, kind="insert",
        anchor="        return {",
        new="        await self.db.flush()",
        want=f"{T19}.py::test_the_storage_snapshot_no_longer_invents_a_version",
        why="加回一次 `flush()` ⇒ 备份动作又把调用方尚未完成的写入推进数据库。它不改内容，"
            "所以「零 version 写」那条判据满足不了这一点，必须单独钉住「不动事务」",
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task19_writer_migration.py",
                "backend/tests/workpaper_sync/test_task15_content_mutation.py",
                "backend/tests/workpaper_sync/test_task18_html_save_unified_revision.py",
                "backend/tests/test_workpaper_writer_inventory.py",
                "backend/tests/test_custom_workpaper_cells.py",
                # 只取本任务相关的类：整文件另有 14 条与 Task 19 无关的既存失败
                # （QCEngine 的 qc_rule_definitions 空表、若干 API/Review 用例），
                # 基线非空会让差集判定不可信。
                "backend/tests/test_wopi_working_paper_qc_review.py::TestWOPIHostService",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
        )
    )
