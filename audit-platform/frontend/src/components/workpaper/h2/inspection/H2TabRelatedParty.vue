<template>
  <div class="h2-tab-related-party">
    <!-- 关联交易检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>关联方在建工程交易（H2-17）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-17')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" class="rp-table"
        :row-class-name="rpRowClass">
        <el-table-column prop="relatedPartyName" label="关联方名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.relatedPartyName" size="small"
              @change="onCellChange(row.rowId, 'relatedPartyName', $event)" />
            <span v-else>{{ row.relatedPartyName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.relationship" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'relationship', $event)">
              <el-option label="母公司" value="母公司" />
              <el-option label="子公司" value="子公司" />
              <el-option label="联营企业" value="联营企业" />
              <el-option label="合营企业" value="合营企业" />
              <el-option label="关键管理人" value="关键管理人" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transType" label="交易类型" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.transType" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'transType', $event)">
              <el-option label="工程建设" value="工程建设" />
              <el-option label="材料采购" value="材料采购" />
              <el-option label="设备采购" value="设备采购" />
              <el-option label="劳务" value="劳务" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.transType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="projectName" label="工程项目" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.projectName" size="small"
              @change="onCellChange(row.rowId, 'projectName', $event)" />
            <span v-else>{{ row.projectName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractAmount" label="合同金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.contractAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'contractAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.contractAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transAmount" label="交易金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.transAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'transAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketPrice" label="市场价格" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.marketPrice"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'marketPrice', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.marketPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价格差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=交易-市场">{{ fmtAmt(row.priceDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.priceDiffRate ?? 0) > 10 }]"
              :title="`=(交易-市场)/市场×100`">
              {{ row.priceDiffRate != null ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingBasis" label="定价依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.pricingBasis" size="small"
              @change="onCellChange(row.rowId, 'pricingBasis', $event)" />
            <span v-else>{{ row.pricingBasis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalStatus" label="审批状态" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.approvalStatus" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'approvalStatus', $event)">
              <el-option label="已审批" value="已审批" />
              <el-option label="未审批" value="未审批" />
            </el-select>
            <el-tag v-else :type="row.approvalStatus === '已审批' ? 'success' : 'danger'" size="small">
              {{ row.approvalStatus || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.conclusion" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'conclusion', $event)">
              <el-option label="公允" value="公允" />
              <el-option label="存疑" value="存疑" />
              <el-option label="不公允" value="不公允" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isTotal" size="small" type="danger" link
              @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增关联交易</el-button>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>价格差异率>10%红色高亮（需重点解释公允性）</li>
        <li>定价依据：参考市场报价/评估报告/招投标文件等</li>
        <li>合计行自动SUM交易金额列</li>
        <li>未审批的关联交易需特别关注</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabRelatedParty.vue — H2-17 关联交易
 * el-table 15列 + 价格差异率>10%红色 + 合计行
 * Spec: Task 4.12 | Requirements: 13.1-13.6
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2RelatedParty } from '../../composables/useH2RelatedParty'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2RelatedParty({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const displayRows = computed(() => [...state.detailRows.value, state.totalRow.value])

function rpRowClass({ row }: any) {
  if (row.isTotal) return 'total-row'
  if (Math.abs(row.priceDiffRate ?? 0) > 10) return 'price-alert-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handleAiGenerate() {
  console.log('AI generate H2-17')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-related-party { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.rp-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
:deep(.price-alert-row) { background-color: #fef0f0 !important; }
</style>
