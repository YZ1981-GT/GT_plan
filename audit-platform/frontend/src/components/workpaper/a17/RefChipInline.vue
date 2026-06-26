<script setup lang="ts">
/**
 * RefChipInline — 行内 wp_code 引用芯片组件
 *
 * 可点击跳转到对应底稿；禁用时灰色 + tooltip "该底稿在当前项目中不存在"。
 *
 * Requirements: 2.1, 2.2, 2.3
 */
import { useRouter } from 'vue-router'

const props = defineProps<{
  wpCode: string
  disabled?: boolean
  tooltip?: string
  projectId?: string
  wpId?: string
}>()

const router = useRouter()

function handleClick() {
  if (props.disabled || !props.wpId || !props.projectId) return
  router.push({
    name: 'WorkpaperEditor',
    params: {
      projectId: props.projectId,
      wpId: props.wpId,
    },
  })
}
</script>

<template>
  <el-tooltip
    :content="tooltip || (disabled ? '该底稿在当前项目中不存在' : wpCode)"
    :disabled="!tooltip && !disabled"
    placement="top"
  >
    <span
      class="ref-chip-inline"
      :class="{ 'is-disabled': disabled, 'is-active': !disabled }"
      @click.stop="handleClick"
    >
      {{ wpCode }}
    </span>
  </el-tooltip>
</template>

<style scoped>
.ref-chip-inline {
  display: inline-flex;
  align-items: center;
  padding: 0 6px;
  height: 20px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  vertical-align: middle;
  margin: 0 2px;
  transition: all 0.2s;
  white-space: nowrap;
}
.ref-chip-inline.is-active {
  background: var(--gt-color-primary-bg, #ecf5ff);
  color: var(--gt-color-primary, #409eff);
  border: 1px solid var(--gt-color-primary-light, #b3d8ff);
  cursor: pointer;
}
.ref-chip-inline.is-active:hover {
  background: var(--gt-color-primary, #409eff);
  color: #fff;
}
.ref-chip-inline.is-disabled {
  background: var(--gt-color-bg, #f5f7fa);
  color: var(--gt-color-text-placeholder, #a8abb2);
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  cursor: not-allowed;
}
</style>
