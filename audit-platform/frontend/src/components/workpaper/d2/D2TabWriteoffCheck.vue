<script setup lang="ts">
/**
 * D2TabWriteoffCheck — 转回核销D2-11
 * 双段结构: 转回区(8列) + 核销区(8列), 各区域添加+合计, 一致性警告
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2WriteoffCheck } from '../composables/useD2WriteoffCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
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
  const rowKey = row?.rowId || row?.section || 'unknown'
  openReviewDialog(`D2-writeoff-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  reversalRows,
  writeoffRows,
  reversalTotal,
  writeoffTotal,
  reversalConsistencyWarning,
  addRow,
  removeRow,
  updateCell,
} = useD2WriteoffCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d2-tab-writeoff">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 一致性警告 -->
    <el-alert v-if="reversalConsistencyWarning" type="warning" :closable="false" class="consistency-alert">
      {{ reversalConsistencyWarning }}
    </el-alert>

    <!-- 转回区 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">坏账转回</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('reversal')">添加</el-button>
      </div>
      <el-table :data="reversalRows" border size="small" style="width: 100%">
        <el-table-column label="债务人" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" @change="(v: number) => updateCell(row.rowId, 'amount', v)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确认日期" width="120">
          <template #default="{ row }">{{ row.originalDate || '-' }}</template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="120">
          <template #default="{ row }">{{ row.reason || '-' }}</template>
        </el-table-column>
        <el-table-column label="审批文件" width="100">
          <template #default="{ row }">{{ row.approvalDoc || '-' }}</template>
        </el-table-column>
        <el-table-column label="合理性" width="70" align="center">
          <template #default="{ row }">{{ row.isReasonable || '-' }}</template>
        </el-table-column>
        <el-table-column label="审计意见" min-width="100">
          <template #default="{ row }">{{ row.auditorComment || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="total-line">转回合计: {{ displayPrefs.fmtAmount(reversalTotal) }}</div>
    </div>

    <!-- 核销区 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">坏账核销</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('writeoff')">添加</el-button>
      </div>
      <el-table :data="writeoffRows" border size="small" style="width: 100%">
        <el-table-column label="债务人" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" @change="(v: number) => updateCell(row.rowId, 'amount', v)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确认日期" width="120">
          <template #default="{ row }">{{ row.originalDate || '-' }}</template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="120">
          <template #default="{ row }">{{ row.reason || '-' }}</template>
        </el-table-column>
        <el-table-column label="审批文件" width="100">
          <template #default="{ row }">{{ row.approvalDoc || '-' }}</template>
        </el-table-column>
        <el-table-column label="合理性" width="70" align="center">
          <template #default="{ row }">{{ row.isReasonable || '-' }}</template>
        </el-table-column>
        <el-table-column label="审计意见" min-width="100">
          <template #default="{ row }">{{ row.auditorComment || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="total-line">核销合计: {{ displayPrefs.fmtAmount(writeoffTotal) }}</div>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-writeoff { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.consistency-alert { margin-bottom: 12px; }
.section-block { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
.total-line { text-align: right; font-size: 13px; font-weight: 600; margin-top: 6px; padding: 4px 8px; background: #fafafa; border-radius: 4px; }
</style>
