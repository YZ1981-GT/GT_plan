<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">试算平衡表</h1>
      <span class="aud-header__note">标准科目口径：未审数 + 已批准的调整分录 = 审定数</span>
    </header>

    <nav class="aud-tabs">
      <button
        v-for="item in TABS"
        :key="item.key"
        type="button"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === item.key }"
        @click="tab = item.key"
      >{{ item.label }}</button>
    </nav>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="sheet-caption">
          <h2 class="sheet-caption__title">{{ tab === 'audited' ? '审定科目余额表' : '底稿取数余额表' }}</h2>
          <p class="sheet-caption__period">所属期间：{{ year }}年1月—12月</p>
          <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：元</span></div>
        </div>

        <div class="citar-toolbar">
          <input v-model.trim="keyword" class="citar-search" type="search" placeholder="按科目编码或名称筛选" />
          <label v-if="tab === 'source'" class="citar-check"><input v-model="nonZeroOnly" type="checkbox" /> 只看有数科目</label>
          <span class="citar-toolbar__count">共 {{ shown.length }} 个科目</span>
          <button class="citar-btn" type="button" :disabled="loading || recalcing" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="recalcing" @click="recalc">
            {{ recalcing ? '重算中…' : '重算试算表' }}
          </button>
        </div>

        <div ref="scrollRef" class="sheet-scroll">
          <!-- 审定科目余额表：两层表头，看得出「原值 + 调整 = 调整后」 -->
          <table v-if="tab === 'audited'" class="sheet-table aud-table">
            <thead>
              <tr class="group-row">
                <th v-for="g in AUDITED_TRIAL_BALANCE_GROUPS" :key="g.label" :colspan="g.columns.length">{{ g.label }}</th>
              </tr>
              <tr class="column-row">
                <template v-for="g in AUDITED_TRIAL_BALANCE_GROUPS" :key="g.label">
                  <th v-for="(c, i) in g.columns" :key="c.key" :class="columnClass(c, i)">{{ c.label }}</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in shown" :key="r.code" :data-locate="r.code" :class="{ 'citar-located': isLocated(r.code) }">
                <td class="is-seq">{{ i + 1 }}</td>
                <td class="is-code">{{ r.code }}</td>
                <td>{{ r.name }}</td>
                <td class="group-start citar-center">{{ r.opening.dir }}</td>
                <td class="is-numeric" :data-src="`${r.code}:opening`">{{ fmtMoney(r.opening.amount) }}</td>
                <td class="is-numeric is-adjustment" :data-src="`${r.code}:opening_adj`">-</td>
                <td class="is-numeric" :data-src="`${r.code}:opening`">{{ fmtMoney(r.opening.amount) }}</td>
                <td class="group-start is-numeric" :data-src="`${r.code}:period_debit`">{{ fmtMoney(r.periodDebit) }}</td>
                <td class="is-numeric is-adjustment" :data-src="`${r.code}:adj_debit`">{{ fmtMoney(r.adjDebit) }}</td>
                <td class="is-numeric" :data-src="`${r.code}:period_credit`">{{ fmtMoney(r.periodCredit) }}</td>
                <td class="is-numeric is-adjustment" :data-src="`${r.code}:adj_credit`">{{ fmtMoney(r.adjCredit) }}</td>
                <td class="group-start citar-center">{{ r.adjClosing.dir }}</td>
                <td
                  class="is-numeric"
                  :class="{ 'citar-tb__editable': canManualEdit }"
                  :data-src="`${r.code}:adj_closing`"
                  @click="openAdjust(r)"
                >
                  {{ fmtMoney(r.adjClosing.amount) }}<sup v-if="r.wp" class="citar-mark">底稿</sup><sup v-if="pending.get(r.code)" class="citar-mark citar-mark--pending">待批 {{ pending.get(r.code) }}</sup>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 底稿取数余额表：全部标准科目，本期发生额含审计调整，期末为审定数 -->
          <table v-else class="sheet-table">
            <thead>
              <tr><th v-for="c in TRIAL_BALANCE_COLUMNS" :key="c.key">{{ c.label }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in shown" :key="r.code" :data-locate="r.code" :class="{ 'citar-located': isLocated(r.code) }">
                <td class="is-seq">{{ i + 1 }}</td>
                <td class="is-code">{{ r.code }}</td>
                <td>{{ r.name }}</td>
                <td class="citar-center">{{ r.opening.dir }}</td>
                <td class="is-numeric" :data-src="`${r.code}:opening`">{{ fmtMoney(r.opening.amount) }}</td>
                <td class="is-numeric" :data-src="`${r.code}:src_debit`">{{ fmtMoney(r.periodDebit + r.adjDebit) }}</td>
                <td class="is-numeric" :data-src="`${r.code}:src_credit`">{{ fmtMoney(r.periodCredit + r.adjCredit) }}</td>
                <td class="citar-center">{{ r.audited.dir }}</td>
                <td class="is-numeric" :class="{ 'citar-tb__editable': canManualEdit }" :data-src="`${r.code}:audited`" @click="openAdjust(r)">
                  {{ fmtMoney(r.audited.amount) }}<sup v-if="pending.get(r.code)" class="citar-mark citar-mark--pending">待批 {{ pending.get(r.code) }}</sup>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="loading" class="sheet-empty">正在读取试算平衡表…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>
        <p v-else-if="!shown.length" class="sheet-empty">{{ rows.length ? '没有符合筛选条件的科目' : '本年度还没有试算表数据，请先导入账套' }}</p>
        <ul v-else class="citar-footnotes">
          <li v-if="tab === 'audited'">只列有发生额、余额或调整的科目。审计调整只计已批准的调整分录；期初调整平台暂无来源，按 0 列示。</li>
          <li v-else>按平台标准科目表列示（{{ rows.length }} 个科目，含零余额）。本期借方 / 贷方含已批准的审计调整；期末余额是试算表审定数，平台审计底稿读这一列（损益类为本期发生额）；税审底稿取数读科目余额表导入数，不含审计调整。</li>
          <li>标「底稿」的科目含从底稿审定表发布的调整。悬停金额可查看数据来源。</li>
          <li v-if="canManualEdit">点审定数可修改：按差额生成调整分录草稿（标「待批」），复核批准后进入试算表；期初与本期发生额请在「账务查询 → 科目余额表」修改。</li>
          <li v-else>{{ MANUAL_EDIT_DENIED_TIP }}</li>
        </ul>
      </template>
    </section>

    <CitarTbAdjustDialog
      :account="adjusting"
      :project-id="projectId"
      :year="year ?? 0"
      :account-names="accountNames"
      @close="adjusting = null"
      @created="onAdjustCreated"
    />

    <CitarSourceCard
      :state="hover.card.value"
      :label="cardLabel"
      @open="openSourceLink"
      @enter="hover.onCardEnter"
      @leave="hover.onCardLeave"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 试算平衡表（CITAR「审定科目余额表 / 底稿取数余额表」版式，接平台试算表）。
 * 数据：GET /trial-balance/standard-view（借正贷负）；重算：POST /trial-balance/recalc。
 * 审定数可点开修改（spec citar-table-manual-edit R2）：按差额生成调整分录草稿，不直接改试算表。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { accountChart as P_chart, adjustments as P_adj, cellSources as P_src, trialBalance as P_tb } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { ADJUSTMENT_STATUS } from '@/constants/statusEnum'
import CitarSourceCard from '../components/CitarSourceCard.vue'
import CitarTbAdjustDialog, { type TbAdjustAccount } from '../components/CitarTbAdjustDialog.vue'
import { cellSourceLink, localSource, type CellSource, type CellSourceLink, type CellSourceResponse } from '../cellSource'
import { useCellSourceHover } from '../useCellSourceHover'
import { AUDITED_TRIAL_BALANCE_GROUPS, TRIAL_BALANCE_COLUMNS, type AuditedColumnGroup } from '../data/reportLines'
import { fmtMoney, splitDirection, useCitarProject } from '../useCitarProject'
import { normCode, useCitarRowLocate } from '../useCitarRowLocate'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

defineOptions({ name: 'CitarTrialBalance' })

interface ViewRow {
  standard_account_code: string
  account_name: string
  opening_balance: string
  period_debit: string
  period_credit: string
  adjustment_debit: string
  adjustment_credit: string
  wp_adjustment: string
  adjusted_closing_balance: string
  /** 平台审定数（自然正数口径）：底稿取数读的就是它 */
  audited_amount: string | null
  direction: 'debit' | 'credit'
}

type TabKey = 'audited' | 'source'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'audited', label: '审定科目余额表' },
  { key: 'source', label: '底稿取数余额表' },
]

const { projectId, year, yearLoading, entityName, goSegment } = useCitarProject()
const { canManualEdit } = useManualEditPermission()

const tab = ref<TabKey>('audited')
const rows = ref<ViewRow[]>([])
const loading = ref(false)
const recalcing = ref(false)
const error = ref('')
const keyword = ref('')
const nonZeroOnly = ref(false)

const prepared = computed(() =>
  rows.value.map(r => {
    const periodDebit = Number(r.period_debit) || 0
    const periodCredit = Number(r.period_credit) || 0
    const adjDebit = Number(r.adjustment_debit) || 0
    const adjCredit = Number(r.adjustment_credit) || 0
    const wp = Number(r.wp_adjustment) || 0
    const opening = splitDirection(r.opening_balance)
    const adjClosing = splitDirection(r.adjusted_closing_balance)
    // 审定数是自然正数口径：贷方科目转成借正贷负再分方向
    const audited = splitDirection(
      r.audited_amount === null ? r.adjusted_closing_balance : (r.direction === 'credit' ? -1 : 1) * (Number(r.audited_amount) || 0),
    )
    const hasValue = [opening.amount, periodDebit, periodCredit, adjDebit, adjCredit, wp, adjClosing.amount, audited.amount].some(v => Math.abs(v) >= 0.005)
    return {
      audited,
      code: r.standard_account_code,
      name: r.account_name,
      opening,
      periodDebit,
      periodCredit,
      adjDebit,
      adjCredit,
      wp,
      adjClosing,
      hasValue,
    }
  }),
)

const shown = computed(() => {
  const kw = keyword.value
  return prepared.value.filter(r => {
    if (kw && !r.code.includes(kw) && !r.name.includes(kw)) return false
    // 审定科目余额表只列有数科目；底稿取数余额表默认全列
    if ((tab.value === 'audited' || nonZeroOnly.value) && !r.hasValue) return false
    return true
  })
})

/** 按列性质给宽度类名；每组第一列加左边界，三组的分界才看得出 */
function columnClass(c: AuditedColumnGroup['columns'][number], index: number) {
  let width = ''
  if (c.key === 'seq') width = 'col-seq'
  else if (c.key === 'accountCode') width = 'col-code'
  else if (c.key === 'accountName') width = 'col-name'
  else if (c.key.endsWith('Direction')) width = 'col-direction'
  else if (c.numeric) width = 'col-amount'
  return [width, c.adjustment ? 'is-adjustment' : '', index === 0 ? 'group-start' : ''].filter(Boolean)
}

// ── 改审定数 → 调整分录草稿（spec citar-table-manual-edit R2） ──
type PreparedRow = (typeof prepared.value)[number]

const adjusting = ref<TbAdjustAccount | null>(null)
/** 科目 → 未批准（草稿 / 待复核 / 驳回）的调整分录组数 */
const pending = ref<Map<string, number>>(new Map())
const accountNames = ref<Map<string, string>>(new Map())
const SILENT = { _silent: true } as any
const PENDING_STATUSES = new Set<string>([ADJUSTMENT_STATUS.DRAFT, ADJUSTMENT_STATUS.PENDING_REVIEW, ADJUSTMENT_STATUS.REJECTED])

/** 审定数（借正贷负）：审定科目余额表取调整后期末，底稿取数余额表取期末余额 */
function auditedSigned(r: PreparedRow): number {
  const side = tab.value === 'audited' ? r.adjClosing : r.audited
  return side.dir === '贷' ? -side.amount : side.amount
}

function auditedTitle(r: PreparedRow): string {
  const lines = [canManualEdit.value ? '点击修改：按差额生成调整分录草稿' : MANUAL_EDIT_DENIED_TIP]
  if (r.wp) lines.push(`含底稿发布调整 ${fmtMoney(r.wp)}`)
  const n = pending.value.get(r.code)
  if (n) lines.push(`有 ${n} 张未批准的调整分录涉及本科目（批准后才进入试算表）`)
  return lines.join('\n')
}

function openAdjust(r: PreparedRow) {
  if (!canManualEdit.value) return
  adjusting.value = { code: r.code, name: r.name, audited: auditedSigned(r) }
}

async function onAdjustCreated() {
  adjusting.value = null
  hover.invalidate()
  await loadPending()
}

async function loadPending() {
  if (!year.value) return
  const counts = new Map<string, number>()
  try {
    for (let page = 1; page < 50; page += 1) {
      const res: any = await api.get(P_adj.list(projectId.value), { params: { year: year.value, page, page_size: 200 }, ...SILENT })
      const items = res?.items || []
      for (const item of items) {
        if (!PENDING_STATUSES.has(item.review_status)) continue
        const codes = new Set<string>((item.line_items || []).map((li: any) => li.standard_account_code).filter(Boolean))
        for (const code of codes) counts.set(code, (counts.get(code) || 0) + 1)
      }
      if (items.length < 200) break
    }
  } catch {
    // 只是标记，读不到不影响试算表
  }
  pending.value = counts
}

async function loadAccountNames() {
  try {
    const list: any = await api.get(P_chart.standard(projectId.value), SILENT)
    accountNames.value = new Map((Array.isArray(list) ? list : []).map((a: any) => [a.account_code, a.account_name]))
  } catch {
    accountNames.value = new Map()
  }
}

async function load() {
  if (!year.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await api.get(P_tb.standardView(projectId.value), { params: { year: year.value } })
    rows.value = Array.isArray(data) ? (data as ViewRow[]) : []
  } catch (e: any) {
    rows.value = []
    error.value = e?.response?.data?.detail || e?.message || '读取试算平衡表失败'
  } finally {
    loading.value = false
  }
  if (!error.value) await locateRow()
}

// ── 悬浮数据来源（spec citar-cell-source-hover R4） ──
const scrollRef = ref<HTMLElement | null>(null)
const COL_LABELS: Record<string, string> = {
  opening: '期初余额', opening_adj: '期初调整', period_debit: '本期借方', period_credit: '本期贷方',
  adj_debit: '借方审计调整', adj_credit: '贷方审计调整', adj_closing: '调整后期末', src_debit: '本期借方（含调整）',
  src_credit: '本期贷方（含调整）', audited: '期末余额（审定数）',
}
const EDIT_HINTS: Record<string, string> = {
  opening: '期初余额请在「账务查询 → 科目余额表」修改',
  period_debit: '本期发生额请在「账务查询 → 科目余额表」修改',
  period_credit: '本期发生额请在「账务查询 → 科目余额表」修改',
}

function splitKey(key: string): [string, string] {
  const i = key.lastIndexOf(':')
  return [key.slice(0, i), key.slice(i + 1)]
}

const hover = useCellSourceHover(scrollRef, {
  async load() {
    const res = (await api.get(P_src.trialBalance(projectId.value), { params: { year: year.value }, _silent: true } as any)) as CellSourceResponse
    return res?.cells ?? {}
  },
  resolve(key, sources) {
    const [code, col] = splitKey(key)
    const r = prepared.value.find(x => x.code === code)
    if (col === 'opening_adj') return localSource('none', '平台暂无期初调整分录，按 0 列示')
    if (!sources) return null
    const s = sources[key]
    if (!s) return null
    const hint = col === 'adj_closing' || col === 'audited' ? (r ? auditedTitle(r) : null) : (EDIT_HINTS[col] ?? null)
    // 表格按「方向 + 金额」显示，卡片按借正贷负：有负数时说明一句，免得对不上
    const negative = [s.value, ...s.items.map(i => i.amount)].some(v => Number(v) < 0)
    return { ...s, hint, notes: negative ? [...s.notes, '卡片金额按借正贷负列示：负数为贷方'] : s.notes } as CellSource
  },
})

const cardLabel = computed(() => {
  const key = hover.card.value.key
  if (!key) return ''
  const [code, col] = splitKey(key)
  const r = prepared.value.find(x => x.code === code)
  return `${code} ${r?.name ?? ''} · ${COL_LABELS[col] ?? col}`
})

function openSourceLink(l: CellSourceLink) {
  hover.close()
  const link = cellSourceLink(l)
  if (link) goSegment(link.segment, link.query)
}

// 数据刷新 / 重算 / 新建调整后作废，下次悬停重取
watch(rows, () => hover.invalidate())

// ── 从「数据源头」跳来定位到标准科目行（?locate=，spec citar-fs-issue-source-locate） ──
const { code: locateCode, isLocated, apply: applyLocate } = useCitarRowLocate()

async function locateRow() {
  await applyLocate(
    code => prepared.value.some(r => normCode(r.code) === code),
    () => {
      keyword.value = ''
      // 审定科目余额表只列有数科目：零余额行切到底稿取数余额表（全部科目）
      const hit = prepared.value.find(r => normCode(r.code) === locateCode.value)
      if (hit && !hit.hasValue) {
        tab.value = 'source'
        nonZeroOnly.value = false
      }
    },
    `试算平衡表里没有标准科目 ${locateCode.value}`,
  )
}

async function recalc() {
  if (!year.value) return
  recalcing.value = true
  try {
    // _silent：错误由 handleApiError 提示一次（含前置条件「请先完成科目映射」等）
    await api.post(P_tb.recalc(projectId.value), null, {
      params: { year: year.value },
      _silent: true,
      timeout: 300000,
    } as any)
    ElMessage.success('试算表已重算')
    await load()
  } catch (e) {
    handleApiError(e, '重算试算表')
  } finally {
    recalcing.value = false
  }
}

watch([projectId, year], () => {
  void load()
  void loadPending()
  void loadAccountNames()
}, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-mark {
  margin-left: 2px;
  font-size: var(--citar-fs-9);
  color: var(--citar-c-8a5300);
}

.citar-mark--pending {
  color: var(--citar-c-6e0ba6);
}

.citar-tb__editable {
  cursor: pointer;
}

.citar-tb__editable:hover {
  outline: 1px solid #c9a8ea;
  outline-offset: -1px;
}

.citar-footnotes {
  margin: 12px 0 0;
  padding-left: 18px;
  font-size: var(--citar-fs-12);
  line-height: 1.8;
  color: var(--citar-c-8c8c96);
}
</style>
