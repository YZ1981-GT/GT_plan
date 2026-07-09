<template>
  <div class="h2-tab-decrease-check">
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
          <el-input-number v-model="state.params.value.totalAmount" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('totalAmount', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">重要性水平：</span>
          <el-input-number v-model="state.params.value.materiality" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('materiality', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法：</span>
          <el-select v-model="state.params.value.method" size="small" :disabled="isReadonly"
            @change="onParamChange('method', $event)">
            <el-option label="货币单位抽样" value="MUS" />
            <el-option label="随机抽样" value="RANDOM" />
            <el-option label="判断抽样" value="JUDGMENTAL" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">样本量：</span>
          <span class="param-value">{{ state.params.value.sampleSize ?? '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 区域2: 减少检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>本期减少检查明细（H2-9）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-9')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="projectName" label="工程项目" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectName" size="small"
              @change="onCellChange(row.rowId, 'projectName', $event)" />
            <span v-else>{{ row.projectName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decreaseType" label="减少类型" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.decreaseType" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'decreaseType', $event)">
              <el-option label="转固" value="转固" />
              <el-option label="报废" value="报废" />
              <el-option label="出售" value="出售" />
              <el-option label="损失" value="损失" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.decreaseType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lossCategory" label="损失分类" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && (row.decreaseType === '报废' || row.decreaseType === '损失')"
              v-model="row.lossCategory" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'lossCategory', $event)">
              <el-option label="正常损耗" value="正常损耗" />
              <el-option label="管理不善" value="管理不善" />
              <el-option label="自然灾害" value="自然灾害" />
              <el-option label="技术淘汰" value="技术淘汰" />
            </el-select>
            <span v-else>{{ row.lossCategory || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证编号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
              @change="onCellChange(row.rowId, 'voucherNo', $event)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="减少金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small"
              @change="onCellChange(row.rowId, 'approvalDoc', $event)" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkResult" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'checkResult', $event)">
              <el-option label="无异常" value="无异常" />
              <el-option label="存疑" value="存疑" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <el-tag v-else :type="row.checkResult === '无异常' ? 'success' : 'warning'" size="small">
              {{ row.checkResult || '待检' }}
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
        样本合计: <strong>{{ fmtAmt(state.sampleTotal.value) }}</strong>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>减少类型：转固/报废/出售/损失/其他</li>
        <li>损失分类仅在"报废"或"损失"时显示</li>
        <li>报废/损失需附审批文件(董事会决议等)</li>
        <li>先使用"抽凭引擎"确定样本，再逐项检查</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDecreaseCheck.vue — H2-9 减少检查
 * 双区域(抽样参数+明细) + 损失分类 + 抽凭
 * Spec: Task 4.11 | Requirements: 9.3-9.5, 9.7-9.8
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2DecreaseCheck } from '../../composables/useH2DecreaseCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2DecreaseCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

function onParamChange(field: string, value: any) {
  state.updateParam(field, value)
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function handleSampling() {
  state.openSamplingEngine()
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handleAiGenerate() {
  console.log('AI generate H2-9')
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
.h2-tab-decrease-check { padding: 16px; font-size: 13px; }
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
