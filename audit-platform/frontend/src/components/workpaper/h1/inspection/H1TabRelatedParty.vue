<template>
  <div class="h1-tab-related-party">
    <div class="methodology-context">
      <p>检查与关联方之间的固定资产交易（购入/出售/无偿调拨），关注交易价格公允性。价格差异率超过10%标红需追加程序。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-18 关联方固定资产交易（{{ state.rows.value.length }} 笔）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-18')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="420">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="relatedPartyName" label="关联方" min-width="120" fixed />
        <el-table-column prop="relationship" label="关联关系" width="100" />
        <el-table-column prop="assetName" label="资产名称" min-width="110" />
        <el-table-column prop="transactionType" label="交易方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.transactionType === '购入' ? 'primary' : 'warning'" size="small">{{ row.transactionType }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="transactionPrice" label="交易价格" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.transactionPrice) }}</span></template>
        </el-table-column>
        <el-table-column prop="fairValue" label="公允价值" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.fairValue) }}</span></template>
        </el-table-column>
        <el-table-column label="差异率%" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.priceDiffRate) > 10 }]" title="差异率=(交易-公允)÷公允×100%">
              {{ row.priceDiffRate != null ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingBasis" label="定价依据" min-width="120" />
        <el-table-column prop="approvalInfo" label="审批情况" width="100" />
        <el-table-column prop="conclusion" label="结论" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" style="width:55px">
              <el-option label="OK" value="OK" />
              <el-option label="异" value="ERR" />
            </el-select>
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>交易金额合计: <b class="amount-cell">{{ fmtAmt(state.transactionTotal.value) }}</b></span>
        <span>差异率>10%: <b :class="{ 'error-amount': state.abnormalCount.value > 0 }">{{ state.abnormalCount.value }}</b> 笔</span>
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
import { useH1LeaseCheck } from '../../composables/useH1LeaseCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const state = useH1LeaseCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, { variant: 'relatedParty' })

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('关联方名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-related-party { padding: 16px; font-size: 13px; }
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
