<template>
  <div class="h8-tab-measurement-annual">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实使用权资产初始计量（按年）的准确性，确认初始确认=H9租赁负债初始确认+初始直接费用-租赁激励（CAS21）。" />

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

    <H8LeaseTermSyncBar
      :options="h85TermOptions"
      :mismatch="h85TermMismatch"
      :source-contract="measurementParams.leaseTermSourceContract"
      :synced-from="measurementParams.leaseTermSyncedFrom"
      :lease-term-months="measurementParams.leaseTermMonths"
      :is-readonly="isReadonly"
      @pull="handlePullH85"
      @navigate="(s) => emit('navigate-sheet', s)"
    />

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
          <span class="result-value">{{ measurementParams.leaseTermMonths }}月（≈{{ Math.ceil(measurementParams.leaseTermMonths / 12) || 0 }}年）</span>
        </div>
      </div>
    </el-card>

    <!-- HTML 摊销表（结构化主路径） -->
    <H8AmortSchedulePanel :schedule="amortSchedule" mode="annual" />

    <!-- OO 兜底（可选展开） -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>OnlyOffice 源表（兜底精编）</span>
          <el-button size="small" link type="primary" @click="showOO = !showOO">
            {{ showOO ? '收起' : '展开' }}
          </el-button>
        </div>
      </template>
      <div v-if="showOO" class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId"
          :wp-id="wpId"
          :sheet-name="'使用权资产 租赁负债初始及后续计量（按年）H8-6'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
      </div>
      <el-empty v-else description="已收起 OnlyOffice；上方 HTML 摊销表可满足日常编制" :image-size="48" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="请输入审计说明..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="请输入审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>编制流程：H8-5填起租/约满 → 本表B9/L9自动带入；Q9选期初/期末；改K9/M9后表2/表3自动生成</li>
        <li>动态年限：L9为5/10/15等时仅前L9年有数；折旧=入账/MIN(L9,I9)</li>
        <li>年租金K9、初始直接费用M9；折现率H9默认=G9</li>
        <li>租赁期优先从 H8-5「回写/带入」；与来源合同不一致时顶部会告警</li>
        <li>H9联动：负债初始=表2现值合计；期末勾稽H8-1/H9；复杂月付请用按月表</li>
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
import { ref, computed, toRef, watch, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useH8Measurement,
  buildH86AmortSchedule,
  type H8MeasurementParams,
} from '../../composables/useH8Measurement'
import GtIndexChip from '../../GtIndexChip.vue'
import H8LeaseTermSyncBar from './H8LeaseTermSyncBar.vue'
import H8AmortSchedulePanel from './H8AmortSchedulePanel.vue'

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
  (e: 'navigate-sheet', sheetName: string): void
}>()

const showOO = ref(false)

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-measurement-annual-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-measurement-annual-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

const {
  measurementParams, initialMeasurement, formulaText, annualRental,
  h85TermOptions, h85TermMismatch,
  updateParam, pullLeaseTermFromH85,
} = useH8Measurement({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

/** 本页强制按年摊销（与父分段器一致，不依赖 H8-6-branch 存档） */
const amortSchedule = computed(() =>
  buildH86AmortSchedule({
    leaseLiabilityInitial: measurementParams.value.leaseLiabilityInitial,
    discountRate: measurementParams.value.discountRate,
    leaseTermMonths: measurementParams.value.leaseTermMonths,
    rentalPerPeriod: measurementParams.value.rentalPerPeriod,
    branch: '按年计量',
  }),
)

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleParamChange(field: keyof H8MeasurementParams, value: any) {
  updateParam(field, value)
}

function handlePullH85(contractNo?: string) {
  if (props.isReadonly) return
  const r = pullLeaseTermFromH85(contractNo)
  if (!r.ok) {
    ElMessage.warning(r.reason || '带入失败')
    return
  }
  ElMessage.success(`已从 H8-5 带入：${r.contractNo} → ${r.months} 月`)
  if (r.shortTermHint) {
    ElMessage.info('租赁期≤12个月，请关注是否适用 H8-13 短期租赁简化处理')
  }
}
</script>

<style scoped>
.h8-tab-measurement-annual { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.formula-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border: 1px solid #6ee7b7; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
}
.formula-icon { font-size: 28px; }
.formula-content { flex: 1; }
.formula-title { font-weight: 700; font-size: 14px; color: #065f46; margin-bottom: 4px; }
.formula-text { font-size: var(--wp-font-size, 13px); color: #047857; }
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
