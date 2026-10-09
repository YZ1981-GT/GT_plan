"""adopt-substrate —— 反向收敛：以已发布 substrate 为准，覆盖 HTML store。

spec: workpaper-sync-managed-row-convergence（Requirement 2 / 3）

🔴 **现状定位：运维工具，不在常规链路上**（方向裁决后的如实更新）

本端点原是 P0「解阻 D4 恒 500」的手段。但 500 的**根治**走的是 P1 方向 C
（materialize 侧受管行收敛 —— store 权威、substrate 跟随），已于第十一轮
真实链路验收通过（`generation` 165→166、200 OK）。因此本端点**不再承担解阻职责**，
保留为运维工具，适用场景是「substrate 侧有 store 不认识的数据、需要让 store 反向认领」
这类人工介入，例如历史脏数据排查、迁移期对账。

不回滚它的理由：`substrate → store` 这个方向确实**缺少不依赖 room 的入口**
（forcesave / onlyoffice-callback / recovery-cases 都要 room_id，而 room 由 materialize
创建），这个能力缺口与 500 是否修复无关，独立成立。

🔴 **不得**把它接进常规链路（如 materialize 失败时自动 adopt）：那会让 store 与 substrate
互相认领 ⇒ 谁是权威失去定义，也就消灭了方向 C 的前提。

═══ 为什么需要它（原始动因，已被 C 取代的那部分保留作记录）═══

三个取数方向里，`substrate → store` 此前**没有不依赖 room 的入口**。
当 materialize 因 `roundtrip_projection_mismatch` 恒 500 时，用户被彻底锁死。

本端点让 store **认领** substrate 当前受管区的全部行：
`intended ⊇ extracted` ⇒ `extra = 0` ⇒ materialize 恢复 200，且**不删任何数据**
（多余行显示在 HTML 侧，由审计师判断后手工删）。R1 已由离线 harness 钉死
（`_d4p_adopt_selfheal`：base=substrate + projection=substrate 自反读 ⇒ materialize
1 趟不插行、extra=0；变异组删一行恰得该行字段数的 extra）。

═══ 与 OO callback 的关系（避免第二真源）═══

「按 provider 分发、逐 store item merge 后写回 checklist」这件事与 OO callback 落地
完全同构，差别只在 projection 的来源。故落库统一走 `store_mirror.mirror_projection_into_store`
（OO callback 的 `_mirror_store_backed_if_needed` 也转发它）。本模块只负责：
定位并准入 published substrate → extract → 调 store_mirror。

🔴 fail-closed（替代 OoToHtmlCoordinator 的 incoming 准入门，见 spec design §3.1）：
  - substrate 必须是 **已发布**（`resolution.resolve(intent=materialize)` 只解析已发布
    representation；解析失败 / 文件缺失 一律拒，**不得降级成空 projection = 清空整表**）；
  - 并发保护：`expected_revision` 与服务端不符 → 冲突（替代 fence）；
  - 可回滚 + 审计：覆盖前留存原值、写审计日志。

═══ spec workpaper-sync-adopt-overwrite-and-refresh-source（Task 6.1 / 6.2）═══

Requirements 3.1 / 3.2 / 3.4 / 4.4 · ADR-AOS-003（dry_run 与真实执行共用同一计划纯函数）

**Task 6.1**：`dry_run` 不再只报 substrate 逐表行数，改为返回完整 `OverwritePlan`
（两侧逐表行数 + 逐 item 三清单与四个计数 + `plan_digest` + 显式跳过清单）。
🔴 **只有一处算法**：:func:`compute_plan_for_adopt` 是 dry_run 与真实执行**共同**的唯一
计划来源（它转发 `adopt_overwrite_compute.compute_overwrite_plan`），
摘要可信不靠「两处算出同样的数」，靠只有一处能算。

🔴 **已删除的两个私有函数（指针注释，勿重造）**：

* `_dry_run_summary` —— 被 :func:`_plan_wire_form` 取代（Task 6.1 的字面要求）；
* `_baseline_row_counts` —— substrate 逐表行数现由 `plan.substrate_rows_by_table` 供出。
  两者口径**有实质差别**且这正是删它的理由：旧函数用 `len(ids or ())` 数**原始**序列长度，
  而计划侧用 `_declared_identities` 数**去重后**的身份数 —— 两处并存必有一天不等，
  而不等的那天 `substrate_rows_by_table` 与 added/updated 的集合运算会对不上。
  🔴 `adopt_overwrite_compute` 的 `_row_keys_of` / `compute_overwrite_plan` 两处 docstring
  与 `adopt_overwrite_plan.OverwritePlan` 的 docstring 仍按「同源 / 本来就是」引用
  `_baseline_row_counts` 与 `_dry_run_summary` —— 那是**历史引用**，落点即本注释。
  未顺手改那三处的理由：那两个函数的源码是 Task 4.4 / 4.6 变异测试的锚点宿主
  （`AOC.compute_overwrite_plan` / `AOC._normalise_reasons` 等，判据含「锚点恰 1 次」），
  为行文准确去动锚点宿主的源码是拿假绿风险换措辞。

**Task 6.2**：新增三个 domain 错误类（与既有三个同风格，见其 `error_code`）与 `plan_digest`
校验。🔴 校验点在**任何写之前**：客户端确认的那份计划与服务端将执行的必须是同一份
（Requirement 3.4）。

**Task 6.3**（Requirements 1.1 / 1.2 / 3.5）：删除侧应用 + 提交前复读比对，落点是伴生模块
`adopt_overwrite_apply`（本文件只接线）。三件事按这个顺序，**顺序不可调换**：

1. `mirror_projection_into_store(..., commit=False)` —— 既有，追加 + 更新 + 幽灵行门；
2. `apply_overwrite_deletions(...)` —— 删除侧 prune + 幽灵行**观测** + 经
   `ghost_dropped_by_item` 回喂重算计划；
3. `_snapshot_store(...)` 复读 + `verify_applied_plan(...)` 逐 item / 逐分区比**身份集合**，
   不符即抛 :class:`AdoptPlanVerificationError` ⇒ 既有 `except Exception` 回滚整个事务。

🔴 为什么删除侧不能前置：清 base 会让 projection 每一行都变成「本次新增身份」⇒ 幽灵行门
全面生效 ⇒ 锚点业务名为空的行整批被剔除，「覆盖」变成大面积静默少写（ADR-AOS-001 否决
方案 3 的实证理由，探针用例 B 与 E 是直接证据）。

**Task 6.4 / 6.5**（Requirements 1.8 / 3.6 / 6.7 / 6.9）：`changed_item_count` 改由 plan 供出
（`changed_items_from_plan(applied.plan)`）；审计 details 追加 `rows_deleted_by_item` /
`plan_digest` / `skipped_items`。🔴 `_diff_snapshots` **保留但降级** —— 唯一用途是与 plan 口径
取**并集**得出回滚快照覆盖面（`rollback_snapshot_items`，两个口径的盲区不重合）。
四个纯函数与三条裁定全部落在 `adopt_overwrite_apply` 末尾那一节，本模块只接线。

🔴 **本模块不 commit**（平台铁律：service 只 flush 不 commit 的唯一例外是本函数末尾那一处
统一 commit —— 它是 adopt 的事务边界，改动前后不变；新增代码一律不碰事务）。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Final, Mapping

import sqlalchemy as sa

from app.services.workpaper_sync.adopt_overwrite_apply import (
    apply_overwrite_deletions,
    audit_details_for_applied,
    changed_items_from_plan,
    rollback_snapshot_items,
    skipped_items_wire,
    verify_applied_plan,
)
from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import (
    OverwritePlan,
    OverwritePlanShapeError,
    RowReader,
    SkipReason,
)
from app.services.workpaper_sync.adopt_row_reader import (
    RowReaderResolution,
    diagnose_row_reader,
)


class AdoptSubstrateError(Exception):
    """本模块的 domain 错误基类；router 映射成 4xx（fail visible）。"""

    error_code = "adopt_substrate_failed"


class AdoptContractRequiredError(AdoptSubstrateError):
    error_code = "adopt_contract_required"


class AdoptSubstrateNotPublishedError(AdoptSubstrateError):
    """无已发布 substrate 可采纳（缺 pointer / 文件缺失）——绝不降级成空覆盖。"""

    error_code = "adopt_substrate_not_published"


class AdoptRevisionConflictError(AdoptSubstrateError):
    """客户端 expected_revision 与服务端当前 content_revision 不符（并发保护）。"""

    error_code = "adopt_revision_conflict"


# ═══════════════════════════════════════════════════════════════════════════════
# Task 6.2 新增的三个 domain 错误类
#
# 🔴 `error_code` 命名风格**照既有三个**（不是照 `AdoptXxxError` 的字面推测）：
#   `AdoptContractRequiredError`      → `adopt_contract_required`
#   `AdoptSubstrateNotPublishedError` → `adopt_substrate_not_published`
#   `AdoptRevisionConflictError`      → `adopt_revision_conflict`
# 规则 = 类名去掉 `Error` 后 CamelCase → snake_case，**不加**任何后缀；
# 唯一例外是基类 `AdoptSubstrateError` → `adopt_substrate_failed` —— 它的类名去 `Error`
# 后只剩「主语」没有「状态词」，故补 `_failed`。因此 `AdoptPlanVerificationError`
# （`verification` 是动作名不是状态词）同样补 `_failed`，与基类同一条规则；
# 另两个类名自带状态词（`mismatch` / `unreadable`）⇒ 不补。
# 这一节的三个 error_code 与 design §4.2 的三行逐字相同。
# ═══════════════════════════════════════════════════════════════════════════════


class AdoptPlanDigestMismatchError(AdoptSubstrateError):
    """客户端回传的 `plan_digest` 与服务端重算值不符 → 409（Requirement 3.4）。

    语义与 `AdoptRevisionConflictError` 正交：revision 管「表单整体版本」，digest 管
    「用户在弹窗上看到的那份增删清单」。substrate 侧换了一版、或别人改了 store 的某几行，
    revision 可能没变而计划已变 ⇒ 只靠 revision 会让用户按着旧摘要确认一份新计划。
    """

    error_code = "adopt_plan_digest_mismatch"


class AdoptStorePayloadUnreadableError(AdoptSubstrateError):
    """某 store item 的载荷不可解析为行对象数组 → 422（Requirement 4.4）。

    🔴 **不得当成零行处理**：那会让「载荷坏了」伪装成「这张表本来就没有行」，
    删除侧随即把 substrate 的全部身份报成 `rows_added`（而 merge 什么也不会加）。

    🔴 **本类的 `item_id` 是它存在的全部理由**：Requirement 4.4 逐字要求「给出该 item 的
    item_id」，而原生异常的文案**并非都带** item_id —— `adopt_overwrite_plan`
    `_reject_unreadable_payload` 那条兜底文案就不带（Task 3.6 的
    `test_aos_property_unreadable_payload.M1_PLAN_RED_REASON` 已把该现状登记在案）。
    ⇒ 本类在**调用点**按 item 包装，不靠异常类型学甄别（原生类型异构：引擎
    `RowTableStorePayloadError(Exception)` / 多数 provider `StorePayloadError(SyncDomainError)` /
    `phase5_d4_customer_structure` 的 `StorePayloadError(ValueError)`，按类型分流必漂）。
    """

    error_code = "adopt_store_payload_unreadable"

    def __init__(self, message: str, *, item_id: str = "") -> None:
        super().__init__(message)
        #: 出问题的 store item。**必须**能被调用方原样读出（响应 / 日志定位用）。
        self.item_id = str(item_id or "")


class AdoptPlanVerificationError(AdoptSubstrateError):
    """提交前复读的实际落库结果与 Overwrite_Plan 不符 → 500 并回滚（Requirement 3.5）。

    🔴 **Task 6.3 已接线**：唯一 raise 点在 :func:`compute_adopt_substrate` 的复读比对处
    （在统一 commit **之前**），抛出后由同函数的 `except Exception: rollback; raise` 回滚整个
    事务；router 侧有专属 `except` 映成 **500**，且该分支**必须排在兜底
    `except AdoptSubstrateError` 之前** —— 它是后者的子类，放后面永远进不去（会被映成 422）。

    为什么是 500 而不是 4xx：复读不符意味着「计划与落库结果对不上」= 服务端自身不一致
    （声明漂移 / merge 语义变化 / 并发删除），不是用户能改输入重试的事。
    """

    error_code = "adopt_plan_verification_failed"


async def _resolve_published_substrate(
    *, resolution: Any, project_id: uuid.UUID, wp_id: Any, entry_id: str, contract: Any
) -> tuple[Path, str, str]:
    """定位当前**已发布** substrate。失败一律抛（fail-closed），返回 (path, sha256, adapter_id)。

    与 `store_projection_response._overlay_with_published_substrate` 同一解析口径：
    `ResolutionIntent.materialize` 只解析已发布 representation，天然排除 incoming/room。
    """
    from app.services.workpaper_sync.resolution import (
        EntryPointerMissingError,
        ResolutionIntent,
    )

    try:
        resolved = await resolution.resolve(
            intent=ResolutionIntent.materialize,
            project_id=project_id,
            wp_id=wp_id if isinstance(wp_id, uuid.UUID) else uuid.UUID(str(wp_id)),
            entry_id=str(entry_id),
            expected_document_type=str(contract.document_type),
        )
    except EntryPointerMissingError as exc:
        raise AdoptSubstrateNotPublishedError(
            f"entry {entry_id!r} 尚无已发布底稿可采纳（无 representation 指针）——"
            "不能以空内容覆盖表单（那会清空整表）"
        ) from exc

    substrate = Path(resolved.artifact_path)
    if not substrate.is_file():
        raise AdoptSubstrateNotPublishedError(
            f"entry {entry_id!r} 的已发布底稿文件缺失（{resolved.artifact_relative_path}）——"
            "拒绝以空内容覆盖表单"
        )
    return substrate, str(resolved.artifact_sha256), str(resolved.adapter_id)


async def _current_revision(session: Any, wp_id: Any) -> int:
    return int(
        (
            await session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(wp_id)},
            )
        ).scalar_one()
    )


async def compute_adopt_substrate(
    *,
    session: Any,
    project_id: uuid.UUID,
    wp_id: Any,
    entry_id: str,
    registration: Any,
    resolution: Any,
    expected_revision: int | None,
    dry_run: bool,
    expected_plan_digest: str | None = None,
) -> dict[str, Any]:
    """反向收敛主链。dry_run=True 时只算差异不落库（供弹窗差异摘要）。

    调用方（router 端点）负责 guard 与状态码映射；本函数只做业务并抛 `AdoptSubstrateError`。

    :param expected_plan_digest: 客户端从 dry_run 拿到并回传的 `plan_digest`；
        非空且与服务端重算值不符 ⇒ `AdoptPlanDigestMismatchError` → 409（Requirement 3.4）。
        dry_run 分支**不**校验它（那一趟本来就是去取新 digest 的）。
    """
    contract = registration.contract
    if contract is None:
        raise AdoptContractRequiredError(
            f"entry {entry_id!r} 的 registration 没有 approved contract —— 无契约无从 extract"
        )

    # ── 并发保护（替代 fence）：先对 revision，再干活 ──────────────────
    current_rev = await _current_revision(session, wp_id)
    if expected_revision is not None and int(expected_revision) != current_rev:
        raise AdoptRevisionConflictError(
            f"表单版本已变化（客户端 {expected_revision} ≠ 服务端 {current_rev}）——"
            "请刷新后重试，避免覆盖他人改动"
        )

    # ── 准入 + extract（published substrate 的纯函数）───────────────────
    substrate, substrate_sha, adapter_id = await _resolve_published_substrate(
        resolution=resolution,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        contract=contract,
    )
    import asyncio

    baseline = await asyncio.to_thread(
        registration.adapter.extract, artifact=substrate, contract=contract
    )

    # ── Overwrite_Plan：dry_run 与真实执行**共用**这一处（ADR-AOS-003）───────
    # 🔴 `store_payloads` 与下方 `before_snapshot` 是**同一次**读取 ⇒ 计划算在哪份 store 状态
    #    上、回滚快照存的就是哪份，两者天然一致；分两次读会留下「计划与快照错版」的窗口。
    plan_inputs = census_plan_inputs(registration)
    store_payloads = await _snapshot_store(
        session, wp_id=wp_id, item_ids=plan_inputs.item_ids
    )
    plan = compute_plan_for_adopt(
        baseline=baseline, store_payloads=store_payloads, plan_inputs=plan_inputs
    )

    # ── dry_run：只算「会改多少行」，不落库、不留存、不审计 ─────────────
    if dry_run:
        return {
            "dry_run": True,
            "substrate_sha256": substrate_sha,
            "expected_revision": current_rev,
            **_plan_wire_form(plan),
        }

    # 🔴 digest 校验必须在**任何写之前**（Requirement 3.4）。
    verify_plan_digest(plan, expected=expected_plan_digest)

    # ── 落库前留存原值（可回滚）+ 审计 ──────────────────────────────────
    from app.services.workpaper_sync.store_mirror import mirror_projection_into_store

    before_snapshot = store_payloads

    # store_mirror 按 provider 分发 + 逐 item merge（与 OO callback 同一执行层）。
    # 🔴 `commit=False`：store_mirror 默认逐 item commit（OO callback 幂等重放可接受），
    #    但 adopt 要**原子**（Req 2.8）——中途失败不得留部分写入。故让 store_mirror 只 flush，
    #    审计留痕后由本函数**统一 commit**。若 mirror 抛异常，下方 except 回滚整个事务。
    try:
        await mirror_projection_into_store(
            session,
            adapter_id=adapter_id,
            project_id=project_id,
            wp_id=wp_id,
            merged_projection=baseline,
            commit=False,
        )

        # ── ★ Task 6.3 删除侧：**必须在 merge 之后**（ADR-AOS-001）───────────────
        # 🔴 顺序不可调换：前置清 base 会让 projection 里每一行都变成「本次新增身份」⇒
        #    幽灵行门全面生效 ⇒ 锚点业务名为空的行被整批剔除，「覆盖」变成大面积静默少写
        #    （探针用例 B 与 E 是该结论的直接证据）。后置 prune 不改变「谁是新增」的判定。
        #    幽灵行在这一步由**观测**得出（计划期不可兑现，裁定见 compute_overwrite_plan），
        #    并经 `ghost_dropped_by_item` 回喂重算 ⇒ `applied.plan` 才是最终计划。
        applied = await apply_overwrite_deletions(
            session,
            wp_id=wp_id,
            baseline=baseline,
            store_payloads=store_payloads,
            plan_inputs=plan_inputs,
            plan=plan,
        )

        # 🔴 这次读取必须在删除侧**之后**：它是复读比对（Req 3.5）的输入，也是 `rollback_snapshot`
        #    覆盖面里「字节差集」那一半的来源 —— 早读两者都看不见删除侧改动（Req 6.9）。
        after_snapshot = await _snapshot_store(
            session, wp_id=wp_id, item_ids=plan_inputs.item_ids
        )
        # ── ★ 提交前复读比对（Requirement 3.5）：逐 item / 逐分区比**身份集合** ──────
        # 🔴 不比计数：删错行但删对个数两侧计数一模一样。不符即抛 ⇒ 下方 except 回滚整个事务
        #    （业务写 / 回滚快照 / 审计三者一起回滚，不留「改了 store 却对不上计划」的中间态）。
        mismatches = [
            *applied.mismatches,
            *verify_applied_plan(
                applied.plan,
                final_payloads=after_snapshot,
                row_readers=plan_inputs.row_readers,
                item_scopes=plan_inputs.item_scopes,
                post_merge_ids=applied.post_merge_ids,
            ),
        ]
        if mismatches:
            raise AdoptPlanVerificationError(
                "提交前复读与计划不符，已回滚本次覆盖（不落库任何一半）：\n- "
                + "\n- ".join(mismatches)
            )
        # ── ★ Task 6.4：`changed` 取自 **plan**（Requirement 3.6）─────────────────
        # 🔴 不再取「覆盖前后 remark 快照差集」：design ADR-AOS-003 附注真库实测它两个方向
        #    都失真（漏报 `applied<=0 and base_rows` 那条出口 · 虚报重序列化漂移）。
        changed = changed_items_from_plan(applied.plan)
        # 🔴 Task 6.5 / Requirement 6.9：回滚快照的覆盖面取**两个口径的并集** —— plan 侧看不见
        #    被跳过的 item（删除侧跳过 ≠ merge 跳过，它们的 remark 照样被改写），字节差集侧本身
        #    不可信。并集只会让快照变大不会变小，裁定与理由见 `rollback_snapshot_items`。
        rollback_items = rollback_snapshot_items(
            plan_changed=changed,
            snapshot_changed=_diff_snapshots(before_snapshot, after_snapshot),
        )

        # 审计留痕**在统一 commit 之前**入同一事务：要么「写入 + 留痕」一起成功，
        # 要么一起回滚。绝不出现「改了 store 却没留痕」（回滚快照丢失）。
        await _record_rollback_and_audit(
            session,
            project_id=project_id,
            wp_id=wp_id,
            entry_id=entry_id,
            substrate_sha=substrate_sha,
            before_snapshot=before_snapshot,
            changed_items=changed,
            rollback_items=rollback_items,
            applied=applied,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {
        "dry_run": False,
        "substrate_sha256": substrate_sha,
        "expected_revision": current_rev,
        "changed_item_count": len(changed),
        "changed_items": changed,
    }


#: 门面**定义模块**里「本 item 的行表 table_key」声明常量名。
#:
#: 🔴 这是取**声明**不是键名兜底 —— 与 `adopt_row_reader` 取 `STORE_ITEM_ID` /
#: `ROW_IDENTITY_STORE_KEY` 同源。现读实证：三条 `declared_scopes` 为空的 item，其门面定义
#: 模块的这个常量**正是**该 provider 自己 `build_store_projection` 里
#: `row_keys={ROWS_TABLE_KEY: tuple(row_keys)}` 用的那一个（三家逐个现读确认）。
_ROWS_TABLE_KEY_CONST: Final[str] = "ROWS_TABLE_KEY"


class AdoptPlanInputs:
    """`compute_overwrite_plan` 的四样入参（item 分母 / reader / 跳过原因 / scope 覆盖）。

    刻意是**普通类不是 dataclass**：本模块无 `assert_no_mutation_surface` 的约束语境，
    而四个字段都是只读快照，用最少的代码表达即可（ponytail 原则第 6 级）。
    """

    __slots__ = ("item_ids", "row_readers", "skip_reasons", "item_scopes")

    def __init__(
        self,
        *,
        item_ids: tuple[str, ...],
        row_readers: Mapping[str, RowReader],
        skip_reasons: Mapping[str, SkipReason],
        item_scopes: Mapping[str, tuple[tuple[str, str | None], ...]],
    ) -> None:
        self.item_ids = item_ids
        self.row_readers = row_readers
        self.skip_reasons = skip_reasons
        self.item_scopes = item_scopes


def _scope_override_from_declaration(
    resolution: RowReaderResolution,
) -> tuple[tuple[str, str | None], ...]:
    """`declared_scopes` 为空的 reader ⇒ 从门面定义模块的 `ROWS_TABLE_KEY` 取声明。

    🔴 **这是 Task 6.1 的硬前提**：现算恰 **3** 条 item 的 `declared_scopes` 为空
    （`D2-detail-rows` / `D4-2-rows` / `H1-8-rows`，三者的 reader 都是裸 `_FacadeRowReader`、
    provider 无 `managed_row_table_specs`、全域 spec 索引亦无）。不接线它们就会在
    `compute_overwrite_plan._scopes_of` 当场 fail visible —— 那正是该函数 docstring
    「交给 Task 6.1 的接线前提」写明的后果。

    🔴 **有分区维度却拿不到 scope 声明时返回空元组（让 compute 当场抛），不猜 `None` 分区**：
    `section_field` 非空意味着行的分区归属由该字段决定，硬塞 `(table_key, None)` 不会触发
    `_in_scope_by_section` 的任何一条门（它只拦「无 section_field 却给了分区」这一向），
    于是真实分区的行永远匹配不上 `None` 桶 ⇒ **静默少删**。宁可报错。
    """
    if resolution.declared_scopes or resolution.reader is None:
        return ()
    if str(getattr(resolution.reader, "section_field", "") or ""):
        return ()
    owner = sys.modules.get(str(resolution.facade_module or ""))
    table_key = (
        str(getattr(owner, _ROWS_TABLE_KEY_CONST, "") or "") if owner is not None else ""
    )
    return ((table_key, None),) if table_key else ()


def build_plan_inputs(
    resolutions: Mapping[str, RowReaderResolution],
    *,
    adapter_key: str,
    adapter_reason: SkipReason | None = None,
) -> AdoptPlanInputs:
    """把逐 item 的 `RowReaderResolution` 摊成 `compute_overwrite_plan` 的入参。**纯函数。**

    :param resolutions: `item_id` → 判定结果（由 `diagnose_row_reader` 现算）。
    :param adapter_key: adapter 级原因的键（`SkipReason.no_store_item` / `import_failed`
        没有 item_id 可填 ⇒ 第一位放 adapter_id，裁定见
        `adopt_overwrite_compute._ADAPTER_LEVEL_REASONS`）。
    :param adapter_reason: adapter 级跳过原因；`None` = 无。

    🔴 **未裁决形态（`is_unruled_shape`）既不登记 reader 也不登记原因** —— 它**不是**「无行」
    （`RowReaderResolution.is_unruled_shape` docstring 逐字写明），硬塞任一 `SkipReason` 成员
    就是 Requirement 4.3 的「白名单失效条目」。不登记 ⇒ `compute_overwrite_plan` 对它当场抛
    （「既无 reader 也无跳过原因 —— 本函数不猜」）= fail visible，这正是想要的处置。
    顶层现算 **0** 例（ADR-AOS-005 采纳 R3 后棘轮基线已清成空集）。
    """
    readers: dict[str, RowReader] = {}
    reasons: dict[str, SkipReason] = {}
    scopes: dict[str, tuple[tuple[str, str | None], ...]] = {}
    for item_id, resolution in resolutions.items():
        if resolution.reader is not None:
            readers[item_id] = resolution.reader
            override = _scope_override_from_declaration(resolution)
            if override:
                scopes[item_id] = override
        elif resolution.skip_reason is not None:
            reasons[item_id] = resolution.skip_reason
    if adapter_reason is not None:
        reasons[str(adapter_key)] = adapter_reason
    return AdoptPlanInputs(
        item_ids=tuple(sorted(resolutions)),
        row_readers=readers,
        skip_reasons=reasons,
        item_scopes=scopes,
    )


def _resolve_store_provider(registration: Any) -> Any:
    from app.services.workpaper_sync.store_projection_response import (
        resolve_store_projection_provider,
    )

    return resolve_store_projection_provider(str(registration.adapter_id))


def _provider_store_item_ids(provider: Any) -> tuple[str, ...]:
    """本 entry 全部 store item —— 复用 provider 单一口径 all_store_item_ids()。"""
    fn = getattr(provider, "all_store_item_ids", None)
    if callable(fn):
        return tuple(str(x) for x in fn())
    single = str(getattr(provider, "STORE_ITEM_ID", "") or "")
    return (single,) if single else ()


def census_plan_inputs(registration: Any) -> AdoptPlanInputs:
    """现算本 entry 的计划入参：解析 provider → 逐 item 判行枚举器 → 摊成入参。

    🔴 分母走 **adopt 真实路径**（`resolve_store_projection_provider` →
    `DELIVERED_PER_ENTRY_CONTRACTS`，现算 51 adapter / 129 item），**不是**
    `store_item_registry.STORE_MERGE_REGISTRY`（42 / 113）—— 两者对 `d2.receivable_detail`
    的 provider 指向不一致，用错会让 D2 一侧只看到 1 条 item。

    判定链 L1 的两个 adapter 级结论在**本函数**产出（`adopt_row_reader` 观测不到它们）：
    `import_failed`（provider 解析抛）/ `no_store_item`（解析成功但没有 store item，
    现算 2 条：`a51.cashflow_audit` / `c2.control_test_summary`）。
    """
    adapter_key = str(registration.adapter_id)
    try:
        provider = _resolve_store_provider(registration)
    except Exception:
        return build_plan_inputs(
            {}, adapter_key=adapter_key, adapter_reason=SkipReason.import_failed
        )
    items = _provider_store_item_ids(provider)
    if not items:
        return build_plan_inputs(
            {}, adapter_key=adapter_key, adapter_reason=SkipReason.no_store_item
        )
    return build_plan_inputs(
        {
            item: diagnose_row_reader(provider=provider, store_item_id=item)
            for item in items
        },
        adapter_key=adapter_key,
    )


def _first_unreadable_item(
    store_payloads: Mapping[str, Any], row_readers: Mapping[str, RowReader]
) -> str:
    """逐 item 复读，返回**第一个**载荷读不动的 item_id；全都读得动返回空串。

    🔴 只在**错误路径**上调 —— happy path 一次都不会跑它，故「多读一遍」无成本。
    这么做是为了在原生异常不带 item_id 时仍能兑现 Requirement 4.4 的「给出该 item 的
    item_id」，而不必按异常类型甄别（原生类型异构，按类型分流必漂）。
    """
    for item_id in sorted(row_readers):
        payload = store_payloads.get(item_id)
        if payload is None:
            continue
        try:
            for _identity, _row in row_readers[item_id].iter_rows(payload):
                pass
        except Exception:  # noqa: BLE001 —— 本函数就是在找「哪一个会抛」
            return item_id
    return ""


def compute_plan_for_adopt(
    *,
    baseline: Any,
    store_payloads: Mapping[str, Any],
    plan_inputs: AdoptPlanInputs,
    ghost_dropped_by_item: Mapping[str, tuple[str, ...]] | None = None,
) -> OverwritePlan:
    """**dry_run 与真实执行共用的唯一计划入口**（Requirement 3.1 / ADR-AOS-003）。

    只做两件事：转发 `adopt_overwrite_compute.compute_overwrite_plan`，
    以及把「载荷不可解析」的原生异常翻译成 :class:`AdoptStorePayloadUnreadableError`（422）。

    :param ghost_dropped_by_item: **观测到**被幽灵行门剔除的身份（Task 6.3 在 merge 之后回喂）。
        计划期恒空 —— 预测幽灵行就是复现引擎判据 = 第二真源，裁定见
        `adopt_overwrite_compute.compute_overwrite_plan` 的 docstring。
        🔴 回喂走**本门面**而不是直接调纯函数：「只有一处算法」对第二次计算同样成立。

    🔴 `OverwritePlanShapeError` **原样穿透不翻译**：它的 docstring 明写是**编程错误**
    （500 + 堆栈），而「store 里存着一份非法 JSON」是**数据**问题 —— 翻译它会把归类搞反，
    让声明漂移 / 分母漏登记这类必须修代码的缺陷伪装成「用户可重试」。
    """
    try:
        return compute_overwrite_plan(
            substrate_projection=baseline,
            store_payloads=store_payloads,
            row_readers=plan_inputs.row_readers,
            skip_reasons=plan_inputs.skip_reasons,
            item_scopes=plan_inputs.item_scopes,
            ghost_dropped_by_item=ghost_dropped_by_item,
        )
    except OverwritePlanShapeError:
        raise
    except Exception as exc:
        item_id = _first_unreadable_item(store_payloads, plan_inputs.row_readers)
        raise AdoptStorePayloadUnreadableError(
            f"store item {item_id or '<未能定位>'!r} 的载荷无法解析成行对象数组"
            f"（{type(exc).__name__}: {exc}）—— 拒绝当成零行处理：那会把 substrate 的全部行"
            "报成新增而实际一行都不会写",
            item_id=item_id,
        ) from exc


def _plan_wire_form(plan: OverwritePlan) -> dict[str, Any]:
    """`OverwritePlan` → 响应体（dry_run 与真实执行**同构**，前端一套渲染）。

    🔴 四个计数**显式给出**（Requirement 3.2 逐字要求「四个计数」），尽管它们是
    `len(清单)` 的派生量 —— Task 10.1 要求「数字全部取自响应字段，前端不自行重算」，
    前端自己数一遍就是第二真源。计划侧仍不存字段（派生自清单），两处的口径因此不可能不等。

    🔴 `changed_item_count` **刻意不在这里**（Task 6.4 落地后仍然如此）：它是**真实执行**
    分支的产出（「这次真的动了几个 item」），而 dry_run 那一趟什么都没动 —— 在摘要里给一个
    「将会动 N 个」会和 `deltas` 里逐 item 的清单构成第二口径，前端两处数不一致时无从判谁对。
    真实执行分支由 `changed_items_from_plan(applied.plan)` 供出（同一份 plan，不是快照差集）。
    """
    return {
        "plan_digest": plan.digest,
        "store_row_count": plan.store_row_count,
        "substrate_row_count": plan.substrate_row_count,
        "store_rows_by_table": dict(plan.store_rows_by_table),
        "substrate_rows_by_table": dict(plan.substrate_rows_by_table),
        "deltas": [
            {
                "item_id": delta.item_id,
                "table_key": delta.table_key,
                "row_section": delta.row_section,
                "rows_added": list(delta.rows_added),
                "rows_deleted": list(delta.rows_deleted),
                "rows_updated": list(delta.rows_updated),
                "rows_ghost_dropped": list(delta.rows_ghost_dropped),
                "rows_added_count": delta.rows_added_count,
                "rows_deleted_count": delta.rows_deleted_count,
                "rows_updated_count": delta.rows_updated_count,
                "rows_ghost_dropped_count": delta.rows_ghost_dropped_count,
                "skipped_reason": (
                    delta.skipped_reason.value if delta.skipped_reason is not None else None
                ),
            }
            for delta in plan.deltas
        ],
        # 🔴 投影走**同一个**门面：审计 details 也要这份清单，两处各写一遍就是两处口径。
        "skipped_items": skipped_items_wire(plan),
    }


def verify_plan_digest(plan: OverwritePlan, *, expected: str | None) -> None:
    """客户端回传的 `plan_digest` 必须与服务端重算值逐字符相等（Requirement 3.4）。

    :param expected: 客户端回传值；`None` / 空串 = 未回传 ⇒ **不校验**（兼容运维直调）。

    🔴 **调用点必须在任何写之前**：这条校验的全部意义是「用户确认的就是将执行的」，
    放到写之后就只剩一个漂亮的错误消息。
    """
    wanted = str(expected or "").strip()
    if not wanted:
        return
    actual = plan.digest
    if wanted != actual:
        raise AdoptPlanDigestMismatchError(
            f"两侧已变化：你确认的差异摘要（{wanted[:12]}…）与服务端当前重算值"
            f"（{actual[:12]}…）不符 —— 请重新查看差异后再执行，避免按旧摘要执行新计划"
        )


async def _snapshot_store(
    session: Any, *, wp_id: Any, item_ids: tuple[str, ...]
) -> dict[str, str | None]:
    """取给定 store item 的当前 remark（覆盖前后各一次，用于 diff 与回滚）。

    🔴 item 分母由调用方传入（`AdoptPlanInputs.item_ids`），**不在本函数再解析一次** ——
    计划与回滚快照必须建立在同一份 item 清单上，否则「计划报了 5 个 item、快照只存了 4 个」
    这种漏存没人能发现。
    """
    snap: dict[str, str | None] = {}
    for item in item_ids:
        row = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                ),
                {"wp": str(wp_id), "item": item},
            )
        ).scalar_one_or_none()
        snap[item] = str(row) if row is not None else None
    return snap


def _diff_snapshots(
    before: dict[str, str | None], after: dict[str, str | None]
) -> list[str]:
    """返回 remark 发生变化的 item_id（有序去重）。"""
    keys = sorted(set(before) | set(after))
    return [k for k in keys if before.get(k) != after.get(k)]


async def _record_rollback_and_audit(
    session: Any,
    *,
    project_id: uuid.UUID,
    wp_id: Any,
    entry_id: str,
    substrate_sha: str,
    before_snapshot: dict[str, str | None],
    changed_items: list[str],
    rollback_items: list[str],
    applied: Any,
) -> None:
    """留存被覆盖的原值（可回滚）+ 写审计日志。复用既有 hash-chain 审计留痕，不新造表。

    :param changed_items: **plan 口径**的有变更 item（Task 6.4 / Requirement 3.6）。
    :param rollback_items: 回滚快照要留原值的 item = plan 口径 ∪ 字节差集（Task 6.5 /
        Requirement 6.9）。🔴 它**不等于** `changed_items` —— 被跳过的 item 在 plan 口径里看不见
        而 merge 照样改写了它们的 `remark`，只按 `changed_items` 存快照会当场丢掉那些原值。
    :param applied: `AppliedOverwrite` —— details 的三个追加字段全部从它派生。

    🔴 event_type `workpaper_sync_adopt_substrate` **有意**不进 `EVENT_TYPE_SCHEMAS`：
    `validate_event_type_details` 对未登记 event_type 跳过 schema 校验（正常写入 + 维护
    hash chain）。这与 spec D 的教训一致——不同操作用**独立** event_type，不复用他人的。
    🔴 Task 6.5 **不得**顺手给它登记 schema（登记后三个追加字段就变必填，而它们是「有就写」的
    诊断信息），也不得复用别人的 event_type。
    rollback_snapshot 即被覆盖的原值，误操作可据此恢复（可追溯，不新造回滚表）。
    """
    import json

    from app.services.audit_log_helper import append_audit_log

    rollback_payload = {item: before_snapshot.get(item) for item in rollback_items}
    await append_audit_log(
        session,
        {
            "user_id": None,
            "project_id": project_id,
            "action": "workpaper_sync.adopt_substrate",
            "resource_type": "workpaper_entry",
            "resource_id": str(entry_id),
            "details": {
                "event_type": "workpaper_sync_adopt_substrate",
                "wp_id": str(wp_id),
                "entry_id": str(entry_id),
                "substrate_sha256": substrate_sha,
                **audit_details_for_applied(applied),
                "changed_item_count": len(changed_items),
                "changed_items": changed_items,
                "rollback_snapshot": json.dumps(rollback_payload, ensure_ascii=False),
            },
        },
    )
