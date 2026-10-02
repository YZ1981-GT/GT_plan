# L7 manifest 翻转 mount-diff 零能力损失复核

> 任务：`l7-true-bidirectional-2026-10-01` 第5步。
> 口径：**完整 manifest build 对比**（worktree 新 manifest vs HEAD `b117123b1` 旧 manifest），
> 不是错误的 `entries[].mounts vs live` 口径（L4 踩过）。

## 环境

- 干净 worktree：`.worktrees/l7-flip`，分支 `work/2026-10-01-l7-true-bidirectional`，基于 commit `b117123b1`
  （含第1~3步的 host/provider/contract/登记/测试），只叠加本 spec 的 overlay L7 override 一处改动。
- worktree frontend 的 `node_modules` 用 junction 指向主树（新检出未装依赖）。
- `approved_source_digest`：`d648767136…`（L4 轮旧值）→ `7ae8f4c7987a64236a911ea68284290a29034bc4058a2abfe0e99dcc164141d2`
  （worktree 重算，只含本任务改动）。
- manifest digest：`1cf5e73932305d28a71f0590a0e10db6caf1db941ce4ea8fabf906dc4c50d80b`。
- baseline digest：`49731b4da91370cdebfe61a605d7182dd916a49eb465457728c8d420cc07231a`。

## capability 范围校验表（逐 entry 现算）

| 维度 | 旧（HEAD b117123b1） | 新（worktree 翻转后） |
|------|------|------|
| entry 集合 | 155 | 155（零增减） |
| **changed entry count** | — | **1（唯一 = `xlsx/gt-l7-other-noncurrent-liabilities`）** |
| L7 capability | `single_onlyoffice` | `bidirectional` |
| L7 migration_state | `legacy_fake_bidirectional` | `adapter_registered` |
| L7 adapter_id | `None` | `l7.other_noncurrent_liabilities` |
| L7 per-entry mount | 1 | 2（+1） |

**其它所有 154 条 entry 的 capability / migration_state / adapter_id / mount 数零变化。**无预期外翻转。

## stats 对比

| stat | 旧 | 新 |
|------|----|----|
| host_count | 154 | 154（不变） |
| mount_count | 246 | 247（+1） |
| dispatcher_count | 1 | 1（不变） |
| entry_count | 155 | 155（不变） |
| byComponent.GtOnlyOfficeSheet | 240 | 241（+1） |
| byComponent.OnlyOfficeWordDialog | 2 | 2（不变） |
| byComponent.WorkpaperWordEditor | 4 | 4（不变） |
| capability_counts.bidirectional | 16 | 17（+1） |
| capability_counts.single_onlyoffice | 133 | 132（−1） |
| capability_counts.single_html | 5 | 5（不变） |
| capability_counts.unreachable | 1 | 1（不变） |

mount 仅 `GtOnlyOfficeSheet` +1（host 新增的过程表 OO 挂载块），零无关 churn。

## baseline（manifest 下游）diff 范围

对比 worktree 新 baseline vs HEAD `b117123b1` 旧 baseline：
- **唯一变化 entry = `xlsx/gt-l7-other-noncurrent-liabilities`**。
- 顶层仅 `manifest_digest` / `source_digest` / `baseline_digest` / `stats` 变化。
- 无并发预存哈希修正（对比基准干净）。

## worktree 门验证

- `generate_workpaper_sync_manifest.py --check`（worktree）：rc=0，无漂移，digest `1cf5e739…` 一致。
- `test_task73_entry_profile_manifest.py`（worktree）：**46 passed, 0 failed**（123s）。

## 🔴 主树 `--check` FAIL 的归因（并发会话，非本任务）

主树 `generate_workpaper_sync_manifest.py --check` 报
`current='0fdfc3a0aa9483989fd3026a2b3164f7fc4eedb78a42046424249b9a2aca707b'`
≠ worktree 算的 `7ae8f4c7…`。这是**预期的**：主树工作区有 K/J/N/I 并发会话**未提交**的其它
workpaper host 改动，它们改变了别的 entry 的 mount 源 ⇒ 主树 sourceDigest 掺入了与本任务
无关的 mount churn。本任务采用的是**干净 worktree** 算的 `7ae8f4c7…`（只含 L7 host+overlay 改动），
回拷的 manifest.json / baseline / generated.ts 均是 worktree 的权威产物逐字拷贝。
这正是 J1/L4 铁律「翻转 digest 必在干净 worktree 算」的落地理由。
