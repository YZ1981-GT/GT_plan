<template>
  <div class="g8-adj" data-testid="g8-adjustment">
    <div class="toolbar">
      <div class="title-block">
        <h3>G8-3 调整分录汇总</h3>
        <p class="sheet-sub">登记 1503 相关 AJE/RJE → 借贷平衡校验 → 1503 净额回写 G8-1</p>
      </div>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" /></span>
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-3" @imported="onImported" />
        <GtReviewTrigger section-id="G8-3-adjustment" />
      </div>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「调整分录汇总 G8-3」：仅列示与其他权益工具投资（1503）相关的审计调整与重分类。</p>
        <p>2. AJE=账项调整（影响审定余额）；RJE=重分类（影响列报，通常不改变 1503 净额回写口径，但仍须借贷平衡）。</p>
        <p>3. FVOCI 公允变动应成对入账：上升 Dr 1503 / Cr 4002 OCI；下降反向。处置时累计 OCI 可转入留存收益（不经损益）。</p>
        <p>4. 整表借贷须平衡；系统仅汇总科目代码以 <b>1503</b> 开头的借−贷净额，自动回写 G8-1「公允价值」行期末账项调整。</p>
        <p>5. 可从 G8-4「推送差异→G8-3」带入公允差异分录组（同指纹重复推送会覆盖旧组）；亦可「从调整分录模块同步 / 推送至调整分录模块」与集中台账双向联动（1503/4002）。</p>
        <p class="cas-basis">CAS 依据：调整须有充分适当审计证据（《中国注册会计师审计准则第 1301 号》）；计量与列报遵循 CAS 22 / 企业会计准则第 22 号。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实其他权益工具投资（1503）相关 AJE/RJE 依据充分、借贷平衡、OCI 对方科目正确，并与 G8-1 审定表期末账项调整勾稽一致。"
      class="objective-alert"
    />

    <el-alert v-if="!adj.balanceOk.value" type="error" :closable="false" class="balance-alert" data-testid="g8-adj-balance-error">
      借贷不平衡：借方 {{ fmt(adj.summary.value.totalDebits) }} ≠ 贷方 {{ fmt(adj.summary.value.totalCredits) }}，差额
      {{ fmt(Math.abs(adj.balanceDiff.value)) }}
    </el-alert>
    <el-alert
      v-else-if="adj.writebackPreview.value.closingAdjustment !== 0"
      type="success"
      :closable="false"
      class="balance-alert"
      data-testid="g8-adj-writeback-hint"
    >
      已回写 G8-1「{{ G8_ADJ_WRITEBACK_ROW_KEY }}」期末账项调整
      {{ fmt(adj.writebackPreview.value.closingAdjustment) }}
      （AJE 净额 {{ fmt(adj.summary.value.ajeNet1503) }} / RJE 净额 {{ fmt(adj.summary.value.rjeNet1503) }}；OCI 净额 {{ fmt(adj.summary.value.ociNet) }}）
    </el-alert>
    <el-alert
      v-else-if="adj.rows.value.length > 0 && adj.balanceOk.value"
      type="info"
      :closable="false"
      class="balance-alert"
    >
      借贷已平衡；1503 净额为 0，G8-1 期末账项调整保持 0。
    </el-alert>

    <div class="adj-toolbar">
      <el-button v-if="!isReadonly" size="small" type="primary" data-testid="g8-adj-add" @click="adj.addRow()">
        + 新增分录
      </el-button>
      <el-button v-if="!isReadonly" size="small" plain data-testid="g8-adj-add-pair" @click="adj.addFvOciPair()">
        + 公允变动分录组
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        :loading="adj.syncing.value"
        :disabled="!projectId"
        data-testid="g8-adj-sync-module"
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
        data-testid="g8-adj-push-module"
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
      empty-text="暂无调整分录。可「新增分录」、录入「公允变动分录组」，或从 G8-4 推送公允差异。"
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
            <el-tag v-if="isFromG84(row)" size="small" type="warning" class="src-tag">G8-4</el-tag>
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
              v-for="opt in G8_ADJ_ACCOUNT_OPTIONS"
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
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateRow(row.rowId, { debitAmount: v ?? 0 })"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="108" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
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

    <div class="adj-footer" :class="{ 'balance-fail': !adj.balanceOk.value }" data-testid="g8-adj-footer">
      <span class="footer-label">合计</span>
      <span>借方 {{ fmt(adj.summary.value.totalDebits) }}</span>
      <span>贷方 {{ fmt(adj.summary.value.totalCredits) }}</span>
      <span v-if="adj.balanceOk.value" class="ok">✓ 平衡</span>
      <span v-else class="err">✗ 差额 {{ fmt(Math.abs(adj.balanceDiff.value)) }}</span>
      <span class="sep">|</span>
      <span>1503 净额 {{ fmt(adj.summary.value.net1503) }}</span>
      <span>OCI 净额 {{ fmt(adj.summary.value.ociNet) }}</span>
    </div>

    <p class="sheet-note">
      【注：本底稿适用于调整分录较多或需留痕公允差异调整的项目；仅列示与 1503 相关的审计调整。项目组可按实际情况选用。】
    </p>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      v-model:conclusion-option="conclusionOption"
      note-ai-section="adjustment-note"
      conclusion-ai-section="adjustment-conclusion"
      note-placeholder="填写审计说明：调整依据、AJE/RJE 判断、对 1503 与 OCI/留存收益的影响、与 G8-4 推送及 G8-1 回写勾稽情况。"
      note-hint="覆盖调整依据、借贷平衡、OCI 对方科目及回写审定表情况。"
      conclusion-placeholder="填写审计结论：A、调整分录借贷平衡且依据充分，已正确回写 G8-1。B、除上述调整事项外未见异常。C、存在重大未调整事项或范围受限，不可确认。"
      conclusion-hint="可先选 A/B/C 口径，再按需补充说明。"
      :related-context="{
        分录数: adj.summary.value.rowCount,
        AJE行数: adj.summary.value.ajeCount,
        RJE行数: adj.summary.value.rjeCount,
        借方合计: adj.summary.value.totalDebits,
        贷方合计: adj.summary.value.totalCredits,
        借贷平衡: adj.balanceOk.value,
        差额: adj.balanceDiff.value,
        回写1503净额: adj.summary.value.net1503,
        OCI净额: adj.summary.value.ociNet,
      }"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G8TabAdjustment.vue — G8-3 调整分录汇总
 * 对齐 Excel 10 列：序号|类型|日期|摘要|科目代码|科目名称|借方|贷方|编制人|备注
 * 联动：G8-4 推送差异高亮；1503 净额回写 G8-1；截止测试填入
 */
import { computed, ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { ElMessage } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import { G8_ADJ_WRITEBACK_ROW_KEY } from '../../composables/g8Constants'
import { useG8Adjustment, G8_ADJ_ACCOUNT_OPTIONS } from '../../composables/useG8Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { G8_NAV_HIGHLIGHT_ADJ_EVENT } from '../../composables/g8CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const runtime = inject(WorkpaperRuntimeContextKey, null)
const auditYear = computed(() => {
  const raw = runtime?.year?.value ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1900 ? Math.trunc(n) : null
})

const adj = useG8Adjustment({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId || ''),
  auditYear,
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId || '',
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G8',
  itemId: 'G8-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.summary)?.summary || 'G8 其他权益工具投资调整',
    adjustmentType: adj.rows.value.length > 0 && adj.rows.value.every((r) => r.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const highlightedIds = ref<Set<string>>(new Set())
const conclusionOption = ref('')

const AUDIT_NOTE_KEY = 'G8-3-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-3-audit-conclusion'
const AUDIT_CONCLUSION_OPTION_KEY = 'G8-3-audit-conclusion-option'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const _adjConcl = props.allResponses.get(AUDIT_CONCLUSION_KEY)
const auditConclusion = ref(String(_adjConcl?.conclusion ?? _adjConcl?.remark ?? ''))
conclusionOption.value = props.allResponses.get(AUDIT_CONCLUSION_OPTION_KEY)?.conclusion ?? ''
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: v, remark: null })
})
watch(conclusionOption, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_OPTION_KEY, { conclusion: v || null, remark: null })
})

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onImported() { emit('imported') }

async function onSyncFromModule() {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else ElMessage.info(adj.lastSyncMsg.value || '无相关分录')
}

async function onPushToModule() {
  if (!adj.balanceOk.value) {
    ElMessage.error('借贷不平衡，无法推送')
    return
  }
  const { pushed } = await adj.confirmAndPush()
  if (pushed > 0) ElMessage.success(`已推送 ${pushed} 笔至调整分录模块，并回写 G8-1`)
  else ElMessage.info(adj.lastSyncMsg.value || '无可推送分录（可能已同步或分组不平衡）')
}

function onAccountChange(rowId: string, code: string) {
  const known = G8_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  adj.updateRow(rowId, {
    accountCode: code,
    ...(known ? { accountName: known.name } : {}),
  })
}

function isFromG84(row: { remark?: string; summary?: string }): boolean {
  const r = String(row.remark || '')
  const s = String(row.summary || '')
  return r.includes('G8-4') || s.includes('G8-4')
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

function onHighlightFromFv(e: Event) {
  const detail = (e as CustomEvent).detail || {}
  const names: string[] = Array.isArray(detail.investeeNames) ? detail.investeeNames : []
  const source = String(detail.source || 'G8-4')
  const ids = new Set<string>()
  for (const row of adj.rows.value) {
    const hitBySource = String(row.remark || '').includes(source) || String(row.summary || '').includes('G8-4')
    const hitByName = names.some((n) => n && String(row.summary || '').includes(n))
    if (hitBySource || hitByName) ids.add(row.rowId)
  }
  highlightedIds.value = ids
  if (ids.size) {
    setTimeout(() => {
      highlightedIds.value = new Set()
    }, 5000)
  }
}

function adjRowClassName({ row }: { row: { rowId: string } }): string {
  return highlightedIds.value.has(row.rowId) ? 'g8-adj-hl' : ''
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
  window.addEventListener(G8_NAV_HIGHLIGHT_ADJ_EVENT, onHighlightFromFv as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
  window.removeEventListener(G8_NAV_HIGHLIGHT_ADJ_EVENT, onHighlightFromFv as EventListener)
})
</script>

<style scoped>
.g8-adj { font-size: var(--wp-font-size, 13px); }
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.balance-alert { margin-bottom: 8px; }
.objective-alert { margin-bottom: 10px; }
.guidance-details {
  margin-bottom: 10px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 2px 0; }
.cas-basis { color: #909399; font-size: 11px; }
.adj-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.row-count { font-size: 12px; color: #909399; }
.sync-msg { font-size: 12px; color: #909399; }
.summary-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
.adj-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 8px 0 4px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
}
.adj-footer.balance-fail { background: #fef0f0; }
.footer-label { font-weight: 600; }
.adj-footer .ok { color: #67c23a; }
.adj-footer .err { color: #f56c6c; font-weight: 600; }
.sep { color: #dcdfe6; }
.sheet-note { font-size: 12px; color: #909399; margin: 8px 0 12px; line-height: 1.5; }
.g8-adj :deep(.g8-adj-hl > td) {
  background: #fdf6ec !important;
  animation: g8-adj-flash 1.2s ease-in-out 0s 2;
}
@keyframes g8-adj-flash {
  0%, 100% { background-color: #fdf6ec; }
  50% { background-color: #faecd8; }
}
</style>
