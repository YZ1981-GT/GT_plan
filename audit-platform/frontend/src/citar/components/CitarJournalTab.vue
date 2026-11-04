<template>
  <div>
    <div class="sheet-caption">
      <h2 class="sheet-caption__title">序时账</h2>
      <p class="sheet-caption__period">所属期间：{{ year ? `${year}年1月—12月` : '' }}</p>
      <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：元</span></div>
    </div>

    <div class="citar-toolbar">
      <input
        v-model.trim="codeInput"
        class="citar-search"
        type="search"
        placeholder="科目编码（含下级），留空看全部"
        @keydown.enter="applyFilter"
      />
      <button class="citar-btn" type="button" @click="applyFilter">查询</button>
      <button v-if="activeCode" class="citar-btn" type="button" @click="clearFilter">看全部分录</button>
      <span class="citar-toolbar__count">
        {{ activeCode ? `科目 ${activeCode} 及下级` : '全部科目' }}{{ total !== null ? `，共 ${total} 条分录` : '' }}
      </span>
      <span class="citar-toolbar__hint">{{ canManualEdit ? '每条分录可「修改」；序时账的修改不回写科目余额表' : MANUAL_EDIT_DENIED_TIP }}</span>
    </div>

    <div class="sheet-scroll">
      <table class="sheet-table">
        <thead>
          <tr>
            <th v-for="c in JOURNAL_COLUMNS" :key="c.key">{{ c.label }}</th>
            <th v-if="activeCode">余额</th>
            <th class="citar-journal__ops-head" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in items" :key="r.id" :class="{ 'citar-journal__row--edited': editedIds.has(r.id) }">
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
              <td v-if="activeCode" class="is-numeric">{{ fmtMoney(r.running_balance) }}</td>
              <td class="citar-center citar-journal__ops">
                <button class="citar-btn citar-btn--primary" type="button" :disabled="saving" @click="saveEdit(r)">{{ saving ? '保存中…' : '保存' }}</button>
                <button class="citar-btn" type="button" :disabled="saving" @click="editingId = ''">取消</button>
              </td>
            </template>
            <template v-else>
              <td>{{ r.voucher_date }}</td>
              <td>{{ r.voucher_no }}</td>
              <td class="citar-journal__summary" :title="r.summary || ''">{{ r.summary }}</td>
              <td>{{ r.account_code }}</td>
              <td class="citar-journal__summary" :title="r.account_name || ''">
                {{ r.account_name }}<span v-if="editedIds.has(r.id)" class="citar-journal__tag" :title="editedTitle(r.id)">已修改</span>
              </td>
              <td>{{ pickExtra(r, AUX_KEYS) }}</td>
              <td>{{ pickExtra(r, CURRENCY_KEYS) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.debit_amount, '') }}</td>
              <td class="is-numeric">{{ fmtMoney(r.credit_amount, '') }}</td>
              <td v-if="activeCode" class="is-numeric">{{ fmtMoney(r.running_balance) }}</td>
              <td class="citar-center citar-journal__ops">
                <template v-if="canManualEdit">
                  <button class="citar-btn" type="button" :disabled="saving" @click="startEdit(r)">修改</button>
                  <button v-if="editedIds.has(r.id)" class="citar-btn" type="button" :disabled="saving" @click="restore(r)">恢复</button>
                </template>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="loading" class="sheet-empty">正在读取序时账…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="!items.length" class="sheet-empty">
      {{ activeCode
        ? `序时账里没有编码以 ${activeCode} 开头的分录。若余额表有发生额，多半是序时账导入的科目编码与余额表不一致，可点「看全部分录」核对。`
        : '本年度还没有导入序时账' }}
    </p>

    <div v-if="items.length" class="citar-pager">
      <span>第 {{ pageIndex + 1 }} 页{{ pageCount ? ` / 共 ${pageCount} 页` : '' }}</span>
      <button class="citar-btn" type="button" :disabled="pageIndex === 0 || loading" @click="prevPage">上一页</button>
      <button class="citar-btn" type="button" :disabled="!hasMore || loading" @click="nextPage">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 序时账（未审）：
 * - 全部科目：GET /ledger/entries-all（页码分页；总数只在第 1 页返回）
 * - 指定科目：GET /ledger/entries/{code}*（含下级，游标分页，带累计余额）
 * 辅助核算 / 币种：平台没有专列，取导入时保留的额外列（extra_fields）里名字匹配的那一列。
 * 每条分录可人工修改、恢复导入原值（spec citar-table-manual-edit R4 / R5）；修改不回写余额表。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { JOURNAL_COLUMNS } from '../data/reportLines'
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
const AUX_KEYS = ['辅助核算', '核算维度', '辅助项', '辅助']
const CURRENCY_KEYS = ['币种', '币别', '货币']

const props = defineProps<{ projectId: string; year: number; entityName: string; accountCode?: string }>()
const { canManualEdit } = useManualEditPermission()
/** 筛选科目变化时通知父组件写回 ?account=，刷新不丢、也不残留旧筛选 */
const emit = defineEmits<{ 'update:accountCode': [code: string] }>()

const codeInput = ref(props.accountCode || '')
const activeCode = ref(props.accountCode || '')
const items = ref<JournalRow[]>([])
const total = ref<number | null>(null)
const loading = ref(false)
const error = ref('')
const pageIndex = ref(0)
const hasMore = ref(false)
/** 指定科目时的游标栈：cursors[i] 是第 i 页的起点（第 0 页为 null） */
const cursors = ref<(string | null)[]>([null])

const offset = computed(() => pageIndex.value * PAGE_SIZE)
const pageCount = computed(() => (total.value !== null ? Math.max(1, Math.ceil(total.value / PAGE_SIZE)) : 0))

function pickExtra(r: JournalRow, keys: string[]): string {
  const extra = r.extra_fields || {}
  for (const k of Object.keys(extra)) {
    if (keys.some(key => k.includes(key))) {
      const v = extra[k]
      return v === null || v === undefined ? '' : String(v)
    }
  }
  return ''
}

async function loadPage(index: number) {
  loading.value = true
  error.value = ''
  try {
    if (activeCode.value) {
      const code = activeCode.value.endsWith('*') ? activeCode.value : `${activeCode.value}*`
      const data: any = await api.get(P_ledger.entries(props.projectId, code), {
        params: { year: props.year, limit: PAGE_SIZE, ...(cursors.value[index] ? { cursor: cursors.value[index] } : {}) },
      })
      items.value = data?.items || []
      hasMore.value = !!data?.has_more
      if (typeof data?.total === 'number') total.value = data.total
      if (data?.next_cursor) cursors.value[index + 1] = data.next_cursor
    } else {
      const data: any = await api.get(P_ledger.entriesAll(props.projectId), {
        params: { year: props.year, page: index + 1, page_size: PAGE_SIZE },
      })
      items.value = data?.items || []
      if (index === 0) total.value = typeof data?.total === 'number' ? data.total : null
      hasMore.value = total.value !== null ? (index + 1) * PAGE_SIZE < total.value : items.value.length === PAGE_SIZE
    }
    pageIndex.value = index
  } catch (e: any) {
    items.value = []
    error.value = e?.message || '读取序时账失败'
  } finally {
    loading.value = false
  }
}

function reset() {
  cursors.value = [null]
  total.value = null
  void loadPage(0)
}

function applyFilter() {
  activeCode.value = codeInput.value.replace(/\*+$/, '')
  emit('update:accountCode', activeCode.value)
  reset()
}

function clearFilter() {
  codeInput.value = ''
  activeCode.value = ''
  emit('update:accountCode', '')
  reset()
}

function nextPage() {
  if (hasMore.value) void loadPage(pageIndex.value + 1)
}

function prevPage() {
  if (pageIndex.value > 0) void loadPage(pageIndex.value - 1)
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

// 从科目余额表点科目进来：父组件改 accountCode（本组件自己发出的变更值相同，不重复加载）
watch(
  () => props.accountCode,
  (code) => {
    if ((code || '') === activeCode.value) return
    codeInput.value = code || ''
    activeCode.value = code || ''
    reset()
  },
)

watch(() => [props.projectId, props.year], () => {
  editingId.value = ''
  reset()
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
