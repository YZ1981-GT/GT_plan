<script setup lang="ts">
/**
 * D4TabProductPrice — D4-11 产品价格趋势
 *
 * 动态行 + 变动率高亮
 * Requirements: 8.5, 19.3
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Analysis, type ProductPriceRow } from '../../composables/useD4Analysis'
import { calcChangeRate, isChangeRateExceeding } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { productPrices, addProductPriceRow, removeProductPriceRow } = useD4Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtRate(val: number | '' | 'N/A'): string {
  if (val === '' || val === 'N/A') return String(val || '-')
  return (val * 100).toFixed(1) + '%'
}

function getRowChangeRate(row: ProductPriceRow): number | '' | 'N/A' {
  return calcChangeRate(row.priorPrice, row.currentPrice)
}
</script>

<template>
  <div class="d4-tab-product-price">
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addProductPriceRow()">
        + 添加行
      </el-button>
    </div>

    <el-table :data="productPrices" border stripe>
      <el-table-column prop="product" label="产品名称" min-width="160" />
      <el-table-column label="本期单价" width="120" align="right">
        <template #default="{ row }">{{ row.currentPrice.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="上期单价" width="120" align="right">
        <template #default="{ row }">{{ row.priorPrice.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-600': isChangeRateExceeding(getRowChangeRate(row), 0.2) }">
            {{ fmtRate(getRowChangeRate(row)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="120" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeProductPriceRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-11-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入产品价格趋势分析..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-product-price { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
</style>
