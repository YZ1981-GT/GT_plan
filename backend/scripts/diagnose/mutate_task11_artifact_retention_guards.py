"""Task 11 变异检验：证明 artifact/OOXML/retention 守卫真的锁死（RED/GREEN/ANCHOR-MISS/WRONG-TEST）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 2.4, 3.4, 5.6, 5.7, 5.8, 5.9, 5.11, 9.6, 9.7, 10.7, 10.8, 14.11
Properties: P5 / P17 / P42 / P60

═══ 变异改的是**生产代码与配置**，不是守卫 ═══

Task 9 的变异改 schema（SQL），Task 10 改 ORM/domain/repository。Task 11 的被测物是
文件系统协议 + OOXML 安全门 + 版本化 retention 策略，因此变异落在五处：

  * `app/services/workpaper_sync/limits.py`        —— 关掉预算门、把 `>` 改成 `>=`
  * `app/services/workpaper_sync/ooxml_security.py` —— 关掉安全门、把流式读改成整包读、
                                                       打乱门顺序
  * `app/services/workpaper_sync/artifacts.py`     —— 关掉路径安全/digest 校验/同卷前置、
                                                       把 quarantine 分支短路成 durable、
                                                       把授权判定挪到资源读取之后
  * `app/services/workpaper_sync/retention.py`     —— 关掉 legal hold / grace / 二次引用复核、
                                                       缩小引用来源清单
  * `data/workpaper_sync_limits.json` /
    `data/workpaper_sync_retention_policy.json`    —— **配置是单一真源**：改配置必须让
                                                       守卫变红，否则代码里藏着第二真源

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 两条本任务实测到的判据设计教训 ═══

1. **magic bytes 门一度是不可达判据**：Python 的 `zipfile` 按中央目录反算偏移，
   前置 EXE stub 的 polyglot 包**照样打得开**。首版守卫只测「非 ZIP 文件」，那与
   `BadZipFile` 完全重合 ⇒ M19（删掉 magic 检查）会判 GREEN。补 `polyglot_prefix`
   用例后该门才有独立判据。
2. **`class_not_deletable` 一度被 `legal_hold` 遮蔽**：审计产物同时带 legal hold 与
   `deletable=false`，而 legal hold 判定在前 ⇒ 只看审计产物永远测不到 deletable 分支。
   守卫改成同时断言 `definition` 类（无 legal hold、deletable=false），M36 才可被抓到。

用法（仓库根）:
    python backend/scripts/diagnose/mutate_task11_artifact_retention_guards.py --list
    python backend/scripts/diagnose/mutate_task11_artifact_retention_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task11_artifact_retention_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task11-artifact-retention/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

LIMITS = "backend/app/services/workpaper_sync/limits.py"
SECURITY = "backend/app/services/workpaper_sync/ooxml_security.py"
ARTIFACTS = "backend/app/services/workpaper_sync/artifacts.py"
RETENTION = "backend/app/services/workpaper_sync/retention.py"
LIMITS_JSON = "backend/data/workpaper_sync_limits.json"
POLICY_JSON = "backend/data/workpaper_sync_retention_policy.json"

#: 覆盖面分母：Task 11 新建的两个守卫文件。
GUARD_FILES = {
    "test_task11_artifact_repository.py": "Task 11 新建：文件系统/OOXML 安全/预算/candidate 隔离守卫",
    "test_task11_retention_orphan_pg.py": "Task 11 新建：真实 PG 的 Property 5 / orphan / retention 守卫",
}

FS = "test_task11_artifact_repository"
PG = "test_task11_retention_orphan_pg"

MUTATIONS: list[Mutation] = [
    # ══ 一、Requirement 14.11 预算门（limits.py）═══════════════════════
    Mutation(
        id="M01", side="be", path=LIMITS, kind="replace",
        anchor="        if observed > self.max_compressed_bytes:",
        new="        if False:",
        want=f"{FS}.py::test_property_60_scalar_budget_boundaries",
        wants=(f"{FS}.py::test_property_60_streaming_stage_aborts_at_cap_without_partial_residue",),
        why="关掉压缩体积预算 ⇒ 50 MiB 以上的 OOXML 与流式 staging 都不再有界，"
            "Requirement 14.11 的『超限必须 fail visible』失效",
    ),
    Mutation(
        id="M02", side="be", path=LIMITS, kind="replace",
        anchor="        if observed > self.max_zip_entries:",
        new="        if observed >= self.max_zip_entries:",
        want=f"{FS}.py::test_property_60_scalar_budget_boundaries",
        wants=(f"{FS}.py::test_property_60_zip_entry_boundaries_end_to_end",),
        why="off-by-one：把 `>` 改成 `>=` ⇒ 恰好 N（20000）个 entry 的合法文件被拒。"
            "只测 N+1 的守卫看不见这条，必须有 N-1/N/N+1 三点才抓得到",
    ),
    Mutation(
        id="M03", side="be", path=LIMITS, kind="replace",
        anchor="        if ratio > self.max_compression_ratio:",
        new="        if False:",
        want=f"{FS}.py::test_property_60_compression_ratio_boundaries",
        wants=(f"{FS}.py::test_property_60_expanded_and_ratio_gates_end_to_end",),
        why="关掉压缩比预算 ⇒ 高压缩比 zip bomb 只剩总量一道门，单 entry 的比值不再受限",
    ),
    Mutation(
        id="M04", side="be", path=LIMITS, kind="replace",
        anchor="        if observed > self.max_expanded_bytes:",
        new="        if False:",
        want=f"{FS}.py::test_property_60_scalar_budget_boundaries",
        wants=(
            f"{FS}.py::test_property_17_zip_bomb_is_quarantined_with_bounded_memory",
            f"{FS}.py::test_property_60_expanded_and_ratio_gates_end_to_end",
        ),
        why="关掉展开总量预算 ⇒ zip bomb 会被完整展开，Requirement 10.8『不得直接交给"
            "解析器无限展开』失效",
    ),
    Mutation(
        id="M05", side="be", path=LIMITS, kind="replace",
        anchor="        if observed > self.max_table_rows:",
        new="        if False:",
        want=f"{FS}.py::test_property_60_table_rows_and_projection_fields_boundaries",
        why="关掉单表行数预算（Requirement 14.11 的 100000 行）",
    ),
    Mutation(
        id="M06", side="be", path=LIMITS, kind="replace",
        anchor="        if observed > self.max_projection_fields:",
        new="        if False:",
        want=f"{FS}.py::test_property_60_table_rows_and_projection_fields_boundaries",
        why="关掉单 projection field 数预算（Requirement 14.11 的 200000 fields）",
    ),
    Mutation(
        id="M07", side="be", path=LIMITS, kind="replace",
        anchor='        raise LimitsConfigError("配置缺少 ooxml_policy 段")',
        new='        policy_raw = {"policy_version": "silent-default", "zip_magic_hex": '
            '"504b0304", "required_parts": ["[Content_Types].xml"], '
            '"document_type_markers": {"xlsx": "xl/workbook.xml"}, '
            '"external_relationship_target_mode": "External", '
            '"allow_external_relationships": False, "allow_macros": False, '
            '"allow_embedded_objects": False, "reject_absolute_entry_names": True}',
        want=f"{FS}.py::test_limits_config_missing_or_invalid_fails_instead_of_falling_back",
        why="给缺失配置加一个静默内置默认值 ⇒ 配置被删/写坏时按看不见的默认值继续跑，"
            "Requirement 14.11 的『单一配置锁死预算』变成两个真源",
    ),

    # ══ 二、配置即单一真源（改 JSON 必须让守卫变红）═══════════════════
    Mutation(
        id="M08", side="be", path=LIMITS_JSON, kind="replace",
        anchor='    "max_zip_entries": 20000,',
        new='    "max_zip_entries": 19999,',
        want=f"{FS}.py::test_limits_config_matches_requirement_14_11_exactly",
        why="改配置里的 entry 预算 ⇒ 与 Requirement 14.11 不符必须打红。"
            "若边界测试也随之飘（因为它们从配置取值）而契约测试不红，说明缺少『配置 ↔ AC』"
            "这条锁",
    ),
    Mutation(
        id="M09", side="be", path=LIMITS_JSON, kind="replace",
        anchor='    "allow_macros": false,',
        new='    "allow_macros": true,',
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="策略层放开宏 ⇒ 带 `vbaProject.bin` 的 incoming 变成 durable。"
            "证明宏拒绝是**配置驱动**的真实行为，而不是代码里写死的分支",
    ),
    Mutation(
        id="M10", side="be", path=POLICY_JSON, kind="replace",
        anchor='      "deletable": false,',
        scope='    "retention_audit": {',
        offset=7,
        new='      "deletable": true,',
        want=f"{FS}.py::test_retention_policy_declares_every_class_used_by_production_code",
        why="让删除审计自身可被 GC 删 ⇒ 下一轮 GC 会抹掉上一轮的删除记录，"
            "Requirement 5.11 的『删除结果证据』自我消解",
    ),
    Mutation(
        id="M11", side="be", path=POLICY_JSON, kind="replace",
        anchor='    "dry_run_never_deletes": true,',
        new='    "dry_run_never_deletes": false,',
        want=f"{FS}.py::test_retention_policy_declares_every_class_used_by_production_code",
        wants=(f"{PG}.py::test_dry_run_never_deletes_and_reports_grace",),
        why="把不变式声明改成 false ⇒ 策略解析必须 fail closed。"
            "这些不变式不是可选项（Requirement 5.11），配置里写 false 就该拒绝加载",
    ),

    # ══ 三、OOXML 安全门（ooxml_security.py）═══════════════════════════
    Mutation(
        id="M12", side="be", path=SECURITY, kind="replace",
        anchor="    if head != policy.zip_magic:",
        new="    if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        wants=(f"{FS}.py::test_contract_validation_gate_order_and_masquerade",),
        why="删掉 magic bytes 门 ⇒ **polyglot（前置 EXE stub 的自解压包）会通过**。"
            "🔴 首版守卫只测『非 ZIP 文件』，那与 zipfile 自己的 BadZipFile 完全重合，"
            "本条会判 GREEN；补 polyglot 用例后该门才有独立判据",
    ),
    Mutation(
        id="M13", side="be", path=SECURITY, kind="replace",
        anchor="            if policy.reject_absolute_entry_names and _ABSOLUTE_ENTRY_RE.match(name):",
        new="            if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="放开绝对路径 entry 名（`/etc/passwd`、`C:\\evil`）⇒ 解压到 ZIP 外任意位置",
    ),
    Mutation(
        id="M14", side="be", path=SECURITY, kind="replace",
        anchor="                if bad and bad in name:",
        new="                if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        wants=(f"{FS}.py::test_gate_order_is_cheapest_first",),
        why="放开 `..` 等禁止片段 ⇒ 目录穿越 entry 名进入 incoming",
    ),
    Mutation(
        id="M15", side="be", path=SECURITY, kind="replace",
        anchor="        lim.assert_zip_entries(report.entry_count)",
        new="        pass",
        want=f"{FS}.py::test_property_60_zip_entry_boundaries_end_to_end",
        wants=(f"{FS}.py::test_gate_order_is_cheapest_first",),
        why="不再调用 entry 数预算门 ⇒ 20001 个 entry 的文件通过。"
            "这条与 M02 配对：M02 证明门本身有效，本条证明它真的被调用了",
    ),
    Mutation(
        id="M16", side="be", path=SECURITY, kind="replace",
        anchor="                    lim.assert_expanded_size(total_expanded)",
        new="                    pass",
        want=f"{FS}.py::test_property_17_zip_bomb_is_quarantined_with_bounded_memory",
        wants=(f"{FS}.py::test_property_60_expanded_and_ratio_gates_end_to_end",),
        why="去掉**循环内**的展开量判定 ⇒ 变成『先解完再看总数』，zip bomb 赢了",
    ),
    Mutation(
        id="M17", side="be", path=SECURITY, kind="replace",
        anchor="                    chunk = src.read(lim.chunk_bytes)",
        new="                    chunk = src.read()",
        want=f"{FS}.py::test_property_17_zip_bomb_is_quarantined_with_bounded_memory",
        why="把流式分块读改成整包读 ⇒ 64 MiB 的 entry 一次进内存，tracemalloc 峰值突破"
            "16 MiB 预算。**这是唯一能证明『流式』本身的判据** —— 只断言『被拒绝』的守卫"
            "看不见整包读（拒绝仍然发生，只是先 OOM 风险）",
    ),
    Mutation(
        id="M18", side="be", path=SECURITY, kind="replace",
        anchor="        if missing:",
        new="        if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="放开必需部件缺失（`[Content_Types].xml`）⇒ 不完整 OOXML 进入 durable",
    ),
    Mutation(
        id="M19", side="be", path=SECURITY, kind="replace",
        anchor="        if detected != document_type:",
        new="        if False:",
        want=f"{FS}.py::test_contract_validation_gate_order_and_masquerade",
        wants=(f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",),
        why="放开扩展名伪装（xlsx 字节声明成 docx）⇒ 走错 adapter engine 解析",
    ),
    Mutation(
        id="M20", side="be", path=SECURITY, kind="replace",
        anchor="        if report.external_relationship_parts and not policy.allow_external_relationships:",
        new="        if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="放开外部关系 ⇒ OOXML 可引用外部 URL（Requirement 10.8 明令拒绝或隔离）",
    ),
    Mutation(
        id="M21", side="be", path=SECURITY, kind="replace",
        anchor="        if report.macro_parts and not policy.allow_macros:",
        new="        if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="放开宏 ⇒ 带 VBA 的文档进入 durable 并可被下发给编辑器",
    ),
    Mutation(
        id="M22", side="be", path=SECURITY, kind="replace",
        anchor="        if report.embedded_object_parts and not policy.allow_embedded_objects:",
        new="        if False:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="放开嵌入对象（OLE）⇒ Requirement 10.8 的『嵌入对象按策略拒绝或隔离』失效",
    ),
    Mutation(
        id="M23", side="be", path=SECURITY, kind="replace",
        anchor="        report._passed(\"zip_entries\")",
        new="        pass",
        want=f"{FS}.py::test_contract_validation_gate_order_and_masquerade",
        why="漏记一个门 ⇒ `report.gates` 与 `GATE_ORDER` 不等。守卫用**实际顺序序列**"
            "作判据（而不是『某个门存在』），这条证明该判据真的在比较序列",
    ),

    # ══ 四、路径安全与内容寻址发布（artifacts.py）═══════════════════════
    Mutation(
        id="M24", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if candidate != root_real and root_real not in candidate.parents:",
        new="        if False:",
        want=f"{FS}.py::test_contract_path_safety_cases_all_rejected",
        wants=(f"{FS}.py::test_property_42_resolution_never_escapes_project_root",),
        why="关掉项目根归属判定 ⇒ 8 类逃逸全部放行（Property 42 归零）",
    ),
    Mutation(
        id="M25", side="be", path=ARTIFACTS, kind="replace",
        anchor="        candidate = Path(os.path.realpath(os.path.join(str(root_real), str(relative))))",
        new="        candidate = Path(os.path.join(str(root_real), str(relative)))",
        want=f"{FS}.py::test_contract_path_safety_cases_all_rejected",
        why="把 realpath 换成纯字符串拼接 ⇒ `..` 不被规范化、软链接不被解析，"
            "Task 7 fs7 的 symlink_escape 与 traversal 全部通过。"
            "『仅字符串前缀比较拦不住软链接越界』这条实测结论就是这么来的",
    ),
    Mutation(
        id="M26", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if digest != expected_sha256:",
        new="        if False:",
        want=f"{FS}.py::test_finalize_rejects_tampered_candidate_bytes",
        wants=(
            f"{FS}.py::test_publish_rejects_declared_digest_mismatch_and_post_publish_drift",
            f"{FS}.py::test_staging_residue_is_invisible_to_resolver_and_refused_by_publish_gate",
        ),
        why="关掉 finalize **前**的 digest 校验 ⇒ 被 kill 截断的半成品与被篡改的 candidate "
            "都能进 publish（Requirement 3.4 要求反读校验通过才允许 pointer 指向）",
    ),
    Mutation(
        id="M27", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if post_digest != expected_sha256:",
        new="        if False:",
        want=f"{FS}.py::test_publish_rejects_declared_digest_mismatch_and_post_publish_drift",
        why="关掉 finalize **后**的 digest 校验 ⇒ replace 之后目标内容漂移无人发现。"
            "任务正文明确要求『finalize 前后都校验』，两条各有独立变异",
    ),
    Mutation(
        id="M28", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if not same_volume(staged_path, target.parent):",
        new="        if False:",
        want=f"{FS}.py::test_cross_volume_publish_fails_visible",
        why="去掉 publish 的同卷前置 ⇒ 跨卷 publish 依赖底层 OSError 才失败，"
            "错误信息不再指出『staging 必须与发布目录同卷』这条架构结论（Task 7 fs4）",
    ),
    Mutation(
        id="M29", side="be", path=ARTIFACTS, kind="replace",
        anchor="    if winerror in (5, 32):",
        new="    if winerror in (5,):",
        want=f"{FS}.py::test_contract_diagnostic_mapping_matches_classifier",
        wants=(f"{FS}.py::test_file_in_use_diagnostics_for_target_and_source",),
        why="把『源被占用』（WinError 32）从 FILE_IN_USE 里摘掉 ⇒ 与 Task 7 fs5 实测的"
            "诊断映射不符，Requirement 9.7 的可诊断性缺一半",
    ),
    Mutation(
        id="M30", side="be", path=ARTIFACTS, kind="replace",
        anchor="    if winerror == 17 or exc.errno == errno.EXDEV:",
        new="    if False:",
        want=f"{FS}.py::test_contract_diagnostic_mapping_matches_classifier",
        wants=(f"{FS}.py::test_cross_volume_publish_fails_visible",),
        why="去掉跨卷诊断码 ⇒ WinError 17 被误诊成通用 IO 错误",
    ),
    Mutation(
        id="M31", side="be", path=ARTIFACTS, kind="replace",
        anchor='                    held="source" if winerror == 32 else "target",',
        new='                    held="target",',
        want=f"{FS}.py::test_file_in_use_diagnostics_for_target_and_source",
        why="把『源被占用』误报成『目标被占用』⇒ 运维按错的方向排查。"
            "只断言『抛了 FILE_IN_USE』的守卫看不见这条",
    ),
    Mutation(
        id="M32", side="be", path=ARTIFACTS, kind="replace",
        anchor="            if existing_digest == expected_sha256:",
        new="            if False:",
        want=f"{FS}.py::test_contract_target_name_pattern_and_idempotency_scope",
        wants=(f"{FS}.py::test_content_addressed_publish_survives_held_current_artifact",),
        why="去掉『目标已存在且内容相同 ⇒ 幂等复用』⇒ 重复 publish 会去覆盖已存在目标，"
            "而 Task 7 fs5 实测目标被任何 share 模式占用都报 WinError 5",
    ),

    # ══ 五、incoming durable / quarantine 两支（artifacts.py）═══════════
    Mutation(
        id="M33", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if rejection is None:",
        new="        if True:",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        wants=(f"{FS}.py::test_property_17_quarantine_is_permanent_and_download_only",),
        why="让 sealing 恒走 durable 分支 ⇒ 恶意文件直接成为 application substrate，"
            "Requirement 5.6 的『校验通过才可 durable』彻底失效",
    ),
    Mutation(
        id="M34", side="be", path=ARTIFACTS, kind="replace",
        anchor="                rejection = (exc.error_code, exc.gate, str(exc))",
        new="                rejection = None",
        want=f"{FS}.py::test_property_17_malicious_incoming_is_quarantined_never_durable",
        why="把安全异常吞成 None ⇒ 经典 fail-open：`except` 抓到了却当成通过。"
            "与 M33 的区别是这条只吞 OOXML 安全/结构异常，预算异常仍会隔离 ——"
            "证明守卫对**每一类**拒绝都有独立判据",
    ),
    Mutation(
        id="M35", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if self.state is ArtifactState.quarantined:",
        new="        if False:",
        want=f"{FS}.py::test_property_17_quarantine_is_permanent_and_download_only",
        why="短路 `raise_if_not_durable` 的隔离分支 ⇒ quarantined 会抛"
            "`IncomingNotDurableError`（暂态）而不是 `QuarantinedIncomingError`（终态）。"
            "🔴 这正是 Task 10 记录过的遮蔽形态：两个异常类型共用时本条判 GREEN",
    ),
    Mutation(
        id="M36", side="be", path=ARTIFACTS, kind="replace",
        anchor="        raise QuarantineReleaseForbiddenError(",
        # 🔴 必须保持语法合法：`raise X(` 的续行是字符串拼接，直接换成 `return None`
        # 会让续行变成缩进错误 ⇒ 整文件 collect error ⇒ 判定退化成 WRONG-TEST
        # （首轮实测就是这样）。换成 `_ = (` 后续行原样成为括号内表达式，语法合法且行为归零。
        new="        _ = (",
        want=f"{FS}.py::test_property_17_quarantine_is_permanent_and_download_only",
        why="把『隔离永不 release』的恒抛方法改成静默成功 ⇒ 禁令消失。"
            "把禁令写成恒抛方法（而不是『不提供该方法』）正是为了让这条可被变异检验",
    ),
    Mutation(
        id="M37", side="be", path=ARTIFACTS, kind="replace",
        anchor="        raise IncomingNotResolvableError(",
        scope="    def promote_incoming_to_published(self, sealed: SealedIncoming) -> None:",
        offset=2,
        new="        _ = (",  # 同 M36：保持续行语法合法
        want=f"{FS}.py::test_property_17_quarantine_is_permanent_and_download_only",
        why="把『incoming 永不 published』的恒抛方法改成静默成功 ⇒ incoming 可被原地晋升",
    ),
    Mutation(
        id="M38", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if not authorization.granted:",
        new="        if not sealed.path.exists():\n"
            "            raise ArtifactRepositoryError('quarantined artifact 文件缺失')\n"
            "        if not authorization.granted:",
        want=f"{FS}.py::test_authorization_precedes_any_resource_read",
        why="把『资源存在性检查』插到授权判定**之前** ⇒ 违反 Requirement 10.6 的不可交换"
            "顺序（认证 → scope → … → 业务资源读取）。这条只能被『文件不存在 + 未授权 ⇒ "
            "仍抛授权错误』这种顺序判据抓到，看代码或断言异常类型都抓不到",
    ),
    Mutation(
        id="M39", side="be", path=ARTIFACTS, kind="replace",
        anchor='        if authorization.action != "download_only":',
        new="        if False:",
        want=f"{FS}.py::test_property_17_quarantine_is_permanent_and_download_only",
        why="放开 action ⇒ 拿着 `action='extract'` 的授权也能读 quarantined 文件，"
            "『只允许 download-only』失效",
    ),

    # ══ 六、resolver 可见性与判定顺序（artifacts.py）═══════════════════
    Mutation(
        id="M40", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if k is ArtifactKind.incoming:",
        new="        if False:",
        want=f"{FS}.py::test_contract_resolver_predicate_rejects_candidate_incoming_orphan",
        why="去掉 incoming 的专属可见性禁令 ⇒ 退化成通用 `ArtifactNotPublishedError`，"
            "Requirement 5.12 要求的 error code 定位失效",
    ),
    Mutation(
        id="M41", side="be", path=ARTIFACTS, kind="replace",
        anchor="        if k is ArtifactKind.upgrade_candidate:",
        new="        if False:",
        want=f"{FS}.py::test_contract_resolver_predicate_rejects_candidate_incoming_orphan",
        wants=(f"{FS}.py::test_candidate_is_non_current_and_outside_resolver_namespace",),
        why="去掉 candidate 的专属可见性禁令 ⇒ candidate 与『未发布』无法区分",
    ),
    Mutation(
        id="M42", side="be", path=ARTIFACTS, kind="insert",
        anchor="        s = state if isinstance(state, ArtifactState) else ArtifactState(state)",
        new="        if s is not ArtifactState.published:\n"
            "            raise ArtifactNotPublishedError(f'not published: {s.value}')",
        want=f"{FS}.py::test_contract_resolver_predicate_rejects_candidate_incoming_orphan",
        why="把通用 state 门插到 kind 专属禁令**之前** ⇒ incoming/candidate 的专属异常成为"
            "永久不可达分支。这是任务正文点名的两类高频遮蔽之一（校验顺序），"
            "只有『逐类断言异常类型』的守卫才抓得到",
    ),

    # ══ 七、RetentionPolicy（retention.py）════════════════════════════
    Mutation(
        id="M43", side="be", path=RETENTION, kind="replace",
        anchor="        if row.legal_hold and klass.honor_legal_hold:",
        new="        if False:",
        want=f"{PG}.py::test_retain_reason_matrix_covers_every_uncertainty_branch",
        wants=(f"{PG}.py::test_audit_is_per_object_persisted_and_itself_not_deletable",),
        why="关掉 legal hold ⇒ 法务冻结对象会被 GC 删除（Requirement 5.11 的 legal hold 例外）",
    ),
    Mutation(
        id="M44", side="be", path=RETENTION, kind="replace",
        anchor="        if not klass.deletable:",
        new="        if False:",
        want=f"{PG}.py::test_audit_is_per_object_persisted_and_itself_not_deletable",
        why="关掉 `deletable=false` ⇒ definition blob / evidence manifest / 删除审计自身"
            "都能被回收。🔴 只看审计产物测不到这条（它同时带 legal hold，先命中 legal_hold），"
            "必须再断言 definition 类才可达",
    ),
    Mutation(
        id="M45", side="be", path=RETENTION, kind="replace",
        anchor="        if klass.requires_orphaned_at and row.orphaned_at is None:",
        new="        if False:",
        want=f"{PG}.py::test_retain_reason_matrix_covers_every_uncertainty_branch",
        why="关掉『orphan 必须有 orphaned_at 才可删』⇒ 未经对账的 canonical 文件被当 orphan 删",
    ),
    Mutation(
        id="M46", side="be", path=RETENTION, kind="replace",
        anchor="        if age_hours < klass.ttl_hours + klass.grace_hours:",
        new="        if False:",
        want=f"{PG}.py::test_dry_run_never_deletes_and_reports_grace",
        why="关掉 grace ⇒ TTL 一到就删，Task 7 db5『grace 过后才删』的分支消失",
    ),
    Mutation(
        id="M47", side="be", path=RETENTION, kind="replace",
        anchor="        if in_flight is not None:",
        new="        if False:",
        want=f"{PG}.py::test_retain_reason_matrix_covers_every_uncertainty_branch",
        why="关掉 in-flight operation 检查 ⇒ 正在 merging 的 operation 产出的 artifact 被删",
    ),
    Mutation(
        id="M48", side="be", path=RETENTION, kind="replace",
        anchor="        if refs:",
        new="        if False:",
        want=f"{PG}.py::test_second_reference_recheck_retains_when_reference_reappears",
        why="关掉引用判定 ⇒ 计划与执行之间新出现的引用被无视，直接删掉在用文件，"
            "形成 Requirement 5.9 禁止的『pointer 指向缺失 artifact』半成功态",
    ),
    Mutation(
        id="M49", side="be", path=RETENTION, kind="replace",
        anchor="            fresh = await self._decide(row, moment, recheck=True)",
        new="            fresh = planned",
        want=f"{PG}.py::test_second_reference_recheck_retains_when_reference_reappears",
        why="apply 直接沿用 dry-run 的判定、不做二次复核 ⇒ 『dry-run + 二次复核』变成"
            "『只 dry-run』。这条与 M48 配对：M48 打引用判定本身，本条打**第二次调用**",
    ),
    Mutation(
        id="M50", side="be", path=RETENTION, kind="replace",
        anchor="        for src in REFERENCE_SOURCES:",
        new="        for src in REFERENCE_SOURCES[1:]:",
        want=f"{PG}.py::test_second_reference_recheck_retains_when_reference_reappears",
        why="漏查引用来源清单的第一项（definition blob）⇒ 被 definition 引用的 blob 会被删。"
            "这条模拟『新迁移加了 FK 但忘了登记』的真实事故形态",
    ),
    Mutation(
        id="M51", side="be", path=RETENTION, kind="replace",
        anchor='        "working_paper_pending_mutation", "payload_artifact_id",',
        new='        "working_paper_callback_delivery", "incoming_artifact_id",',
        want=f"{FS}.py::test_reference_sources_match_v151_ddl_bidirectionally",
        why="把一条引用来源改成另一张表的重复项 ⇒ 声明清单与 V151 DDL 不再相等。"
            "SQL 仍然合法（不会连带打红 PG 守卫），因此这条精确证明『双向比对』这一条判据",
    ),
    Mutation(
        id="M52", side="be", path=RETENTION, kind="replace",
        anchor="            row.state = ArtifactState.deleted.value",
        new="            row.state = row.state",
        want=f"{PG}.py::test_apply_deletes_only_after_unreferenced_and_writes_audit",
        why="删了文件却不把行标 deleted ⇒ DB 与磁盘再次分叉，下一轮 GC 会重复处理",
    ),
    Mutation(
        id="M53", side="be", path=RETENTION, kind="replace",
        anchor="            return self._retain(row, reason=\"no_policy_retain_and_alert\", age_hours=None)",
        new="            return self._retain(row, reason=\"class_not_deletable\", age_hours=None)",
        want=f"{PG}.py::test_retain_reason_matrix_covers_every_uncertainty_branch",
        why="把『无策略』的保留原因换成别的 ⇒ 告警集合不再包含它，"
            "『不确定即保留**并告警**』退化成静默保留",
    ),
    Mutation(
        id="M54", side="be", path=RETENTION, kind="replace",
        anchor="            alert=reason in self._policy.alert_retain_reasons,",
        new="            alert=False,",
        want=f"{PG}.py::test_retain_reason_matrix_covers_every_uncertainty_branch",
        wants=(f"{PG}.py::test_second_reference_recheck_retains_when_reference_reappears",),
        why="把告警位恒置 False ⇒ 保留了但没人知道，Requirement 5.11 的告警要求失效",
    ),
    Mutation(
        id="M55", side="be", path=RETENTION, kind="replace",
        anchor="                    retention_class=\"retention_audit\",",
        new="                    retention_class=\"default\",",
        want=f"{PG}.py::test_audit_is_per_object_persisted_and_itself_not_deletable",
        why="审计产物落错 retention class ⇒ 它不再受 `retention_audit` 规则保护",
    ),
    Mutation(
        id="M56", side="be", path=RETENTION, kind="replace",
        anchor="                    legal_hold=True,",
        new="                    legal_hold=False,",
        want=f"{PG}.py::test_audit_is_per_object_persisted_and_itself_not_deletable",
        why="审计产物不再 legal hold ⇒ 少一层保护（与 M55 是两条独立防线）",
    ),

    # ══ 八、Orphan 对账（artifacts.py）════════════════════════════════
    Mutation(
        id="M57", side="be", path=ARTIFACTS, kind="replace",
        anchor="            if rel in by_path:",
        new="            if True:",
        want=f"{PG}.py::test_orphan_reconciliation_registers_and_marks",
        why="不再登记『磁盘有文件、DB 无 row』的 orphan ⇒ DB rollback 留下的文件永远无人回收"
            "（Task 7 db4 的形态一）",
    ),
    Mutation(
        id="M58", side="be", path=ARTIFACTS, kind="replace",
        anchor="                row.state = ArtifactState.orphan.value",
        new="                pass",
        want=f"{PG}.py::test_orphan_reconciliation_registers_and_marks",
        why="不再把『无引用的 published row』标 orphan ⇒ Task 7 db4 的形态二失效，"
            "RetentionPolicy 也就永远等不到 orphaned_at",
    ),
    Mutation(
        id="M60", side="be", path=ARTIFACTS, kind="replace",
        anchor='                    row.retention_class = "orphan_canonical"',
        new="                    pass",
        want=f"{PG}.py::test_orphan_reconciliation_registers_and_marks",
        why="标记 orphan 时不同步 retention class ⇒ 这批 orphan 永远停在 `default` 类，"
            "而 `default.applies_to_states` 只含 `published` ⇒ RetentionPolicy 恒判 "
            "`class_scope_mismatch`（保留 + 告警）：既回收不了也持续刷屏。"
            "这条对应的生产缺陷正是首轮变异（M58 判 GREEN）追查出来的",
    ),
    Mutation(
        id="M59", side="be", path=ARTIFACTS, kind="replace",
        anchor="        root = self._layout.versions_root(project_id, wp_id)",
        new="        root = self._layout.project_root(project_id)",
        want=f"{FS}.py::test_property_17_incoming_sealing_is_delivery_scoped_and_durable",
        wants=(
            f"{FS}.py::test_candidate_is_non_current_and_outside_resolver_namespace",
            f"{FS}.py::test_finalize_candidate_copies_and_verifies_digest_before_and_after",
        ),
        why="把 resolver 命名空间从 `.versions` 扩到整个项目根 ⇒ `.staging` 半成品、"
            "`.incoming` 与 `.upgrade-candidates` 都变成『可解析』。"
            "Task 7 fs6 的三重理由之一（命名空间隔离）就此消失",
    ),

]

#: 🔴 **预期 GREEN 的对照项**，刻意不进 `MUTATIONS`（否则 `--run all` 的退出码会因为
#: 一条故意的 GREEN 而恒非零）。它们的作用是自证判定**不是**靠错误文案字符串匹配：
#: 只改文案、不改行为的变异若也判 RED，说明有守卫在断言文案 = grep 式假绿，必须改判据。
#:
#: 运行方式（结果记入 evidence，不参与 `--run all`）:
#:     python -c "import runpy,sys; ..."  见 evidence/task11-artifact-retention/findings.md
CONTROLS: list[Mutation] = [
    Mutation(
        id="C01", side="be", path=LIMITS, kind="replace",
        anchor='                detail="压缩包体积超限；拒绝在解压前发生，避免无界展开",',
        new='                detail="unused",',
        want="*",
        why="只改预算超限的错误文案、不改行为。预期 GREEN —— 若判 RED 说明守卫在断言文案",
        tags=("selfcheck",),
    ),
    Mutation(
        id="C02", side="be", path=ARTIFACTS, kind="replace",
        anchor='#: definition store 的 kind → 子目录（design §Filesystem Layout）。',
        new="#: 注释改写（对照项：不改行为）",
        want="*",
        why="只改注释。预期 GREEN —— 若判 RED 说明守卫在读源码注释而不是行为",
        tags=("selfcheck",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 11 CanonicalArtifactRepository / OOXML 安全 / RetentionPolicy 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task11_artifact_repository.py",
                "backend/tests/workpaper_sync/test_task11_retention_orphan_pg.py",
                # 🔴 必须 `-rfE`：harness（module fixture）异常在 pytest 里是 ERROR 而不是
                # FAILED，只给 `-rf` 时短摘要不含 `ERROR ...` 行，runner 收不到失败名 ⇒
                # 整轮判 GREEN（Task 10 实测有 5 条因此被误判）。
                "-q", "--tb=no", "-rfE", "-p", "no:randomly",
            ],
            baseline_backend_passed=59,
        )
    )
