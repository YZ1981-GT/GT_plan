<template>
  <div class="f2-val-sheet f2-val-monthly">
    <header class="sheet-header">
      <div>
        <h3>{{ title }}</h3>
        <span class="code">{{ sheetCode }}</span>
      </div>
      <div class="stat-row">
        <el-tag v-if="exceedCount > 0" type="danger">超差异月度 {{ exceedCount }}</el-tag>
        <span class="stat">差异合计 {{ fmt(bundleVariance) }}</span>
        <span class="stat sub">阈值 {{ thresholdRate }}%</span>
      </div>
    </header>

    <!-- 编制说明（源模板前置） -->
    <details class="prep-notes" open>
      <summary>编制说明</summary>
      <ol>
        <li v-for="(note, i) in prepNotes" :key="i">{{ note }}</li>
      </ol>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="`一、测试目标`"
    />
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
      placeholder="说明样本选取标准：如按金额重要性、周转频率、品类代表性选取测试项目；源模板通常列示 4 个产品类。"
      @update:model-value="(v: string) => $emit('update:samplingCriteria', v)"
    />

    <div class="section-label">三、测试</div>
    <div class="method-line">
      <span>（一）计价方法说明：</span>
      <strong>{{ methodLabel }}</strong>
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

    <!-- 各测试项目（品名） -->
    <section
      v-for="(proj, idx) in projects"
      :key="proj.id"
      class="product-block"
    >
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
        <template v-if="method === 'standard-cost'">
          <span class="std-label">标准单价</span>
          <el-input-number
            :model-value="proj.stdPrice"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            class="compact-num std-price"
            @change="(v: number | undefined) => $emit('updateProject', proj.id, { stdPrice: v ?? 0 })"
          />
        </template>
        <el-input
          :model-value="proj.remark"
          size="small"
          :disabled="isReadonly"
          placeholder="备注（进口/运费/返利等）"
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
        <table class="month-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-month">月份</th>
              <th colspan="3">本期生产（或购入）</th>
              <th colspan="3">本期销售（或发出）</th>
              <th colspan="3">期末结存</th>
              <th colspan="2">应结转</th>
              <th rowspan="2" class="col-calc">结余<br /><span class="ref">L</span></th>
              <th rowspan="2" class="col-calc">差异<br /><span class="ref">M=K−F</span></th>
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
              v-for="m in proj.months"
              :key="m.key"
              :class="{ 'row-opening': m.key === 'opening', 'row-warn': isMonthExceed(m) }"
            >
              <td class="col-month">{{ m.label }}</td>
              <!-- 生产/购入 A B C（年初数亦录入于此） -->
              <td>
                <el-input-number
                  :model-value="m.prodQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { prodQty: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="m.prodPrice"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { prodPrice: v ?? 0 })"
                />
              </td>
              <td>
                <el-input-number
                  :model-value="m.prodAmt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { prodAmt: v ?? 0 })"
                />
              </td>
              <!-- 销售/发出：年初行通常为空 -->
              <td>
                <el-input-number
                  v-if="m.key !== 'opening'"
                  :model-value="m.saleQty"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { saleQty: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <el-input-number
                  v-if="m.key !== 'opening'"
                  :model-value="m.salePrice"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { salePrice: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <el-input-number
                  v-if="m.key !== 'opening'"
                  :model-value="m.saleAmt"
                  size="small"
                  :controls="false"
                  :disabled="isReadonly"
                  class="compact-num"
                  @change="(v: number | undefined) => patchMonth(proj.id, m.key, { saleAmt: v ?? 0 })"
                />
                <span v-else class="muted">—</span>
              </td>
              <!-- 期末 / 应结转 / 结余 / 差异：自动 -->
              <td class="auto">{{ fmtQty(m.endQty) }}</td>
              <td class="auto">{{ fmt(m.endPrice) }}</td>
              <td class="auto">{{ fmt(m.endAmt) }}</td>
              <td class="auto">{{ m.key === 'opening' ? '—' : fmt(m.shouldPrice) }}</td>
              <td class="auto">{{ m.key === 'opening' ? '—' : fmt(m.shouldAmt) }}</td>
              <td class="auto">{{ m.key === 'opening' ? '—' : fmt(m.remainder) }}</td>
              <td class="auto" :class="{ 'var-warn': isMonthExceed(m) }">
                {{ m.key === 'opening' ? '—' : fmt(m.variance) }}
              </td>
            </tr>
            <!-- 合计 -->
            <tr class="row-total">
              <td class="col-month">合计</td>
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
        placeholder="填写审计说明：概述计价方法测试的抽样与重新计算程序、差异分析及核对结果，以及拟调整/未调整事项及其影响。"
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
        placeholder="填写审计结论：A、计价方法运用正确、一贯，未见异常。B、除上述应调整事项外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @update:model-value="(v: string) => $emit('update:testConclusion', v)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F2-38/39/40 多产品×月度计价测试表（F2-38 专用；F2-39/40 见各自组件）
 */
import { computed, toRef, type Ref } from 'vue'
import type { SamplingParams } from '../../composables/useF2ValuationTestFormulas'
import {
  VALUATION_PREP_NOTES,
  type ValuationProductProject,
  type ValuationMonthLine,
  type ValuationMonthKey,
  type ValuationMonthlyMethod,
  type ProductMonthTotals,
} from '../../composables/useF2ValuationMonthlyFormulas'
import { useF2ValuationAiGenerate } from '../../composables/useF2ValuationAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  title: string
  sheetCode: string
  method: ValuationMonthlyMethod
  methodLabel: string
  thresholdRate: number
  defaultObjective: string
  projects: ValuationProductProject[]
  samplingParams: SamplingParams
  samplingCriteria: string
  testObjective: string
  testConclusion: string
  auditNote: string
  exceedCount: number
  bundleVariance: number
  projectTotals: (p: ValuationProductProject) => ProductMonthTotals
  wpId?: string
  projectId?: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  addProject: []
  removeProject: [id: string]
  updateProject: [id: string, patch: Partial<ValuationProductProject>]
  updateMonth: [projectId: string, monthKey: ValuationMonthKey, patch: Partial<ValuationMonthLine>]
  'update:testObjective': [v: string]
  'update:samplingCriteria': [v: string]
  'update:testConclusion': [v: string]
  'update:auditNote': [v: string]
}>()

const prepNotes = VALUATION_PREP_NOTES
const isReadonly = computed(() => !!props.isReadonly)

// ─── AI 辅助（与 D4/F2-33 gold 标准一致，直接挂在说明/结论文本框上）──────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)
const aiTip = computed(() => (aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用'))
function aiCtx(): Record<string, unknown> {
  return { sheet: props.sheetCode, method: props.methodLabel, exceedCount: props.exceedCount, projectCount: props.projects.length }
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

function isMonthExceed(m: ValuationMonthLine): boolean {
  if (m.key === 'opening') return false
  if (Math.abs(m.variance) < 0.005) return false
  if (!m.saleAmt) return Math.abs(m.variance) > 0.005
  return Math.abs(m.variance / m.saleAmt) * 100 > props.thresholdRate
}

function totalsOf(p: ValuationProductProject): ProductMonthTotals {
  return props.projectTotals(p)
}

function patchMonth(projectId: string, monthKey: ValuationMonthKey, patch: Partial<ValuationMonthLine>) {
  emit('updateMonth', projectId, monthKey, patch)
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-val-monthly { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.prep-notes {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #eef1f6;
  border-top: 3px solid var(--gt-purple, #4b2d77);
  border-radius: 4px;
  font-size: 13px;
  color: #3a4a6b;
}
.prep-notes summary { cursor: pointer; font-weight: 600; color: var(--gt-purple, #4b2d77); }
.prep-notes ol { margin: 8px 0 0; padding-left: 1.4em; line-height: 1.7; }

.section-label {
  margin: 14px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.section-text { margin-bottom: 10px; }
.method-line { margin-bottom: 10px; font-size: 13px; color: #606266; }
.method-line strong { color: var(--gt-purple, #4b2d77); }

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
  background: var(--gt-purple-soft, #f3eef8);
  border-bottom: 1px solid #e4dceb;
}
.product-title { font-weight: 600; font-size: 13px; color: var(--gt-purple, #4b2d77); white-space: nowrap; }
.item-name-input { width: 200px; max-width: 40vw; }
.remark-input { width: 220px; max-width: 40vw; }
.std-label { font-size: 12px; color: #606266; }
.std-price { width: 100px; }

.table-scroll { overflow-x: auto; }
.month-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1100px;
}
.month-table th,
.month-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 4px;
  text-align: center;
  vertical-align: middle;
}
.month-table thead th {
  background: var(--gt-purple-soft, #f3eef8);
  color: #3d2a55;
  font-weight: 600;
  white-space: nowrap;
}
.ref { color: #c45656; font-weight: 600; font-size: 11px; }
.col-month { width: 64px; font-weight: 500; background: #faf8fc; }
.col-calc { min-width: 72px; }
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

:deep(.compact-num) { width: 78px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 12px; }
</style>
