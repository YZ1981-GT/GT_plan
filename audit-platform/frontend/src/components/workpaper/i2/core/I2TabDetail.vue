<template>
  <div class="i2-detail">
    <div class="section-header">
      <span class="section-title">I2-2 开发支出明细表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li>确认开发支出明细完整、真实发生，各研发项目归集与立项一致（存在/发生、完整性）。</li>
        <li>确认增减变动（资本化增加、转无形资产/存货、转当期损益）金额准确、期间正确（准确性、截止）。</li>
        <li>确认期末审定数与无形资产/存货等科目勾稽一致，差异已解释或调整（计价和分摊、权利和义务）。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        按项目滚动勾稽「未审数 → 期初/账项调整 → 审定数」；
        期末未审 = 期初 + 增加 − 转无形/存货 − 转损益；
        审定各列 = 未审 + 对应调整；审定期末再与无形/存货期末审定比对差异。
        账项调整列可从 <b>I2-3</b> 一键同步。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增项目</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly"
          :loading="syncing"
          @click="handleSyncAje"
        >
          从 I2-3 同步账项调整
        </el-button>
        <el-button
          v-if="activeRowIndex >= 0"
          size="small"
          type="danger"
          plain
          :disabled="isReadonly"
          @click="handleRemoveRow"
        >
          删除选中行
        </el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-1')">← 审定表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-3')">I2-3 调整 →</el-button>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-3" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
        <el-tag size="small" type="success">审定期末 {{ fmtAmount(totalRow.auditedEnding) }}</el-tag>
        <el-tag v-if="ajeLinkage.hasWarning" size="small" type="danger">
          账项 vs I2-3 差 {{ fmtAmount(ajeLinkage.diff) }}
        </el-tag>
        <el-tag v-else-if="ajeLinkage.i23RowCount > 0" size="small" type="success">账项已勾稽 I2-3</el-tag>
      </div>
    </div>

    <el-alert
      v-if="ajeLinkage.hasWarning"
      type="warning"
      :closable="false"
      show-icon
      class="link-alert"
      :title="`明细账项净额 ${fmtAmount(ajeLinkage.detailAjeNet)} 与 I2-3 开发支出账项净额 ${fmtAmount(ajeLinkage.i23AjeNet)} 不一致，请同步或核对。`"
    />
    <el-alert
      v-if="crossValidation.hasWarning"
      type="warning"
      :closable="false"
      show-icon
      class="link-alert"
      :title="`明细审定期末合计 ${fmtAmount(crossValidation.detailEndTotal)} 与审定表期末 ${fmtAmount(crossValidation.adjEndTotal)} 差异 ${fmtAmount(crossValidation.difference)}。`"
    />

    <!-- 二、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程</span>
          <el-segmented
            v-model="activeSegmentIndex"
            :options="segmentOptions"
            size="small"
            @change="onSegmentChange"
          />
        </div>
      </template>

      <el-table
        :data="displayRows"
        border
        size="small"
        max-height="520"
        :row-class-name="getRowClassName"
        highlight-current-row
        class="detail-table"
        @current-change="onRowSelect"
      >
        <el-table-column type="index" label="#" width="44" align="center" fixed />
        <el-table-column
          v-for="col in currentColumns"
          :key="col.key"
          :prop="col.key"
          :label="col.label"
          :min-width="col.width"
          :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
        >
          <template #header>
            <el-tooltip v-if="col.type === 'formula'" :content="col.tooltip || ''" placement="top">
              <span class="formula-col-header" :class="{ emphasis: col.emphasis }">{{ col.label }}</span>
            </el-tooltip>
            <span v-else :class="{ emphasis: col.emphasis }">{{ col.label }}</span>
          </template>
          <template #default="{ row, $index }">
            <template v-if="row._isTotal">
              <span class="total-text">
                {{ col.type === 'number' || col.type === 'formula' ? fmtAmount((row as any)[col.key]) : (row as any)[col.key] }}
              </span>
            </template>
            <template v-else-if="col.type === 'formula'">
              <el-tooltip :content="col.tooltip || ''" placement="top">
                <span class="formula-value" :class="{ 'diff-warn': col.key === 'diffVsIA' && Math.abs(row.diffVsIA) > 0.01 }">
                  {{ fmtAmount((row as any)[col.key]) }}
                </span>
              </el-tooltip>
            </template>
            <template v-else-if="col.type === 'number' && col.editable && !isReadonly">
              <el-input-number
                :model-value="(row as any)[col.key]"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                @change="(v: number | undefined) => onCellChange($index, col.key, v ?? 0)"
              />
            </template>
            <template v-else-if="col.type === 'date' && col.editable && !isReadonly">
              <el-date-picker
                :model-value="(row as any)[col.key]"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:100%"
                @change="(v: string) => onCellChange($index, col.key, v)"
              />
            </template>
            <template v-else-if="col.type === 'select' && col.editable && !isReadonly">
              <el-select
                :model-value="(row as any)[col.key]"
                size="small"
                style="width:100%"
                @change="(v: string) => onCellChange($index, col.key, v)"
              >
                <el-option v-for="opt in col.options || []" :key="opt || '_'" :label="opt || '—'" :value="opt" />
              </el-select>
            </template>
            <template v-else-if="col.editable && !isReadonly">
              <el-input
                :model-value="(row as any)[col.key]"
                size="small"
                @change="(v: string) => onCellChange($index, col.key, v)"
              />
            </template>
            <template v-else>
              <span>{{ col.type === 'number' ? fmtAmount((row as any)[col.key]) : ((row as any)[col.key] || '—') }}</span>
            </template>
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
        placeholder="记录抽样范围、资本化/费用化划分、与 I2-3/I2-6/I2-7/I1 勾稽及差异处理…"
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
        placeholder="如：经检查，开发支出明细滚动勾稽正确，审定数与无形资产转入勾稽一致，余额可以确认…"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI2Detail } from '../../composables/useI2Detail'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  activeSegment,
  activeRowIndex,
  totalRow,
  crossValidation,
  ajeLinkage,
  activeColumns,
  segments,
  switchSegment,
  setActiveRow,
  updateField,
  addRow,
  removeRow,
  save: saveData,
  syncAjeFromI23,
} = useI2Detail({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

const AUDIT_NOTE_KEY = 'I2-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const syncing = ref(false)

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
  void props.saveResponse('I2-2', { [AUDIT_NOTE_KEY]: val })
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-2', { [AUDIT_CONCLUSION_KEY]: val })
}
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(hydrateAudit)

const segmentOptions = segments.map((s) => s.label)
const activeSegmentIndex = ref(segmentOptions[0])

function onSegmentChange(val: string) {
  const idx = segmentOptions.indexOf(val)
  if (idx >= 0) {
    switchSegment(idx)
    activeSegment.value = idx
  }
}

const currentColumns = computed(() => activeColumns.value)

const displayRows = computed(() => {
  const dataRows = rows.value.map((r) => ({ ...r, _isTotal: false }))
  return [...dataRows, { ...totalRow.value, _isTotal: true }]
})

function getRowClassName({ row }: { row: any }): string {
  if (row._isTotal) return 'total-row'
  if (Math.abs(row.diffVsIA || 0) > 0.01) return 'diff-row'
  return ''
}

function onRowSelect(row: any) {
  if (!row || row._isTotal) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  setActiveRow(idx)
}

function onCellChange(displayIndex: number, field: string, value: any) {
  if (displayIndex >= rows.value.length) return
  updateField(displayIndex, field, value ?? 0)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：课题1 / 数据资源平台',
    })
    if (value?.trim()) {
      addRow(value.trim())
      ElMessage.success('已添加项目')
    }
  } catch { /* cancel */ }
}

function handleRemoveRow() {
  if (activeRowIndex.value >= 0) removeRow(activeRowIndex.value)
}

async function handleSyncAje() {
  syncing.value = true
  try {
    const res = syncAjeFromI23()
    if (res.applied > 0) {
      ElMessage.success(res.message)
      await saveData()
      emit('save')
    } else {
      ElMessage.info(res.message)
    }
  } finally {
    syncing.value = false
  }
}

async function handleSave() {
  await saveData()
  emit('save')
  ElMessage.success('明细表已保存')
}

function handleReview() {
  openReviewDialog('I2-2-开发支出明细')
}

function fmtAmount(value: number | null | undefined): string {
  if (value == null || Math.abs(Number(value)) < 0.005) return '—'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-detail { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 8px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.link-alert { margin-bottom: 10px; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-weight: 600; }
.block-title-text { font-weight: 600; }
.detail-table { width: 100%; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.emphasis { color: #b45309; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; color: #409eff; }
.diff-warn { color: #dc2626; font-weight: 600; }
.total-text { font-weight: 600; color: #303133; }
:deep(.total-row) { background: #f3f4f6 !important; font-weight: 600; }
:deep(.diff-row) { background: #fff7ed !important; }
</style>
