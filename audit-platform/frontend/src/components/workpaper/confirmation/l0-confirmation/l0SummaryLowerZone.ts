/**
 * l0SummaryLowerZone.ts — L0-1 下区「二、样本选择 / 三、审计说明 / 四、审计结论」文字真源
 *
 * spec: l0-confirmation-source-alignment，Task 11（Requirements 3.6 ~ 3.9）
 *
 * ─── 源模板事实（openpyxl 直读，后端 `test_l0_source_template_facts.py` 已固化）──
 * 四块段头：`C28 一、函证情况` / `J28 二、样本选择` / `S28 二、审计说明` / `C39 四、审计结论`
 *
 * 🔴 **`S28` 的「二、」是源模板序号笔误** —— C28 已是「一、」、J28 是「二、」、
 * C39 是「四、」，故审计说明段应为「三、」。平台展示更正值 + tooltip 标注原字面，
 * **不改源 xlsx**（登记在 `L0_SECTION_TITLES`）。
 *
 * 🔴 **三处「一句话被源模板拆成两格」必须合并渲染**，只取前格会出现半句话：
 * | 前格 | 后格 | 内容                                   |
 * |------|------|----------------------------------------|
 * | W30  | W31  | 误差界定条件（前格以「［」开，后格才有「］」） |
 * | S34  | S35  | 针对不符事项的程序 + 其补充说明          |
 * | K35  | K36  | 抽样过程（前格以逗号结尾 = 续行标志）     |
 *
 * 🔴 `K33`（「如果使用了样本计算器…」）是 `J32` 的**括注**（`J33` 无标签），
 * 作提示文本不作独立录入项。
 *
 * 🔴 `S33` 的「（L0-6）」是**正确索引号**（底稿目录 `F10=L0-6`），不在三处笔误之列 ——
 * 判索引号对错一律回查底稿目录 `F4:F11`，别看见括号就当笔误。
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

/** 收敛锚点（裁决门 D = D-2）—— 下区类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'

/** 下区持久化键前缀（`checklist_responses` 的 item_id 用它，与上区 grid 载荷不重叠） */
export const L0_LOWER_KEY_PREFIX = 'L0-1-lower'

// ─── 段标题（含笔误更正） ───────────────────────────────────────────────────

export interface L0SectionTitleDef {
  /** 段标识 */
  id: 'matrix' | 'sample' | 'auditNote' | 'conclusion'
  /** 平台展示值（笔误已更正） */
  display: string
  /** 源模板字面 */
  sourceLiteral: string
  /** 源锚点 */
  source_ref: string
  /** 非空 = 源模板此处有笔误，tooltip 展示本说明 */
  typoNote?: string
}

export const L0_SECTION_TITLES: readonly L0SectionTitleDef[] = Object.freeze([
  { id: 'matrix', display: '一、函证情况', sourceLiteral: '一、函证情况', source_ref: 'L0-1!C28' },
  { id: 'sample', display: '二、样本选择', sourceLiteral: '二、样本选择', source_ref: 'L0-1!J28' },
  {
    id: 'auditNote',
    display: '三、审计说明',
    sourceLiteral: '二、审计说明',
    source_ref: 'L0-1!S28',
    typoNote: '源模板此处字面为「二、审计说明」，与同页 C28「一、」/ J28「二、」/ C39「四、」冲突，'
      + '判定为源模板序号笔误，平台按「三、」展示（不改源 xlsx）',
  },
  { id: 'conclusion', display: '四、审计结论', sourceLiteral: '四、审计结论', source_ref: 'L0-1!C39' },
])

export const L0_SECTION_TITLE_BY_ID: Readonly<Record<string, L0SectionTitleDef>> = Object.freeze(
  Object.fromEntries(L0_SECTION_TITLES.map((s) => [s.id, s])),
)

// ─── 通用文本项定义 ─────────────────────────────────────────────────────────

export interface LowerZoneTextDef {
  /** 持久化键（`{L0_LOWER_KEY_PREFIX}-...`） */
  field: string
  /** 源模板逐字标签 */
  label: string
  /** 源模板示例文本 → 作 placeholder（**不预填**，否则会被当成审计师录入的内容） */
  placeholder: string
  /** 括注/提示（源模板的说明性文字，只读展示） */
  hint?: string
  /** 源锚点 */
  source_ref: string
  /** 该项的文本是否由源模板多格拼成（登记合并来源，供守卫核对） */
  mergedFrom?: string[]
}

// ─── 二、样本选择（源 J29~J35，6 项） ──────────────────────────────────────

export const L0_SAMPLE_SELECTION_DEFS: readonly LowerZoneTextDef[] = Object.freeze([
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-1`,
    label: '测试总体',
    placeholder: '如长期应付款账面余额XX、债权人XX个；应付债券账面余额XX、债权人XX个；……',
    source_ref: 'L0-1!J29',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-2`,
    label: '特定样本',
    placeholder: '长期应付款XX金额以上（大额）……、关联方/关联交易形成的款项、XX异常款项全部测试，共XX个供应商；',
    source_ref: 'L0-1!J30',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-3`,
    label: '抽样总体',
    placeholder: '测试总体扣除特定样本以外的样本，长期应付款共XX个供应商、金额XX，应付债券共XX债券、金额XX，……；',
    source_ref: 'L0-1!J31',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-4`,
    label: '确定的抽样样本量',
    placeholder: '长期应付款、应付债券……分别抽取XX个、XX个、XX个供应商；',
    // 🔴 K33 是 J32 的括注（J33 无标签）→ 提示文本，不是独立录入项
    hint: '（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）',
    source_ref: 'L0-1!J32',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-5`,
    label: '抽样方法',
    placeholder: '随机选样/系统选样/货币单元抽样/随意选样',
    source_ref: 'L0-1!J34',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-sample-6`,
    label: '抽样过程',
    // 🔴 K35 + K36 合并（K35 以逗号结尾 = 续行标志），只取 K35 会出现半句话
    placeholder: '使用IDEA（XX抽样工具）选取样本进行函证，长期应付款选择XX个供应商、金额XX的样本，'
      + '抽样工具中的样本选择过程和结果见<XX>底稿',
    source_ref: 'L0-1!J35',
    mergedFrom: ['L0-1!K35', 'L0-1!K36'],
  },
])

// ─── 三、审计说明（源 S29 / W29 / S33 / S34 / S36，5 段） ──────────────────

export const L0_AUDIT_NOTE_DEFS: readonly LowerZoneTextDef[] = Object.freeze([
  {
    field: `${L0_LOWER_KEY_PREFIX}-audit-note-1`,
    label: '1、对询证函保持的控制的说明',
    placeholder: '说明询证函的设计、寄发、回收全过程由项目组直接控制的情况（含防伪标识、寄送方式、回函接收方式）。',
    source_ref: 'L0-1!S29',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-audit-note-2`,
    label: '2、对误差的分析',
    placeholder: '分析回函不符事项的性质、金额与成因，并说明是否构成错报。',
    // 🔴 W30 + W31 合并（前格以「［」开、后格才有「］」），只取 W30 会缺右方括号
    hint: '界定误差构成条件：［不符事项的金额高于或低于账户余额人民币（）万元，'
      + '并且被审计单位不能合理解释其差异并提供相应依据］',
    source_ref: 'L0-1!W29',
    mergedFrom: ['L0-1!W30', 'L0-1!W31'],
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-audit-note-3`,
    label: '3、对以传真或电子邮件形式收到的回函的可靠性的考虑（L0-6）',
    placeholder: '说明对电子形式回函执行的可靠性验证（发件人身份、邮箱域名、致电确认），详见 L0-6。',
    source_ref: 'L0-1!S33',
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-audit-note-4`,
    label: '4、针对不符事项的程序',
    placeholder: '说明对不符事项执行的追查程序、取得的证据与结论。',
    // 🔴 S34 + S35 合并（S35 是 S34 的补充说明）
    hint: '如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序',
    source_ref: 'L0-1!S34',
    mergedFrom: ['L0-1!S34', 'L0-1!S35'],
  },
  {
    field: `${L0_LOWER_KEY_PREFIX}-audit-note-5`,
    label: '5、针对未回函的替代程序',
    placeholder: '说明对未回函项目执行的替代程序（详见 L0-5）及其结论。',
    source_ref: 'L0-1!S36',
  },
])

// ─── 四、审计结论（源 C39；参考结论 A65:B68 只读） ─────────────────────────

export const L0_CONCLUSION_FIELD = `${L0_LOWER_KEY_PREFIX}-conclusion`

export interface L0ReferenceConclusion {
  /** 源模板选项字母（A/B/C） */
  code: string
  text: string
  source_ref: string
}

/** 源 `A66:B68` 三条参考结论（**只读**展示，供审计师参照撰写） */
export const L0_REFERENCE_CONCLUSIONS: readonly L0ReferenceConclusion[] = Object.freeze([
  { code: 'A', text: '未见异常。', source_ref: 'L0-1!B66' },
  { code: 'B', text: '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。', source_ref: 'L0-1!B67' },
  {
    code: 'C',
    text: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
    source_ref: 'L0-1!B68',
  },
])

/** 源 `A65` 参考结论区标题 */
export const L0_REFERENCE_CONCLUSION_TITLE = '参考结论：'

/** 源 `A69` 后附审计证据说明（只读） */
export const L0_ATTACHED_EVIDENCE_NOTE = '后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。'

// ─── 键集（供守卫与持久化层） ───────────────────────────────────────────────

/** 下区全部持久化键（矩阵手工覆盖键不在此列，见 `l0MatrixDataSources`） */
export const L0_LOWER_ZONE_FIELDS: readonly string[] = Object.freeze([
  ...L0_SAMPLE_SELECTION_DEFS.map((d) => d.field),
  ...L0_AUDIT_NOTE_DEFS.map((d) => d.field),
  L0_CONCLUSION_FIELD,
])
