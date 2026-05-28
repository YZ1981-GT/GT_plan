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
      <!-- Sheet 选择器（多 sheet 时显示） -->
      <div v-if="visibleSheets.length > 1" class="gt-wp-renderer__sheet-tabs">
        <el-tabs
          v-model="activeSheetName"
          type="card"
          class="gt-wp-renderer__sheet-tabs-inner"
        >
          <el-tab-pane
            v-for="sheet in visibleSheets"
            :key="sheet.sheet_name"
            :name="sheet.sheet_name"
          >
            <template #label>
              <span class="gt-wp-renderer__tab-label" :title="sheet.sheet_name">
                <span class="gt-wp-renderer__tab-icon">{{ getSheetIcon(sheet.componentType) }}</span>
                <span class="gt-wp-renderer__tab-name">{{ sheet.sheet_name }}</span>
              </span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 内容区域 -->
      <div class="gt-wp-renderer__content">
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
      </div><!-- /.gt-wp-renderer__content -->
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
// 内部维护 activeSheetName（支持 sheet 切换）
const internalActiveSheetName = ref<string>('')

// ─── Composables ───
const wpIdRef = toRef(props, 'wpId')
const { renderConfig, loading, error, reload } = useWpRenderer(wpIdRef)

// ─── Computed ───
/** 可见 sheet 列表（过滤掉 skip 类，但 skip 仍可在唯一 sheet 时显示） */
const visibleSheets = computed(() => {
  const sheets = renderConfig.value?.sheets ?? []
  // 全部 skip 时仍展示一个；否则过滤 skip
  const nonSkip = sheets.filter(s => s.componentType !== 'skip')
  return nonSkip.length > 0 ? nonSkip : sheets
})

const activeSheetName = computed<string>({
  get() {
    if (!renderConfig.value?.sheets?.length) return ''
    // 优先用内部 ref（用户切换过）
    if (internalActiveSheetName.value) {
      const exists = renderConfig.value.sheets.find(s => s.sheet_name === internalActiveSheetName.value)
      if (exists) return internalActiveSheetName.value
    }
    // 否则匹配 initialSheet
    if (props.initialSheet) {
      const matched = renderConfig.value.sheets.find(s => s.sheet_name === props.initialSheet)
      if (matched) return matched.sheet_name
    }
    // 兜底：第一个非 skip 的 sheet
    return visibleSheets.value[0]?.sheet_name ?? renderConfig.value.sheets[0].sheet_name
  },
  set(name: string) {
    internalActiveSheetName.value = name
    emit('sheet-change', name)
  },
})

const activeSheet = computed(() => {
  if (!renderConfig.value?.sheets?.length) return null
  return renderConfig.value.sheets.find(s => s.sheet_name === activeSheetName.value) ?? null
})

const activeSheetSchema = computed(() => activeSheet.value?.schema ?? {})
const activeSheetHtmlData = computed<any>(() => activeSheet.value?.html_data ?? {})
/** 当前 sheet 的 componentType（每个 sheet 独立路由） */
const componentType = computed<WpComponentType>(() => {
  return (activeSheet.value?.componentType as WpComponentType) ?? 'skip'
})

/** componentType → 图标（sheet tab 显示） */
function getSheetIcon(ct: string): string {
  const map: Record<string, string> = {
    'a-program-console': '📋',
    'b-index': '🗂️',
    'c-note-table': '📝',
    'd-form-table': '📑',
    'd-form-paragraph': '📄',
    'd-form-qa': '❓',
    'd-form-confirmation': '✉️',
    'd-form-review': '✍️',
    'e-control-test': '🧪',
    'h-static-doc': '📖',
    'univer': '📊',
    'skip': '⏭️',
  }
  return map[ct] || '📄'
}

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
  display: flex;
  flex-direction: column;
}

.gt-wp-renderer__sheet-tabs {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-page);
  padding: 4px 12px 0;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__nav-wrap) {
  margin-bottom: 0;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__header) {
  margin-bottom: 0;
  border-bottom: 0;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__content) {
  display: none;
}

.gt-wp-renderer__sheet-tabs-inner :deep(.el-tabs__item) {
  height: 36px;
  line-height: 36px;
  font-size: 13px;
}

.gt-wp-renderer__tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 240px;
}

.gt-wp-renderer__tab-icon {
  flex: 0 0 auto;
}

.gt-wp-renderer__tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-wp-renderer__content {
  flex: 1 1 auto;
  position: relative;
  overflow: auto;
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
