<script setup lang="ts">
/** F2TabDisclosureSoe — 附注披露（国企） */
import { toRef, type Ref } from 'vue'
import { useF2DisclosureSoe } from '../../composables/useF2DisclosureSoe'
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

const { isApplicable, rows, subtotal, noteText, dataUpdatedVisible } = useF2DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})
</script>

<template>
  <div class="f2-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

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
          存货分类披露
          <GtIndexChip value="F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...rows, subtotal]" size="small" border stripe>
          <el-table-column prop="label" label="存货类别" width="180">
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
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
.f2-disclosure-soe { padding: 12px; font-size: 13px; }
.update-bar { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 20px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
</style>
