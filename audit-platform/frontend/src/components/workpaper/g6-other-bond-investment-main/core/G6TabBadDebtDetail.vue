<!--
  G6TabBadDebtDetail.vue — G6-3 坏账准备明细表（20列 → 2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 未审+调整(10列): 序号|投资项目|①账面余额|②信用损失率|③未审坏账(公式)|⑤余额调整|②A调整后损失率|⑥坏账调整(公式)|⑦审定余额(公式)|⑧审定坏账(公式)|⑨审定账面(公式)
  - Tab2: 审定数(10列): 序号|投资项目|上年末坏账|本年计提|本年转回|本年核销|期末坏账(公式)|差异|充分性(下拉)|结论|证据索引|备注

  ECL公式链：
  - ③ = ① × ②
  - ⑥ = ⑤×②A + ①×(②A-②)
  - ⑦ = ① + ⑤
  - ⑧ = ③ + ⑥ = ⑦×②A（恒等式）
  - ⑨ = ⑦ - ⑧

  Stage分组：Stage1/Stage2/Stage3/单项 + 各组小计 + 总计行
  方法论上下文（琥珀色左边线+浅黄背景）
  公式列虚线下划线+tooltip
  底部审计结论textarea + AI按钮

  Spec: .kiro/specs/g6-other-bond-investment-main/ Task 5.2
  Requirements: 6.1, 6.2, 6.3
-->
<template>
  <div class="g6-bad-debt">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <strong>ECL公式链推导：</strong>
      <div class="formula-chain">
        <span>③未审坏账 = ①余额 × ②损失率</span>
        <span>⑥坏账调整 = ⑤调整 × ②A + ①余额 × (②A - ②)</span>
        <span>⑦审定余额 = ① + ⑤</span>
        <span>⑧审定坏账 = ③ + ⑥ = ⑦ × ②A</span>
        <span>⑨审定账面 = ⑦ - ⑧ = ⑦ × (1 - ②A)</span>
      </div>
    </div>

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-3 坏账准备明细表</h3>
      <div class="head-actions">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in dropdownOptions"
                :key="opt.command"
                :command="opt.command"
                :disabled="opt.disabled"
              >{{ opt.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G6-3-bad-debt')">💬复核</el-button>
      </div>
    </div>

    <!-- Stage分组表格 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="bad-debt-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row._groupLabel }}小计</span>
          </template>
          <template v-else-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 投资项目列（始终显示作为锚定列） -->
      <el-table-column label="投资项目" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 未审+调整列 ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="①账面余额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookBalance) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'bookBalance', v)" />
              <span v-else>{{ fmtNum(row.bookBalance) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②信用损失率" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.creditLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                :class="{ 'rate-invalid': row.creditLossRate < 0 || row.creditLossRate > 1 }"
                @change="(v: number) => updateField(row.id, 'creditLossRate', v)" />
              <span v-else>{{ fmtPercent(row.creditLossRate) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="③未审坏账" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.unadjustedProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="③ = ① × ②" placement="top">
                <span class="formula-cell">{{ fmtNum(row.unadjustedProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑤余额调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.balanceAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'balanceAdjustment', v)" />
              <span v-else>{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②A调整后损失率" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.adjustedLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                :class="{ 'rate-invalid': row.adjustedLossRate < 0 || row.adjustedLossRate > 1 }"
                @change="(v: number) => updateField(row.id, 'adjustedLossRate', v)" />
              <span v-else>{{ fmtPercent(row.adjustedLossRate) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑥坏账调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentAdjustment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑥ = ⑤×②A + ①×(②A-②)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentAdjustment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑦审定余额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjustedBalance) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑦ = ① + ⑤" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjustedBalance) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑧审定坏账" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjustedProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑧ = ③ + ⑥ = ⑦×②A" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjustedProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑨审定账面" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjustedBookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑨ = ⑦ - ⑧" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjustedBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 审定数列 ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="上年末坏账" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.priorProvision) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.priorProvision" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'priorProvision', v)" />
              <span v-else>{{ fmtNum(row.priorProvision) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年计提" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.currentProvision) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.currentProvision" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'currentProvision', v)" />
              <span v-else>{{ fmtNum(row.currentProvision) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年转回" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.currentReversal) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.currentReversal" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'currentReversal', v)" />
              <span v-else>{{ fmtNum(row.currentReversal) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年核销" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.currentWriteOff) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.currentWriteOff" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'currentWriteOff', v)" />
              <span v-else>{{ fmtNum(row.currentWriteOff) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末坏账" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.endingProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="期末坏账 = 上年末 + 计提 - 转回 - 核销" placement="top">
                <span class="formula-cell">{{ fmtNum(row.endingProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="差异" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.difference" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'difference', v)" />
              <span v-else>{{ fmtNum(row.difference) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="充分性" min-width="90">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" :model-value="row.adequacy" size="small" style="width:100%"
                @change="(v: string) => updateField(row.id, 'adequacy', v)">
                <el-option value="充分" label="充分" />
                <el-option value="基本充分" label="基本充分" />
                <el-option value="不充分" label="不充分" />
              </el-select>
              <span v-else>{{ row.adequacy }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="结论" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small"
                @change="(v: string) => updateField(row.id, 'conclusion', v)" />
              <span v-else>{{ row.conclusion }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="证据索引" width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <GtIndexChip v-else :value="row.indexRef" />
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @change="(v: string) => updateField(row.id, 'remark', v)" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isSubtotal && !row._isTotal" title="确认删除？"
            @confirm="removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入坏账准备的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>③ 未审坏账 = ① 账面余额 × ② 信用损失率</li>
        <li>⑥ 坏账调整 = ⑤×②A + ①×(②A-②)，可为负值</li>
        <li>⑦ 审定余额 = ① + ⑤</li>
        <li>⑧ 审定坏账 = ③ + ⑥ = ⑦×②A（恒等式验证）</li>
        <li>⑨ 审定账面 = ⑦ - ⑧ = ⑦×(1-②A)</li>
        <li>损失率②和②A须在[0,1]区间内，超出范围红框提示</li>
        <li>Stage1=12个月ECL / Stage2=整个存续期ECL / Stage3=已发生信用减值</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabBadDebtDetail.vue — G6-3 坏账准备明细表（2区段Tab + ECL公式链 + Stage分组）
 *
 * - el-segmented 切换 Tab1(未审+调整) / Tab2(审定数)
 * - 行共享同一reactive数组，Tab切换只改可见列
 * - selectedRowIndex跨Tab保持（行同步）
 * - Stage1/Stage2/Stage3/单项分组 + 小计行 + 总计行
 * - ECL公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧
 * - 损失率超出[0,1]红框高亮
 * - 底部审计结论textarea + AI按钮
 * - 动态行增删 + 导入导出(useG6MainImportExport, sheet='G6-3')
 */
import { ref, reactive, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  calcUnadjustedProvision,
  calcImpairmentAdjustment,
  calcAdjustedBookValue,
  parseNum,
} from '@/composables/useG6MainFormulaEngine'
import {
  useG6MainImportExport,
  type G6MainImportableSheet,
} from '@/components/workpaper/composables/useG6MainImportExport'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 区段Tab ─────────────────────────────────────────────────────────────────

const activeTab = ref<'tab1' | 'tab2'>('tab1')

const segmentOptions = [
  { label: '未审+调整', value: 'tab1' },
  { label: '审定数', value: 'tab2' },
]

// ─── 行数据类型 ──────────────────────────────────────────────────────────────

type StageGroup = 'Stage1' | 'Stage2' | 'Stage3' | '单项'

interface BadDebtRow {
  id: string
  seq: number
  investProject: string
  stageGroup: StageGroup
  // Tab1 未审+调整
  bookBalance: number           // ①
  creditLossRate: number        // ②
  unadjustedProvision: number   // ③ = ①×②
  balanceAdjustment: number     // ⑤
  adjustedLossRate: number      // ②A
  impairmentAdjustment: number  // ⑥ = ⑤×②A + ①×(②A-②)
  adjustedBalance: number       // ⑦ = ① + ⑤
  adjustedProvision: number     // ⑧ = ③ + ⑥
  adjustedBookValue: number     // ⑨ = ⑦ - ⑧
  // Tab2 审定数
  priorProvision: number
  currentProvision: number
  currentReversal: number
  currentWriteOff: number
  endingProvision: number       // 公式 = 上年末 + 计提 - 转回 - 核销
  difference: number
  adequacy: string
  conclusion: string
  indexRef: string
  remark: string
}

interface DisplayRow extends BadDebtRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _groupLabel?: string
}

function createEmptyRow(seq: number, name: string, stage: StageGroup = 'Stage1'): BadDebtRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investProject: name,
    stageGroup: stage,
    bookBalance: 0,
    creditLossRate: 0,
    unadjustedProvision: 0,
    balanceAdjustment: 0,
    adjustedLossRate: 0,
    impairmentAdjustment: 0,
    adjustedBalance: 0,
    adjustedProvision: 0,
    adjustedBookValue: 0,
    priorProvision: 0,
    currentProvision: 0,
    currentReversal: 0,
    currentWriteOff: 0,
    endingProvision: 0,
    difference: 0,
    adequacy: '',
    conclusion: '',
    indexRef: '',
    remark: '',
  }
}

const rows = reactive<BadDebtRow[]>([])
const selectedRowIndex = ref(0)
const auditConclusion = ref('')

// ─── ECL公式重算 ─────────────────────────────────────────────────────────────

function recalcRow(row: BadDebtRow): void {
  // ③ = ① × ②
  row.unadjustedProvision = calcUnadjustedProvision(row.bookBalance, row.creditLossRate)
  // ⑥ = ⑤×②A + ①×(②A-②)
  row.impairmentAdjustment = calcImpairmentAdjustment(
    row.balanceAdjustment, row.adjustedLossRate, row.bookBalance, row.creditLossRate
  )
  // ⑦ = ① + ⑤
  row.adjustedBalance = Math.round((parseNum(row.bookBalance) + parseNum(row.balanceAdjustment)) * 100) / 100
  // ⑧ = ③ + ⑥
  row.adjustedProvision = Math.round((parseNum(row.unadjustedProvision) + parseNum(row.impairmentAdjustment)) * 100) / 100
  // ⑨ = ⑦ - ⑧
  row.adjustedBookValue = calcAdjustedBookValue(row.adjustedBalance, row.adjustedProvision)
  // 期末坏账 = 上年末 + 计提 - 转回 - 核销
  row.endingProvision = Math.round(
    (parseNum(row.priorProvision) + parseNum(row.currentProvision)
    - parseNum(row.currentReversal) - parseNum(row.currentWriteOff)) * 100
  ) / 100
}

// ─── Stage分组显示行 ─────────────────────────────────────────────────────────

function calcGroupSubtotal(groupRows: BadDebtRow[]): Partial<DisplayRow> {
  return {
    bookBalance: groupRows.reduce((s, r) => s + parseNum(r.bookBalance), 0),
    unadjustedProvision: groupRows.reduce((s, r) => s + parseNum(r.unadjustedProvision), 0),
    balanceAdjustment: groupRows.reduce((s, r) => s + parseNum(r.balanceAdjustment), 0),
    impairmentAdjustment: groupRows.reduce((s, r) => s + parseNum(r.impairmentAdjustment), 0),
    adjustedBalance: groupRows.reduce((s, r) => s + parseNum(r.adjustedBalance), 0),
    adjustedProvision: groupRows.reduce((s, r) => s + parseNum(r.adjustedProvision), 0),
    adjustedBookValue: groupRows.reduce((s, r) => s + parseNum(r.adjustedBookValue), 0),
    priorProvision: groupRows.reduce((s, r) => s + parseNum(r.priorProvision), 0),
    currentProvision: groupRows.reduce((s, r) => s + parseNum(r.currentProvision), 0),
    currentReversal: groupRows.reduce((s, r) => s + parseNum(r.currentReversal), 0),
    currentWriteOff: groupRows.reduce((s, r) => s + parseNum(r.currentWriteOff), 0),
    endingProvision: groupRows.reduce((s, r) => s + parseNum(r.endingProvision), 0),
  }
}

const displayRows = computed<DisplayRow[]>(() => {
  const stages: StageGroup[] = ['Stage1', 'Stage2', 'Stage3', '单项']
  const result: DisplayRow[] = []

  for (const stage of stages) {
    const groupRows = rows.filter(r => r.stageGroup === stage)
    if (groupRows.length === 0) continue

    for (const r of groupRows) result.push(r as DisplayRow)

    // 小计行
    result.push({
      ...createEmptyRow(0, ''),
      _isSubtotal: true,
      _groupLabel: stage,
      ...calcGroupSubtotal(groupRows),
    } as DisplayRow)
  }

  // 总计行
  const grandTotal = calcGroupSubtotal(rows as BadDebtRow[])
  result.push({
    ...createEmptyRow(0, ''),
    _isTotal: true,
    ...grandTotal,
  } as DisplayRow)

  return result
})

// ─── 行同步（selectedRowIndex 跨Tab保持） ───────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isSubtotal || row._isTotal) return
  const idx = rows.findIndex(r => r.id === row.id)
  if (idx >= 0) selectedRowIndex.value = idx
}

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  if (row._isTotal) return 'row-total'
  return ''
}

// ─── 字段更新（触发ECL公式重算） ─────────────────────────────────────────────

function updateField(id: string, field: keyof BadDebtRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? (typeof (row as any)[field] === 'number' ? 0 : '')
  recalcRow(row)
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim(), 'Stage1')
      rows.push(newRow)
      recalcRow(newRow)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => reloadData(),
})

const dropdownOptions = computed(() => ie.getDropdownOptions('G6-3'))

async function handleDropdownCommand(command: string) {
  const [action, sheet] = command.split(':') as [string, G6MainImportableSheet]
  if (action === 'export-template') {
    await ie.exportTemplate(sheet)
  } else if (action === 'export-data') {
    await ie.exportData(sheet)
  } else if (action === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) await ie.importData(sheet, file)
    }
    input.click()
  }
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成审计结论功能将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

function reloadData() {
  loadFromHtmlData(props.htmlData)
}

function loadFromHtmlData(data: Record<string, any> | null) {
  rows.splice(0, rows.length)
  const items: any[] = data?.bad_debt_rows || data?.rows || []
  if (items.length === 0) {
    // 默认每个Stage各2行 = 8行
    const stages: StageGroup[] = ['Stage1', 'Stage1', 'Stage2', 'Stage2', 'Stage3', 'Stage3', '单项', '单项']
    stages.forEach((stage, i) => {
      rows.push(createEmptyRow(i + 1, '', stage))
    })
  } else {
    items.forEach((item: any, i: number) => {
      const row = createEmptyRow(
        i + 1,
        item.investProject || item.invest_project || '',
        (item.stageGroup || item.stage_group || 'Stage1') as StageGroup,
      )
      Object.assign(row, {
        bookBalance: parseNum(item.bookBalance ?? item.book_balance),
        creditLossRate: parseNum(item.creditLossRate ?? item.credit_loss_rate),
        balanceAdjustment: parseNum(item.balanceAdjustment ?? item.balance_adjustment),
        adjustedLossRate: parseNum(item.adjustedLossRate ?? item.adjusted_loss_rate),
        priorProvision: parseNum(item.priorProvision ?? item.prior_provision),
        currentProvision: parseNum(item.currentProvision ?? item.current_provision),
        currentReversal: parseNum(item.currentReversal ?? item.current_reversal),
        currentWriteOff: parseNum(item.currentWriteOff ?? item.current_write_off),
        difference: parseNum(item.difference),
        adequacy: item.adequacy || '',
        conclusion: item.conclusion || '',
        indexRef: item.indexRef || item.index_ref || '',
        remark: item.remark || '',
      })
      recalcRow(row)
      rows.push(row)
    })
  }
}

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})
</script>

<style scoped>
.g6-bad-debt {
  padding: 12px 16px;
}
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.methodology-context strong {
  color: #e6a23c;
}
.formula-chain {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #606266;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bad-debt-table {
  font-size: var(--wp-font-size, 13px);
}
.bad-debt-table :deep(.row-subtotal) {
  background-color: #f0f9eb;
  font-weight: 500;
}
.bad-debt-table :deep(.row-total) {
  background-color: #fafafa;
  font-weight: 600;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #303133;
}
.subtotal-label {
  font-weight: 500;
  color: #67c23a;
  font-size: 12px;
}
.total-label {
  font-weight: 600;
  color: #606266;
}
.subtotal-num {
  font-weight: 500;
}
.compact-num {
  width: 100%;
}
.compact-num :deep(.el-input__inner) {
  text-align: right;
}
.rate-invalid :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
.delete-icon {
  cursor: pointer;
  color: #f56c6c;
  font-size: 14px;
}
.delete-icon:hover {
  color: #e6001f;
}
.conclusion-card {
  margin-top: 16px;
}
.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}
.prep-hint {
  margin-top: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 6px 0 0;
  padding-left: 20px;
}
.prep-hint li {
  margin-bottom: 3px;
}
</style>
