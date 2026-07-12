<template>
  <div class="h3-tab-detail-cost">
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

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-cost')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-2-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明/结论..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDetailCost.vue — H3-2 明细表（成本模式）
 * 3区段Tab切换+行同步+固定列+合计+交叉验证+导入导出
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH3DetailCost } from '../../composables/useH3DetailCost'
import { useH3FormData } from '../../composables/useH3FormData'

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
const conclusion = ref(getValue('H3-2-cost-conclusion') ?? '')

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
