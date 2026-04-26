<template>
  <div class="partner-dashboard">
    <div class="gt-page-banner gt-page-banner--dark">
      <div class="gt-banner-content">
        <h2>🏛️ 合伙人看板</h2>
        <span class="gt-banner-sub" v-if="overview">
          {{ overview.total_projects }} 个项目 · {{ overview.risk_alert_count }} 个风险预警 · {{ overview.pending_sign_count }} 个待签字
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="loadAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 风险预警横幅 -->
    <el-alert v-if="overview && overview.risk_alert_count > 0" type="warning" :closable="false" style="margin-bottom: 16px">
      <template #title>
        ⚠️ {{ overview.risk_alert_count }} 个项目存在风险预警
      </template>
      <div v-for="a in overview.risk_alerts" :key="a.id" style="margin-top: 4px; font-size: 13px">
        <span style="font-weight: 600">{{ a.client_name || a.name }}</span>：{{ a.risk_reasons.join('、') }}
      </div>
    </el-alert>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 项目总览 -->
      <el-tab-pane label="项目总览" name="projects">
        <el-table :data="overview?.projects || []" stripe v-loading="loading" @row-click="onProjectClick" style="cursor: pointer">
          <el-table-column label="风险" width="60" align="center">
            <template #default="{ row }">
              <span :class="'gt-risk-dot gt-risk-dot--' + row.risk_level" />
            </template>
          </el-table-column>
          <el-table-column label="客户" prop="client_name" width="160" />
          <el-table-column label="项目" prop="name" min-width="180" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="完成率" width="130">
            <template #default="{ row }">
              <el-progress :percentage="row.completion_rate" :stroke-width="6"
                :color="row.completion_rate >= 80 ? '#67c23a' : row.completion_rate >= 50 ? '#e6a23c' : '#f56c6c'" />
            </template>
          </el-table-column>
          <el-table-column label="底稿" width="80" align="center">
            <template #default="{ row }">{{ row.wp_passed }}/{{ row.wp_total }}</template>
          </el-table-column>
          <el-table-column label="待复核" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.wp_pending > 0 ? '#e6a23c' : '#999' }">{{ row.wp_pending }}</span>
            </template>
          </el-table-column>
          <el-table-column label="退回" width="60" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.wp_rejected > 0 ? '#f56c6c' : '#999' }">{{ row.wp_rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click.stop="goToProject(row.id)">进入</el-button>
              <el-button size="small" link @click.stop="checkSign(row.id)">签字检查</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 待签字 -->
      <el-tab-pane name="sign">
        <template #label>
          待签字
          <el-badge v-if="overview?.pending_sign_count" :value="overview.pending_sign_count" type="danger" style="margin-left: 4px" />
        </template>
        <div v-if="overview?.pending_sign?.length" class="sign-list">
          <div v-for="p in overview.pending_sign" :key="p.id" class="sign-card" @click="checkSign(p.id)">
            <div class="sign-card-left">
              <div class="sign-card-name">{{ p.client_name || p.name }}</div>
              <div class="sign-card-meta">完成率 {{ p.completion_rate }}% · {{ p.wp_passed }}/{{ p.wp_total }} 底稿通过</div>
            </div>
            <el-button type="primary" size="small" round>签字前检查 →</el-button>
          </div>
        </div>
        <el-empty v-else description="暂无待签字项目" />
      </el-tab-pane>

      <!-- Tab 3: 团队效能 -->
      <el-tab-pane label="团队效能" name="team">
        <div v-if="teamData" class="gt-team-summary">
          <div class="gt-team-stat" v-for="s in teamStats" :key="s.label">
            <div class="gt-team-stat-num">{{ s.value }}</div>
            <div class="gt-team-stat-label">{{ s.label }}</div>
          </div>
        </div>
        <el-table :data="teamData?.staff_metrics || []" stripe v-loading="teamLoading">
          <el-table-column label="人员" prop="user_name" width="120" />
          <el-table-column label="底稿数" prop="total" width="80" align="center" />
          <el-table-column label="通过" prop="passed" width="60" align="center" />
          <el-table-column label="退回" width="60" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.rejected > 0 ? '#f56c6c' : '#999' }">{{ row.rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="通过率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.pass_rate" :stroke-width="6"
                :color="row.pass_rate >= 80 ? '#67c23a' : row.pass_rate >= 50 ? '#e6a23c' : '#f56c6c'" />
            </template>
          </el-table-column>
          <el-table-column label="退回率" width="80" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.reject_rate > 10 ? '#f56c6c' : '#999' }">{{ row.reject_rate }}%</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 签字前检查弹窗 -->
    <el-dialog v-model="showSignDialog" title="🖊️ 签字前检查" width="600" append-to-body>
      <div v-if="signResult">
        <div class="gt-check-status" :class="signResult.ready_to_sign ? 'gt-check-status--pass' : 'gt-check-status--fail'">
          {{ signResult.ready_to_sign ? '✅ 满足签字条件' : '⚠️ 尚未满足签字条件' }}
          <span class="gt-check-score">{{ signResult.passed_count }}/{{ signResult.total_checks }}</span>
        </div>
        <div class="gt-check-list">
          <div v-for="c in signResult.checks" :key="c.id" class="gt-check-item">
            <span class="gt-check-icon">{{ c.passed ? '✅' : '❌' }}</span>
            <div>
              <div class="gt-check-label">{{ c.label }}</div>
              <div class="gt-check-detail">{{ c.detail }}</div>
            </div>
          </div>
        </div>
      </div>
      <div v-else v-loading="signLoading" style="min-height: 100px" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getPartnerOverview, getSignReadiness, getTeamEfficiency,
  type PartnerOverview, type SignReadiness, type TeamEfficiency,
} from '@/services/partnerApi'

const router = useRouter()
const loading = ref(false)
const activeTab = ref('projects')

const overview = ref<PartnerOverview | null>(null)
const teamData = ref<TeamEfficiency | null>(null)
const teamLoading = ref(false)
const signResult = ref<SignReadiness | null>(null)
const signLoading = ref(false)
const showSignDialog = ref(false)

const teamStats = computed(() => {
  const s = teamData.value?.summary
  if (!s) return []
  return [
    { label: '团队人数', value: s.total_staff },
    { label: '底稿总数', value: s.total_workpapers },
    { label: '平均通过率', value: s.avg_pass_rate + '%' },
    { label: '平均退回率', value: s.avg_reject_rate + '%' },
    { label: '人均底稿', value: s.avg_per_person },
  ]
})

function statusLabel(s: string) {
  const m: Record<string, string> = { created: '已创建', planning: '计划中', execution: '执行中', completion: '完成中', reporting: '报告中', archived: '已归档' }
  return m[s] || s
}
function statusType(s: string) {
  if (s === 'archived') return 'success'
  if (s === 'execution') return ''
  if (s === 'reporting' || s === 'completion') return 'warning'
  return 'info'
}

function goToProject(pid: string) {
  router.push(`/projects/${pid}/progress-board`)
}
function onProjectClick(row: any) {
  goToProject(row.id)
}

async function checkSign(pid: string) {
  showSignDialog.value = true
  signResult.value = null
  signLoading.value = true
  try { signResult.value = await getSignReadiness(pid) }
  catch { ElMessage.error('检查失败') }
  finally { signLoading.value = false }
}

async function loadAll() {
  loading.value = true
  try { overview.value = await getPartnerOverview() } catch { ElMessage.error('加载失败') }
  finally { loading.value = false }
  teamLoading.value = true
  try { teamData.value = await getTeamEfficiency() } catch {}
  finally { teamLoading.value = false }
}

onMounted(loadAll)
</script>

<style scoped>
.partner-dashboard { padding: 0; }
.sign-list { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.sign-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-4) var(--gt-space-5); background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  cursor: pointer; transition: all var(--gt-transition-fast);
  border: 1px solid var(--gt-color-border-light);
}
.sign-card:hover { box-shadow: var(--gt-shadow-md); border-color: rgba(75,45,119,0.08); }
.sign-card-name { font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text); }
.sign-card-meta { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; }
</style>
