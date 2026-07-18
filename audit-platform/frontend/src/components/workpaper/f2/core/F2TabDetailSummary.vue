<script setup lang="ts">
/**
 * F2TabDetailSummary — F2-2 明细汇总表
 * 对齐源模板：(一)原值 (二)跌价 (三)账面价值 + 审计目标/过程/说明/结论（含 AI）
 */
import { ref, toRef, type Ref } from 'vue'
import {
  useF2DetailSummary,
  fmtChangeRate,
  type F2SummaryGrossRow,
  type F2SummaryImpRow,
  type F2SummaryBvRow,
} from '../../composables/useF2DetailSummary'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  projectId?: string
  wpId?: string
  isReadonly?: boolean
}>()

const isReadonlyRef = toRef(() => !!props.isReadonly)
const {
  grossRows,
  grossTotal,
  impRows,
  impTotal,
  bvRows,
  bvTotal,
  auditObjective,
  auditProcess,
  auditNote,
  auditConclusion,
  updateGrossAdj,
  updateImpAdj,
  updateBvText,
  updateManualUnaud,
  getAiContext,
} = useF2DetailSummary({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: isReadonlyRef as Ref<boolean>,
})

const wpIdRef = toRef(() => props.wpId || '')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(wpIdRef as Ref<string>)
const changeReasonHint = ref('')

function fmtAmt(v: number): string {
  return !v ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function runAi(
  section: F2AiSection,
  current: Ref<string>,
  title: string,
): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  const text = await generateAndConfirm(section, current.value, getAiContext(), title)
  if (text) current.value = text
}

function grossRowClass({ row }: { row: F2SummaryGrossRow }): string {
  if (row.rowKey === '__total__') return 'total-row'
  return row.crossSheet ? 'cross-row' : ''
}
function impRowClass({ row }: { row: F2SummaryImpRow }): string {
  return row.rowKey === '__total__' ? 'total-row' : ''
}
function bvRowClass({ row }: { row: F2SummaryBvRow }): string {
  return row.rowKey === '__total__' ? 'total-row' : ''
}
</script>

<template>
  <div class="f2-summary">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. （一）原值未审数自 F2-3~F2-13 明细合计跨表取数；在产品/数据资源无独立明细表时可手工录入。</p>
        <p>2. 审定数 = 未审数 + 期初调整 + 期末调整（增加/减少）；灰底列为公式列。</p>
        <p>3. （二）跌价未审数自 F2-1 跌价准备区跨表取数；审定减少可细分转回/核销/其他。</p>
        <p>4. （三）账面价值 = 原值 − 跌价；变动率自动计算；文本框支持 AI 辅助填写。</p>
      </div>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="summary-title">F2-2 存货明细汇总表</span>
        <F2ReviewChip section-id="F2-2-summary" />
        <el-tag size="small" type="info">跨表取数</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-3" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>一、审计目标</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAi('summary-objective', auditObjective, 'AI · 审计目标')"
          >AI 填写</el-button>
        </div>
      </template>
      <el-input
        v-model="auditObjective"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="1. 确定存货是否存在；2. 确定存货是否归被审计单位所有；3. 确定存货增减变动记录是否完整、计价是否正确、期末余额是否正确。"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>二、审计过程</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAi('summary-process', auditProcess, 'AI · 审计过程')"
          >AI 填写</el-button>
        </div>
      </template>
      <el-input
        v-model="auditProcess"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="1. 取得各类存货明细表并与总账、明细账核对；2. 抽查收发存记录；3. 执行截止测试；4. 分析库龄及跌价准备计提…"
      />
    </el-card>

    <div class="section-block">
      <h4 class="section-title">
        (一) 原值
        <el-tooltip content="未审数来自 F2-3~F2-13 明细合计" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
      </h4>
      <div class="table-wrap">
        <el-table
          :data="[...grossRows, grossTotal]"
          border
          size="small"
          style="width:100%"
          :row-class-name="grossRowClass"
        >
          <el-table-column prop="label" label="项目" min-width="160" fixed>
            <template #default="{ row }">
              <span :class="{ 'total-label': row.rowKey === '__total__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="未审数" align="center">
            <el-table-column label="期初余额" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.unaudOpen) }}</span>
                <el-input-number
                  v-else-if="!row.crossSheet"
                  :model-value="row.unaudOpen"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateManualUnaud(row.rowKey, 'open', v ?? 0)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmt(row.unaudOpen) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.unaudInc) }}</span>
                <el-input-number
                  v-else-if="!row.crossSheet"
                  :model-value="row.unaudInc"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateManualUnaud(row.rowKey, 'inc', v ?? 0)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmt(row.unaudInc) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期减少" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.unaudDec) }}</span>
                <el-input-number
                  v-else-if="!row.crossSheet"
                  :model-value="row.unaudDec"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateManualUnaud(row.rowKey, 'dec', v ?? 0)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmt(row.unaudDec) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：期初 + 增加 − 减少（明细合计）" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.unaudClose) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初调整" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.openingAdj) }}</span>
              <el-input-number
                v-else
                :model-value="row.openingAdj"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => updateGrossAdj(row.rowKey, 'openingAdj', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末调整" align="center">
            <el-table-column label="本期增加" min-width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.closeAdjInc) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.closeAdjInc"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateGrossAdj(row.rowKey, 'closeAdjInc', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="本期减少" min-width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.closeAdjDec) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.closeAdjDec"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateGrossAdj(row.rowKey, 'closeAdjDec', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="审定数" align="center">
            <el-table-column label="期初余额" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：未审期初 + 期初调整" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.audOpen) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：未审增加 + 期末调整增加" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.audInc) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="本期减少" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：未审减少 + 期末调整减少" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.audDec) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="期末数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：审定期初 + 审定增加 − 审定减少" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.audClose) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="row.rowKey !== '__total__'"
                :model-value="row.remark"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateGrossAdj(row.rowKey, 'remark', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="索引号" width="80">
            <template #default="{ row }">
              <GtIndexChip v-if="row.sheetCode" :value="row.sheetCode" :context-project-id="projectId" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="section-block">
      <h4 class="section-title">
        (二) 跌价准备
        <el-tooltip content="未审数来自 F2-1 跌价准备区" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
      </h4>
      <div class="table-wrap">
        <el-table
          :data="[...impRows, impTotal]"
          border
          size="small"
          style="width:100%"
          :row-class-name="impRowClass"
        >
          <el-table-column prop="label" label="项目" min-width="160" fixed>
            <template #default="{ row }">
              <span :class="{ 'total-label': row.rowKey === '__total__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="未审数" align="center">
            <el-table-column label="期初余额" min-width="100" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.unaudOpen) }}</span></template>
            </el-table-column>
            <el-table-column label="本期增加" min-width="100" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.unaudInc) }}</span></template>
            </el-table-column>
            <el-table-column label="本期减少" min-width="100" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.unaudDec) }}</span></template>
            </el-table-column>
            <el-table-column label="期末数" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.unaudClose) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初调整" min-width="90" align="right">
            <template #default="{ row }">
              <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.openingAdj) }}</span>
              <el-input-number
                v-else
                :model-value="row.openingAdj"
                :controls="false"
                size="small"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'openingAdj', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末调整" align="center">
            <el-table-column label="增加" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.closeAdjInc) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.closeAdjInc"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'closeAdjInc', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="减少" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.closeAdjDec) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.closeAdjDec"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'closeAdjDec', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="审定数" align="center">
            <el-table-column label="期初余额" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.audOpen) }}</span></template>
            </el-table-column>
            <el-table-column label="本期增加" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.audInc) }}</span></template>
            </el-table-column>
            <el-table-column label="本期减少" align="center">
              <el-table-column label="转回" min-width="90" align="right">
                <template #default="{ row }">
                  <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.audDecReversal) }}</span>
                  <el-input-number
                    v-else
                    :model-value="row.audDecReversal"
                    :controls="false"
                    size="small"
                    :disabled="isReadonly"
                    style="width:100%"
                    @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'audDecReversal', v ?? 0)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="核销" min-width="90" align="right">
                <template #default="{ row }">
                  <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.audDecWriteOff) }}</span>
                  <el-input-number
                    v-else
                    :model-value="row.audDecWriteOff"
                    :controls="false"
                    size="small"
                    :disabled="isReadonly"
                    style="width:100%"
                    @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'audDecWriteOff', v ?? 0)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="其他" min-width="90" align="right">
                <template #default="{ row }">
                  <span v-if="row.rowKey === '__total__'" class="total-label">{{ fmtAmt(row.audDecOther) }}</span>
                  <el-input-number
                    v-else
                    :model-value="row.audDecOther"
                    :controls="false"
                    size="small"
                    :disabled="isReadonly"
                    style="width:100%"
                    @change="(v: number | undefined) => updateImpAdj(row.rowKey, 'audDecOther', v ?? 0)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="合计" min-width="100" align="right" class-name="auto-calc-col">
                <template #default="{ row }">
                  <el-tooltip content="公式：未审减少 + 期末调整减少" placement="top">
                    <span class="formula-cell">{{ fmtAmt(row.audDec) }}</span>
                  </el-tooltip>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末数" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：审定期初 + 审定增加 − 审定减少" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.audClose) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="section-block">
      <h4 class="section-title">
        (三) 账面价值
        <el-tooltip content="账面价值 = 原值 − 跌价准备" placement="top">
          <el-tag size="small" type="info">公式联动</el-tag>
        </el-tooltip>
      </h4>
      <div class="table-wrap">
        <el-table
          :data="[...bvRows, bvTotal]"
          border
          size="small"
          style="width:100%"
          :row-class-name="bvRowClass"
        >
          <el-table-column prop="label" label="项目" min-width="150" fixed>
            <template #default="{ row }">
              <span :class="{ 'total-label': row.rowKey === '__total__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="未审数" align="center">
            <el-table-column label="期初数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.unaudOpen) }}</span></template>
            </el-table-column>
            <el-table-column label="期末数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.unaudClose) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="审定数" align="center">
            <el-table-column label="期初数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.audOpen) }}</span></template>
            </el-table-column>
            <el-table-column label="期末数" min-width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.audClose) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="变动率" align="center">
            <el-table-column label="未审变动率" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <el-tooltip content="公式：(期末 − 期初) / 期初" placement="top">
                  <span class="formula-cell">{{ fmtChangeRate(row.changeRateUnaud) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="审定变动率" min-width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="formula-cell">{{ fmtChangeRate(row.changeRateAud) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="变动原因分析" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="row.rowKey !== '__total__'"
                :model-value="row.changeReason"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateBvText(row.rowKey, 'changeReason', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="确定可变现净值的具体依据" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="row.rowKey !== '__total__'"
                :model-value="row.nrvBasis"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateBvText(row.rowKey, 'nrvBasis', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期转回或转销存货跌价准备的原因" min-width="160">
            <template #default="{ row }">
              <el-input
                v-if="row.rowKey !== '__total__'"
                :model-value="row.reversalReason"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateBvText(row.rowKey, 'reversalReason', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="索引号" width="80">
            <template #default="{ row }">
              <GtIndexChip v-if="row.sheetCode" :value="row.sheetCode" :context-project-id="projectId" />
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="bv-ai-bar">
        <el-button
          v-if="!isReadonly && aiAvailable"
          size="small"
          type="primary"
          plain
          :loading="aiLoading"
          @click="runAi('summary-change-reason', changeReasonHint, 'AI · 变动原因分析提示')"
        >AI 生成变动原因分析提示</el-button>
        <el-input
          v-if="changeReasonHint"
          v-model="changeReasonHint"
          type="textarea"
          class="mt-8"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="AI 提示可复制到上方各行「变动原因分析」"
        />
      </div>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAi('summary-note', auditNote, 'AI · 审计说明')"
          >AI 填写说明</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="概述明细汇总复核情况、与明细表/审定表勾稽、重大调整及影响…"
      />
      <p class="hint-text">提示：可说明测试情况、拟调整分录及对报表的影响。</p>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAi('summary-conclusion', auditConclusion, 'AI · 审计结论')"
          >AI 填写结论</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-summary { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-summary :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-summary :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.summary-title { font-weight: 600; font-size: 14px; }
.chip-wrap { display: inline-flex; }
.section-block { margin: 20px 0; }
.section-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.table-wrap { overflow-x: auto; }
.cross-sheet-cell { color: #409eff; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.total-label { font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.total-row) { background: #f5f7fa; font-weight: 600; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.hint-text { margin: 8px 0 0; font-size: 12px; color: #909399; }
.bv-ai-bar { margin-top: 8px; }
.mt-8 { margin-top: 8px; }
</style>
