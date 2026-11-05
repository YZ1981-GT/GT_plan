<template>
  <div>
    <div class="sheet-caption">
      <h2 class="sheet-caption__title">序时账</h2>
      <p class="sheet-caption__period">所属期间：{{ year ? `${year}年1月—12月` : '' }}</p>
      <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：元</span></div>
    </div>

    <div ref="toolbarRef" class="citar-toolbar">
      <input
        v-model.trim="codeInput"
        class="citar-search"
        type="search"
        placeholder="科目编码（含下级），留空看全部"
        @keydown.enter="applyFilter"
      />
      <button class="citar-btn" type="button" @click="applyFilter">查询</button>
      <button v-if="!isAllEntries" class="citar-btn" type="button" @click="clearFilter">看全部分录</button>
      <button v-if="backFrame" class="citar-btn" type="button" :disabled="loading" @click="drillBackTo(drillStack.length - 1)">
        ← 返回上一级
      </button>
      <span class="citar-toolbar__count">{{ viewTitle }}{{ total !== null ? `，共 ${total} 条分录` : '' }}</span>
      <span class="citar-toolbar__hint">
        点凭证号进入该张凭证、点科目编码进入该科目序时账；{{ canManualEdit ? '每条分录可「修改」，序时账的修改不回写科目余额表' : MANUAL_EDIT_DENIED_TIP }}
      </span>
    </div>

    <!-- 穿透路径：前面各级可点，直接回到那一级（原页码、点过的那一行高亮） -->
    <nav v-if="drillStack.length" class="citar-journal__crumbs" aria-label="穿透路径">
      <template v-for="(f, i) in drillStack" :key="i">
        <button type="button" class="citar-drill" :disabled="loading" @click="drillBackTo(i)">{{ viewLabel(f.view) }}</button>
        <span class="citar-journal__crumb-sep">›</span>
      </template>
      <span class="citar-journal__crumb-current">{{ viewLabel(view) }}</span>
    </nav>

    <div ref="scrollRef" class="sheet-scroll">
      <table class="sheet-table">
        <thead>
          <tr>
            <th v-for="c in JOURNAL_COLUMNS" :key="c.key">{{ c.label }}</th>
            <th v-if="showBalance">余额</th>
            <th class="citar-journal__ops-head" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(r, i) in items"
            :key="r.id"
            :data-journal-row="r.id"
            :class="{ 'citar-journal__row--edited': editedIds.has(r.id), 'citar-located': r.id === anchorId }"
          >
            <td class="is-numeric">{{ offset + i + 1 }}</td>
            <template v-if="editingId === r.id">
              <td><input v-model="draft.voucher_date" class="citar-search citar-journal__input" type="date" aria-label="凭证日期" /></td>
              <td><input v-model="draft.voucher_no" class="citar-search citar-journal__input" aria-label="凭证号" /></td>
              <td><input v-model="draft.summary" class="citar-search citar-journal__input citar-journal__input--wide" aria-label="摘要" /></td>
              <td><input v-model="draft.account_code" class="citar-search citar-journal__input" aria-label="科目编码" /></td>
              <td><input v-model="draft.account_name" class="citar-search citar-journal__input" aria-label="科目名称" /></td>
              <td>{{ pickExtra(r, AUX_KEYS) }}</td>
              <td>{{ pickExtra(r, CURRENCY_KEYS) }}</td>
              <td><input v-model="draft.debit_amount" class="citar-search citar-journal__input citar-journal__input--num" aria-label="借方金额" /></td>
              <td><input v-model="draft.credit_amount" class="citar-search citar-journal__input citar-journal__input--num" aria-label="贷方金额" /></td>
              <td v-if="showBalance" class="is-numeric">{{ fmtMoney(r.running_balance) }}</td>
              <td class="citar-center citar-journal__ops">
                <button class="citar-btn citar-btn--primary" type="button" :disabled="saving" @click="saveEdit(r)">{{ saving ? '保存中…' : '保存' }}</button>
                <button class="citar-btn" type="button" :disabled="saving" @click="editingId = ''">取消</button>
              </td>
            </template>
            <template v-else>
              <td :data-src="srcKey(r, 'voucher_date')">{{ r.voucher_date }}</td>
              <td :data-src="srcKey(r, 'voucher_no')">
                <button
                  v-if="canDrillVoucher(r)"
                  type="button"
                  class="citar-drill"
                  title="进入该张凭证，列出全部分录"
                  @click="drillVoucher(r)"
                >{{ r.voucher_no }}</button>
                <template v-else>{{ r.voucher_no }}</template>
              </td>
              <td class="citar-journal__summary" :data-src="srcKey(r, 'summary')">{{ r.summary }}</td>
              <td :data-src="srcKey(r, 'account_code')">
                <button
                  v-if="canDrillAccount(r.account_code)"
                  type="button"
                  class="citar-drill"
                  title="进入该科目（含下级）序时账"
                  @click="drillAccount(r.account_code, r.id)"
                >{{ r.account_code }}</button>
                <template v-else>{{ r.account_code }}</template>
              </td>
              <td class="citar-journal__summary" :data-src="srcKey(r, 'account_name')">
                {{ r.account_name }}<span v-if="editedIds.has(r.id)" class="citar-journal__tag" :title="editedTitle(r.id)">已修改</span>
              </td>
              <td :data-src="srcKey(r, 'aux')">{{ pickExtra(r, AUX_KEYS) }}</td>
              <td :data-src="srcKey(r, 'currency')">{{ pickExtra(r, CURRENCY_KEYS) }}</td>
              <td class="is-numeric" :data-src="srcKey(r, 'debit')">{{ fmtMoney(r.debit_amount, '') }}</td>
              <td class="is-numeric" :data-src="srcKey(r, 'credit')">{{ fmtMoney(r.credit_amount, '') }}</td>
              <td v-if="showBalance" class="is-numeric">{{ fmtMoney(r.running_balance) }}</td>
              <td class="citar-center citar-journal__ops">
                <template v-if="canManualEdit">
                  <button class="citar-btn" type="button" :disabled="saving" @click="startEdit(r)">修改</button>
                  <button v-if="editedIds.has(r.id)" class="citar-btn" type="button" :disabled="saving" @click="restore(r)">恢复</button>
                </template>
              </td>
            </template>
          </tr>
        </tbody>
        <!-- 凭证级：整张凭证的借贷合计 -->
        <tfoot v-if="view.kind === 'voucher' && items.length">
          <tr class="citar-journal__total">
            <td :colspan="JOURNAL_COLUMNS.length - 2">合计（{{ voucherTotals.balanced ? '借贷平衡' : '借贷不平' }}）</td>
            <td class="is-numeric">{{ fmtMoney(voucherTotals.debit, '0.00') }}</td>
            <td class="is-numeric">{{ fmtMoney(voucherTotals.credit, '0.00') }}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
    <p v-if="view.kind === 'voucher' && items.length && !voucherTotals.balanced" class="citar-journal__unbalanced">
      借贷不平：{{ voucherTotals.diff > 0 ? '借方比贷方多' : '贷方比借方多' }} {{ fmtMoney(Math.abs(voucherTotals.diff), '0.00') }} 元
    </p>
    <p v-if="loading" class="sheet-empty">正在读取序时账…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="!items.length" class="sheet-empty">{{ emptyText }}</p>

    <div v-if="items.length && view.kind === 'account'" class="citar-pager">
      <span>第 {{ pageIndex + 1 }} 页{{ pageCount ? ` / 共 ${pageCount} 页` : '' }}</span>
      <button class="citar-btn" type="button" :disabled="pageIndex === 0 || loading" @click="prevPage">上一页</button>
      <button class="citar-btn" type="button" :disabled="!hasMore || loading" @click="nextPage">下一页</button>
    </div>

    <CitarSourceCard
      :state="hover.card.value"
      :label="cardLabel"
      @open="openSource"
      @enter="hover.onCardEnter"
      @leave="hover.onCardLeave"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 序时账（未审）：
 * - 全部科目：GET /ledger/entries-all（页码分页；总数只在第 1 页返回）
 * - 指定科目：GET /ledger/entries/{code}*（含下级，游标分页，带累计余额）
 * 辅助核算 / 币种：平台没有专列，取导入时保留的额外列（extra_fields）里名字匹配的那一列。
 * 每条分录可人工修改、恢复导入原值（spec citar-table-manual-edit R4 / R5）；修改不回写余额表。
 * 穿透（逐级进入、逐级返回，不弹窗）：
 * - 点凭证号 → 凭证级：列出这张凭证的全部分录（GET /ledger/voucher/{号}?voucher_date=，凭证号单独不唯一，带日期定位）+ 借贷合计
 * - 点科目编码 → 科目级：该科目（含下级）序时账
 * 每级都可再往下点；「返回上一级」/ 路径上点前面某一级，回到那一级原来的页码并高亮点过的那一行。
 * 换级别会改地址栏（?account= / ?voucher=&vdate=），布局按 fullPath 重挂载本页 ⇒ 穿透历史存在 journalDrillMemory，挂载时取回。
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { cellSources as P_src, ledger as P_ledger } from '@/services/apiPaths'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import { handleApiError } from '@/utils/errorHandler'
import { JOURNAL_COLUMNS } from '../data/reportLines'
import CitarSourceCard from './CitarSourceCard.vue'
import { AUX_KEYS, CURRENCY_KEYS, pickExtra, pickExtraHeader } from '../citarLedgerExtra'
import { forgetDrill, recallDrill, rememberDrill, viewKey, type DrillFrame, type JournalView } from '../journalDrillMemory'
import { localSource, mergeLedgerSources, type CellSource, type CellSourceLink, type CellSourceResponse } from '../cellSource'
import { useCellSourceHover } from '../useCellSourceHover'
import { editLedgerEntry, fetchManualEdits, restoreLedgerRow, type ManualEditInfo } from '../citarLedgerEdits'
import { fmtMoney } from '../useCitarProject'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

interface JournalRow {
  id: string
  voucher_date: string | null
  voucher_no: string | null
  summary: string | null
  account_code: string
  account_name: string | null
  debit_amount: number | null
  credit_amount: number | null
  running_balance?: number | null
  extra_fields?: Record<string, unknown> | null
}

const PAGE_SIZE = 200

const props = defineProps<{
  projectId: string
  year: number
  entityName: string
  /** 科目级：科目编码（含下级）；空 = 全部分录 */
  accountCode?: string
  /** 凭证级：凭证号与凭证日期（YYYY-MM-DD）；有凭证号时忽略 accountCode */
  voucherNo?: string
  voucherDate?: string
}>()
const { canManualEdit } = useManualEditPermission()
/** 级别变化时通知父组件写回地址栏（?account= / ?voucher=&vdate=），刷新不丢、也不残留旧级别 */
const emit = defineEmits<{ 'update:view': [view: JournalView]; 'open-source': [link: CellSourceLink] }>()

function viewFromProps(): JournalView {
  if (props.voucherNo) return { kind: 'voucher', no: props.voucherNo, date: props.voucherDate ? props.voucherDate.slice(0, 10) : null }
  return { kind: 'account', code: (props.accountCode || '').replace(/\*+$/, '') }
}

/** 当前级别 */
const view = ref<JournalView>(viewFromProps())
const activeCode = computed(() => (view.value.kind === 'account' ? view.value.code : ''))
const isAllEntries = computed(() => view.value.kind === 'account' && !view.value.code)
/** 累计余额只有科目级有（接口按科目算） */
const showBalance = computed(() => view.value.kind === 'account' && Boolean(view.value.code))
const codeInput = ref(activeCode.value)
const items = ref<JournalRow[]>([])
const total = ref<number | null>(null)
const loading = ref(false)
const error = ref('')
const pageIndex = ref(0)
const hasMore = ref(false)
/** 科目级的游标栈：cursors[i] 是第 i 页的起点（第 0 页为 null） */
const cursors = ref<(string | null)[]>([null])
/** 进入当前级别之前走过的各级（「返回」逐级弹出） */
const drillStack = ref<DrillFrame[]>([])
const backFrame = computed(() => drillStack.value[drillStack.value.length - 1] ?? null)
/** 高亮的那一行（从哪一行点进来 / 返回时点过的那一行） */
const anchorId = ref('')
const toolbarRef = ref<HTMLElement | null>(null)

function viewLabel(v: JournalView): string {
  if (v.kind === 'voucher') return `凭证 ${v.no}${v.date ? `（${v.date}）` : '（全年同号）'}`
  return v.code ? `科目 ${v.code} 及下级` : '全部科目'
}
const viewTitle = computed(() => viewLabel(view.value))

const emptyText = computed(() => {
  const v = view.value
  if (v.kind === 'voucher') return '没有找到这张凭证的分录，可能序时账已重新导入。可点「返回上一级」或「看全部分录」。'
  if (v.code) return `序时账里没有编码以 ${v.code} 开头的分录。若余额表有发生额，多半是序时账导入的科目编码与余额表不一致，可点「看全部分录」核对。`
  return '本年度还没有导入序时账'
})

/** 凭证级借贷合计：十进制累加，避免浮点尾差把平衡的凭证判成不平 */
const calc = useDecimalCalc()
function amountOf(v: number | string | null | undefined): number | string {
  if (v === null || v === undefined || v === '') return 0
  return Number.isFinite(Number(v)) ? v : 0
}
const voucherTotals = computed(() => {
  const debit = Number(calc.sum(0, ...items.value.map(l => amountOf(l.debit_amount))))
  const credit = Number(calc.sum(0, ...items.value.map(l => amountOf(l.credit_amount))))
  const diff = Number(calc.sub(debit, credit))
  return { debit, credit, diff, balanced: diff === 0 }
})

const offset = computed(() => pageIndex.value * PAGE_SIZE)
const pageCount = computed(() => (total.value !== null ? Math.max(1, Math.ceil(total.value / PAGE_SIZE)) : 0))

// ── 悬浮数据来源（spec citar-cell-source-hover R6）：列取自导入文件哪个表头（整表一取）+ 本行特殊情况（悬停时单取） ──
type JournalCol = 'voucher_date' | 'voucher_no' | 'summary' | 'account_code' | 'account_name' | 'aux' | 'currency' | 'debit' | 'credit'
const J_LABELS: Record<JournalCol, string> = {
  voucher_date: '凭证日期', voucher_no: '凭证号', summary: '摘要', account_code: '科目编码', account_name: '科目名称',
  aux: '辅助核算', currency: '币种', debit: '借方', credit: '贷方',
}
const srcKey = (r: JournalRow, col: JournalCol) => `${r.id}|${col}`
const scrollRef = ref<HTMLElement | null>(null)
const rowSources = new Map<string, Promise<CellSource | null>>()

function cellText(r: JournalRow, col: JournalCol): string | null {
  if (col === 'debit') return r.debit_amount === null ? null : String(r.debit_amount)
  if (col === 'credit') return r.credit_amount === null ? null : String(r.credit_amount)
  if (col === 'aux') return pickExtra(r, AUX_KEYS) || null
  if (col === 'currency') return pickExtra(r, CURRENCY_KEYS) || null
  const v = r[col]
  return v === null || v === undefined ? null : String(v)
}

const hover = useCellSourceHover(scrollRef, {
  async load() {
    const res = (await api.get(P_src.ledgerJournal(props.projectId), { params: { year: props.year }, _silent: true } as any)) as CellSourceResponse
    return res?.cells ?? {}
  },
  extra(key) {
    const id = key.split('|')[0]
    if (!rowSources.has(id)) {
      rowSources.set(id, (api.get(P_src.ledgerJournalRow(props.projectId, id), { params: { year: props.year }, _silent: true } as any) as Promise<any>)
        .then(res => (res?.cell ?? null) as CellSource | null))
    }
    return rowSources.get(id)!
  },
  resolve(key, sources, extra) {
    const [id, col] = key.split('|') as [string, JournalCol]
    const r = items.value.find(x => x.id === id)
    if (!r || !sources) return null
    if (col === 'aux' || col === 'currency') {
      const header = pickExtraHeader(r, col === 'aux' ? AUX_KEYS : CURRENCY_KEYS)
      return localSource('import', header ? `取自导入文件里没映射的「${header}」列` : '导入文件里没有这一列', cellText(r, col))
    }
    const merged = mergeLedgerSources(sources[`col:${col}`], extra, cellText(r, col))
    // 摘要 / 科目名称在表格里会截断：卡片里写全
    if (merged && (col === 'summary' || col === 'account_name') && r[col]) merged.notes = [`全文：${r[col]}`, ...merged.notes]
    return merged
  },
  disabled: () => Boolean(editingId.value),
})
const cardLabel = computed(() => {
  const [id, col] = hover.card.value.key.split('|') as [string, JournalCol]
  const r = items.value.find(x => x.id === id)
  return r ? `${r.voucher_date ?? ''} ${r.voucher_no ?? ''} · ${J_LABELS[col] ?? ''}` : ''
})
watch(items, () => {
  rowSources.clear()
  hover.invalidate()
})

/** 晚到的旧请求不覆盖新结果（穿透 / 返回连点时两次读取可能交错） */
let loadSeq = 0

async function loadPage(index: number) {
  const mine = ++loadSeq
  const v = view.value
  loading.value = true
  error.value = ''
  try {
    if (v.kind === 'voucher') {
      // 一张凭证的分录不多，不分页
      const params: Record<string, unknown> = { year: props.year }
      if (v.date) params.voucher_date = v.date
      const data: any = await api.get(P_ledger.voucher(props.projectId, v.no), { params })
      if (mine !== loadSeq) return
      items.value = Array.isArray(data) ? data : []
      total.value = items.value.length
      hasMore.value = false
      index = 0
    } else if (v.code) {
      const code = `${v.code}*`
      const data: any = await api.get(P_ledger.entries(props.projectId, code), {
        params: { year: props.year, limit: PAGE_SIZE, ...(cursors.value[index] ? { cursor: cursors.value[index] } : {}) },
      })
      if (mine !== loadSeq) return
      items.value = data?.items || []
      hasMore.value = !!data?.has_more
      if (typeof data?.total === 'number') total.value = data.total
      if (data?.next_cursor) cursors.value[index + 1] = data.next_cursor
    } else {
      const data: any = await api.get(P_ledger.entriesAll(props.projectId), {
        params: { year: props.year, page: index + 1, page_size: PAGE_SIZE },
      })
      if (mine !== loadSeq) return
      items.value = data?.items || []
      if (index === 0) total.value = typeof data?.total === 'number' ? data.total : null
      hasMore.value = total.value !== null ? (index + 1) * PAGE_SIZE < total.value : items.value.length === PAGE_SIZE
    }
    pageIndex.value = index
  } catch (e: any) {
    if (mine !== loadSeq) return
    items.value = []
    error.value = e?.message || '读取序时账失败'
  } finally {
    if (mine === loadSeq) loading.value = false
  }
}

function reset() {
  cursors.value = [null]
  total.value = null
  anchorId.value = ''
  void loadPage(0)
}

/** 查询 / 看全部分录：换到某科目级，清掉穿透路径 */
function setRootAccount(code: string) {
  if (blockedByEditing()) return
  hover.close()
  drillStack.value = []
  forgetDrill(props.projectId, props.year)
  switchView({ kind: 'account', code })
  reset()
}

function applyFilter() {
  setRootAccount(codeInput.value.replace(/\*+$/, ''))
}

function clearFilter() {
  setRootAccount('')
}

function nextPage() {
  anchorId.value = ''
  if (hasMore.value) void loadPage(pageIndex.value + 1)
}

function prevPage() {
  anchorId.value = ''
  if (pageIndex.value > 0) void loadPage(pageIndex.value - 1)
}

// ── 穿透：凭证号 → 凭证级；科目编码 → 科目级（含下级）；逐级返回 ──

/** 本行科目就是当前科目级本身时不必再点 */
function canDrillAccount(code: string | null | undefined): boolean {
  const c = String(code ?? '').trim()
  return Boolean(c) && !(view.value.kind === 'account' && c === view.value.code)
}

/** 凭证级里的凭证号都是这一张，不必再点 */
function canDrillVoucher(r: JournalRow): boolean {
  return Boolean(r.voucher_no) && view.value.kind !== 'voucher'
}

/** 正在改的分录没保存时换级别会丢草稿：先提示 */
function blockedByEditing(): boolean {
  if (!editingId.value) return false
  ElMessage.warning('有分录正在修改，请先保存或取消')
  return true
}

/** 卡片里点来源链接（如导入记录的某列映射）：分录在改先提示，再交给账务查询页跳转（spec citar-cell-source-hover R9.5） */
function openSource(link: CellSourceLink) {
  hover.close()
  if (!blockedByEditing()) emit('open-source', link)
}

/** 换级别：同步搜索框、通知父组件写地址栏（写完本页会按新地址重挂载） */
function switchView(v: JournalView) {
  view.value = v
  codeInput.value = v.kind === 'account' ? v.code : ''
  emit('update:view', v)
}

/** 进入下一级：记下当前位置；新一级里高亮点过的那一行，工具条滚回可见处 */
function drillInto(target: JournalView, rowId: string) {
  if (viewKey(target) === viewKey(view.value) || blockedByEditing()) return
  hover.close()
  const stack = [...drillStack.value, {
    view: { ...view.value },
    pageIndex: pageIndex.value,
    cursors: [...cursors.value],
    total: total.value,
    rowId,
  }]
  drillStack.value = stack
  const entry: DrillFrame = { view: target, pageIndex: 0, cursors: [null], total: null, rowId }
  // 先记下再改地址栏：改完本页会按新地址重挂载，新页面从记录里取回路径与高亮行
  rememberDrill(props.projectId, props.year, target, stack, entry)
  switchView(target)
  void restoreFrame(entry, false)
  void nextTick(() => toolbarRef.value?.scrollIntoView?.({ block: 'nearest' }))
}

function drillVoucher(r: JournalRow) {
  if (!r.voucher_no) return
  drillInto({ kind: 'voucher', no: r.voucher_no, date: r.voucher_date ? r.voucher_date.slice(0, 10) : null }, r.id)
}

function drillAccount(code: string, rowId = '') {
  const c = String(code ?? '').trim()
  if (c) drillInto({ kind: 'account', code: c }, rowId)
}

/** 回到路径上第 index 级（「返回上一级」= 最后一级）：原页码，点过的那一行滚到中间高亮 */
function drillBackTo(index: number) {
  const frame = drillStack.value[index]
  if (!frame || blockedByEditing()) return
  hover.close()
  const stack = drillStack.value.slice(0, index)
  drillStack.value = stack
  rememberDrill(props.projectId, props.year, frame.view, stack, frame, true)
  switchView({ ...frame.view })
  void restoreFrame(frame, true)
}

/** 按记下的页码读，并高亮那一行（那一行已不在本页则只回页码）；scroll 为真时滚到中间 */
async function restoreFrame(frame: DrillFrame, scroll: boolean) {
  cursors.value = [...frame.cursors]
  total.value = frame.total
  anchorId.value = ''
  await loadPage(frame.pageIndex)
  if (!frame.rowId || !items.value.some(r => r.id === frame.rowId)) return
  anchorId.value = frame.rowId
  if (!scroll) return
  await nextTick()
  scrollRef.value?.querySelector<HTMLElement>(`[data-journal-row="${frame.rowId}"]`)?.scrollIntoView?.({ block: 'center' })
}

/** 挂载 / 换项目年度时：取回本级别下的穿透历史，有待恢复位置就按它读，否则读第 1 页 */
function loadFromMemory() {
  const { stack, restore, scrollToRow } = recallDrill(props.projectId, props.year, view.value)
  drillStack.value = stack
  if (restore) void restoreFrame(restore, scrollToRow)
  else reset()
}

// ── 人工修改（spec citar-table-manual-edit R4 / R5） ──
const edits = ref<ManualEditInfo[]>([])
const editedIds = computed(() => new Set(edits.value.map(e => e.row_id)))
const editingId = ref('')
const saving = ref(false)
const draft = reactive({ voucher_date: '', voucher_no: '', summary: '', account_code: '', account_name: '', debit_amount: '', credit_amount: '' })

async function loadEdits() {
  try {
    edits.value = await fetchManualEdits(props.projectId, props.year, 'ledger')
  } catch {
    edits.value = []
  }
}

function editedTitle(id: string): string {
  const e = edits.value.find(x => x.row_id === id)
  if (!e) return ''
  const o = e.original
  const when = e.edited_at ? e.edited_at.slice(0, 16).replace('T', ' ') : ''
  return `导入原值：${o.voucher_date ?? ''} ${o.voucher_no ?? ''} ${o.summary ?? ''} 借 ${fmtMoney(o.debit_amount, '0')} 贷 ${fmtMoney(o.credit_amount, '0')}\n最后修改：${when}`
}

function startEdit(r: JournalRow) {
  editingId.value = r.id
  draft.voucher_date = (r.voucher_date || '').slice(0, 10)
  draft.voucher_no = r.voucher_no || ''
  draft.summary = r.summary || ''
  draft.account_code = r.account_code || ''
  draft.account_name = r.account_name || ''
  draft.debit_amount = r.debit_amount ? String(r.debit_amount) : ''
  draft.credit_amount = r.credit_amount ? String(r.credit_amount) : ''
}

function money(text: string): number | null | undefined {
  const t = text.replace(/,/g, '').trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) ? n : undefined
}

async function saveEdit(r: JournalRow) {
  const debit = money(draft.debit_amount)
  const credit = money(draft.credit_amount)
  if (debit === undefined || credit === undefined) {
    ElMessage.warning('金额只能填数字')
    return
  }
  if (!draft.voucher_date || !draft.voucher_no.trim() || !draft.account_code.trim()) {
    ElMessage.warning('凭证日期、凭证号、科目编码不能为空')
    return
  }
  saving.value = true
  try {
    await editLedgerEntry(props.projectId, props.year, r.id, {
      voucher_date: draft.voucher_date,
      voucher_no: draft.voucher_no.trim(),
      summary: draft.summary.trim() || null,
      account_code: draft.account_code.trim(),
      account_name: draft.account_name.trim() || null,
      debit_amount: debit,
      credit_amount: credit,
    })
    editingId.value = ''
    ElMessage.success('分录已修改')
    await Promise.all([loadPage(pageIndex.value), loadEdits()])
  } catch (e) {
    handleApiError(e, '修改序时账')
  } finally {
    saving.value = false
  }
}

async function restore(r: JournalRow) {
  try {
    await ElMessageBox.confirm('恢复这条分录导入时的原值？', '恢复原值', { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' })
  } catch {
    return
  }
  saving.value = true
  try {
    await restoreLedgerRow(props.projectId, props.year, 'ledger', r.id)
    ElMessage.success('已恢复导入原值')
    await Promise.all([loadPage(pageIndex.value), loadEdits()])
  } catch (e) {
    handleApiError(e, '恢复分录')
  } finally {
    saving.value = false
  }
}

// 父组件改了级别（从科目余额表点科目进来等）：本组件自己发出的变更值相同，不重复加载
watch(
  () => viewKey(viewFromProps()),
  (key) => {
    if (key === viewKey(view.value)) return
    view.value = viewFromProps()
    codeInput.value = activeCode.value
    drillStack.value = []
    forgetDrill(props.projectId, props.year)
    reset()
  },
)

watch(() => [props.projectId, props.year], () => {
  editingId.value = ''
  loadFromMemory()
  void loadEdits()
}, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-journal__summary {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.citar-journal__row--edited td {
  background: #f6efff;
}

/* 穿透路径：全部科目 › 科目 1122 及下级 › 凭证 … */
.citar-journal__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: -4px 0 12px;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-6b6b76);
}

.citar-journal__crumb-sep {
  color: var(--citar-c-b4a8c2);
}

.citar-journal__crumb-current {
  font-weight: 700;
  color: var(--citar-c-4c1273);
}

.citar-journal__total td {
  font-weight: 700;
  background: var(--citar-c-fbf9fe);
  color: var(--citar-c-4c1273);
}

.citar-journal__unbalanced {
  margin: 8px 0 0;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-a3262a);
}

.citar-journal__tag {
  margin-left: 6px;
  padding: 0 4px;
  border: 1px solid #d7c3ee;
  border-radius: 3px;
  font-size: var(--citar-fs-11);
  color: var(--citar-c-6e0ba6);
}

.citar-journal__ops {
  white-space: nowrap;
}

.citar-journal__ops-head {
  width: 120px;
}

.citar-journal__input {
  width: 110px;
}

.citar-journal__input--wide {
  width: 200px;
}

.citar-journal__input--num {
  width: 110px;
  text-align: right;
}
</style>
