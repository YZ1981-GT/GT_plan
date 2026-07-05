<template>
  <div class="g1-derivative-check">
    <div class="section-head">
      <h3 class="sheet-title">G1-14 衍生金融工具核查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="dc.addRow()">新增衍生工具</el-button>
        <el-button size="small" @click="openReviewDialog('G1-14-conclusion')">💬复核</el-button>
      </div>
    </div>

    <div class="stats-bar">
      衍生工具：<b>{{ dc.rows.value.length }}</b> 项 ·
      名义金额合计：{{ dc.notionalTotal.value.toLocaleString() }} ·
      保证金合计：{{ dc.marginTotal.value.toLocaleString() }} ·
      会计处理不适当：<b :class="{ warn: dc.inappropriateCount.value > 0 }">{{ dc.inappropriateCount.value }}</b>
    </div>

    <el-table :data="dc.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in dc.columns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :fixed="col.prop === 'instrumentName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <el-select
            v-else-if="col.type === 'type-select'"
            v-model="row.instrumentType"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { instrumentType: row.instrumentType })"
          >
            <el-option v-for="o in dc.typeOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-select
            v-else-if="col.type === 'accounting-select'"
            v-model="row.accountingAppropriateness"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { accountingAppropriateness: row.accountingAppropriateness })"
          >
            <el-option v-for="o in dc.accountingOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="dc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="dc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="dc.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对衍生金融工具合规性的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>衍生工具类型：期权/期货/互换/远期，需关注名义金额、对手方及保证金安排。</li>
        <li>会计处理适当性下拉判定，标记为「不适当」的项目应在合规结论中说明并提出调整建议。</li>
        <li>套期工具需单独判断套期关系有效性，非套期衍生工具计入交易性金融资产。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { useG1DerivativeCheck } from '../../composables/useG1DerivativeCheck'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const dc = useG1DerivativeCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.g1-derivative-check { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #f56c6c; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
