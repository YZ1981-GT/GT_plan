<template>
  <div v-if="matchedConfigs.length" class="gt-cycle-dialog-slot">
    <!-- Trigger buttons for each matched dialog config -->
    <el-button
      v-for="config in matchedConfigs"
      :key="config.id"
      :type="config.triggerType === 'default' ? '' : config.triggerType"
      size="small"
      @click="openDialog(config)"
    >
      <span class="gt-cycle-dialog-slot__icon">{{ config.triggerIcon }}</span>
      {{ config.triggerLabel }}
    </el-button>

    <!-- Dynamically loaded dialog -->
    <component
      v-if="activeDialog"
      :is="activeDialog"
      :visible="dialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :wp-code="wpDetail.wp_code"
      :active-sheet-id="activeSheetId"
      @update:visible="onDialogVisibleChange"
      @saved="onChildSaved"
      @applied="onChildSaved"
    />

    <!-- Loading overlay while dialog component loads -->
    <el-dialog
      v-model="loadingVisible"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      width="300px"
      align-center
    >
      <div class="gt-cycle-dialog-slot__loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * CycleDialogSlot — 配置驱动的循环 Dialog 插槽组件
 *
 * 根据 wpDetail.wp_code 从 cycleDialogRegistry 匹配对应的 dialog 配置，
 * 渲染 trigger 按钮，点击后异步加载 dialog 组件并传入标准 props。
 *
 * 替代 WorkpaperEditor.vue 中 12 个 trigger div + 15 个 dialog 实例。
 * 锚定 spec workpaper-editor-slimdown Sprint 2 Task 3.2
 */
import { computed, ref, shallowRef, type Component } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { getMatchedDialogs, type CycleDialogConfig } from '@/config/cycleDialogRegistry'

interface WorkpaperDetail {
  wp_code: string
  [key: string]: any
}

interface Props {
  wpDetail: WorkpaperDetail
  projectId: string
  wpId: string
  activeSheetId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'child-saved': []
}>()

// 1. Compute matched configs based on wp_code
const matchedConfigs = computed<CycleDialogConfig[]>(() => {
  if (!props.wpDetail?.wp_code) return []
  return getMatchedDialogs(props.wpDetail.wp_code)
})

// 2. Dialog state management
const activeDialog = shallowRef<Component | null>(null)
const dialogVisible = ref(false)
const loadingVisible = ref(false)

// 3. Open dialog: async load component then show
async function openDialog(config: CycleDialogConfig) {
  // If requiresSheet and no activeSheetId, skip
  if (config.requiresSheet && !props.activeSheetId) return

  loadingVisible.value = true
  try {
    const module = await config.component()
    // Handle both default export and module with .default
    activeDialog.value = module.default || module
    loadingVisible.value = false
    dialogVisible.value = true
  } catch (err) {
    loadingVisible.value = false
    console.error(`[CycleDialogSlot] Failed to load dialog: ${config.id}`, err)
  }
}

// 4. Dialog visibility change handler
function onDialogVisibleChange(v: boolean) {
  dialogVisible.value = v
  if (!v) {
    // Clean up after dialog closes
    activeDialog.value = null
  }
}

// 5. Child dialog saved/applied → emit upward
function onChildSaved() {
  emit('child-saved')
}
</script>

<style scoped>
.gt-cycle-dialog-slot {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-cycle-dialog-slot__icon {
  margin-right: 4px;
}

.gt-cycle-dialog-slot__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 0;
  color: var(--el-text-color-secondary);
}
</style>
