# -*- coding: utf-8 -*-
"""stable-field 三方 merge 域（Task 14）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 14
Requirements 6.6 / 6.7 / 6.8 / 6.9 / 7.4 / 8.1 / 8.5
Properties P24（保护字段冲突）/ P25（不同字段自动合并）/ P26（同字段异值必冲突）/
P27（delete-update 不整表覆盖）/ P32（Word 多实例异值）/ P35（冲突双侧可追溯）

## 边界：纯域，零载体、零 IO

本模块**不 import** openpyxl / python-docx / sqlalchemy / repository / outbox。
输入是 Task 13 的 :class:`~app.services.workpaper_sync.adapters.base.Projection`
（按 stable field key 索引）与 :class:`~app.services.workpaper_sync.contracts.SyncContract`，
输出是 :class:`MergeOutcome`。Word 特性只体现为契约已表达的**形态**
（`sdt_tag`、`{row_uuid}`、`instances: many`），不做任何真实 DOCX 解析。

## 三方真值表（design §Merge Algorithm 原文 + MISSING 扩展）

``b/c/i`` = base / current / incoming 的**值信封**（:class:`ValueEnvelope`，
absent 与 present-but-null 不折叠）。判据从上到下短路：

===  ==============================================  ==========================  ===================
序   条件                                            结果                        verdict
===  ==============================================  ==========================  ===================
0    所属行/键被结构冲突封锁                          merged = c（fail closed）    held_by_schema_conflict
1    所属行处于 delete-update 冲突                    merged = c（整行 hold）      held_by_row_conflict
2    mode = word_only                                merged = i or c，不进 HTML   word_only
3    非行域字段在 incoming 缺失                       schema 冲突（载体消失）      conflict_schema
4    protected 且 b/i 都在且 i ≠ b                    protected 冲突               conflict_protected
5    i == b                                          merged = c（OO 未改）        kept_current
6    c == b                                          merged = i（仅 OO 改）       took_incoming
7    c == i                                          merged = c（两侧同改）       both_sides_agree
8    b 在且 c/i 恰一侧缺失                            delete_update 冲突           conflict_delete_update
9    其余                                            value 冲突                   conflict_value
===  ==============================================  ==========================  ===================

**永不 last-write-wins**：第 8/9 行不选边，merged 保持 c 并把三值原样写入冲突记录，
由人工裁决（:func:`apply_resolutions`）收敛。

## MISSING 为什么必须是独立哨兵

「字段不存在」与「字段被显式清空」是两种输入：

* ``b=X, c=X, i=MISSING`` → 行/载体被删除 ⇒ merged 也缺失
* ``b=X, c=X, i=None``    → 用户在 OO 里清空了这个格 ⇒ merged 是显式 null

若把 MISSING 折叠成 ``None``，两者结果相同，「删除」与「清空」在 HTML projection、
回滚与审计轨迹里再也分不开。:data:`MISSING` 因此是**独立单例**：与 ``None``、``""``、
``0``、``False`` 都不相等，:func:`normalize_value` 对它恒等返回，
:func:`values_equal` 只在两侧同为 MISSING 时判等。
`TestMissingSentinel` 逐条锁死这些方向，变异脚本 M20/M21 用**注入折叠**证明可 falsify。

## 类型规范化只用于比较，不改写值

design 原文：「值比较先按类型规范化：金额 Decimal、日期 ISO、字符串仅规范化 OO 非语义
控制字符，不 trim 用户有意义空格；空值与 0 严格区分。」

因此 :func:`normalize_value` 返回的是**比较键**，merged projection 里存的仍是胜出那一侧
的原值（不会把用户填的 ``"1,234.50"`` 改写成 ``Decimal('1234.5')``）。会规范化的只有：

* `amount` / `rate` / `ratio` → `Decimal`（``"1234.50"`` == ``1234.5`` == ``Decimal("1234.5")``）
* `integer` → `int`（整值 float 也接受；**bool 拒绝**，`True` 不等于 `1`）
* `date` / `datetime` → `date` / `datetime`（ISO 串与对象等价；两者互相**不**等价）
* `boolean` → `bool`（只接受真 bool 与 ``"true"``/``"false"``；`0/1` 拒绝）
* `text` → CRLF/CR 归一为 LF、去 BOM(U+FEFF)。**不** trim、**不**折叠空白、
  NBSP(U+00A0) 与普通空格**不**等价
* `json` → canonical bytes（键序无关）
* `enum` → 原样精确比较（不做大小写折叠）

不可规范化的输入不静默放过，也不静默相等：抛
:class:`ValueNormalizationError` → 由 merge 收成 `schema` 冲突并**保留原值供裁决**
（design §Extract）。这是窄类型捕获 + 记录 error 文案，不是 `except Exception` 降级。

## 生产消费方：Task 15 已接线（原延后登记已退役）

merge 域曾经零生产消费方，:data:`DEFERRED_CONSUMERS` 把这条欠账登记成可验证的延后
（`blocking_task="15,26"`）。**Task 15 落地后该登记已退役**并移入
:data:`RETIRED_DEFERRALS`：唯一消费方是
`app/services/workpaper_sync/content_mutation.py` 的 `ContentMutationService.commit(...)`，
它消费 :class:`MergeOutcome`（拒绝未裁决冲突、按 `requires_client_refresh` 决定
client-confirmed 基线）并复用 :func:`values_equal` 做 roundtrip 反读等值判据。

`TestTask14ScopeBoundary` 的边界判据随之**翻转而不是删除**：从「零消费方」变成
「恰一个消费方，且正是那个模块」。多一个消费方（有人绕过唯一 commit 入口）或零消费方
（有人把接线删了、能力退回死代码）都打红。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.conflicts import (
    ConflictKind,
    ConflictRecord,
    ConflictSet,
    FieldLocator,
    FieldSource,
    MergeDomainError,
    ProtectionPolicy,
    ResolutionChoice,
    SchemaAnomalyKind,
    SuggestedAction,
    ValueEnvelope,
    WordInstanceRef,
    assert_all_conflicts_resolved,
    resolved_value_for,
)
from app.services.workpaper_sync.contracts import (
    PROTECTED_MODES,
    ROW_UUID_PLACEHOLDER,
    FieldMode,
    FieldSpec,
    SyncContract,
    ValueType,
    column_in_ranges,
)
from app.services.workpaper_sync.definitions import canonical_json_bytes

# ═══════════════════════════════════════════════════════════════════════════
# 0. 未接线消费方登记（Task 13 的 protocol-type 延后同款）
# ═══════════════════════════════════════════════════════════════════════════

#: 本模块新增能力的**唯一**延后登记。字段与
#: `backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py` 的 POLICY
#: 同构（`intended_status` / `blocking_task` / `reason`），便于后续收口任务机器核对。
#: 🔴 **当前为空**：Task 37 还清了 Excel 侧、Task 59 还清了 Word 侧
#: （`WordInstanceObservation` / Word 侧 `StructuralAnomaly` 输入形态，见
#: `RETIRED_DEFERRALS` 的 Task 59 条目）。空元组**不是**「登记表被删了」，且这句话
#: 不是自我声明 —— `TestTask14ScopeBoundary` 用**三条**断言把「合法的空」与
#: 「被删的空」分开：
#:
#: 1. `test_deferred_consumers_registration_is_complete`：本表为空时，
#:    `RETIRED_DEFERRALS` 必须非空**且** merge 域必须真有生产消费方；
#: 2. `test_retired_deferral_records_who_wired_it`：退役登记逐条完整，且
#:    `expected_consumer_module` 指向的文件真的存在；
#: 3. `test_merge_domain_consumers_match_the_retirement_registry_exactly`：
#:    实测消费方集合与退役登记**双向等值**（多一个＝有人绕过唯一 commit 入口，
#:    少一个＝登记与事实脱钩）。
DEFERRED_CONSUMERS: Final[tuple[Mapping[str, Any], ...]] = ()

#: **已退役**的延后登记。退役不等于删除：这里保留「谁在什么时候接线、接到哪」的可核对
#: 记录，让边界判据从「零消费方」平滑翻转成「恰一个消费方且是那个模块」，而不是把
#: 判据整段删掉（删掉之后没人能证明当初的欠账真的被还了）。
#:
#: `expected_consumer_module` 是仓库相对路径，`TestTask14ScopeBoundary` 用它做**唯一**
#: 消费方的期望值：接线出现在别的模块 ⇒ 打红（有人绕过唯一 commit 入口）。
RETIRED_DEFERRALS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "capability": "merge_projections / MergeOutcome",
        "intended_status": "retired",
        "retired_by_task": "15",
        "consumer": "ContentMutationService.commit(...)",
        "expected_consumer_module": "app/services/workpaper_sync/content_mutation.py",
        "commits_through": None,
        "reason": (
            "Task 15 落地了唯一 `ContentMutationService.commit(...)`：它在一次 "
            "lock/expected revision 里消费 MergeOutcome（拒绝未裁决冲突、按 "
            "`requires_client_refresh` 决定 client-confirmed 基线是否推进）并用 "
            "`values_equal` 做 roundtrip 反读等值判据。它是**唯一** commit 边界，"
            "任何跑 merge 的编排层都必须经由它落库。"
        ),
    },
    {
        "capability": "merge_projections 调用点（OO→HTML 三方 merge 编排）",
        "intended_status": "retired",
        "retired_by_task": "26",
        "consumer": "OoToHtmlCoordinator.apply_durable_incoming(...)",
        "expected_consumer_module": "app/services/workpaper_sync/oo_to_html.py",
        # 🔴 这一列是本条登记的核心：编排层允许**跑** merge，但它自己不 commit ——
        # 必须经由下面这个模块落库。守卫按这一列反查该模块真的被 import。
        "commits_through": "app/services/workpaper_sync/content_mutation.py",
        "reason": (
            "Task 15 的 `BusinessMutation` 明文写着「本模块不重跑 merge —— 那是 "
            "Task 26 coordinator 的活；这里只消费它的结论」，design §Module Layout 也把 "
            "`coordinator.py` 列为 OO→HTML 编排方。所以 `merge_projections` 的**调用点**"
            "在 Task 26 落地后必然出现在编排层：三方投影（frozen base / current "
            "published / durable incoming）只有 coordinator 拿得到。"
            "边界没有被放宽 —— 编排层不含任何 commit 面，它把 `MergeOutcome` 交给 "
            "`ContentMutationService.commit(...)` 落库（见 `commits_through`）。"
        ),
    },
    {
        "capability": "evaluate_resolve_fence / apply_resolutions",
        "intended_status": "retired",
        "retired_by_task": "27",
        "consumer": "ConflictResolutionService.resolve(...) / .preview(...) / .rollback(...)",
        "expected_consumer_module": "app/services/workpaper_sync/conflict_resolution.py",
        # 🔴 resolve 不自建 rematerialize：fence 通过后它把裁决交给 Task 26 的
        #    coordinator，coordinator 再经由下面这个唯一 commit 边界落库。
        "commits_through": "app/services/workpaper_sync/content_mutation.py",
        "reason": (
            "Task 27 落地 `ConflictResolutionService`：它按 AC 8.5 的不可交换顺序调用 "
            "`evaluate_resolve_fence`（requested duplicate 的 direct-primary invariant → "
            "canonical identity → effective sequence → digest → revision），把 "
            "`FenceDecision` 映射成 409/422，并在 proceed/fold 时把 `ResolutionChoice` "
            "交给 Task 26 的 coordinator 折叠为 merged projection —— 折叠本身走 "
            "`merge.apply_resolutions`，落库仍只经 `ContentMutationService.commit(...)`。"
            "router 注册属 Task 28，但『判据有没有消费方』这件事在本任务已经收口。"
        ),
    },
    {
        "capability": "ResolutionChoice / ResolveFenceRequest 的请求体翻译层",
        "intended_status": "retired",
        "retired_by_task": "28",
        "consumer": (
            "endpoint_payloads.build_resolution_choices / .build_resolve_fence"
            "（被 wp_sync_router 的 resolve 端点调用）"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/endpoint_payloads.py",
        # 🔴 纯翻译层：不连库、不 commit、不判权限，因此没有 `commits_through`。
        #    落库仍在 conflict_resolution → oo_to_html → content_mutation 那一条上。
        "commits_through": None,
        "reason": (
            "AC 8.3 要求裁决落点由服务端决定：前端只有 preview 给它的 opaque "
            "`conflict_id`，而 merge 域按 `(stable_field_key, row_key, oo_location)` 去重。"
            "这段翻译必须在服务层 —— 放进 `app/routers/` 会让表现层成为 merge 域消费方"
            "（本判据立刻打红），也等于让前端选择裁决落在哪一行。"
            "另：Task 26 收口时 `oo_to_html.py` 与 `conflict_resolution.py` 都**没有生产"
            "调用方**，非死代码只由本登记表做**结构性**背书（Task 26 evidence README 明写"
            "「Task 28 接线后应翻转成真实调用链判据」）。Task 28 落地 "
            "`app/routers/wp_sync_router.py` 后这笔欠账还清：callback → "
            "`CallbackDeliveryService.handle_callback`（durable + correlate）→ "
            "`_apply_durable_incoming` → `OoToHtmlCoordinator.apply_durable_incoming`；"
            "resolve/retry/rollback → `ConflictResolutionService` → 同一个 coordinator。"
            "那条链由 `test_task28_sync_router.py` 的 AST 判据从 router 出发反查 —— "
            "登记表本身查不出「接线被删」或「接线搬去别的模块」。"
        ),
    },
    {
        "capability": "StructuralAnomaly 输入形态（Excel 侧行身份/类型异常探测）",
        "intended_status": "retired",
        "retired_by_task": "37",
        "consumer": (
            "excel_extract.extract_projection(...) → ExcelExtractOutcome.merge_inputs()"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/excel_extract.py",
        # 🔴 没有 `commits_through`：extractor 是**只读**的，既不 commit 也不 import
        #    `content_mutation`（Task 37 先于 Task 38，extract 侧不得依赖写入侧）。
        #    落库仍在 oo_to_html → content_mutation 那一条上，由上面两条登记把守。
        "commits_through": None,
        "reason": (
            "Task 37 落地 Excel identity-aware extractor：空 / 重复 / 已 tombstone 的 row "
            "UUID、同 stable key 多位置异值与类型规范化失败五种形态在那里被**探测**并翻成 "
            "`StructuralAnomaly`，再由 Task 26 的 coordinator 交给 `merge_projections` 的 "
            "`structural_anomalies` 参数收成 schema 冲突。它同时消费 `normalize_value` / "
            "`ContractIndex` 做类型规范化与 locator 解析（verifier 与 merge 必须同口径，"
            "否则会出现「merge 认为等值、verifier 认为不等值」的无法解释的发布失败）。"
            "本模块只读：不连库、不 commit、不发事件，也不 import 任何 materializer。"
        ),
    },
    {
        "capability": "normalize_value / ValueNormalizationError（Excel 写入侧落盘值规范化）",
        "intended_status": "retired",
        "retired_by_task": "38",
        "consumer": (
            "excel_materialize.plan_managed_writes(...) → `_normalised_write_value`"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/excel_materialize.py",
        # 🔴 没有 `commits_through`：materializer 只产出 staged 文件与 `MaterializeResult`，
        #    发布由 `ContentMutationService` / `RepresentationService` 唯一控制。它连
        #    `content_mutation` 都不 import（写入侧不得依赖 commit 侧，否则「engine 自己
        #    就能发布」在类型上合法）。落库仍在 oo_to_html → content_mutation 那一条上。
        "commits_through": None,
        "reason": (
            "Task 38 落地 Excel identity-aware materializer：projection 值落盘前必须按契约 "
            "`value_type` 规范化，而这套口径**只能**与 merge / verifier 共用一份 —— 写入侧"
            "自己写一套就会出现「merge 认为等值、反读认为不等值」的无法解释的发布失败"
            "（Task 37 的 extractor 与 `verify_roundtrip_equivalence` 已经复用同一个 "
            "`normalize_value`，写入侧是这条链上的第三个点）。规范化失败翻成 "
            "`EditableCellWriteError` 而不是静默写一个自己都读不懂的值。"
        ),
    },
    {
        "capability": "ConflictRecord 作为受保护格篡改的跨层闭合输入（Excel rematerialize 侧）",
        "intended_status": "retired",
        "retired_by_task": "38",
        "consumer": (
            "excel_rematerialize.rematerialize_merged_projection(...) → "
            "assert_protected_tamper_fully_reported / protected_conflicts_from_incoming"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/excel_rematerialize.py",
        # 🔴 同上：rematerializer 只写 staged result 并过 Task 37 的 `verify_before_commit`，
        #    自身零发布面。`RematerializeOutcome.assert_ready_for_commit()` 是交给
        #    `ContentMutationService` 之前的门，不是 commit 本身。
        "commits_through": None,
        "reason": (
            "Task 38 的 OO→HTML 入口在写第一个字节之前要求「incoming 侧发现的每一处受保护格"
            "篡改都已在调用方交来的 conflict set 里」（Property 24）。少了这条跨层闭合，"
            "merge 漏报 protected 冲突时 rematerialize 会照常发布 —— 公式格被 OO 改成字面量"
            "而审计师看不到任何冲突。判据消费的正是冲突域的 `ConflictRecord`：本模块不重写"
            "补齐规则，只定向包装 Task 37 的 `protected_conflicts_for_findings`，"
            "两侧口径因此不可能分叉。"
        ),
    },
    {
        "capability": "merge_projections / apply_resolutions（P25 / P26 的 evidence oracle）",
        "intended_status": "retired",
        "retired_by_task": "39",
        "consumer": (
            "pilot_harness.evaluate_different_field_merge(...) / "
            "evaluate_same_field_conflict(...) —— 由 `run_scenario_oracle` 调度"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/pilot_harness.py",
        # 🔴 无 `commits_through`：harness 只**读**判定结果，写的是 evidence 表
        #    （`working_paper_sync_test_run` / `working_paper_entry_evidence_scenario`），
        #    与 content version / representation / pointer / outbox 完全不相交。
        #    它不是第二个内容写入边界 —— 它连 `content_mutation` 都不 import。
        "commits_through": None,
        "reason": (
            "Task 39 的 evidence oracle 必须**真跑一次** merge 才能判定 Property 25 "
            "（不同字段并行修改自动合并、conflict_count=0 且两侧值都在）与 Property 26 "
            "（同字段异值必冲突、三值完整、未裁决时不得等于 incoming）。判据若改成"
            "「读调用方声明的 conflict_count」就退化成自证 —— 那正是本 spec 点名的"
            "「禁止手填 result」。因此 harness 是 merge 域的**只读**消费方：它不 stage、"
            "不发布、不递增 revision、不 import `content_mutation`，唯一写入面是 evidence "
            "表。少了这条登记，Task 14 的双向等值判据会把它误报成「绕过唯一 commit 入口」。"
        ),
    },
    {
        "capability": "WordInstanceObservation / Word 侧 StructuralAnomaly 输入形态",
        "intended_status": "retired",
        "retired_by_task": "59",
        "consumer": (
            "word_sdt_engine.extract_word_projection(...) —— 同 stable tag 多实例异值时"
            "构造 `duplicate_word_instance` 冲突（列出全部 XPath），类型规范化失败时"
            "构造 `type_normalization_failure` schema 冲突"
        ),
        "expected_consumer_module": "app/services/workpaper_sync/word_sdt_engine.py",
        # 🔴 无 `commits_through`：Word engine 与 Excel 侧的 extractor/materializer 同构 ——
        #    它只读 substrate、只写 staged result，零发布面，连 `content_mutation` 都不
        #    import（守卫 `TestNoRuntimeStateSurfaceInEngine` 在 AST 上锁死这一点）。
        #    落库仍在 oo_to_html → content_mutation 那一条上，由上面的登记把守。
        "commits_through": None,
        "reason": (
            "Task 59 落地通用 tagged-SDT engine：AC 7.4 要求同一 stable field key 的多个"
            "实例值一致时合并、不一致时产生冲突并列出**全部** OO 位置，因此 extract 必须"
            "真的构造 `ConflictKind.duplicate_word_instance` 并填满 `word_instances`。"
            "Word 侧行身份由**单元格内** field SDT 的 tag 承载（Task 6 实测 row 级 SDT 在 "
            "OO 9.4 上首次序列化即被剥离），所以结构异常的输入形态也在这一层成形。"
            "本 engine 不 stage 发布、不切 pointer、不递增 revision；candidate 只由 "
            "`word_instrumentation` 登记为 non-current，approved bundle 之后才由 "
            "`RepresentationService.finalize_candidate` 发布。"
        ),
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常
# ═══════════════════════════════════════════════════════════════════════════


class MergeInputError(MergeDomainError):
    """三方输入本身不自洽（contract 不一致、row_key 与 stable key 不符……）。"""

    error_code = "merge_input_invalid"


class ValueNormalizationError(MergeDomainError):
    """值无法按声明的 value_type 规范化 —— 转成 `schema` 冲突并保留原值供裁决。"""

    error_code = "value_normalization_failed"


class UnknownStableKeyError(MergeDomainError):
    """projection 里出现 contract 未登记的 stable key（fail closed，禁位置猜测）。"""

    error_code = "merge_unknown_stable_key"


# ═══════════════════════════════════════════════════════════════════════════
# 2. MISSING 哨兵
# ═══════════════════════════════════════════════════════════════════════════


class _Missing:
    """「该 stable key 在这一侧不存在」的独立单例哨兵。

    刻意的三个设计：

    1. **不实现 `__bool__`** —— 保持默认真值。若定义成 falsy，生产代码里一句
       `if value:` 就会把 MISSING 与 ``None``/``""``/``0`` 一起当空值，
       这正是要防的折叠。
    2. **不实现 `__eq__`** —— 用默认的身份相等，因此 ``MISSING == None`` 恒为
       ``False``，也不可能被某个 `__eq__` 重载悄悄判等。
    3. `__deepcopy__` / `__copy__` 返回自身，保证跨 copy 边界仍是同一个身份。
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 诊断文案
        return "MISSING"

    def __copy__(self) -> "_Missing":
        return self

    def __deepcopy__(self, memo: dict) -> "_Missing":
        return self

    def __reduce__(self) -> tuple:
        return (_missing_singleton, ())


def _missing_singleton() -> "_Missing":
    return MISSING


#: 「字段不存在」。与 ``None``（存在但为空）严格区分 —— 见模块 docstring。
MISSING: Final[_Missing] = _Missing()


# ═══════════════════════════════════════════════════════════════════════════
# 3. 类型规范化（只用于比较）
# ═══════════════════════════════════════════════════════════════════════════

#: `text` 规范化会动的**唯一**两件事。刻意极小：多规范化一步就多一种「把不同值判等」
#: 的风险，AC 层面只承认 OO 的换行表示与 BOM 是非语义差异。
_LINE_ENDING_PAIRS: Final[tuple[tuple[str, str], ...]] = (("\r\n", "\n"), ("\r", "\n"))
_ZERO_WIDTH_BOM: Final[str] = "\ufeff"

_DECIMAL_TYPES: Final[frozenset[ValueType]] = frozenset(
    {ValueType.amount, ValueType.rate, ValueType.ratio}
)


def _as_decimal(value: Any, value_type: ValueType) -> Decimal:
    if isinstance(value, bool):
        raise ValueNormalizationError(
            f"{value_type.value} 字段收到 bool {value!r} —— True/False 不是数值，"
            "不得与 1/0 判等"
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # 先转字符串再进 Decimal：`Decimal(0.1)` 会带二进制误差尾巴，
        # 让 `0.1` 与 `"0.1"` 判不等。
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueNormalizationError(
                f"{value_type.value} 字段收到空串 —— 空串不是 0、也不是 null，"
                "无法规范化为金额（保留原值供裁决）"
            )
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueNormalizationError(
                f"{value_type.value} 字段的字符串 {value!r} 不是合法数值"
            ) from exc
    raise ValueNormalizationError(
        f"{value_type.value} 字段收到 {type(value).__name__} {value!r}，无法规范化"
    )


def normalize_value(value: Any, value_type: ValueType) -> Any:
    """把值规范化成**比较键**。MISSING 恒等返回，None 保持 None。

    🔴 两条不得折叠的方向（`TestTypeNormalization` 双向锁死）：

    * ``MISSING`` 永不变成 ``None``/``""``/``0``
    * ``None`` 永不变成 ``0``/``""``/``False``
    """
    if value is MISSING:
        return MISSING
    if value is None:
        return None
    if value_type in _DECIMAL_TYPES:
        return _as_decimal(value, value_type)
    if value_type is ValueType.integer:
        if isinstance(value, bool):
            raise ValueNormalizationError(
                f"integer 字段收到 bool {value!r} —— True 不等于 1"
            )
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueNormalizationError(f"integer 字段收到非整值 float {value!r}")
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError as exc:
                raise ValueNormalizationError(
                    f"integer 字段的字符串 {value!r} 不是整数"
                ) from exc
        raise ValueNormalizationError(
            f"integer 字段收到 {type(value).__name__} {value!r}"
        )
    if value_type is ValueType.date:
        # 顺序要紧：datetime 是 date 的子类，先判 datetime 才能拒绝它。
        if isinstance(value, datetime):
            raise ValueNormalizationError(
                f"date 字段收到 datetime {value!r} —— 日期与时点是两种值，不得互相折叠"
            )
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError as exc:
                raise ValueNormalizationError(
                    f"date 字段的字符串 {value!r} 不是 ISO 日期（YYYY-MM-DD）"
                ) from exc
        raise ValueNormalizationError(f"date 字段收到 {type(value).__name__} {value!r}")
    if value_type is ValueType.datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            raise ValueNormalizationError(
                f"datetime 字段收到 date {value!r} —— 缺时间部分，不得当同一个值"
            )
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.strip())
            except ValueError as exc:
                raise ValueNormalizationError(
                    f"datetime 字段的字符串 {value!r} 不是 ISO 8601 时点"
                ) from exc
        raise ValueNormalizationError(
            f"datetime 字段收到 {type(value).__name__} {value!r}"
        )
    if value_type is ValueType.boolean:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value in ("true", "false"):
            return value == "true"
        raise ValueNormalizationError(
            f"boolean 字段只接受真 bool 或 'true'/'false'，实得 {value!r} —— "
            "0/1 与 'True' 都不折叠"
        )
    if value_type is ValueType.enum:
        if isinstance(value, str):
            return value
        raise ValueNormalizationError(
            f"enum 字段必须是字符串，实得 {type(value).__name__} {value!r}"
        )
    if value_type is ValueType.json:
        try:
            # 复用 Task 12 的 canonical 字节：键序无关、跨语言可复现。
            return canonical_json_bytes({"v": value})
        except (TypeError, ValueError) as exc:
            raise ValueNormalizationError(
                f"json 字段无法 canonical 序列化: {value!r}（{exc}）"
            ) from exc
    if value_type is ValueType.text:
        if not isinstance(value, str):
            raise ValueNormalizationError(
                f"text 字段必须是字符串，实得 {type(value).__name__} {value!r} —— "
                "不得把数字与其字符串形态判等"
            )
        out = value
        for src, dst in _LINE_ENDING_PAIRS:
            out = out.replace(src, dst)
        return out.replace(_ZERO_WIDTH_BOM, "")
    raise ValueNormalizationError(f"未登记的 value_type: {value_type!r}")  # pragma: no cover


def values_equal(left: Any, right: Any, value_type: ValueType) -> bool:
    """规范化后比较。MISSING 只与 MISSING 相等。"""
    a = normalize_value(left, value_type)
    b = normalize_value(right, value_type)
    if a is MISSING or b is MISSING:
        return a is MISSING and b is MISSING
    if a is None or b is None:
        return a is None and b is None
    return bool(a == b)


def envelopes_equal(
    left: ValueEnvelope, right: ValueEnvelope, value_type: ValueType
) -> bool:
    """信封级比较：present 不同即不等（absent 与 present-but-null 不折叠）。"""
    if left.present != right.present:
        return False
    if not left.present:
        return True
    return values_equal(left.value, right.value, value_type)


# ═══════════════════════════════════════════════════════════════════════════
# 4. contract 索引：stable key → 定位器
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _FieldTemplate:
    spec: FieldSpec
    sheet_key: str | None
    sheet_excel_name: str | None
    table_key: str | None
    formula_mask: tuple[str, ...]


def _segments_match(template: str, actual: str) -> tuple[bool, str]:
    """模板段与实例段逐段比对，返回 (是否匹配, 行身份值)。

    🔴 必须逐段比：只比前缀会让 `equity_changes/{row_uuid}/closing_amount` 误配到
    任何同前缀键（Task 13 的 `TestGuardSelfCheck` 已用替身证明过这个假绿形态）。
    """
    exp = template.split("/")
    act = actual.split("/")
    if len(exp) != len(act):
        return (False, "")
    row_key = ""
    for expected, given in zip(exp, act):
        if expected == ROW_UUID_PLACEHOLDER:
            if not given:
                return (False, "")
            row_key = given
            continue
        if expected != given:
            return (False, "")
    return (True, row_key)


class ContractIndex:
    """把 contract 展平成「stable key 模板 → 定位信息」的索引。

    行域字段的模板含 ``{row_uuid}``，因此索引是**模板级**的；解析具体键时逐段匹配
    并抽出行身份值。同一份 contract 只需建一次索引，`merge_projections` 内复用。
    """

    def __init__(
        self,
        contract: SyncContract,
        *,
        label_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self._contract = contract
        self._labels = dict(label_overrides or {})
        self._templates: list[_FieldTemplate] = []
        for sheet in contract.sheets:
            for table in sheet.tables:
                for spec in table.fields:
                    self._templates.append(
                        _FieldTemplate(
                            spec=spec,
                            sheet_key=sheet.sheet_key,
                            sheet_excel_name=sheet.excel_name,
                            table_key=table.table_key,
                            formula_mask=tuple(table.formula_mask),
                        )
                    )
        for spec in contract.fields + contract.repeaters:
            self._templates.append(
                _FieldTemplate(
                    spec=spec,
                    sheet_key=None,
                    sheet_excel_name=None,
                    table_key=None,
                    formula_mask=(),
                )
            )
        self._cache: dict[str, FieldLocator] = {}

    # ── 保护策略 ──────────────────────────────────────────────────────
    @staticmethod
    def _protection(template: _FieldTemplate) -> ProtectionPolicy:
        """三类只读来源分别登记（AC 6.6 的「公式 / auto-source / 受保护单元格」）。

        第三类是**独立判据**：契约允许一个 `editable` 字段的列落在 `formula_mask` 里
        （Task 13 只校验反向：formula 字段必须在 mask 内）。这种格在 OO 里是受保护
        单元格，仍必须只读 —— 把这条与前两条合并会让「受保护单元格」永不被测到。
        """
        spec = template.spec
        if spec.mode is FieldMode.formula:
            return ProtectionPolicy.read_only_formula
        if spec.mode is FieldMode.auto_source:
            return ProtectionPolicy.read_only_auto_source
        if spec.mode is FieldMode.word_only:
            return ProtectionPolicy.word_only
        if (
            spec.cell is not None
            and template.formula_mask
            and column_in_ranges(spec.cell.column, template.formula_mask)
        ):
            return ProtectionPolicy.read_only_masked_cell
        return ProtectionPolicy.editable

    @staticmethod
    def _field_source(spec: FieldSpec, document_type: str) -> FieldSource:
        if spec.mode is FieldMode.formula:
            return FieldSource.server_formula
        if spec.mode is FieldMode.auto_source:
            return FieldSource.auto_data_source
        if spec.mode is FieldMode.word_only:
            return FieldSource.word_free_text
        return (
            FieldSource.onlyoffice_cell
            if document_type == "xlsx"
            else FieldSource.onlyoffice_sdt
        )

    def _oo_location(self, template: _FieldTemplate, row_key: str) -> str:
        """OO 地址：xlsx 用单元格、docx 用实例化后的 `sdt_tag`（design §冲突记录）。

        动态行的具体行号在 rematerialize 时才确定（行会随增删上移下移），因此这里给的是
        **行身份寻址**形态 `Sheet!列@row=<row_uuid>` —— 行号不是稳定身份
        （Requirement 6.5 明令禁止用位置作持久化身份），行 UUID 才是。
        """
        spec = template.spec
        if spec.sdt_tag is not None:
            return spec.sdt_tag.replace(ROW_UUID_PLACEHOLDER, row_key)
        if spec.cell is None:  # pragma: no cover - Task 13 解析器已保证二者必有其一
            raise MergeInputError(
                f"{spec.stable_field_key}: contract 既无 cell 也无 sdt_tag，无法定位 OO 地址"
            )
        sheet = template.sheet_excel_name or (template.sheet_key or "")
        if spec.cell.static_row is not None:
            return f"{sheet}!{spec.cell.column}{spec.cell.static_row}"
        return f"{sheet}!{spec.cell.column}@row={row_key}"

    def _label(self, template: _FieldTemplate, key: str) -> str:
        """业务标签。

        契约当前**没有**中文业务标签字段（Task 13 的 `FieldSpec` 不含 label），
        所以这里派生一个确定、可追溯、非空的路径式标签，并允许调用方用
        `label_overrides` 覆盖。真正的中文标签需要契约新增字段 —— 见
        :data:`DEFERRED_CONSUMERS` 之外的已知欠账（evidence README §欠账）。
        """
        if key in self._labels:
            return self._labels[key][:300]
        spec = template.spec
        leaf = spec.column_key or spec.json_pointer.rstrip("/").split("/")[-1]
        parts = [
            part
            for part in (template.sheet_excel_name or template.sheet_key, template.table_key, leaf)
            if part
        ]
        return " / ".join(parts)[:300] or key[:300]

    # ── 解析 ──────────────────────────────────────────────────────────
    def resolve(self, stable_key: str, *, declared_row_key: str | None = None) -> FieldLocator:
        cached = self._cache.get(stable_key)
        if cached is not None:
            self._assert_row_key(cached, declared_row_key)
            return cached
        matches: list[tuple[_FieldTemplate, str]] = []
        for template in self._templates:
            ok, row_key = _segments_match(template.spec.stable_field_key, stable_key)
            if ok:
                matches.append((template, row_key))
        if not matches:
            raise UnknownStableKeyError(
                f"stable key {stable_key!r} 未在 contract {self._contract.contract_id} 登记 —— "
                "受管字段必须逐条声明，禁止按中文表头/位置猜测（Requirement 6.20）"
            )
        if len(matches) > 1:
            raise MergeInputError(
                f"stable key {stable_key!r} 命中 {len(matches)} 个契约模板 "
                f"{[t.spec.stable_field_key for t, _ in matches]} —— 键索引失去唯一性"
            )
        template, row_key = matches[0]
        spec = template.spec
        locator = FieldLocator(
            stable_field_key=stable_key,
            business_label=self._label(template, stable_key),
            json_pointer=spec.json_pointer.replace(ROW_UUID_PLACEHOLDER, row_key),
            oo_location=self._oo_location(template, row_key),
            field_source=self._field_source(spec, self._contract.document_type),
            protection_policy=self._protection(template),
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=row_key,
            sheet_key=template.sheet_key,
            table_key=template.table_key,
        )
        self._cache[stable_key] = locator
        self._assert_row_key(locator, declared_row_key)
        return locator

    @staticmethod
    def _assert_row_key(locator: FieldLocator, declared: str | None) -> None:
        if declared is None:
            return
        if (declared or "") != locator.row_key:
            raise MergeInputError(
                f"{locator.stable_field_key}: FieldValue.row_key={declared!r} 与 stable key 里的"
                f"行身份段 {locator.row_key!r} 不符 —— 行身份只有一个真源"
            )

    @property
    def is_row_scoped_map(self) -> Mapping[str, bool]:  # pragma: no cover - 诊断用
        return {t.spec.stable_field_key: t.spec.row_scoped for t in self._templates}


# ═══════════════════════════════════════════════════════════════════════════
# 5. 输入形态：Word 多实例观测 + 结构异常
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordInstance:
    """extract 观测到的一个 SDT 实例。"""

    xpath: str
    value: Any = MISSING

    @property
    def envelope(self) -> ValueEnvelope:
        return ValueEnvelope.absent() if self.value is MISSING else ValueEnvelope.of(self.value)


@dataclass(frozen=True)
class WordInstanceObservation:
    """同一 stable field key 在 Word 中的**全部**实例（AC 7.4 / Property 32）。"""

    stable_field_key: str
    instances: tuple[WordInstance, ...]

    def __post_init__(self) -> None:
        if not self.instances:
            raise MergeInputError(
                f"{self.stable_field_key}: 实例清单为空 —— 没有观测到实例就不该有观测记录"
            )
        seen = {inst.xpath for inst in self.instances}
        if len(seen) != len(self.instances):
            raise MergeInputError(
                f"{self.stable_field_key}: 实例 XPath 重复 {sorted(seen)} —— "
                "每个实例位置必须唯一可追溯"
            )


@dataclass(frozen=True)
class StructuralAnomaly:
    """extract 报出的结构/身份异常（Task 37/59 探测，本域只收成 `schema` 冲突）。

    `blocks_row_key` 非空时，该行的**全部**受管字段都被封锁在 current（fail closed），
    这样「一处行身份坏了」不会被当成整表覆盖（Requirement 6.9 / 6.10）。
    """

    kind: SchemaAnomalyKind
    stable_field_key: str
    detail: str
    row_key: str = ""
    table_key: str | None = None
    oo_location: str | None = None
    business_label: str | None = None
    json_pointer: str | None = None
    blocks_row_key: str = ""
    blocks_stable_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.detail.strip()) < 8:
            raise MergeInputError(
                f"{self.stable_field_key}: StructuralAnomaly.detail 过短 —— "
                "结构异常必须带可操作诊断（AC 5.12）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 输出形态
# ═══════════════════════════════════════════════════════════════════════════


class FieldVerdict(str, Enum):
    """每个 stable key 走到了真值表的哪一行（可诊断、可统计）。"""

    kept_current = "kept_current"
    took_incoming = "took_incoming"
    both_sides_agree = "both_sides_agree"
    row_deleted = "row_deleted"
    word_only = "word_only"
    held_by_row_conflict = "held_by_row_conflict"
    held_by_schema_conflict = "held_by_schema_conflict"
    conflict_value = "conflict_value"
    conflict_protected = "conflict_protected"
    conflict_delete_update = "conflict_delete_update"
    conflict_schema = "conflict_schema"
    conflict_duplicate_word_instance = "conflict_duplicate_word_instance"

    @property
    def is_conflict(self) -> bool:
        return self.value.startswith("conflict_")


class RowLifecycle(str, Enum):
    """一行在三方之间的生命周期。**按 row identity 判定，永不看位置。**"""

    unchanged = "unchanged"
    added_by_incoming = "added_by_incoming"
    added_by_current = "added_by_current"
    deleted_by_incoming = "deleted_by_incoming"
    deleted_by_current = "deleted_by_current"
    delete_update_conflict = "delete_update_conflict"
    modified = "modified"


@dataclass(frozen=True)
class RowDecision:
    table_key: str | None
    row_key: str
    lifecycle: RowLifecycle
    member_keys: tuple[str, ...]
    held: bool = False


@dataclass(frozen=True)
class MergeOutcome:
    """一次三方 merge 的完整结果。冲突非空时 `merged` 只是「hold 在 current」的快照。"""

    merged: Projection
    conflicts: ConflictSet
    verdicts: Mapping[str, FieldVerdict]
    rows: tuple[RowDecision, ...]
    word_only_keys: tuple[str, ...]
    deleted_keys: tuple[str, ...]
    incoming_managed_keys: tuple[str, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def auto_merged_keys(self) -> tuple[str, ...]:
        """真正采纳了 OO 变更的键（AC 6.8「不同字段的并行修改自动合并」的判据）。"""
        return tuple(
            key
            for key, verdict in sorted(self.verdicts.items())
            if verdict in (FieldVerdict.took_incoming, FieldVerdict.both_sides_agree)
        )

    def value_of(self, stable_key: str) -> ValueEnvelope:
        field = self.merged.get(stable_key)
        return ValueEnvelope.absent() if field is None else ValueEnvelope.of(field.value)

    def requires_client_refresh(self, incoming: Projection) -> bool:
        """**未经裁决**的 merged 与 incoming 是否不等值（AC 4.11 / 8.12 的纯判据）。

        🔴 只在「零冲突」路径上等价于最终判据。有冲突并经人工裁决时，落库的是
        :func:`apply_resolutions` 的产物而不是 `self.merged`（后者对每个冲突字段保留
        **current** 侧值），此时必须改用 :func:`projection_requires_client_refresh`
        并传入**真正发布的那份** projection —— 否则 refresh 裁决按错值计算：审计师
        选了 incoming、服务端却认为「merged==incoming，不必重载」，客户端基线被推进到
        一份它从未见过的内容上（Task 26 审计发现的静默错值路径的第二半）。
        """
        return projection_requires_client_refresh(
            settled=self.merged, incoming=incoming, word_only_keys=self.word_only_keys
        )


def projection_requires_client_refresh(
    *,
    settled: Projection,
    incoming: Projection,
    word_only_keys: Sequence[str],
) -> bool:
    """**要发布的那份** projection 与 incoming 是否不等值（AC 4.11 / 8.12 的唯一判据）。

    `settled` 是「最终会落库的受管 projection」：零冲突路径下就是 `MergeOutcome.merged`，
    经人工裁决时是 :func:`apply_resolutions` 的产物。判据只有这一份实现，
    :meth:`MergeOutcome.requires_client_refresh` 也委托到这里 —— 两份实现就意味着
    「裁决路径的 refresh 判据」可以悄悄退回读 `merged`。

    `word_only` 键不参与比较：它们永不进 HTML projection，Word 侧本就与 settled 不同。
    """
    excluded = set(word_only_keys)
    keys = (set(settled.values) | set(incoming.values)) - excluded
    for key in keys:
        mine = settled.get(key)
        theirs = incoming.get(key)
        if (mine is None) != (theirs is None):
            return True
        if mine is None or theirs is None:
            continue
        if not values_equal(mine.value, theirs.value, mine.value_type):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 7. Word 多实例归并（AC 7.4 / Property 32）
# ═══════════════════════════════════════════════════════════════════════════


def reduce_word_instances(
    observation: WordInstanceObservation, locator: FieldLocator
) -> tuple[ValueEnvelope, ConflictRecord | None]:
    """同 tag 多实例：值一致则合并为一个字段；不一致则生成 duplicate 冲突并列出全部位置。

    返回 `(incoming 值, 冲突或 None)`。冲突时 `incoming_value` 取 XPath 序首个实例的
    快照，**权威清单在 `word_instances`**（AC 7.4「列出全部 OO 位置」）——
    不挑一个当代表就落库，是为了让裁决界面能显示三值列。
    """
    ordered = tuple(sorted(observation.instances, key=lambda inst: inst.xpath))
    first = ordered[0].envelope
    if all(
        envelopes_equal(inst.envelope, first, locator.value_type) for inst in ordered[1:]
    ):
        return (first, None)
    refs = tuple(WordInstanceRef(xpath=inst.xpath, value=inst.envelope) for inst in ordered)
    record = ConflictRecord(
        locator=locator,
        kind=ConflictKind.duplicate_word_instance,
        base=ValueEnvelope.absent(),
        current=ValueEnvelope.absent(),
        incoming=first,
        suggested_action=SuggestedAction.pick_instance,
        reason=(
            f"同一 stable tag 共 {len(ordered)} 个实例但值不一致；incoming_value 仅为 XPath "
            f"序首个实例（{ordered[0].xpath}）的快照，全部位置见 word_instances（AC 7.4）"
        ),
        word_instances=refs,
    )
    return (first, record)


# ═══════════════════════════════════════════════════════════════════════════
# 8. 三方 merge
# ═══════════════════════════════════════════════════════════════════════════


def _envelope(projection: Projection, key: str) -> ValueEnvelope:
    field = projection.get(key)
    return ValueEnvelope.absent() if field is None else ValueEnvelope.of(field.value)


def _row_order(projection: Projection, table_key: str | None) -> tuple[str, ...]:
    """`Projection.row_keys` 按 **table_key** 索引（顶层 docx repeater 用空串）。"""
    declared = projection.row_keys.get(table_key or "", ()) if projection.row_keys else ()
    return tuple(declared)


def merge_projections(
    *,
    base: Projection,
    current: Projection,
    incoming: Projection,
    contract: SyncContract,
    word_instances: Sequence[WordInstanceObservation] = (),
    structural_anomalies: Sequence[StructuralAnomaly] = (),
    label_overrides: Mapping[str, str] | None = None,
) -> MergeOutcome:
    """base/current/incoming 的字段级三方合并（design §Merge Algorithm 的真值表）。

    * 不同字段的并行修改天然自动合并（键互不相交 ⇒ 各自独立走真值表）——
      Property 25。
    * 同字段异值**不选边**：生成冲突并保留 JSON Pointer / OO 地址 / 三值 / 行身份 ——
      Property 26 / 35。
    * 行新增、删除、重排、footer 下移全部按 row identity 判定；位置从不参与比较 ——
      Property 27 / AC 6.9。
    """
    for name, projection in (("base", base), ("current", current), ("incoming", incoming)):
        if projection.contract_id != contract.contract_id:
            raise MergeInputError(
                f"{name} projection 的 contract_id {projection.contract_id!r} 与 contract "
                f"{contract.contract_id!r} 不符 —— 三方必须来自同一 frozen contract"
            )
        if projection.document_type != contract.document_type:
            raise MergeInputError(
                f"{name} projection 的 document_type {projection.document_type!r} 与 contract "
                f"{contract.document_type!r} 不符"
            )
        projection.assert_matches_contract(contract)

    index = ContractIndex(contract, label_overrides=label_overrides)
    conflicts: list[ConflictRecord] = []
    verdicts: dict[str, FieldVerdict] = {}

    # ── 8.1 Word 多实例先归并成单个 incoming 值 ────────────────────────
    reduced_incoming: dict[str, ValueEnvelope] = {}
    for observation in word_instances:
        locator = index.resolve(observation.stable_field_key)
        value, record = reduce_word_instances(observation, locator)
        reduced_incoming[observation.stable_field_key] = value
        if record is not None:
            conflicts.append(record)
            verdicts[observation.stable_field_key] = (
                FieldVerdict.conflict_duplicate_word_instance
            )

    # ── 8.2 结构异常 → schema 冲突 + 封锁区 ────────────────────────────
    blocked_keys: set[str] = set()
    blocked_rows: set[str] = set()
    for anomaly in structural_anomalies:
        locator = _anomaly_locator(anomaly, index)
        conflicts.append(
            ConflictRecord(
                locator=locator,
                kind=ConflictKind.schema,
                base=_envelope(base, anomaly.stable_field_key),
                current=_envelope(current, anomaly.stable_field_key),
                incoming=_envelope(incoming, anomaly.stable_field_key),
                suggested_action=(
                    SuggestedAction.manual_merge
                    if anomaly.kind.adjudicable_by_value_choice
                    else SuggestedAction.fix_structure
                ),
                reason=f"{anomaly.kind.value}: {anomaly.detail}",
                schema_anomaly=anomaly.kind,
            )
        )
        blocked_keys.update(anomaly.blocks_stable_keys or (anomaly.stable_field_key,))
        if anomaly.blocks_row_key:
            blocked_rows.add(anomaly.blocks_row_key)

    # ── 8.3 键域与定位 ────────────────────────────────────────────────
    all_keys = sorted(set(base.values) | set(current.values) | set(incoming.values))
    locators: dict[str, FieldLocator] = {}
    for key in all_keys:
        declared = None
        for projection in (incoming, current, base):
            field = projection.get(key)
            if field is not None:
                declared = field.row_key or ""
                break
        locators[key] = index.resolve(key, declared_row_key=declared)

    #: 三方信封只算一次：`incoming` 侧若有 Word 多实例归并结果则用归并值。
    envs: dict[str, tuple[ValueEnvelope, ValueEnvelope, ValueEnvelope]] = {
        key: (
            _envelope(base, key),
            _envelope(current, key),
            reduced_incoming.get(key) or _envelope(incoming, key),
        )
        for key in all_keys
    }

    # ── 8.4 行生命周期（按 row identity，不看位置）────────────────────
    rows_members: dict[tuple[str | None, str], list[str]] = {}
    for key, locator in locators.items():
        if not locator.row_key:
            continue
        rows_members.setdefault((locator.table_key, locator.row_key), []).append(key)

    row_decisions: list[RowDecision] = []
    held_rows: dict[tuple[str | None, str], RowDecision] = {}
    for (table_key, row_key), members in sorted(
        rows_members.items(), key=lambda item: (item[0][0] or "", item[0][1])
    ):
        in_base = any(envs[key][0].present for key in members)
        in_current = any(envs[key][1].present for key in members)
        in_incoming = any(envs[key][2].present for key in members)
        current_changed = any(
            not envelopes_equal(envs[key][1], envs[key][0], locators[key].value_type)
            for key in members
            if _comparable(locators[key], envs[key][0], envs[key][1])
        )
        incoming_changed = any(
            not envelopes_equal(envs[key][2], envs[key][0], locators[key].value_type)
            for key in members
            if _comparable(locators[key], envs[key][0], envs[key][2])
        )
        lifecycle = _classify_row(
            in_base=in_base,
            in_current=in_current,
            in_incoming=in_incoming,
            current_changed=current_changed,
            incoming_changed=incoming_changed,
        )
        held = lifecycle is RowLifecycle.delete_update_conflict or row_key in blocked_rows
        decision = RowDecision(
            table_key=table_key,
            row_key=row_key,
            lifecycle=lifecycle,
            member_keys=tuple(sorted(members)),
            held=held,
        )
        row_decisions.append(decision)
        if held:
            held_rows[(table_key, row_key)] = decision

    accepted_row_deletions = {
        (d.table_key, d.row_key)
        for d in row_decisions
        if d.lifecycle is RowLifecycle.deleted_by_incoming
    }

    # ── 8.5 逐字段真值表 ──────────────────────────────────────────────
    merged_values: dict[str, FieldValue] = {}
    word_only_keys: list[str] = []
    for key in all_keys:
        locator = locators[key]
        row_id = (locator.table_key, locator.row_key)
        b, c, i = envs[key]

        if key in verdicts and verdicts[key].is_conflict:
            # Word duplicate 冲突已在 8.1 生成 —— hold 在 current。
            _put(merged_values, locator, c)
            continue
        if key in blocked_keys or (locator.row_key and locator.row_key in blocked_rows):
            verdicts[key] = FieldVerdict.held_by_schema_conflict
            _put(merged_values, locator, c)
            continue
        if locator.row_key and row_id in held_rows:
            verdict, record = _row_conflict_for(locator, b, c, i, held_rows[row_id])
            verdicts[key] = verdict
            if record is not None:
                conflicts.append(record)
            _put(merged_values, locator, c)
            continue
        if locator.mode is FieldMode.word_only:
            # Word 权威且永不进 HTML projection（AC 7.3 / design §Word extract）。
            verdicts[key] = FieldVerdict.word_only
            word_only_keys.append(key)
            continue

        try:
            same_incoming_base = envelopes_equal(i, b, locator.value_type)
            same_current_base = envelopes_equal(c, b, locator.value_type)
            same_current_incoming = envelopes_equal(c, i, locator.value_type)
        except ValueNormalizationError as exc:
            # 窄类型捕获：把「类型转换失败」如实记成 schema 冲突并保留原值供裁决
            # （design §Extract）。不是 `except Exception` 降级，error 文案原样带出。
            verdicts[key] = FieldVerdict.conflict_schema
            conflicts.append(
                ConflictRecord(
                    locator=locator,
                    kind=ConflictKind.schema,
                    base=b,
                    current=c,
                    incoming=i,
                    suggested_action=SuggestedAction.manual_merge,
                    reason=(
                        f"{SchemaAnomalyKind.type_normalization_failure.value}: {exc} —— "
                        "保留原值供裁决，不按任一侧静默应用"
                    ),
                    schema_anomaly=SchemaAnomalyKind.type_normalization_failure,
                )
            )
            _put(merged_values, locator, c)
            continue

        if not locator.row_key and b.present and not i.present:
            # 静态受管格/SDT 在 incoming 里消失 = 载体漂移。HTML store 可以省略未填字段，
            # 但 extract 出来的受管静态格必然存在，故这条只对 incoming 侧成立（不对称是
            # 两侧语义不同，不是遗漏）。
            verdicts[key] = FieldVerdict.conflict_schema
            conflicts.append(
                ConflictRecord(
                    locator=locator,
                    kind=ConflictKind.schema,
                    base=b,
                    current=c,
                    incoming=i,
                    suggested_action=SuggestedAction.fix_structure,
                    reason=(
                        f"{SchemaAnomalyKind.missing_identity_carrier.value}: 受管静态字段在 "
                        "incoming projection 中缺失 —— 载体（单元格/SDT）疑似被删除，"
                        "fail closed 不按位置猜测（Requirement 6.10 / 7.8）"
                    ),
                    schema_anomaly=SchemaAnomalyKind.missing_identity_carrier,
                )
            )
            _put(merged_values, locator, c)
            continue

        if (
            locator.is_protected
            and b.present
            and i.present
            and not same_incoming_base
        ):
            # Property 24：current 公式与值不变，只生成 protected 冲突。
            verdicts[key] = FieldVerdict.conflict_protected
            conflicts.append(
                ConflictRecord(
                    locator=locator,
                    kind=ConflictKind.protected,
                    base=b,
                    current=c,
                    incoming=i,
                    suggested_action=SuggestedAction.keep_current,
                    reason=(
                        f"受保护字段（{locator.protection_policy.value}）在 OO 侧被改动 —— "
                        "公式/auto-source 结果不得被覆盖（AC 6.6），"
                        "incoming 值只用于篡改检测"
                    ),
                )
            )
            _put(merged_values, locator, c)
            continue

        if same_incoming_base:
            verdicts[key] = (
                FieldVerdict.row_deleted
                if row_id in accepted_row_deletions and not c.present
                else FieldVerdict.kept_current
            )
            _put(merged_values, locator, c)
            continue
        if same_current_base:
            verdicts[key] = (
                FieldVerdict.row_deleted
                if row_id in accepted_row_deletions and not i.present
                else FieldVerdict.took_incoming
            )
            _put(merged_values, locator, i)
            continue
        if same_current_incoming:
            verdicts[key] = FieldVerdict.both_sides_agree
            _put(merged_values, locator, c)
            continue

        kind = (
            ConflictKind.delete_update
            if b.present and (c.present != i.present)
            else ConflictKind.value
        )
        verdicts[key] = (
            FieldVerdict.conflict_delete_update
            if kind is ConflictKind.delete_update
            else FieldVerdict.conflict_value
        )
        conflicts.append(
            ConflictRecord(
                locator=locator,
                kind=kind,
                base=b,
                current=c,
                incoming=i,
                suggested_action=SuggestedAction.manual_merge,
                reason=(
                    "同一 stable field key 的 current 与 incoming 相对 base 改成了不同值 —— "
                    "三方规则不选边，必须人工裁决（AC 6.8 / Property 26）"
                    if kind is ConflictKind.value
                    else (
                        "同一 row identity 一侧删除、另一侧更新 —— 只锁这一行，"
                        "其他行照常合并（AC 6.9 / Property 27）"
                    )
                ),
            )
        )
        _put(merged_values, locator, c)

    merged = Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=merged_values,
        row_keys=_merged_row_order(merged_values, locators, incoming, current),
    )
    deleted = tuple(
        key
        for key in all_keys
        if key not in merged_values and key not in word_only_keys
    )
    return MergeOutcome(
        merged=merged,
        conflicts=ConflictSet(tuple(conflicts)),
        verdicts=dict(verdicts),
        rows=tuple(row_decisions),
        word_only_keys=tuple(sorted(word_only_keys)),
        deleted_keys=deleted,
        incoming_managed_keys=tuple(sorted(set(incoming.values) | set(reduced_incoming))),
    )


def _comparable(
    locator: FieldLocator, left: ValueEnvelope, right: ValueEnvelope
) -> bool:
    """行级「是否改动过」的比较里，跳过会抛规范化错误的键（它们自有 schema 冲突）。

    刻意只试**规范化**而不试相等：`absent` 在这里不能被换成 `None` 去凑一次比较 ——
    那会在判据内部把 MISSING 折叠成 null（本模块要防的正是这种折叠）。
    """
    for env in (left, right):
        if not env.present:
            continue
        try:
            normalize_value(env.value, locator.value_type)
        except ValueNormalizationError:
            return False
    return True


def _classify_row(
    *,
    in_base: bool,
    in_current: bool,
    in_incoming: bool,
    current_changed: bool,
    incoming_changed: bool,
) -> RowLifecycle:
    """行生命周期分类。**只看 row identity 的存在性与值变化，绝不看顺序/位置。**"""
    if not in_base:
        if in_incoming and not in_current:
            return RowLifecycle.added_by_incoming
        if in_current and not in_incoming:
            return RowLifecycle.added_by_current
        return RowLifecycle.modified if (current_changed or incoming_changed) else RowLifecycle.unchanged
    if not in_incoming and in_current:
        return (
            RowLifecycle.delete_update_conflict
            if current_changed
            else RowLifecycle.deleted_by_incoming
        )
    if not in_current and in_incoming:
        return (
            RowLifecycle.delete_update_conflict
            if incoming_changed
            else RowLifecycle.deleted_by_current
        )
    if not in_current and not in_incoming:
        return RowLifecycle.deleted_by_incoming
    return RowLifecycle.modified if (current_changed or incoming_changed) else RowLifecycle.unchanged


def _row_conflict_for(
    locator: FieldLocator,
    b: ValueEnvelope,
    c: ValueEnvelope,
    i: ValueEnvelope,
    decision: RowDecision,
) -> tuple[FieldVerdict, ConflictRecord | None]:
    """被 hold 的行：只对**真被改动**的字段出 delete_update 冲突，其余仅 hold。"""
    if decision.lifecycle is not RowLifecycle.delete_update_conflict:
        return (FieldVerdict.held_by_schema_conflict, None)
    if not (b.present and (c.present != i.present)):
        return (FieldVerdict.held_by_row_conflict, None)
    try:
        changed_side_differs = not envelopes_equal(
            c if c.present else i, b, locator.value_type
        )
    except ValueNormalizationError:
        changed_side_differs = True
    if not changed_side_differs:
        return (FieldVerdict.held_by_row_conflict, None)
    record = ConflictRecord(
        locator=locator,
        kind=ConflictKind.delete_update,
        base=b,
        current=c,
        incoming=i,
        suggested_action=SuggestedAction.manual_merge,
        reason=(
            f"row identity {locator.row_key!r} 在一侧被删除、另一侧被更新 —— 只锁本行，"
            "其他行照常自动合并（AC 6.9 / Property 27）"
        ),
    )
    return (FieldVerdict.conflict_delete_update, record)


def _anomaly_locator(anomaly: StructuralAnomaly, index: ContractIndex) -> FieldLocator:
    """结构异常的定位器：能在 contract 里解析就用 contract，否则用异常自带的三要素。

    `unknown_stable_key` / `missing_identity_carrier` 这类异常的 key 可能根本不在
    contract 里，此时不许伪造契约信息 —— 由 extract 侧提供 label/pointer/OO 地址。
    """
    try:
        return index.resolve(anomaly.stable_field_key)
    except (UnknownStableKeyError, MergeInputError):
        missing = [
            name
            for name in ("business_label", "json_pointer", "oo_location")
            if not (getattr(anomaly, name) or "").strip()
        ]
        if missing:
            raise MergeInputError(
                f"{anomaly.stable_field_key}: 该 key 不在 contract "
                f"内，结构异常必须自带 {missing} 才能形成可追溯冲突（AC 8.1/8.2），"
                "禁止用空标签或空地址落库"
            ) from None
        return FieldLocator(
            stable_field_key=anomaly.stable_field_key,
            business_label=anomaly.business_label or "",
            json_pointer=anomaly.json_pointer or "",
            oo_location=anomaly.oo_location or "",
            field_source=FieldSource.onlyoffice_cell,
            protection_policy=ProtectionPolicy.editable,
            value_type=ValueType.json,
            mode=FieldMode.editable,
            row_key=anomaly.row_key,
            table_key=anomaly.table_key,
        )


def _put(
    values: dict[str, FieldValue], locator: FieldLocator, envelope: ValueEnvelope
) -> None:
    """把胜出信封写进 merged。absent ⇒ **不写键**（键缺失就是 MISSING 的表示）。"""
    if not envelope.present:
        values.pop(locator.stable_field_key, None)
        return
    values[locator.stable_field_key] = FieldValue(
        stable_key=locator.stable_field_key,
        value=envelope.value,
        value_type=locator.value_type,
        mode=locator.mode,
        row_key=locator.row_key or None,
    )


def _merged_row_order(
    merged_values: Mapping[str, FieldValue],
    locators: Mapping[str, FieldLocator],
    incoming: Projection,
    current: Projection,
) -> dict[str, tuple[str, ...]]:
    """merged 的行顺序：以 incoming 的展示顺序为主，current 独有行按其顺序追加。

    顺序只是**展示**，不是身份 —— 重排不改变任何字段值，因此不产生冲突
    （AC 6.9「不得把位置变化误判为整表覆盖」）。
    """
    surviving: dict[str | None, list[str]] = {}
    for key in merged_values:
        locator = locators.get(key)
        if locator is None or not locator.row_key:
            continue
        bucket = surviving.setdefault(locator.table_key, [])
        if locator.row_key not in bucket:
            bucket.append(locator.row_key)
    out: dict[str, tuple[str, ...]] = {}
    for table_key, rows in surviving.items():
        alive = set(rows)
        ordered: list[str] = [r for r in _row_order(incoming, table_key) if r in alive]
        ordered += [
            r
            for r in _row_order(current, table_key)
            if r in alive and r not in ordered
        ]
        ordered += [r for r in rows if r not in ordered]
        out[table_key or ""] = tuple(ordered)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 9. 人工裁决落地
# ═══════════════════════════════════════════════════════════════════════════


def apply_resolutions(
    outcome: MergeOutcome,
    choices: Sequence[ResolutionChoice],
    *,
    contract: SyncContract,
    label_overrides: Mapping[str, str] | None = None,
) -> Projection:
    """把人工裁决落成 merged projection。

    * 缺一条裁决就抛 :class:`~conflicts.UnresolvedConflictError` —— **绝不**自动选边
    * 受保护字段只允许 `keep_current`（AC 6.6）
    * 身份类结构冲突不可靠选边收敛（fail closed）
    * 被 hold 的行：其冲突全部裁决为「缺失」时整行删除，否则整行保留
    """
    by_key = assert_all_conflicts_resolved(outcome.conflicts, choices)
    index = ContractIndex(contract, label_overrides=label_overrides)
    values = dict(outcome.merged.values)
    records = outcome.conflicts.by_key()
    resolved_env: dict[tuple[str, str, str], ValueEnvelope] = {}
    for key, choice in by_key.items():
        record = records[key]
        envelope = resolved_value_for(record, choice)
        resolved_env[key] = envelope
        _put(values, record.locator, envelope)

    for decision in outcome.rows:
        if not decision.held:
            continue
        row_conflicts = [
            record
            for record in outcome.conflicts
            if record.locator.row_key == decision.row_key
            and record.locator.table_key == decision.table_key
        ]
        if not row_conflicts:
            continue
        if all(
            not resolved_env[record.dedupe_key].present for record in row_conflicts
        ):
            for member in decision.member_keys:
                values.pop(member, None)

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=_merged_row_order(
            values,
            {key: index.resolve(key) for key in values},
            outcome.merged,
            outcome.merged,
        ),
    )


def settled_projection(outcome: MergeOutcome) -> Projection:
    """应用成功后的稳定态：base/current/incoming 三方都是 merged。

    canonical rematerialize 把 merged 写回 incoming substrate（AC 8.10），因此三方
    同时前进到 merged —— 这正是「merge 幂等」的语义化定义：
    ``merge(m, m, m).merged == m``。
    """
    return outcome.merged


__all__ = [
    "DEFERRED_CONSUMERS", "RETIRED_DEFERRALS",
    "MergeInputError", "ValueNormalizationError", "UnknownStableKeyError",
    "MISSING",
    "normalize_value", "values_equal", "envelopes_equal",
    "ContractIndex",
    "WordInstance", "WordInstanceObservation", "StructuralAnomaly",
    "FieldVerdict", "RowLifecycle", "RowDecision", "MergeOutcome",
    "projection_requires_client_refresh",
    "reduce_word_instances", "merge_projections", "apply_resolutions",
    "settled_projection",
]
