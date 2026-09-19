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
          ref="timesheetRef"
          :staff-id="currentStaffId"
          :ai-suggestions="aiFillData"
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
        <WorkHourStatsDashboard />
      </el-tab-pane>

      <!-- ═══ Tab 4: 预算对比 (Phase 7 F8) ═══ -->
      <el-tab-pane label="预算对比" name="budget">
        <div class="gt-budget-project-selector" style="margin-bottom: 12px;">
          <el-select
            v-model="budgetProjectId"
            filterable
            placeholder="选择项目查看预算对比"
            style="width: 320px;"
            @change="onBudgetProjectChange"
          >
            <el-option
              v-for="p in myProjects"
              :key="p.project_id"
              :label="p.project_name || p.project_id"
              :value="p.project_id"
            />
          </el-select>
        </div>
        <BudgetCompareChart v-if="budgetProjectId" :project-id="budgetProjectId" />
        <el-empty v-else description="请选择项目" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getAISuggestions, getMyStaffId, getMyAssignments } from '@/services/staffApi'
import { usePermission } from '@/composables/usePermission'
import WorkHourApprovalTab from '@/components/workhour/WorkHourApprovalTab.vue'
import BudgetCompareChart from '@/components/workhour/BudgetCompareChart.vue'
import WeeklyTimesheet from '@/components/workhour/WeeklyTimesheet.vue'
import WorkHourStatsPanel from '@/components/workhour/WorkHourStatsPanel.vue'
import WorkHourStatsDashboard from '@/components/workhour/WorkHourStatsDashboard.vue'
import { handleApiError } from '@/utils/errorHandler'

const { can } = usePermission()
const route = useRoute()

/**
 * 允许外部深链直达某个 tab（如经理看板的「待审批」入口）。
 *
 * 只接受下面白名单里的值，且 `approve` 仍受 `can('approve_workhours')` 门控 ——
 * 无权用户即使手敲 `?tab=approve` 也只会看到默认页，不会出现空白 tab。
 */
const TAB_NAMES = ['mine', 'approve', 'stats', 'budget'] as const
function initialTab(): string {
  const requested = route.query.tab
  if (typeof requested !== 'string' || !TAB_NAMES.includes(requested as (typeof TAB_NAMES)[number])) {
    return 'mine'
  }
  if (requested === 'approve' && !can('approve_workhours')) return 'mine'
  return requested
}
const activeTab = ref(initialTab())

// [R9 F15 Task 35] 待审批数量 badge
const pendingApprovalCount = ref(0)
function onApprovalCountChange(count: number) {
  pendingApprovalCount.value = count
}

// ══════════════════════════════════════════════
// Tab 1: 我的填报（由 WeeklyTimesheet 子组件处理）
// ══════════════════════════════════════════════
const currentStaffId = ref('')
const aiFillData = ref<any[]>([])
const timesheetRef = ref<InstanceType<typeof WeeklyTimesheet> | null>(null)

// ══════════════════════════════════════════════
// Tab 4: 预算对比 — 项目选择
// ══════════════════════════════════════════════
const budgetProjectId = ref('')
const myProjects = ref<Array<{ project_id: string; project_name: string }>>([])

function onBudgetProjectChange() {
  // 选择后 BudgetCompareChart 通过 v-if + prop 自动刷新
}

async function showAISuggest() {
  if (!currentStaffId.value) return
  const today = new Date().toISOString().slice(0, 10)
  try {
    const res = await getAISuggestions(currentStaffId.value, today)
    if (res.suggestions?.length) {
      // 将AI建议回填到WeeklyTimesheet的edits中
      const timesheetEl = document.querySelector('.timesheet') as any
      const timesheetComponent = timesheetEl?.__vueParentComponent?.exposed || timesheetEl?.__vue_app__
      // 通过ref调用更简洁：直接设置edits
      aiFillData.value = res.suggestions
      ElMessage.success(`AI 已生成 ${res.suggestions.length} 条工时建议，已填入待保存`)
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

  // 加载我的项目列表(给预算Tab用)
  try {
    const assignments = await getMyAssignments()
    myProjects.value = assignments.map(a => ({
      project_id: a.project_id,
      project_name: a.project_name || a.project_id,
    }))
    // 默认选中第一个项目
    if (myProjects.value.length > 0) {
      budgetProjectId.value = myProjects.value[0].project_id
    }
  } catch { /* 静默 */ }

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
