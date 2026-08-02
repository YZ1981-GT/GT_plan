# Implementation Plan: H 类四表取数与科目映射收口

## Overview

25 个任务分 6 个 wave。核心是 Wave 1 的 H 类三层分派共享件（阻塞全部后续），Wave 2 的 7 个 render 改造可并行，Wave 5 的披露/附注侧修复与前四个 wave 无代码交集可全程并行，Wave 6 收口实测。

三个 P0（H3 取 `1503`/`1504` 金融资产科目、H8 取 `1901` 待处理财产损溢、H9 取 `2205` 合同负债）分别落在 Task 6/8/9；公式预设整片贴错标签落在 Task 11。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "共享件与科目真源（阻塞全部后续）",
      "tasks": ["1", "2", "3"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "各循环 render 改造",
      "tasks": ["4", "5", "6", "7", "8", "9", "10"],
      "parallel": true,
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "公式预设纠正",
      "tasks": ["11", "12"],
      "parallel": false,
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "前端科目真源与消费面",
      "tasks": ["13", "14", "15"],
      "parallel": false,
      "depends_on": [2]
    },
    {
      "wave": 5,
      "name": "披露与附注侧遗留修复",
      "tasks": ["16", "17", "18", "19", "20", "21"],
      "parallel": true
    },
    {
      "wave": 6,
      "name": "CI、实测与收尾",
      "tasks": ["22", "23", "24", "25"],
      "parallel": false,
      "depends_on": [2, 3, 4, 5]
    }
  ]
}
```

依赖说明：Wave 2 的 7 个任务互不依赖（各改自己的 render 文件），但都依赖 Wave 1 的共享件。Wave 5 与 Wave 1~4 无代码交集（改的是披露/附注侧文件），可与之并行。Wave 6 的实测必须在全部改动落地后进行。

---

## Tasks

### Wave 1：共享件与科目真源

- [ ] 1. 新建 H 类三层分派共享件 `backend/app/services/four_table/h_asset_layers.py`
  - 定义 `HAssetLayerSpec` / `HAssetLayers` dataclass（字段见 design §Components）
  - 定义 `H_CYCLE_SPECS: dict[str, HAssetLayerSpec]`，10 个循环各一条，每条注明报表行与兜底码依据
  - 实现纯函数 `classify_h_layer` / `split_h_layers` / `build_h_tb_values` / `build_h_parent_check`
  - 实现 `resolve_h_asset_layers(ctx, spec)`（复用 `resolve_report_line_accounts` 的解析结果做二次分派）与 `load_h_leaves(ctx, layers)`（一次查询 + `get_active_filter` + `select_leaves`）
  - 名称分类优先级：减值准备 → 累计折旧/摊销/折耗 → 未确认融资费用 → gross（顺序不可打乱）
  - 符号交叉校验：负号码不得落 gross，冲突记 `sign_conflicts`
  - 备抵层聚合取绝对值；备抵「增加」取 `credit_amount`、「减少」取 `debit_amount`
  - 🔴 **不得修改** `report_line_accounts.py` 与 `leaf_aggregation.py`
  - _Requirements: 1.1, 1.2, 1.3, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4_

- [ ] 2. 新建共享件守卫 `backend/tests/four_table/test_h_asset_layers.py`
  - Property 1：三层分派完备且互斥
  - Property 2：名称分类优先级 + **反向自检**（打乱顺序则「投资性房地产减值准备」被误判为 gross）
  - Property 3：负号码不落 gross；冲突时 `sign_conflicts` 非空
  - Property 6：fail-open（各 DB 环节分别抛异常）且 `gross` 恒非空
  - Property 5：点号边界（`1521` 不命中 `15210`）
  - 替身要求：`get_active_filter` 返回真实 `sa.true()`；同表多次查询按 SQL/params 区分
  - _Requirements: 11.1, 11.6_

- [ ] 3. 新建平台级科目码守卫 `backend/tests/test_h_cycle_account_codes.py`
  - 条件①：`H_CYCLE_SPECS` 中每个码存在于标准科目表（读 `backend/data/*account_chart*.json`，不连库以便进 CI）
  - 条件②：每个码 ∈ 该循环报表行公式引用集 ∪ 该循环声明的兜底集
  - 反向自检：断言旧错误码 `1503`/`1504`/`1901`/`2205`/`1522`/`1523`/`2802`/`2803` 中，属于「真科目但不属本循环」与「不存在的码」两类各至少一个能被规则抓出
  - _Requirements: 11.2, 7.3_

### Wave 2：各循环 render 改造

- [ ] 4. 改造 H1 固定资产与 H6 固定资产清理 render
  - `_h1_fixed_assets.py`：改走 `H_CYCLE_SPECS['H1']` + 共享件，删除 `_H1_ACCOUNT_PREFIXES` 与直调 `resolve_report_line_account_codes`；`tb_source_codes` 改为 `HAssetLayers.as_dict()`
  - `_h6_asset_disposal_clearing.py`：改走 `H_CYCLE_SPECS['H6']`，`build_d_adjudication_prefill` 的 `account_prefix` 改传解析结果
  - 输出 `parent_check`；`tb_values` 键名不变
  - _Requirements: 1.1, 1.2, 1.7, 3.4, 4.1_

- [ ] 5. 改造 H2 在建工程与 H4 工程物资 render
  - H2 用 `BS-029` + `extra_standard_codes=('1605',)` 单列工程物资（不塞 impairment 槽）
  - H4 用 `BS-029` 兜底 `1605`，并单列 `1604` 供 H4-1 与报表核对
  - 删除各自 `_ACCOUNT_PREFIXES` 与局部 `_is_leaf`
  - _Requirements: 1.1, 1.2, 3.1, 3.2, 4.1_

- [ ] 6. 🔴 改造 H3 投资性房地产 render（P0 取错科目族）
  - `_H3_ACCOUNT_PREFIXES = {"1503","1504"}` → `H_CYCLE_SPECS['H3']`（`BS-027` + `IMP-010`，兜底 `1521`/`1525`,`1526`/`1527`）
  - 删除无点号边界的局部 `_is_leaf`
  - 把裸 SQL 的 `trial_balance` 查询改为经 `get_active_filter`
  - `6051` 其他业务收入的租金勾稽查询同样改走 `get_active_filter`
  - 增补 `adjudication_prefill`（现状无）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 4.1, 5.1_

- [ ] 7. 改造 H5 油气资产与 H7 生产性生物资产 render
  - H5：`row_code=None`（无 BS 行）→ 兜底 `1631`/`1632`，溯源面板须明示「无报表行映射」
  - H7：`BS-030` + `IMP-013`，兜底 `1621`/`1622`（现状缺备抵 `1622`）
  - 两者 `build_d_adjudication_prefill` 改传解析结果
  - _Requirements: 1.1, 1.2, 1.7, 1.8, 4.1_

- [ ] 8. 🔴 改造 H8 使用权资产 render（P0 取错科目族）
  - `_H8_ACCOUNT_PREFIXES = {"1901","190101"}` → `H_CYCLE_SPECS['H8']`（`BS-031` + `IMP-015`，兜底 `1641`/`1642`/`1643`）
  - 删除 `is_contra = len(code) > 4 and code.startswith("1901")` 与 `_H8_CONTRA_PATTERNS`
  - `build_d_adjudication_prefill(account_prefix="1901")` 改传解析结果，按三层各发一段
  - 新增 `rou_imp_*` 键承载减值层（现状只有原值与折旧两层）
  - _Requirements: 1.1, 1.2, 1.5, 1.7, 2.1, 4.1_

- [ ] 9. 🔴 改造 H9 租赁负债 render（P0 取错科目族）
  - `_H9_ACCOUNT_PREFIXES = {"2205"}` → `H_CYCLE_SPECS['H9']`（`BS-063`，兜底 `2601` + 抵减层 `2602`）
  - `build_d_adjudication_prefill(account_prefix="2205")` 改传解析结果
  - 新增 `unearned_finance_*` 键承载未确认融资费用
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 4.1_

- [ ] 10. 改造 H10 资产处置损益 render（损益口径）
  - 用 `H_CYCLE_SPECS['H10']`（`IS-018`，`occurrence=True`）
  - 取数改为 **本期发生额**：`trial_balance` 优先，兜底 `tb_balance` 按方向取 `credit_amount`/`debit_amount`
  - 删除 `debit - credit` 形态（含年末结转损益的全年账上结构性恒为 0）
  - _Requirements: 1.1, 1.2, 5.4, 4.1_

### Wave 3：公式预设纠正

- [ ] 11. 新建幂等脚本 `backend/scripts/fix/fix_h_cycle_prefill_presets.py`
  - CLI `--dry-run` / `--check` / `--apply` / `--only`
  - 真源 = `H_CYCLE_SPECS` + openpyxl 直读源 xlsx 的 sheet 名
  - 纠正：H3 审定表整块（现为使用权资产内容）、H3 明细表 `1522`/`1523`、H5 `1611`、H8 审定表 `1631`、H8 明细表 `1621`/`1622`、H9 `2802`/`2803`
  - 删除 H2 明细表的 `AUX('1604','项目名称','B510003'|'B510006',…)` 4 条硬编码工程编码
  - 修 H1 分析程序病态区间 `TB_SUM('1601~1604')`
  - 修 H10 的 `TB('6115','期初余额')` / `TB('6115','期末余额')` → 本期发生额口径
  - 补 10 个循环各两个披露 sheet 的预设块（现状全空白）
  - 底稿间联动用 `WP()`：审定表可引明细表，明细表禁引审定表
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 12. 新建预设守卫 `backend/tests/test_h_cycle_formula_presets.py`
  - 科目码正确性（复用 Task 3 的双条件）
  - 防成环：明细表块不得含引审定表的 `WP()`
  - 语法合法性：按 prefill 词汇表放行 `ADJ`/`TB_SUM`/`LEDGER`/`AUX`/`PREV`
  - 禁硬编码具体项目/工程编码（`AUX` 第三参不得为具体业务编码字面量）
  - Property 10：H10 块不出现期初/期末余额口径
  - sheet 名与源 xlsx tab 名三处一致（openpyxl 直读）
  - _Requirements: 11.3, 7.3, 7.4, 5.4_

### Wave 4：前端科目真源与消费面

- [ ] 13. 新建 `composables/h{n}AccountScope.ts` ×10 并清零字面量
  - 每份含报表行常量、三层兜底码、`h{n}GrossCodes`/`h{n}ContraCodes`/`h{n}ImpairmentCodes`/`h{n}WritebackCode`
  - 运行态优先取 render 下发的 `tb_source_codes`，常量只作兜底与展示
  - 清零各循环组件与 composable 中的科目码字面量（重点 H3 的 `1503`/`1504`、H8 的 `1901`、H9 的 `2205`）
  - 🔴 `writebackTB` 目标改走 scope —— 现状 H8 会往 `1901`、H9 会往 `2205` 写审定数，污染 K2/D7 口径
  - 新增守卫 `h{n}AccountScope.spec.ts` ×10 + 跨循环 `hCycleFourTableWiring.spec.ts`（`stripComments()` + 反向自检）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 11.4, 11.6_

- [ ] 14. 接入取数溯源面板（消灭 dead output）
  - 评估 `shared/WpFourTableSourcePanel.vue` 扩展为可变层列表（`layers: {label, codes, resolvedFrom}[]`）的成本；若改动会波及 K1/K2 现有 111 例守卫则改为新建 `WpHFourTableSourcePanel.vue`，并把取舍依据写进本文件 Notes
  - 展示三层科目码 + 报表行编码 + 公式原文 + `resolved_from` + `sign_conflicts` + `parent_check` 差异条
  - 10 个循环的审定表接入面板（H1 现有 `tb_source_codes` 是 dead output，本任务消灭它）
  - _Requirements: 4.1, 4.2, 4.3, 3.4_

- [ ] 15. 审定表「从四表库带入未审数」
  - 10 个循环的审定表加按钮，数据源 = render 下发的三层预填
  - 宁缺勿造：解析为空或无活体数据时输出空，不用 0 冒充
  - 手工优先：已有持久化值不覆盖；与现值不同时给确认（可选「仅补空值」）
  - _Requirements: 5.1, 5.2, 5.3_

### Wave 5：披露与附注侧遗留修复

- [ ] 16. 修 `fix_note_h2_construction_structure.py` 的陈旧 `report_row_code`
  - `BS-015` → `BS-029`（在建工程）
  - 加守卫钉死（`--dry-run` 对当前模板须零变更）
  - 顺带核查其余 H 类脚本是否有同类陈旧 `report_row_code`
  - _Requirements: 8.1, 11.1_

- [ ] 17. 修 `fix_note_h8_right_of_use_structure.py` 的 guidance `**`
  - 剥离 `**`（guidance 一律纯文本），消除与平台级 `fix_note_bold_markers.py` 的互相翻转
  - 加守卫：H 类结构脚本的 guidance 目标值不得含 markdown 粗体
  - _Requirements: 8.2_

- [ ] 18. 收敛 `fix_h1_note_section_alignment.py` 与 `fix_note_h1_fixed_assets_structure.py` 双真源
  - 先逐字比对两者对同一批表的 guidance 差异，把差异与取舍依据记入本文件 Notes
  - 保留走共享 kit 的 `fix_note_h1_fixed_assets_structure.py` 为唯一真源，把源模板口径的 guidance 并入
  - 删除 `fix_h1_note_section_alignment.py`（它无 argparse / 无 check / 无 dry-run，无法进 CI）
  - _Requirements: 8.3_

- [ ] 19. 修 `h5NoteSectionMap.spec.ts` 7 例全红 + CI 前端步骤
  - spec 改用现签名（`layerTotals` 而非 `summaryRows`）
  - `buildH5SoeRows` 加 `undefined` 入参保护
  - CI job `note-h5-structure` 补前端步骤（对齐 `note-h7-frontend`/`note-h8-frontend`）
  - _Requirements: 8.4, 8.5_

- [ ] 20. H9 两版披露表动态插行
  - 上市：租赁类别区改动态增删（源模板 `A8:A10` 空白自由列示区），`H9_LISTED_DEFAULT_ROWS` 降级为 seed；`小计`/`减：一年内到期`/`合计` 保持派生不可删
  - 国企：在 `重分类至一年内到期的非流动负债` 后支持续加扣减项（源模板 `A11` = `……`），让模板 seed 的该行能收到数据；`租赁负债净额` 保持派生
  - 稳定 key `rowId`（`H9-listed-{seq}` / `H9-soe-extra-{seq}`），**不用 label**
  - 新增行先 `ElMessageBox.prompt` 输名，撞名拒绝；删除清键 + `_removed_table_keys` 求差集
  - 迁移零丢数：历史固定行持久化键沿用旧 rowKey
  - 守卫 `h9DisclosureDynamicRows.spec.ts`（含 PBT 往返无损）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

- [ ] 21. H10 「不适用的项目删除」口径 + 期限分段反向守卫 + 平台守卫盲区
  - H10：源模板两版均写「不适用的项目删除」，在「提供删行能力」与「推送侧对全空行输出 null 由附注侧折叠」之间择一，写明依据（11 行是准则固定项，倾向后者）
  - 新增 `backend/tests/test_h_cycle_no_maturity_buckets.py`：openpyxl 直读 20 个披露 sheet，期限类判据词命中集 == 白名单（H9 上市 `A12`、H9 国企 `A10`、H2 上市 `D31`/`A36`、H2 国企 `I26`），白名单空则判失效
  - 修 `disclosureAutoSyncCoverage.spec.ts` 的 `/<template>([\s\S]*?)<\/template>/` 截断盲区（H 类 22 个使用点中 12 个未被检查），加反向自检替身
  - _Requirements: 9.5, 10.1, 10.2, 10.3, 11.5, 11.6_

### Wave 6：CI、实测与收尾

- [ ] 22. 新增 CI job
  - `h-cycle-four-table`：Task 2/3/12 + `fix_h_cycle_prefill_presets.py --check` + 各循环 render 测试
  - `h-cycle-four-table-frontend`：Task 13/20 的前端守卫
  - `note-h5-structure` 补前端步骤（Task 19）
  - _Requirements: 11.7_

- [ ] 23. 真实 DB 直跑 render 实测
  - 有活体数据的循环（H1 `1601`/`1602`、H2 `1604`、H3 `1521`/`1525`/`1526`、H6 `1606`、H10 `6115`）：核对 `resolved_from`、三层科目码、`parent_check.diff`、预填金额；验证「叶子和 == 父科目行金额」
  - H3 重点：证明纠正前 `1503`/`1504` 恒空、纠正后取到 `1521` 的真实数据
  - 无活体数据的循环（H5/H7/H8/H9）：只验「解析出正确科目码 + 空值不造假」，**在本文件明确记录验证边界，不把「空」当通过**
  - _Requirements: 12.1, 12.2, 12.3_

- [ ] 24. 浏览器实测披露表与附注同步
  - H9 两版：动态行增删改名 + 撞名拒绝 + 金额千分符 + 推送到附注 + `_removed_table_keys` 生效 + `last_sync_at` 前移
  - 抽验 H3 审定表「从四表库带入未审数」+ 溯源面板显示
  - 测后按快照逐字复原数据
  - _Requirements: 12.4, 9.1, 9.2, 9.6, 4.2, 5.1_

- [ ] 25. 基线对比与收尾
  - 后端与基线 65 failed / 1247 passed 对比；前端与 2070 passed / 8 failed 对比，逐条区分「本次引入」与「HEAD 预存在」
  - Property 15 零回归验证：`git diff` 确认 `report_line_accounts.py` / `leaf_aggregation.py` 未被修改；跑 `backend/tests/four_table` 全量 + D1/K1/K2/F1/G7 相关测试
  - 清理本会话的 `tmp_*` 诊断产物
  - 把实测结论、验证边界、取舍依据写入本文件 Notes
  - _Requirements: 12.5, 2.5_

---

## Notes

（实测结论、取舍依据、验证边界在执行过程中追加）

### 调查阶段已固化的事实

见 requirements.md §Introduction。三个 P0 与公式预设贴错标签清单均有 DB 只读 + `account_chart` + 活体 `tb_balance` 双证。

### 明确的范围外事项

- 上市会计政策章残留的 H8 披露表重复副本（`三、使用权资产`，表名是表头首格泄漏 `项  目`、第 5 列未展开 `……`、39 行与 §五、25 同构）属平台级 data-hygiene，与 G7「章三重复 30 张表」同族 → 不在本 spec 修，避免只补单章节。
- 上市 `三、固定资产` 折旧率表缺 columns/guidance（合法政策表，表名是整段政策文本泄漏）同上。
- `note_template` 的 rows 级 `report_row_code` 全库陈旧（旧编号 `BS-014` vs 现 `BS-028`）属平台级待办，需一次性 remap 脚本，不在本 spec 逐章节补。
- `test_h_cycle_export_import_verification.py` 的 49 例失败锁的是「H 循环还没专属组件」的旧状态，属陈旧测试，本 spec 不改（会与 componentType 契约相互牵动，需单独裁决）。
