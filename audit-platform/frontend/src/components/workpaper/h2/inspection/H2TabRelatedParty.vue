<template>
  <div class="h2-tab-related-party">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核查在建工程涉及的关联方交易（施工/供材/设计/监理）的公允性与披露完整性，评估定价合理性（价格差异率）及审批程序合规性。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-17" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 关联交易检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>关联方在建工程交易（H2-17）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-17')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" class="rp-table"
        :row-class-name="rpRowClass">
        <el-table-column prop="partyName" label="关联方名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.partyName" size="small"
              @change="onCellChange(row.rowId, 'partyName', $event)" />
            <span v-else>{{ row.partyName || (row.isTotal ? '合计' : '-') }}</span>
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
        <el-table-column prop="transactionType" label="交易类型" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.transactionType" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'transactionType', $event)">
              <el-option label="施工" value="施工" />
              <el-option label="供材" value="供材" />
              <el-option label="设计" value="设计" />
              <el-option label="监理" value="监理" />
            </el-select>
            <span v-else>{{ row.transactionType || '-' }}</span>
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
        <el-table-column prop="currentAmount" label="本期发生额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.currentAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'currentAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cumulativeAmount" label="累计发生额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.cumulativeAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'cumulativeAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cumulativeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketPrice" label="市场价参考" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.marketPrice"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'marketPrice', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.marketPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价格差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=合同金额-市场价参考">{{ fmtAmt(row.priceDifference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.differenceRate ?? 0) > 10 }]"
              :title="`=(合同-市场)/市场×100`">
              {{ row.differenceRate != null ? row.differenceRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingMethod" label="定价方式" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.pricingMethod" size="small"
              @change="onCellChange(row.rowId, 'pricingMethod', $event)" />
            <span v-else>{{ row.pricingMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批文件" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.approvalDoc" size="small"
              @change="onCellChange(row.rowId, 'approvalDoc', $event)" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="independentDirectorOpinion" label="独立董事意见" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.independentDirectorOpinion" size="small"
              @change="onCellChange(row.rowId, 'independentDirectorOpinion', $event)" />
            <span v-else>{{ row.independentDirectorOpinion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.auditConclusion" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'auditConclusion', $event)">
              <el-option label="公允" value="公允" />
              <el-option label="存疑" value="存疑" />
              <el-option label="不公允" value="不公允" />
            </el-select>
            <span v-else>{{ row.auditConclusion || '-' }}</span>
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述关联方识别、交易类型、定价依据与市场价比较、审批与独立董事意见的核查情况。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：如关联交易定价公允、审批程序完备、披露充分，未见异常；或说明价格差异重大事项及其影响。" :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
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
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2RelatedParty({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const displayRows = computed(() => [
  ...state.rows.value,
  { ...state.totalRow.value, isTotal: true, rowId: 'row-total', partyName: '合计' },
])

function rpRowClass({ row }: any) {
  if (row.isTotal) return 'total-row'
  if (Math.abs(row.differenceRate ?? 0) > 10) return 'price-alert-row'
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


function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.rp-table { font-size: var(--wp-font-size, 13px); }
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
