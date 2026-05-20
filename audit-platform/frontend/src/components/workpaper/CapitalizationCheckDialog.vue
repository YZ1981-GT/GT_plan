<template>
  <el-dialog
    :model-value="visible"
    title="🧮 开发支出资本化时点判断（I-F5 / CAS 6 五条件）"
    width="780px"
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
        《企业会计准则第 6 号 — 无形资产》第 9 条规定，企业内部研发项目开发阶段的支出
        <strong>同时满足 5 个条件</strong>方可资本化。逐项勾选已满足条件并填写满足日期，
        系统将自动计算建议的资本化起始日期 = max(各条件满足日期, 项目启动日期)。
        任一条件未满足时返回缺失清单（在缺失条件满足前的支出应费用化进入 I6 研发费用）。
        <strong>「采纳并写回」会把判断结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="180px" size="small">
      <el-form-item label="研发项目启动日期" required>
        <el-date-picker
          v-model="form.project_start_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="如 2025-01-15"
          style="width: 200px"
        />
      </el-form-item>
      <el-form-item label="项目预计完成日期">
        <el-date-picker
          v-model="form.project_end_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="可选"
          style="width: 200px"
        />
        <span class="gt-form-unit">（可选；用于上限校验）</span>
      </el-form-item>
    </el-form>

    <el-divider>CAS 6 第 9 条 — 五项资本化条件</el-divider>

    <el-table :data="conditionRows" size="small" border>
      <el-table-column label="#" width="48" align="center">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="条件" min-width="320">
        <template #default="{ row }">
          <div class="cond-cell">
            <el-checkbox
              v-model="form.conditions[(row as ConditionRow).field]"
              size="small"
            >
              <strong>{{ (row as ConditionRow).short }}</strong>
            </el-checkbox>
            <div class="cond-detail">{{ (row as ConditionRow).label }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="满足日期" width="200" align="center">
        <template #default="{ row }">
          <el-date-picker
            v-model="form.condition_dates[(row as ConditionRow).field]"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="YYYY-MM-DD"
            :disabled="!form.conditions[(row as ConditionRow).field]"
            style="width: 170px"
            size="small"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>判断结果</el-divider>
      <div class="cap-result">
        <el-alert
          :title="result.recommendation"
          :type="result.all_conditions_met ? 'success' : 'warning'"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="5 条件全部满足">
            <el-tag :type="result.all_conditions_met ? 'success' : 'danger'" size="small">
              {{ result.all_conditions_met ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="result.capitalization_start_date" label="建议资本化起始日期">
            <span class="amt-highlight">{{ result.capitalization_start_date }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="result.missing_conditions.length > 0" label="缺失条件">
            <ul class="missing-list">
              <li v-for="c in result.missing_conditions" :key="c">{{ c }}</li>
            </ul>
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
        🚀 计算建议
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

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface CapitalizationCheckResponse {
  all_conditions_met: boolean
  capitalization_start_date: string | null
  missing_conditions: string[]
  condition_status: Record<string, boolean>
  recommendation: string
  applied_to_sheet?: string | null
}

type ConditionField =
  | 'technical_feasibility'
  | 'completion_intent'
  | 'ability_to_use_or_sell'
  | 'future_economic_benefits'
  | 'resource_sufficiency'

interface ConditionRow {
  field: ConditionField
  short: string
  label: string
}

const CONDITIONS: ConditionRow[] = [
  {
    field: 'technical_feasibility',
    short: '技术可行性已论证',
    label: '完成该无形资产以使其能够使用或出售在技术上具有可行性（CAS 6 第 9 条 (一)）',
  },
  {
    field: 'completion_intent',
    short: '具有完成并使用或出售的意图',
    label: '具有完成该无形资产并使用或出售的意图（CAS 6 第 9 条 (二)）',
  },
  {
    field: 'ability_to_use_or_sell',
    short: '使用或出售产生经济利益的方式',
    label:
      '无形资产产生经济利益的方式，包括能够证明运用该无形资产生产的产品存在市场或无形资产自身存在市场（CAS 6 第 9 条 (三)）',
  },
  {
    field: 'future_economic_benefits',
    short: '存在使用或出售市场可产生未来经济利益',
    label:
      '该无形资产存在使用或出售的市场，能够产生未来经济利益（CAS 6 第 9 条 (四)）',
  },
  {
    field: 'resource_sufficiency',
    short: '技术/财务/其他资源充足',
    label: '有足够的技术、财务和其他资源支持开发并使用或出售该无形资产（CAS 6 第 9 条 (五)）',
  },
]

const conditionRows = computed(() => CONDITIONS)

const loading = ref(false)
const applying = ref(false)
const result = ref<CapitalizationCheckResponse | null>(null)

const form = reactive({
  project_start_date: '',
  project_end_date: '' as string | '',
  conditions: {
    technical_feasibility: false,
    completion_intent: false,
    ability_to_use_or_sell: false,
    future_economic_benefits: false,
    resource_sufficiency: false,
  } as Record<ConditionField, boolean>,
  condition_dates: {
    technical_feasibility: '',
    completion_intent: '',
    ability_to_use_or_sell: '',
    future_economic_benefits: '',
    resource_sufficiency: '',
  } as Record<ConditionField, string>,
})

// 取消勾选时清空对应日期
watch(
  () => CONDITIONS.map((c) => form.conditions[c.field]),
  () => {
    for (const c of CONDITIONS) {
      if (!form.conditions[c.field]) {
        form.condition_dates[c.field] = ''
      }
    }
  },
  { deep: true },
)

const isFormValid = computed(() => {
  if (!form.project_start_date) return false
  // 任何已勾选的条件都必须填日期
  for (const c of CONDITIONS) {
    if (form.conditions[c.field] && !form.condition_dates[c.field]) {
      return false
    }
  }
  return true
})

function buildRequestBody(applySheet?: string) {
  const condition_dates: Record<string, string> = {}
  for (const c of CONDITIONS) {
    if (form.conditions[c.field] && form.condition_dates[c.field]) {
      condition_dates[c.field] = form.condition_dates[c.field]
    }
  }
  const body: Record<string, any> = {
    technical_feasibility: form.conditions.technical_feasibility,
    completion_intent: form.conditions.completion_intent,
    ability_to_use_or_sell: form.conditions.ability_to_use_or_sell,
    future_economic_benefits: form.conditions.future_economic_benefits,
    resource_sufficiency: form.conditions.resource_sufficiency,
    condition_dates,
    project_start_date: form.project_start_date,
  }
  if (form.project_end_date) {
    body.project_end_date = form.project_end_date
  }
  if (applySheet) {
    body.apply_to_sheet = applySheet
  }
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<CapitalizationCheckResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/i2/capitalization-check`,
      buildRequestBody(),
    )
    result.value = resp
    if (resp?.all_conditions_met) {
      ElMessage.success(`5 条件全部满足；建议自 ${resp.capitalization_start_date} 起资本化`)
    } else {
      ElMessage.warning(`不满足资本化条件，缺失 ${resp.missing_conditions.length} 项`)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '资本化时点判断失败')
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
    const resp = await api.post<CapitalizationCheckResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/i2/capitalization-check`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('分析完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '采纳写回失败')
  } finally {
    applying.value = false
  }
}

// 重置 result 在弹窗关闭时
watch(() => props.visible, (v) => {
  if (!v) result.value = null
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.cond-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cond-detail {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  margin-left: 22px;
}
.cap-result {
  margin-top: 8px;
}
.amt-highlight {
  color: var(--el-color-primary);
  font-weight: 600;
}
.missing-list {
  margin: 0;
  padding-left: 18px;
}
.missing-list li {
  line-height: 1.6;
  color: var(--el-color-warning);
}
</style>
