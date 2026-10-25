# ROI-6 锁临界区收窄 — Evidence（2026-10-07）

## 改动摘要

per-room `lock_room_oo_apply` 的临界区从「状态转移 + CPU 重段 + fence + DB 事务 + 后处理」
收窄为「DB 事务 + 后处理」。CPU 重段（materialize + extract + roundtrip + unmanaged verify +
structure_hash + artifact publish，D4 实测 40–69s）移到锁外。

### 改动文件

| 文件 | 改动 |
|------|------|
| `content_mutation.py` | 新增 `StagedCommit`（frozen dataclass）、`_ReplayHit`（控制流异常）、`stage_for_commit`（前半段）、`commit_staged`（后半段）；原 `commit` 不变 |
| `oo_to_html.py` | `_apply_settled` 拆为 `_prepare_and_stage`（锁外）+ `_apply_committed`（锁内）；删 `_apply_settled_locked` |
| `test_task26_oo_to_html.py` | `_SETTLED_BRANCH_METHODS` 更新为三段（`_apply_settled` / `_prepare_and_stage` / `_apply_committed`） |
| `test_roi6_lock_narrowing.py` | **新增** 15 个结构守卫 |

## 安全性三层保障

1. **staging 隔离**：CPU 段写到 UUID-唯一的 staging 目录，并行 apply 的文件产物互不冲突。
2. **CAS 乐观锁**：`_commit_once` 内 `bump_content_revision WHERE = :expected` 只放一个过。
3. **fence 在锁内**：`fence.before_write` 在 `_commit_once` 的 wp advisory xact lock 内执行。

## 焦点回归

| 测试套件 | 结果 |
|---|---|
| test_task26_oo_to_html.py | 134 passed |
| test_task26_oo_to_html_pg.py | 99 passed |
| test_d4_29_customer_detail_sync.py | 26 passed |
| test_bp61_row_uuid_instantiation_gate.py | 17 passed / 1 预存失败（git stash 归因） |
| test_task37_excel_extract.py | 106 passed |
| test_task38_excel_materialize.py | 93 passed |
| test_projection_structure_hash_semantics.py | 14 passed |
| **test_roi6_lock_narrowing.py** | **15 passed** |
| **总计** | **504 passed / 0 本轮新增失败** |

## 守卫覆盖（test_roi6_lock_narrowing.py）

- **TestLockNarrowingMethodTopology**（5 例）：旧方法删除、新方法存在、AST 验证 prepare→lock→committed 顺序、prepare 不取锁、committed 不调 stage
- **TestTwoPhaseCommitApi**（6 例）：StagedCommit frozen、stage_for_commit/commit_staged/commit 存在、_ReplayHit 不继承 ContentMutationError、_ReplayHit 携带 receipt
- **TestLockSemanticsInvariant**（3 例）：SQL 级验证会话级 pg_advisory_lock（非事务级）、finally 释放、keying 不变
- **TestMutationProof**（1 例）：删 lock 后拓扑判据确实红

## 预期收益

锁内串行窗口从 **~69s**（CPU 重段 + fence + DB 事务 + 后处理）缩小到 **<1s**（DB 事务 + 后处理）。
多人同编同一底稿时，第二个人不再排队等第一个人的 CPU 段完成。

## 待验：真实 PG 多人并发 → ✅ 2026-10-07 验证通过

用两个独立 asyncpg 连接（非共享会话）在真实 PG 16 上验证四个安全性质：

| 性质 | 结果 | 关键数据 |
|---|---|---|
| 同 room 互斥 | ✅ PASS | B 被阻塞 2s 超时；A 释放后 B 立即取到锁（0.004s） |
| 不同 room 并行 | ✅ PASS | 不同 room 取锁无阻塞（0.001s） |
| CPU 段重叠 | ✅ PASS | 两个 1s CPU 段重叠 **1.013s**；总耗时 **1.231s**（串行模型需 2.2s） |
| revision CAS 拒绝 | ✅ PASS | A CAS UPDATE 1 成功；B 同 expected_revision CAS UPDATE 0 正确拒绝 |

性质 3 的时间线证实了 ROI-6 的核心收益：
- `A_cpu_start` 和 `B_cpu_start` 在 0.000s 同时开始
- `A_cpu_end` 和 `B_cpu_end` 都在 ~1.01s 结束（1s CPU 段完全重叠）
- `A_lock_acquired` 在 1.015s，`B_lock_acquired` 在 1.123s（B 等 A 的 commit 段 ~0.1s）
- 总耗时 1.231s = 1s CPU 段 + 2×0.1s 串行 commit + 调度开销

探针脚本 `_probe_roi6_concurrent_advisory_lock.py` 已按 `_` 前缀规约用完即删。
