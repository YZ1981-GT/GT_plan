<template>
  <div class="h2-tab-decrease-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：对本期在建工程减少（报废/毁损/转出等）抽样检查，核实减少的真实性与损失计量准确性，验证审批文件、残值与保险理赔的完整性。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-9" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
      </div>
    </div>

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

    <!-- 区域2: 减少检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>本期减少检查明细（H2-9）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-9')">💬</el-button>
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
        <el-table-column prop="decreaseDate" label="减少日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.decreaseDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'decreaseDate', $event)" />
            <span v-else>{{ row.decreaseDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decreaseReason" label="减少原因" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.decreaseReason" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'decreaseReason', $event)">
              <el-option label="报废" value="报废" />
              <el-option label="毁损" value="毁损" />
              <el-option label="转出" value="转出" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.decreaseReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalValue" label="原账面值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalValue" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'originalValue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.originalValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="residualValue" label="残值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.residualValue" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'residualValue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.residualValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失金额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=原账面值-残值">{{ fmtAmt(row.lossAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="insuranceClaim" label="保险理赔" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.insuranceClaim" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'insuranceClaim', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.insuranceClaim) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净损失" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=损失金额-保险理赔">{{ fmtAmt(row.netLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small"
              @change="onCellChange(row.rowId, 'approvalDoc', $event)" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalMethod" label="处置方式" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.disposalMethod" size="small"
              @change="onCellChange(row.rowId, 'disposalMethod', $event)" />
            <span v-else>{{ row.disposalMethod || '-' }}</span>
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
        原账面合计: <strong>{{ fmtAmt(state.originalTotal.value) }}</strong>
        <span style="margin-left:16px">损失合计: <strong>{{ fmtAmt(state.lossTotal.value) }}</strong></span>
        <span style="margin-left:16px">净损失合计: <strong>{{ fmtAmt(state.netLossTotal.value) }}</strong></span>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述抽样与逐项检查（减少原因/审批/损失计量/保险理赔）情况及发现的异常。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：如所抽减少真实、损失计量准确、审批齐全，未见异常；或说明需调整事项（→ H2-3 调整分录）。" :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>减少原因：报废/毁损/转出/其他</li>
        <li>损失金额=原账面值-残值；净损失=损失金额-保险理赔（公式列自动计算）</li>
        <li>报废/毁损需附审批文件(董事会决议等)</li>
        <li>先使用"抽凭引擎"确定样本，再逐项检查</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1604 在建工程-减少）" width="720px"
      :close-on-click-modal="false" destroy-on-close>
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
 * H2TabDecreaseCheck.vue — H2-9 减少检查
 * 双区域(抽样参数+明细) + 损失/净损失公式 + 抽凭引擎
 * Spec: Task 4.11 | Requirements: 9.3-9.5, 9.7-9.8
 */
import { ref, inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2DecreaseCheck } from '../../composables/useH2DecreaseCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const showSamplingDialog = ref(false)

const state = useH2DecreaseCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
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
      if (s.amount != null) lastRow.originalValue = Number(s.amount) || 0
      if (s.summary || s.description) lastRow.name = s.summary || s.description
      if (s.date) lastRow.decreaseDate = s.date
      lastRow.samplingStatus = '待检查'
    }
  }
  state.fillSamplingResults(
    samples.map((_s, i) => ({
      rowId: state.rows.value[state.rows.value.length - samples.length + i]?.rowId ?? '',
      status: '待检查',
    })),
  )
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
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
.h2-tab-decrease-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-weight: 500; min-width: 90px; }
.param-value { font-weight: 600; color: var(--el-color-primary); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.summary-line { padding: 12px 0; font-size: var(--wp-font-size, 13px); border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
