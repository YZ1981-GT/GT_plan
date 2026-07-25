<template>
  <div class="k12-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的营业外收入（政府补助/罚没利得/债务重组利得等）确已发生；</li>
        <li><b>完整性：</b>所有应确认的营业外收入均已记录，不存在漏记或跨期；</li>
        <li><b>准确性：</b>营业外收入金额计算准确、与支持性文件一致；</li>
        <li><b>分类与列报：</b>与营业收入/其他收益的划分恰当，列报披露充分。</li>
      </ol>
    </el-alert>

    <!-- ═══ 跨底稿引用（GtIndexChip：K12-1 → TB） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
      <GtIndexChip value="K12-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K12-3" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="k12-audit-goal"
    >
      <template #title>审计目标</template>
      <template #default>
        确认营业外收入（6301）本期发生额的真实性、完整性与分类准确性；按来源核实与日常活动无关的利得已正确计入营业外收入，
        审定发生额与K12-2明细一致并准确回写试算表。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="k12-methodology-ctx">
      <p><strong>营业外收入(6301)</strong>：与日常经营活动无关的各项利得，包括政府补助、债务重组利得、资产盘盈利得、罚款收入、捐赠利得、无法支付款项转入等。损益类贷方科目，取发生额非余额。</p>
      <p>审定数 = 未审数 + AJE + RJE。同比变动率 = (本期审定 − 上期审定) ÷ |上期审定|。</p>
    </div>

    <!-- ═══ 损益类科目公式提示 ═══ -->
    <div class="k12-formula-badge">
      <span>⚠️ 损益类贷方科目6301：发生额 = 贷方发生（收入增加）− 借方发生（冲回）</span>
    </div>

    <!-- ═══ 审定表 section ═══ -->
    <el-card shadow="never" class="k12-section-card">
      <template #header>
        <div class="section-header">
          <div class="section-title-group">
            <span class="section-title">营业外收入审定表 K12-1</span>
            <el-tag type="warning" size="small" class="income-tag">损益类·贷方·发生额</el-tag>
            <el-tag size="small" type="info" effect="plain">共 {{ adjudication.rows.value.length }} 行</el-tag>
            <!-- 交叉验证badge -->
            <el-tag
              v-if="!adjudication.detailCrossValidation.value.isBalanced"
              type="danger"
              size="small"
              effect="dark"
              class="cv-badge"
            >
              ⚠ K12-1 vs K12-2 差异 {{ fmtAmt(adjudication.detailCrossValidation.value.diff) }}
            </el-tag>
            <el-tag
              v-else
              type="success"
              size="small"
              class="cv-badge"
            >
              ✓ K12-1 = K12-2
            </el-tag>
          </div>
          <div class="section-actions">
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="props.isReadonly"
              :loading="adjPull.loading.value"
              @click="openBringInAdjustment"
            >
              <el-icon><Download /></el-icon> 带入调整
            </el-button>
            <el-button size="small" :loading="aiLoading" @click="handleAI('adjudication')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <GtReviewTrigger section-id="K12-1-adjudication" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table
        :data="adjudication.rows.value"
        border
        size="small"
        show-summary
        :summary-method="getSummaries"
        style="width: 100%"
        highlight-current-row
        class="adjudication-table"
      >
        <!-- 项目名称 -->
        <el-table-column prop="name" label="项目（来源）" min-width="140" fixed>
          <template #default="{ row }">
            <span class="category-cell">{{ row.name }}</span>
          </template>
        </el-table-column>

        <!-- 本期未审 -->
        <el-table-column prop="unadjusted" label="本期未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.unadjusted"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'unadjusted', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.unadjusted < 0 }]">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE -->
        <el-table-column prop="aje" label="AJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.aje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'aje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.aje < 0 }]">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE -->
        <el-table-column prop="rje" label="RJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.rje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'rje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.rje < 0 }]">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数（公式列） -->
        <el-table-column prop="audited" label="审定数" min-width="115" align="right" class-name="auto-calc-col">
          <template #header>
            <el-tooltip content="公式：审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="`${row.unadjusted} + ${row.aje} + ${row.rje} = ${row.audited}`" placement="top">
              <span class="formula-value">{{ fmtAmt(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 上期未审 -->
        <el-table-column prop="priorUnadj" label="上期未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorUnadj"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorUnadj', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorUnadj < 0 }]">{{ fmtAmt(row.priorUnadj) }}</span>
          </template>
        </el-table-column>

        <!-- 上期AJE -->
        <el-table-column prop="priorAje" label="上期AJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorAje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorAje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorAje < 0 }]">{{ fmtAmt(row.priorAje) }}</span>
          </template>
        </el-table-column>

        <!-- 上期RJE -->
        <el-table-column prop="priorRje" label="上期RJE" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly && row.isEditable"
              :model-value="row.priorRje"
              size="small"
              :controls="false"
              :precision="2"
              class="cell-input"
              @change="(v: number) => adjudication.updateCell(row.rowKey, 'priorRje', v ?? 0)"
            />
            <span v-else :class="['cell-value', { negative: row.priorRje < 0 }]">{{ fmtAmt(row.priorRje) }}</span>
          </template>
        </el-table-column>

        <!-- 上期审定（公式列） -->
        <el-table-column prop="priorAudited" label="上期审定" min-width="115" align="right" class-name="auto-calc-col">
          <template #header>
            <el-tooltip content="公式：上期审定 = 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-col">上期审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="上期审定 = 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-value">{{ fmtAmt(row.priorAudited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 同比变动（公式列） -->
        <el-table-column prop="yoyChange" label="同比变动" min-width="90" align="right" class-name="auto-calc-col">
          <template #header>
            <el-tooltip content="公式：同比变动 = (本期审定 − 上期审定) ÷ |上期审定|" placement="top">
              <span class="formula-col">同比变动</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="(本期审定 − 上期审定) ÷ |上期审定|" placement="top">
              <span :class="['formula-value', { negative: row.yoyChange != null && row.yoyChange < 0 }]">
                {{ fmtPercent(row.yoyChange) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 索引号（源模板列） -->
        <el-table-column prop="refIndex" label="索引号" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly && row.isEditable"
              v-model="row.refIndex"
              size="small"
              placeholder="如 K12-2"
              @change="adjudication.updateCell(row.rowKey, 'refIndex', row.refIndex)"
            />
            <span v-else class="cell-value">{{ row.refIndex || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly && row.isEditable"
              v-model="row.remark"
              size="small"
              placeholder="备注..."
              @change="adjudication.updateCell(row.rowKey, 'remark', row.remark)"
            />
            <span v-else class="cell-value">{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!props.isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.isEditable" link size="small" type="danger" @click="adjudication.removeRow(row.rowKey)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!props.isReadonly" class="table-actions">
        <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增来源行</el-button>
      </div>
    </el-card>

    <!-- ═══ 试算平衡表核对行（源模板：试算平衡表数 / 差异数） ═══ -->
    <el-card shadow="never" class="k12-section-card k12-tb-recon-card">
      <template #header><span class="section-title">与试算平衡表核对</span></template>
      <div class="tb-recon-grid">
        <div class="tb-recon-item">
          <span class="tb-recon-label">审定合计（本表）</span>
          <span class="tb-recon-value">{{ fmtAmt(adjudication.totalRow.value.audited) }}</span>
        </div>
        <div class="tb-recon-item">
          <span class="tb-recon-label">试算平衡表数（6301审定发生额）</span>
          <span class="tb-recon-value">{{ fmtAmt(props.tbData?.audited6301) }}</span>
        </div>
        <div class="tb-recon-item">
          <span class="tb-recon-label">差异数</span>
          <span :class="['tb-recon-value', { 'diff-warn': tbDiffAbnormal }]">{{ fmtAmt(tbDiff) }}</span>
        </div>
        <el-tag v-if="tbDiffAbnormal" type="danger" size="small" effect="dark">⚠ 审定合计与试算表存在差异，请核对</el-tag>
        <el-tag v-else type="success" size="small">✓ 与试算平衡表一致</el-tag>
      </div>
    </el-card>

    <!-- ═══ TB回写操作栏 ═══ -->
    <div class="k12-action-bar">
      <el-button
        type="primary"
        size="small"
        :disabled="props.isReadonly"
        :loading="writebackLoading"
        @click="handleWritebackTB"
      >
        回写审定数 → TB(6301发生额)
      </el-button>
      <span class="tb-info">
        TB未审发生额：{{ fmtAmt(props.tbData?.unadjusted6301) }}　|　
        TB审定发生额：{{ fmtAmt(props.tbData?.audited6301) }}
      </span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="k12-section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计说明</span>
          <div class="section-actions">
            <el-button size="small" link type="primary" @click="handleAI('note')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请输入审计说明（变动原因分析、特殊事项说明等）..."
        :disabled="props.isReadonly"
        @blur="handleNoteSave"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="k12-section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button size="small" link type="primary" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计结论..."
        :disabled="props.isReadonly"
        @blur="handleConclusionSave"
      />
    </el-card>

    <!-- ═══ 编制提示（details折叠） ═══ -->
    <details class="k12-tips-details">
      <summary>编制提示</summary>
      <ul class="tips-list">
        <li>营业外收入为损益类贷方科目(6301)，取发生额（贷方-借方），非期末余额</li>
        <li>审定数 = 未审数 + AJE + RJE，同比变动 = (本期-上期)/|上期|</li>
        <li>K12-1审定合计应与K12-2明细合计一致，差异时显示红色告警badge</li>
        <li>回写操作将审定发生额写入试算表科目6301，并发布 substantive:adjudicated 联动附注</li>
        <li>与日常活动无关的利得计入营业外收入(6301)；与日常活动相关计入其他收益(6117/K10)</li>
        <li>「带入调整」：按科目6301拉取调整分录，逐笔选目标分类行累加到 AJE/RJE，带入后自动联动披露表与附注</li>
      </ul>
    </details>

    <!-- ═══ 从集中登记带入调整 弹窗（K12 试点） ═══ -->
    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6301 营业外收入"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabAdjudication.vue — K12-1 营业外收入审定表
 *
 * 损益类！取发生额非余额（6301贷方科目）
 * 按来源分行：政府补助/债务重组利得/资产盘盈利得/罚款收入/捐赠利得/无法支付款项转入/其他
 * GtIndexChip跨底稿引用：K12-1 → TB(试算表) / K12-2(明细) / K12-3(调整)
 *
 * Spec: .kiro/specs/k12-non-operating-income/ Task 4.2
 * Requirements: 2.1-2.7
 */
import { ref, defineAsyncComponent, watch, toRef, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Download } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { useK12Adjudication } from '../../composables/useK12Adjudication'
import { generateK12AiText } from '../../composables/useK12AiText'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { eventBus } from '@/utils/eventBus'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtReviewTrigger = defineAsyncComponent(() => import('../../GtReviewTrigger.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6301: number; audited6301: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

// props.allResponses 经父级模板绑定已解包为 Map；用 ref+watch 重新包成 Ref 喂 composable
const allResponsesRef = ref(props.allResponses)
watch(() => props.allResponses, (val) => { allResponsesRef.value = val }, { immediate: true })

const adjudication = useK12Adjudication({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as any,
  wpId: toRef(props, 'wpId') as any,
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId: string, value: any) => emit('save', itemId, value),
  writebackTB: handleWritebackTBInternal,
})

// ─── 从集中登记带入调整（K12 试点，adjustment-collaboration-and-propagation） ──
// 审定表按科目(6301)拉取集中调整分录，逐笔分配到目标分类行的 AJE/RJE 列（累加）。
// 带入后 writeback → substantive:adjudicated → 披露表 + 附注自动刷新。
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6301',
  direction: 'credit', // 损益贷方：净发生额 = 贷 − 借
  subjectCode: '6301',
  wpCode: 'K12',
  subjectLabel: '营业外收入(6301)',
  rows: adjudication.rows,
  updateCell: adjudication.updateCell,
  totalAudited: () => adjudication.totalRow.value.audited,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackLoading = ref(false)

// ─── 试算平衡表核对（审定合计 vs TB 6301 审定发生额） ─────────────────────────
const tbDiff = computed(() => {
  const audited = adjudication.totalRow.value.audited || 0
  const tbAudited = Number(props.tbData?.audited6301 ?? 0)
  return audited - tbAudited
})
const tbDiffAbnormal = computed(() => Math.abs(tbDiff.value) > 1)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined | null): string {
  if (val == null || isNaN(val as number) || val === 0) return '—'
  return (val as number).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: any): string[] {
  const sums: string[] = []
  const t = adjudication.totalRow.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合  计'; return }
    const map: Record<string, number | null> = {
      unadjusted: t.unadjusted,
      aje: t.aje,
      rje: t.rje,
      audited: t.audited,
      priorUnadj: t.priorUnadj,
      priorAje: t.priorAje,
      priorRje: t.priorRje,
      priorAudited: t.priorAudited,
      yoyChange: t.yoyChange,
    }
    const prop = col.property
    if (prop === 'yoyChange') {
      sums[i] = fmtPercent(t.yoyChange)
    } else if (prop && map[prop] !== undefined) {
      sums[i] = fmtAmt(map[prop] as number)
    } else {
      sums[i] = ''
    }
  })
  return sums
}

// ─── 动态行 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入收入来源名称', '新增来源行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：政府补助/债务重组利得/资产盘盈利得...',
    })
    if (value?.trim()) {
      adjudication.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────

async function handleWritebackTBInternal(auditedAmount: number): Promise<void> {
  // P1-8：真实 HTTP 回写 trial_balance.audited_amount（原仅 emit 事件不落库）
  if (props.projectId) {
    await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '6301',
      audited_amount: auditedAmount,
    })
  }
  // 发布 EventBus 'substantive:adjudicated'（附注刷新 + 联动）
  eventBus.emit('substantive:adjudicated' as any, {
    accountCode: '6301',
    auditedAmount,
    wpCode: 'K12',
    type: 'occurrence_amount', // 标识：发生额回写（损益类）
    timestamp: Date.now(),
  })
  ElMessage.success('审定数已回写试算表（科目6301发生额）')
}

async function handleWritebackTB(): Promise<void> {
  writebackLoading.value = true
  try {
    await adjudication.writeback()
  } catch (err: any) {
    ElMessage.error(`回写失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

function handleNoteSave(): void {
  adjudication.saveNote(adjudication.auditNote.value)
}

function handleConclusionSave(): void {
  adjudication.saveConclusion(adjudication.auditConclusion.value)
}

// ─── AI辅助（接真实 /ai/generate-text，context 为 dict[str,str]） ─────────────

const aiLoading = ref(false)

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const t = adjudication.totalRow.value
    const context: Record<string, unknown> = {
      科目: '6301 营业外收入（损益类·贷方·发生额）',
      本期审定合计: fmtAmt(t.audited),
      上期审定合计: fmtAmt(t.priorAudited),
      同比变动: fmtPercent(t.yoyChange),
      各来源审定: adjudication.rows.value
        .map(r => `${r.name}=${fmtAmt(r.audited)}`)
        .join('；'),
      与K12_2差异: fmtAmt(adjudication.detailCrossValidation.value.diff),
    }
    const promptMap: Record<string, string> = {
      adjudication: '你是资深审计师。请基于营业外收入审定表数据，分析各来源本期发生额、同比变动及分类合理性，重点关注非经常性损益列报正确性，输出审计说明草稿。',
      note: '你是资深审计师。请为营业外收入审定表撰写审计说明（变动原因分析、特殊事项、非经常性损益列报），供人工确认。',
      conclusion: '你是资深审计师。请为营业外收入审定表撰写审计结论，说明发生额真实完整、分类列报是否恰当。',
    }
    const existing = section === 'conclusion' ? adjudication.auditConclusion.value : adjudication.auditNote.value
    const content = await generateK12AiText(props.wpId, {
      prompt: promptMap[section] || promptMap.adjudication,
      section: `K12-1-${section}`,
      context,
      existingContent: existing,
    })
    if (!content) return
    if (section === 'conclusion') {
      adjudication.auditConclusion.value = content
      adjudication.saveConclusion(content)
    } else {
      adjudication.auditNote.value = content
      adjudication.saveNote(content)
    }
  } finally {
    aiLoading.value = false
  }
}

</script>

<style scoped>
.k12-tab-adjudication {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ─── 跨底稿引用栏 ─── */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.cross-refs-label {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}

.k12-audit-goal { font-size: var(--wp-font-size, 13px); }

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.k12-methodology-ctx {
  padding: 10px 14px;
  background: #fffbe6;
  border-left: 4px solid #e6a23c;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.7;
}
.k12-methodology-ctx p {
  margin: 0 0 4px;
}
.k12-methodology-ctx p:last-child {
  margin-bottom: 0;
}

/* ─── 公式提示badge ─── */
.k12-formula-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  font-size: 12px;
  color: #e6a23c;
}

/* ─── Section card ─── */
.k12-section-card {
  margin: 0;
}
.k12-section-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: #fafbfc;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.income-tag {
  font-size: 11px;
}
.cv-badge {
  font-size: 11px;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ─── 审定表样式 ─── */
.adjudication-table {
  font-size: var(--wp-font-size, 13px);
}
.adjudication-table :deep(.el-table__header th) {
  font-size: 12px;
  background: #f8f9fb;
}
.adjudication-table :deep(.el-table__footer td) {
  font-weight: 600;
  background: #f0f4ff;
}

/* auto-calc-col 灰底虚线（公式列） */
.adjudication-table :deep(.auto-calc-col) {
  background: #fafafa;
}
.formula-col {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #409eff;
  font-weight: 500;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #303133;
  display: inline-block;
  padding: 0 2px;
}

.category-cell {
  font-weight: 500;
  color: #303133;
}

.cell-input {
  width: 100%;
}
.cell-input :deep(.el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-value {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.cell-value.negative,
.formula-value.negative {
  color: #f56c6c;
}

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

/* ─── 试算平衡表核对 ─── */
.k12-tb-recon-card :deep(.el-card__body) { padding: 10px 16px; }
.tb-recon-grid {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}
.tb-recon-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tb-recon-label { font-size: 12px; color: #909399; }
.tb-recon-value { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }
.tb-recon-value.diff-warn { color: #f56c6c; }

/* ─── 操作栏 ─── */
.k12-action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 6px;
  border: 1px solid #d9ecff;
}
.tb-info {
  font-size: 12px;
  color: #909399;
}

/* ─── 编制提示 ─── */
.k12-tips-details {
  font-size: 12px;
  color: #909399;
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}
.k12-tips-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
  margin-bottom: 4px;
}
.tips-list {
  margin: 6px 0 0 16px;
  padding: 0;
  line-height: 1.8;
}
.tips-list li {
  margin: 2px 0;
}
</style>
