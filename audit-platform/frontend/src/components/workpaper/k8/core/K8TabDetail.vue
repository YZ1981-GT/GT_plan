<template>
  <div class="k8-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与完整性：</b>各明细项销售费用真实发生且记录完整，合计与 K8-1 审定数一致；</li>
        <li><b>准确性与分类：</b>各费用明细金额准确、按费用性质恰当分类。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + 导入导出 + AI + 复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K8-2 销售费用明细表</h3>
        <GtIndexChip value="K8-1" :context-project-id="props.projectId" />
      </div>
      <div class="header-actions">
        <el-dropdown size="small" trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI波动分析
          </el-button>
        </el-tooltip>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :loading="pullingI1"
          :disabled="isReadonly"
          data-testid="k8-pull-i1-amort"
          @click="handlePullI1Amort"
        >
          从 I1-9 取摊销
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>销售费用明细表从<strong>tb_ledger明细科目</strong>取发生额（科目6601）。对齐源模板拆<strong>3区段</strong>：<strong>月度构成</strong>（1~12月+本期未审合计）/<strong>审定与占比</strong>（账项调整+重分类调整→本期审定+各项目占比+勾稽索引）/<strong>同比分析</strong>（上期审定+占比+占比变动+波动分析）。本期审定合计联动审定表K8-1。同比变动率&gt;±30%红色高亮需说明波动原因。</p>
    </div>

    <!-- ═══ 3区段Tab切换（el-segmented） ═══ -->
    <div class="tab-bar">
      <el-segmented v-model="activeTab" :options="tabOptions" size="small" />
      <div class="tab-right">
        <el-button size="small" type="warning" plain :loading="pullingLedger" :disabled="isReadonly" @click="handlePullLedgerMonthly">
          从序时账取数
        </el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增明细
        </el-button>
      </div>
    </div>

    <!-- ═══ 明细表主表 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      max-height="660"
      :row-class-name="detailRowClass"
    >
      <el-table-column type="index" label="序号" width="50" align="center" fixed />

      <!-- ═══ 月度构成区段（对齐源模板 1~12 月 + 本期未审合计）═══ -->
      <template v-if="activeTab === 'month'">
        <el-table-column prop="accountName" label="明细科目" min-width="130" fixed>
          <template #default="{ row }"><span class="account-name">{{ row.accountName }}</span></template>
        </el-table-column>
        <el-table-column
          v-for="(m, mi) in monthLabels"
          :key="mi"
          :label="m"
          width="82"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable"
              :model-value="row.months[mi] ?? 0"
              :disabled="isReadonly"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 72px"
              @change="(v: number) => handleCellChange(row.rowKey, `month-${mi}`, v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmtNum(row.months[mi] ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期未审合计" width="120" align="right" fixed="right">
          <template #default="{ row }">
            <el-tooltip content="公式：SUM(1~12月)" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.unadjTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.isEditable" type="danger" link size="small" :disabled="isReadonly" @click="handleRemoveRow(row.rowKey)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 审定与占比区段（对齐源模板 账项调整/重分类/审定/占比/勾稽索引）═══ -->
      <template v-if="activeTab === 'audit'">
        <el-table-column prop="accountCode" label="科目编码" width="96" align="center">
          <template #default="{ row }">
            <el-input v-if="row.isEditable" :model-value="row.accountCode" :disabled="isReadonly" size="small" placeholder="编码" style="width: 78px" @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'accountCode', (e.target as HTMLInputElement)?.value ?? '')" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="明细科目" min-width="130" fixed />
        <el-table-column label="本期未审合计" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：SUM(1~12月)" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.unadjTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable" :model-value="row.aje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width: 80px" @change="(v: number) => handleCellChange(row.rowKey, 'aje', v ?? 0)" />
            <span v-else class="formula-cell">{{ fmtNum(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable" :model-value="row.rje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width: 85px" @change="(v: number) => handleCellChange(row.rowKey, 'rje', v ?? 0)" />
            <span v-else class="formula-cell">{{ fmtNum(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整联动" width="150" align="center">
          <template #default="{ row }">
            <template v-if="adjCountFor(row.accountCode) > 0">
              <el-tag size="small" type="warning" effect="plain" style="cursor: pointer" title="点击跳转到集中调整分录" @click="jumpFirstAdjustment(row.accountCode)">受 {{ adjCountFor(row.accountCode) }} 笔调整影响</el-tag>
              <el-button v-if="row.isEditable" link size="small" type="primary" :disabled="isReadonly" style="margin-left: 4px" @click="openBringIn(row)">带入</el-button>
            </template>
            <span v-else style="color: var(--el-text-color-placeholder)">—</span>
          </template>
        </el-table-column>
        <el-table-column label="本期审定金额" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：本期未审+账项调整+重分类调整" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="各项目占比" width="100" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：本期审定/审定合计" placement="top">
              <span class="formula-cell formula-underline">{{ fmtRate(row.ratioToTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="勾稽索引" min-width="120">
          <template #default="{ row }">
            <el-input v-if="row.isEditable" :model-value="row.crossRefIndex" :disabled="isReadonly" size="small" placeholder="如 L1-XXX / J1-XXX" @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'crossRefIndex', (e.target as HTMLInputElement)?.value ?? '')" />
            <span v-else>{{ row.crossRefIndex || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 同比分析区段（对齐源模板 上期审定/占比/占比变动/波动分析）═══ -->
      <template v-if="activeTab === 'analysis'">
        <el-table-column prop="accountName" label="明细科目" min-width="140" fixed />
        <el-table-column label="本期审定" width="115" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtNum(row.audited) }}</span></template>
        </el-table-column>
        <el-table-column label="上期审定" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable" :model-value="row.priorAmount" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width: 100px" @change="(v: number) => handleCellChange(row.rowKey, 'priorAmount', v ?? 0)" />
            <span v-else class="formula-cell">{{ fmtNum(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动率" width="105" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：(本期−上期)/|上期|" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'abnormal-highlight': isAbnormalRate(row.yoyChangeRate) }">{{ fmtRate(row.yoyChangeRate) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="本期占比" width="90" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtRate(row.ratioToTotal) }}</span></template>
        </el-table-column>
        <el-table-column label="上期占比" width="90" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtRate(row.priorRatioToTotal) }}</span></template>
        </el-table-column>
        <el-table-column label="占比变动" width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：本期占比−上期占比" placement="top">
              <span class="formula-cell formula-underline">{{ fmtRate(row.ratioChange) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="占收入比" width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：审定数/营业收入" placement="top">
              <span class="formula-cell formula-underline">{{ fmtRate(row.ratioToRevenue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="波动分析" min-width="180">
          <template #default="{ row }">
            <el-input v-if="row.isEditable" :model-value="row.fluctuationNote" :disabled="isReadonly" size="small" placeholder="变动率>30%需说明波动原因" @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'fluctuationNote', (e.target as HTMLInputElement)?.value ?? '')" />
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- ═══ 底部统计栏 ═══ -->
    <div class="subtotal-bar">
      <span class="total-label">合  计</span>
      <span class="total-item">未审合计: <strong>{{ fmtNum(subtotal.unadjTotal) }}</strong></span>
      <span class="total-item">AJE: <strong>{{ fmtNum(subtotal.aje) }}</strong></span>
      <span class="total-item">RJE: <strong>{{ fmtNum(subtotal.rje) }}</strong></span>
      <span class="total-item">审定合计: <strong>{{ fmtNum(subtotal.audited) }}</strong></span>
      <span class="total-item">上期合计: <strong>{{ fmtNum(subtotal.priorAmount) }}</strong></span>
      <span class="total-item">共 <strong>{{ tableData.length }}</strong> 行</span>
    </div>

    <!-- ═══ 费用测算（重新测算复核，源模板 K8-2 第三张表）═══ -->
    <el-card shadow="never" class="recalc-card">
      <template #header>
        <div class="recalc-head">
          <span class="recalc-title">费用测算（重新测算复核）</span>
          <div class="recalc-actions">
            <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleAddRecalc">
              <el-icon><Plus /></el-icon> 新增测算项
            </el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly || recalcAdjustCount === 0" @click="handlePushRecalcToK83">
              推送需调整差异至 K8-3（{{ recalcAdjustCount }}）
            </el-button>
          </div>
        </div>
      </template>
      <div class="recalc-hint">
        对折旧费/职工薪酬/福利费等按 <strong>计提依据(基数)×计提比例</strong> 重新测算应计提金额，与账面计提比较；差异需查明原因并判断是否调整。<strong>应计提=基数×比例；差异=应计提−账面</strong>。
      </div>
      <el-table :data="accrualRecalcRows" border size="small" style="width:100%" max-height="360" :row-class-name="recalcRowClass">
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column label="项目" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectName" size="small" placeholder="如 折旧费/职工福利费" @change="(v: string) => updateRecalc(row.id, 'projectName', v)" />
            <span v-else>{{ row.projectName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据(基数)" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.basisAmount" size="small" :controls="false" :precision="2" style="width:118px" @change="(v: number | undefined) => updateRecalc(row.id, 'basisAmount', v ?? 0)" />
            <span v-else class="formula-cell">{{ fmtNum(row.basisAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提比例(%)" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ratePct" size="small" :controls="false" :precision="4" style="width:92px" @change="(v: number | undefined) => updateRecalc(row.id, 'ratePct', v ?? 0)" />
            <span v-else>{{ row.ratePct }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提金额" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：计提依据×计提比例" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.shouldAccrue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面计提金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookAccrue" size="small" :controls="false" :precision="2" style="width:110px" @change="(v: number | undefined) => updateRecalc(row.id, 'bookAccrue', v ?? 0)" />
            <span v-else class="formula-cell">{{ fmtNum(row.bookAccrue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：应计提−账面计提" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'abnormal-highlight': Math.abs(row.diff) > 0.01 }">{{ fmtNum(row.diff) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.diffReason" size="small" :placeholder="Math.abs(row.diff) > 0.01 ? '差异需说明原因' : ''" @change="(v: string) => updateRecalc(row.id, 'diffReason', v)" />
            <span v-else>{{ row.diffReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否调整" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.needAdjust" size="small" style="width:70px" @change="(v: string) => updateRecalc(row.id, 'needAdjust', v)">
              <el-option value="否" label="否" />
              <el-option value="是" label="是" />
            </el-select>
            <el-tag v-else :type="row.needAdjust === '是' ? 'danger' : 'info'" size="small">{{ row.needAdjust }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRecalc(row.id)"><el-icon><Delete /></el-icon></el-button>
          </template>
        </el-table-column>
        <template #empty>
          <span style="color:#909399;font-size:12px">暂无测算项，点「新增测算项」添加折旧费/职工福利费等重新测算复核</span>
        </template>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>明细表从<strong>tb_ledger</strong>明细科目取发生额（科目6601，非期末余额）</li>
        <li>3区段Tab：<strong>月度构成</strong>（录入1~12月，本期未审合计自动SUM）/<strong>审定与占比</strong>（账项调整+重分类调整→本期审定金额，各项目占比自动=本项/审定合计，勾稽索引填L1/J1等关联底稿）/<strong>同比分析</strong>（上期审定+占比变动+波动分析）</li>
        <li>本期审定金额=本期未审+账项调整+重分类调整；各项目占比=本期审定/审定合计</li>
        <li>同比变动率=(本期−上期)/|上期|；占比变动=本期占比−上期占比</li>
        <li>本期审定合计应与K8-1审定表合计保持一致（交叉勾稽）</li>
        <li>变动率&gt;±30%需在"波动分析"列填写原因</li>
        <li>「占收入比」分母取自 K8-4 实质性分析录入的营业收入（未录入则显示"—"）</li>
        <li>可点「从 I1-9 取摊销」回填本表「无形资产摊销/折旧及摊销」行</li>
        <li><strong>调整联动</strong>：审定区段明细行标注"受 N 笔调整影响"可跳转集中调整；点「带入」把调整金额（单行/多选合计/全部求和）带入本行 账项调整/重分类调整 列</li>
      </ul>
    </details>

    <!-- 调整分录带入弹窗（adjustment-collaboration-and-propagation Part B） -->
    <AdjustmentBringInDialog
      v-model="bringInVisible"
      :matches="bringInMatches"
      :account-label="bringInRow ? `${bringInRow.accountCode || ''} ${bringInRow.accountName || ''}` : ''"
      @bring-in="onBringIn"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabDetail.vue — K8-2 销售费用明细表
 * 48行×27列→3区段Tab（基础/分析/检查）
 *
 * 区段Tab用el-segmented切换，行同步。动态行新增弹ElMessageBox.prompt。
 * 导入导出：useK8ImportExport。合计行联动审定表K8-1。
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.3
 * Requirements: 3.1-3.4
 */
import { computed, inject, reactive, onMounted, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown, Plus, Delete } from '@element-plus/icons-vue'
import { defineAsyncComponent } from 'vue'
import { useK8Detail, DETAIL_TABS, type K8DetailTabKey } from '../../composables/useK8Detail'
import { useK8ImportExport } from '../../composables/useK8ImportExport'
import { useK8AiGenerate } from '../../composables/useK8AiGenerate'
import { pullI1AmortIntoExpenseDetail } from '../../composables/expenseWpI1AmortPull'
import { pullExpenseLedgerMonthly } from '../../composables/expenseLedgerMonthlyPull'
import { useAdjustmentDetailPropagation } from '../../composables/useAdjustmentDetailPropagation'
import AdjustmentBringInDialog, { type BringInPayload } from '@/components/adjustment/AdjustmentBringInDialog.vue'
import { useAuditContext } from '@/composables/useAuditContext'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog', () => {})

const activeTab = ref<K8DetailTabKey>('month')
const tabOptions = DETAIL_TABS.map(t => ({ label: t.label, value: t.key }))
const monthLabels = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

// 营业收入分母（占收入比）：复用 K8-4 实质性分析录入的营业收入，避免本表「占收入比」列恒为"—"
const revenue = computed<number>(() => {
  const item = props.allResponses.get('K8-4-revenue')
  return Number(item?.remark ?? item?.conclusion ?? 0) || 0
})

const { rows, subtotal, updateCell, addRow, removeRow, applyMonthlyRows, applyI1AmortAmount } = useK8Detail({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  revenue,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  onSave: (itemId: string, value: any) => emit('save', itemId, value),
})

const pullingI1 = ref(false)

// ─── 从序时账按月取数（6601 明细科目×月发生额）─────────────────────────────
const pullingLedger = ref(false)
const detailYear = computed(() => props.year ?? new Date().getFullYear())
async function handlePullLedgerMonthly() {
  if (props.isReadonly) return
  pullingLedger.value = true
  try {
    const res = await pullExpenseLedgerMonthly(props.projectId, '6601', detailYear.value)
    if (!res.ok) { ElMessage.warning(res.message); return }
    await ElMessageBox.confirm(
      `将从序时账聚合 ${res.rows.length} 个明细科目的月度发生额（合计 ${res.total.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}）回填明细表（同名覆盖月度、缺失新增行）。是否继续？`,
      '从序时账取数确认',
      { confirmButtonText: '回填', cancelButtonText: '取消', type: 'warning' },
    )
    const applied = applyMonthlyRows(res.rows)
    if (applied.ok) { ElMessage.success(applied.message); activeTab.value = 'month' }
    else ElMessage.warning(applied.message)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.error(e?.message || '序时账取数失败')
  } finally {
    pullingLedger.value = false
  }
}

async function handlePullI1Amort() {
  if (props.isReadonly) return
  pullingI1.value = true
  try {
    const result = await pullI1AmortIntoExpenseDetail(props.projectId, 'K8')
    if (!result.amount) {
      ElMessage.warning(result.message || 'I1-9 摊销合计为 0')
      return
    }
    const applied = applyI1AmortAmount(result.amount)
    if (applied.ok) ElMessage.success(applied.message)
    else ElMessage.warning(applied.message)
  } catch (e: any) {
    ElMessage.error(e?.message || '拉取 I1-9 失败')
  } finally {
    pullingI1.value = false
  }
}

const { exportTemplate, exportData, importData } = useK8ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  sheetCode: 'K8-2',
})

// ─── Part B：调整分录 → 明细行联动（标注/跳转/带入） ─────────────────────────
const { year: k8AuditYear } = useAuditContext()
const propagation = useAdjustmentDetailPropagation({
  projectId: toRef(props, 'projectId') as Ref<string>,
  year: k8AuditYear as unknown as Ref<number>,
})
const bringInVisible = ref(false)
const bringInRow = ref<any>(null)
const bringInMatches = computed(() => propagation.matchByAccount(bringInRow.value?.accountCode || ''))
const adjBroughtIn = reactive<Record<string, string[]>>({})
function adjCountFor(accountCode: string): number { return propagation.countForRow(accountCode || '') }
function jumpFirstAdjustment(accountCode: string): void {
  const m = propagation.matchByAccount(accountCode || '')
  if (m.length) propagation.jumpToAdjustment(m[0].entry_group_id)
}
function openBringIn(row: any): void { bringInRow.value = row; bringInVisible.value = true }
function onBringIn(payload: BringInPayload): void {
  const row = bringInRow.value
  if (!row) return
  const field = payload.adjustmentType === 'rje' ? 'rje' : 'aje'
  handleCellChange(row.rowKey, field, payload.amount)
  adjBroughtIn[row.rowKey] = payload.sourceEntryRefs
  ElMessage.success(`已带入 ${payload.lineCount} 笔调整（净额 ${payload.amount.toFixed(2)}）至 ${field === 'rje' ? '重分类调整' : '账项调整'} 列`)
}
onMounted(() => { propagation.load() })

const tableData = computed(() => rows.value)
const CHANGE_RATE_THRESHOLD = 0.3

function isAbnormalRate(rate: number | null): boolean {
  if (rate === null || rate === undefined) return false
  return Math.abs(rate) > CHANGE_RATE_THRESHOLD
}

function handleCellChange(rowKey: string, field: string, value: any): void {
  updateCell(rowKey, field, value)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入明细科目名称', '新增明细科目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：广告费、业务招待费、职工薪酬等',
      inputValidator: (v: string) => (!v || !v.trim() ? '科目名称不能为空' : true),
    })
    if (value && value.trim()) addRow(value.trim())
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowKey: string): void { removeRow(rowKey) }

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template': exportTemplate(); break
    case 'export-data': exportData(); break
    case 'import-data': triggerImport(); break
  }
}

function triggerImport(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) await importData(file)
  }
  input.click()
}

// ─── AI 波动分析（统一 /ai/generate-text 端点）─────────────────────────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK8AiGenerate({
  wpId: toRef(props, 'wpId') as Ref<string>,
})
async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly) return
  const abnormalRows = rows.value.filter((r: any) => r.isEditable && isAbnormalRate(r.yoyChangeRate))
  if (abnormalRows.length === 0) {
    ElMessage.info('未发现异常波动项目（|同比变动率|>30%），无需生成波动分析')
    return
  }
  const detail = abnormalRows
    .map((r: any) => `${r.accountName || '(未命名)'}：变动率${r.yoyChangeRate == null ? '—' : (r.yoyChangeRate * 100).toFixed(1) + '%'}`)
    .join('；')
  const text = await generateAndConfirm(
    'k8-detail-fluctuation',
    '',
    {
      异常项目数: abnormalRows.length,
      异常明细: detail,
      任务: '请针对上述销售费用异常波动明细项目，逐项给出可能的波动原因分析草稿（每项一句，供审计师参考修改）',
    },
    'AI 生成 · 波动说明（填入异常项空白说明）',
  )
  if (!text) return
  // 填入尚未填写波动说明的异常行（作为草稿，供审计师逐行修改）
  let filled = 0
  for (const r of abnormalRows) {
    if (!r.fluctuationNote) { updateCell(r.rowKey, 'fluctuationNote', text); filled++ }
  }
  ElMessage.success(filled > 0 ? `已为 ${filled} 个异常项填入波动说明草稿，请逐行核对修改` : '异常项均已有波动说明，未覆盖')
}
function handleReview(): void { openReviewDialog('K8-2', '销售费用明细表复核') }

function detailRowClass({ row }: { row: any }): string {
  return isAbnormalRate(row.yoyChangeRate) ? 'abnormal-row' : ''
}

// ═══ 费用测算（重新测算复核，源模板 K8-2 "3.XX费用测算如下"）═══════════════
interface RecalcRawRow {
  id: string
  projectName: string
  basisAmount: number   // 计提依据(基数)
  ratePct: number       // 计提比例(%)
  bookAccrue: number    // 账面计提金额
  diffReason: string
  needAdjust: '是' | '否'
}
const RECALC_KEY = 'K8-2-accrual-recalc'
const recalcRaw = ref<RecalcRawRow[]>([])

function _normalizeRecalc(r: any): RecalcRawRow {
  return {
    id: r.id ?? `recalc-${Math.random().toString(36).slice(2, 9)}`,
    projectName: String(r.projectName ?? ''),
    basisAmount: Number(r.basisAmount) || 0,
    ratePct: Number(r.ratePct) || 0,
    bookAccrue: Number(r.bookAccrue) || 0,
    diffReason: String(r.diffReason ?? ''),
    needAdjust: r.needAdjust === '是' ? '是' : '否',
  }
}

function loadRecalc(): void {
  const item = props.allResponses.get(RECALC_KEY)
  const raw = item?.remark ?? item?.conclusion
  if (!raw) { recalcRaw.value = []; return }
  try {
    const p = typeof raw === 'string' ? JSON.parse(raw) : raw
    recalcRaw.value = Array.isArray(p) ? p.map(_normalizeRecalc) : []
  } catch { recalcRaw.value = [] }
}
watch(allResponsesRef, loadRecalc, { immediate: true })

/** 应计提=基数×比例；差异=应计提−账面（公式列） */
const accrualRecalcRows = computed(() =>
  recalcRaw.value.map((r) => {
    const shouldAccrue = (Number(r.basisAmount) || 0) * (Number(r.ratePct) || 0) / 100
    const diff = shouldAccrue - (Number(r.bookAccrue) || 0)
    return { ...r, shouldAccrue, diff }
  }),
)
const recalcAdjustCount = computed(() =>
  accrualRecalcRows.value.filter(r => r.needAdjust === '是' && Math.abs(r.diff) > 0.01).length,
)

function persistRecalc(): void {
  emit('save', RECALC_KEY, { remark: JSON.stringify(recalcRaw.value) })
}
function updateRecalc(id: string, field: keyof RecalcRawRow, value: any): void {
  if (props.isReadonly) return
  const row = recalcRaw.value.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value
  persistRecalc()
}
async function handleAddRecalc(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入测算费用项目名称', '新增费用测算项', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如 折旧费、职工福利费、工会经费等',
      inputValidator: (v: string) => (!v || !v.trim() ? '项目名称不能为空' : true),
    })
    if (value && value.trim()) {
      recalcRaw.value.push(_normalizeRecalc({ projectName: value.trim() }))
      persistRecalc()
    }
  } catch { /* cancelled */ }
}
function removeRecalc(id: string): void {
  if (props.isReadonly) return
  recalcRaw.value = recalcRaw.value.filter(r => r.id !== id)
  persistRecalc()
}
function recalcRowClass({ row }: { row: any }): string {
  return Math.abs(row.diff) > 0.01 ? 'abnormal-row' : ''
}

/** 将"是否调整=是"且差异≠0的测算差异推送为 K8-3 调整分录草稿（对齐 K8-5 差异→K8-3 范式）*/
function handlePushRecalcToK83(): void {
  if (props.isReadonly) return
  const drafts = accrualRecalcRows.value.filter(r => r.needAdjust === '是' && Math.abs(r.diff) > 0.01)
  if (!drafts.length) { ElMessage.info('无"是否调整=是"的测算差异'); return }
  const item = props.allResponses.get('K8-3-adj-entries')
  const raw = item?.remark ?? item?.conclusion
  let existing: any[] = []
  try {
    const p = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(p)) existing = p
  } catch { /* ignore */ }
  const MARK = '【K8-2费用测算】'
  // 去重：先移除上次由本表推送的分录，再重新追加
  existing = existing.filter(e => !String(e.summary ?? '').startsWith(MARK))
  for (const d of drafts) {
    // diff>0 少提→调增费用(借销售费用)；diff<0 多提→冲减费用(贷销售费用)。对方科目留待 K8-3 补录
    existing.push({
      id: `k82recalc-${d.id}`,
      seq: 0,
      category: '账项调整',
      summary: `${MARK}${d.projectName}测算差异`,
      reportItem: '销售费用',
      accountName: '销售费用',
      noteItem: '',
      debitAmount: d.diff > 0 ? Number(d.diff.toFixed(2)) : 0,
      creditAmount: d.diff < 0 ? Number((-d.diff).toFixed(2)) : 0,
      indexRef: 'K8-2',
      remark: d.diffReason || '费用测算差异',
    })
  }
  existing.forEach((e, i) => { e.seq = i + 1 })
  emit('save', 'K8-3-adj-entries', { remark: JSON.stringify(existing) })
  ElMessage.success(`已推送 ${drafts.length} 项测算差异至 K8-3（草稿，请在 K8-3 补录对方科目并核对借贷平衡后保存回写）`)
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  if (v === 0) return '0.00'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return (v * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.k8-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.tab-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.tab-right { display: flex; gap: 8px; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.account-name { font-size: var(--wp-font-size, 13px); color: #303133; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.abnormal-highlight { color: #f56c6c !important; font-weight: 600; }
:deep(.abnormal-row) { background-color: #fef0f0 !important; }
.subtotal-bar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin: 12px 0; padding: 10px 14px; background: linear-gradient(90deg, #eef6ff 0%, #f5faff 100%); border: 1px solid #d6e4f0; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.total-label { font-weight: 700; color: #303133; min-width: 50px; }
.total-item { color: #606266; }
.total-item strong { color: #303133; font-family: 'JetBrains Mono', monospace; }
.k8-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
