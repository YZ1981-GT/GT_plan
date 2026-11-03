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
    </div>

    <div class="sheet-scroll">
      <table class="sheet-table">
        <thead>
          <tr>
            <th v-for="c in JOURNAL_COLUMNS" :key="c.key">{{ c.label }}</th>
            <th v-if="activeCode">余额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in items" :key="r.id">
            <td class="is-numeric">{{ offset + i + 1 }}</td>
            <td>{{ r.voucher_date }}</td>
            <td>{{ r.voucher_no }}</td>
            <td class="citar-journal__summary" :title="r.summary || ''">{{ r.summary }}</td>
            <td>{{ r.account_code }}</td>
            <td class="citar-journal__summary" :title="r.account_name || ''">{{ r.account_name }}</td>
            <td>{{ pickExtra(r, AUX_KEYS) }}</td>
            <td>{{ pickExtra(r, CURRENCY_KEYS) }}</td>
            <td class="is-numeric">{{ fmtMoney(r.debit_amount, '') }}</td>
            <td class="is-numeric">{{ fmtMoney(r.credit_amount, '') }}</td>
            <td v-if="activeCode" class="is-numeric">{{ fmtMoney(r.running_balance) }}</td>
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
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { JOURNAL_COLUMNS } from '../data/reportLines'
import { fmtMoney } from '../useCitarProject'

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

watch(() => [props.projectId, props.year], reset, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-journal__summary {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
