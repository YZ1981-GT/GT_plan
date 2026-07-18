<script setup lang="ts">
/**
 * F2TabProductionSales — F2-19 存货产销量变动分析表
 * 库存商品产量/销量/产销比 + 原材料采购/耗用/采购产出比/产耗比 + 说明/结论
 */
import { inject, toRef, type Ref } from 'vue'
import {
  useF2ProductionSales,
  F2_MONTH_LABELS,
  F2_PS_QUESTION_DEFS,
} from '../../composables/useF2ProductionSales'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

const ps = useF2ProductionSales({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const {
  productViews,
  materialViews,
  abnormalCount,
  questions,
  conclusion,
  addProduct,
  removeProduct,
  updateProduct,
  updateProductMonth,
  addMaterial,
  removeMaterial,
  updateMaterial,
  updateMaterialMonth,
  updateQuestion,
  aiContext,
} = ps

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

function fmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  return `${v.toFixed(2)}%`
}

function saveConclusion(v: string) {
  conclusion.value = v
}

async function genAi(
  section: 'f2-19-note' | 'f2-19-conclusion' | 'production-sales-conclusion',
  existing: string,
  title: string,
  apply: (t: string) => void,
) {
  const text = await generateAndConfirm(section, existing, aiContext(), title)
  if (text) apply(text)
}

async function genQuestion(key: typeof F2_PS_QUESTION_DEFS[number]['key'], label: string) {
  await genAi('f2-19-note', questions.value[key], `AI 生成 · ${label}`, (t) => updateQuestion(key, t))
}
</script>

<template>
  <div class="f2-production-sales">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 先填库存商品各月产量、销量；产销比（销量/产量）自动计算；合计、与上年度比较变动率自动计算。</p>
        <p>2. 再填原材料各月采购、耗用；采购产出比≈采购÷关联产品产量，产耗比≈关联产品产量÷耗用（默认产品名1:1关联）。</p>
        <p>3. 变动率绝对值＞20% 标为异常关注；对异常产品进一步执行生产成本及单耗分析（索引如 F2-64）。</p>
        <p>4. 若一产品多材料，请在「关联产品」手工指定对应关系后复核比率。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：获取产销量及材料购耗月度数据，分析产销匹配与购耗产出关系，识别异常波动并为舞弊应对/单耗分析提供方向。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag v-if="abnormalCount > 0" type="danger" size="small">异常关注 {{ abnormalCount }} 项</el-tag>
        <F2ReviewChip section-id="F2-19-analysis" />
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-19"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-19" :context-project-id="projectId" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-64" :context-project-id="projectId" :validate="false" /></span>
      </div>
    </div>

    <!-- 库存商品产量 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">一、库存商品各月产量统计</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addProduct">+ 新增产品</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table :data="productViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.name" size="small"
                @change="(v: string) => updateProduct(row.rowId, 'name', v)" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'p'+mi" :label="lab" width="78" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.prodMonths[mi]" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProductMonth(row.rowId, 'prod', mi, v ?? 0)" />
              <span v-else>{{ fmt(row.prodMonths[mi]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.prodTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.prodPrior" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'prodPrior', v ?? 0)" />
              <span v-else>{{ fmt(row.prodPrior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="{ abnormal: row.isProdAbnormal }">{{ fmtPct(row.prodChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="55" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeProduct(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 库存商品销量 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">二、库存商品各月销售数量统计</span></template>
      <div class="table-scroll">
        <el-table :data="productViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'s'+mi" :label="lab" width="78" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.salesMonths[mi]" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProductMonth(row.rowId, 'sales', mi, v ?? 0)" />
              <span v-else>{{ fmt(row.salesMonths[mi]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.salesTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.salesPrior" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'salesPrior', v ?? 0)" />
              <span v-else>{{ fmt(row.salesPrior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="{ abnormal: row.isSalesAbnormal }">{{ fmtPct(row.salesChange) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 产销比 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">三、库存商品各月销售量与产量占比分析（销量÷产量）</span></template>
      <div class="table-scroll">
        <el-table :data="productViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'r'+mi" :label="lab" width="78" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.ratioMonths[mi]) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.ratioTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.ratioPrior) }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.ratioChange) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 原材料采购 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">四、原材料各月采购统计</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addMaterial">+ 新增材料</el-button>
        </div>
      </template>
      <div class="table-scroll">
        <el-table :data="materialViews" border size="small">
          <el-table-column label="项目" width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.name" size="small"
                @change="(v: string) => updateMaterial(row.rowId, 'name', v)" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="关联产品" width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.linkedProduct" size="small" placeholder="默认=材料名"
                @change="(v: string) => updateMaterial(row.rowId, 'linkedProduct', v)" />
              <span v-else>{{ row.linkedProduct || row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'mp'+mi" :label="lab" width="78" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.purchaseMonths[mi]" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateMaterialMonth(row.rowId, 'purchase', mi, v ?? 0)" />
              <span v-else>{{ fmt(row.purchaseMonths[mi]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.purchaseTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.purchasePrior" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateMaterial(row.rowId, 'purchasePrior', v ?? 0)" />
              <span v-else>{{ fmt(row.purchasePrior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="{ abnormal: row.isPurchaseAbnormal }">{{ fmtPct(row.purchaseChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="55" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeMaterial(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 原材料耗用 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">五、原材料各月耗用统计</span></template>
      <div class="table-scroll">
        <el-table :data="materialViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'mc'+mi" :label="lab" width="78" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.consumeMonths[mi]" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateMaterialMonth(row.rowId, 'consume', mi, v ?? 0)" />
              <span v-else>{{ fmt(row.consumeMonths[mi]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.consumeTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.consumePrior" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateMaterial(row.rowId, 'consumePrior', v ?? 0)" />
              <span v-else>{{ fmt(row.consumePrior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="{ abnormal: row.isConsumeAbnormal }">{{ fmtPct(row.consumeChange) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 采购产出比 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">六、原材料采购 ÷ 库存商品产量比</span>
          <el-tag size="small" type="info">波动异常进一步见 F2-64</el-tag>
        </div>
      </template>
      <div class="table-scroll">
        <el-table :data="materialViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'po'+mi" :label="lab" width="78" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.purchaseOutRatioMonths[mi]) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.purchaseOutRatioTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.purchaseOutRatioPrior) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 产耗比 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">七、产耗比（关联产品产量 ÷ 原材料耗用）</span>
          <el-tag size="small" type="info">波动异常进一步见 F2-64</el-tag>
        </div>
      </template>
      <div class="table-scroll">
        <el-table :data="materialViews" border size="small">
          <el-table-column label="项目" width="120" fixed>
            <template #default="{ row }">{{ row.name || '—' }}</template>
          </el-table-column>
          <el-table-column v-for="(lab, mi) in F2_MONTH_LABELS" :key="'y'+mi" :label="lab" width="78" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.yieldRatioMonths[mi]) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.yieldRatioTotal) }}</template>
          </el-table-column>
          <el-table-column label="上年度" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.yieldRatioPrior) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 审计说明 5问 -->
    <el-card shadow="never" class="block-card audit-note-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">三、审计说明</span>
        </div>
      </template>
      <div v-for="q in F2_PS_QUESTION_DEFS" :key="q.key" class="q-block">
        <div class="note-head">
          <span>{{ q.label }}</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="genQuestion(q.key, q.label)">AI辅助</el-button>
        </div>
        <el-input
          type="textarea"
          :model-value="questions[q.key]"
          :disabled="isReadonly"
          :autosize="{ minRows: 2 }"
          :placeholder="q.placeholder"
          @change="(v: string) => updateQuestion(q.key, v)"
        />
      </div>
    </el-card>

    <!-- 结论 -->
    <el-card class="opinion-card audit-note-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计结论</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="genAi('f2-19-conclusion', conclusion, 'AI 生成 · 产销量分析结论', saveConclusion)"
            >AI辅助</el-button>
            <F2ReviewChip section-id="F2-19-conclusion" />
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="conclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-production-sales { padding: 12px; font-size: 13px; font-size: var(--wp-font-size, 13px); }
.f2-production-sales :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-production-sales :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.card-header-flex { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.table-scroll { overflow-x: auto; }
.abnormal { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.q-block { margin-bottom: 12px; }
.note-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px; font-weight: 500;
}
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
</style>
