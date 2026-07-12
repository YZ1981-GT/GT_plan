# Implementation Plan: Version Trail Full Coverage

## Overview

将 `useWorkpaperVersionToolbar` + `GtWpVersionTrail` 版本链标准接线推广至全部 D3~N5 未接入底稿主入口组件（~70 文件），并新建 CI 守卫确保未来不遗漏。每个组件执行 5 步接入（import → call composable → hook save → mount template → provide）。按循环分组、波次并行执行（最大并发 5）。

## Tasks

- [x] 1. D3~D7 版本链接入
  - [x] 1.1 GtD3PrepaidAccounts 接入: import useWorkpaperVersionToolbar + defineAsyncComponent GtWpVersionTrail, call composable(wpId/projectId), 保存成功后 scheduleAutoSnapshot, template 末尾 mount GtWpVersionTrail(:workpaper-id/:project-id/ref), provide d3VersionTrailRef + d3OpenVersionHistory
  - [x] 1.2 GtD4Revenue 接入: 同 1.1 模式, provide keys d4VersionTrailRef/d4OpenVersionHistory
  - [x] 1.3 GtD5OtherCurrentAssets 接入: 同模式, provide keys d5VersionTrailRef/d5OpenVersionHistory
  - [x] 1.4 GtD6LongTermReceivables 接入: 同模式, provide keys d6VersionTrailRef/d6OpenVersionHistory
  - [x] 1.5 GtD7OtherNonCurrentAssets 接入: 同模式, provide keys d7VersionTrailRef/d7OpenVersionHistory
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 2. E1 版本链接入
  - [x] 2.1 GtE1CashAndBank 接入: 5 步标准接入, provide keys e1VersionTrailRef/e1OpenVersionHistory
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 3. F1~F5 版本链接入
  - [x] 3.1 GtF1Inventory 接入: 5 步标准接入, provide keys f1VersionTrailRef/f1OpenVersionHistory
  - [x] 3.2 GtF2CostOfSales 主入口接入 (f2 keys); IF 子入口 GtF2InventoryMain/Special/Valuation/Stocktake 独立持有 wpId/projectId THEN 子入口级独立接入
  - [x] 3.3 GtF3NotesPayable + GtF4AccountsPayable + GtF5CostOfSales: 3 组件统一接入 (f3/f4/f5 keys)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 4. G1~G14 版本链接入
  - [x] 4.1 GtG1~GtG7: 7 个主入口 5 步标准接入, provide keys g1~g7VersionTrailRef/OpenVersionHistory
  - [x] 4.2 GtG8~GtG14: 7 个主入口 5 步标准接入, provide keys g8~g14VersionTrailRef/OpenVersionHistory
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 5. H1~H10 版本链接入
  - [x] 5.1 GtH1~GtH5: 5 个主入口 5 步标准接入, provide keys h1~h5
  - [x] 5.2 GtH6~GtH10: 5 个主入口 5 步标准接入, provide keys h6~h10
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 6. I1~I6 + J1~J3 版本链接入
  - [x] 6.1 GtI1~GtI6: 6 个主入口 5 步标准接入, provide keys i1~i6
  - [x] 6.2 GtJ1~GtJ3: 3 个主入口 5 步标准接入, provide keys j1~j3
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 7. K1~K13 版本链接入
  - [x] 7.1 GtK1~GtK7: 7 个主入口 5 步标准接入, provide keys k1~k7
  - [x] 7.2 GtK8~GtK13: 6 个主入口 5 步标准接入, provide keys k8~k13
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 8. L1~L8 版本链接入
  - [x] 8.1 GtL1~GtL8: 8 个主入口 5 步标准接入, provide keys l1~l8
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 9. M1~M10 版本链接入 (skip M8/M9)
  - [x] 9.1 GtM1~GtM7 + GtM10: 8 个主入口 5 步标准接入, provide keys m1~m7/m10. M8/M9 已接入跳过
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 10. N1~N5 版本链接入
  - [x] 10.1 GtN1~GtN5: 5 个主入口 5 步标准接入, provide keys n1~n5
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 12.1, 12.2, 12.3, 15.1, 15.2_

- [x] 11. CI Guard Script 新建
  - [x] 11.1 创建 `backend/scripts/check/check_wp_version_trail.py`: 零依赖 Python 脚本, 主入口识别(Gt{Letter}{Digit}*.vue regex), useWorkpaperVersionToolbar 检测, GtWpVersionTrail 检测, --strict 退出码 1, UTF-8 安全(sys.stdout.reconfigure), 白名单加载逻辑
  - [x] 11.2 创建 `backend/scripts/check/version_trail_whitelist.txt`: 初始白名单(纯 OO 底稿豁免列表, # 注释支持)
  - [x] 11.3 挂载 CI: `.github/workflows/governance-checks.yml` 新增 step `python backend/scripts/check/check_wp_version_trail.py --strict`
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 12. PBT + 全树验证
  - [x] 12.1 Property 1 PBT: Hypothesis 测试 CI guard scan_file 检测正确性 — 生成含/不含 useWorkpaperVersionToolbar + GtWpVersionTrail 四种组合的随机 Vue SFC 内容, 验证分类准确. min 100 iterations. Tag: Feature: version-trail-full-coverage, Property 1: CI Guard Detection Completeness
  - [x] 12.2 Property 2 PBT: Hypothesis 测试白名单排除逻辑 — 生成随机文件列表+白名单, 验证白名单文件不出现在违规报告中. min 100 iterations. Tag: Feature: version-trail-full-coverage, Property 2: CI Guard Whitelist Exclusion
  - [x] 12.3 运行 CI guard 全树扫描: `python backend/scripts/check/check_wp_version_trail.py --strict` 确认 exit 0
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

## Notes

- D2 为参考实现（`GtD2AccountsReceivable.vue`），所有组件照搬相同 5 步模式
- M8/M9 已完成接入，Task 9 跳过
- `scheduleAutoSnapshot()` 仅在保存成功后调用（失败不触发）
- Prop 绑定统一用 `:workpaper-id`（非 `:wp-id`）和 `:project-id`
- Composable 导入路径：`'./composables/useWorkpaperVersionToolbar'`
- GtWpVersionTrail 导入：`defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))`
- Provide key 命名：`{cyclePrefix}VersionTrailRef` / `{cyclePrefix}OpenVersionHistory`（如 d3、g14、k13）
- CI guard 参照 `check_wp_ref_contract.py` 风格（零依赖、argparse、--strict）
- PBT 测试路径：`backend/tests/check/test_check_wp_version_trail.py`
- Property tests 标签格式：`Feature: version-trail-full-coverage, Property {N}: {title}`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["11.1", "11.2"] },
    { "id": 1, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["2.1", "3.1", "3.2", "3.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "5.2", "6.1", "6.2"] },
    { "id": 4, "tasks": ["7.1", "7.2", "8.1", "9.1", "10.1"] },
    { "id": 5, "tasks": ["11.3", "12.1", "12.2"] },
    { "id": 6, "tasks": ["12.3"] }
  ]
}
```

