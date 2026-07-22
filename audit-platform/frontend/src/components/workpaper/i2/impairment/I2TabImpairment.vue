<template>
  <div class="i2-impairment">
    <div class="methodology-block">
      <p>
        <strong>编制逻辑（CAS6/CAS8，对齐致同 I2-15）：</strong>
        识别减值迹象① → 判定是否测试 → ②账面价值 → ③公允净额 / ④DCF现值（I2-16）
        → ⑤=MAX(③,④) → ⑥=MAX(②−⑤,0) → ⑧=⑥−⑦（正=补提，负=冲回）。
      </p>
      <p class="methodology-note">
        审计目标：检查期末开发支出计提的减值准备是否合理。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：检查期末开发支出计提的减值准备是否合理；比较账面价值与可收回金额，确认应补提或冲回金额。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:I2-15" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ impairmentRows.length }} 行</el-tag>
        <el-tag v-if="impairmentSummary.totalSupplement > 0" type="danger" size="small">
          应补提 {{ fmtNum(impairmentSummary.totalSupplement) }}
        </el-tag>
        <el-tag v-if="impairmentSummary.totalReversal > 0" type="warning" size="small">
          应冲回 {{ fmtNum(impairmentSummary.totalReversal) }}
        </el-tag>
        <el-tag v-if="!prepValidation.ok" type="danger" size="small">
          编制校验 {{ prepValidation.messages.length }} 项
        </el-tag>
        <el-tag v-if="missingRecoverableRows.length" type="danger" size="small">
          缺 I2-16 {{ missingRecoverableRows.length }}
        </el-tag>
        <el-tag v-if="staleSyncCount" type="warning" size="small">
          与 I2-16 不一致 {{ staleSyncCount }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:I2-16" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert
      v-if="missingRecoverableRows.length"
      type="error"
      :closable="false"
      show-icon
      class="mb-8"
      :title="`须测试闸门：${missingRecoverableRows.length} 项须完成 I2-16 可收回测算`"
      :description="`待测：${missingRecoverableRows.map(r => r.name).filter(Boolean).slice(0, 6).join('、')}${missingRecoverableRows.length > 6 ? '…' : ''}。请点「建 I2-16 测算组」后完成测算并回填。`"
    />

    <div class="section-header">
      <span class="section-title">二、审计过程 — I2-15 减值准备测试表</span>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleSeedFromDetail">从 I2-2 带入②⑦</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleSeedI16">建 I2-16 测算组</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleLinkFromI16">回填 I2-16(③④)</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
        <el-button size="small" type="info" plain @click="emit('navigate-sheet', 'I2-16')">→ I2-16</el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePublishSupplement">推送补提</el-button>
        <el-button size="small" @click="handleExportExcel">导出 Excel</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="!prepValidation.ok"
      type="warning"
      :closable="false"
      show-icon
      class="mb-8"
      :title="prepValidation.messages[0]"
      :description="prepValidation.messages.slice(1).join('；') || undefined"
    />

    <el-table
      :data="impairmentRows"
      border
      stripe
      size="small"
      class="impairment-table"
      max-height="520"
      :row-class-name="rowClassName"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column type="index" label="#" width="40" align="center" fixed />

      <el-table-column prop="name" label="开发支出项目名称" min-width="140" fixed>
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.name"
            size="small"
            placeholder="项目名称"
            @update:model-value="(v: string) => updateImpairmentField($index, 'name', v)"
          />
          <span v-else>{{ row.name || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="有迹象" width="88" align="center">
        <template #header>
          <el-tooltip content="是否存在减值迹象" placement="top">
            <span>有迹象</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.hasIndication"
            size="small"
            style="width:100%"
            @change="(v: string) => updateImpairmentField($index, 'hasIndication', v)"
          >
            <el-option label="√ 有" value="Y" />
            <el-option label="× 无" value="N" />
            <el-option label="—" value="" />
          </el-select>
          <span v-else>{{ ynLabel(row.hasIndication) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="①迹象描述" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indicationDesc"
            size="small"
            :disabled="row.hasIndication !== 'Y'"
            placeholder="描述迹象"
            @update:model-value="(v: string) => updateImpairmentField($index, 'indicationDesc', v)"
          />
          <span v-else>{{ row.indicationDesc || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="须测试" width="72" align="center">
        <template #header>
          <el-tooltip content="是否进行减值测试；有迹象时自动为「是」" placement="top">
            <span class="formula-header">须测试</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.needTest ? 'Y' : 'N'"
            size="small"
            style="width:100%"
            @change="(v: string) => updateImpairmentField($index, 'needTest', v === 'Y')"
          >
            <el-option label="是" value="Y" />
            <el-option label="否" value="N" />
          </el-select>
          <el-tag v-else :type="row.needTest ? 'warning' : 'info'" size="small">
            {{ row.needTest ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="②账面价值" width="110" align="right">
        <template #header>
          <el-tooltip content="资本化期末−摊销（不含减值），可自 I2-2 带入" placement="top">
            <span class="formula-header">②账面价值</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.bookValue"
            size="small"
            :controls="false"
            :precision="2"
            class="amt-input"
            @change="(v: number | undefined) => updateImpairmentField($index, 'bookValue', v ?? 0)"
          />
          <span v-else>{{ fmtNum(row.bookValue) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="③公允净额" width="110" align="right">
        <template #header>
          <el-tooltip content="公允价值减去处置费用后的净额（I2-16）" placement="top">
            <span class="formula-header">③公允净额</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly && !row.linkedToDcf"
            :model-value="row.fairValueLessDisposal"
            size="small"
            :controls="false"
            :precision="2"
            class="amt-input"
            :disabled="!row.needTest"
            @change="(v: number | undefined) => updateImpairmentField($index, 'fairValueLessDisposal', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.fairValueLessDisposal) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="④DCF现值" width="110" align="right">
        <template #header>
          <el-tooltip content="预计未来现金流量的现值（I2-16）" placement="top">
            <span class="formula-header">④DCF现值</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly && !row.linkedToDcf"
            :model-value="row.dcfValue"
            size="small"
            :controls="false"
            :precision="2"
            class="amt-input"
            :disabled="!row.needTest"
            @change="(v: number | undefined) => updateImpairmentField($index, 'dcfValue', v ?? 0)"
          />
          <span v-else class="formula-cell">{{ fmtNum(row.dcfValue) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="⑤可收回" width="100" align="right">
        <template #header>
          <el-tooltip content="⑤=MAX(③,④)；无须测试时为 0" placement="top">
            <span class="formula-header">⑤可收回</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <div class="recoverable-cell">
            <span class="formula-cell" title="=MAX(③,④)">{{ fmtNum(row.recoverableAmount) }}</span>
            <el-tag v-if="row.linkedToDcf" type="info" size="small" class="dcf-tag">DCF</el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="⑥应计提" width="100" align="right">
        <template #header>
          <el-tooltip content="⑥=MAX(②−⑤,0)；当⑤&lt;②时计提" placement="top">
            <span class="formula-header">⑥应计提</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'text-danger': row.shouldProvision > 0.005 }" title="=MAX(②-⑤,0)">
            {{ fmtNum(row.shouldProvision) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="⑦已计提" width="100" align="right">
        <template #header>
          <el-tooltip content="期末账面已计提的减值准备（可自 I2-2 带入）" placement="top">
            <span>⑦已计提</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.alreadyProvided"
            size="small"
            :controls="false"
            :precision="2"
            class="amt-input"
            @change="(v: number | undefined) => updateImpairmentField($index, 'alreadyProvided', v ?? 0)"
          />
          <span v-else>{{ fmtNum(row.alreadyProvided) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="⑧补提/冲回" width="110" align="right">
        <template #header>
          <el-tooltip content="⑧=⑥−⑦；正=本期应补提，负=应冲回" placement="top">
            <span class="formula-header">⑧补提/冲回</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="['formula-cell', { 'text-danger': Math.abs(row.difference) > 0.005 }]"
            title="=⑥−⑦"
          >
            {{ fmtNum(row.difference) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="indexRef" label="索引号" min-width="90">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="如 I2-16"
            @update:model-value="(v: string) => updateImpairmentField($index, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="conclusion" label="结论" min-width="96">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.conclusion"
            size="small"
            style="width:100%"
            allow-create
            filterable
            @change="(v: string) => updateImpairmentField($index, 'conclusion', v)"
          >
            <el-option label="无需测试" value="无需测试" />
            <el-option label="无需计提" value="无需计提" />
            <el-option label="计提适当" value="计提适当" />
            <el-option label="需补提" value="需补提" />
            <el-option label="应冲回" value="应冲回" />
          </el-select>
          <span v-else>{{ row.conclusion || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="remark" label="备注" min-width="90">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @update:model-value="(v: string) => updateImpairmentField($index, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="removeImpairmentRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <details class="guidance-details">
      <summary>📋 编制提示（对齐 Excel 底栏 CAS1321）</summary>
      <div class="guidance-content">
        <p v-for="(hint, i) in procedureHints" :key="i">{{ i + 1 }}. {{ hint }}</p>
      </div>
    </details>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录迹象识别、可收回测算复核、⑧差异原因及处理..."
        @change="saveAuditNote"
      />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="fillAutoConclusion">生成草稿</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="经审计，期末开发支出减值准备在重大方面…"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef, ref, onMounted, watch, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Impairment } from '../../composables/useI2Impairment'
import { I2_15_PROCEDURE_HINTS, buildI2ImpairmentAdjustmentHint } from '../../composables/i2ImpairmentModel'
import { exportData } from '@/composables/useExcelIO'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const wpIdRef = toRef(props, 'wpId')
const allResponsesRef = toRef(props, 'allResponses')
const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const procedureHints = I2_15_PROCEDURE_HINTS

const {
  impairmentRows,
  impairmentSummary,
  prepValidation,
  missingRecoverableRows,
  staleSyncCount,
  highlightedRowIds,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
  seedFromDetail,
  seedRecoverableFromImpairment,
  linkRecoverableToImpairment,
  publishImpairmentToParent,
} = useI2Impairment(wpIdRef, allResponsesRef, {
  onSave: (itemId, value) => {
    props.saveResponse('I2-15', { [itemId]: JSON.stringify(value) })
  },
})

const AUDIT_NOTE_KEY = 'I2-15-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-15-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}
function hydrateAudit() {
  auditNote.value = readRemark(AUDIT_NOTE_KEY)
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}
function saveAuditNote(val: string) {
  auditNote.value = val
  void props.saveResponse('I2-15', { [AUDIT_NOTE_KEY]: val })
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-15', { [AUDIT_CONCLUSION_KEY]: val })
}
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(hydrateAudit)

function rowClassName({ row }: { row: any }) {
  return highlightedRowIds.value.has(row.rowId) ? 'diff-highlight-row' : ''
}

function ynLabel(v: string) {
  if (v === 'Y') return '√'
  if (v === 'N') return '×'
  return '—'
}

function fmtNum(v: number): string {
  return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getSummary({ columns }: { columns: any[] }) {
  const s = impairmentSummary.value
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const map: Record<string, number> = {
      bookValue: s.totalBookValue,
      fairValueLessDisposal: s.totalFairValue,
      dcfValue: s.totalDcf,
      recoverableAmount: s.totalRecoverable,
      shouldProvision: s.totalShouldProvision,
      alreadyProvided: s.totalAlreadyProvided,
      difference: s.totalDifference,
    }
    const key = col.property
    if (key && map[key] != null) return fmtNum(map[key])
    // 按 label 匹配无 property 的公式列
    const label = String(col.label || '')
    if (label.includes('②')) return fmtNum(s.totalBookValue)
    if (label.includes('③')) return fmtNum(s.totalFairValue)
    if (label.includes('④')) return fmtNum(s.totalDcf)
    if (label.includes('⑤')) return fmtNum(s.totalRecoverable)
    if (label.includes('⑥')) return fmtNum(s.totalShouldProvision)
    if (label.includes('⑦')) return fmtNum(s.totalAlreadyProvided)
    if (label.includes('⑧')) return fmtNum(s.totalDifference)
    return ''
  })
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入开发支出项目名称', '新增减值测试行', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (value?.trim()) {
      addImpairmentRow({ name: value.trim() })
      ElMessage.success(`已添加：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

function handleSeedFromDetail() {
  const r = seedFromDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSeedI16() {
  const r = seedRecoverableFromImpairment()
  if (r.ok) {
    ElMessage.success(r.message)
    emit('navigate-sheet', 'I2-16')
  } else {
    ElMessage.warning(r.message)
  }
}

function handleLinkFromI16() {
  const r = linkRecoverableToImpairment(false)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

async function handleSave() {
  await props.saveResponse('I2-15', { 'I2-15-rows': JSON.stringify(impairmentRows.value) })
  const r = publishImpairmentToParent()
  await maybeAppendAdjustmentHint()
  emit('save')
  ElMessage.success(r.message)
}

/** 补提金额显著时，将调整分录提示追加进审计说明（若尚未记录过） */
async function maybeAppendAdjustmentHint(): Promise<void> {
  const hint = buildI2ImpairmentAdjustmentHint(impairmentSummary.value.totalSupplement)
  if (!hint) return
  if (auditNote.value.includes('建议调整分录')) return
  const merged = auditNote.value ? `${auditNote.value}\n${hint}` : hint
  auditNote.value = merged
  await props.saveResponse('I2-15', { [AUDIT_NOTE_KEY]: merged })
}

function handlePublishSupplement() {
  const r = publishImpairmentToParent()
  if (r.supplement > 0.005) ElMessage.warning(r.message)
  else ElMessage.success(r.message)
}

async function handleExportExcel() {
  const rows = impairmentRows.value.map((r) => ({
    name: r.name,
    hasIndication: ynLabel(r.hasIndication),
    indicationDesc: r.indicationDesc,
    needTest: r.needTest ? '是' : '否',
    bookValue: r.bookValue,
    fairValueLessDisposal: r.fairValueLessDisposal,
    dcfValue: r.dcfValue,
    recoverableAmount: r.recoverableAmount,
    shouldProvision: r.shouldProvision,
    alreadyProvided: r.alreadyProvided,
    difference: r.difference,
    indexRef: r.indexRef,
    conclusion: r.conclusion,
    remark: r.remark,
  }))
  await exportData({
    data: rows,
    columns: [
      { key: 'name', header: '开发支出项目名称' },
      { key: 'hasIndication', header: '有迹象' },
      { key: 'indicationDesc', header: '①迹象描述' },
      { key: 'needTest', header: '须测试' },
      { key: 'bookValue', header: '②账面价值' },
      { key: 'fairValueLessDisposal', header: '③公允净额' },
      { key: 'dcfValue', header: '④DCF现值' },
      { key: 'recoverableAmount', header: '⑤可收回' },
      { key: 'shouldProvision', header: '⑥应计提' },
      { key: 'alreadyProvided', header: '⑦已计提' },
      { key: 'difference', header: '⑧补提/冲回' },
      { key: 'indexRef', header: '索引号' },
      { key: 'conclusion', header: '结论' },
      { key: 'remark', header: '备注' },
    ],
    sheetName: 'I2-15减值测试',
    fileName: `I2-15减值准备测试表_${projectId.value || ''}.xlsx`,
    numericColumnKeys: ['bookValue', 'fairValueLessDisposal', 'dcfValue', 'recoverableAmount', 'shouldProvision', 'alreadyProvided', 'difference'],
  })
}

function fillAutoConclusion() {
  const s = impairmentSummary.value
  const n = impairmentRows.value.length
  const tested = impairmentRows.value.filter((r) => r.needTest).length
  const draft = [
    `经审计：共检查开发支出项目 ${n} 项，其中须减值测试 ${tested} 项。`,
    s.totalSupplement > 0.005
      ? `本期应补提减值准备合计 ${fmtNum(s.totalSupplement)} 元；`
      : '本期无需补提减值准备；',
    s.totalReversal > 0.005
      ? `应冲回 ${fmtNum(s.totalReversal)} 元（按事务所模板⑧列，请结合 CAS8 评估冲回是否适用）；`
      : '',
    Math.abs(s.totalDifference) < 0.005
      ? '期末开发支出减值准备在重大方面计提适当。'
      : '上述⑧差异尚需关注并完成调整/说明。',
  ].filter(Boolean).join('')
  auditConclusion.value = draft
  saveAuditConclusion(draft)
  ElMessage.success('已生成审计结论草稿')
}

function handleReview() { openReviewDialog('I2-15-减值准备测试') }
</script>

<style scoped>
.i2-impairment { font-size: var(--wp-font-size, 13px); padding: 16px; }
.methodology-block {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.65;
}
.methodology-block p { margin: 0 0 4px; }
.methodology-note { opacity: 0.9; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right, .section-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; gap: 8px; flex-wrap: wrap; }
.section-title { font-size: 14px; font-weight: 600; color: #1f2937; }
.formula-header { border-bottom: 1px dashed #a5b4fc; cursor: help; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.text-danger { color: #dc2626 !important; font-weight: 700; }
.recoverable-cell { display: flex; align-items: center; justify-content: flex-end; gap: 4px; }
.dcf-tag { flex-shrink: 0; }
.amt-input { width: 100%; }
.mb-8 { margin-bottom: 8px; }
.guidance-details {
  margin: 12px 0; font-size: 12px; color: var(--el-text-color-secondary);
  background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-content p { margin: 0 0 4px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.diff-highlight-row) { background-color: #fef2f2 !important; }
:deep(.diff-highlight-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table .cell) { line-height: 1.35; }
</style>
