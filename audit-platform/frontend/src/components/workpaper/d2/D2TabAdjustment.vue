<script setup lang="ts">
/**
 * D2TabAdjustment — 调整分录D2-4
 * 10列, 新增/删除, 借贷平衡检查, 推送至A13
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useD2Adjustment, type AdjustmentEntry } from '../composables/useD2Adjustment'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-4',
)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.index || 'unknown'
  openReviewDialog(`D2-adjustment-${rowKey}-${field}`)
}

const selectedRows = ref<string[]>([])

const {
  entries,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  addEntry,
  removeEntry,
  updateEntry,
  pushToA13,
} = useD2Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 同步到集中调整登记 ─────────────────────────────────────────────
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'D2',
  itemId: 'D2-entry-rows',
  buildLineItems: () => entries.value.map((e) => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: entries.value.find((e) => e.description)?.description || 'D2 应收账款调整',
    adjustmentType: entries.value.length > 0 && entries.value.every((e) => e.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
refreshStatus()

function handleSelection(selection: AdjustmentEntry[]) {
  selectedRows.value = selection.map(e => e.rowId)
}

function handlePushToA13() {
  pushToA13(selectedRows.value)
}
</script>

<template>
  <div class="d2-tab-adjustment">
    <div class="tab-header">
      <h4>调整分录汇总表 D2-4</h4>
      <GtReviewTrigger section-id="D2-adjustment-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>汇总应收账款相关审计调整（AJE）与重分类调整（RJE），确保借贷平衡并推送至 A13 未更正错报汇总。</p>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addEntry">
          新增调整分录
        </el-button>
        <el-button
          size="small"
          type="warning"
          :disabled="selectedRows.length === 0"
          @click="handlePushToA13"
        >推送至A13</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        >同步到集中登记</el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}</el-tag>
      </div>
    </div>

    <el-table
      :data="entries"
      border
      size="small"
      style="width: 100%"
      @selection-change="handleSelection"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="调整事项" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            @change="(v: string) => updateEntry(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
          <GtReviewDot row-prefix="D2-adjustment" :row-key="row.rowId" />
        </template>
      </el-table-column>
      <el-table-column label="类别" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.entryType"
            size="small"
            @change="(v: string) => updateEntry(row.rowId, 'entryType', v)"
          >
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'primary' : 'warning'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" @change="(v: string) => updateEntry(row.rowId, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateEntry(row.rowId, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" placeholder="附注项目" @change="(v: string) => updateEntry(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateEntry(row.rowId, 'debitAmount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateEntry(row.rowId, 'creditAmount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="140">
        <template #default="{ row }">
          <div class="index-cell">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="索引号" @change="(v: string) => updateEntry(row.rowId, 'indexRef', v)" />
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeEntry(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 平衡行 -->
    <div class="balance-bar" :class="{ balanced: isBalanced, unbalanced: !isBalanced }">
      <span>借方合计: {{ displayPrefs.fmtAmount(debitTotal) }}</span>
      <span>贷方合计: {{ displayPrefs.fmtAmount(creditTotal) }}</span>
      <span v-if="isBalanced" class="balance-status">✓ 平衡</span>
      <span v-else class="balance-status">✗ 不平衡：差额{{ displayPrefs.fmtAmount(balanceDiff) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-adjustment { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.index-cell { display: flex; align-items: center; gap: 6px; }
.index-cell .el-input { flex: 1; }
.balance-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 10px 12px; margin-top: 10px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); font-weight: 600;
}
.balance-bar.balanced { background: #f0f9eb; border: 1px solid #e1f3d8; }
.balance-bar.unbalanced { background: #fef0f0; border: 1px solid #fde2e2; }
.balance-status { margin-left: auto; }
.balanced .balance-status { color: #67c23a; }
.unbalanced .balance-status { color: #f56c6c; }
</style>
