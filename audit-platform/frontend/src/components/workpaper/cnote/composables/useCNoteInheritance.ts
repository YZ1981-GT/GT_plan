/**
 * useCNoteInheritance.ts — C 类附注披露嵌套表「子表↔主表合计联动校验」composable
 *
 * 从 GtCNoteTable.vue 剪切 inheritance_rules 实时校验逻辑（design §1.4 引用的
 * ~1052-1191 行，Task 2 后实际位于 710-993 行附近）：
 *   - `inheritanceRules`（computed，applicable_when.standard 过滤）
 *   - `ruleStatuses`（computed，遍历规则求值）
 *   - `findSubTable` / `evaluateRule` / `computeRuleSource` / `computeRuleTarget` / `filterRows`
 *   - `ruleStatusForSubTable`
 * 逐字搬运，零行为改变。
 *
 * 入参为三个响应式引用（schema / subTableData / currentStandardSubClass），
 * 保持单一数据源——composable 不持有状态副本（design D1）。
 *
 * 注：`ruleStatusTagType` / `ruleStatusIcon`（纯展示映射）不在此 composable，
 * 它们将随 Task 6 迁入 CNoteInheritanceBadge.vue（design §1.4）。
 *
 * spec: gt-c-note-table-shrink Task 3
 */
import { computed, type Ref } from 'vue'
import { formatAmount } from '@/utils/formatAmount'
import type {
  CNoteTableSchema,
  InheritanceRule,
  InheritanceRuleSourceTarget,
  RowData,
  RuleStatus,
  SubClass,
  SubTableSchema,
} from '../../GtCNoteTable.types'
import { escapeNumber } from '../cnoteHelpers'

export function useCNoteInheritance(
  schema: Ref<CNoteTableSchema>,
  subTableData: Ref<Record<string, RowData[]>>,
  currentStandardSubClass: Ref<SubClass>,
) {
  const inheritanceRules = computed<InheritanceRule[]>(() => {
    const arr = schema.value?.inheritance_rules ?? []
    if (!Array.isArray(arr)) return []
    return arr.filter(rule => {
      if (rule.applicable_when?.standard) {
        return rule.applicable_when.standard === currentStandardSubClass.value
      }
      return true
    })
  })

  const ruleStatuses = computed<RuleStatus[]>(() => {
    const out: RuleStatus[] = []
    for (const rule of inheritanceRules.value) {
      const status = evaluateRule(rule)
      if (status) out.push(status)
    }
    return out
  })

  function findSubTable(id: string | undefined): SubTableSchema | undefined {
    if (!id) return undefined
    return (schema.value?.sub_tables ?? []).find(s => s.id === id)
  }

  function evaluateRule(rule: InheritanceRule): RuleStatus | null {
    const src = rule.source
    const tgt = rule.target

    // 仅同 sheet 内 sub_table → sub_table 规则可前端实时评估
    if (!src.sub_table || !tgt.sub_table) {
      return {
        ruleId: rule.id,
        subTableId: src.sub_table || tgt.sub_table || '',
        status: 'na',
        label: '外部勾稽',
        tooltip: rule.description || '此规则关联外部数据源（试算表/其它底稿），需保存后服务端校验',
      }
    }

    const sourceValue = computeRuleSource(rule)
    const targetValue = computeRuleTarget(rule)

    if (sourceValue === null || targetValue === null) {
      return null
    }

    const diff = sourceValue - targetValue
    const tolerance = 0.01

    if (rule.validation === 'equal') {
      if (Math.abs(diff) <= tolerance) {
        return {
          ruleId: rule.id,
          subTableId: src.sub_table,
          status: 'ok',
          label: '勾稽一致',
          tooltip: rule.description || `${src.sub_table} → ${tgt.sub_table} 勾稽一致`,
          diff: 0,
        }
      }
      return {
        ruleId: rule.id,
        subTableId: src.sub_table,
        status: rule.on_mismatch === 'error' ? 'mismatch' : 'warning',
        label: `差异 ${formatAmount(diff)}`,
        tooltip: `${rule.description || src.sub_table + ' → ' + tgt.sub_table}\n源值: ${formatAmount(sourceValue)}\n目标值: ${formatAmount(targetValue)}`,
        diff,
      }
    }

    if (rule.validation === 'less_than_or_equal') {
      if (sourceValue <= targetValue + tolerance) {
        return {
          ruleId: rule.id,
          subTableId: src.sub_table,
          status: 'ok',
          label: '上限通过',
          tooltip: rule.description || `${src.sub_table} ≤ ${tgt.sub_table}`,
          diff: 0,
        }
      }
      return {
        ruleId: rule.id,
        subTableId: src.sub_table,
        status: rule.on_mismatch === 'error' ? 'mismatch' : 'warning',
        label: `超限 ${formatAmount(sourceValue - targetValue)}`,
        tooltip: `${rule.description || ''}\n源值 ${formatAmount(sourceValue)} > 目标值 ${formatAmount(targetValue)}`,
        diff: sourceValue - targetValue,
      }
    }

    return null
  }

  function computeRuleSource(rule: InheritanceRule): number | null {
    const src = rule.source
    if (!src.sub_table) return null
    const rows = subTableData.value[src.sub_table] ?? []

    if (src.sum_field) {
      const filtered = filterRows(rows, src)
      let sum = 0
      for (const r of filtered) {
        const n = escapeNumber(r[src.sum_field])
        if (n != null) sum += n
      }
      return sum
    }

    if (src.row && src.column) {
      const st = findSubTable(src.sub_table)
      const col = st?.columns?.[src.column]
      if (!col) return null
      const stored = rows.find(r => r.id === src.row)
      if (!stored) return null
      return escapeNumber(stored[col.field])
    }

    return null
  }

  function computeRuleTarget(rule: InheritanceRule): number | null {
    const tgt = rule.target
    if (!tgt.sub_table || !tgt.row || !tgt.column) return null
    const st = findSubTable(tgt.sub_table)
    const col = st?.columns?.[tgt.column]
    if (!col) return null
    const rows = subTableData.value[tgt.sub_table] ?? []
    const stored = rows.find(r => r.id === tgt.row)
    if (!stored) return null
    return escapeNumber(stored[col.field])
  }

  function filterRows(rows: RowData[], src: InheritanceRuleSourceTarget): RowData[] {
    let result = rows
    if (Array.isArray(src.exclude_rows) && src.exclude_rows.length) {
      const set = new Set(src.exclude_rows)
      result = result.filter(r => !r.id || !set.has(String(r.id)))
    }
    if (src.group_by) {
      const [field, value] = src.group_by.split('=')
      if (field && value !== undefined) {
        result = result.filter(r => String(r[field.trim()] ?? '') === value.trim())
      }
    }
    if (src.filter) {
      const [field, raw] = src.filter.split('=')
      if (field && raw !== undefined) {
        const want = raw.trim()
        result = result.filter(r => {
          const v = r[field.trim()]
          if (want === 'true') return v === true || v === 'true' || v === 1
          if (want === 'false') return v === false || v === 'false' || v === 0 || v == null
          return String(v ?? '') === want
        })
      }
    }
    return result
  }

  function ruleStatusForSubTable(stId: string): RuleStatus[] {
    return ruleStatuses.value.filter(r => r.subTableId === stId)
  }

  return { ruleStatuses, ruleStatusForSubTable }
}
