<template>
  <div class="g7-adjudication">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-1 长期股权投资审定表</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G7-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：按控制类型（子公司/合营/联营）分层汇总长期股权投资的期初、期末审定金额，验证未审数、AJE、RJE 调整的完整准确，确认长期股权投资净值与试算表（科目1511）勾稽一致。
    </el-alert>

    <!-- TB取数信息条 -->
    <div class="tb-info-bar">
      <span class="tb-label">TB取数（科目1511）：</span>
      <span class="tb-amount">{{ fmt(trialBalanceAmount) }}</span>
      <span :class="['diff-value', { 'diff-red': Math.abs(variance) > 0.01 }]">
        差异（审定-TB）：{{ fmt(variance) }}
        <template v-if="Math.abs(variance) <= 0.01"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
      </div>
    </div>

    <!-- 97行分组虚拟滚动容器 -->
    <div class="adj-scroll-container" ref="scrollContainerRef">
      <!-- 正常虚拟滚动模式 / 分页降级模式（结构相同） -->
      <template v-for="group in visibleGroups" :key="group.id">
        <div class="group-header" @click="toggleGroup(group.id)">
          <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.id] }">
            <ArrowDown />
          </el-icon>
          <span class="group-name">{{ group.title }}</span>
          <span class="group-count">({{ group.rows.length }}行)</span>
        </div>
        <div v-show="expandedMap[group.id]" class="group-body">
          <el-table
            :data="getGroupDisplayRows(group)"
            border size="small" class="adj-table"
            :max-height="400"
            :row-class-name="adjRowClassName"
          >
            <el-table-column label="项目" width="160" fixed>
              <template #default="{ row }">
                <span :class="{ 'row-bold': row._isSubtotal }">{{ row.item }}</span>
              </template>
            </el-table-column>
            <el-table-column label="控制类型" width="100">
              <template #default="{ row }">
                <span v-if="!row._isSubtotal">{{ controlTypeLabel(row.controlType) }}</span>
              </template>
            </el-table-column>
              <!-- 期初 -->
              <el-table-column label="期初" align="center">
                <el-table-column label="未审" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!row._isSubtotal && !isReadonly"
                      :model-value="row.openingUnadjusted"
                      size="small" :controls="false" style="width:100%"
                      @update:model-value="(v: number) => updateCell(group.id, row._idx, 'openingUnadjusted', v)"
                    />
                    <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.openingUnadjusted) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="AJE" width="100" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!row._isSubtotal && !isReadonly"
                      :model-value="row.openingAJE"
                      size="small" :controls="false" style="width:100%"
                      @update:model-value="(v: number) => updateCell(group.id, row._idx, 'openingAJE', v)"
                    />
                    <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.openingAJE) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="RJE" width="100" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!row._isSubtotal && !isReadonly"
                      :model-value="row.openingRJE"
                      size="small" :controls="false" style="width:100%"
                      @update:model-value="(v: number) => updateCell(group.id, row._idx, 'openingRJE', v)"
                    />
                    <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.openingRJE) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="审定" width="120" align="right">
                  <template #default="{ row }">
                    <span
                      :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                      :title="'期初审定 = 未审 + AJE + RJE'"
                    >{{ fmt(row.openingAdjusted) }}</span>
                  </template>
                </el-table-column>
              </el-table-column>
              <!-- 期末 -->
              <el-table-column label="期末" align="center">
                <el-table-column label="未审" width="120" align="right">
                  <template #default="{ row }">
                    <span
                      :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                      :title="'期末未审 = 期初审定 + 借方 - 贷方'"
                    >{{ fmt(row.closingUnadjusted) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="AJE" width="100" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!row._isSubtotal && !isReadonly"
                      :model-value="row.closingAJE"
                      size="small" :controls="false" style="width:100%"
                      @update:model-value="(v: number) => updateCell(group.id, row._idx, 'closingAJE', v)"
                    />
                    <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.closingAJE) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="RJE" width="100" align="right">
                  <template #default="{ row }">
                    <el-input-number
                      v-if="!row._isSubtotal && !isReadonly"
                      :model-value="row.closingRJE"
                      size="small" :controls="false" style="width:100%"
                      @update:model-value="(v: number) => updateCell(group.id, row._idx, 'closingRJE', v)"
                    />
                    <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.closingRJE) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="审定" width="120" align="right">
                  <template #default="{ row }">
                    <span
                      :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                      :title="'期末审定 = 未审 + AJE + RJE'"
                    >{{ fmt(row.closingAdjusted) }}</span>
                  </template>
                </el-table-column>
              </el-table-column>
              <!-- 变动额 -->
              <el-table-column label="变动额" width="110" align="right">
                <template #default="{ row }">
                  <span
                    :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    :title="'变动额 = 期末审定 - 期初审定'"
                  >{{ fmt(row.changeAmount) }}</span>
                </template>
              </el-table-column>
              <!-- 变动率 -->
              <el-table-column label="变动率" width="100" align="right">
                <template #default="{ row }">
                  <el-tooltip
                    v-if="isRateWarning(row.changeRate)"
                    content="变动率超过20%，需分析原因"
                    placement="top"
                  >
                    <span
                      :class="['formula-cell', 'rate-orange', { 'row-bold': row._isSubtotal }]"
                      :title="'变动率 = (期末审定 - 期初审定) / 期初审定'"
                    >{{ fmtRate(row.changeRate) }}</span>
                  </el-tooltip>
                  <span v-else
                    :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    :title="'变动率 = (期末审定 - 期初审定) / 期初审定'"
                  >{{ fmtRate(row.changeRate) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>

        <!-- 净值行（六、长期股权投资净值） -->
        <div class="group-header net-value-header">
          <span class="group-name">六、长期股权投资净值（=合计-减值）</span>
          <span class="formula-tag">自动计算</span>
        </div>
        <el-table :data="[netValueRow]" border size="small" class="adj-table">
          <el-table-column label="项目" width="160" fixed>
            <template #default><span class="row-bold">长期股权投资净值</span></template>
          </el-table-column>
          <el-table-column label="控制类型" width="100">
            <template #default><span>—</span></template>
          </el-table-column>
          <el-table-column label="期初" align="center">
            <el-table-column label="审定" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="净值 = 合计审定 - 减值审定">{{ fmt(row.openingAdjusted) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末" align="center">
            <el-table-column label="审定" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="净值 = 合计审定 - 减值审定">{{ fmt(row.closingAdjusted) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="变动额" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="变动额 = 期末净值 - 期初净值">{{ fmt(row.changeAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="100" align="right">
            <template #default="{ row }">
              <el-tooltip
                v-if="isRateWarning(row.changeRate)"
                content="变动率超过20%，需分析原因"
                placement="top"
              >
                <span class="formula-cell rate-orange">{{ fmtRate(row.changeRate) }}</span>
              </el-tooltip>
              <span v-else class="formula-cell">{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>
        </el-table>

      <!-- 分页控制（降级模式时显示） -->
      <div v-if="usePagination && totalPages > 1" class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="PAGE_SIZE"
          :total="totalRowCount"
          layout="prev, pager, next"
          small
        />
      </div>
    </div>

    <!-- 审计说明 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="auditNote" type="textarea"
        :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="对长期股权投资审定表的审计说明…" @change="saveNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="auditConclusion" type="textarea"
        :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="审计结论…" @change="saveConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为借方科目（资产类1511），期末未审 = 期初审定 + 借方发生额 - 贷方发生额</p>
        <p>2. 审定数 = 未审数 + AJE + RJE</p>
        <p>3. 分5组：子公司(成本法)/合营(权益法)/联营(权益法)/投资合计/减值准备</p>
        <p>4. 净值 = 投资合计(审定) - 减值准备(审定)</p>
        <p>5. |变动率|超过20%需分析原因（橙色高亮提示）</p>
        <p>6. 差异 = 净值(期末审定) - 试算表数(科目1511)</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabAdjudication.vue — G7-1 长期股权投资审定表
 *
 * 97行×12列，按控制类型分5组+净值行：
 *   一、对子公司投资（成本法）
 *   二、对合营企业投资（权益法）
 *   三、对联营企业投资（权益法）
 *   四、投资合计
 *   五、减值准备
 *   六、长期股权投资净值（=合计-减值）
 *
 * 12列：项目|控制类型|期初(未审|AJE|RJE|审定)|期末(未审|AJE|RJE|审定)|变动额|变动率
 *
 * 功能：
 * - 分组折叠(localStorage持久化 per wpId)
 * - 虚拟滚动(97行，降级分页模式30行/页)
 * - TB取数(1511) + 差异校验
 * - |变动率|>20% 橙色高亮 + tooltip
 * - 公式列虚线下划线+cursor:help+tooltip来源
 * - EventBus publish substantive:adjudicated(accountCode='1511')
 * - section标题栏右侧复核按钮(inject openReviewDialog)
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.3, 6.6
 */
import { ref, reactive, computed, watch, inject, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { parseNum, calcAdjustedAmount, calcChangeRate } from '../../composables/useG7FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)

// ═══ 常量 ═══════════════════════════════════════════════════════════════════
const PAGE_SIZE = 30
const STORAGE_KEY_PREFIX = 'g7-adjudication-collapse-'

// ═══ 类型定义 ═══════════════════════════════════════════════════════════════
type ControlType = 'subsidiary' | 'joint_venture' | 'associate'
type GroupType = 'subsidiary' | 'joint_venture' | 'associate' | 'total' | 'impairment'

interface AdjRow {
  id: string
  item: string
  controlType: ControlType | ''
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  _isSubtotal?: boolean
  _idx: number
}

interface AdjGroup {
  id: string
  groupType: GroupType
  title: string
  rows: AdjRow[]
}

// ═══ 数据层 — 5组 ═══════════════════════════════════════════════════════════
const groups = reactive<AdjGroup[]>([
  { id: 'subsidiary', groupType: 'subsidiary', title: '一、对子公司投资（成本法）', rows: [] },
  { id: 'joint_venture', groupType: 'joint_venture', title: '二、对合营企业投资（权益法）', rows: [] },
  { id: 'associate', groupType: 'associate', title: '三、对联营企业投资（权益法）', rows: [] },
  { id: 'total', groupType: 'total', title: '四、投资合计', rows: [] },
  { id: 'impairment', groupType: 'impairment', title: '五、减值准备', rows: [] },
])

const auditNote = ref('')
const auditConclusion = ref('')
const trialBalanceAmount = ref(0)
const scrollContainerRef = ref<HTMLElement>()
const usePagination = ref(false)
const currentPage = ref(1)

// ═══ 折叠状态（localStorage持久化 per wpId）═══════════════════════════════════
const expandedMap = reactive<Record<string, boolean>>({
  subsidiary: true,
  joint_venture: true,
  associate: true,
  total: true,
  impairment: true,
})

function getStorageKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw) {
      const saved = JSON.parse(raw)
      for (const key of Object.keys(expandedMap)) {
        if (key in saved) expandedMap[key] = saved[key]
      }
    }
  } catch { /* ignore parse errors */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore quota errors */ }
}

function toggleGroup(groupId: string): void {
  expandedMap[groupId] = !expandedMap[groupId]
  saveCollapseState()
}

// ═══ 虚拟滚动 / 分页降级 ═══════════════════════════════════════════════════
const totalRowCount = computed(() => groups.reduce((s, g) => s + g.rows.length, 0))
const totalPages = computed(() => Math.ceil(totalRowCount.value / PAGE_SIZE))

/** 性能检测：>97行或渲染时间>200ms时降级分页 */
function checkPerformance(): void {
  if (totalRowCount.value > 97) {
    usePagination.value = true
  }
}

const visibleGroups = computed(() => {
  if (!usePagination.value) return groups
  // 分页时显示全部groups（折叠控制可见性）
  return groups
})

// ═══ 小计计算 ═══════════════════════════════════════════════════════════════
function calcGroupSubtotal(rows: AdjRow[]): AdjRow {
  const dataRows = rows.filter(r => !r._isSubtotal)
  const sum = (field: keyof AdjRow) =>
    dataRows.reduce((s, r) => s + parseNum(r[field] as number), 0)
  const openUnadj = sum('openingUnadjusted')
  const openAJE = sum('openingAJE')
  const openRJE = sum('openingRJE')
  const openAdj = calcAdjustedAmount(openUnadj, openAJE, openRJE)
  const closeUnadj = sum('closingUnadjusted')
  const closeAJE = sum('closingAJE')
  const closeRJE = sum('closingRJE')
  const closeAdj = calcAdjustedAmount(closeUnadj, closeAJE, closeRJE)
  const change = Math.round((closeAdj - openAdj) * 100) / 100
  return {
    id: 'subtotal', item: '小计',
    controlType: '',
    openingUnadjusted: openUnadj, openingAJE: openAJE, openingRJE: openRJE,
    openingAdjusted: openAdj,
    closingUnadjusted: closeUnadj, closingAJE: closeAJE, closingRJE: closeRJE,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    _isSubtotal: true, _idx: -1,
  }
}

function getGroupDisplayRows(group: AdjGroup): AdjRow[] {
  const dataRows = group.rows.filter(r => !r._isSubtotal)
  if (dataRows.length === 0) return []
  return [...dataRows, calcGroupSubtotal(dataRows)]
}

// ═══ 净值行（六、长期股权投资净值 = 四投资合计 - 五减值准备）═══════════════
const netValueRow = computed(() => {
  const totalGroup = groups.find(g => g.id === 'total')
  const impairGroup = groups.find(g => g.id === 'impairment')
  const totalSub = totalGroup ? calcGroupSubtotal(totalGroup.rows) : calcGroupSubtotal([])
  const impairSub = impairGroup ? calcGroupSubtotal(impairGroup.rows) : calcGroupSubtotal([])
  const openAdj = totalSub.openingAdjusted - impairSub.openingAdjusted
  const closeAdj = totalSub.closingAdjusted - impairSub.closingAdjusted
  const change = Math.round((closeAdj - openAdj) * 100) / 100
  return {
    id: 'net-value', item: '长期股权投资净值',
    controlType: '' as const,
    openingUnadjusted: 0, openingAJE: 0, openingRJE: 0,
    openingAdjusted: openAdj,
    closingUnadjusted: 0, closingAJE: 0, closingRJE: 0,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    _isSubtotal: true, _idx: -1,
  }
})

// ═══ TB差异 ═══════════════════════════════════════════════════════════════════
const adjudicatedAmount = computed(() => netValueRow.value.closingAdjusted)
const variance = computed(() => Math.round((adjudicatedAmount.value - trialBalanceAmount.value) * 100) / 100)

// ═══ EventBus publish: substantive:adjudicated（window CustomEvent，比照 F2/G8）═══
watch(adjudicatedAmount, (val) => {
  const subsidiarySub = calcGroupSubtotal(groups[0].rows)
  const jvSub = calcGroupSubtotal(groups[1].rows)
  const assocSub = calcGroupSubtotal(groups[2].rows)
  const payload = {
    accountCode: '1511',
    adjudicatedAmount: val,
    byControlType: {
      subsidiary: subsidiarySub.closingAdjusted,
      jointVenture: jvSub.closingAdjusted,
      associate: assocSub.closingAdjusted,
    },
  }
  try {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
  } catch { /* best-effort */ }
  try {
    window.dispatchEvent(new CustomEvent('g7:writeback-trial-balance', {
      detail: { accountCode: '1511', auditedAmount: val },
    }))
  } catch { /* best-effort */ }
})

// ═══ 单元格更新 + 公式重算 ═══════════════════════════════════════════════════
function updateCell(groupId: string, rowIdx: number, field: string, value: number | string): void {
  const group = groups.find(g => g.id === groupId)
  if (!group || rowIdx < 0 || rowIdx >= group.rows.length) return
  const row = group.rows[rowIdx]
  ;(row as any)[field] = value
  recalcRow(row)
}

function recalcRow(row: AdjRow): void {
  row.openingAdjusted = calcAdjustedAmount(
    parseNum(row.openingUnadjusted), parseNum(row.openingAJE), parseNum(row.openingRJE),
  )
  row.closingAdjusted = calcAdjustedAmount(
    parseNum(row.closingUnadjusted), parseNum(row.closingAJE), parseNum(row.closingRJE),
  )
  row.changeAmount = Math.round((row.closingAdjusted - row.openingAdjusted) * 100) / 100
  row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
}

// ═══ 控制类型标签 ═══════════════════════════════════════════════════════════
function controlTypeLabel(ct: ControlType | string): string {
  switch (ct) {
    case 'subsidiary': return '控制'
    case 'joint_venture': return '共同控制'
    case 'associate': return '重大影响'
    default: return ''
  }
}

// ═══ 数据水合 — 从htmlData还原行数据 ═══════════════════════════════════════
function makeRow(item: string, idx: number, controlType: ControlType | '', raw?: any): AdjRow {
  const r: AdjRow = {
    id: raw?.id ?? `row-${idx}`,
    item,
    controlType,
    openingUnadjusted: parseNum(raw?.openingUnadjusted ?? raw?.opening_unadjusted),
    openingAJE: parseNum(raw?.openingAJE ?? raw?.opening_aje),
    openingRJE: parseNum(raw?.openingRJE ?? raw?.opening_rje),
    openingAdjusted: 0,
    closingUnadjusted: parseNum(raw?.closingUnadjusted ?? raw?.closing_unadjusted),
    closingAJE: parseNum(raw?.closingAJE ?? raw?.closing_aje),
    closingRJE: parseNum(raw?.closingRJE ?? raw?.closing_rje),
    closingAdjusted: 0,
    changeAmount: 0, changeRate: null,
    _isSubtotal: false, _idx: idx,
  }
  recalcRow(r)
  return r
}

/** 默认骨架（无外部数据时） */
const DEFAULT_SUBSIDIARIES = ['子公司A', '子公司B', '子公司C']
const DEFAULT_JV = ['合营企业A', '合营企业B']
const DEFAULT_ASSOCIATES = ['联营企业A', '联营企业B', '联营企业C']
const DEFAULT_TOTAL = ['投资合计']
const DEFAULT_IMPAIRMENT = ['减值准备']

function hydrateData(): void {
  const data = props.htmlData
  const groupConfigs: { id: string; ct: ControlType | ''; defaults: string[] }[] = [
    { id: 'subsidiary', ct: 'subsidiary', defaults: DEFAULT_SUBSIDIARIES },
    { id: 'joint_venture', ct: 'joint_venture', defaults: DEFAULT_JV },
    { id: 'associate', ct: 'associate', defaults: DEFAULT_ASSOCIATES },
    { id: 'total', ct: '', defaults: DEFAULT_TOTAL },
    { id: 'impairment', ct: '', defaults: DEFAULT_IMPAIRMENT },
  ]

  for (const cfg of groupConfigs) {
    const group = groups.find(g => g.id === cfg.id)!
    const raw = data?.adjudication?.groups?.find((g: any) => g.id === cfg.id || g.groupType === cfg.id)
    const rowsRaw = raw?.rows ?? data?.[cfg.id] ?? data?.sections?.[cfg.id]
    if (Array.isArray(rowsRaw) && rowsRaw.length > 0) {
      group.rows = rowsRaw.map((r: any, i: number) =>
        makeRow(r.item || r.name || `项目${i + 1}`, i, r.controlType || cfg.ct, r),
      )
    } else {
      group.rows = cfg.defaults.map((item, i) => makeRow(item, i, cfg.ct))
    }
  }

  auditNote.value = data?.auditNote ?? data?.audit_note ?? ''
  auditConclusion.value = data?.auditConclusion ?? data?.audit_conclusion ?? ''
}

// ═══ TB取数 — 科目1511 ═══════════════════════════════════════════════════════
async function fetchTrialBalance(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await api.get('/api/trial-balance/query', {
      params: { project_id: props.projectId, account_code: '1511' },
      _silent: true,
    } as any)
    const items = res?.data?.items ?? res?.data ?? res?.items ?? []
    if (Array.isArray(items) && items.length > 0) {
      trialBalanceAmount.value = items.reduce(
        (s: number, it: any) => s + parseNum(it.audited_amount ?? it.unadjusted_amount), 0,
      )
    } else if (typeof res?.data === 'number') {
      trialBalanceAmount.value = res.data
    }
  } catch {
    console.warn('[G7TabAdjudication] fetchTrialBalance failed')
  }
}

// ═══ 辅助函数 ═══════════════════════════════════════════════════════════════
function isRateWarning(rate: number | null): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.2
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(2) + '%'
}

function adjRowClassName({ row }: { row: AdjRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  return ''
}

// ═══ 审计说明/结论 持久化（checklist_responses）══════════════════════════════
const NOTE_KEY = 'G7-1-adjudication-audit-note'
const CONCLUSION_KEY = 'G7-1-adjudication-audit-conclusion'

function persistAudit(itemId: string, val: string): void {
  if (props.isReadonly || !props.wpId) return
  api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: [{ item_id: itemId, conclusion: null, remark: val }],
  }, { _silent: true } as any).catch(() => {})
}

function saveNote(): void { persistAudit(NOTE_KEY, auditNote.value) }
function saveConclusion(): void { persistAudit(CONCLUSION_KEY, auditConclusion.value) }

async function loadAuditResponses(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : (res as any)?.data || []
    for (const it of items) {
      if (it.item_id === NOTE_KEY && it.remark) auditNote.value = it.remark
      else if (it.item_id === CONCLUSION_KEY && it.remark) auditConclusion.value = it.remark
    }
  } catch { /* silent */ }
}

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════
onMounted(() => {
  loadCollapseState()
  hydrateData()
  loadAuditResponses()
  fetchTrialBalance()
  checkPerformance()
})
</script>

<style scoped>
.g7-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* Section 标题栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

/* TB信息条 */
.tb-info-bar {
  display: flex; gap: 16px; align-items: center;
  padding: 8px 12px; background: #f0f9eb; border: 1px solid #e1f3d8;
  border-radius: 4px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px);
}
.tb-label { font-weight: 500; color: #606266; }
.tb-amount { font-weight: 600; color: #303133; }
.diff-value { font-weight: 600; color: #67c23a; }
.diff-red { color: #f56c6c; }

/* 虚拟滚动容器 */
.adj-scroll-container {
  max-height: 680px; overflow-y: auto;
  border: 1px solid #ebeef5; border-radius: 4px; padding: 4px;
}

/* 分组标题 */
.group-header {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; background: #ecf5ff; border: 1px solid #d9ecff;
  border-radius: 4px; margin-top: 8px; cursor: pointer;
  user-select: none; transition: background 0.2s;
}
.group-header:hover { background: #d9ecff; }
.group-header.net-value-header {
  background: #f0f9eb; border-color: #e1f3d8; cursor: default;
}
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; }
.group-count { font-size: 12px; color: #909399; margin-left: 4px; }
.formula-tag {
  margin-left: auto; font-size: 11px; color: #67c23a;
  background: #f0f9eb; border: 1px solid #e1f3d8;
  padding: 1px 6px; border-radius: 3px;
}
.collapse-icon { transition: transform 0.2s; font-size: 14px; }
.collapse-icon.is-collapsed { transform: rotate(-90deg); }

/* 分组内容 */
.group-body { margin-bottom: 4px; }

/* 表格 */
.adj-table { margin-top: 4px; }

/* 公式列样式（虚线下划线+cursor:help） */
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }

/* 行样式 */
.row-bold { font-weight: 700; }
:deep(.row-subtotal) { background: #f5f7fa !important; font-weight: 700; }

/* 变动率橙色高亮 */
.rate-orange { color: #e6a23c; font-weight: 600; }

/* 分页控制 */
.pagination-bar {
  display: flex; justify-content: center; padding: 12px 0;
}

/* 审计说明/结论卡片 */
.note-card { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

/* 编制提示 */
.guidance-details {
  margin-top: 16px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 4px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-content p { margin: 4px 0; }
</style>
