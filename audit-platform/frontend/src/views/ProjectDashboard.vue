<template>
  <div class="gt-proj-dash gt-fade-in">
    <div class="gt-pd-header">
      <GtPageHeader title="项目看板" :show-back="false">
        <template #actions>
          <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
        </template>
      </GtPageHeader>
    </div>

    <!-- 工作流进度条 + 一键刷新按钮 -->
    <div class="gt-pd-workflow-bar">
      <WorkflowProgress :project-id="projectId" :year="projectYear" @step-action="onStepAction" />
      <el-button
        type="primary"
        :loading="chainExec.executing.value"
        :disabled="chainExec.executing.value"
        @click="onRefreshAll"
        class="gt-pd-refresh-all-btn"
      >
        <template v-if="chainExec.executing.value">执行中...</template>
        <template v-else>🔄 一键刷新全部</template>
      </el-button>
    </div>

    <!-- 全链路执行进度面板 -->
    <div v-if="chainExec.executing.value || showChainProgress" class="gt-pd-chain-progress">
      <div class="gt-chain-steps">
        <div
          v-for="step in chainExec.stepStates.value"
          :key="step.key"
          class="gt-chain-step"
          :class="`gt-chain-step--${step.status}`"
        >
          <span class="gt-chain-step__icon">
            <template v-if="step.status === 'pending'">○</template>
            <template v-else-if="step.status === 'running'">
              <i class="el-icon-loading" style="animation: spin 1s linear infinite;">⟳</i>
            </template>
            <template v-else-if="step.status === 'completed'">✓</template>
            <template v-else-if="step.status === 'failed'">✗</template>
            <template v-else-if="step.status === 'skipped'">⊘</template>
          </span>
          <span class="gt-chain-step__label">{{ step.label }}</span>
          <el-tooltip
            v-if="step.status === 'failed' && step.error"
            :content="step.error"
            placement="top"
          >
            <span class="gt-chain-step__error-hint">⚠</span>
          </el-tooltip>
          <span v-if="step.durationMs" class="gt-chain-step__duration">
            {{ (step.durationMs / 1000).toFixed(1) }}s
          </span>
        </div>
      </div>
      <el-button
        v-if="!chainExec.executing.value && showChainProgress"
        size="small"
        text
        @click="showChainProgress = false"
      >
        收起
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>项目进度</h4>
          <v-chart v-if="progressOption" :option="progressOption" autoresize style="height: 200px" />
          <el-empty v-else :image-size="60" description="暂无数据" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>底稿完成度</h4>
          <div v-if="wpProgress">
            <div v-for="(v, k) in wpProgress.by_cycle" :key="k" style="margin-bottom: 8px">
              <span style="display: inline-block; width: 30px; font-weight: 600">{{ k }}</span>
              <el-progress :percentage="v.total ? Math.round((v.prepared + (v.reviewed||0) + (v.archived||0)) / v.total * 100) : 0"
                :stroke-width="12" style="flex: 1" />
            </div>
            <div style="margin-top: 12px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary)">整体完成率：{{ wpProgress.rate }}%</div>
          </div>
          <el-empty v-else :image-size="60" description="暂无底稿数据" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-pd-card">
          <h4>团队工作量</h4>
          <v-chart v-if="teamOption" :option="teamOption" autoresize style="height: 200px" />
          <el-empty v-else :image-size="60" description="暂无工时数据" />
        </div>
      </el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <div class="gt-pd-card">
          <h4>关键待办 Top10</h4>
          <el-table :data="overdue" border size="small" max-height="250" empty-text="无逾期底稿">
            <el-table-column prop="wp_code" label="编号" width="100" />
            <el-table-column prop="wp_name" label="名称" min-width="180" />
            <el-table-column prop="overdue_days" label="逾期天数" width="90" align="right" />
            <el-table-column label="操作" width="180" align="center">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="warning"
                  :disabled="isRemindDisabled(row)"
                  :loading="row._reminding"
                  @click="onRemind(row)"
                  v-permission="'workpaper:escalate'"
                >
                  催办
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  @click="onReassign(row)"
                >
                  重新分配
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="remindLimitTip" class="gt-pd-remind-tip">
            <el-alert :title="remindLimitTip" type="warning" :closable="true" @close="remindLimitTip = ''" show-icon>
              <template #default>
                <el-button size="small" type="danger" plain style="margin-top: 4px" @click="onEscalateToPartner">
                  升级到合伙人
                </el-button>
              </template>
            </el-alert>
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="gt-pd-card">
          <h4>数据一致性</h4>
          <div v-if="consistency">
            <div v-for="c in consistency.checks" :key="c.check_name" style="margin-bottom: 6px">
              <span>{{ c.passed ? '✅' : '⚠️' }} {{ c.check_name }}</span>
            </div>
          </div>
          <el-empty v-else :image-size="60" description="点击刷新加载" />
        </div>
      </el-col>
    </el-row>

    <!-- 重新分配对话框 -->
    <StaffSelectDialog
      v-model="showReassignDialog"
      :project-id="projectId"
      title="重新分配底稿"
      @confirm="onReassignConfirm"
    />
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import * as P from '@/services/apiPaths'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmEscalate } from '@/utils/confirm'
import {
  getWorkpaperProgress, getOverdueWorkpapers,
  runConsistencyCheck as apiRunConsistencyCheck, getProjectWorkHours,
} from '@/services/commonApi'
import http from '@/utils/http'
import StaffSelectDialog from '@/components/assignment/StaffSelectDialog.vue'
import { handleApiError } from '@/utils/errorHandler'
import WorkflowProgress from '@/components/common/WorkflowProgress.vue'
import { useChainExecution } from '@/composables/useChainExecution'
import { useProjectStore } from '@/stores/project'

use([PieChart, BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const projectStore = useProjectStore()
const projectYear = computed(() => projectStore.year || new Date().getFullYear() - 1)

// ── 全链路执行 ──
const chainExec = useChainExecution(projectId)
const showChainProgress = ref(false)

/** 一键刷新全部按钮点击 */
async function onRefreshAll() {
  try {
    await ElMessageBox.confirm(
      '将依次执行以下步骤：\n1. 重算试算表\n2. 生成底稿\n3. 生成报表\n4. 生成附注\n\n确认执行？',
      '一键刷新全部',
      {
        confirmButtonText: '确认执行',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
  } catch {
    return // 用户取消
  }

  showChainProgress.value = true
  await chainExec.executeFullChain(projectYear.value)
}

/** 工作流步骤动作回调 */
function onStepAction(action: string) {
  // 由 WorkflowProgress 组件 emit，可扩展处理
}

// 清理 SSE 连接
onUnmounted(() => {
  chainExec.cleanup()
})
const loading = ref(false)
const wpProgress = ref<any>(null)
const overdue = ref<any[]>([])
const consistency = ref<any>(null)
const progressOption = ref<any>(null)
const teamOption = ref<any>(null)

// ── 催办相关状态 ──
const remindLimitTip = ref('')
// 记录每个底稿的催办次数（wp_id → count）
// NOTE: remindCounts 是前端 UI 优化缓存，刷新后丢失。
// 后端 429 响应是权威数据源（Redis 7 天窗口计数），前端仅用于即时禁用按钮。
// 无需从后端持久化加载——用户刷新页面后点催办，后端会再次返回 429 并同步计数。
const remindCounts = ref<Record<string, number>>({})

// ── 重新分配相关状态 ──
const showReassignDialog = ref(false)
const reassignTarget = ref<any>(null)

/** 判断催办按钮是否置灰 */
function isRemindDisabled(row: any): boolean {
  if (!row.wp_id) return true
  const count = remindCounts.value[row.wp_id] || 0
  return count >= 3
}

/** 催办按钮点击 */
async function onRemind(row: any) {
  if (!row.wp_id) {
    ElMessage.warning('该底稿暂无文件记录，无法催办')
    return
  }
  row._reminding = true
  try {
    const { data, status } = await http.post(
      P.workpapers.remind(projectId.value, row.wp_id),
      {},
      { validateStatus: (s: number) => s < 600 },
    )
    if (status === 429) {
      // 超限
      const detail = data?.detail
      const msg = typeof detail === 'object' ? detail.message : detail
      remindLimitTip.value = msg || '已连续催办 3 次，请考虑重新分配'
      remindCounts.value[row.wp_id] = 3
      ElMessage.warning(msg || '已连续催办 3 次，请考虑重新分配')
    } else if (status >= 400) {
      handleApiError({ response: { status, data } }, '催办')
    } else {
      // 成功
      if (data?.remind_count !== undefined) {
        remindCounts.value[row.wp_id] = data.remind_count
        ElMessage.success(`催办成功（第 ${data.remind_count} 次）`)
      } else {
        ElMessage.success('催办成功')
      }
    }
  } catch (err: any) {
    handleApiError(err, '催办')
  } finally {
    row._reminding = false
  }
}

/** 催办 3 次后升级到合伙人 */
async function onEscalateToPartner() {
  const overdueItems = overdue.value.filter((r: any) => (remindCounts.value[r.wp_id] || 0) >= 3)
  if (!overdueItems.length) {
    ElMessage.info('没有需要升级的底稿')
    return
  }
  try {
    await confirmEscalate('合伙人')
  } catch { return }
  try {
    await http.post(P.workpapers.escalateToPartner(projectId.value), {
      wp_ids: overdueItems.map((r: any) => r.wp_id),
      reason: '催办 3 次未响应',
    }, { validateStatus: (s: number) => s < 600 })
    ElMessage.success('已通知合伙人关注')
    remindLimitTip.value = ''
  } catch (e: any) {
    handleApiError(e, '升级')
  }
}

/** 重新分配按钮点击 */
function onReassign(row: any) {
  reassignTarget.value = row
  showReassignDialog.value = true
}

/** 重新分配确认回调 */
async function onReassignConfirm(staff: { user_id: string; staff_name: string }) {
  const row = reassignTarget.value
  if (!row) return

  // 使用 wp_id 或 wp_index_id 调用分配端点
  const wpId = row.wp_id || row.wp_index_id
  if (!wpId) {
    ElMessage.warning('该底稿暂无文件记录，无法重新分配')
    return
  }

  try {
    await http.put(
      P.workpapers.assign(projectId.value, wpId),
      { assigned_to: staff.user_id },
    )
    ElMessage.success(`已重新分配给 ${staff.staff_name}`)
    // 刷新列表
    refresh()
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : '重新分配失败，请重试'
    handleApiError(err, '操作')
  }
}

async function refresh() {
  loading.value = true
  try {
    const [wp, od, con, wh] = await Promise.all([
      getWorkpaperProgress(projectId.value).catch(() => null),
      getOverdueWorkpapers(projectId.value).catch(() => []),
      apiRunConsistencyCheck(projectId.value).catch(() => null),
      getProjectWorkHours(projectId.value).catch(() => []),
    ])
    wpProgress.value = wp
    overdue.value = Array.isArray(od) ? od.map((item: any) => ({ ...item, _reminding: false })) : []
    consistency.value = con
    if (wp) {
      const done = wp.done || 0, total = wp.total || 1
      progressOption.value = {
        series: [{ type: 'pie', radius: ['50%', '70%'], data: [
          { value: done, name: '已完成', itemStyle: { color: '#4b2d77' } },
          { value: total - done, name: '未完成', itemStyle: { color: '#e8e0f0' } },
        ]}],
      }
    }
    if (Array.isArray(wh) && wh.length) {
      teamOption.value = {
        xAxis: { type: 'category', data: wh.map((w: any) => w.staff_name) },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: wh.map((w: any) => w.total_hours), itemStyle: { color: '#4b2d77' } }],
      }
    }
  } finally { loading.value = false }
}
onMounted(refresh)
</script>
<style scoped>
.gt-proj-dash { padding: var(--gt-space-4); }
.gt-pd-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-pd-card { background: white; border-radius: var(--gt-radius-md); padding: 16px; box-shadow: var(--gt-shadow-sm); min-height: 240px; }
.gt-pd-card h4 { margin: 0 0 12px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-primary); }
.gt-pd-remind-tip { margin-top: 8px; }

/* ── 工作流进度条 + 一键刷新按钮 ── */
.gt-pd-workflow-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.gt-pd-workflow-bar > :first-child {
  flex: 1;
}
.gt-pd-refresh-all-btn {
  flex-shrink: 0;
  font-weight: 600;
}

/* ── 全链路执行进度面板 ── */
.gt-pd-chain-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--gt-color-bg);
  border: 1px solid var(--gt-color-border-light);
  border-radius: 8px;
  margin-bottom: 12px;
}
.gt-chain-steps {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.gt-chain-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  padding: 4px 10px;
  border-radius: 12px;
  transition: all 0.2s;
}
.gt-chain-step__icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
}
.gt-chain-step__label {
  font-size: var(--gt-font-size-sm);
}
.gt-chain-step__duration {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-left: 4px;
}
.gt-chain-step__error-hint {
  color: var(--gt-color-coral);
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
}

/* 步骤状态样式 */
.gt-chain-step--pending .gt-chain-step__icon { color: var(--gt-color-text-placeholder); }
.gt-chain-step--pending .gt-chain-step__label { color: var(--gt-color-info); }

.gt-chain-step--running {
  background: rgba(64, 158, 255, 0.08);
}
.gt-chain-step--running .gt-chain-step__icon { color: var(--gt-color-teal); }
.gt-chain-step--running .gt-chain-step__label { color: var(--gt-color-teal); font-weight: 500; }

.gt-chain-step--completed {
  background: rgba(103, 194, 58, 0.08);
}
.gt-chain-step--completed .gt-chain-step__icon { color: var(--gt-color-success); }
.gt-chain-step--completed .gt-chain-step__label { color: var(--gt-color-success); font-weight: 500; }

.gt-chain-step--failed {
  background: rgba(245, 108, 108, 0.08);
}
.gt-chain-step--failed .gt-chain-step__icon { color: var(--gt-color-coral); }
.gt-chain-step--failed .gt-chain-step__label { color: var(--gt-color-coral); font-weight: 500; }

.gt-chain-step--skipped .gt-chain-step__icon { color: var(--gt-color-wheat); }
.gt-chain-step--skipped .gt-chain-step__label { color: var(--gt-color-wheat); }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
