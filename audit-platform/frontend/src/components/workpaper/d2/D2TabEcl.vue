<script setup lang="ts">
/**
 * D2TabEcl — ECL测算D2-9+D2-10
 * el-tabs: 单项ECL(D2-9) | 计量测试(D2-10)
 * D2-9: 8列 + 合计 + 差异高亮
 * D2-10: 折现法 + 迁徙率矩阵
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { useD2Ecl, type EclSingleRow, type MigrationRateRow, type EclDiscountRow } from '../composables/useD2Ecl'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2SaveInject } from '../composables/useD2SaveInject'
import { useAgingConfig } from '@/composables/useAgingConfig'
import type { ImportableSheet } from '../composables/useD2ImportExport'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import D2ReferenceBlock from './D2ReferenceBlock.vue'
import { ECL_REFERENCE_SECTIONS, ECL_REFERENCE_SOURCE } from '../composables/d2ReferenceExamples'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = withDefaults(defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** D2-9 单项测算 | D2-10 计量测试；默认展示双 Tab */
  eclFocus?: 'D2-9' | 'D2-10' | 'both'
}>(), {
  eclFocus: 'both',
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const crossSheet = inject('d2CrossSheet') as any

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const { saveItems } = useD2SaveInject()

// 账龄段联动
const { bands: agingConfigBands } = useAgingConfig(toRef(props, 'projectId'), 'D2')
const agingBandsLabels = computed(() => agingConfigBands.value?.map((b: any) => b.label || b.name || b) || [])

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.debtorName || row?.fromBand || 'unknown'
  openReviewDialog(`D2-ecl-${rowKey}-${field}`)
}

const activeTab = ref(props.eclFocus === 'D2-10' ? 'measurement' : 'single')
const showEclTabs = computed(() => props.eclFocus === 'both')

/** D2-9/D2-10 均支持 xlsx 导入导出 */
const eclImportSheet = computed((): ImportableSheet | null => {
  if (props.eclFocus === 'D2-10') return 'D2-10'
  if (props.eclFocus === 'D2-9') return 'D2-9'
  return activeTab.value === 'single' ? 'D2-9' : 'D2-10'
})

const { onExportTemplate, onExportData, onImportFile, importExportEnabled } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  eclImportSheet,
)

const {
  singleRows,
  singleTotal,
  discountRows,
  migrationMatrix,
  outputLossRates,
  migrationChangeWarning,
  importFromDetail,
  addSingleRow,
  removeSingleRow,
  addDiscountRow,
  removeDiscountRow,
  updateCell,
  updateScenario,
} = useD2Ecl({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  agingBands: agingBandsLabels,
})

function fmtAmt(v: number): string {
  if (v == null || Number.isNaN(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number): string {
  if (v === 0) return '-'
  return (v * 100).toFixed(2) + '%'
}

/** 百分比输入辅助：内部存小数，UI 用百分数 */
function toPctInput(v: number): number {
  return Number((v * 100).toFixed(4))
}
function fromPctInput(v: number | null): number {
  return (Number(v) || 0) / 100
}

// ─── 审计说明（inline 存储）─────────────────────────────────────────────────
const NOTE_KEY = 'D2-ecl-note'
const auditNote = ref('')
onMounted(() => { auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || '' })

function saveNote(v: string): void {
  if (props.isReadonly) return
  auditNote.value = v
  const item = { item_id: NOTE_KEY, conclusion: null, remark: v }
  props.allResponses.set(NOTE_KEY, item)
  void saveItems([item])
}

const { aiAvailable, generateAndConfirm } = useD2AiGenerate(toRef(props, 'wpId'))
const aiLoadingNote = ref(false)

async function generateNoteAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm('ecl-note', auditNote.value, {
      sheet: props.eclFocus,
      singleCount: singleRows.value.length,
      singleShouldProvision: singleTotal.value.shouldProvision,
      singleDifference: singleTotal.value.difference,
    }, 'AI · 预期信用损失说明')
    if (text) saveNote(text)
  } finally { aiLoadingNote.value = false }
}

const GUIDANCE_TEXTS = [
  '预期信用损失（ECL，CAS 22）：以违约概率（PD）、违约损失率（LGD）、违约风险敞口（EAD）为基础，结合前瞻性信息计量减值准备。',
  '单项测算（D2-9）：对单项金额重大或存在客观减值证据的应收款单独测算，应计提 = 审定余额 × 预期损失率。',
  '计量测试（D2-10）：组合按账龄迁徙率连乘推算预期损失率，或采用现金流折现法（多情景概率加权）。',
  '前瞻性调整：应考虑宏观经济指标（GDP、行业景气度等）对损失率的影响；迁徙率较上期大幅变动需说明原因（联动 D2-8）。',
]
</script>

<template>
  <div class="d2-tab-ecl">
    <div class="tab-header">
      <h4>{{ eclFocus === 'D2-10' ? '预期信用损失计量测试 D2-10' : eclFocus === 'D2-9' ? '应收坏账准备测算 D2-9' : '预期信用损失（D2-9 / D2-10）' }}</h4>
      <GtReviewTrigger section-id="D2-ecl-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>测算并验证应收账款预期信用损失，评价单项/组合计提方法、损失率及前瞻性调整的合理性（CAS 22）。</p>
      </template>
    </el-alert>

    <!-- ECL↔D2-3坏账准备勾稽提醒 -->
    <el-alert
      v-if="crossSheet?.eclVsBadDebtDiff?.value && !crossSheet.eclVsBadDebtDiff.value.isBalanced"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 8px"
    >
      <template #title>
        D2-10 ECL单项合计({{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.eclTotal) }})
        与D2-3坏账准备期末({{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.badDebtCurrent) }})
        差异 {{ fmtAmt(crossSheet.eclVsBadDebtDiff.value.diff) }} 元，请核实
      </template>
    </el-alert>

    <!-- 源模板示例内嵌编制参考 -->
    <D2ReferenceBlock
      title="ECL 计量编制参考（三要素 / 账龄对照 / 单项概率加权 / 前瞻性打分卡）"
      :source="ECL_REFERENCE_SOURCE"
      :sections="ECL_REFERENCE_SECTIONS as any"
    />

    <div class="tab-toolbar">
      <div v-if="importExportEnabled" class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
      <div v-else class="toolbar-left" />
    </div>

    <el-tabs v-model="activeTab" :class="{ 'single-mode': !showEclTabs }">
      <!-- D2-9 单项ECL -->
      <el-tab-pane v-if="eclFocus !== 'D2-10'" label="单项ECL (D2-9)" name="single">
        <div class="section-actions">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addSingleRow">添加债务人</el-button>
          <el-button size="small" :disabled="isReadonly" @click="importFromDetail">从D2-2导入单项计提</el-button>
        </div>

        <el-table :data="singleRows" border size="small" style="width: 100%">
          <el-table-column label="债务人" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
              <span v-else>{{ row.debtorName }}</span>
              <GtReviewDot row-prefix="D2-ecl" :row-key="row.rowId" />
            </template>
          </el-table-column>
          <el-table-column label="审定余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'auditedBalance', v || 0)" />
              <span v-else>{{ displayPrefs.fmtAmount(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期损失率%" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="toPctInput(row.expectedLossRate)" size="small" :controls="false" :precision="2" :min="0" :max="100" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'expectedLossRate', fromPctInput(v))" />
              <span v-else>{{ fmtPct(row.expectedLossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="应计提" width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="= 审定余额 × 预期损失率（自动计算）" placement="top">
                <span class="calc-cell">{{ displayPrefs.fmtAmount(row.shouldProvision) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="实际余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.actualBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'actualBalance', v || 0)" />
              <span v-else>{{ displayPrefs.fmtAmount(row.actualBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip content="= 实际余额 − 应计提（自动计算）" placement="top">
                <span class="calc-cell" :style="{ color: row.difference !== 0 ? '#f56c6c' : '' }">{{ displayPrefs.fmtAmount(row.difference) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.basis" size="small" placeholder="计提依据" @change="(v: string) => updateCell(row.rowId, 'basis', v)" />
              <span v-else>{{ row.basis || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" v-if="!isReadonly">
            <template #default="{ row }">
              <el-button type="danger" link size="small" @click="removeSingleRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="total-bar">
          <span class="total-label">合计</span>
          <span>审定余额: {{ displayPrefs.fmtAmount(singleTotal.auditedBalance) }}</span>
          <span>应计提: {{ displayPrefs.fmtAmount(singleTotal.shouldProvision) }}</span>
          <span :style="{ color: singleTotal.difference !== 0 ? '#f56c6c' : '' }">
            差异: {{ displayPrefs.fmtAmount(singleTotal.difference) }}
          </span>
        </div>
      </el-tab-pane>

      <!-- D2-10 计量测试 -->
      <el-tab-pane v-if="eclFocus !== 'D2-9'" label="计量测试 (D2-10)" name="measurement">
        <!-- 迁徙率变动警告 -->
        <el-alert v-if="migrationChangeWarning" type="warning" :closable="false" class="migration-alert">
          <span>{{ migrationChangeWarning }}</span>
          <GtIndexChip
            v-if="jumpToSection"
            label="D2-8"
            class="warn-chip"
            @click="jumpToSection('坏账准备计提会计政策检查D2-8')"
          />
        </el-alert>

        <!-- 折现法区域 -->
        <div class="sub-section">
          <div class="sub-header">
            <span class="sub-title">单项折现法ECL</span>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addDiscountRow">添加债务人</el-button>
          </div>
          <el-collapse v-if="discountRows.length > 0">
            <el-collapse-item v-for="dr in discountRows" :key="dr.rowId" :title="`${dr.debtorName || '未命名'} - 余额${displayPrefs.fmtAmount(dr.balance)}`">
              <div class="scenario-grid">
                <div v-for="(s, idx) in dr.scenarios" :key="idx" class="scenario-item">
                  <span class="scenario-name">{{ s.scenarioName }}</span>
                  <span>概率: {{ (s.probability * 100).toFixed(0) }}%</span>
                  <span>现值: {{ displayPrefs.fmtAmount(s.presentValue) }}</span>
                  <span>加权: {{ displayPrefs.fmtAmount(s.weighted) }}</span>
                </div>
              </div>
              <div class="discount-result">
                预期损失率: <b>{{ fmtPct(dr.expectedLossRate) }}</b>
                <el-button v-if="!isReadonly" type="danger" link size="small" style="margin-left:12px" @click="removeDiscountRow(dr.rowId)">删除</el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-else description="暂无折现法ECL数据" :image-size="40" />
        </div>

        <!-- 迁徙率矩阵 -->
        <div class="sub-section">
          <div class="sub-header">
            <span class="sub-title">组合迁徙率矩阵</span>
          </div>
          <el-table :data="migrationMatrix" border size="small" style="width: 100%">
            <el-table-column prop="agingBand" label="账龄段" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.agingBand" size="small" placeholder="账龄段" @change="(v: string) => updateCell(row.rowId, 'agingBand', v)" />
                <span v-else>{{ row.agingBand }}</span>
              </template>
            </el-table-column>
            <el-table-column label="第1年%" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="toPctInput(row.year1Rate)" size="small" :controls="false" :precision="2" :min="0" :max="100" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'year1Rate', fromPctInput(v))" />
                <span v-else>{{ fmtPct(row.year1Rate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="第2年%" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="toPctInput(row.year2Rate)" size="small" :controls="false" :precision="2" :min="0" :max="100" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'year2Rate', fromPctInput(v))" />
                <span v-else>{{ fmtPct(row.year2Rate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="第3年%" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="toPctInput(row.year3Rate)" size="small" :controls="false" :precision="2" :min="0" :max="100" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'year3Rate', fromPctInput(v))" />
                <span v-else>{{ fmtPct(row.year3Rate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="平均迁徙率" width="100" align="right">
              <template #default="{ row }"><span class="calc-cell">{{ fmtPct(row.avgRate) }}</span></template>
            </el-table-column>
            <el-table-column label="预期损失率" width="110" align="right">
              <template #default="{ row }">
                <el-tooltip content="账龄段迁徙率连乘（自动计算）" placement="top">
                  <span class="calc-cell" style="font-weight:600">{{ fmtPct(row.expectedLossRate) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 审计说明 -->
    <div class="section-subtitle">
      审计说明
      <GtReviewTrigger section-id="D2-ecl-note" />
      <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
        <el-button size="small" text type="primary" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNoteAI">🤖 AI 生成</el-button>
      </el-tooltip>
      <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D2-ecl-note')">💬 复核</el-button>
    </div>
    <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" placeholder="记录 ECL 测算方法、损失率依据、前瞻性调整及计提充分性评价..." :disabled="isReadonly" @change="saveNote" />

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-ecl { padding: 12px; }
.d2-tab-ecl :deep(.single-mode > .el-tabs__header) { display: none; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.calc-cell { color: #909399; font-variant-numeric: tabular-nums; }
.section-subtitle { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
.section-actions { margin-bottom: 10px; display: flex; gap: 8px; }
.total-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; }
.migration-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; vertical-align: middle; }
.sub-section { margin-bottom: 20px; }
.sub-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sub-title { font-weight: 600; font-size: 14px; }
.scenario-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }
.scenario-item { display: flex; flex-direction: column; gap: 2px; font-size: 12px; padding: 6px; background: #f5f7fa; border-radius: 4px; }
.scenario-name { font-weight: 600; }
.discount-result { font-size: 13px; padding: 6px 0; }
</style>
