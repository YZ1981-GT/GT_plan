<!--
  公式看板弹窗（从 FormulaManagerDialog 拆出；优化建议 #1 面板拆分）。
  展示全平台公式总览：报表预设 + 附注预设 + 项目级公式 + 试算表覆盖，
  支持按域/层级/报表类型/分类/数据源分组筛选。
-->
<template>
  <el-dialog
    v-model="visible"
    title="📊 公式看板 — 全局审核公式总览"
    width="95%"
    top="2vh"
    append-to-body
    destroy-on-close
    class="gt-fm-dashboard-dialog"
  >
    <PushCoverageCard :show="visible" :project-id="projectId" :year="year" />
    <div style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
      <el-input v-model="search" size="small" placeholder="搜索公式/行次/说明/域..." clearable style="width: 220px;" />
      <el-select v-model="groupBy" size="small" style="width: 130px;">
        <el-option label="按域" value="domain" />
        <el-option label="按层级" value="level" />
        <el-option label="按报表类型" value="report_type" />
        <el-option label="按公式分类" value="category" />
        <el-option label="按数据源" value="source" />
        <el-option label="全部平铺" value="flat" />
      </el-select>
      <el-select v-model="filterDomain" size="small" style="width: 140px;" clearable placeholder="筛选域">
        <el-option v-for="d in domainOptions" :key="d.value" :label="`${d.label}（${d.count}）`" :value="d.value" />
      </el-select>
      <el-select v-model="filterLevel" size="small" style="width: 120px;" clearable placeholder="筛选层级">
        <el-option label="模板预设" value="模板预设" />
        <el-option label="项目级" value="项目级" />
      </el-select>
      <el-select v-model="filterCategory" size="small" style="width: 130px;" clearable placeholder="筛选分类">
        <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-select v-model="filterCategorized" size="small" style="width: 140px;" clearable placeholder="分类健康度">
        <el-option :label="`已分类（${categorizedCount.yes}）`" value="yes" />
        <el-option :label="`未分类（${categorizedCount.no}）`" value="no" />
      </el-select>
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: auto;">
        共 {{ filteredRows.length }} / {{ rows.length }} 条公式
        <template v-if="categorizedCount.no">
          · 未分类 {{ categorizedCount.no }} 条
        </template>
      </span>
    </div>

    <el-alert
      v-if="!loading && !rows.length"
      type="warning"
      :closable="false"
      show-icon
      title="未取到任何公式"
      :description="coverageText"
      style="margin-bottom: 10px;"
    />
    <div v-else-if="!loading" style="margin-bottom: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
      覆盖：{{ coverageText }}
    </div>

    <!-- 分组展示 -->
    <div v-if="groupBy !== 'flat'" style="max-height: 80vh; overflow-y: auto;">
      <div v-for="group in groupedData" :key="group.key" style="margin-bottom: 12px;">
        <div class="gt-fm-dash-group-title" @click="group._open = !group._open">
          {{ group._open ? '▼' : '▶' }} {{ group.label }}
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 6px;">{{ group.rows.length }} 条</span>
        </div>
        <el-table v-show="group._open" :data="group.rows" size="small" border style="width: 100%;"
          :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
          <el-table-column prop="row_code" label="行次" width="90" />
          <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
          <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular);">{{ row.formula }}</code>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="categoryTagType(row.formula_category) || undefined" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
          <el-table-column label="当前值" width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.current_period_amount != null" style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-primary-dark); font-variant-numeric: tabular-nums;">
                {{ fmt(row.current_period_amount) }}
              </span>
              <span v-else style="color: var(--gt-color-text-placeholder);">-</span>
            </template>
          </el-table-column>
          <el-table-column label="域" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row._domainLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="90" align="center">
            <template #default="{ row }">
              <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ row._source_type || '报表' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="86" align="center">
            <template #default="{ row }">
              <el-button v-if="row._editable" size="small" link type="primary" @click="$emit('edit', row)">编辑</el-button>
              <el-button v-else size="small" link type="primary" @click="$emit('locate', row)">定位</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 平铺展示 -->
    <el-table v-else :data="filteredRows" size="small" border max-height="80vh" style="width: 100%;"
      :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
      <el-table-column prop="row_code" label="行次" width="90" />
      <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
      <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular);">{{ row.formula }}</code>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="categoryTagType(row.formula_category) || undefined" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
      <el-table-column label="域" width="120" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row._domainLabel }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="_level" label="层级" width="86" align="center" />
      <el-table-column prop="_report_type_label" label="报表" width="100" />
      <el-table-column label="操作" width="86" align="center">
        <template #default="{ row }">
          <el-button v-if="row._editable" size="small" link type="primary" @click="$emit('edit', row)">编辑</el-button>
          <el-button v-else size="small" link type="primary" @click="$emit('locate', row)">定位</el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import PushCoverageCard from './panels/PushCoverageCard.vue'

defineOptions({ name: 'FormulaDashboardDialog' })

const visible = defineModel<boolean>({ default: false })

const props = defineProps<{
  /** 全部看板行（报表预设 + 附注预设 + 项目级公式 + 试算表覆盖） */
  rows: any[]
  /** 加载状态 */
  loading: boolean
  /** 覆盖情况文案 */
  coverageText: string
  /** 公式分类标签函数 */
  categoryLabel: (cat: string) => string
  /** 公式分类 tag 类型函数 */
  categoryTagType: (cat: string) => string
  /** 格式化数值函数 */
  fmt: (v: number) => string
  /** 项目 ID（有值时 PushCoverageCard 展示推送概要和状态分布） */
  projectId?: string
  /** 审计年度 */
  year?: number
}>()

defineEmits<{
  (e: 'edit', row: any): void
  (e: 'locate', row: any): void
}>()

const search = ref('')
const groupBy = ref('domain')
const filterCategory = ref('')
const filterDomain = ref('')
const filterLevel = ref('')
const filterCategorized = ref('')

const domainOptions = computed(() => {
  const counter = new Map<string, { value: string; label: string; count: number }>()
  for (const r of props.rows) {
    const value = String(r._domain || '')
    if (!value) continue
    const hit = counter.get(value)
    if (hit) hit.count += 1
    else counter.set(value, { value, label: String(r._domainLabel || value), count: 1 })
  }
  return [...counter.values()]
})

const categorizedCount = computed(() => {
  let yes = 0; let no = 0
  for (const r of props.rows) {
    if (r.formula_category) yes += 1; else no += 1
  }
  return { yes, no }
})

const categoryOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const r of props.rows) {
    const key = r.formula_category || ''
    if (!key || seen.has(key)) continue
    seen.set(key, props.categoryLabel(key))
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label }))
})

const filteredRows = computed(() => {
  let rows = props.rows
  if (filterCategory.value) rows = rows.filter(r => r.formula_category === filterCategory.value)
  if (filterDomain.value) rows = rows.filter(r => r._domain === filterDomain.value)
  if (filterLevel.value) rows = rows.filter(r => r._level === filterLevel.value)
  if (filterCategorized.value === 'yes') rows = rows.filter(r => !!r.formula_category)
  else if (filterCategorized.value === 'no') rows = rows.filter(r => !r.formula_category)
  const kw = search.value.toLowerCase()
  if (kw) {
    rows = rows.filter(r =>
      (r.row_code || '').toLowerCase().includes(kw)
      || (r.row_name || '').toLowerCase().includes(kw)
      || (r.formula || '').toLowerCase().includes(kw)
      || (r.formula_description || '').toLowerCase().includes(kw)
      || (r._domainLabel || '').toLowerCase().includes(kw)
      || (r._source_type || '').toLowerCase().includes(kw),
    )
  }
  return rows
})

const groupedData = computed(() => {
  const rows = filteredRows.value
  const groups: Record<string, { key: string; label: string; rows: any[]; _open: boolean }> = {}
  const sourceLabels: Record<string, string> = { tb: '📈 试算表', note: '📝 附注', wp: '📋 底稿', row: '📊 报表行次', other: '其他' }
  for (const r of rows) {
    let gKey = ''; let gLabel = ''
    if (groupBy.value === 'domain') { gKey = r._domain || 'unknown'; gLabel = `${r._domainLabel || gKey}（${r._level || ''}）` }
    else if (groupBy.value === 'level') { gKey = r._level || 'unknown'; gLabel = r._level || gKey }
    else if (groupBy.value === 'report_type') { gKey = r._report_type || 'unknown'; gLabel = r._report_type_label || gKey }
    else if (groupBy.value === 'category') { gKey = r.formula_category || 'none'; gLabel = props.categoryLabel(r.formula_category) }
    else if (groupBy.value === 'source') {
      const formula = r.formula || ''
      if (formula.includes('TB(') || formula.includes('SUM_TB(')) gKey = 'tb'
      else if (formula.includes('NOTE(')) gKey = 'note'
      else if (formula.includes('WP(')) gKey = 'wp'
      else if (formula.includes('ROW(') || formula.includes('SUM_ROW(')) gKey = 'row'
      else gKey = 'other'
      gLabel = sourceLabels[gKey] || gKey
    }
    if (!groups[gKey]) groups[gKey] = { key: gKey, label: gLabel, rows: [], _open: true }
    groups[gKey].rows.push(r)
  }
  return Object.values(groups)
})
</script>
