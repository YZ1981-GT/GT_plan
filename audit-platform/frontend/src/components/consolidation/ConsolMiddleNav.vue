<template>
  <div class="cm-nav">
    <div class="cm-nav-header">
      <span class="cm-nav-title">企业树</span>
      <el-tooltip content="重新读取企业树（按各项目的企业代码、上级代码与与上级关系自动生成）" placement="bottom">
        <el-button size="small" :loading="loading" data-testid="cm-reload" @click="loadTree">🔄 刷新</el-button>
      </el-tooltip>
    </div>
    <div v-if="modeText" class="cm-nav-mode" data-testid="cm-mode">合并方式：{{ modeText }}</div>

    <!-- 企业树：只渲染后端按三码推导的结果，节点键为 node_key -->
    <div class="cm-tree">
      <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }"
        node-key="key" default-expand-all highlight-current :expand-on-click-node="false"
        @node-click="onNodeClick" @node-contextmenu="onNodeContextMenu">
        <template #default="{ data }">
          <span class="cm-tree-node" :class="`cm-tree-node--${data.kind}`" :data-node-key="data.key">
            <span class="cm-tree-icon">{{ data.icon }}</span>
            <span class="cm-tree-label" :title="data.viaText || data.label">{{ data.label }}</span>
            <el-tag v-if="data.relationText" size="small" effect="plain" class="cm-tree-tag">{{ data.relationText }}</el-tag>
            <el-tooltip v-if="data.warnText" :content="data.warnText" placement="right">
              <span class="cm-tree-warn">⚠</span>
            </el-tooltip>
            <!-- 企业节点刷新按钮（hover 显示）；差额节点金额来自分录，不提供 -->
            <el-button v-if="!data.isElim" size="small" link class="cm-refresh-btn"
              title="刷新该单位数据" @click.stop="openRefreshDialog(data)">
              🔄
            </el-button>
          </span>
        </template>
      </el-tree>
      <el-empty v-if="!treeData.length && !loading" :description="emptyText" :image-size="40" />
    </div>

    <!-- 树形右键菜单 -->
    <Teleport to="body">
      <Transition name="cm-ctx-fade">
        <div v-if="treeContextMenu.visible" class="cm-context-menu"
          :style="{ left: treeContextMenu.x + 'px', top: treeContextMenu.y + 'px' }"
          @contextmenu.prevent>
          <div class="cm-ctx-header">{{ treeContextMenu.nodeName }}</div>
          <div class="cm-ctx-divider" />
          <div class="cm-ctx-item" @click="treeCtxAggregateDirect"><span class="cm-ctx-icon">Σ</span> 直接下级汇总</div>
          <div class="cm-ctx-item" @click="treeCtxAggregateCustom"><span class="cm-ctx-icon">📊</span> 自定义汇总</div>
          <div class="cm-ctx-divider" />
          <div class="cm-ctx-item" @click="treeCtxRefresh"><span class="cm-ctx-icon">🔄</span> 刷新数据</div>
          <div class="cm-ctx-item" @click="treeCtxViewReport"><span class="cm-ctx-icon">📋</span> 查看报表</div>
          <div class="cm-ctx-item" @click="treeCtxViewNote"><span class="cm-ctx-icon">📝</span> 查看附注</div>
        </div>
      </Transition>
    </Teleport>

    <!-- 刷新范围选择弹窗 -->
    <el-dialog v-model="showRefreshDialog" :title="`刷新 — ${refreshTarget.name}`" width="420px" append-to-body>
      <p style="font-size: var(--gt-font-size-sm);color: var(--gt-color-text-secondary);margin-bottom:12px">
        选择要从项目数据中刷新的内容（从子企业单体数据重新汇总）：
      </p>
      <div class="cm-refresh-options">
        <el-checkbox v-model="refreshOptions.allReports" @change="onAllReportsChange">全部报表（6张）</el-checkbox>
        <div v-show="!refreshOptions.allReports" class="cm-refresh-sub">
          <el-checkbox v-model="refreshOptions.balance_sheet">资产负债表</el-checkbox>
          <el-checkbox v-model="refreshOptions.income_statement">利润表</el-checkbox>
          <el-checkbox v-model="refreshOptions.cash_flow_statement">现金流量表</el-checkbox>
          <el-checkbox v-model="refreshOptions.equity_statement">权益变动表</el-checkbox>
          <el-checkbox v-model="refreshOptions.cash_flow_supplement">现金流附表</el-checkbox>
          <el-checkbox v-model="refreshOptions.impairment_provision">资产减值准备表</el-checkbox>
        </div>
        <el-checkbox v-model="refreshOptions.notes">全部附注</el-checkbox>
        <el-checkbox v-model="refreshOptions.worksheet">差额表</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showRefreshDialog = false">取消</el-button>
        <el-button type="primary" @click="doRefresh" :loading="refreshing">开始刷新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getWorksheetTree, type ConsolTreeNode, type ConsolTreeResponse } from '@/services/consolidationApi'
import { eventBus } from '@/utils/eventBus'
import { relationLabel } from '@/utils/groupRelation'
import {
  buildNameIndex,
  flagTags,
  modeLabel,
  nodeIcon,
  nodeLabel,
  viaLabel,
} from '@/components/consolidation/composables/consolTreeView'

defineOptions({ name: 'ConsolMiddleNav' })

interface NavNode {
  key: string
  label: string
  icon: string
  kind: string
  role: string
  isElim: boolean
  companyCode: string
  relationText: string
  warnText: string
  viaText: string
  children?: NavNode[]
}

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const loadError = ref('')
const response = ref<ConsolTreeResponse | null>(null)

const modeText = computed(() => modeLabel(response.value?.mode, response.value?.mode_label))
const emptyText = computed(() => loadError.value || response.value?.message || '暂无企业树')

// 后端树 → 导航节点（键 = node_key；标签 = 带角色后缀的展示名）
const treeData = computed<NavNode[]>(() => {
  const root = response.value?.tree
  if (!root) return []
  const names = buildNameIndex(root)
  function build(node: ConsolTreeNode): NavNode {
    const flags = flagTags(node)
    return {
      key: node.node_key,
      label: nodeLabel(node),
      icon: nodeIcon(node),
      kind: node.kind,
      role: node.role,
      isElim: node.kind === 'elim',
      companyCode: node.company_code,
      relationText: relationLabel(node.relation),
      warnText: flags.map((f) => f.hint || f.label).join('；'),
      viaText: viaLabel(node, names),
      children: node.children?.length ? node.children.map(build) : undefined,
    }
  }
  return [build(root)]
})

async function loadTree() {
  if (!projectId.value) return
  loading.value = true
  loadError.value = ''
  try {
    response.value = await getWorksheetTree(projectId.value)
  } catch {
    response.value = null
    loadError.value = '加载企业树失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function payloadOf(data: NavNode) {
  return { companyCode: data.companyCode, label: data.label, nodeKey: data.key, role: data.role, kind: data.kind }
}

function onNodeClick(data: NavNode) {
  // 通过事件总线通知合并页（差额节点由合并页打开差额分录面板）
  eventBus.emit('consol-tree-select', payloadOf(data))
}

// ─── 树形右键菜单（差额节点金额来自分录，不提供汇总/刷新菜单） ─────────────────
const treeContextMenu = reactive({ visible: false, x: 0, y: 0, nodeName: '', nodeData: null as NavNode | null })

function onNodeContextMenu(e: Event, data: NavNode) {
  const me = e as MouseEvent
  me.preventDefault()
  me.stopPropagation()
  if (data.isElim) return
  treeContextMenu.nodeName = data.label || ''
  treeContextMenu.nodeData = data
  setTimeout(() => {
    treeContextMenu.x = me.clientX
    treeContextMenu.y = me.clientY
    treeContextMenu.visible = true
  }, 0)
}

function closeTreeCtxMenu() { treeContextMenu.visible = false }

function treeCtxAggregateDirect() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-aggregate', { mode: 'direct', companyCode: data.companyCode, companyName: data.label })
}

function treeCtxAggregateCustom() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-aggregate', { mode: 'custom', companyCode: data.companyCode, companyName: data.label })
}

function treeCtxRefresh() {
  closeTreeCtxMenu()
  if (treeContextMenu.nodeData) openRefreshDialog(treeContextMenu.nodeData)
}

function treeCtxViewReport() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-select', { ...payloadOf(data), isReport: true, reportType: 'balance_sheet' })
}

function treeCtxViewNote() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-select', { ...payloadOf(data), switchTab: 'consol_note' })
}

function onDocClickTree(e: MouseEvent) {
  if (!(e.target as HTMLElement)?.closest('.cm-context-menu')) closeTreeCtxMenu()
}

// ─── 刷新功能 ────────────────────────────────────────────────────────────────
const showRefreshDialog = ref(false)
const refreshing = ref(false)
const refreshTarget = reactive({ code: '', name: '', nodeKey: '' })
const refreshOptions = reactive({
  allReports: true,
  balance_sheet: true, income_statement: true, cash_flow_statement: true,
  equity_statement: true, cash_flow_supplement: true, impairment_provision: true,
  notes: true, worksheet: true,
})

function openRefreshDialog(data: NavNode) {
  refreshTarget.code = data.companyCode || ''
  refreshTarget.name = data.label || ''
  refreshTarget.nodeKey = data.key
  refreshOptions.allReports = true
  refreshOptions.balance_sheet = true; refreshOptions.income_statement = true
  refreshOptions.cash_flow_statement = true; refreshOptions.equity_statement = true
  refreshOptions.cash_flow_supplement = true; refreshOptions.impairment_provision = true
  refreshOptions.notes = true; refreshOptions.worksheet = true
  showRefreshDialog.value = true
}

function onAllReportsChange(val: string | number | boolean) {
  const v = !!val
  refreshOptions.balance_sheet = v; refreshOptions.income_statement = v
  refreshOptions.cash_flow_statement = v; refreshOptions.equity_statement = v
  refreshOptions.cash_flow_supplement = v; refreshOptions.impairment_provision = v
}

async function doRefresh() {
  refreshing.value = true
  const types: string[] = []
  if (refreshOptions.allReports) {
    types.push('all_reports')
  } else {
    for (const k of ['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'cash_flow_supplement', 'impairment_provision'] as const) {
      if (refreshOptions[k]) types.push(k)
    }
  }
  if (refreshOptions.notes) types.push('notes')
  if (refreshOptions.worksheet) types.push('worksheet')

  // 通知 ConsolidationIndex 执行刷新
  eventBus.emit('consol-refresh-entity', {
    companyCode: refreshTarget.code,
    companyName: refreshTarget.name,
    nodeKey: refreshTarget.nodeKey,
    types,
  })
  await new Promise((r) => setTimeout(r, 500))
  refreshing.value = false
  showRefreshDialog.value = false
  ElMessage.success(`已发起刷新：${refreshTarget.name}（${types.length} 项）`)
}

// 一键刷新 / 分录变更完成后重新读取企业树（诊断与合并方式可能变化）
function onRefreshDone() { loadTree() }

watch(projectId, (pid, old) => { if (pid && pid !== old) loadTree() })

onMounted(() => {
  loadTree()
  document.addEventListener('click', onDocClickTree)
  eventBus.on('consol-refresh-done', onRefreshDone)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClickTree)
  eventBus.off('consol-refresh-done', onRefreshDone)
})

defineExpose({ loadTree })
</script>

<style scoped>
.cm-nav { display: flex; flex-direction: column; height: 100%; }
.cm-nav-header {
  padding: 10px 12px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0);
  display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
}
.cm-nav-title { font-size: var(--gt-font-size-sm); font-weight: 700; color: var(--gt-color-primary); }
.cm-nav-mode {
  padding: 4px 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);
  border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0);
}
.cm-tree { flex: 1; overflow-y: auto; padding: 6px; }
.cm-tree-node { display: flex; align-items: center; font-size: var(--gt-font-size-xs); gap: 4px; min-width: 0; }
.cm-tree-icon { font-size: var(--gt-font-size-sm); }
.cm-tree-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cm-tree-tag { font-size: var(--gt-font-size-xs); }
.cm-tree-warn { color: var(--gt-color-wheat, #d9b56b); cursor: help; }
.cm-tree-node--elim .cm-tree-label { color: var(--gt-color-wheat, #b8923e); font-style: italic; }
.cm-tree-node--aggregate .cm-tree-label { font-weight: 600; }
.cm-refresh-btn { opacity: 0; transition: opacity 0.15s; margin-left: auto; font-size: var(--gt-font-size-xs); padding: 0 2px; }
.cm-tree-node:hover .cm-refresh-btn { opacity: 1; }
.cm-refresh-options { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.cm-refresh-sub { padding-left: 24px; display: flex; flex-direction: column; gap: 4px; }

/* 树形右键菜单 */
.cm-context-menu {
  position: fixed; z-index: 10001; background: var(--gt-color-bg-white);
  border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,0.15); padding: 6px 0; min-width: 180px;
  border: 1px solid var(--gt-color-border-purple);
}
.cm-ctx-header { padding: 6px 14px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.cm-ctx-divider { height: 1px; background: var(--gt-color-primary-bg); margin: 2px 0; }
.cm-ctx-item {
  padding: 8px 14px; font-size: var(--gt-font-size-sm); cursor: pointer; color: var(--gt-color-text-primary);
  display: flex; align-items: center; gap: 6px; transition: background 0.1s;
}
.cm-ctx-item:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.cm-ctx-icon { width: 18px; text-align: center; }
.cm-ctx-fade-enter-active { transition: opacity 0.1s, transform 0.1s; }
.cm-ctx-fade-leave-active { transition: opacity 0.08s; }
.cm-ctx-fade-enter-from { opacity: 0; transform: scale(0.95); }
.cm-ctx-fade-leave-to { opacity: 0; }
</style>
