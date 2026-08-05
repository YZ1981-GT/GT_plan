/**
 * k0LowerZoneSpec.ts — K0-1 下区四块固定文字**单一真源**
 *
 * spec: k0-confirmation-source-alignment · Task 5
 *   Requirement 3.1 / 3.6~3.12 / 6.1 / 6.2
 *
 * ─── 源模板事实（openpyxl `data_only=False` 直读；后端 `test_k0_source_template_facts.py`
 *     已逐格固化，本文件的每条文字都能在那里找到对应断言）────────────────────────
 * `函证结果汇总表K0-1` 下区四块锚点：
 *   `C27 一、函证情况`（矩阵 → `k0MatrixSpec` / `k0SummaryMatrix`）
 *   `I27 二、样本选择`（6 项可录入 —— **本模块只导出文字真源，不渲染**，见下方分工）
 *   `S27 三、审计说明`（5 项 = 小标题 + 可选只读提示语）
 *   `C38 四、审计结论`（+ `A63 参考结论：`，内容在 **B 列** `B64:B66`）
 *   `A40` 传真/电邮回函提示 · `A42~A67` 编制说明（注意事项 8 条在 **`B53:B60`**）
 *
 * 🔴 三处「不能凭常识实现」的源模板事实：
 * 1. **6 项样本选择不是连续 6 行** —— `I32` 为空、`J32` 承载样本计算器提示语；
 *    标签在 `I28/I29/I30/I31/I33/I34`。
 * 2. **`role` 必须区分 `title` / `hint`** —— 小标题永远单格；提示语才可能跨格。
 *    全下区**唯一需要拼接的**是第 2 项的 hint（`X29`+`X30`），
 *    第 3 项的 `S33` 是**独立** hint，与标题 `S32` 拼接会产出错句。
 *    「抽样过程」的 placeholder 同样由 `J34`+`J35` 两格拼成（J34 以逗号结尾 = 半句话）。
 * 3. **参考结论内容在 B 列**（`B64`/`B65`/`B66`），A 列只是 `A、`/`B、`/`C、` 标签；
 *    **注意事项 8 条在 B 列**（`B53:B60`），只扫 A 列会整段漏掉。
 *
 * ─── 🔴🔴 与「二、样本选择」的分工（防双真源）──────────────────────────────────
 * `GtConfirmationSummary.vue` **已有** `<ConfirmationSampling :data="data.sampling">`，
 * 其持久化就是 `SamplingData` JSON。故（与 G0 同款分工）：
 *   · `K0SummaryLowerZone.vue`（Wave 3）渲染 **一、函证情况 · 三、审计说明 · 四、审计结论 · 编制说明**
 *   · **二、样本选择由 `ConfirmationSampling.vue`（`isK0` → 6 项）承担**
 * 本模块的 `K0_SAMPLE_SELECTION` **只导出给该组件消费**，下区组件里一个抽样字段都不录入
 * —— 同一份 `SamplingData` 有两处录入口就会撞上「同一 item_id 被两套口径同写 = 双真源静默漂移」。
 *
 * ─── 与 E0/H0/G0 三份下区副本的关系（裁决门 D = D-2）────────────────────────────
 * 各自实现后收敛：`e0SummaryLowerZone` / `h0SummaryLowerZone` / `g0SummaryLowerZone`
 * **一行不改**。差异登记：
 *
 * | 维度         | E0                   | H0                  | G0                  | K0（本模块）          |
 * |--------------|----------------------|---------------------|---------------------|-----------------------|
 * | 二、样本选择 | 3 段**只读**准则文字 | 6 项可录入（组件内） | 6 项可录入（外部）  | 6 项可录入（外部）    |
 * | 块锚点       | 各自不同             | `C28/J28/S28/C39`   | `C19/J19/S19/C30`   | `C27/I27/S27/C38`     |
 * | 审计说明序号 | 段落式               | `N、`               | `N、`               | **`N.`**（半角句点）  |
 * | 参考结论     | —                    | `A66+B66` 拼接      | 取 B 列             | 取 B 列（`B64:B66`）  |
 * | 注意事项     | —                    | `B55:B62`           | `B44:B51`           | `B53:B60`             |
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

import { K0_SOURCE_REF_PREFIX } from './k0MatrixSpec'

/** 收敛锚点（裁决门 D = D-2）—— 下区类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'

const ref = (anchor: string) => `${K0_SOURCE_REF_PREFIX}${anchor}`

// ─── 四块 ────────────────────────────────────────────────────────────────────

export type K0LowerBlock = 'matrix' | 'sample_selection' | 'audit_note' | 'conclusion'

export interface K0LowerBlockDef {
  key: K0LowerBlock
  anchor: string
  /** 逐字源模板标题 */
  title: string
  sourceRef: string
  /** 本块是否由 `K0SummaryLowerZone.vue` 渲染（`sample_selection` 归 `ConfirmationSampling`） */
  renderedHere: boolean
}

export const K0_LOWER_ZONE_BLOCKS: readonly K0LowerBlockDef[] = Object.freeze([
  Object.freeze({ key: 'matrix', anchor: 'C27', title: '一、函证情况', sourceRef: ref('C27'), renderedHere: true }),
  // 🔴 renderedHere:false —— 由 `ConfirmationSampling.vue`（isK0 → 6 项）渲染，防双真源
  Object.freeze({ key: 'sample_selection', anchor: 'I27', title: '二、样本选择', sourceRef: ref('I27'), renderedHere: false }),
  Object.freeze({ key: 'audit_note', anchor: 'S27', title: '三、审计说明', sourceRef: ref('S27'), renderedHere: true }),
  Object.freeze({ key: 'conclusion', anchor: 'C38', title: '四、审计结论', sourceRef: ref('C38'), renderedHere: true }),
]) as readonly K0LowerBlockDef[]

export function getK0LowerBlock(key: K0LowerBlock): K0LowerBlockDef {
  const b = K0_LOWER_ZONE_BLOCKS.find((x) => x.key === key)
  if (!b) throw new Error(`[k0LowerZoneSpec] 未声明的块: ${key}`)
  return b
}

// ─── 二、样本选择（6 项；字段复用既有抽样字段族，不新造） ─────────────────────

/**
 * 6 项的持久化字段名。
 *
 * 🔴 全部取自**既有**字段族，不新造第二套名字（Requirement 3.6）：
 * - 5 个与替代程序族 `SamplingConfig`（`alternativeD05Types.ts`）**同名同源**；
 * - `test_population` 是 `SamplingData` 上的 additive 槽（由 G0 spec 为「二、样本选择」
 *   第一项建好），其替代程序族对位是 `SamplingConfig.test_scope`。
 *   K0 侧沿用 `test_population` 而**不新增 `test_scope` 到 `SamplingData`** ——
 *   同一个槽两个字段就是「新造第二套字段名」，正是本约束要防的事。
 */
export type K0SampleField =
  | 'test_population'
  | 'specific_samples'
  | 'sampling_population'
  | 'sample_size'
  | 'sampling_method'
  | 'sampling_process'

export interface K0SampleSelectionItem {
  /** `SamplingData` 字段名（既有字段族，不新造） */
  key: K0SampleField
  /** 标签（逐字源模板 I 列，**含**行尾冒号会被去掉 → 这里存去冒号后的） */
  label: string
  labelAnchor: string
  /** placeholder（逐字源模板 J 列示例文字；跨格时为拼接结果） */
  placeholder: string
  placeholderAnchor: string
  sourceRef: string
  /** 点选型选项（源模板 `J33` 本就是斜杠分隔的备选项 → 交互点选优先） */
  options?: readonly string[]
  /** 替代程序族 `SamplingConfig` 的对位字段（守卫据此交叉锁死；`test_population` 例外） */
  legacyFamilyField: string
}

export const K0_SAMPLE_SELECTION: readonly K0SampleSelectionItem[] = Object.freeze([
  Object.freeze({
    key: 'test_population',
    label: '测试范围',
    labelAnchor: 'I28',
    placeholder: '如其他应收款账面余额XX、债务人XX个；其他应付款账面余额XX、债权人XX个；……',
    placeholderAnchor: 'J28',
    sourceRef: ref('I28'),
    legacyFamilyField: 'test_scope',
  }),
  Object.freeze({
    key: 'specific_samples',
    label: '特定样本',
    labelAnchor: 'I29',
    placeholder: '其他应收款XX金额以上（大额）……、关联方/关联交易形成的款项、XX异常款项全部测试，共XX个债务人；',
    placeholderAnchor: 'J29',
    sourceRef: ref('I29'),
    legacyFamilyField: 'specific_samples',
  }),
  Object.freeze({
    key: 'sampling_population',
    label: '抽样总体',
    labelAnchor: 'I30',
    placeholder: '测试总体扣除特定样本以外的样本，其他应收款共XX个债务人、金额XX，其他应付款共XX个债权人、金额XX，……；',
    placeholderAnchor: 'J30',
    sourceRef: ref('I30'),
    legacyFamilyField: 'sampling_population',
  }),
  Object.freeze({
    key: 'sample_size',
    label: '确定的抽样样本量',
    labelAnchor: 'I31',
    placeholder: '其他应收款、其他应付款分别抽取XX个、XX个单位；',
    placeholderAnchor: 'J31',
    sourceRef: ref('I31'),
    legacyFamilyField: 'sample_size',
  }),
  Object.freeze({
    key: 'sampling_method',
    label: '抽样方法',
    labelAnchor: 'I33',
    placeholder: '随机选样/系统选样/货币单元抽样/随意选样',
    placeholderAnchor: 'J33',
    sourceRef: ref('I33'),
    options: Object.freeze(['随机选样', '系统选样', '货币单元抽样', '随意选样']),
    legacyFamilyField: 'sampling_method',
  }),
  Object.freeze({
    key: 'sampling_process',
    label: '抽样过程',
    labelAnchor: 'I34',
    // 🔴 源模板把示例拆成 J34+J35 两格（J34 以逗号结尾 = 半句话）→ 拼接后才完整
    placeholder:
      '使用IDEA（XX抽样工具）选取样本进行函证，其他应收款选择XX个债务人、金额XX的样本，' +
      '其他应付款选择XX个债权人、金额XX的样本，……',
    placeholderAnchor: 'J34+J35',
    sourceRef: ref('I34'),
    legacyFamilyField: 'sampling_process',
  }),
]) as readonly K0SampleSelectionItem[]

/** 6 项之外的只读提示语（源模板 J 列，随对应项就地展示，不是录入项） */
export interface K0SampleHint {
  key: K0SampleField
  text: string
  anchor: string
  sourceRef: string
}

export const K0_SAMPLE_SELECTION_HINTS: readonly K0SampleHint[] = Object.freeze([
  Object.freeze({
    key: 'sample_size',
    text: '（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）',
    anchor: 'J32',
    sourceRef: ref('J32'),
  }),
  Object.freeze({
    key: 'sampling_process',
    text: '抽样工具中的样本选择过程和结果见<XX>底稿',
    anchor: 'J36',
    sourceRef: ref('J36'),
  }),
]) as readonly K0SampleHint[]

// ─── 三、审计说明（5 项） ────────────────────────────────────────────────────

export interface K0AuditNoteItem {
  /** 序号（1..5）—— 持久化键与复核 section-id 都用它 */
  seq: 1 | 2 | 3 | 4 | 5
  /** 持久化键（落 `k0_audit_notes`；`aliasOf` 非空的项不落此处） */
  key: string
  /** 小标题（逐字源模板，含 `N.` 半角句点序号 —— 与 G0/H0 的 `N、` 不同，勿统一） */
  label: string
  labelAnchor: string
  sourceRef: string
  /**
   * 非空时表示**只读引用**既有共享字段（不重复录入，Requirement 3.8）。
   * 目标必须存在于 `NotesData`。
   */
  aliasOf?: keyof {
    note_general: string
    note_exception: string
    note_unreplied: string
    note_alternative: string
    note_other: string
  }
  /** 只读提示语（源模板独立格；**不与标题拼接**，否则出错句） */
  inlineHint?: string
  inlineHintAnchor?: string
  /** AI 生成的 section id（Wave 3 在后端登记） */
  aiSection: string
  /** 复核 section-id（`GtReviewTrigger`） */
  reviewSectionId: string
}

export const K0_AUDIT_NOTES: readonly K0AuditNoteItem[] = Object.freeze([
  Object.freeze({
    seq: 1,
    key: 'control',
    label: '1.对询证函保持的控制的说明',
    labelAnchor: 'S28',
    sourceRef: ref('S28'),
    aiSection: 'k0-summary-control',
    reviewSectionId: 'K0-1-audit-note-1',
  }),
  Object.freeze({
    seq: 2,
    key: 'error_analysis',
    label: '2.对误差的分析',
    labelAnchor: 'X28',
    sourceRef: ref('X28'),
    // 🔴 全下区唯一需要拼接的 hint（X29 + X30 是被源模板拆成两格的一句话）
    inlineHint:
      '界定误差构成条件：［不符事项的金额高于或低于账户余额人民币' +
      '（）万元，并且被审计单位不能合理解释其差异并提供相应依据］',
    inlineHintAnchor: 'X29+X30',
    aiSection: 'k0-summary-error-analysis',
    reviewSectionId: 'K0-1-audit-note-2',
  }),
  Object.freeze({
    seq: 3,
    key: 'reliability',
    // 🔴 源模板写「（K0-6）」而回函可靠性验证表实为 K0-7（K0-6 是其他应付款替代程序）。
    //    索引号笔误的处置见 `K0_INDEX_TYPO_MAP` → 此处**逐字保留原文**，
    //    否则守卫的三向比对会因「顺手修正」而打红。
    label: '3.对以传真或电子邮件形式收到的回函的可靠性的考虑（K0-6）',
    labelAnchor: 'S32',
    sourceRef: ref('S32'),
    // `S33` 是**独立** hint（与标题拼接会得到「…的考虑（K0-6）如果回函中存在…」错句）
    inlineHint: '如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序',
    inlineHintAnchor: 'S33',
    aiSection: 'k0-summary-reliability',
    reviewSectionId: 'K0-1-audit-note-3',
  }),
  Object.freeze({
    seq: 4,
    key: 'mismatch',
    label: '4.针对不符事项的程序',
    labelAnchor: 'X32',
    sourceRef: ref('X32'),
    aiSection: 'k0-summary-mismatch',
    reviewSectionId: 'K0-1-audit-note-4',
  }),
  Object.freeze({
    seq: 5,
    key: 'unreplied_alternative',
    label: '5.针对未回函的替代程序',
    labelAnchor: 'S36',
    sourceRef: ref('S36'),
    // ✅ 唯一能明确对应既有共享字段的项 → 只读引用，不重复录入（R3.8）
    aliasOf: 'note_alternative',
    aiSection: 'k0-summary-unreplied-alternative',
    reviewSectionId: 'K0-1-audit-note-5',
  }),
]) as readonly K0AuditNoteItem[]

// ─── 四、审计结论（参考结论 A/B/C，内容在 B 列） ──────────────────────────────

export interface K0RefConclusion {
  code: 'A' | 'B' | 'C'
  /** 逐字取自 **B 列** */
  text: string
  /** 内容锚点（B 列） */
  anchor: string
  /** 标签锚点（A 列，仅供守卫核对「A 列确实只是标签」） */
  labelAnchor: string
  sourceRef: string
}

export const K0_REFERENCE_CONCLUSIONS: readonly K0RefConclusion[] = Object.freeze([
  Object.freeze({ code: 'A', text: '未见异常。', anchor: 'B64', labelAnchor: 'A64', sourceRef: ref('B64') }),
  Object.freeze({
    code: 'B',
    text: '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    anchor: 'B65',
    labelAnchor: 'A65',
    sourceRef: ref('B65'),
  }),
  Object.freeze({
    code: 'C',
    text: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
    anchor: 'B66',
    labelAnchor: 'A66',
    sourceRef: ref('B66'),
  }),
]) as readonly K0RefConclusion[]

// ─── 编制说明（只读方法论上下文，折叠置底） ──────────────────────────────────

export interface K0GuidanceBlock {
  key: string
  /** 分组标题（逐字源模板；无独立格时自拟并在 sourceRef 标 `-`） */
  heading: string
  headingAnchor: string
  /** 逐行文字 ↔ 源锚点一一对应（守卫按对逐格断言，不解析 '+'） */
  lines: readonly { text: string; anchor: string }[]
}

export const K0_GUIDANCE_BLOCKS: readonly K0GuidanceBlock[] = Object.freeze([
  Object.freeze({
    key: 'fax_email_reply',
    heading: '传真 / 电子邮件回函',
    headingAnchor: '-',
    lines: Object.freeze([
      {
        text:
          '提示：如果被询证者以传真、电子邮件等方式回函，审计项目组应当直接接收，' +
          '并验证传真、电子邮件回函的可靠性，要求被询证者在审计报告日之前寄回询证函原件',
        anchor: 'A40',
      },
    ]),
  }),
  Object.freeze({
    key: 'sample_selection_standard',
    heading: '1、函证样本的选择：',
    headingAnchor: 'A43',
    lines: Object.freeze([
      { text: '《中国注册会计师审计准则第1312号——函证》第十条注册会计师采用审计抽样或其他选取测试项目的方法', anchor: 'A44' },
      { text: '选择函证样本时，样本应当足以代表总体，并包括：', anchor: 'A45' },
      { text: '（一）金额较大的项目；', anchor: 'A46' },
      { text: '（二）账龄较长的项目；', anchor: 'A47' },
      { text: '（三）交易频繁但期末余额较小的项目；', anchor: 'A48' },
      { text: '（四）重大关联方交易；', anchor: 'A49' },
      { text: '（五）重大或异常的交易；', anchor: 'A50' },
      { text: '（六）可能存在争议以及产生重大舞弊或错误的交易。', anchor: 'A51' },
    ]),
  }),
  Object.freeze({
    key: 'confirmation_tips',
    heading: '2、函证注意事项：',
    headingAnchor: 'A52',
    // 🔴 8 条在 **B 列**（B53:B60），只扫 A 列会整段漏掉
    lines: Object.freeze([
      { text: '①严格控制发函过程（亲自发函；直接回函）；', anchor: 'B53' },
      { text: '②传真件、电子邮件回函可以作为证据，但可靠性低于原件且需严格控制并记录函证过程；', anchor: 'B54' },
      { text: '③同一客户的多项往来在同一张询证函列示；', anchor: 'B55' },
      { text: '④关联往来核对一致；', anchor: 'B56' },
      { text: '⑤收信人尽量写清楚；', anchor: 'B57' },
      { text: '⑥收到回函编制函证控制表（函证结果汇总表），保留回函信封，注明选样标准；', anchor: 'B58' },
      { text: '⑦回函有差异须进一步核对原因；', anchor: 'B59' },
      { text: '⑧未回函的全部执行替代程序。', anchor: 'B60' },
    ]),
  }),
  Object.freeze({
    key: 'overview_and_evidence',
    heading: '3、概述：',
    headingAnchor: 'A61',
    lines: Object.freeze([
      { text: '3、概述：（1）程序的测试情况、结果；', anchor: 'A61' },
      { text: '（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。', anchor: 'A62' },
      { text: '后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。', anchor: 'A67' },
    ]),
  }),
]) as readonly K0GuidanceBlock[]

// ─── 源模板索引号笔误（按意图实现 + tooltip 标原值；绝不改源 xlsx） ──────────

export interface K0IndexTypo {
  /** 源出处（含 sheet 名，与后端 `SOURCE_TEMPLATE_TYPOS` 的第一列逐字一致） */
  sourceRef: string
  /** 源模板字面（**逐字保留**，用于 tooltip 呈现原值） */
  literal: string
  /** 意图目标底稿索引号（跳转用） */
  intended: 'K0-3' | 'K0-4' | 'K0-7'
  /** 判据说明（tooltip 第二行） */
  note: string
}

export const K0_INDEX_TYPO_MAP: readonly K0IndexTypo[] = Object.freeze([
  Object.freeze({
    sourceRef: '函证结果汇总表K0-1!V6',
    literal: '调节索引（K1-12）',
    intended: 'K0-4',
    note: '源模板索引号笔误：函证差异调节表实为 K0-4；K1-12 是 K1 循环底稿，与 K0 无关',
  }),
  Object.freeze({
    sourceRef: '函证结果汇总表K0-1!S32',
    literal: '3.对以传真或电子邮件形式收到的回函的可靠性的考虑（K0-6）',
    intended: 'K0-7',
    note: '源模板索引号笔误：回函可靠性验证表实为 K0-7；K0-6 是其他应付款替代程序',
  }),
  Object.freeze({
    sourceRef: '核实被函证单位信息K0-2!AA6',
    literal: '跟函函证控制过程（K1-11）',
    intended: 'K0-3',
    note: '源模板索引号笔误：跟函函证过程控制实为 K0-3；K1-11 是 K1 循环底稿',
  }),
]) as readonly K0IndexTypo[]

/** 按源出处取笔误登记（供 UI tooltip） */
export function getK0IndexTypo(sourceRef: string): K0IndexTypo | undefined {
  return K0_INDEX_TYPO_MAP.find((t) => t.sourceRef === sourceRef)
}

// ─── 持久化键（Property 9：与既有键无交集） ──────────────────────────────────

/**
 * K0-1 下区新增的四个顶层键（存于
 * `working_paper.parsed_data.html_data['函证结果汇总表K0-1']`，与上区 `rows` 同一 payload）。
 *
 * 🔴 全部**可选**：旧 payload 读回为 `undefined`；写回时空值不产生键。
 * 既有 `rows`/`sampling`/`notes`/`conclusion`/`summary_config` 键**不动**
 * （`aliasOf` 项直接读写 `notes`）。
 */
export const K0_LOWER_ZONE_PAYLOAD_KEYS = Object.freeze([
  'k0_matrix_overrides',
  'k0_sample_selection',
  'k0_audit_notes',
  'k0_conclusion',
] as const)

/** 既有键（守卫断言与上面四键无交集） */
export const K0_EXISTING_PAYLOAD_KEYS = Object.freeze([
  'rows',
  'summary_config',
  'sampling',
  'notes',
  'conclusion',
] as const)
