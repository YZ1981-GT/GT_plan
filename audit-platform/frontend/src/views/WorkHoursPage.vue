<template>
  <div class="gt-workhours-page gt-fade-in">
    <div class="gt-wh-header">
      <h2>工时管理</h2>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ═══ Tab 1: 我的填报 ═══ -->
      <el-tab-pane label="我的填报" name="mine">
        <WeeklyTimesheet
          v-if="currentStaffId"
          :staff-id="currentStaffId"
          @ai-fill="showAISuggest"
        />
        <div v-else style="padding: 40px; text-align: center; color: var(--gt-color-text-secondary);">
          <el-empty description="未找到人员信息，请联系管理员" />
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 2: 待审批（抽取为子组件 R7 技术债 5）+ 顶栏 badge [R9 F15 Task 35] ═══ -->
      <el-tab-pane v-if="can('approve_workhours')" name="approve">
        <template #label>
          待审批
          <el-badge
            v-if="pendingApprovalCount > 0"
            :value="pendingApprovalCount"
            :max="99"
            type="danger"
            style="margin-left: 4px"
          />
        </template>
        <WorkHourApprovalTab @count-change="onApprovalCountChange" />
      </el-tab-pane>

      <!-- ═══ Tab 3: 统计 ═══ -->
      <el-tab-pane label="统计" name="stats">
        <div style="padding: 40px; text-align: center; color: var(--gt-color-text-secondary);">
          <el-empty description="工时统计功能开发中" />
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 4: 预算对比 (Phase 7 F8) ═══ -->
      <el-tab-pane label="预算对比" name="budget">
        <BudgetCompareChart />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getAISuggestions, getMyStaffId } from '@/services/staffApi'
import { usePermission } from '@/composables/usePermission'
import WorkHourApprovalTab from '@/components/workhour/WorkHourApprovalTab.vue'
import BudgetCompareChart from '@/components/workhour/BudgetCompareChart.vue'
import WeeklyTimesheet from '@/components/workhour/WeeklyTimesheet.vue'
import { handleApiError } from '@/utils/errorHandler'

const { can } = usePermission()
const activeTab = ref('mine')

// [R9 F15 Task 35] 待审批数量 badge
const pendingApprovalCount = ref(0)
function onApprovalCountChange(count: number) {
  pendingApprovalCount.value = count
}

// ══════════════════════════════════════════════
// Tab 1: 我的填报（由 WeeklyTimesheet 子组件处理）
// ══════════════════════════════════════════════
const currentStaffId = ref('')

async function showAISuggest() {
  if (!currentStaffId.value) return
  const today = new Date().toISOString().slice(0, 10)
  try {
    const res = await getAISuggestions(currentStaffId.value, today)
    if (res.suggestions?.length) {
      ElMessage.info(`AI 建议：${res.suggestions[0].description || '已加载'}`)
    } else { ElMessage.info('暂无建议') }
  } catch (e: any) { handleApiError(e, 'AI 预填') }
}

// ══════════════════════════════════════════════
// Lifecycle
// ══════════════════════════════════════════════
onMounted(async () => {
  try {
    const staffInfo = await getMyStaffId()
    currentStaffId.value = staffInfo.staff_id
  } catch {
    ElMessage.warning('未找到人员信息，请联系管理员')
  }

  // [R9 F15 Task 35] 加载待审批数量
  if (can('approve_workhours')) {
    try {
      const { api } = await import('@/services/apiProxy')
      const { workHours: P_wh } = await import('@/services/apiPaths')
      const summary = await api.get(P_wh.summary) as any
      pendingApprovalCount.value = summary?.pending_count || 0
    } catch { /* 静默 */ }
  }
})
</script>

<style scoped>
.gt-workhours-page { padding: var(--gt-space-4); }
.gt-wh-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-wh-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--gt-color-text-primary, #1a1a1a);
}
</style>
