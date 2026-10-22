<!--
  全平台校对规则目录（spec formula-governance-coverage-closure R3，design §5）。
  左：来源清单（分类 / 规则数 / 能否编辑）；右：所选来源的规则 + 执行位置与去哪编辑。
  搜索框有内容时跨全部来源检索（后端 q），清空后回到所选来源。只读视图：规则在各自页面里改。
-->
<template>
  <div v-loading="loading" class="gt-fcc">
    <div class="gt-fcc-bar">
      <el-input v-model="keyword" size="small" clearable placeholder="跨来源搜索：编号 / 名称 / 公式 / 适用范围"
        style="width: 320px" data-testid="fcc-search" @keyup.enter="onSearch" @clear="onSearch" />
      <el-button size="small" data-testid="fcc-search-btn" @click="onSearch">搜索</el-button>
      <span class="gt-fcc-muted">共 {{ sources.length }} 个来源 · {{ total }} 条规则</span>
    </div>
    <div class="gt-fcc-body">
      <ul class="gt-fcc-sources" role="listbox" aria-label="校对规则来源">
        <li v-for="s in sources" :key="s.key" role="option" tabindex="0" :aria-selected="!searching && current?.key === s.key"
          :class="{ 'is-active': !searching && current?.key === s.key }" :data-testid="`fcc-src-${s.key}`"
          @click="pick(s)" @keydown.enter="pick(s)">
          <div class="gt-fcc-src-top">
            <span>{{ s.label }}</span>
            <span class="gt-fcc-count">{{ searching ? (matched[s.key] ?? 0) : s.rule_count }}</span>
          </div>
          <div class="gt-fcc-muted">{{ s.category }} · {{ s.error ? '加载失败' : s.editable ? '可编辑' : '只读' }}</div>
        </li>
      </ul>
      <div class="gt-fcc-rules">
        <div v-if="searching" class="gt-fcc-head">
          <b>搜索「{{ lastKeyword }}」</b><span class="gt-fcc-muted">命中 {{ rules.length }} 条（每个来源最多显示 500 条）</span>
        </div>
        <div v-else-if="current" class="gt-fcc-head" data-testid="fcc-head">
          <b>{{ current.label }}</b>
          <span class="gt-fcc-muted">执行：{{ current.runs_in }}</span>
          <span class="gt-fcc-muted">{{ current.editable ? `编辑：${current.edit_where}` : '平台内不可编辑（随模板 / 规则文件）' }}</span>
          <span v-if="current.files.length" class="gt-fcc-muted">规则文件：{{ current.files.join('、') }}</span>
          <span v-else-if="current.from_db" class="gt-fcc-muted">来自全局公式设置</span>
        </div>
        <el-alert v-if="!searching && current?.error" type="error" :title="current.error" :closable="false" show-icon
          class="gt-fcc-gap" />
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
import { computed, onMounted, ref } from 'vue'
import { formulaSettingsApi } from '@/services/formulaSettingsApi'
import { showFormulaError, type CheckRule, type CheckRuleSource } from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaCheckCatalog' })

const props = withDefaults(defineProps<{
  /** 打开时先选中的来源（如表间审核面板跳过来选 cross_check_global） */
  initialSource?: string
}>(), { initialSource: '' })

type Row = CheckRule & { _source?: string }

const sources = ref<CheckRuleSource[]>([])
const total = ref(0)
const current = ref<CheckRuleSource | null>(null)
const rules = ref<Row[]>([])
const matched = ref<Record<string, number>>({})
const loading = ref(false)
const keyword = ref('')
const lastKeyword = ref('')
const searching = ref(false)

const emptyText = computed(() => {
  if (searching.value) return '没有匹配的规则'
  if (current.value?.from_db) return '全局层暂无规则（项目里配置的规则在公式管理中心查看）'
  return '暂无规则'
})

async function pick(source: CheckRuleSource): Promise<void> {
  current.value = source
  searching.value = false
  loading.value = true
  try {
    const got = (await formulaSettingsApi.checkRules({ source: source.key }))?.sources?.[0]
    rules.value = got?.rules || []
    if (got) current.value = { ...source, ...got }
  } catch (e) {
    rules.value = []
    showFormulaError(e, '加载校对规则失败')
  } finally {
    loading.value = false
  }
}

async function onSearch(): Promise<void> {
  const kw = keyword.value.trim()
  if (!kw) {
    if (searching.value && current.value) await pick(current.value)
    return
  }
  loading.value = true
  try {
    const found = (await formulaSettingsApi.checkRules({ q: kw }))?.sources || []
    matched.value = Object.fromEntries(found.map((s) => [s.key, s.matched ?? 0]))
    rules.value = found.flatMap((s) => (s.rules || []).map((r) => ({ ...r, _source: s.label })))
    lastKeyword.value = kw
    searching.value = true
  } catch (e) {
    showFormulaError(e, '搜索校对规则失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await formulaSettingsApi.checkRules()
    sources.value = data?.sources || []
    total.value = data?.total || 0
  } catch (e) {
    showFormulaError(e, '加载校对规则目录失败')
  } finally {
    loading.value = false
  }
  const first = sources.value.find((s) => s.key === props.initialSource) || sources.value[0]
  if (first) await pick(first)
})
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
.gt-fcc-count { color: var(--gt-color-text-secondary); font-variant-numeric: tabular-nums; }
.gt-fcc-rules { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.gt-fcc-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; }
.gt-fcc-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fcc-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fcc-gap { margin-bottom: 4px; }
</style>
