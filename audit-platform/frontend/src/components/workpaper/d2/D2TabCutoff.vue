<script setup lang="ts">
/**
 * D2TabCutoff — 截止测试
 * 8列: 序号|发票号|收入日期|入账日期|金额|跨期判定|结论|备注
 * 自动跨期判定, 红色警告header, 底部汇总
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2Cutoff } from '../composables/useD2Cutoff'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate: string
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.seq || row?.index || 'unknown'
  openReviewDialog(`D2-cutoff-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  samples,
  cutoffCount,
  cutoffTotalAmount,
  hasCutoffIssue,
  addSample,
  removeSample,
  updateCell,
} = useD2Cutoff({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})
</script>

<template>
  <div class="d2-tab-cutoff">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample">添加样本</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 跨期警告 -->
    <el-alert v-if="hasCutoffIssue" type="error" :closable="false" class="cutoff-alert">
      发现{{ cutoffCount }}笔跨期，合计金额{{ displayPrefs.fmtAmount(cutoffTotalAmount) }}
    </el-alert>

    <!-- 主表 -->
    <el-table :data="samples" border size="small" style="width: 100%">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column label="发票号" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.invoiceNo" size="small" @change="(v: string) => updateCell(row.rowId, 'invoiceNo', v)" />
          <span v-else>{{ row.invoiceNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收入日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.revenueDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'revenueDate', v)"
          />
          <span v-else>{{ row.revenueDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入账日期" width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.receivableDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'receivableDate', v)"
          />
          <span v-else>{{ row.receivableDate || '-' }}</span>
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
            @change="(v: number) => updateCell(row.rowId, 'amount', v)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="跨期判定" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCutoff" type="danger" size="small">跨期</el-tag>
          <span v-else style="color:#909399">正常</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowId, 'conclusion', v)" />
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeSample(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span>已检查: {{ samples.length }}笔</span>
      <span>跨期笔数: <b :style="{ color: cutoffCount > 0 ? '#f56c6c' : '' }">{{ cutoffCount }}</b></span>
      <span>跨期金额: {{ displayPrefs.fmtAmount(cutoffTotalAmount) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-cutoff { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.cutoff-alert { margin-bottom: 12px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 10px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px;
}
</style>
