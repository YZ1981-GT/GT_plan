<template>
  <div class="gt-four-catalog">
    <!-- 单位/集团树形结构 -->
    <div class="gt-catalog-unit-tree">
      <!-- 用户所有项目（树形结构：合并项目→子项目） -->
      <div class="gt-catalog-unit-group">
        <div class="gt-catalog-unit-group-title">
          <el-icon :size="14"><FolderOpened /></el-icon>
          <span>我的项目 ({{ relatedProjects.length }})</span>
        </div>
        <div class="gt-catalog-unit-group-items">
          <template v-for="group in projectGroups" :key="group.parentId || 'standalone'">
            <!-- 集团父项目 -->
            <div v-if="group.parent" class="gt-catalog-unit-group-parent">
              <el-icon :size="12" style="color: var(--gt-color-text-tertiary)"><Connection /></el-icon>
              <span>{{ group.parent.name || group.parent.client_name }}</span>
            </div>
            <!-- 项目列表 -->
            <div
              v-for="rp in group.items" :key="rp.id"
              class="gt-catalog-unit-related"
              :class="{ 'gt-catalog-unit-related--current': rp.id === project?.id }"
              :style="{ paddingLeft: group.parent ? '24px' : '8px' }"
              @click="onSwitchProject(rp)"
            >
              <span class="gt-catalog-unit-related-dot" :style="{ background: rp.id === project?.id ? 'var(--gt-color-primary)' : '#ccc' }"></span>
              <span class="gt-catalog-unit-related-name">{{ rp.name || rp.client_name }}</span>
              <el-tag v-if="rp.report_scope === 'consolidated'" size="small" type="warning" style="margin-left: auto; font-size: var(--gt-font-size-xs);">合并</el-tag>
            </div>
          </template>
          <div v-if="!relatedProjects.length" style="padding: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); text-align: center;">暂无项目</div>
        </div>
      </div>
    </div>

    <!-- 功能切换 -->
    <div class="gt-catalog-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="gt-catalog-tab"
        :class="{ 'gt-catalog-tab--active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <el-icon :size="14"><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </div>
    </div>

    <!-- 报表目录 -->
    <div v-if="activeTab === 'reports'" class="gt-catalog-list">
      <div class="gt-catalog-group" v-for="year in reportYears" :key="year">
        <div class="gt-catalog-group-title" @click="toggleGroup('report-' + year)">
          <span>{{ expanded['report-' + year] ? '−' : '+' }}</span>
          <span>{{ year }} 年度</span>
        </div>
        <div v-if="expanded['report-' + year]" class="gt-catalog-group-items">
          <div
            v-for="rt in reportTypes"
            :key="rt.key"
            class="gt-catalog-item"
            :class="{ 'gt-catalog-item--active': selectedKey === `report:${year}:${rt.key}` }"
            @click="selectItem('report', { year, type: rt.key, label: rt.label })"
          >
            {{ rt.label }}
          </div>
        </div>
      </div>
    </div>

    <!-- 附注目录 -->
    <div v-if="activeTab === 'notes'" class="gt-catalog-list">
      <div v-for="chapter in noteChapters" :key="chapter.prefix" class="gt-catalog-group">
        <div class="gt-catalog-group-title" @click="toggleGroup('note-' + chapter.prefix)">
          <span>{{ expanded['note-' + chapter.prefix] ? '−' : '+' }}</span>
          <span>{{ chapter.prefix }}、{{ chapter.label }} ({{ chapter.items.length }})</span>
        </div>
        <div v-if="expanded['note-' + chapter.prefix]" class="gt-catalog-group-items">
          <div
            v-for="section in chapter.items"
            :key="section.code"
            class="gt-catalog-item"
            :class="{ 'gt-catalog-item--active': selectedKey === `note:${section.code}` }"
            @click="selectItem('note', section)"
          >
            {{ section.shortLabel || section.title }}
          </div>
        </div>
      </div>
      <el-empty v-if="!noteChapters.length" description="暂无附注数据" :image-size="40" />
    </div>

    <!-- 底稿目录 -->
    <div v-if="activeTab === 'workpapers'" class="gt-catalog-list">
      <div v-for="cycle in wpCycles" :key="cycle.key" class="gt-catalog-group">
        <div class="gt-catalog-group-title" @click="toggleGroup('wp-' + cycle.key)">
          <span>{{ expanded['wp-' + cycle.key] ? '−' : '+' }}</span>
          <span>{{ cycle.label }} ({{ cycle.count }})</span>
        </div>
        <div v-if="expanded['wp-' + cycle.key]" class="gt-catalog-group-items">
          <div
            v-for="wp in cycle.items"
            :key="wp.id"
            class="gt-catalog-item"
            :class="{ 'gt-catalog-item--active': selectedKey === `wp:${wp.id}` }"
            @click="selectItem('workpaper', wp)"
          >
            {{ wp.wp_code }} {{ wp.name }}
          </div>
        </div>
      </div>
      <el-empty v-if="!wpCycles.length" description="暂无底稿" :image-size="40" />
    </div>

    <!-- 试算表目录 -->
    <div v-if="activeTab === 'trial_balance'" class="gt-catalog-list">
      <div v-for="cat in tbCategories" :key="cat.key" class="gt-catalog-group">
        <div class="gt-catalog-group-title" @click="toggleGroup('tb-' + cat.key)">
          <span>{{ expanded['tb-' + cat.key] ? '−' : '+' }}</span>
          <span>{{ cat.label }} ({{ cat.count }})</span>
        </div>
        <div v-if="expanded['tb-' + cat.key]" class="gt-catalog-group-items">
          <div
            v-for="row in cat.items"
            :key="row.code"
            class="gt-catalog-item"
            :class="{ 'gt-catalog-item--active': selectedKey === `tb:${row.code}` }"
            @click="selectItem('trial_balance', row)"
          >
            {{ row.code }} {{ row.name }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed, onUnmounted } from 'vue'
import { DataLine, Notebook, Document, TrendCharts, FolderOpened, Connection } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  project: any
  activeCatalog?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: any): void
  (e: 'tab-change', tab: string): void
}>()

const activeTab = ref(props.activeCatalog || 'reports')

// ─── Task 2.1: 内部状态 + 防抖 ──────────────────────────────────────────────
const loadingProjectId = ref<string | null>(null)
const isNavigating = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

/** 300ms 防抖工具函数 */
function debounce(fn: () => void) {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    fn()
  }, 300)
}

// ─── Task 2.2: onSwitchProject（防抖 + loading + isNavigating 守卫） ─────────
// 单位/集团树
const relatedProjects = ref<any[]>([])

function onSwitchProject(rp: any) {
  // 同项目不操作（Req 1.4）
  if (rp.id === props.project?.id) return
  // 导航进行中禁用交互（Req 4.4）
  if (isNavigating.value) return

  // 设置 loading 状态（Req 4.1）
  loadingProjectId.value = rp.id
  isNavigating.value = true

  // 安全超时：5s 内若 project.id watch 未触发（路由失败），自动解锁
  setTimeout(() => {
    if (isNavigating.value && loadingProjectId.value === rp.id) {
      isNavigating.value = false
      loadingProjectId.value = null
    }
  }, 5000)

  // 防抖 300ms（Req 4.3）
  debounce(() => {
    emit('select', {
      type: 'switch_project',
      project_id: rp.id,
      year: rp.audit_year || rp.year,
      name: rp.name,
    })
  })
}

// 按集团分组项目
const projectGroups = computed(() => {
  const groups: Array<{ parentId: string | null; parent: any; items: any[] }> = []
  const parentMap: Record<string, any[]> = {}
  const standalone: any[] = []
  const parentProjects: Record<string, any> = {}

  for (const p of relatedProjects.value) {
    if (p.parent_project_id) {
      if (!parentMap[p.parent_project_id]) parentMap[p.parent_project_id] = []
      parentMap[p.parent_project_id].push(p)
    }
  }
  for (const p of relatedProjects.value) {
    if (parentMap[p.id]) {
      parentProjects[p.id] = p
    }
  }
  // 集团项目（父+子）
  for (const [pid, children] of Object.entries(parentMap)) {
    const parent = parentProjects[pid] || relatedProjects.value.find((p: any) => p.id === pid)
    const items = parent ? [parent, ...children.filter((c: any) => c.id !== pid)] : children
    groups.push({ parentId: pid, parent, items })
  }
  // 独立项目（不属于任何集团）
  for (const p of relatedProjects.value) {
    if (!p.parent_project_id && !parentMap[p.id]) {
      standalone.push(p)
    }
  }
  if (standalone.length) {
    groups.push({ parentId: null, parent: null, items: standalone })
  }
  return groups
})

// tab 切换时通知父组件
watch(activeTab, (v) => emit('tab-change', v))
const selectedKey = ref('')
const expanded = reactive<Record<string, boolean>>({})

// ─── 导出内部状态供测试使用 ─────────────────────────────────────────────────
defineExpose({ selectedKey, loadingProjectId, isNavigating })

const tabs = [
  { key: 'reports', label: '报表', icon: TrendCharts },
  { key: 'notes', label: '附注', icon: Notebook },
  { key: 'workpapers', label: '底稿', icon: Document },
  { key: 'trial_balance', label: '试算表', icon: DataLine },
]

// 报表
const currentYear = computed(() => Number(props.project?.audit_year) || new Date().getFullYear())
const reportYears = computed(() => [currentYear.value, currentYear.value - 1, currentYear.value - 2])
const reportTypes = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
  { key: 'equity_statement', label: '所有者权益变动表' },
]

// 附注
const noteSections = ref<any[]>([])

// 按大章分组附注（与右侧编辑器树一致）
// 大章标题映射：与 useNoteTree.ts 中 SOE_LABELS 保持一致
const CHAPTER_LABELS: Record<string, string> = {
  '一': '公司基本情况',
  '二': '财务报表编制基础',
  '三': '遵循企业会计准则的声明',
  '四': '重要会计政策、会计估计',
  '五': '会计政策变更及差错更正',
  '六': '税项',
  '七': '企业合并及合并财务报表',
  '八': '财务报表主要项目注释',
  '九': '或有事项',
  '十': '资产负债表日后事项',
  '十一': '关联方关系及其交易',
  '十二': '母公司财务报表附注',
  '十三': '其他披露内容',
  '十四': '财务报表之批准',
  '十五': '其他重要事项',
  '十六': '公司财务报表主要项目注释',
  '十七': '补充资料',
}
const CHAPTER_PREFIXES = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五', '十六', '十七']

const noteChapters = computed(() => {
  if (!noteSections.value.length) return []
  const chapters: Array<{ prefix: string; label: string; items: any[] }> = []

  for (const prefix of CHAPTER_PREFIXES) {
    const items: any[] = []
    noteSections.value.forEach((s) => {
      const code = s.code as string
      if (!code.startsWith(prefix + '、')) return
      // 避免 "十" 误匹配 "十一、" ~ "十七、"
      if (prefix === '十' && /^十[一二三四五六七]/.test(code)) return
      items.push(s)
    })
    if (items.length > 0) {
      // 大章标题从映射表取，确保与右侧树完全一致
      const label = CHAPTER_LABELS[prefix] || prefix
      chapters.push({ prefix, label, items })
    }
  }

  // 无法按中文章节号归类的条目不在四栏目录显示（右侧树也不单独展示这些）
  return chapters
})

// 底稿
const wpCycles = ref<any[]>([])

// 试算表
const tbCategories = ref<any[]>([])

function toggleGroup(key: string) {
  expanded[key] = !expanded[key]
}

// ─── Task 2.3: selectItem — 附注章节点击 debounce + 乐观更新 + 同章节守卫 ───
function selectItem(type: string, data: any) {
  // 导航进行中禁用交互（Req 4.4）
  if (isNavigating.value) return

  const newKey = type === 'report' ? `report:${data.year}:${data.type}`
    : type === 'note' ? `note:${data.code}`
    : type === 'workpaper' ? `wp:${data.id}`
    : `tb:${data.code}`

  // 同项已选中则 no-op（Req 1.4, 2.4）
  if (selectedKey.value === newKey) return

  // 乐观更新 selectedKey（Req 4.2 — 同步更新不等 async）
  selectedKey.value = newKey

  // 构建 payload
  const payload: any = { type, ...data }
  if (type === 'report') {
    payload.type_key = data.type
  }

  if (type === 'note') {
    // 附注章节点击：debounce 后 emit（Req 4.3）
    debounce(() => {
      emit('select', { type: 'note', code: data.code })
    })
  } else {
    // 非附注类型直接 emit（报表/底稿/试算表保持即时响应）
    emit('select', payload)
  }
}

// 默认展开第一组
watch(activeTab, () => {
  if (activeTab.value === 'reports' && !expanded[`report-${currentYear.value}`]) {
    expanded[`report-${currentYear.value}`] = true
  }
}, { immediate: true })

// 加载数据
watch(() => props.project?.id, async (pid) => {
  if (!pid) return

  // 加载附注章节（静默失败，数据可能还没生成）
  try {
    const data = await api.get(`/api/disclosure-notes/${pid}/${currentYear.value}`, {
      validateStatus: (s: number) => s < 500,  // 4xx 不抛异常
    })
    if (data) {
      const d = data
      noteSections.value = Array.isArray(d) ? d.map((s: any) => {
        const code = s.note_section || s.section_code || s.code || ''
        const title = s.section_title || s.title || ''
        // shortLabel: 去掉大章前缀，只显示子编号+标题（如 "一、1 xx" → "1 xx"）
        const subMatch = code.match(/^[一二三四五六七八九十]+、(.+)$/)
        const shortLabel = subMatch ? `${subMatch[1]} ${title}` : title
        return { code, title, shortLabel }
      }) : []
    }
  } catch { noteSections.value = [] }

  // 加载试算表分类（静默失败）
  try {
    const data = await api.get(P.trialBalance.get(pid), {
      params: { year: currentYear.value },
      validateStatus: (s: number) => s < 600,
    })
    if (data && Array.isArray(data)) {
      const rows = data ?? []
    const catMap: Record<string, any[]> = {}
    for (const r of rows) {
      const cat = r.account_category || 'other'
      if (!catMap[cat]) catMap[cat] = []
      catMap[cat].push({ code: r.standard_account_code, name: r.account_name })
    }
    const catLabels: Record<string, string> = {
      asset: '资产类', liability: '负债类', equity: '权益类',
      revenue: '收入类', expense: '费用类', other: '其他',
    }
    tbCategories.value = Object.entries(catMap).map(([k, items]) => ({
      key: k, label: catLabels[k] || k, count: items.length, items,
    }))
    }
  } catch { tbCategories.value = [] }

  // 加载底稿列表（按审计循环分组）
  try {
    const data = await api.get(P.workpapers.list(pid), {
      validateStatus: (s: number) => s < 600,
    })
    const wps = Array.isArray(data) ? (data) : []
    const cycleMap: Record<string, any[]> = {}
    for (const wp of wps) {
      const cycle = wp.audit_cycle || wp.wp_code?.charAt(0) || 'Z'
      if (!cycleMap[cycle]) cycleMap[cycle] = []
      cycleMap[cycle].push({ id: wp.id, wp_code: wp.wp_code, name: wp.wp_name || wp.name })
    }
    const cycleLabels: Record<string, string> = {
      B: 'B-货币资金', C: 'C-应收', D: 'D-存货', E: 'E-固定资产',
      F: 'F-无形资产', G: 'G-投资', H: 'H-负债', I: 'I-收入',
      J: 'J-成本费用', K: 'K-薪酬', L: 'L-税费', M: 'M-权益',
      N: 'N-其他', A: 'A-综合', S: 'S-特殊', Q: 'Q-关联方',
    }
    wpCycles.value = Object.entries(cycleMap).map(([k, items]) => ({
      key: k, label: cycleLabels[k] || `${k}-其他`, count: items.length, items,
    })).sort((a, b) => a.key.localeCompare(b.key))
  } catch { wpCycles.value = [] }
}, { immediate: true })

// 加载用户负责的所有项目
watch(() => props.project?.id, async (pid) => {
  if (!pid) { relatedProjects.value = []; return }
  try {
    const data = await api.get(P.projects.list, { validateStatus: (s: number) => s < 500 })
    const all = Array.isArray(data) ? data : (data?.items || [])
    // 显示用户能看到的所有项目（后端已按权限过滤）
    relatedProjects.value = all
  } catch { relatedProjects.value = [] }
}, { immediate: true })

// ─── Task 2.4: eventBus 监听 + project.id 变化清除 + unmount 清理 ────────────

// 监听 DisclosureEditor 反向通知：更新 selectedKey（Req 3.1）
function onSectionChanged({ noteSection }: { noteSection: string }) {
  if (noteSection) {
    selectedKey.value = `note:${noteSection}`
  }
}
eventBus.on('note:section-changed', onSectionChanged)

// 项目切换完成：清除选中状态 + 重置导航态（Req 3.4）
watch(() => props.project?.id, (_newId, oldId) => {
  // 仅在项目实际变化时清除（非初始化）
  if (oldId && _newId !== oldId) {
    selectedKey.value = ''
    loadingProjectId.value = null
    isNavigating.value = false
  }
})

// 组件卸载时清理 eventBus 监听和 debounce timer
onUnmounted(() => {
  eventBus.off('note:section-changed', onSectionChanged)
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
})
</script>

<style scoped>
.gt-four-catalog { display: flex; flex-direction: column; height: 100%; }

/* 单位/集团树 */
.gt-catalog-unit-tree {
  padding: var(--gt-space-3); border-bottom: 1px solid var(--gt-color-border-light); flex-shrink: 0;
}
.gt-catalog-unit-current {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
}
.gt-catalog-unit-icon { font-size: 24px /* allow-px: special */; }
.gt-catalog-unit-info { flex: 1; min-width: 0; }
.gt-catalog-unit-name {
  font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gt-catalog-unit-meta { display: flex; gap: 4px; margin-top: 2px; }
.gt-catalog-unit-group-title {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 0; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); cursor: pointer;
}
.gt-catalog-unit-group-title:hover { color: var(--gt-color-primary); }
.gt-catalog-unit-group-parent {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);
}
.gt-catalog-unit-related-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0;
}
.gt-catalog-unit-related {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 6px; font-size: var(--gt-font-size-xs); cursor: pointer; border-radius: 4px;
  color: var(--gt-color-text-secondary);
}
.gt-catalog-unit-related:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-catalog-unit-related--current { font-weight: 600; color: var(--gt-color-primary); }
.gt-catalog-unit-related-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}

.gt-catalog-tabs {
  display: flex; gap: 2px; padding: var(--gt-space-2);
  border-bottom: 1px solid var(--gt-color-border-light); flex-shrink: 0;
}
.gt-catalog-tab {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px; border-radius: var(--gt-radius-sm);
  font-size: var(--gt-font-size-xs); cursor: pointer; color: var(--gt-color-text-secondary);
  transition: all var(--gt-transition-fast);
}
.gt-catalog-tab:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-catalog-tab--active { background: var(--gt-color-primary); color: var(--gt-color-text-inverse); }
.gt-catalog-list { flex: 1; overflow-y: auto; padding: var(--gt-space-1); }
.gt-catalog-group { margin-bottom: 2px; }
.gt-catalog-group-title {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 8px; font-size: var(--gt-font-size-xs); font-weight: 600;
  color: var(--gt-color-text-secondary); cursor: pointer;
  border-radius: var(--gt-radius-sm);
}
.gt-catalog-group-title:hover { background: var(--gt-bg-subtle); }
.gt-catalog-group-items { padding-left: 12px; }
.gt-catalog-item {
  padding: 5px 8px; font-size: var(--gt-font-size-xs); cursor: pointer;
  border-radius: var(--gt-radius-sm); color: var(--gt-color-text);
  transition: all var(--gt-transition-fast); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.gt-catalog-item:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-catalog-item--active {
  background: var(--gt-color-primary) !important; color: var(--gt-color-text-inverse) !important;
}
</style>
