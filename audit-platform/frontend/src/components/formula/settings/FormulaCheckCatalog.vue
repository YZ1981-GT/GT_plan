<!--
  全平台校对规则目录（spec formula-governance-coverage-closure R3，design §5）。
  左：来源清单（分类 / 规则数 / 能否编辑）；右：所选来源的规则 + 执行位置与去哪编辑。
  搜索框有内容时跨全部来源检索（后端 q），清空后回到所选来源。只读视图：规则在各自页面里改。
-->
<template>
  <div v-loading="loading" class="gt-fcc" :aria-busy="loading">
    <div class="gt-fcc-bar">
      <el-input v-model="keyword" size="small" clearable placeholder="跨来源搜索：编号 / 名称 / 公式 / 适用范围"
        style="width: 320px" data-testid="fcc-search" @keyup.enter="onSearch" @clear="onSearch" />
      <el-button size="small" data-testid="fcc-search-btn" @click="onSearch">搜索</el-button>
      <span class="gt-fcc-muted">共 {{ sources.length }} 个来源 · {{ total }} 条规则</span>
    </div>
    <div class="gt-fcc-muted" data-testid="fcc-context">
      {{ projectId ? '项目历史仅作来源摘要，不是下表每条规则的执行结论' : '未指定项目，未查询执行结果' }}
      · {{ year != null ? `所选年度：${year}` : '未指定年度；有年度能力的来源取最近记录年度' }}
    </div>
    <div v-if="loading" role="status" class="gt-fcc-muted" data-testid="fcc-loading">正在读取规则与项目历史…</div>
    <div class="gt-fcc-body">
      <ul class="gt-fcc-sources" role="listbox" aria-label="校对规则来源">
        <li v-for="s in sources" :key="s.key" role="option" tabindex="0" :aria-selected="!searching && current?.key === s.key"
          :class="{ 'is-active': !searching && current?.key === s.key }" :data-testid="`fcc-src-${s.key}`"
          @click="pick(s)" @keydown.enter="pick(s)">
          <div class="gt-fcc-src-top">
            <span>{{ s.label }}</span>
            <span class="gt-fcc-count">{{ searching ? (matched[s.key] ?? 0) : s.rule_count }}</span>
          </div>
          <div class="gt-fcc-src-status">
            <span class="gt-fcc-muted">{{ s.category }} · {{ s.error ? '加载失败' : s.editable ? '可编辑' : '只读' }}</span>
            <el-tag v-if="s.execution" size="small" :type="EXECUTION_TAG[s.execution]" effect="light"
              class="gt-fcc-status" :data-testid="`fcc-status-${s.key}`">{{ EXECUTION_LABEL[s.execution] }}</el-tag>
          </div>
        </li>
      </ul>
      <div class="gt-fcc-rules">
        <div v-if="searching" class="gt-fcc-head">
          <b>搜索「{{ lastKeyword }}」</b><span class="gt-fcc-muted">命中 {{ rules.length }} 条（每个来源最多显示 500 条）</span>
        </div>
        <div v-else-if="current" class="gt-fcc-head" data-testid="fcc-head">
          <b>{{ current.label }}</b>
          <span class="gt-fcc-muted">执行：{{ current.runs_in }}</span>
          <span v-if="current.execution" class="gt-fcc-muted" data-testid="fcc-exec-reason">
            状态：{{ EXECUTION_LABEL[current.execution] }}{{ current.execution_reason ? `（${current.execution_reason}）` : '' }}
          </span>
          <span class="gt-fcc-muted">{{ current.editable ? `编辑：${current.edit_where}` : '平台内不可编辑（随模板 / 规则文件）' }}</span>
          <span v-if="current.files.length" class="gt-fcc-muted">规则文件：{{ current.files.join('、') }}</span>
          <span v-else-if="current.from_db" class="gt-fcc-muted">来自全局公式设置</span>
        </div>
        <el-alert v-if="requestError" type="error" :title="requestError" :closable="false" show-icon
          data-testid="fcc-request-error" class="gt-fcc-gap" />
        <el-alert v-if="!searching && current?.error" type="error" :title="current.error" :closable="false" show-icon
          class="gt-fcc-gap" />
        <div v-if="evidenceSources.length" class="gt-fcc-evidence-list">
          <article v-for="s in evidenceSources" :key="s.key" class="gt-fcc-evidence" :data-testid="`fcc-evidence-${s.key}`">
            <b v-if="searching">{{ s.label }}（来源摘要）</b>
            <section :data-testid="`fcc-capability-${s.key}`">
              <b>规则能力</b>
              <el-tag size="small" type="info">{{ capabilityLabel(s) }}</el-tag>
              <span class="gt-fcc-muted">入口能力不代表项目已执行或通过</span>
              <div v-if="s.execution_reason" class="gt-fcc-muted">{{ s.execution_reason }}</div>
              <div v-if="s.executor" class="gt-fcc-muted">入口：{{ s.executor }}</div>
            </section>
            <section :data-testid="`fcc-history-${s.key}`">
              <b>项目历史结果</b><span>{{ historyLabel(s) }}</span>
              <div v-if="projectId && s.last_run?.at" class="gt-fcc-muted">
                摘要最新记录时间：{{ fmtDateTime(parseServerTime(s.last_run.at)) }}
              </div>
              <div v-if="projectId && s.last_run?.year != null" class="gt-fcc-muted">结果年度：{{ s.last_run.year }}</div>
              <div v-if="s.result_table" class="gt-fcc-muted">结果表：{{ s.result_table }}</div>
              <div v-if="projectId && s.last_run && Object.keys(s.last_run.counts).length" class="gt-fcc-counts">
                <span v-for="(count, key) in s.last_run.counts" :key="key">{{ countLabel(String(key)) }}：{{ count }}</span>
              </div>
              <div class="gt-fcc-muted">{{ !projectId ? '未指定项目，未查询执行结果' : s.last_run_note || '未提供历史范围说明，不能据此认定执行通过' }}</div>
              <div class="gt-fcc-muted">以上仅为来源历史摘要，不能作为下表每条规则的执行结论</div>
            </section>
          </article>
        </div>
        <el-table :data="rules" size="small" border max-height="calc(100vh - 380px)" :empty-text="emptyText"
          data-testid="fcc-rules">
          <el-table-column label="编号" prop="id" width="160" show-overflow-tooltip />
          <el-table-column label="名称" prop="label" min-width="200" show-overflow-tooltip />
          <el-table-column label="公式 / 条件" min-width="280" show-overflow-tooltip>
            <template #default="{ row }"><code class="gt-fcc-code">{{ row.expression || '—' }}</code></template>
          </el-table-column>
          <el-table-column label="级别" width="70">
            <template #default="{ row }">{{ row.severity_label || '—' }}</template>
          </el-table-column>
          <el-table-column label="适用范围" prop="scope" width="150" show-overflow-tooltip />
          <el-table-column v-if="searching" label="来源" prop="_source" width="150" show-overflow-tooltip />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formulaSettingsApi } from '@/services/formulaSettingsApi'
import {
  showFormulaError,
  type CheckCatalogQuery,
  type CheckExecutionStatus,
  type CheckRule,
  type CheckRuleSource,
} from '@/composables/formula/useFormulaSettings'
import { fmtDateTime, parseServerTime } from '@/utils/formatters'

defineOptions({ name: 'FormulaCheckCatalog' })

const props = withDefaults(defineProps<{
  /** 打开时先选中的来源（如表间审核面板跳过来选 cross_check_global） */
  initialSource?: string
  projectId?: string | null
  /** 仅 cross-check 支持年度过滤；QC / 门禁会明确标记非年度证据。 */
  year?: number | null
}>(), { initialSource: '' })

type Row = CheckRule & { _source?: string }

/** 入口能力标签，不代表项目已执行或逐条规则通过。 */
const EXECUTION_LABEL: Record<CheckExecutionStatus, string> = {
  wired: '已接入',
  display_only: '仅展示',
  not_executable: '不可执行',
}
const EXECUTION_TAG: Record<CheckExecutionStatus, 'success' | 'info' | 'warning'> = {
  wired: 'success',
  display_only: 'info',
  not_executable: 'warning',
}

const sources = ref<CheckRuleSource[]>([])
const total = ref(0)
const current = ref<CheckRuleSource | null>(null)
const rules = ref<Row[]>([])
const matched = ref<Record<string, number>>({})
const loading = ref(false)
const requestError = ref('')
const keyword = ref('')
const lastKeyword = ref('')
const searching = ref(false)
const selectedKey = ref(props.initialSource)
const searchSources = ref<CheckRuleSource[]>([])
const evidenceSources = computed(() => searching.value ? searchSources.value : current.value ? [current.value] : [])
let generation = 0
let alive = true

const emptyText = computed(() => {
  if (searching.value) return '没有匹配的规则'
  if (current.value?.from_db) return '全局层暂无规则（项目里配置的规则在公式管理中心查看）'
  return '暂无规则'
})

function capabilityLabel(source: CheckRuleSource): string {
  const labels = { wired: '入口可调用', display_only: '仅展示', not_executable: '无可用执行器' }
  return source.execution ? labels[source.execution] || '能力未提供' : '能力未提供'
}
const statusLabels: Record<string, string> = {
  passed: '历史摘要通过', pass: '历史摘要通过', failed: '历史摘要未通过', fail: '历史摘要未通过',
  error: '历史执行出错', unknown: '存在未识别状态，不能认定通过', not_executed: '含未执行项',
  skip: '含未执行项', not_applicable: '不适用', never_run: '未找到运行记录（所查范围内）',
  unavailable: '读取失败，未取得可用结论', allow: '门禁放行（非规则执行结论）',
  warn: '门禁警告（非规则执行结论）', block: '门禁阻断（非规则执行结论）',
}
const countLabels: Record<string, string> = {
  pass: '通过', passed: '通过', fail: '未通过', failed: '未通过', error: '错误', skip: '跳过',
  not_executed: '未执行', not_applicable: '不适用', working_papers: '底稿数', blocking: '阻断项', hit_rules: '命中规则数',
}
function countLabel(key: string): string { return countLabels[key] || `未识别状态（${key}）` }
function historyLabel(source: CheckRuleSource): string {
  if (!props.projectId) return '未指定项目，未查询执行结果'
  if (source.result_table === null) return '本类结果不落库，无法从目录判断是否执行'
  if (!source.last_run) return '未取得项目历史，不能据此认定通过'
  return statusLabels[source.last_run.status] || '未识别的历史状态，不能认定通过'
}

/** 清单、来源、搜索共用代际；旧成功 / 失败 / finally 与卸载后的响应均不再触碰界面。 */
async function load(intent: { source?: string; q?: string }, refreshSources = false): Promise<void> {
  const id = ++generation
  const active = () => alive && id === generation
  const context: CheckCatalogQuery = {}
  if (props.projectId) context.project_id = props.projectId
  if (props.year != null) context.year = props.year
  const kw = intent.q || ''
  loading.value = true
  requestError.value = ''
  current.value = null
  rules.value = []
  searchSources.value = []
  matched.value = {}
  searching.value = Boolean(kw)
  lastKeyword.value = kw
  if (refreshSources) {
    sources.value = []
    total.value = 0
  }
  try {
    if (refreshSources || !sources.value.length) {
      const data = await formulaSettingsApi.checkRules(context)
      if (!active()) return
      sources.value = data?.sources || []
      total.value = data?.total || 0
    }
    if (kw) {
      const found = (await formulaSettingsApi.checkRules({ ...context, q: kw }))?.sources || []
      if (!active()) return
      searchSources.value = found.filter((s) => (s.matched ?? 0) > 0 || Boolean(s.error))
      matched.value = Object.fromEntries(found.map((s) => [s.key, s.matched ?? 0]))
      rules.value = found.flatMap((s) => (s.rules || []).map((r) => ({ ...r, _source: s.label })))
    } else {
      const source = sources.value.find((s) => s.key === intent.source) || sources.value[0]
      if (!source) return
      selectedKey.value = source.key
      const data = await formulaSettingsApi.checkRules({ ...context, source: source.key })
      if (!active()) return
      const got = data?.sources?.find((s) => s.key === source.key)
      if (!got) throw new Error('目录未返回所选来源')
      current.value = got
      rules.value = got.rules || []
      sources.value = sources.value.map((s) => s.key === got.key ? got : s)
    }
  } catch (e) {
    if (active()) {
      requestError.value = '读取失败，未取得当前查询的规则与历史；不能据此认定通过'
      showFormulaError(e, kw ? '搜索校对规则失败' : '加载校对规则目录失败')
    }
  } finally {
    if (active()) loading.value = false
  }
}

function pick(source: CheckRuleSource): Promise<void> {
  selectedKey.value = source.key
  return load({ source: source.key })
}
function onSearch(): Promise<void> {
  const kw = keyword.value.trim()
  return load(kw ? { q: kw } : { source: selectedKey.value })
}

onBeforeUnmount(() => { alive = false; ++generation })
// 同步作废旧项目 / 年度展示，保留当前选择或已提交的搜索。
watch([() => props.projectId, () => props.year], () => {
  void load(searching.value ? { q: lastKeyword.value } : { source: selectedKey.value }, true)
}, { immediate: true, flush: 'sync' })
</script>

<style scoped>
.gt-fcc { display: flex; flex-direction: column; gap: 8px; }
.gt-fcc-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-fcc-body { display: flex; gap: 12px; align-items: flex-start; }
.gt-fcc-sources {
  list-style: none; margin: 0; padding: 0; width: 230px; flex-shrink: 0;
  border: 1px solid var(--gt-color-border-light, #e4e7ed); border-radius: 4px;
  max-height: calc(100vh - 330px); overflow-y: auto;
}
.gt-fcc-sources li { padding: 6px 10px; cursor: pointer; border-bottom: 1px solid var(--gt-color-border-lighter, #ebeef5); }
.gt-fcc-sources li:focus-visible { outline: 2px solid var(--gt-color-primary); outline-offset: -2px; }
.gt-fcc-sources li.is-active { background: var(--gt-color-primary-light-9, #ecf5ff); }
.gt-fcc-src-top { display: flex; justify-content: space-between; gap: 8px; font-size: var(--gt-font-size-sm); }
.gt-fcc-src-status { display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-top: 2px; }
.gt-fcc-status { flex-shrink: 0; }
.gt-fcc-count { color: var(--gt-color-text-secondary); font-variant-numeric: tabular-nums; }
.gt-fcc-rules { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.gt-fcc-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; }
.gt-fcc-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fcc-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fcc-gap { margin-bottom: 4px; }
.gt-fcc-evidence-list { display: grid; gap: 8px; max-height: 270px; overflow-y: auto; }
.gt-fcc-evidence { border: 1px solid var(--gt-color-border-light, #e4e7ed); border-radius: 4px; padding: 8px; }
.gt-fcc-evidence section + section { border-top: 1px solid var(--gt-color-border-lighter, #ebeef5); margin-top: 6px; padding-top: 6px; }
.gt-fcc-evidence section > b { margin-right: 8px; }
.gt-fcc-evidence section > span { margin-right: 8px; }
.gt-fcc-counts { display: flex; flex-wrap: wrap; gap: 12px; font-size: var(--gt-font-size-xs); }
</style>
