<template>
  <div class="k10-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的其他收益（政府补助等）确已发生且与被审计单位相关；</li>
        <li><b>完整性：</b>所有应确认的其他收益均已记录，与资产/收益相关的政府补助分类恰当；</li>
        <li><b>准确性：</b>其他收益金额计算准确，与批文/到账一致；</li>
        <li><b>分类与列报：</b>已记录于恰当账户并按 CAS16 恰当列报披露。</li>
      </ol>
    </el-alert>
    <!-- 四表库取数溯源面板 -->
    <WpFourTableSourcePanel
      v-if="props.tbSourceCodes"
      :source-codes="props.tbSourceCodes"
      gross-label="其他收益"
    />


    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="k10-guide">
      <div class="k10-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>审定表编制说明</span>
      </div>
      <div class="k10-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">先在 K10-2 明细表逐笔录入其他收益 → 点"从K10-2带入"按来源建行（源模板 ='明细表K10-2'! 联动）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">带入的未审/AJE/重分类 → 审定数自动计算（=未审+AJE+RJE）</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">确认审定数后点击"回写TB" → 6117发生额回写trial_balance</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">与K10-2明细合计交叉验证 → 差额为零则一致</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        <strong>损益类科目（6117其他收益）</strong>：取发生额非余额。6117为贷方科目，贷方=收益增加，借方=冲回。
        审定数=未审数+AJE+RJE。按收益来源分行：政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他。
      </p>
    </div>

    <!-- ═══ Section 标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K10-1 其他收益审定表</h3>
        <el-tag size="small" type="warning" effect="plain">损益类·发生额</el-tag>
      </div>
      <div class="header-actions">
        <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K10-1-adjudication" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-3" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-4" :context-project-id="props.projectId" />
      <GtIndexChip value="K7" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ TB自动取数提示 ═══ -->
    <div v-if="props.tbData" class="tb-info-bar">
      <span>TB取数(6117发生额)：未审 <strong>{{ fmtAmt(props.tbData.unadjusted6117) }}</strong></span>
      <span>审定 <strong>{{ fmtAmt(props.tbData.audited6117) }}</strong></span>
    </div>

    <!-- ═══ 审定表格（11列） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      :row-class-name="getTableRowClassName"
    >
      <!-- 项目 -->
      <el-table-column prop="name" label="项目" min-width="150" fixed="left">
        <template #default="{ row }">
          <strong v-if="row._isTotal">{{ row.name }}</strong>
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>

      <!-- 本期未审 -->
      <el-table-column prop="unadjusted" label="本期未审" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.unadjusted"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'unadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column prop="aje" label="AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.aje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'aje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column prop="rje" label="RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.rje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'rje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定（公式列） -->
      <el-table-column label="审定" width="120" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="审定数 = 未审 + AJE + RJE">审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.unadjusted} + ${row.aje} + ${row.rje} = ${row.audited}`">
            {{ fmtAmt(row.audited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 索引号（仅普通行） -->
      <el-table-column label="索引号" width="80" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="!row._isTotal && row.name" :value="`K10-1`" :context-project-id="props.projectId" />
        </template>
      </el-table-column>

      <!-- 上期未审 -->
      <el-table-column prop="priorUnadj" label="上期未审" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorUnadj"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorUnadj', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorUnadj) }}</span>
        </template>
      </el-table-column>

      <!-- 上期AJE -->
      <el-table-column prop="priorAje" label="上期AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorAje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- 上期RJE -->
      <el-table-column prop="priorRje" label="上期RJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorRje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <!-- 上期审定（公式列） -->
      <el-table-column label="上期审定" width="110" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="上期审定 = 上期未审 + 上期AJE + 上期RJE">上期审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.priorUnadj} + ${row.priorAje} + ${row.priorRje} = ${row.priorAudited}`">
            {{ fmtAmt(row.priorAudited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => adjudication.updateCell(row.rowKey, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePullFromDetail">
        从K10-2带入
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增来源行</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleWritebackTB">
        回写TB（6117发生额）
      </el-button>
    </div>

    <!-- ═══ 与K10-2交叉验证 ═══ -->
    <div v-if="!adjudication.detailCrossValidation.value.isBalanced" class="cross-validation-alert">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>
          K10-1审定合计与K10-2明细合计不一致，差额：{{ fmtAmt(adjudication.detailCrossValidation.value.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 与 TB(6117发生额) 勾稽 ═══ -->
    <div v-if="tbTieOut && !tbTieOut.isBalanced" class="cross-validation-alert">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          审定合计 {{ fmtAmt(adjudication.totalRow.value.audited) }} 与 TB(6117)审定发生额 {{ fmtAmt(props.tbData?.audited6117) }} 不一致，差额：{{ fmtAmt(tbTieOut.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>审计说明</span>
          <div class="note-card-actions">
            <el-button size="small" type="primary" text @click="handleAiNote">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计说明..."
        @change="(v: string) => adjudication.saveNote(v)"
      />
    </el-card>

    <!-- ═══ 结论 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>审计结论</span>
          <div class="note-card-actions">
            <el-button size="small" type="primary" text @click="handleAiConclusion">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <GtReviewTrigger section-id="K10-1-conclusion" label="💬 复核" />
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论..."
        @change="(v: string) => adjudication.saveConclusion(v)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>K10-1为损益类审定表（6117其他收益），取贷方发生额（贷方=收益增加）</li>
        <li><b>编制主脉：K10-2明细逐笔录入 → 「从K10-2带入」逐行建审定表</b>（源模板 ='明细表K10-2'!A11/D11/E11/F11 联动）</li>
        <li>按收益来源分行：总额法政府补助/增值税进项加计抵减/增值税直接减免/个税手续费返还/债务重组损益等</li>
        <li>审定数 = 未审数 + AJE + RJE（公式自动计算）</li>
        <li>审定完成后点击"回写TB"将发生额回写trial_balance（6117）</li>
        <li>合计行应与K10-2明细表合计一致（差额为零）；下方并列显示与试算平衡表(6117)勾稽差额</li>
        <li>与日常活动相关→其他收益(6117)；与日常活动无关→营业外收入(6301,K12)</li>
        <li>「带入调整」：按科目6117拉取调整分录，逐笔选目标来源行累加到 AJE/RJE，带入后自动联动披露/附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6117 其他收益"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabAdjudication.vue — K10-1 其他收益审定表
 *
 * Spec: .kiro/specs/k10-other-income/ | Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 功能：
 * - 69公式，损益类6117，发生额取数
 * - 按收益来源分行（政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他）
 * - 11列：项目|本期未审|AJE|RJE|审定|索引号|上期未审|上期AJE|上期RJE|上期审定|备注
 * - 公式列（审定/上期审定）dashed underline + cursor:help + tooltip
 * - TB回写（6117发生额！）
 * - 与K10-2明细交叉验证（差额提示）
 * - 底部：审计说明 + 结论 + 复核入口
 * - 每个section AI辅助按钮
 */
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { computed, inject, toRef, defineAsyncComponent } from 'vue'
import { InfoFilled, MagicStick, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useK10Adjudication, type K10AdjRow } from '../../composables/useK10Adjudication'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData?: { unadjusted6117: number; audited6117: number }
  isReadonly: boolean
  prefill?: Array<{ name: string; unadjustedDebit: number; unadjustedCredit: number   tbSourceCodes?: Record<string, any> | null
}>
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const adjudication = useK10Adjudication({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  prefill: computed(() => props.prefill ?? []) as any,
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── 从集中登记带入调整（6117 其他收益，损益贷方） ────────────────────────────
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6117',
  direction: 'credit', // 损益贷方（收益）：净发生额 = 贷 − 借
  subjectCode: '6117',
  wpCode: 'K10',
  subjectLabel: '其他收益(6117)',
  rows: adjudication.rows,
  updateCell: adjudication.updateCell,
  totalAudited: () => adjudication.totalRow.value.audited,
})

// ─── Table Data (rows + total) ───────────────────────────────────────────────

interface TableRow extends K10AdjRow {
  _isTotal?: boolean
}

const tableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = adjudication.rows.value.map(r => ({ ...r, _isTotal: false }))
  const total = adjudication.totalRow.value
  rows.push({
    rowKey: '__total__',
    name: total.label,
    unadjusted: total.unadjusted,
    aje: total.aje,
    rje: total.rje,
    audited: total.audited,
    priorUnadj: total.priorUnadj,
    priorAje: total.priorAje,
    priorRje: total.priorRje,
    priorAudited: total.priorAudited,
    yoyChange: total.yoyChange,
    remark: '',
    isEditable: false,
    _isTotal: true,
  })
  return rows
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly)

/** 审定合计 vs TB(6117)审定发生额 勾稽（仅当 TB 有审定值时校验） */
const tbTieOut = computed<{ diff: number; isBalanced: boolean } | null>(() => {
  const tbAudited = props.tbData?.audited6117
  if (tbAudited == null || tbAudited === 0) return null
  const diff = adjudication.totalRow.value.audited - tbAudited
  return { diff, isBalanced: Math.abs(diff) < 0.01 }
})

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getTableRowClassName({ row }: { row: TableRow }): string {
  if (row._isTotal) return 'total-row'
  return ''
}

// ─── 操作 ────────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入收益来源名称', '新增来源行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：政府补助-XX/专项基金收益...',
    })
    if (value?.trim()) {
      adjudication.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

async function handleWritebackTB(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认将审定合计 ${fmtAmt(adjudication.totalRow.value.audited)} 回写TB（6117发生额）？`,
      '回写确认',
      { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'warning' },
    )
    await adjudication.writeback()
    ElMessage.success('已回写TB（6117其他收益发生额）')
  } catch { /* cancelled */ }
}

/** 从 K10-2 明细表带入（复现源模板 ='明细表K10-2'! SUMIF 联动，覆盖当前来源行） */
async function handlePullFromDetail(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将按 K10-2 明细表逐行重建审定表来源行（项目/未审/AJE/重分类/上期数），会覆盖当前手工来源行。是否继续？',
      '从K10-2带入',
      { confirmButtonText: '确认带入', cancelButtonText: '取消', type: 'warning' },
    )
    const n = adjudication.pullFromDetail()
    if (n > 0) ElMessage.success(`已从K10-2带入 ${n} 个来源行`)
    else ElMessage.warning('K10-2明细表暂无可带入的项目行，请先编制明细表')
  } catch { /* cancelled */ }
}

// ─── AI 辅助（统一 /ai/generate-text，context 全转字符串避 422） ─────────────

/** context 必须是 dict[str,str]（后端 422 校验），值全部转字符串 */
function buildAiContext(): Record<string, string> {
  const t = adjudication.totalRow.value
  return {
    科目: '6117 其他收益（损益类·贷方发生额）',
    审定合计: String(t.audited),
    未审合计: String(t.unadjusted),
    AJE合计: String(t.aje),
    RJE合计: String(t.rje),
    上期审定合计: String(t.priorAudited),
    与明细差额: String(adjudication.detailCrossValidation.value.diff),
    来源行: adjudication.rows.value.map(r => `${r.name}:审定${r.audited}`).join('；'),
  }
}

async function callAi(section: string, prompt: string, existingContent = ''): Promise<string> {
  const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    section,
    prompt,
    existingContent,
    context: buildAiContext(),
  })
  return (res?.data?.content ?? res?.content ?? '') as string
}

async function handleAiAssist(): Promise<void> {
  await handleAiNote()
}

async function handleAiNote(): Promise<void> {
  if (!props.wpId) return
  try {
    const content = await callAi(
      'K10-1-audit-note',
      '为K10其他收益(6117)审定表生成审计说明：概述本期其他收益构成（政府补助分类）、发生额与上期对比、审定调整情况及与明细表勾稽结论。',
      adjudication.auditNote.value,
    )
    if (content) { adjudication.saveNote(content); ElMessage.success('AI生成完成') }
    else ElMessage.warning('AI未返回内容，请手动填写')
  } catch { ElMessage.warning('AI生成失败，请手动填写') }
}

async function handleAiConclusion(): Promise<void> {
  if (!props.wpId) return
  try {
    const content = await callAi(
      'K10-1-audit-conclusion',
      '为K10其他收益(6117)审定表生成审计结论：其他收益发生、完整性、准确性、分类列报认定是否恰当，审定金额是否公允。',
      adjudication.auditConclusion.value,
    )
    if (content) { adjudication.saveConclusion(content); ElMessage.success('AI生成完成') }
    else ElMessage.warning('AI未返回内容，请手动填写')
  } catch { ElMessage.warning('AI生成失败，请手动填写') }
}
</script>

<style scoped>
.k10-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

.k10-guide {
  margin-bottom: 14px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.k10-guide-header {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; color: #303133; margin-bottom: 8px;
}
.k10-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 14px; }
.step-item { display: flex; align-items: flex-start; gap: 5px; }
.step-num { color: #409eff; font-weight: 700; min-width: 16px; }
.step-text { color: #606266; line-height: 1.5; font-size: 12px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-left h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.tb-info-bar {
  display: flex; gap: 16px; align-items: center;
  margin-bottom: 10px; padding: 6px 12px;
  background: #ecf5ff; border-radius: 4px;
  font-size: 12px; color: #409eff;
}
.tb-info-bar strong { color: #303133; }

/* 公式列样式 */
:deep(.formula-col) .cell { border-bottom: 1px dashed #909399; }
.formula-header {
  cursor: help;
  border-bottom: 1px dashed #606266;
  padding-bottom: 1px;
}
.formula-value {
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
  padding-bottom: 1px;
}

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background-color: #f5f7fa !important; font-weight: 600; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

.cross-validation-alert { margin-top: 12px; }

.note-card { margin-top: 16px; }
.note-card-header {
  display: flex; justify-content: space-between; align-items: center;
}
.note-card-header span { font-weight: 600; font-size: 14px; }
.note-card-actions { display: flex; gap: 6px; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
