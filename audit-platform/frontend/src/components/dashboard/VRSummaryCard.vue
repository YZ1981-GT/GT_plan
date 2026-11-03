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

      <!-- 没有运行一致性检查（如项目未设置审计年度）：写明原因 -->
      <p v-if="vrSummary.unavailable" class="vr-unavailable-reason">
        {{ vrSummary.reason || '未运行一致性检查' }}
      </p>

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

      <!-- 未执行 / 检查异常 / 不适用：各有标签、条数与原因，不算「通过」（需求 16.5；失败项在上面按循环列出） -->
      <div v-if="otherStateCounts.length || otherStateChecks.length" class="vr-status-section">
        <div class="vr-status-counts">
          <span v-for="s in otherStateCounts" :key="s.status" class="vr-status-count">
            {{ s.label }} {{ s.count }} 项
          </span>
        </div>
        <div class="vr-status-list">
          <div
            v-for="(check, i) in otherStateChecks"
            :key="`${i}:${check.check_name}`"
            class="vr-status-item"
          >
            <div class="vr-rule-name">
              <el-tag :type="statusTagType(check)" size="small" effect="plain">
                {{ checkStatusLabel(check) }}
              </el-tag>
              <span class="vr-rule-name-text">{{ check.check_name }}</span>
            </div>
            <div v-if="checkReasonOf(check)" class="vr-rule-details">
              {{ checkReasonOf(check) }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { VRCheckStatusItem, VRSummaryData } from '@/composables/useDashboardData'
import { checkReasonOf, checkStatusLabel, checkStatusOf, type GateCheckStatus } from '@/utils/consistencyCheckStatus'

const props = defineProps<{
  vrSummary: VRSummaryData | null
  error: string | null
}>()

defineEmits<{
  retry: []
}>()

/** 当前展开的循环 collapse item */
const activeNames = ref<string[]>([])

/** 「失败」以外的三种非通过状态，按此顺序显示条数 */
const OTHER_STATES: GateCheckStatus[] = ['not_executed', 'error', 'not_applicable']

const otherStateCounts = computed(() => {
  const counts = props.vrSummary?.status_counts ?? {}
  return OTHER_STATES
    .map(status => ({ status, label: checkStatusLabel({ status }), count: counts[status] ?? 0 }))
    .filter(s => s.count > 0)
})

const otherStateChecks = computed<VRCheckStatusItem[]>(() =>
  (props.vrSummary?.not_passed_checks ?? []).filter(c => OTHER_STATES.includes(checkStatusOf(c))),
)

function statusTagType(check: VRCheckStatusItem): 'danger' | 'warning' | 'info' {
  const st = checkStatusOf(check)
  if (st === 'error') return 'danger'
  return st === 'not_executed' ? 'warning' : 'info'
}
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

/* 未运行原因与其余三态 */
.vr-unavailable-reason {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-color-warning, #e6a23c);
}

.vr-status-section {
  margin-top: 8px;
}

.vr-status-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--gt-color-text-secondary, #909399);
}

.vr-status-list {
  max-height: 240px;
  overflow-y: auto;
}

.vr-status-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.vr-status-item:last-child {
  border-bottom: none;
}
</style>
