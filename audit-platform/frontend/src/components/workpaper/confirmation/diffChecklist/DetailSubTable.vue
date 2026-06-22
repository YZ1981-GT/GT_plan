<template>
  <div class="detail-sub-table">
    <!-- 区块标题 -->
    <div class="detail-sub-table__header">
      <span class="detail-sub-table__title">{{ sectionLabel }}</span>
      <span class="detail-sub-table__total">
        合计：<strong>{{ formatAmount(total) }}</strong>
      </span>
      <el-button
        v-if="!readonly"
        size="small"
        type="primary"
        :icon="Plus"
        text
        @click="$emit('add-row')"
      >
        新增行
      </el-button>
    </div>

    <!-- 明细网格 -->
    <el-table
      :data="rows"
      border
      size="small"
      :show-header="rows.length > 0"
      max-height="240"
      :empty-text="readonly ? '无明细' : '点击"新增行"添加未达明细'"
      class="detail-sub-table__grid"
    >
      <el-table-column label="序号" width="50" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <el-table-column label="日期1" width="120">
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.date1"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @update:model-value="(val: string) => $emit('update-row', row._row_id, 'date1', val)"
          />
          <span v-else>{{ row.date1 || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="日期2" width="120">
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.date2"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @update:model-value="(val: string) => $emit('update-row', row._row_id, 'date2', val)"
          />
          <span v-else>{{ row.date2 || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="凭证号" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.voucher_no"
            size="small"
            placeholder="凭证号"
            @change="(val: string) => $emit('update-row', row._row_id, 'voucher_no', val)"
          />
          <span v-else>{{ row.voucher_no || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.summary"
            size="small"
            placeholder="摘要"
            @change="(val: string) => $emit('update-row', row._row_id, 'summary', val)"
          />
          <span v-else>{{ row.summary || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!readonly"
            :model-value="row.amount"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(val: number) => $emit('update-row', row._row_id, 'amount', val)"
          />
          <span v-else class="detail-sub-table__amount">{{ formatAmount(row.amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.ref_index"
            size="small"
            placeholder="索引"
            @change="(val: string) => $emit('update-row', row._row_id, 'ref_index', val)"
          />
          <span v-else>{{ row.ref_index || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否调整" width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-if="!readonly"
            :model-value="row.need_adjust"
            size="small"
            @change="(val: boolean) => $emit('update-row', row._row_id, 'need_adjust', val)"
          />
          <el-tag v-else :type="row.need_adjust ? 'danger' : 'info'" size="small">
            {{ row.need_adjust ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!readonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="danger"
            :icon="Delete"
            text
            @click="$emit('delete-row', row._row_id)"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { SubTableRow } from './diffChecklistTypes'

const props = defineProps<{
  /** 区块标识：b/c/f/g */
  section: 'b' | 'c' | 'f' | 'g'
  /** 区块显示标签 */
  sectionLabel: string
  /** 明细行数据 */
  rows: SubTableRow[]
  /** 合计金额（由 composable 计算传入） */
  total: number
  /** 是否只读 */
  readonly: boolean
}>()

defineEmits<{
  (e: 'add-row'): void
  (e: 'delete-row', rowId: string): void
  (e: 'update-row', rowId: string, field: string, value: any): void
}>()

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.detail-sub-table {
  margin: 8px 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  background: var(--el-fill-color-lighter);
}

.detail-sub-table__header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.detail-sub-table__title {
  font-weight: 600;
  font-size: 13px;
}

.detail-sub-table__total {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.detail-sub-table__total strong {
  color: var(--el-color-primary);
  font-variant-numeric: tabular-nums;
}

.detail-sub-table__amount {
  font-variant-numeric: tabular-nums;
}

.detail-sub-table__grid {
  width: 100%;
}
</style>
