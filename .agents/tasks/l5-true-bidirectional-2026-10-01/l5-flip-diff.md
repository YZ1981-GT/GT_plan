# L5 manifest 翻转 flip-diff（T6）

spec: `l5-true-bidirectional-2026-10-01` · T6。两区方案（用户裁决 A）。

## 基点与 digest
- 干净 worktree `.worktrees/l5-flip`（临时分支 `work/2026-10-02-l5-flip`），基于主 HEAD `55bd1d1d4`
  （含 L8/L7/L6 翻转），只叠加本 spec 的 **L5 host（GtL5LongTermPayables.vue）+ overlay L5 override** 两处改动。
- node_modules 经 junction 指向主树（worktree 空装，仅为 discover-mounts 的 @typescript-eslint/parser）。
- `approved_source_digest`：`f85f682e3ae1…`（L8 轮）→ **`b165847f6ae14ec9f4d0044c406abcbef06645f6f5311a558626921fd48abc97`**（本轮重算，源 mount 因 L5 host 加 OO 挂载块而变）。
- `manifest_digest`：`cf778b66…` → `fa7158fb…`；`source_digest`：`86a21603…` → `0d9dc468…`；baseline_digest `205593f0…` → `a052c868…`。

## mount-diff 零能力损失复核（完整 manifest build 对比 before/after）
- **entry 集合 155 → 155（不变）**。
- **唯一翻转 entry = `xlsx/gt-l5-long-term-payables`**（changed entry count = 1）：
  - capability `single_onlyoffice` → `bidirectional`
  - migration_state `legacy_fake_bidirectional` → `adapter_registered`
  - adapter_id `None` → `l5.long_term_payables`
  - mounts `1` → `2`（host 新增 OO 挂载块）
- stats（before → after）：
  - by_component：**仅 `GtOnlyOfficeSheet` 243 → 244（+1）**；OnlyOfficeWordDialog 2 / WorkpaperWordEditor 4 不变。
  - capability_counts：bidirectional 19 → 20、single_onlyoffice 130 → 129（−1）、single_html 5 / unreachable 1 不变。
  - mount_count 249 → 250、legacy_fake_bidirectional_count 122 → 121、unadjudicated_count 117 → 116、host_count 154 不变。
- **无任何预期外 entry 翻转。**

## legacy baseline diff（仅 L5 + 顶层 digest/counts）
- 唯一变化 entry = L5：`capability single_onlyoffice→bidirectional`、`missing_adapter true→false`、
  `migration_state legacy_fake_bidirectional→adapter_registered`、`mode_switch_visible false→true`、host 文件 hash 变、
  `evidence` 从 `[]` 变为记录 3 条（segmented_mode_switch L12 / dual_mode_state L13 / mount_condition_mode_gate L24）。
- 顶层：baseline_digest/manifest_digest/source_digest 更新、`missing_adapter_count` 123 → 122。
- 其它 entry 一个未动。

## 自洽验证
- worktree 内 `test_task73_entry_profile_manifest.py` **46 passed**。
- 回拷主树后 `L5.manifest_capability_enabled() == True`、`assert_manifest_capability_enabled()` 不抛。

## 回拷主树的文件
- `backend/data/workpaper_sync_entry_manifest.json`
- `backend/data/workpaper_sync_legacy_baseline.json`
- `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncLegacyBaseline.generated.ts`
- `backend/data/workpaper_sync_entry_overlay.json`（主树内就地：L5 override 追加 + approved_source_digest 更新 + review_basis 追加 L5 段）

## 清理
- `git worktree remove .worktrees/l5-flip` + 删临时分支 `work/2026-10-02-l5-flip` + 删 node_modules junction（T7 收尾）。
