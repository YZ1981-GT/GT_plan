<template>
  <div class="g7-adjudication">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-1 长期股权投资审定表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain :loading="adjPullGross.loading.value" @click="openBringInGross">
          <el-icon><Download /></el-icon>带入调整(原值)
        </el-button>
        <el-button size="small" type="primary" plain :loading="adjPullImpair.loading.value" @click="openBringInImpair">
          <el-icon><Download /></el-icon>带入调整(减值)
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly || !isDirty" :loading="saving" @click="saveAll">
          保存
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：按控制类型（子公司/合营/联营）分层汇总长期股权投资的期初、期末审定金额，验证未审数、AJE、RJE 调整的完整准确；投资合计勾稽科目1511、减值准备勾稽科目1512，净值勾稽 1511−1512。
    </el-alert>

    <!-- TB取数信息条 -->
    <div class="tb-info-bar">
      <span class="tb-label">TB 1511（原值）：</span>
      <span class="tb-amount">{{ fmt(tbGross) }}</span>
      <span :class="['diff-value', { 'diff-red': Math.abs(varianceGross) > 0.01 }]">
        差异：{{ fmt(varianceGross) }}
        <template v-if="Math.abs(varianceGross) <= 0.01"> ✓</template>
        <template v-else> ✗</template>
      </span>
      <span class="tb-sep">|</span>
      <span class="tb-label">TB 1512（减值）：</span>
      <span class="tb-amount">{{ fmt(tbImpairment) }}</span>
      <span :class="['diff-value', { 'diff-red': Math.abs(varianceImpairment) > 0.01 }]">
        差异：{{ fmt(varianceImpairment) }}
        <template v-if="Math.abs(varianceImpairment) <= 0.01"> ✓</template>
        <template v-else> ✗</template>
      </span>
      <span class="tb-sep">|</span>
      <span class="tb-label">净值(1511−1512)：</span>
      <span class="tb-amount">{{ fmt(tbNet) }}</span>
      <span :class="['diff-value', { 'diff-red': Math.abs(varianceNet) > 0.01 }]">
        差异：{{ fmt(varianceNet) }}
        <template v-if="Math.abs(varianceNet) <= 0.01"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
        <el-tag v-if="isDirty" size="small" type="warning">未保存</el-tag>
      </div>
    </div>

    <div class="adj-scroll-container" ref="scrollContainerRef">
      <!-- 一~三：可编辑投资组 + 五：减值 -->
      <template v-for="group in editableGroups" :key="group.id">
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
            <el-table-column label="项目" width="140" fixed>
              <template #default="{ row }">
                <span :class="{ 'row-bold': row._isSubtotal }">{{ row.item }}</span>
              </template>
            </el-table-column>
            <el-table-column label="控制类型" width="90">
              <template #default="{ row }">
                <span v-if="!row._isSubtotal">{{ controlTypeLabel(row.controlType) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初" align="center">
              <el-table-column label="未审" width="100" align="right">
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
              <el-table-column label="AJE" width="90" align="right">
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
              <el-table-column label="RJE" width="90" align="right">
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
              <el-table-column label="审定" width="110" align="right">
                <template #default="{ row }">
                  <span
                    :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="期初审定 = 未审 + AJE + RJE"
                  >{{ fmt(row.openingAdjusted) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末" align="center">
              <el-table-column label="借方" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.debitAmount"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(group.id, row._idx, 'debitAmount', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.debitAmount) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="贷方" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.creditAmount"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(group.id, row._idx, 'creditAmount', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.creditAmount) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="未审" width="110" align="right">
                <template #default="{ row }">
                  <span
                    v-if="row._autoClosing || row._isSubtotal"
                    :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="期末未审 = 期初审定 + 借方 - 贷方"
                  >{{ fmt(row.closingUnadjusted) }}</span>
                  <el-input-number
                    v-else-if="!isReadonly"
                    :model-value="row.closingUnadjusted"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(group.id, row._idx, 'closingUnadjusted', v)"
                  />
                  <span v-else>{{ fmt(row.closingUnadjusted) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="AJE" width="90" align="right">
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
              <el-table-column label="RJE" width="90" align="right">
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
              <el-table-column label="审定" width="110" align="right">
                <template #default="{ row }">
                  <span
                    :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="期末审定 = 未审 + AJE + RJE"
                  >{{ fmt(row.closingAdjusted) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="变动额" width="100" align="right">
              <template #default="{ row }">
                <span
                  :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                  title="变动额 = 期末审定 - 期初审定"
                >{{ fmt(row.changeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动率" width="90" align="right">
              <template #default="{ row }">
                <el-tooltip
                  v-if="isRateWarning(row.changeRate)"
                  content="变动率超过20%，需分析原因"
                  placement="top"
                >
                  <span
                    :class="['formula-cell', 'rate-orange', { 'row-bold': row._isSubtotal }]"
                  >{{ fmtRate(row.changeRate) }}</span>
                </el-tooltip>
                <span v-else :class="['formula-cell', { 'row-bold': row._isSubtotal }]">{{ fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因分析" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!row._isSubtotal && !isReadonly"
                  :model-value="row.varianceNote"
                  size="small"
                  :class="{ 'need-reason': isRateWarning(row.changeRate) && !row.varianceNote }"
                  :placeholder="isRateWarning(row.changeRate) ? '必填：变动原因' : '可选'"
                  @update:model-value="(v: string) => updateCell(group.id, row._idx, 'varianceNote', v)"
                />
                <span v-else-if="!row._isSubtotal">{{ row.varianceNote || '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 四、投资合计（自动 = 一+二+三） -->
      <div class="group-header net-value-header">
        <span class="group-name">四、投资合计（=子公司+合营+联营）</span>
        <span class="formula-tag">自动汇总</span>
      </div>
      <el-table :data="[investmentTotalRow]" border size="small" class="adj-table">
        <el-table-column label="项目" width="140" fixed>
          <template #default><span class="row-bold">投资合计</span></template>
        </el-table-column>
        <el-table-column label="控制类型" width="90">
          <template #default><span>—</span></template>
        </el-table-column>
        <el-table-column label="期初审定" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell row-bold">{{ fmt(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell row-bold">{{ fmt(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell row-bold">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', 'row-bold', { 'rate-orange': isRateWarning(row.changeRate) }]">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 六、净值 -->
      <div class="group-header net-value-header">
        <span class="group-name">六、长期股权投资净值（=合计−减值）</span>
        <span class="formula-tag">自动计算</span>
      </div>
      <el-table :data="[netValueRow]" border size="small" class="adj-table">
        <el-table-column label="项目" width="140" fixed>
          <template #default><span class="row-bold">长期股权投资净值</span></template>
        </el-table-column>
        <el-table-column label="控制类型" width="90">
          <template #default><span>—</span></template>
        </el-table-column>
        <el-table-column label="期初审定" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值 = 合计审定 − 减值审定">{{ fmt(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值 = 合计审定 − 减值审定">{{ fmt(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'rate-orange': isRateWarning(row.changeRate) }]">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-alert
      v-if="missingReasonCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="reason-warn"
      :title="`有 ${missingReasonCount} 行变动率超过20%但未填写原因分析`"
    />

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
        <p>1. 本表为借方科目（资产类1511），期末未审 = 期初审定 + 借方发生额 − 贷方发生额（填写借贷后自动计算；未填借贷时可手填未审）</p>
        <p>2. 审定数 = 未审数 + AJE + RJE；G7-3 保存后自动回写期末 AJE/RJE</p>
        <p>3. 分组：子公司(成本法)/合营(权益法)/联营(权益法)；投资合计自动汇总，不可手工编辑</p>
        <p>4. 勾稽：投资合计 ↔ TB1511；减值准备 ↔ TB1512；净值 ↔ 1511−1512</p>
        <p>5. 回写：1511 回写投资合计审定（原值），1512 回写减值准备审定</p>
        <p>6. |变动率|超过20%需填写原因分析（橙色高亮）</p>
        <p>7. 「带入调整(原值)」：从集中登记按科目 1511 拉取调整分录，逐笔分配到子公司/合营/联营各投资明细行的期末 AJE/RJE；「带入调整(减值)」按科目 1512 分配到减值明细行，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInGrossVisible"
      :matches="adjPullGross.matches.value"
      :row-options="bringInGrossRowOptions"
      subject-label="1511 长期股权投资原值"
      :loading="adjPullGross.loading.value"
      @apply="onBringInGrossApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInImpairVisible"
      :matches="adjPullImpair.matches.value"
      :row-options="bringInImpairRowOptions"
      subject-label="1512 长期股权投资减值准备"
      :loading="adjPullImpair.loading.value"
      @apply="onBringInImpairApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabAdjudication.vue — G7-1 长期股权投资审定表
 *
 * 按控制类型分3组可编辑投资行 + 减值组 + 自动投资合计 + 净值：
 *   一、对子公司投资（成本法）
 *   二、对合营企业投资（权益法）
 *   三、对联营企业投资（权益法）
 *   四、投资合计（=一+二+三，自动）
 *   五、减值准备
 *   六、长期股权投资净值（=合计−减值）
 *
 * 修复要点：
 * - 投资合计不可编辑，自动汇总
 * - TB 勾稽分 1511/1512/净值三口径
 * - 回写 1511=投资合计原值、1512=减值（非净值误写1511）
 * - 表格金额持久化 + 去重回写事件
 * - 借贷发生额驱动期末未审；变动原因分析列
 * - 监听 g7:adjustment-writeback 回写期末 AJE/RJE
 */
import { ref, reactive, computed, watch, inject, onMounted, onBeforeUnmount } from 'vue'
import { ArrowDown, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcAdjustedAmount, calcChangeRate, calcDebitBalance } from '../../composables/useG7FormulaEngine'
import {
  normalizeG7DetailRows,
  type G7CostRow,
  type G7EquityRow,
  type G7ImpairmentRow,
} from '../../composables/g7DetailModel'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
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

const STORAGE_KEY_PREFIX = 'g7-adjudication-collapse-'
const DATA_KEY = 'G7-1-adjudication-data'
const NOTE_KEY = 'G7-1-adjudication-audit-note'
const CONCLUSION_KEY = 'G7-1-adjudication-audit-conclusion'
const ACCOUNT_GROSS = '1511'
const ACCOUNT_IMPAIRMENT = '1512'

type ControlType = 'subsidiary' | 'joint_venture' | 'associate'
type EditableGroupType = 'subsidiary' | 'joint_venture' | 'associate' | 'impairment'

interface AdjRow {
  id: string
  item: string
  controlType: ControlType | ''
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  debitAmount: number
  creditAmount: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  varianceNote: string
  _autoClosing?: boolean
  _isSubtotal?: boolean
  _idx: number
}

interface AdjGroup {
  id: string
  groupType: EditableGroupType
  title: string
  rows: AdjRow[]
}

const groups = reactive<AdjGroup[]>([
  { id: 'subsidiary', groupType: 'subsidiary', title: '一、对子公司投资（成本法）', rows: [] },
  { id: 'joint_venture', groupType: 'joint_venture', title: '二、对合营企业投资（权益法）', rows: [] },
  { id: 'associate', groupType: 'associate', title: '三、对联营企业投资（权益法）', rows: [] },
  { id: 'impairment', groupType: 'impairment', title: '五、减值准备', rows: [] },
])

const editableGroups = computed(() => groups)

const auditNote = ref('')
const auditConclusion = ref('')
const tbGross = ref(0)
const tbImpairment = ref(0)
const scrollContainerRef = ref<HTMLElement>()
const isDirty = ref(false)
const saving = ref(false)
/** G7-3 回写命中行（短暂高亮） */
const writebackHitIds = ref<Set<string>>(new Set())
let writebackHitTimer: ReturnType<typeof setTimeout> | null = null

function markWritebackHits(ids: string[]): void {
  writebackHitIds.value = new Set(ids.filter(Boolean))
  if (writebackHitTimer) clearTimeout(writebackHitTimer)
  writebackHitTimer = setTimeout(() => {
    writebackHitIds.value = new Set()
  }, 8000)
}
let persistTimer: ReturnType<typeof setTimeout> | null = null
let publishTimer: ReturnType<typeof setTimeout> | null = null

const expandedMap = reactive<Record<string, boolean>>({
  subsidiary: true,
  joint_venture: true,
  associate: true,
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
  } catch { /* ignore */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore */ }
}

function toggleGroup(groupId: string): void {
  expandedMap[groupId] = !expandedMap[groupId]
  saveCollapseState()
}

const totalRowCount = computed(() => groups.reduce((s, g) => s + g.rows.length, 0))

function calcGroupSubtotal(rows: AdjRow[]): AdjRow {
  const dataRows = rows.filter(r => !r._isSubtotal)
  const sum = (field: keyof AdjRow) =>
    dataRows.reduce((s, r) => s + parseNum(r[field] as number), 0)
  const openUnadj = sum('openingUnadjusted')
  const openAJE = sum('openingAJE')
  const openRJE = sum('openingRJE')
  const openAdj = calcAdjustedAmount(openUnadj, openAJE, openRJE)
  const debit = sum('debitAmount')
  const credit = sum('creditAmount')
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
    debitAmount: debit, creditAmount: credit,
    closingUnadjusted: closeUnadj, closingAJE: closeAJE, closingRJE: closeRJE,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    varianceNote: '',
    _isSubtotal: true, _idx: -1,
  }
}

function getGroupDisplayRows(group: AdjGroup): AdjRow[] {
  const dataRows = group.rows.filter(r => !r._isSubtotal)
  if (dataRows.length === 0) return []
  return [...dataRows, calcGroupSubtotal(dataRows)]
}

/** 四、投资合计 = 子公司 + 合营 + 联营（不可编辑） */
const investmentTotalRow = computed(() => {
  const sub = calcGroupSubtotal(groups.find(g => g.id === 'subsidiary')?.rows ?? [])
  const jv = calcGroupSubtotal(groups.find(g => g.id === 'joint_venture')?.rows ?? [])
  const assoc = calcGroupSubtotal(groups.find(g => g.id === 'associate')?.rows ?? [])
  const openAdj = sub.openingAdjusted + jv.openingAdjusted + assoc.openingAdjusted
  const closeAdj = sub.closingAdjusted + jv.closingAdjusted + assoc.closingAdjusted
  const change = Math.round((closeAdj - openAdj) * 100) / 100
  return {
    id: 'investment-total', item: '投资合计',
    controlType: '' as const,
    openingUnadjusted: sub.openingUnadjusted + jv.openingUnadjusted + assoc.openingUnadjusted,
    openingAJE: sub.openingAJE + jv.openingAJE + assoc.openingAJE,
    openingRJE: sub.openingRJE + jv.openingRJE + assoc.openingRJE,
    openingAdjusted: openAdj,
    debitAmount: sub.debitAmount + jv.debitAmount + assoc.debitAmount,
    creditAmount: sub.creditAmount + jv.creditAmount + assoc.creditAmount,
    closingUnadjusted: sub.closingUnadjusted + jv.closingUnadjusted + assoc.closingUnadjusted,
    closingAJE: sub.closingAJE + jv.closingAJE + assoc.closingAJE,
    closingRJE: sub.closingRJE + jv.closingRJE + assoc.closingRJE,
    closingAdjusted: closeAdj,
    changeAmount: change,
    changeRate: calcChangeRate(openAdj, closeAdj),
    varianceNote: '',
    _isSubtotal: true, _idx: -1,
  }
})

/** 六、净值 = 投资合计 − 减值 */
const netValueRow = computed(() => {
  const total = investmentTotalRow.value
  const impair = calcGroupSubtotal(groups.find(g => g.id === 'impairment')?.rows ?? [])
  const openAdj = total.openingAdjusted - impair.openingAdjusted
  const closeAdj = total.closingAdjusted - impair.closingAdjusted
  const change = Math.round((closeAdj - openAdj) * 100) / 100
  return {
    id: 'net-value', item: '长期股权投资净值',
    controlType: '' as const,
    openingUnadjusted: 0, openingAJE: 0, openingRJE: 0,
    openingAdjusted: openAdj,
    debitAmount: 0, creditAmount: 0,
    closingUnadjusted: 0, closingAJE: 0, closingRJE: 0,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    varianceNote: '',
    _isSubtotal: true, _idx: -1,
  }
})

const tbNet = computed(() => Math.round((tbGross.value - tbImpairment.value) * 100) / 100)
const varianceGross = computed(() =>
  Math.round((investmentTotalRow.value.closingAdjusted - tbGross.value) * 100) / 100,
)
const varianceImpairment = computed(() => {
  const impair = calcGroupSubtotal(groups.find(g => g.id === 'impairment')?.rows ?? [])
  return Math.round((impair.closingAdjusted - tbImpairment.value) * 100) / 100
})
const varianceNet = computed(() =>
  Math.round((netValueRow.value.closingAdjusted - tbNet.value) * 100) / 100,
)

const missingReasonCount = computed(() => {
  let n = 0
  for (const g of groups) {
    for (const r of g.rows) {
      if (r._isSubtotal) continue
      if (isRateWarning(r.changeRate) && !(r.varianceNote || '').trim()) n++
    }
  }
  return n
})

/** 发布 substantive:adjudicated；仅 writebackTb=true 时父组件回写 TB */
function publishAdjudicated(opts?: { writebackTb?: boolean }): void {
  const impair = calcGroupSubtotal(groups.find(g => g.id === 'impairment')?.rows ?? [])
  const subsidiarySub = calcGroupSubtotal(groups.find(g => g.id === 'subsidiary')?.rows ?? [])
  const jvSub = calcGroupSubtotal(groups.find(g => g.id === 'joint_venture')?.rows ?? [])
  const assocSub = calcGroupSubtotal(groups.find(g => g.id === 'associate')?.rows ?? [])
  const payload = {
    accountCode: ACCOUNT_GROSS,
    /** 1511 回写原值（投资合计），不是净值 */
    adjudicatedAmount: investmentTotalRow.value.closingAdjusted,
    impairmentAccountCode: ACCOUNT_IMPAIRMENT,
    impairmentAmount: impair.closingAdjusted,
    netAmount: netValueRow.value.closingAdjusted,
    writebackTb: opts?.writebackTb === true,
    byControlType: {
      subsidiary: subsidiarySub.closingAdjusted,
      jointVenture: jvSub.closingAdjusted,
      associate: assocSub.closingAdjusted,
    },
  }
  try {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
  } catch { /* best-effort */ }
}

function schedulePublish(): void {
  if (publishTimer) clearTimeout(publishTimer)
  publishTimer = setTimeout(() => {
    publishTimer = null
    // 编辑中仅通知联动，不回写 TB（避免打开/hydrate 误改试算表）
    publishAdjudicated({ writebackTb: false })
  }, 300)
}

watch(
  () => [investmentTotalRow.value.closingAdjusted, netValueRow.value.closingAdjusted],
  () => schedulePublish(),
)

function updateCell(groupId: string, rowIdx: number, field: string, value: number | string): void {
  const group = groups.find(g => g.id === groupId)
  if (!group || rowIdx < 0 || rowIdx >= group.rows.length) return
  const row = group.rows[rowIdx]
  ;(row as any)[field] = value
  recalcRow(row)
  isDirty.value = true
  schedulePersist()
}

// ─── 从集中登记带入调整（双科目：1511 原值[借方] + 1512 减值准备[贷方备抵]；带入期末 AJE/RJE） ───
// 目标行 rowKey 编码为 `${groupId}::${rowIdx}`，桥接到自建 groups 的 updateCell(groupId, idx, field, v)
const bringInRowsGross = computed(() => {
  const out: Array<{ rowKey: string; name: string; aje: number; rje: number }> = []
  for (const gid of ['subsidiary', 'joint_venture', 'associate']) {
    const g = groups.find((x) => x.id === gid)
    if (!g) continue
    g.rows.forEach((r, idx) => {
      if (r._isSubtotal) return
      out.push({ rowKey: `${gid}::${idx}`, name: r.item, aje: r.closingAJE, rje: r.closingRJE })
    })
  }
  return out
})
const bringInRowsImpair = computed(() => {
  const g = groups.find((x) => x.id === 'impairment')
  if (!g) return []
  const out: Array<{ rowKey: string; name: string; aje: number; rje: number }> = []
  g.rows.forEach((r, idx) => {
    if (r._isSubtotal) return
    out.push({ rowKey: `impairment::${idx}`, name: r.item, aje: r.closingAJE, rje: r.closingRJE })
  })
  return out
})
function bringInUpdateCell(rowKey: string, field: any, value: number): void {
  const [gid, idxStr] = rowKey.split('::')
  updateCell(gid, Number(idxStr), field === 'rje' ? 'closingRJE' : 'closingAJE', value)
}
const {
  adjPull: adjPullGross,
  visible: bringInGrossVisible,
  rowOptions: bringInGrossRowOptions,
  open: openBringInGross,
  apply: onBringInGrossApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1511',
  direction: 'debit',
  subjectCode: '1511',
  wpCode: 'G7',
  subjectLabel: '长期股权投资原值(1511)',
  rows: bringInRowsGross,
  updateCell: bringInUpdateCell,
  totalAudited: () => investmentTotalRow.value.closingAdjusted,
})
const {
  adjPull: adjPullImpair,
  visible: bringInImpairVisible,
  rowOptions: bringInImpairRowOptions,
  open: openBringInImpair,
  apply: onBringInImpairApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1512',
  direction: 'credit',
  subjectCode: '1512',
  wpCode: 'G7',
  subjectLabel: '长期股权投资减值准备(1512)',
  rows: bringInRowsImpair,
  updateCell: bringInUpdateCell,
  totalAudited: () =>
    calcGroupSubtotal(groups.find((g) => g.id === 'impairment')?.rows ?? []).closingAdjusted,
})

function recalcRow(row: AdjRow): void {
  row.openingAdjusted = calcAdjustedAmount(
    parseNum(row.openingUnadjusted), parseNum(row.openingAJE), parseNum(row.openingRJE),
  )
  const debit = parseNum(row.debitAmount)
  const credit = parseNum(row.creditAmount)
  // 有借贷发生额时自动推算期末未审；否则保留手填
  if (debit !== 0 || credit !== 0) {
    row.closingUnadjusted = calcDebitBalance(row.openingAdjusted, debit, credit)
    row._autoClosing = true
  } else {
    row._autoClosing = false
  }
  row.closingAdjusted = calcAdjustedAmount(
    parseNum(row.closingUnadjusted), parseNum(row.closingAJE), parseNum(row.closingRJE),
  )
  row.changeAmount = Math.round((row.closingAdjusted - row.openingAdjusted) * 100) / 100
  row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
}

function controlTypeLabel(ct: ControlType | string): string {
  switch (ct) {
    case 'subsidiary': return '控制'
    case 'joint_venture': return '共同控制'
    case 'associate': return '重大影响'
    default: return ''
  }
}

function makeRow(item: string, idx: number, controlType: ControlType | '', raw?: any): AdjRow {
  const r: AdjRow = {
    id: raw?.id ?? `row-${idx}`,
    item,
    controlType,
    openingUnadjusted: parseNum(raw?.openingUnadjusted ?? raw?.opening_unadjusted),
    openingAJE: parseNum(raw?.openingAJE ?? raw?.opening_aje),
    openingRJE: parseNum(raw?.openingRJE ?? raw?.opening_rje),
    openingAdjusted: 0,
    debitAmount: parseNum(raw?.debitAmount ?? raw?.debit_amount),
    creditAmount: parseNum(raw?.creditAmount ?? raw?.credit_amount),
    closingUnadjusted: parseNum(raw?.closingUnadjusted ?? raw?.closing_unadjusted),
    closingAJE: parseNum(raw?.closingAJE ?? raw?.closing_aje),
    closingRJE: parseNum(raw?.closingRJE ?? raw?.closing_rje),
    closingAdjusted: 0,
    changeAmount: 0, changeRate: null,
    varianceNote: String(raw?.varianceNote ?? raw?.variance_note ?? ''),
    _isSubtotal: false, _idx: idx,
  }
  recalcRow(r)
  return r
}

function detailAdjRow(
  raw: G7CostRow | G7EquityRow | G7ImpairmentRow,
  idx: number,
  controlType: ControlType | '',
  previous?: AdjRow,
): AdjRow {
  const increase = raw.section === 'cost'
    ? raw.increaseAmount
    : raw.section === 'equity'
      ? raw.costIncrease + raw.equityIncreaseSubtotal + raw.otherIncrease
      : raw.increaseAmount
  const decrease = raw.section === 'cost'
    ? raw.decreaseAmount
    : raw.section === 'equity'
      ? raw.costDecrease + raw.dividendReceived + raw.otherDecrease
      : raw.decreaseAmount
  const closingAje = raw.section === 'equity'
    ? raw.openingAje
      + raw.ajeCostIncrease + raw.ajeProfitLoss + raw.ajeOci + raw.ajeOtherEquity
      + raw.ajeOtherIncrease - raw.ajeCostDecrease - raw.ajeDividend - raw.ajeOtherDecrease
    : raw.openingAje + raw.ajeIncrease - raw.ajeDecrease
  const closingRje = raw.section === 'equity'
    ? raw.openingRje
      + raw.rjeCostIncrease + raw.rjeProfitLoss + raw.rjeOci + raw.rjeOtherEquity
      + raw.rjeOtherIncrease - raw.rjeCostDecrease - raw.rjeDividend - raw.rjeOtherDecrease
    : raw.openingRje + raw.rjeIncrease - raw.rjeDecrease
  const openingAdjusted = raw.auditedOpeningAmount
  const closingUnadjusted = raw.closingAmount
  const closingAdjusted = raw.auditedClosingAmount

  return {
    id: `g7-2:${raw.id}`,
    item: raw.investeeName,
    controlType,
    openingUnadjusted: raw.openingAmount,
    openingAJE: raw.openingAje,
    openingRJE: raw.openingRje,
    openingAdjusted,
    debitAmount: increase,
    creditAmount: decrease,
    closingUnadjusted,
    closingAJE: closingAje,
    closingRJE: closingRje,
    closingAdjusted,
    changeAmount: Math.round((closingAdjusted - openingAdjusted) * 100) / 100,
    changeRate: calcChangeRate(openingAdjusted, closingAdjusted),
    varianceNote: previous?.varianceNote || '',
    _isSubtotal: false,
    _idx: idx,
    _autoClosing: false,
  }
}

function applyG7DetailRows(payload: unknown, persist = false): void {
  const detail = normalizeG7DetailRows(payload)
  const previous = new Map(
    groups.flatMap(group => group.rows.map(row => [row.id, row] as const)),
  )
  const mappings: Array<{
    id: EditableGroupType
    controlType: ControlType | ''
    rows: Array<G7CostRow | G7EquityRow | G7ImpairmentRow>
  }> = [
    { id: 'subsidiary', controlType: 'subsidiary', rows: detail.costRows },
    {
      id: 'joint_venture',
      controlType: 'joint_venture',
      rows: detail.equityRows.filter(row => row.relationship === 'joint_venture'),
    },
    {
      id: 'associate',
      controlType: 'associate',
      rows: detail.equityRows.filter(row => row.relationship === 'associate'),
    },
    { id: 'impairment', controlType: '', rows: detail.impairmentRows },
  ]
  for (const mapping of mappings) {
    const group = groups.find(item => item.id === mapping.id)
    if (!group) continue
    group.rows = mapping.rows.map((row, index) =>
      detailAdjRow(row, index, mapping.controlType, previous.get(`g7-2:${row.id}`)),
    )
  }
  if (persist && !isReadonly.value) {
    isDirty.value = true
    schedulePersist()
  }
  schedulePublish()
}

function onDetailUpdated(event: Event): void {
  const rows = (event as CustomEvent<{ rows?: unknown }>).detail?.rows
  if (rows) applyG7DetailRows(rows, true)
}

const DEFAULT_SUBSIDIARIES = ['子公司A', '子公司B', '子公司C']
const DEFAULT_JV = ['合营企业A', '合营企业B']
const DEFAULT_ASSOCIATES = ['联营企业A', '联营企业B', '联营企业C']
const DEFAULT_IMPAIRMENT = ['减值准备']

function hydrateData(saved?: any): void {
  const data = saved ?? props.htmlData
  const groupConfigs: { id: string; ct: ControlType | ''; defaults: string[] }[] = [
    { id: 'subsidiary', ct: 'subsidiary', defaults: DEFAULT_SUBSIDIARIES },
    { id: 'joint_venture', ct: 'joint_venture', defaults: DEFAULT_JV },
    { id: 'associate', ct: 'associate', defaults: DEFAULT_ASSOCIATES },
    { id: 'impairment', ct: '', defaults: DEFAULT_IMPAIRMENT },
  ]

  for (const cfg of groupConfigs) {
    const group = groups.find(g => g.id === cfg.id)!
    const raw = data?.adjudication?.groups?.find((g: any) => g.id === cfg.id || g.groupType === cfg.id)
      ?? data?.groups?.find((g: any) => g.id === cfg.id || g.groupType === cfg.id)
    const rowsRaw = raw?.rows ?? data?.[cfg.id] ?? data?.sections?.[cfg.id]
    if (Array.isArray(rowsRaw) && rowsRaw.length > 0) {
      group.rows = rowsRaw.map((r: any, i: number) =>
        makeRow(r.item || r.name || `项目${i + 1}`, i, r.controlType || cfg.ct, r),
      )
    } else {
      group.rows = cfg.defaults.map((item, i) => makeRow(item, i, cfg.ct))
    }
  }

  if (!saved) {
    auditNote.value = data?.auditNote ?? data?.audit_note ?? ''
    auditConclusion.value = data?.auditConclusion ?? data?.audit_conclusion ?? ''
  }
}

function serializeGroups(): object {
  return {
    groups: groups.map(g => ({
      id: g.id,
      groupType: g.groupType,
      title: g.title,
      rows: g.rows.filter(r => !r._isSubtotal).map(r => ({
        id: r.id,
        item: r.item,
        controlType: r.controlType,
        openingUnadjusted: r.openingUnadjusted,
        openingAJE: r.openingAJE,
        openingRJE: r.openingRJE,
        openingAdjusted: r.openingAdjusted,
        debitAmount: r.debitAmount,
        creditAmount: r.creditAmount,
        closingUnadjusted: r.closingUnadjusted,
        closingAJE: r.closingAJE,
        closingRJE: r.closingRJE,
        closingAdjusted: r.closingAdjusted,
        changeAmount: r.changeAmount,
        changeRate: r.changeRate,
        varianceNote: r.varianceNote,
      })),
    })),
    investmentTotal: {
      openingAdjusted: investmentTotalRow.value.openingAdjusted,
      closingAdjusted: investmentTotalRow.value.closingAdjusted,
    },
    netValue: {
      openingAdjusted: netValueRow.value.openingAdjusted,
      closingAdjusted: netValueRow.value.closingAdjusted,
    },
  }
}

function schedulePersist(): void {
  if (isReadonly.value || !props.wpId) return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    persistTimer = null
    void persistTable(false)
  }, 1500)
}

async function persistTable(showMsg: boolean): Promise<void> {
  if (isReadonly.value || !props.wpId) return
  saving.value = true
  try {
    const payload = JSON.stringify(serializeGroups())
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: DATA_KEY, conclusion: null, remark: payload }],
    }, { _silent: !showMsg } as any)
    isDirty.value = false
    if (showMsg) ElMessage.success('审定表已保存')
    publishAdjudicated({ writebackTb: true })
    try {
      const { emitG7SourceRowsSaved } = await import('../../composables/g7DisclosureCrossSheet')
      emitG7SourceRowsSaved({
        projectId: props.projectId,
        wpId: props.wpId,
        itemIds: [DATA_KEY],
      })
    } catch { /* ignore */ }
  } catch {
    if (showMsg) ElMessage.warning('保存失败，请重试')
  } finally {
    saving.value = false
  }
}

async function saveAll(): Promise<void> {
  if (missingReasonCount.value > 0) {
    ElMessage.warning(`有 ${missingReasonCount.value} 行变动率>20%未填写原因分析，已保存但不完整`)
  }
  await persistTable(true)
}

function pickTbAmount(row: any): number {
  return parseNum(row?.unadjusted_amount ?? row?.audited_amount ?? row?.closing_balance)
}

async function fetchTrialBalance(): Promise<void> {
  // 优先消费 render seed（html_data.tb_values），避免仅打开就依赖二次 API
  const seeded = (props.htmlData as any)?.tb_values
  if (seeded && (seeded.closing != null || seeded.opening != null || seeded.current_amount != null)) {
    tbGross.value = parseNum(seeded.closing ?? seeded.current_amount ?? seeded.audited_amount)
    if (seeded.impairment != null) tbImpairment.value = parseNum(seeded.impairment)
  }

  if (!props.projectId) return
  try {
    const res = await api.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '151' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data ?? res)
      ? (res?.data ?? res)
      : (res?.data?.items ?? [])

    const codeOf = (it: any) => String(it.standard_account_code ?? it.account_code ?? '')
    const exact1511 = list.find(it => codeOf(it) === ACCOUNT_GROSS)
    const exact1512 = list.find(it => codeOf(it) === ACCOUNT_IMPAIRMENT)

    if (exact1511) {
      tbGross.value = pickTbAmount(exact1511)
    } else if (list.length) {
      tbGross.value = list
        .filter(it => /^1511/.test(codeOf(it)) && !/^1512/.test(codeOf(it)))
        .reduce((s, it) => s + pickTbAmount(it), 0)
    }

    if (exact1512) {
      tbImpairment.value = pickTbAmount(exact1512)
    } else if (list.length) {
      tbImpairment.value = list
        .filter(it => /^1512/.test(codeOf(it)))
        .reduce((s, it) => s + pickTbAmount(it), 0)
    }
  } catch {
    try {
      const res = await api.get('/api/trial-balance/query', {
        params: { project_id: props.projectId, account_code: ACCOUNT_GROSS },
        _silent: true,
      } as any)
      const items = res?.data?.items ?? res?.data ?? res?.items ?? []
      if (Array.isArray(items) && items.length > 0) {
        tbGross.value = items.reduce(
          (s: number, it: any) => s + parseNum(it.audited_amount ?? it.unadjusted_amount), 0,
        )
      }
    } catch {
      console.warn('[G7TabAdjudication] fetchTrialBalance failed')
    }
  }
}

/** G7-3 回写：优先按被投资单位落到对应行；否则汇总落到投资侧第一行 */
function onAdjustmentWriteback(ev: Event): void {
  const detail = (ev as CustomEvent).detail
  if (!detail) return
  const aje = parseNum(detail.ajeTotal)
  const rje = parseNum(detail.rjeTotal)
  const code = String(detail.accountCode || ACCOUNT_GROSS)
  const byInvestee = Array.isArray(detail.byInvestee) ? detail.byInvestee : []

  if (code.startsWith(ACCOUNT_IMPAIRMENT)) {
    const impair = groups.find(g => g.id === 'impairment')
    if (!impair || impair.rows.length === 0) return
    if (byInvestee.length) {
      applyInvesteeWritebackToGroupsLocal([impair], byInvestee)
    } else {
      for (const r of impair.rows) {
        r.closingAJE = 0
        r.closingRJE = 0
        recalcRow(r)
      }
      const target = impair.rows[0]
      target.closingAJE = aje
      target.closingRJE = rje
      recalcRow(target)
      markWritebackHits([target.id])
    }
  } else {
    const investGroups = groups.filter(g => g.id !== 'impairment')
    if (byInvestee.length) {
      applyInvesteeWritebackToGroupsLocal(investGroups, byInvestee)
    } else {
      for (const g of investGroups) {
        for (const r of g.rows) {
          r.closingAJE = 0
          r.closingRJE = 0
          recalcRow(r)
        }
      }
      const firstGroup = investGroups.find(g => g.rows.length > 0)
      if (firstGroup) {
        const target = firstGroup.rows[0]
        target.closingAJE = aje
        target.closingRJE = rje
        recalcRow(target)
        markWritebackHits([target.id])
      }
    }
  }
  if (!isReadonly.value) {
    isDirty.value = true
    schedulePersist()
  }
  if (!detail.silent) ElMessage.success('已接收 G7-3 调整回写')
}

function applyInvesteeWritebackToGroupsLocal(
  targetGroups: typeof groups,
  byInvestee: Array<{ investeeName: string; ajeTotal: number; rjeTotal: number }>,
): void {
  const allRows = targetGroups.flatMap(g => g.rows)
  for (const r of allRows) {
    r.closingAJE = 0
    r.closingRJE = 0
    recalcRow(r)
  }
  let unmatchedAje = 0
  let unmatchedRje = 0
  const hitIds: string[] = []
  for (const part of byInvestee) {
    const name = String(part.investeeName || '').trim()
    const hit = allRows.find((row) => {
      const item = String(row.item || '').trim()
      return item && name && (item === name || item.includes(name) || name.includes(item))
    })
    if (hit) {
      hit.closingAJE = parseNum(hit.closingAJE) + parseNum(part.ajeTotal)
      hit.closingRJE = parseNum(hit.closingRJE) + parseNum(part.rjeTotal)
      recalcRow(hit)
      hitIds.push(hit.id)
    } else {
      unmatchedAje += parseNum(part.ajeTotal)
      unmatchedRje += parseNum(part.rjeTotal)
    }
  }
  if ((Math.abs(unmatchedAje) > 0.005 || Math.abs(unmatchedRje) > 0.005) && allRows[0]) {
    allRows[0].closingAJE = parseNum(allRows[0].closingAJE) + unmatchedAje
    allRows[0].closingRJE = parseNum(allRows[0].closingRJE) + unmatchedRje
    recalcRow(allRows[0])
    hitIds.push(allRows[0].id)
  }
  markWritebackHits(hitIds)
}

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
  if (writebackHitIds.value.has(row.id)) return 'row-writeback-hit'
  if (isRateWarning(row.changeRate) && !(row.varianceNote || '').trim()) return 'row-need-reason'
  return ''
}

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
    let writeback: any = null
    let detailRows: unknown = null
    for (const it of items) {
      if (it.item_id === NOTE_KEY && it.remark) auditNote.value = it.remark
      else if (it.item_id === CONCLUSION_KEY && it.remark) auditConclusion.value = it.remark
      else if (it.item_id === DATA_KEY && it.remark) {
        try {
          const parsed = JSON.parse(it.remark)
          hydrateData(parsed)
        } catch { /* ignore corrupt */ }
      } else if (it.item_id === 'G7-1-adjustment-writeback' && it.remark) {
        try { writeback = JSON.parse(it.remark) } catch { /* ignore corrupt */ }
      } else if (it.item_id === 'G7-2-rows' && it.conclusion) {
        try { detailRows = JSON.parse(it.conclusion) } catch { /* ignore corrupt */ }
      }
    }
    if (detailRows) applyG7DetailRows(detailRows, false)
    if (writeback?.gross) {
      onAdjustmentWriteback(new CustomEvent('g7:adjustment-writeback', {
        detail: { accountCode: ACCOUNT_GROSS, ...writeback.gross, silent: true },
      }))
    }
    if (writeback?.impairment) {
      onAdjustmentWriteback(new CustomEvent('g7:adjustment-writeback', {
        detail: { accountCode: ACCOUNT_IMPAIRMENT, ...writeback.impairment, silent: true },
      }))
    }
  } catch { /* silent */ }
}

onMounted(async () => {
  loadCollapseState()
  hydrateData()
  await loadAuditResponses()
  await fetchTrialBalance()
  // 不在 mount 时 publish/writebackTB，避免仅打开页面就改写试算表
  window.addEventListener('g7:adjustment-writeback', onAdjustmentWriteback)
  window.addEventListener('g7:detail-updated', onDetailUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('g7:adjustment-writeback', onAdjustmentWriteback)
  window.removeEventListener('g7:detail-updated', onDetailUpdated)
  if (persistTimer) clearTimeout(persistTimer)
  if (publishTimer) clearTimeout(publishTimer)
  if (isDirty.value) void persistTable(false)
})
</script>

<style scoped>
.g7-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

.tb-info-bar {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  padding: 8px 12px; background: #f0f9eb; border: 1px solid #e1f3d8;
  border-radius: 4px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px);
}
.tb-label { font-weight: 500; color: #606266; }
.tb-amount { font-weight: 600; color: #303133; }
.tb-sep { color: #c0c4cc; }
.diff-value { font-weight: 600; color: #67c23a; }
.diff-red { color: #f56c6c; }

.adj-scroll-container {
  max-height: 680px; overflow-y: auto;
  border: 1px solid #ebeef5; border-radius: 4px; padding: 4px;
}

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

.group-body { margin-bottom: 4px; }
.adj-table { margin-top: 4px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.row-bold { font-weight: 700; }
:deep(.row-subtotal) { background: #f5f7fa !important; font-weight: 700; }
:deep(.row-need-reason) { background: #fdf6ec !important; }
:deep(.row-writeback-hit) { background: #e1f3d8 !important; transition: background-color 0.3s; }
.rate-orange { color: #e6a23c; font-weight: 600; }
.need-reason :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }

.reason-warn { margin-top: 12px; }
.note-card { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.guidance-details {
  margin-top: 16px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 4px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-content p { margin: 4px 0; }
</style>
