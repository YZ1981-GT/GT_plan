<script setup lang="ts">
/**
 * CycleDialogHost — 配置驱动的 cycle dialog 渲染宿主 [workpaper-editor-shrink-phase2 §2.2]
 *
 * 使用 editorDialogConfig 元数据 + defineAsyncComponent 实现 v-for 渲染，
 * 替代 Shell 模板中 17 个独立 v-if 块（~279 行 → ~30 行 v-for）。
 *
 * 每个 dialog 通过 defineAsyncComponent lazy 加载，仅在对应 cycle 激活时下载 chunk。
 * chunk 加载失败时 ElMessage.error + 关闭 dialog。
 */
import { defineAsyncComponent, computed, type Component } from 'vue'
import { ElMessage } from 'element-plus'
import {
  TEMPLATE_DIALOGS,
  type TemplateDialogConfig,
  type DialogPropsContext,
} from '@/composables/editorDialogConfig'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import type { CycleTypeFlags } from '@/composables/useCycleType'
import type { CycleDialogsAPI } from '@/composables/useCycleDialogs'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  sheetNavActiveId: string
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
}>()

const emit = defineEmits<{
  saved: []
  applied: [sheet: string]
}>()

// ─── 配置驱动 dialog 列表 ───────────────────────────────────────────────────

/** 仅保留有 component 工厂的 entry（Phase 2 扩展后全部 17 条都有） */
const activeDialogs = computed<TemplateDialogConfig[]>(() =>
  TEMPLATE_DIALOGS.filter((d) => d.component != null),
)

// ─── defineAsyncComponent 缓存（避免每次 render 重建） ─────────────────────

const dialogComponents: Record<string, Component> = {}

for (const config of TEMPLATE_DIALOGS) {
  if (!config.component) continue
  const stateKey = config.dialogStateKey as keyof CycleDialogsAPI
  dialogComponents[config.key] = defineAsyncComponent({
    loader: config.component,
    onError(error, retry, fail, attempts) {
      ElMessage.error(`加载 ${config.title} 组件失败，请刷新重试`)
      // 关闭 dialog
      const entry = props.cycleDialogs[stateKey]
      if (entry?.visible) {
        entry.visible.value = false
      }
      fail()
    },
  })
}

// ─── Props 工厂上下文 ────────────────────────────────────────────────────────

function getDialogProps(config: TemplateDialogConfig): Record<string, any> {
  if (!config.propsFactory) return {}
  const ctx: DialogPropsContext = {
    projectId: props.projectId,
    wpId: props.wpId,
    wpDetail: props.wpDetail,
    sheetNavActiveId: props.sheetNavActiveId,
  }
  return config.propsFactory(ctx)
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function onDialogVisibleChange(config: TemplateDialogConfig, val: boolean) {
  const stateKey = config.dialogStateKey as keyof CycleDialogsAPI
  const entry = props.cycleDialogs[stateKey]
  if (entry?.visible) {
    entry.visible.value = val
  }
}

function onDialogApplied(config: TemplateDialogConfig, sheet: string) {
  const stateKey = config.dialogStateKey as keyof CycleDialogsAPI
  const entry = props.cycleDialogs[stateKey]
  if (entry && 'onApplied' in entry) {
    ;(entry as { onApplied: (s: string) => void }).onApplied(sheet)
  }
  emit('applied', sheet)
}

function onDialogSaved() {
  emit('saved')
}
</script>

<template>
  <template v-for="config in activeDialogs" :key="config.key">
    <component
      :is="dialogComponents[config.key]"
      v-if="cycleDialogs[config.dialogStateKey as keyof CycleDialogsAPI]?.visible?.value"
      v-bind="getDialogProps(config)"
      :visible="cycleDialogs[config.dialogStateKey as keyof CycleDialogsAPI]?.visible?.value"
      @update:visible="onDialogVisibleChange(config, $event)"
      @saved="onDialogSaved"
      @applied="(sheet: string) => onDialogApplied(config, sheet)"
    />
  </template>
</template>
