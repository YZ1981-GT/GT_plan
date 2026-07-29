<template>
  <div class="gt-wp-matrix">
    <!-- 顶部工具栏 -->
    <div class="gt-wp-matrix-toolbar">
      <div class="gt-wp-matrix-stats">
        <div class="gt-wp-matrix-stat-cell">
          <div class="gt-wp-matrix-stat-num">{{ totalSummary.total }}</div>
          <div class="gt-wp-matrix-stat-label">底稿总数</div>
        </div>
        <div class="gt-wp-matrix-stat-cell">
          <div class="gt-wp-matrix-stat-num gt-success">{{ totalSummary.assigned }}</div>
          <div class="gt-wp-matrix-stat-label">{{ mode === 'reviewer' ? '已配复核' : '已委派' }}</div>
        </div>
        <div class="gt-wp-matrix-stat-cell">
          <div class="gt-wp-matrix-stat-num gt-warning">{{ totalSummary.unassigned }}</div>
          <div class="gt-wp-matrix-stat-label">{{ mode === 'reviewer' ? '缺复核人' : '未委派' }}</div>
        </div>
        <el-tooltip :content="completedTooltip" placement="top">
          <div class="gt-wp-matrix-stat-cell">
            <div class="gt-wp-matrix-stat-num">{{ totalSummary.completed }}</div>
            <div class="gt-wp-matrix-stat-label">已完成 ⓘ</div>
          </div>
        </el-tooltip>
        <el-tooltip content="编制人 = 复核人的底稿数，违反职责分离/独立性，建议为这些底稿调整复核人" placement="top">
          <div class="gt-wp-matrix-stat-cell" :class="{ 'is-conflict': selfReviewConflict > 0 }">
            <div class="gt-wp-matrix-stat-num" :class="{ 'gt-warning': selfReviewConflict > 0 }">{{ selfReviewConflict }}</div>
            <div class="gt-wp-matrix-stat-label">自审冲突 ⓘ</div>
          </div>
        </el-tooltip>
      </div>
      <div class="gt-wp-matrix-filters">
        <el-segmented v-model="mode" :options="modeOptions" size="small" />
        <span class="gt-wp-matrix-filter-label">循环：</span>
        <el-select
          v-model="cycleFilter"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="全部循环"
          clearable
          size="small"
          style="width: 150px"
        >
          <el-option
            v-for="c in allCycles"
            :key="c"
            :label="`${c} ${CYCLE_NAMES[c] || ''}`"
            :value="c"
          />
        </el-select>
        <span class="gt-wp-matrix-filter-label">成员：</span>
        <el-select
          v-model="memberFilter"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="全部成员"
          clearable
          size="small"
          style="width: 200px"
        >
          <el-option
            v-for="m in members"
            :key="m.id"
            :label="m.full_name || m.username || m.id"
            :value="m.id"
          />
        </el-select>
        <el-checkbox v-model="highlightUnassigned" size="small">高亮未分配</el-checkbox>
        <el-tooltip content="隐藏未参与编制/复核的管理员、只读、EQCR 等空行，使人均与负载统计更真实" placement="top">
          <el-checkbox v-model="hideIdleNonComposers" size="small">隐藏未参与成员</el-checkbox>
        </el-tooltip>
        <el-tooltip
          v-if="canAssign"
          content="把全部未分配底稿一次送入委派弹窗，选多名候选人 + “均匀轮询/智能推荐”策略即可均衡分配"
          placement="top"
        >
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="unassignedByCycle.totalUnassigned === 0"
            @click="onBalanceAssign"
          >
            ⚖ 均衡分配（{{ unassignedByCycle.totalUnassigned }}）
          </el-button>
        </el-tooltip>
        <el-button size="small" @click="exportMatrix">导出</el-button>
      </div>
    </div>

    <!-- 负载均衡提示 -->
    <div v-if="matrixRows.length > 0" class="gt-wp-matrix-loadhint">
      <span>人均 <strong>{{ loadStats.avg }}</strong> 张</span>
      <span class="gt-wp-matrix-loadhint-sep">·</span>
      <span>最多 {{ loadStats.maxName }} <strong>{{ loadStats.max }}</strong></span>
      <span class="gt-wp-matrix-loadhint-sep">·</span>
      <span>最少 {{ loadStats.minName }} <strong>{{ loadStats.min }}</strong></span>
      <span v-if="!canAssign" class="gt-wp-matrix-loadhint-ro">（当前角色仅可查看，委派需项目经理/合伙人）</span>
    </div>

    <!-- 矩阵表格 -->
    <div class="gt-wp-matrix-table-wrap">
      <el-table
        :data="matrixRows"
        border
        size="small"
        max-height="calc(100vh - 280px)"
        class="gt-wp-matrix-table"
      >
        <el-table-column label="审计人员" prop="member_name" width="160" fixed="left">
          <template #default="{ row }">
            <div class="gt-wp-matrix-member">
              <div class="gt-wp-matrix-member-name">{{ row.member_name }}</div>
              <div class="gt-wp-matrix-member-role">{{ row.member_role }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column
          v-for="cycle in cycleColumns"
          :key="cycle"
          :label="cycle"
          align="center"
          min-width="90"
        >
          <template #header>
            <div class="gt-wp-matrix-col-header">
              <div class="gt-wp-matrix-col-cycle">{{ cycle }}</div>
              <div class="gt-wp-matrix-col-name">{{ CYCLE_NAMES[cycle] || '' }}</div>
              <div class="gt-wp-matrix-col-total">共 {{ cycleTotals[cycle] || 0 }}</div>
            </div>
          </template>
          <template #default="{ row }">
            <div
              class="gt-wp-matrix-cell"
              :class="cellClass(row.cells[cycle])"
              :title="cellTitle(row.cells[cycle])"
              @click="onCellClick(row, cycle)"
            >
              <template v-if="row.cells[cycle].assigned > 0">
                <div class="gt-wp-matrix-cell-num">
                  <strong>{{ row.cells[cycle].assigned }}</strong>
                  <span class="gt-wp-matrix-cell-divider">/</span>
                  <span class="gt-wp-matrix-cell-total">{{ row.cells[cycle].cycle_total }}</span>
                </div>
                <el-progress
                  :percentage="row.cells[cycle].progress"
                  :stroke-width="3"
                  :show-text="false"
                  :color="row.cells[cycle].progress === 100 ? 'var(--gt-color-success)' : 'var(--gt-color-primary)'"
                />
                <div class="gt-wp-matrix-cell-meta">
                  完成 {{ row.cells[cycle].completed }}
                </div>
              </template>
              <span v-else class="gt-wp-matrix-cell-empty">—</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="个人合计" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <div class="gt-wp-matrix-row-total" :class="{ 'is-overloaded': isOverloaded(row) }">
              <strong>{{ row.total_assigned }}</strong>
              <el-tag v-if="isOverloaded(row)" type="warning" size="small" effect="plain">偏高</el-tag>
              <el-progress
                v-if="row.total_assigned > 0"
                :percentage="row.total_progress"
                :stroke-width="4"
                :show-text="false"
              />
              <div class="gt-wp-matrix-cell-meta">完成 {{ row.total_completed }}</div>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底部"未分配"摘要行 -->
      <div v-if="unassignedByCycle.totalUnassigned > 0" class="gt-wp-matrix-unassigned">
        <span class="gt-wp-matrix-unassigned-label">⚠ 未分配 {{ unassignedByCycle.totalUnassigned }} 个底稿：</span>
        <el-tag
          v-for="(count, cycle) in unassignedByCycle.byCycle"
          :key="cycle"
          type="warning"
          size="small"
          style="margin-right: 4px; cursor: pointer"
          @click="onUnassignedClick(cycle as string)"
        >
          {{ cycle }}: {{ count }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessageBox } from 'element-plus'

interface WpItem {
  id: string
  wp_code?: string
  wp_name?: string
  status: string
  assigned_to?: string | null
  reviewer?: string | null
  audit_cycle?: string
  wp_index_id?: string
}

interface Member {
  id: string
  username?: string
  full_name?: string
  role?: string
}

const props = withDefaults(defineProps<{
  projectId: string
  workpapers: WpItem[]
  members: Member[]
  /** 是否允许发起委派（非项目经理/合伙人时为只读矩阵）；缺省可委派，实际由父级按角色传入 */
  canAssign?: boolean
  /** 项目名，用于导出文件名归档 */
  projectName?: string
}>(), { canAssign: true, projectName: '' })

const emit = defineEmits<{
  'cell-click': [payload: { member_id: string; cycle: string }]
  // 委派动作统一改为"请求打开委派弹窗"，由父级弹出 BatchAssignDialog 让用户确认范围+选人+走 enhanced 端点发通知
  // 不再直接携带 member_id 触发无确认的批量 POST（避免误点灾难/甩给错人/委派不通知）
  'open-assign': [payload: { wp_ids: string[] }]
}>()

void props.projectId

const CYCLE_ORDER = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'A', 'S']
const CYCLE_NAMES: Record<string, string> = {
  A: '完成', B: '风评', C: '控测',
  D: '收入', E: '资金', F: '存货', G: '投资',
  H: '固资', I: '无形', J: '薪酬',
  K: '管费', L: '债务', M: '权益', N: '税金', S: '特定',
}

const COMPLETED_STATUSES = new Set(['edit_complete', 'pending_review', 'reviewed', 'review_passed', 'archived', 'level1_passed', 'level2_passed'])

// 通常不承担底稿编制的角色：当其在当前维度下 0 分配时，视为"占位空行"可隐藏（避免拉低人均/污染负载统计）
// 审计员即使 0 分配也保留（是待委派对象）；这些角色一旦真被分配（total>0）也保留
const IDLE_HIDE_ROLES = new Set(['admin', 'readonly', 'eqcr'])

const memberFilter = ref<string[]>([])
const cycleFilter = ref<string[]>([])
const highlightUnassigned = ref(true)
const hideIdleNonComposers = ref(true)

// 维度：编制人(assigned_to) / 复核人(reviewer)
const mode = ref<'assignee' | 'reviewer'>('assignee')
const modeOptions = [
  { label: '编制人', value: 'assignee' },
  { label: '复核人', value: 'reviewer' },
]

const canAssign = computed(() => props.canAssign !== false)

/** 按当前维度取底稿归属人 */
function ownerOf(w: WpItem): string | null | undefined {
  return mode.value === 'reviewer' ? w.reviewer : w.assigned_to
}

const completedTooltip = computed(() =>
  mode.value === 'reviewer'
    ? '已完成 = 已配复核人 且 底稿状态达到编制完成/复核通过/归档等（与个人合计口径一致）'
    : '已完成 = 已委派 且 底稿状态 ∈ 编制完成/待复核/已复核/已通过/已归档（与个人合计口径一致）'
)

// 计算每个循环的总底稿数
const cycleTotals = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {}
  for (const w of props.workpapers) {
    const cycle = (w.wp_code || w.audit_cycle || '?')[0] || '?'
    totals[cycle] = (totals[cycle] || 0) + 1
  }
  return totals
})

// 有底稿的全部循环（供筛选下拉）
const allCycles = computed(() =>
  CYCLE_ORDER.filter(c => (cycleTotals.value[c] || 0) > 0)
)

// 出现的循环列（受循环筛选影响）
const cycleColumns = computed(() =>
  cycleFilter.value.length > 0
    ? allCycles.value.filter(c => cycleFilter.value.includes(c))
    : allCycles.value
)

// 矩阵行：成员 × 循环
interface MatrixCell {
  assigned: number
  completed: number
  cycle_total: number
  progress: number
  wp_ids: string[]
}

interface MatrixRow {
  member_id: string
  member_name: string
  member_role: string
  _role?: string
  cells: Record<string, MatrixCell>
  total_assigned: number
  total_completed: number
  total_progress: number
}

const allMatrixRows = computed<MatrixRow[]>(() => {
  const visibleMembers = memberFilter.value.length > 0
    ? props.members.filter(m => memberFilter.value.includes(m.id))
    : props.members

  return visibleMembers.map(m => {
    const cells: Record<string, MatrixCell> = {}
    let totalAssigned = 0
    let totalCompleted = 0

    for (const cycle of cycleColumns.value) {
      const cycleWps = props.workpapers.filter(w => {
        const c = (w.wp_code || w.audit_cycle || '?')[0]
        return c === cycle
      })
      const assignedWps = cycleWps.filter(w => ownerOf(w) === m.id)
      const completedWps = assignedWps.filter(w => COMPLETED_STATUSES.has(w.status))
      const cell: MatrixCell = {
        assigned: assignedWps.length,
        completed: completedWps.length,
        cycle_total: cycleWps.length,
        progress: assignedWps.length > 0
          ? Math.round((completedWps.length / assignedWps.length) * 100)
          : 0,
        wp_ids: assignedWps.map(w => w.id),
      }
      cells[cycle] = cell
      totalAssigned += cell.assigned
      totalCompleted += cell.completed
    }

    return {
      member_id: m.id,
      member_name: m.full_name || m.username || m.id,
      member_role: roleLabel(m.role),
      _role: m.role,
      cells,
      total_assigned: totalAssigned,
      total_completed: totalCompleted,
      total_progress: totalAssigned > 0
        ? Math.round((totalCompleted / totalAssigned) * 100)
        : 0,
    }
  })
})

// 隐藏"未参与的管理/只读成员"占位空行：非编制角色 且 当前维度 0 分配
const matrixRows = computed<MatrixRow[]>(() => {
  if (!hideIdleNonComposers.value) return allMatrixRows.value
  return allMatrixRows.value.filter(
    r => !(IDLE_HIDE_ROLES.has(r._role || '') && r.total_assigned === 0)
  )
})

function roleLabel(r?: string): string {
  return ({
    auditor: '审计员',
    manager: '经理',
    partner: '合伙人',
    qc: '质控',
    eqcr: 'EQCR',
    admin: '管理员',
    readonly: '只读',
  } as Record<string, string>)[r || ''] || (r || '')
}

// 整体统计（按当前维度）
const totalSummary = computed(() => {
  const total = props.workpapers.length
  const assigned = props.workpapers.filter(w => !!ownerOf(w)).length
  // 与个人合计/单元格口径一致：已分配（当前维度有归属人）且状态达完成
  const completed = props.workpapers.filter(w => !!ownerOf(w) && COMPLETED_STATUSES.has(w.status)).length
  return { total, assigned, unassigned: total - assigned, completed }
})

// 自审冲突：编制人与复核人为同一人（违反职责分离/独立性），与维度无关，恒定义
const selfReviewConflict = computed(() =>
  props.workpapers.filter(w => !!w.assigned_to && !!w.reviewer && w.assigned_to === w.reviewer).length
)

// 负载均衡（基于当前可见成员的个人合计）
const loadStats = computed(() => {
  const rows = matrixRows.value
  if (!rows.length) return { avg: 0, max: 0, min: 0, maxName: '-', minName: '-' }
  const sum = rows.reduce((a, r) => a + r.total_assigned, 0)
  const avg = Math.round((sum / rows.length) * 10) / 10
  let maxR = rows[0]
  let minR = rows[0]
  for (const r of rows) {
    if (r.total_assigned > maxR.total_assigned) maxR = r
    if (r.total_assigned < minR.total_assigned) minR = r
  }
  return { avg, max: maxR.total_assigned, min: minR.total_assigned, maxName: maxR.member_name, minName: minR.member_name }
})

function isOverloaded(row: MatrixRow): boolean {
  return loadStats.value.avg > 0 && row.total_assigned > loadStats.value.avg * 1.5
}

/** 单元格 hover 下钻：列出该格已分配底稿编号 */
function cellTitle(cell: MatrixCell): string {
  if (!cell.wp_ids.length) return ''
  const codes = props.workpapers
    .filter(w => cell.wp_ids.includes(w.id))
    .map(w => w.wp_code || w.id)
  return `底稿：${codes.join('、')}`
}

/** 导出矩阵为 Excel（客户端 SheetJS） */
async function exportMatrix() {
  const XLSX = await import('xlsx')
  const header = [
    '审计人员', '角色',
    ...cycleColumns.value.map(c => `${c} ${CYCLE_NAMES[c] || ''}`),
    '个人合计', '已完成',
  ]
  const body = matrixRows.value.map(r => [
    r.member_name, r.member_role,
    ...cycleColumns.value.map(c => `${r.cells[c].assigned}/${r.cells[c].cycle_total}`),
    r.total_assigned, r.total_completed,
  ])
  const sheetLabel = mode.value === 'reviewer' ? '复核委派矩阵' : '编制委派矩阵'
  const ws = XLSX.utils.aoa_to_sheet([header, ...body])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, sheetLabel)
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const fname = [sheetLabel, (props.projectName || '').trim(), stamp].filter(Boolean).join('_') + '.xlsx'
  XLSX.writeFile(wb, fname)
}

/** 一键均衡：把当前可见循环内全部未分配底稿一次送入委派弹窗，用户选多人+"均匀轮询/智能推荐"策略即均衡 */
function onBalanceAssign() {
  if (!canAssign.value) return
  const visibleCycles = new Set(cycleColumns.value)
  const wpIds = props.workpapers
    .filter(w => {
      if (ownerOf(w)) return false
      const c = (w.wp_code || w.audit_cycle || '?')[0] || '?'
      return visibleCycles.has(c)
    })
    .map(w => w.id)
  if (wpIds.length > 0) {
    emit('open-assign', { wp_ids: wpIds })
  }
}

// 未分配统计（按当前维度 + 受循环筛选影响）
const unassignedByCycle = computed(() => {
  const byCycle: Record<string, number> = {}
  let totalUnassigned = 0
  const visibleCycles = new Set(cycleColumns.value)
  for (const w of props.workpapers) {
    if (!ownerOf(w)) {
      const c = (w.wp_code || w.audit_cycle || '?')[0] || '?'
      if (!visibleCycles.has(c)) continue
      byCycle[c] = (byCycle[c] || 0) + 1
      totalUnassigned += 1
    }
  }
  return { byCycle, totalUnassigned }
})

function cellClass(cell: MatrixCell): Record<string, boolean> {
  return {
    'is-empty': cell.assigned === 0,
    'is-unassigned-warning': highlightUnassigned.value && cell.assigned === 0 && cell.cycle_total > 0,
    'is-complete': cell.assigned > 0 && cell.progress === 100,
    'is-active': cell.assigned > 0 && cell.progress < 100,
    'is-readonly': !canAssign.value,
  }
}

async function onCellClick(row: MatrixRow, cycle: string) {
  const cell = row.cells[cycle]
  emit('cell-click', { member_id: row.member_id, cycle })
  if (!canAssign.value) return // 无委派权限：仅查看
  if (cell.wp_ids.length > 0) {
    // 已委派单元格 → 改派。改派已完成底稿会变更归属并影响已完成成果，先甄别提示
    const completedIds = new Set(
      props.workpapers
        .filter(w => cell.wp_ids.includes(w.id) && COMPLETED_STATUSES.has(w.status))
        .map(w => w.id)
    )
    const pendingIds = cell.wp_ids.filter(id => !completedIds.has(id))
    if (completedIds.size > 0) {
      try {
        await ElMessageBox.confirm(
          `该单元格含 ${completedIds.size} 张已完成底稿。改派会变更其归属并可能影响已完成成果。`,
          '改派确认',
          {
            confirmButtonText: '全部改派',
            cancelButtonText: pendingIds.length > 0 ? '仅改派未完成' : '取消',
            type: 'warning',
            distinguishCancelAndClose: true,
          }
        )
        emit('open-assign', { wp_ids: cell.wp_ids }) // 确认 → 全部改派
      } catch (action) {
        // cancel = 仅改派未完成；close/ESC = 取消不动作
        if (action === 'cancel' && pendingIds.length > 0) {
          emit('open-assign', { wp_ids: pendingIds })
        }
      }
      return
    }
    emit('open-assign', { wp_ids: cell.wp_ids })
    return
  }
  if (cell.cycle_total > 0) {
    // 该循环有底稿但未分配 → 取该循环未分配底稿，打开委派弹窗（不再直接甩给该成员）
    const unassignedWps = props.workpapers.filter(w => {
      const c = (w.wp_code || w.audit_cycle || '?')[0]
      return c === cycle && !ownerOf(w)
    })
    if (unassignedWps.length > 0) {
      emit('open-assign', { wp_ids: unassignedWps.map(w => w.id) })
    }
  }
}

function onUnassignedClick(cycle: string) {
  if (!canAssign.value) return
  const wpIds = props.workpapers
    .filter(w => {
      const c = (w.wp_code || w.audit_cycle || '?')[0]
      return c === cycle && !ownerOf(w)
    })
    .map(w => w.id)
  if (wpIds.length > 0) {
    // 打开委派弹窗让用户选人，不再默认甩给 members[0]
    emit('open-assign', { wp_ids: wpIds })
  }
}
</script>

<style scoped>
.gt-wp-matrix {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
}

/* 顶部工具栏 — KPI 卡片式 */
.gt-wp-matrix-toolbar {
  background: var(--gt-color-bg-white);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.gt-wp-matrix-stats {
  display: flex;
  gap: 8px;
}
.gt-wp-matrix-stat-cell {
  text-align: center;
  padding: 8px 16px;
  background: var(--gt-color-bg, #fafafa);
  border-radius: 8px;
  border: 1px solid var(--gt-color-border-light, #f0f0f0);
  min-width: 70px;
}
.gt-wp-matrix-stat-cell.is-conflict {
  background: #fff0f0;
  border-color: #f89898;
}
.gt-wp-matrix-stat-num {
  font-size: 20px;
  font-weight: 800;
  color: var(--gt-color-primary);
  line-height: 1.2;
}
.gt-wp-matrix-stat-num.gt-success {
  color: var(--gt-color-success);
}
.gt-wp-matrix-stat-num.gt-warning {
  color: var(--gt-color-coral);
}
.gt-wp-matrix-stat-label {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
  margin-top: 2px;
}

.gt-wp-matrix-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-wp-matrix-filter-label {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
}

/* 负载均衡提示 */
.gt-wp-matrix-loadhint {
  font-size: 12px;
  color: var(--gt-color-text-secondary);
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-wp-matrix-loadhint strong {
  color: var(--gt-color-primary);
}
.gt-wp-matrix-loadhint-sep {
  color: var(--gt-color-text-placeholder);
}
.gt-wp-matrix-loadhint-ro {
  color: var(--gt-color-coral, #e65100);
}

/* 矩阵表格区 */
.gt-wp-matrix-table-wrap {
  flex: 1;
  background: var(--gt-color-bg-white);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  padding: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.gt-wp-matrix-table {
  flex: 1;
}

.gt-wp-matrix-member {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-wp-matrix-member-name {
  font-weight: 600;
  color: var(--gt-color-text-primary);
  font-size: var(--wp-font-size, 13px);
}
.gt-wp-matrix-member-role {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
}

.gt-wp-matrix-col-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.gt-wp-matrix-col-cycle {
  font-weight: 700;
  color: var(--gt-color-primary);
  font-size: 14px;
}
.gt-wp-matrix-col-name {
  font-size: 11px;
  color: var(--gt-color-text-secondary);
}
.gt-wp-matrix-col-total {
  font-size: 10px;
  color: var(--gt-color-text-tertiary);
}

.gt-wp-matrix-cell {
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: all 0.15s;
  min-height: 56px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: var(--gt-color-bg, #fafafa);
  border: 1px solid transparent;
}
.gt-wp-matrix-cell:hover {
  background: var(--gt-color-primary-bg, #f8f5ff);
  border-color: var(--gt-color-primary);
}
.gt-wp-matrix-cell.is-unassigned-warning {
  background: #fff8e1;
  border: 1px dashed #ffb74d;
}
.gt-wp-matrix-cell.is-complete {
  background: #e8f5e9;
  border-color: #a5d6a7;
}

.gt-wp-matrix-cell-num {
  display: flex;
  align-items: baseline;
  gap: 2px;
  font-size: var(--gt-font-size-sm);
}
.gt-wp-matrix-cell-num strong {
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-md);
  font-weight: 700;
}
.gt-wp-matrix-cell-divider {
  color: var(--gt-color-text-tertiary);
}
.gt-wp-matrix-cell-total {
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
}
.gt-wp-matrix-cell-meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-wp-matrix-cell-empty {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}

.gt-wp-matrix-row-total {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.gt-wp-matrix-row-total strong {
  font-size: var(--gt-font-size-md);
  color: var(--gt-color-primary);
}
.gt-wp-matrix-row-total.is-overloaded strong {
  color: var(--gt-color-coral, #e65100);
}

/* 只读态单元格（无委派权限） */
.gt-wp-matrix-cell.is-readonly {
  cursor: default;
}
.gt-wp-matrix-cell.is-readonly:hover {
  background: var(--gt-color-bg, #fafafa);
  border-color: transparent;
}

.gt-wp-matrix-unassigned {
  margin-top: 10px;
  padding: 10px 14px;
  background: #fff8e1;
  border-radius: 8px;
  border: 1px solid #ffe082;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.gt-wp-matrix-unassigned-label {
  color: #e65100;
  font-weight: 600;
}

:deep(.gt-wp-matrix-table .el-table__body td) {
  padding: 4px 0;
}
:deep(.gt-wp-matrix-table .el-table__body td .cell) {
  padding: 0 4px;
}
</style>
