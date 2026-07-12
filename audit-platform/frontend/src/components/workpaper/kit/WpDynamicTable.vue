<script setup lang="ts">
/**
 * WpDynamicTable — 底稿动态表格组件（Wp_Kit）
 *
 * 统一13px字体（var(--wp-font-size)）、紧凑密度、auto-calc-col 计算列（灰底禁编辑）、
 * 合计行、动态新增/删除行、账龄动态列（agingBands prop）。
 * 金额单元格反映 DisplayPrefs_Store（inject DisplayPrefs_Key → useDisplayPrefsStore fallback）。
 *
 * Feature: platform-global-hardening
 * Requirements: 4.5, 4.7
 */
import { computed, inject } from 'vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

/** 列定义 */
export interface WpDynamicColumn {
  /** 列唯一标识 */
  key: string
  /** 列标题 */
  label: string
  /** 列宽（如 '120px'） */
  width?: string
  /** 最小列宽 */
  minWidth?: string
  /** 是否计算列（灰底 + 禁编辑） */
  autoCalc?: boolean
  /** 是否金额列（走 displayPrefs 格式化） */
  isAmount?: boolean
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
  /** 自定义 tooltip（用于 auto-calc 来源说明） */
  tooltip?: string
  /** 是否固定列 */
  fixed?: 'left' | 'right' | boolean
}

/** 账龄段定义 */
export interface AgingBand {
  /** 账龄段标识 */
  key: string
  /** 账龄段标题（如 '1年以内'） */
  label: string
  /** 列宽 */
  width?: string
}

/** 行数据（泛型 Record） */
export type DynamicRow = Record<string, any> & {
  /** 行唯一标识 */
  _id?: string
}

const props = withDefaults(defineProps<{
  /** 列定义数组 */
  columns: WpDynamicColumn[]
  /** 行数据（v-model） */
  rows: DynamicRow[]
  /** 账龄动态列（可选） */
  agingBands?: AgingBand[]
  /** 是否只读模式 */
  readonly?: boolean
}>(), {
  agingBands: () => [],
  readonly: false,
})

const emit = defineEmits<{
  'update:rows': [rows: DynamicRow[]]
}>()

// 优先从祖先注入获取 displayPrefs，兜底直接使用 store
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

/** 合并列定义：基础列 + 账龄动态列 */
const mergedColumns = computed<WpDynamicColumn[]>(() => {
  const base = props.columns
  if (!props.agingBands || props.agingBands.length === 0) return base
  const agingCols: WpDynamicColumn[] = props.agingBands.map(band => ({
    key: band.key,
    label: band.label,
    width: band.width || '100px',
    isAmount: true,
    align: 'right',
  }))
  return [...base, ...agingCols]
})

/** 计算合计行 */
const totalsRow = computed<Record<string, any>>(() => {
  const totals: Record<string, any> = {}
  for (const col of mergedColumns.value) {
    if (col.isAmount) {
      let sum = 0
      let hasValue = false
      for (const row of props.rows) {
        const v = row[col.key]
        if (v != null && !isNaN(Number(v))) {
          sum += Number(v)
          hasValue = true
        }
      }
      totals[col.key] = hasValue ? sum : null
    } else {
      totals[col.key] = ''
    }
  }
  return totals
})

/** 格式化金额值 */
function formatAmount(value: any): string {
  return displayPrefs.fmtAmount(value)
}

/** 获取金额 CSS 类名 */
function getAmountClass(value: any): string {
  return displayPrefs.amountClass(value)
}

/** 新增行 */
function addRow() {
  if (props.readonly) return
  const newRow: DynamicRow = { _id: `row_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` }
  for (const col of mergedColumns.value) {
    newRow[col.key] = col.isAmount ? null : ''
  }
  emit('update:rows', [...props.rows, newRow])
}

/** 删除行 */
function removeRow(index: number) {
  if (props.readonly) return
  const updated = [...props.rows]
  updated.splice(index, 1)
  emit('update:rows', updated)
}

/** 单元格值变更 */
function onCellChange(rowIndex: number, colKey: string, value: any) {
  const updated = [...props.rows]
  updated[rowIndex] = { ...updated[rowIndex], [colKey]: value }
  emit('update:rows', updated)
}
</script>

<template>
  <div class="wp-dynamic-table">
    <el-table
      :data="rows"
      border
      size="small"
      class="wp-dynamic-table__main"
      :show-summary="false"
    >
      <!-- 序号列 -->
      <el-table-column
        type="index"
        label="#"
        width="50"
        align="center"
        fixed="left"
      />

      <!-- 数据列 -->
      <el-table-column
        v-for="col in mergedColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth || '100'"
        :align="col.align || (col.isAmount ? 'right' : 'left')"
        :fixed="col.fixed"
        :class-name="col.autoCalc ? 'wp-dynamic-table__col--calc' : ''"
      >
        <template #default="{ row, $index }">
          <!-- auto-calc 计算列：只读灰底显示 -->
          <template v-if="col.autoCalc">
            <span
              v-if="col.isAmount"
              class="wp-dynamic-table__cell--calc"
              :class="getAmountClass(row[col.key])"
              :title="col.tooltip || '自动计算'"
            >{{ formatAmount(row[col.key]) }}</span>
            <span
              v-else
              class="wp-dynamic-table__cell--calc"
              :title="col.tooltip || '自动计算'"
            >{{ row[col.key] ?? '—' }}</span>
          </template>

          <!-- 金额列：可编辑或只读 -->
          <template v-else-if="col.isAmount">
            <template v-if="readonly">
              <span :class="getAmountClass(row[col.key])">{{ formatAmount(row[col.key]) }}</span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row[col.key]"
                :controls="false"
                :precision="2"
                size="small"
                class="wp-dynamic-table__input-number"
                @update:model-value="onCellChange($index, col.key, $event)"
              />
            </template>
          </template>

          <!-- 普通文本列 -->
          <template v-else>
            <template v-if="readonly">
              <span>{{ row[col.key] ?? '—' }}</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row[col.key]"
                size="small"
                @update:model-value="onCellChange($index, col.key, $event)"
              />
            </template>
          </template>
        </template>
      </el-table-column>

      <!-- 操作列（非只读） -->
      <el-table-column
        v-if="!readonly"
        label="操作"
        width="60"
        align="center"
        fixed="right"
      >
        <template #default="{ $index }">
          <el-button
            type="danger"
            link
            size="small"
            @click="removeRow($index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="wp-dynamic-table__totals">
      <el-table
        :data="[totalsRow]"
        border
        size="small"
        class="wp-dynamic-table__totals-table"
        :show-header="false"
      >
        <el-table-column width="50" align="center" fixed="left">
          <template #default>
            <strong>合计</strong>
          </template>
        </el-table-column>

        <el-table-column
          v-for="col in mergedColumns"
          :key="'total-' + col.key"
          :prop="col.key"
          :width="col.width"
          :min-width="col.minWidth || '100'"
          :align="col.align || (col.isAmount ? 'right' : 'left')"
          :fixed="col.fixed"
        >
          <template #default="{ row }">
            <strong v-if="col.isAmount" :class="getAmountClass(row[col.key])">
              {{ formatAmount(row[col.key]) }}
            </strong>
            <span v-else />
          </template>
        </el-table-column>

        <el-table-column v-if="!readonly" width="60" align="center" fixed="right">
          <template #default><span /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增行按钮 -->
    <div v-if="!readonly" class="wp-dynamic-table__footer">
      <el-button type="primary" plain size="small" @click="addRow">
        + 新增行
      </el-button>
      <span class="wp-dynamic-table__row-count">共 {{ rows.length }} 行</span>
    </div>
  </div>
</template>

<style scoped>
.wp-dynamic-table {
  font-size: var(--wp-font-size, 13px);
}

.wp-dynamic-table__main {
  width: 100%;
}

.wp-dynamic-table__main :deep(.el-table__body td),
.wp-dynamic-table__main :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
  padding: 4px 8px;
}

/* auto-calc 计算列灰底 */
.wp-dynamic-table__main :deep(.wp-dynamic-table__col--calc) {
  background-color: #f5f7fa !important;
}

.wp-dynamic-table__cell--calc {
  color: #909399;
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
}

/* 金额输入框紧凑 */
.wp-dynamic-table__input-number {
  width: 100%;
}

.wp-dynamic-table__input-number :deep(.el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 合计行 */
.wp-dynamic-table__totals {
  margin-top: -1px;
}

.wp-dynamic-table__totals-table {
  width: 100%;
}

.wp-dynamic-table__totals-table :deep(.el-table__body td) {
  font-size: var(--wp-font-size, 13px);
  padding: 4px 8px;
  background-color: #fafafa;
  font-weight: 600;
}

/* 底部操作区 */
.wp-dynamic-table__footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  padding: 4px 0;
}

.wp-dynamic-table__row-count {
  font-size: 12px;
  color: #909399;
}

/* 负数红字 */
:deep(.gt-amount--negative) {
  color: var(--el-color-danger, #f56c6c);
}

/* 变动高亮 */
:deep(.gt-amount--highlight) {
  font-weight: 600;
}
</style>
