import { computed, ref, watch } from 'vue'

export type SppiAnswer = 'yes' | 'no' | 'na' | null
export type SppiConclusion = 'pass' | 'fail' | 'na' | null
export type SppiOverallConclusion = 'pass' | 'fail' | null

export interface SppiItem {
  id: string
  seq: number
  checkArea: string
  checkItem: string
  casRequirement: string
  contractTermSummary: string
  isSPPISatisfied: SppiAnswer
  judgmentBasis: string
  riskLevel: 'high' | 'medium' | 'low' | null
  indexRef: string
  remark: string
}

export interface SppiSection {
  id: string
  title: string
  items: SppiItem[]
  sectionConclusion: SppiConclusion
}

export interface SppiInstrument {
  id: string
  name: string
  sections: SppiSection[]
  overallConclusion: SppiOverallConclusion
  hasFailedSection: boolean
}

export interface SppiTestData {
  instruments?: SppiInstrument[]
  activeInstrumentId?: string | null
  /** 当前项目的 sections，保留用于兼容旧版持久化格式。 */
  sections?: SppiSection[]
  overallConclusion?: SppiOverallConclusion
  hasFailedSection?: boolean
}

export interface SppiInstrumentSeed {
  id?: string
  projectId?: string
  name?: string
  projectName?: string
  instrumentName?: string
}

export interface SppiFlatRow extends SppiItem {
  instrumentId: string
  instrumentName: string
  sectionId: string
  sectionTitle: string
  sectionConclusion: SppiConclusion
}

export interface SppiEvidenceGap {
  instrumentId?: string
  instrumentName?: string
  sectionId: string
  sectionTitle: string
  itemId: string
  checkItem: string
  missing: Array<'contractTermSummary' | 'judgmentBasis' | 'indexRef'>
}

export const SPPI_METHODOLOGY: Record<string, string> = {
  principal:
    'CAS 22：本金是金融资产在初始确认时的公允价值，并可因后续偿还而在存续期内变化；合同现金流量不得引入与基本借贷安排无关的本金风险。',
  interest:
    'CAS 22：利息由货币时间价值、与特定期间未偿付本金相关的信用风险、其他基本借贷风险和成本以及合理利润率构成。',
  modified_time_value:
    'CAS 22：货币时间价值要素被修改时，应以定性及必要的定量基准测试评估未折现合同现金流量与基准现金流量的差异。',
  prepayment:
    'CAS 22：提前还款或展期条款仅在结算金额基本代表未偿付本金、应计利息及合理补偿等准则允许成分时保持 SPPI 特征。',
  contractual_linked:
    'CAS 22：合同关联工具应穿透评估底层工具现金流量、信用风险集中程度及分层结构，持有层级的信用风险敞口不得高于底层工具组合。',
  comprehensive:
    'CAS 22：结合全部合同条款及可能影响现金流量金额和时点的情形，判断现金流量是否仅为本金及以未偿付本金为基础的利息。',
}

export const SECTION_DEFINITIONS = [
  { id: 'principal', title: '(一) 本金定义：初始确认时的公允价值', methodologyKey: 'principal' },
  { id: 'interest', title: '(二) 利息定义：基本借贷安排的对价', methodologyKey: 'interest' },
  { id: 'modified_time_value', title: '(三) 修改时间价值：期限及利率重置匹配', methodologyKey: 'modified_time_value' },
  { id: 'prepayment', title: '(四) 提前还款及展期条款', methodologyKey: 'prepayment' },
  { id: 'contractual_linked', title: '(五) 合同关联工具及分层结构', methodologyKey: 'contractual_linked' },
  { id: 'comprehensive', title: '(六) 综合判断：合同现金流量特征', methodologyKey: 'comprehensive' },
] as const

type ItemDefinition = { checkArea: string; checkItem: string }

function statements(checkArea: string, ...checkItems: string[]): ItemDefinition[] {
  return checkItems.map(checkItem => ({ checkArea, checkItem }))
}

/** 70 项合规陈述：10 / 14 / 12 / 12 / 12 / 10。 */
export const DEFAULT_SECTION_ITEMS: Record<string, ItemDefinition[]> = {
  principal: [
    ...statements(
      '初始确认',
      '初始确认本金以金融资产公允价值为基础确定',
      '交易价格与公允价值差异已按适用准则识别并处理',
      '非现金对价不会使本金偏离基本借贷安排',
    ),
    ...statements(
      '本金变动',
      '存续期本金变动仅源于合同约定的正常偿还',
      '折价或溢价摊销反映实际利率法下的本金与利息关系',
      '本金调整不与权益价格、商品价格或其他非借贷变量挂钩',
      '或有本金调整仅补偿基本借贷风险或成本',
    ),
    ...statements(
      '偿付基础',
      '本金偿付金额和时点可由合同条款可靠确定',
      '本金受偿顺序不会形成超出债务人信用风险的额外敞口',
      '本金结算机制不会产生杠杆或放大非基本借贷风险',
    ),
  ],
  interest: [
    ...statements(
      '货币时间价值',
      '合同利率反映特定期间货币时间价值的基本对价',
      '利息以该期间未偿付本金为计算基础',
      '固定利率安排体现合同订立日的市场货币时间价值',
      '浮动利率基准与计价币种及市场惯例相符',
    ),
    ...statements(
      '信用风险',
      '信用利差补偿债务人在相关期间的信用风险',
      '信用利差调整与债务人信用状况变化具有合理关联',
      '担保与增信安排仅影响合理信用风险补偿',
    ),
    ...statements(
      '借贷风险与成本',
      '流动性风险补偿属于基本借贷安排的合理组成部分',
      '行政管理成本补偿与持有和服务该金融资产直接相关',
      '资金成本补偿未引入独立的非借贷风险敞口',
      '税费及监管成本转嫁具有合理且可识别的借贷基础',
    ),
    ...statements(
      '利润及其他',
      '合同利润率与同类基本借贷安排的合理回报相符',
      '利息公式不包含权益、商品、加密资产或业绩指数回报',
      '利息条款整体不会形成杠杆收益或损失',
    ),
  ],
  modified_time_value: [
    ...statements(
      '重置匹配',
      '利率重置频率与对应计息期间保持匹配',
      '利率期限与重置后的剩余计息期间保持匹配',
      '重置日与计息起止日差异不会显著修改货币时间价值',
      '观察期、回溯期或锁定期安排不会显著改变利息经济实质',
    ),
    ...statements(
      '基准特征',
      '利率基准能够代表相关币种和期限的货币时间价值',
      '平均利率或滞后利率机制不会引入与基本借贷无关的风险',
      '利率上限和下限仅限制浮动性且不引入杠杆',
      '管理人或发行人的利率选择权受客观市场参数约束',
    ),
    ...statements(
      '基准测试',
      '定性分析已覆盖可能造成现金流量差异的全部修改因素',
      '需要定量评估时已选取具有可比条款的未修改基准工具',
      '合理可能情景下合同现金流量与基准现金流量差异不显著',
      '基准测试期间覆盖金融工具存续期内具有代表性的利率环境',
    ),
  ],
  prepayment: [
    ...statements(
      '提前还款',
      '提前还款金额基本代表未偿付本金及应计未付利息',
      '提前还款补偿仅覆盖合理的提前终止损失或收益',
      '借款人提前还款权不会带来与基本借贷无关的回报',
      '贷款人回售或赎回权的结算基础符合本金及利息定义',
      '监管、税务或违约触发的提前结算金额符合准则允许成分',
    ),
    ...statements(
      '折溢价例外',
      '以折价或溢价取得的工具符合准则规定的提前还款例外条件',
      '提前还款特征的初始公允价值不重大或已按准则要求评估',
      '提前结算金额中的合理补偿不形成独立衍生回报',
    ),
    ...statements(
      '展期安排',
      '展期期间现金流量仍仅包含未偿付本金及合规利息',
      '展期利率按基本借贷风险和成本重新确定',
      '展期费用仅补偿合理管理成本、信用风险或利润率',
      '展期选择权不会使持有人承担权益、商品或其他非借贷风险',
    ),
  ],
  contractual_linked: [
    ...statements(
      '结构识别',
      '合同分层及现金流量瀑布安排已被完整识别',
      '持有层级的受偿权及损失吸收顺序已得到清晰界定',
      '结构中的信用增级仅重新分配底层资产信用风险',
    ),
    ...statements(
      '底层工具',
      '底层资产合同现金流量本身符合本金和利息定义',
      '底层资产组合仅包含准则允许的合规工具或降低波动的工具',
      '衍生工具仅用于降低底层现金流量波动并保持 SPPI 特征',
      '底层资产替换机制受合规资产标准约束',
    ),
    ...statements(
      '信用风险',
      '持有层级信用风险敞口不高于底层资产组合信用风险敞口',
      '损失分配机制不会形成对非信用变量的杠杆敞口',
      '触发事件仅反映信用恶化、偿付不足或其他基本借贷风险',
    ),
    ...statements(
      '穿透证据',
      '穿透信息足以支持对底层资产特征和风险的持续评估',
      '无法直接逐项穿透时采用的组合证据足以形成可靠结论',
    ),
  ],
  comprehensive: [
    ...statements(
      '条款完整性',
      '全部可能改变合同现金流量金额或时点的条款均已纳入分析',
      '合同主协议、补充协议及嵌入条款之间的影响已综合考虑',
      '极端、异常或发生概率极低但真实的情景已按准则要求考虑',
    ),
    ...statements(
      '非借贷敞口',
      '合同现金流量不与权益价格、商品价格或债务人经营业绩挂钩',
      '合同安排不包含放大现金流量波动的杠杆机制',
      '非真实条款或对现金流量影响极小的条款已具备充分判断依据',
    ),
    ...statements(
      '结论衔接',
      '本金、利息及特殊条款分析之间不存在相互矛盾的结论',
      '合同现金流量整体仅为本金及以未偿付本金为基础的利息',
      'SPPI 结论与金融资产分类及后续计量建议保持一致',
      '关键判断、合同摘录和审计索引足以支持复核与追溯',
    ),
  ],
}

export const defaultItemCounts: Record<string, number> = Object.fromEntries(
  SECTION_DEFINITIONS.map(def => [def.id, DEFAULT_SECTION_ITEMS[def.id].length]),
)

export const defaultTotalRows = Object.values(defaultItemCounts).reduce(
  (total, count) => total + count,
  0,
)

let idCounter = 0
function generateId(prefix = 'sppi'): string {
  idCounter += 1
  return `${prefix}-${Date.now().toString(36)}-${idCounter.toString(36)}`
}

function createItem(
  seq: number,
  definition: ItemDefinition,
  casRequirement: string,
): SppiItem {
  return {
    id: generateId('item'),
    seq,
    checkArea: definition.checkArea,
    checkItem: definition.checkItem,
    casRequirement,
    contractTermSummary: '',
    isSPPISatisfied: null,
    judgmentBasis: '',
    riskLevel: null,
    indexRef: '',
    remark: '',
  }
}

function createSection(definition: (typeof SECTION_DEFINITIONS)[number]): SppiSection {
  return {
    id: definition.id,
    title: definition.title,
    items: DEFAULT_SECTION_ITEMS[definition.id].map((item, index) =>
      createItem(index + 1, item, SPPI_METHODOLOGY[definition.methodologyKey]),
    ),
    sectionConclusion: null,
  }
}

export function createDefaultSections(): SppiSection[] {
  return SECTION_DEFINITIONS.map(createSection)
}

function normalizeItem(
  item: Partial<SppiItem>,
  index: number,
  methodology: string,
): SppiItem {
  return {
    id: item.id || generateId('item'),
    seq: index + 1,
    checkArea: item.checkArea || '',
    checkItem: item.checkItem || '',
    casRequirement: item.casRequirement || methodology,
    contractTermSummary: item.contractTermSummary || '',
    isSPPISatisfied: item.isSPPISatisfied ?? null,
    judgmentBasis: item.judgmentBasis || '',
    riskLevel: item.riskLevel ?? null,
    indexRef: item.indexRef || '',
    remark: item.remark || '',
  }
}

function normalizeSections(input?: SppiSection[]): SppiSection[] {
  return SECTION_DEFINITIONS.map(definition => {
    const existing = input?.find(section => section.id === definition.id)
    if (!existing) return createSection(definition)
    return {
      id: definition.id,
      title: existing.title || definition.title,
      items: (existing.items || []).map((item, index) =>
        normalizeItem(item, index, SPPI_METHODOLOGY[definition.methodologyKey]),
      ),
      sectionConclusion: existing.sectionConclusion ?? null,
    }
  })
}

function createInstrument(name: string, id?: string): SppiInstrument {
  return {
    id: id || generateId('instrument'),
    name: name.trim() || '未命名投资项目',
    sections: createDefaultSections(),
    overallConclusion: null,
    hasFailedSection: false,
  }
}

function cloneInstrument(input: Partial<SppiInstrument>, fallbackName: string): SppiInstrument {
  const sections = normalizeSections(input.sections)
  for (const section of sections) {
    section.sectionConclusion = deriveSectionConclusion(section.items)
  }
  return {
    id: input.id || generateId('instrument'),
    name: input.name?.trim() || fallbackName,
    sections,
    overallConclusion: deriveOverallConclusion(sections),
    hasFailedSection: sections.some(section => section.sectionConclusion === 'fail'),
  }
}

export function deriveSectionConclusion(items: SppiItem[]): SppiConclusion {
  if (!items.length) return null
  if (items.some(item => item.isSPPISatisfied === 'no')) return 'fail'
  if (items.some(item => item.isSPPISatisfied === null)) return null
  return items.some(item => item.isSPPISatisfied === 'yes') ? 'pass' : 'na'
}

export function findEvidenceGaps(
  sections: SppiSection[],
  instrument?: Pick<SppiInstrument, 'id' | 'name'>,
): SppiEvidenceGap[] {
  const gaps: SppiEvidenceGap[] = []
  for (const section of sections) {
    for (const item of section.items) {
      if (item.isSPPISatisfied !== 'yes' && item.isSPPISatisfied !== 'no') continue
      const missing: SppiEvidenceGap['missing'] = []
      if (!item.contractTermSummary.trim()) missing.push('contractTermSummary')
      if (!item.judgmentBasis.trim()) missing.push('judgmentBasis')
      if (
        (item.isSPPISatisfied === 'no' || item.riskLevel === 'high') &&
        !item.indexRef.trim()
      ) {
        missing.push('indexRef')
      }
      if (missing.length) {
        gaps.push({
          instrumentId: instrument?.id,
          instrumentName: instrument?.name,
          sectionId: section.id,
          sectionTitle: section.title,
          itemId: item.id,
          checkItem: item.checkItem,
          missing,
        })
      }
    }
  }
  return gaps
}

export function deriveOverallConclusion(
  sections: SppiSection[],
  options: { requireEvidence?: boolean } = {},
): SppiOverallConclusion {
  if (!sections.length) return null
  if (sections.some(section => section.sectionConclusion === 'fail')) return 'fail'
  if (sections.some(section => section.sectionConclusion === null)) return null
  // 全部不适用不能证明合同现金流量通过 SPPI。
  if (!sections.some(section => section.sectionConclusion === 'pass')) return null
  if (options.requireEvidence !== false && findEvidenceGaps(sections).length) return null
  return 'pass'
}

export function deriveAggregateInstrumentConclusion(
  instruments: SppiInstrument[],
): SppiOverallConclusion {
  if (!instruments.length) return null
  if (instruments.some(instrument => instrument.overallConclusion === 'fail')) return 'fail'
  if (instruments.some(instrument => instrument.overallConclusion !== 'pass')) return null
  return 'pass'
}

export function summarizeFailedItems(sections: SppiSection[]): Array<{
  sectionTitle: string
  checkItem: string
  contractTermSummary: string
  judgmentBasis: string
  riskLevel: SppiItem['riskLevel']
}> {
  return sections.flatMap(section =>
    section.items
      .filter(item => item.isSPPISatisfied === 'no')
      .map(item => ({
        sectionTitle: section.title,
        checkItem: item.checkItem,
        contractTermSummary: item.contractTermSummary,
        judgmentBasis: item.judgmentBasis,
        riskLevel: item.riskLevel,
      })),
  )
}

export function flattenSppiInstruments(instruments: SppiInstrument[]): SppiFlatRow[] {
  const rows: SppiFlatRow[] = []
  for (const instrument of instruments) {
    for (const section of instrument.sections) {
      for (const item of section.items) {
        rows.push({
          instrumentId: instrument.id,
          instrumentName: instrument.name,
          sectionId: section.id,
          sectionTitle: section.title,
          sectionConclusion: section.sectionConclusion,
          ...item,
        })
      }
    }
  }
  return rows
}

export function nestSppiFlatRows(rows: SppiFlatRow[]): SppiInstrument[] {
  // 按投资项目归组答案，再与默认六 section 骨架合并，避免导入缺行导致 section 丢失
  type Bucket = { id: string; name: string; answers: Map<string, SppiFlatRow> }
  const buckets = new Map<string, Bucket>()
  const order: string[] = []

  for (const row of rows) {
    const name = (row.instrumentName || '').trim() || '未命名投资项目'
    const key = name.replace(/\s+/g, '')
    if (!buckets.has(key)) {
      buckets.set(key, {
        id: row.instrumentId || generateId('instrument'),
        name,
        answers: new Map(),
      })
      order.push(key)
    }
    const bucket = buckets.get(key)!
    if (row.instrumentId) bucket.id = row.instrumentId
    const answerKey = `${row.sectionId}::${row.checkItem || row.id}`
    bucket.answers.set(answerKey, row)
  }

  return order.map(key => {
    const bucket = buckets.get(key)!
    const instrument = createInstrument(bucket.name, bucket.id)
    for (const section of instrument.sections) {
      for (const item of section.items) {
        const hit =
          bucket.answers.get(`${section.id}::${item.checkItem}`) ||
          bucket.answers.get(`${section.id}::${item.id}`)
        if (!hit) continue
        item.contractTermSummary = hit.contractTermSummary || ''
        item.judgmentBasis = hit.judgmentBasis || ''
        item.indexRef = hit.indexRef || ''
        item.remark = hit.remark || ''
        const sat = String(hit.isSPPISatisfied || '').toLowerCase()
        if (sat === 'yes' || sat === '是') item.isSPPISatisfied = 'yes'
        else if (sat === 'no' || sat === '否') item.isSPPISatisfied = 'no'
        else if (sat === 'na' || sat === '不适用' || sat === 'n/a') item.isSPPISatisfied = 'na'
        const risk = String(hit.riskLevel || '').toLowerCase()
        if (risk === 'high' || risk === '高') item.riskLevel = 'high'
        else if (risk === 'medium' || risk === '中') item.riskLevel = 'medium'
        else if (risk === 'low' || risk === '低') item.riskLevel = 'low'
      }
      section.sectionConclusion = deriveSectionConclusion(section.items)
    }
    instrument.hasFailedSection = instrument.sections.some(s => s.sectionConclusion === 'fail')
    instrument.overallConclusion = deriveOverallConclusion(instrument.sections)
    return instrument
  })
}

function seedName(seed: SppiInstrumentSeed): string {
  return (seed.projectName || seed.name || seed.instrumentName || '').trim()
}

export function useG6SppiTest() {
  const initialInstrument = createInstrument('综合问卷')
  const instruments = ref<SppiInstrument[]>([initialInstrument])
  const activeInstrumentId = ref<string | null>(initialInstrument.id)

  const activeInstrument = computed(
    () =>
      instruments.value.find(instrument => instrument.id === activeInstrumentId.value) ||
      instruments.value[0] ||
      null,
  )
  const sections = computed<SppiSection[]>(() => activeInstrument.value?.sections || [])
  /** 当前项目结论（页面标签用） */
  const activeOverallConclusion = computed<SppiOverallConclusion>(
    () => activeInstrument.value?.overallConclusion ?? null,
  )
  /** 跨项目汇总结论（持久化 / G6-7 交叉校验用） */
  const aggregateConclusion = computed(() =>
    deriveAggregateInstrumentConclusion(instruments.value),
  )
  const overallConclusion = aggregateConclusion
  const hasFailedSection = computed(() =>
    instruments.value.some(instrument => instrument.hasFailedSection),
  )
  const failedSections = computed(() =>
    sections.value.filter(section => section.sectionConclusion === 'fail'),
  )
  const evidenceGaps = computed(() =>
    findEvidenceGaps(
      sections.value,
      activeInstrument.value
        ? { id: activeInstrument.value.id, name: activeInstrument.value.name }
        : undefined,
    ),
  )
  const evidenceComplete = computed(() => evidenceGaps.value.length === 0)
  const failedItemSummaries = computed(() => summarizeFailedItems(sections.value))
  const allItems = computed(() => {
    let seq = 0
    return sections.value.flatMap(section =>
      section.items.map(item => ({
        ...item,
        seq: ++seq,
        sectionId: section.id,
        sectionTitle: section.title,
      })),
    )
  })
  const totalRows = computed(() => allItems.value.length)

  function recalcConclusions(): void {
    for (const instrument of instruments.value) {
      for (const section of instrument.sections) {
        const next = deriveSectionConclusion(section.items)
        if (section.sectionConclusion !== next) section.sectionConclusion = next
      }
      const failed = instrument.sections.some(section => section.sectionConclusion === 'fail')
      if (instrument.hasFailedSection !== failed) instrument.hasFailedSection = failed
      const next = deriveOverallConclusion(instrument.sections)
      if (instrument.overallConclusion !== next) instrument.overallConclusion = next
    }
  }

  watch(instruments, recalcConclusions, { deep: true })

  function updateItem(
    sectionId: string,
    itemId: string,
    field: keyof SppiItem,
    value: unknown,
    instrumentId = activeInstrumentId.value,
  ): void {
    const instrument = instruments.value.find(current => current.id === instrumentId)
    const item = instrument?.sections
      .find(section => section.id === sectionId)
      ?.items.find(current => current.id === itemId)
    if (item) (item as Record<string, unknown>)[field] = value
  }

  function addItem(sectionId: string, checkArea = '', checkItem = ''): void {
    const section = sections.value.find(current => current.id === sectionId)
    if (!section) return
    section.items.push(
      createItem(
        section.items.length + 1,
        { checkArea, checkItem },
        SPPI_METHODOLOGY[sectionId] || '',
      ),
    )
  }

  function removeItem(sectionId: string, itemId: string): void {
    const section = sections.value.find(current => current.id === sectionId)
    if (!section) return
    section.items = section.items.filter(item => item.id !== itemId)
    section.items.forEach((item, index) => { item.seq = index + 1 })
  }

  function setSectionConclusion(sectionId: string, value: SppiConclusion): void {
    const section = sections.value.find(current => current.id === sectionId)
    if (section) section.sectionConclusion = value
    const instrument = activeInstrument.value
    if (instrument) {
      instrument.hasFailedSection = instrument.sections.some(
        current => current.sectionConclusion === 'fail',
      )
      instrument.overallConclusion = deriveOverallConclusion(instrument.sections)
    }
  }

  function setOverallConclusion(value: SppiOverallConclusion): void {
    const instrument = activeInstrument.value
    if (!instrument) return
    instrument.overallConclusion =
      value === 'pass' && (
        findEvidenceGaps(instrument.sections).length ||
        !instrument.sections.some(section => section.sectionConclusion === 'pass')
      )
        ? null
        : value
  }

  function setActiveInstrument(id: string): void {
    if (instruments.value.some(instrument => instrument.id === id)) {
      activeInstrumentId.value = id
    }
  }

  function updateInstrumentName(id: string, name: string): void {
    const instrument = instruments.value.find(current => current.id === id)
    if (instrument) instrument.name = name
  }

  function addInstrument(name = '未命名投资项目', id?: string): SppiInstrument {
    const instrument = createInstrument(name, id)
    instruments.value.push(instrument)
    activeInstrumentId.value = instrument.id
    return instrument
  }

  function removeInstrument(id: string): void {
    const index = instruments.value.findIndex(instrument => instrument.id === id)
    if (index < 0) return
    instruments.value.splice(index, 1)
    if (!instruments.value.length) instruments.value.push(createInstrument('综合问卷'))
    if (!instruments.value.some(instrument => instrument.id === activeInstrumentId.value)) {
      activeInstrumentId.value = instruments.value[Math.min(index, instruments.value.length - 1)].id
    }
  }

  /** 优先按稳定 ID 合并，其次按项目名；同名异 ID 可并存；名称命中时回填稳定 ID。 */
  function syncFromSeeds(seeds: SppiInstrumentSeed[]): { added: number; kept: number } {
    const existingById = new Map(
      instruments.value.map(instrument => [instrument.id, instrument]),
    )
    const existingByName = new Map(
      instruments.value.map(instrument => [instrument.name.trim().replace(/\s+/g, ''), instrument]),
    )
    const usedIds = new Set<string>()
    const usedNames = new Set<string>()
    const merged: SppiInstrument[] = []
    let added = 0
    let kept = 0
    for (const seed of seeds) {
      const name = seedName(seed)
      if (!name) continue
      const nameKey = name.replace(/\s+/g, '')
      const seedId = String(seed.id || seed.projectId || '').trim()
      if (seedId && usedIds.has(seedId)) continue
      if (!seedId && usedNames.has(nameKey)) continue

      let existing = seedId ? existingById.get(seedId) : undefined
      if (!existing) {
        const byName = existingByName.get(nameKey)
        if (byName && !usedIds.has(byName.id)) existing = byName
      }

      if (existing) {
        if (seedId && existing.id !== seedId && !existingById.has(seedId)) {
          existingById.delete(existing.id)
          existing.id = seedId
          existingById.set(seedId, existing)
        }
        merged.push(existing)
        usedIds.add(existing.id)
        usedNames.add(nameKey)
        kept += 1
      } else {
        const created = createInstrument(name, seedId || undefined)
        merged.push(created)
        usedIds.add(created.id)
        usedNames.add(nameKey)
        added += 1
      }
    }
    for (const instrument of instruments.value) {
      if (usedIds.has(instrument.id)) continue
      const answered = instrument.sections.some(section =>
        section.items.some(
          item => item.isSPPISatisfied !== null || Boolean(item.contractTermSummary?.trim()),
        ),
      )
      if (answered) {
        merged.push(instrument)
        usedIds.add(instrument.id)
        kept += 1
      }
    }
    instruments.value = merged.length ? merged : [createInstrument('综合问卷')]
    if (!instruments.value.some(instrument => instrument.id === activeInstrumentId.value)) {
      activeInstrumentId.value = instruments.value[0].id
    }
    recalcConclusions()
    return { added, kept }
  }

  function loadData(data: SppiTestData | null): void {
    if (data?.instruments?.length) {
      instruments.value = data.instruments.map((instrument, index) =>
        cloneInstrument(instrument, `投资项目 ${index + 1}`),
      )
      activeInstrumentId.value =
        instruments.value.find(instrument => instrument.id === data.activeInstrumentId)?.id ||
        instruments.value[0].id
    } else if (data?.sections?.length) {
      // 旧格式只有 sections，升级为单一历史项目。
      const historical = cloneInstrument(
        { name: '综合问卷（历史）', sections: data.sections },
        '综合问卷（历史）',
      )
      instruments.value = [historical]
      activeInstrumentId.value = historical.id
    } else {
      const instrument = createInstrument('综合问卷')
      instruments.value = [instrument]
      activeInstrumentId.value = instrument.id
    }
    recalcConclusions()
  }

  function toJSON(): SppiTestData {
    const currentSections = sections.value.map(section => ({
      ...section,
      items: section.items.map(item => ({ ...item })),
    }))
    return {
      instruments: instruments.value.map(instrument => ({
        ...instrument,
        sections: instrument.sections.map(section => ({
          ...section,
          items: section.items.map(item => ({ ...item })),
        })),
      })),
      activeInstrumentId: activeInstrumentId.value,
      sections: currentSections,
      overallConclusion: aggregateConclusion.value,
      hasFailedSection: hasFailedSection.value,
    }
  }

  function toFlatRows(): SppiFlatRow[] {
    return flattenSppiInstruments(instruments.value)
  }

  function loadFromFlatRows(rows: SppiFlatRow[]): void {
    const nested = nestSppiFlatRows(rows)
    instruments.value = nested.length ? nested : [createInstrument('综合问卷')]
    activeInstrumentId.value = instruments.value[0].id
    recalcConclusions()
  }

  function reset(): void {
    const instrument = createInstrument('综合问卷')
    instruments.value = [instrument]
    activeInstrumentId.value = instrument.id
  }

  function getSectionMethodology(sectionId: string): string {
    return SPPI_METHODOLOGY[sectionId] || ''
  }

  function getSectionDef(sectionId: string) {
    return SECTION_DEFINITIONS.find(definition => definition.id === sectionId) || null
  }

  return {
    instruments,
    activeInstrumentId,
    activeInstrument,
    sections,
    overallConclusion,
    activeOverallConclusion,
    aggregateConclusion,
    hasFailedSection,
    failedSections,
    evidenceGaps,
    evidenceComplete,
    failedItemSummaries,
    allItems,
    totalRows,
    recalcConclusions,
    updateItem,
    addItem,
    removeItem,
    setSectionConclusion,
    setOverallConclusion,
    setActiveInstrument,
    updateInstrumentName,
    addInstrument,
    removeInstrument,
    syncFromSeeds,
    loadData,
    toJSON,
    toFlatRows,
    loadFromFlatRows,
    reset,
    getSectionMethodology,
    getSectionDef,
  }
}

export default useG6SppiTest
