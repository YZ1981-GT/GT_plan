<template>
  <div>
    <div class="sheet-caption">
      <h2 class="sheet-caption__title">科目余额表</h2>
      <p class="sheet-caption__period">所属期间：{{ year ? `${year}年1月—12月` : '' }}</p>
      <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：元</span></div>
    </div>

    <div class="citar-toolbar">
      <input v-model.trim="keyword" class="citar-search" type="search" placeholder="按科目编码或名称筛选" />
      <label class="citar-check"><input v-model="leafOnly" type="checkbox" /> 只看末级科目</label>
      <span class="citar-toolbar__count">共 {{ shown.length }} 个科目</span>
      <span class="citar-toolbar__hint">点科目行查看该科目序时账</span>
    </div>

    <div class="sheet-scroll">
      <table class="sheet-table">
        <thead>
          <tr><th v-for="c in TRIAL_BALANCE_COLUMNS" :key="c.key">{{ c.label }}</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="(r, i) in shown"
            :key="r.account_code"
            class="citar-row--link"
            :class="{ 'citar-row--parent': r.level === 1 }"
            @click="emit('open-account', r.account_code)"
          >
            <td class="is-numeric">{{ i + 1 }}</td>
            <td>{{ r.account_code }}</td>
            <td :style="{ paddingLeft: `${10 + Math.max(0, (r.level || 1) - 1) * 12}px` }">{{ r.account_name }}</td>
            <td class="citar-center">{{ r.opening.dir }}</td>
            <td class="is-numeric">{{ fmtMoney(r.opening.amount) }}</td>
            <!-- 后端补齐的父级行发生额为 0 时返回 null：与 0 同样显示「-」 -->
            <td class="is-numeric">{{ fmtMoney(r.debit_amount ?? 0) }}</td>
            <td class="is-numeric">{{ fmtMoney(r.credit_amount ?? 0) }}</td>
            <td class="citar-center">{{ r.closing.dir }}</td>
            <td class="is-numeric">{{ fmtMoney(r.closing.amount) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="loading" class="sheet-empty">正在读取科目余额表…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="!rows.length" class="sheet-empty">本年度还没有导入账套。请先在「数据导入」上传科目余额表与序时账。</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 科目余额表（未审，客户科目口径）：GET /ledger/balance —— 导入的 tb_balance，
 * 缺失的父级科目由后端按下级汇总补齐（_is_synthetic）。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { TRIAL_BALANCE_COLUMNS } from '../data/reportLines'
import { fmtMoney } from '../useCitarProject'

interface BalanceRow {
  account_code: string
  account_name: string
  level: number | null
  opening_balance: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
  opening_direction: string | null
  closing_direction: string | null
}

const props = defineProps<{ projectId: string; year: number; entityName: string }>()
const emit = defineEmits<{ 'open-account': [code: string] }>()

const rows = ref<BalanceRow[]>([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const leafOnly = ref(false)

/**
 * 余额 + 方向列 → 显示用方向与正数金额。
 * 余额表有两种存法：无符号金额 + 方向列，或借正贷负。方向列优先，负数再翻向。
 */
function side(amount: number | null, direction: string | null) {
  const n = Number(amount || 0)
  if (Math.abs(n) < 0.005) return { dir: '平', amount: 0 }
  let dir = direction === 'credit' ? '贷' : '借'
  if (n < 0) dir = dir === '借' ? '贷' : '借'
  return { dir, amount: Math.abs(n) }
}

/** 有下级的科目（后端按科目编码排序：下一行编码以本行开头且更长即为下级） */
const parents = computed(() => {
  const set = new Set<string>()
  const list = rows.value
  for (let i = 0; i < list.length - 1; i += 1) {
    const code = list[i].account_code
    const next = list[i + 1].account_code
    if (next.length > code.length && next.startsWith(code)) set.add(code)
  }
  return set
})

const shown = computed(() => {
  const kw = keyword.value
  return rows.value
    .filter(r => !kw || r.account_code.includes(kw) || (r.account_name || '').includes(kw))
    .filter(r => !leafOnly.value || !parents.value.has(r.account_code))
    .map(r => ({
      ...r,
      opening: side(r.opening_balance, r.opening_direction),
      closing: side(r.closing_balance, r.closing_direction),
    }))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.get(P_ledger.balance(props.projectId), { params: { year: props.year } })
    rows.value = Array.isArray(data) ? (data as BalanceRow[]) : []
  } catch (e: any) {
    rows.value = []
    error.value = e?.message || '读取科目余额表失败'
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.year], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
