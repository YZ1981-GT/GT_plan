/**
 * 将 F2-22 AI 生成正文解析为结构化字段，供「填入」回写各文本框。
 * 优先 JSON；兼容 Markdown 章节（二次编辑仍走 el-input）。
 */

const FIELD_KEYS = [
  'entityName',
  'auditYear',
  'bsDate',
  'purpose',
  'scope',
  'warehouses',
  'countDate',
  'auditors',
  'clientStaff',
  'assignment',
  'prep',
  'inventoryComposition',
  'countMethod',
  'requirements',
  'remoteWarehouse',
  'fraudRisk',
  'expertNeeded',
  'teamName',
  'planDate',
] as const

export type F2PlanAiFieldId = (typeof FIELD_KEYS)[number]

export interface F2PlanAiParseResult {
  fields: Partial<Record<F2PlanAiFieldId, string>>
  /** 写入「监盘计划结论」的摘要 */
  conclusion: string
}

function stripMd(text: string): string {
  return text
    .replace(/\*\*/g, '')
    .replace(/^#+\s*/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .trim()
}

function tryParseJson(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim()
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const candidate = fence ? fence[1].trim() : trimmed
  const start = candidate.indexOf('{')
  const end = candidate.lastIndexOf('}')
  if (start < 0 || end <= start) return null
  try {
    const obj = JSON.parse(candidate.slice(start, end + 1))
    return obj && typeof obj === 'object' ? (obj as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function fromJson(obj: Record<string, unknown>): F2PlanAiParseResult {
  const fields: Partial<Record<F2PlanAiFieldId, string>> = {}
  for (const key of FIELD_KEYS) {
    const v = obj[key]
    if (v != null && String(v).trim()) fields[key] = String(v).trim()
  }
  const conclusion =
    String(obj.planConclusion || obj.conclusion || obj.auditNote || '').trim()
  return { fields, conclusion }
}

/** Markdown 章节标题 → 字段 */
const MD_SECTION_MAP: Array<{ pattern: RegExp; field: F2PlanAiFieldId | 'bundle-scope-purpose' }> = [
  { pattern: /监盘目的|审计目标/, field: 'purpose' },
  { pattern: /监盘范围|覆盖范围/, field: 'scope' },
  { pattern: /监盘地点|物理地点|存放地点/, field: 'warehouses' },
  { pattern: /监盘时间|时间安排/, field: 'countDate' },
  { pattern: /项目组|监盘人员(?!配合)/, field: 'auditors' },
  { pattern: /被审计单位配合|客户人员|陪同/, field: 'clientStaff' },
  { pattern: /分工/, field: 'assignment' },
  { pattern: /监盘前准备|准备工作/, field: 'prep' },
  { pattern: /存货构成|类别占比|存放分布/, field: 'inventoryComposition' },
  { pattern: /监盘方式|抽盘/, field: 'countMethod' },
  { pattern: /监盘要求|覆盖率|取证/, field: 'requirements' },
  { pattern: /异地|代管/, field: 'remoteWarehouse' },
  { pattern: /舞弊/, field: 'fraudRisk' },
  { pattern: /专家/, field: 'expertNeeded' },
  { pattern: /监盘范围与目标|范围与目标/, field: 'bundle-scope-purpose' },
]

function extractMeta(text: string, fields: Partial<Record<F2PlanAiFieldId, string>>): void {
  const entity = text.match(/\*?\*?被审计单位\*?\*?[：:]\s*(.+)/)
  if (entity) fields.entityName = stripMd(entity[1]).split('\n')[0]
  const year = text.match(/\*?\*?审计年度\*?\*?[：:]\s*(\d{4})/)
  if (year) fields.auditYear = year[1]
  const bs = text.match(/\*?\*?(?:资产负债表日|基准日)\*?\*?[：:]\s*(.+)/)
  if (bs) fields.bsDate = stripMd(bs[1]).split('\n')[0]
  const planDate = text.match(/\*?\*?编制日期\*?\*?[：:]\s*(.+)/)
  if (planDate) fields.planDate = stripMd(planDate[1]).split('\n')[0]
  const team = text.match(/\*?\*?(?:编制人|项目组)\*?\*?[：:]\s*(.+)/)
  if (team && !fields.teamName) fields.teamName = stripMd(team[1]).split('\n')[0]
}

function fromMarkdown(raw: string): F2PlanAiParseResult {
  const fields: Partial<Record<F2PlanAiFieldId, string>> = {}
  extractMeta(raw, fields)

  // 按 ### / ## / 一、 切段
  const parts = raw.split(/(?=^#{1,3}\s|^[一二三四五六七八九十]+[、．.])/m)
  for (const part of parts) {
    const head = part.split('\n')[0] || ''
    const body = stripMd(part.replace(head, '')).trim()
    if (!body) continue
    let matched: (typeof MD_SECTION_MAP)[number] | undefined
    for (const rule of MD_SECTION_MAP) {
      if (rule.pattern.test(head) || rule.pattern.test(part.slice(0, 80))) {
        matched = rule
        break
      }
    }
    if (!matched) continue
    if (matched.field === 'bundle-scope-purpose') {
      // 「范围与目标」合段：拆目标/范围子块
      const purposeBit = body.match(/(?:审计目标|监盘目的)[：:]?\s*([\s\S]*?)(?=覆盖范围|监盘范围|$)/)
      const scopeBit = body.match(/(?:覆盖范围|监盘范围)[：:]?\s*([\s\S]*?)(?=审计目标|监盘目的|$)/)
      if (purposeBit?.[1]?.trim()) fields.purpose = stripMd(purposeBit[1])
      if (scopeBit?.[1]?.trim()) fields.scope = stripMd(scopeBit[1])
      if (!fields.purpose && !fields.scope) {
        fields.purpose = body
        fields.scope = body
      }
      // 地点常嵌在覆盖范围内
      const loc = body.match(/(?:物理地点|存放地点)[：:]?\s*([\s\S]*?)(?=存货类别|权属|$)/)
      if (loc?.[1]?.trim()) fields.warehouses = stripMd(loc[1])
    } else {
      const id = matched.field
      fields[id] = fields[id] ? `${fields[id]}\n${body}` : body
    }
  }

  // 若几乎没切开，整篇落入 purpose，避免「填入」空操作
  const filled = Object.keys(fields).filter((k) => fields[k as F2PlanAiFieldId])
  if (filled.length <= 2) {
    const cleaned = stripMd(raw)
    if (cleaned && !fields.purpose) fields.purpose = cleaned.slice(0, 2000)
  }

  const conclusion = [
    fields.purpose ? `目的：${fields.purpose.slice(0, 80)}` : '',
    fields.scope ? `范围：${fields.scope.slice(0, 80)}` : '',
    fields.requirements ? `要求：${fields.requirements.slice(0, 80)}` : '',
  ]
    .filter(Boolean)
    .join('\n')

  return { fields, conclusion }
}

/** 解析 AI 正文 → 字段补丁 + 结论 */
export function parseF2PlanAiContent(raw: string): F2PlanAiParseResult {
  if (!raw?.trim()) return { fields: {}, conclusion: '' }
  const asJson = tryParseJson(raw)
  if (asJson) {
    const fromJ = fromJson(asJson)
    if (Object.keys(fromJ.fields).length > 0) return fromJ
  }
  return fromMarkdown(raw)
}

export default parseF2PlanAiContent
