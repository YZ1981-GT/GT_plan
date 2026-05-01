<template>
  <div class="gt-ack-dashboard gt-fade-in">
    <!-- 横幅 -->
    <div class="gt-page-banner gt-page-banner--purple">
      <div class="gt-page-banner__content">
        <h2 class="gt-page-banner__title">审计检查仪表盘</h2>
        <p class="gt-page-banner__desc">项目级审计检查汇总 · 按循环分组 · 通过率一览</p>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="gt-ack-summary">
      <div class="gt-ack-card">
        <span class="gt-ack-card-value">{{ totalChecks }}</span>
        <span class="gt-ack-card-label">总检查数</span>
      </div>
      <div class="gt-ack-card gt-ack-card--pass">
        <span class="gt-ack-card-value">{{ passedChecks }}</span>
        <span class="gt-ack-card-label">通过</span>
      </div>
      <div class="gt-ack-card gt-ack-card--fail">
        <span class="gt-ack-card-value">{{ failedChecks }}</span>
        <span class="gt-ack-card-label">未通过</span>
      </div>
      <div class="gt-ack-card gt-ack-card--pending">
        <span class="gt-ack-card-value">{{ pendingChecks }}</span>
        <span class="gt-ack-card-label">待验证</span>
      </div>
      <div class="gt-ack-card">
        <span class="gt-ack-card-value">{{ passRate }}%</span>
        <span class="gt-ack-card-label">通过率</span>
      </div>
    </div>

    <!-- 按循环分组 -->
    <div class="gt-ack-cycles" v-loading="loading">
      <div v-for="group in cycleGroups" :key="group.cycle" class="gt-ack-cycle-group">
        <div class="gt-ack-cycle-header" @click="group._open = !group._open">
          <span class="gt-ack-cycle-name">{{ group._open ? '▼' : '▶' }} {{ group.cycleName }}</span>
          <el-progress :percentage="group.passRate" :stroke-width="14" :text-inside="true" style="width:120px" />
          <span class="gt-ack-cycle-count">{{ group.passed }}/{{ group.total }}</span>
        </div>
        <div v-show="group._open" class="gt-ack-cycle-body">
          <div v-for="wp in group.workpapers" :key="wp.wp_code" class="gt-ack-wp-section">
            <div class="gt-ack-wp-title">
              <span>{{ wp.wp_code }} {{ wp.wp_name }}</span>
              <el-tag size="small" :type="wp.allPassed ? 'success' : 'warning'">
                {{ wp.passedCount }}/{{ wp.checks.length }}
              </el-tag>
            </div>
            <div v-for="chk in wp.checks" :key="chk.code" class="gt-ack-check-row"
              :class="{ 'gt-ack-check--pass': chk.passed === true, 'gt-ack-check--fail': chk.passed === false }">
              <span class="gt-ack-check-code">{{ chk.code }}</span>
              <span class="gt-ack-check-desc">{{ chk.description }}</span>
              <span class="gt-ack-check-severity">
                <el-tag :type="chk.severity === 'blocking' ? 'danger' : chk.severity === 'warning' ? 'warning' : 'info'" size="small">
                  {{ chk.severity }}
                </el-tag>
              </span>
              <span class="gt-ack-check-result">
                {{ chk.passed === true ? '✓' : chk.passed === false ? '✗' : '—' }}
              </span>
            </div>
          </div>
          <el-empty v-if="!group.workpapers.length" description="该循环暂无审计检查数据" />
        </div>
      </div>
      <el-empty v-if="!cycleGroups.length && !loading" description="暂无审计检查数据，请先对底稿执行精细化提取" />
    </div>

    <!-- 依赖关系图 -->
    <div style="margin-top:24px">
      <h3 style="font-size:15px;font-weight:600;color:#333;margin-bottom:12px">B→C→D 依赖关系</h3>
      <DependencyGraph :project-id="projectId" :cycle="selectedGraphCycle" />
      <div style="margin-top:8px">
        <el-radio-group v-model="selectedGraphCycle" size="small">
          <el-radio-button v-for="c in ['D','E','F','G','H','I','J','K','L','N']" :key="c" :value="c">{{ c }}</el-radio-button>
        </el-radio-group>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'
import http from '@/utils/http'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const selectedGraphCycle = ref('E')

interface CheckItem {
  code: string; type: string; severity: string; description: string;
  passed: boolean | null; message: string;
}

interface WpCheckGroup {
  wp_code: string; wp_name: string; checks: CheckItem[];
  passedCount: number; allPassed: boolean;
}

interface CycleGroup {
  cycle: string; cycleName: string; workpapers: WpCheckGroup[];
  total: number; passed: number; passRate: number; _open: boolean;
}

const cycleGroups = ref<CycleGroup[]>([])

const totalChecks = computed(() => cycleGroups.value.reduce((s, g) => s + g.total, 0))
const passedChecks = computed(() => cycleGroups.value.reduce((s, g) => s + g.passed, 0))
const failedChecks = computed(() => {
  let count = 0
  for (const g of cycleGroups.value) {
    for (const wp of g.workpapers) {
      count += wp.checks.filter(c => c.passed === false).length
    }
  }
  return count
})
const pendingChecks = computed(() => totalChecks.value - passedChecks.value - failedChecks.value)
const passRate = computed(() => totalChecks.value > 0 ? Math.round(passedChecks.value / totalChecks.value * 100) : 0)

const CYCLE_NAMES: Record<string, string> = {
  D: '收入循环', E: '货币资金', F: '存货循环', G: '投资循环',
  H: '固定资产', I: '无形资产', J: '职工薪酬', K: '管理循环',
  L: '债务循环', M: '权益循环', N: '税金循环', Q: '关联方',
}

async function loadDashboard() {
  loading.value = true
  try {
    // 获取项目所有底稿
    const { data: wps } = await http.get(`/api/projects/${projectId.value}/working-papers`, {
      validateStatus: (s: number) => s < 600,
    })
    const wpList = Array.isArray(wps) ? wps : wps?.data || []

    // 按循环分组
    const groupMap: Record<string, CycleGroup> = {}

    for (const wp of wpList) {
      const cycle = wp.audit_cycle || 'OTHER'
      if (!groupMap[cycle]) {
        groupMap[cycle] = {
          cycle, cycleName: CYCLE_NAMES[cycle] || cycle,
          workpapers: [], total: 0, passed: 0, passRate: 0, _open: false,
        }
      }

      // 尝试获取精细化检查结果
      try {
        const { data: extractResult } = await http.post(
          `/api/projects/${projectId.value}/workpapers/${wp.id}/fine-extract`,
          null,
          { validateStatus: (s: number) => s < 600, timeout: 5000 },
        )
        const checks: CheckItem[] = extractResult?.checks || []
        if (checks.length > 0) {
          const passedCount = checks.filter(c => c.passed === true).length
          groupMap[cycle].workpapers.push({
            wp_code: wp.wp_code, wp_name: wp.wp_name,
            checks, passedCount, allPassed: passedCount === checks.length,
          })
          groupMap[cycle].total += checks.length
          groupMap[cycle].passed += passedCount
        }
      } catch { /* 无精细化规则的底稿跳过 */ }
    }

    // 计算通过率
    for (const g of Object.values(groupMap)) {
      g.passRate = g.total > 0 ? Math.round(g.passed / g.total * 100) : 0
      if (g.workpapers.length > 0) g._open = true
    }

    cycleGroups.value = Object.values(groupMap)
      .filter(g => g.workpapers.length > 0)
      .sort((a, b) => a.cycle.localeCompare(b.cycle))
  } catch { cycleGroups.value = [] }
  finally { loading.value = false }
}

onMounted(loadDashboard)
</script>

<style scoped>
.gt-ack-dashboard { padding: var(--gt-space-4); }
.gt-ack-summary { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.gt-ack-card {
  background: #fff; border-radius: 8px; padding: 16px 24px; text-align: center;
  border: 1px solid #e8e4f0; min-width: 100px; flex: 1;
}
.gt-ack-card--pass { border-left: 3px solid #67c23a; }
.gt-ack-card--fail { border-left: 3px solid #e6a23c; }
.gt-ack-card--pending { border-left: 3px solid #909399; }
.gt-ack-card-value { display: block; font-size: 28px; font-weight: 800; color: #4b2d77; }
.gt-ack-card-label { display: block; font-size: 11px; color: #999; margin-top: 4px; }
.gt-ack-cycle-group { margin-bottom: 12px; border: 1px solid #e8e4f0; border-radius: 8px; overflow: hidden; }
.gt-ack-cycle-header {
  display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  background: #faf8fd; cursor: pointer; user-select: none;
}
.gt-ack-cycle-header:hover { background: #f0ecf5; }
.gt-ack-cycle-name { font-size: 14px; font-weight: 600; color: #333; min-width: 120px; }
.gt-ack-cycle-count { font-size: 12px; color: #999; }
.gt-ack-cycle-body { padding: 8px 16px; }
.gt-ack-wp-section { margin-bottom: 8px; }
.gt-ack-wp-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.gt-ack-check-row {
  display: flex; align-items: center; gap: 8px; padding: 3px 8px; font-size: 12px;
  border-radius: 4px; margin-bottom: 2px;
}
.gt-ack-check--pass { background: #f0f9eb; }
.gt-ack-check--fail { background: #fdf6ec; }
.gt-ack-check-code { font-weight: 600; color: #666; min-width: 80px; }
.gt-ack-check-desc { flex: 1; color: #333; }
.gt-ack-check-severity { min-width: 60px; }
.gt-ack-check-result { min-width: 20px; text-align: center; }
</style>
