<!--
  PriorYearStatusTag — 上年结转状态标签

  颜色映射：
  - blue = "new" (本年新增)
  - orange/warning = "continuing" (上年延续)
  - gray/info = "reversed" (已转回)

  Requirements: 4.7
-->
<template>
  <el-tag
    v-if="status"
    :type="tagType"
    size="small"
    effect="light"
  >
    {{ label }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status?: string | null
}>()

const tagType = computed<'' | 'success' | 'warning' | 'info' | 'danger'>(() => {
  switch (props.status) {
    case 'new': return ''        // blue (default/primary)
    case 'continuing': return 'warning'  // orange
    case 'reversed': return 'info'       // gray
    default: return 'info'
  }
})

const label = computed(() => {
  switch (props.status) {
    case 'new': return '本年新增'
    case 'continuing': return '上年延续'
    case 'reversed': return '已转回'
    default: return props.status || ''
  }
})
</script>
