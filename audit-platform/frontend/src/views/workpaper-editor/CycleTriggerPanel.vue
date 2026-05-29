<script setup lang="ts">
/**
 * CycleTriggerPanel — 配置驱动的 cycle trigger 按钮面板 [workpaper-editor-shrink-phase2 §2.3]
 *
 * 使用 editorDialogConfig 元数据中的 triggerButton + triggerVisible 配置实现 v-for 渲染，
 * 替代 Shell 模板中 15+ 个独立 v-if 按钮块（~221 行 → ~20 行 v-for）。
 *
 * 每个按钮的可见性由 triggerVisible(wpCode, sheetId) 决定，
 * 点击时通过 emit('open-dialog', key) 通知父组件打开对应 dialog。
 */
import { computed } from 'vue'
import {
  TEMPLATE_DIALOGS,
  type TemplateDialogConfig,
} from '@/composables/editorDialogConfig'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import type { CycleTypeFlags } from '@/composables/useCycleType'
import type { CycleDialogsAPI } from '@/composables/useCycleDialogs'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  wpDetail: WorkpaperDetail
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
  sheetNavActiveId: string
  iCycle: any
  gCycle: any
  kCycle: any
  lCycle: any
  mCycle: any
  nCycle: any
  fCycle: any
}>()

const emit = defineEmits<{
  'open-dialog': [key: string]
}>()

// ─── 配置驱动 trigger 列表 ──────────────────────────────────────────────────

/** 仅保留有 triggerButton + triggerVisible 的 entry */
const triggerConfigs = computed<TemplateDialogConfig[]>(() =>
  TEMPLATE_DIALOGS.filter((d) => d.triggerButton != null && d.triggerVisible != null),
)

/** 当前可见的 trigger 按钮（基于 wpCode + sheetId 过滤） */
const visibleTriggers = computed<TemplateDialogConfig[]>(() => {
  const wpCode = props.wpDetail?.wp_code || ''
  const sheetId = props.sheetNavActiveId || ''
  return triggerConfigs.value.filter((config) => config.triggerVisible!(wpCode, sheetId))
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function openDialog(config: TemplateDialogConfig) {
  // 通过 cycleDialogs 直接打开 dialog
  const stateKey = config.dialogStateKey as keyof CycleDialogsAPI
  const entry = props.cycleDialogs[stateKey]
  if (entry?.visible) {
    entry.visible.value = true
  }
  emit('open-dialog', config.key)
}
</script>

<template>
  <div v-if="visibleTriggers.length > 0" class="gt-wp-cycle-triggers">
    <template v-for="config in visibleTriggers" :key="config.key">
      <div :class="`gt-${config.key}-trigger`">
        <el-button
          :type="config.triggerButton?.type || 'primary'"
          :plain="config.triggerButton?.plain !== false"
          size="small"
          @click="openDialog(config)"
        >
          {{ config.triggerButton?.icon }} {{ config.triggerButton?.label }}
        </el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.gt-wp-cycle-triggers {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
}
</style>
