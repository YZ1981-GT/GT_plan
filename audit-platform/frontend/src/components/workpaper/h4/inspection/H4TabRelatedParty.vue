<template>
  <div class="h4-tab-related-party">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-9关联交易检查：核查工程物资采购中的关联交易定价公允性。价差率=（交易金额-市场价格）/市场价格×100%，|价差率|>10%时红色高亮标记为异常。需评估关联采购的商业合理性、审批流程和信息披露完整性。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>关联交易检查表 H4-9</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H4-9-related-party')">💬</el-button>
      </div>
    </div>

    <!-- 16列表格 -->
    <el-table :data="rows" border stripe size="small" class="check-table" row-key="rowId"
      :row-class-name="getRowClassName" max-height="520">
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed="left" />
      <el-table-column label="物资名称" min-width="110" fixed="left">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.name" size="small"
            @change="updateCell(row.rowId, 'name', $event)" />
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="交易对手" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.counterparty" size="small"
            @change="updateCell(row.rowId, 'counterparty', $event)" />
          <span v-else>{{ row.counterparty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.relationship" size="small"
            @change="updateCell(row.rowId, 'relationship', $event)" />
          <span v-else>{{ row.relationship }}</span>
        </template>
      </el-table-column>
      <el-table-column label="交易金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.transAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'transAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.transAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="市场价格" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.marketPrice" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'marketPrice', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.marketPrice) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="价差率" width="80" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'rate-abnormal': row.isAbnormal }"
            title="价差率 = (交易金额-市场价格)/市场价格×100%">
            {{ row.marketPrice ? row.priceDiffRate.toFixed(2) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="合同日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.contractDate" size="small" placeholder="YYYY-MM-DD"
            @change="updateCell(row.rowId, 'contractDate', $event)" />
          <span v-else>{{ row.contractDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同编号" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.contractNo" size="small"
            @change="updateCell(row.rowId, 'contractNo', $event)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="定价依据" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.pricingBasis" size="small"
            @change="updateCell(row.rowId, 'pricingBasis', $event)" />
          <span v-else>{{ row.pricingBasis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审批流程" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.approvalProcess" size="small"
            @change="updateCell(row.rowId, 'approvalProcess', $event)" />
          <span v-else>{{ row.approvalProcess }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否公允" width="80" align="center">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.isFair" size="small" style="width: 68px"
            @change="updateCell(row.rowId, 'isFair', $event)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="待定" value="待定" />
          </el-select>
          <span v-else :class="{ 'rate-abnormal': row.isFair === '否' }">{{ row.isFair || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="决策程序" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.decisionProcess" size="small"
            @change="updateCell(row.rowId, 'decisionProcess', $event)" />
          <span v-else>{{ row.decisionProcess }}</span>
        </template>
      </el-table-column>
      <el-table-column label="披露情况" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.disclosureStatus" size="small"
            @change="updateCell(row.rowId, 'disclosureStatus', $event)" />
          <span v-else>{{ row.disclosureStatus }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核查结论" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.conclusion" size="small"
            @change="updateCell(row.rowId, 'conclusion', $event)" />
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
            @change="updateCell(row.rowId, 'remark', $event)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="40" v-if="!props.isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 统计摘要 -->
    <div class="stats-bar">
      <span class="stats-item">关联交易笔数 <strong>{{ stats.transCount }}</strong></span>
      <span class="stats-item">总金额 <strong>{{ fmtAmt(stats.totalAmount) }}</strong></span>
      <span class="stats-item" :class="{ 'stats-warn': stats.abnormalCount > 0 }">
        异常笔数 <strong>{{ stats.abnormalCount }}</strong>
      </span>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加关联交易</el-button>
      <el-dropdown trigger="click" @command="handleImportExport" style="margin-left: 8px">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-9-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写关联交易审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>价差率=(交易金额-市场价格)/市场价格×100%，|价差率|>10%自动红色高亮</li>
        <li>关联关系类型：母子公司/共同控制/重大影响/主要投资者/关键管理人员等</li>
        <li>需评估定价依据（市场比较法/成本加成法/协商定价）的合理性</li>
        <li>审批流程需检查是否经独立董事/审计委员会审批</li>
        <li>核查披露是否符合CAS36关联方披露要求</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabRelatedParty.vue — H4-9 关联交易检查表
 *
 * 16列: 序号|物资名称|交易对手|关联关系|交易金额|市场价格|价差率|合同日期|合同编号|
 *       定价依据|审批流程|是否公允|决策程序|披露情况|核查结论|备注
 *
 * 价差率: auto-calculated via calcPriceDiffRate, RED highlight when |rate| > 10%
 * 底部: 统计摘要 (关联交易笔数/总金额/异常笔数)
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.9
 * Requirements: 8.1-8.5
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4RelatedParty, type H4RelatedPartyRow } from '../../composables/useH4RelatedParty'
import { useH4ImportExport } from '../../composables/useH4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, stats,
  addRow, deleteRow, updateCell, save,
} = useH4RelatedParty({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
})

const importExport = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
// Load audit note from allResponses
const noteResp = props.allResponses.get('H4-9-note')
if (noteResp?.remark) auditNote.value = noteResp.remark

function saveAuditNote() {
  props.allResponses.set('H4-9-note', { item_id: 'H4-9-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: H4RelatedPartyRow }) {
  if (row.isAbnormal) return 'abnormal-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加关联交易', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H4-9')
  else if (command === 'export-data') importExport.exportData('H4-9')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-9', file)
    }
    input.click()
  }
}

function handleAiGenerate() {
  console.log('[H4-9] AI generate')
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.check-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; font-variant-numeric: tabular-nums; }

.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
}
.rate-abnormal { color: #f56c6c; font-weight: 600; border-bottom-color: #f56c6c; }

:deep(.abnormal-row) { background-color: #fef0f0 !important; }

.stats-bar {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}
.stats-item { color: var(--el-text-color-secondary); }
.stats-item strong { color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
.stats-warn strong { color: #f56c6c; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
