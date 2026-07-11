<template>
  <div class="h8-tab-recoverable">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS8可收回金额测试：可收回金额=max(公允价值-处置费用, 资产预计未来现金流量现值)。本表采用DCF法计算现值，折现率取增量借款利率。90行28列DCF模型。</p>
    </div>

    <!-- 索引 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-11" />
    </div>

    <!-- DCF参数卡片 -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>DCF测试参数（H8-11，90行28列12公式）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'recoverable')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'recoverable')">复核</el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" size="small" label-position="left" :disabled="isReadonly">
        <el-form-item label="折现率(%)">
          <el-input-number v-model="dcfParams.discountRate" :controls="false" :precision="4" :step="0.01"
            @change="handleParamChange" />
        </el-form-item>
        <el-form-item label="预测期（年）">
          <el-input-number v-model="dcfParams.forecastYears" :controls="false" :min="1" :max="30"
            @change="handleParamChange" />
        </el-form-item>
        <el-form-item label="年租金节省">
          <el-input-number v-model="dcfParams.annualCashFlow" :controls="false"
            @change="handleParamChange" />
        </el-form-item>
        <el-form-item label="残值/期末价值">
          <el-input-number v-model="dcfParams.terminalValue" :controls="false"
            @change="handleParamChange" />
        </el-form-item>
      </el-form>

      <!-- 计算结果 -->
      <div class="dcf-result" v-if="dcfParams.annualCashFlow > 0">
        <div class="result-row">
          <div class="result-item">
            <span class="result-label">现金流量现值</span>
            <span class="result-value">{{ fmtAmt(presentValue) }} 元</span>
          </div>
          <div class="result-item">
            <span class="result-label">残值现值</span>
            <span class="result-value">{{ fmtAmt(terminalPV) }} 元</span>
          </div>
          <div class="result-item">
            <span class="result-label">可收回金额</span>
            <span class="result-value highlight">{{ fmtAmt(recoverableAmount) }} 元</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>DCF现金流量折现明细（90行28列12公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'可收回金额测试表H8-11'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载，显示DCF参数摘要">
            <template #image><span style="font-size:40px">📈</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>DCF折现率取增量借款利率（与H8-6一致）</li>
        <li>现金流量=使用期内因持有该使用权资产节省的租金</li>
        <li>预测期不超过剩余租赁期</li>
        <li>可收回金额=max(公允价值-处置费用, DCF现值)</li>
        <li>如可收回金额≥账面价值，则无需计提减值</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabRecoverable.vue — H8-11 可收回金额测试表（DCF，OO渲染）
 * 90行28列12公式
 * Spec: Task 4.7 | Requirements: 7.1-7.2
 */
import { ref, reactive, computed, defineAsyncComponent } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() =>
  import('../../GtOnlyOfficeSheet.vue').catch(() => ({ template: '<div>OO不可用</div>' })),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const showOO = ref(true)

const dcfParams = reactive({
  discountRate: 0.05,
  forecastYears: 5,
  annualCashFlow: 0,
  terminalValue: 0,
})

// 从allResponses恢复
const stored = props.allResponses.get('H8-11-params')
if (stored) {
  try {
    const parsed = JSON.parse(stored.remark ?? stored.conclusion ?? '{}')
    Object.assign(dcfParams, parsed)
  } catch { /* ignore */ }
}

/** 简化DCF计算 - 年金现值 */
const presentValue = computed(() => {
  const r = dcfParams.discountRate
  const n = dcfParams.forecastYears
  const cf = dcfParams.annualCashFlow
  if (r <= 0 || n <= 0 || cf <= 0) return 0
  return cf * (1 - Math.pow(1 + r, -n)) / r
})

/** 残值现值 */
const terminalPV = computed(() => {
  const r = dcfParams.discountRate
  const n = dcfParams.forecastYears
  const tv = dcfParams.terminalValue
  if (r <= 0 || n <= 0) return 0
  return tv / Math.pow(1 + r, n)
})

/** 可收回金额 */
const recoverableAmount = computed(() => presentValue.value + terminalPV.value)

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleParamChange() {
  emit('save', 'H8-11-params', JSON.stringify(dcfParams))
}
</script>

<style scoped>
.h8-tab-recoverable { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.params-card { margin-bottom: 16px; }
.dcf-result { margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--el-border-color); }
.result-row { display: flex; gap: 32px; flex-wrap: wrap; }
.result-item { display: flex; flex-direction: column; gap: 4px; }
.result-label { font-size: 12px; color: var(--el-text-color-secondary); }
.result-value { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.highlight { color: #059669; }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 400px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
