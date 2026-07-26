<template>
  <div class="h3-tab-adjudication-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产审定表（成本模式），列示原值与累计折旧双区块，净值 = 原值期末 − 折旧期末。</p>
        <p>2. 期初数应与上年末审定数一致；未审数取自试算表（科目 1503 投资性房地产 / 1504 累计折旧），审定数 = 未审 + AJE + RJE。</p>
        <p>3. 计量模式在成本模式与公允价值模式之间选择（CAS3）：成本模式计提折旧与减值；公允价值模式不计提折旧、以公允价值调整账面价值，请切换至公允价值版本。</p>
        <p>4. 关注三角勾稽是否平衡（期初 + 增加 − 减少 ± 转换 = 期末）。</p>
        <p>5.「带入调整(原值/折旧/减值)」：从集中登记按科目 1503/1504/1505 拉取调整分录，逐笔分配到各分类的 AJE/RJE（原值借方净额、折旧/减值贷方净额），带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产（成本模式：原值 1503 + 累计折旧 1504）期末余额的存在、准确与完整，确认调整分录恰当，为报表及附注披露提供审定依据。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="openFillDialog">从 H3-2 回填</el-button>
      <el-button
        size="small"
        type="warning"
        :disabled="isReadonly || (!hasDetailCostDiff && !hasDetailDepDiff)"
        @click="alignFromH32"
      >
        {{ hasDetailCostDiff || hasDetailDepDiff ? '一键对齐 H3-2' : '已与 H3-2 勾稽' }}
      </el-button>
      <el-button
        size="small"
        :disabled="isReadonly || !hasTransferDiff"
        @click="onFillTransferFromH36"
      >
        {{ hasTransferDiff ? '从 H3-6 回填转换' : '转换已勾稽' }}
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="adjPullCost.loading.value" @click="openBringInCost">
        <el-icon><Download /></el-icon>带入调整(原值)
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="adjPullDep.loading.value" @click="openBringInDep">
        <el-icon><Download /></el-icon>带入调整(折旧)
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="adjPullImpair.loading.value" @click="openBringInImpair">
        <el-icon><Download /></el-icon>带入调整(减值)
      </el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H3-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ originalRows.length }} 行</el-tag>
      <el-tag v-if="h32CategoryMatch.unmatchedCount > 0" size="small" type="warning">
        H3-2 非标准类别 {{ h32CategoryMatch.unmatchedCount }} 行
      </el-tag>
    </div>

    <!-- 回填预览对话框 -->
    <el-dialog v-model="fillDialogVisible" title="从 H3-2 回填 H3-1" width="720px" destroy-on-close>
      <el-radio-group v-model="fillMode" class="fill-mode-group">
        <el-radio value="book">仅账面+未审（保留 AJE/RJE，推荐）</el-radio>
        <el-radio value="full">完整覆盖（含明细 AJE/RJE）</el-radio>
      </el-radio-group>
      <p v-if="fillPreview.unmatchedCount" class="fill-warn">
        注意：H3-2 有 {{ fillPreview.unmatchedCount }} 行非标准类别，金额 {{ fmtNum(fillPreview.unmatchedEnd) }} 将归入归一后类别。
      </p>
      <el-table :data="fillPreview.diffs" border size="small" max-height="360" empty-text="无差异（已与 H3-2 一致）">
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column prop="block" label="区块" width="70" />
        <el-table-column prop="field" label="字段" width="80" />
        <el-table-column prop="before" label="回填前" align="right" min-width="100">
          <template #default="{ row }">{{ fmtNum(row.before) }}</template>
        </el-table-column>
        <el-table-column prop="after" label="回填后" align="right" min-width="100">
          <template #default="{ row }">{{ fmtNum(row.after) }}</template>
        </el-table-column>
        <el-table-column prop="delta" label="差异" align="right" min-width="100">
          <template #default="{ row }">
            <span :class="{ 'text-danger': Math.abs(row.delta) >= 0.01 }">{{ fmtNum(row.delta) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="fillDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="fillPreview.empty" @click="confirmFillFromH32">确认回填</el-button>
      </template>
    </el-dialog>

    <!-- 一、投资性房地产 — 原值 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、投资性房地产 — 原值</span>
          <span v-if="!isTriangleBalanced" class="triangle-warn">⚠ 勾稽不平</span>
        </div>
      </template>
      <el-table :data="originalRows" border size="small" class="audit-table" show-summary :summary-method="getOriginalSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折旧 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>二、累计折旧</span>
      </template>
      <el-table :data="depRows" border size="small" class="audit-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="provision" label="计提" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.provision" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'provision')" />
          </template>
        </el-table-column>
        <el-table-column prop="reversal" label="转回" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.reversal" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'reversal')" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDep" label="转换折旧" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferDep" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'transferDep')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+计提-转回±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、减值准备 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>三、减值准备</span>
      </template>
      <el-table :data="impairRows" border size="small" class="audit-table" show-summary :summary-method="getImpairSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="provision" label="计提" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.provision" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'provision')" />
          </template>
        </el-table-column>
        <el-table-column prop="reversal" label="转回" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.reversal" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'reversal')" />
          </template>
        </el-table-column>
        <el-table-column prop="transferImp" label="转换减值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferImp" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'transferImp')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+计提-转回±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onImpairCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 净值合计 -->
    <el-card shadow="never" class="net-value-card">
      <div class="net-value-row">
        <span class="net-label">净值合计（原值期末 − 折旧期末 − 减值期末）</span>
        <span class="net-amount">{{ fmtNum(netValueTotal) }}</span>
      </div>
    </el-card>

    <!-- 跨表勾稽面板：H3-2 明细 / H3-6 互转 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>跨表勾稽（H3-2 明细 / H3-6 互转）</span>
          <div class="chip-row-inline">
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-2')">打开 H3-2</el-tag>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-6 互转审核')">打开 H3-6</el-tag>
          </div>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="H3-1 原值审定">{{ fmtNum(originalTotal.audited) }}</el-descriptions-item>
        <el-descriptions-item label="H3-2 原值期末">
          <span :class="{ 'text-danger': hasDetailCostDiff }">{{ fmtNum(detailCostAudited) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="原值差异">
          <el-tag :type="hasDetailCostDiff ? 'danger' : 'success'" size="small">{{ fmtNum(detailCostDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-1 折旧审定">{{ fmtNum(depTotal.audited) }}</el-descriptions-item>
        <el-descriptions-item label="H3-2 折旧期末">
          <span :class="{ 'text-danger': hasDetailDepDiff }">{{ fmtNum(detailDepAudited) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="折旧差异">
          <el-tag :type="hasDetailDepDiff ? 'danger' : 'success'" size="small">{{ fmtNum(detailDepDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-1 转换列合计">{{ fmtNum(originalTotal.transfer) }}</el-descriptions-item>
        <el-descriptions-item label="H3-6 净转入">
          <span :class="{ 'text-danger': hasTransferDiff }">{{ fmtNum(transferNet) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="转换差异">
          <el-tag :type="hasTransferDiff ? 'danger' : 'success'" size="small">{{ fmtNum(transferDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-6 自用→投资(H1)" :span="1">{{ fmtNum(transferSummary.fromH1) }}</el-descriptions-item>
        <el-descriptions-item label="H3-6 投资→自用(H1)" :span="1">{{ fmtNum(transferSummary.toH1) }}</el-descriptions-item>
        <el-descriptions-item label="H3-6 在建→投资(H2)" :span="1">{{ fmtNum(transferSummary.fromH2) }}</el-descriptions-item>

        <el-descriptions-item label="H3-3 AJE(1503)">{{ fmtNum(adjustmentSync.aje1503) }}</el-descriptions-item>
        <el-descriptions-item label="H3-3 RJE(1503)">{{ fmtNum(adjustmentSync.rje1503) }}</el-descriptions-item>
        <el-descriptions-item label="H3-3 折旧AJE/RJE">{{ fmtNum(adjustmentSync.aje1504) }} / {{ fmtNum(adjustmentSync.rje1504) }}</el-descriptions-item>
        <el-descriptions-item label="H3-3 减值AJE/RJE" :span="3">{{ fmtNum(adjustmentSync.aje1505) }} / {{ fmtNum(adjustmentSync.rje1505) }}</el-descriptions-item>
      </el-descriptions>
      <p class="reconcile-note">{{ crossSheetNote }}</p>
      <div v-if="hasDetailCostDiff || hasDetailDepDiff" class="align-row">
        <el-button size="small" type="warning" :disabled="isReadonly" @click="alignFromH32">差异一键对齐（账面模式）</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-cost')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：程序执行情况、成本模式下原值/累计折旧勾稽核对、拟调整与未调整事项及其影响。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、未见异常。B、除上述调整事项外未见异常。C、存在重大未调整事项（或审计范围受限），不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
      <div class="chip-row">
        <span class="chip-label">跳转：</span>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-6 互转审核')">H3-6 互转审核</el-tag>
      </div>
    </el-card>

    <AdjudicationBringInDialog
      v-model="bringInCostVisible"
      :matches="adjPullCost.matches.value"
      :row-options="bringInCostRowOptions"
      subject-label="1503 投资性房地产原值"
      :loading="adjPullCost.loading.value"
      @apply="onBringInCostApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInDepVisible"
      :matches="adjPullDep.matches.value"
      :row-options="bringInDepRowOptions"
      subject-label="1504 累计折旧"
      :loading="adjPullDep.loading.value"
      @apply="onBringInDepApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInImpairVisible"
      :matches="adjPullImpair.matches.value"
      :row-options="bringInImpairRowOptions"
      subject-label="1505 减值准备"
      :loading="adjPullImpair.loading.value"
      @apply="onBringInImpairApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationCost.vue — H3-1 审定表（成本模式）
 * 双区块(原值+折旧)+三角勾稽+TB回写+AI+💬复核+GtIndexChip→H3-6
 */
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useH3AdjudicationCost } from '../../composables/useH3AdjudicationCost'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import type { H3CostOriginalRow, H3CostDepRow, H3CostImpairRow } from '../../composables/useH3AdjudicationCost'
import type { H3FillDiffRow, H3FillMode } from '../../composables/h3FillFromDetail'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3CrossSheet } from '../../composables/useH3CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost'),
})

const {
  originalRows, depRows, impairRows, originalTotal, depTotal, impairTotal, netValueTotal,
  isTriangleBalanced, h32CategoryMatch,
  updateOriginalCell, updateDepCell, updateImpairCell,
  previewFillFromH32, fillFromH32Detail, fillTransferFromH36,
} = useH3AdjudicationCost({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

// ─── 从集中登记带入调整（三科目：1503原值[资产借]/1504累计折旧[备抵贷]/1505减值[备抵贷]；带入AJE/RJE） ───
const bringInCostRows = computed(() =>
  originalRows.value.map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullCost,
  visible: bringInCostVisible,
  rowOptions: bringInCostRowOptions,
  open: openBringInCost,
  apply: onBringInCostApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1503',
  direction: 'debit',
  subjectCode: '1503',
  wpCode: 'H3',
  subjectLabel: '投资性房地产原值(1503)',
  rows: bringInCostRows,
  updateCell: (rowKey: string, field: any, value: number) => updateOriginalCell(rowKey, field, value),
  totalAudited: () => originalTotal.value.audited,
})

const bringInDepRows = computed(() =>
  depRows.value.map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullDep,
  visible: bringInDepVisible,
  rowOptions: bringInDepRowOptions,
  open: openBringInDep,
  apply: onBringInDepApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1504',
  direction: 'credit',
  subjectCode: '1504',
  wpCode: 'H3',
  subjectLabel: '累计折旧(1504)',
  rows: bringInDepRows,
  updateCell: (rowKey: string, field: any, value: number) => updateDepCell(rowKey, field, value),
  totalAudited: () => depTotal.value.audited,
})

const bringInImpairRows = computed(() =>
  impairRows.value.map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullImpair,
  visible: bringInImpairVisible,
  rowOptions: bringInImpairRowOptions,
  open: openBringInImpair,
  apply: onBringInImpairApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1505',
  direction: 'credit',
  subjectCode: '1505',
  wpCode: 'H3',
  subjectLabel: '减值准备(1505)',
  rows: bringInImpairRows,
  updateCell: (rowKey: string, field: any, value: number) => updateImpairCell(rowKey, field, value),
  totalAudited: () => impairTotal.value.audited,
})

const fillDialogVisible = ref(false)
const fillMode = ref<H3FillMode>('book')
const fillPreview = ref<{ diffs: H3FillDiffRow[]; unmatchedCount: number; unmatchedEnd: number; empty: boolean }>({
  diffs: [], unmatchedCount: 0, unmatchedEnd: 0, empty: true,
})

function refreshFillPreview() {
  fillPreview.value = previewFillFromH32(fillMode.value)
}
function openFillDialog() {
  refreshFillPreview()
  if (fillPreview.value.empty) {
    ElMessage.warning('H3-2 成本明细尚无数据，请先编制 H3-2')
    return
  }
  fillDialogVisible.value = true
}
watch(fillMode, () => { if (fillDialogVisible.value) refreshFillPreview() })

function confirmFillFromH32() {
  const r = fillFromH32Detail(fillMode.value)
  fillDialogVisible.value = false
  ElMessage.success(
    `已按类别回填原值 ${r.originalFilled} / 折旧 ${r.depFilled} / 减值 ${r.impairFilled} 行（${fillMode.value === 'book' ? '保留AJE/RJE' : '完整覆盖'}）`,
  )
}
function alignFromH32() {
  const r = fillFromH32Detail('book')
  if (!r.originalFilled) {
    ElMessage.warning('H3-2 成本明细尚无数据')
    return
  }
  ElMessage.success('已按账面模式对齐 H3-2（保留 AJE/RJE）')
}
function onFillTransferFromH36() {
  const r = fillTransferFromH36(transferNet.value)
  ElMessage.success(`已按权重分摊 H3-6 净转入至转换列（${r.filled} 行）`)
}

const measurementModel = ref('cost')
const { adjudicationFromDetail, transferSummary, detailTotals, adjustmentSync } = useH3CrossSheet(
  computed(() => props.allResponses) as any,
  measurementModel,
)

const detailCostAudited = computed(() => {
  const v = adjudicationFromDetail.value
  return 'costAudited' in v ? v.costAudited : detailTotals.value.assetEnd
})
const detailDepAudited = computed(() => {
  const v = adjudicationFromDetail.value
  return 'depAudited' in v ? v.depAudited : detailTotals.value.depEnd
})
const detailCostDiff = computed(() => originalTotal.value.audited - detailCostAudited.value)
const detailDepDiff = computed(() => depTotal.value.audited - detailDepAudited.value)
const hasDetailCostDiff = computed(() => Math.abs(detailCostDiff.value) >= 0.01)
const hasDetailDepDiff = computed(() => Math.abs(detailDepDiff.value) >= 0.01)

const transferNet = computed(
  () => transferSummary.value.fromH1 + transferSummary.value.fromH2 - transferSummary.value.toH1,
)
const transferDiff = computed(() => originalTotal.value.transfer - transferNet.value)
const hasTransferDiff = computed(() => Math.abs(transferDiff.value) >= 0.01)

const crossSheetNote = computed(() => {
  if (!hasDetailCostDiff.value && !hasDetailDepDiff.value && !hasTransferDiff.value) {
    return 'H3-1 与 H3-2 明细、H3-6 互转勾稽一致。'
  }
  const parts: string[] = []
  if (hasDetailCostDiff.value) parts.push(`原值差 ${detailCostDiff.value.toLocaleString('zh-CN')}`)
  if (hasDetailDepDiff.value) parts.push(`折旧差 ${detailDepDiff.value.toLocaleString('zh-CN')}`)
  if (hasTransferDiff.value) parts.push(`转换差 ${transferDiff.value.toLocaleString('zh-CN')}`)
  return `存在勾稽差异：${parts.join('；')}。请核对明细编制、互转审核或审定调整。`
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-1-cost-audit-note'
const CONCLUSION_KEY = 'H3-1-cost-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onOrigCellChange(row: H3CostOriginalRow, field: keyof H3CostOriginalRow) {
  updateOriginalCell(row.rowId, field, (row as any)[field])
  debouncedWritebackTb()
}
function onDepCellChange(row: H3CostDepRow, field: keyof H3CostDepRow) {
  updateDepCell(row.rowId, field, (row as any)[field])
  debouncedWritebackTb()
}
function onImpairCellChange(row: H3CostImpairRow, field: keyof H3CostImpairRow) {
  updateImpairCell(row.rowId, field, (row as any)[field])
  debouncedWritebackTb()
}

// ─── TB 回写 + 发布 substantive:adjudicated ────────────────────────────────
let _wbTimer: ReturnType<typeof setTimeout> | null = null
function debouncedWritebackTb() {
  if (_wbTimer) clearTimeout(_wbTimer)
  _wbTimer = setTimeout(() => { void writebackTrialBalance() }, 1500)
}

async function writebackTrialBalance() {
  try {
    const costAudited = originalTotal.value.audited ?? 0
    const depAudited = depTotal.value.audited ?? 0
    // 回写 1503 投资性房地产原值（借方审定数）
    await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1503',
      audited_amount: costAudited,
    })
    // 回写 1504 累计折旧（贷方备抵审定数，绝对值）
    await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1504',
      audited_amount: depAudited,
    })
    // 发布审定事件联动附注/公式管理/A13
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'H3',
      accountCode: '1503',
      auditedAmount: costAudited - depAudited,
      adjudicatedAmount: costAudited - depAudited,
      timestamp: Date.now(),
    })
  } catch (e) {
    console.warn('[H3-1 Cost] TB writeback failed:', e)
  }
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getOriginalSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'increase', 'decrease', 'transfer', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((originalTotal.value as any)[key] ?? 0) : ''
  })
}
function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'provision', 'reversal', 'transferDep', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((depTotal.value as any)[key] ?? 0) : ''
  })
}
function getImpairSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'provision', 'reversal', 'transferImp', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((impairTotal.value as any)[key] ?? 0) : ''
  })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-start; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.tab-toolbar .chip-wrap { margin-left: auto; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.triangle-warn { color: var(--el-color-danger); font-size: 12px; font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.net-value-card { margin-bottom: 16px; }
.net-value-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.net-label { font-weight: 600; }
.net-amount { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
.chip-row { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.chip-label { font-size: 12px; color: var(--el-text-color-secondary); }
.nav-chip { cursor: pointer; }
.reconcile-card { margin-bottom: 16px; }
.chip-row-inline { display: flex; gap: 8px; }
.reconcile-note { margin: 8px 0 0; font-size: 12px; color: #909399; line-height: 1.5; }
.align-row { margin-top: 8px; }
.fill-mode-group { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.fill-warn { color: var(--el-color-warning); font-size: 12px; margin: 0 0 8px; }
.text-danger { color: var(--el-color-danger); font-weight: 500; }
</style>
