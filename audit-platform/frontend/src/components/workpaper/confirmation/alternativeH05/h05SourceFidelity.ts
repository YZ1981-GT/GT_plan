/**
 * h05SourceFidelity.ts — H0-5 替代程序源模板字面真源
 *
 * 唯一裁决者：`backend/wp_templates/H/H0 固定资产循环函证.xlsx` → sheet `替代程序H0-5`
 * 后端事实守卫：`backend/tests/test_h0_source_template_facts.py`
 *   - `test_h0_5_sample_fields_and_guidance`（6 字段标签 + 3 条替代程序编制说明）
 *   - `test_h0_5_check_record_area_is_blank`（R11:R19 空白自由区 → 四区块属源外增强）
 *
 * 🔴 本文件所有字符串必须与源模板单元格**逐字一致**（含标点与尾分号）。
 *    组件只许引用本文件，禁止在模板里内联字面量（守卫
 *    `__tests__/alternativeH05SourceFidelity.spec.ts` 会打红）。
 *
 * 🔴 H0-5 的「测试范围」占位是**借方发生额单侧**，源模板 B7 无「贷方发生额」措辞
 *    （那是 F0-5 的口径，历史实现抄错过一次）。
 */

// ─── 一、样本选取标准与规模（源模板 A6，6 字段） ─────────────────────────────

export interface H05SamplingFieldDef {
  /** `SamplingConfig` 字段名 */
  field: 'test_scope' | 'specific_samples' | 'sampling_population' | 'sample_size' | 'sampling_method' | 'sampling_process'
  /** 标签（逐字源模板，不含尾部全角冒号） */
  label: string
  /** 标签所在单元格 */
  labelRef: string
  /** 占位提示（逐字源模板示例文字） */
  placeholder: string
  /** 占位所在单元格 */
  placeholderRef: string
  /** 控件形态 */
  control: 'textarea' | 'input' | 'select'
  /** select 形态的取值（逐字拆分源模板示例） */
  options?: string[]
  /** 附加提示（源模板同行另一格的说明文字） */
  hint?: string
  /** 附加提示所在单元格 */
  hintRef?: string
}

/** 源模板 B9 的抽样方法四选项（`随机选样/系统选样/货币单元抽样/随意选样（非统计抽样适用）`）。 */
export const H05_SAMPLING_METHOD_OPTIONS: readonly string[] = Object.freeze([
  '随机选样',
  '系统选样',
  '货币单元抽样',
  '随意选样（非统计抽样适用）',
])

/**
 * 6 个抽样字段。顺序即源模板阅读顺序（左列 A7/A8/A9，右列 I7/I8/I9）。
 */
export const H05_SAMPLING_FIELDS: readonly H05SamplingFieldDef[] = Object.freeze([
  {
    field: 'test_scope',
    label: '测试范围',
    labelRef: 'A7',
    placeholder: '如固定资产借方发生额所有凭证共XX笔金额XX',
    placeholderRef: 'B7',
    control: 'textarea',
  },
  {
    field: 'specific_samples',
    label: '特定样本',
    labelRef: 'I7',
    placeholder: 'XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔；',
    placeholderRef: 'J7',
    control: 'textarea',
  },
  {
    field: 'sampling_population',
    label: '抽样总体',
    labelRef: 'A8',
    placeholder: '测试总体扣除特定样本以外的样本，共XX笔、金额XX',
    placeholderRef: 'B8',
    control: 'input',
  },
  {
    field: 'sample_size',
    label: '确定的抽样样本量',
    labelRef: 'I8',
    placeholder: '抽取XX笔',
    placeholderRef: 'K8',
    control: 'input',
    hint: '（如果使用了样本计算器计算样本量，样本量计算过程见<XX>底稿）',
    hintRef: 'L8',
  },
  {
    field: 'sampling_method',
    label: '抽样方法',
    labelRef: 'A9',
    placeholder: '随机选样/系统选样/货币单元抽样/随意选样（非统计抽样适用）',
    placeholderRef: 'B9',
    control: 'select',
    options: H05_SAMPLING_METHOD_OPTIONS as string[],
  },
  {
    field: 'sampling_process',
    label: '抽样过程',
    labelRef: 'I9',
    placeholder: '使用IDEA（XX抽样工具）选择XX数量占比XX%的样本进行测试，抽样工具中的样本选择过程和结果见XX底稿',
    placeholderRef: 'J9',
    control: 'textarea',
  },
] as const)

// ─── 四个区块标题（源模板 A6/A10/A20/A23） ───────────────────────────────────

export interface H05SectionTitleDef {
  key: 'sampling' | 'check_record' | 'audit_note' | 'conclusion'
  /** 标题（逐字源模板，不含尾部全角冒号） */
  title: string
  anchor: string
}

/**
 * 🔴 源模板四段编号为 一/二/三/四 = 样本选取 / 检查过程记录 / 审计说明 / 审计结论。
 * 改造前平台是 一、样本选取 / 二、余额汇总与检查比例 / 三、检查过程记录 / 四、审计说明与结论
 * —— 编号与源模板全部错位且把说明与结论合并成一段。
 */
export const H05_SECTION_TITLES: readonly H05SectionTitleDef[] = Object.freeze([
  { key: 'sampling', title: '一、样本选取标准与规模', anchor: 'A6' },
  { key: 'check_record', title: '二、检查过程记录', anchor: 'A10' },
  { key: 'audit_note', title: '三、审计说明', anchor: 'A20' },
  { key: 'conclusion', title: '四、审计结论', anchor: 'A23' },
] as const)

export function h05SectionTitle(key: H05SectionTitleDef['key']): string {
  const found = H05_SECTION_TITLES.find((s) => s.key === key)
  if (!found) throw new Error(`[h05SourceFidelity] 未知区块 key: ${key}`)
  return found.title
}

// ─── 二、检查过程记录：自由记录区 + 源外增强标注 ─────────────────────────────

/**
 * 自由记录区持久化键（落在 `AlternativeCompany.check_record_free`，
 * 随 `buildPayload()` 一起写入 `html_data`）。
 * 语义 = 源模板 R11:R19 的空白自由记录区。
 */
export const H05_CHECK_RECORD_FREE_KEY = 'H0-5-check-record-free'

export const H05_CHECK_RECORD_FREE_LABEL = '检查过程自由记录（对应源模板空白记录区）'

export const H05_CHECK_RECORD_FREE_PLACEHOLDER =
  '按源模板此处为空白自由记录区，可逐笔或分段记录检查过程、所见凭证与判断依据。'

/** 源外增强统一标注文字（渲染在四区块与余额汇总上方）。 */
export const H05_SOURCE_EXTRA_BADGE = '平台增强（源模板此处为空白记录区）'

export const H05_SOURCE_EXTRA_REASON =
  '源模板 H0-5「二、检查过程记录」R11:R19 为空白自由记录区（无表头、无列定义）。'
  + '下列结构化区块与比例指标由平台自建，用于提高可核查性与覆盖率统计，'
  + '不属源模板要求；已在 alternativeBlockManifest.ALTERNATIVE_BLOCK_MANIFEST.H05 登记 sourceExtra。'

// ─── 编制说明（源模板 A28 起） ───────────────────────────────────────────────

export interface H05GuidanceItem {
  anchor: string
  /** 展示文字 */
  text: string
  /** 源模板原文（与 text 不同时给出，如含前导空白的续行） */
  sourceText?: string
}

export interface H05GuidanceGroup {
  anchor: string
  /** 分组标题（逐字源模板，不含尾部全角冒号） */
  title: string
  items: readonly H05GuidanceItem[]
}

export const H05_GUIDANCE_TITLE = '编制说明'

export const H05_GUIDANCE_GROUPS: readonly H05GuidanceGroup[] = Object.freeze([
  {
    anchor: 'A29',
    title: '1、函证替代程序',
    items: Object.freeze([
      { anchor: 'B30', text: '①检查本期付款、期后收货或回收；' },
      { anchor: 'B31', text: '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等；' },
      { anchor: 'B32', text: '③对回函可能性不高的、余额重大的，发函同时执行替代程序。' },
    ]),
  },
  {
    anchor: 'A34',
    title: '2、概述',
    items: Object.freeze([
      {
        anchor: 'A34',
        text: '（1）程序的测试情况、结果；',
        sourceText: '2、概述：（1）程序的测试情况、结果；',
      },
      {
        anchor: 'A35',
        text: '（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。',
        sourceText:
          '                      （2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。',
      },
    ]),
  },
] as const)

/** 顶部提示条沿用源模板第 ③ 条（发函同时执行替代程序）。 */
export const H05_HEADER_TIP = H05_GUIDANCE_GROUPS[0].items[2].text
