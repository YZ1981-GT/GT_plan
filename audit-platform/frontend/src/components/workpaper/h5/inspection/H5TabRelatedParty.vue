<template>
  <div class="h5-tab-related-party">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-17 关联交易检查（异常{{ state.abnormalCount.value }}项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-17')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>交易总额: {{ fmtAmt(state.totalTransAmount.value) }}</span>
        <el-tag v-if="state.abnormalCount.value > 0" type="danger" size="small">{{ state.abnormalCount.value }}项价差率>10%</el-tag>
      </div>

      <el-table :data="state.rows.value" border stripe size="small" class="rp-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="relatedParty" label="关联方" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.relatedParty" size="small" @change="state.updateCell(row.rowId, 'relatedParty', $event)" />
            <span v-else>{{ row.relatedParty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.relationship" size="small" @change="state.updateCell(row.rowId, 'relationship', $event)" />
            <span v-else>{{ row.relationship }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transType" label="交易类型" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.transType" size="small" @change="state.updateCell(row.rowId, 'transType', $event)">
              <el-option label="购买" value="购买" /><el-option label="出售" value="出售" />
              <el-option label="租赁" value="租赁" /><el-option label="服务" value="服务" />
            </el-select>
            <span v-else>{{ row.transType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transAmount" label="交易金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" @change="state.updateCell(row.rowId, 'transAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transPrice" label="交易价格" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transPrice" :controls="false" size="small" @change="state.updateCell(row.rowId, 'transPrice', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketPrice" label="市场价格" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.marketPrice" :controls="false" size="small" @change="state.updateCell(row.rowId, 'marketPrice', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.marketPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价差率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'abnormal-rate': row.isAbnormal }" title="=(交易价-市场价)/市场价×100">
              {{ row.priceDiffRate.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingBasis" label="定价依据" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingBasis" size="small" @change="state.updateCell(row.rowId, 'pricingBasis', $event)" />
            <span v-else>{{ row.pricingBasis }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly"><el-button size="small" @click="handleAddRow">+ 新增关联交易</el-button></div>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" /></el-card>
    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>价差率=(交易价格-市场价格)/市场价格×100%</li><li>价差率>10%自动高亮为异常项</li><li>关联交易需评价定价公允性</li></ul></details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5RelatedParty } from '../../composables/useH5RelatedParty'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5RelatedParty({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入关联方名称', '新增关联交易', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addRow(value)
}
function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-related-party { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; } .section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; } .summary-row { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.rp-table { font-size: 13px; } .amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.abnormal-rate { color: var(--el-color-danger); font-weight: 600; background: var(--el-color-danger-light-9); }
.action-bar { margin: 12px 0; } .note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; } .compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
