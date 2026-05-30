<template>
  <el-drawer
    v-model="visible"
    title="数据溯源"
    direction="rtl"
    size="520px"
    :destroy-on-close="true"
  >
    <div v-loading="loading" class="lineage-graph-panel">
      <!-- 当前节点 -->
      <div v-if="lineageData" class="lineage-section">
        <div class="section-title">当前对象</div>
        <div class="lineage-node current-node" @click="handleNodeClick(lineageData.current)">
          <el-icon><Location /></el-icon>
          <span class="node-label">{{ lineageData.current?.wp_code || '未知' }}</span>
          <span v-if="lineageData.current?.cell_ref" class="node-ref">
            {{ lineageData.current.cell_ref }}
          </span>
        </div>
      </div>

      <!-- 上游节点 -->
      <div v-if="lineageData?.upstream?.length" class="lineage-section">
        <div class="section-title">
          <el-icon><Top /></el-icon>
          上游来源（{{ lineageData.upstream.length }}）
        </div>
        <div
          v-for="(node, idx) in lineageData.upstream"
          :key="'up-' + idx"
          class="lineage-node upstream-node"
          @click="handleNodeClick(node)"
        >
          <el-icon><Document /></el-icon>
          <span class="node-label">{{ node.wp_code }}</span>
          <span v-if="node.sheet_name" class="node-sheet">{{ node.sheet_name }}</span>
          <span v-if="node.cell_ref" class="node-ref">{{ node.cell_ref }}</span>
          <span v-if="node.label" class="node-desc">{{ node.label }}</span>
        </div>
      </div>

      <!-- 下游节点 -->
      <div v-if="lineageData?.downstream?.length" class="lineage-section">
        <div class="section-title">
          <el-icon><Bottom /></el-icon>
          下游影响（{{ lineageData.downstream.length }}）
        </div>
        <div
          v-for="(node, idx) in lineageData.downstream"
          :key="'down-' + idx"
          class="lineage-node downstream-node"
          @click="handleNodeClick(node)"
        >
          <el-icon><Document /></el-icon>
          <span class="node-label">{{ node.wp_code }}</span>
          <span v-if="node.sheet_name" class="node-sheet">{{ node.sheet_name }}</span>
          <span v-if="node.cell_ref" class="node-ref">{{ node.cell_ref }}</span>
          <span v-if="node.label" class="node-desc">{{ node.label }}</span>
        </div>
      </div>

      <!-- 关联附件 -->
      <div v-if="lineageData?.attachments?.length" class="lineage-section">
        <div class="section-title">
          <el-icon><Paperclip /></el-icon>
          关联附件（{{ lineageData.attachments.length }}）
        </div>
        <div
          v-for="(att, idx) in lineageData.attachments"
          :key="'att-' + idx"
          class="lineage-node attachment-node"
          @click="handleAttachmentClick(att)"
        >
          <el-icon><Document /></el-icon>
          <span class="node-label">{{ att.file_name || '未命名附件' }}</span>
          <el-tag size="small" type="info">{{ att.file_type || '文件' }}</el-tag>
        </div>
      </div>

      <!-- 空状态 -->
      <el-empty
        v-if="!loading && lineageData && !lineageData.upstream?.length && !lineageData.downstream?.length && !lineageData.attachments?.length"
        description="暂无溯源数据"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Location, Top, Bottom, Document, Paperclip } from '@element-plus/icons-vue'
import { useCellLocate, type LocateTarget } from '@/composables/useCellLocate'
import { apiProxy } from '@/utils/apiProxy'

interface LineageNode {
  wp_code: string
  wp_id?: string | null
  sheet_name?: string | null
  cell_ref?: string | null
  component_type?: string | null
  value?: string | null
  label?: string | null
}

interface AttachmentRef {
  id: string
  attachment_id: string
  target_type: string
  target_ref?: string | null
  file_name?: string | null
  file_type?: string | null
  created_at?: string | null
}

interface LineageData {
  current: LineageNode
  upstream: LineageNode[]
  downstream: LineageNode[]
  attachments: AttachmentRef[]
}

const props = defineProps<{
  modelValue: boolean
  objectType: string
  objectId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'preview-attachment': [attachment: AttachmentRef]
}>()

const visible = ref(props.modelValue)
const loading = ref(false)
const lineageData = ref<LineageData | null>(null)

const route = useRoute()
const { locateCell } = useCellLocate()

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    fetchLineage()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

async function fetchLineage() {
  const projectId = route.params.projectId as string
  if (!projectId || !props.objectId) return

  loading.value = true
  try {
    const data = await apiProxy.get(
      `/api/projects/${projectId}/lineage`,
      {
        params: {
          object_type: props.objectType,
          object_id: props.objectId,
          direction: 'both',
        },
      }
    )
    lineageData.value = data as LineageData
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '溯源查询失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}

function handleNodeClick(node: LineageNode) {
  if (!node?.wp_code) return

  const target: LocateTarget = {
    wp_code: node.wp_code,
    wp_id: node.wp_id ?? undefined,
    sheet_name: node.sheet_name ?? undefined,
    cell_ref: node.cell_ref ?? undefined,
    component_type: node.component_type ?? undefined,
    value: node.value ?? undefined,
    label: node.label ?? undefined,
  }

  const success = locateCell(target)
  if (!success) {
    ElMessage.info(`定位到 ${node.wp_code}${node.cell_ref ? ' ' + node.cell_ref : ''}`)
  }
}

function handleAttachmentClick(att: AttachmentRef) {
  emit('preview-attachment', att)
}
</script>

<style scoped>
.lineage-graph-panel {
  padding: 0 8px;
}

.lineage-section {
  margin-bottom: 20px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.lineage-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
  border: 1px solid var(--el-border-color-lighter);
}

.lineage-node:hover {
  background-color: var(--el-fill-color-light);
}

.current-node {
  border-left: 3px solid var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.upstream-node {
  border-left: 3px solid var(--el-color-success);
}

.downstream-node {
  border-left: 3px solid var(--el-color-warning);
}

.attachment-node {
  border-left: 3px solid var(--el-color-info);
}

.node-label {
  font-weight: 500;
  font-size: 13px;
}

.node-sheet {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.node-ref {
  font-size: 12px;
  color: var(--el-color-primary);
  font-family: monospace;
}

.node-desc {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-left: auto;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
