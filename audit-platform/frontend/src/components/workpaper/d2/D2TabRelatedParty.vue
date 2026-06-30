<script setup lang="ts">
/**
 * D2TabRelatedParty — 关联方D2-6
 * 12列表 + 添加关联方 + 从D2-2导入 + 合计行
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2RelatedParty } from '../composables/useD2RelatedParty'
import GtIndexChip from '../GtIndexChip.vue'

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
  const rowKey = row?.rowId || row?.seq || 'unknown'
  openReviewDialog(`D2-relatedparty-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  rows,
  totalRow,
  addRow,
  removeRow,
  updateCell,
  importFromDetail,
} = useD2RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d2-tab-related-party">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">添加关联方</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromDetail">从D2-2导入</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <el-table :data="rows" border size="small" style="width: 100%">
      <el-table-column label="关联方名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
          <span v-else>{{ row.debtorName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relationType" size="small" @change="(v: string) => updateCell(row.rowId, 'relationType', v)" />
          <span v-else>{{ row.relationType || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="交易类型" width="100">
        <template #default="{ row }">{{ row.transactionType || '-' }}</template>
      </el-table-column>
      <el-table-column label="期初余额" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorBalance) }}</template>
      </el-table-column>
      <el-table-column label="本期借方" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.debitAmount) }}</template>
      </el-table-column>
      <el-table-column label="本期贷方" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.creditAmount) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight:600">{{ displayPrefs.fmtAmount(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="坏账准备" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.badDebtProvision) }}</template>
      </el-table-column>
      <el-table-column label="账面价值" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.bookValue) }}</template>
      </el-table-column>
      <el-table-column label="公允交易" width="80" align="center">
        <template #default="{ row }">{{ row.isArmsLength || '-' }}</template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <span>期初: {{ displayPrefs.fmtAmount(totalRow.priorBalance) }}</span>
      <span>期末: {{ displayPrefs.fmtAmount(totalRow.endBalance) }}</span>
      <span>账面价值: {{ displayPrefs.fmtAmount(totalRow.bookValue) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-related-party { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.total-bar {
  display: flex; gap: 24px; align-items: center; padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; }
</style>
