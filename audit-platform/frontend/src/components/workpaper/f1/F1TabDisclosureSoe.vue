<template>
<div class="d3-disclosure-soe">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 国有企业应按《企业财务报告条例》和国资委监管要求，分别披露预付账款（科目1123）按账龄分类和超1年重要预收情况。</p>
        <p>2. 账龄分类简化为"1年以内"和"1年以上"两档。</p>
        <p>3. 账龄超过1年的重要预付账款应逐户披露，说明未结转原因。</p>
        <p>4. 跨sheet取数（浅蓝色背景）自动从 F1-1 审定表按账龄分类区块同步。</p>
      </div>
    </details>

    <!-- 子节一：按账龄分类 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付账款按账龄分类
        <el-tooltip content="数据来源：F1-1审定表按账龄分类区块" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
      </h4>
      <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="账龄" width="160">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">
              {{ fmtAmount(row.endAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">
              {{ fmtAmount(row.priorAmount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 子节二：超1年重要预收 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预付账款
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加</el-button>
      </h4>
      <el-table :data="[...section2Rows, section2Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="对方单位" width="160">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else-if="row.rowId?.startsWith('cs-')">
              <span class="cross-sheet-cell">{{ row.label }}</span>
            </template>
            <template v-else>
              <el-input v-model="row.label" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(row.rowId, 'label', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__' || row.rowId?.startsWith('cs-')">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ fmtAmount(row.endAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.endAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(row.rowId, 'endAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__' || row.rowId?.startsWith('cs-')">
              <span>{{ fmtAmount(row.priorAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.priorAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(row.rowId, 'priorAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="140">
          <template #default="{ row }">
            <template v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'">
              <el-input v-model="row.reason" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(row.rowId, 'reason', val)" />
            </template>
            <span v-else>{{ row.reason || '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-popconfirm v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'" title="删除？" @confirm="removeRow(row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

  </template>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabDisclosureSoe.vue — 附注披露（国企）
 * 2子节卡片 + 跨sheet取数 + 动态行 + 合计 + applicable_standards判断
 */
import { computed, toRef, type Ref } from 'vue'
import { useF1DisclosureSoe } from '../composables/useF1DisclosureSoe'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  applicableStandards: string[]
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const {
  isApplicable,
  section1Rows,
  section1Subtotal,
  section2Rows,
  section2Subtotal,
  addRow,
  removeRow,
  updateCell,
} = useF1DisclosureSoe({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as unknown as Ref<string[]>,
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d3-disclosure-soe { padding: 16px; }
.d3-disclosure-soe :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.d3-disclosure-soe :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

.disclosure-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
</style>
