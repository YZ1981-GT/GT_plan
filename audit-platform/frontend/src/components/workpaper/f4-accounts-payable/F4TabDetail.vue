<script setup lang="ts">
/**
 * F4TabDetail — F4-2 应付账款明细表（27列→3区段Tab）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.2
 * 3区段Tab切换(基础信息/账龄与核对/调整与审定) + 行同步 + 账龄交叉校验
 * 📎OCR列(发票金额/供应商识别→确认merge)
 * 动态行增删 + 底部合计 + 导入导出
 * Requirements: 5.1~5.8, 14.4
 */
import { inject, toRef, ref, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { useF4Detail } from '../composables/useF4Detail'
import type { APDetailRow } from '../composables/useF4Detail'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  activeSegment,
  rows,
  filteredRows,
  subtotalRow,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  rowClassName,
  basicColumns,
  agingColumns,
  auditColumns,
} = useF4Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── OCR ─────────────────────────────────────────────────────────────────────
const ocrLoading = ref(false)

async function handleOcr(row: APDetailRow) {
  ocrLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/contract-ocr`, {
      rowId: row.rowId,
    })
    const result = data?.data || data
    const msg = `识别结果：供应商=${result.supplier || '未识别'}，金额=${result.amount ?? '未识别'}`
    const confirmed = await ElMessageBox.confirm(msg, '📎 OCR识别结果', {
      confirmButtonText: '确认合并',
      cancelButtonText: '取消',
      type: 'info',
    }).catch(() => null)
    if (confirmed === 'confirm') {
      if (result.supplier) updateCell(row.rowId, 'creditor', result.supplier)
      if (result.amount != null) updateCell(row.rowId, 'currentCredit', result.amount)
      ElMessage.success('OCR数据已合并')
    }
  } catch {
    ElMessage.error('OCR识别失败')
  } finally {
    ocrLoading.value = false
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-2`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-2明细表模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-2`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-2明细表数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-2`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────
const NOTE_KEY = 'F4-2-audit-note'
const CONCLUSION_KEY = 'F4-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistF4(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistF4(NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistF4(CONCLUSION_KEY, val)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<template>
  <div class="f4-tab-detail">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 明细表共27列，拆为3区段Tab操作，行在各区段间同步。</p>
        <p>2. 期末余额(公式) = 期初审定 + 本期贷方 - 本期借方（贷方科目方向）。</p>
        <p>3. 账龄合计(公式) = 1年内 + 1-2年 + 2-3年 + 3年以上。若合计≠期末→行标红。</p>
        <p>4. 审定余额(公式) = 期末 + 账项调整(AJE) + 重分类(RJE)。</p>
        <p>5. 📎OCR列可上传发票扫描件，自动识别金额/供应商并合并。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核对应付账款(2202)明细的完整性与准确性，验证期末余额=期初审定+本期贷方-本期借方，账龄划分合理，关注长期挂账与关联方款项。"
    />

    <div class="section-toolbar tab-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索债权人/公司代码/款项性质"
          clearable
          size="small"
          style="width: 240px"
        />
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:F4-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-2-detail')"
        >复核</el-button>
      </div>
    </div>

    <!-- 3区段Tab切换 -->
    <el-tabs v-model="activeSegment" type="card" class="segment-tabs">
      <el-tab-pane label="基础信息" name="basic" />
      <el-tab-pane label="账龄与核对" name="aging" />
      <el-tab-pane label="调整与审定" name="audit" />
    </el-tabs>

    <!-- ─── 基础信息区段 ──────────────────────────────────────────────── -->
    <el-table
      v-show="activeSegment === 'basic'"
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      style="width: 100%; font-size: 13px"
      max-height="600"
    >
      <el-table-column prop="seq" label="序号" width="60" fixed />
      <el-table-column label="📎" width="50" fixed>
        <template #default="{ row }">
          <el-button link size="small" :loading="ocrLoading" @click="handleOcr(row)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column label="债权人" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.creditor" size="small" @change="(v: string) => updateCell(row.rowId, 'creditor', v)" />
          <span v-else>{{ row.creditor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公司代码" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.companyCode" size="small" @change="(v: string) => updateCell(row.rowId, 'companyCode', v)" />
          <span v-else>{{ row.companyCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联方类型" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relatedPartyType" size="small" @change="(v: string) => updateCell(row.rowId, 'relatedPartyType', v)" />
          <span v-else>{{ row.relatedPartyType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="款项性质" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.paymentNature" size="small" @change="(v: string) => updateCell(row.rowId, 'paymentNature', v)" />
          <span v-else>{{ row.paymentNature }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingAdjusted" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'openingAdjusted', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.openingAdjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期借方" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentDebit" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentDebit', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.currentDebit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期贷方" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentCredit" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentCredit', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.currentCredit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="期末 = 期初 + 贷方 - 借方" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.closingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 账龄与核对区段 ────────────────────────────────────────────── -->
    <el-table
      v-show="activeSegment === 'aging'"
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      style="width: 100%; font-size: 13px"
      max-height="600"
    >
      <el-table-column prop="seq" label="序号" width="60" fixed />
      <el-table-column prop="creditor" label="债权人" min-width="120" fixed />
      <el-table-column label="1年以内" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.aging1Year" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'aging1Year', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.aging1Year) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="1-2年" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.aging1to2Year" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'aging1to2Year', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.aging1to2Year) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="2-3年" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.aging2to3Year" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'aging2to3Year', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.aging2to3Year) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="3年以上" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.aging3YearPlus" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'aging3YearPlus', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.aging3YearPlus) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账龄合计" min-width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="合计 = 各账龄段SUM" placement="top">
            <span class="formula-cell" :class="{ 'mismatch-cell': row.agingMismatch }">{{ fmtAmount(row.agingTotal) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="是否函证" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.isConfirmed" size="small" @change="(v: string) => updateCell(row.rowId, 'isConfirmed', v)" />
          <span v-else>{{ row.isConfirmed }}</span>
        </template>
      </el-table-column>
      <el-table-column label="函证结果" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.confirmationResult" size="small" @change="(v: string) => updateCell(row.rowId, 'confirmationResult', v)" />
          <span v-else>{{ row.confirmationResult }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期后付款" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.subsequentPayment" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'subsequentPayment', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.subsequentPayment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="付款日期" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.subsequentPaymentDate" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => updateCell(row.rowId, 'subsequentPaymentDate', v)" />
          <span v-else>{{ row.subsequentPaymentDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 调整与审定区段 ────────────────────────────────────────────── -->
    <el-table
      v-show="activeSegment === 'audit'"
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      style="width: 100%; font-size: 13px"
      max-height="600"
    >
      <el-table-column prop="seq" label="序号" width="60" fixed />
      <el-table-column prop="creditor" label="债权人" min-width="120" fixed />
      <el-table-column label="账项调整" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.ajeAdjustment" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'ajeAdjustment', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.ajeAdjustment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="重分类" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.rjeReclassification" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'rjeReclassification', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.rjeReclassification) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定余额" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="审定 = 期末 + AJE + RJE" placement="top">
            <span class="formula-cell audited-cell">{{ fmtAmount(row.adjustedBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="审定1年内" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.adjustedAging1" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'adjustedAging1', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.adjustedAging1) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定1-2年" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.adjustedAging2" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'adjustedAging2', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.adjustedAging2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定2-3年" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.adjustedAging3" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'adjustedAging3', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.adjustedAging3) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定3年以上" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.adjustedAging4" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'adjustedAging4', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.adjustedAging4) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 底部合计 ──────────────────────────────────────────────────── -->
    <div class="subtotal-bar">
      <span>合计：期初 {{ fmtAmount(subtotalRow.openingAdjusted) }} ｜借方 {{ fmtAmount(subtotalRow.currentDebit) }} ｜贷方 {{ fmtAmount(subtotalRow.currentCredit) }} ｜期末 {{ fmtAmount(subtotalRow.closingBalance) }} ｜审定 {{ fmtAmount(subtotalRow.adjustedBalance) }}</span>
    </div>

    <!-- ─── 审计说明 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-2-note')">💬</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述明细核对情况、账龄划分依据、长期挂账与关联方款项关注点及处理。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ─── 审计结论 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或审计范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-detail {
  font-size: var(--wp-font-size, 13px);
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: var(--wp-font-size, 13px);
}
.guidance-details .guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-details .guidance-content p {
  margin: 2px 0;
}
.audit-objective {
  margin-bottom: 12px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.segment-tabs {
  margin-bottom: 8px;
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
.audited-cell {
  font-weight: 600;
  color: #409eff;
}
.mismatch-cell {
  color: #f56c6c;
  font-weight: 700;
}
:deep(.aging-mismatch-row td) {
  background: #fef0f0 !important;
}
.subtotal-bar {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
</style>
