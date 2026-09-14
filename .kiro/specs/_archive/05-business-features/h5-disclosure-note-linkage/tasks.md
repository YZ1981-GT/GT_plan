# Implementation Plan:

## Overview

H5 油气资产 SOE 披露表→附注结构化同步 + 审定表双科目 bring-in。纯前端，4 波 8 任务。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "tasks": ["1"], "description": "h5NoteSectionMap 纯函数+测试" },
    { "id": "W1", "tasks": ["2", "3"], "description": "SOE 披露同步+跳转" },
    { "id": "W2", "tasks": ["4", "5"], "description": "审定表双科目 bring-in" },
    { "id": "W3", "tasks": ["6", "7", "8"], "description": "守卫+回归+live" }
  ]
}
```

## Tasks

- [x] 1. 新建 h5NoteSectionMap.ts + vitest (P1/P2/P3)
  - 新建 `composables/h5NoteSectionMap.ts`：H5_NOTE_SECTION 常量 + buildH5SyncPayload 纯函数 + H5_SOE_COLUMNS 列定义
  - 新建 `h5NoteSectionMap.spec.ts`：验证 P1(子表键) + P2(中文列头) + P3(year传入)
  _Requirements: 1.1, 1.2, 1.4, 6.1_

- [x] 2. H5TabDisclosureSoe 加「同步到附注」按钮
  - import buildH5SyncPayload + useAuditContext + http + eventBus
  - syncToNote(): 组装载荷 → POST sync-from-workpaper → emit disclosure:note-text-updated
  - 行数据空时不发请求 + warning
  _Requirements: 1.1-1.7_

- [x] 3. H5TabDisclosureSoe 加「↩ 跳转回附注（八、25）」按钮
  - import buildNoteJumpRoute + useRouter
  - el-button jump → router.push
  - vitest P4（上市版无按钮）
  _Requirements: 2.1, 2.2, 5.1_

- [x] 4. H5TabAdjudication 接入 useAdjudicationBringIn 双实例
  - import useAdjudicationBringIn + AdjudicationBringInDialog + useAuditContext
  - 实例1: 1631/debit（原值区块）
  - 实例2: 1632/credit（折耗区块）
  - 按钮触发两实例 load，无匹配 ElMessage.info
  - 两 dialog 独立渲染
  _Requirements: 3.1-3.4, 3.6_

- [x] 5. bring-in apply 接线 + vitest (P5/P6/P7)
  - onBringInApply(allocations, block): 累加 updateCell + publishAdjudicated
  - vitest h5AdjudicationBringIn.spec.ts: P5(direction debit) + P6(direction credit) + P7(累加非替换)
  _Requirements: 3.5, 6.1_

- [x] 6. 覆盖率守卫登记
  - check_disclosure_columns_coverage.py COLUMN_BUILDERS 加 buildH5SyncPayload
  - --strict exit 0
  _Requirements: 4.1, 4.2_

- [x] 7. 全量零回归验证
  - get_diagnostics 全改动文件全清
  - Vite transform 全 200
  - 已有 H5 vitest 全绿
  _Requirements: 5.2, 5.4_

- [ ]* 8. live round-trip（可选，需 H5 实例化项目）
  - 备份 八、25 → sync → GET 验证 → 恢复 → RESTORED_IDENTICAL
  _Requirements: 6.2_

## Notes

- 后端零改动
- 仅 SOE 变体（listed=null 无独立章节）
- 复用已验证共享 helper（K6/K1 双科目范式）
- H5 行业限定底稿需 oil_gas/mining 标记项目
