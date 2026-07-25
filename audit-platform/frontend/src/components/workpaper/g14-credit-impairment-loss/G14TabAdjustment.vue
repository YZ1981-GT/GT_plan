<template>
  <div class="g14-adjustment">
    <details class="compile-hint">
      <summary>📋 编制提示（对齐 Excel 调整分录汇总 G14-3）</summary>
      <div class="hint-content">
        <p>1. 本表对齐 Excel「信用减值损失调整分录汇总表 G14-3」：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / 借贷 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报，不回写 G14-2；「其他」按账项调整处理。</p>
        <p>3. 系统仅汇总科目 <b>6702 信用减值损失</b> 的借−贷净额：按「回写行」分项写入 G14-2；对方科目（坏账准备等）用于借贷平衡。</p>
        <p>4. 摘要应说明调整事由（ECL 补提/转回、跨期、分类更正等），并交叉索引至 G14-2 / D1·D2·D5·G4·G5 源底稿。</p>
        <p>5. 可经「截止性测试」结果一键回填；亦可「从调整分录模块同步 / 确认调整」与集中台账双向联动（含 6702 及相关对方科目）。</p>
        <p>6. 「推送 A13」将账项调整行送入未更正错报汇总（报表调整默认不推）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：复核信用减值损失（6702）相关账项/报表调整依据充分、借贷平衡，并按明细行分项同步回 G14-2（CAS 22 ECL 口径）"
    />

    <div class="adj-toolbar">
      <el-button
        size="small"
        :loading="adj.syncing.value"
        :disabled="isReadonly || !projectId"
        @click="onSyncFromModule"
      >
        从调整分录模块同步
      </el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow">+ 新增调整分录</el-button>
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
        :disabled="isReadonly || adj.rows.value.length === 0"
        @click="adj.pushToA13()"
      >
        推送 A13
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
      <el-tag size="small" type="info" effect="plain" data-testid="g14-adjustment-count">
        共 {{ adj.rows.value.length }} 行
      </el-tag>
      <el-tag v-if="adj.summary.value.netAje6702 !== 0" type="success" size="small" effect="plain">
        6702 账项净额 {{ fmtAmount(adj.summary.value.netAje6702) }}
      </el-tag>
      <el-tag v-if="adj.summary.value.netRje6702 !== 0" type="warning" size="small" effect="plain">
        报表调整净额 {{ fmtAmount(adj.summary.value.netRje6702) }}（不回写）
      </el-tag>
      <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>
      <GtIndexChip value="wp:G14-3" :validate="false" />
      <GtIndexChip value="wp:G14-2" :validate="false" />
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="g14"
        sheet="G14-3"
        :disabled="isReadonly"
        @imported="emit('imported')"
      />
      <GtReviewTrigger section-id="G14-3-adjustment" />
    </div>

    <div class="balance-row">
      <span>借方合计：{{ fmtAmount(adj.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmtAmount(adj.creditTotal.value) }}</span>
      <span :class="adj.isBalanced.value ? 'balanced' : 'unbalanced'">
        {{ adj.isBalanced.value ? '✓ 借贷平衡' : `✗ 差额：${fmtAmount(Math.abs(adj.balanceDiff.value))}` }}
      </span>
    </div>

    <el-alert
      v-if="writebackHint"
      type="success"
      :closable="false"
      class="writeback-hint"
      :title="writebackHint"
    />

    <el-table
      :data="adj.rows.value"
      size="small"
      border
      stripe
      style="font-size:13px"
      max-height="520"
      :row-class-name="adj.tableRowClassName"
      data-testid="g14-adjustment-table"
      empty-text="暂无调整分录。点击「新增」录入；6702 净额将按回写行写入 G14-2。"
    >
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G14-aje" :row-key="row.rowId" />
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
      <el-table-column label="报表项目" width="120">
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
      <el-table-column label="科目" width="160">
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
            @change="(v: string) => adj.updateRow(row.rowId, { adjudicationRowKey: v })"
          >
            <el-option
              v-for="opt in adj.writebackOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ writebackLabel(row.adjudicationRowKey) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
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
          <GtIndexChip
            v-else-if="row.indexRef"
            :value="row.indexRef.startsWith('wp:') ? row.indexRef : `wp:${row.indexRef}`"
            :validate="false"
          />
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
      <el-table-column v-if="!isReadonly" label="操作" width="56">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="adj.removeRow(row.rowId)">
            <template #reference>
              <el-button size="small" type="danger" link>删</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <p class="footer-note">
      【注：本底稿适用于调整分录较多、较复杂的项目，且仅列示与信用减值损失相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。】
    </p>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述调整分录的事由、依据、明细分项影响，以及拟调整/未调整事项。"
        @update:model-value="saveAuditNote"
      />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应予调整外，其余未见异常。C、由于存在重大未调整事项，不可确认。"
        @update:model-value="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useG14Adjustment } from '../composables/useG14Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useG14Detail } from '../composables/useG14Detail'
import { G14_LINE_ITEMS } from '../composables/g14Constants'
import type { G14AdjustmentWritebackMap } from '../composables/g14AdjStorage'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../composables/gCycleCutoffFill'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtReviewDot from '../GtReviewDot.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  auditYear?: number | string | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const NOTE_KEY = 'G14-3-adjustment-audit-note'
const CONCLUSION_KEY = 'G14-3-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const lastWriteback = ref<G14AdjustmentWritebackMap | null>(null)
const projectIdRef = computed(() => props.projectId ?? '')
const auditYearRef = computed(() => props.auditYear)

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

const detailHelper = useG14Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

function applyByRow(byRow: G14AdjustmentWritebackMap): void {
  let touched = 0
  for (const [rowKey, net] of Object.entries(byRow)) {
    if (!G14_LINE_ITEMS.some((d) => d.rowKey === rowKey)) continue
    detailHelper.updateCell(rowKey, 'currentAdjustment', net)
    if (Math.abs(net) >= 0.005) touched += 1
  }
  lastWriteback.value = { ...byRow }
  if (touched === 0) {
    ElMessage.info('6702 账项净额为 0，明细调整数已按分项覆盖/清零')
  } else {
    ElMessage.success(`已按明细行回写 ${touched} 行调整数`)
  }
}

const adj = useG14Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  projectId: projectIdRef,
  auditYear: auditYearRef,
  applyAdjustmentToDetail: applyByRow,
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: projectIdRef,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G14',
  itemId: 'G14-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.description)?.description || 'G14 信用减值损失调整',
    adjustmentType: adj.rows.value.length > 0 && adj.rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

async function onSyncFromModule(): Promise<void> {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else if (adj.lastSyncMsg.value) ElMessage.info(adj.lastSyncMsg.value)
}

function onConfirm(): void {
  if (!adj.isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法确认')
    return
  }
  adj.publishAdjustment()
  ElMessage.success('已确认：回写 G14-2 明细，并尝试推送至调整分录模块')
}

const writebackHint = computed(() => {
  const map = lastWriteback.value
  if (!map) return ''
  const parts = Object.entries(map)
    .filter(([, v]) => Math.abs(v) > 0.005)
    .map(([k, v]) => `${writebackLabel(k)} ${fmtAmount(v)}`)
  if (!parts.length) return '已同步：6702 账项净额为 0，明细调整数已按分项清零/覆盖。'
  return `最近回写：${parts.join('；')}`
})

function writebackLabel(rowKey: string): string {
  return G14_LINE_ITEMS.find((d) => d.rowKey === rowKey)?.label ?? rowKey
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g14, onCutoffFilled as EventListener)
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g14, onCutoffFilled as EventListener)
})

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g14-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 12px; }
.audit-note-card { margin-top: 12px; }
.compile-hint {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 12px;
  color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
.hint-content p { margin: 4px 0; }
.adj-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.balance-row {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}
.writeback-hint { margin-bottom: 12px; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
.sync-msg { font-size: 12px; color: #909399; }
.footer-note { margin: 10px 0; font-size: 12px; color: #909399; }
:deep(.rje-row) { background: #fdf6ec !important; }
:deep(.g14-acct-row) { background: #f0f9eb !important; }
</style>
