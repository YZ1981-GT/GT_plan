<!--
  QueryConditionEditor — 业务视图条件编辑器（advanced-query-linkage-closure 任务 29，design §4.2；R6.1、R6.2、R6.4，AQ-13 前端）

  v-model `{conditions: {field, op, value}[], logic}`，与模板 `config.conditions` 同形（W3 起弹窗复用）。字段显示中文列名
  （`resolveColumnLabel`，按数据源）；条件值框不窄于 120px、条件行可换行；数据源不支持条件（附注表格、合并工作底稿、底稿
  选区）时整块禁用并说明原因。纯函数与类型在 `queryConditions.ts`。
-->
<template>
  <div class="gt-qce" :class="{ 'is-disabled': disabled }" data-testid="cq-condition-editor">
    <div class="gt-qce-head">
      <span class="gt-qce-title">条件筛选</span>
      <el-radio-group
        :model-value="modelValue.logic"
        size="small"
        :disabled="disabled"
        aria-label="条件组合方式"
        @update:model-value="(v: unknown) => emitState({ logic: v === 'or' ? 'or' : 'and' })"
      >
        <el-radio-button value="and">全部满足（AND）</el-radio-button>
        <el-radio-button value="or">任一满足（OR）</el-radio-button>
      </el-radio-group>
    </div>
    <el-alert
      v-for="notice in notices"
      :key="notice"
      :title="notice"
      type="info"
      :closable="false"
      show-icon
      class="gt-qce-notice"
      data-testid="cq-condition-notice"
    />
    <div v-if="disabled && disabledReason" class="gt-qce-reason" data-testid="cq-condition-disabled">{{ disabledReason }}</div>
    <div class="gt-qce-rows">
      <div v-for="(cond, idx) in modelValue.conditions" :key="idx" class="gt-qce-row" data-testid="cq-condition-row">
        <el-select
          :model-value="cond.field"
          size="small"
          filterable
          placeholder="字段"
          class="gt-qce-field"
          :disabled="disabled"
          :aria-label="`第 ${idx + 1} 个条件的字段`"
          @update:model-value="(v: unknown) => onFieldChange(idx, String(v ?? ''))"
        >
          <el-option v-for="f in fieldOptions" :key="f.key" :label="f.label" :value="f.key" />
        </el-select>
        <el-select
          :model-value="cond.op"
          size="small"
          placeholder="操作符"
          class="gt-qce-op"
          :disabled="disabled"
          :aria-label="`第 ${idx + 1} 个条件的操作符`"
          @update:model-value="(v: unknown) => onOperatorChange(idx, String(v ?? 'eq'))"
        >
          <el-option v-for="op in operatorsFor(cond)" :key="op.value" :label="op.label" :value="op.value" />
        </el-select>
        <el-select
          v-if="cond.op === 'weekday_in'"
          :model-value="weekdayValue(cond.value)"
          multiple
          size="small"
          class="gt-qce-value"
          placeholder="选择星期"
          :disabled="disabled"
          :aria-label="`第 ${idx + 1} 个条件的星期`"
          data-testid="cq-condition-weekday"
          @update:model-value="(v: unknown) => patch(idx, { value: weekdayValue(v) }, true)"
        >
          <el-option v-for="day in WEEKDAY_OPTIONS" :key="day.value" :label="day.label" :value="day.value" />
        </el-select>
        <el-input
          v-else-if="needsConditionValue(cond.op)"
          :model-value="textValue(cond.value)"
          size="small"
          class="gt-qce-value"
          :placeholder="cond.op === 'between' ? '起,止' : '值'"
          :disabled="disabled"
          :aria-label="`第 ${idx + 1} 个条件的值`"
          data-testid="cq-condition-value"
          @update:model-value="(v: unknown) => patch(idx, { value: String(v ?? '') }, true)"
        />
        <span v-else class="gt-qce-novalue">无需值</span>
        <el-tag
          v-if="cond.params?.length"
          size="small"
          type="info"
          effect="plain"
          data-testid="cq-condition-param"
        >参数：{{ cond.params.join('、') }}</el-tag>
        <el-button
          size="small"
          link
          type="danger"
          :disabled="disabled"
          :aria-label="`删除第 ${idx + 1} 个条件`"
          @click="remove(idx)"
        >删除</el-button>
      </div>
      <el-button
        size="small"
        link
        type="primary"
        :disabled="disabled || !fieldOptions.length"
        aria-label="添加条件"
        data-testid="cq-condition-add"
        @click="add"
      >＋ 添加条件</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { resolveColumnLabel } from './queryColumnLabels'
import {
  WEEKDAY_OPTIONS, conditionOpsForDtype, conditionsIncompleteReason, needsConditionValue,
  type ConditionFieldInput, type ConditionState, type EditorCondition, type QueryFieldDtype,
} from './queryConditions'

const props = withDefaults(defineProps<{
  modelValue: ConditionState
  /** 可作条件的字段；旧缓存只有 columns 时可传字符串并按文本处理 */
  fields: readonly ConditionFieldInput[]
  /** 数据源键（列名按数据源取中文） */
  source?: string
  /** 参数来源 / 截止窗口等说明 */
  notices?: readonly string[]
  disabled?: boolean
  /** 禁用原因（如该数据源不支持条件） */
  disabledReason?: string
}>(), { source: '', notices: () => [], disabled: false, disabledReason: '' })

const emit = defineEmits<{ 'update:modelValue': [state: ConditionState] }>()

const normalizedFields = computed(() => props.fields.map((field) => (
  typeof field === 'string' ? { key: field, dtype: 'text' as const } : {
    key: String(field.key),
    dtype: (['text', 'number', 'date', 'bool'].includes(field.dtype) ? field.dtype : 'text') as QueryFieldDtype,
  }
)))
const fieldOptions = computed(() => normalizedFields.value.map((field) => ({
  ...field, label: resolveColumnLabel(field.key, undefined, props.source || undefined),
})))
const fieldDtypes = computed(() => new Map(normalizedFields.value.map((field) => [field.key, field.dtype])))

function operatorsFor(condition: EditorCondition) {
  return conditionOpsForDtype(fieldDtypes.value.get(condition.field))
}

function textValue(value: EditorCondition['value']): string {
  return Array.isArray(value) ? value.join(',') : String(value ?? '')
}

function weekdayValue(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  return value.map(Number).filter((item) => Number.isInteger(item) && item >= 0 && item <= 6)
}

const incompleteReason = computed(() => conditionsIncompleteReason(
  props.modelValue.conditions,
  (field) => resolveColumnLabel(field, undefined, props.source || undefined),
))

defineExpose({ incompleteReason })

function emitState(next: Partial<ConditionState>) {
  emit('update:modelValue', { conditions: props.modelValue.conditions, logic: props.modelValue.logic, ...next })
}

function patch(idx: number, change: Partial<EditorCondition>, clearParams = false) {
  const conditions = props.modelValue.conditions.map((condition, i) => {
    if (i !== idx) return condition
    const next = { ...condition, ...change }
    if (clearParams) delete next.params
    return next
  })
  emitState({ conditions })
}

function onFieldChange(idx: number, field: string) {
  patch(idx, { field, op: 'eq', value: '' }, true)
}

function onOperatorChange(idx: number, op: string) {
  const current = props.modelValue.conditions[idx]
  const value = op === 'weekday_in' ? [] : !needsConditionValue(op) || Array.isArray(current?.value) ? '' : current.value
  patch(idx, { op, value }, true)
}

function add() {
  emitState({ conditions: [
    ...props.modelValue.conditions,
    { field: normalizedFields.value[0]?.key ?? '', op: 'eq', value: '' },
  ] })
}

function remove(idx: number) {
  emitState({ conditions: props.modelValue.conditions.filter((_, i) => i !== idx) })
}
</script>

<style scoped>
.gt-qce { display: flex; flex-direction: column; gap: 8px; }
.gt-qce-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.gt-qce-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); }
.gt-qce-reason { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-qce-rows { display: flex; flex-direction: column; gap: 6px; }
/* 条件行可换行：字段 / 操作符 / 值三者挤不下时值框换到下一行，宽度不小于 120px（R6.4；原先 flex:1 + min-width:0 被挤到 0 宽） */
.gt-qce-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gt-qce-field { width: 150px; }
.gt-qce-op { width: 120px; }
.gt-qce-value { flex: 1 1 120px; min-width: 120px; }
.gt-qce-novalue { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); min-width: 120px; }
</style>
