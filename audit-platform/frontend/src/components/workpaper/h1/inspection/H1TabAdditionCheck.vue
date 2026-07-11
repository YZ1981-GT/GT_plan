<template>
  <div class="h1-tab-addition-check">
    <div class="methodology-context">
      <p>对本期新增固定资产进行实质性测试。通过抽样选取增加样本，核对原始凭证（发票/合同/验收单），验证入账金额、时点、分类的正确性。</p>
    </div>

    <!-- 抽样参数 -->
    <el-card shadow="never" class="sampling-card">
      <template #header>
        <div class="section-title">
          <span>抽样参数</span>
          <el-button size="small" type="primary" @click="handleSampling" :disabled="isReadonly">🎲 抽凭引擎</el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="总体金额">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</el-descriptions-item>
        <el-descriptions-item label="样本量">{{ state.samplingParams.value.sampleSize }}</el-descriptions-item>
        <el-descriptions-item label="覆盖率">{{ state.summary.value.coverageRate.toFixed(1) }}%</el-descriptions-item>
        <el-descriptions-item label="抽样方法">{{ state.samplingParams.value.samplingMethod || '待确定' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 检查明细表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>增加检查明细（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-7')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="450" class="check-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="入账金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entryDate" label="入账日期" width="110" />
        <el-table-column prop="invoiceNo" label="发票号" width="120" />
        <el-table-column prop="contractNo" label="合同号" width="120" />
        <el-table-column prop="supplier" label="供应商" width="120" />
        <el-table-column prop="checkResult" label="检查结果" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkResult" size="small" style="width:70px">
              <el-option label="OK" value="OK" />
              <el-option label="异常" value="ERR" />
            </el-select>
            <el-tag v-else :type="row.checkResult === 'OK' ? 'success' : 'danger'" size="small">{{ row.checkResult }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleOcr(row)" :disabled="isReadonly">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>样本金额合计: <b class="amount-cell">{{ fmtAmt(state.summary.value.checkedAmount) }}</b></span>
        <span>异常: <b :class="{ 'error-amount': state.summary.value.anomalyCount > 0 }">{{ state.summary.value.anomalyCount }}</b> 项</span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>📎 点击上传发票/合同→OCR识别→确认后自动填入金额/日期/发票号</li>
        <li>抽凭引擎可按MUS/随机/系统抽样自动选取样本</li>
        <li>检查要点：金额一致性/时点截止/分类正确/资本化条件</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1601 固定资产-增加）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['1601']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1AdditionCheck } from '../../composables/useH1AdditionCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const showSamplingDialog = ref(false)

const state = useH1AdditionCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增检查项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}

function handleSampling() {
  showSamplingDialog.value = true
}

/** 抽凭引擎完成后回调：将样本行填入检查表 */
function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    state.addRow(s.summary || s.description || '抽样项')
    // 将最后添加的行填入抽凭信息
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (lastRow) {
      lastRow.amount = s.amount ?? 0
      lastRow.entryDate = s.date ?? s.entryDate ?? ''
      lastRow.invoiceNo = s.voucherNo ?? ''
    }
  }
}

/** 行级 OCR：📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge字段 */
async function handleOcr(row: any) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = data?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`识别结果：\n${preview}\n\n确认填入？`, 'OCR识别结果', { confirmButtonText: '填入', cancelButtonText: '取消' })
      // merge fields into row
      if (fields.amount) row.amount = Number(fields.amount) || row.amount
      if (fields.date || fields.entryDate) row.entryDate = fields.date || fields.entryDate
      if (fields.invoiceNo || fields.invoice_no) row.invoiceNo = fields.invoiceNo || fields.invoice_no
      if (fields.contractNo || fields.contract_no) row.contractNo = fields.contractNo || fields.contract_no
      if (fields.supplier) row.supplier = fields.supplier
    } catch { /* user cancelled or request failed */ }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-addition-check { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.sampling-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
