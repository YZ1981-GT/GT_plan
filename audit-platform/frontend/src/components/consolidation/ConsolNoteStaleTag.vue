<template>
  <el-tag
    v-if="isStale"
    type="warning"
    size="small"
    data-testid="consol-note-stale-tag"
  >
    待更新：{{ reasonLabel || '历史标记' }}<span v-if="formattedAt">（{{ formattedAt }}）</span>
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { fmtDateTime, parseServerTime } from '@/utils/formatters'

const props = defineProps<{
  isStale?: boolean
  reasonLabel?: string | null
  staleAt?: string | null
}>()

const formattedAt = computed(() => {
  if (!props.staleAt) return ''
  const parsed = parseServerTime(props.staleAt)
  return Number.isNaN(parsed.getTime()) ? props.staleAt : fmtDateTime(parsed)
})
</script>
