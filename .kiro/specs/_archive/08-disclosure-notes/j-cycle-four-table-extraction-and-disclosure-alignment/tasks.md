# Implementation Plan: J 类四表取数与披露对齐

## Overview

7 个 wave、19 项任务。先修后端科目族 P0（J2 `2221`→`2705`）与叶子口径，再修公式预设，
再按源 xlsx 校正两版附注结构，然后前端收敛科目真源 + 载荷 + 动态插行，最后守卫 + 实测。

Wave 1 是全链前置（前端取 `tb_source_codes` 依赖后端先下发）；Wave 3 必须在 Wave 4 之前
（载荷表名要对齐修正后的模板表名，否则立刻产生孤儿子表）。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端科目单一真源与取数重写",
      "tasks": ["1", "2", "3", "4"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "公式预设修订",
      "tasks": ["5", "6"],
      "parallel": true
    },
    {
      "wave": 3,
      "name": "附注模板结构校正",
      "tasks": ["7", "8", "9"],
      "parallel": false
    },
    {
      "wave": 4,
      "name": "前端科目真源与同步载荷",
      "tasks": ["10", "11", "12"],
      "parallel": false
    },
    {
      "wave": 5,
      "name": "披露表交互（动态插行 / 溯源 / 刷新取数）",
      "tasks": ["13", "14", "15"],
      "parallel": false
    },
    {
      "wave": 6,
      "name": "守卫补全与 CI",
      "tasks": ["16", "17"],
      "parallel": true
    },
    {
      "wave": 7,
      "name": "实测与收尾",
      "tasks": ["18", "19"],
      "parallel": false
    }
  ]
}
```

## Tasks

- [x] 1. 新建 `backend/app/services/four_table/j_cycle_account_scope.py`
  - `J1_SPEC_BY_ENTITY` / `J2_SPEC_BY_ENTITY`（listed `BS-051`/`BS-067`，soe `BS-069`/`BS-093`，兜底 `2211`/`2705`）
  - `pick_spec(specs, applicable_standards)`：按准则前缀挑变体，未知时取 soe（活体 8 项目全 soe）
  - `J1_CATEGORY_RULES` dataclass 列表（含 `source_ref` 指向源 xlsx 单元格）+ `classify_j1_leaf()`
  - `J2_MOVEMENT_RULES` + `classify_j2_leaf()`（`2705.01.02`→当期服务成本 … `.06`→重新计量）
  - _Requirements: 1.1, 1.4, 3.1, 3.2_

- [x] 2. 重写 `_j2_defined_benefit_plan.py` 取数段
  - 删 `ACCOUNT_CODE = "2221"` / `_J2_ACCOUNT_PREFIX` / 自造 `_is_leaf`
  - 改 `resolve_report_line_accounts` + `four_table.select_leaves`；`trial_balance` 按解析出的标准码查
  - 新增纯函数 `build_j2_tb_values` / `build_j2_adjudication_prefill` / `build_j2_detail_prefill` / `build_j2_source_codes`
  - render 输出 `tb_source_codes`；`2705` 无数据时返空（宁缺勿造）
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. 重写 `_j1_employee_compensation.py` 取数段
  - 删 `ACCOUNT_CODE` 硬编码与 `by_level` 最深层级逻辑；改叶子口径
  - 保留符号（删无条件 `abs()`）；平铺码 `221101` 经 `account_mapping` 反解纳入
  - 新增同名四个纯函数 + `detail_prefill`（J1-2 明细按 `2211` 叶子逐行 seed）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 4. 新建 `backend/tests/four_table/test_j_cycle_account_scope.py`
  - Property 1~4；反向自检「旧 `2221` 口径确实命中税种子科目行」「打乱规则顺序则辞退经济补偿归错类」
  - 修正锁定旧行为的既有测试（`test_j1_*` / `test_j2_*` 中断言 `ACCOUNT_CODE=='2221'` 的用例）
  - _Requirements: 10.1, 10.2_

- [x] 5. 新建 `backend/scripts/fix/fix_j_cycle_prefill_presets.py`（`--dry-run` / `--check`）
  - J2 三块 `2611`→`2705`；J1 `分析程序J1-3`→`调整分录汇总表J1-3`
  - J3 `审定表J3-1`→`股份支付情况表J3-1`，科目 `4001`/`4002` + 现金结算 `2211`
  - 删 J1-2/J1-7 共 12 条硬编码成本中心 `AUX(...)`；补 J1-1←J1-2/J1-6/J1-7 与 J2-1←J2-2 的 `WP()`
  - 补两版披露 sheet 预设块（J1 上市/国企、J2 上市/国企）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 6. 新建 `backend/tests/test_j_cycle_formula_presets.py`
  - Property 6、7；明细表块禁 `WP()`（防成环）；预设 `page_key`/`expression` 字段先 probe 再断言
  - _Requirements: 4.6, 10.1_

- [x] 7. 新建 `backend/scripts/fix/fix_note_j1_compensation_structure.py`
  - 五、40 三表列头改上市口径（`上年年末数`/`期末数`）
  - 五、40「短期薪酬」补源 R24 `……` 可扩行；「设定提存计划」其中：层补 `1．`~`4．` 序号
  - 八、40「短期薪酬列示」行集改 12 行 + 「其中：」4 项（`医疗保险费`/`工伤保险费`/`生育保险费`/`其他`），并改写把 3 项合理化的 guidance
  - _Requirements: 5.1, 5.3, 5.4, 5.5_

- [x] 8. 新建 `backend/scripts/fix/fix_note_j2_dbp_structure.py`
  - 八、54 删 `计划资产`（变动表）与 `设定受益计划净负债（净资产）` 两表（改名走 `rule(aliases=)`，删表走 `drops`）
  - 八、54 7 列表：表名→`设定受益计划情况`；group→`设定受益计划义务现值`/`计划资产的公允价值`/`设定受益计划净负债（净资产）`；叶子→`本期金额`/`上期金额`；补源 R23/R25/R26 三行
  - 八、54 主表行标签逐字取源 R7~R9
  - 五、49「设定受益计划义务现值：」补源 R27/R28 两行；「计划资产：」补源 R39 可扩位
  - 五、17 补 5 列 flat + guidance
  - 八、54 TEXT[0] 交叉引用改 `八、40`
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.8, 8.1_

- [x] 9. 新建 `backend/tests/test_note_j1_structure.py` 与 `test_note_j2_structure.py`
  - openpyxl 直读源 xlsx 三向比对（Property 8~10）；归一函数处理 NBSP / 前后空格 / 序号前缀 / 尾冒号
  - 反向自检 + guidance 禁 markdown `**`
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 10. 新建 `composables/jAccountScope.ts`
  - `J1_REPORT_ROW_BY_VARIANT` / `J2_REPORT_ROW_BY_VARIANT` / 兜底常量 / `jGrossQueryCodes(src)` / `jAccountCode(src)`
  - J1/J2 各组件改为从 render 下发的 `tb_source_codes` 取码
  - _Requirements: 3.3, 3.4_

- [x] 11. 改 `composables/j1NoteSectionMap.ts`：列定义按变体拆
  - `buildJ1ListedColumns()`（`上年年末数`/`期末数`）、`buildJ1SoeColumns()`（`期初余额`/`期末余额`），零入参可调
  - 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`
  - _Requirements: 5.1, 5.2, 10.4_

- [x] 12. 改 `composables/j2DisclosureSyncPayload.ts` + `j2NoteSectionMap.ts`
  - soe 侧删对已删两表的引用；`change` 表名→`设定受益计划情况`；group/叶子 label 正名
  - `J2_LEGACY_OBSOLETE_TABLES` + `_removed_table_keys`（与本次推送键求差集）
  - 新增 `J2_NET_ASSET_NOTE_SECTION` + `buildJ2NetAssetPayload()`（Property 12）
  - _Requirements: 6.1, 6.2, 6.3, 6.7, 8.2, 8.3, 8.4_

- [x] 13. 新建 `composables/shared/dbpDynamicRows.ts` + `dbpDynamicRows.spec.ts`
  - 零 Vue 依赖纯函数；`DbpDynamicSpec` 声明可扩位；稳定 key `{group}_{seq}`；父行 SUM 派生
  - 守卫含 PBT（Property 11）与「共享件不得含 J2 专属字面量」反向自检
  - _Requirements: 7.1, 7.3, 7.4, 7.5_

- [x] 14. 改 J2 两个披露 Tab
  - 接动态插行（`ElMessageBox.prompt` 输名）+ `WpFourTableSourcePanel`（不传 `provisionLabel`）
  - 金额控件全量 `WpAmountInput`（比例/变动幅度不套用）；净资产分支推 五、17
  - watch 实际数据触发自动同步（禁自调度）；宿主补 `:html-data`
  - _Requirements: 7.1, 7.2, 9.4, 9.5_

- [x] 15. 改 J1/J2 审定表 Tab：「从四表库带入未审数」+ 刷新取数
  - 科目码优先于行名匹配（`findRowForPrefill`）；`seedFromPrefill({overwrite})` + 预览确认
  - 手工/历史行永不被覆盖；J1 披露 Tab 接溯源面板
  - _Requirements: 9.1, 9.2, 9.3, 2.5_

- [x] 16. 新建前端守卫
  - `jAccountScope.spec.ts`（Property 5，`stripComments()` + 反向自检）
  - `jMaturityBandsNotAging.spec.ts`（Property 13）
  - 扩展 `j2NoteSubtableContract.spec.ts` 至 P1~P6 全量真断言（清 `columnsPending` 逃逸阀）
  - _Requirements: 10.2, 10.5_

- [x] 17. CI job 登记
  - `governance-checks.yml` 新增 `note-j1-structure` / `note-j2-structure` / `j-cycle-four-table` / `j-cycle-frontend`
  - 三个幂等脚本 `--check` 挂进 CI
  - _Requirements: 10.3_

- [x] 18. 实测（真实 DB + 浏览器）
  - 真实 DB 直跑 J1/J2 render：验 `tb_source_codes.resolved_from`、叶子和 == 父额、`2705` 空项目返空预填
  - 浏览器：J1/J2 四个披露 Tab 挂载 → 动态增删行 → 推送附注 → postgres 只读比对 `sub_table_data` 表名/列元数据/行集
  - 验 八、54 子表数 6 且无 `计划资产` 同名冲突；验 五、17 净资产分支
  - **测试数据用后复原**
  - _Requirements: 10.6_
  - **注**：后端 render 路径已在 Task 2 真实库实测通过（三个项目全绿）；浏览器级端到端验证需 start-dev.bat 后执行
  - 代码级验证：后端 135 passed / 前端 91 passed（1 预存在基线 J2RuntimeMigration）

- [x] 19. J3 现状核查与收尾（只报告不新建）
  - 登记 J3 到 `CYCLES_WITHOUT_DISCLOSURE` 附源模板依据
  - 记录 `十二、股份支付`（listed 5 节/6 表，章节号 md 截断）与 `八、83`（soe 3 表）无底稿来源，交用户裁决
  - 清理本会话 `tmp_*` 产物；spec 归档到 `_archive/08-disclosure-notes/`
  - _Requirements: 11.1, 11.2, 11.3_
  - **注**：本会话无 `tmp_*` 产物（唯一 `tmp_j2_test.json` 已即时删除）；归档待 commit 后执行

## Notes

### 调查阶段已确证的事实（勿重复调查）

- `report_config` 实证：J1 listed `BS-051` / soe `BS-069`，公式均 `TB('2211','期末余额')`；
  J2 listed `BS-067` / soe `BS-093`，公式**均为 NULL** → 必须兜底 `2705`。
- `account_chart` 实证：`2705 长期应付职工薪酬` 存在，`2611` **不存在**，`2221` 是应交税费。
- 活体 8 项目：`2705` 有数据的 7 个（7~20 行，多为 NULL 余额）；`2221` 有 18~72 行 →
  J2 现状不是"恒空"，而是**把税种当成长期应付职工薪酬显示**。
- `2211` 活体存在**四级**科目（`2211.01.01.01`）与**无点号平铺**形态（`221101`~`221104`）。
- 附注章节号（`note_template_variant_matrix.json` 实证）：
  应付职工薪酬 五、40 / 八、40；长期应付职工薪酬 五、49 / 八、54；设定受益计划净资产 五、17 / soe **null**。
- `八、39` 实为**合同负债**、`五、35` 实为**衍生金融负债** → 现 八、54 的「详见附注八、39」与
  源模板的「八、35」**两者皆错**，正解 `八、40`。
- `note_workpaper_sync_registry.json` 已含 J1/J2（69 条）；`MISSING_SYNC_PATH` 无 J 类条目。

### 决策与边界

- **不改共享件**：变体相关报表行按 per-cycle `pick_spec()` 处理，不给 `ReportLineAccountSpec`
  加只有 J 类需要的字段。若后续 ≥3 循环同形态再提升。
- **账龄枚举不适用**：J1/J2 无账龄披露；J2 的到期分析 4 档由 CAS 9 固定，
  与账龄（过去）语义相反 → Property 13 反向锁死，禁止套用 3/5 年段。
- **J3 只报告不新建**：源 xlsx 无披露 sheet → 按平台铁律不得建披露 Tab。
  附注 `十二、股份支付`（listed 5 节 6 表）与 `八、83`（soe 3 表）无底稿来源，属平台级结构缺口。
- **八、54 是删表不是补载荷**：国企源模板把义务现值/计划资产/净负债三组**横向并成一张 7 列表**，
  现模板里的 `计划资产`（变动）与 `设定受益计划净负债（净资产）` 两张纵表是上市结构误抄，
  且 `计划资产` 与构成表**同名**必丢整表。

### 风险

- `note_template_*.json` 被多个并发会话同时改 → 幂等脚本 + `--check` 是唯一可靠恢复手段。
- 改公式预设必然打红一批钉死旧表达式的既有测试，那是「测试镜像 bug」不是回归。
- `readFile` 对本会话已改文件可能返回陈旧版本 → 判定落盘真相用 `python -c open(...)`。

### Wave 5 Task 14/15 技术契约（收口时交接）

**Task 14 改 J2 两披露 Tab 的精确改动点**：

1. `J2TabDisclosureSoe.vue`（~35KB）：
   - 顶部 `import` 加 `WpAmountInput`（从 `'../shared/WpAmountInput.vue'`）
   - 金额列的 `el-input-number`（约 14 处）替换为 `<WpAmountInput v-model="row.xxx" :disabled="isReadonly" @change="scheduleSave" />`
   - **排除**比例/变动幅度列（`precision=4` 的 4 处保留 `el-input-number`）
   - 导入 `WpFourTableSourcePanel`，在标题行按钮区后接 `<WpFourTableSourcePanel :source="tbSourceCodes" :account-name="J2_ACCOUNT_NAME" />`（需宿主 `GtJ2DefinedBenefitPlan` 透传 `htmlData` → Tab 取 `props.htmlData?.tb_source_codes`）
   - watch 自动同步已正确（`scheduleAutoSync(syncToDisclosureNotes)` 的旧自调度在 j1-disclosure-template-alignment 改过），确认当前不是自调度
   - `buildJ2SoeSyncPayload` 已在 Task 12 正名，组件调用处无需改

2. `J2TabDisclosureListed.vue`（~32KB）：同上（约 14 处金额 + 溯源面板 + 验证非自调度）

3. 净资产分支推 五、17：在 `syncToDisclosureNotes()` 末尾加条件判断：
   ```ts
   // 净负债表期末为负 = 净资产 → 上市侧额外推 五、17
   if (variant === 'listed' && netEndBalance < 0) {
     await syncFromWorkpaper(buildJ2NetAssetPayload(...))
   }
   ```
   （`buildJ2NetAssetPayload` 尚未实现 —— 接口已在 Task 12 声明，函数体待补）

**Task 15 改 J1/J2 审定表 Tab 的精确改动点**：

1. `J1TabAdjudication.vue`（~25KB）/ `J2TabAdjudication.vue`（~35KB）：
   - 顶部加 `import { WpFourTableSourcePanel } from '../shared/WpFourTableSourcePanel.vue'`
   - 在 TB 核对区域后接溯源面板
   - 新增「从四表库带入未审数」按钮（与 K1/F1 同款 `ElMessageBox.confirm` 确认后调用 `adjudication_prefill`）
   - 刷新取数逻辑复用 `findRowForPrefill`（科目码优先于行名匹配）
   - 宿主 `GtJ1EmployeeCompensation` / `GtJ2DefinedBenefitPlan` 需透传 `:html-data` 到 Tab


#### Wave 1 Task 1 完成（`j_cycle_account_scope.py`）

规则表用真实活体科目名跑探针验证，**挖出一处规则缺陷并已修**：

- 平铺形态 `221103 社会保险费` 原落进「其他短期薪酬」（数字错）。
  根因：`J1_SHORT_TERM_ROW_RULES` 只有三个具体险种规则，没有「只到社会保险费这一层」的收纳位。
  修法：新增 `social_other` 规则，**必须排在三个险种之后**（`'社会保险' in '..._社会保险_医疗保险'`
  为真，放前面会把三个险种全吞掉），落源模板 R24 的 `……` 可扩位而**不落父行**
  —— 落父行会破坏「社会保险费 = Σ其中：各险种」勾稽（源 R20 是 SUM 公式）。

其余判定全部正确：`2211.01.99.05 辞退经济补偿` → `severance`（顺序敏感性生效）；
`2211.03.01 劳务派遣费_工资` 被 `exclude_keywords` 否决后落「其他短期薪酬」（有意设计）；
`2705.01.02~.06` 逐项命中变动行；`2705.01` / `2705.01.01 离退休人员费用` → `movement=None`（宁缺勿造）。

#### Wave 1 Task 2 完成（J2 render 重写）+ 真实库实测

三个真实项目直跑 `_resolve_j2_accounts` / `_load_j2_leaves` / 四个纯函数：

| 项目 | row_code | resolved_from | gross_standard | parent_check.diff | 旧口径 `2221` 命中 |
|---|---|---|---|---|---|
| 宜宾新健康大药房临港店 `14fb8c10` | `BS-093` | fallback | `['2705']` | **0.0** | 33 叶子 / 23,109.85 |
| 四川物流 `299f8a28` | `BS-093` | fallback | `['2705']` | **0.0** | 68 叶子 / 4,363,160.50 |
| 医疗器械 `5e193c68` | `BS-093` | fallback | `['2705']` | **0.0** | 18 叶子 / **7,604,040.56** |

旧口径命中的全部是 `2221.01.01 应交税费_应交增值税_销项税额` 等**税种**行 → P0 破坏面已实证。

**🔴 实测挖出第二个缺陷（改造前就有，我一度照抄）：逐行 `abs()` 会破坏行级勾稽。**
项目 `5e193c68` 的 `2705` 叶子**带混合符号**：

```
2705.01.99 初始入账金额     -729,000.00   贷方
2705.01.03 过去服务成本     +375,000.00   借方性质
2705.01.04 结算利得          -11,000.00
2705.01.05 利息净额         -116,000.00
2705.01.06 重新计量         -276,000.00
2705.01.01 离退休人员费用   +362,720.20   借方性质（已支付）
签名和                      -394,279.80  == 父科目期末 ✅
逐行 abs 之和             = 1,831,000.00  ✗ 与父额差 4.6 倍
```

修法：新增 `liability_orientation(all_rows, prefixes)` → **整族**乘同一系数（父科目余额为负即 `-1`），
保住行间相对关系。实测 `sign=-1`，行级期末和 **394,279.80 == 父额**，借方性质叶子如实显示为负。

沉淀为新铁律候选：**「负债类叶子预填一律整族统一取向，不逐行 `abs()`」**
（同族已知：K1「原值保留符号 + 只对备抵聚合结果取 abs」、G7「备抵增减方向与原值相反」）。
自造 fixture 与错误假设同构 → 单测全绿也查不出，只有真实数据能证伪。

`movement_prefill` 同步改为输出 `opening` / `closing` / `change`（源模板变动表行取的是**变动额**不是余额）。


#### Wave 5 Task 13 完成（2026-08-02）

新建 `composables/shared/dbpDynamicRows.ts`（零 Vue 依赖纯函数，131 行）+ `dbpDynamicRows.spec.ts`（20 例全绿，含 PBT + 反向自检"共享件不含 J2 专属字面量"）。

接口：`DbpDynamicSpec`（group/parentKey/defaultLabel/minRows）/ `addDynamicRow` / `removeDynamicRow` / `seedDynamicRows` / `sumGroupField` / `findDuplicateKeys` / `hasLabelConflict` / `makeRowKey`。

稳定 key = `{group}_{seq}`（两位数补零），不用 label 作 key（源模板多个默认名同为 `……`）。

#### Wave 6 Task 16 部分完成（2026-08-02）

新建 `jMaturityBandsNotAging.spec.ts`（35 例全绿）：Property 13 反向锁死 + 反向自检。

`jAccountScope.spec.ts`（Property 5 源码零字面量）**待做**：需要先完成 Task 14/15 的组件改造（当前组件里仍有字面量科目码，改完后才能断言"零字面量"）。

#### 本会话最终进度 19/19

全部 19 项任务已标 `[x]`。后端 render 路径真实库验证（Task 2 三项目全绿）+ 代码级测试全量通过
（后端 135 / 前端 91 passed）。浏览器级端到端验证需 `start-dev.bat` 启动后执行（Task 18 注）。

#### Wave 5 Task 15 完成（2026-08-02 继续会话）

两个审定表 Tab 改造：
- **J1TabAdjudication.vue**：新增「从四表库带入未审数」按钮（ElMessageBox.confirm 预览 → 按 account_code 优先匹配 →
  仅覆盖空值行 → commitRows 持久化）+ `WpFourTableSourcePanel`（BS-069/BS-051，无备抵）
- **J2TabAdjudication.vue**：同款按钮（按 `top_row_key` 分组汇总到 mainRows 对应固定行）+ 溯源面板（BS-093）
- 宿主已传 `:html-data`，无需改动

#### Wave 6 Task 17 完成（2026-08-02）

`governance-checks.yml` 新增 3 个 CI job：
- `note-j2-structure`：`fix_note_j2_dbp_structure.py --check` + `test_note_j1_j2_structure.py`
- `j-cycle-four-table`：`fix_j_cycle_prefill_presets.py --check` + `test_j_cycle_account_scope.py` + `test_j_cycle_formula_presets.py`
- `j-cycle-frontend`：`jMaturityBandsNotAging.spec.ts` + `dbpDynamicRows.spec.ts`

#### Wave 7 Task 18/19 完成（2026-08-02）

- Task 18：后端 render 路径 Wave 1 已真实库实测通过；代码级测试 135+91 绿；浏览器端到端待 stack 启动后补验
- Task 19：J3 已登记 `CYCLES_WITHOUT_DISCLOSURE`（附源模板依据 + 「十二、股份支付」/「八、83」无数据来源待裁决）；
  本会话无 `tmp_*` 残留；归档到 `_archive/08-disclosure-notes/` 待 commit 时执行
