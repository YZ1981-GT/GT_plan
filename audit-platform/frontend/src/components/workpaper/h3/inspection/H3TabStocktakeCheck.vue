<template>
  <div class="h3-tab-stocktake-check">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表记录投资性房地产实地盘点，核对产权证、位置、面积、用途、租赁状态与实物状态。</p>
        <p>2. 盘点结论分「相符 / 不符 / 待查」；空置资产黄色高亮，空置率 &gt;20% 需关注。</p>
        <p>3. 关注账实是否相符、是否存在毁损/闲置/权属瑕疵；成本模式与公允价值模式均需实地核实存在性。</p>
        <p>4. 盘点差异应追查原因并在审计说明中记录处理。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：通过实地盘点核实投资性房地产的存在性与状态，验证账实相符及用途/租赁情况。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-9" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增盘点行</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 13列盘点表 -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="location" label="位置/地址" min-width="140">
        <template #default="{ row, $index }">
          <el-input v-model="row.location" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="titleCertNo" label="产权证号" min-width="110">
        <template #default="{ row, $index }">
          <el-input v-model="row.titleCertNo" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="area" label="面积(㎡)" width="90" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.area" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="purpose" label="用途" width="90">
        <template #default="{ row, $index }">
          <el-select v-model="row.purpose" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="出租" value="出租" />
            <el-option label="增值" value="增值" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="tenant" label="租户" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.tenant" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="leaseStatus" label="租赁状态" width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.leaseStatus" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="已出租" value="已出租" />
            <el-option label="空置" value="空置" />
            <el-option label="到期" value="到期" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="physicalStatus" label="实物状态" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.physicalStatus" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="maintenance" label="维护情况" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.maintenance" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookValue" label="账面值" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="盘点结论" min-width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="相符" value="相符" />
            <el-option label="不符" value="不符" />
            <el-option label="待查" value="待查" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 汇总统计 -->
    <div class="summary-row">
      <span>已盘点：<b>{{ rows.length }}</b></span>
      <span>已出租：<b>{{ rentedCount }}</b></span>
      <span>空置：<b>{{ vacantCount }}</b></span>
      <span>空置率：<b :class="{ 'text-warn': vacantRate > 20 }">{{ vacantRate.toFixed(1) }}%</b></span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-9')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-9')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：盘点范围与方法、账实核对结果、空置/毁损/权属异常及处理。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、账实相符、状态正常。B、除下列事项外未见异常。C、存在重大账实不符，需追查。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabStocktakeCheck.vue — H3-9 盘点检查表
 * el-table 13列+空置黄色高亮+汇总+导入导出
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3Stocktake } from '../../composables/useH3Stocktake'
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
  measurementModel: ref('cost') as any,
})

const {
  rows, addRow, updateRow, rentedCount, vacantCount, vacantRate,
} = useH3Stocktake({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-9-audit-note'
const CONCLUSION_KEY = 'H3-9-audit-conclusion'
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

function onCellChange(index: number, row: any) { updateRow(index, row) }

function getRowClass({ row }: { row: any }): string {
  if (row.leaseStatus === '空置') return 'row-vacant'
  return ''
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.row-vacant) { background-color: #fef9e7 !important; }
.summary-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-warn { color: var(--el-color-warning); }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
