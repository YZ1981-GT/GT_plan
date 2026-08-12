<template>
  <div class="gt-dst">
    <!-- ── 降级标注：未做风险匹配（显著位置，不塞 tooltip） ── -->
    <el-alert
      v-if="suggestion.degraded"
      type="warning"
      show-icon
      :closable="false"
      class="gt-dst__alert"
    >
      <template #title>
        <span class="gt-dst__alert-title">未做风险匹配</span>
      </template>
      <div class="gt-dst__alert-body">
        本项目 B50 认定层次风险评估不可用，以下建议<strong>仅按加权负载均衡</strong>分配，
        未按风险等级匹配执行人资历。高风险领域是否由资历足够的人员承担，需人工逐行复核。
      </div>
    </el-alert>

    <!-- ── warnings：算法如实暴露的判据缺口（独立区块） ── -->
    <el-alert
      v-if="suggestion.warnings.length > 0"
      type="info"
      show-icon
      :closable="false"
      class="gt-dst__alert"
    >
      <template #title>
        <span class="gt-dst__alert-title">建议生成提示（{{ suggestion.warnings.length }} 条）</span>
      </template>
      <ul class="gt-dst__warn-list">
        <li v-for="(w, i) in suggestion.warnings" :key="i">{{ w }}</li>
      </ul>
    </el-alert>

    <!-- ── 未能分配的目标（不硬塞，须人工处置） ── -->
    <div v-if="suggestion.unassignedTargets.length > 0" class="gt-dst__block">
      <div class="gt-dst__block-title">
        未能分配（{{ suggestion.unassignedTargets.length }} 张）
        <span class="gt-dst__block-hint">
          把高风险底稿分给资历不足的人比不分配更坏，故算法不硬塞；请加派人员或经项目负责人评估后调整。
        </span>
      </div>
      <el-table :data="suggestion.unassignedTargets" size="small" class="gt-dst__table">
        <el-table-column label="底稿" width="110">
          <template #default="{ row }">{{ row.wpCode || row.wpIndexId }}</template>
        </el-table-column>
        <el-table-column label="循环" width="70" align="center">
          <template #default="{ row }">{{ row.cycle || '—' }}</template>
        </el-table-column>
        <el-table-column label="风险" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTagType(row.risk)">{{ riskLabel(row.risk) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="未分配原因" min-width="260">
          <template #default="{ row }">{{ row.reason }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ── 建议分配表（底稿粒度，逐行可改可移除） ── -->
    <div class="gt-dst__block">
      <div class="gt-dst__block-title">
        建议分配（{{ rows.length }} 张底稿）
        <span class="gt-dst__block-hint">
          执行人与复核人均可逐行改；复核人下拉已排除本行执行人（不相容职务分离）。
        </span>
      </div>

      <el-table :data="rows" size="small" class="gt-dst__table" row-key="wpIndexId">
        <el-table-column label="底稿" width="110">
          <template #default="{ row }">
            <span class="gt-dst__wp">{{ row.wpCode || row.wpIndexId }}</span>
          </template>
        </el-table-column>

        <el-table-column label="循环" width="66" align="center">
          <template #default="{ row }">{{ row.cycle || '—' }}</template>
        </el-table-column>

        <el-table-column label="风险" width="88" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTagType(row.risk)">{{ riskLabel(row.risk) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="权重" width="72" align="right">
          <template #default="{ row }">
            <el-tooltip placement="top" :content="weightTip(row)">
              <span class="gt-dst__num gt-dst__formula">{{ fmt2(row.weight) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column :label="TERM_ASSIGNEE" min-width="170">
          <template #default="{ row }">
            <el-select
              v-model="row.assigneeStaffId"
              size="small"
              filterable
              class="gt-dst__select"
              @change="onAssigneeChange(row)"
            >
              <el-option
                v-for="m in members"
                :key="m.staffId"
                :label="memberOptionLabel(m)"
                :value="m.staffId"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column :label="TERM_REVIEWER" min-width="170">
          <template #default="{ row }">
            <el-select
              v-model="row.reviewerStaffId"
              size="small"
              filterable
              clearable
              placeholder="未指派"
              class="gt-dst__select"
              @change="emitChange"
            >
              <el-option
                v-for="m in reviewerOptions(row)"
                :key="m.staffId"
                :label="memberOptionLabel(m)"
                :value="m.staffId"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="112" align="center">
          <template #default="{ row }">
            <el-tag v-if="rowIssue(row) === 'seniority'" size="small" type="danger">资历不足</el-tag>
            <el-tag v-else-if="rowIssue(row) === 'no_reviewer'" size="small" type="warning">缺复核人</el-tag>
            <el-tag v-else-if="row._edited" size="small" type="warning">已调整</el-tag>
            <el-tag v-else size="small" type="success">按建议</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="分配依据" min-width="120">
          <template #default="{ row }">
            <el-tooltip placement="top" :content="rationaleOf(row)">
              <span class="gt-dst__rationale">{{ rationaleOf(row) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="72" align="center">
          <template #default="{ row, $index }">
            <el-button size="small" link type="danger" @click="removeRow($index)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="rows.length === 0" class="gt-dst__empty">
        建议分配表为空（全部行已被移除，或算法未产生任何可分配建议）。
      </div>
    </div>

    <!-- ── 应用前负载对比（不均衡一眼可见） ── -->
    <div class="gt-dst__block">
      <div class="gt-dst__block-title">
        应用前负载对比
        <span class="gt-dst__block-hint">
          分配前取后端口径的在办任务数；负载未知的成员不补 0（0 会被误读为这个人很空闲）。
        </span>
      </div>
      <div class="gt-dst__loads">
        <div v-for="b in loadBoard" :key="b.staffId" class="gt-dst__load-row">
          <div class="gt-dst__load-name">
            {{ b.name }}
            <span class="gt-dst__load-role">{{ b.seniorityLabel }}</span>
          </div>
          <div class="gt-dst__load-bar">
            <div class="gt-dst__load-track">
              <div class="gt-dst__load-fill gt-dst__load-fill--before" :style="barStyle(b.before)"></div>
            </div>
            <div class="gt-dst__load-track">
              <div class="gt-dst__load-fill gt-dst__load-fill--after" :style="barStyle(b.after)"></div>
            </div>
          </div>
          <div class="gt-dst__load-text">
            <template v-if="b.before === null">
              <span class="gt-dst__unknown">负载未知</span>
              <span class="gt-dst__delta">本次 +{{ fmt2(b.increment) }}</span>
            </template>
            <template v-else>
              <span class="gt-dst__num">{{ fmt2(b.before) }}</span>
              <span class="gt-dst__arrow">→</span>
              <span class="gt-dst__num gt-dst__num--after">{{ fmt2(b.after as number) }}</span>
              <span v-if="b.increment > 0" class="gt-dst__delta">+{{ fmt2(b.increment) }}</span>
            </template>
          </div>
        </div>
        <div v-if="loadBoard.length === 0" class="gt-dst__empty">项目组成员清单为空。</div>
      </div>
      <div v-if="unknownLoadNames" class="gt-dst__unknown-note">
        以下成员当前负载未知，其建议须先确认在手任务量后再采用：{{ unknownLoadNames }}
      </div>
    </div>

    <div class="gt-dst__footer">
      <span class="gt-dst__footer-stat">
        待应用 {{ rows.length }} 张 · 执行人 {{ distinctAssigneeCount }} 人 ·
        缺复核人 {{ noReviewerCount }} 张 · 资历不足 {{ seniorityIssueCount }} 张
      </span>
      <el-button
        size="small"
        type="primary"
        :disabled="rows.length === 0"
        @click="emitApply"
      >应用建议分配</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 建议分配表（只读渲染 + 逐行编辑 + emit 上报；**组件自身不发请求、不写库**）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 18
 * 守卫: `__tests__/delegationSuggestionTable.spec.ts`
 * _Requirements: 11.1, 11.6, 11.8_
 *
 * ## 职责边界（三条，均有守卫）
 *
 * 1. **零 IO**：本组件不 import `http` / `commonApi`，不调 `preview` / `apply`。
 *    建议结果由宿主算好后经 props 传入，用户编辑经 emit 上报，落库归 Task 19 的
 *    既有 `previewProcedureDelegation` → `applyProcedureDelegation` 两阶段。
 *    把请求塞进展示组件会让「委派写入路径唯一」（Property 28）无法用源码级判据钉死。
 * 2. **负载未知不补 0**：`loadAfter` 只含负载已知的成员（见
 *    `composables/delegationSuggestion.ts` 模块文档），故本组件的「分配前」直接取
 *    `members[].currentLoad`，`null` 一律渲染成「负载未知」+ 本次增量，**绝不显示 0**。
 *    0 会被审计师读成「这个人很空闲」，进而把工作堆给恰好取数失败的那个人。
 * 3. **SOD 由构造保证**：复核人下拉**排除本行执行人**，用户无法在 UI 上造出
 *    执行人 = 复核人。后端 `assert_sod_distinct` 在 preview / apply 两侧逐 task
 *    双查仍是权威，此处是第一道而非唯一一道。
 *
 * ## 负载对比条为何按**编辑后**的行重算
 *
 * `suggestion.loadAfter` 是算法在**原始建议**下的结果。用户改了执行人或移除了行之后，
 * 若仍显示算法给的 `loadAfter`，屏幕上的「分配后负载」就与表格里实际要应用的分配
 * 不一致 —— 而这块面板的唯一用途正是「应用前看清不均衡」。故 `loadBoard` 按
 * `rows` 现值重算增量：`after = currentLoad + Σ(本人承担的行权重)`。
 *
 * 口径一致性：`currentLoad` 是后端下发的非终态任务数，`weight` 是
 * `computeTargetWeight` 的加权工作量，两者相加与 `suggestion.loadAfter` 同一把尺子
 * （算法内部也是 `baseLoad + assignedWeight`）。**复核工作量不计入**，与算法一致。
 */
import { ref, computed, watch } from 'vue'
import {
  RISK_MIN_SENIORITY,
  RISK_COEFFICIENT,
  ROW_COUNT_DIVISOR,
  type DelegationSuggestionResult,
  type DelegationAssignment,
  type DelegationMember,
  type RiskLevel,
} from '../composables/delegationSuggestion'
import { seniorityLabel } from '../composables/delegationSeniority'

/** 表格行 = 建议条 + 编辑痕迹（`_edited` 仅用于 UI 标注，不参与写入）。 */
interface EditableRow extends DelegationAssignment {
  _edited: boolean
  _suggestedAssigneeStaffId: string
}

/** 按执行人分组的应用载荷（Task 19 消费；selector 用底稿粒度 `kind: 'workpaper'`）。 */
export interface DelegationApplyGroup {
  assigneeStaffId: string
  assigneeName: string
  reviewerStaffId: string | null
  selector: { kind: 'workpaper'; wp_index_ids: string[] }
  wpCodes: string[]
}

const props = defineProps<{
  suggestion: DelegationSuggestionResult
  members: DelegationMember[]
}>()

const emit = defineEmits<{
  (e: 'change', rows: DelegationAssignment[]): void
  (e: 'apply', groups: DelegationApplyGroup[], rows: DelegationAssignment[]): void
}>()

// 术语与裁剪页保持一致（避免同一概念两个叫法）
const TERM_ASSIGNEE = '程序执行人'
const TERM_REVIEWER = '操作复核人'

const rows = ref<EditableRow[]>([])

/**
 * props → 本地可编辑副本。
 *
 * 🔴 深拷贝而非引用：直接改 props 里的对象会让宿主的 `suggestion` 被就地改写，
 * 于是「重新生成建议」拿不回算法原值，`_suggestedAssigneeStaffId`（用于判断
 * 「已调整」）也会随之漂移。
 */
watch(
  () => props.suggestion,
  (s) => {
    const list = Array.isArray(s?.assignments) ? s.assignments : []
    rows.value = list.map((a) => ({
      ...a,
      _edited: false,
      _suggestedAssigneeStaffId: a.assigneeStaffId,
    }))
  },
  { immediate: true, deep: false },
)

const memberById = computed(() => {
  const m = new Map<string, DelegationMember>()
  for (const x of props.members || []) m.set(x.staffId, x)
  return m
})

function memberOptionLabel(m: DelegationMember): string {
  const load = m.currentLoad === null ? '负载未知' : `在办 ${m.currentLoad}`
  return `${m.name}（${seniorityLabel(m.seniority)} · ${load}）`
}

/** 复核人候选：排除本行执行人（SOD 由构造保证），并要求资历不低于执行人。 */
function reviewerOptions(row: EditableRow): DelegationMember[] {
  const assignee = memberById.value.get(row.assigneeStaffId)
  const floor = assignee ? assignee.seniority : 0
  return (props.members || []).filter(
    (m) => m.staffId !== row.assigneeStaffId && m.seniority >= floor,
  )
}

function riskLabel(risk: RiskLevel): string {
  if (risk === 'H') return '高风险'
  if (risk === 'M') return '中风险'
  if (risk === 'L') return '低风险'
  return '未评估'
}

function riskTagType(risk: RiskLevel): 'danger' | 'warning' | 'success' | 'info' {
  if (risk === 'H') return 'danger'
  if (risk === 'M') return 'warning'
  if (risk === 'L') return 'success'
  return 'info'
}

function fmt2(v: number): string {
  return Number.isFinite(v) ? v.toFixed(2) : '—'
}

/** 权重公式溯源（与 `computeTargetWeight` 同一组常量，不另写死数值）。 */
function weightTip(row: EditableRow): string {
  const key = row.risk === 'H' || row.risk === 'M' || row.risk === 'L' ? row.risk : 'none'
  const coefficient = RISK_COEFFICIENT[key]
  return `加权工作量 = 1（底稿基数）+ ${coefficient.toFixed(1)}（${riskLabel(row.risk)}系数）`
    + ` + 行数/${ROW_COUNT_DIVISOR}`
}

/**
 * 行状态：资历不足 > 缺复核人 > 已调整 > 按建议。
 *
 * 「资历不足」只在**人工改过执行人**后才可能出现 —— 算法本身不会产出不达门槛的
 * 分配（不达标的目标会进 `unassignedTargets`）。降级模式下不判资历（风险值不可信，
 * 拿它判等于假装做了风险匹配）。
 */
function rowIssue(row: EditableRow): 'seniority' | 'no_reviewer' | null {
  if (!props.suggestion.degraded) {
    const m = memberById.value.get(row.assigneeStaffId)
    const key = row.risk === 'H' || row.risk === 'M' || row.risk === 'L' ? row.risk : 'none'
    if (m && m.seniority < RISK_MIN_SENIORITY[key]) return 'seniority'
  }
  if (!row.reviewerStaffId) return 'no_reviewer'
  return null
}

/** 逐行分配依据：算法 `rationale` + 人工调整后的补充说明。 */
function rationaleOf(row: EditableRow): string {
  if (!row._edited) return row.rationale
  const m = memberById.value.get(row.assigneeStaffId)
  const key = row.risk === 'H' || row.risk === 'M' || row.risk === 'L' ? row.risk : 'none'
  const required = RISK_MIN_SENIORITY[key]
  const who = m ? `${m.name}（${seniorityLabel(m.seniority)}）` : row.assigneeStaffId
  const verdict = m && m.seniority < required && !props.suggestion.degraded
    ? `资历低于${riskLabel(row.risk)}要求（要求资历 ≥ ${required}），须经项目负责人评估`
    : '资历满足该风险等级要求'
  return `已人工调整为 ${who}：${verdict}。原系统建议：${row.rationale}`
}

function onAssigneeChange(row: EditableRow) {
  row._edited = row.assigneeStaffId !== row._suggestedAssigneeStaffId
  // 改执行人后原复核人可能与新执行人同一人 → 立即清空，避免落库前才被后端拒
  if (row.reviewerStaffId && row.reviewerStaffId === row.assigneeStaffId) {
    row.reviewerStaffId = null
    row.reviewerName = null
  }
  emitChange()
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
  emitChange()
}

/**
 * 负载看板（按**编辑后**的行重算，见组件文档）。
 *
 * `before === null` ⇒ 负载未知，此时 `after` 亦为 `null`（不拿 0 当基线凑一个
 * 看起来像绝对值的数），只暴露本次增量。
 */
const loadBoard = computed(() => {
  const increments = new Map<string, number>()
  for (const r of rows.value) {
    increments.set(r.assigneeStaffId, (increments.get(r.assigneeStaffId) ?? 0) + r.weight)
  }
  return (props.members || []).map((m) => {
    const increment = increments.get(m.staffId) ?? 0
    const before = m.currentLoad
    return {
      staffId: m.staffId,
      name: m.name,
      seniorityLabel: seniorityLabel(m.seniority),
      before,
      after: before === null ? null : before + increment,
      increment,
    }
  })
})

/** 条形图刻度：取当前最大「分配后」值，全未知时退化为增量最大值。 */
const barMax = computed(() => {
  let max = 0
  for (const b of loadBoard.value) {
    max = Math.max(max, b.after ?? b.increment)
  }
  return max > 0 ? max : 1
})

function barStyle(value: number | null): Record<string, string> {
  if (value === null) return { width: '0%' }
  const pct = Math.min(100, (value / barMax.value) * 100)
  return { width: `${pct}%` }
}

const unknownLoadNames = computed(() =>
  (props.members || [])
    .filter((m) => m.currentLoad === null)
    .map((m) => m.name)
    .join('、'),
)

const distinctAssigneeCount = computed(
  () => new Set(rows.value.map((r) => r.assigneeStaffId)).size,
)
const noReviewerCount = computed(() => rows.value.filter((r) => !r.reviewerStaffId).length)
const seniorityIssueCount = computed(
  () => rows.value.filter((r) => rowIssue(r) === 'seniority').length,
)

/** 剥掉 UI 私有字段，只上报写入所需的行集。 */
function plainRows(): DelegationAssignment[] {
  return rows.value.map(({ _edited, _suggestedAssigneeStaffId, ...rest }) => rest)
}

function emitChange() {
  emit('change', plainRows())
}

/**
 * 按执行人分组的应用载荷。
 *
 * 后端 `procedure_delegation_service` 的 preview/apply 一次只接**一个**
 * `assignee_staff_id`，故多执行人必须分组多次 preview/apply（Task 19 逐组执行并
 * 汇总结果）。selector 用 `kind: 'workpaper'` + `wp_index_ids`。
 *
 * 🔴 `wp_index_ids` 必须是 `wp_index.id`（本行的 `wpIndexId`，取数时来自
 * `listWorkpapers` 的 `wp_index_id` 字段），**不是** `wp_id`（= `working_paper.id`，
 * `getProcedures` 下发的那个）。后端 `_resolve_targets` 按
 * `ProcedureRowTask.wp_index_id.in_(...)` 匹配 ⇒ 传 `wp_id` 会静默匹配到 0 个目标：
 * 请求成功、统计全 0、无任何报错。
 */
const applyGroups = computed<DelegationApplyGroup[]>(() => {
  const byAssignee = new Map<string, EditableRow[]>()
  for (const r of rows.value) {
    const list = byAssignee.get(r.assigneeStaffId)
    if (list) list.push(r)
    else byAssignee.set(r.assigneeStaffId, [r])
  }
  const out: DelegationApplyGroup[] = []
  for (const [assigneeStaffId, list] of byAssignee) {
    // 同一执行人下复核人可能被逐行改成不同人：按首行取，其余在 Task 19 再细分组。
    const reviewerStaffId = list[0]?.reviewerStaffId ?? null
    out.push({
      assigneeStaffId,
      assigneeName: memberById.value.get(assigneeStaffId)?.name ?? assigneeStaffId,
      reviewerStaffId,
      selector: {
        kind: 'workpaper',
        wp_index_ids: list.map((r) => r.wpIndexId),
      },
      wpCodes: list.map((r) => r.wpCode).filter(Boolean),
    })
  }
  return out
})

function emitApply() {
  emit('apply', applyGroups.value, plainRows())
}

defineExpose({ applyGroups })
</script>

<style scoped>
.gt-dst { font-size: 13px; }

.gt-dst__alert { margin-bottom: 10px; }
.gt-dst__alert-title { font-size: 13px; font-weight: 700; }
.gt-dst__alert-body { font-size: 12px; line-height: 1.7; }
.gt-dst__warn-list { margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.7; }

.gt-dst__block { margin-bottom: 14px; }
.gt-dst__block-title {
  font-size: 13px; font-weight: 700; margin-bottom: 6px;
  color: var(--gt-color-text-primary);
}
.gt-dst__block-hint {
  display: block; font-size: 12px; font-weight: 400; line-height: 1.6;
  color: var(--gt-color-text-secondary);
}
.gt-dst__table { font-size: 13px; }
.gt-dst__wp { font-weight: 600; }
.gt-dst__select { width: 100%; }

.gt-dst__num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.gt-dst__num--after { font-weight: 700; }
.gt-dst__formula {
  border-bottom: 1px dashed var(--gt-color-text-secondary);
  cursor: help;
}
.gt-dst__rationale {
  display: block; font-size: 12px; line-height: 1.5;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  cursor: help;
}

.gt-dst__empty {
  padding: 10px 0; font-size: 12px; color: var(--gt-color-text-secondary);
}

.gt-dst__loads { display: flex; flex-direction: column; gap: 6px; }
.gt-dst__load-row { display: flex; align-items: center; gap: 10px; }
.gt-dst__load-name { width: 150px; flex: none; font-size: 12px; }
.gt-dst__load-role { margin-left: 4px; color: var(--gt-color-text-secondary); }
.gt-dst__load-bar { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.gt-dst__load-track {
  height: 7px; border-radius: 4px; overflow: hidden;
  background: var(--gt-color-fill-light, #f0f2f5);
}
.gt-dst__load-fill { height: 100%; border-radius: 4px; }
.gt-dst__load-fill--before { background: var(--gt-color-text-secondary); opacity: 0.45; }
.gt-dst__load-fill--after { background: var(--gt-color-primary); }
.gt-dst__load-text {
  width: 190px; flex: none; text-align: right; font-size: 12px;
  display: flex; align-items: center; justify-content: flex-end; gap: 5px;
}
.gt-dst__arrow { color: var(--gt-color-text-secondary); }
.gt-dst__delta { color: var(--gt-color-primary); font-variant-numeric: tabular-nums; }
.gt-dst__unknown { color: var(--gt-color-coral); font-weight: 600; }
.gt-dst__unknown-note {
  margin-top: 8px; font-size: 12px; line-height: 1.6;
  color: var(--gt-color-coral);
}

.gt-dst__footer {
  display: flex; align-items: center; gap: 12px;
  padding-top: 10px; border-top: 1px solid var(--gt-color-border-light, #ebeef5);
}
.gt-dst__footer-stat { font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-dst__footer .el-button { margin-left: auto; }
</style>
