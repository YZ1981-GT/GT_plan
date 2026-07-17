<template>
  <div class="f2-val-sheet f2-std-cost">
    <header class="sheet-header">
      <div>
        <h3>{{ title }}</h3>
        <span class="code">{{ sheetCode }}</span>
      </div>
      <div class="stat-row">
        <el-tag v-if="exceedCount > 0" type="danger">超差异 {{ exceedCount }} 月</el-tag>
        <span class="stat">差异合计 {{ fmt(bundleDiff) }}</span>
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
      <strong>标准成本法（分项记录标准成本及标准成本差异）</strong>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="$emit('addProject')">+ 测试项目</el-button>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          :sheet="sheetCode"
          :disabled="isReadonly"
          :review-section="`${sheetCode}-conclusion`"
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
          placeholder="备注"
          class="remark-input"
          @update:model-value="(v: string) => $emit('updateProject', proj.id, { remark: v })"
        />
        <el-button
          link
          type="danger"
          size="small"
          :disabled="isReadonly || projects.length <= 1"
          @click="$emit('removeProject', proj.id)"
        >删除</el-button>
      </div>

      <div class="table-scroll">
        <table class="std-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-month">月份</th>
              <th colspan="4">本期生产（或购入）</th>
              <th colspan="3">本期销售（或发出）应结转</th>
              <th colspan="3">期末应结存</th>
              <th colspan="3">期末实际结存</th>
              <th rowspan="2" class="col-diff">差异</th>
            </tr>
            <tr>
              <th>数量</th>
              <th>标准单价</th>
              <th class="calc-h">标准成本</th>
              <th class="calc-h">标准成本差异</th>
              <th>数量</th>
              <th class="calc-h">标准成本</th>
              <th class="calc-h">标准成本差异</th>
              <th>数量</th>
              <th class="calc-h">标准成本</th>
              <th class="calc-h">标准成本差异</th>
              <th>数量</th>
              <th class="calc-h">标准成本</th>
              <th class="calc-h">标准成本差异</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in proj.months"
              :key="m.key"
              :class="{ 'row-opening': m.kind === 'opening', 'row-warn': isMonthExceed(m) }"
            >
              <td class="col-month">{{ m.label }}</td>
              <!-- 生产 -->
              <td>
                <el-input-number
                  v-if="m.kind !== 'opening'"
                  :model-value="m.prodQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { prodQty: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <el-input-number
                  v-if="m.kind !== 'opening'"
                  :model-value="m.stdUnitPrice"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { stdUnitPrice: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td class="auto">
                {{ m.kind === 'opening' ? '—' : fmt(m.prodStdCost) }}
              </td>
              <td>
                <el-input-number
                  v-if="m.kind !== 'opening'"
                  :model-value="m.prodStdVariance"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { prodStdVariance: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <!-- 销售应结转 -->
              <td>
                <el-input-number
                  v-if="m.kind !== 'opening'"
                  :model-value="m.saleQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { saleQty: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td class="auto">{{ m.kind === 'opening' ? '—' : fmt(m.saleStdCost) }}</td>
              <td>
                <el-input-number
                  v-if="m.kind !== 'opening'"
                  :model-value="m.saleStdVariance"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { saleStdVariance: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <!-- 应结存 -->
              <td class="auto">{{ fmtQty(m.expEndQty) }}</td>
              <td class="auto">{{ fmt(m.expEndStdCost) }}</td>
              <td class="auto">{{ fmt(m.expEndStdVariance) }}</td>
              <!-- 实际结存 -->
              <td>
                <el-input-number
                  :model-value="m.actEndQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { actEndQty: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="m.actEndStdCost"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { actEndStdCost: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="m.actEndStdVariance"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { actEndStdVariance: v ?? 0 })"
                />
              </td>
              <td class="auto" :class="{ 'var-warn': isMonthExceed(m) }">{{ fmt(m.diffStdCost) }}</td>
            </tr>
            <tr class="row-total">
              <td class="col-month">合计</td>
              <td class="auto">{{ fmtQty(totalsOf(proj).prodQty) }}</td>
              <td class="muted">—</td>
              <td class="auto">{{ fmt(totalsOf(proj).prodStdCost) }}</td>
              <td class="auto">{{ fmt(totalsOf(proj).prodStdVariance) }}</td>
              <td class="auto">{{ fmtQty(totalsOf(proj).saleQty) }}</td>
              <td class="auto">{{ fmt(totalsOf(proj).saleStdCost) }}</td>
              <td class="auto">{{ fmt(totalsOf(proj).saleStdVariance) }}</td>
              <td colspan="3" class="muted">—</td>
              <td colspan="3" class="muted">—</td>
              <td class="auto" :class="{ 'var-warn': Math.abs(totalsOf(proj).diffStdCost) > 0.005 }">
                {{ fmt(totalsOf(proj).diffStdCost) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head-row">
          <span class="conclusion-header">四、审计说明</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="genNote">🤖 AI辅助说明</el-button>
          </el-tooltip>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：概述标准成本差异测试程序、差异分析及核对结果。"
        @update:model-value="(v: string) => $emit('update:auditNote', v)"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head-row">
          <span class="conclusion-header">五、审计结论</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="genConclusion">🤖 AI辅助结论</el-button>
          </el-tooltip>
        </div>
      </template>
      <el-input
        :model-value="testConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论。"
        @update:model-value="(v: string) => $emit('update:testConclusion', v)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import type { SamplingParams } from '../../composables/useF2ValuationTestFormulas'
import type {
  StdCostProductProject,
  StdCostMonthLine,
  StdCostMonthKey,
  StdCostProjectTotals,
} from '../../composables/useF2StdCostMonthlyFormulas'
import { useF2ValuationAiGenerate } from '../../composables/useF2ValuationAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  title: string
  sheetCode: string
  thresholdRate: number
  defaultObjective: string
  projects: StdCostProductProject[]
  samplingParams: SamplingParams
  samplingCriteria: string
  testObjective: string
  testConclusion: string
  auditNote: string
  exceedCount: number
  bundleDiff: number
  projectTotals: (p: StdCostProductProject) => StdCostProjectTotals
  wpId?: string
  projectId?: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  addProject: []
  removeProject: [id: string]
  updateProject: [id: string, patch: Partial<StdCostProductProject>]
  updateMonth: [projectId: string, monthKey: StdCostMonthKey, patch: Partial<StdCostMonthLine>]
  'update:testObjective': [v: string]
  'update:samplingCriteria': [v: string]
  'update:testConclusion': [v: string]
  'update:auditNote': [v: string]
}>()

const isReadonly = computed(() => !!props.isReadonly)

// ─── AI 辅助（挂在说明/结论文本框，对齐 D4/F2-33 gold）─────────────────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)
const aiTip = computed(() => (aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用'))
function aiCtx(): Record<string, unknown> {
  return { sheet: props.sheetCode, exceedCount: props.exceedCount, projectCount: props.projects.length }
}
async function genNote(): Promise<void> {
  const t = await generateAndConfirm('valuation-note', props.auditNote, aiCtx(), `AI 生成 · ${props.title}审计说明`)
  if (t) emit('update:auditNote', t)
}
async function genConclusion(): Promise<void> {
  const t = await generateAndConfirm('valuation-conclusion', props.testConclusion, aiCtx(), `AI 生成 · ${props.title}结论`)
  if (t) emit('update:testConclusion', t)
}

function fmt(v: number): string {
  if (v === 0 || v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtQty(v: number): string {
  if (v === 0 || v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function isMonthExceed(m: StdCostMonthLine): boolean {
  if (Math.abs(m.diffStdCost) < 0.005) return false
  if (!m.expEndStdCost) return Math.abs(m.diffStdCost) > 0.005
  return Math.abs(m.diffStdCost / m.expEndStdCost) * 100 > props.thresholdRate
}

function totalsOf(p: StdCostProductProject): StdCostProjectTotals {
  return props.projectTotals(p)
}

function patchMonth(projectId: string, monthKey: StdCostMonthKey, patch: Partial<StdCostMonthLine>) {
  emit('updateMonth', projectId, monthKey, patch)
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-std-cost { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.section-text { margin-bottom: 10px; }
.method-line { margin-bottom: 10px; font-size: 13px; color: #606266; }
.method-line strong { color: var(--gt-purple); }

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
.std-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1280px;
}
.std-table th,
.std-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 4px;
  text-align: center;
  vertical-align: middle;
}
.std-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
  white-space: nowrap;
}
.calc-h { background: #ebe6f2 !important; }
.col-month { width: 56px; font-weight: 500; background: #faf8fc; }
.col-diff { min-width: 72px; }
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

.conclusion-card { margin-top: 14px; }
.conclusion-header { font-weight: 600; font-size: 14px; }
.conclusion-head-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }

:deep(.compact-num) { width: 72px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 12px; }
</style>
