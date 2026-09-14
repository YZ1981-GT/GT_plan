/**
 * h0SummaryLowerZone.ts — H0-1 下区四块固定文字**单一真源**
 *
 * 源模板：`函证结果汇总表H0-1` R28~R37（四块） + R42~R69（编制说明/参考结论）
 * 逐格 openpyxl `data_only=False` 直读实证（2026-08-04）。
 *
 * 四块：
 *   一、函证情况（矩阵，内容由 `h0SummaryMatrix` 提供）   锚点 C28
 *   二、样本选择（6 字段）                                锚点 J28
 *   三、审计说明（5 小节）                                锚点 S28
 *   四、审计结论                                          锚点 C39
 *
 * 设计约束（对齐 `e0SummaryLowerZone.ts` 范式）：
 * - 跨格拆句必须合并渲染（`W30+W31`、`K32+K33`、`K35+K36+K37`），
 *   否则界面出现半句话
 * - 🔴 源模板 `S28` 的编号是「二、审计说明」（**笔误**，前一块 J28 已是「二、样本选择」，
 *   本块应为「三」）→ `title` 用修正后的「三、审计说明」，`sourceText` 保留原文
 *   供守卫按原文断言（防被「顺手修正」后三向比对打红）
 * - 🔴 `K35/K36` 的示例文字里写的是「预付账款/应付票据」—— 这是 F0 模板被复制到
 *   H0 时**残留的措辞**（源模板事实），逐字保留不改写
 *
 * spec: .kiro/specs/h0-confirmation-source-fidelity-and-linkage/
 *       Requirements 2.6~2.10；Property 7
 */

// ─── 类型 ────────────────────────────────────────────────────────────────────

export type H0LowerBlock = 'sample_selection' | 'audit_note' | 'conclusion' | 'guidance'

export interface H0LowerZoneText {
  block: H0LowerBlock
  key: string
  /** 逐字源模板文字；跨格拆句的已在此合并 */
  text: string
  /** 源模板锚点，多格合并用 '+' 连接 */
  anchor: string
  /** true = 只读方法论上下文；false = 该段下方有录入位置 */
  readonly: boolean
}

export interface H0SampleField {
  key: string
  /** 字段标签（逐字源模板，去尾冒号） */
  label: string
  anchor: string
  /** 源模板示例文字，作 placeholder（跨格已合并） */
  placeholder: string
  placeholderAnchor: string
}

export interface H0AuditNoteSection {
  key: string
  /** 小节标题（逐字源模板，含「1、」序号） */
  title: string
  anchor: string
  /** 只读提示（源模板挂在该小节下的说明文字，跨格已合并；无则 undefined） */
  hint?: string
  hintAnchor?: string
  /** AI 辅助的 section id（后端 `_SECTION_PROMPTS` 须有对应条目） */
  aiSection: string
}

// ─── 四块锚点与标题 ──────────────────────────────────────────────────────────

export const H0_LOWER_ZONE_BLOCKS = {
  matrix: { anchor: 'C28', title: '一、函证情况' },
  sample_selection: { anchor: 'J28', title: '二、样本选择' },
  /**
   * 🔴 源模板 `S28` 原文是「二、审计说明」（与 J28 的「二、样本选择」撞号），
   * 属源模板编号笔误 → UI 显示「三、审计说明」，`sourceText` 保留原文。
   */
  audit_note: { anchor: 'S28', title: '三、审计说明', sourceText: '二、审计说明' },
  conclusion: { anchor: 'C39', title: '四、审计结论' },
} as const

// ─── 二、样本选择（6 字段，标签逐字 J29/J30/J31/J32/J34/J35） ─────────────────

export const H0_SAMPLE_SELECTION_FIELDS: readonly H0SampleField[] = [
  {
    key: 'population',
    label: '测试总体',
    anchor: 'J29',
    placeholder: '如固定资产账面余额XX、供应商XX个；工程物资账面余额XX、供应商XX个；……',
    placeholderAnchor: 'K29',
  },
  {
    key: 'specific_sample',
    label: '特定样本',
    anchor: 'J30',
    placeholder: '固定资产XX金额以上（大额）……、关联方/关联交易形成的款项、XX异常款项全部测试，共XX个供应商；',
    placeholderAnchor: 'K30',
  },
  {
    key: 'sampling_population',
    label: '抽样总体',
    anchor: 'J31',
    placeholder: '测试总体扣除特定样本以外的样本，固定资产共XX个供应商、金额XX，工程物资共XX供应商、金额XX，……；',
    placeholderAnchor: 'K31',
  },
  {
    key: 'sample_size',
    label: '确定的抽样样本量',
    anchor: 'J32',
    // K32 + K33 合并（一句话被源模板拆成两格）
    placeholder: '固定资产、工程物资、……分别抽取XX个、XX个、XX个供应商；（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）',
    placeholderAnchor: 'K32+K33',
  },
  {
    key: 'sampling_method',
    label: '抽样方法',
    anchor: 'J34',
    placeholder: '随机选样/系统选样/货币单元抽样/随意选样',
    placeholderAnchor: 'K34',
  },
  {
    key: 'sampling_process',
    label: '抽样过程',
    anchor: 'J35',
    // K35 + K36 + K37 合并（一句话被源模板拆成三格）
    // 🔴「预付账款/应付票据」是 F0 模板复制到 H0 的残留措辞，源模板事实，逐字保留
    placeholder: '使用IDEA（XX抽样工具）选取样本进行函证，预付账款选择XX个供应商、金额XX的样本，应付票据选择XX个供应商、金额XX的样本，……抽样工具中的样本选择过程和结果见<XX>底稿',
    placeholderAnchor: 'K35+K36+K37',
  },
]

// ─── 三、审计说明（5 小节，标题逐字 S29/W29/S33/S34/S37） ─────────────────────

export const H0_AUDIT_NOTE_SECTIONS: readonly H0AuditNoteSection[] = [
  {
    key: 'control',
    title: '1、对询证函保持的控制的说明',
    anchor: 'S29',
    aiSection: 'summary-control',
  },
  {
    key: 'error_analysis',
    title: '2、对误差的分析',
    anchor: 'W29',
    // W30 + W31 合并（误差构成条件被源模板拆成两格）
    hint: '界定误差构成条件：［不符事项的金额高于或低于账户余额人民币（）万元，并且被审计单位不能合理解释其差异并提供相应依据］',
    hintAnchor: 'W30+W31',
    aiSection: 'summary-error-analysis',
  },
  {
    key: 'reliability',
    title: '3、对以传真或电子邮件形式收到的回函的可靠性的考虑（H0-6）',
    anchor: 'S33',
    aiSection: 'summary-reliability',
  },
  {
    key: 'mismatch',
    title: '4、针对不符事项的程序',
    anchor: 'S34',
    hint: '如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序',
    hintAnchor: 'S35',
    aiSection: 'summary-mismatch',
  },
  {
    key: 'alternative',
    title: '5、针对未回函的替代程序',
    anchor: 'S37',
    aiSection: 'summary-alternative',
  },
]

// ─── 四、审计结论 参考结论（逐字 A66:B68，只读方法论上下文） ───────────────────

export const H0_REFERENCE_CONCLUSIONS: readonly { code: string; text: string; anchor: string }[] = [
  { code: 'A', text: '未见异常。', anchor: 'A66+B66' },
  { code: 'B', text: '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。', anchor: 'A67+B67' },
  { code: 'C', text: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。', anchor: 'A68+B68' },
]

// ─── 只读方法论上下文（编制说明 / 提示，逐字源模板） ──────────────────────────

export const H0_LOWER_ZONE_TEXTS: readonly H0LowerZoneText[] = [
  // ── 传真/电子邮件回函提示（A42） ──
  {
    block: 'guidance',
    key: 'fax_email_hint',
    text: '如果被询证者以传真、电子邮件等方式回函，审计项目组应当直接接收，并验证传真、电子邮件回函的可靠性，要求被询证者在审计报告日之前寄回询证函原件',
    anchor: 'A42',
    readonly: true,
  },
  // ── 编制说明 1：函证样本的选择（A45~A53，准则 1312 第十条六项） ──
  {
    block: 'guidance',
    key: 'sample_selection_standard',
    text:
      '1、函证样本的选择：\n'
      + '《中国注册会计师审计准则第1312号——函证》第十条注册会计师采用审计抽样或其他选取测试项目的方法\n'
      + '选择函证样本时，样本应当足以代表总体，并包括：\n'
      + '（一）金额较大的项目；\n'
      + '\u3000\u3000（二）账龄较长的项目；\n'
      + '\u3000\u3000（三）交易频繁但期末余额较小的项目；\n'
      + '\u3000\u3000（四）重大关联方交易；\n'
      + '\u3000\u3000（五）重大或异常的交易；\n'
      + '\u3000\u3000（六）可能存在争议以及产生重大舞弊或错误的交易。',
    anchor: 'A45+A46+A47+A48+A49+A50+A51+A52+A53',
    readonly: true,
  },
  // ── 编制说明 2：函证注意事项（A54 + B55~B62 八条） ──
  {
    block: 'guidance',
    key: 'confirmation_cautions',
    text:
      '2、函证注意事项：\n'
      + '①严格控制发函过程（亲自发函；直接回函）；\n'
      + '②传真件、电子邮件回函可以作为证据，但可靠性低于原件且需严格控制并记录函证过程；\n'
      + '③同一客户的多项往来在同一张询证函列示；\n'
      + '④关联往来核对一致；\n'
      + '⑤收信人尽量写清楚；\n'
      + '⑥收到回函编制函证控制表（函证结果汇总表），保留回函信封，注明选样标准；\n'
      + '⑦回函有差异须进一步核对原因；\n'
      + '⑧未回函的全部执行替代程序。',
    anchor: 'A54+B55+B56+B57+B58+B59+B60+B61+B62',
    readonly: true,
  },
  // ── 编制说明 3：概述（A63+A64） ──
  {
    block: 'guidance',
    key: 'overview_note',
    text:
      '3、概述：（1）程序的测试情况、结果；\n'
      + '（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。',
    anchor: 'A63+A64',
    readonly: true,
  },
  // ── 后附审计证据（A69） ──
  {
    block: 'guidance',
    key: 'attached_evidence',
    text: '后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。',
    anchor: 'A69',
    readonly: true,
  },
]

// ─── 持久化 key ──────────────────────────────────────────────────────────────

export const H0_SAMPLE_KEY_PREFIX = 'H0-1-lower-sample-'
export const H0_AUDIT_NOTE_KEY_PREFIX = 'H0-1-lower-audit-note-'
export const H0_CONCLUSION_KEY = 'H0-1-lower-conclusion'

export function h0SampleItemId(fieldKey: string): string {
  return `${H0_SAMPLE_KEY_PREFIX}${fieldKey}`
}

export function h0AuditNoteItemId(sectionKey: string): string {
  return `${H0_AUDIT_NOTE_KEY_PREFIX}${sectionKey}`
}

// ─── 便捷取值 ────────────────────────────────────────────────────────────────

export function getH0TextsForBlock(block: H0LowerBlock): readonly H0LowerZoneText[] {
  return H0_LOWER_ZONE_TEXTS.filter((t) => t.block === block)
}

/** 全部 AI section id（供守卫比对后端 `_SECTION_PROMPTS` 登记情况） */
export const H0_AI_SECTIONS: readonly string[] = H0_AUDIT_NOTE_SECTIONS.map((s) => s.aiSection)
