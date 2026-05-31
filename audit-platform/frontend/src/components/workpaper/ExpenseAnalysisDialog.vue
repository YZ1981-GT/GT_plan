<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="880px"
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
        3 维度分析（同比 / 预算差异 / 行业对比），异常自动标记。计算结果可「采纳并写回」当前底稿
        parsed_data.expense_analysis。
      </template>
    </el-alert>

    <!-- 底稿选择 -->
    <el-form :model="form" label-width="120px" size="small">
      <el-form-item label="底稿">
        <el-radio-group v-model="form.wp_code">
          <el-radio value="K8">K8 销售费用</el-radio>
          <el-radio value="K9">K9 管理费用</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="本年营业收入">
        <el-input-number
          v-model="form.revenue"
          :min="0"
          :step="100000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（用于行业占比对比）</span>
      </el-form-item>
    </el-form>

    <el-divider>费用类别明细</el-divider>

    <el-table :data="form.categories" size="small" border max-height="320">
      <el-table-column label="费用类别" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.category" placeholder="如：职工薪酬" />
        </template>
      </el-table-column>
      <el-table-column label="本年金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.current"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="上年金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.prior"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="预算金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.budget"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="行业均值占比" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.industry_rate"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="4"
            controls-position="right"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="" width="60" align="center">
        <template #default="{ $index }">
          <el-button type="danger" size="small" link @click="removeCategory($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div style="margin-top: 8px">
      <el-button size="small" @click="addCategory">+ 添加费用类别</el-button>
    </div>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>分析结果</el-divider>

      <el-descriptions :column="2" size="small" border style="margin-bottom: 8px">
        <el-descriptions-item label="LLM Stub">{{ result.is_llm_stub ? '是（待接入）' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="异常项数">{{ result.anomaly_flags?.length || 0 }}</el-descriptions-item>
        <el-descriptions-item label="简要" :span="2">{{ result.summary }}</el-descriptions-item>
      </el-descriptions>

      <!-- AI 解释区域 -->
      <div v-if="result.is_llm_stub" class="ai-explanation-stub">
        AI 分析功能待接入，当前显示规则引擎结果。
      </div>
      <div
        v-else-if="renderedExplanation"
        class="ai-explanation-content"
        v-html="renderedExplanation"
      />

      <el-tabs>
        <el-tab-pane label="同比变化">
          <el-table :data="yoyTable" size="small" border max-height="240">
            <el-table-column label="费用类别" prop="category" min-width="120" />
            <el-table-column label="变化金额" width="140" align="right">
              <template #default="{ row }">¥ {{ formatAmount(row.amount_change) }}</template>
            </el-table-column>
            <el-table-column label="变化率" width="100" align="right">
              <template #default="{ row }">{{ formatRate(row.rate_change) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="flagTagType(row.flag)" size="small">{{ flagLabel(row.flag) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="budgetTable.length" label="预算差异">
          <el-table :data="budgetTable" size="small" border max-height="240">
            <el-table-column label="费用类别" prop="category" min-width="120" />
            <el-table-column label="差异金额" width="140" align="right">
              <template #default="{ row }">¥ {{ formatAmount(row.variance_amount) }}</template>
            </el-table-column>
            <el-table-column label="差异率" width="100" align="right">
              <template #default="{ row }">{{ formatRate(row.variance_rate) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="flagTagType(row.flag)" size="small">{{ flagLabel(row.flag) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="industryTable.length" label="行业对比">
          <el-table :data="industryTable" size="small" border max-height="240">
            <el-table-column label="费用类别" prop="category" min-width="120" />
            <el-table-column label="项目占比" width="120" align="right">
              <template #default="{ row }">{{ formatRate(row.project_rate) }}</template>
            </el-table-column>
            <el-table-column label="行业均值" width="120" align="right">
              <template #default="{ row }">{{ formatRate(row.industry_avg_rate) }}</template>
            </el-table-column>
            <el-table-column label="偏离度" width="100" align="right">
              <template #default="{ row }">{{ formatRate(row.deviation) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="flagTagType(row.flag)" size="small">{{ flagLabel(row.flag) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="result.anomaly_flags?.length" :label="`异常清单 (${result.anomaly_flags.length})`">
          <el-tag
            v-for="(f, i) in result.anomaly_flags"
            :key="i"
            type="danger"
            size="default"
            style="margin: 4px"
          >{{ f }}</el-tag>
        </el-tab-pane>
      </el-tabs>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onCalc"
      >🚀 计算</el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >✅ 采纳并写回</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前激活的 sheet 名（用于写回 parsed_data.expense_analysis[sheet]） */
  targetSheet?: string
  /** 默认 wp_code 选择（K8 / K9） */
  defaultWpCode?: 'K8' | 'K9'
}

const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
  defaultWpCode: 'K8',
})

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface YoyChangeItem { amount_change: number; rate_change: number; flag: string }
interface BudgetVarianceItem { variance_amount: number; variance_rate: number; flag: string }
interface IndustryComparisonItem { project_rate: number; industry_avg_rate: number; deviation: number; flag: string }

interface AnalysisResponse {
  yoy_changes: Record<string, YoyChangeItem>
  budget_variances: Record<string, BudgetVarianceItem> | null
  industry_comparison: Record<string, IndustryComparisonItem> | null
  anomaly_flags: string[]
  summary: string
  is_llm_stub: boolean
  ai_explanation?: string | null
  applied_to_sheet?: string | null
}

interface CategoryRow {
  category: string
  current: number
  prior: number
  budget: number
  industry_rate: number
}

const loading = ref(false)
const applying = ref(false)
const result = ref<AnalysisResponse | null>(null)

const form = reactive({
  wp_code: props.defaultWpCode as 'K8' | 'K9',
  revenue: 0,
  categories: [
    { category: '职工薪酬', current: 0, prior: 0, budget: 0, industry_rate: 0 } as CategoryRow,
    { category: '差旅费', current: 0, prior: 0, budget: 0, industry_rate: 0 } as CategoryRow,
    { category: '折旧费', current: 0, prior: 0, budget: 0, industry_rate: 0 } as CategoryRow,
    { category: '其他', current: 0, prior: 0, budget: 0, industry_rate: 0 } as CategoryRow,
  ],
})

const dialogTitle = computed(() => {
  const name = form.wp_code === 'K8' ? '销售费用' : '管理费用'
  return `📊 ${name}分析（K-F7 同比/预算/行业对比）`
})

const isFormValid = computed(() => {
  // 至少一个类别填了 category 名 + 本年金额 > 0
  return form.categories.some(
    (c) => c.category.trim() && c.current > 0,
  )
})

const yoyTable = computed(() => {
  if (!result.value) return []
  return Object.entries(result.value.yoy_changes).map(([cat, info]) => ({
    category: cat,
    ...info,
  }))
})

const budgetTable = computed(() => {
  const b = result.value?.budget_variances
  if (!b) return []
  return Object.entries(b).map(([cat, info]) => ({
    category: cat,
    ...info,
  }))
})

const industryTable = computed(() => {
  const ind = result.value?.industry_comparison
  if (!ind) return []
  return Object.entries(ind).map(([cat, info]) => ({
    category: cat,
    ...info,
  }))
})

/** Render ai_explanation as sanitized HTML via marked + DOMPurify */
const renderedExplanation = computed(() => {
  if (!result.value) return ''
  if (result.value.is_llm_stub) return ''
  const raw = result.value.ai_explanation
  if (!raw) return ''
  const html = marked(raw, { async: false }) as string
  return DOMPurify.sanitize(html)
})

function addCategory() {
  form.categories.push({ category: '', current: 0, prior: 0, budget: 0, industry_rate: 0 })
}

function removeCategory(index: number) {
  form.categories.splice(index, 1)
}

function formatAmount(n: number | undefined) {
  if (n === undefined || n === null) return '0.00'
  if (!Number.isFinite(n)) return String(n)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatRate(r: number | undefined) {
  if (r === undefined || r === null) return '—'
  if (!Number.isFinite(r) || Math.abs(r) > 100) return '∞'
  return (r * 100).toFixed(2) + '%'
}

function flagTagType(flag: string): 'success' | 'warning' | 'danger' | 'info' {
  if (flag === 'normal') return 'success'
  if (flag === 'increase_anomaly' || flag === 'overrun' || flag === 'above_industry') return 'danger'
  if (flag === 'decrease_anomaly' || flag === 'underrun' || flag === 'below_industry') return 'warning'
  if (flag === 'new_category' || flag === 'no_budget') return 'info'
  return 'info'
}

function flagLabel(flag: string): string {
  const map: Record<string, string> = {
    normal: '正常',
    increase_anomaly: '异常增加',
    decrease_anomaly: '异常减少',
    new_category: '新增项',
    overrun: '超预算',
    underrun: '低于预算',
    no_budget: '无预算',
    above_industry: '高于行业',
    below_industry: '低于行业',
  }
  return map[flag] || flag
}

function buildBody(applySheet?: string) {
  const current_year: Record<string, number> = {}
  const prior_year: Record<string, number> = {}
  const budget: Record<string, number> = {}
  const industry_avg_rates: Record<string, number> = {}
  for (const c of form.categories) {
    if (!c.category.trim() || c.current <= 0) continue
    current_year[c.category] = c.current
    if (c.prior > 0) prior_year[c.category] = c.prior
    if (c.budget > 0) budget[c.category] = c.budget
    if (c.industry_rate > 0) industry_avg_rates[c.category] = c.industry_rate
  }
  return {
    wp_code: form.wp_code,
    current_year,
    prior_year,
    budget: Object.keys(budget).length ? budget : null,
    industry_avg_rates: Object.keys(industry_avg_rates).length
      ? industry_avg_rates
      : null,
    revenue: form.revenue > 0 ? form.revenue : null,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<AnalysisResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/k8/expense-analysis`,
      buildBody(),
    )
    result.value = resp
    ElMessage.success(`分析完成，发现 ${resp.anomaly_flags?.length || 0} 项异常`)
  } catch (e: any) {
    handleApiError(e, '分析')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<AnalysisResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/k8/expense-analysis`,
      buildBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('计算完成但未写回')
    }
  } catch (e: any) {
    handleApiError(e, '写回')
  } finally {
    applying.value = false
  }
}

watch(
  () => props.visible,
  (v) => {
    if (!v) result.value = null
  },
)

watch(
  () => props.defaultWpCode,
  (v) => {
    if (v) form.wp_code = v
  },
)
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

/* AI explanation stub placeholder */
.ai-explanation-stub {
  margin: 12px 0;
  padding: 10px 14px;
  background-color: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  color: var(--el-text-color-placeholder, #a8abb2);
  font-size: 13px;
  font-style: italic;
}

/* AI explanation rendered markdown */
.ai-explanation-content {
  margin: 12px 0;
  padding: 12px 16px;
  background-color: var(--el-fill-color-blank, #ffffff);
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.ai-explanation-content :deep(h1),
.ai-explanation-content :deep(h2),
.ai-explanation-content :deep(h3) {
  margin: 12px 0 6px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ai-explanation-content :deep(h1) { font-size: 18px; }
.ai-explanation-content :deep(h2) { font-size: 16px; }
.ai-explanation-content :deep(h3) { font-size: 14px; }

.ai-explanation-content :deep(p) {
  margin: 6px 0;
}

.ai-explanation-content :deep(ul),
.ai-explanation-content :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.ai-explanation-content :deep(li) {
  margin: 3px 0;
}

.ai-explanation-content :deep(strong) {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ai-explanation-content :deep(code) {
  padding: 2px 5px;
  background-color: var(--el-fill-color-light, #f0f2f5);
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.ai-explanation-content :deep(pre) {
  margin: 8px 0;
  padding: 10px 12px;
  background-color: var(--el-fill-color-light, #f0f2f5);
  border-radius: 4px;
  overflow-x: auto;
}

.ai-explanation-content :deep(pre code) {
  padding: 0;
  background: none;
}

.ai-explanation-content :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--el-color-primary);
  background-color: var(--el-fill-color-lighter, #f5f7fa);
  color: var(--el-text-color-secondary);
}
</style>
