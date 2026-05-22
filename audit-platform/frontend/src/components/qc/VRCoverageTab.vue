<template>
  <div class="vr-coverage-tab">
    <!-- Summary cards -->
    <div class="coverage-summary">
      <div class="summary-card">
        <div class="summary-num">{{ coverageData?.total_rules ?? 0 }}</div>
        <div class="summary-label">VR 规则总数</div>
      </div>
      <div class="summary-card summary-card--success">
        <div class="summary-num">{{ coverageData?.compliant_cycles ?? 0 }}</div>
        <div class="summary-label">达标循环</div>
      </div>
      <div class="summary-card summary-card--danger">
        <div class="summary-num">{{ coverageData?.non_compliant_cycles ?? 0 }}</div>
        <div class="summary-label">未达标循环</div>
      </div>
    </div>

    <!-- Coverage table -->
    <el-table
      :data="coverageData?.cycles ?? []"
      stripe
      :row-class-name="rowClassName"
      @row-click="onRowClick"
      style="width: 100%; cursor: pointer"
    >
      <el-table-column prop="cycle_name" label="循环" width="120" />
      <el-table-column prop="blocking_count" label="Blocking" width="100">
        <template #default="{ row }">
          <span :class="{ 'text-danger': row.blocking_count < 3 }">{{ row.blocking_count }}</span>
          <span v-if="row.gap_blocking > 0" class="gap-badge">缺 {{ row.gap_blocking }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="warning_count" label="Warning" width="100">
        <template #default="{ row }">
          <span :class="{ 'text-danger': row.warning_count < 2 }">{{ row.warning_count }}</span>
          <span v-if="row.gap_warning > 0" class="gap-badge">缺 {{ row.gap_warning }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="info_count" label="Info" width="80" />
      <el-table-column prop="total_count" label="合计" width="80" />
      <el-table-column label="达标情况" width="200">
        <template #default="{ row }">
          <div class="progress-cell">
            <el-progress
              :percentage="calcPercentage(row)"
              :color="row.meets_standard ? '#67c23a' : '#f56c6c'"
              :stroke-width="14"
              :show-text="false"
              style="flex: 1"
            />
            <el-tag
              :type="row.meets_standard ? 'success' : 'danger'"
              size="small"
              style="margin-left: 8px"
            >
              {{ row.meets_standard ? '达标' : '未达标' }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- Standard explanation -->
    <div class="standard-note">
      <el-icon><InfoFilled /></el-icon>
      达标标准：每循环 Blocking ≥ 3 且 Warning ≥ 2
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface CycleCoverage {
  cycle_name: string
  blocking_count: number
  warning_count: number
  info_count: number
  total_count: number
  meets_standard: boolean
  gap_blocking: number
  gap_warning: number
}

interface VRCoverageData {
  cycles: CycleCoverage[]
  total_rules: number
  compliant_cycles: number
  non_compliant_cycles: number
}

const emit = defineEmits<{
  (e: 'cycle-click', cycleName: string): void
}>()

const coverageData = ref<VRCoverageData | null>(null)

function calcPercentage(row: CycleCoverage): number {
  // Progress based on meeting both criteria
  const blockingPct = Math.min(row.blocking_count / 3, 1) * 50
  const warningPct = Math.min(row.warning_count / 2, 1) * 50
  return Math.round(blockingPct + warningPct)
}

function rowClassName({ row }: { row: CycleCoverage }) {
  return row.meets_standard ? '' : 'non-compliant-row'
}

function onRowClick(row: CycleCoverage) {
  emit('cycle-click', row.cycle_name)
}

async function loadCoverage() {
  try {
    const res = await api.get('/api/qc/vr-coverage')
    coverageData.value = res.data || res
  } catch {
    coverageData.value = null
  }
}

onMounted(() => {
  loadCoverage()
})
</script>

<style scoped>
.vr-coverage-tab {
  padding: 16px 0;
}
.coverage-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.summary-card {
  flex: 1;
  padding: 16px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  text-align: center;
}
.summary-card--success {
  background: #f0f9eb;
}
.summary-card--danger {
  background: #fef0f0;
}
.summary-num {
  font-size: 24px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  font-family: 'Arial Narrow', Arial, sans-serif;
}
.summary-card--success .summary-num {
  color: #67c23a;
}
.summary-card--danger .summary-num {
  color: #f56c6c;
}
.summary-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.progress-cell {
  display: flex;
  align-items: center;
}
.text-danger {
  color: #f56c6c;
  font-weight: 600;
}
.gap-badge {
  margin-left: 4px;
  font-size: 11px;
  color: #f56c6c;
  background: #fef0f0;
  padding: 1px 4px;
  border-radius: 3px;
}
.standard-note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}
:deep(.non-compliant-row) {
  background-color: #fef0f0 !important;
}
:deep(.non-compliant-row:hover > td) {
  background-color: #fde2e2 !important;
}
</style>
