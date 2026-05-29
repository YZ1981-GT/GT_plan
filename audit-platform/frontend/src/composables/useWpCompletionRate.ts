/**
 * useWpCompletionRate — 底稿填写完成度计算 composable
 *
 * 按组件类型分化计算逻辑：
 * - A 类：已决策程序数 / 总程序数（status !== 'pending'）
 * - D 类：已回答问题数 / 总问题数（value !== null && value !== ''）
 * - E 类：已完成步骤 / 总步骤（step.completed === true）
 * - B 类：已填编制信息字段 / 总必填字段
 * - C 类：已填子表行数 / schema 定义最小行数
 *
 * @example
 * const { rate } = useWpCompletionRate(componentType, schema, htmlData)
 * // rate.value => { filled: 3, total: 5, percentage: 60, category: 'partial' }
 *
 * Validates: Requirements US-8
 */
import { computed, type Ref } from 'vue'
import type { WpComponentType } from '@/composables/useWpRenderer'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface CompletionRate {
  filled: number       // 已填必填字段数
  total: number        // 总必填字段数
  percentage: number   // 0~100
  category: 'empty' | 'partial' | 'complete'
}

// ─── 内部计算函数（纯函数，便于测试） ─────────────────────────────────────────

/**
 * A 类：已决策程序数 / 总程序数
 * programs 数组中 status !== 'pending' 视为已决策
 */
export function calcACompletion(htmlData: Record<string, any>): CompletionRate {
  const programs: any[] = htmlData?.programs ?? []
  if (programs.length === 0) return { filled: 0, total: 0, percentage: 0, category: 'empty' }

  const total = programs.length
  const filled = programs.filter(p => p.status !== 'pending' && p.status != null).length
  return buildRate(filled, total)
}

/**
 * D 类：已回答问题数 / 总问题数
 * 遍历 fields/questions/items，value !== null && value !== '' 视为已答
 */
export function calcDCompletion(htmlData: Record<string, any>): CompletionRate {
  // D 类数据可能在 fields / questions / items 中
  const fields: any[] = htmlData?.fields ?? htmlData?.questions ?? htmlData?.items ?? []
  if (fields.length === 0) return { filled: 0, total: 0, percentage: 0, category: 'empty' }

  const total = fields.length
  const filled = fields.filter(f => {
    const val = f.value ?? f.answer ?? f.content
    return val !== null && val !== undefined && val !== ''
  }).length
  return buildRate(filled, total)
}

/**
 * E 类：已完成步骤 / 总步骤
 * steps 数组中 step.completed === true 视为已完成
 */
export function calcECompletion(htmlData: Record<string, any>): CompletionRate {
  const steps: any[] = htmlData?.steps ?? []
  if (steps.length === 0) return { filled: 0, total: 0, percentage: 0, category: 'empty' }

  const total = steps.length
  const filled = steps.filter(s => s.completed === true).length
  return buildRate(filled, total)
}

/**
 * B 类：已填编制信息字段 / 总必填字段
 * required_fields 中 value 非空视为已填
 */
export function calcBCompletion(htmlData: Record<string, any>, schema: Record<string, any>): CompletionRate {
  const requiredFields: string[] = schema?.required_fields ?? []
  if (requiredFields.length === 0) return { filled: 0, total: 0, percentage: 100, category: 'complete' }

  const data = htmlData?.fields ?? htmlData ?? {}
  const total = requiredFields.length
  const filled = requiredFields.filter(fieldName => {
    const val = data[fieldName]
    return val !== null && val !== undefined && val !== ''
  }).length
  return buildRate(filled, total)
}

/**
 * C 类：已填子表行数 / schema 定义最小行数
 */
export function calcCCompletion(htmlData: Record<string, any>, schema: Record<string, any>): CompletionRate {
  const minRows: number = schema?.min_rows ?? 1
  const rows: any[] = htmlData?.rows ?? htmlData?.table_data ?? []
  const filledRows = rows.filter(r => {
    // 至少有一个非空字段视为已填行
    if (!r || typeof r !== 'object') return false
    return Object.values(r).some(v => v !== null && v !== undefined && v !== '')
  }).length

  const total = Math.max(minRows, 1)
  const filled = Math.min(filledRows, total)
  return buildRate(filled, total)
}

/**
 * 构建 CompletionRate 对象
 */
export function buildRate(filled: number, total: number): CompletionRate {
  if (total === 0) return { filled: 0, total: 0, percentage: 0, category: 'empty' }
  const percentage = Math.round((filled / total) * 100)
  let category: CompletionRate['category'] = 'partial'
  if (percentage === 0) category = 'empty'
  else if (percentage >= 100) category = 'complete'
  return { filled, total, percentage: Math.min(percentage, 100), category }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpCompletionRate(
  componentType: Ref<WpComponentType | string>,
  schema: Ref<Record<string, any>>,
  htmlData: Ref<Record<string, any>>,
) {
  const rate = computed<CompletionRate>(() => {
    const type = componentType.value
    const data = htmlData.value ?? {}
    const schemaVal = schema.value ?? {}

    switch (type) {
      case 'a-program-console':
        return calcACompletion(data)
      case 'd-form-table':
      case 'd-form-paragraph':
      case 'd-form-qa':
      case 'd-form-confirmation':
      case 'd-form-review':
        return calcDCompletion(data)
      case 'e-control-test':
        return calcECompletion(data)
      case 'b-index':
        return calcBCompletion(data, schemaVal)
      case 'c-note-table':
        return calcCCompletion(data, schemaVal)
      default:
        return { filled: 0, total: 0, percentage: 0, category: 'empty' as const }
    }
  })

  return { rate }
}
