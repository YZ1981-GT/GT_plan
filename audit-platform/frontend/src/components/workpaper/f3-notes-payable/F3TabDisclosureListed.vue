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
      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 应付票据按种类分类
          <el-tooltip content="数据来源：F3-1审定表银行/商业承兑分类" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip target="F3-1" label="→F3-1" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
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
        <el-table :data="[...section2Rows, section2Subtotal]" size="small" border stripe>
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
        <el-input v-model="noteText" type="textarea" :rows="3" :disabled="isReadonly"
          placeholder="应付票据附注披露说明..." />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f3-disclosure-listed { font-size: 13px; }
.disclosure-card { margin-bottom: 16px; }
.card-title { margin: 0 0 8px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
.cross-sheet-cell { color: #409eff; }
.note-area { margin-top: 12px; }
.note-prefix { font-weight: 600; display: block; margin-bottom: 4px; }
</style>
