<script setup lang="ts">
/**
 * GtB60DocxPane — B60 子底稿双模式承载壳
 *
 * 统一封装「结构化视图 / 在线编辑」双模式：
 * - 切到在线编辑前先 GET onlyoffice-config「拉取成功」才显示（D4 双模式铁律）
 * - 结构化视图通过默认插槽承载专属结构化组件
 * - 顶部显示 OnlyOffice 就绪状态（拉取成功/不可用/拉取中）
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { toRef, computed } from 'vue'
import { defineAsyncComponent } from 'vue'
// Task 45: legacy useB60DualMode deleted — pilot host now delegates to sync bridge.
import { usePilotBridgeAdapter } from '../sync/usePilotBridgeAdapter'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))

const props = withDefaults(defineProps<{
  /** 承载 OnlyOffice 文档的 wp_id（子底稿无独立 wp 记录时为空，则仅结构化视图） */
  wpId: string
  projectId: string
  sheetName: string
  structuredLabel?: string
  /** 是否已有结构化视图（无则仅在线编辑，不显示切换） */
  hasStructured?: boolean
  readonly?: boolean
}>(), {
  structuredLabel: '结构化视图',
  hasStructured: true,
  readonly: false,
})

// 无 wp 记录则无法在线编辑（OnlyOffice 需 wp_id+sheet 拉配置）
const canOnline = computed(() => !!props.wpId)

const {
  currentMode,
  isOoAvailable,
  switching,
  onModeChange,
} = usePilotBridgeAdapter({
  entryId: 'xlsx/b60/gt-b60-bundle',
  wpId: toRef(props, 'wpId'),
  sheetName: toRef(props, 'sheetName'),
})

const modeOptions = computed(() => [
  { label: props.structuredLabel, value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const, disabled: !canOnline.value || !isOoAvailable.value },
])

// OnlyOffice 就绪状态提示
const ooStatus = computed(() => {
  if (!canOnline.value) return { type: 'info' as const, text: '在线编辑需先生成该子底稿' }
  if (switching.value) return { type: 'info' as const, text: '切换中…' }
  if (isOoAvailable.value) return { type: 'success' as const, text: '在线编辑就绪' }
  return { type: 'warning' as const, text: 'OnlyOffice 不可用（在线编辑已禁用）' }
})

// 无结构化视图时直接强制在线编辑；无 wpId 时强制结构化
const effectiveMode = computed(() => {
  if (!props.hasStructured) return 'onlyoffice'
  if (!canOnline.value) return 'html'
  return currentMode.value
})
</script>

<template>
  <div class="gt-b60-docx-pane">
    <div class="pane-mode-bar">
      <el-segmented
        v-if="hasStructured"
        :model-value="currentMode"
        :options="modeOptions"
        @change="onModeChange"
      />
      <el-tag :type="ooStatus.type" size="small" effect="light" class="oo-status-tag">
        {{ ooStatus.text }}
      </el-tag>
    </div>

    <!-- 结构化视图 -->
    <div v-if="effectiveMode === 'html'" class="pane-structured">
      <slot />
    </div>

    <!-- 在线编辑（拉取成功后才渲染） -->
    <ErrorBoundary v-else>
      <GtOnlyOfficeSheet
        :wp-id="props.wpId"
        :sheet-name="props.sheetName"
        :project-id="props.projectId"
        :readonly="props.readonly"
      />
    </ErrorBoundary>
  </div>
</template>

<style scoped>
.gt-b60-docx-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
}

.pane-mode-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.oo-status-tag {
  flex-shrink: 0;
}

.pane-structured {
  min-height: 200px;
}
</style>
