<template>
  <el-tooltip
    :disabled="!lockInfo"
    placement="bottom"
    effect="dark"
  >
    <template #content>
      <div v-if="lockInfo" class="lock-tooltip-content">
        <p>{{ lockInfo.holder_name || '其他用户' }} 正在导入</p>
        <p v-if="lockInfo.current_phase">阶段: {{ phaseLabel }}</p>
        <p v-if="typeof lockInfo.progress === 'number'">进度: {{ lockInfo.progress }}%</p>
        <p v-if="lockInfo.estimated_remaining">预计剩余: {{ formatRemaining(lockInfo.estimated_remaining) }}</p>
      </div>
    </template>
    <el-button
      :type="lockInfo ? 'info' : 'primary'"
      :disabled="!!lockInfo"
      :icon="lockInfo ? undefined : undefined"
      aria-label="导入账表"
      @click="emit('click')"
    >
      <slot>{{ lockInfo ? '导入中...' : '导入账表' }}</slot>
    </el-button>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface LockInfo {
  holder_name?: string
  progress?: number
  estimated_remaining?: number  // seconds
  current_phase?: string
}

const props = defineProps<{
  lockInfo?: LockInfo | null
}>()

const emit = defineEmits<{
  click: []
}>()

const PHASE_LABEL: Record<string, string> = {
  bootstrap: '初始化',
  parsing: '解析',
  validating: '校验',
  writing: '写入',
  activating: '激活',
}

const phaseLabel = computed(() => {
  const phase = props.lockInfo?.current_phase
  if (!phase) return ''
  return PHASE_LABEL[phase] || phase
})

function formatRemaining(seconds: number): string {
  if (seconds < 60) return `约 ${Math.round(seconds)} 秒`
  return `约 ${Math.ceil(seconds / 60)} 分钟`
}
</script>

<style scoped>
.lock-tooltip-content p {
  margin: 2px 0;
  font-size: var(--gt-font-size-xs);
  line-height: 1.5;
}
</style>
