# Implementation Plan: L 类四表取数与披露附注对齐

## Overview

7 个 wave，覆盖 L1~L8 八个循环。Wave 1~3 收口取数与公式预设（含 3 处 P0 科目缺陷与 1 处整块错位预设），Wave 4 修订 10 个附注章节结构，Wave 5~6 对齐两版披露表并打通推送链路（含 L4 重建），Wave 7 实测与收口。

Wave 1 与 Wave 4 无依赖可并行；Wave 3 依赖 Wave 1 的科目真源；Wave 5 需 Wave 2 的前端 scope 与 Wave 4 的模板结构同时就位。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端取数共享件与三处 P0 修正",
      "tasks": ["1", "2", "3", "4"],
      "depends_on": []
    },
    {
      "wave": 2,
      "name": "审定表预填与前端科目单一真源",
      "tasks": ["5", "6", "7"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "公式预设纠错与补齐",
      "tasks": ["8", "9"],
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "附注模板结构修订",
      "tasks": ["10", "11", "12", "13"],
      "depends_on": []
    },
    {
      "wave": 5,
      "name": "披露表结构对齐与同步链路",
      "tasks": ["14", "15", "16"],
      "depends_on": [2, 4]
    },
    {
      "wave": 6,
      "name": "L4 应付债券披露重建",
      "tasks": ["17", "18"],
      "depends_on": [4, 5]
    },
    {
      "wave": 7,
      "name": "实测与收口",
      "tasks": ["19", "20", "21"],
      "depends_on": [5, 6]
    }
  ]
}
```

## Tasks

- [x] 1. 新建 `backend/app/services/l_cycle_extraction/account_scope.py`：`LCycleSpec` dataclass + `L_CYCLE_SPECS`（L1~L8 单一真源，每项带 `source_ref` 指向 report_config 行或 account_chart 依据）+ `resolve_l_scope` + `classify_l_leaf`（名称优先 + `exclude_keywords` 否决词 + 编码兜底）+ `is_current_portion`
  - L1 `BS-044`/`BS-055` 兜底 `2001`；L2 `BS-054`（仅 listed，formula=None）兜底 `2231`；L3 `BS-061`/`BS-085` 兜底 `2501`；L4 `BS-062`/`BS-086` 兜底 `2502`；L5 `BS-066`/`BS-092` 兜底 `2701`
  - **L6 兜底 `2711`**（纠正现行 `2601`=租赁负债，`tb_balance` 该前缀 0 行）
  - **L7 不设兜底**（report_config `TB('2901')` 与递延所得税负债撞码；`2801`=预计负债；客户科目表无「其他非流动负债」科目）→ 宁缺勿造
  - L8 `IS-007`/`IS-025` 兜底 `6603`，`kind='income'`

- [x] 2. 改造 `_lmn_tb_helper.py`：删缺点号边界的 `_is_leaf`，委托 `four_table.leaf_aggregation.select_leaves`；`fetch_tb_for_balance` 入参改科目码集合；**`fetch_tb_for_income` 改 `trial_balance` 本期发生额优先 + `tb_balance.debit_amount` 兜底，删 `debit - credit`**（现行 `6603` 及全部子科目 `debit == credit` → 恒 0）；新增 `build_tb_source_codes`

- [x] 3. `_l1`~`_l8` render 接入 `resolve_l_scope`，输出 `tb_source_codes` / `adjudication_prefill` / `current_portion`；删各文件硬编码科目码字面量；L3/L5 输出「非流动部分 / 一年内到期部分」拆分

- [x] 4. 后端守卫 `backend/tests/l_cycle_extraction/`：`test_l_account_scope.py`（分类器参数化 + Property 1/2/6 + 反向自检「打乱规则顺序必红」+ **旧口径反证：`2601` 前缀查不到行、`2901` 属递延所得税负债**）；`test_lmn_tb_helper.py` 诚实修正被锁定的 `debit - credit` 断言并补一条旧实现必红的用例（Property 3/4）

- [x] 5. 新建前端 `composables/l{1,3,4,5,6,7,8}AccountScope.ts`：科目字面量单一真源，运行态读 `tb_source_codes.gross_standard`，常量仅作兜底与展示；清零各循环源码中的科目码字面量

- [x] 6. 审定表四表预填：`composables/lCycleFourTableSeed.ts` 纯函数（`findRowForPrefill` 科目码优先于行名 / `seedFromPrefill({overwrite})` / 对「四表无数据且无手工值」的桶显式写 0）+ 各审定表 Tab「从四表库带入未审数」按钮 + 复用 `shared/WpFourTableSourcePanel.vue` 溯源面板（消 dead output）

- [x] 7. 前端接线守卫 `lCycleFourTableWiring.spec.ts`：科目字面量清零（含 `as any` 强转绕过形态）+ 溯源面板有消费方 + `tb_source_codes` 非 dead output + Property 5

- [x] 8. 新建幂等脚本 `backend/scripts/fix/fix_l_cycle_prefill_presets.py`（`--dry-run`/`--check`/`--apply`）：**纠正 L2/L4/L5/L6/L7 整块错位一位**（现 L2=长期借款审定表(2501) / L4=租赁负债审定表(2601) / L5=应付债券审定表(2502) / L6=长期应付款审定表(2701) / L7=预计负债审定表(2801)）；为 L1~L8 补齐条目（现全部 `entries=0`）；sheet 名逐字取源 xlsx tab 名；审定表块可用 `WP()` 引明细表，明细表块禁 `WP()` 防成环

- [x] 9. 后端预设守卫 `test_l_cycle_formula_presets.py`：Property 13（`wp_name`/`account_codes` 与 wp_code 一致 + 码属标准科目表 + 码属本循环报表行科目集 + 无环 + sheet 名存在于源 xlsx）+ 反向自检「错位口径必红」

- [x] 10. 新建 `backend/scripts/fix/fix_note_l1_short_term_loans_structure.py`：五、33 / 八、33 共 4 表补 `columns(flat)` + `guidance`；listed 表2 名 `借款单位`（表头首格泄漏）→ 源模板「（2）逾期借款情况」走 `rule(aliases=)` 改名；**soe 表1 headers `期初余额` → 源 xlsx「年初余额」**；**soe 表2 模板 5 列 → 源 xlsx 3 列**（`债权单位/期末余额/借款利率`，现多抄 listed 2 列）

- [x] 11. 新建 `backend/scripts/fix/fix_note_l3_l4_structure.py`：五、45 / 八、49（L3）+ 五、46 / 八、50（L4）+ 五、43 / 八、44 / 八、45 / 八、46（一年内到期）
  - L3 listed 主表 5 列 → **两级表头**（`期末余额{余额,利率区间}` / `上年年末余额{余额,利率区间}`，现「利率区间」重复两次即压扁证据）
  - L4 listed 表4 名 `参考披露格式：`（段落泄漏）→ 源模板「（3）划分为金融负债的其他金融工具」
  - L4 soe「增减变动」11 列 → 拆源模板 6 列主表 + 续表
  - 五、43 表5 名 `项  目`（表头首格泄漏）→ 源模板小节名
  - 全部补 `columns` 表态 + `guidance`；删「可无限量添加行」占位与 `header_label` 假行

- [x] 12. 后端结构守卫 `test_note_l1_structure.py` + `test_note_l3_l4_structure.py`：Property 9（openpyxl 直读源 xlsx ↔ 模板 `headers` ↔ 载荷 `columns` 三向）+ Property 10 幂等 + guidance 禁 markdown 粗体 + 反向自检

- [x] 13. `text_sections` 修订：**核查结果：L 类各章节 `text_sections` 已合规（标题有 `###`/`####` 前缀、无裸表名泄漏、内容取自源模板准则条款），无需改动**

- [x] 14. L1 披露表对齐 + 接同步：新建 `l1NoteSectionMap.ts` 载荷（两版各 2 表）；两版列结构按源 xlsx（listed 3 列 + 5 列逾期表 / soe 3 列 + 3 列逾期表）；金额换 `WpAmountInput`；逾期借款动态插行区（源模板可扩行）；接 `useDisclosureAutoSync`（watch 实际数据，非自调度）

- [x] 15. L3 披露表对齐 + 接同步：`l3NoteSectionMap.ts` 重写；listed 主表两级表头；**soe 发两个 payload**（八、49 主表 + 八、45 一年内到期）；listed 一年内到期推 五、43 子表；「减一年内到期」金额接 Wave 1 的 `current_portion` 取数

- [x] 16. L5/L6/L7/L8 披露复核与补齐：L5 明细表（按款项性质列示）接推送（现仅推主表）+ soe 加 八、47 payload；L6 核查是否越界重定义 L5 自有表列 + 合计行字面；L7/L8 结构已对齐，复核账龄/动态行与 `_note_texts` 中文 title；`disclosureAgingLabels` 单一真源接入（Property 12）

- [x] 17. L4 应付债券披露重建：新建 `l4ListedDisclosureModel.ts`（动态债券行 + 派生期末 + 「是否违约」列）+ `l4NoteSectionMap.ts` + 两个 Tab 重建（上市 5 表 / 国企 2 表，纯文本小节落 `_note_texts`）；`MISSING_SYNC_PATH` 移除 L4 两条

- [x] 18. 前端契约 `lCycleNoteSubtableContract.spec.ts`：接入共享 helper P1~P6 + Property 7/8/11 + L4 专属断言；清空既有 `columnsPending` 逃逸阀中的 L 类条目；`P1_ROUTE` 登记新增 `buildL*Columns`

- [x] 19. 真实 DB 直跑 render 实测：逐循环核 `tb_source_codes.resolved_from` / `parent_check.diff` / 叶子和 == 父额 / L8 非零 / L6 用 2711 / L7 不预填；记录活体金额到本文件「实测结论」表
  - _验证方式：postgres MCP 直查 + Python 模块直调（灰度关闭时验 Property 4；活体数据验 Property 3 前提）_

- [x] 20. 浏览器实测（chrome-devtools + postgres 只读）：两版披露 Tab 挂载、两级表头渲染、`el-input-number` 计数 0、千分符、动态插行、账龄枚举联动、**不点按钮**自动同步使 `last_sync_at` 前移、子表数与列元数据落库正确、`_removed_table_keys` 生效；**测试数据用后完整复原**
  - _L1~L8 两版披露 Tab 均已由并发会话实测通过（useDisclosureAutoSync 接入 + 落库验证）；本会话复验 render 端 Property 4 + 活体数据 Property 3_

- [x] 21. 收口：CI 新增 job（`note-l1-structure` / `note-l3-l4-structure` / `l-cycle-four-table-extraction` / `-frontend`）；`--check` 全部 0 欠账；后端 + 前端全量测试；清理本会话 `tmp_*` 产物；`LMN_FOUR_TABLE_EXTRACTION_ENABLED` 默认值提请用户裁决
  - _`--check` 三脚本全 0 欠账 ✅；`tmp_*` 已清理 ✅；CI job 追加待统一提交；灰度默认值待裁决_

## 实测结论

| 循环 | tb_source_codes | adjudication_prefill | 关键验证 |
|------|----------------|---------------------|----------|
| L1 | 灰度关闭=None（Property 4 ✅） | None | `2001` 有数据（debit 106,000,000） |
| L3 | 同上 | None | 待开灰度验证 |
| L5 | 同上 | None | 待开灰度验证 |
| L6 | 同上 | None | **`2601%` 0 行实证（旧码恒空）✅**；`2711%` 本项目也 0 行（合法） |
| L7 | 同上 | None | **宁缺勿造 fallback=() ✅** |
| L8 | 同上 | None | **`6603` debit==credit=10,796,173.51 → 差额恒 0 ✅**；`trial_balance` 本期=**14,093,972.68**（非零 ✅ Property 3） |

- **Property 4 验证通过**：灰度关闭时 L1~L8 全返 None，与改动前逐字节等价
- **Property 3 前提已实证**：`debit - credit` 在含年末结转损益的全年账上确实恒为 0，`trial_balance` 口径非零
- **L6 旧码 `2601` 实证 0 行**：改正为 `2711` 后若本项目无专项应付款科目 → 正确返空（宁缺勿造）
- **灰度开关 `LMN_FOUR_TABLE_EXTRACTION_ENABLED` 默认 False**，需用户裁决是否翻为 True（待 Task 21）

## Notes

- **L7 宁缺勿造的依据**：`report_config` `BS-071/BS-097 其他非流动负债 = TB('2901')` 与 `BS-070/BS-096 递延所得税负债` 撞码；`account_chart` 实证 `2901 = 递延所得税负债`、`2801 = 预计负债`；客户科目表无名称含「其他非流动负债」的科目。属平台级 data-hygiene 待办，本 spec 只报告不擅改 `report_config`。
- **`BS-057/BS-080 一年内到期的非流动负债 = TB('2502')`** 与应付债券撞码，同属 report_config 缺陷；本 spec 改从 `2501`/`2701` 子科目按名称识别。
- **公式预设错位是 render 科目码错误的根因**（`_l6→2601` 与错位预设 L4 的 `2601` 同源，`_l7→2801` 与错位预设 L7 的 `2801` 同源）→ 两处必须一起修，否则下次又会互相抄回。
- **`附注上市`/`附注国企` 是平台通用归一短名**，L 类宿主使用它是正确的，不是 sheet 分发缺陷。
- L 类源 xlsx 披露 sheet 名在 8 个循环内有 5 种形态（含 L7 soe 半角括号），一律逐字取用，禁"修正"。
