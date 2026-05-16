<script setup lang="ts">
/**
 * 风险追溯链路图
 * Sprint 8 Task 8.7: 风险→底稿追溯链路可视化
 */
import { computed } from 'vue'

interface WorkpaperNode {
  wp_id: string
  wp_code: string
  wp_name?: string
  stage: string
  match_type?: string
}

interface ChainStage {
  stage: string
  stage_order: number
  workpapers: WorkpaperNode[]
  has_coverage: boolean
}

interface RiskTrace {
  risk_id: string
  risk_title: string
  chain: ChainStage[]
}

const props = defineProps<{
  trace: RiskTrace | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-wp', wpId: string): void
}>()

const stageLabels: Record<string, string> = {
  risk_assessment: 'B 风险评估',
  control_test: 'C 控制测试',
  substantive: 'D-N 实质性程序',
  completion: 'A 完成阶段',
}

const stageColors: Record<string, string> = {
  risk_assessment: '#409eff',
  control_test: '#67c23a',
  substantive: '#e6a23c',
  completion: '#909399',
}

const completeness = computed(() => {
  if (!props.trace) return 0
  const covered = props.trace.chain.filter(s => s.has_coverage).length
  return Math.round((covered / props.trace.chain.length) * 100)
})
</script>

<template>
  <div class="risk-trace-graph">
    <template v-if="trace">
      <div class="trace-header">
        <h4>{{ trace.risk_title }}</h4>
        <el-progress
          :percentage="completeness"
          :stroke-width="8"
          style="width: 120px"
        />
      </div>

      <!-- 链路图 -->
      <div class="chain-flow">
        <div
          v-for="(stage, idx) in trace.chain"
          :key="stage.stage"
          class="chain-node"
        >
          <!-- 连接线 -->
          <div v-if="idx > 0" class="chain-connector">
            <div class="connector-line" />
            <span class="connector-arrow">→</span>
          </div>

          <!-- 阶段节点 -->
          <div
            class="stage-card"
            :class="{ 'has-coverage': stage.has_coverage, 'no-coverage': !stage.has_coverage }"
            :style="{ borderColor: stageColors[stage.stage] }"
          >
            <div class="stage-label" :style="{ color: stageColors[stage.stage] }">
              {{ stageLabels[stage.stage] || stage.stage }}
            </div>

            <div v-if="stage.workpapers.length > 0" class="wp-list">
              <div
                v-for="wp in stage.workpapers"
                :key="wp.wp_id"
                class="wp-item"
                @click="emit('navigate-wp', wp.wp_id)"
              >
                <el-tag size="small" effect="plain">{{ wp.wp_code }}</el-tag>
              </div>
            </div>
            <div v-else class="no-wp">
              <el-tag type="danger" size="small" effect="light">未覆盖</el-tag>
            </div>
          </div>
        </div>
      </div>
    </template>

    <el-empty v-else-if="!loading" description="选择一个风险项查看追溯链路" />
  </div>
</template>

<style scoped>
.risk-trace-graph {
  padding: 12px;
}
.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.trace-header h4 {
  margin: 0;
  font-size: var(--gt-font-size-sm);
}
.chain-flow {
  display: flex;
  align-items: flex-start;
  overflow-x: auto;
  padding: 8px 0;
}
.chain-node {
  display: flex;
  align-items: center;
}
.chain-connector {
  display: flex;
  align-items: center;
  padding: 0 8px;
}
.connector-line {
  width: 20px;
  height: 2px;
  background: var(--gt-color-border);
}
.connector-arrow {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-md);
  margin-left: -4px;
}
.stage-card {
  border: 2px solid;
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 130px;
  text-align: center;
  transition: box-shadow 0.2s;
}
.stage-card.has-coverage {
  background: var(--gt-bg-success);
}
.stage-card.no-coverage {
  background: var(--gt-bg-danger);
  border-style: dashed;
}
.stage-label {
  font-weight: 600;
  font-size: var(--gt-font-size-xs);
  margin-bottom: 8px;
}
.wp-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}
.wp-item {
  cursor: pointer;
}
.wp-item:hover :deep(.el-tag) {
  background: var(--el-color-primary-light-9);
}
.no-wp {
  margin-top: 4px;
}
</style>
