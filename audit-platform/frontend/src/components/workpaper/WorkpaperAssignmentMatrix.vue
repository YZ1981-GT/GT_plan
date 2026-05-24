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
          <div class="gt-wp-matrix-stat-label">已委派</div>
        </div>
        <div class="gt-wp-matrix-stat-cell">
          <div class="gt-wp-matrix-stat-num gt-warning">{{ totalSummary.unassigned }}</div>
          <div class="gt-wp-matrix-stat-label">未委派</div>
        </div>
        <div class="gt-wp-matrix-stat-cell">
          <div class="gt-wp-matrix-stat-num">{{ totalSummary.completed }}</div>
          <div class="gt-wp-matrix-stat-label">已完成</div>
        </div>
      </div>
      <div class="gt-wp-matrix-filters">
        <span class="gt-wp-matrix-filter-label">筛选成员：</span>
        <el-select
          v-model="memberFilter"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="全部成员"
          clearable
          size="small"
          style="width: 240px"
        >
          <el-option
            v-for="m in members"
            :key="m.id"
            :label="m.full_name || m.username || m.id"
            :value="m.id"
          />
        </el-select>
        <el-checkbox v-model="highlightUnassigned" size="small">高亮未分配</el-checkbox>
      </div>
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
            <div class="gt-wp-matrix-row-total">
              <strong>{{ row.total_assigned }}</strong>
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

interface WpItem {
  id: string
  wp_code?: string
  wp_name?: string
  status: string
  assigned_to?: string | null
  audit_cycle?: string
  wp_index_id?: string
}

interface Member {
  id: string
  username?: string
  full_name?: string
  role?: string
}

const props = defineProps<{
  projectId: string
  workpapers: WpItem[]
  members: Member[]
}>()

const emit = defineEmits<{
  'cell-click': [payload: { member_id: string; cycle: string }]
  'assign': [payload: { wp_ids: string[]; member_id: string }]
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

const memberFilter = ref<string[]>([])
const highlightUnassigned = ref(true)

// 计算每个循环的总底稿数
const cycleTotals = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {}
  for (const w of props.workpapers) {
    const cycle = (w.wp_code || w.audit_cycle || '?')[0] || '?'
    totals[cycle] = (totals[cycle] || 0) + 1
  }
  return totals
})

// 出现的循环列（仅显示有底稿的）
const cycleColumns = computed(() =>
  CYCLE_ORDER.filter(c => (cycleTotals.value[c] || 0) > 0)
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
  cells: Record<string, MatrixCell>
  total_assigned: number
  total_completed: number
  total_progress: number
}

const matrixRows = computed<MatrixRow[]>(() => {
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
      const assignedWps = cycleWps.filter(w => w.assigned_to === m.id)
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
      cells,
      total_assigned: totalAssigned,
      total_completed: totalCompleted,
      total_progress: totalAssigned > 0
        ? Math.round((totalCompleted / totalAssigned) * 100)
        : 0,
    }
  })
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

// 整体统计
const totalSummary = computed(() => {
  const total = props.workpapers.length
  const assigned = props.workpapers.filter(w => !!w.assigned_to).length
  const completed = props.workpapers.filter(w => COMPLETED_STATUSES.has(w.status)).length
  return { total, assigned, unassigned: total - assigned, completed }
})

// 未分配统计（按循环）
const unassignedByCycle = computed(() => {
  const byCycle: Record<string, number> = {}
  let totalUnassigned = 0
  for (const w of props.workpapers) {
    if (!w.assigned_to) {
      const c = (w.wp_code || w.audit_cycle || '?')[0] || '?'
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
  }
}

function onCellClick(row: MatrixRow, cycle: string) {
  const cell = row.cells[cycle]
  emit('cell-click', { member_id: row.member_id, cycle })
  if (cell.wp_ids.length > 0) {
    emit('assign', { wp_ids: cell.wp_ids, member_id: row.member_id })
  } else if (cell.cycle_total > 0) {
    // 该循环有底稿但未分配给该成员，发起委派
    const unassignedWps = props.workpapers.filter(w => {
      const c = (w.wp_code || w.audit_cycle || '?')[0]
      return c === cycle && !w.assigned_to
    })
    if (unassignedWps.length > 0) {
      emit('assign', { wp_ids: unassignedWps.map(w => w.id), member_id: row.member_id })
    }
  }
}

function onUnassignedClick(cycle: string) {
  const wpIds = props.workpapers
    .filter(w => {
      const c = (w.wp_code || w.audit_cycle || '?')[0]
      return c === cycle && !w.assigned_to
    })
    .map(w => w.id)
  if (wpIds.length > 0 && props.members.length > 0) {
    // 默认选第一个 member 让用户在弹窗里改
    emit('assign', { wp_ids: wpIds, member_id: props.members[0].id })
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
  font-size: 13px;
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

.gt-wp-matrix-unassigned {
  margin-top: 10px;
  padding: 10px 14px;
  background: #fff8e1;
  border-radius: 8px;
  border: 1px solid #ffe082;
  font-size: 13px;
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
