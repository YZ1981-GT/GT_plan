/**
 * g06SourceFidelity.ts — `替代程序检查表G0-6` 结构与字面**单一真源**
 *
 * spec: g0-confirmation-source-alignment，Task 14（Requirement 7.1 / 7.6 / 7.7）
 *
 * ─── 为什么新建这个文件（2026-08-04 逐格直读源表后的返工）────────────────────
 * Task 14 一度被判「已交付」，依据是「`G0_ACCOUNT_SUBJECT_OPTIONS` 已存在 + 守卫全绿」。
 * 但守卫只覆盖**列定义**（`blockColumnConfigsG06`），从不校验**段结构与段内字面**
 * → 用户指出该表不对，逐格 openpyxl 直读后确认 **5 处不一致**（见下表）。
 *
 * 教训：区块列守卫全绿 ≠ 整表对齐。段标题/段号/点选项/录入位置属另一维度，须另有真源。
 *
 * ─── 源模板段结构（openpyxl `data_only=False` 直读，`ws.max_column=29`）───────
 * | 锚点  | 逐字内容                        |
 * |-------|---------------------------------|
 * | `A5`  | 会计科目：                       |
 * | `D5`  | 投资产品/名称：                  |
 * | `A6`  | 一、样本选取标准与规模            |
 * | `A7`  | 测试范围：                       |
 * | `B7`  | 大额（）关联方（）大额交易频繁（）异常（）全部（） |
 * | `A8`  | **二、检查过程记录**             |
 * | `A9`  | 1.检查初始投资协议、公司章程等     |
 * | `A15` | 2.检查本期发生额                 |
 * | `C15` | 大额（）关联方（）大额交易频繁（）异常（）**其他**（） |
 * | `A16` | （1）本期借方发生额               |
 * | `A24` | （2）本期贷方发生额               |
 * | `A32` | 3.检查期后是否被出售或赎回         |
 * | `A40` | **三、审计说明：**               |
 * | `A43` | **四、审计结论：**               |
 * | `A46` | 编制说明：                       |
 * | `A47` | 1、函证替代程序：                 |
 * | `B48`~`B50` | 三条替代程序要点（逐字见下）  |
 *
 * 🔴 源模板**只有四个带序号的段**（一/二/三/四），且「二」是**检查过程记录**。
 *
 * ─── 改造前的 5 处不一致（本文件逐条修掉）───────────────────────────────────
 * 1. **源外增强段「余额汇总与检查比例」抢占了段号「二」** → 其后全部串位。
 *    处置：源外增强段**不带段号**（`G06_EXTRA_SECTIONS`），源模板四段各归其位。
 * 2. 「检查过程记录」被编成「三」（源为**二**）。
 * 3. 「三、审计说明」与「四、审计结论」被并成一段「四、审计说明与结论」→ 段号错 + 两段并一。
 *    处置：拆两段、编号归位；**数据仍共用同一 `AuditConclusion` 对象**（不新增持久化键）。
 * 4. `测试范围` 是自由 textarea，而源 `B7` 是 **5 个点选项** → 违反「交互点选优先」铁律。
 *    处置：`el-select multiple allow-create`，选项逐字取源；**旧自由文本作自定义 tag 保留**（数据零丢失）。
 * 5. 源 `C15`「本期发生额」抽样标准（**末项是「其他」不是「全部」**）在平台无任何录入位置。
 *    处置：additive 字段 `SamplingConfig.occurrence_sampling_scope`（其余六枢纽不设值 = 零影响）。
 *
 * ─── 交叉锁死 ───────────────────────────────────────────────────────────────
 * `__tests__/g06SourceFidelity.spec.ts` 把本文件的字面与
 * `backend/tests/test_g0_source_template_facts.py` 的源事实常量（openpyxl 直读）双向比对，
 * 并断言组件确实消费本文件（不抄第二份中文）。
 */

// ─── 段结构 ──────────────────────────────────────────────────────────────────

export interface G06SectionDef {
  key: string
  /** 逐字源模板标题（**含段号**，不含尾部冒号 —— 源 A40/A43 带「：」，UI 由样式控制） */
  title: string
  /** 源锚点 */
  anchor: string
}

/**
 * 源模板四个带序号的段（顺序即渲染顺序）。
 *
 * 🔴 段号是源模板事实，**不得被源外增强段挤位**（改造前正是如此）。
 */
export const G06_SECTIONS: readonly G06SectionDef[] = Object.freeze([
  { key: 'sampling', title: '一、样本选取标准与规模', anchor: 'A6' },
  { key: 'process', title: '二、检查过程记录', anchor: 'A8' },
  { key: 'audit_note', title: '三、审计说明', anchor: 'A40' },
  { key: 'conclusion', title: '四、审计结论', anchor: 'A43' },
])

export function g06Section(key: string): G06SectionDef {
  const s = G06_SECTIONS.find((x) => x.key === key)
  if (!s) throw new Error(`[g06SourceFidelity] 未声明的段: ${key}`)
  return s
}

/**
 * 源外增强段 —— **一律不带段号**，并在标题里明示「源外增强」。
 *
 * 「余额汇总与检查比例」是平台增强（源模板无此段），但它承载 `BalanceSummary` 与
 * 检查比例派生，有真实审计价值 → 保留（裁决门 C 同精神），只是不占源模板段号。
 */
export const G06_EXTRA_SECTIONS: readonly { key: string; title: string; reason: string }[] =
  Object.freeze([
    {
      key: 'balance',
      title: '余额汇总与检查比例（源外增强）',
      reason:
        '源模板 G0-6 无余额汇总段（其 `二、检查过程记录` 直接是三个检查区块）。本段承载 `BalanceSummary` 与借/贷发生额检查比例派生，是判断替代程序覆盖是否充分的依据 → 保留，但不占用源模板段号（改造前它占了「二」，导致检查过程记录被编成「三」、审计说明与结论被挤成「四」并合并）。',
    },
  ])

// ─── 检查过程记录的区块小标题（源 A9 / A15 / A16 / A24 / A32）────────────────

export const G06_BLOCK_HEADINGS: Readonly<Record<string, { title: string; anchor: string }>> =
  Object.freeze({
    block1: { title: '1.检查初始投资协议、公司章程等', anchor: 'A9' },
    block2: { title: '2.检查本期发生额', anchor: 'A15' },
    block2_debit: { title: '（1）本期借方发生额', anchor: 'A16' },
    block2_credit: { title: '（2）本期贷方发生额', anchor: 'A24' },
    block3: { title: '3.检查期后是否被出售或赎回', anchor: 'A32' },
  })

// ─── 点选项（源 B7 / C15）────────────────────────────────────────────────────

/**
 * `一、样本选取标准与规模` 的「测试范围」5 个点选项（源 `B7` 逐字）。
 *
 * 源单元格原文：`大额（）关联方（）大额交易频繁（）异常（）全部（）`
 * —— 括号是纸质底稿的打勾位，平台改为多选。
 */
export const G06_TEST_SCOPE_OPTIONS: readonly string[] = Object.freeze([
  '大额',
  '关联方',
  '大额交易频繁',
  '异常',
  '全部',
])

/** 源 `B7` 原文（守卫据此断言选项集合是它的解析结果，防选项漂移） */
export const G06_TEST_SCOPE_SOURCE_TEXT = '大额（）关联方（）大额交易频繁（）异常（）全部（）'

/**
 * `2.检查本期发生额` 的抽样标准 5 个点选项（源 `C15` 逐字）。
 *
 * 🔴 **末项是「其他」不是「全部」** —— 与 `B7` 只差最后一项，抄错会让两处语义混同。
 */
export const G06_OCCURRENCE_SAMPLING_OPTIONS: readonly string[] = Object.freeze([
  '大额',
  '关联方',
  '大额交易频繁',
  '异常',
  '其他',
])

export const G06_OCCURRENCE_SAMPLING_SOURCE_TEXT =
  '大额（）关联方（）大额交易频繁（）异常（）其他（）'

/** 分隔符：序列化用「、」；解析时容忍中英文逗号/分号 */
const SCOPE_DELIMITER = '、'
const SCOPE_SPLIT_RE = /[、,，;；]/

/**
 * 解析已存字符串为多选值。
 *
 * 🔴 **数据零丢失**：旧版是自由 textarea，存量值可能是整段叙述（无分隔符）
 * → 整段作为一个自定义 tag 保留（配 `allow-create`），绝不丢弃。
 */
export function parseG06ScopeSelections(raw?: string | null): string[] {
  if (!raw || !String(raw).trim()) return []
  return String(raw)
    .split(SCOPE_SPLIT_RE)
    .map((x) => x.trim())
    .filter((x) => x.length > 0)
}

/** 多选值序列化回字符串（与 `parseG06ScopeSelections` 互为逆运算） */
export function serializeG06ScopeSelections(values?: readonly string[] | null): string {
  if (!values || values.length === 0) return ''
  return values.map((v) => String(v).trim()).filter((v) => v.length > 0).join(SCOPE_DELIMITER)
}

// ─── 编制说明（源 A46 / A47 / B48:B50）───────────────────────────────────────

export const G06_PREPARATION_HEADING = { title: '编制说明', anchor: 'A46' }
export const G06_PREPARATION_SUBHEADING = { title: '1、函证替代程序：', anchor: 'A47' }

/** 三条替代程序要点（逐字源模板 `B48`/`B49`/`B50`） */
export const G06_PREPARATION_NOTES: readonly { text: string; anchor: string }[] = Object.freeze([
  { text: '①检查期初原始投资协议、期后出售或赎回协议；', anchor: 'B48' },
  { text: '②检查原始凭证：合同、交易流水、银行回单、支票存根等；', anchor: 'B49' },
  { text: '③对回函可能性不高的、余额重大的，发函同时执行替代程序。', anchor: 'B50' },
])

// ─── 表头字段（源 A5 / D5）───────────────────────────────────────────────────

export const G06_HEADER_FIELDS: readonly { label: string; anchor: string }[] = Object.freeze([
  { label: '会计科目', anchor: 'A5' },
  { label: '投资产品/名称', anchor: 'D5' },
])

/**
 * 红字提示语（源 `O17`）—— 是提示不是列，只作只读方法论上下文展示。
 */
export const G06_KEY_EVIDENCE_HINT = {
  text: '检查的关键证据和要素根据被审计单位具体情况修改',
  anchor: 'O17',
}

// ─── 主表（master 列表）文案 ─────────────────────────────────────────────────

/**
 * G0-6 的主表文案（覆盖共享 `AlternativeD05Master` 的 D0-5 销售循环默认值）。
 *
 * 🔴 改造前 G0-6 的主表显示的是 **D0-5 语义**：`供应商/客户名称` · `新增公司` ·
 * `从 D0-1 带入` · `收款比例` · `出库比例` · 索引号占位符 `D0-` —— 投资循环替代程序
 * 里问「供应商」、看「出库比例」，术语与源模板完全脱节（2026-08-04 用户看界面指出）。
 *
 * 各项的源模板依据：
 * - `被投资单位名称` ← 源 `A10 被投资单位` / `B34 被投资单位名称`
 * - `从 G0-1 带入`   ← G0-1 是本循环的函证结果汇总表（未回函项目由它带入）
 * - `G0-`           ← 询证函索引号前缀（G0-1!B 列形态）
 * - 两个比例列       ← 与明细区既有口径一致（`payment`=股利检查 / `inbound`=持仓检查），
 *                     `type` 仍用 `receipt`/`shipment`，由 `getCheckRatioForMaster` 适配
 */
export const G06_MASTER_LABELS = Object.freeze({
  addButton: '新增被投资单位',
  importFromSummary: '从 G0-1 带入',
  entityColumn: '被投资单位名称',
  entityPlaceholder: '被投资单位名称',
  confirmIndexPlaceholder: 'G0-',
  ratioColumns: Object.freeze([
    { type: 'receipt', label: '股利检查比例' },
    { type: 'shipment', label: '持仓检查比例' },
  ] as const),
  emptyText: '暂无被投资单位记录，请新增或从 G0-1 带入未回函项目',
})
