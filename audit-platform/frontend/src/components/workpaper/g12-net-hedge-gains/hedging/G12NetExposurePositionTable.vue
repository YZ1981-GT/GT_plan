<template>
  <el-table :data="rows" border size="small" class="position-table" :row-class-name="rowClassName">
    <el-table-column label="#" prop="seq" width="44" fixed />

    <el-table-column label="套期关系编号" width="110" fixed>
      <template #default="{ row }">
        <el-input v-model="row.hedgeRelationId" size="small" :disabled="isReadonly"
          placeholder="↔ G12-2/6"
          @change="() => ne.updateCell(row.rowId, 'hedgeRelationId', row.hedgeRelationId)" />
      </template>
    </el-table-column>

    <el-table-column label="项目" min-width="130" fixed>
      <template #default="{ row }">
        <el-input v-model="row.item" size="small" type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
          placeholder="如：预期销售和预期采购的外汇净头寸"
          @change="() => ne.updateCell(row.rowId, 'item', row.item)" />
      </template>
    </el-table-column>

    <el-table-column label="币种" width="108" fixed>
      <template #default="{ row }">
        <el-select v-model="row.currency" size="small" :disabled="isReadonly" filterable allow-create
          default-first-option class="currency-select"
          @change="(v: string) => ne.updateCell(row.rowId, 'currency', v)">
          <el-option v-for="c in G12_NET_EXPOSURE_CURRENCIES" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
      </template>
    </el-table-column>

    <el-table-column label="头寸1" min-width="160">
      <template #header>
        <div class="col-head">
          <span>头寸1</span>
          <span class="col-sub">头寸 / 金额</span>
        </div>
      </template>
      <template #default="{ row }">
        <el-input v-model="row.position1Desc" size="small" :disabled="isReadonly"
          placeholder="预期外币销售收入"
          @change="() => ne.updateCell(row.rowId, 'position1Desc', row.position1Desc)" />
        <el-input v-model="row.position1Amount" size="small" class="amount-input" :disabled="isReadonly"
          :placeholder="amountPlaceholder(row.currency)"
          @change="() => ne.updateCell(row.rowId, 'position1Amount', row.position1Amount)" />
      </template>
    </el-table-column>

    <el-table-column label="头寸2" min-width="160">
      <template #header>
        <div class="col-head">
          <span>头寸2</span>
          <span class="col-sub">头寸 / 金额</span>
        </div>
      </template>
      <template #default="{ row }">
        <el-input v-model="row.position2Desc" size="small" :disabled="isReadonly"
          placeholder="预期外币固定资产采购"
          @change="() => ne.updateCell(row.rowId, 'position2Desc', row.position2Desc)" />
        <el-input v-model="row.position2Amount" size="small" class="amount-input" :disabled="isReadonly"
          :placeholder="amountPlaceholder(row.currency, '1,200')"
          @change="() => ne.updateCell(row.rowId, 'position2Amount', row.position2Amount)" />
      </template>
    </el-table-column>

    <el-table-column label="净头寸" min-width="130">
      <template #default="{ row, $index }">
        <el-input v-model="row.netPosition" size="small" :disabled="isReadonly"
          :placeholder="netPlaceholder(row.currency)"
          @change="() => ne.updateCell(row.rowId, 'netPosition', row.netPosition)" />
        <el-button
          v-if="hintAt(row.rowId, $index) && hintAt(row.rowId, $index) !== row.netPosition"
          link size="small" type="primary" :disabled="isReadonly"
          @click="ne.applyNetPositionHint(row.rowId)"
        >采用建议：{{ hintAt(row.rowId, $index) }}</el-button>
      </template>
    </el-table-column>

    <el-table-column label="支持性证据" min-width="168">
      <template #header>
        <div class="col-head">
          <span>支持性证据</span>
          <span class="col-sub">类型 / 明细</span>
        </div>
      </template>
      <template #default="{ row }">
        <el-select
          v-model="row.evidenceType"
          size="small"
          :disabled="isReadonly"
          clearable
          placeholder="证据类型"
          class="evidence-type-select"
          @change="(v: string) => ne.updateCell(row.rowId, 'evidenceType', v || '')"
        >
          <el-option
            v-for="t in G12_NET_EXPOSURE_EVIDENCE_TYPES"
            :key="t.value"
            :label="t.label"
            :value="t.value"
          />
        </el-select>
        <el-input
          v-model="row.supportingEvidence"
          size="small"
          class="evidence-detail"
          :disabled="isReadonly"
          placeholder="证据明细/备注"
          @change="() => ne.updateCell(row.rowId, 'supportingEvidence', row.supportingEvidence)"
        />
      </template>
    </el-table-column>

    <el-table-column label="套期工具" min-width="110">
      <template #default="{ row }">
        <el-input v-model="row.hedgingInstrument" size="small" :disabled="isReadonly"
          @change="() => ne.updateCell(row.rowId, 'hedgingInstrument', row.hedgingInstrument)" />
      </template>
    </el-table-column>

    <el-table-column label="索引号" width="140">
      <template #default="{ row }">
        <template v-if="!isReadonly">
          <el-select
            v-model="row.indexRef"
            size="small"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="选/填索引"
            class="index-select"
            @change="(v: string) => ne.updateCell(row.rowId, 'indexRef', v || '')"
          >
            <el-option
              v-for="opt in indexSuggestions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
        <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
      </template>
    </el-table-column>

    <el-table-column label="" width="88" fixed="right">
      <template #default="{ row }">
        <el-button link type="primary" size="small" :disabled="isReadonly"
          @click="ne.addCurrencyRow(row.rowId)">+币种</el-button>
        <el-button link type="danger" size="small" :disabled="isReadonly || totalRows <= 1"
          @click="ne.removeRow(row.rowId)">删</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { G12NetExposureCrossIssue } from '../../composables/g12NetExposureCross'
import { amountPlaceholder, currencyUnitLabel } from '../../composables/g12NetExposureCalc'
import {
  G12_NET_EXPOSURE_CURRENCIES,
  G12_NET_EXPOSURE_EVIDENCE_TYPES,
} from '../../composables/g12Constants'
import { collectG12NetExposureIndexSuggestions } from '../../composables/g12NetExposureEvidence'
import type { G12NetExposureRow } from '../../composables/useG12NetExposure'
import type { useG12NetExposure } from '../../composables/useG12NetExposure'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  rows: G12NetExposureRow[]
  totalRows: number
  isReadonly: boolean
  ne: ReturnType<typeof useG12NetExposure>
  crossIssues: G12NetExposureCrossIssue[]
  allResponses: Map<string, ChecklistResponse>
}>()

const indexSuggestions = computed(() =>
  collectG12NetExposureIndexSuggestions(
    props.allResponses,
    props.ne.rows.value.map((r) => r.indexRef).filter(Boolean),
  ),
)

function hintAt(rowId: string, index: number): string {
  const globalIdx = props.ne.rows.value.findIndex((r) => r.rowId === rowId)
  const idx = globalIdx >= 0 ? globalIdx : index
  return props.ne.netPositionHints.value[idx] ?? ''
}

function netPlaceholder(currency: string): string {
  const unit = currencyUnitLabel(currency)
  return unit ? `支付200万${unit}` : '支付200'
}

function rowClassName({ row }: { row: G12NetExposureRow }): string {
  const classes: string[] = []
  if (!row.item.trim() || !row.currency.trim() || !row.position1Desc.trim() || !row.position2Desc.trim() || !row.netPosition.trim()) {
    classes.push('g12-ne-incomplete')
  }
  if (props.crossIssues.some((i) => i.rowId === row.rowId)) {
    classes.push('g12-ne-cross')
  }
  return classes.join(' ')
}
</script>

<style scoped>
.position-table { margin-bottom: 12px; font-size: 13px; }
.col-head { display: flex; flex-direction: column; line-height: 1.2; }
.col-sub { font-size: 11px; color: #909399; font-weight: 400; }
.amount-input { margin-top: 4px; }
.currency-select { width: 100%; }
.evidence-type-select { width: 100%; }
.evidence-detail { margin-top: 4px; }
.index-select { width: 100%; }
:deep(.g12-ne-incomplete) { background: #fef0f0 !important; }
:deep(.g12-ne-cross) { background: #fdf6ec !important; }
</style>
