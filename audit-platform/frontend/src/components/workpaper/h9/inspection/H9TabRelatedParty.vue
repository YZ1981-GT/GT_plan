<template>
  <div class="h9-tab-related-party">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：识别关联方租赁合同并评价其定价公允性，关注价差率异常（>10%）是否存在利益输送，确认关联租赁已按 CAS36 在附注中充分披露。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H9-6关联交易检查：从H9-2明细表中筛选标记为关联方的租赁合同，评估关联租赁定价的公允性。价差率=(年租金-市场租金)/市场租金×100%，价差率>10%需重点关注是否存在利益输送。</p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button v-if="!props.isReadonly" size="small" @click="handleRefresh">🔄 从明细表刷新</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-6" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- Section Header -->
    <div class="section-header">
      <span>关联方租赁检查 H9-6</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H9-6-related-party')">💬</el-button>
      </div>
    </div>

    <!-- 关联方统计概要 -->
    <div class="summary-bar" v-if="rows.length > 0">
      <div class="summary-item">
        <span class="summary-label">关联租赁合同数：</span>
        <span class="summary-value">{{ rows.length }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">关联负债合计：</span>
        <span class="summary-value">{{ fmtAmt(totalLiability) }}</span>
      </div>
      <div class="summary-item" v-if="abnormalRows.length > 0">
        <span class="summary-label abnormal-label">异常(价差>10%)：</span>
        <span class="summary-value abnormal-value">{{ abnormalRows.length }}笔</span>
      </div>
    </div>

    <!-- 15列关联方检查表 -->
    <el-table :data="rows" border size="small" class="formula-table"
      :row-class-name="getRowClassName" row-key="rowId">
      <el-table-column prop="contractNo" label="合同号" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.contractNo" size="small"
            @change="updateCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="lessor" label="出租方" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.lessor" size="small"
            @change="updateCell(row.rowId, 'lessor', row.lessor)" />
          <span v-else>{{ row.lessor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" width="110">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.relationship" size="small"
            @change="updateCell(row.rowId, 'relationship', row.relationship)">
            <el-option label="母公司" value="母公司" />
            <el-option label="子公司" value="子公司" />
            <el-option label="联营企业" value="联营企业" />
            <el-option label="合营企业" value="合营企业" />
            <el-option label="关键管理人员" value="关键管理人员" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.relationship }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="70" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source === 'H9-2' ? '' : 'warning'">
            {{ row.source }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="leaseTerm" label="租赁期(年)" width="90" align="center">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.leaseTerm" :controls="false"
            size="small" :min="0" :precision="1"
            @change="(v: number | undefined) => updateCell(row.rowId, 'leaseTerm', v)" />
          <span v-else>{{ row.leaseTerm || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="actualRent" label="年租金" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.actualRent" :controls="false"
            size="small"
            @change="(v: number | undefined) => updateCell(row.rowId, 'actualRent', v)" />
          <span v-else>{{ fmtAmt(row.actualRent) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="marketRent" label="市场租金" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.marketRent" :controls="false"
            size="small"
            @change="(v: number | undefined) => updateCell(row.rowId, 'marketRent', v)" />
          <span v-else>{{ fmtAmt(row.marketRent) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="价差率(%)" width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="row.isAbnormal ? 'abnormal' : ''"
            :title="`公式：(${row.actualRent}-${row.marketRent})/${row.marketRent}×100%`">
            {{ row.marketRent > 0 ? row.priceDiffRate.toFixed(2) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="是否偏高" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isAbnormal" type="danger" size="small">偏高</el-tag>
          <el-tag v-else-if="row.marketRent > 0" type="success" size="small">正常</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="liabilityBalance" label="负债余额" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.liabilityBalance"
            size="small"
            @change="(v: number | undefined) => updateCell(row.rowId, 'liabilityBalance', v)" />
          <span v-else>{{ fmtAmt(row.liabilityBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允性评价" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.fairnessAssessment" size="small"
            @change="updateFairness(row.rowId, row.fairnessAssessment)">
            <el-option label="公允" value="公允" />
            <el-option label="基本公允" value="基本公允" />
            <el-option label="存在异常" value="存在异常" />
            <el-option label="待核实" value="待核实" />
          </el-select>
          <span v-else>{{ row.fairnessAssessment || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
            @change="updateCell(row.rowId, 'remark', row.remark)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空数据提示 -->
    <el-empty v-if="rows.length === 0" description="暂无关联方租赁数据，请先在H9-2明细表中标记关联方后点击“从明细表刷新”" />

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" type="primary" @click="handleSave" :loading="saving">保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H9-6-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="请填写关联方租赁检查的审计说明：筛选口径、可比市场租金取数依据、价差率异常处理等..."
        :disabled="props.isReadonly" @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>关联租赁公允性审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H9-6-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="请填写关联租赁公允性审计结论..." :disabled="props.isReadonly"
        @blur="saveConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>关联方租赁数据自动从H9-2（S列=关联方）筛选，也可手动点击"从明细表刷新"更新</li>
        <li>价差率=(年租金-市场租金)/市场租金×100%，当价差率绝对值>10%时标红</li>
        <li>公允性评价：参照同地段同期限可比市场租金水平判断</li>
        <li>关联租赁需在附注中单独披露：关联方名称、关系、租赁标的、金额</li>
        <li>价差率偏高时需关注商业合理性，判断是否存在利益输送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H9TabRelatedParty.vue — H9-6 关联方筛选视图
 *
 * 从H9-2(S列=关联方)过滤出关联租赁，评估公允性。
 * 15列: 合同号|出租方|关联关系|来源|租赁期|年租金|市场租金|价差率|是否偏高|
 *       负债余额|公允性评价|备注
 * 价差率>10%红色高亮
 * 使用calcPriceDiffRate from useH9FormulaEngine
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 4.5
 * Requirements: 5.2-5.4
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH9RelatedParty, type H9RelatedPartyRow } from '../../composables/useH9RelatedParty'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})
const saving = ref(false)

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, abnormalRows, totalLiability,
  updateCell, refreshFromDetails, save,
} = useH9RelatedParty({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

// ─── Audit Note / Conclusion ─────────────────────────────────────────────────
const auditNote = ref('')
const noteData = props.allResponses.get('H9-6-note')
if (noteData) auditNote.value = noteData.remark ?? noteData.conclusion ?? ''

const auditConclusion = ref('')
const conclusionData = props.allResponses.get('H9-6-conclusion')
if (conclusionData) auditConclusion.value = conclusionData.remark ?? conclusionData.conclusion ?? ''

function saveAuditNote() {
  saveResponse('H9-6-note', auditNote.value)
}

function saveConclusion() {
  saveResponse('H9-6-conclusion', auditConclusion.value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleRefresh() {
  refreshFromDetails()
}

function updateFairness(rowId: string, value: string) {
  const row = rows.value.find((r: H9RelatedPartyRow) => r.rowId === rowId)
  if (!row) return
  ;(row as any).fairnessAssessment = value
  save()
}

async function handleSave() {
  saving.value = true
  try {
    save()
  } finally {
    saving.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Row highlight ───────────────────────────────────────────────────────────
function getRowClassName({ row }: { row: H9RelatedPartyRow }) {
  if (row.isAbnormal) return 'abnormal-row'
  return ''
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
.h9-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.summary-bar {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.summary-item { display: flex; align-items: center; gap: 6px; }
.summary-label { color: var(--el-text-color-secondary); font-size: 12px; }
.summary-value { font-weight: 600; font-variant-numeric: tabular-nums; }
.abnormal-label { color: #dc2626; }
.abnormal-value { color: #dc2626; }

.formula-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.formula-table :deep(.formula-col) { background: #fefce8; }
.formula-table :deep(.abnormal-row) { background: #fef2f2 !important; }
.formula-value {
  border-bottom: 1px dashed #d97706;
  cursor: help;
  color: #d97706;
}
.formula-value.abnormal { color: #dc2626; font-weight: 700; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
