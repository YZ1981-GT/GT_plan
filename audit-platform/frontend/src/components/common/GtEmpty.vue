<!--
  GtEmpty — 统一空态组件 [R7-S1-09, R8-S2-8.4.1]
  所有空态必须经此组件，文案不再自由发挥。

  用法（preset 模式）：
    <GtEmpty preset="no-data" @action="refetch" />
    <GtEmpty preset="developing" />

  用法（自定义模式）：
    <GtEmpty title="暂无底稿" description="请先导入账套数据" action-text="去导入" @action="goImport" icon="📋" />
-->
<template>
  <div class="gt-empty">
    <el-empty :image-size="80">
      <template #image v-if="resolvedIcon">
        <span class="gt-empty__icon">{{ resolvedIcon }}</span>
      </template>
      <template #description>
        <h4 class="gt-empty__title">{{ resolvedTitle }}</h4>
        <p v-if="resolvedDescription" class="gt-empty__desc">{{ resolvedDescription }}</p>
      </template>
      <el-button v-if="resolvedActionText" type="primary" @click="$emit('action')">
        {{ resolvedActionText }}
      </el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 5 种预设空态类型 */
export type EmptyPreset = 'no-data' | 'no-permission' | 'developing' | 'no-search-result' | 'load-failed'

const PRESET_CONFIG: Record<EmptyPreset, { icon: string; title: string; description?: string; actionText?: string }> = {
  'no-data': { icon: '📭', title: '暂无数据', actionText: '刷新' },
  'no-permission': { icon: '🔒', title: '无权限访问', description: '请联系项目经理或管理员' },
  'developing': { icon: '🚧', title: '功能开发中', description: '该模块正在开发中，敬请期待' },
  'no-search-result': { icon: '🔍', title: '无匹配结果', description: '请调整筛选条件后重试' },
  'load-failed': { icon: '⚠️', title: '加载失败', description: '请检查网络后重试', actionText: '重试' },
}

const props = defineProps<{
  /** 预设类型（与 title 二选一） */
  preset?: EmptyPreset
  /** 主标题（自定义模式） */
  title?: string
  /** 描述文字（可选） */
  description?: string
  /** 操作按钮文字（可选，不传则不显示按钮） */
  actionText?: string
  /** emoji 图标（可选，替代默认空态图） */
  icon?: string
}>()

defineEmits<{ (e: 'action'): void }>()

const presetConfig = computed(() => props.preset ? PRESET_CONFIG[props.preset] : null)
const resolvedIcon = computed(() => props.icon ?? presetConfig.value?.icon)
const resolvedTitle = computed(() => props.title ?? presetConfig.value?.title ?? '暂无数据')
const resolvedDescription = computed(() => props.description ?? presetConfig.value?.description)
const resolvedActionText = computed(() => props.actionText ?? presetConfig.value?.actionText)
</script>

<style scoped>
.gt-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
  padding: var(--gt-space-8) var(--gt-space-4);
}
.gt-empty__icon {
  font-size: 48px /* allow-px: special */;
  line-height: 1;
}
.gt-empty__title {
  margin: 0 0 var(--gt-space-2);
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-empty__desc {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
</style>
