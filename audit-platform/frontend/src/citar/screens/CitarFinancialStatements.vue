<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">单体财务报表</h1>
      <span class="aud-header__note">数据源与「试算平衡表」相同（标准科目审定数）；格式按申报表 A000000 第 107 项会计准则代码自动选择</span>
    </header>

    <nav v-if="visibleStatements.length" class="aud-tabs">
      <button
        v-for="(s, i) in visibleStatements"
        :key="s.key"
        type="button"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === i }"
        @click="tab = i"
      >{{ s.title }}</button>
    </nav>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <span v-if="data?.format_label" class="citar-tag citar-tag--type">
            {{ data.format_label }}格式{{ data.standard_code ? `（代码 ${data.standard_code}）` : '' }}
          </span>
          <button class="citar-btn" type="button" :disabled="loading || edits.dirty.value" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data?.statements.length || exporting || edits.dirty.value" @click="exportXlsx">
            {{ exporting ? '导出中…' : '导出 Excel' }}
          </button>
          <template v-if="data?.statements.length && canManualEdit">
            <button class="citar-btn" type="button" :disabled="!edits.dirty.value || saving" @click="edits.clear">放弃修改</button>
            <button class="citar-btn citar-btn--primary" type="button" :disabled="!edits.dirty.value || saving" @click="saveEdits">
              {{ saving ? '保存中…' : '保存修改' }}
            </button>
            <span v-if="edits.dirty.value" class="citar-toolbar__count">有 {{ edits.count.value }} 处未保存的修改</span>
          </template>
          <span v-if="canManualEdit" class="citar-toolbar__hint">点金额可修改，合计按改后的数重算，点开可「恢复」；调整分录批准、试算表重算后点「刷新」</span>
          <span v-else class="citar-toolbar__hint">{{ MANUAL_EDIT_DENIED_TIP }}</span>
        </div>

        <details v-if="otherNotices.length || failedChecks.length || error" class="citar-errors">
          <summary>其他问题（{{ otherNotices.length + failedChecks.length + (error ? 1 : 0) }}）</summary>
          <div
            v-for="n in otherNotices"
            :key="n"
            class="citar-notice"
            :class="{ 'fs-issue--active': activeIssue === `notice|${n}` }"
          >
            <button
              v-if="targetsOf(n).length"
              type="button"
              class="fs-issue"
              :title="`点击定位到 ${placeText(targetsOf(n)[0])}`"
              @click="locate(`notice|${n}`, targetsOf(n))"
            >{{ n }}</button>
            <span v-else>{{ n }}</span>
            <button
              v-for="s in noticeSourcesOf(n)"
              :key="`${s.page}|${s.title}`"
              class="citar-btn"
              type="button"
              @click="openSource({ page: s.page!, code: '' })"
            >{{ s.title }}</button>
          </div>
          <div
            v-for="c in failedChecks"
            :key="c.label"
            class="citar-notice fs-issue-block"
            :class="{ 'fs-issue--active': activeIssue === `check|${c.label}` }"
          >
            <button
              v-if="visibleTargets(c.targets).length"
              type="button"
              class="fs-issue"
              :title="`点击定位到 ${placeText(visibleTargets(c.targets)[0])}`"
              @click="locate(`check|${c.label}`, visibleTargets(c.targets))"
            >{{ c.label }}：{{ fmtMoney(numberOf(c.difference)) }}（不平，请核对科目映射与调整分录）</button>
            <span v-else>{{ c.label }}：{{ fmtMoney(numberOf(c.difference)) }}（不平，请核对科目映射与调整分录）</span>
            <span v-if="visibleTargets(c.targets).length > 1" class="fs-issue__links">
              <button
                v-for="t in visibleTargets(c.targets)"
                :key="`${t.statement}|${t.r}|${t.column}`"
                type="button"
                class="fs-issue__link"
                @click="locate(`check|${c.label}`, visibleTargets(c.targets), t)"
              >{{ placeText(t) }}</button>
            </span>
            <CitarFsIssueSources :sources="c.sources ?? []" @open="openSource" />
          </div>
          <p v-if="error" class="citar-notice citar-notice--error">{{ error }}</p>
        </details>

        <p v-if="loading && !data" class="sheet-empty">正在生成财务报表…</p>
        <template v-else-if="current">
          <div class="sheet-caption">
            <p v-if="current.attachment" class="fs-attachment">{{ current.attachment }}</p>
            <h2 class="sheet-caption__title">{{ current.title }}</h2>
            <p class="sheet-caption__period">{{ periodText }}</p>
            <div class="sheet-caption__meta"><span>编制单位：{{ data?.entity_name }}</span><span>单位：人民币元</span></div>
          </div>
          <div ref="scrollRef" class="sheet-scroll">
            <table class="sheet-table">
              <thead>
                <tr>
                  <th>项　　目</th>
                  <th
                    v-for="(c, ci) in current.columns"
                    :key="c"
                    class="fs-amount"
                    :class="{ 'fs-located-col': isColumnLocated(FS_COLS[ci]) }"
                  >{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in current.rows"
                  :key="r.r"
                  :data-fs-row="r.r"
                  :class="[rowClass(r), { 'fs-located-row': isRowLocated(r) }]"
                  :title="r.note || undefined"
                >
                  <td :style="{ paddingLeft: `${10 + r.indent * 14}px` }">
                    {{ r.label }}<span v-if="r.note" class="fs-note">（{{ r.note }}）</span>
                  </td>
                  <template v-for="col in FS_COLS" :key="col">
                    <td v-if="r.heading" class="is-numeric" :class="{ 'fs-located-cell': isCellLocated(r, col) }" />
                    <CitarAmountCell
                      v-else
                      :class="{ 'fs-located-cell': isCellLocated(r, col) }"
                      :value="numberOf(r[col])"
                      :manual="Boolean(r.manual?.[col])"
                      :auto="numberOf(r.manual?.[col]?.auto)"
                      :draft="edits.draftOf(cellKey(current, r, col))"
                      :restored="edits.isRestored(cellKey(current, r, col))"
                      :editable="!saving && !r.note && canManualEdit"
                      :label="r.label"
                      :src-key="`${current.key}:${r.r}:${col}`"
                      @edit="v => edits.edit(cellKey(current!, r, col), v)"
                      @restore="edits.restore(cellKey(current!, r, col), Boolean(r.manual?.[col]))"
                    />
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>
    </section>

    <CitarSourceCard
      :state="sources.card.value"
      :label="sources.cardLabel.value"
      @open="sources.open"
      @enter="sources.onCardEnter"
      @leave="sources.onCardLeave"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 单体财务报表（CITAR 鉴证报告 · 单体财务报表）。
 * 企业会计制度格式由后端按税审专用行次配置从标准科目审定数计算；企业会计准则格式复用平台审定报表。
 * 金额：取不到（null）留空，0 显示「-」。点金额可手工修改（标题行除外），合计、平衡校验与导出按手工值。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import CitarAmountCell from '../components/CitarAmountCell.vue'
import CitarFsIssueSources, { type FsSourceOpen } from '../components/CitarFsIssueSources.vue'
import CitarSourceCard from '../components/CitarSourceCard.vue'
import { api } from '@/services/apiProxy'
import { cellSources as P_src } from '@/services/apiPaths'
import type { CellSourceLink, CellSourceResponse } from '../cellSource'
import { useCitarSourceCard } from '../useCitarSourceCard'
import { saveReportManualValues, type ManualReportItem } from '../citarReportManual'
import { sourceLink } from '../fsIssueSources'
import {
  downloadTaxAssurance, fetchFinancialStatements, numberOf, saveFinancialStatements,
  type FinancialStatementsData, type FsRow, type FsSource, type FsStatement, type FsTarget,
} from '../taxAssuranceApi'
import { useCitarAmountDrafts } from '../useCitarAmountDrafts'
import { fmtMoney, useCitarProject } from '../useCitarProject'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

defineOptions({ name: 'CitarFinancialStatements' })

const { projectId, year, yearLoading, goSegment } = useCitarProject()
const { canManualEdit } = useManualEditPermission()
const data = ref<FinancialStatementsData | null>(null)
const loading = ref(false)
const exporting = ref(false)
const error = ref('')
const tab = ref(0)
/** 金额手工修改（spec citar-table-manual-edit R7）：企业会计制度格式存 __fs__，企业会计准则格式改审定报表 */
const edits = useCitarAmountDrafts()
const saving = ref(false)

const HIDDEN_STATEMENT_KEYS = new Set([
  'cash_flow_statement',
  'cash_flow_supplement',
])
const HIDDEN_NOTICE_MARKERS = ['税审底稿', '1-12', '现金流量表底稿']

const visibleStatements = computed(() =>
  (data.value?.statements ?? []).filter(s => !HIDDEN_STATEMENT_KEYS.has(s.key)),
)
const current = computed(() => visibleStatements.value[tab.value] ?? null)
const otherNotices = computed(() =>
  (data.value?.notices ?? []).filter(n => !HIDDEN_NOTICE_MARKERS.some(marker => n.includes(marker))),
)
const failedChecks = computed(() => (data.value?.checks ?? []).filter(c => !c.ok))
const periodText = computed(() => {
  if (!year.value || !current.value) return ''
  return current.value.columns[0]?.startsWith('期末') ? `${year.value}年12月31日` : `${year.value}年度`
})

/* ── 「其他问题」点击定位：切到问题所在页签、滚到该行并高亮（位置由后端 notice_targets / checks[].targets 给出） ── */
const scrollRef = ref<HTMLElement | null>(null)
/** 当前点的问题（notice|文字 / check|标签） */
const activeIssue = ref('')
const located = ref<FsTarget | null>(null)

/** 只留本页能显示的表（现金流量表等隐藏页签上的位置定位不了） */
function visibleTargets(list: FsTarget[] | undefined): FsTarget[] {
  return (list ?? []).filter(t => visibleStatements.value.some(s => s.key === t.statement))
}

function targetsOf(notice: string): FsTarget[] {
  return visibleTargets(data.value?.notice_targets?.[notice])
}

/* ── 数据源头（spec citar-fs-issue-source-locate）：跳到源头页并定位到行；本页格子就地定位 ── */
function noticeSourcesOf(notice: string): FsSource[] {
  return (data.value?.notice_sources?.[notice] ?? []).filter(s => sourceLink(s.page))
}

async function openSource({ page, code, row }: FsSourceOpen) {
  if (page === 'statement') {
    if (row?.statement && row.r != null) {
      void locate(`source|${row.statement}|${row.r}`, [{ statement: row.statement, r: row.r, column: row.column ?? null }])
    }
    return
  }
  const link = sourceLink(page, code)
  if (!link) return
  if (edits.dirty.value) {
    try {
      await ElMessageBox.confirm('有未保存的修改，离开本页会丢失。仍要去看数据源头吗？', '未保存的修改', {
        type: 'warning', confirmButtonText: '离开', cancelButtonText: '留在本页',
      })
    } catch {
      return
    }
  }
  goSegment(link.segment, link.query)
}

function sameTarget(a: FsTarget, b: FsTarget) {
  return a.statement === b.statement && a.r === b.r && a.column === b.column
}

/** 位置说明：资产负债表「资产总计」期末余额 / 利润表上期金额列 / 利润表 */
function placeText(t: FsTarget): string {
  const s = visibleStatements.value.find(x => x.key === t.statement)
  if (!s) return ''
  const row = t.r == null ? null : s.rows.find(x => x.r === t.r)
  const col = t.column == null ? '' : (s.columns[FS_COLS.indexOf(t.column)] ?? '')
  if (row) return `${s.title}「${row.label.trim()}」${col}`
  return col ? `${s.title}${col}列` : s.title
}

/** 定位；同一问题有多个位置时再点依次轮换，pick = 直接点某个位置 */
async function locate(issue: string, targets: FsTarget[], pick?: FsTarget) {
  if (!targets.length) return
  let t = pick
  if (!t) {
    const prev = activeIssue.value === issue ? located.value : null
    const idx = prev ? targets.findIndex(x => sameTarget(x, prev)) : -1
    t = targets[(idx + 1) % targets.length]
  }
  activeIssue.value = issue
  located.value = t
  const i = visibleStatements.value.findIndex(s => s.key === t.statement)
  if (i >= 0) tab.value = i
  await nextTick()
  const el = t.r == null
    ? scrollRef.value
    : scrollRef.value?.querySelector<HTMLElement>(`tr[data-fs-row="${t.r}"]`)
  el?.scrollIntoView?.({ behavior: 'smooth', block: t.r == null ? 'start' : 'center' })
}

function locatedHere(): FsTarget | null {
  const t = located.value
  return t && current.value && t.statement === current.value.key ? t : null
}

function isRowLocated(r: FsRow) {
  return locatedHere()?.r === r.r
}

function isColumnLocated(col: FsCol) {
  const t = locatedHere()
  return Boolean(t && t.r == null && t.column === col)
}

/** 定位到的格：指定行的那一列（列为空 = 整行）；整列定位时该列每一格 */
function isCellLocated(r: FsRow, col: FsCol) {
  const t = locatedHere()
  if (!t) return false
  if (t.r == null) return t.column === col
  return t.r === r.r && (t.column == null || t.column === col)
}

let seq = 0
async function load() {
  if (!year.value) return
  const mine = ++seq
  loading.value = true
  error.value = ''
  try {
    const res = await fetchFinancialStatements(projectId.value, year.value)
    if (mine !== seq) return
    data.value = res
    // 数据换了，问题可能已不在 ⇒ 去掉上次的定位高亮
    activeIssue.value = ''
    located.value = null
    if (tab.value >= visibleStatements.value.length) tab.value = 0
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '生成财务报表失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

async function exportXlsx() {
  if (!year.value) return
  exporting.value = true
  try {
    await downloadTaxAssurance('financialStatementsExport', projectId.value, year.value, `${year.value}年度财务报表.xlsx`)
  } catch (e) {
    handleApiError(e, '导出财务报表')
  } finally {
    exporting.value = false
  }
}

type FsCol = 'current' | 'prior'
const FS_COLS: FsCol[] = ['current', 'prior']

// ── 悬浮数据来源（spec citar-cell-source-hover R5.6）：本页格子的链接在本页定位，其余跳页 ──
const sources = useCitarSourceCard({
  container: scrollRef,
  async load() {
    const res = (await api.get(P_src.financialStatements(projectId.value), {
      params: { year: year.value }, _silent: true,
    } as any)) as CellSourceResponse
    return res?.cells ?? {}
  },
  label(key) {
    const [stmtKey, r, col] = key.split(':')
    const s = data.value?.statements.find(x => x.key === stmtKey)
    const row = s?.rows.find(x => String(x.r) === r)
    const colText = s?.columns[FS_COLS.indexOf(col as FsCol)] ?? ''
    return `${s?.title ?? ''}「${row?.label.trim() ?? ''}」${colText}`
  },
  locate(l: CellSourceLink) {
    let target: FsTarget | null = null
    if (l.page === 'statement' && l.sheet && l.row != null) {
      target = { statement: l.sheet, r: Number(l.row), column: (l.column as FsCol) ?? null }
    } else if (l.page === 'reports' && l.report_type && l.code) {
      // 企业会计准则格式即审定报表：本页就有这一行
      const row = data.value?.statements.find(s => s.key === l.report_type)?.rows.find(x => x.row_code === l.code)
      if (row) target = { statement: l.report_type, r: row.r, column: null }
    }
    if (!target || !visibleStatements.value.some(s => s.key === target!.statement)) return false
    void locate(`src|${target.statement}|${target.r}|${target.column ?? ''}`, [target])
    return true
  },
  dirty: () => edits.dirty.value,
})
watch(data, () => sources.invalidate())

/** 草稿键：来源|表|行（企业会计准则格式用行次编码）|列 */
function cellKey(stmt: FsStatement, r: FsRow, col: FsCol): string {
  return stmt.source === 'report' ? `report|${stmt.key}|${r.row_code}|${col}` : `fs|${stmt.key}|${r.r}|${col}`
}

/** 企业会计制度格式：已保存的手工值 + 草稿 − 已恢复，整份提交 */
function fsValues(): Record<string, Record<string, Partial<Record<FsCol, number | null>>>> {
  const out: Record<string, Record<string, Partial<Record<FsCol, number | null>>>> = {}
  const put = (key: string, row: string, col: FsCol, v: number | null) => {
    ((out[key] ??= {})[row] ??= {})[col] = v
  }
  for (const s of data.value?.statements ?? []) {
    if (s.source !== 'fs') continue
    for (const r of s.rows) {
      for (const col of FS_COLS) {
        if (r.manual?.[col] && !edits.isRestored(cellKey(s, r, col))) put(s.key, String(r.r), col, numberOf(r[col]))
      }
    }
  }
  for (const [key, v] of Object.entries(edits.drafts.value)) {
    const [source, stmt, row, col] = key.split('|')
    if (source === 'fs') put(stmt, row, col as FsCol, v)
  }
  return out
}

function reportItems(): ManualReportItem[] {
  const items: ManualReportItem[] = []
  for (const [key, value] of Object.entries(edits.drafts.value)) {
    const [source, stmt, rowCode, col] = key.split('|')
    if (source === 'report') items.push({ report_type: stmt, row_code: rowCode, column: col as FsCol, value })
  }
  for (const key of edits.restored.value) {
    const [source, stmt, rowCode, col] = key.split('|')
    if (source === 'report') items.push({ report_type: stmt, row_code: rowCode, column: col as FsCol, restore: true })
  }
  return items
}

async function saveEdits() {
  if (!data.value || !year.value) return
  const keys = [...Object.keys(edits.drafts.value), ...edits.restored.value]
  saving.value = true
  try {
    if (keys.some(k => k.startsWith('fs|'))) {
      await saveFinancialStatements(projectId.value, year.value, data.value.version, fsValues())
    }
    const items = reportItems()
    if (items.length) await saveReportManualValues(projectId.value, year.value, items)
    edits.clear()
    ElMessage.success('已保存，报表已按修改后的金额重算')
    await load()
  } catch (e: any) {
    if (e?.response?.status === 409) ElMessage.warning(e?.response?.data?.detail || '报表已被他人修改，请刷新后再改')
    else handleApiError(e, '保存财务报表修改')
  } finally {
    saving.value = false
  }
}

function rowClass(r: FsRow) {
  if (r.heading) return 'level-group'
  if (r.total) return /总计\s*$/.test(r.label) ? 'level-total' : 'level-subtotal'
  return ''
}

watch([projectId, year], () => {
  edits.clear()
  void load()
}, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-errors {
  margin: 0 0 12px;
  border: 1px solid #eadff3;
  border-radius: var(--gt-radius-sm);
  background: var(--citar-c-fbf9fe);
}

.citar-errors summary {
  padding: 8px 12px;
  color: var(--citar-c-4c1273);
  font-size: var(--citar-fs-13);
  font-weight: 600;
  cursor: pointer;
  user-select: none;
}

.citar-errors[open] summary {
  border-bottom: 1px solid #eadff3;
}

.citar-errors .citar-notice {
  margin: 8px 12px;
}

.citar-errors .citar-notice:last-child {
  margin-bottom: 12px;
}

.citar-notice--error {
  color: var(--citar-c-e5484d);
}

.fs-attachment {
  margin: 0;
  text-align: left;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-6b6b76);
}

.fs-amount {
  width: 200px;
}

.fs-note {
  margin-left: 6px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-a0a0aa);
}

/* 「其他问题」可点击定位的条目 */
.fs-issue {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  text-decoration: underline dotted;
  text-underline-offset: 3px;
  cursor: pointer;
}

.fs-issue:hover,
.fs-issue:focus-visible {
  color: var(--citar-c-6e0ba6);
}

.fs-issue__links {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fs-issue__link {
  padding: 1px 8px;
  border: 1px solid #d7c3ee;
  border-radius: 10px;
  background: var(--citar-c-ffffff);
  font-size: var(--citar-fs-12);
  color: var(--citar-c-6e0ba6);
  cursor: pointer;
}

.fs-issue__link:hover {
  border-color: var(--citar-c-6e0ba6);
}

.fs-issue-block {
  flex-wrap: wrap;
}

.citar-errors .fs-issue--active {
  border-color: #c9a8ea;
  box-shadow: 0 0 0 2px #efe4fb;
}

/* 定位到的行 / 列 / 格 */
.sheet-table .fs-located-row td {
  background: #fff6db;
}

.sheet-table .fs-located-col {
  background: #ffe9a8;
}

.sheet-table td.fs-located-cell {
  background: #ffe9a8;
  box-shadow: inset 0 0 0 2px #e0a100;
}
</style>
