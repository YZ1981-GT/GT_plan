<script setup lang="ts">
/**
 * E1TabAdjudication.vue — E1-1 货币资金审定表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.1
 *
 * 渲染：
 * - 固定项目行矩阵 el-table（项目名称 | 期初未审数 | 期初账项调整 | 期初审定数 |
 *   期末未审数 | 期末账项调整 | 期末审定数 | 变动额 | 变动率 | 原因分析）
 * - 变动率>30% → 红色高亮
 * - 合计/试算平衡/差异行 → bold背景
 * - AI按钮生成原因分析
 * - el-skeleton加载占位
 *
 * Requirements: 1.1-1.7, 12.1-12.5
 */
import { ref, inject, computed, toRef, onMounted, type Ref } from 'vue'
import {
  useE1Adjudication,
  type UseE1BaseOptions,
  type AdjRow,
} from '../composables/useE1Adjudication'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  isLoading,
  isRateExceeding,
  hasDifference,
  saveVarianceNote,
  aiGenerateNote,
} = useE1Adjudication(options)

// ─── AI Generation ───────────────────────────────────────────────────────────

const aiLoadingKey = ref<string | null>(null)

async function handleAiGenerate(row: AdjRow): Promise<void> {
  if (props.isReadonly) return
  aiLoadingKey.value = row.itemKey
  try {
    const text = await aiGenerateNote(row.itemKey)
    if (text) {
      saveVarianceNote(row.itemKey, text)
    }
  } finally {
    aiLoadingKey.value = null
  }
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtRate(rate: number | ''): string {
  if (rate === '' || rate === 0) return '-'
  return (rate * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: AdjRow }): string {
  const classes: string[] = []
  if (row.isSubtotal || row.itemKey === 'total' || row.itemKey === 'tb_amount' || row.itemKey === 'diff') {
    classes.push('e1-adj-subtotal-row')
  }
  if (isRateExceeding(row)) {
    classes.push('e1-adj-red-highlight')
  }
  if (row.itemKey === 'diff' && hasDifference()) {
    classes.push('e1-adj-red-highlight')
  }
  return classes.join(' ')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // hydration is done inside composable
})
</script>

<template>
  <div class="e1-tab-adjudication">
    <el-skeleton :loading="isLoading" :rows="12" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :row-class-name="getRowClass"
          style="width: 100%"
          max-height="680"
        >
          <!-- 项目名称 -->
          <el-table-column
            prop="itemName"
            label="项目名称"
            fixed="left"
            width="200"
          >
            <template #default="{ row }">
              <span :class="{ 'font-bold': row.isSubtotal || row.isReadonly }">
                {{ row.itemName }}
              </span>
            </template>
          </el-table-column>

          <!-- 期初未审数 -->
          <el-table-column label="期初未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期初账项调整 -->
          <el-table-column label="期初账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期初审定数 -->
          <el-table-column label="期初审定数" width="130" align="right">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.openingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 期末未审数 -->
          <el-table-column label="期末未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期末账项调整 -->
          <el-table-column label="期末账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期末审定数 -->
          <el-table-column label="期末审定数" width="130" align="right">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.endingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 变动额 -->
          <el-table-column label="变动额" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.changeAmount) }}
            </template>
          </el-table-column>

          <!-- 变动率 -->
          <el-table-column label="变动率" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'red-text': isRateExceeding(row) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="220">
            <template #default="{ row }">
              <div v-if="row.isReadonly && row.itemKey !== 'diff'" class="readonly-cell">
                {{ row.varianceNote || '-' }}
              </div>
              <div v-else class="note-cell">
                <el-input
                  type="textarea"
                  :model-value="row.varianceNote"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="填写原因分析"
                  @change="(val: string) => saveVarianceNote(row.itemKey, val)"
                />
                <el-button
                  v-if="!isReadonly"
                  :loading="aiLoadingKey === row.itemKey"
                  size="small"
                  type="primary"
                  text
                  class="ai-btn"
                  @click="handleAiGenerate(row)"
                >
                  🤖
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-adjudication {
  padding: 12px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.red-text {
  color: #f56c6c;
  font-weight: 600;
}
.readonly-cell {
  color: #909399;
}
.note-cell {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.note-cell .el-textarea {
  flex: 1;
}
.ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}
.font-bold {
  font-weight: 700;
}

:deep(.e1-adj-subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 700;
}
:deep(.e1-adj-red-highlight) {
  background-color: #fef0f0 !important;
}
:deep(.e1-adj-red-highlight td) {
  color: #f56c6c;
}
</style>
