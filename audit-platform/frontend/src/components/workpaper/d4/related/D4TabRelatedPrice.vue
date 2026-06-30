<script setup lang="ts">
/**
 * D4TabRelatedPrice — D4-21 关联方价格公允性分析
 *
 * 对比分析表（关联vs非关联单价+差异率+结论）
 * >10%黄色 / >20%红色
 * GtIndexChip→A17 + AI评价按钮(disabled) + 💬复核
 *
 * Requirements: 13.1-13.8
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4RelatedPrice, type RelatedPriceRow } from '../../composables/useD4RelatedPrice'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  rows,
  relatedSalesTotal,
  proportionToRevenue,
  auditNote,
  auditConclusion,
  getDiffRateColor,
  addRow,
  removeRow,
  updateCell,
} = useD4RelatedPrice({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number): string {
  if (v === 0) return '-'
  return v.toFixed(2) + '%'
}

function getRowClass({ row }: { row: RelatedPriceRow }): string {
  const color = getDiffRateColor(row.priceDiffRate)
  if (color === 'red') return 'row-red'
  if (color === 'yellow') return 'row-yellow'
  return ''
}
</script>

<template>
  <div class="d4-tab-related-price">
    <!-- 汇总信息 -->
    <div class="summary-bar mb-3">
      <span class="summary-item">
        <label>关联方销售合计：</label>
        <strong>{{ fmtAmount(relatedSalesTotal) }}</strong>
      </span>
      <span class="summary-item">
        <label>占营业收入比例：</label>
        <strong>{{ fmtPercent(proportionToRevenue) }}</strong>
      </span>
      <!-- GtIndexChip placeholder → A17 -->
      <span class="index-chip" title="关联方披露 → A17">📎 A17</span>
    </div>

    <!-- 工具栏 -->
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow">
        + 添加对比项
      </el-button>
    </div>

    <!-- 对比分析表 -->
    <el-table :data="rows" border stripe max-height="500" :row-class-name="getRowClass">
      <el-table-column label="产品/服务" min-width="120">
        <template #default="{ row }">
          <el-input
            v-model="row.product"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'product', row.product)"
          />
        </template>
      </el-table-column>

      <el-table-column label="关联客户" min-width="110">
        <template #default="{ row }">
          <el-input
            v-model="row.relatedCustomer"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'relatedCustomer', row.relatedCustomer)"
          />
        </template>
      </el-table-column>

      <el-table-column label="关联单价" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.relatedPrice"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'relatedPrice', row.relatedPrice)"
          />
        </template>
      </el-table-column>

      <el-table-column label="非关联客户" min-width="110">
        <template #default="{ row }">
          <el-input
            v-model="row.nonRelatedCustomer"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'nonRelatedCustomer', row.nonRelatedCustomer)"
          />
        </template>
      </el-table-column>

      <el-table-column label="非关联单价" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.nonRelatedPrice"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'nonRelatedPrice', row.nonRelatedPrice)"
          />
        </template>
      </el-table-column>

      <el-table-column label="差异率" width="90" align="right">
        <template #default="{ row }">
          <span :class="['diff-rate', getDiffRateColor(row.priceDiffRate)]">
            {{ fmtPercent(row.priceDiffRate) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="原因说明" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.reason"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'reason', row.reason)"
          />
        </template>
      </el-table-column>

      <el-table-column label="结论" width="90" align="center">
        <template #default="{ row }">
          <el-select
            v-model="row.conclusion"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'conclusion', row.conclusion)"
          >
            <el-option value="" label="-" />
            <el-option value="normal" label="正常" />
            <el-option value="attention" label="关注" />
            <el-option value="abnormal" label="异常" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="updateCell(row.rowId, 'remark', row.remark)"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 阈值说明 -->
    <div class="threshold-legend mt-2">
      <span class="legend-item yellow">■ 差异率>10%（关注）</span>
      <span class="legend-item red">■ 差异率>20%（重大偏离）</span>
    </div>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI评价</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-21-note')">💬</el-button>
        </div>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="请输入关联方价格公允性分析结论..."
      />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-related-price { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mt-2 { margin-top: 8px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }

.summary-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
.summary-item label { color: #606266; font-size: 13px; }
.summary-item strong { color: #303133; }
.index-chip {
  margin-left: auto;
  padding: 2px 8px;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
  font-size: 12px;
  color: #409eff;
  cursor: pointer;
}

.diff-rate.red { color: #f56c6c; font-weight: 600; }
.diff-rate.yellow { color: #e6a23c; font-weight: 600; }

.threshold-legend { display: flex; gap: 16px; font-size: 12px; color: #606266; }
.legend-item.yellow { color: #e6a23c; }
.legend-item.red { color: #f56c6c; }

:deep(.row-red) { background-color: #fef0f0 !important; }
:deep(.row-yellow) { background-color: #fdf6ec !important; }
</style>
