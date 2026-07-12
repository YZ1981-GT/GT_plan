<script setup lang="ts">
/** F3TabDisclosureListed — 附注披露（上市）| Task 9.2 */
import { toRef, type Ref } from 'vue'
import { useF3DisclosureListed } from '../composables/useF3DisclosureListed'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards: string[]
}>()

function fmtAmount(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  isApplicable, section1Rows, section1Subtotal, section2Rows, section2Subtotal,
  noteText, addRow, removeRow, updateCell,
} = useF3DisclosureListed({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})
</script>

<template>
  <div class="f3-disclosure-listed">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />

    <template v-else>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 应付票据（科目2201）按种类披露：银行承兑汇票、商业承兑汇票，分别列示期末/期初余额。</p>
          <p>2. 期末已到期未兑付的应付票据金额及原因、开具票据的保证金存款受限情况应单独披露。</p>
          <p>3. 大额或异常应付票据、关联方开具/承兑票据应结合 CAS 36 关联方披露一并说明。</p>
          <p>4. 分类合计应与 F3-1 审定表、资产负债表"应付票据"项目核对一致（浅蓝为跨sheet取数）。</p>
        </div>
      </details>

      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 应付票据按种类分类
          <el-tooltip content="数据来源：F3-1审定表银行/商业承兑分类" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="wp:F3-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="项目" width="200">
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ fmtAmount(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ fmtAmount(row.priorAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 其他应披露事项
          <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加</el-button>
        </h4>
        <el-table :data="[...section2Rows, section2Subtotal]" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="项目" width="200">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'" class="subtotal-label">合计</span>
              <el-input v-else :model-value="row.label" size="small" :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'label', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'">{{ fmtAmount(row.endAmount) }}</span>
              <el-input-number v-else :model-value="row.endAmount" :controls="false" size="small"
                :disabled="isReadonly" style="width:100%"
                @change="(v: number) => updateCell(row.rowId, 'endAmount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'">{{ fmtAmount(row.priorAmount) }}</span>
              <el-input-number v-else :model-value="row.priorAmount" :controls="false" size="small"
                :disabled="isReadonly" style="width:100%"
                @change="(v: number) => updateCell(row.rowId, 'priorAmount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__subtotal__'" link type="danger" size="small"
                :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="note-area">
        <span class="note-prefix">附注说明：</span>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
          placeholder="应付票据附注披露说明（到期未兑付、保证金受限、关联方票据等）..." />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f3-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-listed :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-listed :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.disclosure-card {
  margin-bottom: 16px;
}
.card-title {
  margin: 0 0 8px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.subtotal-label {
  font-weight: 600;
}
.cross-sheet-cell {
  background-color: #e6f7ff;
  padding: 2px 6px;
  border-radius: 2px;
  color: #409eff;
}
.note-area {
  margin-top: 12px;
}
.note-prefix {
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}
</style>
