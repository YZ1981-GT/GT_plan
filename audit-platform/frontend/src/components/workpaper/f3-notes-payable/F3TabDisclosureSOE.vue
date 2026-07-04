<script setup lang="ts">
/** F3TabDisclosureSOE — 附注披露（国企）| Task 9.2 */
import { toRef, type Ref } from 'vue'
import { useF3DisclosureSoe } from '../composables/useF3DisclosureSoe'
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
  isApplicable, section1Rows, section1Subtotal, dynamicRows,
  noteText, addRow, removeRow, updateCell,
} = useF3DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})
</script>

<template>
  <div class="f3-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

    <template v-else>
      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 应付票据分类
          <el-tag size="small" type="info">跨sheet取数</el-tag>
          <GtIndexChip target="F3-1" label="→F3-1" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
          <el-table-column prop="label" label="项目" width="200" />
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmount(row.endAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmount(row.priorAmount) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 补充披露
          <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加</el-button>
        </h4>
        <el-table :data="dynamicRows" size="small" border stripe>
          <el-table-column prop="label" label="项目" width="200">
            <template #default="{ row }">
              <el-input :model-value="row.label" size="small" :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'label', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.endAmount" :controls="false" size="small"
                :disabled="isReadonly" style="width:100%"
                @change="(v: number) => updateCell(row.rowId, 'endAmount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.priorAmount" :controls="false" size="small"
                :disabled="isReadonly" style="width:100%"
                @change="(v: number) => updateCell(row.rowId, 'priorAmount', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
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
.f3-disclosure-soe { font-size: 13px; }
.disclosure-card { margin-bottom: 16px; }
.card-title { margin: 0 0 8px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.cross-sheet-cell { color: #409eff; }
.note-area { margin-top: 12px; }
.note-prefix { font-weight: 600; display: block; margin-bottom: 4px; }
</style>
