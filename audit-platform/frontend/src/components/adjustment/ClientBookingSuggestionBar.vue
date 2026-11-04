<template>
  <el-alert v-if="suggestions.length" type="warning" show-icon :closable="false" class="gt-booking-suggestion">
    <template #title>
      <div class="gt-booking-suggestion__content">
        <span>检测到 {{ suggestions.length }} 组调整疑似已由客户入账。系统仅按科目、借贷栏和金额精确匹配，不会自动标记。</span>
        <el-button v-if="canEdit" size="small" type="warning" plain data-testid="booking-suggestion-toggle"
          @click="expanded = !expanded">
          {{ expanded ? '收起' : '逐组确认' }}
        </el-button>
        <span v-else class="gt-booking-suggestion__hint">请有编辑权限的成员确认</span>
      </div>
    </template>
    <!-- 列出全部建议（原先只能打开第一条），每条单独确认（spec voucher-workflow-linkage-lineage-closure R5.2） -->
    <div v-if="canEdit && expanded" class="gt-booking-suggestion__list" data-testid="booking-suggestion-list">
      <div v-for="item in suggestions" :key="item.entry_group_id" class="gt-booking-suggestion__item">
        <strong>{{ item.adjustment_no }}</strong>
        <span class="gt-booking-suggestion__desc">{{ item.description || '无摘要' }}</span>
        <span class="gt-booking-suggestion__hint">候选凭证 {{ item.candidates.length }} 张</span>
        <el-button size="small" type="primary" link @click="emit('review', item)">确认</el-button>
      </div>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AdjustmentBookingSuggestion } from '@/services/auditPlatformApi'

/** canEdit：与「标记客户已入账」同一判定（项目可写 × 调整分录编辑权限）；为假只提示、不给按钮 */
defineProps<{ suggestions: AdjustmentBookingSuggestion[]; canEdit: boolean }>()
const emit = defineEmits<{ review: [suggestion: AdjustmentBookingSuggestion] }>()
const expanded = ref(false)
</script>

<style scoped>
.gt-booking-suggestion { margin-bottom: 8px; }
.gt-booking-suggestion__content { display: flex; align-items: center; gap: 12px; justify-content: space-between; flex-wrap: wrap; }
.gt-booking-suggestion__hint { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); }
.gt-booking-suggestion__list { display: grid; gap: 4px; margin-top: 6px; }
.gt-booking-suggestion__item { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-booking-suggestion__desc { color: var(--gt-color-text-secondary); }
</style>
