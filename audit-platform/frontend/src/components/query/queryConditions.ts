/**
 * queryConditions.ts — 业务视图结构化条件（advanced-query-linkage-closure 任务 29，design §4.2；R6.1、R6.2、R6.4，AQ-13 前端）
 *
 * 条件编辑器 `QueryConditionEditor.vue` 的数据形状与纯函数（单独成模块：页面版、弹窗（W3）与 vitest 共用，
 * 不在 `<script setup>` 里 export）。条件以 `{field, op, value}` + `logic` 发送（后端 `QueryRequest.conditions` /
 * `condition_logic`），由服务端转为参数化谓词；与模板 `config.conditions` 同形。改造前页面版把条件拼成
 * `{字段}_min` / `{字段}_max` / `{字段}_from` 之类的筛选键，后端不认（任何条件都被忽略），AND / OR 也不随请求发送。
 */

/** 本批条件编辑器提供的算子（后端 `OPERATOR_WHITELIST` 的子集；W3 再按列类型补「开头是」等） */
export type ConditionOp = 'eq' | 'like' | 'gt' | 'lt' | 'between' | 'is_null' | 'is_not_null'

export interface EditorCondition {
  field: string
  op: ConditionOp | string
  /** 输入框里的原文；介于写「起,止」 */
  value: string
}

export type ConditionLogic = 'and' | 'or'

export interface ConditionState {
  conditions: EditorCondition[]
  logic: ConditionLogic
}

/** 请求体里的一条条件（后端 `ConditionSpec`） */
export interface RequestCondition {
  field: string
  op: string
  value: unknown
}

export const CONDITION_OPS: ReadonlyArray<{ value: ConditionOp; label: string }> = [
  { value: 'eq', label: '等于' },
  { value: 'like', label: '包含' },
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
  { value: 'between', label: '介于（起,止）' },
  { value: 'is_null', label: '为空' },
  { value: 'is_not_null', label: '不为空' },
]

const NO_VALUE_OPS = new Set(['is_null', 'is_not_null'])
const RANGE_SPLIT = /[,，]/

/** 该算子要不要填值 */
export function needsConditionValue(op: string): boolean {
  return !NO_VALUE_OPS.has(op)
}

function rangeParts(value: string): string[] {
  return String(value ?? '').split(RANGE_SPLIT).map((s) => s.trim())
}

/** 编辑器条件 → 请求体条件：没选字段的行不发；为空 / 不为空不带值；介于发两个端点；其余发去首尾空白的原文（服务端按列类型转换） */
export function toRequestConditions(conditions: readonly EditorCondition[]): RequestCondition[] {
  const out: RequestCondition[] = []
  for (const c of conditions) {
    if (!c?.field || !c.op) continue
    if (!needsConditionValue(c.op)) out.push({ field: c.field, op: c.op, value: null })
    else if (c.op === 'between') out.push({ field: c.field, op: c.op, value: rangeParts(c.value).slice(0, 2) })
    else out.push({ field: c.field, op: c.op, value: String(c.value ?? '').trim() })
  }
  return out
}

/**
 * 第一个填得不完整的条件的原因（宿主据此禁用「查询」并显示原因）；都完整时返回空串。
 * 没选字段又填了值、该填值的没填、介于不是两个值，都算不完整。
 */
export function conditionsIncompleteReason(
  conditions: readonly EditorCondition[], labelOf: (field: string) => string = (f) => f,
): string {
  for (const [i, c] of conditions.entries()) {
    const value = String(c?.value ?? '').trim()
    if (!c?.field) {
      if (value) return `第 ${i + 1} 个条件未选择字段`
      continue
    }
    if (!needsConditionValue(c.op)) continue
    if (!value) return `条件「${labelOf(c.field)}」未填写值`
    if (c.op === 'between') {
      const parts = rangeParts(value)
      if (parts.length !== 2 || !parts[0] || !parts[1]) return `条件「${labelOf(c.field)}」请按「起,止」填写两个值`
    }
  }
  return ''
}

/** 旧写法的算子名 → 现名（页面版改造前保存的模板用 `operator` 键与 `contains`） */
const LEGACY_OPS: Readonly<Record<string, string>> = { contains: 'like' }

/** 模板里保存的条件 → 编辑器条件（兼容旧写法 `{field, operator, value}`；介于存成数组的拼回「起,止」） */
export function fromSavedConditions(raw: unknown): EditorCondition[] {
  if (!Array.isArray(raw)) return []
  const out: EditorCondition[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const op = String(r.op ?? r.operator ?? 'eq')
    const value = Array.isArray(r.value) ? r.value.join(',') : r.value === null || r.value === undefined ? '' : String(r.value)
    out.push({ field: String(r.field ?? ''), op: LEGACY_OPS[op] ?? op, value })
  }
  return out
}

/** 模板里保存的组合逻辑 → `and` / `or`（改造前存的是大写 AND / OR） */
export function normalizeConditionLogic(raw: unknown): ConditionLogic {
  return String(raw ?? '').toLowerCase() === 'or' ? 'or' : 'and'
}
