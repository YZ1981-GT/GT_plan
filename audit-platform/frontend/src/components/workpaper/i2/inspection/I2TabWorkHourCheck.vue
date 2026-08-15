<template>
  <div class="i2-workhour-check">
    <div class="section-header">
      <span class="section-title">I2-10 研发人员工时检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I2_WORKHOUR_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        按「项目 → 人员 → 工时 → 分配依据 → 薪酬计提」核查研发人工归集；
        非全时人员须用同期总工时计算占比，验证分摊合理性；与 I2-9 认定结论交叉印证；
        含股份支付的须说明分摊基础。检查要素可按实际情况增减。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-10" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-9" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ summary.totalCount }} 行</el-tag>
        <el-tag size="small" type="info">工时 {{ fmtNum(summary.totalHours, 1) }}h</el-tag>
        <el-tag size="small" type="info">薪酬 {{ fmtAmt(summary.totalSalary) }}</el-tag>
        <el-tag v-if="summary.highRatioCount" size="small" type="danger">占比偏高 {{ summary.highRatioCount }}</el-tag>
        <el-tag v-if="summary.lowRatioCount" size="small" type="warning">占比偏低 {{ summary.lowRatioCount }}</el-tag>
        <el-tag v-if="summary.missingBasisCount" size="small" type="warning">缺依据 {{ summary.missingBasisCount }}</el-tag>
        <el-tag v-if="summary.sharePayCount" size="small" type="warning">股份支付 {{ summary.sharePayCount }}</el-tag>
        <el-tag v-if="!workHourGate.ok" size="small" type="danger">闸门失败 {{ workHourGate.messages.length }}</el-tag>
        <el-tag :type="reconcileResult.ok ? 'success' : 'danger'" size="small" :title="reconcileResult.message">
          薪酬勾稽{{ reconcileResult.ok ? '一致' : '不一致' }}
        </el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-9')">← I2-9</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-11')">I2-11 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="!workHourGate.ok"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`I2-9 ↔ I2-10 硬闸门校验失败：${workHourGate.messages.length} 项`"
      :description="workHourGate.messages.slice(0, 6).join('；') + (workHourGate.messages.length > 6 ? '…' : '')"
    />
    <el-alert
      v-if="!prepValidation.ok"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="prepValidation.messages[0]"
      :description="prepValidation.messages.slice(1).join('；') || undefined"
    />
    <el-alert
      v-else-if="summary.abnormalCount || summary.sharePayCount"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="riskHint"
    />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程 — 工时与薪酬分摊检查</span>
          <div class="title-actions">
            <el-segmented
              v-model="columnViewMode"
              :options="[
                { label: '精简', value: 'compact' },
                { label: '完整', value: 'full' },
              ]"
              size="small"
            />
            <el-button size="small" :disabled="isReadonly" @click="handleSeedFromStaff">从 I2-9 带入</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleSeedFromDetail">从 I2-2 带入项目</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" :disabled="isReadonly" @click="applyAllSuggestions">采纳建议结论</el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleSampling">抽凭引擎</el-button>
            <el-button size="small" @click="handleExportExcel">导出 Excel</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="focus-tip"
        title="核对重点：工时是否有分配依据；研发工时≤同期总工时；薪酬与工时勾稽；兼职人员占比是否合理；股份支付分摊是否清晰。【检查要素可按实际情况增减】"
      />

      <el-table
        :data="rows"
        border
        size="small"
        class="check-table"
        max-height="520"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="序号" width="50" fixed align="center" />

        <el-table-column prop="projectName" label="项目名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectName" size="small" placeholder="项目" />
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="projectCode" label="项目号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectCode" size="small" />
            <span v-else>{{ row.projectCode || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="projectPeriod" label="项目起止时间" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectPeriod" size="small" placeholder="如 2024.01-2024.12" />
            <span v-else>{{ row.projectPeriod || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="staffName" label="研发人员姓名" min-width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.staffName" size="small" @change="onRowChange(row)" />
            <span v-else>{{ row.staffName || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="month" label="月份" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.month"
              type="month"
              size="small"
              value-format="YYYY-MM"
              placeholder="月份"
              style="width:100%"
            />
            <span v-else>{{ row.month || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="hours" label="研发工时" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.hours"
              size="small"
              :controls="false"
              :precision="1"
              style="width:100%"
              @change="onRowChange(row)"
            />
            <span v-else>{{ fmtNum(row.hours, 1) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="totalHours" label="同期总工时" width="100" align="right">
          <template #header>
            <el-tooltip content="非全时人员分功能统计用；占比=研发工时/同期总工时" placement="top">
              <span class="formula-header">同期总工时</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.totalHours"
              size="small"
              :controls="false"
              :precision="1"
              style="width:100%"
              @change="onRowChange(row)"
            />
            <span v-else>{{ fmtNum(row.totalHours, 1) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="ratio" label="占比" width="72" align="right">
          <template #header>
            <el-tooltip content="=研发工时/同期总工时" placement="top">
              <span class="formula-header">占比</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'text-danger': row.ratio >= 0.95 || (row.totalHours > 0 && row.hours > row.totalHours) }"
              :title="`${row.hours}/${row.totalHours}`"
            >
              {{ fmtPercent(row.ratio) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="allocationBasis" label="工时分配依据" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.allocationBasis"
              size="small"
              filterable
              allow-create
              clearable
              style="width:100%"
              @change="onRowChange(row)"
            >
              <el-option v-for="b in I2_WORKHOUR_BASIS_OPTIONS" :key="b" :label="b" :value="b" />
            </el-select>
            <span v-else>{{ row.allocationBasis || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="salaryAccrual" label="研发薪酬计提" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.salaryAccrual"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="onRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.salaryAccrual) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="hasShareBasedPay" label="股份支付" width="88" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.hasShareBasedPay"
              size="small"
              style="width:100%"
              @change="onRowChange(row)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
              <el-option label="—" value="" />
            </el-select>
            <span v-else>{{ row.hasShareBasedPay === 'Y' ? '是' : row.hasShareBasedPay === 'N' ? '否' : '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="customCheck" label="检查要素…" min-width="110">
          <template #header>
            <el-tooltip content="可按实际情况增减的检查要素" placement="top">
              <span>检查要素…</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.customCheck" size="small" placeholder="可选" />
            <span v-else>{{ row.customCheck || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="attachmentIndex" label="附件索引号" min-width="100">
          <template #default="{ row, $index }">
            <div class="attach-cell">
              <el-input v-if="!isReadonly" v-model="row.attachmentIndex" size="small" placeholder="索引" />
              <span v-else>{{ row.attachmentIndex || '—' }}</span>
              <el-button v-if="!isReadonly" size="small" text @click="handleOcr($index)">📎</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="conclusion" label="结论" min-width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.conclusion"
              size="small"
              style="width:100%"
            >
              <el-option v-for="c in I2_WORKHOUR_CONCLUSION_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <el-tag v-else size="small" :type="conclusionTagType(row.conclusion)">
              {{ row.conclusion || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" text @click="handleRemoveRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录工时抽查范围、分配依据复核、异常占比原因、股份支付分摊说明…"
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
        placeholder="经检查，研发人员工时分配及薪酬归集在重大方面…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="prep-notes" open>
      <summary>编制说明</summary>
      <ol>
        <li v-for="(n, i) in I2_WORKHOUR_PREP_NOTES" :key="i">{{ n }}</li>
      </ol>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 开发支出(1717) 工时检查" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1717"
        phase="final"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, inject, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { exportData } from '@/composables/useExcelIO'
import {
  I2_WORKHOUR_BASIS_OPTIONS,
  I2_WORKHOUR_CONCLUSION_OPTIONS,
  I2_WORKHOUR_OBJECTIVES,
  I2_WORKHOUR_PREP_NOTES,
  I2_WORKHOUR_STORAGE_KEY,
  I2_WORKHOUR_AUDIT_NOTE_KEY,
  I2_WORKHOUR_AUDIT_CONCLUSION_KEY,
  buildWorkHourConclusionDraft,
  emptyI2WorkHourRow,
  normalizeI2WorkHourRow,
  persistI2WorkHourRow,
  recomputeI2WorkHourRow,
  reconcileWorkHourSalaryVsAnalysis,
  seedWorkHourFromDetail,
  seedWorkHourFromStaff,
  suggestWorkHourConclusion,
  summarizeI2WorkHourRows,
  validateI2WorkHourPrep,
  validateWorkHourAgainstStaff,
  workHourRowRiskClass,
  type I2WorkHourCheckRow,
} from '../../composables/i2WorkHourModel'
import { I2_STAFF_STORAGE_KEY } from '../../composables/i2StaffCheckModel'
import {
  pickOcrField,
  runWorkpaperOcr,
  writeSheetCompletionMarker,
} from '../../composables/i2EnhancementHelpers'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// STORAGE_KEY 等常量集中定义于 i2WorkHourModel.ts / i2StaffCheckModel.ts（跨sheet引用共用，避免硬编码分裂）
const STORAGE_KEY = I2_WORKHOUR_STORAGE_KEY
const AUDIT_NOTE_KEY = I2_WORKHOUR_AUDIT_NOTE_KEY
const AUDIT_CONCLUSION_KEY = I2_WORKHOUR_AUDIT_CONCLUSION_KEY
const STAFF_KEY = I2_STAFF_STORAGE_KEY
const DETAIL_KEY = 'I2-2-rows'
const ANALYSIS_BUNDLE_KEY = 'I2-5-analysis-bundle'

const rows = ref<I2WorkHourCheckRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const columnViewMode = ref<'compact' | 'full'>('compact')
const isReadonly = computed(() => Boolean(props.isReadonly))
const samplingVisible = ref(false)
const tb6602 = ref<number | null>(null)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const summary = computed(() => summarizeI2WorkHourRows(rows.value))
const prepValidation = computed(() => validateI2WorkHourPrep(rows.value))

/** I2-9 ↔ I2-10 硬闸门：工时表人员须为 I2-9 已认定研发人员 */
const workHourGate = computed(() => validateWorkHourAgainstStaff(rows.value, parseRows(STAFF_KEY)))

/** I2-5 人工费本期数（人工费 currentAmount），供薪酬勾稽核对 */
const analysisLaborCurrent = computed(() => {
  try {
    const raw = props.allResponses.get(ANALYSIS_BUNDLE_KEY)
    if (!raw) return 0
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    const labor = (parsed?.compositionRows || []).find((r: any) => String(r.itemName || '').includes('人工'))
    return Number(labor?.currentAmount) || 0
  } catch {
    return 0
  }
})

const reconcileResult = computed(() =>
  reconcileWorkHourSalaryVsAnalysis(summary.value.totalSalary, analysisLaborCurrent.value, tb6602.value),
)

const riskHint = computed(() => {
  const parts: string[] = []
  if (summary.value.highRatioCount) parts.push(`工时占比偏高 ${summary.value.highRatioCount} 条`)
  if (summary.value.lowRatioCount) parts.push(`占比偏低 ${summary.value.lowRatioCount} 条`)
  if (summary.value.sharePayCount) parts.push(`含股份支付 ${summary.value.sharePayCount} 条`)
  return parts.length ? `关注：${parts.join('；')}，请核实分配依据与归集准确性。` : ''
})

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}

function parseRows(key: string): any[] {
  const raw = props.allResponses.get(key)
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string'
      ? JSON.parse(raw)
      : (raw.remark ? JSON.parse(raw.remark) : raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadData() {
  rows.value = parseRows(STORAGE_KEY).map(normalizeI2WorkHourRow)
}

function hydrateAudit() {
  auditNote.value = readRemark(AUDIT_NOTE_KEY)
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}

function saveAuditNote(val: string) {
  auditNote.value = val
  void props.saveResponse('I2-10', { [AUDIT_NOTE_KEY]: val })
}

function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-10', { [AUDIT_CONCLUSION_KEY]: val })
}

watch(() => props.allResponses, () => { loadData(); hydrateAudit() }, { immediate: true })
onMounted(() => {
  hydrateAudit()
  void _loadTb6602()
})

function onRowChange(row: I2WorkHourCheckRow) {
  const prevSuggested = row.suggestedConclusion
  const next = recomputeI2WorkHourRow(row, { refreshSuggested: false })
  Object.assign(row, next)
  row.suggestedConclusion = suggestWorkHourConclusion(row)
  if (!row.conclusion || row.conclusion === prevSuggested) {
    row.conclusion = row.suggestedConclusion
  }
}

function handleAddRow() {
  rows.value.push(emptyI2WorkHourRow())
}

function handleRemoveRow(index: number) {
  if (index < 0 || index >= rows.value.length) return
  rows.value.splice(index, 1)
}

function mergeSeeded(seeded: I2WorkHourCheckRow[], mode: 'staff' | 'detail') {
  if (!seeded.length) {
    ElMessage.warning(mode === 'staff' ? 'I2-9 无可带入人员（请先完成认定）' : 'I2-2 无项目明细可带入')
    return
  }
  const keyOf = (r: I2WorkHourCheckRow) =>
    `${(r.staffName || '').trim()}|${(r.projectName || '').trim()}|${(r.month || '').trim()}`
  const existing = new Set(rows.value.map(keyOf))
  let added = 0
  let updated = 0
  for (const s of seeded) {
    const key = keyOf(s)
    const hit = rows.value.find((r) => keyOf(r) === key)
    if (hit) {
      if (mode === 'detail') {
        hit.projectCode = s.projectCode || hit.projectCode
        hit.projectPeriod = s.projectPeriod || hit.projectPeriod
      }
      if (mode === 'staff' && !hit.hours && s.hours) {
        hit.hours = s.hours
        hit.totalHours = s.totalHours
        onRowChange(hit)
      }
      updated++
    } else if (!existing.has(key) || !s.staffName) {
      // detail 壳行允许同项目多名待填
      if (mode === 'detail' && rows.value.some((r) => r.projectName === s.projectName && !r.staffName)) {
        updated++
        continue
      }
      rows.value.push(s)
      existing.add(key)
      added++
    }
  }
  ElMessage.success(`已带入 ${added} 行` + (updated ? `，更新 ${updated} 行` : ''))
}

function handleSeedFromStaff() {
  mergeSeeded(seedWorkHourFromStaff(parseRows(STAFF_KEY)), 'staff')
}

function handleSeedFromDetail() {
  mergeSeeded(seedWorkHourFromDetail(parseRows(DETAIL_KEY)), 'detail')
}

function applyAllSuggestions() {
  for (const row of rows.value) {
    row.suggestedConclusion = suggestWorkHourConclusion(row)
    row.conclusion = row.suggestedConclusion
  }
  ElMessage.success('已按规则刷新全部结论')
}

async function handleSave() {
  const persist = rows.value.map(persistI2WorkHourRow)
  await props.saveResponse('I2-10', { [STORAGE_KEY]: JSON.stringify(persist) })
  const total = summary.value.totalCount
  const progress = total <= 0
    ? 10
    : Math.min(100, 30 + Math.round(((total - summary.value.missingBasisCount) / Math.max(total, 1)) * 70))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 'I2-10',
    progress,
    ok: prepValidation.value.ok && workHourGate.value.ok && total > 0 && summary.value.abnormalCount === 0,
    detail: {
      totalCount: total,
      abnormalCount: summary.value.abnormalCount,
      missingBasisCount: summary.value.missingBasisCount,
      gateOk: workHourGate.value.ok,
    },
  })
  emit('save')
  ElMessage.success('研发人员工时检查表已保存')
}

/** assertCanConclude 风格闸门校验：闸门失败或薪酬勾稽不一致时返回消息，供「生成草稿」等结论前置校验调用 */
function assertCanConclude(): { ok: boolean; messages: string[] } {
  const messages = [...workHourGate.value.messages]
  if (!reconcileResult.value.ok) messages.push(reconcileResult.value.message)
  return { ok: messages.length === 0, messages }
}

function fillAutoConclusion() {
  let draft = buildWorkHourConclusionDraft(summary.value)
  const gate = assertCanConclude()
  if (!gate.ok) {
    draft += `【闸门/勾稽警示】${gate.messages.join('；')}`
  }
  auditConclusion.value = draft
  saveAuditConclusion(draft)
  if (!gate.ok) {
    ElMessage.warning('已生成结论草稿，但存在闸门/勾稽异常，请核实后再定稿')
  } else {
    ElMessage.success('已生成审计结论草稿')
  }
}

/** 行级 OCR：上传领用/工时单据 → runWorkpaperOcr 回填 */
async function handleOcr(idx: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const fields = await runWorkpaperOcr(props.wpId, file)
      const name = pickOcrField(fields, 'name', 'staffName', 'personName')
      const project = pickOcrField(fields, 'projectName', 'project')
      const hours = pickOcrField(fields, 'hours', 'rdHours', 'workHours')
      const amount = pickOcrField(fields, 'amount', 'salary', 'salaryAccrual')
      await ElMessageBox.confirm(
        `OCR 识别结果：\n姓名: ${name || '-'}\n项目: ${project || '-'}\n工时: ${hours || '-'}\n薪酬: ${amount || '-'}\n\n确认填入第 ${idx + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const row = rows.value[idx]
      if (!row) return
      if (name) row.staffName = name
      if (project) row.projectName = project
      if (hours) {
        const h = Number(hours)
        if (Number.isFinite(h)) row.hours = h
      }
      if (amount) {
        const n = Number(String(amount).replace(/,/g, ''))
        if (Number.isFinite(n)) row.salaryAccrual = n
      }
      if (!row.attachmentIndex) row.attachmentIndex = file.name
      onRowChange(row)
      ElMessage.success('OCR 结果已填入')
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.error(e?.message || 'OCR 识别失败')
    }
  }
  input.click()
}

function handleSampling() {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('缺少工作底稿或项目上下文，无法打开抽凭引擎')
    return
  }
  samplingVisible.value = true
}

function onSamplesFilled(payload: { samples?: any[] }) {
  const samples = payload?.samples ?? []
  let n = 0
  for (const s of samples) {
    const amount = Number(s?.debitAmount) || Number(s?.creditAmount) || Number(s?.amount) || 0
    const summaryText = String(s?.summary ?? s?.description ?? '')
    const row = emptyI2WorkHourRow({
      staffName: summaryText || String(s?.voucherNo ?? ''),
      projectName: String(s?.projectName ?? s?.accountName ?? ''),
      salaryAccrual: amount,
      attachmentIndex: s?.voucherNo ? `凭证 ${s.voucherNo}` : '',
    })
    rows.value.push(row)
    onRowChange(row)
    n++
  }
  samplingVisible.value = false
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已回填 ${n} 笔抽样到工时行` : '未回填新凭证')
}

async function _loadTb6602(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6602' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let total = 0
    let hit = false
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (!code.startsWith('6602')) continue
      hit = true
      total += Number(item.audited_amount ?? item.unadjusted_amount ?? 0) || 0
    }
    tb6602.value = hit ? Math.abs(total) : null
  } catch {
    tb6602.value = null
  }
}

function handleExportExcel() {
  const data = rows.value.map((r) => ({
    projectName: r.projectName,
    projectCode: r.projectCode,
    projectPeriod: r.projectPeriod,
    staffName: r.staffName,
    hours: r.hours,
    allocationBasis: r.allocationBasis,
    salaryAccrual: r.salaryAccrual,
    customCheck: r.customCheck,
    attachmentIndex: r.attachmentIndex,
    conclusion: r.conclusion,
  }))
  void exportData({
    fileName: `I2-10研发人员工时检查表_${props.projectId || ''}.xlsx`,
    sheetName: 'I2-10',
    columns: [
      { key: 'projectName', header: '项目名称' },
      { key: 'projectCode', header: '项目号' },
      { key: 'projectPeriod', header: '起止' },
      { key: 'staffName', header: '人员' },
      { key: 'hours', header: '工时' },
      { key: 'allocationBasis', header: '依据' },
      { key: 'salaryAccrual', header: '薪酬' },
      { key: 'customCheck', header: '检查要素' },
      { key: 'attachmentIndex', header: '附件' },
      { key: 'conclusion', header: '结论' },
    ],
    data,
  })
}

function handleReview() {
  openReviewDialog('I2-10-研发人员工时检查')
}

function rowClassName({ row }: { row: I2WorkHourCheckRow }) {
  return workHourRowRiskClass(row)
}

function conclusionTagType(c: string): 'success' | 'danger' | 'warning' | 'info' {
  if (c === '合理') return 'success'
  if (c === '偏高') return 'danger'
  if (c === '偏低' || c === '待核实') return 'warning'
  return 'info'
}

function fmtPercent(v: number): string {
  return v == null || isNaN(v) || v <= 0 ? '—' : `${(v * 100).toFixed(1)}%`
}

function fmtNum(v: number, digits = 2): string {
  return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtAmt(v: number): string {
  return fmtNum(v, 2)
}

function getSummary({ columns }: { columns: any[] }) {
  const s = summary.value
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'hours') return fmtNum(s.totalHours, 1)
    if (prop === 'salaryAccrual') return fmtAmt(s.totalSalary)
    return ''
  })
}
</script>

<style scoped>
.i2-workhour-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 8px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.check-alert { margin-bottom: 12px; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.focus-tip { margin-bottom: 10px; }
.check-table { font-size: var(--wp-font-size, 13px); width: 100%; }
.formula-header { border-bottom: 1px dashed #a5b4fc; cursor: help; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.text-danger { color: #dc2626 !important; font-weight: 700; }
.attach-cell { display: flex; align-items: center; gap: 2px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
.prep-notes {
  margin-top: 12px; font-size: 12px; color: #4b5563; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 14px; line-height: 1.7;
}
.prep-notes summary { cursor: pointer; font-weight: 600; color: #374151; }
.prep-notes ol { margin: 8px 0 0; padding-left: 18px; }
:deep(.risk-high-row) { background-color: #fef2f2 !important; }
:deep(.risk-low-row) { background-color: #fff7ed !important; }
:deep(.risk-pending-row) { background-color: #fffbeb !important; }
</style>
