<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D1TabAdjustment — 调整分录 D1-5（对齐 D4-4）
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD1Adjustment, type D1AdjustmentRow } from '../composables/useD1Adjustment'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useD1FormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

async function saveImmediate(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>) {
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
  } catch {
    ElMessage.warning('保存失败，请重试')
  }
}

const {
  rows,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  ajeTotal,
  rjeTotal,
  addEntry,
  removeEntry,
  updateCell,
  publishAdjustment,
  pushToA13,
} = useD1Adjustment({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  saveImmediate,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-5')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)

// ─── 同步到集中调整登记 ─────────────────────────────────────────────
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'D1',
  itemId: 'D1-entry-rows',
  buildLineItems: () => rows.value.map((r) => ({
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: rows.value.find((r) => r.description)?.description || 'D1 应收票据调整',
    adjustmentType: rows.value.length > 0 && rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
refreshStatus()

const selectedRows = ref<D1AdjustmentRow[]>([])
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

const categoryOptions = [
  { label: '账项调整', value: '账项调整' },
  { label: '报表调整', value: '报表调整' },
  { label: '其他', value: '其他' },
]

const auditNote = computed({
  get: () => props.allResponses.get('D1-5-note')?.remark || '',
  set: (val: string) => (props.allResponses as Map<string, any>).set('D1-5-note', { item_id: 'D1-5-note', conclusion: null, remark: val }),
})

const auditConclusion = computed({
  get: () => props.allResponses.get('D1-5-conclusion')?.remark || '',
  set: (val: string) => (props.allResponses as Map<string, any>).set('D1-5-conclusion', { item_id: 'D1-5-conclusion', conclusion: null, remark: val }),
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleSelectionChange(selection: D1AdjustmentRow[]) {
  selectedRows.value = selection
}

function handlePushToA13() {
  const indices = selectedRows.value
    .map((row) => rows.value.findIndex(r => r.rowId === row.rowId) + 1)
    .filter(i => i > 0)
  pushToA13(indices)
}

function buildAdjContext(guidance: string): Record<string, unknown> {
  const lines = rows.value.map((r) =>
    `${r.description || '调整'}: ${r.accountName} 借${fmtAmount(r.debitAmount)}/贷${fmtAmount(r.creditAmount)} [${r.category}]`,
  )
  return {
    sheet: 'D1-5',
    rowCount: rows.value.length,
    debitTotal: debitTotal.value,
    creditTotal: creditTotal.value,
    isBalanced: isBalanced.value,
    tableSummary: lines.slice(0, 20).join('\n') || '（暂无调整分录）',
    auditNote: auditNote.value,
    guidance,
  }
}

async function generateNote() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'adj-note',
      auditNote.value,
      buildAdjContext('根据D1-5调整分录汇总生成审计说明，说明调整原因、对审定表/AJE/RJE的影响。'),
      'AI · 审计说明',
    )
    if (text) auditNote.value = text
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateConclusion() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'adj-conclusion',
      auditConclusion.value,
      buildAdjContext(`审计说明：${auditNote.value || '（未填写）'}；借贷${isBalanced.value ? '平衡' : `不平衡差异${fmtAmount(balanceDiff.value)}`}`),
      'AI · 审计结论',
    )
    if (text) auditConclusion.value = text
  } finally {
    aiLoadingConclusion.value = false
  }
}

function saveAuditMeta() {
  saveImmediate([
    { item_id: 'D1-5-note', conclusion: null, remark: auditNote.value || null },
    { item_id: 'D1-5-conclusion', conclusion: null, remark: auditConclusion.value || null },
  ])
}
</script>

<template>
  <div class="d1-tab-adjustment">
    <div class="tab-header">
      <h4>调整分录汇总表 D1-5</h4>
      <GtReviewTrigger section-id="D1-adjustment-header" />
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录应收票据审计过程中发现的需要调整的会计分录。</p>
        <p>2. 「账项调整」(AJE) 影响科目余额；「报表调整」(RJE) 仅影响报表列报。</p>
        <p>3. 借方合计与贷方合计必须平衡；不平衡时请关注差异金额。</p>
        <p>4. 确认后自动更新 D1-1 审定表 AJE/RJE 列；可选中分录推送至 A13。</p>
        <p>5. 导出模板含「编制说明」工作表；表头在第5行，数据从第6行填写。</p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addEntry">
          + 新增调整分录
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRows.length === 0"
          @click="handlePushToA13"
        >
          推送至 A13
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-button-group size="small">
          <el-button @click="onExportTemplate">导出模板</el-button>
          <el-button @click="onExportData">导出数据</el-button>
          <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="publishAdjustment"
        >
          确认调整
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
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

    <div class="balance-indicator">
      <span>借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong></span>
      <span>AJE 合计：<strong>{{ fmtAmount(ajeTotal) }}</strong></span>
      <span>RJE 合计：<strong>{{ fmtAmount(rjeTotal) }}</strong></span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差异{{ fmtAmount(balanceDiff) }}</el-tag>
    </div>

    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
      @selection-change="handleSelectionChange"
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
          <span v-else>{{ row.description || '-' }}</span>
          <GtReviewDot row-prefix="D1-adjustment" :row-key="row.rowId" />
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
            <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
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
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如 1121-应收票据"
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)"
          />
          <span v-else>{{ row.accountName || '-' }}</span>
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
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            class="cell-amount-input"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v || 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            class="cell-amount-input"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v || 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
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
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column width="72" align="center">
        <template #header>
          <el-tooltip content="是否已推送至 A13 调整分录表" placement="top" :show-after="200">
            <span class="col-header-ellipsis">已推送</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip
            :content="row.isPushedToAdjTable ? '已推送至 A13' : '尚未推送'"
            placement="top"
            :show-after="200"
          >
            <el-tag :type="row.isPushedToAdjTable ? 'success' : 'info'" size="small">
              {{ row.isPushedToAdjTable ? '是' : '否' }}
            </el-tag>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeEntry(rows.findIndex(r => r.rowId === row.rowId) + 1)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="rows.length === 0" class="empty-hint">
      暂无调整分录。点击「新增调整分录」添加，或从 Excel 模板导入。
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D1-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:A13" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span>1. 审计说明</span>
          <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
            <el-button size="small" plain :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNote">
              🤖 AI
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @blur="saveAuditMeta"
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span>2. 审计结论</span>
          <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
            <el-button size="small" plain :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusion">
              🤖 AI
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @blur="saveAuditMeta"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d1-tab-adjustment { padding: 12px 0; width: 100%; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; }
.guidance-content p { margin: 4px 0; }
.tab-toolbar {
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.balance-indicator {
  display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
  margin-bottom: 12px; padding: 8px 12px; background: #fafafa; border-radius: 4px; font-size: var(--wp-font-size, 13px);
}
.cell-amount-input { width: 100%; }
.empty-hint { text-align: center; color: #909399; padding: 24px; font-size: var(--wp-font-size, 13px); }
.opinion-card { margin-top: 16px; border: 1px solid #ebeef5; }
.opinion-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.opinion-title { font-weight: 600; font-size: 14px; }
.opinion-chips { display: flex; gap: 8px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-weight: 500; font-size: var(--wp-font-size, 13px); }
.col-header-ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
  cursor: default;
}
</style>
