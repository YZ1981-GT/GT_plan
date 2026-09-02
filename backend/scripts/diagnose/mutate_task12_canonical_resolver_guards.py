# -*- coding: utf-8 -*-
"""Task 12 变异检验：统一 canonical resolver / definition-bundle store / candidate 隔离 /
resolver 迁移矩阵的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.3, 2.10, 6.2, 6.10, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.11, 9.12
Properties: P7 / P28 / P39 / P40 / P41 / P42

═══ 变异改的是**生产代码**，不是守卫 ═══

落点七处：

* `workpaper_sync/canonical_paths.py` —— 关掉 realpath 边界、把子码正则改回 A-only、
  把类型门短路、把两类异常合并成继承
* `workpaper_sync/definitions.py` —— 关掉 FC-1~FC-14 各条、拆掉 DAG 偏序、允许反向/
  自引用、让 alias 可用于历史读取、去掉 canonical 序列化的稳定性参数
* `workpaper_sync/resolution.py` —— 关掉历史意图 frozen 门、删 candidate 检查、
  让 sheet 隐藏对 published 放行、跳过 bundle digest 重算、关 scope 归属
* `workpaper_sync/artifacts.py` —— 不再委托统一边界判据（边界实现变两份）
* `wp_export/wp_file_resolver.py` —— 去掉边界/类型门、把窄 except 改回
  `except Exception`（fail-open）、把 ERROR 降级成 WARNING
* `wopi_service.py` / `wp_storage_service.py` —— 把统一入口改回自写 `Path(wp.file_path)`
  （检验「迁移是否真发生」）
* `scripts/gen/generate_workpaper_resolver_migration_matrix.py` —— 把「证据」判定退化成
  「声明」、缩小分母、漏收直接调用

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 本任务实测到的四条判据设计教训（已固化进守卫与生产代码）═══

1. **「类型不符」与「模板缺失」共用/继承同一异常类型会互相遮蔽**：二者都让调用方拿不到
   文件；合并后把 type 门短路掉，missing 分支抛同一类型 ⇒ GREEN。守卫显式断言
   `not issubclass(...)` 双向（M08）。
2. **模块级 residue 判据会逼守卫降标**：`if not version_dir.exists()`（目录检查）与
   `Path(wp.file_path).name`（取显示名）不是解析分叉；用模块级会误判，降标后真正的
   回退反而抓不到。故 residue 判据落在**函数级**（M48）。
3. **identity map 未 expire ⇒ WRONG-TEST**：真库测试里裸 SQL UPDATE 后不 `expire_all()`，
   `assert_candidate_finalizable` 读回旧 ORM 对象，「缺等值报告」实际测到的是「缺
   contract」——异常类型对、原因错。守卫因此断言到具体原因文本（M42）。
4. **多行 raise 不可被变异**：整行替换会破坏续行语法 ⇒ 文件级 collect ERROR ⇒ 判定
   退化成 WRONG-TEST。故 `resolve_for_history` / 相关禁令的 raise 都改成**单行**
   （文案提成模块常量），让禁令本身可被变异检验（M31）。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task12_canonical_resolver_guards.py --list
    python backend/scripts/diagnose/mutate_task12_canonical_resolver_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task12_canonical_resolver_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task12-canonical-resolver/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PATHS = "backend/app/services/workpaper_sync/canonical_paths.py"
DEFS = "backend/app/services/workpaper_sync/definitions.py"
RESOLVE = "backend/app/services/workpaper_sync/resolution.py"
ARTIFACTS = "backend/app/services/workpaper_sync/artifacts.py"
LEGACY = "backend/app/services/wp_export/wp_file_resolver.py"
EXPORT = "backend/app/services/wp_export/export_engine.py"
WOPI = "backend/app/services/wopi_service.py"
STORAGE = "backend/app/services/wp_storage_service.py"
MATRIX_GEN = "backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py"
MODELS = "backend/app/services/workpaper_sync/models.py"
#: 🔴 不能叫 `REPO` —— 本模块顶部已有 `REPO = Path(...)`（仓库根），同名会把它覆盖成
#: 字符串，`Mutation.abspath()` 里 `repo / self.path` 直接 TypeError（实测踩过）。
SYNC_REPO = "backend/app/services/workpaper_sync/repository.py"

#: 覆盖面分母：Task 12 新建的两个守卫文件。
GUARD_FILES = {
    "test_task12_canonical_resolver.py":
        "Task 12 新建：路径安全/子码最具体/类型 fail-closed/bundle canonicalizer/"
        "发布 DAG/意图策略/迁移矩阵守卫",
    "test_task12_resolution_pg.py":
        "Task 12 新建：真实 PG 的 Property 7 十意图同解、Property 28 两道门、"
        "candidate 隔离与 finalize gate、Property 42 DB 侧",
}

U = "test_task12_canonical_resolver"
PG = "test_task12_resolution_pg"

MUTATIONS: list[Mutation] = [
    # ══ 一、Property 42 路径安全 ═════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=PATHS, kind="replace",
        anchor="    if candidate != root_real and root_real not in candidate.parents:",
        new="    if False:",
        want=f"{U}.py::TestProperty42PathBoundary::test_traversal_rejected",
        wants=(
            f"{U}.py::TestProperty42PathBoundary::test_absolute_outside_rejected",
            f"{PG}.py::TestProperty42DbSidePathSafety::test_traversal_rejected",
        ),
        why="关掉边界比较 ⇒ 目录穿越/项目外绝对路径/软链接越界全部放行；"
            "Property 42 核心失效，artifacts.py 因委托它也一起破",
    ),
    Mutation(
        id="M02", side="be", path=PATHS, kind="replace",
        anchor="    candidate = Path(os.path.realpath(os.path.join(str(root_real), str(relative))))",
        new='    candidate = Path(str(root_real) + "/" + str(relative))',
        want=f"{U}.py::TestProperty42PathBoundary::test_symlink_escape_rejected",
        wants=(f"{U}.py::TestProperty42PathBoundary::test_traversal_rejected",),
        why="把候选路径的 realpath 换成字符串拼接 ⇒ `..` 与软链接都不再展开，"
            "退回「只做前缀比较」的旧写法（Task 7 fs7 证明拦不住）",
    ),
    Mutation(
        id="M03", side="be", path=PATHS, kind="replace",
        anchor='            reason="empty_relative_path", detail="relative_path 不得为空或纯空白"',
        new='            reason="outside_root", detail="relative_path 不得为空或纯空白"',
        want=f"{U}.py::TestProperty42PathBoundary::test_empty_relative_rejected",
        wants=(f"{PG}.py::TestProperty42DbSidePathSafety::test_empty_relative_path_rejected",),
        why="把空路径的 reason 改掉 ⇒ 「空串」与「越界」在诊断里无法区分，"
            "Requirement 5.12 要求的 error code 定位失效",
    ),
    Mutation(
        id="M04", side="be", path=PATHS, kind="replace",
        anchor="    if target != root_real and root_real not in target.parents:",
        new="    if False:",
        want=f"{U}.py::TestProperty42PathBoundary::test_cross_root_reuse_rejected",
        wants=(
            f"{U}.py::TestGuardSelfCheck::test_prefix_only_boundary_check_is_fooled_by_symlink",
            f"{PG}.py::TestProperty42DbSidePathSafety::test_cross_project_rejected",
        ),
        why="关掉「已是绝对路径」的归属判定 ⇒ 同一 relative_path 在别的 project 根下"
            "也能解析成功（Task 7 fs7 的跨项目复用反例）",
    ),

    # ══ 二、Property 40 子码最具体 ══════════════════════════════════════
    Mutation(
        id="M05", side="be", path=PATHS, kind="replace",
        anchor='_SUB_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]+\\d+-[0-9A-Za-z]")',
        new='_SUB_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^A\\d+-\\d+")',
        want=f"{U}.py::TestProperty40MostSpecificSubCode::test_sub_code_is_letter_class_agnostic",
        wants=(
            f"{U}.py::TestProperty40MostSpecificSubCode::test_parent_code_of",
            f"{U}.py::TestGuardSelfCheck::test_a_only_regex_misses_b_sub_codes",
        ),
        why="把子码判据改回 A-only（既有 wp_template_finder 的写法）⇒ B12-1/S33-REV "
            "被当主码，父级 XLSX 抢占子码 DOCX；正是 Requirement 9.4 点名的缺陷",
    ),
    Mutation(
        id="M06", side="be", path=PATHS, kind="replace",
        anchor="        return len(a)",
        new="        return len(a) + 2000",
        want=f"{U}.py::TestProperty40MostSpecificSubCode::test_specificity_rank_orders_exact_above_parent",
        wants=(
            f"{U}.py::TestProperty40MostSpecificSubCode::test_sub_code_docx_wins_over_parent_xlsx",
            f"{U}.py::TestProperty40MostSpecificSubCode::test_exact_code_wins_over_parent_same_type",
        ),
        why="把父码的具体度抬到精确匹配之上 ⇒ 父级候选反过来抢占子码候选",
    ),

    # ══ 三、Property 41 异类型 fail closed ══════════════════════════════
    Mutation(
        id="M07", side="be", path=PATHS, kind="replace",
        anchor="    if observed != expected:",
        new="    if False:",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_assert_document_type_rejects_xlsm_for_docx",
        wants=(
            f"{U}.py::TestProperty41NoCrossTypeFallback::test_legacy_resolver_type_gate_is_wired",
            f"{PG}.py::TestProperty42DbSidePathSafety::test_document_type_mismatch_rejected",
        ),
        why="关掉类型门 ⇒ 需要 docx 时拿到 xlsx 也放行，`Document(xlsx)` 导出损坏",
    ),
    Mutation(
        id="M08", side="be", path=PATHS, kind="replace",
        anchor="class TemplateMissingError(SyncDomainError):",
        new="class TemplateMissingError(DocumentTypeMismatchError):",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_missing_and_mismatch_are_distinct_types",
        why="把两类异常做成继承关系 ⇒ 「拒绝异类型回退」会被「缺模板」遮蔽，"
            "Requirement 9.4 与 9.5 无法各自验证（本任务实测到的遮蔽形态）",
    ),
    Mutation(
        id="M09", side="be", path=PATHS, kind="replace",
        anchor="        if applicable:",
        new="        if False:",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_only_parent_xlsx_raises_type_mismatch",
        why="删掉「有异类型候选但无同类型候选」分支 ⇒ 父级 XLSX 场景退化成 "
            "TemplateMissingError，两条 Requirement 的语义被合并",
    ),
    Mutation(
        id="M10", side="be", path=LEGACY, kind="replace",
        anchor="        if expected_document_type is not None and (",
        new="        if False and (",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_legacy_resolver_type_gate_is_wired",
        why="legacy resolver 的类型门被短路 ⇒ `type_mismatch` 档不可达，"
            "异类型文件被当成命中返回",
    ),
    Mutation(
        id="M11", side="be", path=EXPORT, kind="replace",
        anchor='            file_path, wp_code=wp_code, expected_document_type="docx"',
        new="            file_path, wp_code=wp_code",
        want=f"{U}.py::TestProperty41NoCrossTypeFallback::test_export_engine_declares_docx_type",
        why="把 P41 的**真实消费方**改回不声明类型 ⇒ 新能力变成 additive 死代码"
            "（假绿第①源）",
    ),

    # ══ 四、legacy resolver 的边界门与 fail-open ═════════════════════════
    Mutation(
        id="M12", side="be", path=LEGACY, kind="replace",
        anchor="        if not is_within_any_legacy_root(candidate):",
        new="        if False:",
        want=f"{U}.py::TestPathBoundaryHasSingleImplementation::test_legacy_resolver_uses_boundary_gate",
        wants=(
            f"{U}.py::TestLegacyResolverBoundaryVerdicts::test_out_of_root_absolute_is_path_rejected",
        ),
        why="关掉 legacy 路径的边界门 ⇒ `/tmp/xxx.xlsx` 这类历史脏数据与项目外绝对"
            "路径被当成合法底稿读出去（download/WOPI/storage 三条链一起破）",
    ),
    Mutation(
        id="M13", side="be", path=LEGACY, kind="replace",
        anchor="    except (OSError, ValueError, KeyError, TypeError) as err:",
        new="    except Exception as err:  # noqa: BLE001",
        want=f"{U}.py::TestLegacyResolverBoundaryVerdicts::test_template_fallback_has_no_blanket_except",
        why="把窄 except 改回 `except Exception` ⇒ 函数名写错/索引结构变了都被吞成"
            "「该 wp_code 无模板」；memory 记的「最贵的一类」fail-open",
    ),
    Mutation(
        id="M14", side="be", path=LEGACY, kind="replace",
        anchor="        logger.error(",
        scope='            "resolve_wp_file: 模板库模块不可导入 wp_code=%s: %s（部署缺件，非「无模板」）",',
        offset=-1,
        new="        logger.warning(",
        want=f"{U}.py::TestLegacyResolverBoundaryVerdicts::test_template_fallback_has_no_blanket_except",
        why="把 fail-open 诊断从 ERROR 降级成 WARNING ⇒ 「模板库不可导入」在日志里"
            "看不见，表现为「该底稿没有模板」。守卫因此要求整个函数零 WARNING 出口",
    ),

    # ══ 五、Property 28 bundle canonicalizer（FC-1 ~ FC-14）══════════════
    Mutation(
        id="M15", side="be", path=DEFS, kind="replace",
        anchor="    missing = [s.value for s in BundleSlot if s not in keyed]",
        new="    missing = []",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc1_slot_omission",
        why="关掉 slot omission 检查（FC-1）⇒ 少一个 typed slot 也能进 canonical bytes",
    ),
    Mutation(
        id="M16", side="be", path=DEFS, kind="replace",
        anchor="    if raw is None:",
        new="    if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc2_sql_null_slot",
        why="关掉 SQL NULL slot 检查（FC-2）",
    ),
    Mutation(
        id="M17", side="be", path=DEFS, kind="replace",
        anchor="            if raw[key] is None:",
        new="            if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc3_json_null_field",
        why="关掉 JSON null 字段检查（FC-3）—— 与 FC-2 是两条独立判据，"
            "只测一条时删另一条入口不会红",
    ),
    Mutation(
        id="M18", side="be", path=MODELS, kind="replace",
        anchor="    if spec.slot_type is None or not str(spec.slot_type).strip():",
        new="    if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc4_empty_string_field",
        why="关掉空串/纯空白 slot 字段检查（FC-4）。锚点落在 "
            "`models.validate_bundle_slot`（唯一实现）—— `definitions` 侧的重合副本已删除",
    ),
    Mutation(
        id="M19", side="be", path=DEFS, kind="replace",
        anchor="    if str(spec.slot_digest).strip() == _ALL_ZERO_DIGEST:",
        new="    if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc5_all_zero_digest",
        wants=(f"{U}.py::TestBundleCanonicalBytes::test_canonical_bytes_have_no_forbidden_tokens",),
        why="关掉全零 hash 检查（FC-5）⇒ 「忘了算 hash 就填 0」的伪身份进 canonical bytes",
    ),
    Mutation(
        id="M20", side="be", path=MODELS, kind="replace",
        anchor="    if not is_digest(spec.slot_digest):",
        new="    if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc6_malformed_digest",
        why="关掉 digest 形态检查（FC-6）⇒ 大写 hex / 长度不符也放行。"
            "🔴 锚点落在 `models.validate_bundle_slot`（唯一实现）：改造前 "
            "`definitions._normalize_slot_input` 自带一份重合副本，短路任一侧都不改行为 "
            "⇒ 首轮变异实测 GREEN。已删掉副本、改为委托",
    ),
    Mutation(
        id="M21", side="be", path=DEFS, kind="replace",
        anchor="    marker = TYPED_NULL_MARKERS.get(spec.slot_type)",
        new="    marker = TYPED_NULL_MARKERS.get(spec.slot_type) or TypedNullMarker("
            "slot=slot, version=1, slot_type=spec.slot_type, slot_ref=spec.slot_ref, "
            "slot_digest=spec.slot_digest)",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc7_unregistered_marker",
        wants=(
            f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc8_cross_slot_marker",
            f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc9_marker_digest_mismatch",
        ),
        why="让未登记 marker 自动「登记」⇒ registry 失去唯一性，任意 `xxx:none:vN` 都合法",
    ),
    Mutation(
        id="M22", side="be", path=MODELS, kind="replace",
        anchor="        if not _DEFINITION_REF_RE.match(spec.slot_ref):",
        new="        if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc10_malformed_definition_ref",
        why="关掉 `definition:<uuid>` ref 形态检查（FC-10）。同 M20：锚点必须落在唯一"
            "实现上，`definitions` 侧的重合副本已删除",
    ),
    Mutation(
        id="M23", side="be", path=MODELS, kind="replace",
        anchor="    if not is_digest(authority_model_definition_sha256):",
        new="    if False:",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc13_invalid_authority_digest",
        why="关掉 authority model digest 检查（FC-13）。`definitions.normalize_authority_digest` "
            "现在只做 NULL 判定 + 归一，形态判据单点在此",
    ),
    Mutation(
        id="M24", side="be", path=DEFS, kind="replace",
        anchor="        return value if isinstance(value, AuthorityModel) else AuthorityModel(value)",
        new="        return AuthorityModel.projection_contract",
        want=f"{U}.py::TestProperty28BundleCanonicalizerFailClosed::test_fc14_unknown_authority_model",
        why="把未登记枚举静默当成 projection_contract（FC-14）⇒ 自由文本 authority "
            "model 被接受，custom/opaque 的 marker 规则同时失效",
    ),
    Mutation(
        id="M25", side="be", path=DEFS, kind="replace",
        anchor='        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False',
        new="        payload, ensure_ascii=False",
        want=f"{U}.py::TestBundleCanonicalBytes::test_marker_digest_matches_v151_seed_bytes",
        wants=(
            f"{U}.py::TestBundleCanonicalBytes::test_key_order_perturbation_is_stable",
            f"{U}.py::TestBundleCanonicalBytes::test_canonical_json_rejects_nan",
        ),
        why="去掉 sort_keys/separators/allow_nan ⇒ canonical bytes 不再对键序稳定，"
            "marker digest 与 V151 seed 不一致，DB trigger 与服务层互相打红",
    ),

    # ══ 六、发布 DAG 与反向/自引用 ═══════════════════════════════════════
    Mutation(
        id="M26", side="be", path=DEFS, kind="replace",
        anchor="    PublishStage.contract: (PublishStage.template, PublishStage.instrumentation),",
        new="    PublishStage.contract: (),",
        want=f"{U}.py::TestPublishDag::test_contract_requires_template_and_instrumentation",
        wants=(f"{U}.py::TestPublishDag::test_prerequisites_are_monotone",),
        why="拆掉 contract 的前置 ⇒ 可以先发 contract 再发 template/instrumentation，"
            "DAG 固定顺序失效",
    ),
    Mutation(
        id="M27", side="be", path=DEFS, kind="replace",
        anchor="    if missing:",
        scope="    missing = [p.value for p in PUBLISH_PREREQUISITES[st] if p not in approved]",
        offset=1,
        new="    if False:",
        want=f"{U}.py::TestPublishDag::test_contract_requires_template_and_instrumentation",
        wants=(f"{U}.py::TestPublishDag::test_bundle_requires_all_three",),
        why="关掉阶段偏序断言本体（`assert_publish_order` 的 raise 分支）",
    ),
    Mutation(
        id="M28", side="be", path=DEFS, kind="replace",
        anchor="        k for k in keys if k.startswith(_BACKWARD_REFERENCE_PREFIXES)",
        new="        k for k in [] if k.startswith(_BACKWARD_REFERENCE_PREFIXES)",
        want=f"{U}.py::TestPublishDag::test_instrumentation_payload_rejects_backward_reference",
        wants=(f"{U}.py::TestPublishDag::test_instrumentation_payload_rejects_bundle_reference",),
        why="关掉 payload 级反向引用禁令 ⇒ instrumentation 可以引用 contract/bundle "
            "digest；只有阶段偏序时这条能被「先发 contract」绕过（两条判据缺一不可）",
    ),
    Mutation(
        id="M29", side="be", path=DEFS, kind="replace",
        anchor="    hit = sorted(set(_walk_keys(payload)) & _SELF_REFERENCE_KEYS)",
        new="    hit = []",
        want=f"{U}.py::TestPublishDag::test_payload_rejects_self_reference",
        why="关掉自引用禁令 ⇒ canonical payload 内嵌自身 UUID/hash，"
            "「同语义→同 digest」这条前提崩掉（Requirement 6.2）",
    ),
    Mutation(
        id="M30", side="be", path=DEFS, kind="replace",
        anchor="        raise AliasResolutionForbiddenError(_ALIAS_HISTORY_FORBIDDEN.format(alias=alias))",
        new="        return self.resolve_for_publish(alias)",
        want=f"{U}.py::TestAliasNeverUsedForHistory::test_history_resolution_always_raises",
        why="让历史读取可以按 alias 解析 ⇒ 同一历史 operation 重跑得到不同 bundle"
            "（Requirement 2.10 后半句失效）",
    ),

    # ══ 七、Property 7 / 39 意图策略与 resolver 主流程 ═══════════════════
    Mutation(
        id="M31", side="be", path=RESOLVE, kind="replace",
        anchor="    ResolutionIntent.retry: IntentPolicy(False, True, False),",
        new="    ResolutionIntent.retry: IntentPolicy(True, False, False),",
        want=f"{U}.py::TestProperty7SingleResolverEntry::test_historical_intents_require_frozen_identity",
        wants=(
            f"{PG}.py::TestHistoricalReadsUseFrozenBundle::test_historical_intents_reject_missing_frozen_identity",
        ),
        why="让 retry 可以按 entry current pointer 解析 ⇒ 历史 retry 读到当前 bundle，"
            "Property 28「旧 operation 仍固定原 bundle」失效",
    ),
    Mutation(
        id="M32", side="be", path=RESOLVE, kind="replace",
        anchor="    ResolutionIntent.config: IntentPolicy(True, False, False),",
        new="    ResolutionIntent.config: IntentPolicy(True, False, True),",
        want=f"{U}.py::TestProperty39ConfigCallbackSameSource::test_neither_config_nor_callback_may_hide_sheets",
        wants=(
            f"{U}.py::TestProperty7SingleResolverEntry::test_only_materialize_may_hide_sheets",
            f"{U}.py::TestSheetVisibilityGate::test_config_intent_is_forbidden",
        ),
        why="让 config 也能改 sheet 可见性 ⇒ Requirement 9.12「只作用于 room/staged "
            "representation」失效，openpyxl 会原地改共享 current artifact",
    ),
    Mutation(
        id="M33", side="be", path=RESOLVE, kind="replace",
        anchor="        if s is not ArtifactState.staged:",
        new="        if False:",
        want=f"{U}.py::TestSheetVisibilityGate::test_published_current_artifact_is_forbidden",
        why="关掉 staged 限制 ⇒ 对 published current artifact 原地隐藏 sheet",
    ),
    Mutation(
        id="M34", side="be", path=RESOLVE, kind="replace",
        anchor="        if policy.requires_frozen_identity and representation_id is None:",
        new="        if False:",
        want=f"{PG}.py::TestHistoricalReadsUseFrozenBundle::test_historical_intents_reject_missing_frozen_identity",
        why="关掉历史意图的 frozen identity 门（服务层本体）",
    ),
    Mutation(
        id="M35", side="be", path=RESOLVE, kind="replace",
        anchor="        if representation_id is not None:",
        new="        if False:",
        want=f"{PG}.py::TestCandidateIsolation::test_candidate_id_as_representation_is_rejected",
        why="删掉 candidate 显式拒绝 ⇒ 拿 candidate id 当 representation_id 会一路走到"
            "模糊报错，Requirement 5.12 的 error code 定位失效",
    ),
    Mutation(
        id="M36", side="be", path=RESOLVE, kind="replace",
        anchor='        if recomputed != (bundle.canonical_payload_sha256 or "").strip():',
        new="        if False:",
        want=f"{PG}.py::TestProperty28FailClosedOnDrift::test_service_rejects_insert_time_digest_mismatch",
        why="跳过 canonical digest 重算 ⇒ 「插入时 digest 就与 typed slots 不符」"
            "这条只有服务层能拦的门失效（DB trigger 只拦 approved 后的 UPDATE）",
    ),
    Mutation(
        id="M37", side="be", path=RESOLVE, kind="replace",
        anchor="        if bundle.state != DefinitionState.approved.value:",
        new="        if False:",
        want=f"{PG}.py::TestProperty28FailClosedOnDrift::test_unapproved_bundle_is_not_loadable",
        why="让 candidate 态 bundle 可被 resolver 加载 ⇒ unapproved bundle 进 room",
    ),
    Mutation(
        id="M38", side="be", path=RESOLVE, kind="replace",
        anchor="            if child.state != DefinitionState.approved.value:",
        new="            if False:",
        want=f"{PG}.py::TestProperty28FailClosedOnDrift::test_retired_contract_child_invalidates_bundle",
        why="让 retired 的 contract child 仍算合法 ⇒ definition 漂移后旧 bundle 不再 fail closed",
    ),
    Mutation(
        id="M39", side="be", path=RESOLVE, kind="replace",
        anchor="        if rep.wp_id != wp_id or rep.entry_id != entry_id:",
        new="        if False:",
        want=f"{PG}.py::TestProperty42DbSidePathSafety::test_cross_scope_rejected",
        why="关掉 scope 归属校验 ⇒ 用别的 wp/entry 的 id 能解析到本 representation"
            "（横向越权）",
    ),
    Mutation(
        id="M40", side="be", path=RESOLVE, kind="replace",
        anchor="        if cand.target_contract_definition_id is None:",
        new="        if False:",
        want=f"{PG}.py::TestCandidateIsolation::test_finalize_requires_approved_contract",
        why="关掉 candidate finalize 的 approved contract 前置 ⇒ 无 per-entry contract "
            "也能 finalize 成 published representation（Requirement 6.18）",
    ),
    Mutation(
        id="M41", side="be", path=RESOLVE, kind="replace",
        anchor='        if not is_digest(cand.visible_equivalence_report_sha256 or ""):',
        new="        if False:",
        want=f"{PG}.py::TestCandidateIsolation::test_finalize_requires_equivalence_report",
        why="关掉 visible-equivalence 报告前置 ⇒ compatibility 未通过也能 finalize"
            "（Requirement 9.10）",
    ),
    Mutation(
        id="M42", side="be", path=RESOLVE, kind="replace",
        anchor="        raise CandidateNotResolvableError(_CANDIDATE_NOT_CONSUMABLE.format(cid=candidate_id, intent=it.value))",
        new="        return None",
        want=f"{PG}.py::TestCandidateIsolation::test_candidate_not_consumable_for_every_intent",
        why="把 `assert_candidate_not_consumable` 的恒抛禁令改成静默通过 ⇒ candidate "
            "可被 resolver/room/evidence 消费（禁令必须有可执行判据）",
    ),

    # ══ 八、迁移矩阵：证据退化成声明 ═════════════════════════════════════
    Mutation(
        id="M43", side="be", path=MATRIX_GEN, kind="replace",
        anchor="    if not evidence_ok or residue:",
        new="    if False:",
        want=f"{U}.py::TestResolverMigrationMatrix::test_status_derivation_truth_table",
        why="把「意图 ∧ 证据」退化成「意图」⇒ 手写 migrated 就永远绿，"
            "任务书要求的「旧调用点已真的指向统一入口」失去判据（假绿第②源）。"
            "🔴 判定已抽成纯函数 `derive_status` 并由真值表守卫锁死：内联在 "
            "`build_matrix` 时，因当前矩阵零 regressed 行，短路后输出不变 ⇒ 首轮实测 GREEN",
    ),
    Mutation(
        id="M44", side="be", path=MATRIX_GEN, kind="replace",
        anchor="            out.add(fn.id)",
        new="            pass",
        want=f"{U}.py::TestGuardSelfCheck::test_called_names_ignores_import_only",
        wants=(f"{U}.py::TestResolverMigrationMatrix::test_matrix_is_fresh",),
        why="让「直接函数调用」不再被收集 ⇒ 迁移证据只剩属性调用，"
            "`resolve_wp_file(...)` 这种直接调用形态漏判",
    ),
    Mutation(
        id="M45", side="be", path=MATRIX_GEN, kind="replace",
        anchor="        if is_resolver_fork(entry)",
        new="        if False",
        want=f"{U}.py::TestResolverMigrationMatrix::test_denominator_matches_inventory",
        wants=(f"{U}.py::TestResolverMigrationMatrix::test_matrix_is_fresh",),
        why="把分母从「Task 3 清册的全部 resolver 分叉」缩成「POLICY 点名模块」⇒ "
            "少登记一行就能蒙过去（分母必须由清册决定）",
    ),

    # ══ 九、存量分叉回退（迁移是否真发生）═══════════════════════════════
    Mutation(
        id="M46", side="be", path=WOPI, kind="replace",
        anchor="        fp = _resolve_put_target(file_id, wp.file_path)",
        new="        fp = Path(wp.file_path)",
        want=f"{U}.py::TestResolverMigrationMatrix::test_matrix_is_fresh",
        wants=(
            f"{U}.py::TestResolverMigrationMatrix::test_task12_named_forks_are_migrated",
            f"{U}.py::TestResolverMigrationMatrix::test_migrated_functions_have_no_self_written_markers",
        ),
        why="把 WOPI 写入目标改回自写 `Path(wp.file_path)` ⇒ put_file 的函数级 residue "
            "出现 raw_file_path_construction，矩阵该行必须变 regressed",
    ),
    Mutation(
        id="M47", side="be", path=STORAGE, kind="replace",
        anchor="        file_path = resolution.path",
        scope='            return {"error": resolution.reason, "verdict": resolution.verdict}',
        offset=1,
        new="        file_path = Path(wp.file_path)",
        want=f"{U}.py::TestResolverMigrationMatrix::test_matrix_is_fresh",
        wants=(
            f"{U}.py::TestResolverMigrationMatrix::test_task12_named_forks_are_migrated",
            f"{U}.py::TestResolverMigrationMatrix::test_migrated_functions_have_no_self_written_markers",
        ),
        why="把 storage/version 分叉改回自写 `Path(wp.file_path)` ⇒ save_version 的函数级 "
            "residue 判据必须打红（这正是「迁移是否真发生」的核心判据）",
    ),
    Mutation(
        id="M48", side="be", path=ARTIFACTS, kind="replace",
        anchor="            return resolve_within_root(root, relative, boundary=boundary)",
        new="            return Path(os.path.join(str(root), str(relative)))",
        want=f"{U}.py::TestPathBoundaryHasSingleImplementation::test_artifacts_delegates_to_canonical_paths",
        wants=(f"{PG}.py::TestProperty42DbSidePathSafety::test_traversal_rejected",),
        why="让 artifacts.py 不再委托统一边界判据 ⇒ 边界实现又变两份"
            "（改一处另一处不红）",
    ),

    # ══ 十、真实模板库上的 P40/P41（收口补录）═════════════════════════════
    #
    # 补录理由：M05~M11 的判据全部建立在 monkeypatch 过的 tmp 模板根上，证明的是
    # 「判据函数正确」。真实库上的行为（`find_template_file_any("B12-1")` 返回父级
    # `B12 ….xlsx`）此前没有任何判据，于是 Task 12 交付的类型安全包装
    # `resolve_template_docx` 可以整个是死代码而 Property 40/41 照样全绿。
    Mutation(
        id="M49", side="be", path=LEGACY, kind="replace",
        anchor='        expected_document_type="docx",',
        new="        expected_document_type=None,",
        want=f"{U}.py::TestProperty40And41OnRealTemplateLibrary::test_resolve_template_docx_rejects_parent_xlsx",
        why="拿掉 `resolve_template_docx` 的类型门 ⇒ 真实库里 B12-1 直接解析到父级 "
            "`B12 与相关人员访谈程序及记录.xlsx`，被 `Document()` 当 docx 打开 ⇒ "
            "导出损坏（Requirement 9.4/9.5 的原始反例）",
    ),
    Mutation(
        id="M50", side="be", path=LEGACY, kind="replace",
        anchor="        blank=False,",
        scope="        raw=None,",
        offset=2,
        new="        blank=True,",
        want=f"{U}.py::TestProperty40And41OnRealTemplateLibrary::test_absent_code_is_missing_not_empty",
        why="把模板专用入口的终态从 `missing` 退回 `empty` ⇒ 「模板缺失（部署缺件）」"
            "在裁决清册里显示成「未配置底稿文件路径」，Requirement 9.5 要求的显式报错"
            "指错了成因。锚点用 scope 相对定位：`blank=False,` 在本文件出现两次",
    ),

    # ══ 十一、finalize 只增不改（Task 12 第 3 条后半句）══════════════════
    Mutation(
        id="M51", side="be", path=SYNC_REPO, kind="replace",
        anchor="        cand.finalized_at = _now()",
        new='        cand.finalized_at = _now(); await self._session.execute(sa.text('
            '"UPDATE working_paper SET content_revision = content_revision + 1 '
            'WHERE id = :w"), {"w": str(cand.wp_id)})',
        want=f"{PG}.py::TestCandidateFinalizeIsAdditiveOnly::test_finalize_is_additive_only",
        why="让 finalize 顺手推进 business content revision ⇒ Requirement 9.10"
            "「纯 representation 升级不得递增 content revision」失效。"
            "🔴 这条变异是**注入**而不是短路：finalize 里本来没有任何改旧行的语句，"
            "「不改」这类否定式承诺只能靠注入反例来证明判据可falsify",
    ),
    Mutation(
        id="M52", side="be", path=SYNC_REPO, kind="replace",
        anchor="        cand.finalized_representation_id = finalized_representation_id",
        new="        cand.finalized_representation_id = None",
        want=f"{PG}.py::TestCandidateFinalizeIsAdditiveOnly::test_finalize_creates_new_generation_and_binds_candidate",
        wants=(
            f"{PG}.py::TestCandidateFinalizeIsAdditiveOnly::test_finalize_succeeded",
        ),
        why="finalize 不再把 candidate 绑到新建的 representation ⇒ 命中 DB 的 "
            "`ck_wpruc_finalized_pointer`（state=finalized 必须有 pointer），"
            "整段 finalize 回滚、新 generation 不落库；证明「新增一行 + 绑定」这条"
            "判据不是恒真的空转",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task12_canonical_resolver.py",
            "backend/tests/workpaper_sync/test_task12_resolution_pg.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider",
        ],
        # 冻结基线来源：2026-08-25 收口实测（仓库根、`.venv` 解释器）
        #   test_task12_canonical_resolver.py  99 passed
        #   test_task12_resolution_pg.py       37 passed
        # 首轮登记的 126 是补录 M49~M52 对应的 9 条守卫之前的数字。
        baseline_backend_passed=136,
    ))
