<template>
<div class="d7-related-party">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">添加关联方</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromD72">从D7-2导入</el-button>
    </div>

    <!-- 11列表格 -->
    <el-table :data="rows" size="small" border max-height="500">
      <el-table-column label="关联方名称" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(v: string) => updateCell(row.rowId, 'partyName', v)" />
          <span v-else>
            {{ row.partyName }}
            <GtIndexChip wp-code="D7-2" :label="`→D7-2`" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" width="140">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.relationship" size="small" @change="(v: string) => updateCell(row.rowId, 'relationship', v)">
            <el-option v-for="r in RELATIONSHIP_OPTIONS" :key="r" :label="r" :value="r" />
          </el-select>
          <span v-else>{{ row.relationship }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'openingBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.openingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方发生" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方发生" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发生时间及账龄" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.agingTime" size="small" @change="(v: string) => updateCell(row.rowId, 'agingTime', v)" />
          <span v-else>{{ row.agingTime }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未结转原因" width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="至审计日结转金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditDateTransfer" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'auditDateTransfer', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditDateTransfer) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处理计划" width="120">
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
      <span>期初合计：<strong>{{ fmtAmt(totalRow.openingBalance) }}</strong></span>
      <span>借方合计：<strong>{{ fmtAmt(totalRow.debitAmount) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmt(totalRow.creditAmount) }}</strong></span>
      <span>期末合计：<strong>{{ fmtAmt(totalRow.endBalance) }}</strong></span>
      <span>结转合计：<strong>{{ fmtAmt(totalRow.auditDateTransfer) }}</strong></span>
    </div>

    <!-- 审计说明/结论 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="对关联方合同负债的分析说明..." />
      <div class="note-actions">
        <el-button size="small" :disabled="true">🤖AI</el-button>
        <el-button size="small" @click="openReview('D7-6-note-explanation')">💬复核</el-button>
      </div>
    </div>
    <div class="audit-notes-section">
      <h4>审计结论</h4>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="关联方交易结论..." />
      <div class="note-actions">
        <el-button size="small" @click="openReview('D7-6-note-conclusion')">💬复核</el-button>
      </div>
    </div>
  </template>

  <div v-else class="oo-mode-placeholder">
    <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabRelatedParty.vue — 关联方 D7-6 (~300行)
 * Task: 21.1
 * Requirements: 11.1-11.9, 19.3, 20.1, 21.1-21.3
 */
import { ref, computed, inject, type Ref } from 'vue'
import { useD7RelatedParty, RELATIONSHIP_OPTIONS } from '../composables/useD7RelatedParty'
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

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromD72, auditNotes,
} = useD7RelatedParty({
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
.d7-related-party { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }

.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: 13px;
}

.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
