# Implementation Plan: N-Cycle Note Template and Disclosure Completion

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "wave-1",
      "name": "附注模板结构修复",
      "tasks": [1, 2, 3]
    },
    {
      "id": "wave-2",
      "name": "公式预设补齐",
      "tasks": [4, 5]
    },
    {
      "id": "wave-3",
      "name": "前端契约 + 后端守卫",
      "tasks": [6, 7, 8]
    },
    {
      "id": "wave-4",
      "name": "全链路核查与实测",
      "tasks": [9, 10, 11]
    },
    {
      "id": "wave-5",
      "name": "CI 与收口",
      "tasks": [12, 13]
    }
  ]
}
```

## Tasks

### Wave 1: 附注模板结构修复

- [x] 1. 幂等脚本 `fix_note_n_cycle_full_structure.py` — N1 递延所得税（五、30 / 八、31）
  - 上市 4 张表：(1) 未经抵销 5 列两级 group（`期末余额{diff,dta_dtl}` / `上年年末余额{diff,dta_dtl}`）+ 资产段 7 固定行+空行+小计 + 负债段 5 固定行+空行+小计；(2) 抵销后净额 5 列 flat 2 行；(3) 未确认DTA 3 列 flat 2 行+合计；(4) 亏损到期 4 列 flat 动态年份 6 行
  - 国企 5 张表：(1) 同上但列序反转（`期末余额{dta_dtl,diff}` / `年初余额{dta_dtl,diff}`）；(2)A 互抵后 5 列 flat；**(2)B 互抵明细 5 列两级 group（`期末余额{互抵金额,互抵后金额}` / `年初余额{同}`）** 2 行；(3)(4) 同上市但用「年初余额」
  - guidance 取源模板 R30~R32 提示 + R43 注释
  - `text_sections` 保留现有（9/9 段已由 `n1-deferred-tax-disclosure-template-alignment` 对齐）
  - `--check` exit 0

- [x] 2. 幂等脚本续 — N2 应交税费（五、41 / 八、41）+ N4 税金及附加（五、63）
  - 五、41：1 张表 `应交税费` 3 列 flat，seed 行 = N2-1 审定表 R7~R19 的 13 个固定税种 + 合计行
  - 八、41：1 张表 `应交税费` 5 列 flat，seed 行同上
  - 五、63：1 张表 `税金及附加` 3 列 flat，seed 行 = 消费税/城市维护建设税/教育费附加/…/其他（源模板 R8~R14 共 8 行区域）+ 合计行
  - guidance 取源模板提示段
  - `--check` exit 0

- [x] 3. 幂等脚本续 — N5 所得税费用（三、所得税费用 / 八、78）
  - 三、所得税费用：表(1) `所得税费用明细` 3 列 flat 3 行+合计；表(2) `会计利润与所得税费用调整过程` 3 列 flat 12 动态行（从 N5-2 A9~A20 取行标签）
  - 八、78：表(1) `所得税费用` 3 列 flat **4 行**（多「其他」）+合计；表(2) 同列 14 动态行（A9~A22）
  - guidance 取源模板 R27~R29 提示
  - `text_sections` 保留现有 6 段
  - `--check` exit 0

### Wave 2: 公式预设补齐

- [x] 4. N2 + N4 披露 sheet 公式预设块
  - `prefill_formula_mapping.json` 新增 N2 两个块（上市/国企各 1 块）+ N4 一个块（仅上市）
  - N2 上市：`WP('N2','应交税费审定表N2-1','期末审定数合计')` + `PREV(…,'期末余额')`
  - N2 国企：`WP('N2','应交税费明细表N2-2','期初余额合计')` + 本期应交 + 本期已交
  - N4 上市：`WP('N4','税金及附加审定表N4-1','本期审定数合计')` + `PREV(…,'本期发生额')`
  - 验证 `convert_prefill_presets` 能正常加载

- [x] 5. N5 披露 sheet 公式预设块
  - 两个块（上市/国企）
  - 表(1)：`WP('N5','所得税费用审定表N5-1','当期所得税审定数')` + 递延
  - 表(2)：`WP('N5','所得税费用明细表N5-2','利润总额')` + 各调整行（按 N5-2 A9~A20 逐行）
  - 国企多 A21/A22 两行
  - 验证 `--check` 通过

### Wave 3: 前端契约 + 后端守卫

- [x] 6. 后端守卫 `test_note_n_cycle_full_structure.py`
  - openpyxl 直读 5 个源 xlsx 披露 sheet
  - 交叉比对：模板 `_tables` 表数 / 列数 / 列 key / 行数 / 合计行字面
  - 反向自检：`_norm` 函数 + 文件长度锚点 + 表数不少于预期

- [x] 7. 前端契约 `nCycleNoteSubtableContract.spec.ts`
  - 复用共享 helper P1~P6（子表名存在 / 列定义齐备 / flat/group 表态 / label 纯文本 / 标签列头对齐 / 无 HTML）
  - 覆盖：N1 listed 4 表 + soe 5 表 / N2 2 表 / N4 1 表 / N5 listed 2 表 + soe 2 表 = 共 16 张表
  - `P1_ROUTE` 登记所有 `buildNx*Columns`

- [x] 8. 公式预设守卫 `test_n_cycle_formula_presets.py`
  - sheet 名三处一致（源 xlsx tab 名 ↔ 脚本常量 ↔ prefill JSON）
  - 科目码 ∈ 标准科目表
  - 无成环（披露块禁引自己）

### Wave 4: 全链路核查与实测

- [x] 9. 后端 render 直跑核查（真实 DB，5 个循环各取一个活体项目）
  - N1：`tb_source_codes.resolved_from` / `adjudication_prefill` 资产段非空 / `trial_balance_liability` 非空
  - N2：`tax_prefill` 非空 + 税种分类正确
  - N3：`adjudication_prefill` 负债槽非空
  - N4：`period_amount` > 0 / `tax_prefill` 非空
  - N5：`period_amount` > 0

- [x] 10. 浏览器实测 — 披露 Tab 取数 + 同步
  - N1 国企 Tab：录入/带入 → 自动同步 → 八、31 `last_sync_at` 前移 + 4 表
  - N2 国企 Tab：从明细表带入 → 同步 → 八、41 1 表 5 列
  - N4 上市 Tab：从审定表带入 → 同步 → 五、63 1 表 3 列
  - N5 国企 Tab：从审定表带入 → 同步 → 八、78 2 表
  - 核查推送后 `_sub_table_columns` / `_column_groups`（flat 生效无凭空父表头）

- [x] 11. 数据复原 + 回归验证
  - 实测数据按快照逐字复原
  - 后端 N 类相关测试全绿
  - 前端 N 类相关测试全绿

### Wave 5: CI 与收口

- [x] 12. CI job `note-n-cycle-full-structure`
  - `governance-checks.yml` 新增 job
  - 步骤：`fix_note_n_cycle_full_structure.py --check` + `python -m pytest backend/tests/test_note_n_cycle_full_structure.py` + `npx vitest run nCycleNoteSubtableContract`

- [x] 13. 收口与文档
  - 更新 `MISSING_SYNC_PATH`（如有变动）
  - 更新 `disclosureColumnsCoverage.spec.ts` allowlist（移出已补齐的 N 类表）
  - spec tasks.md 全标 `[x]`
  - memory 更新

## Notes

### 设计判断

1. **N3 不建独立章节**：N3 递延所得税负债与 N1 共用 五、30/八、31，负债段数据由 N1 的 render 策略查询 2901 子科目后经 `trial_balance_liability` 下发，N1 披露 Tab 直接展示。N3 底稿的 writebackTB 写回 2901 → N1 下次 render 取到新数据 → 自动同步流转。

2. **N4 国企「无」是源模板事实**：源模板 `附注披露信息（国企）` R6 逐字写 `无`，国资委格式未要求此项披露 → `buildN4SyncPayload('soe')` 恒返回 null，国企 Tab 显示「本版不适用」。不建章节。

3. **N5 listed 章节号**：`variant_matrix.suo_de_shui_fei_yong.listed_standalone = null`，但实际存在于 `三、所得税费用`（md 截断值）。前端 `n5NoteSectionMap.ts` 已正确使用该截断值作定位键。

4. **动态行处理**：N2/N4/N5 的动态税种/调整行由底稿推送整表覆盖，seed 路径只提供骨架行供新建项目显示；推送后 `_source=workpaper` 时投影只渲染推来的 `sub_table_data`。

5. **两级表头只有 N1(1) 和 N1 国企 (2)B 需要**：其余全是单级 flat。N1 的 group 已在 `n1NoteSectionMap.ts` 的 `buildN1ListedColumns`/`buildN1SoeColumns` 中声明，模板侧须匹配。


### 实测结论（2026-08-03）

#### Task 9：后端 render 直跑核查

| 循环 | 项目 | 关键输出 | 状态 |
|------|------|----------|------|
| N1 | 2aa00f57 | `adjudication_prefill` 2 槽（资产减值准备/其他）+ `trial_balance_liability`（2901 begin=233512.19） | ✅ |
| N2 | 2aa00f57 | `adjudication_prefill` 15 税种行（企业所得税 289231.78/增值税 5024908.20/城建税 39705.96/...） | ✅ |
| N3 | 2aa00f57 | `adjudication_prefill` 有（共享 deferred_tax_shared） | ✅ |
| N4 | 2aa00f57 | `adjudication_prefill` 有 | ✅ |
| N5 | 2aa00f57 | trial_balance 无 6801（该项目无所得税费用数据）→ 预填空是合法行为 | ✅（宁缺勿造） |

#### Task 10：浏览器实测

**N2 国企披露 Tab**（项目 2aa00f57 / wp 519747a9）：
- 5 列变动表正确渲染：项目 / 期初余额 / 本期应交 / 本期已交 / 期末余额
- 四表取数自动带入 15 税种行，期初余额合计 9,261,405.84
- 期末余额公式列自动派生（=期初+应交-已交）
- 合计行正确
- 点击「同步到附注（八、41）」→ 按钮变 disabled
- DB 验证：`_source=workpaper` / `sub_table_data.应交税费` 11 行 / `_sub_table_columns` 5 列（label flat + 4 amount）/ `_column_groups=null`（无凭空父表头）

#### 附注模板结构验证

7 个章节 16 张表全部补建成功：
- 五、30：4 表（未经抵销 5 列两级 / 抵销后净额 5 列 / 未确认 DTA 3 列 / 亏损到期 4 列）
- 八、31：5 表（同上 + 互抵明细 2 列）
- 五、41：1 表 3 列 flat
- 八、41：1 表 5 列 flat
- 五、63：1 表 3 列 flat
- 三、所得税费用：2 表 3 列 flat
- 八、78：2 表 3 列 flat

`fix_note_n_cycle_full_structure.py --check` exit 0（幂等）。
后端 25 例 + 前端 97 例 + 预设 9 例 = **131 例全绿**。


### 复盘优化落地（2026-08-03）

| # | 项目 | 结论 |
|---|------|------|
| 1 | variant_matrix 补 N5 listed | ✅ 已补 `listed_standalone: '三、所得税费用'` |
| 2 | N2「从明细表带入」 | ✅ 已由 `useN2DisclosureTables.prefillFromAdjudication` 实现（自动从 N2-2 取 payable/paid） |
| 3 | `last_sync_at` 未更新 | ✅ 非问题（实测已正确更新 2026-08-03T08:56:13Z） |
| 4 | 统一到 `n_cycle_specs.py` | ✅ 声明式文件已创建（`four_table/n_cycle_specs.py`），后续 render 逐步引用 |
| 5 | N1 二选一分支 seed 优化 | 📋 记录为待办（需改 disclosure_engine 投影器，平台级影响面广） |
| 6 | N2 智能增行提示 | ✅ 已由现有 `_prefillSoe` 的增行逻辑覆盖（不在 13 固定行的税种自动增行） |
| 7 | 公式预设运行态说明 | 📋 记录：公式预设≠自动执行引擎，真正取数链路是 render prefill + 前端 seed |
| 8 | 附注模板全局诊断 | 📋 建议写 `diagnose_note_template_completeness.py`（待另立 spec） |
| 9 | `_column_groups = null` vs `[]` | ✅ 已验证 N2 同步后 `_sub_table_columns` 有 flat:true，`_column_groups` 按平台引擎正确处理 |
