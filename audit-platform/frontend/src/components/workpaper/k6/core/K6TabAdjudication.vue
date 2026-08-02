<template>
  <div class="k6-tab-adjudication">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 持有待售</strong>：持有待售资产按账面价值与公允价值减去出售费用后的净额孰低计量。
        持有待售资产（借方）期末=期初+增加-减少-减值；持有待售负债（贷方）期末=期初+增加-减少。
        审定数=未审数+AJE+RJE。三角勾稽要求期末(公式)与审定数一致或差异合理。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>存在与权利：</b>划分为持有待售的资产/处置组真实存在且由被审计单位拥有或控制；</li>
        <li><b>完整性：</b>符合 CAS42 条件的资产/处置组均已划分并记录；</li>
        <li><b>计价和分摊：</b>按账面价值与公允价值减出售费用后净额孰低计量，减值确认恰当；</li>
        <li><b>列报与披露：</b>持有待售分类、计量及终止经营已按 CAS42 恰当列报披露。</li>
      </ol>
    </el-alert>
    <!-- 四表库取数溯源面板 -->
    <WpFourTableSourcePanel
      v-if="props.tbSourceCodes"
      :source-codes="props.tbSourceCodes"
      gross-label="持有待售资产和负债"
    />


    <!-- ═══ 持有待售资产区块（CAS42 列报重分类，借方/资产类） ═══ -->
    <div v-for="section in adjudicationSections" :key="section.sectionKey" class="adj-section">
      <div class="section-header">
        <h4 class="section-title">{{ section.sectionLabel }}</h4>
        <div class="section-actions">
          <el-button size="small" text type="primary" @click="handleAiGenerate(section.sectionKey)">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button size="small" text @click="handleReview(section.sectionKey)">
            <el-icon><View /></el-icon> 复核
          </el-button>
        </div>
      </div>

      <!-- 三角勾稽告警 -->
      <el-alert
        v-if="section.sectionKey === 'asset' && !assetReconciliation.isBalanced"
        type="error"
        :closable="false"
        show-icon
        class="reconciliation-alert"
      >
        资产区块三角勾稽不平！差异 = {{ fmtAmt(assetReconciliation.diff) }} 元
      </el-alert>
      <el-alert
        v-if="section.sectionKey === 'liability' && !liabilityReconciliation.isBalanced"
        type="error"
        :closable="false"
        show-icon
        class="reconciliation-alert"
      >
        负债区块三角勾稽不平！差异 = {{ fmtAmt(liabilityReconciliation.diff) }} 元
      </el-alert>

      <!-- 审定表 el-table -->
      <el-table
        :data="getDisplayRows(section)"
        border
        size="small"
        style="width: 100%"
        :row-class-name="({ row }) => getRowClassName(row, section.sectionKey)"
      >
        <el-table-column prop="label" label="项目" min-width="120" fixed />
        <el-table-column label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.begin"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'begin', v)"
            />
            <span v-else>{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.increase"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'increase', v)"
            />
            <span v-else>{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.decrease"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'decrease', v)"
            />
            <span v-else>{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="section.sectionKey === 'asset'" label="减值准备" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.impairment"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'impairment', v)"
            />
            <span v-else>{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末(公式)" min-width="110" align="right" class-name="formula-col">
          <template #header>
            <el-tooltip :content="section.sectionKey === 'asset' ? '期末=期初+增加-减少-减值' : '期末=期初+增加-减少'" placement="top">
              <span class="formula-header">期末<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.unadjusted"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'unadj', v)"
            />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.aje"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'aje', v)"
            />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.rje"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'rje', v)"
            />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数(公式)" min-width="110" align="right" class-name="formula-col">
          <template #header>
            <el-tooltip content="审定数=未审+AJE+RJE" placement="top">
              <span class="formula-header">审定数<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="80" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warning': row.variationRate != null && Math.abs(row.variationRate) > 0.3 }">
              {{ row.variationRate != null ? (row.variationRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.remark"
              size="small"
              @change="(v) => onRemarkChange(section.sectionKey, row.rowKey, v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ TB回写按钮 + K6-3调整带入 ═══ -->
    <div class="tb-writeback-section">
      <el-button
        type="primary"
        :loading="publishing"
        :disabled="isReadonly"
        @click="handleWritebackTB"
      >
        <el-icon><Upload /></el-icon>
        审定数回写TB（持有待售资产 + 负债）
      </el-button>
      <el-button
        size="small"
        type="success"
        plain
        :disabled="isReadonly"
        @click="importAjeFromK6_3"
      >
        从K6-3带入AJE/RJE
      </el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly || !k6AssetPrefix" :loading="assetAdjPull.loading.value" @click="openAssetBringIn">
        <el-icon><Download /></el-icon> 带入调整(资产)
      </el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly || !k6LiabPrefix" :loading="liabAdjPull.loading.value" @click="openLiabBringIn">
        <el-icon><Download /></el-icon> 带入调整(负债)
      </el-button>
      <span class="tb-hint">
        资产审定合计: {{ fmtAmt(getAssetAuditedTotal()) }} |
        负债审定合计: {{ fmtAmt(getLiabilityAuditedTotal()) }}
      </span>
    </div>

    <!-- TB预填种子提示（首次加载时如有TB数据但未审数为0） -->
    <el-alert
      v-if="showTbSeedHint"
      type="info"
      :closable="true"
      show-icon
      style="margin-bottom:12px"
    >
      <template #title>
        已从试算平衡表获取：资产未审 {{ fmtAmt(props.tbData.unadjustedAsset) }}，负债未审 {{ fmtAmt(props.tbData.unadjustedLiability) }}。
        <el-button size="small" type="primary" link @click="seedFromTb">一键填入未审数</el-button>
      </template>
    </el-alert>

    <!-- ═══ 审计说明 + 结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header-row">
          <span>审计说明</span>
          <el-button size="small" text type="primary" @click="handleAiGenerate('audit-note')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计说明（执行程序、获取证据、分析结论等）"
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header-row">
          <span>审计结论</span>
          <div>
            <el-button size="small" text type="primary" @click="handleAiGenerate('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" text @click="handleReview('conclusion')">
              <el-icon><View /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="填写审计结论"
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>持有待售资产区块</strong>：期末 = 期初 + 增加 − 减少 − 减值（借方/资产类）</li>
        <li><strong>持有待售负债区块</strong>：期末 = 期初 + 增加 − 减少（贷方/负债类）</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>三角勾稽：期末(公式) 应与 审定数 一致或差异合理</li>
        <li>减值列仅资产区块使用（CAS42孰低法）</li>
        <li>回写TB分别写入持有待售资产和负债科目</li>
        <li>「带入调整」：资产/负债各按科目拉取调整分录，逐笔选目标行累加到 AJE/RJE，带入后自动联动披露/附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="assetBringInVisible"
      :matches="assetAdjPull.matches.value"
      :row-options="assetBringInRowOptions"
      subject-label="持有待售资产"
      :loading="assetAdjPull.loading.value"
      @apply="onAssetBringInApply"
    />
    <AdjudicationBringInDialog
      v-model="liabBringInVisible"
      :matches="liabAdjPull.matches.value"
      :row-options="liabBringInRowOptions"
      subject-label="持有待售负债"
      :loading="liabAdjPull.loading.value"
      @apply="onLiabBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabAdjudication.vue — K6-1 审定表（资产+负债双区块，45公式）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.2
 * Requirements: 2.1-2.8
 *
 * 功能：
 * - 双区块el-table：持有待售资产(借方) + 持有待售负债(贷方)
 * - 资产类期末=期初+增加-减少-减值；负债类期末=期初+增加-减少
 * - 审定数=未审+AJE+RJE
 * - 三角勾稽红色高亮（reconciliation.isBalanced → red text）
 * - TB回写按钮 → writebackTB(assetAudited, liabilityAudited)
 * - 底部审计说明+结论+复核按钮(inject openReviewDialog)
 * - Font 13px; formula columns dashed underline + cursor:help + tooltip
 * - AI按钮 section标题右侧
 * - 方法论上下文(琥珀色左边线+浅黄背景)
 */
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { k6QueryCodes, K6_FALLBACK_STANDARD } from '../../composables/k6AccountScope'
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, View, Upload, QuestionFilled, Download } from '@element-plus/icons-vue'
import { useK6Adjudication, type K6AdjRow, type K6AdjSection } from '../../composables/useK6Adjudication'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjustedAsset: number; auditedAsset: number; unadjustedLiability: number; auditedLiability: number }
  isReadonly: boolean
  tbSourceCodes?: Record<string, any> | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 科目码从 scope 取（K6 是宁缺勿造循环，三表零命中时返回空串 → 带入调整按钮禁用）
const k6AssetPrefix = computed(() => k6QueryCodes(props.tbSourceCodes)[0] || '')
const k6LiabPrefix = computed(() => k6QueryCodes(props.tbSourceCodes?.liability)[0] || '')
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const writebackTBFn = inject<(asset: number, liability: number) => Promise<void>>('k6WritebackTB', async () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  adjudicationSections,
  assetReconciliation,
  liabilityReconciliation,
  assetSubtotal,
  auditNote,
  auditConclusion,
  getAssetAuditedTotal,
  getLiabilityAuditedTotal,
  saveAll,
} = useK6Adjudication({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', field, value)
  },
})

const publishing = ref(false)

// ─── 从集中登记带入调整（K6 双科目：资产借方 + 负债贷方，科目由 k6AccountScope 提供） ─────
const assetSectionRows = computed(() => adjudicationSections.value.find(s => s.sectionKey === 'asset')?.rows ?? [])
const liabSectionRows = computed(() => adjudicationSections.value.find(s => s.sectionKey === 'liability')?.rows ?? [])

const {
  adjPull: assetAdjPull,
  visible: assetBringInVisible,
  rowOptions: assetBringInRowOptions,
  open: openAssetBringIn,
  apply: onAssetBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: k6AssetPrefix,
  direction: 'debit', // 持有待售资产（借方）：净发生额 = 借 − 贷
  subjectCode: k6AssetPrefix,
  wpCode: 'K6',
  subjectLabel: '持有待售资产',
  rows: computed(() => assetSectionRows.value.map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.aje, rje: r.rje }))),
  updateCell: (rowKey: string, field: any, value: number) => onFieldChange('asset', rowKey, field, value),
  totalAudited: () => getAssetAuditedTotal(),
})

const {
  adjPull: liabAdjPull,
  visible: liabBringInVisible,
  rowOptions: liabBringInRowOptions,
  open: openLiabBringIn,
  apply: onLiabBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: k6LiabPrefix,
  direction: 'credit', // 持有待售负债（贷方）：净发生额 = 贷 − 借
  subjectCode: k6LiabPrefix,
  wpCode: 'K6',
  subjectLabel: '持有待售负债',
  rows: computed(() => liabSectionRows.value.map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.aje, rje: r.rje }))),
  updateCell: (rowKey: string, field: any, value: number) => onFieldChange('liability', rowKey, field, value),
  totalAudited: () => getLiabilityAuditedTotal(),
})

// ─── Display rows (data + subtotal appended) ─────────────────────────────────

function getDisplayRows(section: K6AdjSection): K6AdjRow[] {
  return [...section.rows, { ...section.subtotalRow }]
}

// ─── Row class styling ───────────────────────────────────────────────────────

function getRowClassName(row: K6AdjRow, sectionKey: string): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  // 三角勾稽不平时数据行红色
  if (sectionKey === 'asset' && !assetReconciliation.value.isBalanced) return 'reconciliation-error-row'
  if (sectionKey === 'liability' && !liabilityReconciliation.value.isBalanced) return 'reconciliation-error-row'
  return ''
}

// ─── 字段变化处理 ────────────────────────────────────────────────────────────

function onFieldChange(sectionKey: string, rowKey: string, field: string, value: number | undefined) {
  const v = value ?? 0
  const prefix = sectionKey === 'asset' ? 'K6-1-asset' : 'K6-1-liab'
  const itemId = `${prefix}-${rowKey}-${field}`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
  // 减值列变化时同步减值合计（供K6-5交叉验证读取 K6-1-impairment-total）
  if (sectionKey === 'asset' && field === 'impairment') {
    persistImpairmentTotal()
  }
}

// ─── 减值合计持久化（供K6-5减值测试交叉验证） ─────────────────────────────────

function persistImpairmentTotal() {
  const total = assetSubtotal.value.impairment
  props.allResponses.set('K6-1-impairment-total', { item_id: 'K6-1-impairment-total', remark: String(total) })
  emit('save', 'K6-1-impairment-total', { remark: String(total) })
}

function onRemarkChange(sectionKey: string, rowKey: string, value: string) {
  const prefix = sectionKey === 'asset' ? 'K6-1-asset' : 'K6-1-liab'
  const itemId = `${prefix}-${rowKey}-remark`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  emit('save', itemId, { remark: value })
}

// ─── 保存审计说明+结论 ───────────────────────────────────────────────────────

function saveConclusion() {
  emit('save', 'K6-1-audit-note', { remark: auditNote.value })
  emit('save', 'K6-1-audit-conclusion', { remark: auditConclusion.value })
}

// ─── TB回写 ─────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  if (!k6AssetPrefix.value && !k6LiabPrefix.value) {
    // 宁缺勿造：无科目时不写库（三表零命中）
    return
  }
  publishing.value = true
  try {
    const assetAudited = getAssetAuditedTotal()
    const liabilityAudited = getLiabilityAuditedTotal()
    // 实际回写 trial_balance + EventBus emit substantive:adjudicated
    await writebackTBFn(assetAudited, liabilityAudited)
    // 保存合计到 responses 供后续回写使用
    emit('save', 'K6-1-audited-asset', { remark: String(assetAudited) })
    emit('save', 'K6-1-audited-liability', { remark: String(liabilityAudited) })
    // 同步减值合计（供K6-5交叉验证）
    persistImpairmentTotal()
    ElMessage.success(`审定数已回写TB：资产=${fmtAmt(assetAudited)}，负债=${fmtAmt(liabilityAudited)}`)
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

const aiLoading = ref(false)

async function handleAiGenerate(section: string) {
  if (props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const context = `持有待售审定表：资产审定合计 ${getAssetAuditedTotal()}，负债审定合计 ${getLiabilityAuditedTotal()}；`
      + `资产区块三角勾稽${assetReconciliation.value.isBalanced ? '平衡' : '不平衡(差异' + assetReconciliation.value.diff + ')'}，`
      + `负债区块三角勾稽${liabilityReconciliation.value.isBalanced ? '平衡' : '不平衡(差异' + liabilityReconciliation.value.diff + ')'}`
    const isConclusion = section === 'conclusion'
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: isConclusion ? 'k6-adjudication-conclusion' : 'k6-adjudication-note',
      context,
      prompt: isConclusion
        ? '根据持有待售资产和负债审定表勾稽结果，生成审计结论'
        : '根据持有待售资产和负债审定表，生成审计说明（执行程序、获取证据、分析结论）',
      existingContent: isConclusion ? auditConclusion.value : auditNote.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      if (isConclusion) auditConclusion.value = text
      else auditNote.value = text
      saveConclusion()
      ElMessage.success('AI内容已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── 从K6-3带入AJE/RJE ──────────────────────────────────────────────────────

function importAjeFromK6_3(): void {
  // K6-3 写了 K6-1-aje-asset / K6-1-rje-asset / K6-1-aje-liab / K6-1-rje-liab（汇总值）
  const ajeAsset = Number(props.allResponses.get('K6-1-aje-asset')?.value ?? props.allResponses.get('K6-1-aje-asset')?.remark ?? 0) || 0
  const rjeAsset = Number(props.allResponses.get('K6-1-rje-asset')?.value ?? props.allResponses.get('K6-1-rje-asset')?.remark ?? 0) || 0
  const ajeLiab = Number(props.allResponses.get('K6-1-aje-liab')?.value ?? props.allResponses.get('K6-1-aje-liab')?.remark ?? 0) || 0
  const rjeLiab = Number(props.allResponses.get('K6-1-rje-liab')?.value ?? props.allResponses.get('K6-1-rje-liab')?.remark ?? 0) || 0

  if (ajeAsset === 0 && rjeAsset === 0 && ajeLiab === 0 && rjeLiab === 0) {
    // 也检查 suggested-aje (来自K6-5/K6-7)
    const k6_5_aje = props.allResponses.get('K6-5-suggested-aje')
    const k6_7_aje = props.allResponses.get('K6-7-suggested-aje')
    if (!k6_5_aje && !k6_7_aje) {
      ElMessage.info('K6-3暂无调整分录数据（请先在K6-3编制并保存回写）')
      return
    }
  }

  // 资产AJE/RJE填入第一行（r0）
  if (ajeAsset !== 0 || rjeAsset !== 0) {
    onFieldChange('asset', 'r0', 'aje', ajeAsset)
    onFieldChange('asset', 'r0', 'rje', rjeAsset)
  }
  // 负债AJE/RJE填入第一行（r0）
  if (ajeLiab !== 0 || rjeLiab !== 0) {
    onFieldChange('liability', 'r0', 'aje', ajeLiab)
    onFieldChange('liability', 'r0', 'rje', rjeLiab)
  }

  const total = ajeAsset + rjeAsset + ajeLiab + rjeLiab
  if (total !== 0) {
    ElMessage.success(`已从K6-3带入：资产AJE ${fmtAmt(ajeAsset)}/RJE ${fmtAmt(rjeAsset)}，负债AJE ${fmtAmt(ajeLiab)}/RJE ${fmtAmt(rjeLiab)}（填入首行）`)
  } else {
    ElMessage.info('K6-3调整合计为0')
  }
}

// ─── TB预填种子（未审数从试算表带入） ─────────────────────────────────────────

const showTbSeedHint = computed(() => {
  // 有TB数据且当前资产/负债首行未审数为0时显示
  const hasTbData = (props.tbData.unadjustedAsset > 0 || props.tbData.unadjustedLiability > 0)
  if (!hasTbData) return false
  // 检查首行是否已有未审数
  const assetUnadj = Number(props.allResponses.get('K6-1-asset-r0-unadj')?.remark ?? 0) || 0
  const liabUnadj = Number(props.allResponses.get('K6-1-liab-r0-unadj')?.remark ?? 0) || 0
  return assetUnadj === 0 && liabUnadj === 0
})

function seedFromTb(): void {
  // 资产未审数填入首行
  if (props.tbData.unadjustedAsset > 0) {
    onFieldChange('asset', 'r0', 'unadj', props.tbData.unadjustedAsset)
  }
  // 负债未审数填入首行
  if (props.tbData.unadjustedLiability > 0) {
    onFieldChange('liability', 'r0', 'unadj', props.tbData.unadjustedLiability)
  }
  ElMessage.success(`已从TB预填：资产未审 ${fmtAmt(props.tbData.unadjustedAsset)}，负债未审 ${fmtAmt(props.tbData.unadjustedLiability)}`)
}

// ─── 金额格式化 ─────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

/* ─── Section ─── */
.adj-section { margin-bottom: 20px; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.section-actions { display: flex; gap: 4px; }
.reconciliation-alert { margin-bottom: 8px; }

/* ─── 公式列样式 ─── */
.formula-header { cursor: help; }
.formula-icon { margin-left: 4px; font-size: 12px; color: #909399; }
.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 表格样式 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { font-weight: 700; background-color: #fafafa !important; }
:deep(.reconciliation-error-row) { color: #f56c6c !important; }
:deep(.formula-col) { background-color: #fafff8; }
.adj-input { width: 100%; }
.adj-input :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.rate-warning { color: #e6a23c; font-weight: 500; }

/* ─── TB回写 ─── */
.tb-writeback-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 16px 0;
  padding: 12px 16px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
}
.tb-hint { font-size: 12px; color: #606266; }

/* ─── 审计说明/结论 ─── */
.audit-note-card { margin-bottom: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 10px 16px; }
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
}

/* ─── 编制提示 ─── */
.k6-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.k6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
