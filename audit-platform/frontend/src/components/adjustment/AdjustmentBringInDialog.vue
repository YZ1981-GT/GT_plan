<!--
  AdjustmentBringInDialog — 明细行带入调整分录（三模式）
  spec: adjustment-collaboration-and-propagation (Part B / Req5)

  列出该行对应科目匹配的调整明细行，三模式带入：
    单行带入 / 选定多行合计带入 / 全部求和带入。
  emit bring-in { amount(净=借-贷), debitTotal, creditTotal, adjustmentType, sourceEntryRefs, lineCount }。
  只输出通用载荷，由各明细表 tab 映射到自身调整列（账项调整/重分类调整）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="带入调整分录"
    width="680px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div class="gt-bring-in">
      <div class="gt-bring-in-head">
        <span>科目：{{ accountLabel || '—' }}</span>
        <el-tag size="small" type="info" effect="plain">匹配 {{ matches.length }} 笔</el-tag>
      </div>

      <el-radio-group v-model="mode" size="small" style="margin-bottom: 10px">
        <el-radio-button label="single">单行带入</el-radio-button>
        <el-radio-button label="multi">多选合计带入</el-radio-button>
        <el-radio-button label="all">全部求和带入</el-radio-button>
      </el-radio-group>

      <el-empty v-if="!matches.length" description="无匹配调整分录" :image-size="60" />

      <!-- 单行：radio 选择 -->
      <el-table v-else-if="mode === 'single'" :data="matches" border size="small" max-height="320">
        <el-table-column width="46">
          <template #default="{ $index }">
            <el-radio v-model="singleIdx" :label="$index"><span /></el-radio>
          </template>
        </el-table-column>
        <el-table-column label="来源/编号" min-width="130">
          <template #default="{ row }">
            {{ row.source_wp_code ? row.source_wp_code + ' · ' : '' }}{{ row.adjustment_no }}
            <el-tag size="small" :type="row.adjustment_type === 'rje' ? 'warning' : 'primary'" effect="plain">{{ row.adjustment_type?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140" show-overflow-tooltip prop="description" />
        <el-table-column label="借方" width="110" align="right"><template #default="{ row }">{{ fmt(row.debit_amount) }}</template></el-table-column>
        <el-table-column label="贷方" width="110" align="right"><template #default="{ row }">{{ fmt(row.credit_amount) }}</template></el-table-column>
      </el-table>

      <!-- 多选：checkbox -->
      <el-table v-else-if="mode === 'multi'" :data="matches" border size="small" max-height="320" @selection-change="onSel">
        <el-table-column type="selection" width="40" />
        <el-table-column label="来源/编号" min-width="130">
          <template #default="{ row }">
            {{ row.source_wp_code ? row.source_wp_code + ' · ' : '' }}{{ row.adjustment_no }}
            <el-tag size="small" :type="row.adjustment_type === 'rje' ? 'warning' : 'primary'" effect="plain">{{ row.adjustment_type?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140" show-overflow-tooltip prop="description" />
        <el-table-column label="借方" width="110" align="right"><template #default="{ row }">{{ fmt(row.debit_amount) }}</template></el-table-column>
        <el-table-column label="贷方" width="110" align="right"><template #default="{ row }">{{ fmt(row.credit_amount) }}</template></el-table-column>
      </el-table>

      <!-- 全部 -->
      <el-table v-else :data="matches" border size="small" max-height="320">
        <el-table-column label="来源/编号" min-width="130">
          <template #default="{ row }">
            {{ row.source_wp_code ? row.source_wp_code + ' · ' : '' }}{{ row.adjustment_no }}
            <el-tag size="small" :type="row.adjustment_type === 'rje' ? 'warning' : 'primary'" effect="plain">{{ row.adjustment_type?.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140" show-overflow-tooltip prop="description" />
        <el-table-column label="借方" width="110" align="right"><template #default="{ row }">{{ fmt(row.debit_amount) }}</template></el-table-column>
        <el-table-column label="贷方" width="110" align="right"><template #default="{ row }">{{ fmt(row.credit_amount) }}</template></el-table-column>
      </el-table>

      <div v-if="matches.length" class="gt-bring-in-summary">
        将带入净额（借-贷）：<b>{{ fmt(preview.amount) }}</b>
        <span class="gt-bring-in-sub">（借 {{ fmt(preview.debitTotal) }} / 贷 {{ fmt(preview.creditTotal) }}，{{ preview.lineCount }} 行，类型 {{ preview.adjustmentType.toUpperCase() }}）</span>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!canBringIn" @click="doBringIn">带入</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts">
// 普通 script 块承载命名导出（<script setup> 内禁止 export，否则 Vite 编译报错）。
import type { AdjustmentLineMatch } from '@/components/workpaper/composables/useAdjustmentDetailPropagation'

export interface BringInPayload {
  amount: number            // 净额 = Σ借 - Σ贷
  debitTotal: number
  creditTotal: number
  adjustmentType: 'aje' | 'rje' | 'mixed'
  sourceEntryRefs: string[] // 去重的 entry_group_id
  lineCount: number
}

/** 纯函数：对一组匹配行求带入载荷（供单测；全部求和 == 全选多选合计）。 */
export function sumBringIn(lines: AdjustmentLineMatch[]): BringInPayload {
  let debitTotal = 0
  let creditTotal = 0
  const types = new Set<string>()
  const refs = new Set<string>()
  for (const l of lines) {
    debitTotal += Number(l.debit_amount) || 0
    creditTotal += Number(l.credit_amount) || 0
    if (l.adjustment_type) types.add(l.adjustment_type)
    if (l.entry_group_id) refs.add(l.entry_group_id)
  }
  const adjustmentType = types.size === 1 ? (Array.from(types)[0] as 'aje' | 'rje') : 'mixed'
  return {
    amount: Math.round((debitTotal - creditTotal) * 100) / 100,
    debitTotal: Math.round(debitTotal * 100) / 100,
    creditTotal: Math.round(creditTotal * 100) / 100,
    adjustmentType,
    sourceEntryRefs: Array.from(refs),
    lineCount: lines.length,
  }
}
</script>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { AdjustmentLineMatch } from '@/components/workpaper/composables/useAdjustmentDetailPropagation'

const props = defineProps<{
  modelValue: boolean
  matches: AdjustmentLineMatch[]
  accountLabel?: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'bring-in', payload: BringInPayload): void }>()

const mode = ref<'single' | 'multi' | 'all'>('single')
const singleIdx = ref<number>(-1)
const multiSel = ref<AdjustmentLineMatch[]>([])

watch(() => props.modelValue, (v) => { if (v) { mode.value = 'single'; singleIdx.value = -1; multiSel.value = [] } })

function onSel(rows: AdjustmentLineMatch[]): void { multiSel.value = rows }

const selectedLines = computed<AdjustmentLineMatch[]>(() => {
  if (mode.value === 'all') return props.matches
  if (mode.value === 'multi') return multiSel.value
  return singleIdx.value >= 0 && props.matches[singleIdx.value] ? [props.matches[singleIdx.value]] : []
})

const preview = computed(() => sumBringIn(selectedLines.value))
const canBringIn = computed(() => selectedLines.value.length > 0)

function fmt(v: number): string {
  return (Number(v) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function doBringIn(): void {
  if (!canBringIn.value) { ElMessage.warning('请先选择要带入的调整行'); return }
  emit('bring-in', sumBringIn(selectedLines.value))
  emit('update:modelValue', false)
}
</script>

<style scoped>
.gt-bring-in { font-size: 13px; }
.gt-bring-in-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.gt-bring-in-summary { margin-top: 10px; padding: 8px 10px; background: var(--el-fill-color-light); border-radius: 6px; }
.gt-bring-in-sub { color: var(--el-text-color-secondary); font-size: 12px; margin-left: 6px; }
</style>
