<template>
<div class="d3-long-term">
  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <strong>审计目标</strong>：检查账龄 1 年以上预收账款的未结转原因，评估是否应确认收入或存在长期挂账、需转营业外收入的风险（CAS 14 收入确认）。
    </template>
  </el-alert>

  <!-- 工具栏 -->
  <div class="lt-toolbar">
    <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
    <el-button size="small" :disabled="isReadonly" @click="doImport">从D3-2导入</el-button>
    <GtReviewTrigger section-id="D3-lt-header" />
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="onExportTemplate">导出模板</el-button>
      <el-button @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button>导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>

  <!-- 处理结论跨底稿联动提示（CAS14：应确认收入→D4 / 应转营业外收入→K12） -->
  <div v-if="disposalLinkageHints.length" class="disposal-hints">
    <el-alert
      v-for="hint in disposalLinkageHints"
      :key="hint.key"
      :type="hint.type"
      :closable="false"
      show-icon
      class="disposal-hint"
    >
      <template #title>
        <span>{{ hint.text }}</span>
        <GtIndexChip v-if="hint.target" :value="hint.target" :context="hint.context" />
      </template>
    </el-alert>
  </div>

  <!-- 明细表 -->
  <el-table :data="tableData" size="small" border stripe>
    <el-table-column label="对方单位名称" width="160">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-label">合计</span>
        </template>
        <template v-else>
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell(row.rowId, 'customerName', val)" />
          <GtIndexChip target="D3-2" :label="row.customerName" />
          <GtReviewDot row-prefix="D3-lt" :row-key="row.rowId" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="期末余额" width="120" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.endBalance) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.endBalance" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'endBalance', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="账龄" width="100">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.aging" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'aging', val)" />
      </template>
    </el-table-column>
    <el-table-column label="经济业务说明" min-width="140">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.businessDescription" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'businessDescription', val)" />
      </template>
    </el-table-column>
    <el-table-column label="未结转原因" min-width="160">
      <template #default="{ row }">
        <template v-if="row.rowId !== '__subtotal__'">
          <div class="reason-cell">
            <el-input v-model="row.reason" size="small" :disabled="isReadonly"
              @change="(val: string) => updateCell(row.rowId, 'reason', val)" />
            <el-button
              size="small"
              :disabled="isReadonly || !aiAvailable || aiLoading"
              :loading="aiLoading"
              @click="genRowReason(row)"
            >🤖</el-button>
          </div>
        </template>
      </template>
    </el-table-column>
    <el-table-column label="结转金额" width="120" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.settlementAmount) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.settlementAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'settlementAmount', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="处理结论" width="150">
      <template #default="{ row }">
        <template v-if="row.rowId !== '__subtotal__'">
          <el-select v-model="row.disposalConclusion" size="small" clearable :disabled="isReadonly"
            placeholder="判断结论" @change="(val: any) => updateCell(row.rowId, 'disposalConclusion', val || '')">
            <el-option v-for="c in DISPOSAL_CONCLUSIONS" :key="c" :value="c" :label="c" />
          </el-select>
        </template>
      </template>
    </el-table-column>
    <el-table-column label="处理计划" width="120">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.plan" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'plan', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" width="100">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <!-- 操作 -->
    <el-table-column label="操作" width="60" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm v-if="row.rowId !== '__subtotal__'" title="确认删除？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <!-- 审计说明 + 结论 -->
  <div class="audit-notes-section">
    <h4 class="section-header-row">
      审计说明
      <el-button
        size="small"
        :disabled="isReadonly || !aiAvailable || aiLoading"
        :loading="aiLoading"
        @click="genAuditNote"
      >🤖AI</el-button>
    </h4>
    <el-input
      v-model="auditNote"
      type="textarea"
      :rows="3"
      :disabled="isReadonly"
      placeholder="对超1年预收账款未结转原因的审计说明..."
    />
    <h4 style="margin-top: 16px">审计结论</h4>
    <el-input
      v-model="conclusion"
      type="textarea"
      :rows="2"
      :disabled="isReadonly"
      placeholder="审计结论..."
    />
  </div>

  <!-- 编制提示 -->
  <details class="guidance-fold">
    <summary>📋 编制提示（CAS 14 收入 / CAS 1301 审计证据）</summary>
    <p>1. 对超 1 年未结转预收款，核查合同履约进度、是否已满足收入确认的五步法条件（控制权转移）；</p>
    <p>2. 关注无合同支撑或对方已注销的长期挂账，评估是否应转入营业外收入或作为无需支付款项处理；</p>
    <p>3. 结合期后结转（D3-7）情况判断管理层结转安排的合理性，异常长期挂账应提请调整或披露。</p>
  </details>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabLongTerm.vue — D3-5 账龄1年以上检查表
 * 8列表 + 从D3-2导入 + AI建议 + GtIndexChip
 */
import { computed, toRef, type Ref } from 'vue'
import { useD3LongTerm, DISPOSAL_CONCLUSIONS } from '../composables/useD3LongTerm'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import type { useD3CrossSheet } from '../composables/useD3CrossSheet'
import type { ChecklistResponse } from '../composables/useD3FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtReviewDot from '../GtReviewDot.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useD3CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const {
  rows,
  subtotalRow,
  disposalSummary,
  auditNote,
  conclusion,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
} = useD3LongTerm({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD3AiGenerate(wpIdRef)

async function genRowReason(row: { rowId: string; customerName: string; endBalance: number; aging: string; reason: string }) {
  if (props.isReadonly) return
  const text = await generateAndConfirm('longterm-reason', row.reason, {
    customerName: row.customerName,
    endBalance: row.endBalance,
    aging: row.aging,
  }, `AI · 未结转原因 — ${row.customerName || '该行'}`)
  if (text) updateCell(row.rowId, 'reason', text)
}

async function genAuditNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNote.value, {
    task: '超1年预收账款审计说明',
    rowCount: rows.value.length,
  }, 'AI · 审计说明')
  if (text) auditNote.value = text
}

// Append subtotal row for display
const tableData = computed(() => [
  ...rows.value,
  { rowId: '__subtotal__', customerName: '合计', endBalance: 0, aging: '', businessDescription: '', reason: '', settlementAmount: 0, disposalConclusion: '', plan: '', remark: '' },
])

// 处理结论跨底稿联动提示（基于 disposalSummary）
function fmtAmt(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
const disposalLinkageHints = computed(() => {
  const s = disposalSummary.value
  const hints: Array<{ key: string; type: 'warning' | 'info'; text: string; target?: string; context?: string }> = []
  if (s.shouldRecognizeRevenue.count > 0) {
    hints.push({
      key: 'revenue',
      type: 'warning',
      text: `${s.shouldRecognizeRevenue.count} 笔判断为「应确认收入」（合计 ${fmtAmt(s.shouldRecognizeRevenue.amount)} 元），履约义务或已完成，请核对收入截止（D4）并考虑调整分录。`,
      target: 'wp:D4',
      context: '应确认收入的长期预收关联收入截止测试底稿 D4',
    })
  }
  if (s.shouldTransferNonOperating.count > 0) {
    hints.push({
      key: 'non-operating',
      type: 'warning',
      text: `${s.shouldTransferNonOperating.count} 笔判断为「应转营业外收入」（合计 ${fmtAmt(s.shouldTransferNonOperating.amount)} 元），确无需支付/对方注销/超时效，关注营业外收入（K12）与披露。`,
      target: 'wp:K12',
      context: '应转营业外收入的长期挂账预收关联营业外收入底稿 K12',
    })
  }
  if (s.shouldRefund.count > 0) {
    hints.push({
      key: 'refund',
      type: 'info',
      text: `${s.shouldRefund.count} 笔判断为「应退回」（合计 ${fmtAmt(s.shouldRefund.amount)} 元），关注列报是否应重分类至其他应付款/其他流动负债。`,
    })
  }
  if (s.pending.count > 0) {
    hints.push({
      key: 'pending',
      type: 'info',
      text: `${s.pending.count} 笔处理结论「待确定」（合计 ${fmtAmt(s.pending.amount)} 元），需进一步取证后明确处理方向。`,
    })
  }
  return hints
})

function doImport() {
  const longTermRows = props.crossSheet.longTermRows.value
  importFromCrossSheet(longTermRows)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const { onExportTemplate, onExportData, onImportFile } = useD3TabImportExport(wpIdRef, 'D3-5')
</script>

<style scoped>
.d3-long-term { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.guidance-fold { margin-top: 16px; font-size: 12px; color: #606266; background: #f9fafb; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.guidance-fold summary { cursor: pointer; font-weight: 600; color: #409eff; }
.guidance-fold p { margin: 6px 0 0; line-height: 1.6; }
.lt-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.disposal-hints { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
.disposal-hint :deep(.el-alert__title) { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.reason-cell { display: flex; gap: 4px; align-items: center; }
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; margin-bottom: 8px; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.note-label { display: flex; gap: 8px; }
</style>
