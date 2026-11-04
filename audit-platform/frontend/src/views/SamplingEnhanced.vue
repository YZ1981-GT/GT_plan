<template>
  <div class="gt-sampling-enhanced gt-fade-in">
    <GtPageHeader title="审计抽样" :show-back="false" />
    <!-- 年度取项目审计年度，没填不按日历猜：各页签都不查询，给去填的入口（spec voucher-workflow-linkage-lineage-closure R4.4） -->
    <el-alert v-if="auditYear == null" type="warning" :closable="false" show-icon class="year-missing"
      data-testid="sampling-year-missing" title="项目未填审计年度">
      各页签按审计年度取数，填写前不查询。
      <el-button link type="primary" @click="goFillAuditYear">去填写审计年度</el-button>
    </el-alert>
    <el-tabs v-model="activeTab">
      <!-- 项目级抽凭概览：当前账套版本的存续核对未确认数（任务 17，需求 8.3）；切到本页签才加载（R4.5） -->
      <el-tab-pane label="抽凭概览" name="voucher">
        <div class="voucher-overview-toolbar">
          <el-input-number v-model="voucherYear" :min="YEAR_MIN" :max="yearMax" aria-label="抽凭概览年度" />
          <el-button :loading="voucherLoading" :disabled="voucherYear == null" @click="loadVoucherOverview">刷新</el-button>
          <span v-if="voucherOverview?.active_dataset_id" class="overview-hint">
            当前账套 {{ String(voucherOverview.active_dataset_id).slice(0, 8) }}
          </span>
        </div>
        <el-alert v-if="voucherError" type="error" :closable="false" show-icon class="overview-error"
          data-testid="sampling-overview-error" :title="`抽凭概览读取失败：${voucherError}`">
          <el-button size="small" :loading="voucherLoading" @click="loadVoucherOverview">重试</el-button>
        </el-alert>
        <el-alert v-else-if="voucherOverview?.note" type="info" :closable="false" show-icon class="overview-error"
          :title="voucherOverview.note" />
        <el-table v-loading="voucherLoading" :data="voucherOverview?.by_workpaper ?? []" stripe size="small"
          data-testid="sampling-overview-table"
          :empty-text="voucherError ? '读取失败，点「重试」重新读取' : '暂无抽凭或存续核对记录'">
          <el-table-column prop="wp_code" label="底稿编码" width="110" />
          <el-table-column prop="wp_name" label="底稿名称" min-width="220" />
          <el-table-column prop="batch_count" label="抽凭批次" width="100" align="right" />
          <el-table-column prop="sample_count" label="样本数" width="90" align="right" />
          <el-table-column label="预审样本存续核对" min-width="250">
            <template #default="{ row }">
              <template v-if="row.interim_survival_counts">
                <el-tag v-if="row.interim_survival_unacked > 0" type="danger" effect="plain">
                  {{ row.interim_survival_unacked }} 条变化未确认
                </el-tag>
                <el-tag v-else type="success" effect="plain">已核对，无待确认变化</el-tag>
                <span class="overview-hint">
                  未变 {{ row.interim_survival_counts.unchanged }} / 已改 {{ row.interim_survival_counts.modified }} /
                  疑似改号 {{ row.interim_survival_counts.renumbered }} / 已删 {{ row.interim_survival_counts.deleted }}
                </span>
              </template>
              <span v-else class="overview-hint">尚未在当前账套核对</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button v-if="row.working_paper_id" link type="primary" @click="openWorkpaper(row.working_paper_id)">
                打开底稿
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <template v-if="voucherOverview?.duplicated?.length">
          <el-alert
            type="warning"
            :closable="false"
            :title="`另有 ${voucherOverview.duplicated.length} 张凭证被多张底稿抽取，请结合抽凭目的复核是否有意重复`"
            class="overview-duplicate"
          />
          <el-table :data="voucherOverview.duplicated" size="small" class="overview-duplicate-table"
            data-testid="sampling-overview-duplicated">
            <el-table-column label="凭证" min-width="160">
              <template #default="{ row }">{{ row.voucher_date || '无日期' }} {{ voucherLabel(row.voucher_type, row.voucher_no) }}</template>
            </el-table-column>
            <el-table-column prop="workpaper_count" label="抽取底稿数" width="110" align="right" />
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-button v-if="ledgerRouteOf(row)" link type="primary" @click="openLedger(row)">序时账</el-button>
                <span v-else class="overview-hint">{{ row.legacy ? '旧登记没有凭证日期' : '登记时没有科目' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-tab-pane>
      <!-- 截止性测试 -->
      <el-tab-pane label="截止性测试" name="cutoff">
        <el-form :model="cutoffForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="科目编码"><el-input v-model="cutoffForm.codes" placeholder="多个用逗号分隔，如 6001,6401" /></el-form-item>
          <el-form-item label="年度"><el-input-number v-model="cutoffForm.year" :min="YEAR_MIN" :max="yearMax" /></el-form-item>
          <el-form-item label="期末前天数"><el-input-number v-model="cutoffForm.days_before" :min="1" :max="30" /></el-form-item>
          <el-form-item label="期末后天数"><el-input-number v-model="cutoffForm.days_after" :min="1" :max="30" /></el-form-item>
          <el-form-item label="金额阈值"><el-input-number v-model="cutoffForm.threshold" :min="0" :step="1000" /></el-form-item>
          <el-form-item><el-button type="primary" v-permission="'sampling:execute'" :disabled="cutoffForm.year == null" @click="runCutoff" :loading="loading">执行</el-button></el-form-item>
        </el-form>
        <el-table v-if="cutoffResult" :data="cutoffResult.entries" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="voucher_date" label="日期" width="100" />
          <el-table-column prop="voucher_no" label="凭证号" width="100" />
          <el-table-column prop="account_code" label="科目" width="100" />
          <el-table-column prop="debit_amount" label="借方" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.debit_amount" /></template>
          </el-table-column>
          <el-table-column prop="credit_amount" label="贷方" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.credit_amount" /></template>
          </el-table-column>
          <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
          <el-table-column label="截止" width="80">
            <template #default="{ row }"><el-tag :type="row.is_before_cutoff ? 'success' : 'danger'" size="small">{{ row.is_before_cutoff ? '期内' : '期后' }}</el-tag></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <!-- 账龄分析 -->
      <el-tab-pane label="账龄分析" name="aging">
        <el-form :model="agingForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="科目编码"><el-input v-model="agingForm.account_code" placeholder="如 1122" /></el-form-item>
          <el-form-item label="基准日"><el-date-picker v-model="agingForm.base_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="账龄区间">
            <div v-for="(b, i) in agingForm.brackets" :key="i" style="display:flex;gap:8px;margin-bottom:4px">
              <el-input v-model="b.label" placeholder="标签" style="width:120px" />
              <el-input-number v-model="b.min_days" :min="0" placeholder="起始天" />
              <el-input-number v-model="b.max_days" placeholder="结束天" />
              <el-button text type="danger" @click="agingForm.brackets.splice(i, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="agingForm.brackets.push({ label: '', min_days: 0, max_days: null })">添加区间</el-button>
          </el-form-item>
          <el-form-item><el-button type="primary" :disabled="!agingForm.base_date" @click="runAging" :loading="loading">分析</el-button></el-form-item>
        </el-form>
        <el-table v-if="agingResult" :data="agingResult.details" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="aux_name" label="辅助维度" width="160" />
          <el-table-column prop="total_balance" label="余额合计" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.total_balance" /></template>
          </el-table-column>
          <el-table-column v-for="b in agingResult.summary" :key="b.label" :label="b.label" align="right">
            <template #default="{ row }">{{ row.brackets?.find((x: any) => x.label === b.label)?.amount ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <!-- 月度明细 -->
      <el-tab-pane label="月度明细" name="monthly">
        <el-form :model="monthlyForm" label-width="100px" style="max-width: 400px" inline>
          <el-form-item label="科目"><el-input v-model="monthlyForm.account_code" /></el-form-item>
          <el-form-item label="年度"><el-input-number v-model="monthlyForm.year" :min="YEAR_MIN" :max="yearMax" /></el-form-item>
          <el-form-item><el-button type="primary" :disabled="monthlyForm.year == null" @click="runMonthly" :loading="loading">查询</el-button></el-form-item>
        </el-form>
        <el-table v-if="monthlyResult" :data="monthlyResult.months" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="period" label="月份" width="80" />
          <el-table-column prop="debit_total" label="借方合计" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.debit_total" /></template>
          </el-table-column>
          <el-table-column prop="credit_total" label="贷方合计" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.credit_total" /></template>
          </el-table-column>
          <el-table-column prop="net_change" label="净变动" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.net_change" /></template>
          </el-table-column>
          <el-table-column prop="cumulative" label="累计" width="120" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.cumulative" /></template>
          </el-table-column>
          <el-table-column prop="entry_count" label="笔数" width="80" align="right" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/utils/http'
import { cutoffTest, agingAnalysis, monthlyDetail } from '@/services/commonApi'
import { useProjectStore } from '@/stores/project'
import { fetchProjectAuditPhase } from '@/composables/useProjectAuditPhase'
import { resolveAuditYearOrNull } from '@/utils/resolveAuditYear'
import { migrationPendingMessage } from '@/utils/migrationPending'
import { voucherLabel } from '@/utils/voucherIdentity'
import { ledgerRouteOfVoucherKey, workpaperRouteFromLedger } from '@/utils/voucherLedgerRoute'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

interface DuplicatedVoucher {
  voucher_key: string | null
  voucher_no: string
  voucher_date: string | null
  voucher_type: string | null
  account_code?: string | null
  workpaper_count: number
  legacy: boolean
}

const route = useRoute()
const router = useRouter()
const projectId = ref(route.params.projectId as string || '')
const projectStore = useProjectStore()
const activeTab = ref('cutoff')
const loading = ref(false)

// ─── 审计年度与审计期末（R4.4）：年度只取项目的，没填为 null（不按日历猜）─────────────
const YEAR_MIN = 2001
const auditPeriodEnd = ref<string | null>(null)
const auditYear = computed(() => resolveAuditYearOrNull({
  routeYear: route.query?.year, storeYear: projectStore.year, periodEnd: auditPeriodEnd.value,
}))
// 年度下拉上限：审计年度与今年取大再加一（原先写死 2030）
const yearMax = computed(() => Math.max(auditYear.value ?? 0, new Date().getFullYear()) + 1)

/** 账龄基准日默认值：审计期末（与所选年度同年才用），否则所选年度的 12-31；没有年度为空 */
function defaultBaseDate(year: number | null): string {
  if (year == null) return ''
  const end = auditPeriodEnd.value?.slice(0, 10) ?? ''
  return end.startsWith(`${year}-`) ? end : `${year}-12-31`
}

const voucherYear = ref<number | null>(null)
const cutoffForm = ref({ codes: '6001', year: null as number | null, days_before: 5, days_after: 5, threshold: 10000 })
const cutoffResult = ref<any>(null)
const agingForm = ref({
  account_code: '1122', base_date: '',
  brackets: [
    { label: '1年以内', min_days: 0, max_days: 365 as number | null },
    { label: '1-2年', min_days: 366, max_days: 730 as number | null },
    { label: '2-3年', min_days: 731, max_days: 1095 as number | null },
    { label: '3年以上', min_days: 1096, max_days: null as number | null },
  ],
})
const agingResult = ref<any>(null)
const monthlyForm = ref({ account_code: '6001', year: null as number | null })
const monthlyResult = ref<any>(null)

// 基准日只在还是上一次默认值时跟着换（用户改过的不覆盖）
let lastDefaultBaseDate = ''
function applyDefaultBaseDate() {
  const next = defaultBaseDate(auditYear.value)
  if (agingForm.value.base_date === lastDefaultBaseDate) agingForm.value.base_date = next
  lastDefaultBaseDate = next
}
watch(auditYear, (year) => {
  voucherYear.value = year
  cutoffForm.value.year = year
  monthlyForm.value.year = year
  applyDefaultBaseDate()
}, { immediate: true })
watch(auditPeriodEnd, applyDefaultBaseDate)

onMounted(async () => {
  if (!projectId.value) return
  try {
    auditPeriodEnd.value = (await fetchProjectAuditPhase(projectId.value)).auditPeriodEnd
  } catch { /* 取不到审计期末：基准日按年度 12-31 */ }
})

function goFillAuditYear() {
  void router.push({ name: 'ProjectSettingsCenter', params: { projectId: projectId.value }, query: { tab: 'standard' } })
}

// ─── 抽凭概览（R4.5）：切到本页签才加载；失败显示原因与重试；行上打开底稿 / 序时账 ────────
const voucherLoading = ref(false)
const voucherOverview = ref<any>(null)
const voucherError = ref<string | null>(null)
const voucherLoaded = ref(false)
let overviewSeq = 0

/** 读取失败的原因：后端给的中文原因原样显示；迁移未执行单独说明；都没有时按状态说 */
function overviewErrorText(err: unknown): string {
  const pending = migrationPendingMessage(err)
  if (pending) return pending
  const res = (err as { response?: { status?: number; data?: any } } | null)?.response
  const raw = res?.data?.detail ?? res?.data?.message
  const text = typeof raw === 'string' ? raw : (raw && typeof raw === 'object' ? String(raw.message ?? '') : '')
  if (text) return text
  if (!res) return '网络连接失败，请检查网络'
  return res.status === 403 ? '没有本项目的查看权限' : `服务返回错误（状态码 ${res.status}）`
}

async function loadVoucherOverview() {
  if (!projectId.value || voucherYear.value == null) return
  const seq = ++overviewSeq
  voucherLoading.value = true
  voucherError.value = null
  // 先清掉上一次的结果：改了年度再读失败时，表里不能还是别的年度的行（浏览器实测发现）
  voucherOverview.value = null
  try {
    const res = await http.get(`/api/projects/${projectId.value}/sampling/voucher-coverage`, {
      params: { year: voucherYear.value }, _silent: true, _dedupe: false,
    } as any)
    if (seq !== overviewSeq) return
    voucherOverview.value = res?.data?.data ?? res?.data ?? res
    voucherLoaded.value = true
  } catch (err) {
    if (seq === overviewSeq) voucherError.value = overviewErrorText(err)
  } finally {
    if (seq === overviewSeq) voucherLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'voucher' && !voucherLoaded.value && !voucherLoading.value) void loadVoucherOverview()
}, { immediate: true })

function openWorkpaper(workpaperId: string) {
  void router.push(workpaperRouteFromLedger(projectId.value, workpaperId))
}

function ledgerRouteOf(row: DuplicatedVoucher) {
  return ledgerRouteOfVoucherKey(projectId.value, row.voucher_key, { accountCode: row.account_code })
}

function openLedger(row: DuplicatedVoucher) {
  const target = ledgerRouteOf(row)
  if (target) void router.push(target)
}

// ─── 截止性测试 / 账龄分析 / 月度明细 ─────────────────────────────────────────────
async function runCutoff() {
  const year = cutoffForm.value.year
  if (year == null) return
  loading.value = true
  try {
    cutoffResult.value = await cutoffTest(projectId.value, {
      account_codes: cutoffForm.value.codes.split(',').map(s => s.trim()),
      year, days_before: cutoffForm.value.days_before,
      days_after: cutoffForm.value.days_after, amount_threshold: cutoffForm.value.threshold,
    })
  } finally { loading.value = false }
}
async function runAging() {
  if (!agingForm.value.base_date) return
  loading.value = true
  try {
    agingResult.value = await agingAnalysis(projectId.value, {
      account_code: agingForm.value.account_code, base_date: agingForm.value.base_date,
      aging_brackets: agingForm.value.brackets,
    })
  } finally { loading.value = false }
}
async function runMonthly() {
  const year = monthlyForm.value.year
  if (year == null) return
  loading.value = true
  try { monthlyResult.value = await monthlyDetail(projectId.value, { account_code: monthlyForm.value.account_code, year }) }
  finally { loading.value = false }
}
</script>
<style scoped>
.gt-sampling-enhanced { padding: var(--gt-space-4); }
.gt-page-header { margin-bottom: var(--gt-space-3); }
.year-missing { margin-bottom: var(--gt-space-3); }
.voucher-overview-toolbar { display: flex; align-items: center; gap: var(--gt-space-2); margin-bottom: var(--gt-space-3); }
.overview-hint { margin-left: var(--gt-space-2); color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); }
.overview-error { margin-bottom: var(--gt-space-3); }
.overview-duplicate { margin-top: var(--gt-space-3); }
.overview-duplicate-table { margin-top: var(--gt-space-2); }
</style>
