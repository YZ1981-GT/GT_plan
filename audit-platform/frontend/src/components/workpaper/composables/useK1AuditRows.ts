/**
 * useK1AuditRows.ts — K1 检查类底稿通用「动态行明细表 + 审计说明 + 结论」状态
 *
 * 适用于源模板中「审计目标 + 明细表(动态行) + 审计说明 + 审计结论」范式的检查表：
 *   K1-9  坏账准备转回/收回/核销检查表（双表）
 *   K1-10 长期未收回款项检查表
 *   K1-11 关联方及交易检查表
 *
 * 每个 sheet 用一个/多个 table key 管理动态行；列定义由组件层声明。
 * 持久化为单一 JSON 存 checklist_responses。
 */
import { ref, type Ref } from 'vue'

export type AuditRow = Record<string, any> & { id: string }

function newRow(defaults: Record<string, any> = {}): AuditRow {
  return { id: `k1r-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, ...defaults }
}

export function useK1AuditRows(opts: {
  allResponses: Ref<Map<string, any>>
  itemId: string
  /** 表键列表，如 ['reversal','writeoff'] 或 ['rows'] */
  tableKeys: string[]
  /** 各表的行默认值 */
  rowDefaults?: Record<string, Record<string, any>>
}) {
  const tables = ref<Record<string, AuditRow[]>>(
    Object.fromEntries(opts.tableKeys.map(k => [k, []]))
  )
  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  function load(): void {
    const stored = opts.allResponses.value.get(opts.itemId)
    const raw = stored?.remark ?? stored?.value
    if (!raw) return
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      for (const k of opts.tableKeys) {
        if (Array.isArray(data.tables?.[k])) {
          tables.value[k] = data.tables[k].map((r: any) => ({ ...newRow(), ...r }))
        }
      }
      auditNote.value = data.auditNote ?? ''
      conclusion.value = data.conclusion ?? ''
      conclusionOption.value = data.conclusionOption ?? ''
    } catch {
      // 忽略损坏
    }
  }

  function addRow(tableKey: string): void {
    const defaults = opts.rowDefaults?.[tableKey] ?? {}
    tables.value[tableKey]?.push(newRow(defaults))
  }

  function removeRow(tableKey: string, id: string): void {
    if (tables.value[tableKey]) {
      tables.value[tableKey] = tables.value[tableKey].filter(r => r.id !== id)
    }
  }

  /** 数字列求和 */
  function columnSum(tableKey: string, col: string): number {
    return (tables.value[tableKey] ?? []).reduce((s, r) => s + (Number(r[col]) || 0), 0)
  }

  function serialize(): string {
    return JSON.stringify({
      tables: tables.value,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  return { tables, auditNote, conclusion, conclusionOption, load, addRow, removeRow, columnSum, serialize }
}

/** 通用结论模板（其他应收款检查类） */
export const K1_CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '未见异常。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}
