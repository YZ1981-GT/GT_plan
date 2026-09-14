<template>
  <div class="g9-adj" data-testid="g9-adjustment">
    <div class="toolbar">
      <div class="title-block">
        <h3>G9-3 调整分录汇总</h3>
        <p class="sheet-sub">登记 1504 相关 AJE/RJE → 借贷平衡校验 → 分项回写 G9-1</p>
      </div>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G9-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-4" /></span>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-3" @imported="onImported" />
        <GtReviewTrigger section-id="G9-3-adjustment" />
      </div>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「调整分录汇总 G9-3」：仅列示与其他非流动金融资产（1504）相关的审计调整与重分类。</p>
        <p>2. AJE=账项调整（影响审定余额）；RJE=重分类（影响列报）。二者分别回写 G9-1 期末 AJE/RJE。</p>
        <p>3. FVTPL 公允变动应成对：上升 Dr 1504 / Cr 6101；下降反向。FVOCI 则用 1504 ↔ 4002。</p>
        <p>4. 整表借贷须平衡；系统仅汇总科目代码以 <b>1504</b> 开头的借−贷净额，回写 G9-1「{{ G9_ADJ_WRITEBACK_ROW_KEY }}」行。</p>
        <p>5. 可从 G9-4「推送差异→G9-3」带入；亦可与中央调整分录模块双向同步（1504/6101/4002 等）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：核实其他非流动金融资产（1504）相关 AJE/RJE 依据充分、借贷平衡、对方科目正确，并与 G9-1 审定表期末 AJE/RJE 勾稽一致。"
    />

    <el-alert v-if="!adj.balanceOk.value" type="error" :closable="false" class="balance-alert" data-testid="g9-adj-balance-error">
      借贷不平衡：借方 {{ fmt(adj.summary.value.totalDebits) }} ≠ 贷方 {{ fmt(adj.summary.value.totalCredits) }}，差额
      {{ fmt(Math.abs(adj.balanceDiff.value)) }}
    </el-alert>
    <el-alert
      v-else-if="adj.writebackPreview.value.closingAje !== 0 || adj.writebackPreview.value.closingRje !== 0"
      type="success"
      :closable="false"
      class="balance-alert"
      data-testid="g9-adj-writeback-hint"
    >
      已回写 G9-1「{{ G9_ADJ_WRITEBACK_ROW_KEY }}」期末
      AJE {{ fmt(adj.writebackPreview.value.closingAje) }}
      / RJE {{ fmt(adj.writebackPreview.value.closingRje) }}
      （1504 净额 {{ fmt(adj.summary.value.net1504) }}；6101 净额 {{ fmt(adj.summary.value.fvPlNet) }}；OCI 净额 {{ fmt(adj.summary.value.ociNet) }}）
    </el-alert>
    <el-alert
      v-else-if="adj.rows.value.length > 0 && adj.balanceOk.value"
      type="info"
      :closable="false"
      class="balance-alert"
    >
      借贷已平衡；1504 净额为 0，G9-1 期末 AJE/RJE 保持 0。
    </el-alert>

    <div class="adj-toolbar">
      <el-button v-if="!isReadonly" size="small" type="primary" data-testid="g9-adj-add" @click="adj.addRow()">
        + 新增分录
      </el-button>
      <el-button v-if="!isReadonly" size="small" plain data-testid="g9-adj-add-fvtpl" @click="adj.addFvPlPair()">
        + 公允变动组(FVTPL)
      </el-button>
      <el-button v-if="!isReadonly" size="small" plain data-testid="g9-adj-add-fvoci" @click="adj.addFvOciPair()">
        + 公允变动组(FVOCI)
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        :loading="adj.syncing.value"
        :disabled="!projectId"
        data-testid="g9-adj-sync-module"
        @click="onSyncFromModule"
      >
        从调整分录模块同步
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :disabled="!adj.balanceOk.value || !projectId"
        data-testid="g9-adj-push-module"
        @click="onPushToModule"
      >
        推送至调整分录模块
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="centralSyncing"
        :disabled="!adj.balanceOk.value || adj.rows.value.length === 0"
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
      <span class="row-count">共 {{ adj.summary.value.rowCount }} 行（AJE {{ adj.summary.value.ajeCount }} / RJE {{ adj.summary.value.rjeCount }}）</span>
      <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>
    </div>

    <el-table
      :data="adj.rows.value"
      border
      size="small"
      style="font-size:13px"
      max-height="480"
      empty-text="暂无调整分录。可「新增分录」、录入公允变动分录组，或从 G9-4 推送公允差异。"
      :row-class-name="adjRowClassName"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" />
      <el-table-column label="类型" width="78">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.entryType"
            size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { entryType: v as 'AJE' | 'RJE' })"
          >
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="128">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            type="date"
            :model-value="row.date"
            size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })"
          />
          <span v-else>{{ row.date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <div class="summary-cell">
            <el-tag v-if="isFromG94(row)" size="small" type="warning" class="src-tag">G9-4</el-tag>
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              placeholder="调整事由"
              @update:model-value="(v: string) => adj.updateRow(row.rowId, { summary: v })"
            />
            <span v-else>{{ row.summary }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="168">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            allow-create
            default-first-option
            @update:model-value="(v: string) => onAccountChange(row.rowId, v)"
          >
            <el-option
              v-for="opt in G9_ADJ_ACCOUNT_OPTIONS"
              :key="opt.code"
              :value="opt.code"
              :label="`${opt.code} ${opt.name}`"
            />
          </el-select>
          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { accountName: v })"
          />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="108" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateRow(row.rowId, { debitAmount: v ?? 0 })"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="108" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateRow(row.rowId, { creditAmount: v ?? 0 })"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="88">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.preparedBy"
            size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })"
          />
          <span v-else>{{ row.preparedBy || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { remark: v })"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="adj-footer" :class="{ 'balance-fail': !adj.balanceOk.value }" data-testid="g9-adj-footer">
      <span class="footer-label">合计</span>
      <span>借方 {{ fmt(adj.summary.value.totalDebits) }}</span>
      <span>贷方 {{ fmt(adj.summary.value.totalCredits) }}</span>
      <span v-if="adj.balanceOk.value" class="ok">✓ 平衡</span>
      <span v-else class="err">✗ 差额 {{ fmt(Math.abs(adj.balanceDiff.value)) }}</span>
      <span class="sep">|</span>
      <span>1504 净额 {{ fmt(adj.summary.value.net1504) }}</span>
      <span>6101 净额 {{ fmt(adj.summary.value.fvPlNet) }}</span>
      <span>OCI 净额 {{ fmt(adj.summary.value.ociNet) }}</span>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="adjustment-note"
      conclusion-ai-section="adjustment-conclusion"
      note-placeholder="填写审计说明：调整依据、AJE/RJE 判断、对 1504 与公允变动/OCI 的影响、与 G9-4 推送及 G9-1 回写勾稽情况。"
      note-hint="覆盖调整依据、借贷平衡、对方科目及回写审定表情况。"
      conclusion-placeholder="填写审计结论：A、调整分录借贷平衡且依据充分，已正确回写 G9-1。B、除上述调整事项外未见异常。C、存在重大未调整事项或范围受限，不可确认。"
      :related-context="{
        分录数: adj.summary.value.rowCount,
        AJE行数: adj.summary.value.ajeCount,
        RJE行数: adj.summary.value.rjeCount,
        借方合计: adj.summary.value.totalDebits,
        贷方合计: adj.summary.value.totalCredits,
        借贷平衡: adj.balanceOk.value,
        差额: adj.balanceDiff.value,
        回写1504净额: adj.summary.value.net1504,
        公允变动净额: adj.summary.value.fvPlNet,
        OCI净额: adj.summary.value.ociNet,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import { G9_ADJ_WRITEBACK_ROW_KEY } from '../../composables/g9Constants'
import { G9_ADJ_ACCOUNT_OPTIONS, useG9Adjustment } from '../../composables/useG9Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  auditYear?: number | null
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const adj = useG9Adjustment({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId || ''),
  auditYear: computed(() => props.auditYear),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId || '',
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G9',
  itemId: 'G9-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.summary)?.summary || 'G9 其他非流动金融资产调整',
    adjustmentType: adj.rows.value.length > 0 && adj.rows.value.every((r) => r.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

function onImported() { emit('imported') }

function onAccountChange(rowId: string, code: string) {
  adj.updateRow(rowId, { accountCode: code })
}

function isFromG94(row: { summary?: string; remark?: string }): boolean {
  const t = `${row.summary || ''} ${row.remark || ''}`
  return /G9-4|公允测试差异/.test(t)
}

function adjRowClassName({ row }: { row: { remark?: string; summary?: string; sourceGroupId?: string } }) {
  if (isFromG94(row)) return 'row-from-fv'
  if (row.sourceGroupId) return 'row-from-module'
  return ''
}

async function onSyncFromModule() {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
}

async function onPushToModule() {
  const { ok, pushed } = await adj.confirmAndPush()
  if (!ok) {
    ElMessage.warning('请先保证借贷平衡后再推送')
    return
  }
  if (pushed > 0) ElMessage.success(`已推送 ${pushed} 笔至调整分录模块，并回写 G9-1`)
  else ElMessage.info(adj.lastSyncMsg.value || '无可推送分录（可能已同步）')
}

const NOTE_KEY = 'G9-adjustment-audit-note'
const CONCLUSION_KEY = 'G9-adjustment-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const _adjConcl = props.allResponses.get(CONCLUSION_KEY)
const auditConclusion = ref(String(_adjConcl?.conclusion ?? _adjConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: v, remark: null })
})

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g9-adj { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 10px; }
.balance-alert { margin-bottom: 8px; }
.adj-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.row-count { font-size: 12px; color: #909399; }
.sync-msg { font-size: 12px; color: #e6a23c; }
.summary-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.adj-footer {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px;
}
.adj-footer.balance-fail { background: #fef0f0; }
.footer-label { font-weight: 600; }
.ok { color: #67c23a; }
.err { color: #f56c6c; font-weight: 600; }
.sep { color: #dcdfe6; }
:deep(.row-from-fv) { background: #fdf6ec; }
:deep(.row-from-module) { background: #f0f9eb; }
</style>
