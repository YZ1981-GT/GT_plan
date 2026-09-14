/**
 * F2-21 盘点计划问卷 — 对齐 Excel 1~22 题结构
 * 持久化：checklist_responses.item_id = F2-21-fields（JSON）
 */

export interface F21LocationRow {
  id: string
  location: string
  inventoryType: string
  sharePct: string
  countTime: string
}

export interface F21PersonnelRow {
  id: string
  name: string
  location: string
  role: string
  competence: string
  phone: string
}

export interface F21TextQuestion {
  id: string
  no: string
  label: string
  /** 步骤分组：prep | control | evaluate */
  group: 'prep' | 'control' | 'evaluate'
  hint?: string
}

export interface F21QuestionnaireData {
  version: 2
  locations: F21LocationRow[]
  personnel: F21PersonnelRow[]
  /** q3~q21、q22_1、q22_2 */
  answers: Record<string, string>
}

export const F21_TEXT_QUESTIONS: F21TextQuestion[] = [
  {
    id: 'q3',
    no: '3',
    label: '是否有专家参与？如何安排？',
    group: 'prep',
    hint: '贵金属、化学品、液体密度等需专家复核计量或质量时，应在此记录安排。',
  },
  {
    id: 'q4',
    no: '4',
    label: '是否召开盘点预备会议？如何安排任务与分工？',
    group: 'prep',
  },
  {
    id: 'q5',
    no: '5',
    label: '盘点期间存货如何整理与摆放？是否便于盘点？',
    group: 'prep',
  },
  {
    id: 'q6',
    no: '6',
    label: '是否存在第三方存货（如寄销商品）？如何识别与处理？',
    group: 'prep',
    hint: '应取得存放地点清单，关注第三方仓库及租赁合同是否隐含额外存放地点。',
  },
  {
    id: 'q7',
    no: '7',
    label: '残次、过时或毁损存货如何识别与存放？',
    group: 'prep',
  },
  {
    id: 'q8',
    no: '8',
    label: '原材料、在产品、产成品是否分开存放与盘点？',
    group: 'prep',
  },
  {
    id: 'q9',
    no: '9',
    label: '大宗或散装存货有无特殊盘点或折算程序？',
    group: 'prep',
  },
  {
    id: 'q10',
    no: '10',
    label: '相同存货存放于不同地点时，如何汇总？',
    group: 'prep',
  },
  {
    id: 'q11',
    no: '11',
    label: '盘点使用何种计量工具与方法？',
    group: 'prep',
  },
  {
    id: 'q12',
    no: '12',
    label: '在产品完工程度如何确认？料工费如何归集？',
    group: 'prep',
  },
  {
    id: 'q13',
    no: '13',
    label: '由第三方保管的存货如何盘点或函证？',
    group: 'control',
  },
  {
    id: 'q14',
    no: '14',
    label: '异地存放存货如何安排盘点？',
    group: 'control',
    hint: '多地点时宜考虑同时盘点或突击盘点，降低转移存货舞弊风险。',
  },
  {
    id: 'q15',
    no: '15',
    label: '存货收发截止如何控制？',
    group: 'control',
  },
  {
    id: 'q16',
    no: '16',
    label: '盘点期间存货移动如何控制？是否需要停止生产？',
    group: 'control',
  },
  {
    id: 'q17',
    no: '17',
    label: '盘点表单如何设计、使用与控制？记录形式是什么？是否预先编号？',
    group: 'control',
  },
  {
    id: 'q18',
    no: '18',
    label: '是否对盘点进行独立检查？永续盘存制下数量差异如何再盘？监督者是否记录检查情况？',
    group: 'control',
  },
  {
    id: 'q19',
    no: '19',
    label: '盘点结果如何汇总？',
    group: 'evaluate',
  },
  {
    id: 'q20',
    no: '20',
    label: '如何对盘盈或盘亏进行分析、调查与处理？',
    group: 'evaluate',
  },
  {
    id: 'q21',
    no: '21',
    label: '是否存在其他在盘点中需要注意的事项？',
    group: 'evaluate',
    hint: '如存在数量舞弊风险，可考虑不预先通知、扩大覆盖或聘请专家。',
  },
]

export const F21_EVAL_Q22_1_OPTIONS = [
  { label: '适当', value: 'yes' },
  { label: '部分适当', value: 'partial' },
  { label: '不适当', value: 'no' },
] as const

export const F21_STEP_LABELS = [
  '范围与时间',
  '人员组织',
  '盘点准备',
  '控制与截止',
  '汇总评价',
] as const

function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyLocationRow(): F21LocationRow {
  return { id: genId('loc'), location: '', inventoryType: '', sharePct: '', countTime: '' }
}

export function emptyPersonnelRow(): F21PersonnelRow {
  return { id: genId('per'), name: '', location: '', role: '', competence: '', phone: '' }
}

export function emptyQuestionnaire(): F21QuestionnaireData {
  const answers: Record<string, string> = { q22_1: '', q22_2: '' }
  for (const q of F21_TEXT_QUESTIONS) answers[q.id] = ''
  return {
    version: 2,
    locations: [emptyLocationRow()],
    personnel: [emptyPersonnelRow()],
    answers,
  }
}

function parseScheduleLine(line: string): Partial<F21LocationRow> | null {
  const text = line.trim()
  if (!text) return null
  const parts = text.split(/\s*[·|｜]\s*/).map((p) => p.trim()).filter(Boolean)
  if (parts.length >= 2) {
    const share = parts.find((p) => /占比/.test(p))?.replace(/占比|%/g, '').trim() || ''
    const time = parts.find((p) => /盘点/.test(p))?.replace(/^盘点/, '').trim()
      || parts.find((p) => /\d{4}/.test(p)) || ''
    const type = parts.find((p) => /原料|材料|在产|产成|商品|库存/.test(p)) || parts[1] || ''
    return {
      location: parts[0] || '',
      inventoryType: type === parts[0] ? (parts[1] || '') : type,
      sharePct: share,
      countTime: time,
    }
  }
  return { location: text, inventoryType: '', sharePct: '', countTime: '' }
}

/** 旧版扁平字段 / OO 地点行 → v2 问卷 */
export function migrateLegacyToQuestionnaire(
  parsed: Record<string, unknown> | null | undefined,
  legacyRowsRaw?: string | null,
): F21QuestionnaireData {
  const base = emptyQuestionnaire()
  if (!parsed && !legacyRowsRaw) return base

  // 已是 v2
  if (parsed && (parsed.version === 2 || Array.isArray(parsed.locations))) {
    return normalizeQuestionnaire(parsed)
  }

  const flat = (parsed || {}) as Record<string, string>
  const locations: F21LocationRow[] = []

  // 优先 OO 地点行
  if (legacyRowsRaw) {
    try {
      const rows = JSON.parse(legacyRowsRaw) as Array<{
        location?: string
        inventoryType?: string
        sharePct?: string
        countDate?: string
      }>
      if (Array.isArray(rows)) {
        for (const r of rows) {
          if (!r.location && !r.inventoryType) continue
          locations.push({
            id: genId('loc'),
            location: r.location || '',
            inventoryType: r.inventoryType || '',
            sharePct: r.sharePct != null ? String(r.sharePct) : '',
            countTime: r.countDate || '',
          })
        }
      }
    } catch { /* ignore */ }
  }

  if (!locations.length && flat.countSchedule) {
    for (const line of flat.countSchedule.split('\n')) {
      const row = parseScheduleLine(line)
      if (row) locations.push({ ...emptyLocationRow(), ...row })
    }
  }
  if (!locations.length && flat.warehouses) {
    for (const line of flat.warehouses.split('\n')) {
      const loc = line.trim()
      if (loc) locations.push({ ...emptyLocationRow(), location: loc })
    }
  }

  const personnel: F21PersonnelRow[] = []
  if (flat.auditors) {
    for (const line of flat.auditors.split(/[\n；;]/)) {
      const name = line.trim()
      if (name) personnel.push({ ...emptyPersonnelRow(), name, role: '项目组监盘' })
    }
  }
  if (flat.clientStaff) {
    for (const line of flat.clientStaff.split(/[\n；;]/)) {
      const name = line.trim()
      if (name) personnel.push({ ...emptyPersonnelRow(), name, role: '被审计单位' })
    }
  }

  const answers = { ...base.answers }
  if (flat.expertNeeded) answers.q3 = flat.expertNeeded
  if (flat.prepProcedure) answers.q17 = flat.prepProcedure
  if (flat.countMethod) answers.q4 = [answers.q4, flat.countMethod].filter(Boolean).join('\n')
  if (flat.remoteWarehouse) {
    answers.q13 = flat.remoteWarehouse
    answers.q14 = flat.remoteWarehouse
  }
  if (flat.fraudRisk) answers.q21 = flat.fraudRisk
  if (flat.inventoryTypes && !locations.some((l) => l.inventoryType)) {
    answers.q8 = [answers.q8, `存货类型：${flat.inventoryTypes}`].filter(Boolean).join('\n')
  }
  if (flat.coveragePct) {
    answers.q21 = [answers.q21, `监盘覆盖比例：${flat.coveragePct}`].filter(Boolean).join('\n')
  }

  return {
    version: 2,
    locations: locations.length ? locations : [emptyLocationRow()],
    personnel: personnel.length ? personnel : [emptyPersonnelRow()],
    answers,
  }
}

export function normalizeQuestionnaire(raw: unknown): F21QuestionnaireData {
  const base = emptyQuestionnaire()
  if (!raw || typeof raw !== 'object') return base
  const obj = raw as Record<string, unknown>

  if (obj.version !== 2 && !Array.isArray(obj.locations)) {
    return migrateLegacyToQuestionnaire(obj as Record<string, unknown>)
  }

  const locations = Array.isArray(obj.locations)
    ? (obj.locations as F21LocationRow[]).map((r) => ({
        id: r.id || genId('loc'),
        location: r.location || '',
        inventoryType: r.inventoryType || '',
        sharePct: r.sharePct != null ? String(r.sharePct) : '',
        countTime: r.countTime || (r as { countDate?: string }).countDate || '',
      }))
    : base.locations

  const personnel = Array.isArray(obj.personnel)
    ? (obj.personnel as F21PersonnelRow[]).map((r) => ({
        id: r.id || genId('per'),
        name: r.name || '',
        location: r.location || '',
        role: r.role || '',
        competence: r.competence || '',
        phone: r.phone || '',
      }))
    : base.personnel

  const srcAnswers = (obj.answers && typeof obj.answers === 'object'
    ? obj.answers
    : obj) as Record<string, string>
  const answers = { ...base.answers }
  for (const key of Object.keys(answers)) {
    if (srcAnswers[key] != null) answers[key] = String(srcAnswers[key])
  }

  return {
    version: 2,
    locations: locations.length ? locations : [emptyLocationRow()],
    personnel: personnel.length ? personnel : [emptyPersonnelRow()],
    answers,
  }
}

export function isQuestionnaireFilled(data: F21QuestionnaireData): {
  filled: number
  total: number
  q1: boolean
  q2: boolean
  q22: boolean
} {
  const q1 = data.locations.some((r) => r.location.trim() || r.inventoryType.trim())
  const q2 = data.personnel.some((r) => r.name.trim())
  let textFilled = 0
  for (const q of F21_TEXT_QUESTIONS) {
    if ((data.answers[q.id] || '').trim()) textFilled += 1
  }
  const q22_1 = !!(data.answers.q22_1 || '').trim()
  const q22_2 = !!(data.answers.q22_2 || '').trim()
  const filled = (q1 ? 1 : 0) + (q2 ? 1 : 0) + textFilled + (q22_1 ? 1 : 0) + (q22_2 ? 1 : 0)
  const total = 2 + F21_TEXT_QUESTIONS.length + 2
  return { filled, total, q1, q2, q22: q22_1 }
}

export function questionsByGroup(group: F21TextQuestion['group']): F21TextQuestion[] {
  return F21_TEXT_QUESTIONS.filter((q) => q.group === group)
}
