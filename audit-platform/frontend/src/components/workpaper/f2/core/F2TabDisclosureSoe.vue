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
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 存货分类披露的期末/期初余额自 F2-1 审定表各类别净值自动取数（跨 sheet，只读）。</p>
          <p>2. 依《企业会计准则第 1 号——存货》，应按存货类别披露账面价值及跌价准备计提情况。</p>
          <p>3. 国有企业需按主管部门要求补充披露存货减值、周转及积压情况。</p>
          <p>4. 审定表数据更新后本表自动刷新，请核对分类合计与报表一致。</p>
        </div>
      </details>

      <!-- 工具栏 -->
      <div class="tab-toolbar">
        <div class="toolbar-left" />
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        </div>
      </div>

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
          <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
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
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="附注披露说明..." />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-soe { padding: 12px; font-size: 13px; }
.f2-disclosure-soe :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-disclosure-soe :deep(.el-table .cell) { font-size: 13px !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.update-bar { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 20px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
</style>
