<template>
  <div class="h3-tab-detail-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产明细表（成本模式），分「基本 / 折旧变动 / 增减转换」三区段，行数据在各区段间同步。</p>
        <p>2. 折旧期末 = 期初 + 计提 − 转回；净值 = 原值 − 折旧 − 减值；期末原值 = 期初 + 增加 − 减少 ± 转入/转出。</p>
        <p>3. 明细合计应与 H3-1 审定表勾稽一致（差异区提示）；成本模式按固定资产准则计提折旧。</p>
        <p>4. 若企业采用公允价值模式，请切换至公允价值明细版本。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：逐项核实投资性房地产（成本模式）的原值、累计折旧、净值及增减变动的真实、准确与完整，支持 H3-1 审定表。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddAsset">+ 添加资产</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="doExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="doExportData">导出数据</el-dropdown-item>
            <el-dropdown-item @click="doImportData">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 基本信息区段 -->
    <el-table v-if="activeSegment === '基本'" :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
      <el-table-column prop="assetType" label="类型" min-width="100" fixed />
      <el-table-column prop="location" label="位置/地址" min-width="160" />
      <el-table-column prop="area" label="面积(㎡)" min-width="90" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.area" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="acquireDate" label="取得日期" min-width="110" />
      <el-table-column prop="originalCost" label="入账原值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.originalCost" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 折旧变动区段 -->
    <el-table v-if="activeSegment === '折旧变动'" :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
      <el-table-column prop="assetType" label="类型" min-width="100" fixed />
      <el-table-column prop="accDepBegin" label="折旧期初" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.accDepBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="depProvision" label="本期计提" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.depProvision" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="depReversal" label="转回" min-width="90" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.depReversal" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column label="折旧期末" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="期初+计提-转回">{{ fmtNum(row.accDepEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="净值" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="原值-折旧-减值">{{ fmtNum(row.netValue) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 增减转换区段 -->
    <el-table v-if="activeSegment === '增减转换'" :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
      <el-table-column prop="assetType" label="类型" min-width="100" fixed />
      <el-table-column prop="costIncrease" label="本期增加" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.costIncrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="costDecrease" label="本期减少" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.costDecrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="transferIn" label="转入" min-width="90" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="transferOut" label="转出" min-width="90" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column label="期末原值" min-width="110" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="期初+增加-减少±转入/转出">{{ fmtNum(row.costEnd) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 交叉验证 -->
    <div v-if="crossValidationDiff !== 0" class="cross-validation-warn">
      <el-alert type="error" :closable="false" show-icon>
        明细合计与H3-1审定表差异：{{ fmtNum(crossValidationDiff) }}
      </el-alert>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-cost')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-2-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：明细核对情况、折旧测算复核、增减变动核查、与 H3-1 审定表勾稽差异及原因。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、未见异常。B、除上述事项外未见异常。C、存在重大未调整事项，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDetailCost.vue — H3-2 明细表（成本模式）
 * 3区段Tab切换+行同步+固定列+合计+交叉验证+导入导出
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH3DetailCost } from '../../composables/useH3DetailCost'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'

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
  rows, subtotal: subtotalRow, crossValidationDiff, addRow, updateCell, removeRow,
} = useH3DetailCost({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const activeSegment = ref('基本')
const segmentOptions = ['基本', '折旧变动', '增减转换']
// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-2-cost-audit-note'
const CONCLUSION_KEY = 'H3-2-cost-audit-conclusion'
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

async function handleAddAsset() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '添加资产', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  if (value) addRow(value)
}

function onCellChange(row: any) {
  updateCell(row.rowId, row)
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => idx === 0 ? '合计' : '')
}

function doExportTemplate() { /* TODO: useH3ImportExport */ }
function doExportData() { /* TODO */ }
function doImportData() { /* TODO */ }

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-detail-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.cross-validation-warn { margin: 12px 0; }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
