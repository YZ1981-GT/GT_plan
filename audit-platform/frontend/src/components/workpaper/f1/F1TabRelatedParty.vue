<template>
<div class="f1-related-party">
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表列示关联方预付账款，核真实性、商业实质与定价公允性，防止漏识关联方及资金占用。</p>
      <p>2. 期末余额 = 期初 + 借方 − 贷方；账面价值 = 期末 − 坏账准备（灰底自动）。</p>
      <p>3. 关联关系按模板枚举选择；款项性质与 F1-2 一致；大额长期关联预付关注占资与披露。</p>
      <p>4. 可从 F1-2 导入非「非关联方」户（同名合并）；结论与附注披露勾稽。</p>
    </div>
  </details>

  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实对关联方预付款项的真实性、合理性、合法性及会计处理正确性，确认不存在未识别关联方，关联方关系及交易披露恰当。"
    class="objective-alert"
  />

  <!-- 完整性校验：登记表关联方未在本表识别 -->
  <el-alert
    v-if="missingRelatedParties.length > 0"
    type="warning"
    :closable="false"
    show-icon
    style="margin-bottom: 12px"
  >
    <template #title>
      <span>关联方清单中有 {{ missingRelatedParties.length }} 个未在本表识别（防漏列）：{{ missingRelatedParties.slice(0, 6).join('、') }}{{ missingRelatedParties.length > 6 ? '…' : '' }}</span>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="warning"
        plain
        style="margin-left: 8px"
        @click="doAddMissing"
      >补充漏列（{{ missingRelatedParties.length }}）</el-button>
    </template>
  </el-alert>

  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
      <el-button size="small" :disabled="isReadonly" @click="doImport">从 F1-2 导入</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-6')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-6')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-6')">
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
    sheet-code="F1-6"
    label="关联方检查附件"
  />

  <el-table :data="tableData" size="small" border stripe :row-class-name="rowClassName">
    <el-table-column label="关联方名称" width="140" fixed>
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="subtotal-label">合计</span>
        <el-input v-else :model-value="row.partyName" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'partyName', val)" />
      </template>
    </el-table-column>
    <el-table-column label="关联关系" width="160">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" :model-value="row.relationship" size="small"
          :disabled="isReadonly" filterable allow-create
          @change="(val: string) => updateCell(row.rowId, 'relationship', val)">
          <el-option v-for="opt in F1_RELATED_PARTY_RELATIONSHIP_OPTIONS" :key="opt" :label="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="期初余额" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.priorBalance) }}</span>
        <el-input v-else :model-value="row.priorBalance" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'priorBalance', val)" />
      </template>
    </el-table-column>
    <el-table-column label="借方发生额" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.debit) }}</span>
        <el-input v-else :model-value="row.debit" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'debit', val)" />
      </template>
    </el-table-column>
    <el-table-column label="贷方发生额" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.credit) }}</span>
        <el-input v-else :model-value="row.credit" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'credit', val)" />
      </template>
    </el-table-column>
    <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="amt auto">{{ fmtAmount(row.rowId === '__subtotal__' ? subtotalRow.endBalance : row.endBalance) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="减：坏账准备" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.badDebt) }}</span>
        <el-input v-else :model-value="row.badDebt" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'badDebt', val)" />
      </template>
    </el-table-column>
    <el-table-column label="账面价值" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="amt auto">{{ fmtAmount(row.rowId === '__subtotal__' ? subtotalRow.bookValue : row.bookValue) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="发生时间及账龄" width="160">
      <template #default="{ row }">
        <el-select
          v-if="row.rowId !== '__subtotal__'"
          :model-value="row.agingDescription"
          size="small"
          :disabled="isReadonly"
          filterable
          allow-create
          clearable
          placeholder="选择账龄"
          @change="(val: string) => updateCell(row.rowId, 'agingDescription', val ?? '')"
        >
          <el-option v-for="opt in agingOptions" :key="opt" :label="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="发生原因（款项性质）" width="140">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" :model-value="row.natureDescription" size="small"
          :disabled="isReadonly" filterable allow-create clearable
          @change="(val: string) => updateCell(row.rowId, 'natureDescription', val || '')">
          <el-option v-for="opt in F1_PAYMENT_NATURE_OPTIONS" :key="opt" :label="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="期后到货" width="110" align="right">
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(subtotalRow.postPeriodDelivery) }}</span>
        <el-input v-else :model-value="row.postPeriodDelivery" size="small" :disabled="isReadonly"
          @change="(val: any) => updateCell(row.rowId, 'postPeriodDelivery', val)" />
      </template>
    </el-table-column>
    <el-table-column label="索引号" width="90">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" :model-value="row.indexRef" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'indexRef', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" min-width="100">
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
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计说明</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading"
          @click="generateNote">🤖AI</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="评价关联方预付的商业实质、定价公允性、是否存在资金占用及披露充分性..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计结论</span>
        <div class="opinion-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading"
            @click="generateConclusion">🤖AI</el-button>
          <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
        </div>
      </div>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。" />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabRelatedParty.vue — F1-6 关联方及交易检查表（13列，对齐 Excel）
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useF1RelatedParty,
  F1_RELATED_PARTY_RELATIONSHIP_OPTIONS,
} from '../composables/useF1RelatedParty'
import { F1_PAYMENT_NATURE_OPTIONS } from '../composables/useF1Adjudication'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { useAgingConfig } from '@/composables/useAgingConfig'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from '../composables/agingPresets'

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
  /** 项目关联方清单（来自后端 render 登记表），用于完整性校验 */
  relatedParties?: string[]
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { bands } = useAgingConfig(projectIdRef, 'F1')
const agingOptions = computed(() => {
  const labels = bands.value.map((b) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[b.key] || b.label)
  return labels.length ? labels : ['1年以内(含1年)', '1至2年(含2年)', '2至3年(含3年)', '3年以上']
})

const {
  rows,
  subtotalRow,
  auditNote,
  conclusion,
  missingRelatedParties,
  addMissingRelatedParties,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
} = useF1RelatedParty({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  relatedParties: computed(() => props.relatedParties ?? []) as unknown as Ref<string[]>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)

function doAddMissing() {
  const n = addMissingRelatedParties()
  if (n > 0) ElMessage.success(`已补充 ${n} 个疑似漏列关联方（请核对余额与关系）`)
  else ElMessage.info('无漏列关联方')
}

const tableData = computed(() => [
  ...rows.value,
  {
    rowId: '__subtotal__',
    partyName: '合计',
    relationship: '',
    priorBalance: 0,
    debit: 0,
    credit: 0,
    endBalance: 0,
    badDebt: 0,
    bookValue: 0,
    agingDescription: '',
    natureDescription: '',
    postPeriodDelivery: 0,
    indexRef: '',
    remark: '',
  },
])

function rowClassName({ row }: { row: any }) {
  return row.rowId === '__subtotal__' ? 'subtotal-row' : ''
}

function doImport() {
  importFromCrossSheet(props.crossSheet.relatedPartyRows.value)
}

function noteContext() {
  return {
    sheet: 'F1-6',
    rowCount: rows.value.length,
    endBalanceTotal: subtotalRow.value.endBalance,
    bookValueTotal: subtotalRow.value.bookValue,
    parties: rows.value.map(r => `${r.partyName}(${r.relationship}):${r.endBalance}`).slice(0, 8).join('; '),
  }
}

async function generateNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('related-party-note', auditNote.value, noteContext(), 'F1-6 审计说明')
  if (text) auditNote.value = text
}

async function generateConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('related-party-conclusion', conclusion.value, noteContext(), 'F1-6 审计结论')
  if (text) conclusion.value = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function openReview() {
  openReviewDialog?.('F1-rp-conclusion')
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
.f1-related-party { padding: 16px; }
.f1-related-party :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f1-related-party :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

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
.opinion-title { font-size: 14px; font-weight: 600; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; }
.opinion-actions { display: flex; gap: 6px; }
</style>
