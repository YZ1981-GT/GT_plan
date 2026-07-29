<template>
  <div class="k2-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K2-1审定表审定其他流动资产(1231借方/资产类)，含合同取得成本/预付款项/待摊费用等。资产类期末=期初+借方-贷方；审定数=未审+AJE+RJE。三角勾稽：期末=期初+借-贷，差额须为0。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>记录的其他流动资产在资产负债表日确实存在且已恰当记录；</li>
        <li><b>完整性：</b>所有应当记录的其他流动资产均已记录，相关披露完整；</li>
        <li><b>权利和义务：</b>记录的其他流动资产确为被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>其他流动资产以恰当金额包括在报表中，计价调整已恰当记录，披露充分适当；</li>
        <li><b>列报与披露：</b>已按企业会计准则规定作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- Section标题 + AI/复核按钮右对齐 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>K2-1 其他流动资产审定表</span>
          <div class="title-actions">
            <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
              <el-icon><Download /></el-icon> 带入调整
            </el-button>
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-overall')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-1')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 三角勾稽校验 Banner -->
      <div class="reconciliation-banner" :class="reconciliation.isBalanced ? 'balanced' : 'unbalanced'">
        <el-icon v-if="reconciliation.isBalanced" color="#67c23a"><CircleCheck /></el-icon>
        <el-icon v-else color="#f56c6c"><WarningFilled /></el-icon>
        <span v-if="reconciliation.isBalanced">✓ 三角勾稽平衡（期末=期初+借-贷）</span>
        <span v-else>✗ 三角勾稽不平，差额: {{ fmtAmt(reconciliation.diff) }}</span>
      </div>

      <!-- 跨Sheet交叉验证徽章 -->
      <div class="cross-sheet-badge" v-if="crossSheetResult">
        <el-tag :type="crossSheetResult.isMatch ? 'success' : 'warning'" size="small" effect="plain">
          K2-1合计 vs K2-2明细:
          {{ crossSheetResult.isMatch ? '一致 ✓' : `差额 ${fmtAmt(crossSheetResult.diff)}` }}
        </el-tag>
      </div>

      <!-- 审定表主体 -->
      <el-table
        :data="displayRows"
        border stripe size="small" class="adj-table"
        :max-height="540"
        :row-class-name="getRowClassName"
      >
        <!-- 项目 -->
        <el-table-column prop="label" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowKey === 'subtotal' }">{{ row.label }}</span>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>

        <!-- 本期借方 -->
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>

        <!-- 本期贷方 -->
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列） -->
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 期末=期初+借方-贷方" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.end) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 未审数（TB自动取入） -->
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE（可编辑） -->
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onAjeChange(row.rowKey, $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE（可编辑） -->
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onRjeChange(row.rowKey, $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数（公式列） -->
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 审定=未审+AJE+RJE" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 变动率（公式列） -->
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 变动率=(审定-上期审定)/|上期审定|" placement="top">
              <span class="formula-cell" :class="getChangeRateClass(row.changeRate)">
                {{ formatChangeRate(row.changeRate) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @blur="onRemarkChange(row.rowKey, ($event.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写其他流动资产审定说明..."
        :disabled="isReadonly"
        @blur="saveNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-1-conclusion')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..."
        :disabled="isReadonly"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- 与TB核对区 -->
    <el-card shadow="never" class="block-card" style="margin-top:12px">
      <template #header>
        <div class="section-title">
          <span>与试算平衡表核对</span>
        </div>
      </template>
      <div class="tb-reconcile-grid">
        <div class="tb-row">
          <span class="tb-label">K2-1 审定合计</span>
          <span class="tb-value">{{ fmtAmt(subtotalRow.audited) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">试算平衡表数(1231)</span>
          <span class="tb-value tb-auto">{{ fmtAmt(props.tbData.audited1231) }}</span>
        </div>
        <div class="tb-row" :class="{ 'tb-diff-warn': Math.abs(subtotalRow.audited - props.tbData.audited1231) > 0.01 }">
          <span class="tb-label">差异</span>
          <span class="tb-value">{{ fmtAmt(subtotalRow.audited - props.tbData.audited1231) }}</span>
          <el-tag v-if="Math.abs(subtotalRow.audited - props.tbData.audited1231) < 0.01" type="success" size="small" effect="plain" style="margin-left:8px">✓ 核对一致</el-tag>
          <el-tag v-else type="danger" size="small" effect="plain" style="margin-left:8px">✗ 差异需排查</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="warning" plain @click="handleFillFromDetail">
        从K2-2明细带入
      </el-button>
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB(1231)
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>其他流动资产(1231)：资产类，期末=期初+借方-贷方</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(灰色斜体只读)</li>
        <li>三角勾稽：期末=期初+借-贷，绿色表示平衡，红色表示差异</li>
        <li>公式列(期末/审定数/变动率)虚线下划线+鼠标悬停显示公式来源</li>
        <li>变动率=（审定-上期审定）/ |上期审定|，上期为0则显示"-"</li>
        <li>跨Sheet验证：K2-1合计应与K2-2明细表合计一致</li>
        <li>"确认审定"将回写trial_balance(1231)并发布EventBus事件通知附注刷新</li>
        <li>「带入调整」：按科目1231拉取调整分录，逐笔选目标分类行累加到 AJE/RJE，带入后自动联动披露/附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1231 其他流动资产"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabAdjudication.vue — K2-1 审定表（85公式+三角勾稽+TB回写）
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 核心功能：
 * - el-table 23行×16列 85公式 审定表
 * - 公式列：期末=期初+借-贷，审定=未审+AJE+RJE（dashed underline + cursor:help + tooltip）
 * - 三角勾稽 Banner：绿色✓ / 红色✗
 * - 合计行（bottom subtotal）
 * - TB回写(1231) + EventBus substantive:adjudicated
 * - 审计说明(textarea + AI) + 结论 + 复核入口
 * - 跨Sheet验证 badge（K2-1 total vs K2-2 detail total）
 * - Section标题行右侧 AI + 复核按钮
 */
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick, CircleCheck, WarningFilled, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useK2Adjudication, type K2AdjRow } from '../../composables/useK2Adjudication'
import { useK2CrossSheet } from '../../composables/useK2CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

// ─── Props / Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1231: number; audited1231: number }
  prefill?: Array<Record<string, unknown>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Inject ───────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  subtotalRow,
  reconciliation,
  auditNote,
  auditConclusion,
  updateField,
} = useK2Adjudication(allResponsesRef as any, {
  prefill: toRef(props, 'prefill') as any,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

const { adjudicationVsDetail } = useK2CrossSheet(allResponsesRef as any)

// ─── 从集中登记带入调整（1231 其他流动资产，资产借方） ────────────────────────
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1231',
  direction: 'debit', // 资产借方：净发生额 = 借 − 贷
  subjectCode: '1231',
  wpCode: 'K2',
  subjectLabel: '其他流动资产(1231)',
  rows: computed(() => rows.value.map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.aje, rje: r.rje }))),
  updateCell: (rowKey: string, field: any, value: number) => updateField(rowKey, field, value),
  totalAudited: () => subtotalRow.value.audited,
})

// ─── Local State ──────────────────────────────────────────────────────────────

const publishing = ref(false)

// ─── Display Data ─────────────────────────────────────────────────────────────

/** 数据行 + 合计行 */
const displayRows = computed((): K2AdjRow[] => {
  return [...rows.value, subtotalRow.value]
})

/** 跨sheet交叉验证结果 */
const crossSheetResult = computed(() => adjudicationVsDetail.value)

// ─── Event Handlers ───────────────────────────────────────────────────────────

function onAjeChange(rowKey: string, value: number | undefined) {
  const v = value ?? 0
  updateField(rowKey, 'aje', v)
}

function onRjeChange(rowKey: string, value: number | undefined) {
  const v = value ?? 0
  updateField(rowKey, 'rje', v)
}

function onRemarkChange(rowKey: string, value: string) {
  updateField(rowKey, 'remark', value)
}

function saveNote() {
  emit('save', 'K2-1-audit-note', { remark: auditNote.value })
}

function saveConclusion() {
  emit('save', 'K2-1-audit-conclusion', { remark: auditConclusion.value })
}

/** 确认审定 → 回写TB(1231) + EventBus 通知 */
async function handleWritebackTB() {
  publishing.value = true
  try {
    const auditedTotal = subtotalRow.value.audited
    // 1. 调用TB回写端点
    await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1231',
      audited_amount: auditedTotal,
    })
    // 2. 持久化审定合计
    emit('save', 'K2-1-audited-total', { remark: String(auditedTotal) })
    // 3. EventBus发布审定事件（通知附注/其他底稿刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K2',
      accountCode: '1231',
      auditedAmount: auditedTotal,
      adjudicatedAmount: auditedTotal,
      timestamp: Date.now(),
    })
    ElMessage.success('审定数已回写TB（1231其他流动资产）')
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

/** 从K2-2明细表按性质汇总带入审定表各分类行 */
function handleFillFromDetail(): void {
  const detailData = props.allResponses.get('K2-2-detail-rows')
  const raw = detailData?.remark ?? detailData?.value ?? (typeof detailData === 'string' ? detailData : null)
  if (!raw) {
    ElMessage.warning('K2-2明细表暂无数据，请先编制明细表')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessage.info('K2-2明细表为空')
      return
    }
    // 按性质汇总期末余额
    const byNature: Record<string, number> = {}
    for (const row of parsed) {
      const nature = row.nature || '其他'
      const endBal = Number(row.endBalance ?? 0)
      byNature[nature] = (byNature[nature] || 0) + endBal
    }
    // 映射到审定表行（通过rowKey匹配）
    let filled = 0
    for (const [nature, amount] of Object.entries(byNature)) {
      if (amount === 0) continue
      // 尝试按性质名关键词匹配审定表行
      const matchRow = rows.value.find(r =>
        r.label?.includes(nature) || nature.includes(r.label || ''),
      )
      if (matchRow) {
        updateField(matchRow.rowKey, 'unadjusted', amount)
        filled++
      }
    }
    if (filled > 0) {
      ElMessage.success(`已从K2-2明细按性质汇总带入 ${filled} 行未审数`)
    } else {
      ElMessage.info('未找到匹配的审定表行（性质名称不一致）')
    }
  } catch {
    ElMessage.warning('解析K2-2数据失败')
  }
}

async function handleAiGenerate(section: string) {
  try {
    const context: Record<string, string> = {
      accountCode: '1231',
      accountName: '其他流动资产',
      sheet: 'K2-1',
      section,
      auditedTotal: String(subtotalRow.value.audited ?? 0),
      unadjustedTotal: String(subtotalRow.value.unadjusted ?? 0),
      reconciliationStatus: reconciliation.value.isBalanced ? '三角勾稽平衡' : `不平衡，差额${reconciliation.value.diff}`,
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: section === 'adj-note'
        ? '请生成其他流动资产(1231)审定表的审计说明，概述审定过程与结果'
        : section === 'adj-conclusion'
          ? '请生成其他流动资产(1231)审定表的审计结论'
          : '请生成其他流动资产(1231)审定表的综合分析说明',
      context,
      existingContent: section === 'adj-note' ? auditNote.value : auditConclusion.value,
      section,
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (!generated) { ElMessage.warning('AI未生成内容'); return }
    if (section === 'adj-note' || section === 'adj-overall') {
      auditNote.value = generated
      saveNote()
    } else if (section === 'adj-conclusion') {
      auditConclusion.value = generated
      saveConclusion()
    }
    ElMessage.success('AI内容已填入')
  } catch {
    ElMessage.warning('AI生成失败或已取消')
  }
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Formatters ───────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatChangeRate(rate: number | null): string {
  if (rate == null) return '-'
  return `${rate >= 0 ? '+' : ''}${rate.toFixed(1)}%`
}

function getChangeRateClass(rate: number | null): string {
  if (rate == null) return ''
  if (Math.abs(rate) > 50) return 'rate-warning'
  if (Math.abs(rate) > 20) return 'rate-attention'
  return ''
}

function getRowClassName({ row }: { row: K2AdjRow }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  return ''
}
</script>

<style scoped>
.k2-tab-adjudication {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }

/* 三角勾稽 Banner */
.reconciliation-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}
.reconciliation-banner.balanced {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  color: #67c23a;
}
.reconciliation-banner.unbalanced {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  color: #f56c6c;
}

/* 跨Sheet验证徽章 */
.cross-sheet-badge {
  margin-bottom: 12px;
}

/* 卡片布局 */
.block-card {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.title-actions {
  display: flex;
  gap: 8px;
}

/* 审定表 */
.adj-table {
  font-size: var(--wp-font-size, 13px);
}
.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* TB自动取入（只读灰色斜体） */
.tb-auto {
  color: var(--el-text-color-secondary);
  font-style: italic;
}

/* 合计行样式 */
.subtotal-label {
  font-weight: 600;
}
:deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 变动率警告色 */
.rate-warning {
  color: var(--el-color-danger);
  font-weight: 600;
}
.rate-attention {
  color: var(--el-color-warning);
  font-weight: 500;
}

/* 审计说明/结论卡片 */
.note-card {
  margin-bottom: 12px;
}

/* 操作按钮 */
.action-bar {
  margin-top: 16px;
  text-align: right;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}

/* TB核对区 */
.tb-reconcile-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-radius: 4px;
}
.tb-label {
  min-width: 160px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.tb-value {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 13px;
}
.tb-diff-warn {
  background: #fef0f0;
  border: 1px solid #fde2e2;
}
</style>
