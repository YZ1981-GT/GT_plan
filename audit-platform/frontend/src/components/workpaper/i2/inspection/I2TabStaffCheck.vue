<template>
  <div class="i2-staff-check">
    <div class="section-header">
      <span class="section-title">I2-9 研发人员认定检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I2_STAFF_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        按编制说明中的认定规则，对纳入研发费用归集的人员逐人核查身份、资质、聘用形式、是否全时及工时占比；
        剔除后勤辅助、劳务派遣、工时占比不足等不合规人员；结论与 I2-10 工时检查表交叉印证。
        检查要素可按实际情况增删。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-9" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-10" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ summary.totalCount }} 人</el-tag>
        <el-tag size="small" type="success">认定 {{ summary.acceptedCount }}</el-tag>
        <el-tag v-if="summary.rejectedCount" size="small" type="danger">不予认定 {{ summary.rejectedCount }}</el-tag>
        <el-tag v-if="summary.pendingCount" size="small" type="warning">待核实 {{ summary.pendingCount }}</el-tag>
        <el-tag v-if="summary.overrideRiskCount" size="small" type="danger">
          覆盖风险 {{ summary.overrideRiskCount }}
        </el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-8')">← I2-8</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-10')">I2-10 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="summary.overrideRiskCount > 0"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${summary.overrideRiskCount} 人系统建议「不予认定」，但人工结论仍为「认定为研发人员」，请在审计说明中充分论证。`"
    />
    <el-alert
      v-else-if="summary.dispatchCount > 0 || summary.lowRatioCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="riskHint"
    />

    <!-- 二、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程 — 研发人员逐人认定</span>
          <div class="title-actions">
            <el-segmented
              v-model="columnViewMode"
              :options="[
                { label: '精简', value: 'compact' },
                { label: '完整', value: 'full' },
              ]"
              size="small"
            />
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" :disabled="isReadonly" @click="applyAllSuggestions">采纳建议结论</el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleSampling">抽凭引擎</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="focus-tip"
        title="核对重点：聘用形式是否为劳动合同；是否全时且工时占比≥50%；岗位/部门是否属直接研发或相关管理服务；附件（合同、学历、工时表）索引完整。"
      />

      <el-table
        :data="rows"
        border
        size="small"
        class="check-table"
        max-height="520"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="序号" width="50" fixed align="center" />

        <el-table-column prop="staffName" label="姓名" min-width="88" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.staffName" size="small" @change="onRowChange(row)" />
            <span v-else>{{ row.staffName || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="gender" label="性别" width="72" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.gender" size="small" clearable style="width:100%">
              <el-option v-for="g in ['男', '女']" :key="g" :label="g" :value="g" />
            </el-select>
            <span v-else>{{ row.gender || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="age" label="年龄" width="72" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.age"
              size="small"
              :controls="false"
              :min="16"
              :max="80"
              style="width:100%"
            />
            <span v-else>{{ row.age ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="education" label="学历" min-width="90">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.education"
              size="small"
              filterable
              allow-create
              clearable
              style="width:100%"
            >
              <el-option v-for="e in I2_STAFF_EDU_OPTIONS" :key="e" :label="e" :value="e" />
            </el-select>
            <span v-else>{{ row.education || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="graduateSchool" label="毕业院校" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.graduateSchool" size="small" />
            <span v-else>{{ row.graduateSchool || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="major" label="所学专业" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.major" size="small" />
            <span v-else>{{ row.major || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="title" label="职称" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.title" size="small" placeholder="职称" />
            <span v-else>{{ row.title || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="position" label="职务" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.position" size="small" @change="onRowChange(row)" />
            <span v-else>{{ row.position || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="department" label="部门" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" @change="onRowChange(row)" />
            <span v-else>{{ row.department || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="personnelCategory" label="人员类别" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.personnelCategory"
              size="small"
              filterable
              allow-create
              clearable
              style="width:100%"
              @change="onRowChange(row)"
            >
              <el-option v-for="c in I2_STAFF_CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.personnelCategory || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="hireDate" label="入职日期" min-width="128">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.hireDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
            />
            <span v-else>{{ row.hireDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="employmentForm" label="聘用形式" min-width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.employmentForm"
              size="small"
              filterable
              allow-create
              clearable
              style="width:100%"
              @change="onRowChange(row)"
            >
              <el-option v-for="e in I2_STAFF_EMPLOY_OPTIONS" :key="e" :label="e" :value="e" />
            </el-select>
            <span v-else>{{ row.employmentForm || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="fullTimeRd" label="是否全时" min-width="90" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.fullTimeRd"
              size="small"
              clearable
              style="width:100%"
              @change="onRowChange(row)"
            >
              <el-option v-for="f in I2_STAFF_FULLTIME_OPTIONS" :key="f" :label="f" :value="f" />
            </el-select>
            <span v-else>{{ row.fullTimeRd || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="rdHourRatio" label="研发工时占比%" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.rdHourRatio"
              size="small"
              :controls="false"
              :min="0"
              :max="100"
              :precision="1"
              style="width:100%"
              @change="onRowChange(row)"
            />
            <span v-else>{{ row.rdHourRatio == null ? '—' : `${row.rdHourRatio}%` }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="projects" label="参与项目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projects" size="small" placeholder="研发项目" />
            <span v-else>{{ row.projects || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="attachmentIndex" label="附件索引号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.attachmentIndex" size="small" placeholder="合同/学历等" />
            <span v-else>{{ row.attachmentIndex || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="建议结论" min-width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="conclusionTagType(row.suggestedConclusion)" size="small">
              {{ row.suggestedConclusion || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="conclusion" label="认定结论" min-width="130">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.conclusion"
              size="small"
              style="width:100%"
            >
              <el-option
                v-for="c in I2_STAFF_CONCLUSION_OPTIONS"
                :key="c"
                :label="c"
                :value="c"
              />
            </el-select>
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="附件" width="56" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" text @click="handleOcr($index)">📎</el-button>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" text @click="handleRemoveRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title-text">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录抽样范围、不予认定人员处理、与工时表交叉核对情况、人工覆盖系统建议的理由…"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title-text">四、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="如：经检查，本期纳入研发费用归集的人员认定总体恰当；剔除劳务派遣/工时不足等××人，金额××元已建议调整…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制说明 -->
    <details class="prep-notes" open>
      <summary>编制说明（认定规则）</summary>
      <ol>
        <li v-for="(n, i) in I2_STAFF_PREP_NOTES" :key="i">{{ n }}</li>
      </ol>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 开发支出(1717) 人员认定检查" width="90%" top="5vh" destroy-on-close>
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
import {
  I2_STAFF_CATEGORY_OPTIONS,
  I2_STAFF_CONCLUSION_OPTIONS,
  I2_STAFF_EDU_OPTIONS,
  I2_STAFF_EMPLOY_OPTIONS,
  I2_STAFF_FULLTIME_OPTIONS,
  I2_STAFF_OBJECTIVES,
  I2_STAFF_PREP_NOTES,
  emptyI2StaffRow,
  normalizeI2StaffRow,
  persistI2StaffRow,
  staffRowRiskClass,
  suggestStaffConclusion,
  summarizeI2StaffRows,
  type I2StaffCheckRow,
} from '../../composables/i2StaffCheckModel'
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

const STORAGE_KEY = 'I2-9-rows'
const AUDIT_NOTE_KEY = 'I2-9-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-9-audit-conclusion'

const rows = ref<I2StaffCheckRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const columnViewMode = ref<'compact' | 'full'>('compact')
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const summary = computed(() => summarizeI2StaffRows(rows.value))

const riskHint = computed(() => {
  const parts: string[] = []
  if (summary.value.dispatchCount) parts.push(`劳务派遣 ${summary.value.dispatchCount} 人`)
  if (summary.value.lowRatioCount) parts.push(`工时占比不足50% ${summary.value.lowRatioCount} 人`)
  if (summary.value.nonRdKeywordCount) parts.push(`疑似非研发岗位 ${summary.value.nonRdKeywordCount} 人`)
  return parts.length ? `关注：${parts.join('；')}，请逐人核实认定结论。` : ''
})

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) {
    rows.value = []
    return
  }
  try {
    const parsed = typeof raw === 'string'
      ? JSON.parse(raw)
      : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map(normalizeI2StaffRow)
    } else {
      rows.value = []
    }
  } catch {
    rows.value = []
  }
}

function hydrateAudit() {
  auditNote.value = readRemark(AUDIT_NOTE_KEY)
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}

function saveAuditNote(val: string) {
  auditNote.value = val
  void props.saveResponse('I2-9', { [AUDIT_NOTE_KEY]: val })
}

function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-9', { [AUDIT_CONCLUSION_KEY]: val })
}

watch(() => props.allResponses, () => { loadData(); hydrateAudit() }, { immediate: true })
onMounted(hydrateAudit)

function onRowChange(row: I2StaffCheckRow) {
  const prevSuggested = row.suggestedConclusion
  row.suggestedConclusion = suggestStaffConclusion(row)
  // 若人工结论仍等于旧建议，则跟随新建议（未手工改过）
  if (!row.conclusion || row.conclusion === prevSuggested) {
    row.conclusion = row.suggestedConclusion
  }
}

function handleAddRow() {
  rows.value.push(emptyI2StaffRow())
}

function handleRemoveRow(index: number) {
  if (index < 0 || index >= rows.value.length) return
  rows.value.splice(index, 1)
}

function applyAllSuggestions() {
  for (const row of rows.value) {
    row.suggestedConclusion = suggestStaffConclusion(row)
    row.conclusion = row.suggestedConclusion
  }
  ElMessage.success('已按编制说明规则刷新全部认定结论')
}

async function handleSave() {
  const persist = rows.value.map(persistI2StaffRow)
  await props.saveResponse('I2-9', { [STORAGE_KEY]: JSON.stringify(persist) })
  const total = summary.value.totalCount
  const progress = total <= 0
    ? 10
    : Math.min(100, Math.round(((summary.value.acceptedCount + summary.value.rejectedCount) / total) * 100))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 'I2-9',
    progress,
    ok: total > 0 && summary.value.pendingCount === 0 && summary.value.overrideRiskCount === 0,
    detail: {
      totalCount: total,
      acceptedCount: summary.value.acceptedCount,
      rejectedCount: summary.value.rejectedCount,
      overrideRiskCount: summary.value.overrideRiskCount,
    },
  })
  emit('save')
  ElMessage.success('研发人员认定检查表已保存')
}

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
      const education = pickOcrField(fields, 'education', 'degree')
      const hireDate = pickOcrField(fields, 'hireDate', 'date', 'startDate')
      const school = pickOcrField(fields, 'graduateSchool', 'school')
      await ElMessageBox.confirm(
        `OCR 识别结果：\n姓名: ${name || '-'}\n学历: ${education || '-'}\n入职: ${hireDate || '-'}\n院校: ${school || '-'}\n\n确认填入第 ${idx + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const row = rows.value[idx]
      if (!row) return
      if (name) row.staffName = name
      if (education) row.education = education
      if (hireDate) row.hireDate = hireDate
      if (school) row.graduateSchool = school
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
    const summaryText = String(s?.summary ?? '')
    rows.value.push(emptyI2StaffRow({
      staffName: summaryText || String(s?.voucherNo ?? ''),
      remark: [
        s?.voucherNo ? `凭证 ${s.voucherNo}` : '',
        s?.voucherDate || '',
        summaryText,
      ].filter(Boolean).join(' / '),
    }))
    n++
  }
  samplingVisible.value = false
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已回填 ${n} 笔抽样到人员行` : '未回填新凭证')
}

function handleReview() {
  openReviewDialog('I2-9-研发人员认定检查')
}

function rowClassName({ row }: { row: I2StaffCheckRow }) {
  return staffRowRiskClass(row)
}

function conclusionTagType(c: string): 'success' | 'danger' | 'warning' | 'info' {
  if (c === '认定为研发人员') return 'success'
  if (c === '不予认定') return 'danger'
  if (c === '待核实') return 'warning'
  return 'info'
}
</script>

<style scoped>
.i2-staff-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
.block-title-text { font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.focus-tip { margin-bottom: 10px; }
.check-table { font-size: var(--wp-font-size, 13px); width: 100%; }
.prep-notes {
  margin-top: 8px; font-size: 12px; color: #4b5563; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 14px; line-height: 1.7;
}
.prep-notes summary { cursor: pointer; font-weight: 600; color: #374151; }
.prep-notes ol { margin: 8px 0 0; padding-left: 18px; }
:deep(.risk-reject-row) { background-color: #fef2f2 !important; }
:deep(.risk-override-row) { background-color: #fff7ed !important; }
:deep(.risk-pending-row) { background-color: #fffbeb !important; }
</style>
