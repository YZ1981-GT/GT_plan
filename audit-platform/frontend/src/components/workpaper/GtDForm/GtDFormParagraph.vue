<!--
  GtDFormParagraph.vue — D 类段落型政策检查子组件（实现版）

  适用范围：~19 sheet（会计政策检查 / 编号段落 / 长篇问答）
  样本 schema：D-D2-8.yaml（坏账准备计提会计政策检查）

  核心交互：
  - segments[] 顺序渲染：每段显示 seq + title（如「一、审计目标」）
  - editable: false → 渲染 content 为只读（marked + DOMPurify markdown 渲染）
  - editable: true  → el-input type="textarea" + placeholder（多行模板）折叠展示
  - hint 行（带 InfoFilled icon）显示提示语
  - reference_doc.enabled → 渲染「📄 引用文档」按钮 + GtIndexChip
    点击 emit 'jump-to-reference' 携带 target_section
  - conclusion mode=single：radio + class + icon
  - debounced auto-save 1.5s
  - 字段变更 emit 'field-change' { field_name, old_value, new_value }

  锚定 spec workpaper-html-renderer Task 8.4
  Validates: Requirements 3.5（D 子模式 2：段落型政策）

  cross-ref:updated 订阅由 `useWpRenderer.ts` 集中处理（Task 13.2），本组件不直接订阅。
-->

<template>
  <div class="gt-d-form-paragraph">
    <!-- ─── 顶部头部信息（只读展示） ─── -->
    <header v-if="hasHeaderInfo" class="gt-dfp__header">
      <div class="gt-dfp__header-meta">
        <span v-if="entityName" class="gt-dfp__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfp__period">{{ periodEnd }}</span>
      </div>
      <div v-if="indexNo" class="gt-dfp__index">
        索引号：<strong>{{ indexNo }}</strong>
      </div>
    </header>

    <!-- ─── 段落顺序渲染 ─── -->
    <section
      v-for="seg in segments"
      :key="seg.id"
      class="gt-dfp__segment"
    >
      <header class="gt-dfp__segment-header">
        <h3 class="gt-dfp__segment-title">
          <span class="gt-dfp__segment-seq">{{ formatSeq(seg.seq) }}</span>
          <span class="gt-dfp__segment-name">{{ seg.title }}</span>
        </h3>
        <!-- 引用文档跳转按钮 -->
        <div
          v-if="seg.reference_doc?.enabled && seg.reference_doc.target_section"
          class="gt-dfp__segment-ref"
        >
          <el-button
            link
            type="primary"
            size="small"
            :icon="DocumentIcon"
            @click="onReferenceDocClick(seg)"
          >{{ seg.reference_doc.label || '查看引用文档' }}</el-button>
          <GtIndexChip
            v-if="referenceChipValue(seg)"
            :value="referenceChipValue(seg)"
            :validate="false"
            @click="onReferenceChipClick(seg)"
          />
        </div>
      </header>

      <!-- 只读段落（editable=false）：渲染预设 content 作为说明 -->
      <div
        v-if="!seg.editable"
        class="gt-dfp__segment-readonly"
      >
        <div
          v-if="seg.formatting === 'markdown' && renderedContent[seg.id]"
          class="gt-dfp__markdown"
          v-html="renderedContent[seg.id]"
        />
        <pre
          v-else-if="seg.content"
          class="gt-dfp__plain"
        >{{ seg.content }}</pre>
        <el-empty
          v-else
          :image-size="60"
          description="（暂无内容）"
        />
      </div>

      <!-- 可编辑段落（editable=true）：textarea + 占位符模板 + hint -->
      <div v-else class="gt-dfp__segment-editable">
        <!-- 占位模板（多行 markdown）折叠展示 -->
        <el-collapse
          v-if="seg.placeholder"
          class="gt-dfp__placeholder-collapse"
        >
          <el-collapse-item :title="'📋 填写模板示例（点击展开）'" :name="seg.id">
            <pre class="gt-dfp__placeholder-text">{{ seg.placeholder }}</pre>
          </el-collapse-item>
        </el-collapse>

        <!-- 主输入区 -->
        <el-input
          v-model="segmentValues[seg.id]"
          type="textarea"
          :rows="segmentRows(seg)"
          :disabled="readonly"
          :maxlength="seg.max_length"
          :show-word-limit="!!seg.max_length"
          :placeholder="seg.hint || ('请填写' + seg.title)"
          class="gt-dfp__textarea"
          @change="onSegmentChange(seg.id)"
          @blur="onSegmentBlur(seg.id)"
        />

        <!-- hint 行 -->
        <div v-if="seg.hint" class="gt-dfp__field-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ seg.hint }}</span>
        </div>

        <!-- 实时 markdown 预览（formatting=markdown 且已填内容时显示） -->
        <el-collapse
          v-if="seg.formatting === 'markdown' && segmentValues[seg.id]"
          class="gt-dfp__preview-collapse"
        >
          <el-collapse-item :title="'👁 Markdown 预览'" :name="seg.id + '-preview'">
            <div
              class="gt-dfp__markdown gt-dfp__markdown--preview"
              v-html="renderedSegmentValue[seg.id]"
            />
          </el-collapse-item>
        </el-collapse>
      </div>
    </section>

    <!-- ─── 整体审计结论（single 模式） ─── -->
    <section
      v-if="hasConclusion"
      class="gt-dfp__conclusion"
    >
      <h3 class="gt-dfp__title">最终结论</h3>
      <el-radio-group
        v-model="conclusionValue"
        :disabled="readonly"
        class="gt-dfp__conclusion-group"
        @change="onConclusionChange"
      >
        <el-radio
          v-for="opt in conclusionOptions"
          :key="opt.value"
          :value="opt.value"
          :class="['gt-dfp__conclusion-option', 'is-' + (opt.class || 'info')]"
        >
          <div class="gt-dfp__conclusion-label">
            <el-icon
              v-if="opt.icon && conclusionIcons[opt.icon]"
              class="gt-dfp__conclusion-icon"
            >
              <component :is="conclusionIcons[opt.icon]" />
            </el-icon>
            <span class="gt-dfp__conclusion-name">{{ opt.label }}</span>
          </div>
          <span
            v-if="opt.description"
            class="gt-dfp__conclusion-desc"
          >{{ opt.description }}</span>
        </el-radio>
      </el-radio-group>
    </section>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import {
  InfoFilled,
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
  Document as DocumentIcon,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface ReferenceDoc {
  enabled?: boolean
  label?: string
  source?: string
  target_section?: string
  render?: 'index_chip' | string
}

interface SegmentDef {
  id: string
  seq?: string
  title: string
  start_row?: number
  end_row?: number
  editable?: boolean
  content?: string                    // 只读段落预设内容
  type?: 'textarea' | string
  cell?: string
  max_length?: number
  placeholder?: string                // 多行填写模板
  hint?: string                       // 单行提示
  formatting?: 'markdown' | string
  reference_doc?: ReferenceDoc
}

interface ConclusionOption {
  value: string
  label: string
  description?: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
}

interface ConclusionBlock {
  mode?: 'single' | string
  cell?: string
  options?: ConclusionOption[]
  mutual_exclusive?: boolean
  required?: boolean
}

interface ParagraphData extends DFormData {
  segments?: Record<string, string>
  conclusion?: string
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
}>()

// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────

const segmentValues = ref<Record<string, string>>({})
const conclusionValue = ref<string>('')

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Static maps ─────────────────────────────────────────────────────────────

const conclusionIcons: Record<string, any> = {
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
}

// ─── Computed ────────────────────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.I3 || fixedCells.value?.J3 || fixedCells.value?.O3 || fixedCells.value?.P3 || ''
)
const hasHeaderInfo = computed(
  () => !!(entityName.value || periodEnd.value || indexNo.value)
)

const segments = computed<SegmentDef[]>(() => {
  const arr = (props.schema as any)?.segments
  return Array.isArray(arr) ? arr as SegmentDef[] : []
})

const conclusionBlock = computed<ConclusionBlock | null>(() => {
  const c = (props.schema as any)?.conclusion
  return c && typeof c === 'object' ? c : null
})

const conclusionOptions = computed<ConclusionOption[]>(
  () => conclusionBlock.value?.options ?? []
)

const hasConclusion = computed(
  () => conclusionBlock.value?.mode === 'single' && conclusionOptions.value.length > 0
)

/** 只读段落预渲染 markdown → 安全 HTML（按 segment.id 缓存） */
const renderedContent = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const seg of segments.value) {
    if (!seg.editable && seg.formatting === 'markdown' && seg.content) {
      try {
        const html = marked(seg.content, { async: false }) as string
        out[seg.id] = DOMPurify.sanitize(html)
      } catch {
        out[seg.id] = ''
      }
    }
  }
  return out
})

/** 可编辑段落用户输入实时渲染 markdown 预览 */
const renderedSegmentValue = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const seg of segments.value) {
    if (seg.editable && seg.formatting === 'markdown') {
      const text = segmentValues.value[seg.id]
      if (text) {
        try {
          const html = marked(text, { async: false }) as string
          out[seg.id] = DOMPurify.sanitize(html)
        } catch {
          out[seg.id] = ''
        }
      }
    }
  }
  return out
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 中文/阿拉伯数字 seq 统一加顿号：「一」→「一、」 */
function formatSeq(seq: string | undefined): string {
  if (!seq) return ''
  const trimmed = String(seq).trim()
  if (!trimmed) return ''
  if (/[、.．]$/.test(trimmed)) return trimmed
  return trimmed + '、'
}

/** 段落 textarea 默认行数：按 max_length 推导 */
function segmentRows(seg: SegmentDef): number {
  const max = seg.max_length || 0
  if (max <= 600) return 6
  if (max <= 2000) return 8
  if (max <= 4000) return 10
  return 12
}

/** 引用文档解析为 GtIndexChip 可识别的 ref（target_section 形如「五-1-2 应收账款会计政策」） */
function referenceChipValue(seg: SegmentDef): string {
  const ref = seg.reference_doc
  if (!ref?.enabled || !ref.target_section) return ''
  // section like "五-1-2 应收账款会计政策" → "Note:五-1-2"（只取空格前的 section_id）
  const section = ref.target_section.split(/\s+/)[0] || ref.target_section
  return 'Note:' + section
}

// ─── Field change emitters ───────────────────────────────────────────────────

function emitFieldChange(field_name: string, oldValue: any, newValue: any, cell?: string) {
  emit('field-change', {
    field_name,
    old_value: oldValue,
    new_value: newValue,
    cell,
  })
}

// ─── Segment handlers ────────────────────────────────────────────────────────

function onSegmentChange(_segId: string) {
  // change 事件触发 debounce 保存
  debounceSave()
}

function onSegmentBlur(segId: string) {
  const seg = segments.value.find(s => s.id === segId)
  emitFieldChange(
    'segments.' + segId,
    undefined,
    segmentValues.value[segId],
    seg?.cell,
  )
  // blur 立即保存（无 debounce），避免用户切换 sheet 丢失草稿
  if (props.readonly) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  emit('save', buildSavePayload())
}

// ─── Reference doc handlers ──────────────────────────────────────────────────

function onReferenceDocClick(seg: SegmentDef) {
  const ref = seg.reference_doc
  if (!ref?.target_section) return
  emit('jump-to-reference', ref.target_section)
}

function onReferenceChipClick(seg: SegmentDef) {
  const ref = seg.reference_doc
  if (!ref?.target_section) return
  emit('jump-to-reference', ref.target_section)
}

// ─── Conclusion handlers ─────────────────────────────────────────────────────

function onConclusionChange(value: string | number | boolean | undefined) {
  const newVal = String(value ?? '')
  emitFieldChange(
    'conclusion',
    undefined,
    newVal,
    conclusionBlock.value?.cell,
  )
  debounceSave()
}

// ─── Init / Sync ─────────────────────────────────────────────────────────────

function initData() {
  const data = (props.htmlData ?? {}) as ParagraphData

  // 段落值
  const segIn = data.segments && typeof data.segments === 'object' ? data.segments : {}
  const segOut: Record<string, string> = {}
  for (const seg of segments.value) {
    if (!seg.editable) continue  // 只读段落不需要存值
    const v = (segIn as Record<string, any>)[seg.id]
    segOut[seg.id] = typeof v === 'string' ? v : ''
  }
  segmentValues.value = segOut

  // 结论
  conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''
}

initData()

watch(
  () => props.htmlData,
  () => {
    initData()
  },
  { deep: true }
)

watch(
  () => props.schema,
  () => {
    initData()
  },
  { deep: true }
)

// ─── Save payload + debounce ─────────────────────────────────────────────────

function buildSavePayload(): ParagraphData {
  return {
    ...(props.htmlData || {}),
    segments: { ...segmentValues.value },
    conclusion: conclusionValue.value,
  }
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', buildSavePayload())
  }, 1500)
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})
</script>



<style scoped>
.gt-d-form-paragraph {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* ── Header ── */
.gt-dfp__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}
.gt-dfp__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-dfp__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfp__period {
  color: var(--el-text-color-regular);
}
.gt-dfp__index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfp__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── Segment ── */
.gt-dfp__segment {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfp__segment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.gt-dfp__segment-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.gt-dfp__segment-seq {
  color: var(--el-color-primary);
  font-weight: 700;
}
.gt-dfp__segment-name {
  color: var(--el-text-color-primary);
}
.gt-dfp__segment-ref {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* ── Readonly segment ── */
.gt-dfp__segment-readonly {
  padding: 8px 12px;
  background: var(--el-color-info-light-9);
  border-left: 3px solid var(--el-color-info-light-3);
  border-radius: 4px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}
.gt-dfp__plain {
  margin: 0;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Markdown rendered HTML ── */
.gt-dfp__markdown {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.gt-dfp__markdown :deep(h1),
.gt-dfp__markdown :deep(h2),
.gt-dfp__markdown :deep(h3),
.gt-dfp__markdown :deep(h4) {
  margin: 8px 0 4px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfp__markdown :deep(p) {
  margin: 4px 0;
}
.gt-dfp__markdown :deep(ul),
.gt-dfp__markdown :deep(ol) {
  padding-left: 24px;
  margin: 4px 0;
}
.gt-dfp__markdown :deep(code) {
  padding: 1px 4px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  font-size: 12px;
}
.gt-dfp__markdown :deep(strong) {
  color: var(--el-text-color-primary);
}
.gt-dfp__markdown--preview {
  padding: 8px 12px;
  background: var(--el-color-success-light-9);
  border-left: 3px solid var(--el-color-success-light-5);
  border-radius: 4px;
}

/* ── Editable segment ── */
.gt-dfp__segment-editable {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-dfp__placeholder-collapse,
.gt-dfp__preview-collapse {
  border: none;
}
.gt-dfp__placeholder-collapse :deep(.el-collapse-item__header),
.gt-dfp__preview-collapse :deep(.el-collapse-item__header) {
  height: 32px;
  font-size: 13px;
  padding: 0 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.gt-dfp__placeholder-collapse :deep(.el-collapse-item__wrap),
.gt-dfp__preview-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
}
.gt-dfp__placeholder-text {
  margin: 0;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
}
.gt-dfp__textarea :deep(.el-textarea__inner) {
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
}

/* ── Field hint ── */
.gt-dfp__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfp__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── Conclusion ── */
.gt-dfp__conclusion {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
}
.gt-dfp__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfp__conclusion-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.gt-dfp__conclusion-group :deep(.el-radio) {
  height: auto;
  padding: 12px 14px;
  margin-right: 0;
  align-items: flex-start;
  border: 1px solid transparent;
  border-radius: 4px;
  transition: background 0.15s, border-color 0.15s;
  white-space: normal;
}
.gt-dfp__conclusion-group :deep(.el-radio:hover) {
  background: var(--el-color-primary-light-8);
}
.gt-dfp__conclusion-group :deep(.el-radio.is-checked) {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}
.gt-dfp__conclusion-group :deep(.el-radio__label) {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.gt-dfp__conclusion-option.is-success :deep(.el-radio.is-checked) {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-8);
}
.gt-dfp__conclusion-option.is-warning :deep(.el-radio.is-checked) {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-8);
}
.gt-dfp__conclusion-option.is-danger :deep(.el-radio.is-checked) {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-8);
}
.gt-dfp__conclusion-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.gt-dfp__conclusion-icon {
  font-size: 16px;
}
.gt-dfp__conclusion-option.is-success .gt-dfp__conclusion-icon {
  color: var(--el-color-success);
}
.gt-dfp__conclusion-option.is-warning .gt-dfp__conclusion-icon {
  color: var(--el-color-warning);
}
.gt-dfp__conclusion-option.is-danger .gt-dfp__conclusion-icon {
  color: var(--el-color-danger);
}
.gt-dfp__conclusion-option.is-info .gt-dfp__conclusion-icon {
  color: var(--el-color-info);
}
.gt-dfp__conclusion-name {
  font-weight: 600;
}
.gt-dfp__conclusion-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 22px;
}
</style>
