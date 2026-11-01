/**
 * queryConditions.ts — 业务视图结构化条件（advanced-query-linkage-closure 任务 29，design §4.2；R6.1、R6.2、R6.4，AQ-13 前端）
 *
 * 条件编辑器 `QueryConditionEditor.vue` 的数据形状与纯函数（单独成模块：页面版、弹窗（W3）与 vitest 共用，
 * 不在 `<script setup>` 里 export）。条件以 `{field, op, value}` + `logic` 发送（后端 `QueryRequest.conditions` /
 * `condition_logic`），由服务端转为参数化谓词；与模板 `config.conditions` 同形。改造前页面版把条件拼成
 * `{字段}_min` / `{字段}_max` / `{字段}_from` 之类的筛选键，后端不认（任何条件都被忽略），AND / OR 也不随请求发送。
 */

/** 条件编辑器支持的字段类型（来自指标树叶子 `condition_fields`） */
export type QueryFieldDtype = 'text' | 'number' | 'date' | 'bool'
export interface ConditionField { key: string; dtype: QueryFieldDtype }
export type ConditionFieldInput = ConditionField | string

export type ConditionOp =
  | 'eq' | 'like' | 'starts_with' | 'gt' | 'gte' | 'lt' | 'lte' | 'between'
  | 'is_null' | 'is_not_null' | 'is_blank' | 'weekday_in'

export interface EditorCondition {
  field: string
  op: ConditionOp | string
  /** 普通 / 区间输入为原文；星期多选为 0..6 数组 */
  value: string | number[]
  /** 服务端解析参数后附带；用户改字段、算子或值时清除 */
  params?: string[]
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

export interface ConditionOperator { value: ConditionOp; label: string }

const TEXT_OPS: readonly ConditionOperator[] = [
  { value: 'eq', label: '等于' },
  { value: 'like', label: '包含' },
  { value: 'starts_with', label: '开头是' },
  { value: 'is_null', label: '为空' },
  { value: 'is_not_null', label: '不为空' },
  { value: 'is_blank', label: '为空或空白' },
]
const NUMBER_OPS: readonly ConditionOperator[] = [
  { value: 'eq', label: '等于' },
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '小于等于' },
  { value: 'between', label: '介于（起,止）' },
  { value: 'is_null', label: '为空' },
  { value: 'is_not_null', label: '不为空' },
]
const DATE_OPS: readonly ConditionOperator[] = [
  ...NUMBER_OPS,
  { value: 'weekday_in', label: '星期为' },
]
const BOOL_OPS: readonly ConditionOperator[] = [
  { value: 'eq', label: '等于' },
  { value: 'is_null', label: '为空' },
  { value: 'is_not_null', label: '不为空' },
]

const OPS_BY_DTYPE: Readonly<Record<QueryFieldDtype, readonly ConditionOperator[]>> = {
  text: TEXT_OPS, number: NUMBER_OPS, date: DATE_OPS, bool: BOOL_OPS,
}

/** 预置模板允许使用的编辑器算子全集；与按 dtype 展示的集合由同一常量生成。 */
export const EDITOR_OPS: ReadonlySet<ConditionOp> = new Set(
  Object.values(OPS_BY_DTYPE).flat().map((item) => item.value),
)
/** 兼容既有导入：现在表示编辑器算子全集；组件实际按 dtype 调 `conditionOpsForDtype`。 */
export const CONDITION_OPS: readonly ConditionOperator[] = [...new Map(
  Object.values(OPS_BY_DTYPE).flat().map((item) => [item.value, item]),
).values()]

export const WEEKDAY_OPTIONS = [
  { value: 1, label: '周一' }, { value: 2, label: '周二' }, { value: 3, label: '周三' },
  { value: 4, label: '周四' }, { value: 5, label: '周五' }, { value: 6, label: '周六' },
  { value: 0, label: '周日' },
] as const

export function conditionOpsForDtype(dtype: QueryFieldDtype | string | undefined): readonly ConditionOperator[] {
  return OPS_BY_DTYPE[dtype as QueryFieldDtype] ?? TEXT_OPS
}

const NO_VALUE_OPS = new Set(['is_null', 'is_not_null', 'is_blank'])
const RANGE_SPLIT = /[,，]/

/** 该算子要不要填值 */
export function needsConditionValue(op: string): boolean {
  return !NO_VALUE_OPS.has(op)
}

function rangeParts(value: EditorCondition['value']): string[] {
  if (Array.isArray(value)) return value.map(String)
  return String(value ?? '').split(RANGE_SPLIT).map((s) => s.trim())
}

function weekdayValues(value: EditorCondition['value']): number[] {
  if (Array.isArray(value)) return value.map(Number).filter((item) => Number.isInteger(item))
  if (!String(value ?? '').trim()) return []
  return String(value).split(RANGE_SPLIT).map((item) => Number(item.trim())).filter((item) => Number.isInteger(item))
}

/** 编辑器条件 → 请求体条件：只发 field / op / value，参数来源标记绝不进入执行请求。 */
export function toRequestConditions(conditions: readonly EditorCondition[]): RequestCondition[] {
  const out: RequestCondition[] = []
  for (const c of conditions) {
    if (!c?.field || !c.op) continue
    if (!needsConditionValue(c.op)) out.push({ field: c.field, op: c.op, value: null })
    else if (c.op === 'between') out.push({ field: c.field, op: c.op, value: rangeParts(c.value).slice(0, 2) })
    else if (c.op === 'weekday_in') out.push({ field: c.field, op: c.op, value: weekdayValues(c.value) })
    else out.push({ field: c.field, op: c.op, value: String(c.value ?? '').trim() })
  }
  return out
}

/**
 * 编辑器条件 → 模板持久化条件。有 params 的解析值恢复成 `$param` 占位，其余保存当前字面值。
 * 返回形状仍只有 field / op / value，不把运行时来源标记写成额外契约字段。
 */
export function toSavedConditions(conditions: readonly EditorCondition[]): RequestCondition[] {
  const out: RequestCondition[] = []
  for (const condition of conditions) {
    const [saved] = toRequestConditions([condition])
    if (!saved) continue
    const params = condition.params?.filter(Boolean) ?? []
    if (!params.length || !needsConditionValue(saved.op)) {
      out.push(saved)
      continue
    }
    if (saved.op === 'between') {
      const literals = Array.isArray(saved.value) ? saved.value : []
      out.push({ ...saved, value: [
        params[0] ? { $param: params[0] } : literals[0],
        params[1] ? { $param: params[1] } : literals[1],
      ] })
    } else {
      out.push({ ...saved, value: { $param: params[0] } })
    }
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
    const hasValue = Array.isArray(c?.value) ? c.value.length > 0 : Boolean(String(c?.value ?? '').trim())
    if (!c?.field) {
      if (hasValue) return `第 ${i + 1} 个条件未选择字段`
      continue
    }
    if (!needsConditionValue(c.op)) continue
    if (!hasValue) return `条件「${labelOf(c.field)}」未填写值`
    if (c.op === 'between') {
      const parts = rangeParts(c.value)
      if (parts.length !== 2 || !parts[0]?.trim() || !parts[1]?.trim()) {
        return `条件「${labelOf(c.field)}」请按「起,止」填写两个值`
      }
    }
  }
  return ''
}

/** 旧写法的算子名 → 现名（页面版改造前保存的模板用 `operator` 键与 `contains`） */
const LEGACY_OPS: Readonly<Record<string, string>> = { contains: 'like' }

/** 模板里保存的条件 → 编辑器条件（兼容旧写法，并保留服务端解析时附带的 params 来源标记）。 */
export function fromSavedConditions(raw: unknown): EditorCondition[] {
  if (!Array.isArray(raw)) return []
  const out: EditorCondition[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const op = String(r.op ?? r.operator ?? 'eq')
    const explicitParams = Array.isArray(r.params) ? r.params.filter((p): p is string => typeof p === 'string' && p !== '') : []
    const placeholderParams: string[] = []
    const displayPart = (part: unknown): string => {
      if (part && typeof part === 'object' && typeof (part as Record<string, unknown>).$param === 'string') {
        placeholderParams.push(String((part as Record<string, unknown>).$param))
        return ''
      }
      return part === null || part === undefined ? '' : String(part)
    }
    let value: EditorCondition['value']
    if ((LEGACY_OPS[op] ?? op) === 'weekday_in' && Array.isArray(r.value)) {
      value = r.value.map(Number).filter((part) => Number.isInteger(part))
    } else {
      value = Array.isArray(r.value) ? r.value.map(displayPart).join(',') : displayPart(r.value)
    }
    const params = explicitParams.length ? explicitParams : placeholderParams
    out.push({
      field: String(r.field ?? ''), op: LEGACY_OPS[op] ?? op, value,
      ...(params.length ? { params } : {}),
    })
  }
  return out
}

/** 模板里保存的组合逻辑 → `and` / `or`（改造前存的是大写 AND / OR） */
export function normalizeConditionLogic(raw: unknown): ConditionLogic {
  return String(raw ?? '').toLowerCase() === 'or' ? 'or' : 'and'
}
