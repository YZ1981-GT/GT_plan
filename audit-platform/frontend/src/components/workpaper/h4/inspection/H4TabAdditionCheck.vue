<template>
  <div class="h4-tab-addition-check">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-4增加检查：对本期新增工程物资逐项检查，核验入库单/发票/合同三方一致性。差异列自动计算（=金额-发票金额），差异>0时红色高亮。支持行级抽凭验证和附件OCR识别。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>增加检查表 H4-4</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H4-4-addition')">💬</el-button>
      </div>
    </div>

    <!-- 19列表格 -->
    <el-table :data="rows" border stripe size="small" class="check-table" row-key="rowId"
      :row-class-name="getRowClassName">
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
      <el-table-column label="物资名称" min-width="100" fixed>
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.name" size="small"
            @change="updateCell(row.rowId, 'name', $event)" />
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="规格型号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.spec" size="small"
            @change="updateCell(row.rowId, 'spec', $event)" />
          <span v-else>{{ row.spec }}</span>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="70" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.quantity" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'quantity', $event)" />
          <span v-else>{{ row.quantity || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单价" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.unitPrice" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'unitPrice', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.unitPrice) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.amount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'amount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="供应商" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.supplier" size="small"
            @change="updateCell(row.rowId, 'supplier', $event)" />
          <span v-else>{{ row.supplier }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同编号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.contractNo" size="small"
            @change="updateCell(row.rowId, 'contractNo', $event)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入库日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.inboundDate" size="small" placeholder="YYYY-MM-DD"
            @change="updateCell(row.rowId, 'inboundDate', $event)" />
          <span v-else>{{ row.inboundDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入库单号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.inboundNo" size="small"
            @change="updateCell(row.rowId, 'inboundNo', $event)" />
          <span v-else>{{ row.inboundNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发票号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.invoiceNo" size="small"
            @change="updateCell(row.rowId, 'invoiceNo', $event)" />
          <span v-else>{{ row.invoiceNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发票金额" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.invoiceAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'invoiceAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.invoiceAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'diff-error': Math.abs(row.diff) > 0 }"
            title="差异 = 金额 - 发票金额">{{ fmtAmt(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="验收人" width="80">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.inspector" size="small"
            @change="updateCell(row.rowId, 'inspector', $event)" />
          <span v-else>{{ row.inspector }}</span>
        </template>
      </el-table-column>
      <el-table-column label="抽凭" width="60" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="handleVoucherSampling(row)">抽凭</el-button>
        </template>
      </el-table-column>
      <el-table-column label="附件" width="50" align="center">
        <template #default="{ row }">
          <el-button size="small" link @click="handleAttachment(row)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column label="核查结论" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.conclusion" size="small"
            @change="updateCell(row.rowId, 'conclusion', $event)" />
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
            @change="updateCell(row.rowId, 'remark', $event)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.refIndex" size="small"
            @change="updateCell(row.rowId, 'refIndex', $event)" />
          <span v-else>{{ row.refIndex }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="40" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 统计摘要 -->
    <div class="stats-bar">
      <span class="stats-item">已检查 <strong>{{ stats.checkedCount }}</strong> 笔</span>
      <span class="stats-item">总金额 <strong>{{ fmtAmt(stats.totalAmount) }}</strong></span>
      <span class="stats-item" :class="{ 'stats-warn': stats.diffCount > 0 }">
        差异笔数 <strong>{{ stats.diffCount }}</strong>
      </span>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加检查行</el-button>
      <el-dropdown trigger="click" @command="handleImportExport" style="margin-left: 8px">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>逐项核对本期新增物资：入库单/发票/合同三方一致</li>
        <li>差异=金额-发票金额，差异>0时红色高亮提示核查</li>
        <li>📎附件列可上传扫描件进行OCR自动识别填入</li>
        <li>"抽凭"按钮打开凭证抽样引擎，检查原始凭证</li>
        <li>底部统计：已检查笔数/总金额/差异笔数一目了然</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabAdditionCheck.vue — H4-4 增加检查表
 *
 * 19列: 序号|物资名称|规格|数量|单价|金额|供应商|合同编号|入库日期|入库单号|
 *       发票号|发票金额|差异|验收人|抽凭|附件|核查结论|备注|索引
 * 差异列: auto-calculated, red highlight when |diff| > 0
 * 底部: 统计摘要 (已检查/总金额/差异笔数)
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.5
 * Requirements: 5.1-5.7
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4AdditionCheck, type H4AdditionCheckRow } from '../../composables/useH4AdditionCheck'
import { useH4ImportExport } from '../../composables/useH4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, stats,
  addRow, deleteRow, updateCell, save,
} = useH4AdditionCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
})

const importExport = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-4-note', { item_id: 'H4-4-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: H4AdditionCheckRow }) {
  if (Math.abs(row.diff) > 0.01) return 'diff-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

function handleVoucherSampling(row: H4AdditionCheckRow) {
  console.log('[H4-4] Voucher sampling for:', row.name)
  // GtVoucherSamplingEngine dialog integration
}

function handleAttachment(row: H4AdditionCheckRow) {
  console.log('[H4-4] Attachment OCR for:', row.name)
  // 📎 upload + OCR integration (contract-ocr endpoint)
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H4-4')
  else if (command === 'export-data') importExport.exportData('H4-4')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-4', file)
    }
    input.click()
  }
}

function handleAiGenerate() {
  console.log('[H4-4] AI generate')
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-addition-check { padding: 16px; font-size: 13px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.check-table { font-size: 13px; margin-bottom: 12px; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
}
.diff-error { color: #f56c6c; font-weight: 600; border-bottom-color: #f56c6c; }

:deep(.diff-row) { background-color: #fef0f0 !important; }

.stats-bar {
  display: flex; align-items: center; gap: 24px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 13px;
}
.stats-item { color: var(--el-text-color-secondary); }
.stats-item strong { color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
.stats-warn strong { color: #f56c6c; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
