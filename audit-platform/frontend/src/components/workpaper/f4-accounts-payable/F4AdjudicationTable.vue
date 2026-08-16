<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/** F4AdjudicationTable — F4-1 双分类审定表通用宽表。 */
import type {
  F4AdjudicationRow,
  F4AdjudicationSection,
  StoredF4AdjRow,
} from '../composables/useF4Adjudication'

defineProps<{
  section: F4AdjudicationSection
  rows: F4AdjudicationRow[]
  readonly: boolean
  aiAvailable: boolean
  aiLoading: boolean
}>()

const emit = defineEmits<{
  (event: 'update', rowKey: string, field: keyof StoredF4AdjRow, value: unknown): void
  (event: 'ai-reason', row: F4AdjudicationRow): void
}>()

function amount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function rate(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function update(rowKey: string, field: keyof StoredF4AdjRow, value: unknown): void {
  emit('update', rowKey, field, value)
}
</script>

<template>
  <div class="table-scroll">
    <el-table :data="rows" border size="small" row-key="rowKey" class="adjudication-table">
      <el-table-column prop="label" label="项目" width="138" fixed>
        <template #default="{ row }">
          <strong v-if="!row.isEditable">{{ row.label }}</strong>
          <span v-else>{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column prop="openingUnadjusted" label="未审数" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly"
              :model-value="row.openingUnadjusted"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'openingUnadjusted', value ?? 0)"
            />
            <span v-else>{{ amount(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="openingAje" label="账项调整" width="112" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly"
              :model-value="row.openingAje"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'openingAje', value ?? 0)"
            />
            <span v-else>{{ amount(row.openingAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="openingRje" label="重分类调整" width="112" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly"
              :model-value="row.openingRje"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'openingRje', value ?? 0)"
            />
            <span v-else>{{ amount(row.openingRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="openingAdjusted" label="审定数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="期初审定数 = 未审数 + 账项调整 + 重分类调整">
              <span class="formula audited">{{ amount(row.openingAdjusted) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column prop="closingUnadjusted" label="未审数" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly && !row.closingFromDetail"
              :model-value="row.closingUnadjusted"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'closingUnadjusted', value ?? 0)"
            />
            <el-tooltip v-else-if="row.closingFromDetail" content="自动汇总自 F4-2 应付账款明细表">
              <span class="linked">{{ amount(row.closingUnadjusted) }}</span>
            </el-tooltip>
            <span v-else>{{ amount(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="closingAje" label="账项调整" width="112" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly && !row.closingFromDetail"
              :model-value="row.closingAje"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'closingAje', value ?? 0)"
            />
            <span v-else :class="{ linked: row.closingFromDetail }">{{ amount(row.closingAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="closingRje" label="重分类调整" width="112" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !readonly && !row.closingFromDetail"
              :model-value="row.closingRje"
              size="small"
              @change="(value: number | undefined) => update(row.rowKey, 'closingRje', value ?? 0)"
            />
            <span v-else :class="{ linked: row.closingFromDetail }">{{ amount(row.closingRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="closingAdjusted" label="审定数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末审定数 = 未审数 + 账项调整 + 重分类调整">
              <span class="formula audited">{{ amount(row.closingAdjusted) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期审定数与上期审定数比较" align="center">
        <el-table-column prop="changeAmount" label="变动额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ material: Math.abs(row.changeRate) > 0.3 }">{{ amount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="changeRate" label="变动率" width="94" align="right">
          <template #default="{ row }">
            <el-tag v-if="Math.abs(row.changeRate) > 0.3" type="warning" size="small">
              {{ rate(row.changeRate) }}
            </el-tag>
            <span v-else>{{ rate(row.changeRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column prop="reasonAnalysis" label="原因分析" min-width="210" fixed="right">
        <template #default="{ row }">
          <template v-if="row.isEditable">
            <div class="reason-actions">
              <el-button
                link
                type="primary"
                size="small"
                :disabled="readonly || !aiAvailable"
                :loading="aiLoading"
                @click="emit('ai-reason', row)"
              >AI</el-button>
            </div>
            <el-input
              v-if="!readonly"
              :model-value="row.reasonAnalysis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="说明余额变动原因"
              @change="(value: string) => update(row.rowKey, 'reasonAnalysis', value)"
            />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.table-scroll { overflow-x: auto; }
.adjudication-table { min-width: 1420px; font-size: var(--wp-font-size, 13px); }
.adjudication-table :deep(.el-input-number) { width: 100%; }
.formula { border-bottom: 1px dashed #b7bcc5; cursor: help; }
.audited { color: #315a8a; font-weight: 600; }
.linked { color: #7b4ba3; font-weight: 600; }
.material { color: #d97706; font-weight: 700; }
.reason-actions { display: flex; justify-content: flex-end; height: 20px; }
</style>
