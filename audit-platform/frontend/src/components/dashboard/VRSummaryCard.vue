<template>
  <div class="vr-summary-card">
    <!-- 降级状态：vrSummary 为 null -->
    <template v-if="vrSummary === null">
      <el-empty
        :image-size="64"
        description="数据获取失败"
      >
        <template #description>
          <p class="vr-error-text">{{ error || '数据获取失败' }}</p>
        </template>
        <el-button type="primary" size="small" @click="$emit('retry')">
          重试
        </el-button>
      </el-empty>
    </template>

    <!-- 正常状态 -->
    <template v-else>
      <!-- 顶部汇总 -->
      <div class="vr-summary-header">
        <div class="vr-summary-stat">
          <span class="vr-blocking-count">{{ vrSummary.blocking_failed }}</span>
          <span class="vr-separator"> / </span>
          <span class="vr-total-count">{{ vrSummary.total_rules }}</span>
          <span class="vr-label"> blocking</span>
        </div>

        <!-- 全部通过标识 -->
        <el-tag
          v-if="vrSummary.all_passed"
          type="success"
          effect="dark"
          size="small"
          class="vr-pass-badge"
        >
          全部通过
        </el-tag>
      </div>

      <!-- 按循环分组列表 -->
      <div v-if="!vrSummary.all_passed" class="vr-cycle-list">
        <el-collapse v-model="activeNames" accordion>
          <template v-for="cycleStat in vrSummary.by_cycle" :key="cycleStat.cycle">
            <el-collapse-item
              v-if="cycleStat.blocking_failed > 0"
              :name="cycleStat.cycle"
            >
              <template #title>
                <div class="vr-cycle-header">
                  <span class="vr-cycle-name">{{ cycleStat.cycle }}</span>
                  <el-badge
                    :value="cycleStat.blocking_failed"
                    type="danger"
                    class="vr-cycle-badge"
                  />
                </div>
              </template>

              <!-- 展开的规则列表 -->
              <div class="vr-rules-list">
                <div
                  v-for="rule in cycleStat.failed_rules"
                  :key="rule.rule_id"
                  class="vr-rule-item"
                >
                  <div class="vr-rule-name">
                    <el-tag type="danger" size="small" effect="plain">
                      {{ rule.rule_id }}
                    </el-tag>
                    <span class="vr-rule-name-text">{{ rule.rule_name }}</span>
                  </div>
                  <div v-if="rule.details" class="vr-rule-details">
                    {{ rule.details }}
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </template>
        </el-collapse>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { VRSummaryData } from '@/composables/useDashboardData'

defineProps<{
  vrSummary: VRSummaryData | null
  error: string | null
}>()

defineEmits<{
  retry: []
}>()

/** 当前展开的循环 collapse item */
const activeNames = ref<string[]>([])
</script>

<style scoped>
.vr-summary-card {
  width: 100%;
}

.vr-error-text {
  color: var(--el-color-danger, #f56c6c);
  font-size: 13px;
  margin: 0 0 8px;
}

/* 顶部汇总 */
.vr-summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.vr-summary-stat {
  font-size: 14px;
  color: var(--gt-color-text-primary, #303133);
}

.vr-blocking-count {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-color-danger, #f56c6c);
}

.vr-separator {
  font-size: 16px;
  color: var(--gt-color-text-secondary, #909399);
}

.vr-total-count {
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.vr-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #909399);
  margin-left: 4px;
}

.vr-pass-badge {
  font-weight: 600;
}

/* 循环分组列表 */
.vr-cycle-list {
  max-height: 300px;
  overflow-y: auto;
}

.vr-cycle-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.vr-cycle-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--gt-color-text-primary, #303133);
}

.vr-cycle-badge {
  margin-left: 4px;
}

/* 规则列表 */
.vr-rules-list {
  padding: 4px 0;
}

.vr-rule-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.vr-rule-item:last-child {
  border-bottom: none;
}

.vr-rule-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vr-rule-name-text {
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
}

.vr-rule-details {
  margin-top: 6px;
  padding-left: 8px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
  line-height: 1.5;
  border-left: 2px solid var(--el-border-color-lighter, #ebeef5);
}
</style>
