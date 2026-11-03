<template>
  <div>
    <p v-if="loading && !accounts.length" class="sheet-empty">正在按取数规则核对科目与底稿…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <p v-else-if="!accounts.length" class="sheet-empty">{{ notices[0] || '本年度还没有导入科目余额表。请先在「数据导入」上传账套。' }}</p>
    <template v-else>
      <div class="wpmap-summary">
        <span>有余额或发生额的 <b>{{ activeCount }}</b> 个科目中，<b>{{ coveredCount }}</b> 个进入税审底稿</span>
        <span v-if="pendingCount" class="wpmap-summary__warn">{{ pendingCount }} 个科目规则指向了底稿但没取到数（橙色虚线框，悬停看原因）</span>
        <span v-if="unmappedCount" class="wpmap-summary__warn">
          {{ unmappedCount }} 个未映射标准科目，可能取不到数：
          <button class="wpmap-link" type="button" @click="emit('go-standard')">去映射</button>
        </span>
        <span v-if="hiddenSheets.length" :title="hiddenSheets.map(c => `${c} ${sheetName(c)}`).join('\n')">
          已隐藏税审底稿目录里标为「无」的 {{ hiddenSheets.length }} 张底稿
        </span>
      </div>

      <div class="citar-toolbar">
        <input v-model.trim="keyword" class="citar-search" type="search" placeholder="按科目编码、名称或标准科目筛选" />
        <select v-model="sheetFilter" class="citar-search wpmap-select">
          <option value="">全部底稿</option>
          <option value="none">未进税审底稿</option>
          <option v-for="s in sheetOptions" :key="s.code" :value="s.code">{{ s.code }} {{ s.name }}</option>
        </select>
        <label class="citar-check"><input v-model="activeOnly" type="checkbox" /> 只看有余额或发生额</label>
        <span class="citar-toolbar__count">共 {{ shown.length }} 个科目</span>
        <span class="citar-toolbar__hint">按税审底稿取数规则推算，只读；点底稿编号打开该底稿</span>
      </div>

      <div class="sheet-scroll">
        <table class="sheet-table wpmap-table">
          <thead>
            <tr>
              <th>客户科目编码</th><th>客户科目名称</th><th>标准科目</th>
              <th>本期借方</th><th>本期贷方</th><th>期末方向</th><th>期末余额</th><th>对应税审底稿</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in shown" :key="a.code" :class="{ 'citar-row--parent': a.level === 1 }">
              <td>{{ a.code }}</td>
              <td :style="{ paddingLeft: `${10 + (a.level - 1) * 12}px` }">{{ a.name }}</td>
              <td>
                <template v-if="a.standard_code">{{ a.standard_code }} {{ a.standard_name || '' }}</template>
                <span v-else class="wpmap-muted">未映射</span>
              </td>
              <td class="is-numeric">{{ fmtMoney(a.debit) }}</td>
              <td class="is-numeric">{{ fmtMoney(a.credit) }}</td>
              <td class="citar-center">{{ a.closingSide.dir }}</td>
              <td class="is-numeric">{{ fmtMoney(a.closingSide.amount) }}</td>
              <td class="wpmap-sheets">
                <button
                  v-for="c in a.workpapers"
                  :key="c"
                  class="wpmap-chip"
                  :class="{ 'wpmap-chip--inherited': !a.direct.includes(c) }"
                  type="button"
                  :title="chipTitle(c, a.direct.includes(c))"
                  @click="openSheet(c)"
                >{{ c }} {{ sheetName(c) }}</button>
                <button
                  v-for="p in a.pending"
                  :key="`p-${p.code}`"
                  class="wpmap-chip wpmap-chip--pending"
                  type="button"
                  :title="pendingTitle(p)"
                  @click="openSheet(p.code)"
                >{{ p.code }} {{ sheetName(p.code) }}</button>
                <span v-if="!a.workpapers.length && !a.pending.length" class="wpmap-muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!shown.length" class="sheet-empty">没有符合筛选条件的科目</p>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 底稿映射页「科目 → 税审底稿」页签（spec citar-account-workpaper-map）。
 *
 * GET /tax-workpapers/account-map：后端用税审底稿取数的同一执行器逐条跑规则，
 * 返回每个客户科目实际取数用到的底稿（含上级 / 下级）与「规则指向但没取到」的底稿及原因。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { taxWorkpapers as P_tw } from '@/services/apiPaths'
import { findTaxWorkpaperSheet, saveActiveTaxSheet } from '@/views/tax-workpapers/taxWorkpaperIndex'
import { loadMarks } from '@/views/tax-workpapers/taxWorkpaperMarks'
import { fmtMoney, splitDirection } from '../useCitarProject'

interface PendingSheet {
  code: string
  reasons: string[]
}

interface AccountRow {
  code: string
  name: string
  level: number
  parent: string | null
  standard_code: string | null
  standard_name: string | null
  debit: string
  credit: string
  /** 借正贷负 */
  closing: string
  has_activity: boolean
  workpapers: string[]
  /** 取数直接用到本科目的底稿（其余为经上级 / 下级进入） */
  direct: string[]
  pending: PendingSheet[]
}

interface AccountMapResult {
  year: number
  accounts: AccountRow[]
  notices: string[]
}

const props = defineProps<{ projectId: string; year: number; refreshKey: number }>()
const emit = defineEmits<{ 'go-standard': [] }>()
const router = useRouter()

const accounts = ref<AccountRow[]>([])
const notices = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const sheetFilter = ref('')
const activeOnly = ref(true)

const sheetName = (code: string) => findTaxWorkpaperSheet(code)?.name || ''

/** 税审底稿目录里标为「无」的底稿（本项目不适用，如民非 / 金融业专用表）：不在这里列出 */
const absentCodes = ref<ReadonlySet<string>>(new Set())

function refreshMarks() {
  const marks = loadMarks(props.projectId)
  absentCodes.value = new Set(Object.keys(marks).filter(code => marks[code] === 'absent'))
}

/** 去掉标为「无」的底稿后的科目行 */
const visible = computed(() => {
  const absent = absentCodes.value
  return accounts.value.map(a => ({
    ...a,
    workpapers: a.workpapers.filter(c => !absent.has(c)),
    pending: a.pending.filter(p => !absent.has(p.code)),
  }))
})

/** 本项目出现过、但因标为「无」而不显示的底稿 */
const hiddenSheets = computed(() => {
  const absent = absentCodes.value
  const codes = new Set<string>()
  for (const a of accounts.value) {
    a.workpapers.forEach(c => absent.has(c) && codes.add(c))
    a.pending.forEach(p => absent.has(p.code) && codes.add(p.code))
  }
  return [...codes].sort((x, y) => x.localeCompare(y, 'zh-CN', { numeric: true }))
})

const rows = computed(() => visible.value.map(a => ({ ...a, closingSide: splitDirection(a.closing) })))

const active = computed(() => visible.value.filter(a => a.has_activity))
const activeCount = computed(() => active.value.length)
const coveredCount = computed(() => active.value.filter(a => a.workpapers.length).length)
const pendingCount = computed(() => active.value.filter(a => a.pending.length && !a.workpapers.length).length)
const unmappedCount = computed(() => active.value.filter(a => !a.standard_code).length)

/** 下拉里只列出本项目实际出现的底稿 */
const sheetOptions = computed(() => {
  const codes = new Set<string>()
  for (const a of visible.value) {
    a.workpapers.forEach(c => codes.add(c))
    a.pending.forEach(p => codes.add(p.code))
  }
  return [...codes]
    .sort((x, y) => x.localeCompare(y, 'zh-CN', { numeric: true }))
    .map(code => ({ code, name: sheetName(code) }))
})

const shown = computed(() => {
  const kw = keyword.value
  const sheet = sheetFilter.value
  return rows.value.filter((a) => {
    if (activeOnly.value && !a.has_activity) return false
    if (sheet === 'none' && (a.workpapers.length || a.pending.length)) return false
    if (sheet && sheet !== 'none' && !a.workpapers.includes(sheet) && !a.pending.some(p => p.code === sheet)) return false
    if (!kw) return true
    return [a.code, a.name, a.standard_code, a.standard_name].some(v => (v || '').includes(kw))
  })
})

function chipTitle(code: string, isDirect: boolean): string {
  const name = sheetName(code)
  return isDirect ? `${code} ${name}：取数直接用到本科目` : `${code} ${name}：经上级或下级科目进入`
}

function pendingTitle(p: PendingSheet): string {
  const head = `${p.code} ${sheetName(p.code)}：规则指向本科目，但没取到数`
  return p.reasons.length ? `${head}\n${p.reasons.join('\n')}` : head
}

function openSheet(code: string) {
  saveActiveTaxSheet(props.projectId, code)
  router.push({ path: `/projects/${props.projectId}/workpapers`, query: { year: String(props.year) } })
}

async function load() {
  refreshMarks()
  loading.value = true
  error.value = ''
  try {
    const res = (await api.get(P_tw.accountMap(props.projectId), { params: { year: props.year } })) as AccountMapResult
    accounts.value = Array.isArray(res?.accounts) ? res.accounts : []
    notices.value = Array.isArray(res?.notices) ? res.notices : []
  } catch (e: any) {
    accounts.value = []
    error.value = e?.response?.data?.detail || e?.message || '读取科目与底稿对应关系失败'
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.year, props.refreshKey], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.wpmap-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--citar-c-fbf9fe);
  font-size: var(--citar-fs-13);
  color: var(--citar-c-5c5c68);
}

.wpmap-summary b {
  color: var(--citar-c-6e0ba6);
}

.wpmap-summary__warn {
  color: var(--citar-c-8a5300);
}

.wpmap-link {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: var(--citar-c-6e0ba6);
  text-decoration: underline;
  cursor: pointer;
}

.wpmap-select {
  width: 260px;
}

.wpmap-table td {
  vertical-align: middle;
}

/* 表格单元格默认不换行（unaudited.css）；一个科目进多张底稿时标签换行，不把整列撑出可视区 */
.wpmap-table td.wpmap-sheets {
  min-width: 260px;
  white-space: normal;
}

.wpmap-chip {
  margin: 2px 6px 2px 0;
  padding: 1px 8px;
  border: 1px solid #d9c4ee;
  border-radius: 10px;
  background: var(--citar-c-f1e7fb);
  font: inherit;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-5b2a86);
  cursor: pointer;
  white-space: nowrap;
}

.wpmap-chip:hover {
  border-color: #8b3fd0;
}

/* 经上级 / 下级进入：浅一档 */
.wpmap-chip--inherited {
  background: var(--citar-c-ffffff);
}

/* 规则指向但没取到数：虚线框、橙字 */
.wpmap-chip--pending {
  border-style: dashed;
  border-color: #f0d9b5;
  background: var(--citar-c-fffaf2);
  color: var(--citar-c-8a5300);
}

.wpmap-muted {
  color: var(--citar-c-9a9aa4);
}
</style>
