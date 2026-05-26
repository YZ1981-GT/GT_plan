<!--
  GtWpRenderer.vue — 底稿 HTML 渲染器顶层路由组件

  按 componentType 分发到对应子组件（A/B/C/D/E/H/skip/univer）。
  遵循 overlay 模式：容器永远渲染，loading/error 用蒙层覆盖。
  不加顶层 v-if="loading" 守卫（避免 init 死锁）。

  锚定 spec workpaper-html-renderer Task 3.4
  Validates: Requirements 1.2（9 类路由分发）
-->
<template>
  <div class="gt-wp-renderer" ref="containerRef">
    <!-- Loading overlay -->
    <GtLoadingOverlay
      :visible="loading"
      text="正在加载渲染配置..."
      :hint="loadingHint"
      :size="32"
    />

    <!-- Error overlay -->
    <div v-if="!loading && error" class="gt-wp-renderer__error">
      <el-result icon="error" :title="errorTitle" :sub-title="errorSubTitle">
        <template #extra>
          <el-button type="primary" @click="reload">重试</el-button>
        </template>
      </el-result>
    </div>

    <!-- Ready: dispatch by componentType -->
    <template v-if="!loading && !error && renderConfig">
      <!-- A 程序表中控台 -->
      <GtAProgramConsole
        v-if="componentType === 'a-program-console'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :readonly="readonly"
        @save="onSave"
      />

      <!-- B 底稿目录 -->
      <GtBIndex
        v-else-if="componentType === 'b-index'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :readonly="readonly"
        @save="onSave"
      />

      <!-- C 附注披露嵌套表 -->
      <GtCNoteTable
        v-else-if="componentType === 'c-note-table'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :readonly="readonly"
        @save="onSave"
        @subtable-toggle="onSubtableToggle"
        @standard-switch="onStandardSwitch"
        @sync-to-disclosure-notes="onSyncToDisclosureNotes"
        @jump-to-reference="onJumpToReference"
      />

      <!-- D 检查表（5 子模式由 GtDForm 内部路由） -->
      <GtDForm
        v-else-if="componentType === 'd-form-table' || componentType === 'd-form-paragraph' || componentType === 'd-form-qa' || componentType === 'd-form-confirmation' || componentType === 'd-form-review'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :form-type="componentType"
        :readonly="readonly"
        @save="onSave"
      />

      <!-- E 控制测试 -->
      <GtEControlTest
        v-else-if="componentType === 'e-control-test'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
        :readonly="readonly"
        @save="onSave"
        @trigger-procedure-trimming-suggestion="onTrimmingSuggestion"
        @conclusion-change="onConclusionChange"
        @step-advance="onStepAdvance"
      />

      <!-- H 辅助说明（只读 markdown） -->
      <GtHStaticDoc
        v-else-if="componentType === 'h-static-doc'"
        :wp-id="wpId"
        :sheet-name="activeSheetName"
        :schema="activeSheetSchema"
        :html-data="activeSheetHtmlData"
      />

      <!-- Univer 保留渲染（F/G 类） -->
      <div v-else-if="componentType === 'univer'" class="gt-wp-renderer__univer-placeholder">
        <el-result icon="info" title="Univer 渲染">
          <template #sub-title>
            <span>此底稿使用 Univer Sheets 渲染，请通过底稿编辑器打开。</span>
          </template>
        </el-result>
      </div>

      <!-- Skip 占位 -->
      <SkippedSheetPlaceholder
        v-else-if="componentType === 'skip'"
        :sheet-name="activeSheetName"
      />

      <!-- 未知 componentType fallback（不应出现） -->
      <div v-else class="gt-wp-renderer__unknown-placeholder">
        <el-result icon="info" :title="`组件类型: ${componentType}`">
          <template #sub-title>
            <span>该组件类型尚未实现，将在后续版本中支持。</span>
          </template>
        </el-result>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { useWpRenderer, type WpComponentType } from '@/composables/useWpRenderer'
import GtLoadingOverlay from '@/components/common/GtLoadingOverlay.vue'

// ─── Sub-components (real + placeholder stubs) ───
// GtAProgramConsole is the real implementation (Task 3.9)
// Others will be replaced by real implementations in later tasks
import GtAProgramConsole from '@/components/workpaper/GtAProgramConsole.vue'
import GtBIndex from '@/components/workpaper/GtBIndex.vue'
import GtCNoteTable from '@/components/workpaper/GtCNoteTable.vue'
import GtDForm from '@/components/workpaper/GtDForm/GtDForm.vue'
import GtEControlTest from '@/components/workpaper/GtEControlTest.vue'
import GtHStaticDoc from '@/components/workpaper/GtHStaticDoc.vue'
import SkippedSheetPlaceholder from '@/components/workpaper/SkippedSheetPlaceholder.vue'

// ─── Types ───
export interface SavePayload {
  sheet_name: string
  html_data: Record<string, any>
  schema_version?: string
}

export interface CrossRefPayload {
  source_wp_code: string
  target_wp_code: string
  cell: string
  old_value?: any
  new_value?: any
}

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  initialSheet?: string
  initialCell?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  'sheet-change': [sheetName: string]
  'cell-focus': [payload: { sheet: string; cell: string }]
  'save-success': [payload: SavePayload]
  'cross-ref-update': [payload: CrossRefPayload]
  'trigger-procedure-trimming-suggestion': [payload: Record<string, any>]
  'conclusion-change': [conclusion: string]
  'step-advance': [step: number]
  'subtable-toggle': [subTableId: string]
  'standard-switch': [standard: string]
  'sync-to-disclosure-notes': [payload: Record<string, any>]
  'jump-to-reference': [refCode: string]
}>()

// ─── Refs ───
const containerRef = ref<HTMLElement | null>(null)
const loadingHint = ref('')

// ─── Composables ───
const wpIdRef = toRef(props, 'wpId')
const { renderConfig, loading, error, componentType, reload } = useWpRenderer(wpIdRef)

// ─── Computed ───
const activeSheetName = computed(() => {
  if (!renderConfig.value?.sheets?.length) return ''
  // 如果指定了 initialSheet，尝试匹配
  if (props.initialSheet) {
    const matched = renderConfig.value.sheets.find(s => s.sheet_name === props.initialSheet)
    if (matched) return matched.sheet_name
  }
  return renderConfig.value.sheets[0].sheet_name
})

const activeSheet = computed(() => {
  if (!renderConfig.value?.sheets?.length) return null
  return renderConfig.value.sheets.find(s => s.sheet_name === activeSheetName.value) ?? null
})

const activeSheetSchema = computed(() => activeSheet.value?.schema ?? {})
const activeSheetHtmlData = computed(() => activeSheet.value?.html_data ?? {})

const errorTitle = computed(() => {
  if (!error.value) return ''
  return '加载渲染配置失败'
})

const errorSubTitle = computed(() => {
  if (!error.value) return ''
  return error.value.message || '请检查网络连接后重试'
})

// ─── Methods ───
function onSave(data: Record<string, any>) {
  const payload: SavePayload = {
    sheet_name: activeSheetName.value,
    html_data: data,
  }
  emit('save-success', payload)
}

function onTrimmingSuggestion(payload: Record<string, any>) {
  emit('trigger-procedure-trimming-suggestion', payload)
}

function onConclusionChange(conclusion: string) {
  emit('conclusion-change', conclusion)
}

function onStepAdvance(step: number) {
  emit('step-advance', step)
}

function onSubtableToggle(subTableId: string) {
  emit('subtable-toggle', subTableId)
}

function onStandardSwitch(standard: string) {
  emit('standard-switch', standard)
}

function onSyncToDisclosureNotes(payload: Record<string, any>) {
  emit('sync-to-disclosure-notes', payload)
}

function onJumpToReference(refCode: string) {
  emit('jump-to-reference', refCode)
}
</script>

<style scoped>
.gt-wp-renderer {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.gt-wp-renderer__error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-bg-white, #fff);
  z-index: 99;
}

.gt-wp-renderer__univer-placeholder,
.gt-wp-renderer__unknown-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
