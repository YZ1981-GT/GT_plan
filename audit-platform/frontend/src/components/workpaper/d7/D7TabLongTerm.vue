<template>
<div class="d7-longterm">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">添加行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromD72">从D7-2导入</el-button>
    </div>

    <!-- 8列表格 -->
    <el-table :data="rows" size="small" border>
      <el-table-column label="客户名称" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateCell(row.rowId, 'customerName', v)" />
          <span v-else>
            {{ row.customerName }}
            <GtIndexChip wp-code="D7-2" :label="`→D7-2`" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.endBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账龄" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => updateCell(row.rowId, 'aging', v)" />
          <span v-else>{{ row.aging }}</span>
        </template>
      </el-table-column>
      <el-table-column label="经济业务说明" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessDescription" size="small" @change="(v: string) => updateCell(row.rowId, 'businessDescription', v)" />
          <span v-else>{{ row.businessDescription }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未结转原因" min-width="160">
        <template #default="{ row }">
          <div class="reason-cell">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason }}</span>
            <el-button v-if="!isReadonly" size="small" :disabled="true" style="margin-left:4px">🤖AI</el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="至审计日结转金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditDateTransfer" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'auditDateTransfer', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditDateTransfer) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处理计划" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.plan" size="small" @change="(v: string) => updateCell(row.rowId, 'plan', v)" />
          <span v-else>{{ row.plan }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="60" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-section">
      <span>期末余额合计：<strong>{{ fmtAmt(totalRow.endBalance) }}</strong></span>
      <span>至审计日结转合计：<strong>{{ fmtAmt(totalRow.auditDateTransfer) }}</strong></span>
    </div>

    <!-- 审计说明/结论 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="对账龄超过1年合同负债的原因分析..." />
      <div class="note-actions">
        <el-button size="small" :disabled="true">🤖AI</el-button>
      </div>
    </div>
    <div class="audit-notes-section">
      <h4>审计结论</h4>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="结论..." />
    </div>
  </template>

  <div v-else class="oo-mode-placeholder">
    <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabLongTerm.vue — 账龄1年以上 D7-5 (~250行)
 * Task: 20.1
 * Requirements: 10.1-10.8, 19.3, 20.1
 */
import { ref, computed, type Ref } from 'vue'
import { useD7LongTerm } from '../composables/useD7LongTerm'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromD72, auditNotes,
} = useD7LongTerm({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d7-longterm { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.reason-cell { display: flex; align-items: center; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  gap: 24px;
  font-size: 13px;
}

.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
