<script setup lang="ts">
/** F2TabDisclosureListed — 附注披露（上市） */
import { toRef, type Ref } from 'vue'
import { useF2DisclosureListed } from '../../composables/useF2DisclosureListed'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  applicableStandards: string[]
}>()

function fmtAmount(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  isApplicable, section1Rows, section1Subtotal, section2Rows, section2Subtotal,
  noteText, dataUpdatedVisible, addRow, removeRow, updateCell,
} = useF2DisclosureListed({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})
</script>

<template>
  <div class="f2-disclosure-listed">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />

    <template v-else>
      <el-alert
        v-if="dataUpdatedVisible"
        type="info"
        title="审定表数据已更新，附注分类披露已自动刷新"
        :closable="false"
        show-icon
        class="update-bar"
      />

      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 存货分类披露
          <el-tooltip content="数据来源：F2-1审定表各类别净值" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
          <el-table-column prop="label" label="存货类别" width="180">
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.priorAmount) }}</span>
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
              <el-button v-if="row.rowId !== '__subtotal__' && !isReadonly" size="small" type="danger" link
                @click="removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">附注说明文字</h4>
        <el-input v-model="noteText" type="textarea" :rows="4" :disabled="isReadonly" placeholder="附注披露说明..." />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-listed { padding: 12px; font-size: 13px; }
.update-bar { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 20px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
.cross-sheet-cell { color: #409eff; }
</style>
