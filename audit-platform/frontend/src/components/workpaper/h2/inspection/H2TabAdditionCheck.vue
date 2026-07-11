<template>
  <div class="h2-tab-addition-check">
    <!-- 区域1: 抽样参数 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>抽样参数</span>
          <div class="section-header-actions">
            <el-button size="small" @click="handleSampling">抽凭引擎</el-button>
          </div>
        </div>
      </template>
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">总体金额：</span>
          <el-input-number v-model="state.samplingParams.value.populationAmount" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('populationAmount', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">重要性水平：</span>
          <el-input-number v-model="state.samplingParams.value.materialityLevel" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('materialityLevel', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法：</span>
          <el-select v-model="state.samplingParams.value.samplingMethod" size="small" :disabled="isReadonly"
            @change="onParamChange('samplingMethod', $event)">
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随机抽样" value="随机抽样" />
            <el-option label="判断抽样" value="判断抽样" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">样本量：</span>
          <span class="param-value">{{ state.samplingParams.value.sampleSize ?? '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 区域2: 增加检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>本期增加检查明细（H2-8）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-8')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="name" label="工程项目" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="费用类别" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'category', $event)">
              <el-option label="材料" value="材料" />
              <el-option label="人工" value="人工" />
              <el-option label="机械" value="机械" />
              <el-option label="利息" value="利息" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="invoiceNo" label="凭证/发票号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.invoiceNo" size="small"
              @change="onCellChange(row.rowId, 'invoiceNo', $event)" />
            <span v-else>{{ row.invoiceNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="supplier" label="供应商" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supplier" size="small"
              @change="onCellChange(row.rowId, 'supplier', $event)" />
            <span v-else>{{ row.supplier || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractNo" label="合同编号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="onCellChange(row.rowId, 'contractNo', $event)" />
            <span v-else>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">
            <el-button size="small" link @click="handleOcr(row.rowId)" :disabled="isReadonly">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.auditConclusion" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'auditConclusion', $event)">
              <el-option label="无异常" value="无异常" />
              <el-option label="存疑" value="存疑" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <el-tag v-else :type="row.auditConclusion === '无异常' ? 'success' : 'warning'" size="small">
              {{ row.auditConclusion || '待检' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-line">
        样本合计: <strong>{{ fmtAmt(state.amountTotal.value) }}</strong>
        <span style="margin-left:16px">覆盖率: {{ state.actualCoverageRate.value?.toFixed(1) ?? '-' }}%</span>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>先使用"抽凭引擎"确定样本，再逐项检查</li>
        <li>📎附件列：上传合同/发票后OCR自动识别填入关键字段</li>
        <li>固定列(项目/费用类型)不跟随横滚，证据列可横滚</li>
        <li>检查结论"需调整"的项目应在H2-3录入调整分录</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1604 在建工程-增加）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['1604']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAdditionCheck.vue — H2-8 增加检查
 * 双区域(抽样参数+明细) + 固定列+滚动列 + OCR📎 + 抽凭
 * Spec: Task 4.10 + 6.4 + 6.5 | Requirements: 9.1-9.2, 9.5-9.8
 */
import { ref, inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2AdditionCheck } from '../../composables/useH2AdditionCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const showSamplingDialog = ref(false)

const state = useH2AdditionCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const isReadonly = computed(() => props.isReadonly)

function onParamChange(field: string, value: any) {
  state.updateSamplingParams({ [field]: value } as any)
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

/** 打开抽凭引擎 dialog */
function handleSampling() {
  showSamplingDialog.value = true
}

/** 抽凭引擎完成后回调：将样本行填入检查表 */
function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    state.addRow()
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (lastRow) {
      if (s.amount != null) lastRow.amount = Number(s.amount) || 0
      if (s.summary || s.description) lastRow.name = s.summary || s.description
      if (s.voucherNo) lastRow.contractNo = s.voucherNo
      if (s.date) lastRow.date = s.date
      lastRow.samplingStatus = '待检查'
    }
  }
  state.fillSamplingResults(
    samples.map((s, i) => ({
      rowId: state.rows.value[state.rows.value.length - samples.length + i]?.rowId ?? '',
      status: '待检查',
    })),
  )
}

/** 行级 OCR：📎上传→POST contract-ocr→ElMessageBox确认→merge字段 */
function handleOcr(rowId: string) {
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
      await ElMessageBox.confirm(
        `识别结果：\n${preview}\n\n确认填入？`,
        'OCR识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消' },
      )
      // merge fields into row via composable
      state.mergeOcrResult(rowId, fields)
    } catch { /* user cancelled or request failed */ }
  }
  input.click()
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handleAiGenerate() {
  console.log('AI generate H2-8')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-addition-check { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-weight: 500; min-width: 90px; }
.param-value { font-weight: 600; color: var(--el-color-primary); }
.check-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.summary-line { padding: 12px 0; font-size: 13px; border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
