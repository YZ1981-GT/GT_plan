<script setup lang="ts">
/**
 * D1TabBusinessMode.vue — 应收票据业务模式分析 D1-6（对齐 D1-4）
 *
 * 卡片视图 / 矩阵视图 + (一) 业务模式及依据 + (二) 分类判断 QA + 审计意见区 + AI
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1BusinessMode, type BusinessModeRow } from '../composables/useD1BusinessMode'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import D1BusinessModeCard from './D1BusinessModeCard.vue'
import D1BusinessModeMatrix from './D1BusinessModeMatrix.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import http from '@/utils/http'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

const openReviewDialog = inject<((params: { sectionId: string }) => void) | null>('openReviewDialog', null)

const {
  basisRows,
  qaMatrix,
  businessModeResults,
  reportItemResults,
  auditProcedures,
  auditNote,
  auditConclusion,
  updateBasisRow,
  updateQACell,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
} = useD1BusinessMode({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch {
      ElMessage.warning('保存失败，请重试')
    }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const BUSINESS_MODE_OPTIONS = [
  '以收取合同现金流量为目标',
  '以收取合同现金流量和出售金融资产为目标',
  '其他',
]

// ─── 双视图：卡片 / 矩阵（在线编辑由 D1 入口工具栏统一切换） ─────────────
const viewMode = ref<'card' | 'matrix'>('matrix')
const viewModeOptions = [
  { label: '卡片视图', value: 'card' as const },
  { label: '矩阵视图', value: 'matrix' as const },
]

const TAB_LABELS: Record<string, string> = {
  'fixed-high-bank': '高信用银行承兑',
  'fixed-low-bank': '低信用银行承兑',
  'fixed-commercial': '商业承兑汇票',
}

const activeTab = ref(basisRows.value[0]?.rowId ?? 'fixed-high-bank')

const completedComboCount = computed(() => {
  const qaCount = qaMatrix.value.questions.length
  return basisRows.value.filter((row, i) => {
    const hasBasis = !!(row.businessMode || row.basis)
    const qaDone = qaMatrix.value.cells.filter((r) => r[i]?.answer).length === qaCount
    return hasBasis && qaDone && !!businessModeResults.value[i]
  }).length
})

const judgmentCompleteCount = computed(() =>
  businessModeResults.value.filter((r) => !!r).length,
)

const AUDIT_OBJECTIVES = [
  '了解并评价被审计单位对应收票据组合的业务模式是否恰当；',
  '业务模式判断与贴现/背书实际情况及未来预期一致；',
  '分类判断矩阵结论与「业务模式及依据」表相互印证；',
  '列报项目（应收票据/应收款项融资等）符合 CAS 22 要求并与 D1-1 审定表勾稽。',
]

const BUSINESS_MODE_REFERENCE = {
  heading: '关于应收票据业务模式',
  principles: [
    '业务模式决定企业所管理金融资产现金流量的来源是收取合同现金流量、出售金融资产还是两者兼有。',
    '业务模式是一项事实而非仅仅是认定，也不是一项选择，不依赖于管理层对单项工具的意图。',
    '业务模式应当在反映如何对多组金融资产一起进行管理以实现特定业务目标的层次上确定。',
    '出售本身并不能决定业务模式。',
    '但频繁且重大的出售（贴现或背书）说明业务模式不以收取合同现金流量为目标。',
  ],
  checks: [
    {
      title: '1. 了解并观察被审计单位如何管理其金融资产以产生现金流量',
      items: [
        '1.1 了解被审计单位关键管理人员决定的对金融资产进行管理的特定业务目标。',
        '1.2 了解被审计单位评价和向关键管理人员报告金融资产业绩的方式、影响金融资产业绩风险及其管理方式、相关管理人员获得报酬的方式（例如报酬基于公允价值还是合同现金流量）。',
      ],
    },
    {
      title: '2. 了解被审计单位确定业务模式的层次',
      items: [
        '若被审计单位将应收票据划分为不同组合从而确定多个业务模式，分析划分组合的依据是否明确、各组合是否可明确区分。',
      ],
    },
    {
      title: '3. 对于以收取合同现金流量为目标的业务模式',
      items: [
        '3.1 了解以前的出售（背书或贴现）是否频繁，但金额不重大，或金额虽重大（如在压力情景下出售）但不频繁。',
        '3.2 了解以前的出售（背书或贴现）是否在接近到期日发生。',
        '3.3 了解被审计单位对未来出售（背书或贴现）活动的预期。',
      ],
    },
    {
      title: '4. 对于以收取合同现金流量和出售金融资产为目标的业务模式',
      items: [
        '4.1 了解收取合同现金流量和出售金融资产对于实现其管理目标而言是否都不可或缺。',
        '4.2 了解被审计单位是否涉及更高频率和更大价值的出售，即经常进行大额贴现或背书。',
      ],
    },
    {
      title: '5. 对于其他业务模式',
      items: [
        '5.1 了解被审计单位持有应收票据的目的是否是交易性的。',
        '5.2 了解被审计单位是否基于应收票据的公允价值作出决策并对其进行管理。',
      ],
    },
  ],
}

const PREP_HINTS = [
  '卡片视图按组合逐项填写依据与 QA；矩阵视图横向比对三组合，对齐 Excel 模板。',
  '导出模板含「编制说明」工作表；表(一)业务模式依据支持 Excel 导入导出。',
  '表(二)分类判断 QA 矩阵仅在页面填写，导出/导入不包含该部分。',
  '三组合固定行（高/低信用银行承兑、商业承兑）请勿删除或改名。',
  '「确定业务模式」「确定报表项目」由 QA 矩阵自动判定，无需手工填写。',
  '判定结论应与 D1-7 备查簿、D1-8 贴现/背书明细及 D1-1 列报分类核对。',
]

const GUIDANCE_SECTIONS = [
  {
    title: '提示 1：贴现/背书与终止确认、业务模式',
    paragraphs: [
      '银行票据的贴现或背书是否导致票据终止确认，将影响业务模式判断：',
      '· 信用等级低的银行承兑汇票、商业承兑汇票：贴现/背书通常不导致终止确认，一般不应改变「以收取合同现金流量为目标」的业务模式。',
      '· 信用等级高的银行承兑汇票：若频繁贴现或背书，可能属于「以收取合同现金流量和出售金融资产为目标」，应列报为应收款项融资。',
      '高信用银行通常包括 6 家大型商业银行（中行、农行、建行、工行、邮储、交行）及 9 家上市股份制商业银行（招商、浦发、中信、光大、华夏、民生、平安、兴业、浙商）。',
    ],
  },
  {
    title: '提示 2：组合层次评价',
    paragraphs: [
      '应在组合层次（而非逐张票据）评价业务模式，可区分：',
      '· 银行承兑汇票与财务公司/商业承兑汇票；或',
      '· 信用等级高与信用等级低/商业承兑汇票等不同组合分别判断。',
    ],
  },
  {
    title: '监管参考',
    paragraphs: [
      '证监会《2013年上市公司年报会计监管报告》：',
      '· 信用等级较低银行承兑汇票及商业承兑汇票：主要风险为信用风险和延迟支付风险；银行一般保留追索权，贴现/背书时不应终止确认。',
      '· 信用等级较高银行承兑汇票：主要风险为利率风险；贴现/背书时风险报酬已转移，可以终止确认。',
    ],
  },
]

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-6')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingProcedures = ref(false)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildBmContext(guidance: string): Record<string, unknown> {
  const basisSummary = basisRows.value.map((r) =>
    `${r.combinationName}: 模式=${r.businessMode || '未填'}, 依据=${r.basis || '无'}`,
  ).join('\n')
  const qaSummary = qaMatrix.value.questions.map((q, qi) => {
    const answers = qaMatrix.value.columns.map((col, ci) =>
      `${col}=${qaMatrix.value.cells[qi]?.[ci]?.answer || '未答'}`,
    ).join(', ')
    return `${q} → ${answers}`
  }).join('\n')
  return {
    sheet: 'D1-6',
    objectives: AUDIT_OBJECTIVES.join(' '),
    basisSummary,
    qaSummary,
    businessModeResults: businessModeResults.value.join(' | '),
    reportItemResults: reportItemResults.value.join(' | '),
    auditProcedures: auditProcedures.value || '',
    guidance,
  }
}

async function generateAuditProceduresWithAI() {
  if (props.isReadonly) return
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'bm-audit-procedures',
      auditProcedures.value,
      buildBmContext('按编号列出D1-6业务模式分析应执行的审计程序，覆盖组合划分、贴现背书观察、QA矩阵填写、与D1-7/D1-8勾稽。'),
      'AI · 审计过程',
    )
    if (text) saveAuditProcedures(text)
  } finally {
    aiLoadingProcedures.value = false
  }
}

async function generateAuditNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'bm-audit-note',
      auditNote.value,
      buildBmContext('根据D1-6业务模式依据表与分类判断矩阵生成审计说明。'),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateAuditConclusionWithAI() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'bm-audit-conclusion',
      auditConclusion.value,
      buildBmContext(`审计说明：${auditNote.value || '（未填写）'}；列报判定：${reportItemResults.value.join('、') || '未完成'}`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

function onReview(sectionId: string) {
  openReviewDialog?.({ sectionId })
}

function onCellContextMenu(row: BusinessModeRow, event: MouseEvent) {
  event.preventDefault()
  openReviewDialog?.({ sectionId: 'D1-bm-cell', rowId: row.rowId })
}

function onCardUpdateBasis(rowId: string, field: string, value: string) {
  updateBasisRow(rowId, field, value)
}

function onCardUpdateQA(rowId: string, questionIdx: number, answer: 'Y' | 'N' | '') {
  const colIdx = basisRows.value.findIndex((r) => r.rowId === rowId)
  if (colIdx >= 0) updateQACell(questionIdx, colIdx, answer)
}
</script>

<template>
  <div class="d1-tab-business-mode">
    <div class="tab-header">
      <h4>应收票据业务模式分析 D1-6</h4>
      <GtReviewTrigger section-id="D1-business-mode-header" />
    </div>

    <details class="business-reference-collapse" open>
      <summary class="business-reference-summary">📌 业务模式分析参考（核心指引）</summary>
      <div class="business-reference-body">
        <h5 class="business-reference-heading">{{ BUSINESS_MODE_REFERENCE.heading }}</h5>
        <ol class="business-reference-list">
          <li v-for="(item, i) in BUSINESS_MODE_REFERENCE.principles" :key="'bp-' + i">{{ item }}</li>
        </ol>
        <div
          v-for="(group, gi) in BUSINESS_MODE_REFERENCE.checks"
          :key="'bc-' + gi"
          class="business-reference-group"
        >
          <p class="business-reference-group-title">{{ group.title }}</p>
          <ul class="business-reference-group-list">
            <li v-for="(line, li) in group.items" :key="'bcl-' + gi + '-' + li">{{ line }}</li>
          </ul>
        </div>
      </div>
    </details>

    <!-- 一、审计目标 + 二、审计过程 -->
    <details class="methodology-collapse" open>
      <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
      <div class="methodology-body">
        <p class="method-title"><strong>一、审计目标：</strong></p>
        <ol class="method-objectives">
          <li v-for="(item, i) in AUDIT_OBJECTIVES" :key="'obj-' + i">{{ item }}</li>
        </ol>
        <div class="method-title-row">
          <p class="method-title"><strong>二、审计过程：</strong></p>
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计过程' : 'AI服务暂不可用'" placement="top">
            <el-button
              size="small"
              :loading="aiLoadingProcedures"
              :disabled="isReadonly || !aiAvailable"
              @click="generateAuditProceduresWithAI"
            >
              🤖 AI
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :model-value="auditProcedures"
          placeholder="请记录执行的审计程序，如：1. 了解管理层对应收票据组合的业务模式……"
          :disabled="isReadonly"
          @input="(v: string) => saveAuditProcedures(v)"
        />
      </div>
    </details>

    <div class="table-toolbar">
      <el-segmented v-model="viewMode" :options="viewModeOptions" size="small" />
      <el-button-group size="small">
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="onImportFile"
          style="display:inline-block"
        >
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <details class="prep-hint-collapse">
      <summary class="prep-hint-summary">编制提示（导入导出与填写注意事项）</summary>
      <ul class="prep-hint-list">
        <li v-for="(hint, i) in PREP_HINTS" :key="'prep-' + i">{{ hint }}</li>
      </ul>
    </details>

    <!-- 卡片视图 -->
    <template v-if="viewMode === 'card'">
      <div class="overview-panel">
        <el-progress
          type="circle"
          :percentage="Math.round((completedComboCount / basisRows.length) * 100)"
          :width="56"
          :stroke-width="5"
          :color="completedComboCount === basisRows.length ? '#67c23a' : '#e6a23c'"
        />
        <div class="overview-info">
          <h3 class="overview-title">
            业务模式分析
            <el-tag size="small" effect="plain" class="overview-code">D1-6</el-tag>
          </h3>
          <p class="overview-desc">
            共 <strong>{{ basisRows.length }}</strong> 个票据组合，
            已完成判定 <strong>{{ judgmentCompleteCount }}</strong> 个，
            依据+QA 齐备 <strong>{{ completedComboCount }}</strong> 个
          </p>
        </div>
      </div>

      <el-tabs v-model="activeTab" type="card">
        <el-tab-pane
          v-for="(row, colIdx) in basisRows"
          :key="row.rowId"
          :name="row.rowId"
          :label="TAB_LABELS[row.rowId] || row.combinationName"
        >
          <D1BusinessModeCard
            :row="row"
            :column-index="colIdx"
            :qa-matrix="qaMatrix"
            :business-mode-result="businessModeResults[colIdx]"
            :report-item-result="reportItemResults[colIdx]"
            :business-mode-options="BUSINESS_MODE_OPTIONS"
            :is-readonly="isReadonly"
            :project-id="projectId"
            @update-basis="(field, value) => onCardUpdateBasis(row.rowId, field, value)"
            @update-qa="(qIdx, answer) => onCardUpdateQA(row.rowId, qIdx, answer)"
          />
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 矩阵视图 -->
    <D1BusinessModeMatrix
      v-else
      :basis-rows="basisRows"
      :qa-matrix="qaMatrix"
      :business-mode-results="businessModeResults"
      :report-item-results="reportItemResults"
      :business-mode-options="BUSINESS_MODE_OPTIONS"
      :is-readonly="isReadonly"
      :project-id="projectId"
      @update-basis="updateBasisRow"
      @update-qa="updateQACell"
      @cell-contextmenu="onCellContextMenu"
    />

    <!-- 编制参考提示（模板底部提示1/2/监管参考） -->
    <details class="guidance-reference">
      <summary class="guidance-reference-summary">📋 编制参考提示（终止确认与组合层次判断）</summary>
      <div
        v-for="(section, si) in GUIDANCE_SECTIONS"
        :key="'guide-' + si"
        class="guidance-block"
      >
        <p class="guidance-block-title">{{ section.title }}</p>
        <p
          v-for="(para, pi) in section.paragraphs"
          :key="'gp-' + si + '-' + pi"
          class="guidance-paragraph"
        >
          {{ para }}
        </p>
      </div>
    </details>

    <!-- 三、审计说明 + 四、审计结论 -->
    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计意见区</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D1-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:D1-7" :context-project-id="projectId" />
            <GtIndexChip value="wp:D1-8" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <div class="opinion-body">
        <div class="opinion-field">
          <label>三、审计说明</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :model-value="auditNote"
            placeholder="请输入审计说明..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditNote(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingNote"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditNoteWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-bm-note')">💬 复核</el-button>
          </div>
        </div>
        <div class="opinion-field">
          <label>四、审计结论</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :model-value="auditConclusion"
            placeholder="请输入审计结论..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditConclusion(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingConclusion"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditConclusionWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-bm-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d1-tab-business-mode {
  width: 100%;
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.overview-panel {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  background: linear-gradient(135deg, #f0f7ff 0%, #eaf4ff 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  border: 1px solid #d9ecff;
}

.overview-info {
  flex: 1;
  min-width: 0;
}

.overview-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-code {
  font-size: 11px;
  color: #409eff;
  border-color: #b3d8ff;
  background: #fff;
}

.overview-desc {
  margin: 0;
  font-size: 13px;
  color: #606266;
}

.overview-desc strong {
  color: #303133;
}

.methodology-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.business-reference-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f5f9ff;
}

.business-reference-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #337ecc;
}

.business-reference-body {
  padding: 8px 14px 12px;
  font-size: 13px;
  color: #303133;
  line-height: 1.75;
}

.business-reference-heading {
  margin: 0 0 6px;
  font-size: 13px;
}

.business-reference-list {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.business-reference-group {
  margin-top: 10px;
}

.business-reference-group-title {
  margin: 0 0 4px;
  font-weight: 600;
  color: #303133;
}

.business-reference-group-list {
  margin: 0 0 0 1.2em;
  padding: 0;
  color: #606266;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.method-title {
  margin: 8px 0 4px;
  font-size: 13px;
}

.method-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
}

.method-title-row .method-title {
  margin: 0;
}

.method-objectives {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.prep-hint-collapse {
  margin-bottom: 12px;
  border-radius: 6px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f0f7ff;
}

.prep-hint-summary {
  cursor: pointer;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: #337ecc;
}

.prep-hint-list {
  margin: 0 0 8px;
  padding: 0 12px 8px 28px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}

.guidance-reference {
  margin: 16px 0;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  border-left: 3px solid #909399;
  background: #fafafa;
  padding: 0 12px 10px;
}

.guidance-reference-summary {
  cursor: pointer;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.guidance-block {
  margin-bottom: 12px;
}

.guidance-block-title {
  margin: 0 0 6px;
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}

.guidance-paragraph {
  margin: 4px 0;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}

.audit-opinion-card {
  margin-top: 16px;
  border: 1px solid #ebeef5;
}

.opinion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.opinion-title {
  font-weight: 600;
  font-size: 14px;
}

.opinion-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.opinion-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.opinion-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  font-size: 13px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
