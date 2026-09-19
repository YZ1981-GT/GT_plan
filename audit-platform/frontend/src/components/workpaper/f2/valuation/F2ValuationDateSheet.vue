<template>
  <div class="f2-val-sheet f2-val-date">
    <header class="sheet-header">
      <div>
        <h3>{{ title }}</h3>
        <span class="code">{{ sheetCode }}</span>
      </div>
      <div class="stat-row">
        <el-tag v-if="exceedCount > 0" type="danger">超差异笔数 {{ exceedCount }}</el-tag>
        <span class="stat">差异合计 {{ fmt(bundleVariance) }}</span>
        <span class="stat sub">阈值 {{ thresholdRate }}%</span>
      </div>
    </header>

    <el-alert type="info" :closable="false" show-icon class="objective-alert" title="一、测试目标" />
    <el-input
      :model-value="testObjective"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 5 }"
      :disabled="isReadonly"
      class="section-text"
      :placeholder="defaultObjective"
      @update:model-value="(v: string) => $emit('update:testObjective', v)"
    />

    <div class="section-label">二、样本选取标准与规模</div>
    <el-form inline size="small" class="sampling-form">
      <el-form-item label="总体">
        <el-input v-model="samplingParams.population" :disabled="isReadonly" style="width:120px" />
      </el-form-item>
      <el-form-item label="样本量">
        <el-input-number v-model="samplingParams.sampleSize" :controls="false" :disabled="isReadonly" style="width:80px" />
      </el-form-item>
      <el-form-item label="抽样方法">
        <el-input v-model="samplingParams.method" :disabled="isReadonly" style="width:140px" />
      </el-form-item>
      <el-form-item label="置信水平">
        <el-input v-model="samplingParams.confidence" :disabled="isReadonly" style="width:70px" />
      </el-form-item>
      <el-form-item label="可接受误差">
        <el-input v-model="samplingParams.tolerableError" :disabled="isReadonly" style="width:70px" />
      </el-form-item>
    </el-form>
    <el-input
      :model-value="samplingCriteria"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      placeholder="说明样本选取标准；源模板列示 3 个测试项目（品名）。"
      @update:model-value="(v: string) => $emit('update:samplingCriteria', v)"
    />

    <div class="section-label">三、测试</div>
    <div class="method-line">
      <span>（一）计价方法说明：</span>
      <el-radio-group
        :model-value="costingMode"
        size="small"
        :disabled="isReadonly"
        @update:model-value="(v) => $emit('update:costingMode', v as DateCostingMode)"
      >
        <el-radio-button value="fifo">先进先出法</el-radio-button>
        <el-radio-button value="moving-wa">移动加权平均法</el-radio-button>
      </el-radio-group>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="$emit('addProject')">+ 测试项目</el-button>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          :sheet="sheetCode"
          :disabled="isReadonly"
          ai-section="valuation-conclusion"
          :existing-content="testConclusion"
          :related-context="{ exceedCount, projectCount: projects.length, costingMode }"
          :ai-title="`AI 生成 · ${title}结论`"
          :review-section="`${sheetCode}-conclusion`"
          @ai-filled="(t: string) => $emit('update:testConclusion', t)"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip :value="'wp:' + sheetCode" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">{{ projects.length }} 个测试项目</el-tag>
      </div>
    </div>

    <section v-for="(proj, idx) in projects" :key="proj.id" class="product-block">
      <div class="product-head">
        <span class="product-title">（二）测试项目{{ idx + 1 }}：品名：</span>
        <el-input
          :model-value="proj.itemName"
          size="small"
          :disabled="isReadonly"
          placeholder="填写存货品名/类别"
          class="item-name-input"
          @update:model-value="(v: string) => $emit('updateProject', proj.id, { itemName: v })"
        />
        <el-input
          :model-value="proj.remark"
          size="small"
          :disabled="isReadonly"
          placeholder="备注（进口/运费/返利等）"
          class="remark-input"
          @update:model-value="(v: string) => $emit('updateProject', proj.id, { remark: v })"
        />
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="$emit('addTxnLine', proj.id)"
        >+ 发生行</el-button>
        <el-button
          link
          type="danger"
          size="small"
          :disabled="isReadonly || projects.length <= 1"
          @click="$emit('removeProject', proj.id)"
        >删除项目</el-button>
      </div>

      <div class="table-scroll">
        <table class="date-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-date">日期</th>
              <th colspan="3">本期生产（或购入）</th>
              <th colspan="3">本期销售（或发出）</th>
              <th colspan="3">期末结存</th>
              <th colspan="2">应结转</th>
              <th rowspan="2" class="col-calc">结余</th>
              <th rowspan="2" class="col-calc">差异<br /><span class="ref">M=K−F</span></th>
              <th rowspan="2" class="col-act" />
            </tr>
            <tr>
              <th>数量 <span class="ref">A</span></th>
              <th>单价 <span class="ref">B</span></th>
              <th>金额 <span class="ref">C</span></th>
              <th>数量 <span class="ref">D</span></th>
              <th>单价 <span class="ref">E</span></th>
              <th>金额 <span class="ref">F</span></th>
              <th>数量</th>
              <th>单价</th>
              <th>金额</th>
              <th>单价 <span class="ref">J</span></th>
              <th>金额 <span class="ref">K</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="line in proj.lines"
              :key="line.id"
              :class="{ 'row-opening': line.kind === 'opening', 'row-warn': isLineExceed(line) }"
            >
              <td class="col-date">
                <span v-if="line.kind === 'opening'">{{ line.dateLabel }}</span>
                <el-input
                  v-else
                  :model-value="line.dateLabel"
                  size="small"
                  :disabled="isReadonly"
                  placeholder="日期"
                  class="date-input"
                  @update:model-value="(v: string) => patchLine(proj.id, line.id, { dateLabel: v })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="line.prodQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { prodQty: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="line.prodPrice"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { prodPrice: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="line.prodAmt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { prodAmt: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  v-if="line.kind !== 'opening'"
                  :model-value="line.saleQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { saleQty: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <el-input-number
                  v-if="line.kind !== 'opening'"
                  :model-value="line.salePrice"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { salePrice: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <el-input-number
                  v-if="line.kind !== 'opening'"
                  :model-value="line.saleAmt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchLine(proj.id, line.id, { saleAmt: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td class="auto">{{ fmtQty(line.endQty) }}</td>
              <td class="auto">{{ fmt(line.endPrice) }}</td>
              <td class="auto">{{ fmt(line.endAmt) }}</td>
              <td class="auto">{{ line.kind === 'opening' ? '—' : fmt(line.shouldPrice) }}</td>
              <td class="auto">{{ line.kind === 'opening' ? '—' : fmt(line.shouldAmt) }}</td>
              <td class="auto">{{ line.kind === 'opening' ? '—' : fmt(line.remainder) }}</td>
              <td class="auto" :class="{ 'var-warn': isLineExceed(line) }">
                {{ line.kind === 'opening' ? '—' : fmt(line.variance) }}
              </td>
              <td class="col-act">
                <el-button
                  v-if="line.kind !== 'opening'"
                  link
                  type="danger"
                  size="small"
                  :disabled="isReadonly"
                  @click="$emit('removeTxnLine', proj.id, line.id)"
                >删</el-button>
              </td>
            </tr>
            <tr class="row-total">
              <td class="col-date">合计</td>
              <td class="auto">{{ fmtQty(totalsOf(proj).prodQty) }}</td>
              <td class="muted">—</td>
              <td class="auto">{{ fmt(totalsOf(proj).prodAmt) }}</td>
              <td class="auto">{{ fmtQty(totalsOf(proj).saleQty) }}</td>
              <td class="muted">—</td>
              <td class="auto">{{ fmt(totalsOf(proj).saleAmt) }}</td>
              <td colspan="3" class="muted">—</td>
              <td class="muted">—</td>
              <td class="auto">{{ fmt(totalsOf(proj).shouldAmt) }}</td>
              <td class="muted">—</td>
              <td class="auto" :class="{ 'var-warn': Math.abs(totalsOf(proj).variance) > 0.005 }">
                {{ fmt(totalsOf(proj).variance) }}
              </td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">四、审计说明</span></template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：概述计价方法测试的抽样与重新计算程序、差异分析及核对结果。"
        @update:model-value="(v: string) => $emit('update:auditNote', v)"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">五、审计结论</span></template>
      <el-input
        :model-value="testConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论。"
        @update:model-value="(v: string) => $emit('update:testConclusion', v)"
      />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SamplingParams } from '../../composables/useF2ValuationTestFormulas'
import {
  F2_39_TIPS,
  type ValuationDateProject,
  type ValuationDateLine,
  type DateCostingMode,
  type DateProjectTotals,
} from '../../composables/useF2ValuationDateFormulas'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  title: string
  sheetCode: string
  costingMode: DateCostingMode
  thresholdRate: number
  defaultObjective: string
  projects: ValuationDateProject[]
  samplingParams: SamplingParams
  samplingCriteria: string
  testObjective: string
  testConclusion: string
  auditNote: string
  exceedCount: number
  bundleVariance: number
  projectTotals: (p: ValuationDateProject) => DateProjectTotals
  wpId?: string
  projectId?: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  addProject: []
  removeProject: [id: string]
  addTxnLine: [projectId: string]
  removeTxnLine: [projectId: string, lineId: string]
  updateProject: [id: string, patch: Partial<ValuationDateProject>]
  updateLine: [projectId: string, lineId: string, patch: Partial<ValuationDateLine>]
  'update:costingMode': [mode: DateCostingMode]
  'update:testObjective': [v: string]
  'update:samplingCriteria': [v: string]
  'update:testConclusion': [v: string]
  'update:auditNote': [v: string]
}>()

const tips = F2_39_TIPS
const isReadonly = computed(() => !!props.isReadonly)

function fmt(v: number): string {
  if (v === 0 || v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtQty(v: number): string {
  if (v === 0 || v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function isLineExceed(line: ValuationDateLine): boolean {
  if (line.kind === 'opening') return false
  if (Math.abs(line.variance) < 0.005) return false
  if (!line.saleAmt) return Math.abs(line.variance) > 0.005
  return Math.abs(line.variance / line.saleAmt) * 100 > props.thresholdRate
}

function totalsOf(p: ValuationDateProject): DateProjectTotals {
  return props.projectTotals(p)
}

function patchLine(projectId: string, lineId: string, patch: Partial<ValuationDateLine>) {
  emit('updateLine', projectId, lineId, patch)
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-val-date { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.section-text { margin-bottom: 10px; }
.method-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #606266;
}

.product-block {
  margin-bottom: 20px;
  border: 1px solid #e4dceb;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}
.product-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--gt-purple-soft);
  border-bottom: 1px solid #e4dceb;
}
.product-title { font-weight: 600; font-size: 13px; color: var(--gt-purple); white-space: nowrap; }
.item-name-input { width: 180px; max-width: 35vw; }
.remark-input { width: 200px; max-width: 35vw; }

.table-scroll { overflow-x: auto; }
.date-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1150px;
}
.date-table th,
.date-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 4px;
  text-align: center;
  vertical-align: middle;
}
.date-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
  white-space: nowrap;
}
.row-ref td { background: #f7f3fb; font-size: 11px; }
.ref { color: #c45656; font-weight: 600; font-size: 11px; }
.col-date { width: 88px; font-weight: 500; background: #faf8fc; }
.col-calc { min-width: 72px; }
.col-act { width: 36px; }
.row-opening td { background: #f7f3fb; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.auto {
  background: #f5f7fa !important;
  text-align: right !important;
  padding-right: 6px !important;
  white-space: nowrap;
}
.muted { color: #c0c4cc; }
.var-warn { color: #f56c6c !important; font-weight: 600; }
.date-input { width: 80px; }

.conclusion-card { margin-top: 14px; }
.conclusion-header { font-weight: 600; font-size: 14px; }

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  color: #3a4a6b;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 76px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 12px; }
</style>
