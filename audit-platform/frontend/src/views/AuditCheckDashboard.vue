<template>
  <div class="gt-ack-dashboard gt-fade-in">
    <!-- 横幅 -->
    <GtPageHeader title="审计检查仪表盘" variant="banner" icon="✅" :show-back="false">
      <template #subtitle>
        项目级审计检查汇总 · 聚合精细化规则/审定勾稽等多源 · 按循环分组
      </template>
    </GtPageHeader>

    <!-- 工具栏：重新检查全部（编制权可见，进行中禁重复）+ 筛选 -->
    <div class="gt-ack-toolbar">
      <el-button
        v-if="canRecompute"
        type="primary"
        size="small"
        :loading="recomputingAll"
        :disabled="!!recomputingWp"
        @click="recomputeAll"
      >
        重新检查全部
      </el-button>
      <span v-if="canRecompute" class="gt-ack-toolbar-hint">聚合最新编制成果重新计算全部底稿检查项</span>
      <el-button
        v-if="canReview"
        type="success"
        size="small"
        :loading="signoffLoading"
        @click="doSignoff"
      >
        复核签认
      </el-button>
      <el-button
        v-if="canExport"
        size="small"
        :loading="exporting"
        @click="doExport"
      >
        导出
      </el-button>
      <el-radio-group v-model="filterMode" size="small" class="gt-ack-filter">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="failed">仅未通过</el-radio-button>
        <el-radio-button value="uncovered">仅未覆盖</el-radio-button>
        <el-radio-button value="blocking">仅阻断</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 汇总卡片（后端 summary 口径） -->
    <div class="gt-ack-summary">
      <div class="gt-ack-card">
        <span class="gt-ack-card-value">{{ summary.total }}</span>
        <span class="gt-ack-card-label">总检查数</span>
      </div>
      <div class="gt-ack-card gt-ack-card--pass">
        <span class="gt-ack-card-value">{{ summary.passed }}</span>
        <span class="gt-ack-card-label">通过</span>
      </div>
      <div class="gt-ack-card gt-ack-card--fail">
        <span class="gt-ack-card-value">{{ summary.failed }}</span>
        <span class="gt-ack-card-label">未通过</span>
      </div>
      <div class="gt-ack-card gt-ack-card--uncovered">
        <span class="gt-ack-card-value">{{ summary.uncovered }}</span>
        <span class="gt-ack-card-label">
          未覆盖
          <el-tooltip content="未执行/无法判定的检查项，不计入通过率分母" placement="top">
            <span class="gt-ack-hint">?</span>
          </el-tooltip>
        </span>
      </div>
      <div class="gt-ack-card gt-ack-card--rate">
        <span class="gt-ack-card-value">{{ passRateDisplay }}</span>
        <span class="gt-ack-card-label">
          已判定通过率
          <el-tooltip content="通过率 = 通过 ÷ 已判定；分母为已判定项，不含未覆盖项" placement="top">
            <span class="gt-ack-hint">?</span>
          </el-tooltip>
        </span>
        <span v-if="summary.pass_rate === null" class="gt-ack-card-sub">无已判定项</span>
      </div>
    </div>

    <!-- 最近一次复核签认状态（Req8） -->
    <div v-if="latestSignoff" class="gt-ack-signoff">
      <span class="gt-ack-signoff-label">最近复核签认：</span>
      <span class="gt-ack-signoff-by">{{ latestSignoff.signed_by_name || '—' }}</span>
      <span class="gt-ack-signoff-time">{{ fmtDateTime(latestSignoff.signed_at) }}</span>
      <el-tag
        size="small"
        :type="latestSignoff.blocking_present ? 'warning' : 'success'"
        effect="plain"
      >
        {{ latestSignoff.blocking_present ? '签认时存在未处理阻断项' : '签认时无阻断项' }}
      </el-tag>
      <span v-if="latestSignoff.note" class="gt-ack-signoff-note">备注：{{ latestSignoff.note }}</span>
    </div>
    <div v-else class="gt-ack-signoff gt-ack-signoff--none">尚无复核签认记录</div>

    <!-- 按循环分组 -->
    <div class="gt-ack-cycles" v-loading="loading">
      <div v-for="group in cycleGroups" :key="group.cycle" class="gt-ack-cycle-group">
        <div class="gt-ack-cycle-header" @click="group._open = !group._open">
          <span class="gt-ack-cycle-name">{{ group._open ? '▼' : '▶' }} {{ group.cycleName }}</span>
          <template v-if="group.decided > 0">
            <el-progress :percentage="group.passRate ?? 0" :stroke-width="14" :text-inside="true" style="width:120px" />
          </template>
          <span v-else class="gt-ack-cycle-norate">无已判定项</span>
          <span class="gt-ack-cycle-count">通过 {{ group.passed }}/{{ group.total }}</span>
          <span v-if="group.uncovered > 0" class="gt-ack-cycle-uncovered">未覆盖 {{ group.uncovered }}</span>
        </div>
        <div v-show="group._open" class="gt-ack-cycle-body">
          <template v-for="wp in group.workpapers" :key="wp.wp_code">
          <div v-if="filteredChecks(wp).length" class="gt-ack-wp-section">
            <div class="gt-ack-wp-title">
              <span class="gt-ack-wp-name">{{ wp.wp_code }} {{ wp.wp_name }}</span>
              <el-tag size="small" :type="wp.tagType">{{ wp.tagLabel }}</el-tag>
              <!-- 新鲜度标记 -->
              <el-tag v-if="wp.never_checked" size="small" type="info" effect="plain" class="gt-ack-fresh-tag">未检查</el-tag>
              <el-tag v-else-if="wp.stale" size="small" type="warning" effect="plain" class="gt-ack-fresh-tag">检查结果已过期</el-tag>
              <span v-if="wp.checked_at" class="gt-ack-wp-time">检查于 {{ fmtDateTime(wp.checked_at) }}</span>
              <el-button
                v-if="canRecompute"
                class="gt-ack-wp-recompute"
                size="small"
                text
                type="primary"
                :loading="recomputingWp === wp.wp_id"
                :disabled="recomputingAll || (recomputingWp !== null && recomputingWp !== wp.wp_id)"
                @click="recomputeWp(wp.wp_id)"
              >
                重新检查
              </el-button>
            </div>
            <div v-for="chk in filteredChecks(wp)" :key="chk.code" class="gt-ack-check-row"
              :class="{
                'gt-ack-check--pass': chk.passed === true,
                'gt-ack-check--fail': chk.passed === false,
                'gt-ack-check--jumpable': checkJumpable(chk, wp),
              }"
              @click="onCheckRowClick(chk, wp)">
              <span class="gt-ack-check-code">{{ chk.code }}</span>
              <el-tag class="gt-ack-check-source" size="small" effect="plain" :type="sourceMeta(chk.source).type">
                {{ sourceMeta(chk.source).label }}
              </el-tag>
              <span class="gt-ack-check-desc">{{ chk.description }}</span>
              <span class="gt-ack-check-severity">
                <el-tag :type="chk.severity === 'blocking' ? 'danger' : chk.severity === 'warning' ? 'warning' : 'info'" size="small">
                  {{ SEVERITY_LABELS[chk.severity] || chk.severity }}
                </el-tag>
              </span>
              <span class="gt-ack-check-result" :title="chk.message">
                {{ chk.passed === true ? '✓' : chk.passed === false ? '✗' : '—' }}
              </span>
              <!-- 定位（Req6.1/6.2）：可跳→定位按钮；不可跳→灰色提示不可点 -->
              <el-button
                v-if="checkJumpable(chk, wp)"
                class="gt-ack-check-locate"
                size="small"
                text
                type="primary"
                @click.stop="goToCheck(chk, wp)"
              >
                定位
              </el-button>
              <el-tooltip v-else :content="checkTooltip(chk, wp)" placement="top">
                <span class="gt-ack-check-nolocate">不可定位</span>
              </el-tooltip>
            </div>
          </div>
          </template>
          <el-empty v-if="!group.workpapers.length" description="该循环暂无检查数据" :image-size="60" />
          <div v-else-if="!groupHasVisible(group)" class="gt-ack-cycle-nomatch">当前筛选下无匹配项</div>
        </div>
      </div>
      <el-empty v-if="!cycleGroups.length && !loading" description="暂无审计检查数据，请先对底稿执行检查" />
    </div>

    <!-- 依赖关系图 -->
    <div style="margin-top:24px">
      <h3 style="font-size: var(--gt-font-size-base);font-weight:600;color: var(--gt-color-text-primary);margin-bottom:12px">B→C→D 依赖关系</h3>
      <DependencyGraph :project-id="projectId" :cycle="selectedGraphCycle" />
      <div style="margin-top:8px">
        <!-- 循环列表由实际有检查数据的循环动态生成（Req9.2，含 M，排除 OTHER/Q） -->
        <el-radio-group v-model="selectedGraphCycle" size="small">
          <el-radio-button v-for="c in graphCycles" :key="c" :value="c">{{ c }}</el-radio-button>
        </el-radio-group>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { downloadFile } from '@/utils/http'
import { fmtDateTime } from '@/utils/formatters'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import {
  type CheckFilterMode,
  resolveCheckJumpTarget,
  isCheckJumpable,
  jumpDisabledTooltip,
  matchesCheckFilter,
  sortChecksByPriority,
  deriveGraphCycles,
  resolveSelectedGraphCycle,
} from '@/utils/auditCheckJump'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const selectedGraphCycle = ref('E')

// ── 筛选（Req6.3）：全部 / 仅未通过 / 仅未覆盖 / 仅阻断 ──
const filterMode = ref<CheckFilterMode>('all')

// ── 重算入口权限门控（编制权，Req2.5；无权限隐藏重算按钮） ──
const { canDo } = usePermissionMatrix()
const canRecompute = computed(() => canDo('edit', 'workpaper'))
// ── 签认（复核权）/ 导出（导出权）门控（Req8.4 / Req7.4；无权限隐藏按钮） ──
const canReview = computed(() => canDo('review', 'workpaper'))
const canExport = computed(() => canDo('export', 'workpaper'))
const signoffLoading = ref(false)
const exporting = ref(false)

// ── 重算进行中状态（进行中禁重复触发） ──
const recomputingAll = ref(false)
const recomputingWp = ref<string | null>(null)

// ── 后端统一检查项（audit-checks/summary 项 dict 的超集） ──
interface CheckItem {
  code: string
  type?: string
  check_type?: string
  severity: string
  description: string
  passed: boolean | null
  message: string
  source: string
  wp_code?: string | null
  wp_id?: string | null
  sheet_hint?: string | null
}

// ── summary 端点每底稿行 ──
interface WpSummaryRow {
  wp_id: string
  wp_code: string
  wp_name: string
  audit_cycle: string | null
  checks: CheckItem[]
  checked_at: string | null
  updated_at: string | null
  stale: boolean
  never_checked: boolean
}

// ── 项目汇总 ──
interface ProjectSummary {
  total: number
  decided: number
  passed: number
  failed: number
  uncovered: number
  pass_rate: number | null
  blocking_open: number
}

interface WpCheckGroup {
  wp_code: string
  wp_name: string
  wp_id: string
  checks: CheckItem[]
  passedCount: number
  failedCount: number
  uncoveredCount: number
  decidedCount: number
  checked_at: string | null
  stale: boolean
  never_checked: boolean
  tagType: 'success' | 'warning' | 'danger' | 'info'
  tagLabel: string
}

interface CycleGroup {
  cycle: string
  cycleName: string
  workpapers: WpCheckGroup[]
  total: number
  passed: number
  failed: number
  uncovered: number
  decided: number
  passRate: number | null
  _open: boolean
}

const EMPTY_SUMMARY: ProjectSummary = {
  total: 0, decided: 0, passed: 0, failed: 0, uncovered: 0, pass_rate: null, blocking_open: 0,
}

const summary = ref<ProjectSummary>({ ...EMPTY_SUMMARY })
const cycleGroups = ref<CycleGroup[]>([])

// ── 最近一次复核签认（Req8） ──
interface SignoffInfo {
  id: string
  signed_by: string
  signed_by_name: string | null
  signed_at: string
  summary_snapshot: Record<string, unknown>
  blocking_present: boolean
  note: string | null
}
const latestSignoff = ref<SignoffInfo | null>(null)

// 已判定通过率展示：null → "—"（不显示 0% 全绿）；否则四舍五入百分比
const passRateDisplay = computed(() =>
  summary.value.pass_rate === null ? '—' : `${Math.round(summary.value.pass_rate * 100)}%`,
)

const CYCLE_NAMES: Record<string, string> = {
  D: '收入循环', E: '货币资金', F: '存货循环', G: '投资循环',
  H: '固定资产', I: '无形资产', J: '职工薪酬', K: '管理循环',
  L: '债务循环', M: '权益循环', N: '税金循环', Q: '关联方',
  OTHER: '其他',
}

const SEVERITY_LABELS: Record<string, string> = {
  blocking: '阻断', warning: '警告', info: '提示',
}

// 来源芯片：source → 中文标签 + 颜色（Req4.4）
const SOURCE_META: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'info' | 'danger' }> = {
  fine_rule: { label: '精细化规则', type: 'primary' },
  cycle_recon: { label: '审定勾稽', type: 'success' },
  note_validation: { label: '附注校验', type: 'warning' },
  qc: { label: 'QC', type: 'danger' },
  unadjusted_misstatement: { label: '未更正错报', type: 'danger' },
  tb_recon: { label: '审定↔TB', type: 'info' },
  adjustment_recon: { label: '调整勾稽', type: 'info' },
  report_cross_check: { label: '报表勾稽', type: 'info' },
  cross_sheet: { label: '跨表勾稽', type: 'info' },
}
function sourceMeta(s: string) {
  return SOURCE_META[s] || { label: s || '其他', type: 'info' as const }
}

function wpTag(passed: number, failed: number, uncovered: number, total: number): { tagType: WpCheckGroup['tagType']; tagLabel: string } {
  const label = `${passed}/${total}`
  if (failed > 0) return { tagType: 'warning', tagLabel: label }
  if (uncovered > 0) return { tagType: 'info', tagLabel: label }
  return { tagType: 'success', tagLabel: label }
}

async function loadDashboard() {
  loading.value = true
  try {
    const resp: { summary: ProjectSummary; workpapers: WpSummaryRow[] } = await api.get(
      P.auditChecks.summary(projectId.value),
      { validateStatus: (s: number) => s < 600 },
    )

    summary.value = { ...EMPTY_SUMMARY, ...(resp?.summary || {}) }

    // 按循环分组：从全部底稿（含无检查项者）建循环组，
    // 无检查数据的循环显式呈现"暂无检查数据"（不静默省略）
    const groupMap: Record<string, CycleGroup> = {}
    for (const wp of resp?.workpapers || []) {
      const cycle = wp.audit_cycle || 'OTHER'
      if (!groupMap[cycle]) {
        groupMap[cycle] = {
          cycle, cycleName: CYCLE_NAMES[cycle] || cycle,
          workpapers: [], total: 0, passed: 0, failed: 0, uncovered: 0,
          decided: 0, passRate: null, _open: false,
        }
      }
      const g = groupMap[cycle]
      // 未通过与阻断置顶排序（Req6.3，稳定排序同级保持原序）
      const checks: CheckItem[] = sortChecksByPriority(wp.checks || [])
      if (checks.length === 0) continue  // 无检查项底稿不进列表（其所在循环仍显示）

      const passedCount = checks.filter(c => c.passed === true).length
      const failedCount = checks.filter(c => c.passed === false).length
      const uncoveredCount = checks.filter(c => c.passed === null || c.passed === undefined).length
      const decidedCount = passedCount + failedCount
      const { tagType, tagLabel } = wpTag(passedCount, failedCount, uncoveredCount, checks.length)

      g.workpapers.push({
        wp_code: wp.wp_code, wp_name: wp.wp_name, wp_id: wp.wp_id, checks,
        passedCount, failedCount, uncoveredCount, decidedCount,
        checked_at: wp.checked_at, stale: wp.stale, never_checked: wp.never_checked,
        tagType, tagLabel,
      })
      g.total += checks.length
      g.passed += passedCount
      g.failed += failedCount
      g.uncovered += uncoveredCount
      g.decided += decidedCount
    }

    // 组内通过率（分母=已判定，不含未覆盖）；有数据的组默认展开
    for (const g of Object.values(groupMap)) {
      g.passRate = g.decided > 0 ? Math.round(g.passed / g.decided * 100) : null
      if (g.workpapers.length > 0) g._open = true
    }

    cycleGroups.value = Object.values(groupMap).sort((a, b) => a.cycle.localeCompare(b.cycle))
  } catch {
    summary.value = { ...EMPTY_SUMMARY }
    cycleGroups.value = []
  } finally {
    loading.value = false
  }
}

// ── 重算：调用 recompute 端点，完成后刷新面板 ──
function handleRecomputeResult(resp: any): boolean {
  if (resp?.status === 'in_progress') {
    ElMessage.warning(resp.message || '重算正在进行中，请稍后刷新')
    return false
  }
  const failed: Array<{ wp_id?: string; wp_code?: string; reason?: string }> = resp?.failed || []
  const recomputed = resp?.recomputed ?? 0
  if (failed.length > 0) {
    const detail = failed
      .slice(0, 3)
      .map(f => `${f.wp_code || f.wp_id || '?'}（${f.reason || '未知原因'}）`)
      .join('；')
    ElMessage.warning(
      `重算完成：${recomputed} 张成功，${failed.length} 张失败 — ${detail}${failed.length > 3 ? ' 等' : ''}`,
    )
  } else {
    ElMessage.success(`重算完成，共 ${recomputed} 张底稿`)
  }
  return true
}

async function recomputeAll() {
  if (recomputingAll.value || recomputingWp.value) return
  recomputingAll.value = true
  try {
    const resp: any = await api.post(P.auditChecks.recompute(projectId.value), {})
    handleRecomputeResult(resp)
    await loadDashboard()
  } catch {
    ElMessage.error('重新检查失败，请稍后重试')
  } finally {
    recomputingAll.value = false
  }
}

async function recomputeWp(wpId: string) {
  if (recomputingWp.value || recomputingAll.value) return
  recomputingWp.value = wpId
  try {
    const resp: any = await api.post(P.auditChecks.recompute(projectId.value), { wp_id: wpId })
    handleRecomputeResult(resp)
    await loadDashboard()
  } catch {
    ElMessage.error('重新检查失败，请稍后重试')
  } finally {
    recomputingWp.value = null
  }
}

// ── 筛选展示（Req6.3）：作用于每底稿 checks 展示（不改汇总卡/组进度=真实状态） ──
function filteredChecks(wp: WpCheckGroup): CheckItem[] {
  if (filterMode.value === 'all') return wp.checks
  return wp.checks.filter(c => matchesCheckFilter(c, filterMode.value))
}
function groupHasVisible(group: CycleGroup): boolean {
  return group.workpapers.some(wp => filteredChecks(wp).length > 0)
}

// ── 未通过项定位跳转（Req6.1/6.2）：复用 WorkpaperEditor 的 ?sheet= 定位机制 ──
function checkJumpable(chk: CheckItem, wp: WpCheckGroup): boolean {
  return isCheckJumpable(chk, wp)
}
function checkTooltip(chk: CheckItem, wp: WpCheckGroup): string {
  return jumpDisabledTooltip(chk, wp)
}
function goToCheck(chk: CheckItem, wp: WpCheckGroup): void {
  const target = resolveCheckJumpTarget(chk, wp)
  if (!target) {
    // 不静默失败、不跳错底稿（Req6.2）
    ElMessage.info(jumpDisabledTooltip(chk, wp))
    return
  }
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId: target.wpId },
    query: target.sheet ? { sheet: target.sheet } : {},
  })
}
function onCheckRowClick(chk: CheckItem, wp: WpCheckGroup): void {
  if (checkJumpable(chk, wp)) goToCheck(chk, wp)
}

// ── 依赖图循环动态生成（Req9.2）：由实际有检查数据的循环派生，含 M，排除 OTHER/Q ──
const graphCycles = computed<string[]>(() =>
  deriveGraphCycles(
    cycleGroups.value.filter(g => g.workpapers.length > 0).map(g => g.cycle),
  ),
)
// 选中循环随动态列表收敛：当前值不在列表则回退第一个
watch(
  graphCycles,
  (list) => {
    selectedGraphCycle.value = resolveSelectedGraphCycle(selectedGraphCycle.value, list)
  },
  { immediate: true },
)

// ── 复核签认（Req8）：有阻断项弹提示确认（只提示不阻断），确认后写签认 ──
async function loadSignoff() {
  try {
    const resp: { signoff: SignoffInfo | null } = await api.get(
      P.auditChecks.signoff(projectId.value),
      { validateStatus: (s: number) => s < 600 },
    )
    latestSignoff.value = resp?.signoff || null
  } catch {
    latestSignoff.value = null
  }
}

async function doSignoff() {
  if (signoffLoading.value) return
  // 有未处理阻断项 → 提示确认（只提示不阻断，P14），确认后继续签认
  const blockingOpen = summary.value.blocking_open
  try {
    if (blockingOpen > 0) {
      await ElMessageBox.confirm(
        `存在 ${blockingOpen} 项未处理阻断项，仍要签认吗？（签认将如实记录该状态，不会阻断）`,
        '复核签认确认',
        { type: 'warning', confirmButtonText: '仍要签认', cancelButtonText: '取消' },
      )
    } else {
      await ElMessageBox.confirm('确认对当前审计检查结果进行复核签认？', '复核签认确认', {
        type: 'info',
        confirmButtonText: '确认签认',
        cancelButtonText: '取消',
      })
    }
  } catch {
    return // 用户取消
  }

  signoffLoading.value = true
  try {
    const resp: any = await api.post(P.auditChecks.signoff(projectId.value), {})
    if (resp?.blocking_present) {
      ElMessage.warning(resp.message || '存在未处理阻断项，已记录签认（仅提示）')
    } else {
      ElMessage.success(resp?.message || '签认成功')
    }
    await loadSignoff()
  } catch {
    ElMessage.error('复核签认失败，请稍后重试')
  } finally {
    signoffLoading.value = false
  }
}

// ── 导出（Req7）：xlsx blob 下载（RFC5987 中文名由后端 Content-Disposition 提供） ──
async function doExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    await downloadFile(P.auditChecks.export(projectId.value), {
      method: 'post',
      fileName: '审计检查结果.xlsx',
    })
  } catch {
    ElMessage.error('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  loadDashboard()
  loadSignoff()
})
</script>

<style scoped>
.gt-ack-dashboard { padding: var(--gt-space-4); }
.gt-ack-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.gt-ack-toolbar-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ack-filter { margin-left: auto; }
.gt-ack-cycle-nomatch { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); padding: 8px 4px; }
.gt-ack-wp-recompute { margin-left: auto; font-weight: 400; }
.gt-ack-summary { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.gt-ack-signoff {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 8px 14px; margin-bottom: 16px; border-radius: 8px;
  background: var(--gt-color-bg-white); border: 1px solid var(--gt-color-border-purple);
  font-size: var(--gt-font-size-xs);
}
.gt-ack-signoff--none { color: var(--gt-color-text-tertiary); }
.gt-ack-signoff-label { color: var(--gt-color-text-secondary); font-weight: 600; }
.gt-ack-signoff-by { color: var(--gt-color-text-primary); font-weight: 500; }
.gt-ack-signoff-time { color: var(--gt-color-text-tertiary); }
.gt-ack-signoff-note { color: var(--gt-color-text-tertiary); }
.gt-ack-card {
  background: var(--gt-color-bg-white); border-radius: 8px; padding: 16px 24px; text-align: center;
  border: 1px solid var(--gt-color-border-purple); min-width: 100px; flex: 1;
}
.gt-ack-card--pass { border-left: 3px solid var(--gt-color-success); }
.gt-ack-card--fail { border-left: 3px solid var(--gt-color-wheat); }
.gt-ack-card--uncovered { border-left: 3px solid var(--gt-color-info); }
.gt-ack-card--rate { border-left: 3px solid var(--gt-color-primary); }
.gt-ack-card-value { display: block; font-size: var(--gt-font-size-3xl); font-weight: 800; color: var(--gt-color-primary); }
.gt-ack-card-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; }
.gt-ack-card-sub { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-ack-hint {
  display: inline-flex; align-items: center; justify-content: center;
  width: 13px; height: 13px; border-radius: 50%; margin-left: 2px;
  background: var(--gt-color-border-purple); color: var(--gt-color-text-secondary);
  font-size: 10px; cursor: help;
}
.gt-ack-cycle-group { margin-bottom: 12px; border: 1px solid var(--gt-color-border-purple); border-radius: 8px; overflow: hidden; }
.gt-ack-cycle-header {
  display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  background: var(--gt-color-primary-bg); cursor: pointer; user-select: none;
}
.gt-ack-cycle-header:hover { background: var(--gt-color-primary-bg); }
.gt-ack-cycle-name { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); min-width: 120px; }
.gt-ack-cycle-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-ack-cycle-uncovered { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.gt-ack-cycle-norate { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); width: 120px; }
.gt-ack-cycle-body { padding: 8px 16px; }
.gt-ack-wp-section { margin-bottom: 8px; }
.gt-ack-wp-title { display: flex; align-items: center; gap: 8px; font-size: var(--gt-font-size-sm); font-weight: 500; margin-bottom: 4px; flex-wrap: wrap; }
.gt-ack-wp-name { color: var(--gt-color-text-primary); }
.gt-ack-fresh-tag { font-weight: 400; }
.gt-ack-wp-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); font-weight: 400; }
.gt-ack-check-row {
  display: flex; align-items: center; gap: 8px; padding: 3px 8px; font-size: var(--gt-font-size-xs);
  border-radius: 4px; margin-bottom: 2px;
}
.gt-ack-check--pass { background: var(--gt-bg-success); }
.gt-ack-check--fail { background: var(--gt-bg-warning); }
.gt-ack-check--jumpable { cursor: pointer; }
.gt-ack-check--jumpable:hover { background: var(--gt-color-primary-bg); }
.gt-ack-check-code { font-weight: 600; color: var(--gt-color-text-secondary); min-width: 80px; }
.gt-ack-check-source { flex-shrink: 0; }
.gt-ack-check-desc { flex: 1; color: var(--gt-color-text-primary); }
.gt-ack-check-severity { min-width: 60px; }
.gt-ack-check-result { min-width: 20px; text-align: center; cursor: help; }
.gt-ack-check-locate { flex-shrink: 0; font-weight: 400; }
.gt-ack-check-nolocate { flex-shrink: 0; font-size: 11px; color: var(--gt-color-text-tertiary); cursor: not-allowed; }
</style>
