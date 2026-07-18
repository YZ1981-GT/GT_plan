<template>
  <div class="f2-val-sheet f2-spe-impairment f2-soft-matrix">
    <header class="sheet-header">
      <div>
        <h3>合同履约成本减值准备测算表</h3>
        <span class="code">F2-57</span>
      </div>
      <div class="stat-row">
        <span class="stat">账面价值 {{ fmt(imp.columnTotals.value.bookValue) }}</span>
        <span class="stat sub">测算计提/转回 {{ fmt(imp.columnTotals.value.measuredProvision) }}</span>
        <span class="stat sub">差异合计 {{ fmt(imp.columnTotals.value.difference) }}</span>
        <el-tag v-if="imp.impairedCount.value" type="warning" size="small">
          减值 {{ imp.impairedCount.value }} 项
        </el-tag>
        <el-tag v-if="imp.diffCount.value" type="danger" size="small">
          差异 {{ imp.diffCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p v-for="(tip, i) in tips" :key="i">{{ i + 1 }}. {{ tip }}</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addProject()">+ 项目</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-57"
          :disabled="isReadonly"
          review-section="F2-57-impairment"
        />
        <GtIndexChip value="wp:F2-57" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ filledCount }} 个项目</el-tag>
      </div>
    </div>

    <div v-if="projectId && wpId" class="evidence-panel">
      <h4>减值测算附件</h4>
      <p>上传可收回金额测算、合同预计收入成本等支持性资料。</p>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="F2-57"
        :item-index="1"
        accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
      />
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th class="sticky col-code">项目编码</th>
            <th class="sticky col-name">项目名称</th>
            <th>账面余额</th>
            <th>已计提<br>减值准备</th>
            <th class="calc-col">账面价值</th>
            <th>转让相关商品<br>预期剩余对价</th>
            <th>转让估计<br>将发生成本</th>
            <th class="calc-col">转让对价净额</th>
            <th class="calc-col">是否<br>发生减值</th>
            <th class="calc-col">测算计提<br>或转回金额</th>
            <th>企业账面<br>减值准备</th>
            <th class="calc-col">差异金额</th>
            <th class="col-remark">备注</th>
            <th class="col-act" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in imp.enrichedProjects.value"
            :key="row.id"
            :class="{ 'row-warn': row.highlight }"
          >
            <td class="sticky col-code">
              <el-input v-if="!isReadonly" :model-value="row.projectCode" size="small"
                @update:model-value="(v: string) => imp.updateProject(row.id, { projectCode: v })" />
              <span v-else>{{ row.projectCode || '—' }}</span>
            </td>
            <td class="sticky col-name">
              <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
                @update:model-value="(v: string) => imp.updateProject(row.id, { projectName: v })" />
              <span v-else>{{ row.projectName || '—' }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" size="small" :controls="false"
                class="compact-num wide"
                @change="(v: number | undefined) => imp.updateProject(row.id, { bookBalance: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.bookBalance) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.accumulatedProvision" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => imp.updateProject(row.id, { accumulatedProvision: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.accumulatedProvision) }}</span>
            </td>
            <td class="auto calc calc-col">{{ fmt(row.bookValue) }}</td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.remainingConsideration" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => imp.updateProject(row.id, { remainingConsideration: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.remainingConsideration) }}</span>
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.estimatedFutureCosts" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => imp.updateProject(row.id, { estimatedFutureCosts: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.estimatedFutureCosts) }}</span>
            </td>
            <td class="auto calc calc-col">{{ fmt(row.netRealizableValue) }}</td>
            <td class="calc-col" :class="{ 'abn-yes': row.isImpaired === '是' }">
              {{ row.isImpaired || '—' }}
            </td>
            <td class="auto calc calc-col" :class="{ 'neg': row.measuredProvision < 0 }">
              {{ fmtSigned(row.measuredProvision) }}
            </td>
            <td>
              <el-input-number v-if="!isReadonly" :model-value="row.companyRecordedProvision" size="small"
                :controls="false" class="compact-num wide"
                @change="(v: number | undefined) => imp.updateProject(row.id, { companyRecordedProvision: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.companyRecordedProvision) }}</span>
            </td>
            <td class="auto calc calc-col" :class="{ 'diff-warn': row.hasDifference }">
              {{ fmtSigned(row.difference) }}
            </td>
            <td class="col-remark">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @update:model-value="(v: string) => imp.updateProject(row.id, { remark: v })" />
              <span v-else class="remark-text">{{ row.remark || '—' }}</span>
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="imp.removeProject(row.id)">删</el-button>
            </td>
          </tr>

          <tr class="row-total">
            <td colspan="2" class="sticky col-name">合计</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.bookBalance) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.accumulatedProvision) }}</td>
            <td class="auto calc">{{ fmt(imp.columnTotals.value.bookValue) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.remainingConsideration) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.estimatedFutureCosts) }}</td>
            <td class="auto calc">{{ fmt(imp.columnTotals.value.netRealizableValue) }}</td>
            <td />
            <td class="auto calc">{{ fmtSigned(imp.columnTotals.value.measuredProvision) }}</td>
            <td class="auto">{{ fmt(imp.columnTotals.value.companyRecordedProvision) }}</td>
            <td class="auto calc" :class="{ 'diff-warn': Math.abs(imp.columnTotals.value.difference) > 0.01 }">
              {{ fmtSigned(imp.columnTotals.value.difference) }}
            </td>
            <td colspan="2" />
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('contract-impairment-note')">AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="imp.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="说明减值测算方法、管理层计提充分性判断及差异处理…" :disabled="isReadonly" />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('contract-impairment-conclusion')">AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        :disabled="isReadonly" @update:model-value="saveAuditConclusion" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2Impairment } from '../../composables/useF2Impairment'
import {
  F2_57_OBJECTIVE,
  F2_57_TIPS,
  isBlankImpairmentProject,
} from '../../composables/useF2ContractCostImpairmentFormulas'
import {
  useF2SpecialAiGenerate,
  type F2SpeAiSection,
} from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const imp = useF2Impairment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_57_OBJECTIVE
const tips = F2_57_TIPS

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)
const filledCount = computed(() =>
  imp.sheet.value.projects.filter((row) => !isBlankImpairmentProject(row)).length,
)

const CONCLUSION_KEY = 'F2-57-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-57',
    projectCount: filledCount.value,
    bookBalanceTotal: imp.columnTotals.value.bookBalance,
    accumulatedProvisionTotal: imp.columnTotals.value.accumulatedProvision,
    bookValueTotal: imp.columnTotals.value.bookValue,
    netRealizableValueTotal: imp.columnTotals.value.netRealizableValue,
    measuredProvisionTotal: imp.columnTotals.value.measuredProvision,
    companyRecordedProvisionTotal: imp.columnTotals.value.companyRecordedProvision,
    differenceTotal: imp.columnTotals.value.difference,
    impairedCount: imp.impairedCount.value,
    differenceCount: imp.diffCount.value,
    projects: imp.enrichedProjects.value
      .filter((row) => !isBlankImpairmentProject(row))
      .slice(0, 30)
      .map((row) => ({
        projectCode: row.projectCode,
        projectName: row.projectName,
        bookValue: row.bookValue,
        netRealizableValue: row.netRealizableValue,
        isImpaired: row.isImpaired,
        measuredProvision: row.measuredProvision,
        companyRecordedProvision: row.companyRecordedProvision,
        difference: row.difference,
        remark: row.remark,
      })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'contract-impairment-note'
  const existing = isNote ? imp.auditNote.value : auditConclusion.value
  const title = isNote
    ? 'AI 生成 · 减值测算审计说明'
    : 'AI 生成 · 减值测算审计结论'
  const text = await generateAndConfirm(section, existing || '', aiContext(), title)
  if (!text) return
  if (isNote) imp.auditNote.value = text
  else saveAuditConclusion(text)
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtSigned(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  const s = v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v > 0 ? s : `(${s.replace('-', '')})`
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2SoftMatrixStyles.css"></style>
<style scoped>
.f2-spe-impairment { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
  min-width: 1280px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 4px 4px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
  white-space: nowrap;
  font-size: 10px;
  line-height: 1.3;
}
.matrix-table th.calc-col { background: #6b4d8f; }

.sticky { position: sticky; z-index: 3; background: #faf8fc !important; }
.matrix-table thead th.sticky { background: var(--gt-purple) !important; color: #fff; z-index: 4; }
.col-code { left: 0; min-width: 72px; }
.col-name {
  left: 72px;
  min-width: 100px;
  text-align: left !important;
  padding-left: 4px !important;
  box-shadow: 2px 0 4px rgba(75, 45, 119, 0.08);
}
.col-remark { min-width: 80px; }
.col-act { width: 36px; position: sticky; right: 0; z-index: 3; background: #fff !important; }

.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.row-warn td { background: #fdf6ec !important; }
.auto { text-align: right; padding-right: 2px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { color: #4b2d77; font-weight: 500; background: #faf8fc !important; }
.abn-yes { color: #c45656; font-weight: 600; }
.neg { color: #67c23a; }
.diff-warn { color: #c45656; font-weight: 600; }
.remark-text { font-size: 10px; color: #909399; }

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 80px; }
:deep(.compact-num.wide) { width: 96px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 11px; }
</style>
