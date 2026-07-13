<template>
  <div class="h3-tab-detail-fair">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产明细表（公允价值模式），分「基本 / 公允变动」两区段，行数据在区段间同步。</p>
        <p>2. 期末公允 = 期初 + 增加 − 减少 ± 转换 + 公允价值变动；公允价值模式下不计提折旧与减值（CAS3）。</p>
        <p>3. 明细合计应与 H3-1 审定表勾稽一致；关注公允价值来源（活跃市场报价 / 评估）与变动损益列示。</p>
        <p>4. 若企业采用成本模式，请切换至成本模式明细版本。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：逐项核实投资性房地产（公允价值模式）的期初/期末公允价值及公允价值变动的真实、准确与计量恰当，支持 H3-1 审定表。"
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
      <el-table-column prop="fairValueBegin" label="期初公允" min-width="110" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.fairValueBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 公允变动区段 -->
    <el-table v-if="activeSegment === '公允变动'" :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
      <el-table-column prop="assetType" label="类型" min-width="100" fixed />
      <el-table-column prop="fairIncrease" label="本期增加" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.fairIncrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="fairDecrease" label="本期减少" min-width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.fairDecrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
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
      <el-table-column prop="fairValueChange" label="公允价值变动" min-width="120" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
        </template>
      </el-table-column>
      <el-table-column label="期末公允" min-width="110" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="期初+增加-减少±转换+变动">{{ fmtNum(row.fairValueEnd) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-2-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：明细核对情况、公允价值来源与变动核查、与 H3-1 审定表勾稽差异及原因。" :disabled="isReadonly" @change="saveAuditNote" />
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
 * H3TabDetailFair.vue — H3-2 明细表（公允价值模式）
 * 2区段Tab切换+行同步+固定列+合计+导入导出
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH3DetailFair } from '../../composables/useH3DetailFair'
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
  measurementModel: ref('fair_value'),
})

const {
  rows, subtotal: subtotalRow, addRow, updateCell,
} = useH3DetailFair({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const activeSegment = ref('基本')
const segmentOptions = ['基本', '公允变动']
// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-2-fair-audit-note'
const CONCLUSION_KEY = 'H3-2-fair-audit-conclusion'
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

function doExportTemplate() { /* TODO */ }
function doExportData() { /* TODO */ }
function doImportData() { /* TODO */ }

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-detail-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
