<script setup lang="ts">
/**
 * D1TabAdjustment — 调整分录 D1-5
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1Adjustment, type AdjustmentEntry } from '../composables/useD1Adjustment'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import type { ChecklistResponse } from '../composables/useD1FormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

async function saveImmediate(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>) {
  try {
    await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
  } catch {
    ElMessage.warning('保存失败，请重试')
  }
}

const {
  entries,
  ajeTotal,
  rjeTotal,
  addEntry,
  removeEntry,
  updateEntry,
  pushToA13,
} = useD1Adjustment({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  saveImmediate,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-5')

const selectedIndices = ref<number[]>([])

function handleSelection(selection: AdjustmentEntry[]) {
  selectedIndices.value = selection.map(e => e.index)
}

function handleCellContextMenu(row: AdjustmentEntry, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.label || 'unknown'
  openReviewDialog(`D1-adjustment-${row.index}-${field}`)
}
</script>

<template>
  <div class="d1-tab-adjustment">
    <div class="tab-header">
      <h4>调整分录汇总 D1-5</h4>
      <GtReviewTrigger section-id="D1-adjustment-header" />
    </div>

    <div class="tab-toolbar">
      <el-button size="small" @click="onExportTemplate">导出模板</el-button>
      <el-button size="small" @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button size="small">导入数据</el-button>
      </el-upload>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addEntry()">
        新增调整分录
      </el-button>
      <el-button
        size="small"
        type="warning"
        :disabled="selectedIndices.length === 0 || isReadonly"
        @click="pushToA13(selectedIndices)"
      >推送至 A13</el-button>
    </div>

    <el-table
      :data="entries"
      border
      size="small"
      @selection-change="handleSelection"
      @cell-contextmenu="handleCellContextMenu"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column prop="index" label="序号" width="60" align="center" />
      <el-table-column label="类别" width="90">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.type"
            size="small"
            @change="(v: string) => updateEntry(row.index, { type: v as any })"
          >
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.type === 'AJE' ? 'primary' : 'warning'" size="small">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="借方科目" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.debitAccount"
            size="small"
            @change="(v: string) => updateEntry(row.index, { debitAccount: v })"
          />
          <span v-else>{{ row.debitAccount || '-' }}</span>
          <GtReviewDot row-prefix="D1-adjustment" :row-key="String(row.index)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方科目" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.creditAccount"
            size="small"
            @change="(v: string) => updateEntry(row.index, { creditAccount: v })"
          />
          <span v-else>{{ row.creditAccount || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            size="small"
            :controls="false"
            :precision="2"
            @change="(v: number) => updateEntry(row.index, { amount: v })"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            @change="(v: string) => updateEntry(row.index, { description: v })"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已推送" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isPushedToAdjTable ? 'success' : 'info'" size="small">
            {{ row.isPushedToAdjTable ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeEntry(row.index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-bar">
      <span>AJE 合计：{{ displayPrefs.fmtAmount(ajeTotal) }}</span>
      <span>RJE 合计：{{ displayPrefs.fmtAmount(rjeTotal) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d1-tab-adjustment { padding: 12px 0; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.tab-toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.totals-bar {
  display: flex; gap: 24px; margin-top: 12px;
  padding: 10px 12px; background: #fafafa; border-radius: 4px;
  font-size: 13px; font-weight: 600;
}
</style>
