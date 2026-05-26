<!--
  GtDForm.vue — D 类检查表顶层路由组件（5 子模式入口）

  按 design §3.6 实现：
  - 根据 schema.form_type 分发到 5 个子组件：
      table         → GtDFormTable.vue       (~250 sheet 表格型检查)
      paragraph     → GtDFormParagraph.vue   (~19 sheet 段落型政策)
      qa            → GtDFormQA.vue          (~9 sheet 是否问答型)
      confirmation  → GtDFormConfirmation.vue (~109 sheet 函证/盘点/访谈)
      review        → GtDFormReview.vue      (~27 sheet 复核记录)

  Props/Emits 与 design §3.6 DFormProps/DFormEmits 对齐：
    - field-change             字段值变更（debounce 触发）
    - jump-to-reference        引用文档 / 关联底稿点击
    - save                     保存（debounce 1.5s）
    - sign                     仅 review 子模式（电子签 + 时间戳）

  设计要点：
  - form_type 优先级：schema.form_type > formType prop（fallback）
    (formType prop 来自 GtWpRenderer 的 componentType，形如 'd-form-table'，
     需去除 'd-form-' 前缀归一化为 schema.form_type 取值)
  - 不加顶层 v-if 守卫（避免 init 死锁）；未识别 form_type 显示友好兜底
  - 遵循 setup const 声明顺序铁律：refs > computed > methods

  锚定 spec workpaper-html-renderer Task 8.2
  Validates: Requirements 3.5（D 类 449 sheet 5 子模式）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  GtDForm 及 5 个子组件**不直接订阅** eventBus 'cross-ref:updated' 事件。
  跨底稿引用变化由 `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 +
  重拉 renderConfig，子组件通过 props 接收最新 htmlData 自动更新
  （单一订阅入口避免内存泄漏 + 清理失误风险）。
-->

<template>
  <div class="gt-d-form">
    <!-- 表格型检查（关联方矩阵 / 项目动态增删 / 字典下拉） -->
    <GtDFormTable
      v-if="resolvedFormType === 'table'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @field-change="onFieldChange"
      @jump-to-reference="onJumpToReference"
      @save="onSave"
    />

    <!-- 段落型政策（markdown 富文本 + 占位符 + 引用文档） -->
    <GtDFormParagraph
      v-else-if="resolvedFormType === 'paragraph'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @field-change="onFieldChange"
      @jump-to-reference="onJumpToReference"
      @save="onSave"
    />

    <!-- 是否问答型（4 判断题 × N 组合 → 自动判定业务模式 / 报表项目） -->
    <GtDFormQA
      v-else-if="resolvedFormType === 'qa'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @field-change="onFieldChange"
      @jump-to-reference="onJumpToReference"
      @save="onSave"
    />

    <!-- 函证/盘点/访谈（专属子组件：询证函生成 / 盘点队伍 / 访谈记录） -->
    <GtDFormConfirmation
      v-else-if="resolvedFormType === 'confirmation'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @field-change="onFieldChange"
      @jump-to-reference="onJumpToReference"
      @save="onSave"
    />

    <!-- 复核记录（电子签 + 时间戳 + 状态机） -->
    <GtDFormReview
      v-else-if="resolvedFormType === 'review'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :schema="schema"
      :html-data="htmlData"
      :readonly="readonly"
      @field-change="onFieldChange"
      @jump-to-reference="onJumpToReference"
      @save="onSave"
      @sign="onSign"
    />

    <!-- 未识别 form_type 兜底（不应出现，schema 升级时友好降级） -->
    <div v-else class="gt-d-form__unknown">
      <el-result
        icon="warning"
        :title="`无法识别的 D 子模式: ${resolvedFormType || '(空)'}`"
      >
        <template #sub-title>
          <span>schema.form_type 应取值 table / paragraph / qa / confirmation / review。</span>
          <br />
          <span class="gt-d-form__hint">Sheet: {{ sheetName }}</span>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import GtDFormTable from './GtDFormTable.vue'
import GtDFormParagraph from './GtDFormParagraph.vue'
import GtDFormQA from './GtDFormQA.vue'
import GtDFormConfirmation from './GtDFormConfirmation.vue'
import GtDFormReview from './GtDFormReview.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DFormType = 'table' | 'paragraph' | 'qa' | 'confirmation' | 'review'

export interface DFormSchema {
  form_type?: DFormType | string
  [key: string]: any
}

export type DFormData = Record<string, any>

export interface FieldChangePayload {
  field_name: string
  old_value?: any
  new_value?: any
  cell?: string
}

export interface SignaturePayload {
  role: string
  signed_by: string
  signed_at: string
  cell?: string
  state_transition?: { from: string; to: string }
}

const VALID_FORM_TYPES: readonly DFormType[] = [
  'table',
  'paragraph',
  'qa',
  'confirmation',
  'review',
] as const

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  /**
   * Fallback form type (e.g. 'd-form-table') when schema.form_type is missing.
   * Typically forwarded from GtWpRenderer's componentType.
   */
  formType?: string
  readonly?: boolean
}>(), {
  formType: '',
  readonly: false,
})

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
  'sign': [payload: SignaturePayload]
}>()

// ─── Computed ────────────────────────────────────────────────────────────────

/**
 * Resolve form_type with priority:
 *   1. schema.form_type (canonical, design §3.6)
 *   2. formType prop fallback (componentType from GtWpRenderer, strip 'd-form-' prefix)
 *   3. null (renders unknown placeholder)
 */
const resolvedFormType = computed<DFormType | null>(() => {
  const fromSchema = props.schema?.form_type
  if (typeof fromSchema === 'string' && (VALID_FORM_TYPES as readonly string[]).includes(fromSchema)) {
    return fromSchema as DFormType
  }

  const fromProp = (props.formType || '').replace(/^d-form-/, '')
  if (fromProp && (VALID_FORM_TYPES as readonly string[]).includes(fromProp)) {
    return fromProp as DFormType
  }

  return null
})

// ─── Methods ─────────────────────────────────────────────────────────────────

function onFieldChange(payload: FieldChangePayload) {
  emit('field-change', payload)
}

function onJumpToReference(refCode: string) {
  emit('jump-to-reference', refCode)
}

function onSave(data: DFormData) {
  emit('save', data)
}

function onSign(payload: SignaturePayload) {
  emit('sign', payload)
}
</script>

<style scoped>
.gt-d-form {
  width: 100%;
  height: 100%;
  min-height: 300px;
}

.gt-d-form__unknown {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.gt-d-form__hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
