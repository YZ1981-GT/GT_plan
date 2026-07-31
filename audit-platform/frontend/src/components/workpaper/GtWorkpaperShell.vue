<!--
  GtWorkpaperShell — 底稿骨架套壳组件

  默认注入全部全局能力（displayPrefs/agingConfig/版本链/复核/AI/jumpToSection/reload），
  使新底稿「套壳即拥有」全部全局服务。内部调用 useWorkpaperScaffold 保证与 composable
  路径接线完全一致。

  Requirements: 2.1, 2.2
-->
<script setup lang="ts">
import { type Ref, toRef } from 'vue'
import {
  useWorkpaperScaffold,
} from './composables/useWorkpaperScaffold'

// ─── Props ────────────────────────────────────────────────────────────────────
export interface GtWorkpaperShellProps {
  wpCode: string
  wpId: string
  projectId: string
  year?: number
  agingSubject?: string
  readonly?: boolean
  /**
   * 项目适用准则（供披露 Tab 变体门控）。接受数组 / 逗号串 / v2 对象，
   * 由 scaffold 归一后 provide；套壳路径不经 render-config，故须由使用方传入。
   */
  applicableStandards?: unknown
}

const props = defineProps<GtWorkpaperShellProps>()

// ─── Emits ────────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  'jump-to-section': [sheetLabel: string]
  'navigate-sheet': [sheetName: string]
  save: []
  reload: []
}>()

// ─── Slots（类型声明，供消费者类型提示）──────────────────────────────────────
defineSlots<{
  toolbar?: () => any
  objective?: () => any
  guidance?: () => any
  default?: () => any
}>()

// ─── 调用 useWorkpaperScaffold（共享实现，保证两条路径一致）────────────────────
const scaffold = useWorkpaperScaffold({
  wpCode: toRef(props, 'wpCode') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: toRef(props, 'year') as Ref<number | undefined>,
  agingSubject: props.agingSubject,
  readonly: toRef(props, 'readonly') as Ref<boolean | undefined>,
  applicableStandards: toRef(props, 'applicableStandards'),
  onJumpToSection: (sheetLabel: string) => emit('jump-to-section', sheetLabel),
  reloadFn: () => emit('reload'),
})

// 解构 fontStyle 到顶层使模板自动解包 ComputedRef
const { fontStyle, versionToolbar } = scaffold
</script>

<template>
  <div class="gt-wp-root" :style="fontStyle">
    <!-- #toolbar：默认渲染版本链工具栏 + 导入导出 dropdown 占位 -->
    <div class="gt-wp-shell__toolbar">
      <slot name="toolbar">
        <!-- 版本链工具栏默认内容 -->
        <div class="gt-wp-shell__toolbar-default">
          <button
            class="gt-wp-shell__version-btn"
            type="button"
            title="查看版本历史"
            @click="versionToolbar.openVersionHistory()"
          >
            📋 版本历史
          </button>
          <!-- 导入导出 dropdown 占位（P1 WpImportExport 组件就绪后替换） -->
          <!-- TODO: <WpImportExport :wp-id="wpId" /> -->
        </div>
      </slot>
    </div>

    <!-- #objective：审计目标区域 -->
    <slot name="objective" />

    <!-- #guidance：编制提示区域 -->
    <slot name="guidance" />

    <!-- #default：底稿主体内容 -->
    <slot />
  </div>
</template>

<style scoped>
.gt-wp-root {
  position: relative;
  width: 100%;
  font-size: var(--wp-font-size, 13px);
}

.gt-wp-shell__toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 4px 8px;
  min-height: 32px;
}

.gt-wp-shell__toolbar-default {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-wp-shell__version-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.gt-wp-shell__version-btn:hover {
  color: #409eff;
  border-color: #409eff;
  background: #ecf5ff;
}
</style>
