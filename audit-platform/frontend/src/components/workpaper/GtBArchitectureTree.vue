<!--
  GtBArchitectureTree.vue — B 类目录的底稿架构树

  按 design §11.9 实现：
  - el-tree 展示底稿层级结构
  - 每个节点使用 GtIndexChip 显示索引号
  - 节点状态标签（完成/进行中/待执行）
  - 点击节点跳转到对应底稿

  锚定 spec workpaper-editor-slimdown Task 17.8
  Validates: US-16（程序表流程导航图 — B 类架构树）
-->

<template>
  <div class="gt-b-architecture-tree" v-show="expanded">
    <el-tree
      v-if="treeData.length > 0"
      :data="treeData"
      :props="treeProps"
      default-expand-all
      :expand-on-click-node="false"
      node-key="id"
      @node-click="onNodeClick"
    >
      <template #default="{ data }">
        <span class="gt-b-tree-node">
          <GtIndexChip
            :value="data.wpCode"
            :validate="false"
            class="gt-b-tree-node__chip"
          />
          <span class="gt-b-tree-node__name">{{ data.name }}</span>
          <el-tag
            v-if="data.status"
            :type="statusType(data.status)"
            size="small"
            effect="plain"
          >
            {{ statusLabel(data.status) }}
          </el-tag>
        </span>
      </template>
    </el-tree>

    <el-empty
      v-else
      description="暂无底稿架构数据"
      :image-size="60"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  expanded: boolean
  htmlData?: Record<string, any>
}>()

// ─── Types ───
interface TreeNode {
  id: string
  wpCode: string
  name: string
  status?: string
  children?: TreeNode[]
}

// ─── State ───
const router = useRouter()
const treeData = ref<TreeNode[]>([])
const treeProps = {
  label: 'name',
  children: 'children',
}

// ─── Methods ───
function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'pending': return 'info'
    case 'not_applicable': return 'danger'
    default: return 'info'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'pending': return '待执行'
    case 'not_applicable': return '已裁剪'
    default: return status
  }
}

function onNodeClick(data: TreeNode) {
  if (data.wpCode) {
    router.push({
      path: `/projects/${props.projectId}/workpapers/${data.wpCode}/edit`,
    })
  }
}

function buildTreeFromHtmlData() {
  if (!props.htmlData) {
    treeData.value = []
    return
  }

  // 从 B 类底稿的 navigation rows 构建树
  const nodes: TreeNode[] = []

  // 遍历所有 sheet 的 html_data 寻找导航行
  for (const [sheetName, sheetData] of Object.entries(props.htmlData)) {
    if (!sheetData || typeof sheetData !== 'object') continue
    const navRows = (sheetData as any).navigation_rows || (sheetData as any).rows || []

    if (Array.isArray(navRows)) {
      for (const row of navRows) {
        if (!row || typeof row !== 'object') continue
        const wpCode = row.wp_code || row.index_ref || ''
        const name = row.wp_name || row.description || row.label || wpCode
        const status = row.status || ''

        if (wpCode) {
          nodes.push({
            id: `${sheetName}-${wpCode}`,
            wpCode,
            name,
            status,
          })
        }
      }
    }
  }

  // 按 wpCode 前缀分组构建层级
  treeData.value = buildHierarchy(nodes)
}

function buildHierarchy(nodes: TreeNode[]): TreeNode[] {
  if (nodes.length === 0) return []

  // 简单分组：按 wpCode 的第一个字母+数字分组
  const groups: Record<string, TreeNode[]> = {}

  for (const node of nodes) {
    // 提取前缀如 "D2" from "D2-1", "D2A" etc.
    const match = node.wpCode.match(/^([A-Z]\d+)/i)
    const prefix = match ? match[1] : 'other'

    if (!groups[prefix]) {
      groups[prefix] = []
    }
    groups[prefix].push(node)
  }

  // 如果只有一个组或节点少于 10 个，直接返回扁平列表
  if (Object.keys(groups).length <= 1 || nodes.length < 10) {
    return nodes
  }

  // 构建分组树
  return Object.entries(groups).map(([prefix, children]) => ({
    id: `group-${prefix}`,
    wpCode: prefix,
    name: `${prefix} 系列`,
    children,
  }))
}

// ─── Lifecycle ───
onMounted(() => {
  if (props.expanded) {
    buildTreeFromHtmlData()
  }
})

watch(() => props.expanded, (val) => {
  if (val) {
    buildTreeFromHtmlData()
  }
})

watch(() => props.htmlData, () => {
  if (props.expanded) {
    buildTreeFromHtmlData()
  }
}, { deep: true })
</script>

<style scoped>
.gt-b-architecture-tree {
  padding: 12px 16px;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  margin-bottom: 12px;
}

.gt-b-tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 13px;
}

.gt-b-tree-node__chip {
  flex-shrink: 0;
}

.gt-b-tree-node__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-regular);
}
</style>
