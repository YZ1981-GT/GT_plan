<!--
  NoteTemplateTab.vue — 附注模板 Tab [template-library-coordination Sprint 4.2]

  需求 10.1-10.5：
  - 双栏展示：左栏标准选择（SOE/Listed），右栏章节树
  - 章节按 sort_order 排序
  - 每个章节显示 section_title / has_formula(派生) / linked_report_rows(派生)
  - 顶部统计：章节总数、有公式驱动的章节数

  数据源：GET /api/note-templates/{template_type}（template_type = soe | listed）
  D8 ADR：数字列 .gt-amt class
  has_formula 派生：tables[].rows[] 含 formula 字段 OR check_presets/wide_table_presets 不为空
  linked_report_rows 派生：从 account_name 推断（SOE/Listed 模板 JSON 内未直接存此字段，本组件展示 0/N 提示）
-->
<template>
  <div class="gt-ntt">
    <!-- 顶部统计 -->
    <div class="gt-ntt-stats">
      <span class="gt-ntt-stats-item">
        当前标准：<strong>{{ currentStandardLabel }}</strong>
      </span>
      <span class="gt-ntt-stats-item">
        章节总数：<span class="gt-amt">{{ sectionCount }}</span>
      </span>
      <span class="gt-ntt-stats-item">
        有公式驱动：<span class="gt-amt gt-ntt-stats-formula">{{ formulaSectionCount }}</span>
      </span>
      <span class="gt-ntt-stats-item">
        含表格：<span class="gt-amt">{{ tableSectionCount }}</span>
      </span>
    </div>

    <!-- 双栏布局 -->
    <div class="gt-ntt-body">
      <!-- 左栏：标准选择 -->
      <div class="gt-ntt-left">
        <div class="gt-ntt-left-title">报表标准</div>
        <el-radio-group v-model="standard" class="gt-ntt-radio-group">
          <el-radio value="soe" class="gt-ntt-radio">
            <div class="gt-ntt-radio-content">
              <strong>SOE</strong>
              <span class="gt-ntt-radio-sub">国企版（CAS）</span>
              <span v-if="standardCounts.soe !== null" class="gt-amt gt-ntt-radio-count">
                {{ standardCounts.soe }} 节
              </span>
            </div>
          </el-radio>
          <el-radio value="listed" class="gt-ntt-radio">
            <div class="gt-ntt-radio-content">
              <strong>Listed</strong>
              <span class="gt-ntt-radio-sub">上市公司版</span>
              <span v-if="standardCounts.listed !== null" class="gt-amt gt-ntt-radio-count">
                {{ standardCounts.listed }} 节
              </span>
            </div>
          </el-radio>
        </el-radio-group>

        <div class="gt-ntt-left-search">
          <el-input
            v-model="searchInput"
            size="small"
            placeholder="搜索章节"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <div class="gt-ntt-left-filters">
          <el-checkbox v-model="onlyWithFormula" size="small">仅显示有公式</el-checkbox>
          <el-checkbox v-model="onlyWithTable" size="small">仅显示含表格</el-checkbox>
        </div>
      </div>

      <!-- 右栏：章节树 -->
      <div class="gt-ntt-right" v-loading="loading">
        <el-empty
          v-if="!loading && filteredSections.length === 0"
          :description="filterSectionEmptyText"
        />
        <el-tree
          v-else
          ref="treeRef"
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          :default-expanded-keys="defaultExpandedKeys"
          :expand-on-click-node="true"
          class="gt-ntt-tree"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="gt-ntt-node" :class="{ 'gt-ntt-node--group': data.isGroup }">
              <template v-if="data.isGroup">
                <el-icon><Folder /></el-icon>
                <span class="gt-ntt-group-label">{{ data.label }}</span>
                <span class="gt-amt gt-ntt-group-count">({{ data.children?.length || 0 }})</span>
              </template>
              <template v-else>
                <span class="gt-amt gt-ntt-section-no">{{ data.section_number }}</span>
                <span class="gt-ntt-section-title">{{ data.section_title }}</span>
                <el-tag v-if="data.has_formula" size="small" type="primary" effect="plain" round>
                  ✦ 公式
                </el-tag>
                <el-tag v-if="data.has_table" size="small" type="info" effect="plain" round>
                  📊 表格
                </el-tag>
                <el-tag
                  v-if="data.content_type"
                  size="small"
                  effect="plain"
                  round
                  :class="`gt-ntt-ct--${data.content_type}`"
                >
                  {{ data.content_type }}
                </el-tag>
              </template>
            </span>
          </template>
        </el-tree>
      </div>
    </div>

    <!-- 章节详情弹层 -->
    <el-drawer
      v-model="detailVisible"
      :title="detailTitle"
      direction="rtl"
      size="40%"
    >
      <div v-if="selectedSection" class="gt-ntt-detail">
        <div class="gt-ntt-detail-meta">
          <span class="gt-ntt-detail-meta-item">
            编号：<span class="gt-amt">{{ selectedSection.section_number }}</span>
          </span>
          <span class="gt-ntt-detail-meta-item">
            排序：<span class="gt-amt">{{ selectedSection.sort_order }}</span>
          </span>
          <span class="gt-ntt-detail-meta-item">
            范围：<el-tag size="small" effect="plain">{{ selectedSection.scope || 'both' }}</el-tag>
          </span>
          <span class="gt-ntt-detail-meta-item">
            类型：<el-tag size="small" effect="plain">{{ selectedSection.content_type || 'text' }}</el-tag>
          </span>
        </div>

        <!-- check_presets / wide_table_presets -->
        <div v-if="hasFormulaPresets(selectedSection)" class="gt-ntt-detail-formula">
          <h4 class="gt-ntt-h4">校验公式预设</h4>
          <div class="gt-ntt-tags">
            <el-tag
              v-for="p in (selectedSection.check_presets || [])"
              :key="`cp-${p}`"
              size="small"
              type="primary"
              effect="plain"
            >{{ p }}</el-tag>
            <el-tag
              v-for="p in (selectedSection.wide_table_presets || [])"
              :key="`wp-${p}`"
              size="small"
              type="success"
              effect="plain"
            >宽表:{{ p }}</el-tag>
          </div>
        </div>

        <!-- 表格列表 -->
        <div v-if="(selectedSection.tables || []).length > 0" class="gt-ntt-detail-tables">
          <h4 class="gt-ntt-h4">附注表格（{{ (selectedSection.tables || []).length }}）</h4>
          <div
            v-for="(tbl, ti) in (selectedSection.tables || [])"
            :key="`tbl-${ti}`"
            class="gt-ntt-tbl-card"
          >
            <div class="gt-ntt-tbl-name">{{ tbl.name || `表格 ${ti + 1}` }}</div>
            <el-table
              :data="(tbl.rows || []).map((r: any, idx: number) => ({ ...r, _idx: idx + 1 }))"
              size="small"
              :header-cell-style="{ background: '#f0edf5', color: '#303133' }"
            >
              <el-table-column type="index" label="#" width="50" />
              <el-table-column prop="label" label="项目" min-width="200" show-overflow-tooltip />
              <el-table-column label="期初" min-width="120">
                <template #default="{ row }">
                  <span class="gt-amt">{{ formatCellValue(row.values?.[0]) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="增加" min-width="120">
                <template #default="{ row }">
                  <span class="gt-amt">{{ formatCellValue(row.values?.[1]) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="减少" min-width="120">
                <template #default="{ row }">
                  <span class="gt-amt">{{ formatCellValue(row.values?.[2]) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="期末" min-width="120">
                <template #default="{ row }">
                  <span class="gt-amt">{{ formatCellValue(row.values?.[3]) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="标记" width="80">
                <template #default="{ row }">
                  <el-tag v-if="row.is_total" type="warning" size="small">合计</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- text_sections -->
        <div v-if="(selectedSection.text_sections || []).length > 0" class="gt-ntt-detail-text">
          <h4 class="gt-ntt-h4">文字段落（{{ (selectedSection.text_sections || []).length }}）</h4>
          <div
            v-for="(t, idx) in (selectedSection.text_sections || [])"
            :key="`txt-${idx}`"
            class="gt-ntt-text-block"
          >
            {{ t }}
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Folder } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { noteTemplates as P_nt } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

// ─── 类型 ─────────────────────────────────────────────────────────────────
interface NoteTable {
  name?: string
  headers?: string[]
  rows?: Array<{ label?: string; values?: any[]; is_total?: boolean }>
}

interface NoteSection {
  section_number?: string
  section_title?: string
  account_name?: string
  content_type?: string
  scope?: string
  sort_order?: number
  text_sections?: string[]
  tables?: NoteTable[]
  check_presets?: string[]
  wide_table_presets?: string[]
}

interface TreeNode {
  id: string
  label: string
  isGroup?: boolean
  // 章节字段（仅 leaf）
  section_number?: string
  section_title?: string
  content_type?: string
  has_formula?: boolean
  has_table?: boolean
  raw?: NoteSection
  children?: TreeNode[]
}

// ─── State ────────────────────────────────────────────────────────────────
const standard = ref<'soe' | 'listed'>('soe')
const loading = ref(false)
const sections = ref<NoteSection[]>([])
const standardCounts = ref<{ soe: number | null; listed: number | null }>({
  soe: null,
  listed: null,
})

const searchInput = ref('')
const searchText = ref('')
let searchDebouncer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (v) => {
  if (searchDebouncer) clearTimeout(searchDebouncer)
  searchDebouncer = setTimeout(() => { searchText.value = (v || '').trim() }, 250)
})

const onlyWithFormula = ref(false)
const onlyWithTable = ref(false)

const detailVisible = ref(false)
const selectedSection = ref<NoteSection | null>(null)
const treeRef = ref<any>(null)

// ─── 加载附注模板 ─────────────────────────────────────────────────────────
async function loadTemplate(std: 'soe' | 'listed') {
  loading.value = true
  try {
    const data = await api.get(P_nt.list(std))
    sections.value = (data?.sections || []) as NoteSection[]
    standardCounts.value[std] = sections.value.length
  } catch (e: any) {
    handleApiError(e, `加载${std === 'soe' ? 'SOE' : 'Listed'}附注模板`)
    sections.value = []
    standardCounts.value[std] = 0
  } finally {
    loading.value = false
  }
}

watch(standard, (val) => {
  loadTemplate(val)
})

onMounted(async () => {
  // 并行加载两个标准的章节数（以填充左栏 radio 计数），然后切到当前选中的
  await loadTemplate(standard.value)
  // 后台加载另一个标准的计数（不阻塞 UI）
  const other: 'soe' | 'listed' = standard.value === 'soe' ? 'listed' : 'soe'
  try {
    const data = await api.get(P_nt.list(other))
    standardCounts.value[other] = (data?.sections || []).length
  } catch {
    standardCounts.value[other] = 0
  }
})

// ─── 计算属性 ─────────────────────────────────────────────────────────────
const currentStandardLabel = computed(() =>
  standard.value === 'soe' ? '国企版（SOE / CAS）' : '上市公司版（Listed）',
)

function deriveHasFormula(s: NoteSection): boolean {
  if ((s.check_presets || []).length > 0) return true
  if ((s.wide_table_presets || []).length > 0) return true
  // 还检查 tables[].rows[] 是否含字面 "公式" 字段
  return (s.tables || []).some(t =>
    (t.rows || []).some(r => 'formula' in (r as any) || 'check' in (r as any)),
  )
}

function deriveHasTable(s: NoteSection): boolean {
  return (s.tables || []).length > 0
}

const sectionCount = computed(() => sections.value.length)

const formulaSectionCount = computed(() =>
  sections.value.filter(deriveHasFormula).length,
)

const tableSectionCount = computed(() =>
  sections.value.filter(deriveHasTable).length,
)

const filteredSections = computed<NoteSection[]>(() => {
  const q = searchText.value.toLowerCase()
  return sections.value.filter(s => {
    if (onlyWithFormula.value && !deriveHasFormula(s)) return false
    if (onlyWithTable.value && !deriveHasTable(s)) return false
    if (q) {
      const num = (s.section_number || '').toLowerCase()
      const title = (s.section_title || '').toLowerCase()
      if (!num.includes(q) && !title.includes(q)) return false
    }
    return true
  })
})

const filterSectionEmptyText = computed(() => {
  if (searchText.value || onlyWithFormula.value || onlyWithTable.value) return '未匹配到任何章节'
  return '暂无附注章节数据'
})

/**
 * 章节按 sort_order 排序后，按"section_number 顶级前缀（如"一/二/三"或"附录"）"分组成树。
 * 由于真实 JSON 的 section_number 含中文数字（如"一、""二、"），用前 1 字符做分组键近似。
 */
const treeData = computed<TreeNode[]>(() => {
  const sorted = [...filteredSections.value].sort(
    (a, b) => (a.sort_order ?? 999999) - (b.sort_order ?? 999999),
  )

  const groups = new Map<string, TreeNode[]>()
  const groupOrder: string[] = []
  for (const s of sorted) {
    const num = s.section_number || '其他'
    // 取顶级分组：(一)、(二) 等用 "一" / "二"；纯数字则用第一个数字
    const m = num.match(/^[（(]?([一二三四五六七八九十百零〇0-9]+)/)
    const groupKey = m ? m[1] : num.slice(0, 1) || '其他'
    if (!groups.has(groupKey)) {
      groups.set(groupKey, [])
      groupOrder.push(groupKey)
    }
    const node: TreeNode = {
      id: `s-${num}-${s.sort_order}`,
      label: s.section_title || num,
      section_number: num,
      section_title: s.section_title,
      content_type: s.content_type,
      has_formula: deriveHasFormula(s),
      has_table: deriveHasTable(s),
      raw: s,
    }
    groups.get(groupKey)!.push(node)
  }

  return groupOrder.map(gk => ({
    id: `g-${gk}`,
    label: `第 ${gk} 部分`,
    isGroup: true,
    children: groups.get(gk) || [],
  }))
})

const defaultExpandedKeys = computed<string[]>(() => {
  // 默认展开第一组以便用户立即看到数据
  return treeData.value.length > 0 ? [treeData.value[0].id] : []
})

const detailTitle = computed(() => {
  if (!selectedSection.value) return ''
  return `${selectedSection.value.section_number || ''} ${selectedSection.value.section_title || ''}`
})

// ─── 交互 ─────────────────────────────────────────────────────────────────
function onNodeClick(node: TreeNode) {
  if (node.isGroup) return
  if (!node.raw) return
  selectedSection.value = node.raw
  detailVisible.value = true
}

function hasFormulaPresets(s: NoteSection): boolean {
  return (s.check_presets || []).length > 0 || (s.wide_table_presets || []).length > 0
}

function formatCellValue(v: any): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number') return v.toLocaleString('zh-CN')
  return String(v)
}
</script>

<style scoped>
.gt-ntt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* ─── 顶部统计 ─── */
.gt-ntt-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  border-left: 3px solid var(--gt-color-primary);
  flex-shrink: 0;
}
.gt-ntt-stats-item {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-ntt-stats-formula {
  color: var(--gt-color-teal);
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

/* ─── 双栏布局 ─── */
.gt-ntt-body {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

/* 左栏 200px */
.gt-ntt-left {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 8px;
  padding: 12px;
}
.gt-ntt-left-title {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  font-weight: 600;
  margin-bottom: 4px;
}
.gt-ntt-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-ntt-radio {
  margin-right: 0 !important;
  padding: 8px 12px;
  background: var(--gt-color-bg);
  border-radius: 6px;
  width: 100%;
  height: auto !important;
  align-items: flex-start !important;
}
.gt-ntt-radio :deep(.el-radio__label) {
  width: 100%;
  padding-left: 8px;
}
.gt-ntt-radio-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--gt-font-size-sm);
  line-height: 1.4;
}
.gt-ntt-radio-sub {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.gt-ntt-radio-count {
  margin-top: 4px;
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-xs);
}

.gt-ntt-left-search { margin-top: 8px; }
.gt-ntt-left-filters {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 4px;
  border-top: 1px dashed var(--gt-color-border-lighter);
}

/* 右栏树 */
.gt-ntt-right {
  flex: 1;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 8px;
  padding: 8px 4px;
  overflow: auto;
  min-height: 0;
}
.gt-ntt-tree {
  background: transparent;
}
.gt-ntt-tree :deep(.el-tree-node__content) {
  height: 32px;
}
.gt-ntt-tree :deep(.el-tree-node__content:hover) {
  background-color: var(--gt-color-primary-bg);
}

.gt-ntt-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  flex: 1;
  min-width: 0;
}
.gt-ntt-node--group {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-ntt-group-label {
  white-space: nowrap;
}
.gt-ntt-group-count {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-xs);
}

.gt-ntt-section-no {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-xs);
  flex-shrink: 0;
}
.gt-ntt-section-title {
  color: var(--gt-color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}
.gt-ntt-ct--text { background: var(--gt-color-bg); color: var(--gt-color-text-regular); }
.gt-ntt-ct--mixed { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.gt-ntt-ct--table { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); }

/* ─── 详情抽屉 ─── */
.gt-ntt-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 4px;
}
.gt-ntt-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-ntt-detail-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-ntt-h4 {
  margin: 0 0 8px 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary);
  font-weight: 600;
  border-left: 3px solid var(--gt-color-primary);
  padding-left: 8px;
}

.gt-ntt-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.gt-ntt-tbl-card {
  background: var(--gt-color-bg);
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 12px;
}
.gt-ntt-tbl-name {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--gt-color-text-primary);
}

.gt-ntt-text-block {
  background: var(--gt-color-bg);
  padding: 10px 12px;
  border-radius: 4px;
  border-left: 3px solid var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
  line-height: 1.6;
  color: var(--gt-color-text-primary);
  white-space: pre-wrap;
  margin-bottom: 8px;
}
</style>
