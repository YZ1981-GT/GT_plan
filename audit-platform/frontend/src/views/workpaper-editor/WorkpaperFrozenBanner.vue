<template>
  <el-alert
    v-if="isFrozen"
    type="warning"
    :closable="false"
    style="margin-bottom: 8px"
  >
    {{ message }}
  </el-alert>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status?: string | null }>()
const isFrozen = computed(() => ['review_passed', 'archived'].includes(props.status || ''))
const message = computed(() => {
  const label = props.status === 'archived' ? '已归档' : '复核通过'
  return `底稿${label}，当前为只读。如需修改，请先按流程创建新修订。`
})
</script>
