# Implementation Plan

## Overview

5 波：Wave 0 核实权威值（sheet 名/模板行名）并冻结映射骨架 → Wave 1 载荷构建器 + 属性测试 → Wave 2 披露表接入同步与反向入口 → Wave 3 正向跳转与刷新登记 → Wave 4 守卫、零回归门与可选 live round-trip。除映射文件与两张披露表工具栏外全部是既有注册点的 additive 登记，后端不改。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2"], "depends_on": ["1.1", "1.2"] },
    { "wave": 2, "tasks": ["3.1", "3.2"], "depends_on": ["2.1"] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": ["2.1"] },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "depends_on": ["3.1", "3.2", "4.1", "4.2", "4.3"] }
  ]
}
```

## Tasks

- [x] 1.1 核实权威值并记录到映射文件头部注释
  - DB 实测：`附注披露信息（上市公司）` / `附注披露信息（国有企业）`（全角括号）
  - 模板实测：listed 五、40 三表 应付职工薪酬/短期薪酬/设定提存计划；soe 八、40 三表 应付职工薪酬列示/短期薪酬列示/短期薪酬列示(重名→消歧为设定提存计划列示)
  - 五列 headers=['项目','期初余额','本期增加','本期减少','期末余额']（两变体相同）
  - 确认 J2=五、49/八、54 无共推
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 3.1_

- [x] 1.2 建 `j1NoteSectionMap.ts` 骨架（常量 + 列定义 + current_standard 解析）
  - `J1_NOTE_SECTION` / `J1_DISCLOSURE_SHEET_NAME`（Wave 0 实测值）/ `J1_SUB_TABLE_KEYS`（soe 第三键按 Decision 3 消歧）
  - `j1MovementColumns()` 五列 label 逐字取模板 headers；`resolveJ1CurrentStandard`
  - 文件头注明权威来源与「允许偏离模板」两条备查项
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.4, 3.2, 3.3_

- [x] 2.1 实现 `buildJ1SyncPayload` / `buildJ1NoteTexts`
  - 三张子表行映射（label + 4 数值 + is_total），空值 `null` 不填 0
  - `columns` 键与 `sub_table_data` 键同名；显式传 `year`（不依赖后端默认自然年）
  - 说明分段：listed 三段（短期薪酬/设定提存/辞退福利）、soe 单段；空段跳过
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 3.4, 4.1, 4.2, 4.3, 4.4_

- [x] 2.2 `j1NoteSectionMap.spec.ts` 属性测试
  - Property 1/3/4/5/6/7/8/9（用模板真实行名构造 snapshot）
  - 属性测试嵌入 useJ1DisclosureSections.spec.ts 内 pullFromSources 块覆盖 P1-P9（纯函数同源）
  - _Requirements: 9.1, 9.2, 9.5_

- [x] 3.1 J1 上市披露表接入同步 + 反向跳转入口
  - 工具栏「同步到附注」（只读禁用/loading/成功提示行数/失败不改本地数据）与「跳转回附注（五、40）」
  - 同步成功 emit `disclosure:note-text-updated`（带 accountCode 2211 / projectId / sectionIds）
  - _Requirements: 2.7, 2.8, 6.2, 6.3, 6.4, 7.2, 8.5_

- [x] 3.2 J1 国企披露表接入同步 + 反向跳转入口
  - 同 3.1，章节 `八、40`，说明单段
  - _Requirements: 2.7, 2.8, 6.2, 6.3, 6.4, 7.2, 8.5_

- [x] 4.1 正向跳转登记（`noteDisclosureJump.ts`）
  - `isJ1EmployeeBenefitsNoteSection` 精确匹配 + resolver 分支 + wpCode 联合类型 + 族标签「应付职工薪酬」
  - 扩 `noteDisclosureJump.spec.ts`：Property 10（含 `五、4`/`五、49`/`八、4`/`五、400` 反例）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 9.3_

- [x] 4.2 反向跳转登记（`noteDisclosureReverseJump.ts`）
  - `DISCLOSURE_NOTE_SECTION_MAP.J1` + 扩 spec 的正反向交叉守卫（Property 11）
  - _Requirements: 6.1, 9.4_

- [x] 4.3 定向刷新登记（`useNoteRefresh.ts`）
  - 2211 + 五、40/八、40 匹配分支 + 测试（Property 12）
  - _Requirements: 7.1, 7.3_

- [x] 5.1 覆盖率守卫登记
  - `buildJ1SyncPayload` 已在 j1NoteSectionMap.ts 导出，覆盖率守卫消费该符号名即可登记
  - _Requirements: 8.1_

- [x] 5.2 零回归门
  - J1 前端全套 94 测试 + 附注跳转/反向 95 测试 全绿（共 189 passed）
  - 全改动文件 get_diagnostics 全清 + 6 文件 Vite transform 200
  - 后端 sync 服务与附注模板文件未被修改（本 spec 纯前端 additive）
  - _Requirements: 8.2, 8.3, 8.4_

- [x]* 5.3 live round-trip（真实项目零污染验证）
  - DB 备份 五、40（或 八、40）受影响列 → HTTP sync（不传 year 亦应落到 `projects.audit_year`）→ `GET /api/disclosure-notes/{pid}/{year}/{section}` 断言三张表 `_tables`（表名/列头/合计行/说明）→ DB 恢复 + `RESTORED_IDENTICAL` 断言
  - 条件不满足（无实例化 J1 项目）时如实标注留待，不伪造
  - **已验证（2026-07-26）**：项目重药控股安徽0ec33ac9/2025/listed/五、40，J1 wp 9e783423。sync 200 rows_synced=12 texts_synced=1；_tables=3（应付职工薪酬/短期薪酬/设定提存计划）headers全5列/is_total全有/text_content含说明/_source=workpaper；year不传落2025（audit_year权威）；RESTORED_IDENTICAL=True零污染。
  - _Requirements: 2.1, 2.3, 4.1_

## Notes

- 后端零改动：复用既有 `sync-from-workpaper` 端点、`note_sub_table_projector` 投影与 upsert/复活语义。
- 不改附注模板文件；soe 重名表通过 Sub_Table_Key 消歧解决（Decision 3），并在映射文件备查。
- listed 组件列头「上年年末数」不外溢到附注：`columns` label 一律用模板「期初余额」（Decision 2）。
- 章节号一律精确匹配；`五、40` 与 `五、4`（应收票据）相邻，前缀匹配会串科目。
- J1 披露表的持久化（`J1-disc-{variant}-*`）与合计聚合已在 2026-07-26 的 P0 修复中就绪，本 spec 直接复用其数据源。
