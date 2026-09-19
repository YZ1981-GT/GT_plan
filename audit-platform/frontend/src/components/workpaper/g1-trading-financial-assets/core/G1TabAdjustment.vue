<template>
  <div class="g1-adjustment" data-testid="g1-adjustment">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「调整分录汇总 G1-3」：记录与交易性金融资产（1501）相关的审计调整。</p>
        <p>2. 「账项调整」影响科目余额（AJE）；「报表调整」为重分类（RJE），仅影响列报。</p>
        <p>3. 借贷合计必须平衡；确认后同步至调整分录模块，并可回写 G1-1 审定表。</p>
        <p>4. 可从「调整分录」模块拉取涉及 1501/6101 等相关科目的分录；亦可推送选中行至 A13 错报汇总。</p>
        <p>5. 调整分录较多、较复杂的项目建议使用本表；项目组可按实际情况选用。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实交易性金融资产相关账项/报表调整的完整与借贷平衡，确认与调整分录模块、G1-1 审定表勾稽一致。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tooltip placement="top" :show-after="300">
          <template #content>
            本表与调整分录模块双向联动。<br />
            此处确认的分录会发布至调整分录模块（科目 1501）；<br />
            亦可从模块拉取已有相关分录。
          </template>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
            + 新增调整分录
          </el-button>
        </el-tooltip>
        <el-button
          size="small"
          :loading="syncing"
          :disabled="isReadonly || !projectId"
          @click="onSyncFromModule"
        >
          从调整分录模块同步
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRows.length === 0"
          @click="onPushA13"
        >
          推送至 A13
        </el-button>
        <span v-if="lastSyncMsg" class="sync-msg">{{ lastSyncMsg }}</span>
      </div>
      <div class="toolbar-right">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-3"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="onConfirm"
        >
          确认调整
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
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
        <el-button size="small" @click="openReviewDialog('G1-3-conclusion')">💬复核</el-button>
      </div>
    </div>

    <div class="balance-indicator">
      <span>借方合计：<strong>{{ fmt(debitTotal) }}</strong></span>
      <span>贷方合计：<strong>{{ fmt(creditTotal) }}</strong></span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差异 {{ fmt(balanceDiff) }}</el-tag>
      <el-tag v-if="netAjeToG1 !== 0" type="info" size="small">
        1501 净调整 {{ fmt(netAjeToG1) }}
      </el-tag>
    </div>

    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
      max-height="520"
      empty-text="暂无调整分录。点击「新增调整分录」或「从调整分录模块同步」。"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="调整事项说明" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(v: string) => updateCell(row.rowId, 'description', v)"
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
            @change="(v: string) => updateCell(row.rowId, 'category', v)"
          >
            <el-option v-for="opt in categoryOptions" :key="opt" :label="opt" :value="opt" />
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
            @change="(v: string) => updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如 1501-交易性金融资产"
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'accountCode', v)"
          />
          <span v-else>{{ row.accountCode || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            style="width: 100%"
            @update:model-value="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            style="width: 100%"
            @update:model-value="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="danger"
            link
            @click="removeRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusion"
      note-ai-section="adjustment-note"
      conclusion-ai-section="adjustment-conclusion"
      note-placeholder="填写审计说明：调整依据、事项性质、对 1501 及损益的影响、与调整分录模块勾稽情况。"
      note-hint="覆盖调整依据、借贷平衡与回写影响。"
      conclusion-hint="按 A/B/C 口径评价调整分录是否恰当、完整。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, watch, inject, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useG1Adjustment, type G1AdjustmentRow } from '../../composables/useG1Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  auditYear?: number | string | null
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const categoryOptions = ['账项调整', '报表调整', '其他']

const {
  rows,
  debitTotal,
  creditTotal,
  balanceDiff,
  isBalanced,
  netAjeToG1,
  syncing,
  lastSyncMsg,
  addRow,
  removeRow,
  updateCell,
  publishAdjustment,
  pushToA13,
  syncFromAdjustmentModule,
} = useG1Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId,
  projectId,
  auditYear: toRef(props, 'auditYear'),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId,
  year: centralYear,
  wpId,
  wpCode: 'G1',
  itemId: 'G1-3-rows',
  buildLineItems: () => rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: rows.value.find((r) => r.description)?.description || 'G1 交易性金融资产调整',
    adjustmentType: rows.value.length > 0 && rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const selectedRows = ref<G1AdjustmentRow[]>([])
function onSelectionChange(sel: G1AdjustmentRow[]) {
  selectedRows.value = sel
}

const NOTE_KEY = 'G1-3-audit-note'
const CONCLUSION_KEY = 'G1-3-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const conclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '')

watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { remark: v })
})
watch(conclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: v })
})

function fmt(n: number): string {
  if (!n) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onSyncFromModule() {
  const n = await syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
  else ElMessage.info(lastSyncMsg.value || '无相关分录')
}

function onPushA13() {
  pushToA13(selectedRows.value.map((r) => r.rowId))
  ElMessage.success(`已推送 ${selectedRows.value.length} 行至 A13`)
}

function onConfirm() {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法确认')
    return
  }
  publishAdjustment()
  ElMessage.success('已确认调整并联动调整分录模块 / G1-1')
}
</script>

<style scoped>
.g1-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.guidance-content { margin-top: 8px; padding-left: 4px; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; flex-wrap: wrap; margin-bottom: 10px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.sync-msg { font-size: 12px; color: #909399; }
.balance-indicator {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  margin-bottom: 10px; padding: 8px 12px; background: #f8f9fb;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px;
}
</style>
