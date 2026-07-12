<template>
  <div class="entity-verify-fraud-panel">
    <!-- Row-level flags -->
    <div v-if="rowFlags.size > 0" class="entity-verify-fraud-panel__section">
      <h5 class="entity-verify-fraud-panel__subtitle">行内一致性异常</h5>
      <div
        v-for="[rowId, flags] of rowFlags"
        :key="rowId"
        class="entity-verify-fraud-panel__item"
      >
        <span class="entity-verify-fraud-panel__entity">
          {{ getEntityName(rowId) }}
        </span>
        <el-tag
          v-for="flag in flags"
          :key="flag"
          type="warning"
          size="small"
          class="entity-verify-fraud-panel__flag-tag"
        >
          {{ getFlagLabel(flag) }}
        </el-tag>
      </div>
    </div>

    <!-- Cross-row flags -->
    <div v-if="crossFlags.length > 0" class="entity-verify-fraud-panel__section">
      <h5 class="entity-verify-fraud-panel__subtitle">跨行红旗</h5>
      <el-alert
        v-for="(flag, idx) in crossFlags"
        :key="idx"
        :title="flag.label"
        :description="flag.detail"
        type="error"
        show-icon
        :closable="false"
        class="entity-verify-fraud-panel__cross-alert"
      />
    </div>

    <!-- Empty state -->
    <div v-if="rowFlags.size === 0 && crossFlags.length === 0" class="entity-verify-fraud-panel__empty">
      <span class="entity-verify-fraud-panel__empty-icon">✅</span>
      <span class="entity-verify-fraud-panel__empty-text">未检测到可疑项</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EntityVerifyRow } from './entityVerifyTypes'
import { CONSISTENCY_RULES, type CrossRowFlag } from './composables/useFraudFlagDetect'

const props = defineProps<{
  rowFlags: Map<string, string[]>
  crossFlags: CrossRowFlag[]
  rows: EntityVerifyRow[]
}>()

function getEntityName(rowId: string): string {
  const row = props.rows.find((r) => r._row_id === rowId)
  return row?.entity_name ?? rowId
}

function getFlagLabel(flagId: string): string {
  const rule = CONSISTENCY_RULES.find((r) => r.id === flagId)
  return rule?.label ?? flagId
}
</script>

<style scoped>
.entity-verify-fraud-panel {
  padding: 8px 0 0 0;
  border-radius: 6px;
  margin-bottom: 0;
}

.entity-verify-fraud-panel__section {
  margin-bottom: 8px;
}

.entity-verify-fraud-panel__subtitle {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
}

.entity-verify-fraud-panel__item {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.entity-verify-fraud-panel__entity {
  font-size: 12px;
  font-weight: 500;
  min-width: 100px;
}

.entity-verify-fraud-panel__flag-tag {
  font-size: 11px;
}

.entity-verify-fraud-panel__cross-alert {
  margin-bottom: 8px;
}

.entity-verify-fraud-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 0;
  color: var(--el-color-success);
  font-size: var(--wp-font-size, 13px);
}

.entity-verify-fraud-panel__empty-icon {
  font-size: 16px;
}

.entity-verify-fraud-panel__empty-text {
  color: var(--el-text-color-secondary);
}
</style>
