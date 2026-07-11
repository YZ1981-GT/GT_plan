<template>
  <div class="h8-tab-measurement-annual">
    <!-- CAS21公式说明Banner -->
    <div class="formula-banner">
      <div class="formula-icon">📐</div>
      <div class="formula-content">
        <div class="formula-title">CAS21初始计量公式</div>
        <div class="formula-text">使用权资产 = 租赁负债初始确认(H9) + 初始直接费用 - 租赁激励</div>
        <div class="formula-result" v-if="initialMeasurement > 0">
          计算结果：{{ formulaText }}
        </div>
      </div>
    </div>

    <!-- 索引 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-6" />
      <el-tag size="small" type="info">按年计量</el-tag>
    </div>

    <!-- 计量参数（上方参数区） -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>计量参数</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'measurement-annual')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'measurement-annual')">复核</el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" size="small" label-position="left" :disabled="isReadonly">
        <el-form-item label="H9租赁负债初始确认">
          <el-input-number
            :model-value="measurementParams.leaseLiabilityInitial"
            :controls="false"
            @change="(v: number | undefined) => handleParamChange('leaseLiabilityInitial', v)"
          />
        </el-form-item>
        <el-form-item label="初始直接费用">
          <el-input-number
            :model-value="measurementParams.directCost"
            :controls="false"
            @change="(v: number | undefined) => handleParamChange('directCost', v)"
          />
        </el-form-item>
        <el-form-item label="租赁激励">
          <el-input-number
            :model-value="measurementParams.incentive"
            :controls="false"
            @change="(v: number | undefined) => handleParamChange('incentive', v)"
          />
        </el-form-item>
        <el-form-item label="折现率(%)">
          <el-input-number
            :model-value="measurementParams.discountRate"
            :controls="false" :precision="4" :step="0.01"
            @change="(v: number | undefined) => handleParamChange('discountRate', v)"
          />
        </el-form-item>
        <el-form-item label="租赁期（月）">
          <el-input-number
            :model-value="measurementParams.leaseTermMonths"
            :controls="false" :min="0"
            @change="(v: number | undefined) => handleParamChange('leaseTermMonths', v)"
          />
        </el-form-item>
        <el-form-item label="每期租金">
          <el-input-number
            :model-value="measurementParams.rentalPerPeriod"
            :controls="false"
            @change="(v: number | undefined) => handleParamChange('rentalPerPeriod', v)"
          />
        </el-form-item>
        <el-form-item label="付款方式">
          <el-radio-group
            :model-value="measurementParams.paymentTiming"
            @change="(v: string | number | boolean | undefined) => handleParamChange('paymentTiming', v)"
          >
            <el-radio-button value="期初">期初付</el-radio-button>
            <el-radio-button value="期末">期末付</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 初始计量结果卡片 -->
    <el-card shadow="never" class="result-card">
      <div class="result-row">
        <div class="result-item">
          <span class="result-label">使用权资产初始确认</span>
          <span class="result-value">{{ fmtAmt(initialMeasurement) }}元</span>
        </div>
        <div class="result-item">
          <span class="result-label">年化租金</span>
          <span class="result-value">{{ fmtAmt(annualRental) }}元</span>
        </div>
        <div class="result-item">
          <span class="result-label">租赁期</span>
          <span class="result-value">{{ measurementParams.leaseTermMonths }}月（≈{{ Math.ceil(measurementParams.leaseTermMonths / 12) }}年）</span>
        </div>
      </div>
    </el-card>

    <!-- OO渲染区域（59行13列按年汇总） -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>按年计量明细（59行13列9公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'使用权资产初始及后续计量H8-6'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载，显示参数区和计算结果">
            <template #image><span style="font-size:40px">📊</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>按年计量适用于简单租赁（租赁期≤5年、固定租金）</li>
        <li>如租赁期超过5年或租金递增，建议切换"按月计量"查看更细粒度</li>
        <li>折现率：增量借款利率 / 合同内含利率（优先）</li>
        <li>H9联动：初始计量中的租赁负债部分应等于H9-1初始确认金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabMeasurementAnnual.vue — H8-6(A) 按年计量（OO渲染+CAS21公式说明）
 * 59行13列9公式，按年汇总
 * Spec: Task 4.5 | Requirements: 5.1-5.6
 */
import { ref, toRef, defineAsyncComponent } from 'vue'
import { useH8Measurement, type H8MeasurementParams } from '../../composables/useH8Measurement'
import GtIndexChip from '../../GtIndexChip.vue'

// GtOnlyOfficeSheet可能尚未注册为全局组件，做防御性定义
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

const {
  measurementParams, initialMeasurement, formulaText, annualRental,
  updateParam,
} = useH8Measurement({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleParamChange(field: keyof H8MeasurementParams, value: any) {
  updateParam(field, value)
}
</script>

<style scoped>
.h8-tab-measurement-annual { padding: 16px; font-size: 13px; }

.formula-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border: 1px solid #6ee7b7; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
}
.formula-icon { font-size: 28px; }
.formula-content { flex: 1; }
.formula-title { font-weight: 700; font-size: 14px; color: #065f46; margin-bottom: 4px; }
.formula-text { font-size: 13px; color: #047857; }
.formula-result { font-size: 12px; color: #059669; margin-top: 4px; }

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.params-card { margin-bottom: 16px; }

.result-card { margin-bottom: 16px; }
.result-row { display: flex; gap: 32px; flex-wrap: wrap; }
.result-item { display: flex; flex-direction: column; gap: 4px; }
.result-label { font-size: 12px; color: var(--el-text-color-secondary); }
.result-value { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 400px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
