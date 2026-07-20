<template>
<div class="f1-long-term">
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表检查账龄 1 年及以上的大额预付账款，逐户说明未结转原因、出路及是否减值/重分类。</p>
      <p>2. 审定余额 = 期末余额 − 计提坏账准备（灰底自动）；「是否转入其他应收」若为是，通常需在 F1-3 做重分类。</p>
      <p>3. 期后供货或退款可与 F1-7 勾稽；账龄枚举与 F1-1 / 项目账龄配置一致。</p>
      <p>4. 可从 F1-2 一键导入超 1 年户（同名合并，保留已填说明）。</p>
    </div>
  </details>

  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核查账龄1年及以上大额预付账款的存在与可收回性，评价未结转原因、期后消化及坏账/重分类处理是否恰当。"
    class="objective-alert"
  />

  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="doImport">从 F1-2 导入超1年</el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="isReadonly || suggestedAdjustmentCount === 0"
        @click="doPushAdjustments"
      >
        推送拟调整至 F1-3
        <template v-if="suggestedAdjustmentCount">（{{ suggestedAdjustmentCount }}）</template>
      </el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-5')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-5')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-5')">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
  </div>

  <F1SheetAttachments
    :project-id="projectId"
    :wp-id="wpId"
    sheet-code="F1-5"
    label="长期检查附件"
  />

  <!-- 13 列对齐 Excel -->
  <el-table :data="tableData" size="small" border stripe :row-class-name="rowClassName">
    <el-table-column label="债务人名称" width="140" fixed>
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-label">合计</span>
        </template>
        <template v-else>
          <el-input :model-value="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell(row.rowId, 'customerName', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="期末余额" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.endBalance) }}</span>
        <el-input v-else :model-value="row.endBalance" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'endBalance', val)" />
      </template>
    </el-table-column>
    <el-table-column label="账龄" width="120">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" :model-value="row.aging" size="small" :disabled="isReadonly" filterable allow-create
          @change="(val: string) => updateCell(row.rowId, 'aging', val)">
          <el-option v-for="opt in agingOptions" :key="opt" :label="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="经济业务说明" min-width="140">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.businessDescription" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'businessDescription', val)" />
      </template>
    </el-table-column>
    <el-table-column label="未偿还或未结转的原因" min-width="150">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.reason" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'reason', val)" />
      </template>
    </el-table-column>
    <el-table-column label="计划供货还是退款" width="130">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.plan" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'plan', val)" />
      </template>
    </el-table-column>
    <el-table-column label="是否诉讼" width="90" align="center">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" :model-value="row.isLitigation" size="small" :disabled="isReadonly" clearable
          @change="(val: string) => updateCell(row.rowId, 'isLitigation', val || '')">
          <el-option value="Y" label="是" />
          <el-option value="N" label="否" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="是否转入其他应收款" width="130" align="center">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" :model-value="row.transferToOtherReceivable" size="small" :disabled="isReadonly" clearable
          @change="(val: string) => updateCell(row.rowId, 'transferToOtherReceivable', val || '')">
          <el-option value="Y" label="是" />
          <el-option value="N" label="否" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="计提坏账准备金额" width="130" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.badDebtProvision) }}</span>
        <el-input v-else :model-value="row.badDebtProvision" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'badDebtProvision', val)" />
      </template>
    </el-table-column>
    <el-table-column label="审定余额" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="amt auto">{{ fmtAmount(row.rowId === '__subtotal__' ? subtotalRow.auditedBalance : row.auditedBalance) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="期后供货或退款金额" width="140" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.postSettlementAmount) }}</span>
        <el-input v-else :model-value="row.postSettlementAmount" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'postSettlementAmount', val)" />
      </template>
    </el-table-column>
    <el-table-column label="支持性证据" min-width="120">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.supportingEvidence" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'supportingEvidence', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" width="100">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="60" fixed="right" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm v-if="row.rowId !== '__subtotal__'" title="确认删除？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-3" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">1、审计说明</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading"
          @click="generateNote">🤖AI</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="对超1年大额预付的总体检查情况、主要原因分类、减值与重分类考虑..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2、审计结论</span>
        <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading"
          @click="generateConclusion">🤖AI</el-button>
      </div>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。" />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabLongTerm.vue — F1-5 账龄1年及以上大额预付账款检查表（13列）
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF1LongTerm } from '../composables/useF1LongTerm'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import { useAgingConfig } from '@/composables/useAgingConfig'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const { bands } = useAgingConfig(projectIdRef, 'F1')

/** 超1年账龄选项（排除 1年以内） */
const agingOptions = computed(() => {
  const labels = bands.value.filter(b => b.key !== 'within1').map(b => b.label)
  return labels.length ? labels : ['1-2年', '2-3年', '3年以上']
})

const {
  rows,
  subtotalRow,
  auditNote,
  conclusion,
  suggestedAdjustmentCount,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
  pushSuggestedAdjustmentsToF13,
} = useF1LongTerm({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

function doPushAdjustments() {
  const n = pushSuggestedAdjustmentsToF13()
  if (n > 0) ElMessage.success(`已向 F1-3 追加 ${n} 笔拟调整（减值/重分类），请打开 F1-3 复核`)
  else ElMessage.info('无新增拟调整（可能已推送过或未填坏账/转其他应收）')
}
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)

const tableData = computed(() => [
  ...rows.value,
  {
    rowId: '__subtotal__',
    customerName: '合计',
    endBalance: 0,
    aging: '',
    businessDescription: '',
    reason: '',
    plan: '',
    isLitigation: '',
    transferToOtherReceivable: '',
    badDebtProvision: 0,
    auditedBalance: 0,
    postSettlementAmount: 0,
    supportingEvidence: '',
    remark: '',
  },
])

function rowClassName({ row }: { row: any }) {
  return row.rowId === '__subtotal__' ? 'subtotal-row' : ''
}

function doImport() {
  importFromCrossSheet(props.crossSheet.longTermRows.value)
}

function noteContext() {
  return {
    sheet: 'F1-5',
    rowCount: rows.value.length,
    endBalanceTotal: subtotalRow.value.endBalance,
    badDebtTotal: subtotalRow.value.badDebtProvision,
    auditedTotal: subtotalRow.value.auditedBalance,
    litigationCount: rows.value.filter(r => r.isLitigation === 'Y').length,
    transferCount: rows.value.filter(r => r.transferToOtherReceivable === 'Y').length,
    topDebtors: rows.value
      .slice()
      .sort((a, b) => b.endBalance - a.endBalance)
      .slice(0, 5)
      .map(r => `${r.customerName}:${r.endBalance}/${r.aging}`)
      .join('; '),
  }
}

async function generateNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('longterm-reason', auditNote.value, noteContext(), 'F1-5 审计说明')
  if (text) auditNote.value = text
}

async function generateConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('longterm-conclusion', conclusion.value, noteContext(), 'F1-5 审计结论')
  if (text) conclusion.value = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: wpIdRef })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.f1-long-term { padding: 16px; }
.f1-long-term :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f1-long-term :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto { color: #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
</style>
