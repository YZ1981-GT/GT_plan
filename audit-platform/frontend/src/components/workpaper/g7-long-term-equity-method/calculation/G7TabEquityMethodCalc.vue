<!--
  G7TabEquityMethodCalc.vue — G7-14 权益法测算表（54行×20列→2区段Tab+虚拟滚动，★最核心★）

  蓝色渐变引导区（5步骤指引, 2列grid）
  方法论上下文区域（琥珀色左边线+浅黄背景：权益法核算公式链 CAS2）

  2区段Tab切换（el-segmented）：
  - Tab1 净利润调整(10列): 被投资单位|报告净利润|内部交易抵销|FV折旧|政策调整|其他调整|调整后净利润(公式)|持股比例|享有份额(公式)|企业确认收益
  - Tab2 权益法计算(10列): 被投资单位|收益差异(公式)|OCI变动|OCI份额(公式)|其他权益变动|其他权益份额(公式)|股利|期初余额|期末余额(公式)|审计结论

  公式列：
  - adjustedNetProfit = calcAdjustedNetProfit(reported, internal, fv, policy, other)
  - equityShare = calcEquityShare(adjustedNetProfit, ratio)
  - incomeDifference = equityShare - confirmedIncome
  - ociShare = calcEquityShare(ociChange, ratio)
  - otherEquityShare = calcEquityShare(otherEquityChange, ratio)
  - closingBalance = calcEquityMethodBalance(opening, equityShare, ociShare, otherEquityShare, dividend)

  |收益差异| > 重要性水平 → 红色高亮 + tooltip "收益差异超过重要性水平"
  54行虚拟滚动 + 按被投资单位分组 + 行同步 + 动态行增删
  底部审计结论textarea(AI辅助 equity-method-conclusion) + details编制提示折叠

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 6.2
  Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 7.4, 7.5
-->
<template>
  <div class="g7-tab-equity-method-calc">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-14 权益法测算表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-14-equity-method-calc')">💬复核</el-button>
      </div>
    </div>

    <!-- 蓝色渐变引导区（5步骤指引, 2列grid） -->
    <div class="guidance-steps">
      <div class="step-item">
        <span class="step-num">①</span>
        <span class="step-text">填入被投资方报告净利润</span>
      </div>
      <div class="step-item">
        <span class="step-num">②</span>
        <span class="step-text">填入各项调整（内部交易/FV折旧/政策/其他）</span>
      </div>
      <div class="step-item">
        <span class="step-num">③</span>
        <span class="step-text">系统自动计算调整后净利润和享有份额</span>
      </div>
      <div class="step-item">
        <span class="step-num">④</span>
        <span class="step-text">填入企业确认投资收益，系统自动计算差异</span>
      </div>
      <div class="step-item">
        <span class="step-num">⑤</span>
        <span class="step-text">填入OCI/其他权益变动/股利，系统自动计算期末余额</span>
      </div>
    </div>

    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>权益法核算公式（CAS2）：</strong></p>
      <p>• 调整后净利润 = 报告净利润 - 内部交易抵销 - 公允价值折旧摊销 ± 会计政策调整 ± 其他调整</p>
      <p>• 应享有份额 = 调整后净利润 × 持股比例</p>
      <p>• 收益差异 = 应享有份额 - 企业确认投资收益</p>
      <p>• 期末余额 = 期初 + 投资收益份额 + OCI份额 + 其他权益份额 - 利润分配(股利)</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：复核权益法下投资收益、其他综合收益及其他权益变动的确认是否恰当，验证应享有份额计算准确、收益差异在可接受范围内。"
      class="objective-alert"
    />

    <!-- 重要性水平设置 -->
    <div class="materiality-bar">
      <span class="materiality-label">重要性水平：</span>
      <el-input-number
        v-if="!isReadonly"
        v-model="materialityLevel"
        :controls="false"
        :precision="2"
        size="small"
        style="width: 160px"
        placeholder="重要性水平(元)"
        @change="emitSave"
      />
      <span v-else class="materiality-value">{{ fmtAmount(materialityLevel) }}</span>
      <span class="materiality-hint">（|收益差异| 超过此值将红色高亮）</span>
    </div>

    <!-- 2区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-14" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rowCount }} 行</el-tag>
      </div>
    </div>

    <!-- 54行虚拟滚动 + 按被投资单位分组 -->
    <div class="equity-scroll-container">
      <template v-for="group in groups" :key="group.investeeName">
        <!-- 分组标题 -->
        <div class="group-header" @click="toggleGroup(group.investeeName)">
          <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.investeeName] }">
            <ArrowDown />
          </el-icon>
          <span class="group-name">{{ group.investeeName }}</span>
          <span class="group-count">({{ group.rows.length }}行)</span>
          <div class="group-actions" v-if="!isReadonly" @click.stop>
            <el-button size="small" type="primary" link @click="addRowToGroup(group.investeeName)">
              + 添加行
            </el-button>
          </div>
        </div>

        <!-- 分组表格 -->
        <div v-show="expandedMap[group.investeeName]" class="group-body">
          <el-table
            :data="group.rows"
            border
            size="small"
            class="equity-calc-table"
            :max-height="400"
            highlight-current-row
            row-key="id"
            @current-change="(row: any) => onCurrentChange(row)"
          >
            <!-- 序号 -->
            <el-table-column type="index" label="#" width="45" align="center" fixed />

            <!-- ═══ Tab1: 净利润调整(10列) ═══ -->
            <template v-if="activeTab === 'tab1'">
              <!-- 报告净利润 -->
              <el-table-column label="报告净利润" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.reportedNetProfit" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'reportedNetProfit', v)" />
                  <span v-else>{{ fmtAmount(row.reportedNetProfit) }}</span>
                </template>
              </el-table-column>

              <!-- 内部交易抵销 -->
              <el-table-column label="内部交易抵销" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.internalTransactionAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'internalTransactionAdj', v)" />
                  <span v-else>{{ fmtAmount(row.internalTransactionAdj) }}</span>
                </template>
              </el-table-column>

              <!-- FV折旧摊销 -->
              <el-table-column label="FV折旧摊销" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.fvDepreciationAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'fvDepreciationAdj', v)" />
                  <span v-else>{{ fmtAmount(row.fvDepreciationAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 会计政策调整 -->
              <el-table-column label="会计政策调整" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.accountingPolicyAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'accountingPolicyAdj', v)" />
                  <span v-else>{{ fmtAmount(row.accountingPolicyAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 其他调整 -->
              <el-table-column label="其他调整" min-width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.otherAdj" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'otherAdj', v)" />
                  <span v-else>{{ fmtAmount(row.otherAdj) }}</span>
                </template>
              </el-table-column>

              <!-- 调整后净利润（公式列） -->
              <el-table-column label="调整后净利润" min-width="130" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'调整后净利润 = 报告净利润 - 内部交易 - FV折旧 + 政策调整 + 其他调整'"
                  >{{ fmtAmount(row.adjustedNetProfit) }}</span>
                </template>
              </el-table-column>

              <!-- 持股比例 -->
              <el-table-column label="持股比例" min-width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.investmentRatio" size="small"
                    :controls="false" :precision="4" :step="0.01" :min="0" :max="1"
                    style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'investmentRatio', v)" />
                  <span v-else>{{ fmtPercent(row.investmentRatio) }}</span>
                </template>
              </el-table-column>

              <!-- 享有份额（公式列） -->
              <el-table-column label="享有份额" min-width="120" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'享有份额 = 调整后净利润 × 持股比例'"
                  >{{ fmtAmount(row.equityShare) }}</span>
                </template>
              </el-table-column>

              <!-- 企业确认收益 -->
              <el-table-column label="企业确认收益" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.confirmedIncome" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'confirmedIncome', v)" />
                  <span v-else>{{ fmtAmount(row.confirmedIncome) }}</span>
                </template>
              </el-table-column>
            </template>

            <!-- ═══ Tab2: 权益法计算(10列) ═══ -->
            <template v-if="activeTab === 'tab2'">
              <!-- 收益差异（公式列 + 重要性高亮） -->
              <el-table-column label="收益差异" min-width="130" align="right">
                <template #default="{ row }">
                  <el-tooltip
                    v-if="isOverMateriality(row.incomeDifference)"
                    content="收益差异超过重要性水平"
                    placement="top"
                  >
                    <span class="formula-cell income-diff-warning">
                      {{ fmtAmount(row.incomeDifference) }}
                    </span>
                  </el-tooltip>
                  <span v-else
                    class="formula-cell"
                    :title="'收益差异 = 享有份额 - 企业确认收益'"
                  >{{ fmtAmount(row.incomeDifference) }}</span>
                </template>
              </el-table-column>

              <!-- OCI变动 -->
              <el-table-column label="OCI变动" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.ociChange" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'ociChange', v)" />
                  <span v-else>{{ fmtAmount(row.ociChange) }}</span>
                </template>
              </el-table-column>

              <!-- 享有OCI（公式列） -->
              <el-table-column label="享有OCI" min-width="120" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'享有OCI = OCI变动 × 持股比例'"
                  >{{ fmtAmount(row.ociShare) }}</span>
                </template>
              </el-table-column>

              <!-- 其他权益变动 -->
              <el-table-column label="其他权益变动" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.otherEquityChange" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'otherEquityChange', v)" />
                  <span v-else>{{ fmtAmount(row.otherEquityChange) }}</span>
                </template>
              </el-table-column>

              <!-- 享有其他权益（公式列） -->
              <el-table-column label="享有其他权益" min-width="130" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'享有其他权益 = 其他权益变动 × 持股比例'"
                  >{{ fmtAmount(row.otherEquityShare) }}</span>
                </template>
              </el-table-column>

              <!-- 利润分配(股利) -->
              <el-table-column label="利润分配(股利)" min-width="130" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.dividendDistributed" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'dividendDistributed', v)" />
                  <span v-else>{{ fmtAmount(row.dividendDistributed) }}</span>
                </template>
              </el-table-column>

              <!-- 期初余额 -->
              <el-table-column label="期初余额" min-width="120" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small"
                    :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateNumField(row, 'openingBalance', v)" />
                  <span v-else>{{ fmtAmount(row.openingBalance) }}</span>
                </template>
              </el-table-column>

              <!-- 期末余额（公式列） -->
              <el-table-column label="期末余额" min-width="130" align="right">
                <template #default="{ row }">
                  <span
                    class="formula-cell"
                    :title="'期末余额 = 期初 + 投资收益 + OCI份额 + 其他权益份额 - 股利'"
                  >{{ fmtAmount(row.closingBalance) }}</span>
                </template>
              </el-table-column>

              <!-- 审计结论（下拉） -->
              <el-table-column label="审计结论" min-width="120" align="center">
                <template #default="{ row }">
                  <el-select v-if="!isReadonly" v-model="row.auditConclusion" size="small"
                    style="width:100%" @change="emitSave">
                    <el-option value="无差异" label="无差异" />
                    <el-option value="差异可接受" label="差异可接受" />
                    <el-option value="差异需调整" label="差异需调整" />
                  </el-select>
                  <el-tag v-else size="small" :type="conclusionTagType(row.auditConclusion)">
                    {{ row.auditConclusion }}
                  </el-tag>
                </template>
              </el-table-column>
            </template>

            <!-- 操作列（删除） -->
            <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
              <template #default="{ row }">
                <el-popconfirm :title="`确认删除此行?`" @confirm="deleteRow(row)">
                  <template #reference>
                    <el-button type="danger" link size="small">✕</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="groups.length === 0" class="empty-state">
        <p>暂无权益法测算数据</p>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">
          + 新增被投资单位
        </el-button>
      </div>
    </div>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计说明</span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-head">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link @click="handleAiConclusion">
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据权益法测算结果，总结投资收益差异是否在可接受范围内..."
        @change="emitSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 调整后净利润 = 报告净利润 - 内部交易抵销 - FV折旧摊销 + 会计政策调整 + 其他调整（公式自动计算）</p>
        <p>2. 享有份额 = 调整后净利润 × 持股比例（公式自动计算）</p>
        <p>3. 收益差异 = 享有份额 - 企业确认投资收益（|差异| > 重要性水平时红色高亮，需关注）</p>
        <p>4. OCI份额/其他权益份额 = 变动额 × 持股比例（公式自动计算）</p>
        <p>5. 期末余额 = 期初 + 投资收益份额 + OCI份额 + 其他权益份额 - 利润分配(股利)</p>
        <p>6. 内部交易抵销金额应与G7-15测算表一致；会计政策调整应与G7-6一致性检查表对应</p>
        <p>7. 公式列显示虚线下划线，鼠标悬停可查看公式来源</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabEquityMethodCalc — G7-14 权益法测算表（★最核心★）
 *
 * 54行×20列→2区段Tab + 虚拟滚动 + 按被投资单位分组
 *
 * 公式引擎调用：
 * - calcAdjustedNetProfit → Tab1 调整后净利润
 * - calcEquityShare → Tab1 享有份额 / Tab2 OCI份额 / Tab2 其他权益份额
 * - calcEquityMethodBalance → Tab2 期末余额
 *
 * |收益差异| > materialityLevel → 红色高亮 + tooltip
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 7.4, 7.5
 */
import { ref, reactive, computed, inject, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  parseNum,
  calcAdjustedNetProfit,
  calcEquityShare,
  calcEquityMethodBalance,
} from '../../composables/useG7EquityMethodFormulaEngine'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { EquityMethodCalcRow } from '../../composables/useG7EquityMethodFormData'

// ═══ Props ═══════════════════════════════════════════════════════════════════

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', data: EquityMethodCalcSavePayload): void
}>()

// ═══ Types ═══════════════════════════════════════════════════════════════════

interface EquityCalcGroup {
  investeeName: string
  rows: EquityMethodCalcRow[]
}

interface EquityMethodCalcSavePayload {
  rows: EquityMethodCalcRow[]
  materialityLevel: number
  conclusion: string
  groups: EquityCalcGroup[]
}

// ═══ Injections ═══════════════════════════════════════════════════════════════

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ State ═══════════════════════════════════════════════════════════════════

const isReadonly = computed(() => !!props.readonly)
const groups = reactive<EquityCalcGroup[]>([])
const expandedMap = reactive<Record<string, boolean>>({})
const materialityLevel = ref<number>(0)
const conclusion = ref<string>('')
const selectedRowIndex = ref<number>(-1)

// ═══ 审计说明持久化（checklist_responses，conclusion:null） ═══════════════════

const auditFormData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const AUDIT_NOTE_KEY = 'G7-14-audit-note'
const auditNote = ref('')
const rowCount = computed(() => groups.reduce((n, g) => n + g.rows.length, 0))

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(AUDIT_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

type TabKey = 'tab1' | 'tab2'
const activeTab = ref<TabKey>('tab1')

const segmentOptions = [
  { label: '净利润调整(10)', value: 'tab1' },
  { label: '权益法计算(10)', value: 'tab2' },
]

// ═══ 折叠状态持久化 ═══════════════════════════════════════════════════════

const STORAGE_KEY_PREFIX = 'g7-equity-method-calc-collapse-'

function getStorageKey(): string {
  return `${STORAGE_KEY_PREFIX}${props.wpId}`
}

function loadCollapseState(): void {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (raw) {
      const saved = JSON.parse(raw) as Record<string, boolean>
      Object.assign(expandedMap, saved)
    }
  } catch { /* ignore */ }
}

function saveCollapseState(): void {
  try {
    localStorage.setItem(getStorageKey(), JSON.stringify({ ...expandedMap }))
  } catch { /* ignore */ }
}

function toggleGroup(name: string): void {
  expandedMap[name] = !expandedMap[name]
  saveCollapseState()
}

// ═══ 行同步 ═══════════════════════════════════════════════════════════════════

function onCurrentChange(row: EquityMethodCalcRow | null) {
  if (row) {
    const allRows = groups.flatMap(g => g.rows)
    selectedRowIndex.value = allRows.findIndex(r => r.id === row.id)
  }
}

// ═══ 公式自动计算 ═══════════════════════════════════════════════════════════

/**
 * 重新计算单行所有公式列
 * - adjustedNetProfit = calcAdjustedNetProfit(reported, internal, fv, policy, other)
 * - equityShare = calcEquityShare(adjustedNetProfit, ratio)
 * - incomeDifference = equityShare - confirmedIncome
 * - ociShare = calcEquityShare(ociChange, ratio)
 * - otherEquityShare = calcEquityShare(otherEquityChange, ratio)
 * - closingBalance = calcEquityMethodBalance(opening, equityShare, ociShare, otherEquityShare, dividend)
 */
function recalcRow(row: EquityMethodCalcRow): void {
  // Tab1 公式
  row.adjustedNetProfit = calcAdjustedNetProfit(
    row.reportedNetProfit,
    row.internalTransactionAdj,
    row.fvDepreciationAdj,
    row.accountingPolicyAdj,
    row.otherAdj,
  )
  row.equityShare = calcEquityShare(row.adjustedNetProfit, row.investmentRatio)

  // Tab2 公式
  row.incomeDifference = Math.round(
    (parseNum(row.equityShare) - parseNum(row.confirmedIncome)) * 100,
  ) / 100
  row.ociShare = calcEquityShare(row.ociChange, row.investmentRatio)
  row.otherEquityShare = calcEquityShare(row.otherEquityChange, row.investmentRatio)
  row.closingBalance = calcEquityMethodBalance(
    row.openingBalance,
    row.equityShare,
    row.ociShare,
    row.otherEquityShare,
    row.dividendDistributed,
  )
}

// ═══ 字段更新 + 触发重算 ═══════════════════════════════════════════════════

function updateNumField(row: EquityMethodCalcRow, field: keyof EquityMethodCalcRow, value: number): void {
  ;(row as any)[field] = value ?? 0
  recalcRow(row)
  emitSave()
}

// ═══ 重要性水平判断 ═══════════════════════════════════════════════════════

/**
 * |收益差异| > 重要性水平 → true（红色高亮）
 */
function isOverMateriality(incomeDiff: number): boolean {
  const level = parseNum(materialityLevel.value)
  if (level <= 0) return false
  return Math.abs(parseNum(incomeDiff)) > level
}

// ═══ 动态行增删 ═══════════════════════════════════════════════════════════════

function createEmptyRow(investeeName: string, seq: number): EquityMethodCalcRow {
  return {
    id: `emc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    reportedNetProfit: 0,
    internalTransactionAdj: 0,
    fvDepreciationAdj: 0,
    accountingPolicyAdj: 0,
    otherAdj: 0,
    adjustedNetProfit: 0,
    investmentRatio: 0,
    equityShare: 0,
    confirmedIncome: 0,
    incomeDifference: 0,
    ociChange: 0,
    ociShare: 0,
    otherEquityChange: 0,
    otherEquityShare: 0,
    dividendDistributed: 0,
    openingBalance: 0,
    closingBalance: 0,
    auditConclusion: '无差异',
  }
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增被投资单位',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      },
    )
    const name = value.trim()
    // 检查是否已有该分组
    const existing = groups.find(g => g.investeeName === name)
    if (existing) {
      // 组内添加行
      const newRow = createEmptyRow(name, existing.rows.length + 1)
      existing.rows.push(newRow)
    } else {
      // 新建分组
      const newRow = createEmptyRow(name, 1)
      groups.push({ investeeName: name, rows: [newRow] })
      expandedMap[name] = true
      saveCollapseState()
    }
    emitSave()
    ElMessage.success(`已添加「${name}」`)
  } catch {
    // 用户取消
  }
}

function addRowToGroup(groupName: string): void {
  const group = groups.find(g => g.investeeName === groupName)
  if (!group) return
  const newRow = createEmptyRow(groupName, group.rows.length + 1)
  group.rows.push(newRow)
  emitSave()
}

function deleteRow(row: EquityMethodCalcRow): void {
  const group = groups.find(g => g.investeeName === row.investeeName)
  if (!group) return
  const idx = group.rows.findIndex(r => r.id === row.id)
  if (idx >= 0) {
    group.rows.splice(idx, 1)
    group.rows.forEach((r, i) => { r.seq = i + 1 })
    // 如果组为空则删除整个组
    if (group.rows.length === 0) {
      const gIdx = groups.findIndex(g => g.investeeName === row.investeeName)
      if (gIdx >= 0) groups.splice(gIdx, 1)
    }
    emitSave()
  }
}

// ═══ AI辅助 ═══════════════════════════════════════════════════════════════════

async function handleAiConclusion(): Promise<void> {
  ElMessage.info('正在生成AI审计结论...')
  try {
    const { default: http } = await import('@/utils/http')
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/equity-method-conclusion`,
      { rows: groups.flatMap(g => g.rows), materialityLevel: materialityLevel.value },
    )
    const text = res?.data?.conclusion || res?.data?.text || res?.data || ''
    if (text) {
      conclusion.value = String(text)
      emitSave()
      ElMessage.success('AI结论生成完成')
    }
  } catch {
    ElMessage.warning('AI结论生成暂未连接，请手动填写')
  }
}

// ═══ 导入导出 ═══════════════════════════════════════════════════════════════

function handleDropdownCommand(command: string): void {
  ElMessage.info(`${command === 'template' ? '导出模板' : command === 'export' ? '导出数据' : '导入数据'}功能将在后续集成`)
}

// ═══ 保存 ═══════════════════════════════════════════════════════════════════

function emitSave(): void {
  const allRows = groups.flatMap(g => g.rows)
  emit('save', {
    rows: allRows,
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
    groups: groups.map(g => ({ investeeName: g.investeeName, rows: g.rows })),
  })
}

// ═══ 辅助格式化 ═══════════════════════════════════════════════════════════════

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

function conclusionTagType(c: string): '' | 'success' | 'warning' | 'danger' {
  switch (c) {
    case '无差异': return 'success'
    case '差异可接受': return 'warning'
    case '差异需调整': return 'danger'
    default: return ''
  }
}

// ═══ 数据水合 ═══════════════════════════════════════════════════════════════

function hydrateData(): void {
  hydrateFromData(props.htmlData)
}

// ═══ 对外暴露 ═══════════════════════════════════════════════════════════════

function getData(): EquityMethodCalcSavePayload {
  return {
    rows: groups.flatMap(g => g.rows),
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
    groups: groups.map(g => ({ investeeName: g.investeeName, rows: g.rows })),
  }
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  groups.length = 0
  Object.keys(expandedMap).forEach(k => delete expandedMap[k])
  if (data) {
    hydrateFromData(data)
  }
}

/**
 * 通用水合：支持从任意数据源恢复（props.htmlData 或外部传入）
 */
function hydrateFromData(data: Record<string, any> | null): void {
  const calcData = data?.equityMethodCalc ?? data?.equity_method_calc ?? data

  materialityLevel.value = parseNum(calcData?.materialityLevel ?? calcData?.materiality_level ?? 0)
  conclusion.value = calcData?.conclusion ?? ''

  const rawGroups = calcData?.groups ?? []
  if (Array.isArray(rawGroups) && rawGroups.length > 0) {
    for (const g of rawGroups) {
      const name = g.investeeName ?? g.investee_name ?? '未命名'
      const rows: EquityMethodCalcRow[] = (g.rows ?? []).map((r: any, idx: number) => {
        const row = hydrateRow(r, name, idx)
        recalcRow(row)
        return row
      })
      groups.push({ investeeName: name, rows })
      expandedMap[name] = true
    }
  } else {
    const rawRows = calcData?.rows ?? []
    if (Array.isArray(rawRows) && rawRows.length > 0) {
      const groupMap = new Map<string, EquityMethodCalcRow[]>()
      for (const r of rawRows) {
        const name = r.investeeName ?? r.investee_name ?? '未分组'
        if (!groupMap.has(name)) groupMap.set(name, [])
        const row = hydrateRow(r, name, groupMap.get(name)!.length)
        recalcRow(row)
        groupMap.get(name)!.push(row)
      }
      for (const [name, rows] of groupMap.entries()) {
        groups.push({ investeeName: name, rows })
        expandedMap[name] = true
      }
    }
  }
}

function hydrateRow(r: any, name: string, idx: number): EquityMethodCalcRow {
  return {
    id: r.id ?? `emc-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
    seq: r.seq ?? idx + 1,
    investeeName: name,
    reportedNetProfit: parseNum(r.reportedNetProfit ?? r.reported_net_profit),
    internalTransactionAdj: parseNum(r.internalTransactionAdj ?? r.internal_transaction_adj),
    fvDepreciationAdj: parseNum(r.fvDepreciationAdj ?? r.fv_depreciation_adj),
    accountingPolicyAdj: parseNum(r.accountingPolicyAdj ?? r.accounting_policy_adj),
    otherAdj: parseNum(r.otherAdj ?? r.other_adj),
    adjustedNetProfit: 0,
    investmentRatio: parseNum(r.investmentRatio ?? r.investment_ratio),
    equityShare: 0,
    confirmedIncome: parseNum(r.confirmedIncome ?? r.confirmed_income),
    incomeDifference: 0,
    ociChange: parseNum(r.ociChange ?? r.oci_change),
    ociShare: 0,
    otherEquityChange: parseNum(r.otherEquityChange ?? r.other_equity_change),
    otherEquityShare: 0,
    dividendDistributed: parseNum(r.dividendDistributed ?? r.dividend_distributed),
    openingBalance: parseNum(r.openingBalance ?? r.opening_balance),
    closingBalance: 0,
    auditConclusion: r.auditConclusion ?? r.audit_conclusion ?? '无差异',
  }
}

defineExpose({ getData, loadFromHtmlData })

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════

onMounted(() => {
  loadCollapseState()
  hydrateData()
})
</script>

<style scoped>
.g7-tab-equity-method-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* Section 标题栏 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 蓝色渐变引导区 */
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
  padding: 14px 18px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #ecf5ff 0%, #e6f7ff 100%);
  border: 1px solid #b3d8ff;
  border-radius: 6px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-num {
  font-size: 16px;
  font-weight: 700;
  color: #409eff;
  flex-shrink: 0;
}
.step-text {
  font-size: 12px;
  color: #303133;
  line-height: 1.5;
}

/* 方法论上下文区域 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p {
  margin: 2px 0;
}

/* 重要性水平栏 */
.materiality-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.materiality-label {
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}
.materiality-value {
  font-weight: 600;
  color: #409eff;
}
.materiality-hint {
  font-size: 11px;
  color: #909399;
}

/* 区段Tab */
.segment-bar {
  margin-bottom: 12px;
}

/* 虚拟滚动容器（54行阈值） */
.equity-scroll-container {
  max-height: calc(54 * 34px + 120px);
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 4px;
}

/* 分组标题 */
.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  margin-top: 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}
.group-header:first-child {
  margin-top: 0;
}
.group-header:hover {
  background: #d9ecff;
}
.group-name {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.group-count {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.group-actions {
  margin-left: auto;
}
.collapse-icon {
  transition: transform 0.2s;
  font-size: 14px;
}
.collapse-icon.is-collapsed {
  transform: rotate(-90deg);
}

/* 分组内容 */
.group-body {
  margin-bottom: 4px;
}

/* 表格 */
.equity-calc-table {
  margin-top: 4px;
  font-size: var(--wp-font-size, 13px);
}

/* 公式列样式（虚线下划线+cursor:help） */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 收益差异超过重要性水平 → 红色高亮 */
.income-diff-warning {
  color: #f56c6c;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}
.conclusion-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.conclusion-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
}
.empty-state p {
  margin-bottom: 12px;
}

/* 编制提示 */
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-content p {
  margin: 4px 0;
}
</style>
