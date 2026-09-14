<template>
  <div class="ch-page gt-fade-in">
    <!-- 顶部横幅 -->
    <div class="ch-banner">
      <div class="ch-banner-bg" />
      <div class="ch-banner-content">
        <div class="ch-banner-icon">
          <el-icon :size="36"><Connection /></el-icon>
        </div>
        <div>
          <h1 class="ch-banner-title">集团合并报表</h1>
          <p class="ch-banner-desc">按集团架构树形展示合并项目，点击任意企业节点进入合并工作底稿、抵消分录、差额表、合并报表与附注</p>
        </div>
        <el-button class="ch-banner-action" @click="showBatchImport = true">
          <el-icon style="margin-right:4px"><Upload /></el-icon>批量建项
        </el-button>
      </div>
    </div>

    <!-- 批量建项弹窗 -->
    <BatchImportDialog v-model="showBatchImport" @success="reload" />

    <!-- 统计概览 -->
    <div class="ch-stats" v-if="!loading && hasAnyData">
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ consolidatedCount }}</span>
        <span class="ch-stat-label">合并项目</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ subsidiaryCount }}</span>
        <span class="ch-stat-label">子公司</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ executingCount }}</span>
        <span class="ch-stat-label">执行中</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ completedCount }}</span>
        <span class="ch-stat-label">已完成</span>
      </div>
    </div>

    <!-- 主体 -->
    <div v-loading="loading" class="ch-body">
      <!-- 加载失败 -->
      <el-empty v-if="!loading && error" :description="error" :image-size="120">
        <el-button type="primary" @click="reload">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>重试
        </el-button>
      </el-empty>

      <!-- 空态 -->
      <el-empty v-else-if="!loading && !hasAnyData" description="暂无合并项目" :image-size="120">
        <template #description>
          <p style="color: var(--gt-color-text-tertiary);font-size: var(--gt-font-size-sm)">还没有合并报表项目</p>
          <p style="color: var(--gt-color-text-placeholder);font-size: var(--gt-font-size-xs)">请先在项目管理中创建报表范围为"合并"的项目</p>
        </template>
        <el-button type="primary" @click="$router.push('/projects/new')">
          <el-icon style="margin-right:4px"><Plus /></el-icon>新建合并项目
        </el-button>
      </el-empty>

      <!-- 树形展示 -->
      <template v-else>
        <!-- 搜索框（高亮定位完整逻辑见 Task 5.1） -->
        <div class="ch-toolbar">
          <el-input
            v-model="searchQuery"
            class="ch-search"
            placeholder="搜索企业名称或代码"
            clearable
            :prefix-icon="Search"
          />
        </div>

        <!-- 无搜索匹配 -->
        <el-empty
          v-if="searchQuery.trim() && !hasSearchMatch"
          description="未找到匹配企业"
          :image-size="100"
        />

        <template v-else>
          <!-- 每个 ultimate 分组一棵集团树 -->
          <div v-for="tree in trees" :key="tree.ultimateCode" class="ch-tree-card">
            <div
              class="ch-tree-root"
              :class="{ 'ch-tree-root--clickable': tree.rootProjectId }"
              @click="goConsolidation(tree.rootProjectId)"
            >
              <div class="ch-tree-root-avatar">
                <el-icon :size="20"><OfficeBuilding /></el-icon>
              </div>
              <div class="ch-tree-root-info">
                <span class="ch-tree-root-name">{{ tree.ultimateName || '最终控制方' }}</span>
                <span class="ch-tree-root-code">{{ tree.ultimateCode || '—' }}</span>
              </div>
              <el-tag size="small" effect="light" round class="ch-tree-root-tag">最终控制方</el-tag>
              <el-tag
                v-if="hasScopeDiff(tree)"
                type="warning"
                size="small"
                effect="light"
                round
                class="ch-scope-diff-tag"
                @click.stop="openScopeDiffDialog(tree)"
              >⚠️ 合并范围差异</el-tag>
            </div>

            <!-- 合并方式统计（Task 14.2，无持股/合并方式数据时不显示） -->
            <div v-if="methodCounts(tree).total > 0" class="ch-method-stats">
              <span v-if="methodCounts(tree).full > 0" class="ch-method-stat ch-method-stat--full">完全合并 {{ methodCounts(tree).full }} 家</span>
              <span v-if="methodCounts(tree).equity > 0" class="ch-method-stat ch-method-stat--equity">权益法 {{ methodCounts(tree).equity }} 家</span>
              <span v-if="methodCounts(tree).proportional > 0" class="ch-method-stat ch-method-stat--prop">比例合并 {{ methodCounts(tree).proportional }} 家</span>
            </div>

            <el-tree
              :ref="(el: any) => registerTreeRef(tree.ultimateCode, el)"
              class="ch-tree"
              :data="tree.children"
              node-key="id"
              :props="treeProps"
              :filter-node-method="filterNodeMethod"
              :expand-on-click-node="false"
              default-expand-all
              draggable
              :allow-drag="allowDrag"
              :allow-drop="allowDrop"
              @node-click="onNodeClick"
              @node-drop="onNodeDrop"
              @node-contextmenu="onNodeContextMenu"
            >
              <template #default="{ data }">
                <span class="ch-node" :class="nodeClass(data)">
                  <span class="ch-node-name"><template v-for="(seg, i) in hlSegs(data.companyName || data.label)" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <span class="ch-node-code"><template v-for="(seg, i) in hlSegs(data.companyCode || '—')" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <el-tag
                    :type="statusType(data.status)"
                    size="small"
                    effect="light"
                    round
                  >{{ statusLabel(data.status) }}</el-tag>
                  <span v-if="formatShareholding(data.shareholding)" class="ch-share-badge">{{ formatShareholding(data.shareholding) }}</span>
                  <el-tag v-if="consolMethodLabel(data.consolMethod)" class="ch-method-tag" size="small" effect="plain" round>{{ consolMethodLabel(data.consolMethod) }}</el-tag>
                  <el-tag v-if="data.isDetached" type="warning" size="small" effect="plain" round>脱挂</el-tag>
                  <el-tag v-if="data.isCycleBreak" type="danger" size="small" effect="plain" round>循环引用</el-tag>
                </span>
              </template>
            </el-tree>
          </div>

          <!-- 独立节点分组 -->
          <div v-if="independents.length > 0" class="ch-tree-card ch-tree-card--indep">
            <div class="ch-tree-root ch-tree-root--indep">
              <div class="ch-tree-root-avatar ch-tree-root-avatar--indep">
                <el-icon :size="20"><Document /></el-icon>
              </div>
              <div class="ch-tree-root-info">
                <span class="ch-tree-root-name">独立节点</span>
                <span class="ch-tree-root-code">无最终控制方或缺企业代码</span>
              </div>
            </div>
            <el-tree
              :ref="(el: any) => registerTreeRef('__independent__', el)"
              class="ch-tree"
              :data="independents"
              node-key="id"
              :props="treeProps"
              :filter-node-method="filterNodeMethod"
              :expand-on-click-node="false"
              default-expand-all
              @node-click="onNodeClick"
            >
              <template #default="{ data }">
                <span class="ch-node">
                  <span class="ch-node-name"><template v-for="(seg, i) in hlSegs(data.companyName || data.label)" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <span class="ch-node-code"><template v-for="(seg, i) in hlSegs(data.companyCode || '—')" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <el-tag :type="statusType(data.status)" size="small" effect="light" round>
                    {{ statusLabel(data.status) }}
                  </el-tag>
                  <el-tag v-if="data.hasNoCompanyCode" type="info" size="small" effect="plain" round>缺代码</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </template>
      </template>
    </div>

    <!-- 合并范围差异明细弹窗 -->
    <el-dialog
      v-model="scopeDiffDialogVisible"
      title="合并范围差异明细"
      width="640px"
      class="ch-scope-diff-dialog"
      append-to-body
    >
      <div v-if="activeDiffTree" class="ch-diff-body">
        <p class="ch-diff-intro">
          以集团树形结构（企业代码）为权威源，与合并模块已配置的合并范围进行校对。
        </p>

        <!-- 待纳入：树形有、合并范围无 -->
        <div class="ch-diff-section">
          <div class="ch-diff-section-head">
            <el-tag type="warning" size="small" effect="light" round>待纳入</el-tag>
            <span class="ch-diff-section-desc">树形结构中存在、但合并范围中尚未配置（可一键同步）</span>
          </div>
          <el-table
            v-if="activeDiff.in_tree_not_scope.length > 0"
            :data="activeDiff.in_tree_not_scope"
            size="small"
            class="gt-compact-table"
          >
            <el-table-column prop="company_code" label="企业代码" min-width="200" />
            <el-table-column prop="company_name" label="企业名称" min-width="180">
              <template #default="{ row }">{{ row.company_name || '—' }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无待纳入企业" :image-size="60" />
        </div>

        <!-- 待移除：合并范围有、树形无 -->
        <div class="ch-diff-section">
          <div class="ch-diff-section-head">
            <el-tag type="info" size="small" effect="light" round>待移除</el-tag>
            <span class="ch-diff-section-desc">合并范围中存在、但树形结构中没有（需手动确认移除，系统不自动删除）</span>
          </div>
          <el-table
            v-if="activeDiff.in_scope_not_tree.length > 0"
            :data="activeDiff.in_scope_not_tree"
            size="small"
            class="gt-compact-table"
          >
            <el-table-column prop="company_code" label="企业代码" min-width="200" />
            <el-table-column prop="company_name" label="企业名称" min-width="180">
              <template #default="{ row }">{{ row.company_name || '—' }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无待移除企业" :image-size="60" />
        </div>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="ch-diff-tip"
        >
          <template #title>
            「一键同步到合并范围」仅会<strong>增量添加</strong>上方「待纳入」企业，不会删除「待移除」企业。移除合并范围请前往合并详情页手动确认。
          </template>
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="scopeDiffDialogVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="syncing"
          :disabled="!activeDiff.in_tree_not_scope.length"
          @click="confirmSyncScope"
        >一键同步到合并范围</el-button>
      </template>
    </el-dialog>

    <!-- 节点右键菜单（Task 16.1）—— 查看层级变更历史 -->
    <div
      v-if="contextMenu.visible"
      class="ch-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
    >
      <div class="ch-context-menu-item" @click="openHistoryDialog">
        <el-icon style="margin-right:6px"><Clock /></el-icon>查看层级变更历史
      </div>
    </div>

    <!-- 层级变更历史弹窗（Task 16.1）-->
    <el-dialog
      v-model="historyDialogVisible"
      :title="historyTitle"
      width="600px"
      class="ch-history-dialog"
      append-to-body
    >
      <div v-loading="historyLoading">
        <el-table
          v-if="historyEntries.length > 0"
          :data="historyEntries"
          size="small"
          class="gt-compact-table"
        >
          <el-table-column label="变更时间" min-width="170">
            <template #default="{ row }">{{ formatHistoryTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作人" min-width="120">
            <template #default="{ row }">{{ row.user_id || '—' }}</template>
          </el-table-column>
          <el-table-column label="原上级" min-width="120">
            <template #default="{ row }">{{ row.old || '（顶层）' }}</template>
          </el-table-column>
          <el-table-column label="新上级" min-width="120">
            <template #default="{ row }">{{ row.new || '（顶层）' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!historyLoading" description="暂无变更历史" :image-size="80" />
      </div>
      <template #footer>
        <el-button @click="historyDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Connection, OfficeBuilding, Plus, Refresh, Search, Document, Upload, Clock } from '@element-plus/icons-vue'
import { useGroupTree, highlightSegments, consolMethodLabel, formatShareholding, countConsolMethods, type TreeNode, type GroupTree } from '@/composables/useGroupTree'
import { api } from '@/services/apiProxy'
import BatchImportDialog from '@/components/wizard/BatchImportDialog.vue'

const router = useRouter()
const showBatchImport = ref(false)

const {
  trees,
  independents,
  loading,
  error,
  searchQuery,
  hasTrees,
  totalTreeNodes,
  hasSearchMatch,
  fetchTree,
  filterNode,
} = useGroupTree()

const treeProps = { label: 'label', children: 'children' }

// el-tree filter-node-method 适配（el-tree 传入 TreeNodeData，强转为我们的 TreeNode）
function filterNodeMethod(value: string, data: any): boolean {
  return filterNode(value, data as TreeNode)
}

// ─── el-tree refs（搜索过滤驱动，完整高亮见 Task 5.1）────────────────────────
const treeRefs = new Map<string, any>()
function registerTreeRef(key: string, el: any) {
  if (el) treeRefs.set(key, el)
  else treeRefs.delete(key)
}

// 搜索关键词变化 → 驱动各 el-tree 实例过滤
watch(searchQuery, (q) => {
  treeRefs.forEach((tree) => tree?.filter?.(q))
})

// ─── 统计概览 ────────────────────────────────────────────────────────────────
/** 递归展开森林所有节点 */
function flattenNodes(nodes: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = []
  for (const node of nodes) {
    out.push(node)
    if (node.children?.length) out.push(...flattenNodes(node.children))
  }
  return out
}

const allTreeNodes = computed(() => trees.value.flatMap((t) => flattenNodes(t.children || [])))

const hasAnyData = computed(() => hasTrees.value || independents.value.length > 0)

/** 合并项目数 = 含合并根项目的集团树数量 */
const consolidatedCount = computed(() => trees.value.filter((t) => t.rootProjectId).length)
/** 子公司数 = 森林成员节点总数 */
const subsidiaryCount = computed(() => totalTreeNodes.value)
const executingCount = computed(
  () => allTreeNodes.value.filter((n) => n.status === 'execution').length,
)
const completedCount = computed(
  () => allTreeNodes.value.filter((n) => n.status === 'completion').length,
)

// ─── 状态标签 ────────────────────────────────────────────────────────────────
function statusType(s: string | null): 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined {
  return ({
    created: 'info',
    planning: 'primary',
    execution: 'warning',
    completion: 'success',
    archived: 'info',
  } as Record<string, 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s || ''] || 'info'
}
function statusLabel(s: string | null) {
  return (
    ({
      created: '已创建',
      planning: '计划中',
      execution: '执行中',
      completion: '已完成',
      archived: '已归档',
    } as Record<string, string>)[s || ''] || s || '未知'
  )
}

function nodeClass(data: TreeNode) {
  return {
    'ch-node--detached': data.isDetached,
    'ch-node--cycle': data.isCycleBreak,
  }
}

// ─── 搜索高亮分段（企业名称 + 代码，大小写不敏感）─────────────────────────────
function hlSegs(text: string | null | undefined) {
  return highlightSegments(text, searchQuery.value)
}

// ─── 合并方式统计（Task 14.2）——统计该集团树全部节点的合并方式分布 ──────────────
function methodCounts(tree: GroupTree) {
  return countConsolMethods(tree.children || [])
}

// ─── 导航 ────────────────────────────────────────────────────────────────────
function goConsolidation(projectId: string | null) {
  if (projectId) router.push(`/projects/${projectId}/consolidation`)
}
function onNodeClick(data: TreeNode) {
  if (data?.id) router.push(`/projects/${data.id}/consolidation`)
}

// ─── 加载 ────────────────────────────────────────────────────────────────────
function reload() {
  fetchTree('consolidated').then(loadAllScopeDiffs)
}

onMounted(() => {
  fetchTree('consolidated').then(loadAllScopeDiffs)
})

// ─── Task 15: 树形拖拽调整层级 ────────────────────────────────────────────────
//
// allow-drop 语义决策：只允许 'inner'（拖入目标节点 → 目标成为新上级），
// 'prev'/'next'（同级重排序）一律禁止——重排序不改变父子层级，对"调整上级企业代码"
// 无意义，且会引入"释放到根 / 释放到目标 parent"的歧义。因此 onNodeDrop 只处理 inner。
//
// el-tree 的 draggable 天然限制在同一 <el-tree> 实例内拖拽，每棵集团树是独立 el-tree
// 实例 → 跨 ultimate 树拖拽天然被阻止；allow-drag 进一步禁止拖动 ultimate 根节点本身。

/** 收集一个节点的全部后代 id（含自身），用于禁循环判定 */
function collectNodeIds(node: TreeNode, acc: Set<string>): void {
  if (!node) return
  acc.add(node.id)
  for (const child of node.children || []) collectNodeIds(child, acc)
}

/**
 * allow-drag：禁止拖动最终控制方根节点本身（companyCode === 所属树的 ultimateCode），
 * 仅子公司可被重新挂接。其余节点可拖。
 */
function allowDrag(draggingNode: any): boolean {
  const data = draggingNode?.data as TreeNode | undefined
  if (!data) return false
  // 找到该节点所属的集团树，根节点（companyCode === ultimateCode）不可拖
  const owningTree = trees.value.find((t) =>
    (t.children || []).some((n) => containsNode(n, data.id)),
  )
  if (owningTree && data.companyCode && data.companyCode === owningTree.ultimateCode) {
    return false
  }
  return true
}

/** 递归判断 node 子树中是否含 targetId */
function containsNode(node: TreeNode, targetId: string): boolean {
  if (node.id === targetId) return true
  return (node.children || []).some((c) => containsNode(c, targetId))
}

/**
 * allow-drop：仅允许 'inner'（成为子节点）；禁止拖到自身或自身后代下（防循环）。
 */
function allowDrop(draggingNode: any, dropNode: any, type: 'prev' | 'inner' | 'next'): boolean {
  if (type !== 'inner') return false
  const dragData = draggingNode?.data as TreeNode | undefined
  const dropData = dropNode?.data as TreeNode | undefined
  if (!dragData || !dropData) return false
  // 不能拖到自己身上
  if (dragData.id === dropData.id) return false
  // 不能拖到自己的后代下（防循环）
  const descendants = new Set<string>()
  collectNodeIds(dragData, descendants)
  if (descendants.has(dropData.id)) return false
  return true
}

/**
 * node-drop：拖拽释放后弹确认 → 调 PATCH 更新 parent_company_code。
 * @param draggingNode 被拖动节点
 * @param dropNode 目标节点
 * @param dropType 放置类型（已由 allow-drop 限定为 inner）
 */
async function onNodeDrop(
  draggingNode: any,
  dropNode: any,
  dropType: 'before' | 'after' | 'inner',
) {
  const dragData = draggingNode?.data as TreeNode | undefined
  const dropData = dropNode?.data as TreeNode | undefined
  if (!dragData || !dropData || dropType !== 'inner') {
    // 非预期类型 → 重建树恢复原位
    reload()
    return
  }

  const childName = dragData.companyName || dragData.label || '该企业'
  const newParentName = dropData.companyName || dropData.label || '目标企业'
  const newParentCode = dropData.companyCode || null

  // Task 15.3：拖拽操作确认弹窗
  try {
    await ElMessageBox.confirm(
      `将「${childName}」的上级调整为「${newParentName}」，是否确认？`,
      '确认调整层级',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    // 用户取消 → 重建树恢复原位（el-tree 已在视图上移动了节点）
    reload()
    return
  }

  try {
    await api.patch(`/api/projects/${dragData.id}/parent-code`, {
      parent_company_code: newParentCode,
    })
    ElMessage.success('层级调整成功')
    reload()
  } catch (e: any) {
    // 400（循环引用等）→ 显示后端 detail；其余 → 通用错误。无论如何重建树恢复
    ElMessage.error(e?.message || '层级调整失败')
    reload()
  }
}

// ─── Task 16.1: 节点右键菜单 + 层级变更历史 ───────────────────────────────────

interface ParentCodeHistoryEntry {
  user_id: string | null
  created_at: string | null
  old: string | null
  new: string | null
}

const contextMenu = ref<{ visible: boolean; x: number; y: number; node: TreeNode | null }>({
  visible: false,
  x: 0,
  y: 0,
  node: null,
})

const historyDialogVisible = ref(false)
const historyLoading = ref(false)
const historyEntries = ref<ParentCodeHistoryEntry[]>([])
const historyNodeName = ref('')

const historyTitle = computed(() =>
  historyNodeName.value ? `层级变更历史 — ${historyNodeName.value}` : '层级变更历史',
)

/** 右键节点 → 在光标位置显示上下文菜单 */
function onNodeContextMenu(ev: Event, data: TreeNode) {
  const me = ev as MouseEvent
  me.preventDefault()
  contextMenu.value = { visible: true, x: me.clientX, y: me.clientY, node: data }
}

/** 点击菜单"查看层级变更历史" → 关闭菜单、打开弹窗、拉取历史 */
async function openHistoryDialog() {
  const node = contextMenu.value.node
  contextMenu.value.visible = false
  if (!node) return
  historyNodeName.value = node.companyName || node.label || ''
  historyEntries.value = []
  historyDialogVisible.value = true
  historyLoading.value = true
  try {
    const data = await api.get<ParentCodeHistoryEntry[]>(
      `/api/projects/${node.id}/parent-code-history`,
    )
    historyEntries.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载变更历史失败')
    historyEntries.value = []
  } finally {
    historyLoading.value = false
  }
}

/** 格式化历史时间（ISO → 本地可读） */
function formatHistoryTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 点击页面任意处关闭右键菜单 */
function hideContextMenu() {
  if (contextMenu.value.visible) contextMenu.value.visible = false
}

onMounted(() => {
  window.addEventListener('click', hideContextMenu)
})
onUnmounted(() => {
  window.removeEventListener('click', hideContextMenu)
})

// ─── 合并范围校对（Req 9.2~9.5）────────────────────────────────────────────────

/** scope-diff 响应结构（后端 ScopeDiffResponse） */
interface ScopeDiffEntry {
  company_code: string
  company_name: string | null
}
interface ScopeDiff {
  in_tree_not_scope: ScopeDiffEntry[]
  in_scope_not_tree: ScopeDiffEntry[]
}

const EMPTY_DIFF: ScopeDiff = { in_tree_not_scope: [], in_scope_not_tree: [] }

/** 按 rootProjectId 存放差异结果（不污染 composable 数据） */
const scopeDiffMap = ref<Record<string, ScopeDiff>>({})

const scopeDiffDialogVisible = ref(false)
const activeDiffTree = ref<GroupTree | null>(null)
const syncing = ref(false)

/** 拉取单个合并项目的范围差异（失败静默降级，不抛出、不阻塞树形）。Req 9.5 */
async function loadScopeDiff(projectId: string): Promise<void> {
  try {
    const data = await api.get<ScopeDiff>(`/api/consolidation/${projectId}/scope-diff`)
    scopeDiffMap.value = {
      ...scopeDiffMap.value,
      [projectId]: {
        in_tree_not_scope: Array.isArray(data?.in_tree_not_scope) ? data.in_tree_not_scope : [],
        in_scope_not_tree: Array.isArray(data?.in_scope_not_tree) ? data.in_scope_not_tree : [],
      },
    }
  } catch {
    /* Req 9.5：差异查询失败静默降级——不显示警示标签、不阻塞树形展示 */
  }
}

/** 树形渲染完成后，并行为每棵有合并根项目的树查询范围差异 */
async function loadAllScopeDiffs(): Promise<void> {
  scopeDiffMap.value = {}
  const ids = trees.value.map((t) => t.rootProjectId).filter((id): id is string => !!id)
  if (ids.length === 0) return
  await Promise.allSettled(ids.map((id) => loadScopeDiff(id)))
}

/** 该集团树是否存在合并范围差异（任一方向有条目即视为有差异） */
function hasScopeDiff(tree: GroupTree): boolean {
  if (!tree.rootProjectId) return false
  const diff = scopeDiffMap.value[tree.rootProjectId]
  if (!diff) return false
  return diff.in_tree_not_scope.length > 0 || diff.in_scope_not_tree.length > 0
}

/** 当前弹窗展示的差异（无则返回空差异，避免模板空引用） */
const activeDiff = computed<ScopeDiff>(() => {
  const pid = activeDiffTree.value?.rootProjectId
  if (!pid) return EMPTY_DIFF
  return scopeDiffMap.value[pid] || EMPTY_DIFF
})

/** 点击警示标签 → 打开差异明细弹窗 */
function openScopeDiffDialog(tree: GroupTree) {
  activeDiffTree.value = tree
  scopeDiffDialogVisible.value = true
}

/** 一键同步到合并范围（仅增量添加待纳入企业，用户确认后执行）。Req 9.4 */
async function confirmSyncScope() {
  const tree = activeDiffTree.value
  const pid = tree?.rootProjectId
  if (!pid) return

  const codes = activeDiff.value.in_tree_not_scope.map((e) => e.company_code).filter(Boolean)
  if (codes.length === 0) {
    ElMessage.info('没有需要同步的企业')
    return
  }

  try {
    await ElMessageBox.confirm(
      `将把 ${codes.length} 家「待纳入」企业增量添加到「${tree?.ultimateName || '该集团'}」的合并范围，不会删除已有配置。是否继续？`,
      '确认同步合并范围',
      { confirmButtonText: '确认同步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }

  syncing.value = true
  try {
    const res = await api.post<{ added: number }>(
      `/api/consolidation/${pid}/sync-scope`,
      { company_codes: codes },
    )
    ElMessage.success(`已同步 ${res?.added ?? 0} 家企业`)
    // 重新查询该项目差异以刷新警示标签
    await loadScopeDiff(pid)
    // 若差异已消除则关闭弹窗
    if (!hasScopeDiff(tree as GroupTree)) {
      scopeDiffDialogVisible.value = false
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '同步合并范围失败')
  } finally {
    syncing.value = false
  }
}
</script>

<style scoped>
.ch-page { padding: 0; }

/* ── 横幅 ── */
.ch-banner {
  position: relative; padding: 32px 32px 24px; overflow: hidden;
  border-radius: 0 0 16px 16px;
}
.ch-banner-bg {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, #4b2d77 0%, #7c5caa 50%, #a78bcc 100%);
  opacity: 0.95;
}
.ch-banner-content {
  position: relative; z-index: 1; display: flex; align-items: center; gap: 20px;
}
.ch-banner-action {
  margin-left: auto; flex-shrink: 0;
  background: rgba(255,255,255,0.15); border-color: rgba(255,255,255,0.4);
  color: var(--gt-color-text-inverse);
}
.ch-banner-action:hover {
  background: rgba(255,255,255,0.28); border-color: rgba(255,255,255,0.6);
  color: var(--gt-color-text-inverse);
}
.ch-banner-icon {
  width: 64px; height: 64px; border-radius: 16px;
  background: rgba(255,255,255,0.15); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; color: var(--gt-color-text-inverse);
  flex-shrink: 0;
}
.ch-banner-title { margin: 0; font-size: 24px /* allow-px: special */; font-weight: 700; color: var(--gt-color-text-inverse); }
.ch-banner-desc { margin: 6px 0 0; font-size: var(--gt-font-size-sm); color: rgba(255,255,255,0.8); }

/* ── 统计 ── */
.ch-stats {
  display: flex; gap: 0; margin: -20px 32px 0; position: relative; z-index: 2;
  background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(75,45,119,0.08);
  overflow: hidden;
}
.ch-stat-item {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  padding: 16px 12px; border-right: 1px solid var(--gt-color-border-purple);
}
.ch-stat-item:last-child { border-right: none; }
.ch-stat-num { font-size: var(--gt-font-size-3xl); font-weight: 700; color: var(--gt-color-primary); line-height: 1.2; }
.ch-stat-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; }

/* ── 主体 ── */
.ch-body { padding: 24px 32px 32px; }

/* ── 工具栏 ── */
.ch-toolbar { margin-bottom: 16px; display: flex; }
.ch-search { max-width: 320px; }

/* ── 集团树卡片 ── */
.ch-tree-card {
  background: var(--gt-color-bg-white); border-radius: 12px; overflow: hidden;
  border: 1px solid var(--gt-color-border-purple); margin-bottom: 18px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}

/* 根节点（最终控制方） */
.ch-tree-root {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px;
  background: var(--gt-color-primary-bg);
  border-bottom: 1px solid var(--gt-color-border-purple);
}
.ch-tree-root--clickable { cursor: pointer; transition: background 0.15s; }
.ch-tree-root--clickable:hover { background: var(--gt-color-border-purple); }
.ch-tree-root-avatar {
  width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, #4b2d77, #7c5caa);
  display: flex; align-items: center; justify-content: center;
  color: var(--gt-color-text-inverse);
}
.ch-tree-root-avatar--indep { background: linear-gradient(135deg, #909399, #c0c4cc); }
.ch-tree-root-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.ch-tree-root-name { font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text); }
.ch-tree-root-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); font-family: var(--gt-font-mono, monospace); }
.ch-tree-root--indep { background: var(--gt-color-fill-light, #f5f5f5); }

/* 树 */
.ch-tree { padding: 8px 12px 12px; }

/* 节点内容 */
.ch-node {
  display: inline-flex; align-items: center; gap: 10px;
  font-size: var(--gt-font-size-sm);
}
.ch-node-name { color: var(--gt-color-text); font-weight: 500; }
.ch-node-code {
  color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);
  font-family: var(--gt-font-mono, monospace);
}
.ch-node--detached .ch-node-name { color: var(--gt-color-warning, #e6a23c); }
.ch-node--cycle .ch-node-name { color: var(--gt-color-danger, #f56c6c); }

/* 搜索匹配高亮：琥珀黄底深色字（行 hover 时底色为紫，黄色高亮仍清晰可辨；
   既满足禁用 Element 蓝，又保证 hover 态对比度，符合无障碍） */
.gt-hl {
  background: #ffe9a8;
  color: #5a3d00;
  font-weight: 700;
  border-radius: 2px;
  padding: 0 1px;
}

/* 持股比例 badge（紫色，Task 14.1）—— 禁用 Element 默认蓝 */
.ch-share-badge {
  display: inline-flex; align-items: center;
  height: 20px; padding: 0 7px;
  font-size: var(--gt-font-size-xs); font-weight: 600; line-height: 1;
  color: var(--gt-color-text-inverse);
  background: linear-gradient(135deg, #4b2d77, #7c5caa);
  border-radius: 10px;
  font-family: var(--gt-font-mono, monospace);
}

/* 合并方式 tag（浅紫描边，Task 14.1） */
.ch-method-tag.el-tag {
  --el-tag-text-color: var(--gt-color-primary);
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple);
  color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple);
}

/* 合并方式统计（Task 14.2，根节点下方）*/
.ch-method-stats {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 8px 18px;
  background: var(--gt-color-primary-bg);
  border-bottom: 1px solid var(--gt-color-border-purple);
}
.ch-method-stat {
  display: inline-flex; align-items: center;
  height: 22px; padding: 0 10px;
  font-size: var(--gt-font-size-xs); font-weight: 500; line-height: 1;
  border-radius: 11px;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-purple);
  color: var(--gt-color-primary);
}
.ch-method-stat--full { color: #4b2d77; border-color: #d8b8ee; }
.ch-method-stat--equity { color: #7c5caa; border-color: #d8b8ee; }
.ch-method-stat--prop { color: #a78bcc; border-color: #d8b8ee; }

/* el-tag primary 紫色覆盖（禁用 Element 默认蓝 #409eff） */
:deep(.el-tag--primary) {
  --el-tag-text-color: var(--gt-color-primary);
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple);
  color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple);
}

/* el-tree hover 用紫色而非默认蓝 */
:deep(.el-tree-node__content:hover) { background-color: var(--gt-color-primary-bg); }
:deep(.el-tree-node:focus > .el-tree-node__content) { background-color: var(--gt-color-primary-bg); }

/* 合并范围差异警示标签可点击 */
.ch-scope-diff-tag { cursor: pointer; transition: opacity 0.15s; }
.ch-scope-diff-tag:hover { opacity: 0.8; }

/* ── 差异明细弹窗 ── */
.ch-diff-intro {
  margin: 0 0 16px; font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-tertiary); line-height: 1.6;
}
.ch-diff-section { margin-bottom: 18px; }
.ch-diff-section-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.ch-diff-section-desc { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.ch-diff-tip { margin-top: 4px; }

/* 右键上下文菜单（Task 16.1）—— 紫色描边浮层 */
.ch-context-menu {
  position: fixed;
  z-index: 3000;
  min-width: 168px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-purple);
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(75, 45, 119, 0.18);
  padding: 4px;
  overflow: hidden;
}
.ch-context-menu-item {
  display: flex; align-items: center;
  padding: 8px 12px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.ch-context-menu-item:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .ch-banner { padding: 20px 16px 16px; }
  .ch-stats { margin: -16px 16px 0; }
  .ch-body { padding: 16px; }
  .ch-search { max-width: none; }
}
</style>
