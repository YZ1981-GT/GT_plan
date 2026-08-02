# Implementation Plan: M 循环四表库取数 + 披露同步 + 附注结构对齐

## Overview

M 循环 10 个底稿（M1~M10）覆盖所有者权益类科目。当前后端 render 全部硬编码科目码（3 个取错科目族），前端 13 个披露 Tab 无同步链路，附注模板 8 个章节列结构与源 xlsx 不一致。分 3 波实施：Wave 1 基础设施 + 简单循环 → Wave 2 中等复杂度 → Wave 3 OCI 重建。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "基础设施 + 简单循环（M3/M6/M8）",
      "tasks": ["task-1", "task-2", "task-3", "task-4", "task-5", "task-6"]
    },
    {
      "id": "wave-2",
      "name": "中等复杂度循环（M1/M2/M10）+ M4/M5/M7 补强",
      "tasks": ["task-7", "task-8", "task-9", "task-10", "task-11"]
    },
    {
      "id": "wave-3",
      "name": "高复杂度循环（M9）+ 全量回归",
      "tasks": ["task-12", "task-13", "task-14"]
    }
  ]
}
```

## Wave 1: 基础设施 + 简单循环

- [x] Task 1: 后端 render 策略纠偏（M3/M6/M7/M8/M9/M10 科目码修正 + 前缀匹配改造）
  - [x] 1.1 M3 `_M3_ACCOUNT_CODE` 从 `4002` 改 `4201`（库存股）；查询改 `LIKE '4201%'`
  - [x] 1.2 M7 `_M7_ACCOUNT_CODE` 从 `4201` 改 `4301`（专项储备）；查询改前缀匹配
  - [x] 1.3 M8 `_M8_ACCOUNT_CODE` 从 `4104` 改 `4302`（一般风险准备）
  - [x] 1.4 M9 `_M9_ACCOUNT_CODE` 从 `4103` 改 `4003`（其他综合收益）
  - [x] 1.5 M10 `_M10_ACCOUNT_CODE` 从 `4003` 改 `4401`（其他权益工具）；`formula_direction` 同步修正
  - [x] 1.6 M1 `formula_direction.account_code` 保持 `2232` 不动；M2 保持 `4001`；M4 保持 `4002`；M5 保持 `4101`；M6 保持 `4104` —— 这 5 个码本身正确，只需改查询为前缀匹配
  - [x] 1.7 所有策略查询改 `LIKE code || '%'` 或 `startswith(code + '.')` 并聚合叶子

- [x] Task 2: 公式预设纠偏（`prefill_formula_mapping.json`）
  - [x] 2.1 M1 块：块名「应付股利审定表」+ codes `['2232']` + 公式全替 + 删 `分析程序M1-3` 块（sheet 不存在）
  - [x] 2.2 M3 块：「库存股审定表」+ codes `['4201']` + 公式全替
  - [x] 2.3 M4 块：「资本公积审定表」+ codes `['4002']`
  - [x] 2.4 M5 块：「盈余公积审定表」+ codes `['4101']`
  - [x] 2.5 M6 块：「未分配利润审定表」+ codes `['4104']`
  - [x] 2.6 M7 块：codes `['4301']` 正确不动
  - [x] 2.7 M8 块：codes `['4302']`正确不动
  - [x] 2.8 M9 块：codes `['4003']`（其他综合收益） + 明细表块 `6901.01/.02` 保留（损益科目取 OCI 发生额）
  - [x] 2.9 M10 块：codes `['4401']`
  - [x] 2.10 删 M2 明细表块的 9 条硬编码客户编码 `AUX` 条目

- [x] Task 3: 附注模板结构修复 — 幂等脚本 `fix_note_m_equity_structure.py`
  - [x] 3.1 五、53 股本：两级 8 列重建 + 删 `header_label` + 行骨架
  - [x] 3.2 八、58 实收资本：两级 7 列 + `投资者名称` 标签列 + 动态行骨架
  - [x] 3.3 五、54 其他权益工具：3 表改名 + 表2 两级 9 列 + text 修复
  - [x] 3.4 八、59 其他权益工具：两级 9 列
  - [x] 3.5 五、56 库存股：补 5 列 flat + guidance
  - [x] 3.6 五、57 其他综合收益：两级 8 列 + 删假行 + 补 `以后` 二字
  - [x] 3.7 八、79 归属于母公司 OCI：两级 7 列 + 补表(2) 列转置 + 补行
  - [x] 3.8 五、60 一般风险准备：新建 5 列 flat 表 + 3 行骨架 + guidance
  - [x] 3.9 **八、94（新建）一般风险准备**：插入章节 + 5 列表 + 行骨架 + `variant_matrix` 登记
  - [x] 3.10 八、63 未分配利润：修列名 + 删 `……` + 补 columns
  - [x] 3.11 五、61 未分配利润：补 columns + guidance + 修行名

- [x] Task 4: 后端守卫 `test_note_m_equity_structure.py` + CI job `note-m-equity-structure`
  - [x] 4.1 openpyxl 直读源 xlsx 交叉比对 10 个章节
  - [x] 4.2 反向自检（`_norm` 归一 + 表名断言非空 + 行数上下界）
  - [x] 4.3 CI governance-checks.yml 挂 `note-m-equity-structure` job

- [x] Task 5: M3 库存股披露接线
  - [x] 5.1 新建 `m3NoteSectionMap.ts`（五、56 仅上市；5 列 flat + 动态行 + text）
  - [x] 5.2 `M3TabDisclosureListed.vue` 接 `useDisclosureAutoSync` + `syncToDisclosureNotes`
  - [ ] 5.3 `el-input-number`→`WpAmountInput`（3 处）
  - [ ] 5.4 前端契约 `m3NoteSubtableContract.spec.ts`

- [x] Task 6: M6 未分配利润披露接线
  - [x] 6.1 新建 `m6NoteSectionMap.ts`（五、61 + 八、63；固定行 + 4/3 列 flat + text）
  - [x] 6.2 两个 Tab 接同步 + `el-input-number`→`WpAmountInput`
  - [ ] 6.3 前端契约 `m6NoteSubtableContract.spec.ts`

## Wave 2: 中等复杂度

- [ ] Task 7: M1 应付股利浅合并推 K3
  - [ ] 7.1 新建 `m1NoteSectionMap.ts`（引用 `K3_LISTED_SUBTABLE.dividend/.dividendOverdue` + `K3_SOE_SUBTABLE.dividend`；列定义复用 K3 既有）
  - [ ] 7.2 两版 Tab 接 `useDisclosureAutoSync` + `syncToDisclosureNotes`
  - [ ] 7.3 「超过1年」判定复用 `useAgingConfig` 首档（`dayTo=365` → 超过即 >365d）
  - [ ] 7.4 `el-input-number`→`WpAmountInput`（4 处）
  - [ ] 7.5 守卫：M1 推送的子表键与 K3 推送的键无交集

- [ ] Task 8: M2 实收资本/股本披露接线
  - [ ] 8.1 新建 `m2NoteSectionMap.ts`（五、53 两级 8 列 + 八、58 两级 7 列）
  - [ ] 8.2 两版 Tab 接同步 + 动态插行（叶子科目 4001.xx 自动展开投资者行）
  - [ ] 8.3 `el-input-number`→`WpAmountInput`（6 处）
  - [ ] 8.4 前端契约 `m2NoteSubtableContract.spec.ts`

- [ ] Task 9: M10 其他权益工具披露接线
  - [ ] 9.1 新建 `m10NoteSectionMap.ts`（五、54 三表 + 八、59 一表；两级 9/10 列）
  - [ ] 9.2 两版 Tab 接同步 + 动态插行（金融工具可增删）
  - [ ] 9.3 `el-input-number`→`WpAmountInput`（7 处）
  - [ ] 9.4 前端契约 `m10NoteSubtableContract.spec.ts`

- [ ] Task 10: M8 一般风险准备披露接线
  - [ ] 10.1 新建 `m8NoteSectionMap.ts`（五、60 + 八、94；5 列 flat + 动态插行）
  - [ ] 10.2 两版 Tab 接同步 + `el-input-number`→`WpAmountInput`（6 处）
  - [ ] 10.3 前端契约 `m8NoteSubtableContract.spec.ts`

- [ ] Task 11: M4/M5/M7 补强
  - [ ] 11.1 三循环 6 个 Tab `el-input-number`→`WpAmountInput`（M7 已 0 处，M4/M5 各 6 处）
  - [ ] 11.2 三循环审定表 Tab 接入 `WpFourTableSourcePanel`（溯源面板 + 「从四表库带入未审数」）
  - [ ] 11.3 M4/M5/M7 后端 render 改前缀匹配 + 输出 `tb_source_codes` + `tb_values`
  - [ ] 11.4 前端契约补全（`mEquityNoteSubtableContract` 已有，确认 P1~P6 全通过）

## Wave 3: 高复杂度 + 全量回归

- [ ] Task 12: M9 其他综合收益披露接线
  - [ ] 12.1 新建 `m9NoteSectionMap.ts`（五、57 两表两级 8 列 + 八、79 两表两级 7/9 列）
  - [ ] 12.2 上市 Tab 重建：两大类 × (行集 + 可扩行 + 公式列读时推导) + 合计
  - [ ] 12.3 国企 Tab 重建：11 类分项×「小计=税前−转入」 + 表(2) 列转置余额调节表
  - [ ] 12.4 M9 AI context 改动态取数 + `el-input-number`→`WpAmountInput`（16 处）
  - [ ] 12.5 前端契约 `m9NoteSubtableContract.spec.ts`
  - [ ] 12.6 后端 M9 render 输出 `tb_source_codes`（含 `4003` 叶子分类 → OCI 各项目预填）

- [ ] Task 13: 全量测试 + registry 重生 + MISSING_SYNC_PATH 更新
  - [ ] 13.1 `gen_note_wp_sync_registry.py --write`（M1~M10 全部登记）
  - [ ] 13.2 `disclosureAutoSyncCoverage.spec.ts` 的 `MISSING_SYNC_PATH` 移出已补齐的 13 条
  - [ ] 13.3 后端全量 M 循环测试 + 前端 vitest 全量 workpaper 目录回归
  - [ ] 13.4 `disclosureColumnsCoverage.spec.ts` allowlist 移出 M 类条目

- [ ] Task 14: 真实 DB 实测 + 数据复原
  - [ ] 14.1 选 2 个项目（一个有 4001 子科目、一个 3xxx 旧准则）端到端跑 render
  - [ ] 14.2 浏览器实测：审定表「从四表库带入」→ 披露同步 → 附注落库验证
  - [ ] 14.3 测试数据全部复原



## Notes

### 调研结论（2026-08-02）

1. **系统性科目码错位**（DB 实证）：M3 取到资本公积(`4002`)、M7 取到本年利润(`4103`→4201)、M8 取到利润分配(`4104`)、M9 取到本年利润(`4103`)、M10 取到其他综合收益(`4003`)。公式预设 10 个审定表块整体贴错标签。
2. **项目间科目冲突**（活体 `37814426`）：`4301`=研发支出(debit)、`4401`=工程施工(debit)、`3102` 与 `4003` 并存 → 硬编码码取数在该项目**必然取到错误科目**。
3. **父码精确匹配致恒空**：5 项目中 2 个 `tb_balance` 无裸 `4001` 行（只有 `4001.01/.03/.05`），`== '4001'` 返回 0 行。
4. **M1 豁免不成立**：K3 侧应付股利/超1年两表**从不推送**（底稿无录入区块），M1 有完整录入 → 改浅合并推 K3 章节。
5. **M8 国企章节需新建**：`八、` 编号 1~93 无缺号 → 追加 `八、94`（sort_index 插位，不做编号重排）。
6. **M10 sheet 名分叉**：`附注披露信息核对（上市公司）`/`…核对（国企）` 与其余 9 循环的命名规则不同。
7. **前端 AI 接线**：M7/M4/M5 已真调端点；M9 context 科目码硬编码错误；其余 Tab 需逐个核查。
8. **M4/M5/M7 已接同步**（`mEquityChangeNoteSectionMap.ts`），只需补强：`el-input-number` 替换 + 溯源面板。
9. **动态取数设计**：复用 `four_table/report_line_accounts` + `leaf_aggregation` 共享件（M 是第 N+1 个消费者），各策略声明 `ReportLineAccountSpec`（per-cycle per-variant `row_code`），运行态自适应各项目科目表。
10. **`report_config` BS-076 跨准则歧义**：listed=其他权益工具 / soe=其中应付股利 → 解析必须传 `applicable_standards`。

### 用户裁决

- M8 国企：**新建章节 `八、94`**（sort_index 插位）
- M1：**浅合并推 K3 §五、42/八、42**（H4→H2 范式）
