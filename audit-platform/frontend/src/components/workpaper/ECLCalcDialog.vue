<template>
  <el-dialog
    :model-value="visible"
    title="🧮 ECL 三阶段计算（G-F5 IFRS 9 / CAS 22）"
    width="820px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #default>
        IFRS 9 / CAS 22 预期信用损失三阶段模型。
        Stage 1（信用风险未显著增加，12 个月 ECL）/ Stage 2（信用风险显著增加，存续期 ECL）/ Stage 3（已发生信用减值，存续期 ECL，PD 接近 100%）。
        当 PD₁₂ₘ ≤ PD<sub>存续期</sub> 时单调性 ECL(1) ≤ ECL(2) ≤ ECL(3) 必然成立。
        <strong>「采纳并写回」会把所选阶段结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="160px" size="small">
      <el-form-item label="ECL 阶段" required>
        <el-radio-group v-model="form.stage">
          <el-radio-button :value="1">Stage 1（12 个月）</el-radio-button>
          <el-radio-button :value="2">Stage 2（存续期）</el-radio-button>
          <el-radio-button :value="3">Stage 3（已减值）</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="金融工具类型" required>
        <el-input
          v-model="form.instrument_type"
          placeholder="如 债权投资 / 其他债权投资"
          style="width: 280px"
        />
      </el-form-item>

      <el-form-item label="账面余额（EAD）" required>
        <el-input-number
          v-model="form.book_value"
          :min="0.01"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（违约风险暴露）</span>
      </el-form-item>

      <el-form-item label="12 个月 PD" required>
        <el-input-number
          v-model="form.pd_12m"
          :min="0"
          :max="1"
          :step="0.001"
          :precision="4"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">（0~1，如 0.02 = 2%）</span>
      </el-form-item>

      <el-form-item label="存续期 PD" required>
        <el-input-number
          v-model="form.pd_lifetime"
          :min="0"
          :max="1"
          :step="0.001"
          :precision="4"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">（0~1，需 ≥ 12 个月 PD）</span>
      </el-form-item>

      <el-form-item label="违约损失率（LGD）" required>
        <el-input-number
          v-model="form.lgd"
          :min="0"
          :max="1"
          :step="0.001"
          :precision="4"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">（0~1，如 0.45 = 45%）</span>
      </el-form-item>
    </el-form>

    <!-- 三阶段预览（客户端实时计算，便于直观看单调性） -->
    <el-divider>三阶段预览（客户端估算）</el-divider>
    <el-table :data="stagePreview" size="small" border style="margin-bottom: 12px">
      <el-table-column label="阶段" prop="label" width="200" />
      <el-table-column label="公式" prop="formula" min-width="300" />
      <el-table-column label="ECL（元）" min-width="160" align="right">
        <template #default="{ row }">
          <span :class="{ 'amt-current': row.stage === form.stage }">
            ¥ {{ formatAmount(row.ecl) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <div class="monotonicity-hint" :class="previewMonotonicityOk ? 'ok' : 'warn'">
      <span v-if="previewMonotonicityOk">
        ✓ 单调性预检通过：ECL(1) ≤ ECL(2) ≤ ECL(3)
      </span>
      <span v-else>
        ⚠ 单调性预检异常：12 个月 PD 不应大于存续期 PD
      </span>
    </div>

    <!-- API 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果（来自后端）</el-divider>
      <div class="ecl-result">
        <el-alert
          :title="`Stage ${result.stage} ECL = ¥${formatAmount(result.ecl_amount)}`"
          :type="result.monotonicity_check ? 'success' : 'warning'"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="阶段">Stage {{ result.stage }}</el-descriptions-item>
          <el-descriptions-item label="ECL 金额">
            <span class="amt-highlight">¥ {{ formatAmount(result.ecl_amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="使用公式" :span="2">
            <span class="formula-text">{{ result.formula_used }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="单调性校验">
            <el-tag :type="result.monotonicity_check ? 'success' : 'warning'" size="small">
              {{ result.monotonicity_check ? '通过' : '未通过' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="LLM 实现">
            <el-tag :type="result.is_llm_stub ? 'info' : 'success'" size="small">
              {{ result.is_llm_stub ? 'stub' : '确定性公式' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onAnalyze"
      >
        🚀 计算 ECL
      </el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >
        ✅ 采纳并写回
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
  /** 默认金融工具类型（按 sheet 上下文推荐：G4=债权投资 / G6=其他债权投资）*/
  instrumentType?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
  instrumentType: '债权投资',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ECLCalcResponse {
  stage: 1 | 2 | 3
  ecl_amount: string
  formula_used: string
  monotonicity_check: boolean
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<ECLCalcResponse | null>(null)

const form = reactive({
  stage: 1 as 1 | 2 | 3,
  instrument_type: props.instrumentType,
  book_value: 1000000,
  pd_12m: 0.02 as number | null,
  pd_lifetime: 0.10 as number | null,
  lgd: 0.45 as number | null,
})

// ── 客户端三阶段预览（同后端公式，供直观对比；权威数值仍以后端 result 为准） ──

interface StageRow {
  stage: 1 | 2 | 3
  label: string
  formula: string
  ecl: number
}

const stagePreview = computed<StageRow[]>(() => {
  const ead = Number(form.book_value) || 0
  const p12 = Number(form.pd_12m) || 0
  const pLt = Number(form.pd_lifetime) || 0
  const lgd = Number(form.lgd) || 0
  const ecl1 = ead * p12 * lgd
  const ecl2 = ead * pLt * lgd
  const ecl3 = ead * pLt * lgd
  return [
    {
      stage: 1,
      label: 'Stage 1（信用风险未显著增加）',
      formula: 'ECL = EAD × PD₁₂ₘ × LGD',
      ecl: ecl1,
    },
    {
      stage: 2,
      label: 'Stage 2（信用风险显著增加）',
      formula: 'ECL = EAD × PD存续期 × LGD',
      ecl: ecl2,
    },
    {
      stage: 3,
      label: 'Stage 3（已发生信用减值，PD 接近 100%）',
      formula: 'ECL = EAD × PD存续期 × LGD',
      ecl: ecl3,
    },
  ]
})

const previewMonotonicityOk = computed(() => {
  const p12 = Number(form.pd_12m) || 0
  const pLt = Number(form.pd_lifetime) || 0
  return p12 <= pLt
})

const isFormValid = computed(() => {
  if (!form.instrument_type) return false
  if (form.book_value <= 0) return false
  if (form.pd_12m == null || form.pd_12m < 0 || form.pd_12m > 1) return false
  if (form.pd_lifetime == null || form.pd_lifetime < 0 || form.pd_lifetime > 1) return false
  if (form.lgd == null || form.lgd < 0 || form.lgd > 1) return false
  if (form.pd_12m > form.pd_lifetime) return false
  return true
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string): Record<string, any> {
  const body: Record<string, any> = {
    stage: form.stage,
    book_value: form.book_value,
    pd_12m: form.pd_12m,
    pd_lifetime: form.pd_lifetime,
    lgd: form.lgd,
  }
  if (applySheet) {
    body.apply_to_sheet = applySheet
  }
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<ECLCalcResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g/ecl-calc`,
      buildRequestBody(),
    )
    result.value = resp
    if (resp?.monotonicity_check) {
      ElMessage.success(`计算完成：Stage ${resp.stage} ECL = ¥${formatAmount(resp.ecl_amount)}`)
    } else {
      ElMessage.warning('计算完成但单调性校验未通过，请复核 PD 输入')
    }
  } catch (e: any) {
    handleApiError(e, 'ECL 计算')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet，无法写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<ECLCalcResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g/ecl-calc`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('计算完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    handleApiError(e, '采纳写回')
  } finally {
    applying.value = false
  }
}

// 重置 result + 同步 instrumentType prop 在弹窗关闭/打开时
watch(() => props.visible, (v) => {
  if (!v) {
    result.value = null
  } else {
    if (props.instrumentType) {
      form.instrument_type = props.instrumentType
    }
  }
})

defineExpose({
  form,
  result,
  isFormValid,
  buildRequestBody,
  stagePreview,
  previewMonotonicityOk,
  onAnalyze,
  onApplyToSheet,
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.ecl-result {
  margin-top: 8px;
}
.amt-highlight {
  color: var(--el-color-primary);
  font-weight: 600;
}
.amt-current {
  color: var(--el-color-primary);
  font-weight: 600;
}
.formula-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.monotonicity-hint {
  font-size: 12px;
  margin-bottom: 8px;
}
.monotonicity-hint.ok {
  color: var(--el-color-success);
}
.monotonicity-hint.warn {
  color: var(--el-color-warning);
}
</style>
