<template>
  <div class="gt-materiality gt-fade-in">
    <h2 class="gt-page-title">重要性水平</h2>

    <div class="gt-mat-layout">
      <!-- 左侧：配置表单 -->
      <div class="gt-mat-form-section">
        <el-form :model="form" label-width="130px" label-position="right">
          <el-form-item label="基准类型">
            <el-select v-model="form.benchmark_type" placeholder="请选择" style="width: 100%"
              @change="onBenchmarkTypeChange">
              <el-option label="利润总额" value="pre_tax_profit" />
              <el-option label="营业收入" value="revenue" />
              <el-option label="总资产" value="total_assets" />
              <el-option label="净资产" value="net_assets" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>
          <el-form-item label="基准金额">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-input-number v-model="benchmarkNum" :precision="2" :controls="false"
                placeholder="基准金额" style="flex: 1" @change="onParamChange" />
              <el-button v-if="form.benchmark_type !== 'custom'" plain :loading="autoLoading"
                @click="autoPopulate">从试算表取数</el-button>
            </div>
          </el-form-item>
          <el-form-item label="整体百分比(%)">
            <el-input-number v-model="overallPct" :min="0" :max="100" :precision="2" :step="0.5"
              style="width: 100%" @change="onParamChange" />
          </el-form-item>
          <el-form-item label="执行比例(%)">
            <el-slider v-model="perfRatio" :min="0" :max="100" :step="5" show-input @change="onParamChange" />
          </el-form-item>
          <el-form-item label="微小比例(%)">
            <el-input-number v-model="trivialRatio" :min="0" :max="100" :precision="2" :step="1"
              style="width: 100%" @change="onParamChange" />
          </el-form-item>
        </el-form>
      </div>

      <!-- 右侧：结果卡片 -->
      <div class="gt-mat-result-section">
        <div v-if="result" class="gt-mat-result-cards">
          <div class="gt-mat-result-card gt-mat-result-card--primary">
            <span class="gt-mat-result-label">整体重要性</span>
            <span class="gt-mat-result-value">{{ formatAmt(result.overall_materiality) }}</span>
          </div>
          <div class="gt-mat-result-card">
            <span class="gt-mat-result-label">实际执行重要性</span>
            <span class="gt-mat-result-value">{{ formatAmt(result.performance_materiality) }}</span>
          </div>
          <div class="gt-mat-result-card">
            <span class="gt-mat-result-label">明显微小错报</span>
            <span class="gt-mat-result-value">{{ formatAmt(result.trivial_threshold) }}</span>
          </div>
        </div>
        <div v-else class="gt-mat-no-result">请配置参数后计算</div>

        <!-- 手动覆盖 -->
        <el-collapse v-if="result" style="margin-top: 16px">
          <el-collapse-item title="手动覆盖（可选）" name="override">
            <el-form label-width="130px">
              <el-form-item label="整体重要性">
                <el-input-number v-model="overrideForm.overall_materiality" :precision="2"
                  :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="执行重要性">
                <el-input-number v-model="overrideForm.performance_materiality" :precision="2"
                  :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="微小错报">
                <el-input-number v-model="overrideForm.trivial_threshold" :precision="2"
                  :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="覆盖原因">
                <el-input v-model="overrideForm.reason" type="textarea" :rows="2" placeholder="请说明覆盖原因" />
              </el-form-item>
              <el-form-item>
                <el-button type="warning" :disabled="!overrideForm.reason" :loading="overrideLoading"
                  @click="submitOverride">确认覆盖</el-button>
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <!-- 变更历史 -->
    <div class="gt-mat-history-section" v-if="history.length">
      <h3 class="gt-section-title">变更历史</h3>
      <el-table :data="history" border stripe size="small">
        <el-table-column prop="changed_at" label="时间" width="170">
          <template #default="{ row }">{{ row.changed_at || row.calculated_at }}</template>
        </el-table-column>
        <el-table-column prop="benchmark_type" label="基准类型" width="100" />
        <el-table-column prop="overall_materiality" label="整体重要性" width="140" align="right">
          <template #default="{ row }">{{ formatAmt(row.overall_materiality) }}</template>
        </el-table-column>
        <el-table-column prop="performance_materiality" label="执行重要性" width="140" align="right">
          <template #default="{ row }">{{ formatAmt(row.performance_materiality) }}</template>
        </el-table-column>
        <el-table-column prop="trivial_threshold" label="微小错报" width="140" align="right">
          <template #default="{ row }">{{ formatAmt(row.trivial_threshold) }}</template>
        </el-table-column>
        <el-table-column prop="override_reason" label="原因" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getMateriality, calculateMateriality, overrideMateriality,
  getMaterialityHistory, getMaterialityBenchmark,
  type MaterialityData,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const autoLoading = ref(false)
const overrideLoading = ref(false)
const result = ref<MaterialityData | null>(null)
const history = ref<any[]>([])

const form = reactive({
  benchmark_type: '',
  benchmark_amount: '',
})
const benchmarkNum = ref<number | undefined>(undefined)
const overallPct = ref(5)
const perfRatio = ref(50)
const trivialRatio = ref(5)

const overrideForm = reactive({
  overall_materiality: undefined as number | undefined,
  performance_materiality: undefined as number | undefined,
  trivial_threshold: undefined as number | undefined,
  reason: '',
})

function formatAmt(val: any): string {
  const n = Number(val)
  if (isNaN(n)) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onBenchmarkTypeChange() {
  if (form.benchmark_type && form.benchmark_type !== 'custom') {
    await autoPopulate()
  }
}

async function autoPopulate() {
  if (!projectId.value || !form.benchmark_type) return
  autoLoading.value = true
  try {
    const resp = await getMaterialityBenchmark(projectId.value, year.value, form.benchmark_type)
    benchmarkNum.value = Number(resp.benchmark_amount)
    form.benchmark_amount = String(benchmarkNum.value)
    onParamChange()
  } catch { /* interceptor handles */ }
  finally { autoLoading.value = false }
}

async function onParamChange() {
  form.benchmark_amount = benchmarkNum.value != null ? String(benchmarkNum.value) : ''
  if (!projectId.value || !form.benchmark_type || !form.benchmark_amount || !overallPct.value) return
  try {
    result.value = await calculateMateriality(projectId.value, year.value, {
      benchmark_type: form.benchmark_type,
      benchmark_amount: form.benchmark_amount,
      overall_percentage: String(overallPct.value),
      performance_ratio: String(perfRatio.value),
      trivial_ratio: String(trivialRatio.value),
    })
  } catch { /* silent */ }
}

async function submitOverride() {
  if (!projectId.value || !overrideForm.reason) return
  overrideLoading.value = true
  try {
    const body: any = { override_reason: overrideForm.reason }
    if (overrideForm.overall_materiality != null) body.overall_materiality = String(overrideForm.overall_materiality)
    if (overrideForm.performance_materiality != null) body.performance_materiality = String(overrideForm.performance_materiality)
    if (overrideForm.trivial_threshold != null) body.trivial_threshold = String(overrideForm.trivial_threshold)
    result.value = await overrideMateriality(projectId.value, year.value, body)
    ElMessage.success('覆盖成功')
    fetchHistory()
  } catch { /* interceptor handles */ }
  finally { overrideLoading.value = false }
}

async function fetchHistory() {
  try {
    history.value = await getMaterialityHistory(projectId.value, year.value)
  } catch { /* ignore */ }
}

onMounted(async () => {
  // Load existing
  try {
    const existing = await getMateriality(projectId.value, year.value)
    if (existing) {
      result.value = existing
      form.benchmark_type = existing.benchmark_type
      form.benchmark_amount = String(existing.benchmark_amount)
      benchmarkNum.value = Number(existing.benchmark_amount)
      overallPct.value = Number(existing.overall_percentage)
      perfRatio.value = Number(existing.performance_ratio)
      trivialRatio.value = Number(existing.trivial_ratio)
    }
  } catch { /* no existing data */ }
  fetchHistory()
})
</script>

<style scoped>
.gt-materiality { padding: var(--gt-space-4); }
.gt-mat-layout { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gt-space-6); }
.gt-mat-form-section { background: var(--gt-color-bg-white); padding: var(--gt-space-5); border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm); }
.gt-mat-result-section { }
.gt-mat-result-cards { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-mat-result-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-sm); padding: var(--gt-space-4);
  text-align: center; box-shadow: var(--gt-shadow-sm);
}
.gt-mat-result-card.gt-mat-result-card--primary { border-left: 4px solid var(--gt-color-primary); }
.gt-mat-result-label { display: block; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); margin-bottom: var(--gt-space-1); }
.gt-mat-result-value { display: block; font-size: var(--gt-font-size-2xl); font-weight: 600; color: var(--gt-color-text); }
.gt-mat-result-card.gt-mat-result-card--primary .gt-mat-result-value { color: var(--gt-color-primary); }
.gt-mat-no-result { text-align: center; color: var(--gt-color-text-tertiary); padding: var(--gt-space-10); }
.gt-mat-history-section { margin-top: var(--gt-space-8); }
</style>
