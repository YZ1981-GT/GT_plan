<!--
  GtDFormParagraph.vue — D 类段落型政策检查子组件（Shell）

  适用范围：~19 sheet（会计政策检查 / 编号段落 / 长篇问答）
  样本 schema：D-D2-8.yaml（坏账准备计提会计政策检查）

  核心交互：
  - segments[] 顺序渲染：每段显示 seq + title（如「一、审计目标」）
  - editable: false → 渲染 content 为只读（marked + DOMPurify markdown 渲染）
  - editable: true  → el-input type="textarea" + placeholder（多行模板）折叠展示
  - hint 行（带 InfoFilled icon）显示提示语
  - reference_doc.enabled → 渲染「📄 引用文档」按钮 + GtIndexChip
  - conclusion mode=single：radio + class + icon
  - debounced auto-save 1.5s

  锚定 spec workpaper-html-renderer Task 8.4
  Validates: Requirements 3.5（D 子模式 2：段落型政策）
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

        <!-- 主输入区 + AI 建议按钮 -->
        <div class="gt-dfp__input-wrapper">
          <div class="gt-ai-suggest-trigger" v-if="aiEnabled && !readonly">
            <el-button text size="small" :loading="aiLoading" @click="onAiSuggest(seg)">🤖 AI 建议</el-button>
          </div>
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
        </div>

        <!-- AI 建议面板 -->
        <div v-if="showSuggestionPanel && currentSuggestion?.fieldName === ('segments.' + seg.id)" class="gt-dfp__ai-panel">
          <div class="gt-dfp__ai-panel-header">
            <span class="gt-dfp__ai-panel-title">🤖 AI 建议</span>
            <el-tag size="small" :type="currentSuggestion.confidence >= 0.7 ? 'success' : 'warning'">
              置信度 {{ Math.round(currentSuggestion.confidence * 100) }}%
            </el-tag>
          </div>
          <pre class="gt-dfp__ai-panel-text">{{ currentSuggestion.text }}</pre>
          <div class="gt-dfp__ai-panel-actions">
            <el-button type="primary" size="small" @click="handleAdopt(seg.id)">✅ 采纳</el-button>
            <el-button size="small" @click="handleModify(seg.id)">✏️ 修改后采纳</el-button>
            <el-button size="small" @click="handleIgnore">❌ 忽略</el-button>
          </div>
        </div>

        <!-- hint 行 -->
        <div v-if="seg.hint" class="gt-dfp__field-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ seg.hint }}</span>
        </div>

        <!-- 实时 markdown 预览 -->
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
import {
  InfoFilled,
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
  Document as DocumentIcon,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import { useParagraphVariables } from './composables/useParagraphVariables'
import type { SegmentDef } from './composables/useParagraphVariables'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'

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

// ─── AI 辅助填写 ─────────────────────────────────────────────────────────────

const {
  aiEnabled,
  aiLoading,
  currentSuggestion,
  showSuggestionPanel,
  assistedFieldsList,
  requestSuggestion,
  adoptSuggestion,
  modifySuggestion,
  ignoreSuggestion,
} = useWpAiSuggest({ wpId: props.wpId, sheetName: props.sheetName })

// ─── Core composable（顶层解构保证 wrapper.vm.xxx 可访问） ─────────────────────

const {
  segmentValues,
  conclusionValue,
  renderedContent,
  renderedSegmentValue,
  entityName,
  periodEnd,
  indexNo,
  hasHeaderInfo,
  segments,
  conclusionBlock,
  conclusionOptions,
  hasConclusion,
  formatSeq,
  segmentRows,
  referenceChipValue,
  onSegmentChange,
  onSegmentBlur,
  onConclusionChange,
  debounceSave,
  initData,
} = useParagraphVariables({
  schema: () => props.schema,
  htmlData: () => props.htmlData,
  emit,
  readonly: () => props.readonly,
  assistedFieldsList: () => assistedFieldsList.value,
})

// ─── Static maps ─────────────────────────────────────────────────────────────

const conclusionIcons: Record<string, any> = {
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
}

// ─── AI handlers ─────────────────────────────────────────────────────────────

function onAiSuggest(seg: SegmentDef) {
  const existingContent = segmentValues.value[seg.id] || ''
  requestSuggestion('segments.' + seg.id, existingContent)
}

function handleAdopt(segId: string) {
  const text = adoptSuggestion()
  if (text) {
    segmentValues.value[segId] = text
    debounceSave()
  }
}

function handleModify(segId: string) {
  if (currentSuggestion.value) {
    segmentValues.value[segId] = currentSuggestion.value.text
    modifySuggestion(currentSuggestion.value.text)
    debounceSave()
  }
}

function handleIgnore() {
  ignoreSuggestion()
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
</script>



<style scoped>
.gt-d-form-paragraph { display: flex; flex-direction: column; gap: 16px; padding: 16px; }
.gt-dfp__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 10px 14px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-dfp__header-meta { display: flex; align-items: center; gap: 16px; }
.gt-dfp__entity { font-weight: 600; color: var(--el-text-color-primary); }
.gt-dfp__period { color: var(--el-text-color-regular); }
.gt-dfp__index { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfp__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-dfp__segment { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--gt-color-bg-white, #fff); }
.gt-dfp__segment-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.gt-dfp__segment-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); display: inline-flex; align-items: center; gap: 4px; }
.gt-dfp__segment-seq { color: var(--el-color-primary); font-weight: 700; }
.gt-dfp__segment-name { color: var(--el-text-color-primary); }
.gt-dfp__segment-ref { display: inline-flex; align-items: center; gap: 8px; }
.gt-dfp__segment-readonly { padding: 8px 12px; background: var(--el-color-info-light-9); border-left: 3px solid var(--el-color-info-light-3); border-radius: 4px; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.7; }
.gt-dfp__plain { margin: 0; font-family: inherit; white-space: pre-wrap; word-break: break-word; }
.gt-dfp__markdown { font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); }
.gt-dfp__markdown :deep(h1), .gt-dfp__markdown :deep(h2), .gt-dfp__markdown :deep(h3), .gt-dfp__markdown :deep(h4) { margin: 8px 0 4px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-dfp__markdown :deep(p) { margin: 4px 0; }
.gt-dfp__markdown :deep(ul), .gt-dfp__markdown :deep(ol) { padding-left: 24px; margin: 4px 0; }
.gt-dfp__markdown :deep(code) { padding: 1px 4px; background: var(--el-fill-color-light); border-radius: 3px; font-size: 12px; }
.gt-dfp__markdown :deep(strong) { color: var(--el-text-color-primary); }
.gt-dfp__markdown--preview { padding: 8px 12px; background: var(--el-color-success-light-9); border-left: 3px solid var(--el-color-success-light-5); border-radius: 4px; }
.gt-dfp__segment-editable { display: flex; flex-direction: column; gap: 8px; }
.gt-dfp__input-wrapper { position: relative; }
.gt-ai-suggest-trigger { position: absolute; top: 4px; right: 8px; z-index: 5; }
.gt-dfp__ai-panel { border: 1px solid var(--el-color-primary-light-5); border-radius: 6px; padding: 12px; background: var(--el-color-primary-light-9); }
.gt-dfp__ai-panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.gt-dfp__ai-panel-title { font-size: 13px; font-weight: 600; color: var(--el-color-primary); }
.gt-dfp__ai-panel-text { margin: 0 0 10px; padding: 8px 12px; background: var(--gt-color-bg-white, #fff); border-radius: 4px; font-family: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; color: var(--el-text-color-regular); max-height: 200px; overflow-y: auto; }
.gt-dfp__ai-panel-actions { display: flex; gap: 8px; }
.gt-dfp__placeholder-collapse, .gt-dfp__preview-collapse { border: none; }
.gt-dfp__placeholder-collapse :deep(.el-collapse-item__header), .gt-dfp__preview-collapse :deep(.el-collapse-item__header) { height: 32px; font-size: 13px; padding: 0 8px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.gt-dfp__placeholder-collapse :deep(.el-collapse-item__wrap), .gt-dfp__preview-collapse :deep(.el-collapse-item__wrap) { background: transparent; }
.gt-dfp__placeholder-text { margin: 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: var(--el-text-color-regular); }
.gt-dfp__textarea :deep(.el-textarea__inner) { font-family: inherit; font-size: 13px; line-height: 1.7; }
.gt-dfp__field-hint { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfp__field-hint .el-icon { color: var(--el-color-info); }
.gt-dfp__conclusion { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--el-color-primary-light-9); }
.gt-dfp__title { margin: 0; font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-dfp__conclusion-group { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.gt-dfp__conclusion-group :deep(.el-radio) { height: auto; padding: 12px 14px; margin-right: 0; align-items: flex-start; border: 1px solid transparent; border-radius: 4px; transition: background 0.15s, border-color 0.15s; white-space: normal; }
.gt-dfp__conclusion-group :deep(.el-radio:hover) { background: var(--el-color-primary-light-8); }
.gt-dfp__conclusion-group :deep(.el-radio.is-checked) { background: var(--el-color-primary-light-8); border-color: var(--el-color-primary-light-5); }
.gt-dfp__conclusion-group :deep(.el-radio__label) { display: inline-flex; flex-direction: column; gap: 4px; width: 100%; }
.gt-dfp__conclusion-option.is-success :deep(.el-radio.is-checked) { border-color: var(--el-color-success); background: var(--el-color-success-light-8); }
.gt-dfp__conclusion-option.is-warning :deep(.el-radio.is-checked) { border-color: var(--el-color-warning); background: var(--el-color-warning-light-8); }
.gt-dfp__conclusion-option.is-danger :deep(.el-radio.is-checked) { border-color: var(--el-color-danger); background: var(--el-color-danger-light-8); }
.gt-dfp__conclusion-label { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 500; color: var(--el-text-color-primary); }
.gt-dfp__conclusion-icon { font-size: 16px; }
.gt-dfp__conclusion-option.is-success .gt-dfp__conclusion-icon { color: var(--el-color-success); }
.gt-dfp__conclusion-option.is-warning .gt-dfp__conclusion-icon { color: var(--el-color-warning); }
.gt-dfp__conclusion-option.is-danger .gt-dfp__conclusion-icon { color: var(--el-color-danger); }
.gt-dfp__conclusion-option.is-info .gt-dfp__conclusion-icon { color: var(--el-color-info); }
.gt-dfp__conclusion-name { font-weight: 600; }
.gt-dfp__conclusion-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-left: 22px; }
</style>
