<template>
  <div class="gt-materiality gt-fade-in">
    <!-- 页面横幅 -->
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
      <!-- 操作按钮放默认插槽（row1 flex 行）推右 -->
      <div class="gt-mat-header-actions">
        <el-button
          v-if="previewDirty"
          :loading="saveLoading"
          class="gt-mat-save-btn"
          @click="doSave"
        >💾 保存</el-button>
        <GtToolbar :show-edit-toggle="true" :is-editing="isEditing" @edit-toggle="isEditing ? exitEdit() : enterEdit()" />
      </div>
    </GtPageHeader>

    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <div class="gt-mat-layout">
      <!-- 左侧：配置表单 -->
      <div class="gt-mat-form-section">
        <el-form :model="form" label-width="130px" label-position="right">
          <!-- §1 是否公开交易实体 -->
          <el-form-item label="是否公开交易实体">
            <el-radio-group v-model="form.is_public_entity" @change="onPreviewChange">
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

          <!-- 基准选择合理性编制提示 -->
          <details v-if="form.benchmark_type && form.benchmark_type !== 'custom'" class="benchmark-guidance">
            <summary>📋 基准选择合理性编制提示（CAS1221）</summary>
            <div class="guidance-body">
              <template v-if="form.benchmark_type === 'pre_tax_profit'">
                <p><strong>适用：</strong>盈利稳定的营利性实体（首选）</p>
                <p><strong>不适用：</strong>亏损/利润波动>50%/收入确认存在舞弊风险</p>
                <p><strong>判断：</strong>①扣除非经常性项目后是否仍为正 ②前期是否稳定 ③是否可能被操纵</p>
              </template>
              <template v-else-if="form.benchmark_type === 'revenue'">
                <p><strong>适用：</strong>亏损企业/利润波动大/收入稳定增长</p>
                <p><strong>不适用：</strong>收入确认存在重大舞弊风险/含大量一次性项目</p>
                <p><strong>判断：</strong>①代表经营规模 ②各年稳定 ③收入政策是否激进</p>
              </template>
              <template v-else-if="form.benchmark_type === 'total_assets'">
                <p><strong>适用：</strong>资产密集型（金融/房地产/基础设施）</p>
                <p><strong>不适用：</strong>轻资产/商誉占比过高</p>
              </template>
              <template v-else-if="form.benchmark_type === 'net_assets'">
                <p><strong>适用：</strong>投资控股/基金/资本密集型</p>
                <p><strong>不适用：</strong>负净资产/受重估值大幅波动</p>
              </template>
              <template v-else-if="form.benchmark_type === 'total_expense'">
                <p><strong>适用：</strong>非营利组织/政府资助实体</p>
                <p><strong>不适用：</strong>普通营利性企业</p>
              </template>
            </div>
          </details>

          <!-- 计算基础 -->
          <el-form-item label="计算基础">
            <el-radio-group v-model="form.calc_basis" @change="onCalcBasisChange">
              <el-radio value="forecast">本年预测数</el-radio>
              <el-radio value="unadjusted">年末未审数</el-radio>
              <el-radio value="average_3y">三年平均数</el-radio>
            </el-radio-group>
          </el-form-item>

          <!-- 三年趋势对比 -->
          <div v-if="form.benchmark_type && form.benchmark_type !== 'custom' && (priorYear1 != null || priorYear2 != null)" class="three-year-trend">
            <span class="trend-title">三年趋势对比：</span>
            <div class="trend-values">
              <span>本年: {{ formatAmtWithUnit(benchmarkNum) }}</span>
              <span>上年: {{ formatAmtWithUnit(priorYear1) }}</span>
              <span>前年: {{ formatAmtWithUnit(priorYear2) }}</span>
            </div>
            <div v-if="trendWarning" class="trend-warning">⚠️ {{ trendWarning }}</div>
          </div>

          <el-form-item label="基准金额">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-input-number v-model="benchmarkNum" :precision="2" :controls="false"
                placeholder="基准金额" style="flex: 1" @change="onPreviewChange" />
              <el-button v-if="form.benchmark_type !== 'custom'" plain :loading="autoLoading"
                @click="autoPopulate">从试算表取数</el-button>
            </div>
            <div v-if="form.calc_basis === 'forecast'" class="field-hint" style="color:#D97706">⚠️ 预测数需手工填入</div>
          </el-form-item>

          <el-form-item label="整体百分比(%)">
            <el-input-number v-model="overallPct" :min="0" :max="100" :precision="2" :step="0.5"
              style="width: 100%" @change="onPreviewChange" />
            <div class="field-hint">{{ suggestedPctRange }}</div>
            <!-- 超出建议区间告警 -->
            <div v-if="pctExceedsRange" class="pct-warning">⚠️ 当前百分比超出建议区间上限({{ maxSuggestedPct }}%)，请确认合理性并记录理由</div>
          </el-form-item>

          <el-form-item label="执行比例(%)">
            <el-slider v-model="perfRatio" :min="45" :max="75" :step="5" show-input @change="onPreviewChange" />
            <div class="field-hint">CAS: 45%~75%。{{ perfRatioHint }}</div>
          </el-form-item>

          <el-form-item label="微小比例(%)">
            <el-input-number v-model="trivialRatio" :min="0" :max="5" :precision="2" :step="0.5"
              style="width: 100%" @change="onPreviewChange" />
            <div class="field-hint">CAS: ≤5% 整体重要性</div>
          </el-form-item>

          <!-- 多条特定类别重要性 -->
          <el-divider content-position="left">特定类别重要性（如适用）</el-divider>
          <div class="specific-mat-section">
            <div class="field-hint" style="margin-bottom:8px">如有特定交易/余额/披露需单独确定重要性水平，可添加多条。</div>
            <div v-for="(cat, idx) in specificCategories" :key="idx" class="specific-cat-row">
              <el-form-item :label="`#${idx + 1} 名称`">
                <div style="display:flex;gap:8px;width:100%">
                  <el-input v-model="cat.name" placeholder="如：关联方交易" style="flex:1" @change="onPreviewChange" />
                  <el-button type="danger" text size="small" @click="removeSpecificCategory(idx)">删除</el-button>
                </div>
              </el-form-item>
              <el-form-item label="原因">
                <el-input v-model="cat.reason" type="textarea" :autosize="{minRows:1,maxRows:2}" placeholder="确定原因..." @change="onPreviewChange" />
              </el-form-item>
              <el-form-item label="PM金额">
                <el-input-number v-model="cat.amount" :precision="2" :controls="false" style="width:50%" @change="onPreviewChange" />
              </el-form-item>
              <el-form-item label="TE比例(%)">
                <el-input-number v-model="cat.te_ratio" :min="45" :max="75" :precision="0" style="width:50%" @change="onPreviewChange" />
              </el-form-item>
              <el-divider v-if="idx < specificCategories.length - 1" style="margin:8px 0" />
            </div>
            <el-button type="primary" text @click="addSpecificCategory">+ 新增特定类别</el-button>
          </div>
        </el-form>
      </div>

      <!-- 右侧：结果卡片 -->
      <div class="gt-mat-result-section">
        <!-- 预览计算结果（纯前端，不写库） -->
        <div v-if="previewResult" class="gt-mat-result-cards">
          <div class="gt-mat-result-card gt-mat-result-card--primary">
            <span class="gt-mat-result-label">整体重要性 (PM)</span>
            <span class="gt-mat-result-value">{{ formatAmtWithUnit(previewResult.overall) }}</span>
            <span class="gt-mat-result-formula">= {{ formatAmtWithUnit(benchmarkNum) }} × {{ overallPct }}%</span>
          </div>
          <div class="gt-mat-result-card">
            <span class="gt-mat-result-label">实际执行重要性 (TE)</span>
            <span class="gt-mat-result-value">{{ formatAmtWithUnit(previewResult.performance) }}</span>
            <span class="gt-mat-result-formula">= PM × {{ perfRatio }}%</span>
          </div>
          <div class="gt-mat-result-card">
            <span class="gt-mat-result-label">明显微小错报 (SAT)</span>
            <span class="gt-mat-result-value">{{ formatAmtWithUnit(previewResult.trivial) }}</span>
            <span class="gt-mat-result-formula">= PM × {{ trivialRatio }}%</span>
          </div>
          <div v-if="previewDirty" class="preview-dirty-hint">⚡ 预览值（尚未保存）</div>
        </div>
        <div v-else class="gt-mat-no-result">
          <div style="font-size:24px;margin-bottom:8px;opacity:0.3">📊</div>
          请配置参数后查看预览
        </div>

        <!-- B50 风险面板 -->
        <div v-if="previewResult" class="b50-risk-panel">
          <div class="b50-risk-panel__header"><span>B50 风险↔执行比例参考</span></div>
          <div class="b50-risk-panel__body">
            <div class="b50-risk-hint">
              <span v-if="perfRatio <= 50" class="risk-tag risk-tag--high">较保守(≤50%)</span>
              <span v-else-if="perfRatio >= 70" class="risk-tag risk-tag--low">较宽松(≥70%)</span>
              <span v-else class="risk-tag risk-tag--mid">适中({{ perfRatio }}%)</span>
            </div>
            <ul class="b50-risk-criteria">
              <li :class="{ active: perfRatio <= 55 }">前期审计发现较多错报 → 建议 45-55%</li>
              <li :class="{ active: perfRatio <= 50 }">存在舞弊风险(B50特别风险) → 建议 45-50%</li>
              <li :class="{ active: perfRatio >= 65 }">连续审计+经营平稳+会计系统无变化 → 可考虑 65-75%</li>
            </ul>
          </div>
        </div>

        <!-- 手动覆盖 -->
        <el-collapse v-if="result" style="margin-top: 16px">
          <el-collapse-item title="手动覆盖（可选）" name="override">
            <el-form :model="overrideForm" label-width="130px">
              <el-form-item label="整体重要性">
                <el-input-number v-model="overrideForm.overall_materiality" :precision="2" :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="执行重要性">
                <el-input-number v-model="overrideForm.performance_materiality" :precision="2" :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="微小错报">
                <el-input-number v-model="overrideForm.trivial_threshold" :precision="2" :controls="false" placeholder="留空使用计算值" style="width: 100%" />
              </el-form-item>
              <el-form-item label="覆盖原因">
                <el-input v-model="overrideForm.reason" type="textarea" :rows="2" placeholder="请说明覆盖原因" />
              </el-form-item>
              <el-form-item>
                <el-button type="warning" :disabled="!overrideForm.reason" :loading="overrideLoading" @click="submitOverride">确认覆盖</el-button>
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <!-- §4 重要性修订 -->
    <div class="gt-mat-revision-section" v-if="result">
      <h3 class="gt-section-title">§4 重要性修订（审计过程中）</h3>
      <div class="revision-hint">CAS1221 第十二条：审计过程中获知新信息导致需修订时，应修订重要性水平并记录原因。</div>
      <el-form v-if="isEditing" label-width="100px" style="margin-top:12px">
        <el-form-item label="修订原因">
          <el-input v-model="revisionReason" type="textarea" :autosize="{minRows:2,maxRows:4}" placeholder="说明修订依据..." />
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :disabled="!revisionReason.trim()" @click="submitRevision">修订重要性</el-button>
        </el-form-item>
      </el-form>
      <div v-else class="revision-readonly">进入编辑模式可修订重要性。</div>
    </div>

    <!-- 变更历史（含变更明细） -->
    <div class="gt-mat-history-section" v-if="history.length">
      <h3 class="gt-section-title">变更历史</h3>
      <el-table :data="history" size="small" :row-class-name="historyRowClass" style="width:100%">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div v-if="row.changes && Object.keys(row.changes).length" class="history-detail">
              <div v-for="(change, field) in row.changes" :key="field" class="history-detail-item">
                <span class="history-field">{{ fieldLabel(field) }}：</span>
                <span class="history-old">{{ change.old || '—' }}</span>
                <span class="history-arrow"> → </span>
                <span class="history-new">{{ change.new || '—' }}</span>
              </div>
            </div>
            <div v-else class="history-detail">无变更明细</div>
          </template>
        </el-table-column>
        <el-table-column prop="changed_at" label="时间" width="170">
          <template #default="{ row }">
            <span style="font-size:12px;color:#6b7280">{{ row.changed_at ? row.changed_at.replace('T', ' ').slice(0, 19) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="overall_materiality" label="整体重要性" width="130" align="right">
          <template #default="{ row }">{{ formatAmtWithUnit(row.overall_materiality) }}</template>
        </el-table-column>
        <el-table-column prop="performance_materiality" label="执行重要性" width="130" align="right">
          <template #default="{ row }">{{ formatAmtWithUnit(row.performance_materiality) }}</template>
        </el-table-column>
        <el-table-column prop="trivial_threshold" label="微小错报" width="130" align="right">
          <template #default="{ row }">{{ formatAmtWithUnit(row.trivial_threshold) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useEditMode } from '@/composables/useEditMode'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import {
  getMateriality, calculateMateriality, overrideMateriality,
  getMaterialityHistory, getMaterialityBenchmark,
  type MaterialityData,
} from '@/services/auditPlatformApi'
import { useProjectSelector } from '@/composables/useProjectSelector'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { eventBus, type MaterialityChangedPayload } from '@/utils/eventBus'

const route = useRoute()
const router = useRouter()
const year = computed(() => Number(route.query.year) || new Date().getFullYear())
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()
const prefs = useDisplayPrefsStore()

const {
  projectId, selectedProjectId, projectOptions, selectedYear, yearOptions,
  onProjectChange, onYearChange, loadProjectOptions, syncFromRoute,
} = useProjectSelector('materiality')

const autoLoading = ref(false)
const overrideLoading = ref(false)
const saveLoading = ref(false)
const result = ref<MaterialityData | null>(null)
const history = ref<any[]>([])
const previewDirty = ref(false)

const form = reactive({
  benchmark_type: '',
  benchmark_amount: '',
  is_public_entity: '' as '' | 'yes' | 'no',
  calc_basis: 'unadjusted' as 'forecast' | 'unadjusted' | 'average_3y',
})
const benchmarkNum = ref<number | undefined>(undefined)
const priorYear1 = ref<number | null>(null)
const priorYear2 = ref<number | null>(null)
const overallPct = ref(5)
const perfRatio = ref(50)
const trivialRatio = ref(5)

// 多条特定类别
interface SpecificCategory { name: string; reason: string; amount: number | undefined; te_ratio: number }
const specificCategories = ref<SpecificCategory[]>([])
function addSpecificCategory() { specificCategories.value.push({ name: '', reason: '', amount: undefined, te_ratio: 60 }) }
function removeSpecificCategory(idx: number) { specificCategories.value.splice(idx, 1); onPreviewChange() }

// ── 预览/保存分离 ──
// 纯前端预览计算（不写库）
const previewResult = computed(() => {
  if (!benchmarkNum.value || !overallPct.value) return null
  const overall = benchmarkNum.value * overallPct.value / 100
  const performance = overall * perfRatio.value / 100
  const trivial = overall * trivialRatio.value / 100
  return {
    overall: Math.round(overall * 100) / 100,
    performance: Math.round(performance * 100) / 100,
    trivial: Math.round(trivial * 100) / 100,
  }
})

function onPreviewChange() { previewDirty.value = true }

// 显式保存才写库
async function doSave() {
  if (!projectId.value || !form.benchmark_type || !benchmarkNum.value || !overallPct.value) return
  saveLoading.value = true
  try {
    result.value = await calculateMateriality(projectId.value, year.value, {
      benchmark_type: form.benchmark_type,
      benchmark_amount: String(benchmarkNum.value),
      overall_percentage: String(overallPct.value),
      performance_ratio: String(perfRatio.value),
      trivial_ratio: String(trivialRatio.value),
      notes: buildNotes(),
    })
    previewDirty.value = false
    ElMessage.success('重要性水平已保存')
    eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
    fetchHistory()
  } catch { ElMessage.error('保存失败') }
  finally { saveLoading.value = false }
}

// ── 格式化 ──
function formatAmtWithUnit(val: number | string | null | undefined): string {
  if (val == null || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return '—'
  return `${prefs.fmtAmount(num)} 元`
}

// ── 百分比建议区间 + 超范围告警 ──
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

const maxSuggestedPct = computed(() => {
  const isPublic = form.is_public_entity === 'yes'
  switch (form.benchmark_type) {
    case 'pre_tax_profit': return isPublic ? 5 : 10
    case 'revenue': return isPublic ? 1 : 3
    case 'total_assets': return isPublic ? 1 : 2
    case 'net_assets': return 2
    case 'total_expense': return 3
    default: return 100
  }
})

const pctExceedsRange = computed(() => overallPct.value > maxSuggestedPct.value && form.benchmark_type !== 'custom')

// ── 执行比例提示 ──
const perfRatioHint = computed(() => {
  if (perfRatio.value <= 50) return '较低 — 前期多错报/舞弊风险高/经营变化大'
  if (perfRatio.value >= 70) return '较高 — 前期少错报/经营平稳/无系统变化'
  return ''
})

// ── 三年趋势预警 ──
const trendWarning = computed(() => {
  if (benchmarkNum.value == null || priorYear1.value == null) return ''
  const curr = benchmarkNum.value
  const prior = priorYear1.value
  if (prior === 0) return '上年基准为 0，请确认基准选择是否恰当'
  const changeRate = Math.abs((curr - prior) / prior)
  if (changeRate > 0.5) return `本年较上年变动 ${(changeRate * 100).toFixed(0)}%（超 50%），考虑使用三年平均数或更换基准`
  return ''
})

// ── 覆盖 ──
const overrideForm = reactive({
  overall_materiality: undefined as number | undefined,
  performance_materiality: undefined as number | undefined,
  trivial_threshold: undefined as number | undefined,
  reason: '',
})

const revisionReason = ref('')

// ── 变更历史字段标签 ──
function fieldLabel(field: string): string {
  const map: Record<string, string> = {
    benchmark_type: '基准类型', benchmark_amount: '基准金额',
    overall_percentage: '整体百分比', overall_materiality: '整体重要性',
    performance_ratio: '执行比例', performance_materiality: '执行重要性',
    trivial_ratio: '微小比例', trivial_threshold: '微小错报',
  }
  return map[field] || field
}
function historyRowClass({ row }: { row: any }) {
  return row.reason?.startsWith('[修订]') ? 'history-revision-row' : ''
}

// ── notes 持久化(含特定类别+配置选项) ──
function buildNotes(): string {
  const payload: Record<string, any> = {}
  // 特定类别
  const cats = specificCategories.value.filter(c => c.name || c.amount)
  if (cats.length) payload.specific_categories = cats
  // 配置选项持久化
  if (form.is_public_entity) payload.is_public_entity = form.is_public_entity
  if (form.calc_basis) payload.calc_basis = form.calc_basis
  return Object.keys(payload).length ? JSON.stringify(payload) : ''
}

function parseNotesOnLoad(notes: string | null) {
  if (!notes) return
  try {
    const parsed = JSON.parse(notes)
    if (parsed?.specific_categories?.length) {
      specificCategories.value = parsed.specific_categories
    }
    if (parsed?.is_public_entity) form.is_public_entity = parsed.is_public_entity
    if (parsed?.calc_basis) form.calc_basis = parsed.calc_basis
  } catch { /* non-JSON notes, ignore */ }
}

// ── API 操作 ──
async function onBenchmarkTypeChange() {
  if (form.benchmark_type && form.benchmark_type !== 'custom') await autoPopulate()
  onPreviewChange()
}

async function onCalcBasisChange() {
  if (form.benchmark_type && form.benchmark_type !== 'custom') await autoPopulate()
  onPreviewChange()
}

async function autoPopulate() {
  if (!projectId.value || !form.benchmark_type) return
  autoLoading.value = true
  try {
    const resp = await getMaterialityBenchmark(projectId.value, year.value, form.benchmark_type, form.calc_basis)
    if (resp.benchmark_amount != null) {
      benchmarkNum.value = Number(resp.benchmark_amount)
      form.benchmark_amount = String(benchmarkNum.value)
    }
    priorYear1.value = resp.prior_year_1 != null ? Number(resp.prior_year_1) : null
    priorYear2.value = resp.prior_year_2 != null ? Number(resp.prior_year_2) : null
  } catch { /* interceptor */ }
  finally { autoLoading.value = false }
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
    previewDirty.value = false
    eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
    fetchHistory()
  } catch { /* interceptor */ }
  finally { overrideLoading.value = false }
}

async function submitRevision() {
  if (!revisionReason.value.trim()) return
  await doSave()
  if (result.value) {
    try {
      await overrideMateriality(projectId.value, year.value, { override_reason: `[修订] ${revisionReason.value.trim()}` } as any)
      ElMessage.success('重要性已修订')
      eventBus.emit('materiality:changed', { projectId: projectId.value, year: year.value } as MaterialityChangedPayload)
      revisionReason.value = ''
      fetchHistory()
    } catch { ElMessage.error('修订失败') }
  }
}

async function fetchHistory() {
  try { history.value = await getMaterialityHistory(projectId.value, year.value) } catch { /* ignore */ }
}

onMounted(async () => {
  syncFromRoute()
  loadProjectOptions()
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
      parseNotesOnLoad(existing.notes)
    }
  } catch { /* no existing */ }
  if (form.benchmark_type && form.benchmark_type !== 'custom') autoPopulate()
  fetchHistory()
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════
   B15 重要性水平 — 美化重写
   基准：13px 字号 / EP CSS 变量 / 平台视觉语言
   ═══════════════════════════════════════════════════════ */
.gt-materiality {
  padding: 20px 24px;
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
}

/* ── 两栏布局 ── */
.gt-mat-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 24px;
  align-items: start;
}
@media (max-width: 1100px) { .gt-mat-layout { grid-template-columns: 1fr; } }

/* ── 左侧：配置表单 ── */
.gt-mat-form-section {
  background: #fff;
  padding: 24px 28px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02);
  border: 1px solid #f0f0f0;
}
.gt-mat-form-section :deep(.el-form-item) {
  margin-bottom: 16px;
}
.gt-mat-form-section :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}
.gt-mat-form-section :deep(.el-input-number),
.gt-mat-form-section :deep(.el-input),
.gt-mat-form-section :deep(.el-select) {
  font-size: 13px;
}
.gt-mat-form-section :deep(.el-radio__label) {
  font-size: 13px;
}
.gt-mat-form-section :deep(.el-divider__text) {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary, #4b2d77);
}

/* ── 右侧结果卡片 ── */
.gt-mat-result-section {
  position: sticky;
  top: 80px;
}
.gt-mat-result-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-mat-result-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px 24px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.06);
  border: 1px solid #f3f0f7;
  transition: transform 0.2s, box-shadow 0.2s;
  position: relative;
  overflow: hidden;
}
.gt-mat-result-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #e8e0f0, #d4c8e8);
  opacity: 0.6;
}
.gt-mat-result-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(75, 45, 119, 0.1);
}
.gt-mat-result-card.gt-mat-result-card--primary {
  border: none;
  background: linear-gradient(135deg, #f8f5fc 0%, #f0ebf7 100%);
  box-shadow: 0 4px 16px rgba(75, 45, 119, 0.12);
}
.gt-mat-result-card.gt-mat-result-card--primary::before {
  height: 4px;
  background: linear-gradient(90deg, #6b3fa0, #4b2d77);
  opacity: 1;
}
.gt-mat-result-label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
  font-weight: 500;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.gt-mat-result-value {
  display: block;
  font-size: 26px;
  font-weight: 800;
  color: #1f2937;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.5px;
}
.gt-mat-result-card.gt-mat-result-card--primary .gt-mat-result-value {
  background: linear-gradient(135deg, #6b3fa0, #4b2d77);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-size: 28px;
}
.gt-mat-result-formula {
  display: block;
  font-size: 11px;
  color: #9ca3af;
  margin-top: 6px;
  font-style: italic;
}
.gt-mat-no-result {
  text-align: center;
  color: #9ca3af;
  padding: 60px 20px;
  font-size: 13px;
  background: #fafafa;
  border-radius: 12px;
  border: 1px dashed #e5e7eb;
}
.preview-dirty-hint {
  text-align: center;
  font-size: 11px;
  color: #d97706;
  margin-top: 10px;
  font-weight: 600;
  padding: 4px 12px;
  background: #fffbeb;
  border-radius: 6px;
  border: 1px solid #fde68a;
}

/* ── 字段提示文本 ── */
.field-hint {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 4px;
  line-height: 1.5;
}
.pct-warning {
  font-size: 11px;
  color: #dc2626;
  font-weight: 600;
  margin-top: 6px;
  background: #fef2f2;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #fecaca;
}

/* ── 三年趋势面板 ── */
.three-year-trend {
  background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
  border-left: 3px solid #3b82f6;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 14px;
  font-size: 12px;
}
.trend-title { font-weight: 600; color: #1e40af; }
.trend-values { display: flex; gap: 16px; margin-top: 6px; color: #374151; }
.trend-warning { color: #d97706; font-weight: 600; margin-top: 6px; font-size: 11px; }

/* ── 特定类别区块 ── */
.specific-mat-section {
  background: #fafbfc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px 16px;
}
.specific-cat-row { margin-bottom: 4px; }

/* ── §4 重要性修订区块 ── */
.gt-mat-revision-section {
  margin-top: 24px;
  padding: 18px 20px;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 1px solid #fbbf24;
  border-left: 4px solid #f59e0b;
  border-radius: 10px;
}
.gt-mat-revision-section .gt-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #78350f;
  margin: 0 0 8px;
}
.revision-hint { font-size: 12px; color: #92400e; line-height: 1.6; }
.revision-readonly { font-size: 12px; color: #9ca3af; font-style: italic; margin-top: 8px; }

/* ── 基准选择合理性编制提示 ── */
.benchmark-guidance {
  margin-bottom: 14px;
  border: 1px solid #fde68a;
  border-left: 4px solid #f59e0b;
  border-radius: 8px;
  background: linear-gradient(135deg, #fffbeb, #fef9e7);
  font-size: 12px;
}
.benchmark-guidance summary {
  padding: 8px 14px;
  cursor: pointer;
  font-weight: 600;
  color: #92400e;
  user-select: none;
}
.benchmark-guidance .guidance-body {
  padding: 6px 14px 14px;
  color: #78350f;
  line-height: 1.7;
}
.benchmark-guidance .guidance-body p { margin: 3px 0; }

/* ── B50 风险面板 ── */
.b50-risk-panel {
  margin-top: 16px;
  border: 1px solid #e8e0f0;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.b50-risk-panel__header {
  background: linear-gradient(135deg, #f8f5fc, #f3f0f7);
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #4b2d77;
  border-bottom: 1px solid #e8e0f0;
}
.b50-risk-panel__body { padding: 14px; }
.b50-risk-hint { margin-bottom: 10px; }
.risk-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}
.risk-tag--high { background: #fee2e2; color: #991b1b; }
.risk-tag--mid { background: #fef3c7; color: #92400e; }
.risk-tag--low { background: #d1fae5; color: #065f46; }
.b50-risk-criteria {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 11px;
  color: #6b7280;
}
.b50-risk-criteria li {
  padding: 5px 0 5px 10px;
  border-left: 2px solid transparent;
  transition: all 0.15s;
  border-radius: 0 4px 4px 0;
}
.b50-risk-criteria li.active {
  border-left-color: #4b2d77;
  color: #1f2937;
  font-weight: 500;
  background: rgba(75, 45, 119, 0.03);
}

/* ── 变更历史 ── */
.gt-mat-history-section {
  margin-top: 28px;
}
.gt-mat-history-section .gt-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 14px;
  padding-bottom: 10px;
  border-bottom: 2px solid #f3f0f7;
}
.gt-mat-history-section :deep(.el-table) {
  font-size: 12px;
  border-radius: 8px;
  overflow: hidden;
}
.gt-mat-history-section :deep(.el-table th) {
  background: #f9fafb !important;
  font-weight: 600;
  color: #374151;
  font-size: 12px;
}
.gt-mat-history-section :deep(.el-table td) {
  font-size: 12px;
  padding: 8px 12px;
}
.gt-mat-history-section :deep(.el-table .cell) {
  font-variant-numeric: tabular-nums;
}
.history-detail { padding: 10px 16px; font-size: 12px; background: #f9fafb; border-radius: 6px; }
.history-detail-item { margin: 5px 0; display: flex; align-items: center; gap: 6px; }
.history-field { font-weight: 600; color: #374151; min-width: 80px; }
.history-old { color: #dc2626; text-decoration: line-through; font-size: 11px; }
.history-arrow { color: #9ca3af; font-size: 11px; }
.history-new { color: #059669; font-weight: 600; }
:deep(.history-revision-row) { background: #fffbeb !important; }

/* ── 横幅内操作按钮（默认插槽推右） ── */
.gt-mat-header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.gt-mat-save-btn {
  background: rgba(255, 255, 255, 0.95) !important;
  color: var(--el-color-primary, #4b2d77) !important;
  border: none !important;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 16px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.gt-mat-save-btn:hover {
  background: #fff !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* ── 编辑模式横幅 ── */
.gt-edit-mode-ribbon {
  background: linear-gradient(90deg, #eff6ff, #e0f2fe);
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 8px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  font-weight: 500;
  color: #1e40af;
  display: flex;
  align-items: center;
  gap: 6px;
}
.gt-edit-mode-icon { font-size: 14px; }

/* ── el-collapse 手动覆盖 ── */
:deep(.el-collapse) {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
:deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 600;
  padding: 12px 16px;
  background: #f9fafb;
}
:deep(.el-collapse-item__content) {
  padding: 16px;
  font-size: 13px;
}
</style>
