<template>
  <div class="h1-tab-related-party">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：识别与关联方之间的固定资产交易，评价交易价格公允性，价格差异率超过10%的交易已追加程序并充分披露。</template>
    </el-alert>

    <div class="methodology-context">
      <p>检查与关联方之间的固定资产交易（购入/出售/无偿调拨），关注交易价格公允性。价格差异率超过10%标红需追加程序。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-18 关联方固定资产交易 <el-tag size="small" type="info">共 {{ relatedRows.length }} 笔</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-18')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="relatedRows" border stripe size="small" max-height="420">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="counterparty" label="关联方" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.counterparty" size="small" @change="onCell(row, 'counterparty')" />
            <span v-else>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.relationship" size="small" @change="onCell(row, 'relationship')" />
            <span v-else>{{ row.relationship }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transType" label="交易方向" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.transType" size="small" style="width:76px" @change="onCell(row, 'transType')">
              <el-option label="购入" value="购入" />
              <el-option label="出售" value="出售" />
              <el-option label="无偿调拨" value="无偿调拨" />
            </el-select>
            <span v-else>{{ row.transType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transAmount" label="交易价格" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" @change="onCell(row, 'transAmount')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="appraisedValue" label="公允/评估价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.priceDiffRate) > 10 }]" title="差异率=(交易-公允)÷公允×100%">
              {{ row.priceDiffRate != null ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingBasis" label="定价依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingBasis" size="small" @change="onCell(row, 'pricingBasis')" />
            <span v-else>{{ row.pricingBasis }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批情况" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small" @change="onCell(row, 'approvalDoc')" />
            <span v-else>{{ row.approvalDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" style="width:66px" @change="onCell(row, 'conclusion')">
              <el-option label="公允" value="公允" />
              <el-option label="不公允" value="不公允" />
            </el-select>
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('18', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>交易金额合计: <b class="amount-cell">{{ fmtAmt(transactionTotal) }}</b></span>
        <span>差异率>10%: <b :class="{ 'error-amount': abnormalCount > 0 }">{{ abnormalCount }}</b> 笔</span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul><li>价格差异率=(交易价-公允价)÷公允价×100%，超10%标红</li><li>需获取独立估值报告或可比交易作定价依据</li></ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1LeaseCheck, type RelatedPartyRow } from '../../composables/useH1LeaseCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const { relatedRows, unfairPricingRows, addRelatedRow, removeRow, updateRelatedCell } = useH1LeaseCheck(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
)

const transactionTotal = computed(() => relatedRows.value.reduce((s, r) => s + (r.transAmount || 0), 0))
const abnormalCount = computed(() => unfairPricingRows.value.length)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('关联方名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name != null) {
    addRelatedRow()
    const last = relatedRows.value[relatedRows.value.length - 1]
    if (last) updateRelatedCell(last.rowId, 'counterparty', name)
  }
}
function onCell(row: RelatedPartyRow, field: keyof RelatedPartyRow) { updateRelatedCell(row.rowId, field, (row as any)[field]) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
