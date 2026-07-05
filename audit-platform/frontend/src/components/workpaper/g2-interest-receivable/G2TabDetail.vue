<template>
  <div class="g2-detail">
    <div class="section-head">
      <h3 class="sheet-title">G2-2 应收利息明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">新增行</el-button>
        <el-button size="small" @click="openReviewDialog('G2-2-detail')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="detail.dataRows.value" border size="small" max-height="500">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" width="140" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>
      <el-table-column label="投资类型" width="110">
        <template #default="{ row }">
          <el-input :model-value="row.investType" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'investType', v)" />
        </template>
      </el-table-column>
      <el-table-column label="面值/本金" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.faceValue" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'faceValue', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率(%)" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.couponRate" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" :precision="4"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'couponRate', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="计息起始日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.accrualStart" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => detail.updateCell(row.id, 'accrualStart', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="计息截止日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.accrualEnd" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => detail.updateCell(row.id, 'accrualEnd', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="计息天数" width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="计息天数 = 截止日 - 起始日">{{ row.accruedDays }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应计利息" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="应计利息 = 面值 × 利率/100 × 天数/365">{{ fmtNum(row.accruedInterest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已收利息" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.receivedInterest" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'receivedInterest', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期末应收" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末应收 = 应计利息 - 已收利息">{{ fmtNum(row.netReceivable) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="企业账面值" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.bookValue" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'bookValue', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <span :class="['formula-cell', { 'variance-warn': detail.isVarianceWarning(row) }]"
            title="差异 = 期末应收 - 企业账面值">
            {{ fmtNum(row.variance) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="减值阶段" width="100">
        <template #default="{ row }">
          <el-select :model-value="row.eclStage" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'eclStage', v)">
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        面值 {{ fmtNum(detail.totals.value.faceValue) }} ·
        应计利息 {{ fmtNum(detail.totals.value.accruedInterest) }} ·
        期末应收 {{ fmtNum(detail.totals.value.netReceivable) }} ·
        差异 {{ fmtNum(detail.totals.value.variance) }}
      </div>
    </div>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>计息天数 = 计息截止日 - 计息起始日（自然日）</li>
        <li>应计利息 = 面值 × 票面利率/100 × 计息天数/365（365天基准）</li>
        <li>期末应收 = 应计利息 - 已收利息；差异 = 期末应收 - 企业账面值</li>
        <li>|差异| > 100 元时橙色高亮提示，需关注原因</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2Detail } from '../../composables/useG2Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const detail = useG2Detail({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g2-detail { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.variance-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
