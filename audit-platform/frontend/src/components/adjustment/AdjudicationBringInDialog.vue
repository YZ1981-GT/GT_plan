<!--
  AdjudicationBringInDialog — 集中登记调整分录 → 审定表(X-1) 带入 AJE/RJE
  spec: adjustment-collaboration-and-propagation (审定表带入增强 / K12 试点)

  列出命中本科目的集中调整分录，逐笔分配到审定表目标分类行（解决 科目↔分类 歧义）：
    - 每笔调整默认智能猜测目标行（名称匹配→含"其他"→末行），审计师可改；
    - aje 型分录带入目标行 AJE 列，rje 型带入 RJE 列（净发生额按方向计算）。
  emit apply { allocations: [{ rowKey, aje, rje }] }（按目标行聚合），由审定表累加到对应列。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="带入调整分录（审定表）"
    width="760px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div class="gt-adj-bring-in" v-loading="loading">
      <div class="gt-abi-head">
        <span>科目：{{ subjectLabel || '—' }}</span>
        <el-tag size="small" type="info" effect="plain">命中 {{ matches.length }} 笔调整分录</el-tag>
      </div>

      <el-empty v-if="!matches.length && !loading" description="无命中本科目的调整分录" :image-size="60" />

      <el-table v-else :data="matches" border size="small" max-height="360">
        <el-table-column label="来源/编号" min-width="150">
          <template #default="{ row }">
            <span v-if="row.source_wp_code" class="gt-abi-src">{{ row.source_wp_code }} · </span>{{ row.adjustment_no }}
            <el-tag size="small" :type="row.adjustment_type === 'rje' ? 'warning' : 'primary'" effect="plain">
              {{ row.adjustment_type.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="150" show-overflow-tooltip prop="description" />
        <el-table-column label="净发生额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'gt-abi-neg': row.net < 0 }">{{ fmt(row.net) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="带入目标行" min-width="180">
          <template #default="{ row }">
            <el-select v-model="targetMap[row.entry_group_id]" size="small" style="width: 100%" placeholder="选择目标分类行">
              <el-option v-for="r in rowOptions" :key="r.rowKey" :label="r.name" :value="r.rowKey" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="matches.length" class="gt-abi-summary">
        将按目标行累加：<b>AJE 合计 {{ fmt(totalAje) }}</b> · <b>RJE 合计 {{ fmt(totalRje) }}</b>
        <div class="gt-abi-hint">带入后审定数变化将自动联动披露表与附注（substantive:adjudicated）。</div>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!matches.length" @click="doApply">带入</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts">
// 普通 script 块承载命名导出（<script setup> 内禁止 export）。
import type { AdjudicationAdjMatch } from '@/components/workpaper/composables/useAdjudicationAdjustmentPull'

export interface AdjudicationAllocation {
  rowKey: string
  aje: number
  rje: number
}
</script>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { AdjudicationAdjMatch } from '@/components/workpaper/composables/useAdjudicationAdjustmentPull'
import { guessTargetRowKey } from '@/components/workpaper/composables/useAdjudicationAdjustmentPull'

interface RowOption { rowKey: string; name: string }

const props = defineProps<{
  modelValue: boolean
  matches: AdjudicationAdjMatch[]
  rowOptions: RowOption[]
  subjectLabel?: string
  loading?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'apply', payload: { allocations: AdjudicationAllocation[] }): void
}>()

/** entry_group_id → 目标行 rowKey */
const targetMap = ref<Record<string, string>>({})

// 打开或匹配变化时，重置并智能猜测目标行
watch(
  () => [props.modelValue, props.matches] as const,
  ([visible]) => {
    if (!visible) return
    const map: Record<string, string> = {}
    for (const m of props.matches) {
      map[m.entry_group_id] = guessTargetRowKey(m, props.rowOptions)
    }
    targetMap.value = map
  },
  { immediate: true, deep: true },
)

function fmt(v: number): string {
  return (Number(v) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const totalAje = computed(() =>
  props.matches.filter((m) => m.adjustment_type === 'aje').reduce((s, m) => s + m.net, 0),
)
const totalRje = computed(() =>
  props.matches.filter((m) => m.adjustment_type === 'rje').reduce((s, m) => s + m.net, 0),
)

function doApply(): void {
  const agg = new Map<string, AdjudicationAllocation>()
  for (const m of props.matches) {
    const rowKey = targetMap.value[m.entry_group_id]
    if (!rowKey) continue
    const cur = agg.get(rowKey) || { rowKey, aje: 0, rje: 0 }
    if (m.adjustment_type === 'rje') cur.rje += m.net
    else cur.aje += m.net
    agg.set(rowKey, cur)
  }
  const allocations = Array.from(agg.values()).map((a) => ({
    rowKey: a.rowKey,
    aje: Math.round(a.aje * 100) / 100,
    rje: Math.round(a.rje * 100) / 100,
  }))
  if (!allocations.length) {
    ElMessage.warning('请为调整分录选择带入目标行')
    return
  }
  emit('apply', { allocations })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.gt-adj-bring-in { font-size: 13px; }
.gt-abi-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.gt-abi-src { color: var(--el-color-primary); }
.gt-abi-neg { color: var(--el-color-danger); }
.gt-abi-summary { margin-top: 10px; padding: 8px 10px; background: var(--el-fill-color-light); border-radius: 6px; }
.gt-abi-hint { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
</style>
