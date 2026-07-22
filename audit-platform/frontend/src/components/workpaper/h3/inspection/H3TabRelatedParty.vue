<template>
  <div class="h3-tab-related-party">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核查投资性房地产相关的关联方交易（出租/购入/处置/转换），关注定价公允性与商业实质。</p>
        <p>2. 差异率 =（交易金额 − 市场价参考）/ 市场价 × 100%，&gt;10% 红色高亮需重点关注与解释。</p>
        <p>3. 核对定价方式、审批文件与市场价依据；出租类交易应与 H3-14 租金收入测算表交叉验证。</p>
        <p>4. 关联交易结果应与附注关联方披露一致（CAS36）；支持性文档索引号记入备注列。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <span class="objective-title">一、审计目标</span>
      </template>
      <ol class="objective-list">
        <li>完整性：所有应披露的投资性房地产关联方交易均已识别并记录。</li>
        <li>发生：已记录的关联交易真实发生，与被审计单位有关。</li>
        <li>准确性：关联交易金额及会计处理正确，定价公允、商业实质充分。</li>
        <li>列报与披露：关联方关系及交易在财务报表附注中恰当列报和披露。</li>
        <li>截止：关联交易已记录在正确的会计期间。</li>
      </ol>
    </el-alert>

    <!-- 审计过程 -->
    <div class="methodology-context">
      <p class="procedure-label">二、审计过程</p>
      <p>
        1. 对于合并范围外关联交易，核对合同、发票等有关文件，了解交易目的、价格和条件，确认关联交易是否真实、公允。
      </p>
      <p>
        编制思路：识别关联方及关系 → 逐笔登记交易类型与金额 → 获取定价政策与市场价参考 →
        计算差异率并评估公允性 → 检查审批合规性 → 与 H3-14/附注勾稽 → 形成审计结论。
      </p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-13" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 笔</el-tag>
      <el-tag v-if="highDiffRows.length" size="small" type="danger">
        差异率&gt;10% {{ highDiffRows.length }} 笔
      </el-tag>
      <el-tag v-if="issueRows.length" size="small" type="warning">
        需关注 {{ issueRows.length }} 笔
      </el-tag>
      <el-tag v-if="rentalRows.length" size="small">
        出租类 {{ rentalRows.length }} 笔
      </el-tag>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增关联交易</el-button>
      <el-button
        v-if="rentalRows.length"
        size="small"
        @click="emit('navigate-sheet', 'H3-14 租金收入')"
      >
        跳转 H3-14 勾稽
      </el-button>
      <el-button size="small" :disabled="isReadonly || !rows.length" @click="onDraftNote">
        生成审计说明
      </el-button>
      <el-dropdown size="small" class="export-dropdown" @command="handleExportCommand">
        <el-button size="small" :loading="importing">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <!-- 11列关联交易表 -->
    <el-table
      :data="rows"
      border
      size="small"
      class="audit-table"
      :row-class-name="getRowClass"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
      <el-table-column prop="relatedParty" label="关联方" min-width="120" fixed>
        <template #default="{ row, $index }">
          <el-input
            v-model="row.relatedParty"
            size="small"
            placeholder="关联单位名称"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="relationship" label="关联关系" min-width="130">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.relationship"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="选择关联关系"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          >
            <el-option
              v-for="opt in relationshipOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="transType" label="交易类型" width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.transType" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option v-for="t in transTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input
            v-model.number="row.amount"
            size="small"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="pricingMethod" label="定价政策" min-width="110">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.pricingMethod"
            size="small"
            placeholder="如：市场价/协议价"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="marketRef" label="市场价参考" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input
            v-model.number="row.marketRef"
            size="small"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="差异率" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'text-danger': Math.abs(row.diffRate) > 10 }"
            title="(金额-市场价)/市场价×100%"
          >
            {{ row.marketRef ? row.diffRate.toFixed(1) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="approvalDoc" label="审批文件" width="80" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.approvalDoc" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="是否存在异常" min-width="110">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="无异常" value="无异常" />
            <el-option label="需关注" value="需关注" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注/索引号" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.remark"
            size="small"
            placeholder="支持性文档索引"
            :disabled="isReadonly"
            @change="onCellChange($index, row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="96" align="center" fixed="right">
        <template #default="{ row, $index }">
          <el-button
            type="primary"
            link
            size="small"
            :disabled="isReadonly"
            title="上传租赁/交易合同 OCR 识别"
            @click="handleContractOcr(row, $index)"
          >
            📎OCR
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly"
            @click="removeRow($index)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-13')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-13')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：关联方识别、定价公允性核查、与H3-14/附注勾稽及异常事项。"
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>四、审计结论</span></div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="A、关联交易完整披露、定价公允。B、除下列事项外未见异常。C、存在非公允关联交易，需关注并披露。"
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRelatedParty.vue — H3-13 关联交易
 * el-table 11列+差异率>10%红色+合计行
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH3RelatedParty,
  RELATED_PARTY_RELATIONSHIPS,
  TRANS_TYPES,
} from '../../composables/useH3RelatedParty'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport } from '../../composables/useH3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel?: 'cost' | 'fair_value'
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref(props.measurementModel ?? 'cost') as any,
})

const {
  rows, addRow, removeRow, updateRow, totalAmount,
  highDiffRows, issueRows, rentalRows, draftAuditNote, loadRows,
} = useH3RelatedParty({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const relationshipOptions = RELATED_PARTY_RELATIONSHIPS
const transTypes = TRANS_TYPES

const measurementModelRef = computed(() => props.measurementModel ?? 'cost')
const { importing, exportTemplate, exportData, importData } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelRef as any,
  onImported: () => loadRows(),
})

const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────
const NOTE_KEY = 'H3-13-audit-note'
const CONCLUSION_KEY = 'H3-13-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onCellChange(index: number, row: any) { updateRow(index, row) }

/** 关联交易/租赁合同 OCR：上传 → 识别 → 确认 → 回填对方/金额/定价依据 */
async function handleContractOcr(row: any, index: number) {
  if (props.isReadonly) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const loading = ElMessage({ message: '正在识别合同…', type: 'info', duration: 0 })
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h3/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      loading.close()
      const data = res.data?.data ?? res.data
      const f = data?.extracted_fields ?? {}
      const amt = Number(data?.amount) || Number(f.contractAmount) || Number(f.annualRent) || (Number(f.monthlyRent) || 0) * 12
      await ElMessageBox.confirm(
        `识别结果（置信度 ${(Number(data?.confidence) * 100).toFixed(0)}%）：\n` +
          `承租方：${f.counterparty || '-'}\n出租方：${f.lessor || '-'}\n` +
          `标的：${f.assetName || '-'}\n金额：${amt || '-'}\n` +
          `租期：${f.leaseStart || '-'} ~ ${f.leaseEnd || '-'}\n定价依据：${f.pricingBasis || '-'}\n\n确认填入第 ${index + 1} 行？`,
        '合同 OCR 识别结果',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      if (f.counterparty && !row.relatedParty) row.relatedParty = f.counterparty
      if (amt > 0) row.amount = amt
      if (f.pricingBasis && !row.pricingMethod) row.pricingMethod = f.pricingBasis
      if (!row.transType && (f.monthlyRent || f.annualRent || f.leaseStart)) row.transType = '出租'
      const idxTag = f.contractNo ? `合同:${f.contractNo}` : ''
      if (idxTag) row.remark = [row.remark, idxTag].filter(Boolean).join('；')
      updateRow(index, row)
      ElMessage.success('已填入识别结果，请核对定价公允性')
    } catch (err: any) {
      loading.close()
      if (err === 'cancel' || String(err).includes('cancel')) return
      console.warn('[H3-13 contract OCR]', err)
      ElMessage.error('识别失败，请重试或手工录入')
    }
  }
  input.click()
}

function onDraftNote() {
  if (props.isReadonly) return
  const draft = draftAuditNote()
  saveAuditNote(draft)
}

function getRowClass({ row }: { row: any }): string {
  if (Math.abs(row.diffRate) > 10) return 'row-danger'
  if (row.conclusion === '需关注') return 'row-warn'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (col.property === 'amount') return fmtNum(totalAmount.value)
    return ''
  })
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H3-13')
  else if (cmd === 'export-data') await exportData('H3-13')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) await importData('H3-13', file)
  input.value = ''
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.objective-title { font-weight: 600; }
.objective-list { margin: 6px 0 0; padding-left: 20px; line-height: 1.7; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
  color: #606266;
}
.methodology-context p { margin: 4px 0; }
.procedure-label { font-weight: 600; color: #303133; margin-bottom: 4px !important; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.row-warn) { background-color: #fdf6ec !important; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
