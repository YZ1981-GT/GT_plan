<template>
  <div class="h3-tab-detail-fair">
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

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-2-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明/结论..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDetailFair.vue — H3-2 明细表（公允价值模式）
 * 2区段Tab切换+行同步+固定列+合计+导入导出
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH3DetailFair } from '../../composables/useH3DetailFair'
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
const conclusion = ref(getValue('H3-2-fair-conclusion') ?? '')

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
.h3-tab-detail-fair { padding: 16px; font-size: 13px; }
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: 13px; margin-bottom: 12px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
