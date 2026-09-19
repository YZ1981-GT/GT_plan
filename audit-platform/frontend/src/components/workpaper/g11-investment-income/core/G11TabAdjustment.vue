<template>
  <div class="g11-adjustment" data-testid="g11-adjustment">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「投资收益调整分录汇总表 G11-3」：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / 借贷 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报，不回写 G11-1/G11-2；「其他」按账项调整处理。</p>
        <p>3. 系统仅汇总科目 <b>6111 投资收益</b> 的贷−借净额，按「回写行」分项写入 G11-1 审定表与 G11-2 明细表对应项目。</p>
        <p>4. 摘要应说明调整事由（权益法补提、跨期收益、处置损益更正等），并交叉索引至 G11-2 / G11-5 / 相关资产底稿。</p>
        <p class="cas-basis">CAS 依据：调整分录应有充分、适当的审计证据支持（《中国注册会计师审计准则第 1301 号——审计证据》）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：确认投资收益相关账项/报表调整依据充分、借贷平衡，并按分项准确回写 G11-1 / G11-2。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          :loading="adj.syncing.value"
          :disabled="isReadonly || !projectId"
          @click="onSyncFromModule"
        >
          从调整分录模块同步
        </el-button>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !adj.isBalanced.value || adj.rows.value.length === 0"
          @click="onConfirm"
        >
          确认调整
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !adj.isBalanced.value || adj.rows.value.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
        <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G11-2" /></span>
      </div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G11-3 调整分录汇总</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-3" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G11-3-adjustment" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>

    <div class="balance-indicator">
      <span>借方合计：<strong>{{ fmt(adj.debitTotal.value) }}</strong></span>
      <span>贷方合计：<strong>{{ fmt(adj.creditTotal.value) }}</strong></span>
      <el-tag v-if="adj.isBalanced.value" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差异 {{ fmt(adj.balanceDiff.value) }}</el-tag>
      <el-tag v-if="adj.summary.value.netAje6111 !== 0" type="info" size="small">
        6111 账项净额 {{ fmt(adj.summary.value.netAje6111) }}
      </el-tag>
      <el-tag v-if="adj.summary.value.netRje6111 !== 0" type="warning" size="small">
        报表调整净额 {{ fmt(adj.summary.value.netRje6111) }}（不回写）
      </el-tag>
    </div>

    <el-alert
      v-if="writebackHint"
      type="success"
      :closable="false"
      class="balance-alert"
      :title="writebackHint"
    />

    <el-table
      :data="adj.rows.value"
      border
      size="small"
      style="font-size:13px"
      max-height="520"
      :row-class-name="adj.tableRowClassName"
      empty-text="暂无调整分录。点击「新增」录入；6111 净额将按回写行分项写入 G11-1/G11-2。"
    >
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @update:model-value="(v: string) => adj.updateCell(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => adj.updateCell(row.rowId, 'category', v)"
          >
            <el-option v-for="opt in adj.categoryOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            @update:model-value="(v: string) => adj.updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="150">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            @change="(v: string) => adj.updateRow(row.rowId, { accountCode: v })"
          >
            <el-option
              v-for="opt in adj.accountOptions"
              :key="opt.code"
              :label="`${opt.code} ${opt.name}`"
              :value="opt.code"
            />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @update:model-value="(v: string) => adj.updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回写行" width="150">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.adjudicationRowKey"
            size="small"
            filterable
            @change="(v: string) => adj.updateRow(row.rowId, { adjudicationRowKey: v })"
          >
            <el-option
              v-for="opt in adj.writebackOptions"
              :key="opt.rowKey"
              :label="opt.label"
              :value="opt.rowKey"
            />
          </el-select>
          <span v-else>{{ writebackLabel(row.adjudicationRowKey) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @update:model-value="(v: string) => adj.updateCell(row.rowId, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef.startsWith('wp:') ? row.indexRef : `wp:${row.indexRef}`" />
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @update:model-value="(v: string) => adj.updateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <p class="footer-note">
      【注：本底稿适用于调整分录较多、较复杂的项目，且仅列示与投资收益相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。】
    </p>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述调整分录的事由、依据及对投资收益分项的影响，未调整事项及其原因。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：调整分录借贷平衡、依据充分，分项回写审定表/明细表准确，未见异常（或列明重大未调整事项）。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useG11Adjustment } from '../../composables/useG11Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useG11DetailAnalysis } from '../../composables/useG11DetailAnalysis'
import { G11_ADJUDICATION_WRITEBACK_OPTIONS } from '../../composables/g11AccountMatch'
import { dispatchG11OfferDisclosurePull } from '../../composables/g11DisclosureSync'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  auditYear?: number | string | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const projectId = computed(() => props.projectId ?? '')
const auditYearRef = computed(() => props.auditYear ?? null)

const NOTE_KEY = 'G11-adjustment-audit-note'
const CONCLUSION_KEY = 'G11-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
})

const detail = useG11DetailAnalysis({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const adj = useG11Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId,
  auditYear: auditYearRef,
  applyAdjustmentToDetail: (byRow) => detail.applyAdjustmentByRow(byRow),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G11',
  itemId: 'G11-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.description)?.description || 'G11 投资收益调整',
    adjustmentType: adj.rows.value.length > 0 && adj.rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

async function onSyncFromModule() {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(adj.lastSyncMsg.value || `已同步 ${n} 行`)
  else if (adj.lastSyncMsg.value) ElMessage.info(adj.lastSyncMsg.value)
}

function onConfirm() {
  adj.publishAdjustment()
  ElMessage.success('已确认调整并回写 G11-1/G11-2')
  dispatchG11OfferDisclosurePull('G11-3')
}

const writebackHint = computed(() => {
  const map = adj.writebackPreview.value
  const parts = Object.entries(map)
    .filter(([, v]) => Math.abs(v) > 0.005)
    .map(([k, v]) => {
      const label = G11_ADJUDICATION_WRITEBACK_OPTIONS.find((o) => o.rowKey === k)?.label ?? k
      return `${label} ${fmt(v)}`
    })
  if (!parts.length) return ''
  return `已分项回写 G11-1/G11-2：${parts.join('；')}`
})

function writebackLabel(key: string): string {
  return G11_ADJUDICATION_WRITEBACK_OPTIONS.find((o) => o.rowKey === key)?.label ?? key
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g11-adjustment { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.cas-basis { color: #909399; font-size: 12px; }
.objective-alert { margin-bottom: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.balance-indicator { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 8px; font-size: 13px; }
.balance-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.sync-msg { font-size: 12px; color: #606266; }
.chip-wrap { display: inline-flex; align-items: center; }
.footer-note { margin: 10px 0; color: #909399; font-size: 12px; }
:deep(.rje-row) { background: #fdf6ec; }
:deep(.g11-acct-row) { background: #f0f9eb; }
</style>
