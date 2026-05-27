<template>
  <div class="trust-consistency">
    <template v-if="status">
      <div class="consistency-badges">
        <div class="badge-item" :class="{ 'badge-ok': status.is_synced, 'badge-warn': !status.is_synced }">
          <span class="badge-icon">{{ status.is_synced ? '✅' : '⚠️' }}</span>
          <div class="badge-content">
            <span class="badge-label">同步状态</span>
            <span class="badge-value">{{ status.is_synced ? '已同步' : `${status.unresolved_conflicts} 个未调解冲突` }}</span>
          </div>
        </div>

        <div class="badge-item" :class="{ 'badge-ok': !status.is_stale, 'badge-warn': status.is_stale }">
          <span class="badge-icon">{{ status.is_stale ? '🕐' : '✅' }}</span>
          <div class="badge-content">
            <span class="badge-label">数据新鲜度</span>
            <span class="badge-value">{{ status.is_stale ? '上游已变更，待联动' : '最新' }}</span>
          </div>
        </div>

        <div class="badge-item" :class="{ 'badge-ok': !status.is_manual_override, 'badge-info': status.is_manual_override }">
          <span class="badge-icon">{{ status.is_manual_override ? '✋' : '✅' }}</span>
          <div class="badge-content">
            <span class="badge-label">手工覆盖</span>
            <span class="badge-value">{{ status.is_manual_override ? '已手工覆盖（不自动联动）' : '无' }}</span>
          </div>
        </div>

        <div class="badge-item" :class="{ 'badge-ok': !status.has_pending_ai, 'badge-warn': status.has_pending_ai }">
          <span class="badge-icon">{{ status.has_pending_ai ? '🤖' : '✅' }}</span>
          <div class="badge-content">
            <span class="badge-label">AI 内容确认</span>
            <span class="badge-value">{{ status.has_pending_ai ? `${status.pending_ai_count} 条待确认` : '全部已确认' }}</span>
          </div>
        </div>
      </div>
    </template>
    <el-empty v-else description="暂无一致性数据" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  status: {
    is_synced: boolean
    unresolved_conflicts: number
    is_stale: boolean
    is_manual_override: boolean
    has_pending_ai: boolean
    pending_ai_count: number
  } | undefined
}>()
</script>

<style scoped>
.trust-consistency {
  padding: 12px 0;
}
.consistency-badges {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.badge-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-border-light, #f0f0f5);
  transition: all 0.2s;
}
.badge-item.badge-ok {
  background: #f6ffed;
  border-color: #b7eb8f;
}
.badge-item.badge-warn {
  background: #fffbe6;
  border-color: #ffe58f;
}
.badge-item.badge-info {
  background: #f4f0fa;
  border-color: #d3adf7;
}
.badge-icon {
  font-size: 20px;
}
.badge-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.badge-label {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
}
.badge-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--gt-color-text, #1d1d1f);
}
</style>
