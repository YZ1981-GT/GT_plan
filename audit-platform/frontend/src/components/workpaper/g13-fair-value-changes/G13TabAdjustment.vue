<template>
  <div class="g13-adjustment">
    <details class="compile-hint">
      <summary>📋 编制提示（对齐 Excel 调整分录汇总 G13-3）</summary>
      <div class="hint-content">
        <p>1. 本表对齐 Excel「公允价值变动收益调整分录汇总表 G13-3」：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / 借贷 / 索引 / 备注。</p>
        <p>2. 「账项调整」影响审定数（AJE）；「报表调整」为重分类（RJE），仅影响列报，不回写 G13-2；「其他」按账项调整处理。</p>
        <p>3. 系统仅汇总科目 <b>6101 公允价值变动收益</b> 的贷−借净额：按「所属科目」写入 G13-2，并同步写入 G13-1 分项调整 overlay（无明细行时自动建占位行）。</p>
        <p>4. 摘要应说明调整事由（估值差异、跨期确认、分类更正等），并交叉索引至 G13-2 / G1·G8·G9·G10·H3 源底稿。</p>
        <p>5. 可经「截止性测试」结果一键回填；亦可「从调整分录模块同步 / 确认调整」与集中台账双向联动（含 6101 及相关对方科目）。</p>
        <p>6. G1-6 / G10-5 公允测试可「推送差异→G13-3」（指纹去重）；推送后请「确认调整」回写 G13-2，本表会高亮与明细调整数的差异。</p>
        <p>7. 「推送 A13」将账项调整行送入未更正错报汇总（报表调整默认不推）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：复核公允价值变动收益（6101）相关账项/报表调整依据充分、借贷平衡，并按所属科目分项同步回明细表 G13-2（CAS 39）"
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
      <el-tag size="small" type="info" effect="plain" data-testid="g13-adjustment-count">
        共 {{ adj.rows.value.length }} 行
      </el-tag>
      <el-tag v-if="adj.summary.value.netAje6101 !== 0" type="success" size="small" effect="plain">
        6101 账项净额 {{ fmtAmount(adj.summary.value.netAje6101) }}
      </el-tag>
      <el-tag v-if="adj.summary.value.netRje6101 !== 0" type="warning" size="small" effect="plain">
        报表调整净额 {{ fmtAmount(adj.summary.value.netRje6101) }}（不回写）
      </el-tag>
      <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>
      <GtIndexChip value="wp:G13-3" :validate="false" />
      <GtIndexChip value="wp:G13-2" :validate="false" />
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="g13"
        sheet="G13-3"
        :disabled="isReadonly"
        @imported="emit('imported')"
      />
      <GtReviewTrigger section-id="G13-3-adjustment" />
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

    <el-alert
      v-if="detailVsAdjMsg"
      type="warning"
      :closable="false"
      show-icon
      class="writeback-hint"
      data-testid="g13-adj-detail-mismatch"
      :title="`与 G13-2 调整数不符：${detailVsAdjMsg}（请「确认调整」回写，或核对明细手工调整）`"
    />
    <el-alert
      v-else-if="adj.rows.value.length && detailHelper.rows.value.length"
      type="success"
      :closable="false"
      class="writeback-hint"
      data-testid="g13-adj-detail-ok"
      title="G13-3 账项回写净额与 G13-2 调整数按所属科目一致"
    />

    <el-table
      :data="adj.rows.value"
      size="small"
      border
      stripe
      style="font-size:13px"
      max-height="520"
      :row-class-name="adj.tableRowClassName"
      data-testid="g13-adjustment-table"
      empty-text="暂无调整分录。点击「新增」录入；6101 净额将按所属科目写入 G13-2。"
    >
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G13-aje" :row-key="row.rowId" />
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
      <el-table-column label="所属科目" width="150">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.belongAccount"
            size="small"
            @change="(v: string) => adj.updateRow(row.rowId, { belongAccount: v })"
          >
            <el-option
              v-for="opt in adj.belongOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ belongLabel(row.belongAccount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width:100%"
            @update:model-value="(v: number | undefined) => adj.updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
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
      【注：本底稿适用于调整分录较多、较复杂的项目，且仅列示与公允价值变动收益相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。】
    </p>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述调整分录的事由、依据、所属科目分项影响，以及拟调整/未调整事项。"
        @change="saveAuditNote"
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
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, toRef, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useG13Adjustment } from '../composables/useG13Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useG13Detail } from '../composables/useG13Detail'
import { G13_BELONG_ACCOUNT_LABELS } from '../composables/g13Constants'
import type { G13AdjustmentWritebackMap } from '../composables/g13AdjStorage'
import {
  findG13AdjustmentWritebackMismatches,
  formatG13AdjWritebackMismatchMessage,
  G13_FV_PUSH_EVENT,
} from '../composables/g13FvCrossHelpers'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../composables/gCycleCutoffFill'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtIndexChip from '../GtIndexChip.vue'
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

const NOTE_KEY = 'G13-adjustment-audit-note'
const CONCLUSION_KEY = 'G13-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const lastWriteback = ref<G13AdjustmentWritebackMap | null>(null)
const projectIdRef = computed(() => props.projectId ?? '')
const auditYearRef = computed(() => props.auditYear)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val } as ChecklistResponse)
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null } as ChecklistResponse)
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

const detailHelper = useG13Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

function applyByBelong(byBelong: G13AdjustmentWritebackMap): void {
  const touched = new Set<string>()
  let created = 0
  for (const [belong, net] of Object.entries(byBelong)) {
    if (Math.abs(net) < 0.005 && !detailHelper.rows.value.some((r) =>
      belong === 'other' ? (!r.belongAccount || r.belongAccount === 'other') : r.belongAccount === belong,
    )) {
      continue
    }
    const target = detailHelper.ensureBelongRow(belong)
    if (target.instrumentName?.includes('回写占位') && Math.abs(net) >= 0.005) created += 1
    detailHelper.updateCell(target.rowId, 'adjustment', net)
    touched.add(target.rowId)
  }
  lastWriteback.value = { ...byBelong }
  if (touched.size === 0) {
    ElMessage.info('6101 账项净额为 0，未改写明细行；已同步 G13-1 调整 overlay')
  } else {
    const extra = created > 0 ? `（新建占位 ${created} 行）` : ''
    ElMessage.success(`已按所属科目回写 ${touched.size} 行明细调整数${extra}，并同步 G13-1`)
  }
}

const adj = useG13Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  projectId: projectIdRef,
  auditYear: auditYearRef,
  applyAdjustmentToDetail: applyByBelong,
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: projectIdRef,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G13',
  itemId: 'G13-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.description)?.description || 'G13 公允价值变动收益调整',
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
  ElMessage.success('已确认：回写 G13-2 明细 + G13-1 调整 overlay，并尝试推送至调整分录模块')
}

const writebackHint = computed(() => {
  const map = lastWriteback.value
  if (!map) return ''
  const parts = Object.entries(map)
    .filter(([, v]) => Math.abs(v) > 0.005)
    .map(([k, v]) => `${belongLabel(k)} ${fmtAmount(v)}`)
  if (!parts.length) return '已同步：6101 账项净额为 0，明细调整数已按分项清零/覆盖。'
  return `最近回写：${parts.join('；')}`
})

const detailVsAdjMismatches = computed(() =>
  findG13AdjustmentWritebackMismatches(detailHelper.rows.value, adj.rows.value),
)
const detailVsAdjMsg = computed(() =>
  formatG13AdjWritebackMismatchMessage(detailVsAdjMismatches.value),
)

function belongLabel(code: string): string {
  if (code === 'other') return '其他'
  return G13_BELONG_ACCOUNT_LABELS[code] ?? code
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

function onFvDiffPushed(e: Event) {
  const d = (e as CustomEvent<{ source?: string; count?: number }>).detail
  const src = d?.source || '公允测试'
  const n = d?.count ?? 0
  ElMessage.info(`${src} 已推送 ${n} 笔差异至本表，请核对后「确认调整」回写明细`)
  // 若同页未自动刷新存档，提示用户切换/刷新；watch 会在 allResponses 更新后生效
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g13, onCutoffFilled as EventListener)
  window.addEventListener(G13_FV_PUSH_EVENT, onFvDiffPushed as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g13, onCutoffFilled as EventListener)
  window.removeEventListener(G13_FV_PUSH_EVENT, onFvDiffPushed as EventListener)
})

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g13-adjustment { padding: 16px; }
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
:deep(.g13-acct-row) { background: #f0f9eb !important; }
</style>
