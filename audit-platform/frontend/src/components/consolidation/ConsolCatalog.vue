<template>
  <div class="cc-catalog">
    <!-- 标题行：报表/附注切换 + 刷新 -->
    <div class="cc-header">
      <div class="cc-tab-btns">
        <span class="cc-tab-btn" :class="{ 'cc-tab-btn--active': activeTab === 'reports' }" @click="activeTab = 'reports'">报表</span>
        <span class="cc-tab-btn" :class="{ 'cc-tab-btn--active': activeTab === 'notes' }" @click="activeTab = 'notes'">附注</span>
      </div>
      <el-tooltip content="刷新数据" placement="bottom">
        <el-button size="small" circle @click="refreshAll" :loading="refreshing" style="flex-shrink:0">
          <span style="font-size:12px">🔄</span>
        </el-button>
      </el-tooltip>
    </div>

    <!-- 内容区 -->
    <div class="cc-content">
      <div v-if="activeTab === 'reports'" class="cc-tree">
        <el-tree :data="reportTree" :props="{ label: 'label', children: 'children' }"
          node-key="key" default-expand-all highlight-current
          @node-click="onReportClick">
          <template #default="{ data }">
            <span class="cc-tree-node">
              <span>{{ data.icon }} {{ data.label }}</span>
              <el-button size="small" link class="cc-refresh-btn" @click.stop="refreshSingle('report', data)" title="从项目提取">🔄</el-button>
            </span>
          </template>
        </el-tree>
      </div>
      <div v-else class="cc-tree">
        <el-input v-model="noteSearch" size="small" placeholder="搜索附注..." clearable style="margin-bottom:6px" />
        <el-tree :data="noteTree" :props="{ label: 'label', children: 'children' }"
          node-key="key" highlight-current
          :filter-node-method="filterNote" ref="noteTreeRef"
          @node-click="onNoteClick">
          <template #default="{ data }">
            <span class="cc-tree-node">
              <span class="cc-tree-node-label">{{ data.label }}</span>
              <el-tag v-if="data.table_count" size="small" type="info" style="margin-left:4px;font-size:10px">{{ data.table_count }}表</el-tag>
            </span>
          </template>
        </el-tree>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const route = useRoute()
const _projectId = computed(() => route.params.projectId as string)
const standard = ref('soe')
const activeTab = ref('reports')
const noteSearch = ref('')
const noteTreeRef = ref<any>(null)

// 监听顶部栏准则切换事件
function onStandardChanged(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.standard) {
    standard.value = detail.standard
    loadData()
  }
}

// 监听四栏切换事件，自动切到附注 tab
function onSwitchFourCol(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.tab === 'notes') {
    activeTab.value = 'notes'
  }
}

onMounted(() => {
  loadData()
  window.addEventListener('consol-standard-change', onStandardChanged)
  window.addEventListener('gt-switch-four-col', onSwitchFourCol)
})

onUnmounted(() => {
  window.removeEventListener('consol-standard-change', onStandardChanged)
  window.removeEventListener('gt-switch-four-col', onSwitchFourCol)
})

// ─── 报表树 ──────────────────────────────────────────────────────────────────
const reportTree = computed(() => [
  { key: 'bs', label: '资产负债表', icon: '📋', type: 'balance_sheet' },
  { key: 'is', label: '利润表', icon: '📈', type: 'income_statement' },
  { key: 'cf', label: '现金流量表', icon: '💰', type: 'cash_flow_statement' },
  { key: 'eq', label: '权益变动表', icon: '📊', type: 'equity_statement' },
  { key: 'cfs', label: '现金流附表', icon: '📑', type: 'cash_flow_supplement' },
  { key: 'imp', label: '资产减值准备表', icon: '⚠️', type: 'impairment_provision' },
])

// ─── 附注树 ──────────────────────────────────────────────────────────────────
const noteTree = ref<any[]>([])

async function loadData() {
  try {
    // 从合并附注章节 API 加载（按父章节分组的树形）
    const { data } = await http.get(`/api/consol-note-sections/${standard.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    if (!Array.isArray(groups) || !groups.length) { noteTree.value = []; return }

    noteTree.value = groups.map((g: any) => ({
      key: `grp_${g.parent_seq}`,
      label: `${g.parent_seq}. ${g.label}`,
      table_count: g.table_count,
      children: (g.children || []).map((c: any) => ({
        key: c.section_id,
        label: c.title,
        section_id: c.section_id,
        title: c.title,
        table_count: 1,
      })),
    }))
  } catch { noteTree.value = [] }
}

function filterNote(value: string, data: any) {
  if (!value) return true
  return (data.label || '').includes(value) || (data.fullTitle || '').includes(value)
}

watch(noteSearch, (val) => { noteTreeRef.value?.filter(val) })

function onReportClick(data: any) {
  if (data.type) {
    window.dispatchEvent(new CustomEvent('consol-catalog-select', {
      detail: { type: 'report', reportType: data.type, standard: standard.value }
    }))
  }
}

function onNoteClick(data: any) {
  if (data.section_id) {
    window.dispatchEvent(new CustomEvent('consol-catalog-select', {
      detail: { type: 'note', sectionId: data.section_id, title: data.title || data.label, standard: standard.value }
    }))
  }
}

const refreshing = ref(false)

async function refreshAll() {
  refreshing.value = true
  try {
    // 通知右侧刷新所有报表和附注
    window.dispatchEvent(new CustomEvent('consol-catalog-select', {
      detail: { type: 'refresh-all', standard: standard.value }
    }))
    await loadData()
    ElMessage.success('已刷新所有报表和附注数据')
  } finally { refreshing.value = false }
}

function refreshSingle(type: string, data: any) {
  window.dispatchEvent(new CustomEvent('consol-catalog-select', {
    detail: {
      type: `refresh-${type}`,
      reportType: data.type,
      sectionId: data.sectionId,
      label: data.label || data.fullTitle,
      standard: standard.value,
    }
  }))
  ElMessage.success(`正在从项目提取: ${data.label || data.fullTitle}`)
}

// loadData is called in the onMounted above

const auditing = ref(false)

async function _auditAllNotes() {
  auditing.value = true
  // 通知 ConsolidationIndex 执行全审
  window.dispatchEvent(new CustomEvent('consol-note-audit-all', { detail: { standard: standard.value } }))
  auditing.value = false
}
</script>

<style scoped>
.cc-catalog { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.cc-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0;
}
.cc-tab-btns { display: flex; gap: 0; }
.cc-tab-btn {
  padding: 4px 12px; font-size: 13px; cursor: pointer; color: #999;
  border-bottom: 2px solid transparent; transition: all 0.15s; user-select: none;
}
.cc-tab-btn:hover { color: #4b2d77; }
.cc-tab-btn--active { color: #4b2d77; font-weight: 600; border-bottom-color: #4b2d77; }
.cc-content { flex: 1; overflow-y: auto; min-height: 0; }
.cc-tree { padding: 6px; }
.cc-tree-node { display: flex; align-items: center; font-size: 12px; width: 100%; }
.cc-tree-node-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.cc-refresh-btn { opacity: 0; transition: opacity 0.15s; margin-left: auto; font-size: 11px; padding: 0 4px; }
.cc-tree-node:hover .cc-refresh-btn { opacity: 1; }
</style>
