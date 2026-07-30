# Design — J1 披露表 ↔ 附注模板对齐

## 权威源与裁决

| 序 | 源 | 用途 |
|---|---|---|
| 1 | `backend/wp_templates/J/J1 应付职工薪酬.xlsx` | **运行时权威**（底稿生成时复制）。逐格读出行结构 + Excel 公式（勾稽真源）。无参考副本，不存在两处不一致风险 |
| 2 | `backend/data/consol_note_sections_{listed,soe}.json` | 第 4 方印证：附注交付物的表名 / 表头 / 行序 |
| 3 | `backend/data/note_template_variant_matrix.json` | 章节号（`应付职工薪酬` → listed 五、40 / soe 八、40） |
| 4 | `backend/data/note_workpaper_sync_registry.json` | sheet 名（`附注披露信息（上市公司）` / `附注披露信息（国有企业）`）——实测已正确，不改 |

`note_check_preset_formulas.json` **无 J1 条目**（`J1*` keys = 0）→ 本次裁决者退为源 2。

### 裁决 1：列头取附注口径（沿用已冻结 Decision 2）

源 xlsx 上市侧写「上年年末数 / 期末数」，国企侧写「期初余额 / 期末余额」。
`consol_note_sections_listed.json` 五-40-1/2/3 **三张表都是**
`项  目 / 期初余额 / 本期增加 / 本期减少 / 期末余额`。
→ **附注侧统一「期初余额…期末余额」**；底稿 UI 保留各自源模板列头（上市「上年年末数/期末数」），
同步时由 `j1MovementColumns()` 投影。已实现且有契约测试锁定，本次不改。

### 裁决 2：soe 第 3 表名 = `设定提存计划列示`（撤销原 Decision 3 的"允许偏离"）

原 spec 记录"模板第三张表 name 重复为「短期薪酬列示」（模板笔误），
Sub_Table_Key 改取 text_sections 章节标题「设定提存计划列示」，避免同名键覆盖丢表"。

**这个绕行是错的**：前端推 `设定提存计划列示`，而模板里没有这个表名 →
`_source=workpaper` 时投影器只渲染推送的 `sub_table_data`（不与模板 `_tables` 合并），
对**已同步**项目看起来正常，但：

- 未同步项目的 seed `_tables` 里是两张同名 `短期薪酬列示`（重名 → 附注 TAB 页签重复、
  按 name 建键会互相覆盖）
- 契约 helper 的 P1（子表名逐字存在于模板）**必然失败**

→ 正解是**改模板**（consol_note_sections_soe 五-41-3 的 `title` 就是 `设定提存计划列示`，
证明这是致同原本的措辞，不是自造）。前端键不变，改完自动对齐。

### 裁决 3：国企表2 社保「其中」项保持 4 项，不聚合

源 xlsx 国企侧是 医疗 / 工伤 / 生育 / 其他（4 项）；
附注模板与 consol 是 医疗保险费**及生育保险费** / 工伤保险费 / 其他（3 项）。

按「附注是交付物 → 列结构随附注模版」铁律，本应聚合。但此处是**行**差异而非列差异，
且 `_source=workpaper` 时底稿推送是唯一权威、投影器不与模板合并 →
底稿推 4 行，附注就显示 4 行，信息更细且不丢。**不做聚合**（聚合会让「生育保险费」
在附注里不可见，且引入一层不可逆变换，违背"宁缺勿造 / 不压扁列结构"精神）。

模板侧 seed 行骨架**保持 3 项不动**（它只服务从未同步过的项目，是致同原文）。
这一点写入 `guidance`，避免下次复盘再提。

### 裁决 4：三张表是平行勾稽关系，不是父子派生

源模板里表1「短期薪酬」行 = `'明细表J1-2 '!J33`，表2 合计 = `SUM(...)`，
表2 各行 = `'明细表J1-2 '!J13` 等 —— **三张表都独立引 J1-2 明细表**。
→ 表1 与表2/表3 之间是**应当相等的勾稽关系**，不是"表1 由表2 派生"。

因此：
- 表1 的这两行**保持可手工编辑**（并保留已有的「从审定表/明细表带入」）
- 差异由**勾稽校验面板**报出（H1 范式），而不是静默覆盖用户录入

反例（不采纳）：把表1 两行做成只读派生 → 用户未编制表2/表3 时汇总表恒 0，
且会吞掉「从审定表/明细表带入」的结果。

### 裁决 5：同表内父行 = Σ 紧邻缩进子行 → 做成派生

源模板 `B20=SUM(B21:B27)`（社会保险费）、`B41=SUM(B42:B45)`（离职后福利）
是**同表内**的父子关系，且合计行公式显式排除了这些子行 → 父行是纯派生量。

通用规则（覆盖两处，且对「+ 新增行」自动生效）：
> 非缩进行若其后紧跟 ≥1 个连续缩进行，则该行 期初/增加/减少 = 子行对应列之和。

实现为纯函数 `applyParentSums(rows)`，在 `recalc` 与 `hydrate` 后各跑一次。

## 变更清单

### 1. 幂等修订脚本（新建）

`backend/scripts/fix/fix_note_j1_employee_comp_structure.py`

沿用 `fix_note_g_cycle_structure.py` 范式：`--dry-run` / `--check` / `_aligned_by` 标记，
按 `aliases` 游标匹配表（容忍已改名，保证幂等）。

修订内容：

| variant | 章节 | 动作 |
|---|---|---|
| listed | 五、40 | 3 表补 `columns`(5列 flat)+`_column_groups: []`+`guidance`；表2 删 `……` 行；`text_sections` 重排为【提示】块 + 4 段说明 + 现金流量注 |
| soe | 八、40 | 表3 改名 `短期薪酬列示`→`设定提存计划列示`；3 表补 `columns`+`guidance`；`text_sections` 保留 3 个 `###` 表标题 + 追加 3 条说明正文 |

`guidance` 内容只取：源 xlsx 红字 / 附注模版括注 / CAS 9 条款 / 以「勾稽：」前缀标注的
本 design 已实证的公式关系。

### 2. 勾稽引擎（新建，纯函数）

`audit-platform/frontend/src/components/workpaper/composables/j1DisclosureConsistency.ts`

```ts
export interface J1CheckResult {
  label: string; rule: string
  left: number; right: number; diff: number
  level: 'ok' | 'warn' | 'error'
  detail?: string
  refs?: string[]           // GtIndexChip 追溯
}
export function buildJ1ConsistencyChecks(input: {
  variant: 'listed' | 'soe'
  summary: J1DisclosureRow[]
  shortTerm: J1DisclosureRow[]
  postEmployment: J1DisclosureRow[]
  adjudicationEndTotal?: number
}): J1CheckResult[]
```

规则（6 类，全部有源模板证据）：

1. `表1「短期薪酬」= 表2 合计`（4 列各自校验）
2. `表1「离职后福利-设定提存计划」= 表3 合计`
3. `表1 合计 = Σ 各类别行`
4. `表2 合计 = Σ 非缩进行` / `表3 合计 = 离职后福利 + 其他长期职工福利`
5. `逐行 期末 = 期初 + 增加 − 减少`
6. `表1 合计期末 = J1-1 期末审定合计`（已有 alert，收敛进面板）

容差 0.01 元。`level`：|diff|<0.01 → ok；否则 error（金额勾稽无"警告"中间态）。

### 3. 展示组件（新建）

`.../j1/core/J1DisclosureConsistencyPanel.vue` —— 紧凑单行 bar（`N 项勾稽 · M 项不平`）
+ 折叠明细表（规则 / 左值 / 右值 / 差异 / tooltip）。13px，无 `border stripe`。

### 4. 底稿组件改造

`J1TabDisclosureListed.vue` / `J1TabDisclosureSoe.vue`：

- 顶部方法论上下文块（琥珀色，源模板红字）放在**表1 上方**
- 表1 下方挂勾稽面板
- 表2/表3 父行改为公式单元格（虚线下划线 + tooltip）
- listed 辞退福利 placeholder 改源模板原文
- soe 说明拆 3 个文本域（`soeNonMonetary` / `soeDefinedContribution` / `soeDefinedBenefit`），
  各带 AI 按钮
- 删死代码 `import GtIndexChip`
- 合并重复的 `details 编制提示`

`useJ1DisclosureSections.ts`：新增 `applyParentSums` 并在 `recalcAll` / `hydrate` 调用；
`buildDisclosureSubtotal` 口径不变（已正确排除缩进行）。

### 5. 载荷映射

`j1NoteSectionMap.ts`：
- 头注释更新（撤销 Decision 3，改为"模板已修订"）
- `SOE_NOTE_KEYS` 由 1 段扩为 3 段
- `J1_SUB_TABLE_KEYS` 不变

### 6. 后端 AI prompt

`backend/app/routers/wp_guidance_chat.py` 的 `_SECTION_PROMPTS` 追加 6 条
（listed×3 + soe×3），每条 ≥20 字 + 源模板口径 + 不得虚构。
该端点不做白名单拒绝，追加即生效（ponytail 第 5 层：一个配置搞定）。

### 7. 守卫

| 守卫 | 位置 |
|---|---|
| 模板结构幂等 `--check` | `backend/scripts/fix/fix_note_j1_employee_comp_structure.py` |
| 后端结构断言 | `backend/tests/services/test_note_j1_employee_comp_structure.py` |
| 子表契约（5 Property） | `.../composables/__tests__/j1NoteSubtableContract.spec.ts` |
| 勾稽引擎单测（含反向） | `.../composables/__tests__/j1DisclosureConsistency.spec.ts` |
| CI job | `.github/workflows/governance-checks.yml` → `note-j1-structure` |
| AI prompt 参数化 | `backend/tests/test_j1_ai_sections.py` |

## 风险

| 风险 | 缓解 |
|---|---|
| 并发会话回退模板 JSON | 幂等脚本 + `--check` + CI job；测试红了先重跑脚本 |
| 改模板对既有项目不生效 | 交付说明写清「新建项目 / 重新生成附注才可见」；既有项目靠底稿「同步到附注」整表覆盖 |
| 父行派生吞掉历史手工值 | 只对**存在缩进子行**的父行生效；无子行时行为不变 |
| 上市变体无活体项目 | 8 个在册项目 `entity_type` 全 soe → 国企侧走浏览器实测，上市侧靠契约测试 + 纯函数单测 |
