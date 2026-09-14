/**
 * 程序表 content → 父描述 + 子步骤（与后端 wp_program_sub_steps 对齐）
 */
export interface ProgramSubStep {
  no: number
  text: string
}

const STEP_LINE = /^[（(](\d+)[）)]\s*(.*)/
const STEP_INLINE = /[（(](\d+)[）)]\s*/g

export function parseProgramSubSteps(content: string): { parentDesc: string; subSteps: ProgramSubStep[] } {
  if (!content?.trim()) {
    return { parentDesc: '', subSteps: [] }
  }

  const text = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)

  const parentLines: string[] = []
  const subSteps: ProgramSubStep[] = []
  let inSteps = false

  for (const line of lines) {
    const m = line.match(STEP_LINE)
    if (m) {
      inSteps = true
      subSteps.push({ no: Number(m[1]), text: m[2] })
    } else if (inSteps && subSteps.length > 0) {
      subSteps[subSteps.length - 1].text += line
    } else {
      parentLines.push(line)
    }
  }

  if (subSteps.length > 0) {
    let parentDesc = parentLines.join('\n').trim()
    if (!parentDesc) {
      const m0 = text.match(STEP_INLINE)
      if (m0?.index != null) {
        parentDesc = text.slice(0, m0.index).trim().replace(/[：:]\s*$/, '')
      }
    }
    return { parentDesc: parentDesc || lines[0] || text, subSteps }
  }

  const inlineMatches = [...text.matchAll(STEP_INLINE)]
  if (inlineMatches.length >= 1) {
    const parentDesc = text.slice(0, inlineMatches[0].index!).trim().replace(/[：:]\s*$/, '')
    const parsed: ProgramSubStep[] = []
    inlineMatches.forEach((m, i) => {
      const end = i + 1 < inlineMatches.length ? inlineMatches[i + 1].index! : text.length
      const stepText = text.slice(m.index! + m[0].length, end).trim()
      if (stepText) parsed.push({ no: Number(m[1]), text: stepText })
    })
    if (parsed.length > 0) {
      return { parentDesc: parentDesc || text, subSteps: parsed }
    }
  }

  return { parentDesc: text, subSteps: [] }
}

export function normalizeAProgramRow<T extends Record<string, unknown>>(row: T): T & { sub_steps?: ProgramSubStep[] } {
  const existing = row.sub_steps as ProgramSubStep[] | undefined
  if (Array.isArray(existing) && existing.length > 0) {
    return row as T & { sub_steps?: ProgramSubStep[] }
  }
  const desc = String(row.program_desc ?? row.content ?? '').trim()
  if (!desc) return row as T & { sub_steps?: ProgramSubStep[] }
  const { parentDesc, subSteps } = parseProgramSubSteps(desc)
  if (subSteps.length === 0) return row as T & { sub_steps?: ProgramSubStep[] }
  return {
    ...row,
    program_desc: parentDesc,
    sub_steps: subSteps,
  }
}

export function normalizeAProgramRows<T extends Record<string, unknown>>(rows: T[]): Array<T & { sub_steps?: ProgramSubStep[] }> {
  return rows.map(r => normalizeAProgramRow(r))
}
