<script setup lang="ts">
/**
 * D2TabAnalysis — 分析程序D2-5
 * 卡片布局: 周转率|周转天数|坏账率|账龄分布|前五大集中度
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD2Analysis } from '../composables/useD2Analysis'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import type { useD2CrossSheet } from '../composables/useD2CrossSheet'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const {
  indicators,
  turnoverDaysWarning,
  dataSource,
  remark,
  updateMetaField,
} = useD2Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-5',
)

function fmtPct(v: number): string {
  return (v * 100).toFixed(2) + '%'
}
function fmtDays(v: number): string {
  return v === 0 ? '-' : v.toFixed(1) + '天'
}
function fmtRate(v: number): string {
  return v === 0 ? '-' : v.toFixed(2)
}

const crossSheet = inject<ReturnType<typeof useD2CrossSheet> | null>('d2CrossSheet', null)

const displayAging = computed(() => {
  if (indicators.value.agingDistribution.length > 0) return indicators.value.agingDistribution
  const a = crossSheet?.agingFromDetail.value.audited
  if (!a) return []
  const bands = [
    { band: '一年以内', amount: a.within1Year },
    { band: '一到二年', amount: a.y1to2 },
    { band: '二到三年', amount: a.y2to3 },
    { band: '三到四年', amount: a.y3to4 },
    { band: '四到五年', amount: a.y4to5 },
    { band: '五年以上', amount: a.over5 },
  ]
  const total = bands.reduce((s, b) => s + b.amount, 0)
  return bands.map(b => ({ ...b, ratio: total === 0 ? 0 : b.amount / total }))
})

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))

async function onAiAnalysisNote(): Promise<void> {
  const content = await generateAndConfirm('analysis-note', remark.value, {
    turnoverRate: indicators.value.turnoverRate,
    turnoverDays: indicators.value.turnoverDays,
    badDebtRate: indicators.value.badDebtRate,
    top5Concentration: indicators.value.top5Concentration,
  }, 'AI 生成分析程序备注')
  if (content) updateMetaField('remark', content)
}
</script>

<template>
  <div class="d2-tab-analysis">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag type="info" size="small">分析程序</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>

    <!-- 周转天数警告 -->
    <el-alert v-if="turnoverDaysWarning" type="warning" :closable="false" class="warning-alert">
      <span>{{ turnoverDaysWarning }}</span>
      <GtIndexChip
        v-if="jumpToSection"
        label="D2-1"
        class="warn-chip"
        @click="jumpToSection('审定表D2-1')"
      />
    </el-alert>

    <!-- 指标卡片 -->
    <div class="cards-grid">
      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">周转率</span></template>
        <div class="card-value">{{ fmtRate(indicators.turnoverRate) }}</div>
        <div class="card-label">应收账款周转率 = 营业收入 / 平均应收</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header>
          <span class="card-title">周转天数</span>
          <el-tag v-if="turnoverDaysWarning" type="warning" size="small">变动过大</el-tag>
        </template>
        <div class="card-value">{{ fmtDays(indicators.turnoverDays) }}</div>
        <div class="card-sub">上期: {{ fmtDays(indicators.priorTurnoverDays) }}</div>
        <div class="card-sub">变动: {{ (indicators.turnoverDaysChange * 100).toFixed(1) }}%</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">坏账率</span></template>
        <div class="card-value">{{ fmtPct(indicators.badDebtRate) }}</div>
        <div class="card-label">坏账准备 / 应收账款总额</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card">
        <template #header><span class="card-title">前五大集中度</span></template>
        <div class="card-value">{{ fmtPct(indicators.top5Concentration) }}</div>
        <div class="card-label">前五大客户余额占总余额比</div>
      </el-card>

      <el-card shadow="hover" class="indicator-card wide">
        <template #header><span class="card-title">账龄分布</span></template>
        <el-table :data="displayAging" size="small" border v-if="displayAging.length > 0">
          <el-table-column prop="band" label="账龄段" />
          <el-table-column label="金额" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="占比" width="80" align="right">
            <template #default="{ row }">{{ (row.ratio * 100).toFixed(1) }}%</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无账龄分布数据" :image-size="40" />
      </el-card>
    </div>

    <!-- 手动输入区 -->
    <el-card class="manual-area" shadow="never">
      <template #header><span class="card-title">手动输入</span></template>
      <el-form label-width="80px" size="small">
        <el-form-item label="数据来源">
          <div class="field-with-review">
            <el-input
              :model-value="dataSource"
              :disabled="isReadonly"
              placeholder="请输入数据来源说明"
              @change="(v: string) => updateMetaField('dataSource', v)"
            />
            <GtReviewTrigger section-id="D2-analysis-dataSource" />
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <div class="remark-row">
            <el-input
              :model-value="remark"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="分析程序备注"
              @change="(v: string) => updateMetaField('remark', v)"
            />
            <div class="remark-actions">
              <GtReviewTrigger section-id="D2-analysis-remark" />
              <el-button v-if="aiAvailable && !isReadonly" size="small" type="primary" plain @click="onAiAnalysisNote">🤖 AI生成</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.d2-tab-analysis { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.warning-alert { margin-bottom: 12px; }
.warn-chip { margin-left: 8px; vertical-align: middle; }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
.indicator-card.wide { grid-column: span 2; }
.card-title { font-weight: 600; font-size: 14px; }
.card-value { font-size: 24px; font-weight: 700; color: #303133; margin-bottom: 4px; }
.card-label { font-size: 12px; color: #909399; }
.card-sub { font-size: 12px; color: #606266; }
.manual-area { margin-top: 16px; }
.remark-row { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.field-with-review { display: flex; align-items: center; gap: 4px; width: 100%; }
.field-with-review .el-input { flex: 1; }
.remark-actions { display: flex; gap: 8px; align-items: center; }
</style>
