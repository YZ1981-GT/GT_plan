<!--
  GtWordTemplateStructuredView.vue — Word 模板结构化视图组件

  Spec: .kiro/specs/word-template-dual-mode/
  Task: 4.2

  渲染规则：
  - heading → el-card title
  - paragraph with placeholders → inline editable inputs
  - paragraph without placeholders → read-only styled text
  - table → el-table with editable cells at placeholder positions
  - AI button → disabled el-button with tooltip (Phase3)
-->
<template>
  <div class="gt-wt-structured-view">
    <!-- 无占位符提示 -->
    <el-alert
      v-if="!hasEditableFields"
      type="info"
      :closable="false"
      show-icon
      class="gt-wt-structured-view__empty"
    >
      该模板无可编辑字段，请使用在线编辑模式
    </el-alert>

    <!-- 卡片式渲染 -->
    <template v-for="section in sections" :key="section.key">
      <el-card
        v-if="section.type === 'heading'"
        class="gt-wt-structured-view__card"
        shadow="never"
      >
        <template #header>
          <span class="gt-wt-structured-view__card-title">{{ section.text }}</span>
        </template>
        <!-- 该标题下的段落和表格 -->
        <template v-for="child in section.children" :key="child.key">
          <!-- 含占位符的段落：渲染可编辑字段 -->
          <div v-if="child.type === 'paragraph' && child.placeholderIds.length > 0" class="gt-wt-structured-view__field-group">
            <div
              v-for="phId in child.placeholderIds"
              :key="phId"
              class="gt-wt-structured-view__field-row"
            >
              <label class="gt-wt-structured-view__field-label">{{ getPlaceholderLabel(phId) }}</label>
              <div class="gt-wt-structured-view__field-input">
                <!-- date type -->
                <el-date-picker
                  v-if="getPlaceholderType(phId) === 'date'"
                  :model-value="fieldValues[phId] || ''"
                  type="date"
                  value-format="YYYY-MM-DD"
                  :placeholder="getPlaceholderDefault(phId) || '选择日期'"
                  :disabled="readonly"
                  @update:model-value="(v: string) => emit('update:field', phId, v || '')"
                />
                <!-- textarea type -->
                <el-input
                  v-else-if="getPlaceholderType(phId) === 'textarea'"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :model-value="fieldValues[phId] || ''"
                  :placeholder="getPlaceholderDefault(phId) || '请输入'"
                  :disabled="readonly"
                  @update:model-value="(v: string) => emit('update:field', phId, v)"
                />
                <!-- number type -->
                <el-input-number
                  v-else-if="getPlaceholderType(phId) === 'number'"
                  :model-value="Number(fieldValues[phId]) || undefined"
                  :placeholder="getPlaceholderDefault(phId) || '0'"
                  :disabled="readonly"
                  controls-position="right"
                  @update:model-value="(v: number | undefined) => emit('update:field', phId, String(v ?? ''))"
                />
                <!-- text (default) -->
                <el-input
                  v-else
                  :model-value="fieldValues[phId] || ''"
                  :placeholder="getPlaceholderDefault(phId) || '请输入'"
                  :disabled="readonly"
                  @update:model-value="(v: string) => emit('update:field', phId, v)"
                />
                <!-- AI Fill button (disabled stub) -->
                <el-tooltip
                  v-if="getPlaceholderType(phId) === 'text' || getPlaceholderType(phId) === 'textarea'"
                  content="AI 填充功能即将上线"
                  placement="top"
                >
                  <el-button
                    size="small"
                    :icon="MagicStick"
                    disabled
                    class="gt-wt-structured-view__ai-btn"
                    @click="emit('ai-fill', phId)"
                  />
                </el-tooltip>
              </div>
            </div>
          </div>

          <!-- 纯文本段落：只读 -->
          <p
            v-else-if="child.type === 'paragraph'"
            class="gt-wt-structured-view__readonly-text"
          >
            {{ child.text }}
          </p>

          <!-- 表格 -->
          <div v-else-if="child.type === 'table'" class="gt-wt-structured-view__table-wrap">
            <el-table :data="child.rows" border size="small" style="width: 100%">
              <el-table-column
                v-for="(_, colIdx) in child.rows[0] || []"
                :key="colIdx"
                :label="child.rows[0]?.[colIdx] || `列${colIdx + 1}`"
                :min-width="120"
              >
                <template #default="{ row, $index }">
                  <!-- Skip header row (index 0) -->
                  <template v-if="$index === 0">
                    {{ row[colIdx] }}
                  </template>
                  <!-- Check if cell contains a placeholder -->
                  <template v-else-if="getCellPlaceholder(child, $index, colIdx)">
                    <el-input
                      size="small"
                      :model-value="fieldValues[getCellPlaceholder(child, $index, colIdx)!] || ''"
                      :placeholder="getPlaceholderDefault(getCellPlaceholder(child, $index, colIdx)!) || row[colIdx]"
                      :disabled="readonly"
                      @update:model-value="(v: string) => emit('update:field', getCellPlaceholder(child, $index, colIdx)!, v)"
                    />
                  </template>
                  <template v-else>
                    {{ row[colIdx] }}
                  </template>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import type { TemplateStructure, PlaceholderDef } from './composables/useWordTemplateStructured'

const props = defineProps<{
  templateStructure: TemplateStructure
  fieldValues: Record<string, string>
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:field': [fieldId: string, value: string]
  'ai-fill': [fieldId: string]
}>()

// ─── Placeholder helpers ───
const placeholderMap = computed(() => {
  const map = new Map<string, PlaceholderDef>()
  for (const p of props.templateStructure?.placeholders || []) {
    map.set(p.field_id, p)
  }
  return map
})

function getPlaceholderLabel(fieldId: string): string {
  return placeholderMap.value.get(fieldId)?.label || fieldId
}

function getPlaceholderType(fieldId: string): string {
  return placeholderMap.value.get(fieldId)?.data_type || 'text'
}

function getPlaceholderDefault(fieldId: string): string {
  return placeholderMap.value.get(fieldId)?.default_value || ''
}

// ─── Check if any editable fields exist ───
const hasEditableFields = computed(() => {
  return (props.templateStructure?.placeholders?.length ?? 0) > 0
})

// ─── Build sections from paragraphs + tables ───
interface SectionChild {
  key: string
  type: 'paragraph' | 'table'
  text?: string
  placeholderIds: string[]
  rows?: string[][]
  tableIndex?: number
}

interface Section {
  key: string
  type: 'heading'
  text: string
  children: SectionChild[]
}

const sections = computed<Section[]>(() => {
  const ts = props.templateStructure
  if (!ts) return []

  const result: Section[] = []
  let currentSection: Section | null = null

  // Merge paragraphs and tables by index order
  type DocElement = { kind: 'para'; data: typeof ts.paragraphs[0] } | { kind: 'table'; data: typeof ts.tables[0] }
  const elements: DocElement[] = [
    ...ts.paragraphs.map(p => ({ kind: 'para' as const, data: p })),
    ...ts.tables.map(t => ({ kind: 'table' as const, data: t })),
  ].sort((a, b) => a.data.index - b.data.index)

  for (const el of elements) {
    if (el.kind === 'para') {
      const para = el.data
      if (para.heading_level > 0) {
        // Start a new section
        currentSection = {
          key: `section-${para.index}`,
          type: 'heading',
          text: para.text,
          children: [],
        }
        result.push(currentSection)
      } else {
        // Add as child to current section
        if (!currentSection) {
          currentSection = { key: 'section-root', type: 'heading', text: '文档内容', children: [] }
          result.push(currentSection)
        }
        currentSection.children.push({
          key: `para-${para.index}`,
          type: 'paragraph',
          text: para.text,
          placeholderIds: para.placeholder_ids || [],
        })
      }
    } else {
      const table = el.data
      if (!currentSection) {
        currentSection = { key: 'section-root', type: 'heading', text: '文档内容', children: [] }
        result.push(currentSection)
      }
      currentSection.children.push({
        key: `table-${table.index}`,
        type: 'table',
        placeholderIds: table.placeholder_ids || [],
        rows: table.rows,
        tableIndex: table.index,
      })
    }
  }

  return result
})

// ─── Table cell placeholder detection ───
function getCellPlaceholder(child: SectionChild, _rowIdx: number, _colIdx: number): string | null {
  if (!child.placeholderIds?.length) return null
  // Check if any placeholder's position matches this table cell
  for (const phId of child.placeholderIds) {
    const ph = placeholderMap.value.get(phId)
    if (ph?.position?.table_index === child.tableIndex &&
        ph?.position?.row === _rowIdx &&
        ph?.position?.col === _colIdx) {
      return phId
    }
  }
  return null
}
</script>

<style scoped>
.gt-wt-structured-view {
  padding: 16px;
}

.gt-wt-structured-view__empty {
  margin-bottom: 16px;
}

.gt-wt-structured-view__card {
  margin-bottom: 16px;
}

.gt-wt-structured-view__card-title {
  font-weight: 600;
  font-size: 15px;
}

.gt-wt-structured-view__field-group {
  margin-bottom: 12px;
}

.gt-wt-structured-view__field-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.gt-wt-structured-view__field-label {
  min-width: 100px;
  max-width: 160px;
  padding-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}

.gt-wt-structured-view__field-input {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.gt-wt-structured-view__ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}

.gt-wt-structured-view__readonly-text {
  margin: 8px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.gt-wt-structured-view__table-wrap {
  margin: 12px 0;
}
</style>
