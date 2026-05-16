<!--
  WpTemplateTab.vue — 底稿模板库 Tab [template-library-coordination Sprint 2.8]

  需求 2.1-2.7, 5.1-5.5：
  - 树形结构展示全部主编码模板（数量从 /list 端点动态取），按循环分组
  - 使用 GT_Coding 的 cycle_name 作为分组名称
  - 每个模板节点显示格式图标（xlsx/docx/xlsm）+ 可选 (N sheets) 标识
  - 搜索框模糊匹配 wp_code/wp_name + 高亮（XSS 安全）
  - 按 component_type/循环 筛选
  - 未生成节点 (.gt-tree-ungenerated) 灰色文字
  - has_formula 节点显示蓝色 ✦ 小图标

  数据源：GET /api/projects/{pid}/wp-templates/list
  D8 ADR：数字列 .gt-amt class
  D11 ADR：树节点维度按主编码（一 wp_code 一节点）
-->
<template>
  <div class="gt-wptt">
    <!-- 顶部紧凑工具栏 -->
    <div class="gt-wptt-toolbar">
      <el-input
        v-model="searchInput"
        size="small"
        placeholder="搜索 wp_code 或 wp_name"
        clearable
        class="gt-wptt-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="filterComponentType"
        size="small"
        placeholder="组件类型"
        clearable
        class="gt-wptt-select"
      >
        <el-option label="全部" value="" />
        <el-option label="univer" value="univer" />
        <el-option label="form" value="form" />
        <el-option label="word" value="word" />
        <el-option label="hybrid" value="hybrid" />
      </el-select>

      <el-select
        v-model="filterCycle"
        size="small"
        placeholder="循环"
        clearable
        class="gt-wptt-select"
      >
        <el-option label="全部" value="" />
        <el-option
          v-for="c in cycleOptions"
          :key="c.cycle"
          :label="c.cycle_name"
          :value="c.cycle"
        />
      </el-select>

      <div class="gt-wptt-spacer" />

      <span class="gt-wptt-count">
        共 <span class="gt-amt">{{ filteredCount }}</span> 个模板
      </span>
    </div>

    <!-- 主体：树 -->
    <div v-loading="loading" class="gt-wptt-body">
      <el-empty
        v-if="!loading && templates.length === 0"
        description="暂无模板数据"
      />
      <el-empty
        v-else-if="!loading && filteredCount === 0"
        description="未匹配到任何模板"
      />
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        :props="{ label: 'label', children: 'children' }"
        node-key="id"
        :default-expanded-keys="defaultExpandedKeys"
        :expand-on-click-node="true"
        class="gt-wptt-tree"
        @node-click="onNodeClick"
      >
        <template #default="{ node, data }">
          <span
            class="gt-wptt-node"
            :class="{
              'gt-wptt-node--cycle': data.isCycle,
              'gt-tree-ungenerated': !data.isCycle && data.generated === false,
              'gt-tree-selected': !data.isCycle && data.wpCode === selectedWpCode,
            }"
          >
            <!-- 模板节点：图标 + wp_code + wp_name + 标记 -->
            <template v-if="!data.isCycle">
              <span class="gt-wptt-format-icon">{{ formatIcon(data.format) }}</span>
              <span class="gt-wptt-node-label">
                <span class="gt-wptt-code" v-html="highlightedCode(data.wpCode || '')"></span>
                <span class="gt-wptt-name" v-html="highlightedName(data.wpName || '')"></span>
              </span>
              <span v-if="data.hasFormula" class="gt-wptt-formula-mark" title="包含预填充公式">✦</span>
              <span v-if="data.componentType" class="gt-wptt-comp-tag" :class="`gt-wptt-comp--${data.componentType}`">
                {{ data.componentType }}
              </span>
              <span v-if="data.sheetCount && data.sheetCount > 1" class="gt-wptt-sheets">
                ({{ data.sheetCount }} sheets)
              </span>
            </template>
            <!-- 循环节点：cycle_name（count） -->
            <template v-else>
              <el-icon class="gt-wptt-cycle-icon"><Folder /></el-icon>
              <span class="gt-wptt-cycle-label">{{ node.label }}</span>
            </template>
          </span>
        </template>
      </el-tree>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Folder } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  projectId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'select', wpCode: string): void
}>()

interface TemplateItem {
  wp_code: string
  wp_name: string
  cycle: string
  cycle_name: string
  filename?: string
  format?: string
  component_type?: string | null
  audit_stage?: string | null
  linked_accounts?: string[]
  has_formula?: boolean
  source_file_count?: number
  sheet_count?: number
  generated?: boolean
  sort_order?: number | null
}

interface TreeNode {
  id: string
  label: string
  isCycle?: boolean
  wpCode?: string
  wpName?: string
  format?: string
  componentType?: string | null
  hasFormula?: boolean
  sheetCount?: number
  generated?: boolean
  children?: TreeNode[]
}

// ─── State ───────────────────────────────────────────────────────────────
const loading = ref(false)
const templates = ref<TemplateItem[]>([])
const searchInput = ref('')
const searchText = ref('')  // debounced
const filterComponentType = ref<string>('')
const filterCycle = ref<string>('')
const selectedWpCode = ref<string>('')
const treeRef = ref<any>(null)

// ─── Debounce 搜索 (300ms) ────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(searchInput, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    searchText.value = (val || '').trim()
  }, 300)
})

// ─── 数据加载 ─────────────────────────────────────────────────────────────
async function loadTemplates() {
  if (!props.projectId) {
    templates.value = []
    return
  }
  loading.value = true
  try {
    const data = await api.get(P_wp.templateList(props.projectId))
    const list = Array.isArray(data) ? data : (data?.items || [])
    templates.value = list as TemplateItem[]
  } catch (e: any) {
    handleApiError(e, '加载底稿模板列表')
    templates.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadTemplates()
})

watch(() => props.projectId, () => {
  loadTemplates()
})

// ─── 循环下拉选项（动态从数据中提取） ────────────────────────────────────
const cycleOptions = computed(() => {
  const map = new Map<string, { cycle: string; cycle_name: string; sortOrder: number }>()
  for (const t of templates.value) {
    if (!map.has(t.cycle)) {
      map.set(t.cycle, {
        cycle: t.cycle,
        cycle_name: t.cycle_name || `${t.cycle} 循环`,
        sortOrder: t.sort_order ?? 999999,
      })
    }
  }
  return Array.from(map.values()).sort((a, b) => {
    if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder
    return a.cycle.localeCompare(b.cycle)
  })
})

// ─── 过滤后的模板（搜索 + 组件类型 + 循环） ──────────────────────────────
const filteredTemplates = computed<TemplateItem[]>(() => {
  const q = searchText.value.toLowerCase()
  const ct = filterComponentType.value
  const cy = filterCycle.value
  return templates.value.filter(t => {
    if (ct && t.component_type !== ct) return false
    if (cy && t.cycle !== cy) return false
    if (q) {
      const code = (t.wp_code || '').toLowerCase()
      const name = (t.wp_name || '').toLowerCase()
      if (!code.includes(q) && !name.includes(q)) return false
    }
    return true
  })
})

const filteredCount = computed(() => filteredTemplates.value.length)

// ─── 树形结构（按循环分组） ──────────────────────────────────────────────
const treeData = computed<TreeNode[]>(() => {
  const groups = new Map<string, {
    cycle: string
    cycleName: string
    sortOrder: number
    items: TemplateItem[]
  }>()

  for (const t of filteredTemplates.value) {
    const key = t.cycle || '?'
    if (!groups.has(key)) {
      groups.set(key, {
        cycle: key,
        cycleName: t.cycle_name || `${key} 循环`,
        sortOrder: t.sort_order ?? 999999,
        items: [],
      })
    }
    groups.get(key)!.items.push(t)
  }

  // 按 sort_order 升序
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    const ga = groups.get(a)!
    const gb = groups.get(b)!
    if (ga.sortOrder !== gb.sortOrder) return ga.sortOrder - gb.sortOrder
    return a.localeCompare(b)
  })

  const result: TreeNode[] = []
  for (const key of sortedKeys) {
    const g = groups.get(key)!
    if (g.items.length === 0) continue
    const children: TreeNode[] = g.items
      .slice()
      .sort((a, b) => (a.wp_code || '').localeCompare(b.wp_code || ''))
      .map(t => ({
        id: t.wp_code,
        label: `${t.wp_code} ${t.wp_name}`,
        wpCode: t.wp_code,
        wpName: t.wp_name,
        format: t.format,
        componentType: t.component_type ?? null,
        hasFormula: !!t.has_formula,
        sheetCount: t.sheet_count ?? 1,
        generated: t.generated,
      }))
    result.push({
      id: `cycle-${key}`,
      label: `${g.cycleName}（${g.items.length}）`,
      isCycle: true,
      children,
    })
  }
  return result
})

// 默认展开循环节点（仅在初次加载或筛选变化时展开）
const defaultExpandedKeys = computed<string[]>(() => {
  return treeData.value.map(n => n.id)
})

// ─── 节点点击 → emit('select') ───────────────────────────────────────────
function onNodeClick(data: TreeNode) {
  if (data.isCycle || !data.wpCode) return
  selectedWpCode.value = data.wpCode
  emit('select', data.wpCode)
}

// ─── 格式图标 ─────────────────────────────────────────────────────────────
function formatIcon(format?: string): string {
  const f = (format || '').toLowerCase()
  if (f === 'xlsx' || f === 'xls') return '📊'
  if (f === 'xlsm') return '⚙️'  // 含宏
  if (f === 'docx' || f === 'doc') return '📝'
  return '📄'
}

// ─── 搜索高亮（XSS 安全：先 escape 再 wrap） ─────────────────────────────
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightText(text: string, q: string): string {
  const safe = escapeHtml(text)
  if (!q) return safe
  const safeQ = escapeRegex(escapeHtml(q))
  if (!safeQ) return safe
  try {
    const re = new RegExp(`(${safeQ})`, 'gi')
    return safe.replace(re, '<span class="gt-wptt-hl">$1</span>')
  } catch {
    return safe
  }
}

function highlightedCode(code: string): string {
  return highlightText(code, searchText.value)
}

function highlightedName(name: string): string {
  return highlightText(name, searchText.value)
}
</script>

<style scoped>
.gt-wptt {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* ─── 紧凑工具栏 ─── */
.gt-wptt-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--gt-color-bg);
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}
.gt-wptt-search { width: 240px; }
.gt-wptt-select { width: 140px; }
.gt-wptt-spacer { flex: 1; }
.gt-wptt-count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--gt-color-primary);
}

/* ─── 主体 ─── */
.gt-wptt-body {
  flex: 1;
  overflow: auto;
  padding: 8px 4px;
  min-height: 0;
}

.gt-wptt-tree {
  background: transparent;
}
.gt-wptt-tree :deep(.el-tree-node__content) {
  height: 28px;
  padding-right: 8px;
}
.gt-wptt-tree :deep(.el-tree-node__content:hover) {
  background-color: var(--gt-color-primary-bg);
}

/* ─── 节点样式 ─── */
.gt-wptt-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  flex: 1;
  min-width: 0;
}
.gt-wptt-node--cycle {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-wptt-cycle-icon {
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
}
.gt-wptt-cycle-label {
  white-space: nowrap;
}

.gt-wptt-format-icon {
  font-size: var(--gt-font-size-sm);
  flex-shrink: 0;
}
.gt-wptt-node-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.gt-wptt-code {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-weight: 600;
  color: var(--gt-color-text-primary);
  white-space: nowrap;
}
.gt-wptt-name {
  color: var(--gt-color-text-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 高亮匹配 */
.gt-wptt-node :deep(.gt-wptt-hl) {
  background-color: var(--gt-color-wheat-light);
  color: var(--gt-color-wheat);
  border-radius: 2px;
  padding: 0 1px;
}

/* 公式标记 */
.gt-wptt-formula-mark {
  color: var(--gt-color-teal);
  font-size: var(--gt-font-size-xs);
  flex-shrink: 0;
}

/* 组件类型标签 */
.gt-wptt-comp-tag {
  font-size: var(--gt-font-size-xs);
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--gt-color-bg);
  color: var(--gt-color-text-regular);
  flex-shrink: 0;
  line-height: 1.4;
}
.gt-wptt-comp--univer { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.gt-wptt-comp--form { background: var(--gt-color-primary-bg); color: var(--gt-color-primary-light); }
.gt-wptt-comp--word { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.gt-wptt-comp--hybrid { background: var(--gt-color-success-light); color: var(--gt-color-success); }

/* sheet 数量提示 */
.gt-wptt-sheets {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  flex-shrink: 0;
}

/* 未生成模板灰色显示 */
.gt-tree-ungenerated .gt-wptt-code,
.gt-tree-ungenerated .gt-wptt-name {
  color: var(--gt-color-text-placeholder);
}
.gt-tree-ungenerated .gt-wptt-format-icon {
  opacity: 0.5;
}

/* 选中行：14% 紫色背景 + 3px 紫色左边框 */
.gt-tree-selected {
  background-color: rgba(75, 45, 119, 0.14);
  border-left: 3px solid #4b2d77;
  padding-left: 5px !important;
  margin-left: -8px;
}
</style>
