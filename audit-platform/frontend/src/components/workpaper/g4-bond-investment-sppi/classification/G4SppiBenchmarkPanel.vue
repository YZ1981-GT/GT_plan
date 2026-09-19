<template>
  <el-card shadow="never" class="benchmark-card">
    <template #header>
      <div class="bm-header">
        <span>修正的货币时间价值 — 基准测试工作区</span>
        <el-tag size="small" :type="resultTagType" effect="plain">{{ resultLabel }}</el-tag>
      </div>
    </template>

    <div class="tip-banner tip-blue">
      <strong>用法（对齐源模板提示 2.1～2.3）</strong>
      <p>
        当利率重置期间与基准利率期限不匹配时，构造未含该「修正」的基准工具，逐期比较未折现合同现金流量与基准现金流量。
        差异率不超过阈值时，通常仍可通过 SPPI；超过则通不过。请保留计算假设与结论。
      </p>
    </div>

    <el-form :inline="true" size="small" class="bm-meta">
      <el-form-item label="关联投资项目">
        <el-input
          v-model="local.investProject"
          :disabled="readonly"
          placeholder="与部分(一)项目对应"
          style="width: 200px"
          @change="emitPersist"
        />
      </el-form-item>
      <el-form-item label="重大性阈值(%)">
        <el-input-number
          v-model="local.thresholdPct"
          :disabled="readonly"
          :min="0"
          :max="100"
          :precision="2"
          :controls="false"
          @change="emitPersist"
        />
      </el-form-item>
      <el-form-item label="差异率">
        <strong :class="{ material: isMaterial }">{{ diffRate.toFixed(2) }}%</strong>
      </el-form-item>
      <el-form-item label="基准测试结论">
        <el-select v-model="local.conclusion" :disabled="readonly" style="width: 140px" @change="onManualConclusion">
          <el-option label="通过SPPI测试" value="PASS" />
          <el-option label="通不过SPPI测试" value="FAIL" />
          <el-option label="需进一步分析" value="FURTHER_ANALYSIS" />
        </el-select>
      </el-form-item>
    </el-form>

    <el-table :data="local.rows" border stripe size="small" class="bm-table">
      <el-table-column label="期次" width="70" align="center">
        <template #default="{ row }">{{ row.period }}</template>
      </el-table-column>
      <el-table-column label="合同现金流量" min-width="130">
        <template #default="{ row }">
          <el-input-number
            v-model="row.contractCf"
            size="small"
            :controls="false"
            :disabled="readonly"
            @change="emitPersist"
          />
        </template>
      </el-table-column>
      <el-table-column label="基准现金流量" min-width="130">
        <template #default="{ row }">
          <el-input-number
            v-model="row.benchmarkCf"
            size="small"
            :controls="false"
            :disabled="readonly"
            @change="emitPersist"
          />
        </template>
      </el-table-column>
      <el-table-column label="差异" min-width="110" align="right">
        <template #default="{ row }">
          {{ fmt(calcBenchmarkPeriodDiff(row.contractCf, row.benchmarkCf)) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center">
        <template #default="{ $index }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="readonly || local.rows.length <= 1"
            @click="removeRow($index)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="bm-actions">
      <el-button size="small" type="primary" plain :disabled="readonly" @click="addRow">+ 新增期次</el-button>
      <el-button size="small" :disabled="readonly" @click="recalcAuto">按阈值重算结论</el-button>
    </div>

    <el-input
      v-model="local.remark"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="readonly"
      placeholder="说明重置频率/基准利率期限不匹配的具体情形、样本期间与判断理由…"
      @change="emitPersist"
    />
  </el-card>
</template>

<script setup lang="ts">
/**
 * G4-6 修正货币时间价值 — 基准测试工作区
 */
import { reactive, computed, watch } from 'vue'
import {
  calcBenchmarkPeriodDiff,
  calcBenchmarkDiffRate,
  isBenchmarkDiffMaterial,
  determineBenchmarkSppiConclusion,
  type BenchmarkPeriodRow,
  type SPPIResult,
} from '@/composables/useG4SppiFormulaEngine'

export interface BenchmarkState {
  investProject: string
  thresholdPct: number
  conclusion: SPPIResult
  conclusionOverridden: boolean
  remark: string
  rows: Array<BenchmarkPeriodRow & { id?: string }>
}

const props = defineProps<{
  modelValue: BenchmarkState
  readonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: BenchmarkState): void
  (e: 'persist'): void
}>()

const local = reactive<BenchmarkState>({
  investProject: '',
  thresholdPct: 10,
  conclusion: 'PASS',
  conclusionOverridden: false,
  remark: '',
  rows: [{ period: 1, contractCf: 0, benchmarkCf: 0 }],
})

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    local.investProject = v.investProject ?? ''
    local.thresholdPct = v.thresholdPct ?? 10
    local.conclusion = v.conclusion ?? 'PASS'
    local.conclusionOverridden = Boolean(v.conclusionOverridden)
    local.remark = v.remark ?? ''
    local.rows = (v.rows?.length ? v.rows : [{ period: 1, contractCf: 0, benchmarkCf: 0 }]).map((r, i) => ({
      period: r.period || i + 1,
      contractCf: r.contractCf ?? 0,
      benchmarkCf: r.benchmarkCf ?? 0,
    }))
  },
  { immediate: true, deep: true },
)

const diffRate = computed(() => calcBenchmarkDiffRate(local.rows))
const isMaterial = computed(() => isBenchmarkDiffMaterial(diffRate.value, local.thresholdPct))
const resultLabel = computed(() => {
  if (local.conclusion === 'FAIL') return '通不过SPPI测试'
  if (local.conclusion === 'FURTHER_ANALYSIS') return '需进一步分析'
  return '通过SPPI测试'
})
const resultTagType = computed(() => {
  if (local.conclusion === 'FAIL') return 'danger'
  if (local.conclusion === 'FURTHER_ANALYSIS') return 'warning'
  return 'success'
})

function fmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function snapshot(): BenchmarkState {
  return {
    investProject: local.investProject,
    thresholdPct: local.thresholdPct,
    conclusion: local.conclusion,
    conclusionOverridden: local.conclusionOverridden,
    remark: local.remark,
    rows: local.rows.map((r, i) => ({
      period: i + 1,
      contractCf: r.contractCf,
      benchmarkCf: r.benchmarkCf,
    })),
  }
}

function emitPersist(): void {
  if (!local.conclusionOverridden) {
    local.conclusion = determineBenchmarkSppiConclusion(diffRate.value, local.thresholdPct)
  }
  const snap = snapshot()
  emit('update:modelValue', snap)
  emit('persist')
}

function onManualConclusion(): void {
  local.conclusionOverridden = true
  emitPersist()
}

function recalcAuto(): void {
  local.conclusionOverridden = false
  local.conclusion = determineBenchmarkSppiConclusion(diffRate.value, local.thresholdPct)
  emitPersist()
}

function addRow(): void {
  if (props.readonly) return
  local.rows.push({ period: local.rows.length + 1, contractCf: 0, benchmarkCf: 0 })
  emitPersist()
}

function removeRow(idx: number): void {
  if (props.readonly || local.rows.length <= 1) return
  local.rows.splice(idx, 1)
  local.rows.forEach((r, i) => { r.period = i + 1 })
  emitPersist()
}
</script>

<style scoped>
.benchmark-card { margin: 16px 0; }
.bm-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.bm-meta { margin-bottom: 8px; }
.bm-table { margin-bottom: 8px; }
.bm-actions { display: flex; gap: 8px; margin-bottom: 10px; }
.material { color: #f56c6c; }
.tip-banner { border-radius: 4px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; line-height: 1.6; }
.tip-banner p { margin: 4px 0 0; }
.tip-blue { background: #ecf5ff; border-left: 3px solid #409eff; color: #1d39c4; }
</style>
