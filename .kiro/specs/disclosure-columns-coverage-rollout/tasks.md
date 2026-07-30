# Implementation Plan: 披露表 columns 覆盖与两级表头推广

## Overview

先做基础设施（`ColumnDef.flat` + 后端三态 + 守卫 strict）与 R8 断言清红，再按循环族分 4 批补齐 14 个未覆盖 Tab 并迁移压平 label，最后挂 CI 与实测。

批 1（L1/L3）作为范式样板，固化 helper 写法后再推批 2~4，避免 14 个各写一套。

## Task Dependency Graph

```
1 (ColumnDef.flat + defineColumns)
      └─> 2 (后端 _extract_column_groups 三态) ──> 3 (F2 房企 3 表标 flat)
                                                        │
4 (守卫 --strict + allowlist reason) ───────────────────┤
                                                        ▼
5 (批1 L1/L3 打样) ──> 6 (批2 K4~K7) ──> 7 (批3 J1) ──> 8 (批4 H4)
                                                        │
                                              9 (全 Tab 契约测试)
                                                        │
                                              10 (CI 挂载) ──> 11 (实测) ──┐
                                                                          │
13 (账龄标签披露口径 R6) ─┐                                                │
14 (孤儿表 diff 清理 R7) ─┤                                                │
16 (sheet_name 漂移 R8) ─┴─> 15 (Checkpoint) ────────────────────────────┴─> 12 (收尾)
```

R6/R7/R8 与批 1~4 互不依赖（R6 改**行标签口径**、R7 改**表名生命周期**、
R8 改**测试断言口径**，批 1~4 改**列头元数据**），可独立并行推进；
但同属披露同步口径声明化，故并入本 spec 统一收口。

R8 建议先做：它清掉的是**掩盖真实回归的预存在失败** —— 不清完，后续批次跑全量
vitest 时无法一眼分辨「本批新引入的红」和「历史欠账的红」。

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "4", "13.1", "14.1", "16.1", "16.2", "16.3", "16.4"], "desc": "ColumnDef.flat + 守卫 strict + R6/R7 共享纯函数 + R8 断言清理（互不相干，R8 先清红底）" },
    { "wave": 1, "tasks": ["2", "13.2", "14.2", "16.5", "16.6"], "desc": "后端三态语义 + R6 per-section 覆盖 + R7 持久化 + R8 守卫与全量复跑", "depends_on": [0] },
    { "wave": 2, "tasks": ["3", "5", "13.3", "14.3"], "desc": "F2 标 flat + 批1 打样 + R6/R7 载荷接线", "depends_on": [1] },
    { "wave": 3, "tasks": ["6", "7", "8", "14.4"], "desc": "批2~4 + R7 组件回调", "depends_on": [2] },
    { "wave": 4, "tasks": ["9", "13.4", "13.5", "14.5"], "desc": "全 Tab 契约测试 + R6/R7 契约测试与守卫", "depends_on": [3] },
    { "wave": 5, "tasks": ["10", "11", "14.6"], "desc": "CI 挂载 + Playwright 实测（含改名场景）", "depends_on": [4] },
    { "wave": 6, "tasks": ["15"], "desc": "R6/R7/R8 Checkpoint", "depends_on": [5] },
    { "wave": 7, "tasks": ["12"], "desc": "收尾", "depends_on": [6] }
  ]
}
```

## Tasks

- [x] 1. `ColumnDef.flat` 声明与透传
  - [x] 1.1 `disclosureColumnDefs.ts`：`ColumnDef` 增 `flat?: boolean`（注释说明「标任一列即整表生效」）
  - [x] 1.2 `defineColumns` 透传 `flat`（该 helper 曾漏传 `group`，防同类回归）
  - [x] 1.3 `disclosureColumnDefs.spec.ts` 补 `flat` 透传断言
  - _Requirements: 3.1_

- [x] 2. 后端 `_extract_column_groups` 三态语义
  - [x] 2.1 遇任一列 `flat: true` → 返回 `[]`（显式单级）；无 `group` 且无 `flat` → 仍返回 `None`
  - [x] 2.2 确认 `project_sub_tables` 仅在 `None` 时回退 `_infer_groups_from_headers`
        （守卫写成 `if col_groups is None:`，代码内已留注释说明写 `if not col_groups:` 会让 flat 的 `[]` 也去推断）
  - [x] 2.3 `test_note_sub_table_projector.py` 已含 Property 5 三态（`flat`→`[]` / 未声明→`None` / 显式 group 不被抢占）
        + Property 4 区间合法 + 两条端到端（flat 表抑制推断 / 去掉 flat 反例）——**实测 30/30 绿**
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. F2 房企 3 表标 `flat`（消除凭空「本期」父表头）
  - [x] 3.1 `f2DisclosureSyncPayload.ts`：开发成本 / 开发产品 / 周转房 + 确认为存货的数据资源 标签列已加 `flat: true`
  - [x] 3.2 `f2NoteSectionMap.spec.ts` 已断言：这 4 表标 `flat` 且无 `group`；两级表头 3 表反向断言不得标 `flat`（实测绿）
  - [x] 3.3 Playwright 复验附注侧不再出现「本期」父表头
  - _Requirements: 3.4_

- [x] 4. 覆盖守卫（`--strict` 与 CI 挂载已存在，补 allowlist 原因必填）
  - [x] 4.1 ~~增 `--strict`~~ —— 已存在，实测 exit 1；`governance-checks.yml` 的
        `disclosure-columns-coverage` job 已在跑 `--strict` → **该 job 当前是红的**
  - [x] 4.2 allowlist `reason` **必填**：新增 `allowlist_reason()` / `is_allowlisted()` /
        `blank_reason_entries()`；空串·空白·None 一律**不豁免**（仍计未覆盖、`--strict` 阻断），
        报告单列「原因空白」段并在未覆盖行标注 `← allowlist 已登记但原因空白`，
        防「先占位再补原因」变永久豁免
  - [x] 4.3 ~~输出未覆盖清单~~ —— 已有（逐条列出路径）
  - _Requirements: 4.3_

- [x] 5. 批 1：L1 / L3（4 个 Tab，范式样板）
  - [x] 5.1 逐 sheet 读 L1 / L3 源模板，确认各子表列名与表头层级（结论写入 design §批 1 列头清查 §2~§5）
  - [x] 5.2 `buildL1{Listed,Soe}Columns` / `buildL3{Listed,Soe}Columns` —— 4 表全为单行表头，
        标签列一律 `flat: true`、**0 处 `group`**；冲突处按「附注是交付物」取附注口径
        （国企分类表 `期初余额`、国企逾期表 `债权单位`/`借款利率（%）`、L3 国企丢弃无落点的期初利率列）
  - [x] 5.3 挂入各自 `build*SyncPayload` 的 `columns`（4 个 `.vue` 解构后在 POST 体简写透传）
  - [x] 5.4 更新 L1 / L3 既有单测断言；跑覆盖守卫确认这 4 个已覆盖（22/22 绿）
  - [x] 5.5 固化 helper 写法为后续批次模板（写入本 spec design 附注）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5_

- [x] 6. 批 2：K4 / K5 / K6 / K7（7 个 Tab）
  - [x] 6.1 逐 sheet 读 K4~K7 源模板
  - [x] 6.2 按批 1 范式补 `columns`（同族列结构相似处抽公共 helper）
  - [x] 6.3 更新既有单测断言；跑覆盖守卫
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5_

- [x] 7. 批 3：J1（2 个 Tab）
  - [x] 7.1 逐 sheet 读 J1 源模板（3 表 headers 相同、均单行；列头取模板「期初余额」而非组件的「上年年末数」）
  - [x] 7.2 `columns` 已在 `buildJ1SyncPayload` 中挂载；本会话修掉两处实质缺陷：
        ① **补 `flat: true`** —— 5 列里「本期增加/本期减少」共享前缀「本期」，
        不标 flat 时后端 `_infer_groups_from_headers` 会反猜出源模板不存在的「本期」父表头
        （与 F2 房企 3 表同款，R3.1/R3.4）；
        ② 本地 `ColumnDef` interface 无 `flat`/`format` 字段 → 收敛到共享
        `disclosureColumnDefs.ColumnDef` + `defineColumns()`，4 个金额列补 `format: 'amount'`
        （已 grep 确认无消费方 import 该本地类型）
  - [x] 7.3 新增 `__tests__/j1h4DisclosureColumns.spec.ts` 锁 flat / format / P1 / P2 / P6；跑覆盖守卫
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5, 3.1, 3.4_

- [x] 8. 批 4：H4（1 个 Tab）
  - [x] 8.1 H4 **不读自己的源模板** —— 它推的是 H2 章节（五、23）里的
        `工程物资` 分类表 + 顺带勾稽 `在建工程` 汇总表的工程物资行，两处写同一张表。
        故 `columns` **复用 `buildH2ListedColumns()`**，按本次实际推送键取子集
        （`pickH4ListedColumns`）：各造一份必然分叉，附注列头会随最后一次同步跳变。
        未登记的子表键**不臆造列头**（宁缺勿造，由守卫/契约暴露）
  - [x] 8.2 更新既有单测断言；跑覆盖守卫确认未覆盖数为 0
        （🔴 基数校正：requirements 记 14，实测最初 **16**（漏记 F4 两处）；
        其中 L1/L3 4 个是**守卫假阴性**（ES6 简写透传未被识别，并发会话已修正则）、
        F4 2 个 + K4~K7 + J1 实际已带 `columns` 只是 builder 名未登记 →
        真正缺 `columns` 的只有 H4 一个。**现 92/92 覆盖，`--strict` exit 0**）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5_

- [x] 9. 全 Tab 契约测试
  - [x] 9.1 新建 `__tests__/disclosureColumnsCoverage.spec.ts`：扫描全部 `build*Columns()`
        校验 P1（键一一对应）/ P2（标签列唯一居首）/ P3（group 相邻）/ P6（无英文键当列头）
  - [x] 9.2 跑 `disclosureSyncUrlContract.spec.ts` + 各循环披露单测
  - _Requirements: 1.5, 2.4, 5.1, 5.2_

- [x] 10. CI 挂载
  - [x] 10.1 `governance-checks.yml` 增一步 `check_disclosure_columns_coverage.py --strict`
  - [x] 10.2 本地模拟未覆盖场景验证 CI 会红
  - _Requirements: 4.2_

- [x] 11. 回归与实测
  - [x] 11.1 后端：`test_note_sub_table_projector.py` + `test_note_word_export_sub_table.py` 全绿
  - [x] 11.2 前端：各循环披露相关 spec 全绿；`npx tsc --noEmit` 改动文件 0 错误
  - [x] 11.3 Playwright 抽 1 上市 + 1 国企：披露表同步 → 附注两级表头正确
  - [x] 11.4 Word 导出抽验两行表头
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 13. 账龄标签披露口径映射（R6，方案 A）
  - [x] 13.1 新建 `composables/disclosureAgingLabels.ts`
    - `DISCLOSURE_AGING_LABELS`（7 个预设段 key → 披露口径）
    - `DISCLOSURE_STRUCT_ROW_LABELS`（`小计`→`小 计` / `合计`→`合 计` / `1年以内小计`→`1年以内小计：`）
      + `DISCLOSURE_TOTAL_LABEL` / `DISCLOSURE_SUBTOTAL_LABEL` / `DISCLOSURE_AGING_LABEL_VALUES`
    - `lookupDisclosureAgingLabel(key, overrides?)`（未命中返 `undefined`，供 F1 链式兜底）
    - `toDisclosureAgingLabel(seg, overrides?)`：**① 预设段 key（overrides > 共享表）→ ② 结构行按 label 兜底 → ③ 原样透传**
      🔴 ② 必须按 **label** 而非仅 `__` 前缀 key 兜底 —— D2 组合分表的合计行只有 `label:'合计'`、无段 key
    - `toDisclosureStructLabel(label)` 单参按 label 映射；`isSameStructLabel()` 忽略空格比对
    - _Requirements: 6.1, 6.2, 6.4, 6.5_
  - [x] 13.2 `d2NoteSectionMap.ts` 声明 `D2_AGING_LABEL_OVERRIDES`
    - `soe.within1 = '1年以内（含1年）'`；`listed` 用共享表默认值
    - _Requirements: 6.3_
  - [x] 13.3 `buildD2SyncPayload` 在账龄表与组合分表行 label 上应用映射
    - 只改载荷构建，不动 `agingRows` / 组合分表的 UI 数据源（P8）
    - _Requirements: 6.1, 6.6_
  - [x]* 13.4 `disclosureAgingLabels.spec.ts`（P7/P8）+ `d2NoteSectionMap.spec.ts` 补 D2 两版断言
    - **Property 7: 映射全域性与保守性 / Property 8: 底稿显示口径不变**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**
  - [x] 13.5 扫描守卫：列出仍直接推配置口径标签的同步调用点（warn 不阻断）
    - 复用 `check_disclosure_columns_coverage.py` 增一节输出，或新增轻量检查脚本
    - _Requirements: 6.7_
  - [x] 13.6 余下循环收敛 + 守卫假阳性/假阴性修正（2026-07-30）
    - **守卫判定口径收紧**：信号由「文件含『账龄』」改为 `agingRows|agingSegments|AgingSegment|AGING_BANDS|AGING_LABEL`
      —— 原口径把 D6（列头 `{label:'账龄'}`）/ D7（表名「账龄超过1年的重要合同负债」）判成未覆盖（**假阳性**，
      两者与账龄档位无关）；`FILENAME_RE` 扩为含 `DisclosureRows|DisclosureModel|Disclosure(Listed|Soe|SOE)`
      —— 原口径漏扫 G5 的 `g5ListedDisclosureRows.ts`（**假阴性**，其 `1-2年`/`2-3年` 是真漂移）
    - **收敛 K1 / F4 / G5**：`k1DisclosureModel.K1_NOTE_AGING_LABEL` 与 `f4NoteSectionMap.F4_NOTE_AGING_LABEL`
      改由 `buildDisclosureAgingLabelMap()` 派生；`g5ListedDisclosureRows.G5_DEFAULT_AGING_BANDS`
      改由 `lookupDisclosureAgingLabel` 派生（保留原常量名与形状，下游与既有断言零改动）
    - **收敛 D3**：`useD3DisclosureSoe` 两桶行透出 `rowKey`（`within1`/`over1`），
      `buildD3SyncPayload` 在**国企主表数据行**上用 `toDisclosureAgingLabel(r, SOE_AGING_OVERRIDES)` 映射
      （底稿页仍显示 `1年以内`，Property 8）；`over1: '1年以上'` 进共享表
    - **国企首档字面单一真源**：新增 `DISCLOSURE_AGING_WITHIN1_SOE` + `SOE_AGING_OVERRIDES`，
      D2 soe / F1 soe / F4 / D3 soe 四处覆盖声明统一引用（此前各写一遍 `'1年以内（含1年）'` 字面量）
    - **🔴 D3 合计行不做结构行映射**：D3 附注模板（五、38 / 八、38）合计行字面为 `合计`（**无空格**），
      与 D2 §五、5 / §八、5 的 `合 计` 不同 → 不套 `DISCLOSURE_TOTAL_LABEL`，由
      `d3NoteSubtableContract.spec.ts` 正向锁死此差异
    - 守卫复扫：`15/15` 全覆盖，`--strict` exit 0
    - _Requirements: 6.1, 6.3, 6.7_

- [x] 14. 动态子表名孤儿清理（R7）
  - [x] 14.1 新建 `composables/disclosureSyncedTables.ts`
    - `dataTableNames(subTableData)` / `buildRemovedTableKeys({previouslySynced, legacyObsolete, pushed})`
    - _Requirements: 7.2, 7.3, 7.4, 7.8_
  - [x] 14.2 `useD2DisclosureNote`：持久化 + 快照字段
    - hydrate 读 `synced-tables`；导出 `markSynced(names)`（`isReadonly` 直接 return）
    - `buildSnapshot()` 增 `previouslySyncedTables`
    - _Requirements: 7.1, 7.7_
  - [x] 14.3 `d2NoteSectionMap.ts`：两版统一产出 `_removed_table_keys`
    - `D2_LISTED_OBSOLETE_TABLE_KEYS` 降级为 `legacyObsolete` 种子（保留，非死代码）
    - 删掉 `if (!isSoe)` 分支，国企同样上报
    - _Requirements: 7.2, 7.4_
  - [x] 14.4 `D2DisclosureNoteBody.vue`：同步**成功后**才 `markSynced`
    - POST 失败绝不写入（否则下次误删本轮表）
    - _Requirements: 7.1_
  - [x]* 14.5 `disclosureSyncedTables.spec.ts`（P9）+ `d2NoteSectionMap.spec.ts` 闭环幂等（P10）
    - **Property 9: 差集正确且不误删 / Property 10: 同步-持久化闭环幂等**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6**
    - 实测：`disclosureSyncedTables.spec.ts` 24 / `d2NoteSectionMap.spec.ts` 34 / `d2DisclosureNote.spec.ts` 30 全绿
  - [x] 14.6 Playwright + DB 实测：组合改名 → 同步 → 附注 `sub_table_data` 与 `_sub_table_columns` 均只剩新名
    - _Requirements: 7.5, 7.6_
  - [x] 14.7 基线播种：上线前既存孤儿表自愈（R7.5，2026-07-30）
    - `disclosureSyncedTables.ts` 增 `TableNamespaceSpec` / `isOwnedTableName` /
      `noteExistingTableNames` / `seedSyncedTableBaseline`（跨循环可复用纯函数）
    - `d2NoteSectionMap.ts` 增 `D2_TABLE_NAMESPACE`（固定表名全集 ∪ 组合前缀 `组合计提项目：`
      ∪ 续表后缀 `（续：期初数）` ∪ 上市历史遗留静态旧名）；顺带把
      `D2_PORTFOLIO_TABLE_PREFIX` / `D2_SOE_PRIOR_SUFFIX` 提为常量，消除续表键双真源
    - `useD2DisclosureNote.seedSyncedTablesFromNote(noteTableData)`：清单为空时播种并持久化，
      非空则幂等返回（不发网络请求、不覆盖）；HTTP 取数留在组件层，composable 保持可单测
    - `D2DisclosureNoteBody.syncToDisclosureNotes`：首次同步前 `getDisclosureNoteDetail` 读一次，
      读取失败（附注未生成）不阻断同步
    - **🔴 谓词严格、宁漏不误杀**：同一附注章节可能被别的底稿推送（H2 明细 + H4 汇总），
      只认①固定表名全集 ②动态前缀 ③已知表名+续表后缀；只取 `sub_table_data` 与
      `_sub_table_columns` 的键（`_tables` 是读时投影/快照，`removed` 键删不动它，纳入只会虚报）
    - **Playwright + API 实测**（项目 `重庆医药集团宜宾医药有限公司新健康大药房临港店_2025` §八、5）：
      同步前 13 张子表（含上线前残留 `组合计提项目：应收中央企业客户`）→ 同步后 11 张，
      两张 `组合计提项目：*` 表在 `sub_table_data` 与 `_sub_table_columns` 双双清除
      （该底稿当前「暂无组合计提项目」，故两张皆为孤儿）；**再同步一次 11→11 稳态**（Property 9）
    - 账龄行同步口径同步复验：`1年以内（含1年）/1至2年/…/5年以上/小 计/减：坏账准备/合 计`
    - _Requirements: 7.5, 7.6_

- [x] 16. `sheet_name` 断言漂移统一清理（R8）
  - [x] 16.1 全量扫描分类：`sheet_name` / `sheetName` 断言逐条判定「漂移」vs「合法 wp_code / 归一化输入」
    - 判定口径：`payload.sheet_name` / `target.sheetName` → 漂移；`overrides[code]` / `extractSheet(input)` / `isDisclosureSheetName(input)` → 合法保留
    - 产出清单写回本 spec Notes（实测 10 条待修 + 白名单 10 来个文件，见下方 R8 清单）
    - _Requirements: 8.1, 8.2_
  - [x] 16.2 修 A1 合成标识型（8 条）：`f3NoteSectionMap.spec.ts`(2) / `g1DisclosureListed.spec.ts`(1) / `g2SoeDisclosure.spec.ts`(2) / `g3Disclosure.spec.ts`(3)
    - 断言值全部改引用各自 `X_DISCLOSURE_SHEET_NAME` 常量，无一处写字面量
    - _Requirements: 8.1, 8.3_
  - [x] 16.3 修 A2 短名型（4 条）：`g10DisclosureSyncPayload.spec.ts`(2) / `g11DisclosureSyncPayload.spec.ts`(2)
    - 同样改引用 `G10/G11_DISCLOSURE_SHEET_NAME` —— **不写字面量**：F3/F1 用**半角**括号 `附注披露信息(上市公司)`、G 系用**全角** `（上市公司）`，写死会再次分叉
    - _Requirements: 8.1, 8.3_
  - [x] 16.4 逐循环核对实现：F3/G1/G2/G3/G10/G11 的 `build*SyncPayload` 均已引用 `X_DISCLOSURE_SHEET_NAME`，实现侧无需改（漂移只在测试）
    - _Requirements: 8.6_
  - [x]* 16.5 新增守卫 `composables/__tests__/disclosureSheetNameRegistry.spec.ts`（6 项全绿）
    - **Property 11: `X_DISCLOSURE_SHEET_{NAME,LISTED,SOE}` 常量 = `note_workpaper_sync_registry.json` 的 `sheet_listed`/`sheet_soe` 逐字一致**
    - 覆盖面靠 `import.meta.glob('../**/*NoteSectionMap.ts', {eager:true})` 自动扩展；提取口径与生成脚本 `_WP_CODE` / `_SHEET_CONST` 正则同源（含 `_NAME` 两版共用一个名的形态）
    - 另加 3 条形态约束：禁合成标识 `/-note-(listed|soe)$/`、禁短名 `附注上市`/`附注国企`、须形如「附注披露…」且含变体标识（上市 / 国企 / 国有）
    - 防空转：断言 `declaredPairs > 40` 且有效比对数 `compared > 40`（实测 registry 34 entries / 67 个 sheet 值）
    - 失败提示 `python backend/scripts/gen_note_wp_sync_registry.py --write`；两个漂移方向（改 map 忘生成 / 手改 registry）都拦
    - **Validates: Requirements 8.4, 8.5**
  - [x] 16.6 复跑验证：6 个改动文件 36/36 绿；守卫 6/6 绿；`src/components/workpaper` 全量 `sheet_name` 类失败数 0
    - 登记但不修的预存在失败见下方表（`h8RightOfUseAssetsContract` / `useF3Integration` / `useF5Integration` / `useH4DualMode` / `d1NoteSectionMap` / `d2DisclosureNote` 等）
    - _Requirements: 8.3, 8.7_

- [x] 15. Checkpoint — R6 / R7 / R8 验收
  - Ensure all tests pass, ask the user if questions arise.
  - 门槛：D2 两版同步载荷账龄 label 为披露口径；改名场景 DB 无残留 key；`sheet_name` 断言零漂移且守卫生效

- [ ] 12. 收尾
  - [x] 12.1 清理临时脚本与 dump
  - [x] 12.2 更新 `.kiro/specs/INDEX.md`
  - [ ] 12.3 单 commit

## Notes

- **禁止杜撰列头**：每个 `label` 必须能指到源模板单元格或该 Tab 既有 `el-table-column label`；指不到就走 allowlist 并写明原因
- **不改推断算法本身**，只加 `flat` 旁路；`columns` 已声明但无 `group`/`flat` 的存量 Tab 行为保持不变，避免静默变样
- **分批闭环**：每批做完就跑该循环单测 + 覆盖守卫，不要 14 个全改完再验
- 前置依据：`f2-inventory-disclosure-template-alignment` 已端到端实测该链路（附注 TAB 页签 + 两级表头 + Word 导出）
- **R6/R7 并入来源**：`d2-ar-disclosure-soe-alignment` §O1/§O2 的两项遗留，用户 2026-07-29 决策
  「账龄标签走方案 A（同步层映射）」+「孤儿表清理先立 spec 并进本 rollout」
- **R6 边界**：本 spec 只做共享函数 + D2 两版落地 + warn 级扫描守卫；其余账龄循环
  （D1/D3/F1/K1/K3/G2/G5/D7/F4）随各自批次或后续 spec 收敛，不在本轮一次性铺开
  → **2026-07-30 已收敛完毕**：真实目标集为 D2 / F1 / F4 / K1 / G5 / D3（D6/D7 为守卫假阳性，
  与账龄档位无关；D1/K3/G2 无配置口径泄漏），守卫 `15/15`、`--strict` exit 0
- **R7 边界**：D2 为首个接入循环；其余有动态子表名的 Tab 按同一对纯函数接入，不各写一套
- **🔴 同步失败不得 `markSynced`**：否则下一次会把本轮表名当「上次已同步」，反而把现存表当孤儿删掉

### R6 收敛 + R7.5 基线播种（2026-07-30 落地）

**守卫两类误判都修了**（Task 13.6）：假阳性 D6/D7（只出现「账龄」二字，与档位无关）、
假阴性 G5（文件名不匹配旧 `FILENAME_RE`，而其 `1-2年`/`2-3年` 是真漂移）。
判定按**循环**而非单文件（映射可合法落在该循环任一文件：F1 在 `useF1Disclosure*`、D2 在 `d2NoteSectionMap`）。

**顺带修掉的 3 个实质缺陷**（均非本 spec 目标，但阻断验证/属同族）：

1. **🔴 D2 披露 sheet 分发被 wp_code 后缀抢占（Playwright 实测发现）**
   `workpaper_sheet_classification` 里 D2-1 的披露 tab 名为 `附注披露信息（国企）D2-1` /
   `附注披露信息(上市公司）D2-1` —— 尾部带 wp_code。`GtD2AccountsReceivable.currentSheet`
   **先**跑 `/D2(?:-\d+)?[A-Z]?$/` → 判成 `D2-1` → 渲染「应收账款审定表」，
   **国企/上市披露组件永远挂不上**。`get_diagnostics` 与 vitest 均查不出。
   修法：抽出纯函数 `d2Constants.normalizeD2SheetName()`，把「附注」判定**前置**于 wp_code 正则，
   且「国企」「国有」两种写法都认；守卫 `composables/__tests__/d2SheetRouting.spec.ts`（9 项）。
2. **D3 国企同步静默校对恒为 0**：`D3TabDisclosureSoe` 取 `section1Subtotal.value?.current`，
   而 `SoeDisclosureRow` 的期末数字段是 `endAmount`（无 `current`）→ 改为 `endAmount`。
3. **`（续：期初数）` 续表键双真源**：`buildD2SyncPayload` 内联字面量 → 提为 `D2_SOE_PRIOR_SUFFIX`
   并被 `D2_TABLE_NAMESPACE.soe.suffixes` 复用。

**已知遗留（不在本 spec 范围，需另立 spec）**：
`applicable_standards` 前端全链缺失 → **D3 上市/国企披露 Tab 对所有项目都显示「当前项目不适用…」**。
实证：`/api/projects/{id}` 响应体**不含任何 standard 字段**（库里 `applicable_standard_v2` =
`{scope:'standalone', stage:'normal', entity_type:'soe'}`）；`useWpRenderSchema` 显式写
`applicable_standards: undefined`；`GtD3PrepaidAccounts` 只从 `htmlData` 取 → 恒为 `''`。
且共享的 `normalizeApplicableStandards` 对 v2 对象只认 `type/code/value`，
不认 `{entity_type, scope}` → 即便后端补字段仍返回 `[]`（应派生 `soe_standalone`）。
属**跨前后端 schema 变更 + 影响全部 gating 循环**，须先立 spec。
故 D3 账龄映射本轮以 10 项契约测试（`d3NoteSubtableContract.spec.ts`）锁定，UI 实测待该 spec 落地。

**Task 3.3 Playwright 实测纪实（2026-07-29）**

实测对象：项目「重药控股安徽有限公司_2025」（`0ec33ac9-…`）§五、9 存货，
`_source=workpaper` / `_last_sync_sheet=附注披露信息（上市公司）` / `last_sync_wp_id=F2(2cc1a1ed-…)`。

**🔴 前置发现：`_sub_table_columns` 是同步时快照，标 `flat` 不会自动生效**——
库内该附注上次同步于 flat 落地之前，`_sub_table_columns` 无 `flat` 字段，
附注侧仍在吃前缀推断。必须**重新点一次「同步到附注」**才刷新列元数据。
（同理：存量已同步项目都需重新同步一次才消除凭空父表头，与
`disclosure_notes.table_data` 快照语义一致。）

重同步前后 `GET /api/disclosure-notes/{pid}/2025/五、9` 的 `_tables[]._column_groups`：

| 表 | 重同步前（推断） | 重同步后（flat） |
|---|---|---|
| 周转房 | `[{本期, start:2, span:2}]` ← 凭空 | `[]` |
| 开发产品 | `[{本期, start:3, span:2}, {期末, start:5, span:2}]` ← 凭空 2 个 | `[]` |
| 开发成本 | `[{预计, start:2, span:2}]` ← 凭空（「预计竣工时间/预计总投资」被当同族） | `[]` |
| 确认为存货的数据资源 | `null`（推断也没猜出） | `[]` |

**附注页 DOM 复验**（`/projects/{pid}/disclosure-notes` → 五、9 存货 → 逐 TAB 读
`.gt-de-note-table .el-table__header-wrapper thead tr`）：

| TAB | 表头行数 | 表头文本 |
|---|---|---|
| 开发成本 | **1** | 项目名称 / 开工时间 / 预计竣工时间 / 预计总投资 / 期末数 / 上年年末数 / 期末跌价准备 |
| 开发产品 | **1** | 项目名称 / 竣工时间 / 期初余额 / 本期增加 / 本期减少 / 期末余额 / 期末跌价准备 |
| 周转房 | **1** | 项目名称 / 期初余额 / 本期增加 / 本期减少 / 期末余额 |
| 确认为存货的数据资源 | **1** | 项目 / 外购… / 自行加工… / 其他方式取得… / 合计 |

**对照组（真两级表头未被误伤）**：
- 存货分类 = 2 行，`项目[rowspan=2] | 期末余额[colspan=3] | 上年年末余额[colspan=3]`
- 存货跌价准备及合同履约成本减值准备 = 2 行，`项目[rs=2] | 期初余额[rs=2] | 本期增加[cs=2] | 本期减少[cs=2] | 期末余额[rs=2]`
  —— 说明「本期增加/本期减少」作为**显式声明**的子列仍正常合并，flat 只抑制推断。

结论：R3.4 达成，4 张单级表在附注侧均为单行表头，无「本期」等凭空父表头。

**环境注记**：Playwright MCP 中途 `Connection closed` 掉线，改用 chrome-devtools MCP
新开实例重新登录（admin）完成 DOM 复验；两条链路（API + DOM）结论一致。

### R6/R7 实施纪实与残留边界（2026-07-29 落地）

**R6 落地实测**：附注 `八、5` 账龄行已为
`1年以内（含1年）/1至2年/2至3年/3至4年/4至5年/5年以上/小 计/减：坏账准备/合 计`；
底稿页仍显示 `1-2年 / 小计 / 合计`（Property 8 成立）。
**F1 重复实现已收敛**：并发会话在 `f1-prepayment-disclosure-template-alignment` 里
用 per-cycle 常量（`NOTE_AGING_LABEL` / `SOE_AGING_LABEL`）独立实现了同一方案 A，
两份表与共享表**逐项同值**（含 `within1` 的上市/国企分叉）—— 互为印证，但属重复维护。
已收敛到共享模块：新增 `lookupDisclosureAgingLabel(key, overrides?)`（未命中返回
`undefined`，以保留 F1 原三级回退链 `映射 || ADJUDICATION_LABEL_BY_SEGMENT_KEY || seg.label`；
若用 `toDisclosureAgingLabel` 会因「命中值恰等于配置 label」误落回退分支，如 `over5`）。
F1 相关 54 测试全绿。

守卫 `check_disclosure_aging_label_coverage.py` 按**循环**维度判定覆盖
（映射可合法落在 `use*Disclosure*.ts` 而非 payload 文件），实测 **2/8（D2 + F1）**，
待收敛 5 个：`d3` / `d6` / `d7` / `f4` / `k1`（2 个文件）。

**合计字面统一（超出 R6.5 字面范围但必须做）**：原实现 11 处硬编码 `'合计'` + 2 处 `'合 计'`，
若只改账龄表会造成同一附注章节内 `合 计` 与 `合计` 混排。已全部收敛到
`DISCLOSURE_TOTAL_LABEL`，并让 `isTotalLabel` 容忍全/半角空格
（否则映射后 `合 计` 判不出合计行 → 丢 `is_total`）。

**🔴 R6 前置条件易漏**：映射按账龄段 `key` 生效，而 `buildSnapshot` 原先没透出 `key`
——单测自造快照带了 key 所以全绿，实际同步只有结构行被映射、账龄段没变。
已补 `buildSnapshot` 透出 `key` + `d2DisclosureNote.spec.ts` 专项守卫断言。
**其余循环接入 R6 时必须同时检查其 `buildSnapshot` 是否透出账龄段 key。**

**🔴 顺带修掉的平台级缺陷**：`markSynced` 每次同步都写同一 `item_id`，
与 autoSync 撞在同一个 2s 防抖批次里 → 后端「同一批次不得重复提交相同 item_id」
整批 PUT 被拒。两处修：`markSynced` 值未变则不写；组件 `debouncedSave`
按 `item_id` 去重（后写覆盖先写）。**其他循环的 `debouncedSave` 同样是裸 push，同类风险未排查。**

**R7 残留边界（不在 R7 验收范围，需要时单独处理）**：diff 机制只覆盖
「持久化基线建立**之后**」的改名/删除。R7 上线前就已存在的孤儿表
（本次实测项目里的 `组合计提项目：应收中央企业客户`）不会被自动清掉——
底稿侧无从知道附注里那些历史 key 属于自己还是别的底稿推的。
若要自愈需在首次 `markSynced` 时用「该底稿表名命名空间」过滤附注现存表名来播种基线
（D2 的命名空间 = `D2_TABLE_NAMES[variant]` ∪ `（续：期初数）` ∪ `组合计提项目：*` 前缀），
属新增网络读 + 命名空间谓词，本轮未做。

### R8 并入来源与待修清单（2026-07-29 实测）

来源：`f1-prepayment-disclosure-template-alignment` §S7 —— F1 的 2 条已在其 spec 内修掉，
用户 2026-07-29 决策「其余同类并入本 rollout 统一清理」。

`npx vitest run src/components/workpaper` 全量实测（1290 文件 / 17267 测试）中，
`sheet_name` 漂移类共 **10 条，已全部修完**（改为引用常量，不写字面量）：

| 形态 | 文件 | 条数 | 原断言值 → 现引用 | 状态 |
|------|------|------|------------------|------|
| A1 合成标识 | `__tests__/f3NoteSectionMap.spec.ts` | 2 | `F3-note-soe` / `F3-note-listed` → `F3_DISCLOSURE_SHEET_NAME.{soe,listed}` | ✅ |
| A1 | `composables/__tests__/g1DisclosureListed.spec.ts` | 1 | `G1-note-listed` → `G1_DISCLOSURE_SHEET_NAME.listed` | ✅ |
| A1 | `composables/__tests__/g2SoeDisclosure.spec.ts` | 2 | `G2-note-listed`（`sheetName` + `sheet_name` 各 1）→ `G2_DISCLOSURE_SHEET_NAME.listed` | ✅ |
| A1 | `composables/__tests__/g3Disclosure.spec.ts` | 3 | `G3-note-listed` ×2 / `G3-note-soe` ×1 → `G3_DISCLOSURE_SHEET_NAME.*` | ✅ |
| A2 短名 | `composables/__tests__/g10DisclosureSyncPayload.spec.ts` | 2 | `附注上市` / `附注国企` → `G10_DISCLOSURE_SHEET_NAME.*` | ✅ |
| A2 | `composables/__tests__/g11DisclosureSyncPayload.spec.ts` | 2 | 同上 → `G11_DISCLOSURE_SHEET_NAME.*` | ✅ |

**🔴 修正手法必须是「引用常量」而非「改字面量」**：实测各循环真实 tab 名的括号形态**不统一**
（F1/F3 半角 `附注披露信息(上市公司)`；G 系全角 `（上市公司）`；H/I/J/K/M 系 8 处用
`附注披露信息（国有企业）`；D6 甚至是混括号 `附注披露信息(上市公司）`）——
写死字面量必然再次分叉。registry 实证：34 entries / 67 个 sheet 值 / 8 种不同写法。

**🔴 合法用法白名单（不得改）**：`X-note-listed` 同时是 wp_code 形态，以下断言正确：
`useF2InventoryMainRegistration.spec.ts` / `useF3NotesPayableRegistration.spec.ts` /
`useF4AccountsPayableRegistration.spec.ts` / `useG2InterestReceivableRegistration.spec.ts` /
`useG3DividendReceivableRegistration.spec.ts` / `f1-registry-contract.spec.ts` /
`f2DisclosureAiReviewWiring.spec.ts` / `disclosureSyncBar.spec.ts` /
各 `*.integration.spec.ts` 的 `extractSheet()` 输入样本 / `i2SheetDispatch.spec.ts`。

**守卫**：`composables/__tests__/disclosureSheetNameRegistry.spec.ts`（6 项，Property 11）。
按 `import.meta.glob` 扫全部 `*NoteSectionMap.ts` 取 `X_DISCLOSURE_SHEET_{NAME,LISTED,SOE}`，
与 registry 逐字比对；另禁合成标识 / 短名 / 非「附注披露…」形态；防空转下限
`declaredPairs > 40` 且 `compared > 40`。新循环声明常量后自动纳入，无需登记。

**登记但不修的预存在失败**（同批实测发现，不属 R8）：

| 文件 | 根因 |
|------|------|
| `h8RightOfUseAssetsContract.spec.ts` | `wp_code_overrides` 映射数 16 → 20（注册漂移，属 H8 循环） |
| `useF3Integration.spec.ts` | EventBus `substantive:adjudicated(2201)` 刷新值 1000 vs 1400 |
| `useF5Integration.spec.ts` | EventBus `substantive:adjudicated(6401)` 未产出 |
| `useH4DualMode.spec.ts` | OO 健康检查后未切模式 |
| `d1NoteSectionMap.spec.ts` | 国企表名缺 `期初账面余额`（属 D1 循环） |
| `d2DisclosureNote.spec.ts` | 账龄结构行 10 vs 9（属 `d2-ar-disclosure-soe-alignment`） |
| `b23ProcessControl*` / `n1-linkage-fixes` / `l4-bonds-payable` / `j2RuntimeMigration` / `a173ConsultationRecord` / `GtG0Confirmation` | 与披露无关 |

### 🔴 并发会话覆盖事故与复原（2026-07-29）

**发生了什么**：R6/R7（Task 13/14）由另一会话先行实现（`disclosureAgingLabels.ts` /
`disclosureSyncedTables.ts` + D2 全链接线 + F1 改用共享表）。本会话按 tasks.md 的
`[~]`（未完成）标记去做 13.1/14.1，用 `fs_write` **整文件覆盖**了那两个共享模块，
导致 `d2NoteSectionMap.ts` / `useF1Disclosure{Listed,Soe}.ts` 引用的
`DISCLOSURE_TOTAL_LABEL` / `lookupDisclosureAgingLabel` / `DISCLOSURE_STRUCT_ROW_LABELS`
/ `DISCLOSURE_AGING_LABEL_VALUES` 全部消失（编译期即断）。

**为什么没被立刻发现**：两个模块与其消费方**都是未跟踪新文件**（`git status` 为 `??`），
`git` 无法恢复；`get_diagnostics` 当时只查了我新写的文件，没查消费方。

**怎么复原的**：另一会话的契约测试位于 `components/workpaper/__tests__/`（我写的在
`components/workpaper/composables/__tests__/`，路径不同故**未被覆盖**）→ 那两个 spec
连同 `d2NoteSectionMap.ts` 的调用点，完整还原了 API 契约（导出名、签名、返回值三态）。
据此重写模块，删掉我那两个设计冲突的重复 spec，跑 125 项相关测试全绿。

**教训（已写入 memory）**：

1. **共享模块动手前先 `grep` 消费方**：`?? 未跟踪` ≠ 不存在，多会话下新文件随时可能已被别人建好；
2. **禁止对可能已存在的文件用 `fs_write`**（整文件覆盖），改用 `str_replace` 增量，
   或先 `read_file` 确认内容；
3. **改完共享模块必须 `get_diagnostics` 查全部消费方**，不只查自己新写的文件；
4. **tasks.md 的 `[~]`/`[ ]` 标记不可信**（另一会话完成后未必回写；本轮 13.2~14.6 甚至被
   自动标成 `[x]` 而实际由对方完成）→ **以代码 grep 为准，不以标记为准**。

### 覆盖基数校正：14 → 16（F4 两处）＋ 守卫假阴性修复（Task 5.3，2026-07-30 实测）

**① 守卫此前把 L1/L3 四个 Tab 误报为「缺 columns」（假阴性）。**
`check_disclosure_columns_coverage.py` 的内联检测锚点写成 `sub_table_data\s*:`（只认冒号），
而这 4 个 `.vue` 用的是 **ES6 对象简写**：

```ts
const { sub_table_data, columns } = buildL1SyncPayload({ … })
await http.post(`…/disclosure-notes/sync-from-workpaper`, { …, sub_table_data, columns })
```

→ 邻近窗口从未触发，守卫报未覆盖。**修的是守卫，不是应用代码**：守卫的职责就是判定
「同步调用点是否携带列头元数据」，为了迁就正则去把简写改成 `sub_table_data: sub_table_data`
属于本末倒置；也**没有**把 `buildL1SyncPayload` / `buildL3SyncPayload` 塞进 `COLUMN_BUILDERS`
白名单（design §0① 明确要避免靠扩白名单蒙混过关）。

改动（`backend/scripts/check/check_disclosure_columns_coverage.py`）：

| 项 | 前 | 后 |
|---|---|---|
| 锚点正则 | `sub_table_data\s*:` | `\bsub_table_data\s*[,:}\n]` |
| 字段正则 | `\bcolumns\s*:` | `\bcolumns\s*[,:}\n]` |

后随字符限定为 `, : }` 或换行 → 简写与显式键都认，而 `columns.forEach` / `columnsRef`
之类属性访问/标识符前缀**不**被误当字段；邻近窗口（±400）保留，故远处的
`summary-method({ columns }: { columns: any[] })` 类型注解仍不算覆盖。
**放宽的是写法，不是实质要求**：通篇没有 `columns` 的调用点照旧判未覆盖（已加测试守住）。

守卫单测新增 `backend/tests/scripts/test_check_disclosure_columns_coverage.py`（10 项全绿）：
简写→覆盖 / 显式键→覆盖（防回归）/ 简写但无 columns→未覆盖 / 远处类型注解→未覆盖 /
`columns.forEach`→未覆盖 / builder 白名单与 `build*Columns` 正则→覆盖 / allowlist 原因空白不豁免。

**修复前后实测**（`python backend/scripts/check/check_disclosure_columns_coverage.py`）：

| | 调用点总数 | 已覆盖 | 未覆盖 |
|---|---|---|---|
| 修复前 | 92 | 76 | **16** |
| 修复后 | 92 | 80 | **12** |

差值恰为 4，且消失的正是 `l1/core/L1TabDisclosure{Listed,Soe}.vue` /
`l3/core/L3TabDisclosure{Listed,Soe}.vue` —— 无第 5 个文件被"顺带"判绿
（逐文件比对新旧判定的翻转清单实测只有这 4 条），故正则放宽未误伤 backlog 可见性。

**② requirements.md 的「14 个未覆盖」漏了 F4 两处。** 守卫实测未覆盖为 16：

| 循环 | 未覆盖路径 | 是否在 requirements 表内 |
|---|---|---|
| F4 | `composables/useF4DisclosureListed.ts` | ❌ 漏记 |
| F4 | `composables/useF4DisclosureSOE.ts` | ❌ 漏记 |
| 其余 14 | H4 / J1×2 / K4 / K5×2 / K6×2 / K7×2 / L1×2 / L3×2 | ✅ |

F4 两处是**真未覆盖**（不是假阴性）：其 `syncToNotes()` 直接 `api.post(url, buildSyncPayload())`，
而本地 `buildSyncPayload()` 产出的载荷通篇无 `columns`（两文件 `columns` 出现次数为 0）。
F4 未被 requirements 记入，可能是因为它不是 `*TabDisclosure*.vue` 而是 composable。

**对 Task 8.2 的影响**：批 1~4 覆盖的是 14 个 Tab，全做完未覆盖数是 **2（F4）而非 0**，
`--strict` 仍会 exit 1、CI job 仍红。故 8.2 的验收门槛须二选一（留给后续决策）：

- 把 F4 两处纳入某一批（列头依据：`f4NoteSectionMap` + F4 应付账款源模板披露 sheet）；
- 或按 R4.3 登记 allowlist 并写明原因（哪一波迁移、依据哪个源模板）。

无论哪种，**「未覆盖数为 0」不会因批 1~4 做完而自动达成**。

**Task 11.3 Playwright 实测纪实（2026-07-30，K6 两版 + K7 单级对照）**

**抽样理由**：K6 持有待售资产是本轮 rollout **唯一真两行表头**的 Tab，且两个变体的
父表头串**不同**（上市「期末余额 / 上年年末余额」／ 国企「期末数 / 期初数」）→ 一次抽样
同时验证「两级表头正确」与「变体串不串味」。K7 递延收益作单级对照（`flat` 抑制推断）。

**环境注记**：Playwright MCP 仍 `Not connected` → 沿用 task 3.3 的替代链路
**chrome-devtools MCP**（登录后复用同一 tab，goto + 点 Tab + 等组件根 + 点同步 + 读消息
压进单个原子脚本）+ **postgres MCP 只读**核对落库 + 浏览器内 `fetch` 拉 API 投影。
**本会话重新点过「同步到附注」**（`_sub_table_columns` 是同步时快照，读旧附注等于读陈旧列元数据）。

**🔴 上市变体活体可达（修正 F1 spec 的悲观结论）**：8 个在册项目 `entity_type` 确实全为 `soe`，
但 **K6/K7 主入口 `currentSheet` 只按 sheet 名分发、无 `applicable_standards` gating**，
且项目「重药控股安徽有限公司_2025」的附注是 **listed 模板**生成（`source_template=listed`，
有 五、11 / 五、51 而无 八、12 / 八、56）→ 上市变体**同样是 DOM 实测**，无需降级 API 证明。

| Tab | 变体 | 项目 / 章节 | 附注表头行数 | `th` 文本与跨格 | 证据 |
|---|---|---|---|---|---|
| K6 持有待售资产 | 国企（八、12） | 宜宾…临港店_2025 `c8621493` | **2** | 行1 `项目[rs=2] / 期末数[cs=3] / 期初数[cs=3]`；行2 `账面余额 / 减值准备 / 账面价值` ×2 | **DOM** + API + DB |
| K6 持有待售资产和持有待售负债 | 上市（五、11） | 重药控股安徽_2025 `0ec33ac9` | **2** | 行1 `项目[rs=2] / 期末余额[cs=3] / 上年年末余额[cs=3]`；行2 `账面余额 / 减值准备 / 账面价值` ×2 | **DOM** + API + DB |
| K7 递延收益 | 国企（八、56） | 宜宾…临港店_2025 `c8621493` | **1** | `项目 / 期初余额 / 本期增加 / 本期减少 / 期末余额`（**无「本期」父表头**） | **DOM** + API + DB |

**API 投影核对**（浏览器内 `GET /api/disclosure-notes/{pid}/2025/{section}`，`_source=workpaper`）：

| 章节 | `_tables[0].name` | `_column_groups` |
|---|---|---|
| 八、12 | `持有待售资产` | `[{期末数,start:1,span:3},{期初数,start:4,span:3}]` |
| 五、11 | `持有待售资产和持有待售负债` | `[{期末余额,start:1,span:3},{上年年末余额,start:4,span:3}]` |
| 八、56 | `递延收益` | `[]` ← 显式单级（`flat`），非 `null` 推断 |

**sheet 名分发实测（防「国有企业 ≠ 国企」陷阱）**：K6 国企 tab 真名 `附注披露信息(国企）`
（半角开 + 全角闭）、K7 国企 tab 真名 `附注披露信息（国有企业）` —— 两者点开后
`.k6-tab-disclosure-soe` / `.k7-tab-disclosure-soe` 均挂载，且对应 `-listed` 根
**同时为未挂载**（选择器带组件根作用域校验），落库 `_last_sync_sheet` 与 tab 名逐字一致
（`附注披露信息(国企）` / `附注披露信息（国有企业）`）→ 两循环的 `/附注.*国/` 写法安全。

**DB 时间戳（本会话新写，非陈旧快照）**：八、12 `05:02:48Z` / 五、11 `05:04:04Z` /
八、56 `05:05:23Z`，`last_sync_source=workpaper`。

结论：R5.4 达成 —— 抽样 1 上市（K6 五、11）+ 1 国企（K6 八、12）经「披露表点同步 → 附注」
全链路，附注侧两级表头的父表头串、`rowspan`/`colspan` 区间与源模板一致；同一轮 K7 国企
单级表确认 `flat` 在活体上仍抑制前缀推断（1 行表头、零凭空父表头）。

### 🔴 跨 spec 交接：守卫剩余 6 条未覆盖归属 `disclosure-sync-path-buildout`（Task 12.2，2026-07-30 实测）

`python backend/scripts/check/check_disclosure_columns_coverage.py --strict` 最新实测：

| | 调用点总数 | 已覆盖 | allowlist 豁免 | 未覆盖 | exit |
|---|---|---|---|---|---|
| 批 4 收口时 | 92 | 92 | 0 | **0** | 0 |
| 本次（2026-07-30 清理后） | **98** | 92 | 0 | **6** | **1** |

未覆盖 6 条：

```
components/workpaper/g12-net-hedge-gains/core/G12TabDisclosureListed.vue
components/workpaper/g12-net-hedge-gains/core/G12TabDisclosureSOE.vue
components/workpaper/g5-long-term-receivable/core/G5TabDisclosureListed.vue
components/workpaper/g5-long-term-receivable/core/G5TabDisclosureSOE.vue
components/workpaper/g8-other-equity-instruments/core/G8TabDisclosureBase.vue
components/workpaper/g9-other-noncurrent-financial/core/G9TabDisclosureBase.vue
```

**归属判定**：调用点总数 92 → 98（**+6，与这 6 条一一对应**），且 6 条全部是并发 spec
`disclosure-sync-path-buildout` 批 1 新接线的 G 循环 Tab（其 tasks.md 2.2/2.4/2.5/2.8 已标完成，
Notes 第 6 条亦自记「新 builder 必须登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`」）。
本 rollout 批 1~4 覆盖的 14 个 Tab 与 F4 两处**无一在列**。

**影响**：CI job `disclosure-columns-coverage` 当前为**红**，原因在 `disclosure-sync-path-buildout`
而非本 spec。该 job 的注释仍写「92/92 调用点已覆盖」，属陈述过时——由接手 spec 补齐列头后一并更新，
本 spec 不改（避免两个 spec 抢同一文件）。

**不走 allowlist**：这 6 条不是本 spec 的迁移波次，登记豁免会把别的 spec 的欠账写成本 spec 的永久例外。
