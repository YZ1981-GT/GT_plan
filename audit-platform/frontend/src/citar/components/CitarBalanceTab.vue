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
      <label v-if="editedIds.size" class="citar-check"><input v-model="editedOnly" type="checkbox" /> 只看已修改（{{ editedIds.size }}）</label>
      <span class="citar-toolbar__count">共 {{ shown.length }} 个科目</span>
      <span class="citar-toolbar__hint">{{ canManualEdit ? '点科目行查看该科目序时账；末级科目可「修改」，上级随之汇总、试算表随之重算' : `点科目行查看该科目序时账；${MANUAL_EDIT_DENIED_TIP}` }}</span>
    </div>

    <div class="sheet-scroll">
      <table class="sheet-table">
        <thead>
          <tr><th v-for="c in TRIAL_BALANCE_COLUMNS" :key="c.key">{{ c.label }}</th><th class="citar-balance__ops-head" /></tr>
        </thead>
        <tbody>
          <tr
            v-for="(r, i) in shown"
            :key="r.account_code"
            class="citar-row--link"
            :data-locate="normCode(r.account_code)"
            :class="{
              'citar-row--parent': r.level === 1,
              'citar-balance__row--edited': editedIds.has(r.id ?? ''),
              'citar-located': isLocated(r.account_code),
            }"
            @click="editingId !== r.id && emit('open-account', r.account_code)"
          >
            <td class="is-numeric">{{ i + 1 }}</td>
            <td>{{ r.account_code }}</td>
            <td :style="{ paddingLeft: `${10 + Math.max(0, (r.level || 1) - 1) * 12}px` }">
              {{ r.account_name }}
              <span v-if="editedIds.has(r.id ?? '')" class="citar-balance__tag" :title="editedTitle(r)">已修改</span>
              <span v-else-if="childEdited(r)" class="citar-balance__tag citar-balance__tag--muted">下级已修改</span>
            </td>
            <template v-if="editingId && editingId === r.id">
              <td class="citar-center">{{ draftSide('opening').dir }}</td>
              <td @click.stop><input v-model="draft.opening" class="citar-search citar-balance__input" aria-label="期初余额（借正贷负）" @input="autoClosing" /></td>
              <td @click.stop><input v-model="draft.debit" class="citar-search citar-balance__input" aria-label="本期借方" @input="autoClosing" /></td>
              <td @click.stop><input v-model="draft.credit" class="citar-search citar-balance__input" aria-label="本期贷方" @input="autoClosing" /></td>
              <td class="citar-center">{{ draftSide('closing').dir }}</td>
              <td @click.stop><input v-model="draft.closing" class="citar-search citar-balance__input" aria-label="期末余额（借正贷负）" @input="closingTouched = true" /></td>
              <td class="citar-center citar-balance__ops" @click.stop>
                <button class="citar-btn citar-btn--primary" type="button" :disabled="saving" @click="saveEdit(r)">{{ saving ? '保存中…' : '保存' }}</button>
                <button class="citar-btn" type="button" :disabled="saving" @click="editingId = ''">取消</button>
              </td>
            </template>
            <template v-else>
              <td class="citar-center">{{ r.opening.dir }}</td>
              <td class="is-numeric">{{ fmtMoney(r.opening.amount) }}</td>
              <!-- 后端补齐的父级行发生额为 0 时返回 null：与 0 同样显示「-」 -->
              <td class="is-numeric">{{ fmtMoney(r.debit_amount ?? 0) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.credit_amount ?? 0) }}</td>
              <td class="citar-center">{{ r.closing.dir }}</td>
              <td class="is-numeric">{{ fmtMoney(r.closing.amount) }}</td>
              <td class="citar-center citar-balance__ops" @click.stop>
                <template v-if="canEdit(r)">
                  <button class="citar-btn" type="button" :disabled="saving" @click="startEdit(r)">修改</button>
                  <button v-if="editedIds.has(r.id ?? '')" class="citar-btn" type="button" :disabled="saving" @click="restore(r)">恢复</button>
                </template>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="editingId" class="citar-balance__hint">金额按「借正贷负」填写：贷方余额填负数。期末余额随期初 + 借方 − 贷方自动算出，也可直接改。</p>
    <p v-if="loading" class="sheet-empty">正在读取科目余额表…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="!rows.length" class="sheet-empty">本年度还没有导入账套。请先在「数据导入」上传科目余额表与序时账。</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 科目余额表（未审，客户科目口径）：GET /ledger/balance —— 导入的 tb_balance，
 * 缺失的父级科目由后端按下级汇总补齐（_is_synthetic）。
 * 末级科目可人工修改（spec citar-table-manual-edit R3 / R5）：上级随之同步、试算表未审数随之重算；
 * 改过的行标「已修改」，可恢复导入原值。
 */
import { computed, reactive, ref, toRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { TRIAL_BALANCE_COLUMNS } from '../data/reportLines'
import { editBalanceRow, fetchManualEdits, parseMoneyInput, restoreLedgerRow, type ManualEditInfo } from '../citarLedgerEdits'
import { fmtMoney } from '../useCitarProject'
import { normCode, useCitarRowLocate } from '../useCitarRowLocate'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

interface BalanceRow {
  /** 导入行 id；后端补齐的上级汇总行没有 */
  id?: string
  account_code: string
  account_name: string
  level: number | null
  opening_balance: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
  opening_direction: string | null
  closing_direction: string | null
  _is_synthetic?: boolean
}

/** locateCode：从「数据源头」跳来时要定位的客户科目（spec citar-fs-issue-source-locate） */
const props = defineProps<{ projectId: string; year: number; entityName: string; locateCode?: string }>()
const { canManualEdit } = useManualEditPermission()
const emit = defineEmits<{ 'open-account': [code: string]; changed: [] }>()
const { isLocated, apply: applyLocate } = useCitarRowLocate(toRef(props, 'locateCode'))

const rows = ref<BalanceRow[]>([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const leafOnly = ref(false)
const editedOnly = ref(false)
const edits = ref<ManualEditInfo[]>([])
const editingId = ref('')
const saving = ref(false)
const draft = reactive({ opening: '', debit: '', credit: '', closing: '' })
const closingTouched = ref(false)

const editedIds = computed(() => new Set(edits.value.map(e => e.row_id)))
const editById = computed(() => new Map(edits.value.map(e => [e.row_id, e])))

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

/** 借正贷负 */
function signedOf(amount: number | null, direction: string | null): number {
  const n = Number(amount || 0)
  if (direction === 'credit') return -Math.abs(n)
  if (direction === 'debit') return Math.abs(n)
  return n
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

const editedCodes = computed(() => rows.value.filter(r => r.id && editedIds.value.has(r.id)).map(r => r.account_code))

function childEdited(r: BalanceRow): boolean {
  return parents.value.has(r.account_code) && editedCodes.value.some(c => c !== r.account_code && c.startsWith(r.account_code))
}

const shown = computed(() => {
  const kw = keyword.value
  return rows.value
    .filter(r => !kw || r.account_code.includes(kw) || (r.account_name || '').includes(kw))
    .filter(r => !leafOnly.value || !parents.value.has(r.account_code))
    .filter(r => !editedOnly.value || (r.id && editedIds.value.has(r.id)) || childEdited(r))
    .map(r => ({
      ...r,
      opening: side(r.opening_balance, r.opening_direction),
      closing: side(r.closing_balance, r.closing_direction),
    }))
})

function canEdit(r: BalanceRow): boolean {
  if (!canManualEdit.value) return false
  return Boolean(r.id) && !r._is_synthetic && !parents.value.has(r.account_code)
}

function editedTitle(r: BalanceRow): string {
  const e = editById.value.get(r.id ?? '')
  if (!e) return ''
  const o = e.original
  const opening = signedOf(o.opening_balance === null ? null : Number(o.opening_balance), o.opening_direction)
  const closing = signedOf(o.closing_balance === null ? null : Number(o.closing_balance), o.closing_direction)
  return [
    `导入原值：期初 ${fmtMoney(opening)}、借方 ${fmtMoney(Number(o.debit_amount || 0))}、贷方 ${fmtMoney(Number(o.credit_amount || 0))}、期末 ${fmtMoney(closing)}`,
    `修改 ${e.count} 次${e.edited_at ? `，最近 ${e.edited_at.slice(0, 16).replace('T', ' ')}` : ''}${e.reason ? `，原因：${e.reason}` : ''}`,
  ].join('\n')
}

function draftSide(kind: 'opening' | 'closing') {
  const n = parseMoneyInput(draft[kind])
  return side(Number.isNaN(n) ? 0 : n, null)
}

function startEdit(r: BalanceRow) {
  editingId.value = r.id ?? ''
  draft.opening = String(signedOf(r.opening_balance, r.opening_direction))
  draft.debit = String(r.debit_amount ?? 0)
  draft.credit = String(r.credit_amount ?? 0)
  draft.closing = String(signedOf(r.closing_balance, r.closing_direction))
  closingTouched.value = false
}

/** 期末 = 期初 + 借方 − 贷方（用户直接改过期末就不再自动算） */
function autoClosing() {
  if (closingTouched.value) return
  const [o, d, c] = [draft.opening, draft.debit, draft.credit].map(parseMoneyInput)
  if ([o, d, c].some(Number.isNaN)) return
  draft.closing = String(Math.round((o + d - c) * 100) / 100)
}

async function saveEdit(r: BalanceRow) {
  if (!r.id) return
  const values = {
    opening: parseMoneyInput(draft.opening),
    debit: parseMoneyInput(draft.debit),
    credit: parseMoneyInput(draft.credit),
    closing: parseMoneyInput(draft.closing),
  }
  if (Object.values(values).some(Number.isNaN)) {
    ElMessage.warning('金额只能填数字')
    return
  }
  saving.value = true
  try {
    await editBalanceRow(props.projectId, props.year, r.id, values)
    editingId.value = ''
    ElMessage.success(`${r.account_code} 已修改，试算表已重算`)
    await load()
    emit('changed')
  } catch (e) {
    handleApiError(e, '修改科目余额')
  } finally {
    saving.value = false
  }
}

async function restore(r: BalanceRow) {
  if (!r.id) return
  try {
    await ElMessageBox.confirm(`把 ${r.account_code} ${r.account_name} 恢复为导入时的原值？上级科目随之回调，试算表会重算。`, '恢复导入原值', {
      confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  saving.value = true
  try {
    await restoreLedgerRow(props.projectId, props.year, 'balance', r.id)
    ElMessage.success(`${r.account_code} 已恢复导入原值`)
    await load()
    emit('changed')
  } catch (e) {
    handleApiError(e, '恢复科目余额')
  } finally {
    saving.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [data, changed] = await Promise.all([
      api.get(P_ledger.balance(props.projectId), { params: { year: props.year } }),
      fetchManualEdits(props.projectId, props.year, 'balance').catch(() => [] as ManualEditInfo[]),
    ])
    rows.value = Array.isArray(data) ? (data as BalanceRow[]) : []
    edits.value = changed
  } catch (e: any) {
    rows.value = []
    error.value = e?.message || '读取科目余额表失败'
  } finally {
    loading.value = false
  }
  await locateRow()
}

/** 定位行：清掉会挡住它的筛选 */
async function locateRow() {
  if (loading.value || error.value) return
  await applyLocate(
    code => rows.value.some(r => normCode(r.account_code) === code),
    () => {
      keyword.value = ''
      leafOnly.value = false
      editedOnly.value = false
    },
    `科目余额表里没有科目 ${normCode(props.locateCode)}`,
  )
}

watch(() => [props.projectId, props.year], () => {
  editingId.value = ''
  void load()
}, { immediate: true })
watch(() => props.locateCode, () => void locateRow())
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-balance__ops-head {
  width: 120px;
}

.citar-balance__ops {
  white-space: nowrap;
}

.citar-balance__input {
  width: 120px;
  text-align: right;
}

.citar-balance__row--edited td {
  background: #f6efff;
}

.citar-balance__tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 8px;
  background: #ece0fa;
  font-size: var(--citar-fs-11);
  color: var(--citar-c-6e0ba6);
}

.citar-balance__tag--muted {
  background: #f1f1f4;
  color: var(--citar-c-6b6b76);
}

.citar-balance__hint {
  margin: 8px 0 0;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-6b6b76);
}
</style>
