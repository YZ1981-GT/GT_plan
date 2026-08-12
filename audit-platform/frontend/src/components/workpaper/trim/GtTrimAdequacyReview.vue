<template>
  <div class="gt-trim-review" v-loading="loading">
    <!--
      裁剪充分性复核视图（spec procedure-trimming-and-delegation-intelligence Task 20）

      🔴 本组件**只读**：零 IO、零写入调用。它不 import 任何 api 模块，也不发
         http 请求 —— 复核视图承担的是「看清楚」，改动一律回到裁剪页由有权限的
         角色执行（R12.6）。守卫 trimAdequacyReview.spec.ts 对此有源码级断言：
         组件内不得出现 canonicalTrimApply / rejectTrimSuggestions /
         saveCompletenessScopeOverride / clearCompletenessScopeOverride /
         applyProcedureDelegation / assignProcedures，也不得出现 http.post/put/delete。

      🔴 统计一律由 props 传入的 `review` 派生 —— 那是宿主用 buildTrimAdequacyReview
         （其内部金额汇总走 evaluateAggregateGate、理由码分类走 trimReasonCodes）
         算出来的。本组件**不再自己算任何计数**，否则与裁剪页分叉时无从裁决（R12.7）。
    -->

    <!-- 覆盖面说明：未加载的循环其计数不参与合计，必须显式告知 -->
    <el-alert type="info" :closable="false" class="gt-trim-review__scope">
      <template #title>
        <div class="gt-trim-review__scope-text">
          <span>
            统计口径 = <strong>已落地事实</strong>（程序适用性状态、结构化理由码、驳回留痕）。
            金额汇总与裁剪页那道汇总闸是同一个函数，故同一输入下两处数值逐项相等。
          </span>
          <span v-if="review.unloadedCycles.length > 0" class="gt-trim-review__warn">
            未加载循环 {{ review.unloadedCycles.join(' / ') }}：其计数未参与合计（不是 0）。
          </span>
          <span v-if="review.suggestedDerivableCycles.length < review.cycles.length">
            「待确认」只在裁剪页跑过智能裁剪的循环可派生（当前可派生：{{
              review.suggestedDerivableCycles.length > 0 ? review.suggestedDerivableCycles.join(' / ') : '无'
            }}）；其余循环显示「需打开该循环」而不是 0。
          </span>
        </div>
      </template>
    </el-alert>

    <!-- ── 异常清单（R12.3 / R12.5）───────────────────────────────────────────
         🔴 异常必须把判据写出来，不能只给行上色 —— 复核者要看懂「为什么被标」
            才能判断是否需要退回项目组。每条都能跳转并定位到对应程序。 -->
    <section class="gt-trim-review__section">
      <div class="gt-trim-review__section-head">
        <h4>异常与需关注事项</h4>
        <el-tag v-if="highAnomalies.length > 0" type="danger" size="small" effect="dark">
          审计红线 {{ highAnomalies.length }} 项
        </el-tag>
        <el-tag v-if="mediumAnomalies.length > 0" type="warning" size="small" effect="plain">
          待确认 {{ mediumAnomalies.length }} 项
        </el-tag>
        <el-tag v-if="review.anomalies.length === 0" type="success" size="small" effect="plain">
          未发现异常组合
        </el-tag>
      </div>

      <el-alert
        v-if="review.completenessOverrideUnknown"
        type="warning"
        :closable="false"
        class="gt-trim-review__unknown"
      >
        <template #title>
          <span>
            完整性敏感清单的项目级覆盖状态<strong>未知</strong>（读取失败），
            本次未统计「使用平台默认、未经本项目确认」的循环 ——
            这与「本项目已逐循环确认」不是一回事，请重新打开裁剪页的完整性敏感清单面板确认。
          </span>
        </template>
      </el-alert>

      <div v-if="review.anomalies.length === 0" class="gt-trim-review__empty">
        本次复核范围内未发现「高风险科目被裁」「缺理由的裁剪」「完整性判据未经确认」三类异常组合。
      </div>
      <div v-else class="gt-trim-review__anomalies">
        <div
          v-for="(a, idx) in review.anomalies"
          :key="`${a.kind}-${a.cycle}-${a.wpCode || idx}`"
          class="gt-trim-review__anomaly"
          :class="`is-${a.severity}`"
        >
          <div class="gt-trim-review__anomaly-head">
            <el-tag :type="ANOMALY_TAG_TYPE[a.kind]" size="small" effect="dark">
              {{ ANOMALY_LABEL[a.kind] }}
            </el-tag>
            <span class="gt-trim-review__anomaly-title">{{ a.title }}</span>
            <el-button
              size="small"
              type="primary"
              text
              class="gt-trim-review__anomaly-jump"
              @click="onLocate(a)"
            >{{ a.wpCode ? '跳转并定位该程序 ›' : '打开完整性敏感清单 ›' }}</el-button>
          </div>
          <!-- 判据原文：这是复核者判断的依据，不折叠 -->
          <div class="gt-trim-review__anomaly-detail">{{ a.detail }}</div>
        </div>
      </div>
    </section>

    <!-- ── 因重要性原因裁剪的金额合计 vs 重要性水平（R12.4）───────────────── -->
    <section class="gt-trim-review__section">
      <div class="gt-trim-review__section-head">
        <h4>因金额原因裁剪的汇总评估</h4>
        <el-tag v-if="!review.materiality.materialityAvailable" type="warning" size="small" effect="plain">
          重要性水平未确定
        </el-tag>
        <el-tag v-else-if="review.materiality.confirmedGate.blocked" type="danger" size="small" effect="dark">
          汇总额已达实际执行重要性
        </el-tag>
        <el-tag v-else type="success" size="small" effect="plain">汇总敞口在可容忍范围内</el-tag>
      </div>

      <div class="gt-trim-review__mat">
        <div class="gt-trim-review__mat-grid">
          <div class="gt-trim-review__mat-cell">
            <div class="gt-trim-review__mat-label">已确认金额类裁剪</div>
            <div class="gt-trim-review__mat-num">{{ review.materiality.confirmedCount }} 项</div>
          </div>
          <div class="gt-trim-review__mat-cell">
            <div class="gt-trim-review__mat-label">涉及科目（已去重）</div>
            <div class="gt-trim-review__mat-num">
              {{ review.materiality.confirmedGate.distinctAccountCount }} 个
            </div>
          </div>
          <div class="gt-trim-review__mat-cell">
            <div class="gt-trim-review__mat-label">余额合计</div>
            <div class="gt-trim-review__mat-num">
              {{ fmt(review.materiality.confirmedGate.totalAmount) }} 元
            </div>
          </div>
          <div class="gt-trim-review__mat-cell">
            <div class="gt-trim-review__mat-label">实际执行重要性</div>
            <!-- 🔴 未确定时显示「未确定」，绝不显示 0 元 -->
            <div class="gt-trim-review__mat-num">
              <span v-if="review.materiality.performanceMateriality !== null">
                {{ fmt(review.materiality.performanceMateriality) }} 元
              </span>
              <span v-else class="gt-trim-review__muted">未确定</span>
            </div>
          </div>
          <div v-if="review.materiality.amountUnknownCount > 0" class="gt-trim-review__mat-cell is-unknown">
            <div class="gt-trim-review__mat-label">其中金额无法定位</div>
            <div class="gt-trim-review__mat-num">{{ review.materiality.amountUnknownCount }} 项</div>
          </div>
        </div>
        <div class="gt-trim-review__mat-narrative">{{ review.materiality.narrative }}</div>
        <div
          v-if="review.materiality.suggestedGate.distinctAccountCount > 0"
          class="gt-trim-review__mat-pending"
        >
          待确认建议的汇总闸：{{ review.materiality.suggestedGate.narrative }}
        </div>
      </div>
    </section>

    <!-- ── 理由码分布（R12.2）──────────────────────────────────────────────── -->
    <section class="gt-trim-review__section">
      <div class="gt-trim-review__section-head">
        <h4>裁剪理由分布</h4>
        <span class="gt-trim-review__muted">
          系统判据裁剪需复核判据数值；人工判断裁剪需复核理由是否充分；存量记录只有自由文本。
        </span>
      </div>
      <div v-if="review.reasonDistribution.length === 0" class="gt-trim-review__empty">
        本项目尚无已裁剪的程序，无理由分布可统计。
      </div>
      <el-table
        v-else
        :data="review.reasonDistribution"
        size="small"
        border
        style="font-size: 13px"
      >
        <el-table-column label="理由" min-width="260">
          <template #default="{ row }">
            <el-tag :type="REASON_KIND_TAG[row.kind]" size="small" effect="plain">
              {{ REASON_KIND_LABEL[row.kind] }}
            </el-tag>
            <span class="gt-trim-review__reason-label">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="理由码" min-width="160">
          <template #default="{ row }">
            <code v-if="row.code" class="gt-trim-review__code">{{ row.code }}</code>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="程序数" width="90" align="center">
          <template #default="{ row }">
            <strong>{{ row.count }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="占已裁剪" width="110" align="center">
          <template #default="{ row }">
            <span v-if="review.totals.trimmed > 0">
              {{ Math.round(row.count / review.totals.trimmed * 100) }}%
            </span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ── 各循环计数（R12.1）─────────────────────────────────────────────── -->
    <section class="gt-trim-review__section">
      <div class="gt-trim-review__section-head">
        <h4>各循环裁剪计数</h4>
        <span class="gt-trim-review__muted">点击行跳转对应循环</span>
      </div>
      <el-table
        :data="review.cycles"
        size="small"
        border
        style="font-size: 13px"
        :row-class-name="cycleRowClass"
        @row-click="onCycleRowClick"
      >
        <el-table-column prop="label" label="循环" min-width="130" />
        <el-table-column label="总程序" width="82" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded">{{ row.total }}</span>
            <span v-else class="gt-trim-review__muted">未加载</span>
          </template>
        </el-table-column>
        <el-table-column label="保留" width="72" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded" class="gt-trim-review__keep">{{ row.keep }}</span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="已裁" width="72" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded" class="gt-trim-review__trim">{{ row.trimmed }}</span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="建议待确认" width="112" align="center">
          <template #default="{ row }">
            <!-- 🔴 null = 不可派生 ⇒ 显示提示文字，不显示 0 -->
            <span v-if="row.suggested !== null" class="gt-trim-review__suggest">{{ row.suggested }}</span>
            <el-tooltip
              v-else-if="row.loaded"
              content="建议态是未落库的中间状态，只在裁剪页对该循环跑过智能裁剪后才可派生"
              placement="top"
            >
              <span class="gt-trim-review__muted">需打开该循环</span>
            </el-tooltip>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="缺理由" width="82" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.loaded && row.missingReason > 0" type="danger" size="small">
              {{ row.missingReason }}
            </el-tag>
            <span v-else class="gt-trim-review__muted">{{ row.loaded ? 0 : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="系统判据裁" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded">{{ row.machineTrimmed }}</span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="人工判据裁" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded">{{ row.manualTrimmed }}</span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="已驳回" width="82" align="center">
          <template #default="{ row }">
            <span v-if="row.loaded">{{ row.rejected }}</span>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="76" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.anomalyCount > 0" type="danger" size="small" effect="dark">
              {{ row.anomalyCount }}
            </el-tag>
            <span v-else class="gt-trim-review__muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="gt-trim-review__totals">
        <span>合计（仅已加载循环）：</span>
        <span>总 <strong>{{ review.totals.total }}</strong></span>
        <span>保留 <strong class="gt-trim-review__keep">{{ review.totals.keep }}</strong></span>
        <span>已裁 <strong class="gt-trim-review__trim">{{ review.totals.trimmed }}</strong></span>
        <span>
          建议待确认
          <strong v-if="review.totals.suggested !== null" class="gt-trim-review__suggest">
            {{ review.totals.suggested }}
          </strong>
          <strong v-else class="gt-trim-review__muted">不可派生</strong>
        </span>
        <span v-if="review.totals.missingReason > 0">
          缺理由 <strong class="gt-trim-review__danger">{{ review.totals.missingReason }}</strong>
        </span>
        <span v-if="review.totals.legacyTextOnly > 0">
          仅自由文本 <strong>{{ review.totals.legacyTextOnly }}</strong>
        </span>
        <span v-if="review.totals.rejected > 0">已驳回 <strong>{{ review.totals.rejected }}</strong></span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 裁剪充分性复核视图（只读）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 20
 * Requirements: 12.1 / 12.2 / 12.3 / 12.4 / 12.5 / 12.6 / 12.7
 *
 * 🔴 只读是本组件的承重属性，不是风格偏好：复核视图若能改数据，复核者就同时是
 *    执行者，「独立复核」这件事在流程上就不成立了。故本文件**不 import 任何 api
 *    模块**（连 commonApi 都不引），也不引 http —— 缺少写入能力比"约定不写"可靠。
 *
 * 定位（R12.5）只发 `locate` 事件，由宿主 ProcedureTrimming.vue 完成切循环 +
 * 过滤定位。组件自己不碰路由，也不改宿主状态。
 */
import { computed } from 'vue'
import type { ReviewAnomaly, ReviewAnomalyKind, TrimAdequacyReview } from '../composables/trimAdequacyReview'

const props = defineProps<{
  review: TrimAdequacyReview
  loading?: boolean
}>()

const emit = defineEmits<{
  /** 跳转并定位；`wpCode` 为 null 时表示打开完整性敏感清单面板 */
  (e: 'locate', payload: { cycle: string; wpCode: string | null; kind: ReviewAnomalyKind }): void
  /** 仅切换循环（点击循环行） */
  (e: 'jump-cycle', cycle: string): void
}>()

const ANOMALY_LABEL: Readonly<Record<ReviewAnomalyKind, string>> = {
  risk_protected_trimmed: '高风险科目被裁',
  missing_reason: '缺理由的裁剪',
  platform_default_completeness: '完整性判据未经确认',
}

const ANOMALY_TAG_TYPE: Readonly<Record<ReviewAnomalyKind, 'danger' | 'warning'>> = {
  risk_protected_trimmed: 'danger',
  missing_reason: 'danger',
  platform_default_completeness: 'warning',
}

const REASON_KIND_LABEL: Readonly<Record<string, string>> = {
  machine: '系统判据',
  manual: '人工判断',
  legacy_text: '存量文本',
  missing: '缺理由',
}

const REASON_KIND_TAG: Readonly<Record<string, 'success' | 'info' | 'warning' | 'danger'>> = {
  machine: 'success',
  manual: 'info',
  legacy_text: 'warning',
  missing: 'danger',
}

const highAnomalies = computed(() => props.review.anomalies.filter(a => a.severity === 'high'))
const mediumAnomalies = computed(() => props.review.anomalies.filter(a => a.severity === 'medium'))

/** 金额格式化（千分符 + 两位小数）—— 复核视图为只读展示，不涉及录入。 */
function fmt(value: number | null): string {
  if (value === null || !Number.isFinite(Number(value))) return '—'
  const num = Number(value)
  const negative = num < 0
  const fixed = Math.abs(num).toFixed(2)
  const dot = fixed.indexOf('.')
  const grouped = fixed.slice(0, dot).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}.${fixed.slice(dot + 1)}`
}

function onLocate(a: ReviewAnomaly) {
  emit('locate', { cycle: a.cycle, wpCode: a.wpCode, kind: a.kind })
}

function onCycleRowClick(row: { cycle: string; loaded: boolean }) {
  if (!row?.loaded) return
  emit('jump-cycle', row.cycle)
}

function cycleRowClass({ row }: { row: { loaded: boolean; anomalyCount: number } }): string {
  if (!row?.loaded) return 'gt-trim-review-row--unloaded'
  return row.anomalyCount > 0 ? 'gt-trim-review-row--anomaly' : ''
}
</script>

<style scoped>
.gt-trim-review { font-size: 13px; }
.gt-trim-review__scope { margin-bottom: 12px; }
.gt-trim-review__scope-text { display: flex; flex-direction: column; gap: 3px; font-size: 12px; line-height: 1.7; }
.gt-trim-review__warn { color: var(--el-color-warning); }

.gt-trim-review__section { margin-bottom: 18px; }
.gt-trim-review__section-head {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;
}
.gt-trim-review__section-head h4 {
  margin: 0; font-size: 14px; font-weight: 700; color: var(--gt-color-text-primary);
}
.gt-trim-review__muted { color: var(--gt-color-text-tertiary); font-size: 12px; }
.gt-trim-review__empty {
  padding: 10px 12px; border-radius: 4px; font-size: 12px;
  color: var(--gt-color-text-secondary); background: var(--el-fill-color-lighter);
}
.gt-trim-review__unknown { margin-bottom: 8px; }

/* 异常卡：判据原文常显，不折叠 —— 只给颜色看不出为什么被标 */
.gt-trim-review__anomalies { display: flex; flex-direction: column; gap: 8px; }
.gt-trim-review__anomaly {
  padding: 8px 10px; border-radius: 4px;
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.gt-trim-review__anomaly.is-high {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}
.gt-trim-review__anomaly-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-trim-review__anomaly-title { font-weight: 600; color: var(--gt-color-text-primary); }
.gt-trim-review__anomaly-jump { margin-left: auto; }
.gt-trim-review__anomaly-detail {
  margin-top: 4px; font-size: 12px; line-height: 1.75;
  color: var(--gt-color-text-secondary);
}

/* 重要性对比 */
.gt-trim-review__mat {
  padding: 10px 12px; border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
.gt-trim-review__mat-grid {
  display: flex; flex-wrap: wrap; gap: 10px 24px; margin-bottom: 8px;
}
.gt-trim-review__mat-cell { min-width: 132px; }
.gt-trim-review__mat-cell.is-unknown .gt-trim-review__mat-num { color: var(--el-color-warning); }
.gt-trim-review__mat-label { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-trim-review__mat-num {
  font-size: 16px; font-weight: 700; color: var(--gt-color-text-primary);
  font-variant-numeric: tabular-nums;
}
.gt-trim-review__mat-narrative {
  font-size: 12px; line-height: 1.75; color: var(--gt-color-text-secondary);
  padding-top: 6px; border-top: 1px dashed var(--el-border-color-lighter);
}
.gt-trim-review__mat-pending {
  margin-top: 6px; font-size: 12px; line-height: 1.75; color: var(--el-color-warning);
}

.gt-trim-review__reason-label { margin-left: 6px; }
.gt-trim-review__code {
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 12px; color: var(--gt-color-text-secondary);
}

.gt-trim-review__keep { color: var(--gt-color-primary); }
.gt-trim-review__trim { color: var(--gt-color-coral); }
.gt-trim-review__suggest { color: var(--el-color-warning); }
.gt-trim-review__danger { color: var(--el-color-danger); }

.gt-trim-review__totals {
  display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px;
  padding: 6px 10px; border-radius: 4px; font-size: 12px;
  background: var(--el-fill-color-lighter); color: var(--gt-color-text-secondary);
}

/* 表格金额列防折行（平台级铁律） */
.gt-trim-review :deep(.el-table td.is-right .cell) {
  white-space: nowrap; font-variant-numeric: tabular-nums;
}
.gt-trim-review :deep(.gt-trim-review-row--anomaly) { background: var(--el-color-danger-light-9); }
.gt-trim-review :deep(.gt-trim-review-row--unloaded) { color: var(--gt-color-text-tertiary); }
.gt-trim-review :deep(.el-table__row) { cursor: pointer; }
</style>
