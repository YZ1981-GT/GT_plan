<template>
  <div class="check-block" :class="{ 'check-block--collapsed': collapsed }">
    <!-- 区块标题栏 -->
    <div class="check-block__header" @click="collapsed = !collapsed">
      <el-icon class="check-block__arrow">
        <ArrowRight v-if="collapsed" />
        <ArrowDown v-else />
      </el-icon>
      <span class="check-block__title">{{ config.title }}</span>
      <span class="check-block__count">({{ rows.length }} 条)</span>
      <el-tag v-if="hasAbnormalRows" type="danger" size="small" class="check-block__badge">
        有异常
      </el-tag>
      <span v-if="config.tips?.length" class="check-block__tip-icon">
        <el-tooltip
          :content="config.tips.join('；')"
          placement="top"
          :show-after="300"
        >
          <el-icon><InfoFilled /></el-icon>
        </el-tooltip>
      </span>
    </div>

    <!-- 区块内容 -->
    <div v-show="!collapsed" class="check-block__body">
      <!-- 工具栏 -->
      <div v-if="!readonly" class="check-block__toolbar">
        <el-button size="small" type="primary" plain @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-button size="small" plain @click="handleDeleteSelected" :disabled="!selectedRowId">
          <el-icon><Delete /></el-icon> 删除
        </el-button>
      </div>

      <!-- 数据表格 -->
      <div class="check-block__table-wrapper">
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :max-height="400"
          highlight-current-row
          @current-change="handleCurrentChange"
          :row-class-name="rowClassName"
          class="check-block__table"
        >
          <!-- 按列配置渲染 -->
          <template v-for="col in groupedColumns" :key="col.field">
            <el-table-column
              :prop="col.field"
              :label="col.label"
              :width="col.width"
              :min-width="col.minWidth || 80"
              :fixed="col.fixed ? 'left' : undefined"
              :align="col.align || 'left'"
              :class-name="getColumnClass(col)"
            >
              <template #default="{ row }">
                <!-- 序号列（只读） -->
                <span v-if="col.field === 'seq'">{{ row.seq }}</span>
                <!-- 是否异常（下拉） -->
                <template v-else-if="col.type === 'select' && col.field === 'is_abnormal'">
                  <el-select
                    v-if="!readonly"
                    v-model="row[col.field]"
                    size="small"
                    placeholder="否"
                    @change="(val: string) => handleFieldChange(row, col.field, val)"
                  >
                    <el-option value="否" label="否" />
                    <el-option value="是" label="是" />
                  </el-select>
                  <span v-else :class="{ 'text-danger': row[col.field] === '是' }">
                    {{ row[col.field] || '否' }}
                  </span>
                </template>
                <!-- 数字列 -->
                <template v-else-if="col.type === 'number'">
                  <el-input
                    v-if="!readonly && col.editable !== false"
                    v-model.number="row[col.field]"
                    size="small"
                    type="number"
                    :placeholder="col.placeholder"
                    @change="(val: string) => handleFieldChange(row, col.field, Number(val))"
                  />
                  <span v-else class="check-block__number">
                    {{ formatNumber(row[col.field]) }}
                  </span>
                </template>
                <!-- 日期列 -->
                <template v-else-if="col.type === 'date'">
                  <el-date-picker
                    v-if="!readonly"
                    v-model="row[col.field]"
                    size="small"
                    type="date"
                    format="YYYY-MM-DD"
                    value-format="YYYY-MM-DD"
                    :placeholder="col.placeholder || '选择日期'"
                    @change="(val: string) => handleFieldChange(row, col.field, val)"
                  />
                  <span v-else>{{ row[col.field] || '' }}</span>
                </template>
                <!-- 文本列（默认） -->
                <template v-else>
                  <el-input
                    v-if="!readonly && col.editable !== false"
                    v-model="row[col.field]"
                    size="small"
                    :placeholder="col.placeholder"
                    @change="(val: string) => handleFieldChange(row, col.field, val)"
                  />
                  <span v-else :class="{ 'check-block__empty': !row[col.field] }">
                    {{ row[col.field] || '' }}
                  </span>
                </template>
              </template>
            </el-table-column>
          </template>
        </el-table>
      </div>

      <!-- 合计行 -->
      <div v-if="rows.length > 0" class="check-block__totals">
        <span class="check-block__totals-label">合计：</span>
        <span v-for="(val, field) in totals" :key="field" class="check-block__total-item">
          {{ getFieldLabel(field as string) }}：<b>{{ formatNumber(val) }}</b>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowRight, ArrowDown, Plus, Delete, InfoFilled } from '@element-plus/icons-vue'
import type { CheckRow, BlockType } from './alternativeD05Types'
import type { BlockConfig, BlockColumnDef } from './blockColumnConfigs'

const props = defineProps<{
  config: BlockConfig
  rows: CheckRow[]
  totals: Record<string, number>
  readonly: boolean
}>()

const emit = defineEmits<{
  (e: 'add-row'): void
  (e: 'delete-row', rowId: string): void
  (e: 'update-field', rowId: string, field: string, value: any): void
}>()

const collapsed = ref(false)
const selectedRowId = ref<string | null>(null)

// ─── 分组列（分组表头 5 色轮转） ─────────────────────────────────────────────

const groupedColumns = computed(() => props.config.columns)

const hasAbnormalRows = computed(() =>
  props.rows.some((r) => r.is_abnormal === '是')
)

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAddRow() {
  emit('add-row')
}

function handleDeleteSelected() {
  if (selectedRowId.value) {
    emit('delete-row', selectedRowId.value)
    selectedRowId.value = null
  }
}

function handleFieldChange(row: CheckRow, field: string, value: any) {
  emit('update-field', row._row_id!, field, value)
}

function handleCurrentChange(row: CheckRow | null) {
  selectedRowId.value = row?._row_id ?? null
}

// ─── 辅助 ────────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: CheckRow }) {
  if (row.is_abnormal === '是') return 'check-block__row--abnormal'
  return ''
}

function getColumnClass(col: BlockColumnDef): string {
  if (!col.group) return ''
  // 5 色轮转：根据 group 索引分配颜色类
  const groups = [...new Set(props.config.columns.filter((c) => c.group).map((c) => c.group!))]
  const idx = groups.indexOf(col.group)
  return `check-block__col-group-${(idx % 5) + 1}`
}

function getFieldLabel(field: string): string {
  const col = props.config.columns.find((c) => c.field === field)
  return col?.label ?? field
}

function formatNumber(val: any): string {
  if (val == null || val === '') return ''
  const num = Number(val)
  if (isNaN(num)) return String(val)
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.check-block {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}

.check-block__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  cursor: pointer;
  user-select: none;
  font-weight: 500;
  font-size: 13px;
}

.check-block__arrow {
  transition: transform 0.2s;
}

.check-block__count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.check-block__badge {
  margin-left: auto;
}

.check-block__tip-icon {
  margin-left: 4px;
  color: var(--el-color-info);
  cursor: help;
}

.check-block__body {
  padding: 8px;
}

.check-block__toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
}

.check-block__table-wrapper {
  overflow-x: auto;
}

.check-block__table {
  font-size: 12px;
}

.check-block__number {
  text-align: right;
  display: block;
}

.check-block__empty {
  color: var(--el-text-color-placeholder);
}

.check-block__totals {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 3px;
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.check-block__totals-label {
  font-weight: 600;
}

.check-block__total-item b {
  color: var(--el-color-primary);
}

.text-danger {
  color: var(--el-color-danger);
  font-weight: 600;
}

/* 异常行红色高亮 */
:deep(.check-block__row--abnormal) {
  background-color: var(--el-color-danger-light-9) !important;
}

/* 分组列着色（5 色轮转） */
:deep(.check-block__col-group-1) { background-color: rgba(64, 158, 255, 0.04); }
:deep(.check-block__col-group-2) { background-color: rgba(103, 194, 58, 0.04); }
:deep(.check-block__col-group-3) { background-color: rgba(230, 162, 60, 0.04); }
:deep(.check-block__col-group-4) { background-color: rgba(144, 147, 153, 0.04); }
:deep(.check-block__col-group-5) { background-color: rgba(155, 89, 182, 0.04); }
</style>
