<template>
  <div class="m5-tab-accrual-test">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M5-4 盈余公积计提检查表</h3>
        <GtIndexChip value="M6" :context-project-id="projectId" />
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('accrualTest')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>盈余公积计提检查（公司法第167条）：</strong>
        计提基数 = 净利润 − 弥补以前年度亏损（来自M6未分配利润）。
        法定盈余公积按计提基数的 <strong>10%</strong> 计提。
        累计法定盈余公积达注册资本 <strong>50%</strong> 时可不再计提。
        任意盈余公积由股东大会决议自主计提（无比例限制）。
        计提差异 = 应计提 − 账面计提，超阈值红色高亮。
        本表11公式全部前端实时计算，净利润数据来源于M6底稿EventBus订阅。
      </div>
    </div>

    <!-- ═══ M6数据未就绪警告 ═══ -->
    <el-alert
      v-if="!accrualTest.m6DataReady.value"
      type="warning"
      :closable="false"
      show-icon
      class="m6-warning"
    >
      <template #title>待M6净利润确认</template>
      M6未分配利润净利润/计提基数尚未传入，请先完成M6底稿或手动录入净利润数据。
    </el-alert>

    <!-- ═══ 50%上限提示（绿色tag） ═══ -->
    <el-alert
      v-if="accrualTest.ceilingReached.value"
      type="success"
      :closable="false"
      show-icon
      class="ceiling-alert"
    >
      <template #title>
        <span>累计法定盈余公积已达注册资本50%——可不再计提</span>
        <el-tag type="success" size="small" effect="dark" style="margin-left:8px">已达上限</el-tag>
      </template>
      根据《公司法》第167条，累计法定盈余公积达到注册资本50%时可不再计提。
      当前累计: {{ fmtAmount(accrualTest.accumulatedStatutory.value) }}，
      注册资本50%: {{ fmtAmount(accrualTest.registeredCapital.value * 0.5) }}
    </el-alert>

    <!-- ═══ 计提检查主表（按 Req 4.1 列结构） ═══ -->
    <!-- 列：净利润 | 弥补以前年度亏损 | 计提基数 | 法定计提比例(10%) | 应计提 | 账面计提 | 差异 -->
    <el-table :data="accrualMainRows" border size="small" style="width:100%" class="accrual-main-table">
      <el-table-column prop="label" label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <span :class="{ 'total-row-label': row.isTotal }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="净利润" width="130" align="right">
        <template #header>
          <el-tooltip content="来源: M6未分配利润（EventBus 'm6:net-profit'）" placement="top">
            <span class="formula-col-header">净利润</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.netProfit) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="弥补以前年度亏损" width="150" align="right">
        <template #default="{ row }">{{ fmtAmount(row.priorLossOffset) }}</template>
      </el-table-column>

      <el-table-column label="计提基数" width="130" align="right">
        <template #header>
          <el-tooltip content="公式①: 计提基数 = 净利润 − 弥补以前年度亏损" placement="top">
            <span class="formula-col-header">计提基数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.accrualBase) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="法定计提比例" width="120" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" type="info">{{ row.rateDisplay }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="应计提" width="130" align="right">
        <template #header>
          <el-tooltip content="公式②: 应计提 = 计提基数 × 计提比例" placement="top">
            <span class="formula-col-header">应计提</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.estimated) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="账面计提" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.booked) }}</template>
      </el-table-column>

      <el-table-column label="差异" width="130" align="right">
        <template #header>
          <el-tooltip content="公式③: 差异 = 应计提 − 账面计提（|差异|>阈值红色高亮）" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="{ 'diff-highlight': row.isDiffHighlight }">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 11公式清单（展示前端实时计算覆盖） ═══ -->
    <div class="formula-summary">
      <el-tag size="small" effect="plain" type="info">11公式全部前端实时计算</el-tag>
      <span class="formula-list-hint">
        ①计提基数 ②法定应计提 ③法定差异 ④任意应计提 ⑤任意差异
        ⑥合计应计提 ⑦合计账面 ⑧合计差异 ⑨50%上限判断
        ⑩法定差异高亮 ⑪任意差异高亮
      </span>
    </div>

    <!-- ═══ cross_wp_ref 跨底稿引用区 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref M6联动：</span>
      <GtIndexChip value="M6" :context-project-id="projectId" />
      <span class="cross-wp-desc">未分配利润（净利润/计提基数来源）</span>
      <GtIndexChip value="M5-1" :context-project-id="projectId" />
      <span class="cross-wp-desc">审定表（累计盈余公积来源）</span>
    </div>

    <!-- ═══ 手动输入区（计提参数） ═══ -->
    <el-card shadow="never" class="manual-input-card">
      <template #header>
        <span class="card-title">计提参数输入</span>
      </template>
      <el-form :disabled="isReadonly" label-width="160px" size="small">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="本期净利润">
              <el-input-number
                v-model="localNetProfit"
                :controls="false"
                style="width:100%"
                placeholder="来自M6或手工输入"
                @change="accrualTest.setNetProfit($event ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="弥补以前年度亏损">
              <el-input-number
                v-model="localPriorLoss"
                :controls="false"
                style="width:100%"
                @change="accrualTest.setPriorLossOffset($event ?? 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="法定账面计提">
              <el-input-number
                v-model="localStatBooked"
                :controls="false"
                style="width:100%"
                @change="accrualTest.setStatutoryBooked($event ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任意账面计提">
              <el-input-number
                v-model="localDiscBooked"
                :controls="false"
                style="width:100%"
                @change="accrualTest.setDiscretionaryBooked($event ?? 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="任意计提比例(%)">
              <el-input-number
                v-model="localDiscRate"
                :controls="false"
                :precision="2"
                :step="1"
                :min="0"
                :max="100"
                style="width:100%"
                @change="accrualTest.setDiscretionaryRate(($event ?? 0) / 100)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="累计法定盈余公积">
              <el-input-number
                v-model="localAccumulated"
                :controls="false"
                style="width:100%"
                @change="accrualTest.setAccumulatedStatutory($event ?? 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="注册资本">
              <el-input-number
                v-model="localRegCapital"
                :controls="false"
                style="width:100%"
                @change="accrualTest.setRegisteredCapital($event ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="50%上限状态">
              <el-tag
                :type="accrualTest.ceilingReached.value ? 'success' : 'info'"
                size="default"
                effect="dark"
              >
                {{ accrualTest.ceilingReached.value ? '已达上限·可不再计提' : '未达上限·须继续计提' }}
              </el-tag>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">计提检查结论及说明</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写计提检查结论（如：计提金额准确/差异原因说明等）..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>法定盈余公积：计提基数 = 净利润 − 弥补以前年度亏损，应计提 = 基数 × <strong>10%</strong></li>
        <li>任意盈余公积：由股东大会决议确定计提比例（无法定上限）</li>
        <li>50%上限：累计法定盈余公积 ≥ 注册资本 × 50% 时可不再计提（权利而非义务）</li>
        <li>差异 = 应计提 − 账面计提：正数=少计提需补提，负数=多计提需冲回或说明</li>
        <li>净利润数据来自M6未分配利润底稿（EventBus 'm6:net-profit' 自动推送）</li>
        <li>11公式全部前端实时计算，不依赖后端</li>
        <li>当差异绝对值超过阈值时，差异列红色高亮提示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabAccrualTest — M5-4 盈余公积计提检查表
 *
 * Requirements: 4.1-4.7
 * - 4.1: 显示列：净利润 | 弥补以前年度亏损 | 计提基数 | 法定计提比例(10%) | 应计提 | 账面计提 | 差异
 * - 4.2: 接收M6未分配利润的净利润/计提基数（订阅'm6:net-profit'）
 * - 4.3: 计算应计提法定盈余公积=计提基数×10%
 * - 4.4: 校验累计法定盈余公积达注册资本50%时可不再计提
 * - 4.5: 计算计提差异=应计提-账面计提
 * - 4.6: |计提差异|>阈值时红色高亮
 * - 4.7: 11公式全部前端实时计算
 *
 * 科目：4101 盈余公积（贷方/权益类）
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM5FormData } from '../../composables/useM5FormData'
import { useM5AccrualTest } from '../../composables/useM5AccrualTest'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)

// ─── Composable 初始化 ───────────────────────────────────────────────────────
const formData = useM5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const accrualTest = useM5AccrualTest(formData)

// ─── 本地输入绑定 ────────────────────────────────────────────────────────────
const localNetProfit = ref(0)
const localPriorLoss = ref(0)
const localDiscRate = ref(0)
const localStatBooked = ref(0)
const localDiscBooked = ref(0)
const localAccumulated = ref(0)
const localRegCapital = ref(0)
const auditNote = ref('')

// ─── 同步 composable → local refs（M6 EventBus 推入时自动同步） ──────────────
watch(() => accrualTest.netProfit.value, (v) => { localNetProfit.value = v })
watch(() => accrualTest.priorLossOffset.value, (v) => { localPriorLoss.value = v })

// ─── 主表行结构（Req 4.1 列结构） ───────────────────────────────────────────

interface AccrualMainRow {
  label: string
  netProfit: number
  priorLossOffset: number
  accrualBase: number
  rateDisplay: string
  estimated: number
  booked: number
  diff: number
  isDiffHighlight: boolean
  isTotal: boolean
}

const accrualMainRows = computed<AccrualMainRow[]>(() => {
  const t = accrualTest.testData.value
  return [
    {
      label: '法定盈余公积',
      netProfit: t.netProfit,
      priorLossOffset: t.priorLossOffset,
      accrualBase: t.accrualBase,
      rateDisplay: '10%',
      estimated: t.statutoryEstimated,
      booked: t.statutoryBooked,
      diff: t.statutoryDiff,
      isDiffHighlight: accrualTest.statutoryDiffHighlight.value,
      isTotal: false,
    },
    {
      label: '任意盈余公积',
      netProfit: t.netProfit,
      priorLossOffset: t.priorLossOffset,
      accrualBase: t.accrualBase,
      rateDisplay: t.discretionaryRate > 0 ? `${(t.discretionaryRate * 100).toFixed(1)}%` : '—',
      estimated: t.discretionaryEstimated,
      booked: t.discretionaryBooked,
      diff: t.discretionaryDiff,
      isDiffHighlight: accrualTest.discretionaryDiffHighlight.value,
      isTotal: false,
    },
    {
      label: '合计',
      netProfit: t.netProfit,
      priorLossOffset: t.priorLossOffset,
      accrualBase: t.accrualBase,
      rateDisplay: '—',
      estimated: t.totalEstimated,
      booked: t.totalBooked,
      diff: t.totalDiff,
      isDiffHighlight: accrualTest.statutoryDiffHighlight.value || accrualTest.discretionaryDiffHighlight.value,
      isTotal: true,
    },
  ]
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function handleAI(_section: string) { /* AI钩子 */ }
function handleReview() {
  openReviewDialog?.('M5-4-accrual-test', '盈余公积计提检查')
}
function saveAuditNote() {
  formData.debouncedSave('M5-4-auditNote', { remark: auditNote.value || null })
}

// ─── 生命周期 ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await formData.loadData()
  // 从持久化数据恢复本地值
  const responses = formData.allResponses.value
  const getNum = (key: string): number => {
    const r = responses.get(key)
    return r?.remark ? Number(r.remark) || 0 : 0
  }
  localNetProfit.value = getNum('M5-4-net-profit')
  localPriorLoss.value = getNum('M5-4-prior-loss-offset')
  localStatBooked.value = getNum('M5-4-statutory-booked')
  localDiscBooked.value = getNum('M5-4-discretionary-booked')
  localAccumulated.value = getNum('M5-4-accumulated-statutory')
  localRegCapital.value = getNum('M5-4-registered-capital')
  const discRateResp = responses.get('M5-4-discretionary-rate')
  localDiscRate.value = discRateResp?.remark ? Number(discRateResp.remark) * 100 || 0 : 0
  const noteResp = responses.get('M5-4-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark

  // 同步到 composable
  if (localNetProfit.value) accrualTest.setNetProfit(localNetProfit.value)
  if (localPriorLoss.value) accrualTest.setPriorLossOffset(localPriorLoss.value)
  if (localStatBooked.value) accrualTest.setStatutoryBooked(localStatBooked.value)
  if (localDiscBooked.value) accrualTest.setDiscretionaryBooked(localDiscBooked.value)
  if (localAccumulated.value) accrualTest.setAccumulatedStatutory(localAccumulated.value)
  if (localRegCapital.value) accrualTest.setRegisteredCapital(localRegCapital.value)
  if (localDiscRate.value) accrualTest.setDiscretionaryRate(localDiscRate.value / 100)

  // 主动拉取M6净利润（补充EventBus被动推送，复盘铁律②）
  if (!accrualTest.m6DataReady.value) {
    await accrualTest.fetchM6NetProfit(props.wpId, props.projectId)
    // 同步拉取结果到本地
    if (accrualTest.m6DataReady.value) {
      localNetProfit.value = accrualTest.netProfit.value
      localPriorLoss.value = accrualTest.priorLossOffset.value
    }
  }
})
</script>

<style scoped>
.m5-tab-accrual-test { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* 警告提示 */
.m6-warning { margin-bottom: 12px; }
.ceiling-alert { margin-bottom: 12px; }

/* 公式列虚线下划线+cursor:help */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

/* 差异高亮（红色） */
.diff-highlight { color: #f56c6c; font-weight: 700; }

/* 合计行 */
.total-row-label { font-weight: 700; color: #303133; }

/* 11公式汇总 */
.formula-summary { margin-top: 8px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.formula-list-hint { font-size: 12px; color: #909399; }

/* cross_wp_ref 跨底稿引用 */
.cross-wp-links { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; margin-bottom: 16px; }
.cross-wp-label { font-size: 12px; color: #606266; font-weight: 600; }
.cross-wp-desc { font-size: 12px; color: #909399; }

/* 输入卡片 */
.manual-input-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 审计说明 */
.audit-note-card { margin-top: 16px; }

/* 编制提示 */
.m5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m5-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m5-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m5-details-tip li { margin-bottom: 4px; line-height: 1.5; }

/* 表格 */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.accrual-main-table .el-table__row:last-child) { background: #f0f9eb !important; font-weight: 600; }
:deep(.accrual-main-table .el-table__row:last-child td) { border-top: 2px solid #67c23a; }
</style>
