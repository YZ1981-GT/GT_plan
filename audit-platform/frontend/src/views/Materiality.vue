<template>
  <div class="gt-materiality gt-fade-in">
    <!-- 页面横幅 [R7-S3-01] -->
    <GtPageHeader title="重要性水平" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :badges="[{ value: '三级重要性计算与手动覆盖' }]"
        @unit-change="onProjectChange"
        @year-change="onYearChange"
      />
      <template #actions>
        <GtToolbar :show-edit-toggle="true" :is-editing="isEditing" @edit-toggle="isEditing ? exitEdit() : enterEdit()" />
      </template>
    </GtPageHeader>
    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <div class="gt-mat-layout">
      <!-- 左侧：配置表单 -->
      <div class="gt-mat-form-section">
        <el-form :model="form" label-width="130px" label-position="right">
          <!-- §1 是否公开交易实体（决定百分比区间） -->
          <el-form-item label="是否公开交易实体">
            <el-radio-group v-model="form.is_public_entity" @change="onParamChange">
              <el-radio value="yes">是（IPO/上市/新三板）</el-radio>
              <el-radio value="no">否</el-radio>
            </el-radio-group>
            <div class="field-hint" v-if="form.is_public_entity === 'yes'">百分比参考区间：税前利润 3-5%/收入 0.25-1%/净资产 0.25-2%</div>
            <div class="field-hint" v-else-if="form.is_public_entity === 'no'">百分比参考区间：税前利润 3-10%/收入 0.25-3%/净资产 0.25-2%</div>
          </el-form-item>

          <el-form-item label="基准类型">
            <el-select v-model="form.benchmark_type" placeholder="请选择" style="width: 100%"
              @change="onBenchmarkTypeChange">
              <el-option label="经常性业务的税前利润" value="pre_tax_profit" />
              <el-option label="营业收入" value="revenue" />
              <el-option label="总资产" value="total_assets" />
              <el-option label="净资产" value="net_assets" />
              <el-option label="费用总额" value="total_expense" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>

          <!-- §2.1 计算基础（三年趋势） -->
          <el-form-item label="计算基础">
            <el-radio-group v-model="form.calc_basis" @change="onParamChange">
              <el-radio value="forecast">本年预测数</el-radio>
              <el-radio value="unadjusted">年末未审数</el-radio>
              <el-radio value="average_3y">三年平均数</el-radio>
            </el-radio-group>
          </el-form-item>

          <!-- 三年趋势对比（源§2.1） -->
          <div v-if="form.benchmark_type && form.benchmark_type !== 'custom'" class="three-year-trend">
            <span class="trend-title">三年趋势对比（万元）：</span>
            <div class="trend-values">
              <span>本年: {{ formatAmt(benchmarkNum) }}</span>
              <span>上年: {{ formatAmt(priorYear1) }}</span>
              <span>前年: {{ formatAmt(priorYear2) }}</span>
            </div>
            <div v-if="trendWarning" class="trend-warning">⚠️ {{ trendWarning }}</div>
          </div>

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
            <div class="field-hint">{{ suggestedPctRange }}</div>
          </el-form-item>
          <el-form-item label="执行比例(%)">
            <el-slider v-model="perfRatio" :min="45" :max="75" :step="5" show-input @change="onParamChange" />
            <div class="field-hint">CAS: 45%~75%。{{ perfRatioHint }}</div>
          </el-form-item>
          <el-form-item label="微小比例(%)">
            <el-input-number v-model="trivialRatio" :min="0" :max="5" :precision="2" :step="0.5"
              style="width: 100%" @change="onParamChange" />
            <div class="field-hint">CAS: ≤5% 整体重要性（GTI 统一要求）</div>
          </el-form-item>

          <!-- §3.4 特定类别重要性（如适用） -->
          <el-divider content-position="left">特定类别重要性（如适用）</el-divider>
          <div class="specific-mat-section">
            <div class="field-hint" style="margin-bottom:8px">
              如存在特定交易/余额/披露需单独确定重要性水平（如关联方交易、特定科目），请在此记录。
              无需时留空。
            </div>
            <el-form-item label="特定类别名称">
              <el-input v-model="specificForm.name" placeholder="如：关联方交易" style="width:100%" />
            </el-form-item>
            <el-form-item label="确定原因">
              <el-input v-model="specificForm.reason" type="textarea" :autosize="{minRows:1,maxRows:3}" placeholder="确定为特定类别的原因..." />
            </el-form-item>
            <el-form-item label="特定类别PM">
              <el-input-number v-model="specificForm.amount" :precision="2" :controls="false" placeholder="金额" style="width:100%" />
            </el-form-item>
            <el-form-item label="特定类别TE比例(%)">
              <el-input-number v-model="specificForm.te_ratio" :min="45" :max="75" :precision="0" style="width:100%" />
            </el-form-item>
          </div>
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
            <el-form ref="overrideFormRef" :model="overrideForm" :rules="overrideRules" label-width="130px">
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
              <el-form-item label="覆盖原因" prop="reason">
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

    <!-- §4 重要性修订（CAS1221 第十二条：审计过程中获知新信息时修订） -->
    <div class="gt-mat-revision-section" v-if="result">
      <h3 class="gt-section-title">§4 重要性修订（审计过程中）</h3>
      <div class="revision-hint">
        CAS1221 第十二条：如果在审计过程中获知了某项信息，而该信息可能导致注册会计师确定与原来不同的重要性水平，
        应当修订。常见原因：被审计单位实际经营成果与预测偏差较大/发现新的风险因素/汇总错报接近重要性水平。
      </div>
      <el-form v-if="isEditing" label-width="100px" style="margin-top:12px">
        <el-form-item label="修订原因">
          <el-input v-model="revisionReason" type="textarea" :autosize="{minRows:2,maxRows:4}" placeholder="说明修订依据（如：年末实际利润较预测大幅偏离/发现新的舞弊风险）..." />
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :disabled="!revisionReason.trim()" @click="submitRevision">
            修订重要性（基于上方最新参数）
          </el-button>
        </el-form-item>
      </el-form>
      <div v-else class="revision-readonly">上方参数修改后点"编辑"模式可修订重要性，修订原因将记入变更历史。</div>
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
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useEditMode } from '@/composables/useEditMode'
import { confirmLeave } from '@/utils/confirm'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import {
  getMateriality, calculateMateriality, overrideMateriality,
  getMaterialityHistory, getMaterialityBenchmark,
  type MaterialityData,
} from '@/services/auditPlatformApi'
import { useProjectSelector } from '@/composables/useProjectSelector'
import { fmtAmount } from '@/utils/formatters'
import { eventBus, type MaterialityChangedPayload } from '@/utils/eventBus'

const route = useRoute()
const router = useRouter()
const year = computed(() => Number(route.query.year) || new Date().getFullYear())
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

const {
  projectId, selectedProjectId, projectOptions, selectedYear, yearOptions,
  onProjectChange, onYearChange, loadProjectOptions, syncFromRoute,
} = useProjectSelector('materiality')

const autoLoading = ref(false)
const overrideLoading = ref(false)
const result = ref<MaterialityData | null>(null)
const history = ref<any[]>([])

const form = reactive({
  benchmark_type: '',
  benchmark_amount: '',
  is_public_entity: '' as '' | 'yes' | 'no',
  calc_basis: 'unadjusted' as 'forecast' | 'unadjusted' | 'average_3y',
})
const benchmarkNum = ref<number | undefined>(undefined)
const priorYear1 = ref<number | undefined>(undefined)
const priorYear2 = ref<number | undefined>(undefined)
const overallPct = ref(5)
const perfRatio = ref(50)
const trivialRatio = ref(5)

// 特定类别重要性
const specificForm = reactive({
  name: '',
  reason: '',
  amount: undefined as number | undefined,
  te_ratio: 60,
})

// 百分比参考区间提示（按基准类型+是否公开交易）
const suggestedPctRange = computed(() => {
  const isPublic = form.is_public_entity === 'yes'
  switch (form.benchmark_type) {
    case 'pre_tax_profit': return isPublic ? '公开交易：3-5%' : '其他公司：3-10%'
    case 'revenue': return isPublic ? '公开交易：0.25-1%' : '其他公司：0.25-3%'
    case 'total_assets': return isPublic ? '公开交易：0.25-1%' : '其他公司：0.25-2%'
    case 'net_assets': return isPublic ? '公开交易：0.25-2%' : '其他公司：0.25-2%'
    case 'total_expense': return '非营利组织参考：0.25-3%'
    default: return ''
  }
})

// 执行比例提示（参考舞弊风险因素）
const perfRatioHint = computed(() => {
  if (perfRatio.value <= 50) return '较低 — 适用于：前期发现较多错报/舞弊风险较高/经营变化大'
  if (perfRatio.value >= 70) return '较高 — 适用于：前期较少错报/经营平稳/会计系统无变化'
  return ''
})

// 三年趋势预警
const trendWarning = computed(() => {
  if (benchmarkNum.value == null || !priorYear1.value) return ''
  const curr = benchmarkNum.value
  const prior = priorYear1.value
  if (prior === 0) return '上年基准为 0，请确认基准选择是否恰当'
  const changeRate = Math.abs((curr - prior) / prior)
  if (changeRate > 0.5) return `本年较上年变动 ${(changeRate * 100).toFixed(0)}%（超 50%），考虑使用三年平均数或更换基准`
  return ''
})

const overrideForm = reactive({
  overall_materiality: undefined as number | undefined,
  performance_materiality: undefined as number | undefined,
  trivial_threshold: undefined as number | undefined,
  reason: '',
})
const overrideFormRef = ref<FormInstance>()
const overrideRules: FormRules = {
  reason: [{ required: true, message: '请说明覆盖原因', trigger: 'blur' }],
}

// §4 修订
const revisionReason = ref('')

async function submitRevision() {
  if (!revisionReason.value.trim()) return
  // 修订 = 用当前参数重新计算 + 记录修订原因（与覆盖不同：覆盖是手动改金额，修订是重新跑公式）
  await onParamChange()
  if (result.value) {
    // 把修订原因追加到 override 接口（利用 notes 机制记录）
    try {
      await overrideMateriality(projectId.value, year.value, {
        override_reason: `[修订] ${revisionReason.value.trim()}`,
      } as any)
      ElMessage.success('重要性已修订，原因已记入变更历史')
      eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
      revisionReason.value = ''
      fetchHistory()
    } catch { ElMessage.error('修订失败') }
  }
}

const formatAmt = fmtAmount

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
    // 需求 21.1：保存成功后发布事件，触发试算表 exceeds_materiality 刷新
    eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
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
    // 需求 21.1：覆盖成功后发布事件，触发试算表 exceeds_materiality 刷新
    eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
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
  syncFromRoute()
  loadProjectOptions()
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
.gt-materiality { padding: var(--gt-space-5); }

/* ── 页面横幅 ── */
.gt-mat-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 20px 28px;
  margin-bottom: var(--gt-space-5);
  color: var(--gt-color-text-inverse);
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-mat-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-mat-banner-text h2 { margin: 0 0 2px; font-size: var(--gt-font-size-xl); font-weight: 700; }
.gt-mat-banner-text p { margin: 0; font-size: var(--gt-font-size-xs); opacity: 0.75; }
.gt-mat-banner-row1 {
  display: flex; align-items: center; gap: 16px;
  position: relative; z-index: 1;
}
.gt-mat-title { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 700; white-space: nowrap; }
.gt-mat-info-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-mat-info-item { display: flex; align-items: center; gap: 4px; }
.gt-mat-info-label { font-size: var(--gt-font-size-xs); opacity: 0.8; white-space: nowrap; }
.gt-mat-info-badge { font-size: var(--gt-font-size-xs); background: rgba(255,255,255,0.18); padding: 2px 10px; border-radius: 10px; white-space: nowrap; }
.gt-mat-info-sep { width: 1px; height: 16px; background: rgba(255,255,255,0.25); }
.gt-mat-unit-select, .gt-mat-year-select { width: 160px; }
.gt-mat-unit-select :deep(.el-input__wrapper),
.gt-mat-year-select :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.15) !important;
  border: 1px solid rgba(255,255,255,0.25) !important;
  box-shadow: none !important;
}
.gt-mat-unit-select :deep(.el-input__inner),
.gt-mat-year-select :deep(.el-input__inner) { color: var(--gt-color-text-inverse) !important; font-size: var(--gt-font-size-xs); }
.gt-mat-unit-select :deep(.el-input__suffix),
.gt-mat-year-select :deep(.el-input__suffix) { color: rgba(255,255,255,0.7) !important; }

.gt-materiality .gt-page-title {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: var(--gt-space-5);
}
.gt-materiality .gt-page-title::before {
  content: '';
  width: 4px; height: 22px;
  background: var(--gt-gradient-primary);
  border-radius: 2px;
}

.gt-mat-layout { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gt-space-6); }

.gt-mat-form-section {
  background: var(--gt-color-bg-white); padding: var(--gt-space-5);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
}

.gt-mat-result-section { }
.gt-mat-result-cards { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-mat-result-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  text-align: center; box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.04);
  transition: all var(--gt-transition-base);
  position: relative; overflow: hidden;
}
.gt-mat-result-card:hover { transform: translateY(-2px); box-shadow: var(--gt-shadow-md); }
.gt-mat-result-card.gt-mat-result-card--primary {
  border-left: 4px solid var(--gt-color-primary);
}
.gt-mat-result-card.gt-mat-result-card--primary::after {
  content: '';
  position: absolute; top: -20px; right: -20px;
  width: 60px; height: 60px; border-radius: 50%;
  background: var(--gt-color-primary); opacity: 0.05;
}
.gt-mat-result-label { display: block; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); margin-bottom: var(--gt-space-1); font-weight: 500; }
.gt-mat-result-value { display: block; font-size: var(--gt-font-size-2xl); font-weight: 800; color: var(--gt-color-text); letter-spacing: -0.5px; }
.gt-mat-result-card.gt-mat-result-card--primary .gt-mat-result-value {
  background: var(--gt-gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.gt-mat-no-result { text-align: center; color: var(--gt-color-text-tertiary); padding: var(--gt-space-10); }
.gt-mat-history-section { margin-top: var(--gt-space-8); }

/* ── 增强：字段提示 / 三年趋势 / 特定类别 / 修订 ── */
.field-hint {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #6B7280);
  margin-top: 4px;
  line-height: 1.4;
}
.three-year-trend {
  background: #F0F9FF;
  border-left: 3px solid #3B82F6;
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 12px;
}
.trend-title { font-weight: 600; color: #1E40AF; }
.trend-values { display: flex; gap: 16px; margin-top: 4px; }
.trend-warning { color: #D97706; font-weight: 600; margin-top: 4px; }
.specific-mat-section {
  background: #FAFAFA;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 12px;
  margin-top: 4px;
}
.gt-mat-revision-section {
  margin-top: var(--gt-space-6);
  padding: 16px;
  background: #FFFBEB;
  border: 1px solid #F59E0B;
  border-radius: 8px;
}
.revision-hint {
  font-size: 12px;
  color: #92400E;
  line-height: 1.6;
}
.revision-readonly {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}
</style>
