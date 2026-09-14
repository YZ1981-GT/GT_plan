# Implementation Plan: G6 四表取数与披露对齐

## Task Dependency Graph

```json
{
  "waves": [
    {"tasks": [1, 2]},
    {"tasks": [3, 4]},
    {"tasks": [5, 6]},
    {"tasks": [7, 8]},
    {"tasks": [9]},
    {"tasks": [10]}
  ]
}
```

## Tasks

### Wave 1: 科目纠正 + 共享件接入

- [x] 1. 后端 render 科目映射纠正与共享件接入
  - 1.1 `_g6_other_bond_investment_main.py` 的 `_G6_ACCOUNT_PREFIX` 从 `"1503"` 改为 `"1505"`
  - 1.2 新增 `_G6_ACCOUNT_SPEC = ReportLineAccountSpec(row_code='BS-022', fallback_standard_codes=('1505',))`（无 `provision_row_code`，G6 减值在 OCI 不冲减账面价值）
  - 1.3 `_fetch_tb_values` 改委托 `resolve_report_line_account_codes` + `select_leaves` + `aggregate_leaves`（删除裸 SQL `WHERE account_code LIKE '1503%'`）
  - 1.4 render 输出新增 `tb_source_codes: {gross_standard: [...], resolved_from: 'report_config'|'fallback'}`
  - 1.5 确保灰度关闭时（默认）输出与改前逐字节等价（除科目常量字面量）—— `tb_values` 仍为 `{opening, closing}` 形态，全库 1505 余额 0 → 输出 `{}`（与现在 1503 也是 0 等价）

- [x] 2. 前端科目单一真源 `g6AccountScope.ts`
  - 2.1 新建 `composables/g6AccountScope.ts`（`G6_REPORT_ROW_CODE` / `G6_GROSS_FALLBACK_STANDARD` / `g6GrossQueryCodes(src)` / `g6AccountCode(src)`）
  - 2.2 GtG6OtherBondMain 组件内所有硬编码 `1503` / `account_code` 引用改读 render 下发的 `tb_source_codes` 或 `g6AccountScope` 常量
  - 2.3 新建 `composables/__tests__/g6AccountScope.spec.ts`（断言常量值 / 运行态优先 / 空回退）

### Wave 2: 公式预设重写 + 附注模板核查

- [x] 3. 公式预设重写（幂等脚本）
  - 3.1 新建 `backend/scripts/fix/fix_g6_prefill_presets.py`（`--dry-run` / `--check` / `--apply`）
  - 3.2 审定表 G6-1 块：`account_codes` 改 `["1505"]`；5 条公式科目 `1510` → `1505`（`TB('1505','期初余额')` / `TB('1505','期末余额')` / `ADJ('1505','aje_net')` / `ADJ('1505','rje_net')` / `PREV` 不变）
  - 3.3 明细表 G6-2 块：`account_codes` 改 `["1505"]`；删除 `1531_02_客户_132357` / `1531_02_项目名称_A6000` 两条硬编码 AUX 公式；删除 `子科目_1531_01/02/03_期末` 三条（1531 是长期应收款不是 G6 科目）；保留/改写 `TB('1505','期初余额')` / `TB('1505','期末余额')` / `ADJ('1505',...)` / `PREV`
  - 3.4 新增上市披露块（`附注披露信息（上市公司）`）：`WP('G6','审定表G6-1','其他债权投资公允价值合计')` + `WP('G6','坏账准备明细表G6-3','期末审定数')`
  - 3.5 新增国企披露块（`附注披露信息（国企）`）：同上两条 + `WP('G6','审定表G6-1','期初余额')`
  - 3.6 `--check` 验证无 `1503`/`1510`/`1531` 残留

- [x] 4. 附注模板结构核查
  - 4.1 新建 `backend/scripts/fix/fix_note_g6_structure.py`（用共享 `_note_structure_kit`）
  - 4.2 上市 §五、15：验证 14 表 columns 均非空（已由 `fix_note_g_cycle_structure.py` 修过），核查 key/label 与 `G6_LISTED_SUBTABLE` / `G6_LISTED_STAGE_SUBTABLE` 对齐
  - 4.3 国企 §八、16：验证 2 表 columns 与源模板一致 —— 表(1) `其他债权投资情况` 3 列（项目/期末余额/期初余额，`flat`）；表(2) `期末重要的其他债权投资` 6 列（其他债权投资项目/面值/摊余成本/公允价值/累计OCI/已计提减值准备，`flat`）
  - 4.4 国企 text_sections 第 4 条保留交叉引用文本不动
  - 4.5 `--check` exit 0 则无欠账

### Wave 3: 前端披露同步链路核查

- [x] 5. 上市披露 Tab 同步链路核查与修复
  - 5.1 `G6TabDisclosureListed.vue` 已重建 ✅，`buildG6ListedSyncPayload` 覆盖全部 14 张表（8 命名 + 6 三阶段）+ 3 条 `_note_texts`
  - 5.2 三阶段表动态插行：`buildG6StageRows(block)` 按 individual/portfolio 两子段构建行集，「其中：」可扩明细行正确处理 ✅
  - 5.3 `_note_texts` 含 3 个带英文 section key 的文本域（`listed-fair-value-note` / `listed-significant-change` / `listed-judgement-basis`）—— 缺中文 title（后续补）
  - 5.4 无显式 `_removed_table_keys` 处理（主表二选一格式不涉及 removed，因为 listed 只有一种主表形态）✅
  - 5.5 `sheet_name` = `附注披露信息（上市公司）` 来自 `G6_DISCLOSURE_SHEET_NAME.listed` ✅

- [x] 6. 国企披露 Tab 同步链路核查
  - 6.1 `G6TabDisclosureSOE.vue` 推 4 张表 + 1 条 `_note_texts`（section=`soe-audit-note`）
  - 6.2 🔴 **发现**：`减值准备计提情况` 和 `减值准备变动` 是**孤儿子表**（附注模板 §八、16 只有 2 张表且 text_sections 明确写「参照八、15」）—— 这两张表推送不报错但在附注渲染不出来。**当前不改**（会影响已有数据），留待后续评估是否扩模板或停推
  - 6.3 `sheet_name` = `'附注披露信息（国企）'` 直接字面量 ✅（与源 xlsx tab 名一致）
  - 6.4 自动同步正确接入 `useDisclosureAutoSync`，watch 监听 `buildSyncData()` 的 JSON 序列化结果 ✅（非自调度 bug）

### Wave 4: 审定表四表取数按钮 + 溯源面板

- [x] 7. G6-1 审定表四表取数按钮
  - 7.1 新增「从四表库带入未审数」按钮（读 render `htmlData.adjudication_prefill`，seed block1 公允价值段）✅
  - 7.2 TB 核对行消费 `tb_values`（科目已纠正，composable 内 `fetchTrialBalance` 调 API 取正确科目）✅ 注：`ITEM_ID_TB='G6-1-adj-tb-1503'` 是持久化 key 保持不变（改了会丢历史数据）
  - 7.3 手工优先：`hasTbPrefill` computed 控制按钮可用状态
  - 7.4 `useAdjudicationBringIn` 科目从 `1503` 纠正为 `1505`
  - 7.5 审计目标 alert 文案科目 `1503`→`1505`

- [x] 8. 溯源面板
  - 8.1 直接嵌入共享 `WpFourTableSourcePanel`（无备抵 → 不传 `provisionLabel`，与 K2 同范式）✅
  - 8.2 `tbSourceCodes` computed 从 `props.htmlData?.tb_source_codes` 读取，证明非 dead output ✅
  - 8.3 显示来源科目 + resolved_from + 报表行 BS-022 + hint 说明 FVOCI-Debt 无备抵原因 ✅

### Wave 5: 守卫与测试

- [x] 9. 守卫与回归测试
  - 9.1 `backend/tests/four_table/test_g6_account_scope.py`：7 测试全绿 —— 断言 `_G6_ACCOUNT_PREFIX=='1505'` / spec.row_code / spec.fallback_gross / 无 provision / 源码无禁止码 / 预设只含 1505 / 预设无 AUX ✅
  - 9.2 前端 `g6AccountScope.spec.ts`：10 测试全绿 ✅
  - 9.3 G6 相关前端全量 4 文件 76 测试全绿（g6AccountScope + g6NoteSubtableContract + g6DisclosureSyncPayload + useG6MainAdjudication）✅
  - 9.4 四表库共享件 203 测试零回归 ✅
  - 9.5 附注模板结构已由既有 `g6NoteSubtableContract.spec.ts` 覆盖（14 表上市 + 国企 2 表 columns 验证在内）✅

### Wave 6: 实测与收口

- [x] 10. 真实 DB 实测 + 收口
  - 10.1 真实 DB 直跑 `resolve_report_line_account_codes('BS-022', project='2aa00f57', standards=['soe_standalone','soe','standalone'])` → 返回 `['1505']` ✅
  - 10.2 全库 `trial_balance` 1505 余额为 0 → `tb_values` 将为 `{}` / `adjudication_prefill` 将为 `None`（链路正确但无数据产出，属预期行为）✅
  - 10.3 临时文件已清理 ✅
  - 10.4 memory.md 待更新

## Notes

### 科目考古

| 科目码 | 科目名 | 准则 | 真实用途 |
|--------|--------|------|----------|
| 1503 | 可供出售金融资产 | 旧 CAS22 (2006) | 已废止，合并入 1505/1506 |
| 1505 | 其他债权投资 | 新 CAS22 (2017) | FVOCI-Debt，G6 真源 |
| 1506 | 其他权益工具投资 | 新 CAS22 (2017) | FVOCI-Equity，G8 |
| 1510 | 其他非流动金融资产 | — | 标准科目表无此码 |
| 1531 | 长期应收款 | — | L 循环（长期应收款），非 G6 |

### G6 无备抵科目的会计原理

CAS22 (2017) 规定：以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI-Debt），其减值损失在**其他综合收益**中确认损失准备，**不减少**该金融资产在资产负债表中列示的账面价值。因此：
- 资产负债表"其他债权投资"项目 = 公允价值（不扣减值准备）
- 与 D1/K1/G5 等「账面余额 − 减值准备 = 账面价值」的列报方式**根本不同**
- `report_config` 里只有 `BS-022 = TB('1505')`，无 `IMP-xxx` 备抵行

### 全库余额为 0 的处理

9 个项目的 `trial_balance` 和 `tb_balance` 中 1505 均为 0。这意味着：
- 四表取数链路必须正确但**不会产出数据**
- 实测无法验证金额正确性，只能验证链路通畅（`resolved_from='report_config'`、面板渲染、按钮不崩）
- 有新项目导入 1505 数据后即自动生效
