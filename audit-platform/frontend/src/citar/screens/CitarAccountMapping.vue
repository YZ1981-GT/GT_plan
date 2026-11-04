<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">底稿映射</h1>
      <span class="aud-header__note">{{ TAB_NOTES[tab] }}</span>
    </header>

    <nav class="aud-tabs">
      <button
        v-for="t in TABS"
        :key="t.key"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === t.key }"
        type="button"
        @click="tab = t.key"
      >
        {{ t.label }}
        <span v-if="t.key === 'standard' && unmapped.length" class="citar-map__badge">{{ unmapped.length }}</span>
      </button>
    </nav>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <!-- 两个页签都用 v-show：切换不重新读取，第二个页签里未保存的输入也保留 -->
      <div v-if="year" v-show="tab === 'workpaper'">
        <CitarWorkpaperMapTab :project-id="projectId" :year="year" :refresh-key="refreshKey" @go-standard="tab = 'standard'" />
      </div>
      <div v-if="year" v-show="tab === 'standard'">
        <div class="citar-map__summary">
          <div>
            <span class="citar-map__rate">{{ rate.completion_rate.toLocaleString('zh-CN', { maximumFractionDigits: 1 }) }}%</span>
            <span>已映射 {{ rate.mapped_count }} / {{ rate.total_count }} 个客户科目</span>
          </div>
          <span v-if="unmapped.length" class="citar-map__warn">有余额未映射 {{ unmapped.length }} 个：不映射就不会进入试算表</span>
          <button class="citar-btn" type="button" :disabled="loading || busy" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="busy" @click="autoMatch">
            {{ busy ? '匹配中…' : '智能匹配' }}
          </button>
        </div>

        <datalist :id="DATALIST_ID">
          <option v-for="s in standards" :key="s.code" :value="s.code">{{ s.name }}</option>
        </datalist>

        <!-- 有余额未映射：优先处理 -->
        <template v-if="unmapped.length">
          <h3 class="citar-map__heading">有余额未映射的客户科目</h3>
          <table class="sheet-table citar-map__table">
            <thead>
              <tr><th>客户科目编码</th><th>客户科目名称</th><th>期末余额</th><th>映射到标准科目</th><th /></tr>
            </thead>
            <tbody>
              <tr
                v-for="u in unmapped"
                :key="u.account_code"
                :data-locate="normCode(u.account_code)"
                :class="{ 'citar-located': isLocated(u.account_code) }"
              >
                <td>{{ u.account_code }}</td>
                <td>{{ u.account_name }}</td>
                <td class="is-numeric">{{ fmtMoney(u.closing_balance) }}</td>
                <td>
                  <input v-model.trim="pending[u.account_code]" class="citar-search citar-map__input" :list="DATALIST_ID" placeholder="标准科目编码" />
                  <span class="citar-map__name">{{ standardName(pending[u.account_code]) }}</span>
                </td>
                <td class="citar-center">
                  <button class="citar-btn" type="button" :disabled="busy || !pending[u.account_code]" @click="createMapping(u)">保存</button>
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <h3 class="citar-map__heading">已映射</h3>
        <div class="citar-toolbar">
          <input v-model.trim="keyword" class="citar-search" type="search" placeholder="按客户或标准科目筛选" />
          <span class="citar-toolbar__count">共 {{ shown.length }} 条</span>
        </div>
        <div class="sheet-scroll">
          <table class="sheet-table citar-map__table">
            <thead>
              <tr><th>客户科目编码</th><th>客户科目名称</th><th>标准科目编码</th><th>标准科目名称</th><th>映射方式</th><th /></tr>
            </thead>
            <tbody>
              <tr
                v-for="m in shown"
                :key="m.id"
                :data-locate="normCode(m.original_account_code)"
                :class="{ 'citar-located': isLocated(m.original_account_code) }"
              >
                <td>{{ m.original_account_code }}</td>
                <td>{{ m.original_account_name }}</td>
                <td>
                  <input
                    v-if="editingId === m.id"
                    v-model.trim="editingCode"
                    class="citar-search citar-map__input"
                    :list="DATALIST_ID"
                    @keydown.enter="saveEdit(m)"
                  />
                  <template v-else>{{ m.standard_account_code }}</template>
                </td>
                <td>{{ standardName(editingId === m.id ? editingCode : m.standard_account_code) }}</td>
                <td class="citar-center">{{ MAPPING_TYPE_LABELS[m.mapping_type] || m.mapping_type }}</td>
                <td class="citar-center citar-map__ops">
                  <template v-if="editingId === m.id">
                    <button class="citar-btn" type="button" :disabled="busy" @click="editingId = ''">取消</button>
                    <button class="citar-btn citar-btn--primary" type="button" :disabled="busy || !editingCode" @click="saveEdit(m)">保存</button>
                  </template>
                  <button v-else class="citar-btn" type="button" :disabled="busy" @click="startEdit(m)">修改</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="loading" class="sheet-empty">正在读取映射…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>
        <p v-else-if="!mappings.length" class="sheet-empty">还没有映射。导入账套后会智能匹配一次，也可点「智能匹配」。</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 底稿映射，两个页签（spec citar-account-workpaper-map）：
 * - 科目 → 底稿（默认）：客户科目进入哪些税审底稿，按取数规则推算、只读（CitarWorkpaperMapTab）；
 * - 客户科目 → 标准科目：接平台 /mapping 端点；映射保存后后端发 MAPPING_CHANGED，试算表按新映射重算（平台既有链路），
 *   第一个页签随之重新读取。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { accountChart as P_chart, accountMapping as P_map } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import CitarWorkpaperMapTab from '../components/CitarWorkpaperMapTab.vue'
import { fmtMoney, useCitarProject } from '../useCitarProject'
import { normCode, useCitarRowLocate } from '../useCitarRowLocate'

defineOptions({ name: 'CitarAccountMapping' })

/** 从「数据源头」跳来：?tab=standard&locate=客户科目（spec citar-fs-issue-source-locate） */
const { code: locateCode, isLocated, apply: applyLocate } = useCitarRowLocate()

type TabKey = 'workpaper' | 'standard'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'workpaper', label: '科目 → 底稿' },
  { key: 'standard', label: '客户科目 → 标准科目' },
]
const TAB_NOTES: Record<TabKey, string> = {
  workpaper: '客户科目进入哪些税审底稿：按税审底稿取数规则推算',
  standard: '客户科目 → 标准科目：试算平衡表、审定报表与底稿取数都按标准科目汇总',
}
const tab = ref<TabKey>(locateCode.value ? 'standard' : 'workpaper')
/** 标准科目映射改动后 +1，「科目 → 底稿」重新读取 */
const refreshKey = ref(0)

interface MappingRow {
  id: string
  original_account_code: string
  original_account_name: string | null
  standard_account_code: string
  mapping_type: string
}

interface UnmappedRow {
  account_code: string
  account_name: string | null
  closing_balance: string | number | null
}

const DATALIST_ID = 'citar-map-standards'
const MAPPING_TYPE_LABELS: Record<string, string> = { auto_exact: '智能（精确）', auto_fuzzy: '智能（模糊）', manual: '手工' }
const SILENT = { _silent: true } as any

const { projectId, year, yearLoading } = useCitarProject()

const mappings = ref<MappingRow[]>([])
const unmapped = ref<UnmappedRow[]>([])
const rate = ref({ mapped_count: 0, total_count: 0, completion_rate: 0 })
const standards = ref<{ code: string; name: string }[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const keyword = ref('')
const editingId = ref('')
const editingCode = ref('')
/** 未映射科目各自录入的标准科目编码 */
const pending = reactive<Record<string, string>>({})

const standardNames = computed(() => new Map(standards.value.map(s => [s.code, s.name])))
const standardName = (code?: string) => (code ? standardNames.value.get(code) || '' : '')

const shown = computed(() => {
  const kw = keyword.value
  if (!kw) return mappings.value
  return mappings.value.filter(m =>
    [m.original_account_code, m.original_account_name, m.standard_account_code, standardName(m.standard_account_code)]
      .some(v => (v || '').includes(kw)),
  )
})

async function load() {
  if (!year.value) return
  loading.value = true
  error.value = ''
  try {
    const [list, r] = await Promise.all([
      api.get(P_map.list(projectId.value), SILENT),
      api.get(P_map.completionRate(projectId.value), { params: { year: year.value }, ...SILENT }),
    ])
    mappings.value = ((Array.isArray(list) ? list : []) as MappingRow[]).sort((a, b) =>
      a.original_account_code.localeCompare(b.original_account_code),
    )
    rate.value = {
      mapped_count: r?.mapped_count ?? 0,
      total_count: r?.total_count ?? 0,
      completion_rate: Number(r?.completion_rate) || 0,
    }
    unmapped.value = (r?.unmapped_with_balance || []) as UnmappedRow[]
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '读取映射失败'
  } finally {
    loading.value = false
  }
  if (!error.value) {
    await applyLocate(
      code => unmapped.value.some(u => normCode(u.account_code) === code)
        || mappings.value.some(m => normCode(m.original_account_code) === code),
      () => {
        tab.value = 'standard'
        keyword.value = ''
      },
      `底稿映射里没有客户科目 ${locateCode.value}（「有余额未映射」只列期末有余额的科目）`,
    )
  }
}

async function loadStandards() {
  try {
    const list: any = await api.get(P_chart.standard(projectId.value), SILENT)
    standards.value = (Array.isArray(list) ? list : [])
      .map((a: any) => ({ code: a.account_code, name: a.account_name }))
      .sort((a: { code: string }, b: { code: string }) => a.code.localeCompare(b.code))
  } catch {
    standards.value = []
  }
}

function checkStandard(code: string): boolean {
  if (standardNames.value.size && !standardNames.value.has(code)) {
    ElMessage.warning(`标准科目表里没有 ${code}，请从下拉选项里选`)
    return false
  }
  return true
}

/** action 可返回提示文案覆盖 done */
async function run(action: () => Promise<unknown>, context: string, done: string) {
  busy.value = true
  try {
    const message = await action()
    ElMessage.success(typeof message === 'string' ? message : done)
    refreshKey.value += 1
    await load()
  } catch (e) {
    handleApiError(e, context)
  } finally {
    busy.value = false
  }
}

function autoMatch() {
  void run(async () => {
    const res: any = await api.post(P_map.autoMatch(projectId.value), { year: year.value }, SILENT)
    const saved = res?.saved_count ?? 0
    return saved
      ? `智能匹配新增 ${saved} 条映射，试算表将按新映射重算；仍未匹配 ${res?.unmatched_count ?? 0} 个`
      : `没有可智能匹配的新科目（仍未匹配 ${res?.unmatched_count ?? 0} 个，请手工映射）`
  }, '智能匹配', '智能匹配完成')
}

function createMapping(u: UnmappedRow) {
  const code = pending[u.account_code]
  if (!code || !checkStandard(code)) return
  void run(
    () => api.post(P_map.create(projectId.value), {
      original_account_code: u.account_code,
      original_account_name: u.account_name,
      standard_account_code: code,
      mapping_type: 'manual',
      year: year.value,
    }, SILENT),
    '保存映射',
    `${u.account_code} 已映射到 ${code}`,
  )
}

function startEdit(m: MappingRow) {
  editingId.value = m.id
  editingCode.value = m.standard_account_code
}

function saveEdit(m: MappingRow) {
  const code = editingCode.value
  if (!code || !checkStandard(code)) return
  if (code === m.standard_account_code) {
    editingId.value = ''
    return
  }
  void run(async () => {
    await api.put(P_map.detail(projectId.value, m.id), { standard_account_code: code, year: year.value }, SILENT)
    editingId.value = ''
  }, '修改映射', `${m.original_account_code} 已改为映射到 ${code}`)
}

watch(
  [projectId, year],
  () => {
    editingId.value = ''
    void load()
    void loadStandards()
  },
  { immediate: true },
)
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-map__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--citar-c-fbf9fe);
  font-size: var(--citar-fs-13);
  color: var(--citar-c-5c5c68);
}

.citar-map__summary > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-right: auto;
}

.citar-map__rate {
  font-size: var(--citar-fs-20);
  font-weight: 700;
  color: var(--citar-c-6e0ba6);
}

.citar-map__warn {
  color: var(--citar-c-8a5300);
}

/* 页签上的「有余额未映射」数 */
.citar-map__badge {
  display: inline-block;
  min-width: 18px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 9px;
  background: var(--citar-c-fdf0dc);
  font-size: var(--citar-fs-12);
  font-weight: 400;
  line-height: 18px;
  color: var(--citar-c-8a5300);
}

.citar-map__heading {
  margin: 20px 0 10px;
  font-size: var(--citar-fs-14);
  color: var(--citar-c-4c1273);
}

.citar-map__table td {
  vertical-align: middle;
}

.citar-map__input {
  width: 140px;
}

.citar-map__name {
  margin-left: 8px;
  color: var(--citar-c-6b6b76);
}

.citar-map__ops {
  white-space: nowrap;
}

.citar-map__ops .citar-btn + .citar-btn {
  margin-left: 6px;
}
</style>
