<template>
  <div class="gt-four-catalog">
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
      <div
        v-for="section in noteSections"
        :key="section.code"
        class="gt-catalog-item"
        :class="{ 'gt-catalog-item--active': selectedKey === `note:${section.code}` }"
        @click="selectItem('note', section)"
      >
        {{ section.code }} {{ section.title }}
      </div>
      <el-empty v-if="!noteSections.length" description="暂无附注数据" :image-size="40" />
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
import { ref, reactive, watch, computed } from 'vue'
import { DataLine, Notebook, Document, TrendCharts } from '@element-plus/icons-vue'
import http from '@/utils/http'

const props = defineProps<{
  project: any
  activeCatalog?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: any): void
  (e: 'tab-change', tab: string): void
}>()

const activeTab = ref(props.activeCatalog || 'reports')

// tab 切换时通知父组件
watch(activeTab, (v) => emit('tab-change', v))
const selectedKey = ref('')
const expanded = reactive<Record<string, boolean>>({})

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

// 底稿
const wpCycles = ref<any[]>([])

// 试算表
const tbCategories = ref<any[]>([])

function toggleGroup(key: string) {
  expanded[key] = !expanded[key]
}

function selectItem(type: string, data: any) {
  selectedKey.value = type === 'report' ? `report:${data.year}:${data.type}`
    : type === 'note' ? `note:${data.code}`
    : type === 'workpaper' ? `wp:${data.id}`
    : `tb:${data.code}`
  // 报表需要把原始 type（如 balance_sheet）改名为 type_key，避免和外层 type（report）冲突
  const payload = { type, ...data }
  if (type === 'report') {
    payload.type_key = data.type
  }
  emit('select', payload)
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
    const { data } = await http.get(`/api/disclosure-notes/${pid}/${currentYear.value}`, {
      validateStatus: (s: number) => s < 500,  // 4xx 不抛异常
    })
    if (data) {
      const d = data.data ?? data
      noteSections.value = Array.isArray(d) ? d.map((s: any) => ({
        code: s.note_section || s.section_code || s.code || '',
        title: s.section_title || s.title || '',
      })) : []
    }
  } catch { noteSections.value = [] }

  // 加载试算表分类（静默失败）
  try {
    const { data } = await http.get(`/api/projects/${pid}/trial-balance`, {
      params: { year: currentYear.value },
      validateStatus: (s: number) => s < 600,
    })
    if (data && Array.isArray(data.data ?? data)) {
      const rows = data.data ?? data ?? []
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
    const { data } = await http.get(`/api/projects/${pid}/working-papers`, {
      validateStatus: (s: number) => s < 600,
    })
    const wps = Array.isArray(data?.data ?? data) ? (data.data ?? data) : []
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
</script>

<style scoped>
.gt-four-catalog { display: flex; flex-direction: column; height: 100%; }
.gt-catalog-tabs {
  display: flex; gap: 2px; padding: var(--gt-space-2);
  border-bottom: 1px solid var(--gt-color-border-light); flex-shrink: 0;
}
.gt-catalog-tab {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px; border-radius: var(--gt-radius-sm);
  font-size: 12px; cursor: pointer; color: var(--gt-color-text-secondary);
  transition: all var(--gt-transition-fast);
}
.gt-catalog-tab:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-catalog-tab--active { background: var(--gt-color-primary); color: #fff; }
.gt-catalog-list { flex: 1; overflow-y: auto; padding: var(--gt-space-1); }
.gt-catalog-group { margin-bottom: 2px; }
.gt-catalog-group-title {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 8px; font-size: 12px; font-weight: 600;
  color: var(--gt-color-text-secondary); cursor: pointer;
  border-radius: var(--gt-radius-sm);
}
.gt-catalog-group-title:hover { background: #f5f7fa; }
.gt-catalog-group-items { padding-left: 12px; }
.gt-catalog-item {
  padding: 5px 8px; font-size: 12px; cursor: pointer;
  border-radius: var(--gt-radius-sm); color: var(--gt-color-text);
  transition: all var(--gt-transition-fast); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.gt-catalog-item:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-catalog-item--active {
  background: var(--gt-color-primary) !important; color: #fff !important;
}
</style>
