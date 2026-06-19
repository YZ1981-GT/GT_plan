<script setup lang="ts">
/**
 * CitationList — AI 回答引用来源列表
 *
 * 在 AI 消息气泡下方展示引用来源（准则名/文件名）。
 *
 * Requirements: 6.4, 6.5
 */
import { Document } from '@element-plus/icons-vue'

export interface Citation {
  source_type: string
  source_id: string
  source_name: string
}

defineProps<{
  citations: Citation[]
}>()
</script>

<template>
  <div v-if="citations.length > 0" class="gt-citation-list">
    <div class="gt-citation-list__title">引用来源</div>
    <div
      v-for="(c, idx) in citations"
      :key="idx"
      class="gt-citation-list__item"
    >
      <el-icon :size="12"><Document /></el-icon>
      <span class="gt-citation-list__name">{{ c.source_name }}</span>
    </div>
  </div>
</template>

<style scoped>
.gt-citation-list {
  padding: 6px 12px;
  margin-top: 4px;
  border-radius: 8px;
  background: var(--gt-bg-light, #f4f0fa);
  max-width: 85%;
}

.gt-citation-list__title {
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}

.gt-citation-list__item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
  font-size: 12px;
  color: var(--gt-primary, #4b2d77);
}

.gt-citation-list__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
