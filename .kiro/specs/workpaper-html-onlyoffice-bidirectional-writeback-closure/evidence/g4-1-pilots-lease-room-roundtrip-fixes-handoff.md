# G4-1 四 pilot §9.6 重取证：三处生产缺陷修复交接（待收口方统一提交）

> 状态：**已在工作树磁盘落地并验证，未 commit**（多会话共享工作树，避免夹带并发的 G4-0d/G4-1/G4-2 在途改动）。
> 提交建议：由持有 `work/2026-09-11-...` 工作树的收口方在统一提交 G4 系列时，连同本记录列出的 hunk 一并提交。
> 采集日期：2026-09-12。验证栈：前端 3030 / 后端 9980 / OnlyOffice 8080 / 库 `audit_platform`。

## 背景

在 post-delete（G4-2 删 `/d2-sync/*`）源码上重跑四个 pilot 的 §9.6 真实 OO 往返 Playwright（H1/G7/B60/D2-2）时，逐一暴露并修复了三处**同类真实生产缺陷**——都是「过期资源 / 空值边界没有回收/容忍路径」，此前无人发现，任何用户上次编辑会话超时后都会永久卡死对应 room。

四 pilot 最终全部 `1 passed`，DB 逐一印证（source=onlyoffice / oo_to_html / op+app applied / revision+1）：

| pilot | e2e | 本轮 revision |
|---|---|---|
| H1-8 | 1 passed (2.9m) | 8 |
| G7 SOE | 1 passed (2.8m) | 11 |
| B60-1 | 1 passed (2.7m) | 7 |
| D2-2 | 1 passed (3.7m) | 33 |

## 三处修复（精确位置 + 识别锚点）

### 修复 1：僵尸 participant lease 回收

- **文件**：`backend/app/services/workpaper_sync/rooms.py`
- **改动**：新增方法 `RoomService.expire_participant(...)`（锚点：`async def expire_participant`、docstring「纯 TTL 到期」）。把 `active`/`closing` 且纯 TTL 过期（`revoked_at IS NULL AND left_at IS NULL AND expires_at <= now`）的 lease 推到 `expired` 终态，**不**旋转 generation/fence、**不**取消 outstanding requests；对已终态幂等返回。
- **文件**：`backend/app/services/workpaper_sync/materialize_coordinator.py`
- **改动**：`_join_or_reuse_participant`（锚点：`已被撤销/离开`、`await self._rooms.expire_participant(room_id=room.id, participant_id=live.id)`，约 `@@ -2298`）。把原来「revoked 或过期」合并拒绝的单一分支**拆成两类**：显式撤销/离开继续拒（旧会话必须重开）；纯 TTL 过期则先 `expire_participant` 回收、再 `join_participant` 重建。
- **缺陷**：唯一约束 `uq_wpoop_active_lease((room_id,user_id) WHERE state IN ('active','closing'))` 挡住新建，而过期 lease 无回收路径 ⇒ 用户此后永久 403 `materialize_authorization_denied`。
- **守卫**：`backend/tests/workpaper_sync/test_task21_room_service_pg.py`
  - `test_pure_ttl_expired_lease_is_reclaimed_and_user_can_rejoin`
  - `test_explicitly_revoked_lease_is_not_reclaimed_as_ttl_expiry`
  - 采集阶段 `lease_reclaim` / `lease_reclaim_revoked`（snap key `lease_reclaim`）
- **变异 RED 实证**：删掉「置 expired」→ 回收无效 → 重建撞唯一约束 → 守卫准确打红（IntegrityError）。
- **真库实证**：对真实僵尸 lease `64a35469`（room `de3df2bf`）走生产路径回收成 `expired` 并 commit（回收前 join 被唯一约束拒、回收后 fence/generation 不变）。

### 修复 2：僵尸 room 续期

- **文件**：`backend/app/services/workpaper_sync/rooms.py`
- **改动**：`open_or_reuse_room` 复用分支（锚点：`room 仍处于可用 state 但 TTL 已过`、`renew_ttl = ttl if ttl is not None else timedelta(hours=8)`）。复用一个 state 合法（`opening/active/close_barrier`、非 refresh_required）但 `expires_at` 已过的 room 时**续期**（`expires_at = now + ttl`），不旋转 generation/doc_key/fence/base_version。
- **缺陷**：`open_or_reuse_room` 复用时只看 state/refresh_required、**不看 `expires_at`**，而 forcesave 资格门 `assert_can_initiate_request` 判 `expires_at <= now → RoomNotWritableError`。过期 room 被复用并下发 descriptor（能编辑、能在 OO 改值），一按保存却 422 `room_not_writable`，且 `uq_wpoor_generation` 禁止同代际重建 ⇒ room 永久卡死。
- **守卫**：`test_task21_room_service_pg.py::test_open_or_reuse_room_renews_an_expired_reusable_room`（采集阶段 `room_renewal`，用 `other_room` 隔离，断言 `reused_same_room / now_future / generation_unchanged / doc_key_unchanged / fence_unchanged`，且续期后不再因 TTL 过期被资格门拒）。
- **变异 RED 实证**：短路续期赋值 → `now_future=False` → 守卫打红。
- **真库实证**：对真实 room `de3df2bf` 走生产 `open_or_reuse_room` 续期（same_room=True、gen 不变、expires_at 从 09-11 续到将来）并 commit。

### 修复 3：roundtrip 空 enum/text 误判

- **文件**：`backend/app/services/workpaper_sync/content_mutation.py`
- **改动**：
  - 新增模块级 helper `_is_roundtrip_empty(value)`（锚点：`def _is_roundtrip_empty`），仅把 `None` 与空白字符串判为空；数值 `0`/`False`/`Decimal("0")` 不算空。
  - `_assert_roundtrip_equivalent` 比较循环（锚点：`_is_roundtrip_empty(mine.value) and _is_roundtrip_empty(theirs.value)`）在 `values_equal` 之前增加短路：仅当**两侧都为空表示**时视为等值。
- **缺陷**：提交空 enum/text（`""`）写进 OOXML 得空单元格，extract 反读得 `None`，`values_equal('', None, enum)` 判不等 ⇒ D2 大表任一空 enum 行 materialize 恒 500 `roundtrip_projection_mismatch`。不改全局 `merge.normalize_value`（那里刻意区分 `""`/`None`/`MISSING`，merge 场景「清空」与「从未设置」有别）。
- **守卫**：`backend/tests/workpaper_sync/test_task15_content_mutation.py`
  - `test_roundtrip_empty_string_and_none_are_equivalent`（两方向 + 空白串）
  - `test_roundtrip_empty_vs_real_value_is_still_rejected`（一侧空一侧真实值仍拒）
- **变异 RED 实证**：短路 `if False and ...` → `'' vs None` 判不等 → 守卫打红。

## 验证汇总

- 单测：`test_task21_room_service.py` + `test_task21_room_service_pg.py` + `test_task25_materialize_coordinator.py` + `test_task15_content_mutation.py` 合计 **350 passed**。
- 变异检验：三处修复各短路一次，对应守卫准确打红，还原后复绿（承重确认）。
- 真栈 e2e：四 pilot §9.6 往返全 `1 passed`，DB 三谓词（application applied / operation terminal bound / onlyoffice content version）逐一印证。

## 与并发改动的关系

这三处修复与工作树里 G4-0d/G4-1/G4-2 的并发改动共存于同一批文件（`rooms.py` / `materialize_coordinator.py` / `content_mutation.py`），同属双向回写工作包，语义上互补不冲突（本修复解除的正是四 pilot 真实往返的最后阻塞）。收口方提交时可整体纳入 G4 系列。
