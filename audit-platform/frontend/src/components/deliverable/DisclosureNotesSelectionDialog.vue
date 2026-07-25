<template>
  <el-dialog
    :model-value="visible"
    title="选择要生成的附注章节"
    width="600px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
    @open="onOpen"
  >
    <!-- 加载中 -->
    <div v-if="loading" class="dnsd-state" v-loading="true" element-loading-text="正在加载附注树…">
      <div style="height: 120px" />
    </div>

    <!-- 404：附注未生成 -->
    <el-empty
      v-else-if="loadError === 'not_found'"
      description="附注数据不存在，请先生成附注"
      :image-size="80"
    />

    <!-- 其他失败：重试 -->
    <div v-else-if="loadError === 'failed'" class="dnsd-state">
      <el-alert type="error" :closable="false" title="附注树加载失败" show-icon />
      <div style="margin-top: 12px; text-align: center">
        <el-button size="small" type="primary" @click="loadTree">重试</el-button>
      </div>
    </div>

    <!-- 正常：分组树 -->
    <template v-else>
      <div class="dnsd-toolbar">
        <el-button size="small" type="primary" plain @click="applyPreset">
          一键预设生成（只勾有数据）
        </el-button>
        <span class="dnsd-count">已选 {{ selectedSections.length }} 个章节</span>
      </div>
      <el-tree
        ref="treeRef"
        :data="grouped"
        show-checkbox
        node-key="key"
        :default-expand-all="true"
        :props="{ label: 'label', children: 'children' }"
        :check-strictly="false"
        @check="onCheck"
      >
        <template #default="{ data }">
          <span class="dnsd-node" :class="{ 'dnsd-node--empty': !data.isGroup && !data.has_data }">
            {{ data.label }}
            <el-tag
              v-if="!data.isGroup && !data.has_data"
              size="small"
              type="info"
              effect="plain"
              class="dnsd-tag"
              >无数据</el-tag
            >
          </span>
        </template>
      </el-tree>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!canConfirm"
        @click="onConfirm"
      >
        确认生成
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { disclosureNotes } from '@/services/apiPaths/report'
import {
  buildGroupedTree,
  computePresetKeys,
  deriveSelectedSections,
  type NotesTreeNode,
  type TreeGroup,
} from './disclosureNotesSelection'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
  /** 外部生成中态（DeliverableCenter.generating）—— 确认按钮 loading */
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
  confirm: [payload: { selectedSections: string[] }]
}>()

const treeRef = ref()
const nodes = ref<NotesTreeNode[]>([])
const grouped = ref<TreeGroup[]>([])
const loading = ref(false)
const loadError = ref<'none' | 'not_found' | 'failed'>('none')
const selectedSections = ref<string[]>([])

const submitting = computed(() => props.submitting === true)
const canConfirm = computed(
  () => loadError.value === 'none' && !loading.value && selectedSections.value.length > 0,
)

function onOpen() {
  loadTree()
}

async function loadTree() {
  loading.value = true
  loadError.value = 'none'
  nodes.value = []
  grouped.value = []
  selectedSections.value = []
  try {
    const data = await api.get<NotesTreeNode[]>(
      disclosureNotes.tree(props.projectId, props.year),
      { _silent: true } as any,
    )
    nodes.value = Array.isArray(data) ? data : []
    grouped.value = buildGroupedTree(nodes.value)
  } catch (e: any) {
    const status = e?.response?.status
    loadError.value = status === 404 ? 'not_found' : 'failed'
  } finally {
    loading.value = false
  }
}

/** 一键预设：勾选 has_data=true 的叶子（预设不锁定，之后可自由增删） */
function applyPreset() {
  const keys = computePresetKeys(nodes.value)
  treeRef.value?.setCheckedKeys(keys, false)
  refreshSelected()
}

/** el-tree 勾选变化 → 实时更新最终勾选集 */
function onCheck() {
  refreshSelected()
}

function refreshSelected() {
  const checked: string[] = treeRef.value?.getCheckedKeys(true) ?? []
  selectedSections.value = deriveSelectedSections(checked)
}

function onConfirm() {
  // 空选守卫（按钮已 disabled，此处再兜底，完全阻止提交）
  if (!selectedSections.value.length) {
    ElMessage.warning('请至少选择一个章节')
    return
  }
  emit('confirm', { selectedSections: selectedSections.value })
}
</script>

<style scoped>
.dnsd-state {
  min-height: 120px;
}
.dnsd-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.dnsd-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.dnsd-node {
  font-size: 13px;
}
.dnsd-node--empty {
  color: var(--el-text-color-secondary);
}
.dnsd-tag {
  margin-left: 6px;
}
:deep(.el-tree-node__content) {
  height: 30px;
}
</style>
