<template>
  <div class="g6-adjudication">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">FVOCI-Debt计量特征：</p>
      <p>① 账面以摊余成本列示（成本+利息调整+应计利息）</p>
      <p>② 公允价值变动计入其他综合收益(OCI)</p>
      <p>③ 减值按摊余成本口径计提（非公允价值口径）</p>
      <p>④ 报表列示数=小计+公允价值变动-减值准备</p>
    </div>

    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-1 其他债权投资审定表</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G6-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <!-- 8层分组表格（虚拟滚动容器） -->
    <div class="adj-scroll-container" :style="{ maxHeight: '680px', overflowY: 'auto' }">
      <template v-for="section in sections" :key="section.key">
        <!-- 公式行（四、七）直接显示，无折叠 -->
        <template v-if="section.isFormula">
          <div class="group-header formula-header">
            <span class="group-name">{{ section.label }}</span>
            <span class="formula-tag">自动计算</span>
          </div>
          <el-table
            :data="[section.formulaRow]"
            border size="small" class="adj-table"
            :row-class-name="() => 'row-formula'"
          >
            <el-table-column label="项目" width="160" fixed>
              <template #default="{ row }"><span class="row-bold">{{ row.item }}</span></template>
            </el-table-column>
            <el-table-column label="期初未审" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="section.formulaTooltip">{{ fmt(row.openingUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初调整" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="section.formulaTooltip">{{ fmt(row.openingAdjustment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初审定" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="'期初审定 = 期初未审 + 期初调整'">{{ fmt(row.openingAdjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末未审" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="section.formulaTooltip">{{ fmt(row.closingUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末调整" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="section.formulaTooltip">{{ fmt(row.closingAdjustment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末审定" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="'期末审定 = 期末未审 + 期末调整'">{{ fmt(row.closingAdjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动额" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="变动额 = 期末审定 - 期初审定">{{ fmt(row.changeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动率" width="100" align="right">
              <template #default="{ row }">
                <span :class="['formula-cell', { 'rate-orange': isRateWarning(row.changeRate) }]"
                  title="变动率 = (期末审定 - 期初审定) / 期初审定">{{ fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因分析" min-width="140">
              <template #default><span>—</span></template>
            </el-table-column>
            <el-table-column label="索引" width="80">
              <template #default><span></span></template>
            </el-table-column>
          </el-table>
        </template>

        <!-- 可折叠的数据section（一、二、三、五、六、八） -->
        <template v-else>
          <div class="group-header" @click="toggleSection(section.key)">
            <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[section.key] }">
              <ArrowDown />
            </el-icon>
            <span class="group-name">{{ section.label }}</span>
          </div>

          <div v-show="expandedMap[section.key]" class="group-body">
            <el-table
              :data="getSectionRows(section.key)"
              border size="small" class="adj-table"
              :max-height="400"
              :row-class-name="adjRowClassName"
            >
              <!-- 项目列 -->
              <el-table-column label="项目" width="160" fixed>
                <template #default="{ row }">
                  <span :class="{ 'row-bold': row._isSubtotal }">{{ row.item }}</span>
                </template>
              </el-table-column>
              <!-- 期初未审 -->
              <el-table-column label="期初未审" width="110" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.openingUnadjusted"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(section.key, row._idx, 'openingUnadjusted', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.openingUnadjusted) }}</span>
                </template>
              </el-table-column>
              <!-- 期初调整 -->
              <el-table-column label="期初调整" width="110" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.openingAdjustment"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(section.key, row._idx, 'openingAdjustment', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.openingAdjustment) }}</span>
                </template>
              </el-table-column>
              <!-- 期初审定(公式) -->
              <el-table-column label="期初审定" width="120" align="right">
                <template #default="{ row }">
                  <span :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="期初审定 = 期初未审 + 期初调整">{{ fmt(row.openingAdjusted) }}</span>
                </template>
              </el-table-column>
              <!-- 期末未审 -->
              <el-table-column label="期末未审" width="110" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.closingUnadjusted"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(section.key, row._idx, 'closingUnadjusted', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.closingUnadjusted) }}</span>
                </template>
              </el-table-column>
              <!-- 期末调整 -->
              <el-table-column label="期末调整" width="110" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.closingAdjustment"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => updateCell(section.key, row._idx, 'closingAdjustment', v)"
                  />
                  <span v-else :class="{ 'row-bold': row._isSubtotal }">{{ fmt(row.closingAdjustment) }}</span>
                </template>
              </el-table-column>
              <!-- 期末审定(公式) -->
              <el-table-column label="期末审定" width="120" align="right">
                <template #default="{ row }">
                  <span :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="期末审定 = 期末未审 + 期末调整">{{ fmt(row.closingAdjusted) }}</span>
                </template>
              </el-table-column>
              <!-- 变动额(公式) -->
              <el-table-column label="变动额" width="110" align="right">
                <template #default="{ row }">
                  <span :class="['formula-cell', { 'row-bold': row._isSubtotal }]"
                    title="变动额 = 期末审定 - 期初审定">{{ fmt(row.changeAmount) }}</span>
                </template>
              </el-table-column>
              <!-- 变动率(公式) -->
              <el-table-column label="变动率" width="100" align="right">
                <template #default="{ row }">
                  <span :class="[
                    'formula-cell',
                    { 'row-bold': row._isSubtotal, 'rate-orange': isRateWarning(row.changeRate) },
                  ]" title="变动率 = (期末审定 - 期初审定) / 期初审定">{{ fmtRate(row.changeRate) }}</span>
                </template>
              </el-table-column>
              <!-- 原因分析 -->
              <el-table-column label="原因分析" min-width="140">
                <template #default="{ row }">
                  <el-input
                    v-if="!row._isSubtotal && !isReadonly"
                    :model-value="row.reasonAnalysis"
                    size="small"
                    :class="{ 'reason-required': isRateWarning(row.changeRate) && !row.reasonAnalysis }"
                    :placeholder="isRateWarning(row.changeRate) ? '变动率>20%，必填' : ''"
                    @change="(v: string) => updateCell(section.key, row._idx, 'reasonAnalysis', v)"
                  />
                  <span v-else>{{ row.reasonAnalysis }}</span>
                </template>
              </el-table-column>
              <!-- 索引 -->
              <el-table-column label="索引" width="90">
                <template #default="{ row }">
                  <template v-if="!row._isSubtotal && !isReadonly">
                    <el-input :model-value="row.indexRef" size="small"
                      @change="(v: string) => updateCell(section.key, row._idx, 'indexRef', v)" />
                  </template>
                  <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </template>
    </div>

    <!-- 底部：试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（科目1503）：</span>
      <span class="tb-amount">{{ fmt(trialBalanceAmount) }}</span>
      <span :class="['diff-value', { 'diff-red': Math.abs(variance) > 0.01 }]">
        差异（审定-试算）：{{ fmt(variance) }}
        <template v-if="Math.abs(variance) <= 0.01"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 审计说明 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="auditNote" type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="对其他债权投资审定表的审计说明…" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="auditConclusion" type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="审计结论…" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为借方科目（资产类1503），期末未审 = 期初审定 + 借方发生额 - 贷方发生额</p>
        <p>2. 审定数 = 未审数 + 审计调整(AJE+RJE合并为"调整"列)</p>
        <p>3. 四、小计 = 一、成本 + 二、利息调整 + 三、应计利息</p>
        <p>4. 七、报表列示数 = 四、小计 + 五、公允价值变动 - 六、减值准备</p>
        <p>5. 变动率超过20%需填写原因分析</p>
        <p>6. 差异 = 七、报表列示数（期末审定）- 试算表数</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabAdjudication.vue — G6-1 其他债权投资审定表（77行×11列，8层多层结构）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Req 3.1~3.5, 7.6
 *
 * 8层结构：
 *   一、成本 → 二、利息调整 → 三、应计利息 → 四、小计(=一+二+三)
 *   → 五、公允价值变动 → 六、减值准备 → 七、报表列示数(=四+五-六)
 *   → 八、一年内到期重分类
 *
 * 11列：项目|期初未审|期初调整|期初审定(公式)|期末未审|期末调整|期末审定(公式)|变动额(公式)|变动率(公式)|原因分析|索引
 *
 * 功能：
 * - 分组折叠(expanded toggle) + 虚拟滚动(maxHeight 680px)
 * - 方法论上下文(琥珀色左边线+浅黄背景): FVOCI-Debt计量特征
 * - 公式引用: calcAdjustedAmount / calcSubtotal / calcReportAmount / calcChangeRate
 * - 四小计=一+二+三; 七报表列示数=四+五-六
 * - 底部TB取数(1503)比对 + 差异红色>0.01
 * - |变动率|>20%橙色高亮+原因分析必填
 * - EventBus publish 'substantive:adjudicated' {accountCode:'1503', adjudicatedAmount}
 * - inject('openReviewDialog') for review button
 */
import { ref, reactive, computed, watch, inject, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  parseNum, calcAdjustedAmount, calcSubtotal, calcReportAmount, calcChangeRate,
} from '@/composables/useG6MainFormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)

// ═══ 8层section定义 ═══════════════════════════════════════════════════════════
interface AdjRow {
  item: string
  openingUnadjusted: number
  openingAdjustment: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  _isSubtotal?: boolean
  _idx: number
}

interface SectionDef {
  key: string
  label: string
  isFormula: boolean
  formulaTooltip?: string
  formulaRow?: AdjRow
}

// ═══ 数据层 — 6个可编辑section的行数据 ═══════════════════════════════════════
const sectionData = reactive<Record<string, AdjRow[]>>({
  cost: [],         // 一、成本
  interestAdj: [],  // 二、利息调整
  accrued: [],      // 三、应计利息
  fvChange: [],     // 五、公允价值变动
  impairment: [],   // 六、减值准备
  reclass: [],      // 八、一年内到期重分类
})

const auditNote = ref('')
const auditConclusion = ref('')
const trialBalanceAmount = ref(0)

// ═══ 折叠状态（默认全展开）═══════════════════════════════════════════════════
const expandedMap = reactive<Record<string, boolean>>({
  cost: true,
  interestAdj: true,
  accrued: true,
  fvChange: true,
  impairment: true,
  reclass: true,
})

function toggleSection(key: string): void {
  expandedMap[key] = !expandedMap[key]
}

// ═══ 小计计算 — 每个section汇总行 ═══════════════════════════════════════════
function calcSectionSubtotal(rows: AdjRow[]): AdjRow {
  const dataRows = rows.filter(r => !r._isSubtotal)
  const sumField = (field: keyof AdjRow) =>
    dataRows.reduce((s, r) => s + parseNum(r[field] as number), 0)
  const openUnadj = sumField('openingUnadjusted')
  const openAdj = sumField('openingAdjustment')
  const openAdjusted = calcAdjustedAmount(openUnadj, openAdj)
  const closeUnadj = sumField('closingUnadjusted')
  const closeAdj = sumField('closingAdjustment')
  const closeAdjusted = calcAdjustedAmount(closeUnadj, closeAdj)
  const change = Math.round((closeAdjusted - openAdjusted) * 100) / 100
  const rate = calcChangeRate(openAdjusted, closeAdjusted)
  return {
    item: '小计', openingUnadjusted: openUnadj, openingAdjustment: openAdj,
    openingAdjusted: openAdjusted, closingUnadjusted: closeUnadj, closingAdjustment: closeAdj,
    closingAdjusted: closeAdjusted, changeAmount: change, changeRate: rate,
    reasonAnalysis: '', indexRef: '', _isSubtotal: true, _idx: -1,
  }
}

/** 获取section显示行（含小计） */
function getSectionRows(key: string): AdjRow[] {
  const rows = sectionData[key] || []
  const dataRows = rows.filter(r => !r._isSubtotal)
  if (dataRows.length === 0) return []
  return [...dataRows, calcSectionSubtotal(dataRows)]
}

// ═══ 四、小计(公式=一+二+三) / 七、报表列示数(公式=四+五-六) ═══════════════════
const sectionFourRow = computed<AdjRow>(() => {
  const costSub = calcSectionSubtotal(sectionData.cost.filter(r => !r._isSubtotal))
  const intAdjSub = calcSectionSubtotal(sectionData.interestAdj.filter(r => !r._isSubtotal))
  const accSub = calcSectionSubtotal(sectionData.accrued.filter(r => !r._isSubtotal))
  const openUnadj = calcSubtotal(costSub.openingUnadjusted, intAdjSub.openingUnadjusted, accSub.openingUnadjusted)
  const openAdj = calcSubtotal(costSub.openingAdjustment, intAdjSub.openingAdjustment, accSub.openingAdjustment)
  const openAdjusted = calcAdjustedAmount(openUnadj, openAdj)
  const closeUnadj = calcSubtotal(costSub.closingUnadjusted, intAdjSub.closingUnadjusted, accSub.closingUnadjusted)
  const closeAdj = calcSubtotal(costSub.closingAdjustment, intAdjSub.closingAdjustment, accSub.closingAdjustment)
  const closeAdjusted = calcAdjustedAmount(closeUnadj, closeAdj)
  const change = Math.round((closeAdjusted - openAdjusted) * 100) / 100
  return {
    item: '四、小计(=一+二+三)', openingUnadjusted: openUnadj, openingAdjustment: openAdj,
    openingAdjusted: openAdjusted, closingUnadjusted: closeUnadj, closingAdjustment: closeAdj,
    closingAdjusted: closeAdjusted, changeAmount: change, changeRate: calcChangeRate(openAdjusted, closeAdjusted),
    reasonAnalysis: '', indexRef: '', _isSubtotal: true, _idx: -1,
  }
})

const sectionSevenRow = computed<AdjRow>(() => {
  const four = sectionFourRow.value
  const fvSub = calcSectionSubtotal(sectionData.fvChange.filter(r => !r._isSubtotal))
  const impSub = calcSectionSubtotal(sectionData.impairment.filter(r => !r._isSubtotal))
  const openAdjusted = calcReportAmount(four.openingAdjusted, fvSub.openingAdjusted, impSub.openingAdjusted)
  const closeAdjusted = calcReportAmount(four.closingAdjusted, fvSub.closingAdjusted, impSub.closingAdjusted)
  const openUnadj = calcReportAmount(four.openingUnadjusted, fvSub.openingUnadjusted, impSub.openingUnadjusted)
  const openAdj = Math.round((openAdjusted - openUnadj) * 100) / 100
  const closeUnadj = calcReportAmount(four.closingUnadjusted, fvSub.closingUnadjusted, impSub.closingUnadjusted)
  const closeAdj = Math.round((closeAdjusted - closeUnadj) * 100) / 100
  const change = Math.round((closeAdjusted - openAdjusted) * 100) / 100
  return {
    item: '七、报表列示数(=四+五-六)', openingUnadjusted: openUnadj, openingAdjustment: openAdj,
    openingAdjusted: openAdjusted, closingUnadjusted: closeUnadj, closingAdjustment: closeAdj,
    closingAdjusted: closeAdjusted, changeAmount: change, changeRate: calcChangeRate(openAdjusted, closeAdjusted),
    reasonAnalysis: '', indexRef: '', _isSubtotal: true, _idx: -1,
  }
})

// ═══ sections 渲染列表（按顺序） ═══════════════════════════════════════════════
const sections = computed<SectionDef[]>(() => [
  { key: 'cost', label: '一、成本', isFormula: false },
  { key: 'interestAdj', label: '二、利息调整', isFormula: false },
  { key: 'accrued', label: '三、应计利息', isFormula: false },
  { key: 'four', label: '四、小计(=一+二+三)', isFormula: true, formulaTooltip: '四 = 一成本 + 二利息调整 + 三应计利息', formulaRow: sectionFourRow.value },
  { key: 'fvChange', label: '五、公允价值变动（计入OCI）', isFormula: false },
  { key: 'impairment', label: '六、减值准备（按摊余成本口径ECL）', isFormula: false },
  { key: 'seven', label: '七、报表列示数(=四+五-六)', isFormula: true, formulaTooltip: '七 = 四小计 + 五公允价值变动 - 六减值准备', formulaRow: sectionSevenRow.value },
  { key: 'reclass', label: '八、一年内到期重分类', isFormula: false },
])

// ═══ TB差异计算 ═══════════════════════════════════════════════════════════════
/** 报表列示数（期末审定）为TB比对基准 */
const adjudicatedAmount = computed(() => sectionSevenRow.value.closingAdjusted)
const variance = computed(() => Math.round((adjudicatedAmount.value - trialBalanceAmount.value) * 100) / 100)

// ═══ EventBus publish: substantive:adjudicated ═══════════════════════════════
watch(adjudicatedAmount, (val) => {
  try {
    // EventBus通过api广播
    api.post('/api/event-bus/publish', {
      event: 'substantive:adjudicated',
      payload: { accountCode: '1503', adjudicatedAmount: val },
    }, { _silent: true } as any).catch(() => {})
  } catch { /* best-effort */ }
})

// ═══ 单元格更新 + 公式重算 ═══════════════════════════════════════════════════
function updateCell(sectionKey: string, rowIdx: number, field: string, value: number | string): void {
  const rows = sectionData[sectionKey]
  if (!rows || rowIdx < 0 || rowIdx >= rows.length) return
  const row = rows[rowIdx]
  ;(row as any)[field] = value
  // 重算公式列
  recalcRow(row)
}

function recalcRow(row: AdjRow): void {
  row.openingAdjusted = calcAdjustedAmount(row.openingUnadjusted, row.openingAdjustment)
  row.closingAdjusted = calcAdjustedAmount(row.closingUnadjusted, row.closingAdjustment)
  row.changeAmount = Math.round((row.closingAdjusted - row.openingAdjusted) * 100) / 100
  row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
}

// ═══ 数据水合 — 从htmlData还原行数据 ═══════════════════════════════════════════
function makeRow(item: string, idx: number, raw?: any): AdjRow {
  const r: AdjRow = {
    item,
    openingUnadjusted: parseNum(raw?.openingUnadjusted ?? raw?.opening_unadjusted),
    openingAdjustment: parseNum(raw?.openingAdjustment ?? raw?.opening_adjustment),
    openingAdjusted: 0,
    closingUnadjusted: parseNum(raw?.closingUnadjusted ?? raw?.closing_unadjusted),
    closingAdjustment: parseNum(raw?.closingAdjustment ?? raw?.closing_adjustment),
    closingAdjusted: 0,
    changeAmount: 0, changeRate: null,
    reasonAnalysis: raw?.reasonAnalysis ?? raw?.reason_analysis ?? '',
    indexRef: raw?.indexRef ?? raw?.index_ref ?? '',
    _isSubtotal: false, _idx: idx,
  }
  recalcRow(r)
  return r
}

/** 默认投资项目骨架（无外部数据时） */
const DEFAULT_ITEMS = ['投资项目A', '投资项目B', '投资项目C']

function hydrateData(): void {
  const data = props.htmlData
  const sectionKeys = ['cost', 'interestAdj', 'accrued', 'fvChange', 'impairment', 'reclass'] as const
  for (const key of sectionKeys) {
    const raw = data?.[key] ?? data?.sections?.[key]
    if (Array.isArray(raw) && raw.length > 0) {
      sectionData[key] = raw.map((r: any, i: number) => makeRow(r.item || r.name || `项目${i + 1}`, i, r))
    } else {
      // 默认骨架：3行投资项目
      sectionData[key] = DEFAULT_ITEMS.map((item, i) => makeRow(item, i))
    }
  }
  auditNote.value = data?.auditNote ?? data?.audit_note ?? ''
  auditConclusion.value = data?.auditConclusion ?? data?.audit_conclusion ?? ''
}

// ═══ TB取数 — 科目1503 ═══════════════════════════════════════════════════════
async function fetchTrialBalance(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await api.get('/api/trial-balance/query', {
      params: { project_id: props.projectId, account_code: '1503' },
      _silent: true,
    } as any)
    const items = res?.data?.items ?? res?.data ?? res?.items ?? []
    if (Array.isArray(items) && items.length > 0) {
      // 汇总叶子科目审定数
      trialBalanceAmount.value = items.reduce(
        (s: number, it: any) => s + parseNum(it.audited_amount ?? it.unadjusted_amount), 0,
      )
    } else if (typeof res?.data === 'number') {
      trialBalanceAmount.value = res.data
    }
  } catch {
    console.warn('[G6TabAdjudication] fetchTrialBalance failed')
  }
}

// ═══ 辅助函数 ═══════════════════════════════════════════════════════════════
function isRateWarning(rate: number | null): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.2
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(2) + '%'
}

function adjRowClassName({ row }: { row: AdjRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  return ''
}

// ═══ 生命周期 ═══════════════════════════════════════════════════════════════
onMounted(() => {
  hydrateData()
  fetchTrialBalance()
})
</script>

<style scoped>
.g6-adjudication { padding: 12px; font-size: 13px; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  line-height: 1.8;
  color: #92400e;
}
.methodology-title { font-weight: 600; margin: 0 0 4px 0; color: #78350f; }
.methodology-context p { margin: 2px 0; }

/* Section 标题栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

/* 虚拟滚动容器 */
.adj-scroll-container { overflow-y: auto; border: 1px solid #ebeef5; border-radius: 4px; padding: 4px; }

/* 分组标题 */
.group-header {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; background: #ecf5ff; border: 1px solid #d9ecff;
  border-radius: 4px; margin-top: 8px; cursor: pointer;
  user-select: none; transition: background 0.2s;
}
.group-header:hover { background: #d9ecff; }
.group-header.formula-header {
  background: #f0f9eb; border-color: #e1f3d8; cursor: default;
}
.group-name { font-weight: 600; font-size: 13px; color: #303133; }
.formula-tag {
  margin-left: auto; font-size: 11px; color: #67c23a;
  background: #f0f9eb; border: 1px solid #e1f3d8;
  padding: 1px 6px; border-radius: 3px;
}
.collapse-icon { transition: transform 0.2s; font-size: 14px; }
.collapse-icon.is-collapsed { transform: rotate(-90deg); }

/* 分组内容 */
.group-body { margin-bottom: 4px; }

/* 表格 */
.adj-table { margin-top: 4px; }

/* 公式列样式（虚线下划线+cursor:help） */
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }

/* 行样式 */
.row-bold { font-weight: 700; }
:deep(.row-subtotal) { background: #f5f7fa !important; font-weight: 700; }
:deep(.row-formula) { background: #f0f9eb !important; font-weight: 700; }

/* 变动率橙色高亮 */
.rate-orange { color: #e6a23c; font-weight: 600; }

/* 原因分析必填提示 */
:deep(.reason-required .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

/* 试算表差异行 */
.tb-diff-row { display: flex; gap: 16px; margin: 16px 0; align-items: center; font-size: 13px; }
.tb-label { font-weight: 500; color: #606266; }
.tb-amount { font-weight: 600; }
.diff-value { font-weight: 600; }
.diff-red { color: #f56c6c; }

/* 审计说明/结论卡片 */
.note-card { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

/* 编制提示 */
.guidance-details {
  margin-top: 16px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 4px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-content p { margin: 4px 0; }
</style>
