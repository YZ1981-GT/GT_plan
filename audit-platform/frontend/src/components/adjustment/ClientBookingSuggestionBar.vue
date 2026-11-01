<template>
  <el-alert v-if="suggestions.length" type="warning" show-icon :closable="false" class="gt-booking-suggestion">
    <template #title>
      <div class="gt-booking-suggestion__content">
        <span>检测到 {{ suggestions.length }} 组调整疑似已由客户入账。系统仅按科目、借贷栏和金额精确匹配，不会自动标记。</span>
        <el-button size="small" type="warning" plain @click="emit('review', suggestions[0])">逐组确认</el-button>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import type { AdjustmentBookingSuggestion } from '@/services/auditPlatformApi'

defineProps<{ suggestions: AdjustmentBookingSuggestion[] }>()
const emit = defineEmits<{ review: [suggestion: AdjustmentBookingSuggestion] }>()
</script>

<style scoped>
.gt-booking-suggestion { margin-bottom: 8px; }
.gt-booking-suggestion__content { display: flex; align-items: center; gap: 12px; justify-content: space-between; flex-wrap: wrap; }
</style>
