<template>
  <div class="gt-proj-dash gt-fade-in">
    <div class="gt-pd-header">
      <h2 class="gt-page-title">项目看板</h2>
      <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
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
            <div style="margin-top: 12px; font-size: 13px; color: #666">整体完成率：{{ wpProgress.rate }}%</div>
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
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import { confirmEscalate } from '@/utils/confirm'
import {
  getWorkpaperProgress, getOverdueWorkpapers,
  runConsistencyCheck as apiRunConsistencyCheck, getProjectWorkHours,
} from '@/services/commonApi'
import http from '@/utils/http'
import StaffSelectDialog from '@/components/assignment/StaffSelectDialog.vue'

use([PieChart, BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer])

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
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
      `/api/projects/${projectId.value}/workpapers/${row.wp_id}/remind`,
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
      const detail = data?.detail
      const msg = typeof detail === 'string' ? detail : '催办失败，请重试'
      ElMessage.error(msg)
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
    ElMessage.error('催办失败，请重试')
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
    await http.post(`/api/projects/${projectId.value}/workpapers/escalate-to-partner`, {
      wp_ids: overdueItems.map((r: any) => r.wp_id),
      reason: '催办 3 次未响应',
    }, { validateStatus: (s: number) => s < 600 })
    ElMessage.success('已通知合伙人关注')
    remindLimitTip.value = ''
  } catch {
    ElMessage.error('升级失败，请手动联系合伙人')
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
      `/api/projects/${projectId.value}/working-papers/${wpId}/assign`,
      { assigned_to: staff.user_id },
    )
    ElMessage.success(`已重新分配给 ${staff.staff_name}`)
    // 刷新列表
    refresh()
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : '重新分配失败，请重试'
    ElMessage.error(msg)
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
.gt-pd-card h4 { margin: 0 0 12px; font-size: 14px; color: #333; }
.gt-pd-remind-tip { margin-top: 8px; }
</style>
