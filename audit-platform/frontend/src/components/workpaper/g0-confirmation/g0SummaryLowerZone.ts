/**
 * g0SummaryLowerZone.ts — G0-1 下区四块固定文字**单一真源**
 *
 * spec: g0-confirmation-source-alignment，Task 8/9（Requirement 3.1 / 3.6~3.11 / 11.2）
 *
 * ─── 源模板事实（openpyxl `data_only=False` 直读，2026-08-04 二次交叉验证）──────
 * `函证结果汇总表G0-1` 下区四块锚点：
 *   `C19 一、函证情况`（矩阵，内容由 `g0SummaryMatrix` 提供）
 *   `J19 二、样本选择`（6 项可录入 —— **本模块只导出文字真源，不渲染**，见下方分工）
 *   `S19 三、审计说明`（5 项 = 小标题 + 可选只读提示语）
 *   `C30 四、审计结论`（+ `A54` 参考结论 A/B/C，内容在 **B 列**）
 *   `A33~A58` 编制说明（准则 1312 第十条六项 + 函证注意事项 8 条在 **`B44:B51`**）
 *
 * 🔴 三处推翻立项描述的实证（勿按旧记忆实现）：
 * 1. **审计说明 5 项不是「一句话拆两格」** —— `S25`（小标题「4、针对不符事项的程序」）
 *    与 `S26`（提示语「如果回函中存在未函证的其他信息…」）是两个独立角色，拼接会产出
 *    「4、针对不符事项的程序如果回函中存在未函证的其他信息…」的错句。`X20` 与 `X21+X22`
 *    同理。→ `LowerZoneTextDef.role` 区分 `title` / `hint`，**全下区唯一需要拼接的是
 *    `X21`+`X22`**（第 2 项的 hint）。
 * 2. **参考结论内容在 B 列**（`B55`/`B56`/`B57`），A 列只是 `A、`/`B、`/`C、` 标签。
 * 3. **函证注意事项 8 条在 `B44:B51`**（`A43` 只是标题）→ 只扫 A 列的探针会整段漏掉。
 *
 * 下区合并区实测**只有 `C20:D20` 一处** → 「跨格」全是「相邻格文字需拼接」而非 Excel
 * 合并区，禁用 `merged_cells` 推断跨格关系。
 *
 * ─── 🔴🔴 与 Task 13 的分工（防双真源）─────────────────────────────────────────
 * `GtConfirmationSummary.vue` **已有** `<ConfirmationSampling :data="data.sampling.value">`，
 * 其持久化就是 `G0-1-sampling`（`SamplingConfig` JSON）。故：
 *   · `G0SummaryLowerZone.vue` 渲染 **一、函证情况 · 三、审计说明 · 四、审计结论 · 编制说明**
 *   · **二、样本选择由 `ConfirmationSampling.vue`（`isG0` → 6 项）承担**
 * 本模块的 `G0_SAMPLE_SELECTION_DEFS` **只导出给 Task 13 消费**，组件侧一个字段都不录入
 * （守卫按源码断言组件内无 6 个 sampling 字段的 `v-model`）。同一份 `SamplingConfig`
 * 有两处录入口就会撞上「同一 item_id 被两套口径同写 = 双真源静默漂移」。
 *
 * ─── 与 `confirmation/h0SummaryLowerZone.ts` / `e0SummaryLowerZone.ts` 的关系 ──
 * 裁决门 D = **D-2 各自实现后收敛** → 本模块是独立副本，
 * `E0SummaryLowerZone.vue` / `e0SummaryLowerZone.ts` / `H0SummaryLowerZone.vue` /
 * `h0SummaryLowerZone.ts` **一行不改**。逐条登记同源关系与差异点：
 *
 * | 维度         | E0                        | H0                          | G0（本模块）                    |
 * |--------------|---------------------------|-----------------------------|---------------------------------|
 * | 二、样本选择 | 3 段**只读**准则文字      | 6 项可录入（组件内渲染）    | 6 项可录入（**Task 13 渲染**）  |
 * | 三、审计说明 | 段落式                    | 5 小节 + hint               | 5 小节 + hint（同 H0 结构）     |
 * | 参考结论     | —                         | `A66+B66` 拼接              | **取 B 列**（A 列只是标签）      |
 * | 注意事项 8 条| —                         | `B55:B62`                   | `B44:B51`                       |
 * | 块锚点       | 各自不同                  | `C28/J28/S28/C39`           | `C19/J19/S19/C30`               |
 * | 编号笔误     | —                         | `S28` 原文「二、审计说明」  | **无笔误**（`S19` 就是「三」）   |
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

/** 收敛锚点（裁决门 D = D-2）—— 下区类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'

/** 下区所在 sheet（源模板真实 tab 名，逐字） */
export const G0_LOWER_ZONE_SHEET = '函证结果汇总表G0-1'

/** `source_ref` 前缀（守卫断言 `source_ref === G0_SOURCE_REF_PREFIX + anchor`，防两字段漂移） */
export const G0_SOURCE_REF_PREFIX = 'G0-1!'

// ─── 类型 ────────────────────────────────────────────────────────────────────

export type G0LowerBlock = 'matrix' | 'sample_selection' | 'audit_note' | 'conclusion' | 'tips'

/**
 * 下区固定文字。
 *
 * 🔴 `role` 是本模块的核心设计：
 * - `title` = 小标题，**永远单格**，不参与任何拼接
 * - `hint`  = 只读提示语，**可能**由相邻多格拼接（全下区仅 `X21`+`X22` 一处）
 *
 * 把两者混为一谈就会拼出半句话或错句（见文件头实证 1）。
 */
export interface LowerZoneTextDef {
  block: G0LowerBlock
  key: string
  role: 'title' | 'hint'
  /** 逐字源模板文字；`role==='hint'` 且 anchor 含 '+' 时为多格拼接结果 */
  text: string
  /** 裸锚点（多格拼接用 '+' 连接，如 `X21+X22`） */
  anchor: string
  /** true = 只读方法论上下文；false = 该项下方有录入位置 */
  readonly: boolean
  /** 限定锚点（= `G0-1!` + anchor） */
  source_ref: string
}

/** 四块的锚点与标题 */
export interface LowerZoneBlockDef {
  key: G0LowerBlock
  anchor: string
  title: string
  source_ref: string
  /** 本块是否由 `G0SummaryLowerZone.vue` 渲染（`sample_selection` 归 Task 13） */
  renderedHere: boolean
}

/** 审计说明 5 项：小标题 + 可选只读提示语 */
export interface G0AuditNoteDef {
  /** 序号（1..5），持久化键与复核 section-id 都用它 */
  seq: 1 | 2 | 3 | 4 | 5
  key: string
  /** 小标题（逐字源模板，含「N、」序号） */
  title: string
  titleAnchor: string
  /** 只读提示语（无则 undefined） */
  hint?: string
  hintAnchor?: string
  /** AI 生成的 section id（Task 19 在后端 `wp_ai._SUPPORTED_SECTIONS` 登记） */
  aiSection: string
  /** 复核 section-id（`GtReviewTrigger`） */
  reviewSectionId: string
}

/** 参考结论 A/B/C（标签在 A 列、**内容在 B 列**） */
export interface G0RefConclusionDef {
  code: 'A' | 'B' | 'C'
  /** 逐字取自 B 列 */
  text: string
  /** 内容锚点（B 列） */
  anchor: string
  /** 标签锚点（A 列，仅供守卫核对「A 列确实只是标签」） */
  labelAnchor: string
  source_ref: string
}

/** 编制说明：逐行文字 ↔ 源锚点一一对应（守卫按对逐格断言，不解析 '+'） */
export interface G0PreparationNoteDef {
  key: string
  /** 分组标题（供 UI 分段，非源模板独立格时为 undefined） */
  heading?: string
  lines: readonly { text: string; anchor: string }[]
}

/** 样本选择 6 项（**只导出给 Task 13 的 `ConfirmationSampling.vue`**） */
export interface G0SampleSelectionDef {
  /** `SamplingConfig` 字段名（替代程序族同源；`test_population` 为 additive 新增） */
  field: 'test_population' | 'specific_samples' | 'sampling_population' | 'sample_size' | 'sampling_method' | 'sampling_process'
  /** 标签（逐字源模板 J 列，去尾冒号） */
  label: string
  labelAnchor: string
  /** placeholder（逐字源模板 K 列示例文字） */
  placeholder: string
  placeholderAnchor: string
  /** 该项是否为点选型（源模板 `K25` 是斜杠分隔的选项串） */
  options?: readonly string[]
}

// ─── 四块 ────────────────────────────────────────────────────────────────────

export const G0_LOWER_ZONE_BLOCKS: readonly LowerZoneBlockDef[] = Object.freeze([
  { key: 'matrix', anchor: 'C19', title: '一、函证情况', source_ref: 'G0-1!C19', renderedHere: true },
  // 🔴 renderedHere:false —— 由 Task 13 升级后的 `ConfirmationSampling.vue`（isG0 → 6 项）渲染
  { key: 'sample_selection', anchor: 'J19', title: '二、样本选择', source_ref: 'G0-1!J19', renderedHere: false },
  { key: 'audit_note', anchor: 'S19', title: '三、审计说明', source_ref: 'G0-1!S19', renderedHere: true },
  { key: 'conclusion', anchor: 'C30', title: '四、审计结论', source_ref: 'G0-1!C30', renderedHere: true },
])

/** 便捷索引 */
export function getG0LowerBlock(key: G0LowerBlock): LowerZoneBlockDef {
  const b = G0_LOWER_ZONE_BLOCKS.find((x) => x.key === key)
  if (!b) throw new Error(`[g0SummaryLowerZone] 未声明的块: ${key}`)
  return b
}

// ─── 三、审计说明（5 项，标题逐字 S20/X20/S24/S25/S28） ───────────────────────

export const G0_AUDIT_NOTE_DEFS: readonly G0AuditNoteDef[] = Object.freeze([
  {
    seq: 1,
    key: 'control',
    title: '1、对询证函保持的控制的说明',
    titleAnchor: 'S20',
    aiSection: 'g0-summary-control',
    reviewSectionId: 'G0-1-audit-note-1',
  },
  {
    seq: 2,
    key: 'error_analysis',
    title: '2、对误差的分析',
    titleAnchor: 'X20',
    // 🔴 全下区唯一需要拼接的 hint（X21 + X22 是被源模板拆成两格的一句话）
    hint: '界定误差构成条件：［不符事项的金额高于或低于账户余额人民币（）万元，并且被审计单位不能合理解释其差异并提供相应依据］',
    hintAnchor: 'X21+X22',
    aiSection: 'g0-summary-error-analysis',
    reviewSectionId: 'G0-1-audit-note-2',
  },
  {
    seq: 3,
    key: 'reliability',
    // 🔴 源模板写「（G0-6）」，而回函可靠性验证表实为 G0-7（G0-6 是替代程序检查表）。
    //    索引号笔误的处置归 Task 20（源缺陷登记）→ 此处**逐字保留原文**，
    //    否则守卫的三向比对会因「顺手修正」而打红。
    title: '3、对以传真或电子邮件形式收到的回函的可靠性的考虑（G0-6）',
    titleAnchor: 'S24',
    aiSection: 'g0-summary-reliability',
    reviewSectionId: 'G0-1-audit-note-3',
  },
  {
    seq: 4,
    key: 'mismatch',
    title: '4、针对不符事项的程序',
    titleAnchor: 'S25',
    // 🔴 S26 是独立提示语，**不与 S25 拼接**（拼接会产出错句）
    hint: '如果回函中存在未函证的其他信息，应考虑未函证信息的影响，并考虑实施进一步审计程序',
    hintAnchor: 'S26',
    aiSection: 'g0-summary-mismatch',
    reviewSectionId: 'G0-1-audit-note-4',
  },
  {
    seq: 5,
    key: 'alternative',
    title: '5、针对未回函的替代程序',
    titleAnchor: 'S28',
    aiSection: 'g0-summary-alternative',
    reviewSectionId: 'G0-1-audit-note-5',
  },
])

/** 审计结论的 AI / 复核 section-id */
export const G0_CONCLUSION_AI_SECTION = 'g0-summary-conclusion'
export const G0_CONCLUSION_REVIEW_SECTION_ID = 'G0-1-conclusion'

/** 全部 AI section id（供 Task 19 守卫比对后端登记情况） */
export const G0_AI_SECTIONS: readonly string[] = Object.freeze([
  ...G0_AUDIT_NOTE_DEFS.map((d) => d.aiSection),
  G0_CONCLUSION_AI_SECTION,
])

// ─── 下区固定文字扁平清单（Property 8 逐条比对源格） ──────────────────────────

export const G0_LOWER_ZONE_TEXTS: readonly LowerZoneTextDef[] = Object.freeze([
  ...G0_LOWER_ZONE_BLOCKS.map(
    (b): LowerZoneTextDef => ({
      block: b.key,
      key: `block_${b.key}`,
      role: 'title',
      text: b.title,
      anchor: b.anchor,
      readonly: true,
      source_ref: b.source_ref,
    }),
  ),
  ...G0_AUDIT_NOTE_DEFS.map(
    (d): LowerZoneTextDef => ({
      block: 'audit_note',
      key: `${d.key}_title`,
      role: 'title',
      text: d.title,
      anchor: d.titleAnchor,
      readonly: false, // 标题只读，但该项下方有录入位置
      source_ref: `${G0_SOURCE_REF_PREFIX}${d.titleAnchor}`,
    }),
  ),
  ...G0_AUDIT_NOTE_DEFS.filter((d) => d.hint != null).map(
    (d): LowerZoneTextDef => ({
      block: 'audit_note',
      key: `${d.key}_hint`,
      role: 'hint',
      text: d.hint!,
      anchor: d.hintAnchor!,
      readonly: true,
      source_ref: `${G0_SOURCE_REF_PREFIX}${d.hintAnchor!}`,
    }),
  ),
])

// ─── 四、审计结论 参考结论（内容取 B 列，可一键套用） ─────────────────────────

export const G0_REF_CONCLUSIONS: readonly G0RefConclusionDef[] = Object.freeze([
  { code: 'A', text: '未见异常。', anchor: 'B55', labelAnchor: 'A55', source_ref: 'G0-1!B55' },
  {
    code: 'B',
    text: '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    anchor: 'B56',
    labelAnchor: 'A56',
    source_ref: 'G0-1!B56',
  },
  {
    code: 'C',
    text: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
    anchor: 'B57',
    labelAnchor: 'A57',
    source_ref: 'G0-1!B57',
  },
])

/** 参考结论段标题（源 `A54`） */
export const G0_REF_CONCLUSION_HEADING = { text: '参考结论：', anchor: 'A54', source_ref: 'G0-1!A54' }

// ─── 编制说明（只读折叠，源 A33~A58 + B44:B51） ───────────────────────────────

export const G0_PREPARATION_NOTES: readonly G0PreparationNoteDef[] = Object.freeze([
  {
    key: 'heading',
    lines: [{ text: '编制说明：', anchor: 'A33' }],
  },
  {
    // 准则 1312 第十条六项选样要求。🔴 A38~A42 带全角缩进空格（U+3000 ×2），逐字保留
    key: 'sample_selection_standard',
    heading: '1、函证样本的选择',
    lines: [
      { text: '1、函证样本的选择：', anchor: 'A34' },
      { text: '《中国注册会计师审计准则第1312号——函证》第十条注册会计师采用审计抽样或其他选取测试项目的方法', anchor: 'A35' },
      { text: '选择函证样本时，样本应当足以代表总体，并包括：', anchor: 'A36' },
      { text: '（一）金额较大的项目；', anchor: 'A37' },
      { text: '\u3000\u3000（二）账龄较长的项目；', anchor: 'A38' },
      { text: '\u3000\u3000（三）交易频繁但期末余额较小的项目；', anchor: 'A39' },
      { text: '\u3000\u3000（四）重大关联方交易；', anchor: 'A40' },
      { text: '\u3000\u3000（五）重大或异常的交易；', anchor: 'A41' },
      { text: '\u3000\u3000（六）可能存在争议以及产生重大舞弊或错误的交易。', anchor: 'A42' },
    ],
  },
  {
    // 🔴 八条正文在 **B44:B51**（A43 只是标题）—— 只扫 A 列会整段漏掉
    key: 'confirmation_cautions',
    heading: '2、函证注意事项',
    lines: [
      { text: '2、函证注意事项：', anchor: 'A43' },
      { text: '①严格控制发函过程（亲自发函；直接回函）；', anchor: 'B44' },
      { text: '②传真件、电子邮件回函可以作为证据，但可靠性低于原件且需严格控制并记录函证过程；', anchor: 'B45' },
      { text: '③同一客户的多项往来在同一张询证函列示；', anchor: 'B46' },
      { text: '④关联往来核对一致；', anchor: 'B47' },
      { text: '⑤收信人尽量写清楚；', anchor: 'B48' },
      { text: '⑥收到回函编制函证控制表（函证结果汇总表），保留回函信封，注明选样标准；', anchor: 'B49' },
      { text: '⑦回函有差异须进一步核对原因；', anchor: 'B50' },
      { text: '⑧未回函的全部执行替代程序。', anchor: 'B51' },
    ],
  },
  {
    key: 'overview',
    heading: '3、概述',
    lines: [
      { text: '3、概述：（1）程序的测试情况、结果；', anchor: 'A52' },
      { text: '（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。', anchor: 'A53' },
    ],
  },
  {
    key: 'attached_evidence',
    lines: [{ text: '后附审计证据：询证函回函、不符事项相关资料、替代程序资料等。', anchor: 'A58' }],
  },
])

// ─── 二、样本选择 6 项（**只导出给 Task 13，本模块不渲染**） ───────────────────

/**
 * 源模板 6 项，标签逐字 `J20/J21/J22/J23/J25/J26`、placeholder 逐字 `K20/K21/K22/K23/K25/K26`。
 *
 * 🔴 `test_population` 是 **additive 新增**字段 —— 不可复用 `SamplingConfig.test_scope`
 * （那是 `G0-6!A7`「测试范围」的 5 点选项，与本项「测试总体」语义不同）。
 *
 * 🔴 唯一消费方 = `confirmation/ConfirmationSampling.vue`（Task 13，`isG0` 门控）。
 *    `G0SummaryLowerZone.vue` **不得**渲染这 6 项（双真源红线，守卫按源码断言）。
 */
export const G0_SAMPLE_SELECTION_DEFS: readonly G0SampleSelectionDef[] = Object.freeze([
  {
    field: 'test_population',
    label: '测试总体',
    labelAnchor: 'J20',
    placeholder: '如交易性金融资产账面余额XX、投资产品XX个；……',
    placeholderAnchor: 'K20',
  },
  {
    field: 'specific_samples',
    label: '特定样本',
    labelAnchor: 'J21',
    placeholder: '交易性金融资产XX金额以上（大额）……、关联方/关联交易形成的、XX异常款项全部测试，共XX个产品；',
    placeholderAnchor: 'K21',
  },
  {
    field: 'sampling_population',
    label: '抽样总体',
    labelAnchor: 'J22',
    placeholder: '测试总体扣除特定样本以外的样本，交易性金融资产共XX个产品、金额XX，……；',
    placeholderAnchor: 'K22',
  },
  {
    field: 'sample_size',
    label: '确定的抽样样本量',
    labelAnchor: 'J23',
    placeholder: '交易性金融资产共XX个产品；',
    placeholderAnchor: 'K23',
  },
  {
    field: 'sampling_method',
    label: '抽样方法',
    labelAnchor: 'J25',
    placeholder: '随机选样/系统选样/货币单元抽样/随意选样',
    placeholderAnchor: 'K25',
    // 源模板 K25 就是斜杠分隔的备选项 → 做成可点选（平台「交互点选优先」铁律）
    options: Object.freeze(['随机选样', '系统选样', '货币单元抽样', '随意选样']),
  },
  {
    field: 'sampling_process',
    label: '抽样过程',
    labelAnchor: 'J26',
    placeholder: '使用IDEA（XX抽样工具）选取样本进行函证，交易性金融资产选择XX个产品、金额XX的样本，',
    placeholderAnchor: 'K26',
  },
])

/**
 * 样本选择的两段只读补充提示（源 `K24`/`K27`）。
 *
 * 它们是**说明段落而非录入项**：`K24` 挂在「确定的抽样样本量」下、`K27` 挂在「抽样过程」下。
 * 🔴 不得与 `K23`/`K26` 拼成 placeholder（那样会把说明混进示例文字）。
 */
export const G0_SAMPLE_SELECTION_HINTS: readonly { field: string; text: string; anchor: string; source_ref: string }[] =
  Object.freeze([
    {
      field: 'sample_size',
      text: '（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）',
      anchor: 'K24',
      source_ref: 'G0-1!K24',
    },
    {
      field: 'sampling_process',
      text: '抽样工具中的样本选择过程和结果见<XX>底稿',
      anchor: 'K27',
      source_ref: 'G0-1!K27',
    },
  ])

/** 旧 4 字段 → 新字段的读回映射（数据零丢失，R3.6 / Property 9） */
export const G0_LEGACY_SAMPLING_FIELD_MAP: Readonly<Record<string, string>> = Object.freeze({
  sampling_size: 'sample_size',
  sampling_criteria: 'specific_samples',
  sampling_method: 'sampling_method',
  // 源模板无对应项 → 作源外增强字段原样保留（不迁移、不丢弃）
  sampling_conclusion: 'sampling_conclusion',
})

// ─── 持久化键（R3.11：与上区 grid / 既有 sampling·conclusion 键不冲突） ────────

/**
 * 下区录入键统一前缀。
 *
 * 既有键：`G0-1-sampling`（`SamplingConfig` JSON，归 Task 13）· `G0-1-matrix-{品种}-{指标}`
 * （矩阵手工覆盖，归 `g0MatrixDataSources.g0MatrixOverrideItemId`）。
 * 本前缀与二者均不重叠。
 */
export const G0_LOWER_KEY_PREFIX = 'G0-1-lower-'

export const G0_AUDIT_NOTE_KEY_PREFIX = `${G0_LOWER_KEY_PREFIX}audit-note-`
export const G0_CONCLUSION_KEY = `${G0_LOWER_KEY_PREFIX}conclusion`

export function g0AuditNoteItemId(seq: number): string {
  return `${G0_AUDIT_NOTE_KEY_PREFIX}${seq}`
}

/** 下区全部录入键（供守卫断言互不冲突 / 宿主批量拉取） */
export const G0_LOWER_ITEM_IDS: readonly string[] = Object.freeze([
  ...G0_AUDIT_NOTE_DEFS.map((d) => g0AuditNoteItemId(d.seq)),
  G0_CONCLUSION_KEY,
])
