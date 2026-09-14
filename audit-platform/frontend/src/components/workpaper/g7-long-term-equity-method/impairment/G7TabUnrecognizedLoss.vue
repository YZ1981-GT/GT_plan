<!--
  G7TabUnrecognizedLoss.vue — G7-16 未确认投资损失测试表（40行×17列→2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 长期权益分析(9列): 被投资单位|投资账面|长应收|其他权益|预计负债|合计(公式)|累计亏损|超额亏损(公式)|分配顺序
  - Tab2: 超额亏损分配(8列): 被投资单位|冲减投资|冲减长应收|冲减其他|确认预计负债|未确认损失(公式)|本期变动|审计结论(下拉)

  方法论上下文区域（琥珀色左边线+浅黄背景：CAS2第44条超额亏损抵减顺序）
  超额亏损为0时Tab2全部禁用
  行同步 + 动态行增删
  底部审计结论textarea(AI辅助) + details编制提示折叠

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 8.1
  Requirements: 6.4, 6.7
-->
<template>
  <div class="g7-tab-unrecognized-loss">
    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">超额亏损抵减顺序（CAS2第44条）：</p>
      <ul class="methodology-list">
        <li>① 先冲减<strong>长期股权投资</strong>账面价值</li>
        <li>② 再冲减<strong>长期应收款</strong>等其他实质长期权益</li>
        <li>③ 最后确认<strong>预计负债</strong>（如有额外义务）</li>
        <li>超出①②③的部分为<strong>未确认投资损失</strong>（备查簿登记）</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证被投资单位发生超额亏损时，投资方按抵减顺序确认损失及未确认投资损失的计算是否恰当（CAS2 第44条）。"
      class="objective-alert"
    />

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-16 未确认投资损失测试表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-button size="small" :disabled="isReadonly || syncingCross" :loading="syncingCross" @click="syncFromRelated">
          从关联表带入
        </el-button>
        <el-button size="small" :disabled="isReadonly || !rows.length" @click="applyWaterfallAll">
          按CAS2自动分配
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || !recoveryHintRows.length"
          @click="applyRecoveryAll"
        >
          反序恢复
        </el-button>
        <el-button size="small" :disabled="isReadonly || !rows.length" @click="snapshotAsOpening">
          固化期初
        </el-button>
        <el-button size="small" :disabled="isReadonly || syncingToG714 || !rows.length" :loading="syncingToG714" @click="pushToG714">
          同步至G7-14
        </el-button>
        <el-dropdown trigger="click" size="small" :disabled="importExport.importing.value" @command="handleDropdownCommand">
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-16-unrecognized-loss')">💬复核</el-button>
      </div>
    </div>
    <input
      ref="fileInput"
      type="file"
      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      style="display:none"
      @change="onFileSelected"
    />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-16" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 2区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 超额亏损为0时Tab2禁用提示 -->
    <el-alert
      v-if="activeTab === 'tab2' && allExcessLossZero"
      type="info"
      :closable="false"
      show-icon
      class="tab2-disabled-alert"
    >
      所有被投资单位超额亏损均为0，无需分配超额亏损。Tab2数据已禁用。
    </el-alert>

    <el-alert
      v-if="recoveryHintRows.length"
      type="warning"
      :closable="false"
      show-icon
      class="tab2-disabled-alert"
      title="利润恢复提示"
    >
      以下单位本期变动为负，可点「反序恢复」按 预计负债→其他权益→长应收→投资 冲回已冲减：
      {{ recoveryHintRows.map(r => r.investeeName).join('、') }}
    </el-alert>

    <el-alert
      v-if="validationIssues.length"
      :type="validationIssues.some(i => i.level === 'error') ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="tab2-disabled-alert"
    >
      <div v-for="(iss, idx) in validationIssues.slice(0, 6)" :key="idx">
        【{{ iss.investeeName }}】{{ iss.message }}
      </div>
      <div v-if="validationIssues.length > 6">…另有 {{ validationIssues.length - 6 }} 条</div>
    </el-alert>

    <!-- 表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      class="loss-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <el-table-column label="索引" width="88" align="center" fixed>
        <template #default="{ row }">
          <span class="chip-wrap">
            <GtIndexChip :value="`wp:G7-16#${row.seq}`" :context-project-id="projectId" />
          </span>
        </template>
      </el-table-column>

      <!-- 被投资单位列（始终显示作为锚定列） -->
      <el-table-column label="被投资单位" width="150" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 长期权益分析(9列，含序号+被投资单位共9列显示) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="投资账面" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.investmentBookValue" size="small" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'investmentBookValue', v)" />
            <span v-else>{{ fmtNum(row.investmentBookValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="长期应收款" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.longTermReceivable" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'longTermReceivable', v)" />
            <span v-else>{{ fmtNum(row.longTermReceivable) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="其他实质长期权益" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.otherLongTermEquity" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'otherLongTermEquity', v)" />
            <span v-else>{{ fmtNum(row.otherLongTermEquity) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="预计负债" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.estimatedLiability" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'estimatedLiability', v)" />
            <span v-else>{{ fmtNum(row.estimatedLiability) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合计长期权益" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="合计 = 投资账面 + 长应收 + 其他权益 + 预计负债" placement="top">
              <span class="formula-cell">{{ fmtNum(row.totalLongTermEquity) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="累计亏损" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.cumulativeLoss" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'cumulativeLoss', v)" />
            <span v-else>{{ fmtNum(row.cumulativeLoss) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="超额亏损" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="超额亏损 = MAX(0, 累计亏损 - 合计长期权益)" placement="top">
              <span class="formula-cell" :class="{ 'excess-highlight': row.excessLoss > 0 }">
                {{ fmtNum(row.excessLoss) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="分配顺序说明" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.allocationOrder" size="small"
              @change="(v: string) => updateField(row.id, 'allocationOrder', v)" />
            <span v-else>{{ row.allocationOrder }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 超额亏损分配(8列，含被投资单位共8列) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="冲减投资" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceInvestment" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateReduceField(row.id, 'reduceInvestment', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceInvestment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="冲减长应收" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceLongTermReceivable" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateReduceField(row.id, 'reduceLongTermReceivable', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceLongTermReceivable) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="冲减其他权益" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceOtherEquity" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateReduceField(row.id, 'reduceOtherEquity', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceOtherEquity) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="确认预计负债" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.recognizeEstimatedLiability" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateReduceField(row.id, 'recognizeEstimatedLiability', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.recognizeEstimatedLiability) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未确认损失" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="未确认损失 = MAX(0, 超额亏损 − 各项冲减)" placement="top">
              <span class="formula-cell" :class="{ 'text-disabled': isTab2Disabled(row) }">
                {{ fmtNum(row.unrecognizedLoss) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="上期累计未确认" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && !isTab2Disabled(row)"
              :model-value="row.priorCumulative"
              size="small"
              :controls="false"
              :precision="2"
              class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'priorCumulative', v)"
            />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.priorCumulative) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期变动" min-width="150" align="right">
          <template #default="{ row }">
            <div v-if="!isReadonly && !isTab2Disabled(row)" class="current-change-cell">
              <el-input-number
                :model-value="row.currentChange"
                size="small"
                :controls="false"
                :precision="2"
                class="compact-num"
                @change="(v: number) => updateCurrentChangeManual(row.id, v)"
              />
              <el-button
                v-if="row.currentChangeManual"
                link
                type="primary"
                size="small"
                @click="clearCurrentChangeManual(row.id)"
              >公式</el-button>
            </div>
            <el-tooltip v-else content="本期变动 = 未确认损失 − 上期累计（可手工覆盖）" placement="top">
              <span class="formula-cell" :class="{ 'text-disabled': isTab2Disabled(row) }">
                {{ fmtNum(row.currentChange) }}{{ row.currentChangeManual ? '·手' : '' }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.auditConclusion" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'auditConclusion', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」?`" @confirm="removeRow(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部：审计结论 el-card + AI辅助按钮 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对未确认投资损失测试结果的综合评价（超额亏损分配是否合理）..."
        @change="persistRows"
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>超额亏损 = MAX(0, 累计亏损 - 合计长期权益)，即亏损超过可承受范围的部分</li>
        <li>合计长期权益 = 投资账面 + 长期应收款 + 其他实质长期权益 + 预计负债</li>
        <li>抵减顺序：先冲投资账面→再冲长应收→最后确认预计负债</li>
        <li>超过上述各项可抵减部分 = 未确认投资损失（≥0，账外备查簿登记）</li>
        <li>本期变动 = 期末未确认损失 − 上期累计未确认（可手工覆盖；点「公式」恢复）</li>
        <li>被投资方实现净利润时，按相反顺序恢复（先恢复预计负债→恢复长应收→恢复投资）</li>
        <li>超额亏损为0时，无需进行Tab2分配（系统自动禁用Tab2输入）</li>
        <li>「从关联表带入」：G7-4 名册、G7-14 账面、G7-5 累计亏损（负净资产/未分配利润代理）</li>
        <li>「按CAS2自动分配」：超额亏损按 投资→长应收→其他权益 瀑布冲减；预计负债需手工判断</li>
        <li>「反序恢复」：本期变动为负时，按 预计负债→其他权益→长应收→投资 冲回已冲减</li>
        <li>「固化期初」：将当前未确认损失写入 G7-16-opening-rows，供带入上期累计</li>
        <li>「同步至G7-14」：本期变动累加写入 otherAdj（保留手工/其他来源分量）</li>
        <li>长期应收款：优先 G5-2 关联方净额（剔一年内），其次 TB 1531 客户辅助；亦可从 G7-14 同名字段带入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { extractG7AiText } from '../../composables/g7AiText'
/**
 * G7TabUnrecognizedLoss — G7-16 未确认投资损失测试表
 *
 * 持久化：G7-16-rows 扁平数组（IE/consol/披露真源）+ G7-16-conclusion
 * 兼容旧存：{ rows, conclusion } 对象
 */
import { ref, reactive, inject, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { UnrecognizedLossRow } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import {
  G7_4_ROWS_KEY,
  G7_5_ROWS_KEY,
  applyUnrecognizedLossToG714Payload,
  buildG714DualWriteItems,
  flattenG714Rows,
  loadEquityInvestees,
  makeG714ConclusionGetter,
  parseChecklistJson,
  resolveG714PayloadFromChecklist,
} from '../../composables/g7EquityMethodCrossSheet'
import {
  applyProfitRecoveryReverseOrder,
  extractCumulativeLossFromG75,
  extractLongTermReceivableFromRelated,
  extractPriorCumulativeMap,
  parseUnrecognizedLossRowsPayload,
  recalcUnrecognizedLossRow,
  validateUnrecognizedLossRows,
} from '../../composables/g7UnrecognizedLossModel'
import {
  fetchG52NetInvestmentByDebtor,
  fetchTb1531AuxByCustomer,
  normalizeDebtorName,
} from '../../composables/g5CrossHelpers'
import { emitG7SourceRowsSaved } from '../../composables/g7DisclosureCrossSheet'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

type TabKey = 'tab1' | 'tab2'
const activeTab = ref<TabKey>('tab1')
const segmentOptions = [
  { label: '长期权益分析(9)', value: 'tab1' },
  { label: '超额亏损分配(8)', value: 'tab2' },
]

const selectedRowIndex = ref<number>(-1)
function onCurrentChange(row: UnrecognizedLossRow | null) {
  if (row) {
    const idx = rows.findIndex(r => r.id === row.id)
    selectedRowIndex.value = idx
  }
}

const rows = reactive<UnrecognizedLossRow[]>([])
const conclusion = ref('')
const syncingCross = ref(false)
const syncingToG714 = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const validationIssues = computed(() => validateUnrecognizedLossRows(rows))
const recoveryHintRows = computed(() => rows.filter(r => parseNum(r.currentChange) < -0.005))
const hasBlockingErrors = computed(() => validationIssues.value.some(i => i.level === 'error'))

const auditFormData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const importExport = useG7EquityMethodImportExport({
  wpId: computed(() => props.wpId),
})

const AUDIT_NOTE_KEY = 'G7-16-audit-note'
const ROWS_KEY = 'G7-16-rows'
const CONCLUSION_KEY = 'G7-16-conclusion'
/** 期初未确认（上期期末）快照，用于带入 priorCumulative */
const OPENING_KEY = 'G7-16-opening-rows'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function persistRows(opts?: { force?: boolean }): void {
  if (isReadonly.value) return
  if (!opts?.force && hasBlockingErrors.value) {
    ElMessage.warning('存在分配校验错误，已暂存但请先修正后再依赖下游勾稽')
  }
  const flatRows = JSON.stringify([...rows])
  const pagePayload = JSON.stringify({ rows: [...rows], conclusion: conclusion.value })
  // 扁平数组 → IE/consol；对象 payload 双写 remark 兼容旧消费者
  if (typeof (auditFormData as any).debouncedSaveBatch === 'function') {
    auditFormData.debouncedSaveBatch([
      { itemId: ROWS_KEY, data: { conclusion: flatRows, remark: pagePayload } },
      { itemId: CONCLUSION_KEY, data: { conclusion: conclusion.value, remark: null } },
    ])
  } else {
    auditFormData.debouncedSave(ROWS_KEY, { conclusion: flatRows, remark: pagePayload })
    auditFormData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value, remark: null })
  }
  try {
    emitG7SourceRowsSaved({
      projectId: props.projectId,
      wpId: props.wpId,
      itemIds: [ROWS_KEY],
    })
  } catch { /* ignore */ }
}

function parseSaved(raw: unknown): unknown {
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return null }
}

function hydrateRows(raw: unknown): boolean {
  if (raw == null) return false
  const list = parseUnrecognizedLossRowsPayload(raw)
  if (!list.length) return false
  rows.length = 0
  for (let i = 0; i < list.length; i++) {
    const rawRow = list[i]
    const row: UnrecognizedLossRow = {
      ...createEmptyRow(i + 1, rawRow.investeeName || ''),
      ...rawRow,
      seq: i + 1,
      id: rawRow.id || crypto.randomUUID(),
      priorCumulative: parseNum(rawRow.priorCumulative),
      allocationManual: !!rawRow.allocationManual,
      currentChangeManual: !!rawRow.currentChangeManual,
    }
    rows.push(row)
    // 加载时保留已存冲减，不强制重跑瀑布（用户可点「按CAS2自动分配」）
    recalcUnrecognizedLossRow(row, { applyWaterfall: false })
  }
  if (typeof (raw as any)?.conclusion === 'string') conclusion.value = (raw as any).conclusion
  return true
}

function loadRowsFromChecklist(): boolean {
  const saved = auditFormData.data.value.get(ROWS_KEY)
  const fromConclusion = parseSaved(saved?.conclusion)
  const fromRemark = parseSaved(saved?.remark)
  if (hydrateRows(fromConclusion) || hydrateRows(fromRemark)) {
    const c = auditFormData.data.value.get(CONCLUSION_KEY)
    if (c?.conclusion) conclusion.value = String(c.conclusion)
    return true
  }
  return false
}

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(AUDIT_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark

  const snapshot = props.htmlData?.responses_snapshot?.[ROWS_KEY]
  if (
    !loadRowsFromChecklist()
    && !hydrateRows(parseSaved(snapshot?.conclusion))
    && !hydrateRows(parseSaved(snapshot?.remark))
    && !hydrateRows(props.htmlData?.unrecognizedLoss)
    && !hydrateRows((props.htmlData as any)?.rows)
  ) {
    // 空表起步
  }

  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.conclusion && !conclusion.value) conclusion.value = String(c.conclusion)
})

const allExcessLossZero = computed(() => rows.length > 0 && rows.every(r => r.excessLoss === 0))

function isTab2Disabled(row: UnrecognizedLossRow): boolean {
  return row.excessLoss === 0
}

function recalcRow(row: UnrecognizedLossRow): void {
  recalcUnrecognizedLossRow(row)
}

function createEmptyRow(seq: number, investeeName: string): UnrecognizedLossRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    investmentBookValue: 0,
    longTermReceivable: 0,
    otherLongTermEquity: 0,
    estimatedLiability: 0,
    totalLongTermEquity: 0,
    cumulativeLoss: 0,
    excessLoss: 0,
    allocationOrder: '①冲投资→②冲长应收→③确认预计负债',
    reduceInvestment: 0,
    reduceLongTermReceivable: 0,
    reduceOtherEquity: 0,
    recognizeEstimatedLiability: 0,
    unrecognizedLoss: 0,
    priorCumulative: 0,
    currentChange: 0,
    allocationManual: false,
    currentChangeManual: false,
    auditConclusion: '合理',
  }
}

function updateField(id: string, field: keyof UnrecognizedLossRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function updateFieldWithRecalc(id: string, field: keyof UnrecognizedLossRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value ?? 0
    recalcRow(row)
    persistRows()
  }
}

function updateReduceField(
  id: string,
  field: 'reduceInvestment' | 'reduceLongTermReceivable' | 'reduceOtherEquity' | 'recognizeEstimatedLiability',
  value: number,
) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  row.allocationManual = true
  ;(row as any)[field] = value ?? 0
  recalcUnrecognizedLossRow(row, { applyWaterfall: false })
  persistRows()
}

function updateCurrentChangeManual(id: string, value: number) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  row.currentChangeManual = true
  row.currentChange = value ?? 0
  persistRows()
}

function clearCurrentChangeManual(id: string) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  row.currentChangeManual = false
  recalcRow(row)
  persistRows()
}

function applyWaterfallAll() {
  if (isReadonly.value) return
  for (const row of rows) {
    row.allocationManual = false
    recalcUnrecognizedLossRow(row, { applyWaterfall: true })
  }
  persistRows()
  ElMessage.success('已按 CAS2 第44条自动分配超额亏损（预计负债仍需手工确认）')
}

function applyRecoveryAll() {
  if (isReadonly.value) return
  const targets = rows.filter(r => parseNum(r.currentChange) < -0.005)
  if (!targets.length) {
    ElMessage.info('无需恢复的行')
    return
  }
  let total = 0
  for (const row of targets) {
    const { recovered } = applyProfitRecoveryReverseOrder(row)
    total += recovered
  }
  persistRows()
  ElMessage.success(`已对 ${targets.length} 家按反序恢复，合计冲回 ${total.toFixed(2)}`)
}

function snapshotAsOpening() {
  if (isReadonly.value || !rows.length) return
  const opening = rows.map(r => ({
    investeeName: r.investeeName,
    investeeId: r.investeeId,
    unrecognizedLoss: parseNum(r.unrecognizedLoss),
    priorCumulative: parseNum(r.unrecognizedLoss),
  }))
  auditFormData.debouncedSave(OPENING_KEY, {
    conclusion: JSON.stringify(opening),
    remark: null,
  })
  ElMessage.success('已将当前未确认损失固化为期初快照（供下期/本期 prior 带入）')
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '被投资单位名称不能为空'
        const exists = rows.some(r => r.investeeName === val.trim())
        if (exists) return `「${val.trim()}」已存在，请勿重复添加`
        return true
      },
    })
    if (value?.trim()) {
      rows.push(createEmptyRow(rows.length + 1, value.trim()))
      persistRows()
      ElMessage.success(`已添加「${value.trim()}」`)
    }
  } catch {
    // cancelled
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }
}

function generateLocalConclusion(): void {
  const total = rows.length
  const withExcess = rows.filter(r => r.excessLoss > 0)
  const totalUnrecognized = rows.reduce((s, r) => s + parseNum(r.unrecognizedLoss), 0)
  const totalChange = rows.reduce((s, r) => s + parseNum(r.currentChange), 0)
  conclusion.value =
    `经检查，共测试 ${total} 家被投资单位，其中 ${withExcess.length} 家存在超额亏损。` +
    `未确认投资损失期末合计 ${totalUnrecognized.toFixed(2)} 元，本期变动合计 ${totalChange.toFixed(2)} 元。` +
    (withExcess.length
      ? '超额亏损已按 CAS2 第44条顺序分配（冲减投资→冲减长应收→确认预计负债），超出部分已登记备查。'
      : '本期无超额亏损需分配。') +
    ' 未确认投资损失计算及抵减顺序恰当。'
  persistRows()
  ElMessage.success('已生成本地结论草稿')
}

async function handleAiConclusion() {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/unrecognized-loss-conclusion`,
      {
        existingContent: conclusion.value,
        relatedContext: {
          sheet: 'G7-16',
          rowCount: rows.length,
          excessCount: rows.filter(r => r.excessLoss > 0).length,
          recoveryCount: rows.filter(r => parseNum(r.currentChange) < -0.005).length,
          totalUnrecognized: rows.reduce((s, r) => s + parseNum(r.unrecognizedLoss), 0),
          totalCurrentChange: rows.reduce((s, r) => s + parseNum(r.currentChange), 0),
          validationErrors: validationIssues.value.filter(i => i.level === 'error').slice(0, 8),
          validationWarnings: validationIssues.value.filter(i => i.level === 'warning').slice(0, 8),
          rows: rows.slice(0, 20).map(r => ({
            investeeName: r.investeeName,
            excessLoss: r.excessLoss,
            unrecognizedLoss: r.unrecognizedLoss,
            priorCumulative: r.priorCumulative,
            currentChange: r.currentChange,
            allocationManual: !!r.allocationManual,
            currentChangeManual: !!r.currentChangeManual,
            reduceInvestment: r.reduceInvestment,
            reduceLongTermReceivable: r.reduceLongTermReceivable,
            reduceOtherEquity: r.reduceOtherEquity,
            recognizeEstimatedLiability: r.recognizeEstimatedLiability,
          })),
        },
      },
    )
    const text = extractG7AiText(res?.data)
    if (text) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${text}` : text
      persistRows()
      ElMessage.success('AI结论已生成')
    } else {
      generateLocalConclusion()
    }
  } catch {
    generateLocalConclusion()
  }
}

async function handleDropdownCommand(command: string) {
  if (command === 'template') await importExport.exportTemplate('G7-16')
  else if (command === 'export') await importExport.exportData('G7-16')
  else if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-16', file)
  if (!result) return
  await auditFormData.load()
  if (loadRowsFromChecklist()) {
    ElMessage.success(`导入完成，已刷新 ${rows.length} 行`)
  } else {
    ElMessage.warning('导入完成，但未解析到行数据')
  }
}

async function syncFromRelated(): Promise<void> {
  if (isReadonly.value || syncingCross.value) return
  syncingCross.value = true
  try {
    await auditFormData.loadResponses()
    const g74 = loadEquityInvestees(
      auditFormData.data.value.get(G7_4_ROWS_KEY)?.conclusion
      ?? props.htmlData?.responses_snapshot?.[G7_4_ROWS_KEY]?.conclusion,
    )
    const g714Payload = resolveG714PayloadFromChecklist(
      makeG714ConclusionGetter(auditFormData.data.value, props.htmlData?.responses_snapshot),
    )
    const g714Rows = flattenG714Rows(g714Payload)

    const g75Raw = parseChecklistJson(
      auditFormData.data.value.get(G7_5_ROWS_KEY)?.conclusion
      ?? auditFormData.data.value.get(G7_5_ROWS_KEY)?.remark
      ?? props.htmlData?.responses_snapshot?.[G7_5_ROWS_KEY]?.conclusion,
    )
    const lossMap = extractCumulativeLossFromG75(g75Raw)

    const openingRaw = parseChecklistJson(
      auditFormData.data.value.get(OPENING_KEY)?.conclusion
      ?? props.htmlData?.responses_snapshot?.[OPENING_KEY]?.conclusion
      ?? props.htmlData?.priorUnrecognizedLoss,
    )
    const priorMap = extractPriorCumulativeMap(openingRaw)

    // G5-2 实质净投资长期应收（关联方优先）；失败则 TB 1531 辅助核算降级
    let g52LtMap = new Map<string, number>()
    try {
      g52LtMap = await fetchG52NetInvestmentByDebtor(props.projectId, { relatedPartyOnly: true })
      if (g52LtMap.size === 0) {
        g52LtMap = await fetchG52NetInvestmentByDebtor(props.projectId, { relatedPartyOnly: false })
      }
      if (g52LtMap.size === 0) {
        g52LtMap = await fetchTb1531AuxByCustomer(props.projectId)
      }
    } catch { /* ignore */ }

    let added = 0
    let filled = 0
    let lossFilled = 0
    let priorFilled = 0
    let ltRecFilled = 0
    const names = g74.length
      ? g74.map(x => ({ name: x.name, id: x.investeeId }))
      : g714Rows
        .map((r: any) => ({
          name: String(r.investeeName ?? '').trim(),
          id: String(r.investeeId ?? '').trim() || undefined,
        }))
        .filter(x => x.name)

    if (!names.length && !rows.length) {
      ElMessage.warning('未找到 G7-4 / G7-14 被投资单位，请先维护关联表')
      return
    }

    const targets = names.length
      ? names
      : rows.map(r => ({ name: r.investeeName, id: r.investeeId }))

    for (const inv of targets) {
      let row = rows.find(r =>
        (inv.id && r.investeeId && r.investeeId === inv.id)
        || r.investeeName === inv.name,
      )
      if (!row) {
        row = createEmptyRow(rows.length + 1, inv.name)
        if (inv.id) row.investeeId = inv.id
        rows.push(row)
        added++
      } else if (inv.id && !row.investeeId) {
        row.investeeId = inv.id
      }
      const match714 = g714Rows.find((r: any) => {
        const rid = String(r.investeeId ?? '').trim()
        if (inv.id && rid) return rid === inv.id
        return String(r.investeeName ?? '').trim() === inv.name
      })
      if (match714) {
        if (!parseNum(row.investmentBookValue)) {
          const book = parseNum(
            match714.closingBalance
            ?? match714.lteiBookBalance
            ?? match714.lteBookBalance
            ?? match714.bookValue
            ?? match714.costClosing,
          )
          if (book) {
            row.investmentBookValue = book
            filled++
          }
        }
        if (!parseNum(row.otherLongTermEquity)) {
          const other = parseNum(match714.ociBalClosing) + parseNum(match714.otherEqBalClosing)
          if (other) {
            row.otherLongTermEquity = Math.round(other * 100) / 100
            filled++
          }
        }
        if (!parseNum(row.longTermReceivable)) {
          const lt = extractLongTermReceivableFromRelated(match714)
          if (lt) {
            row.longTermReceivable = lt
            ltRecFilled++
          }
        }
      }
      if (!parseNum(row.longTermReceivable)) {
        const fromG5 = g52LtMap.get(normalizeDebtorName(inv.name))
        if (fromG5 && fromG5 > 0) {
          row.longTermReceivable = fromG5
          ltRecFilled++
        }
      }
      const cumLoss = lossMap.get(inv.name)
      if (cumLoss != null && cumLoss > 0 && !parseNum(row.cumulativeLoss)) {
        row.cumulativeLoss = cumLoss
        lossFilled++
      }
      const prior = priorMap.get(inv.name)
      if (prior != null && prior > 0 && !parseNum(row.priorCumulative)) {
        row.priorCumulative = prior
        priorFilled++
      }
      recalcRow(row)
    }
    rows.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
    ElMessage.success(
      `已带入：新增 ${added} 家，账面 ${filled}，长应收 ${ltRecFilled}，累计亏损 ${lossFilled}，上期未确认 ${priorFilled}`,
    )
  } catch {
    ElMessage.error('关联表带入失败')
  } finally {
    syncingCross.value = false
  }
}

async function pushToG714(): Promise<void> {
  if (isReadonly.value || syncingToG714.value || !rows.length) return
  if (hasBlockingErrors.value) {
    ElMessage.error('存在分配校验错误，请先修正后再同步至 G7-14')
    return
  }
  syncingToG714.value = true
  try {
    await auditFormData.loadResponses()
    const g714Raw = resolveG714PayloadFromChecklist(
      makeG714ConclusionGetter(auditFormData.data.value, props.htmlData?.responses_snapshot),
    )
    const result = applyUnrecognizedLossToG714Payload(g714Raw, [...rows])
    if (!result.ok || !result.payload) {
      ElMessage.warning(result.message)
      return
    }
    await ElMessageBox.confirm(
      `${result.message}。将覆盖 G7-14 对应行的「其他调整(otherAdj)」，是否继续？`,
      '同步至 G7-14',
      { type: 'warning', confirmButtonText: '确认覆盖', cancelButtonText: '取消' },
    )
    const items = buildG714DualWriteItems(result.payload)
    if (typeof (auditFormData as any).debouncedSaveBatch === 'function') {
      auditFormData.debouncedSaveBatch(items)
    } else {
      for (const it of items) {
        auditFormData.debouncedSave(it.itemId, it.data)
      }
    }
    ElMessage.success(result.message)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('同步至 G7-14 失败')
  } finally {
    syncingToG714.value = false
  }
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  hydrateRows(data.unrecognizedLoss || data)
}

function getData(): { rows: UnrecognizedLossRow[]; conclusion: string } {
  return { rows: [...rows], conclusion: conclusion.value }
}

defineExpose({ getData, loadFromHtmlData, persistRows })
</script>

<style scoped>
.g7-tab-unrecognized-loss { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-title { margin: 0 0 6px; font-weight: 600; color: #92400e; }
.methodology-list { margin: 0; padding-left: 18px; color: #78350f; }
.methodology-list li { margin-bottom: 2px; }

/* 顶部工具栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 区段Tab */
.segment-bar { margin-bottom: 12px; }

/* Tab2全局禁用提示 */
.tab2-disabled-alert { margin-bottom: 12px; }

/* 表格 */
.loss-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.current-change-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.current-change-cell .compact-num { flex: 1; }

/* 超额亏损高亮 */
.excess-highlight { color: #f56c6c; font-weight: 600; }

/* 禁用状态（超额亏损为0时） */
.text-disabled { color: #c0c4cc; }

/* 审计结论卡片 */
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }

/* 编制提示 */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
