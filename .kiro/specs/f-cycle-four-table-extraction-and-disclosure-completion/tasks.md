# Implementation Plan: F 类四表取数与披露附注收口

## Overview

把 G/K/D/N 循环已验证的「四表取数三层链路 + 分类桶单一真源 + 溯源下发 + 动态行」范式推广到
F3/F4/F5，复核 F1/F2 残余缺口、F 类四个附注章节与源模板的一致性、以及 F1~F5 的公式预设。
六个 wave 顺序执行：后端取数 → 公式预设 → 前端消费 → 披露表 → 附注同步 → 守卫与实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Wave 1: 后端分类桶真源 + F3/F4/F5 render 改造",
      "tasks": [1, 2, 3, 4]
    },
    {
      "name": "Wave 2: 公式预设纠错与补齐",
      "tasks": [5, 6]
    },
    {
      "name": "Wave 3: 前端科目真源 + 审定表预填 + 溯源面板",
      "tasks": [7, 8, 9]
    },
    {
      "name": "Wave 4: 披露表动态行与账龄枚举",
      "tasks": [10, 11]
    },
    {
      "name": "Wave 5: 附注模板复核 + 同步链路守卫",
      "tasks": [12, 13]
    },
    {
      "name": "Wave 6: 守卫补齐 + CI + 实测",
      "tasks": [14, 15, 16]
    }
  ]
}
```

## Tasks

- [ ] 1. 分类桶单一真源（三个新建模块）
  - [ ] 1.1 新建 `backend/app/services/four_table/f3_note_categories.py`：`F3Category` dataclass（`key`/`label`/`keywords`/`exclude_keywords`/`code_hints`/`source_ref`/`always_show`）+ `F3_CATEGORIES` 顺序即优先级 + `classify_f3_leaf(name, code)` + `f3_category_payload()`
  - [ ] 1.2 新建 `four_table/f4_nature_buckets.py`：五性质桶（货款/工程款/设备款/服务费/其他），`project` 声明在 `equipment` 之前（`2202.11 工程设备款` 归工程款，源模板 A9 在 A10 前），`other` 为 catchall；每条带 `source_ref` 指向 `审定表F4-1!A8~A12`
  - [ ] 1.3 新建 `four_table/f5_cost_segments.py`：主营 / 其他两段，`main` 必须带 `exclude_keywords=('其他业务',)` 否决词（否则「其他业务成本」被吃掉）
  - [ ] 1.4 三个模块统一提供 `classify_*` 纯函数（无 DB）+ `*_payload()` 下发前端，中文标签只存一份（前端不得抄第二份）
  - _Requirements: 1.4, 2.3, 2.4, 2.5, 3.3_

- [ ] 2. F3 render 改造（`_f3_notes_payable.py`）
  - [ ] 2.1 新增 `F3_ACCOUNT_SPEC = ReportLineAccountSpec(row_code='BS-044', fallback_gross=('2201',))`
  - [ ] 2.2 新增 `_load_f3_leaves(ctx, accounts)` 一次查询（`get_active_filter` 全签名 4 参 + await）
  - [ ] 2.3 新增纯函数 `build_f3_tb_values` / `build_f3_leaf_categories` / `build_f3_adjudication_prefill` / `build_f3_source_codes`
  - [ ] 2.4 `tb_values` 补期初键与两口径键；保留既有键 `tb_values['2201']` 语义不变（前端 `useF3FormData.seedTrialBalance` 已在读）
  - [ ] 2.5 删除 `_fetch_f3_2201_tb_balance` 里的 `code.startswith(_F3_ACCOUNT)` 裸前缀段，改委托 `four_table.select_leaves`；`_F3_ACCOUNT` 降级为 `fallback_gross` 用
  - [ ] 2.6 负债聚合 `abs()` 归一（两种符号约定并存）
  - [ ] 2.7 render 输出 `tb_source_codes`（含 `parent_check` + `tb_cross_check`）/ `adjudication_prefill` / `leaf_categories`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 3. F4 render 改造（`_f4_accounts_payable.py`）
  - [ ] 3.1 新增 `F4_ACCOUNT_SPEC = ReportLineAccountSpec(row_code='BS-045', fallback_gross=('2202',))`
  - [ ] 3.2 删除 `LIKE '2202%'` 裸 SQL，改共享件叶子聚合 + `abs()` 归一
  - [ ] 3.3 新增四个 `build_f4_*` 纯函数（同 F3 结构）
  - [ ] 3.4 `project_context.tb_amount` 保持不变（前端 `f4TbAmount` inject 已在读），新增 `tb_amount_opening` 填满 F4-1 双期「试算平衡表数」行
  - [ ] 3.5 `adjudication_prefill` 按五性质桶给期初 / 期末，命中多桶的叶子标 `ambiguous`
  - [ ] 3.6 render 输出 `tb_source_codes` / `leaf_categories`
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7_

- [ ] 4. F5 render 改造（`_f5_cost_of_sales.py`）
  - [ ] 4.1 新增 `F5_ACCOUNT_SPEC = ReportLineAccountSpec(row_code='IS-002', fallback_gross=('6401~6499',))`
  - [ ] 4.2 删除 `LIKE '6401%'`（漏 6402 其他业务成本 / 6404），改区间口径解析
  - [ ] 4.3 损益类聚合取叶子 `debit_amount` 之和（保留符号），禁 `debit - credit`（实证含结转损益的全年账恒为 0）
  - [ ] 4.4 `_ROLLFORWARD_ACCOUNTS` 的 `code.startswith(prefix)` 改共享件严格点号边界
  - [ ] 4.5 按名称归类主营 / 其他两段（编码语义项目间冲突，不按编码）
  - [ ] 4.6 render 输出 `tb_source_codes`（含 `tb_cross_check` 暴露 trial_balance 双算）/ 两段 `adjudication_prefill`
  - [ ] 4.7 `project_context.tb_amount` 语义由「6401 主营」改为「营业成本合计」，原值移到 `tb_amount_main` 保留
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 5. 幂等脚本 `backend/scripts/fix/fix_f_cycle_prefill_presets.py`
  - [ ] 5.1 建脚本骨架（`--dry-run` / `--check` / `--apply`，沿用 `fix_f1_prefill_presets.py` 范式）
  - [ ] 5.2 F5 损益口径纠错：`TB('6401','期初余额')` / `期末余额` → `TB('6401','本期发生额')`；其他业务成本两条同理，并按变体给 `6402` / `6404` 二选一条目
  - [ ] 5.3 F2 科目语义纠错 (a)：`生产成本明细表` / `直接人工分析表` / `制造费用明细表` 引用 `TB('1402',...)` 描述为「在产品（生产成本）」，实为在途物资 → 纠正
  - [ ] 5.4 F2 科目语义纠错 (b)：5 个盘点类块把 `1403` 描述为「库存商品」，实为原材料（两变体一致）→ 纠正描述文字
  - [ ] 5.5 F2 口径统一 (c)：`存货审定表` 首两条 `TB_SUM('1401~1461',...)` → `1401~1499`（BS-010 口径）
  - [ ] 5.6 删虚构 AUX 维度值：F3/F4 的 `'TOP1'~'TOP3'`、F2 的 `'A类'`/`'B类'`/`'长库龄'`/`'呆滞'` → 改 `XX单位` / `XX分类` 占位范式（同 F1）
  - [ ] 5.7 补 F3 联动：审定表块新增 `WP('F3','明细表F3-2',...)` 四条（源模板 B7/F7/G7/H7/I7 全部 SUMPRODUCT 自 F3-2）
  - [ ] 5.8 补 F3 披露块：新增上市 / 国企两块（现完全无预设），含 `WP('F3','审定表F3-1',...)` 与 `TB('2201','期末余额')` 合计核对
  - [ ] 5.9 补 F4 联动：审定表块新增 `WP('F4','明细表F4-2',...)`（按性质 SUMIF / 按账龄引 `明细表F4-2!N32:X32`）与 `WP('F4','长期挂账检查表F4-5','审定余额合计')`
  - [ ] 5.10 补 F4 披露块：新增两块，上市按性质 / 国企按账龄，各含 `WP('F4','长期挂账检查表F4-5',...)`
  - [ ] 5.11 补 F5 联动：F5-1 ← F5-2 / ← F5-3 / ← F5-4 三条 `WP()`
  - [ ] 5.12 修正 F5 的 `WP('J1','审定表','生产人员薪酬')` sheet 名为 J1 真实 sheet 名
  - [ ] 5.13 明细表块不得反向引用审定表（防成环）
  - [ ] 5.14 `convert_prefill_presets()` 运行态确认 F1~F5 全部进入 `workpaper:F{n}` 公式管理页
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [ ] 6. 公式预设守卫
  - [ ] 6.1 新建 `backend/tests/test_f_cycle_account_codes.py`：码 ∈ 标准科目表 ∧ 码 ∈ 本循环报表行引用集合，含反向自检
  - [ ] 6.2 新建 `backend/tests/test_f_cycle_formula_presets.py`：语法合法 + 无成环 + sheet 名与源 xlsx tab 名逐字一致（openpyxl 直读）+ 禁虚构 AUX 维度值
  - [ ] 6.3 诚实修正因预设纠错而变红的既有测试，并为每处补一条「旧表达式必红」的用例
  - _Requirements: 8.1, 8.3_

- [ ] 7. 前端科目单一真源（三个新建 composable）
  - [ ] 7.1 新建 `composables/f3AccountScope.ts`（`F3_REPORT_ROW_CODE='BS-044'` / `F3_GROSS_FALLBACK_STANDARD='2201'` / `f3AccountCode(src)` / `f3GrossQueryCodes(src)`）
  - [ ] 7.2 新建 `f4AccountScope.ts`（`BS-045` / `2202`）与 `f5AccountScope.ts`（`IS-002` / `6401~6499`）
  - [ ] 7.3 清零 F3/F4/F5 各文件里的科目码字面量（writebackTB / 请求参数 / EventBus 载荷 / AI 上下文全部改走 scope）
  - [ ] 7.4 守卫按文件参数化断言「源码不得出现裸科目码作科目码/请求参数/事件载荷」
  - _Requirements: 1.1, 2.1, 3.1_

- [ ] 8. 审定表四表预填
  - [ ] 8.1 `useF3Adjudication` 新增 `adjudicationPrefill` 入参 + `pullFromTB()`（按科目码优先匹配行、其次行名；手工优先；无持久化才套用）
  - [ ] 8.2 F3-1 新增「从四表库带入未审数」按钮（与既有「从 F3-2 带入」并列）
  - [ ] 8.3 F3-1 分类行支持信用证 —— 四表有该子科目即出行，不再要求先录 F3-2 明细
  - [ ] 8.4 `useF4Adjudication` 同款：按性质区五桶预填 + 期初 / 期末双期 + 按钮
  - [ ] 8.5 `useF5Adjudication` 同款：主营 / 其他两段预填 + 按钮
  - [ ] 8.6 预填「只覆盖出现的桶且该行无手工值」，toast 说明写入 / 跳过行数；复核 F1 已踩的「另一口径残留导致合计翻倍」问题
  - _Requirements: 1.4, 1.5, 2.3, 3.4_

- [ ] 9. 溯源面板（复用平台共用件）
  - [ ] 9.1 新建 `F3FourTableSourcePanel.vue` / `F4...` / `F5...` 三个薄壳，委托 `shared/WpFourTableSourcePanel.vue`（无备抵科目不传 `provisionLabel`）
  - [ ] 9.2 面板新增「口径核对」区：叶子聚合 vs `trial_balance` 两个值 + 差异，差异超容差标 danger 并提示重跑 recalc
  - [ ] 9.3 面板新增「叶子归类」明细表：逐叶子展示 `code / name / bucket_label`，`ambiguous` 行标黄提示复核
  - [ ] 9.4 面板挂在 F3-1 / F4-1 / F5-1 审定表页
  - [ ] 9.5 补 F1/F2 溯源面板的 `parent_check` 展示
  - [ ] 9.6 宿主透传 `:html-data` / `:project-id`（守卫扫模板，防「漏传 = 静默失效」）
  - _Requirements: 1.6, 1.7, 2.6, 3.5, 4.1, 4.2, 8.4_

- [ ] 10. F3 披露表增强
  - [ ] 10.1 `orderF3ClassRows` 增加信用证档位，行集合由 render 下发的 `f3_category_payload` + 实际金额决定（`always_show` 的银行/商业承兑恒列示）
  - [ ] 10.2 两版披露表新增「从四表库带入」按钮
  - [ ] 10.3 新建勾稽面板 `f3DisclosureConsistency.ts`（规则取源模板 `B9=SUM(B7:B8)` 与 F7-x 校验预设）
  - [ ] 10.4 可编辑金额格换 `WpAmountInput`，只读金额走 `displayPrefs.fmtAmount()`
  - _Requirements: 6.1, 6.4, 6.5, 6.6_

- [ ] 11. F4 披露表增强
  - [ ] 11.1 国企按账龄行改由 `useAgingConfig` 段驱动，补齐 5 年段与自定义（文案走 `disclosureAgingLabels.ts` 的 `SOE_AGING_OVERRIDES`）
  - [ ] 11.2 上市按性质行接平台共享件 `composables/shared/dynamicAdjudicationRows.ts`；per-cycle 薄壳 `f4NatureRows.ts` 只放声明
  - [ ] 11.3 迁移零丢数：历史固定行 `rowId` 沿用旧 rowKey，只迁有数据的行
  - [ ] 11.4 新建勾稽面板 `f4DisclosureConsistency.ts`（按性质合计 == 按账龄合计 == `TB('2202')`；超1年表合计 ≤ 主表合计）
  - [ ] 11.5 金额控件与格式化同 10.4
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 12. 附注模板三向复核
  - [ ] 12.1 新建 `backend/scripts/fix/fix_note_f_cycle_extraction_alignment.py`（沿用 `_note_structure_kit`；预期多数为空操作）
  - [ ] 12.2 openpyxl 直读四个源 xlsx 披露 sheet，与 `note_template_{listed,soe}.json` 的 `headers` 及同步载荷 `columns` 三向比对
  - [ ] 12.3 复核发现不一致时按源模板修正（改 `label`/`group`，绝不改 `key`）
  - [ ] 12.4 复核 `_note_texts` 全部带中文 `title` 且空文本被过滤
  - [ ] 12.5 复核 `flat` 在 seed 与推送两侧都已声明
  - [ ] 12.6 `--check` 归零
  - _Requirements: 7.1, 7.2, 7.4_

- [ ] 13. 同步链路守卫
  - [ ] 13.1 新建 `backend/tests/test_note_f_cycle_structure.py`（openpyxl 三向比对 + 归一函数 + 反向自检）
  - [ ] 13.2 新建 `composables/__tests__/fCycleNoteSubtableContract.spec.ts`（接共享 helper 跑 P1~P6，四循环两变体）
  - [ ] 13.3 `_removed_table_keys` 与本次推送键求差集的断言
  - [ ] 13.4 在 `disclosureAutoSyncCoverage.spec.ts` 的 `CYCLES_WITHOUT_DISCLOSURE` 登记 F0 / F5 及源模板依据，配反向自检防空转
  - _Requirements: 7.1, 7.2, 7.3, 7.5_

- [ ] 14. 后端守卫
  - [ ] 14.1 新建 `backend/tests/four_table/test_f3_account_scope.py`（含反向自检「打乱顺序则信用证被误归类」）
  - [ ] 14.2 新建 `test_f4_nature_buckets.py`（两变体参数化 + PBT「桶之和 == 叶子合计」+ 反向自检）
  - [ ] 14.3 新建 `test_f5_cost_segments.py`（结转账 fixture 下必须非零；反向自检「改回 debit − credit 则必红」）
  - [ ] 14.4 测试替身按 SQL/params 区分 `tb_balance` 与 `trial_balance` 两次查询；`get_active_filter` mock 返回真实 `sa.true()`
  - [ ] 14.5 `backend/tests/four_table/` 全量绿 + F1/F2 既有测试零回归
  - _Requirements: 8.1, 8.2, 4.3_

- [ ] 15. 前端守卫 + CI
  - [ ] 15.1 新建 `composables/__tests__/f3AccountScope.spec.ts` / `f4NatureRows.spec.ts` / `fCycleHostPropWiring.spec.ts`
  - [ ] 15.2 登记新增 `build*Columns` 到 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`，确认零入参可调返回完整列集
  - [ ] 15.3 新增 CI job `f-cycle-four-table` / `f-cycle-frontend` / `note-f-cycle-structure`
  - [ ] 15.4 前端 F 类相关测试全量绿（失败必须能证明是预存在基线）
  - _Requirements: 8.4, 8.6_

- [ ] 16. 实测
  - [ ] 16.1 真实 DB 直跑 F3 render × 3 项目（`0ec33ac9` 信用证大额 / `2aa00f57` 负数存法 / `c8621493` 稀疏）
  - [ ] 16.2 真实 DB 直跑 F4 render × 3 项目：五桶归类正确、`2202.11` 标 `ambiguous`、`tb_cross_check` 检出双算差异
  - [ ] 16.3 真实 DB 直跑 F5 render × 3 项目：区间口径覆盖 6402/6404、损益取叶子借方非零、检出 3 倍差异
  - [ ] 16.4 浏览器实测 F3 披露 Tab（国企侧）：录入 → 自动同步 → `postgres` 核对 §八、36；信用证行正确列示
  - [ ] 16.5 浏览器实测 F4 披露 Tab（国企侧）：账龄枚举切换 3 年段 ↔ 5 年段 → 核对 §八、37 行集合与 `_removed_table_keys`
  - [ ] 16.6 浏览器实测审定表「从四表库带入未审数」按钮 + 溯源面板「口径核对」danger 状态
  - [ ] 16.7 实测数据完整复原（含 `last_sync_at` 回 NULL、`checklist_responses` 清理）
  - [ ] 16.8 清理本会话 `tmp_*` 诊断产物
  - _Requirements: 8.5_

## Notes

### 范围外发现（须单独立 spec，本 spec 只暴露不修改）

- **G1 `trial_balance` 部分项目父子双算**：`2aa00f57` 的 `2202` = 534,617,953.54
  （真值 267,308,976.77 的 2 倍）、`6401` = 1,211,706,444.39（真值 403,902,148.13 的 3 倍）。
  根因是旧版 recalc 无叶子过滤；`trial_balance_service` 现版本已有 `leaf_cond`，
  故属陈旧数据，需重跑 recalc。影响全部循环的「试算平衡表数」核对行。
- **G2 `trial_balance` 损益类发生额口径缺陷**：`trial_balance_service` 第 1b 段用
  `debit_amount - credit_amount`，实证含年末结转损益的全年账上恒为 0
  （`2aa00f57` 的 6401 四行 net 全 0）→ 一旦重跑 recalc，F5/N4/N5/K8~K13/I6 的试算核对数
  会全部归零。正确口径 = 叶子 `debit_amount` 之和（保留符号）。
- **G3 `note_template` 的 `report_row_code` 全库陈旧**：F 类四章节实测 `report_row_code=None`，
  故不触发 `REPORT()`，属 inert；平台级 remap 待办。

### 待用户裁决

1. **F4 `2202.11 应付账款_工程设备款` 归类** —— 本设计按源模板行序（A9 工程款先于 A10
   设备款）归入「工程款」并标 `ambiguous` 供手工调整。若审计口径应归「设备款」或应拆分，
   需用户明确。
2. **F5 `project_context.tb_amount` 语义变更** —— 由「6401 主营业务成本」改为
   「营业成本合计（含其他业务成本）」，原值移至 `tb_amount_main`。这会改变
   `useF5CrossSheet` 的告警文案（现写「TB 6401」）。是否接受。
3. **灰度开关** —— F3/F4/F5 是否需要 `F{n}_FOUR_TABLE_EXTRACTION_ENABLED` 灰度开关，
   或直接上线（F3/F4/F5 现在本就无预填，无既有行为需回退）。
