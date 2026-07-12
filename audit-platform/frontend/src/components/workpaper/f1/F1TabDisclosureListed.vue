<template>
<div class="d3-disclosure-listed">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 上市公司应按CAS30财务报表列报要求，分别披露预付账款（科目1123）按性质分类和按账龄分类情况。</p>
        <p>2. 账龄超过1年的重要预付账款应逐户披露，说明未结转原因。</p>
        <p>3. 重大变动应说明变动原因，包括新签大额合同、大额结转等情形。</p>
        <p>4. 跨sheet取数单元格（浅蓝色背景）自动从 F1-1 审定表同步，无需手动维护。</p>
      </div>
    </details>

    <!-- 子节一：按性质分类 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付账款按性质分类
        <span class="cross-sheet-badge">
          <el-tooltip content="数据来源：F1-1审定表按性质分类区块" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
        </span>
        <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
      </h4>
      <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="项目" width="200">
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
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note1" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
          placeholder="按性质分类的附注披露说明..." />
      </div>
    </div>

    <!-- 子节二：超1年重要预收 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预付账款
        <el-button size="small" :disabled="isReadonly" @click="addRow(2)">+ 添加</el-button>
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
                @change="(val: string) => updateCell(2, row.rowId, 'label', val)" />
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
                @change="(val: any) => updateCell(2, row.rowId, 'endAmount', val)" />
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
                @change="(val: any) => updateCell(2, row.rowId, 'priorAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="140">
          <template #default="{ row }">
            <template v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'">
              <el-input v-model="row.reason" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(2, row.rowId, 'reason', val)" />
            </template>
            <span v-else>{{ row.reason || '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-popconfirm v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'" title="删除？" @confirm="removeRow(2, row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note2" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
          placeholder="超1年预收的附注披露说明..." />
      </div>
    </div>

    <!-- 子节三：重大变动 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 重大变动说明
        <el-button size="small" :disabled="isReadonly" @click="addRow(3)">+ 添加</el-button>
      </h4>
      <el-table :data="[...section3Rows, section3Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="项目" width="180">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else>
              <el-input v-model="row.label" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(3, row.rowId, 'label', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-val">{{ fmtAmount(row.endAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.endAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(3, row.rowId, 'endAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-val">{{ fmtAmount(row.priorAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.priorAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(3, row.rowId, 'priorAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="变动原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.reason" size="small" :disabled="isReadonly"
              @change="(val: string) => updateCell(3, row.rowId, 'reason', val)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-popconfirm v-if="row.rowId !== '__subtotal__'" title="删除？" @confirm="removeRow(3, row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note3" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
          placeholder="重大变动的附注披露说明..." />
      </div>
    </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabDisclosureListed.vue — 附注披露（上市公司）
 * 3子节卡片 + 跨sheet取数 + 动态行 + 合计 + 说明 + 编制提示
 */
import { computed, ref, toRef, type Ref } from 'vue'
import { useF1DisclosureListed } from '../composables/useF1DisclosureListed'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

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
  note1,
  section2Rows,
  section2Subtotal,
  note2,
  section3Rows,
  section3Subtotal,
  note3,
  addRow,
  removeRow,
  updateCell,
} = useF1DisclosureListed({
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
.d3-disclosure-listed { padding: 16px; }
.d3-disclosure-listed :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.d3-disclosure-listed :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

.disclosure-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.cross-sheet-badge { font-weight: normal; }
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.note-area { margin-top: 12px; display: flex; align-items: flex-start; gap: 8px; }
.note-prefix { font-size: var(--wp-font-size, 13px); color: #606266; white-space: nowrap; padding-top: 6px; }
</style>
