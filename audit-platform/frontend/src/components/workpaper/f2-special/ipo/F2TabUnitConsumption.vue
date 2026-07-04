<template>
  <div class="f2-unit-consumption">
    <header class="sheet-header">
      <div class="header-text">
        <h3>主要产品生产成本及单耗分析</h3>
        <span class="sheet-code">F2-64</span>
      </div>
      <div class="stat-cards">
        <div class="stat-card">
          <span class="stat-val">{{ uc.globalSummary.value.productCount }}</span>
          <span class="stat-label">产品</span>
        </div>
        <div class="stat-card">
          <span class="stat-val">{{ uc.globalSummary.value.materialCount }}</span>
          <span class="stat-label">材料行</span>
        </div>
        <div class="stat-card warn">
          <span class="stat-val">{{ uc.globalSummary.value.abnormalCount }}</span>
          <span class="stat-label">异常行</span>
        </div>
        <div class="stat-card impact">
          <span class="stat-val">{{ fmtMoney(uc.globalSummary.value.totalAmountImpact) }}</span>
          <span class="stat-label">金额影响合计</span>
        </div>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="uc.addProduct()">+ 产品</el-button>
      <el-button size="small" :disabled="isReadonly" @click="uc.addMaterial()">+ 材料</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-64"
        :disabled="isReadonly"
        ai-section="consumption-analysis"
        :existing-content="uc.auditNote.value"
        review-section="F2-64-consumption"
        @ai-filled="(t: string) => { uc.auditNote.value = t }"
      />
      <el-input
        v-model="uc.searchQuery.value"
        size="small"
        placeholder="搜索产品 / 材料 / 规格"
        clearable
        prefix-icon="Search"
        class="search"
      />
      <el-segmented v-model="uc.viewMode.value" :options="viewModes" size="small" />
      <template v-if="uc.viewMode.value === 'group'">
        <el-button size="small" link @click="expandAllGroups">全部展开</el-button>
        <el-button size="small" link @click="collapseAllGroups">全部折叠</el-button>
      </template>
    </div>

    <!-- 聚焦录入：左产品导航 + 右区段表格 -->
    <div v-if="uc.viewMode.value === 'focus'" class="focus-layout">
      <aside class="product-nav">
        <div class="nav-title">产品列表</div>
        <el-scrollbar max-height="520">
          <button
            v-for="g in uc.filteredProductGroups.value"
            :key="g.productName"
            type="button"
            class="product-item"
            :class="{ active: uc.selectedProduct.value === g.productName }"
            @click="uc.selectProduct(g.productName)"
          >
            <span class="product-name">{{ g.productName }}</span>
            <span class="product-meta">
              {{ g.materialCount }} 材料
              <el-tag v-if="g.abnormalCount" type="warning" size="small" effect="plain">
                {{ g.abnormalCount }} 异常
              </el-tag>
            </span>
          </button>
        </el-scrollbar>
      </aside>

      <main class="focus-main">
        <div v-if="uc.activeProductGroup.value" class="product-banner">
          <strong>{{ uc.activeProductGroup.value.productName }}</strong>
          <span class="banner-stats">
            材料 {{ uc.activeProductGroup.value.materialCount }} 行
            · 异常 {{ uc.activeProductGroup.value.abnormalCount }}
            · 金额影响 {{ fmtMoney(uc.activeProductGroup.value.totalAmountImpact) }}
            · 最大差异率 {{ uc.activeProductGroup.value.maxDeviationPct.toFixed(1) }}%
          </span>
        </div>

        <el-segmented v-model="uc.activeSegment.value" :options="segments" size="small" class="segment-bar" />

        <el-table
          :data="uc.focusRows.value"
          border
          size="small"
          max-height="440"
          highlight-current-row
          :row-class-name="rowClassName"
        >
          <el-table-column label="材料名称" width="120" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.materialName" size="small"
                @change="(v: string) => uc.updateRow(row.id, { materialName: v })" />
              <span v-else>{{ row.materialName }}</span>
            </template>
          </el-table-column>

          <template v-if="uc.activeSegment.value === 'basic'">
            <el-table-column label="规格" width="90">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.spec" size="small"
                  @change="(v: string) => uc.updateRow(row.id, { spec: v })" />
                <span v-else>{{ row.spec }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单位" width="72">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
                  @change="(v: string) => uc.updateRow(row.id, { unit: v })" />
                <span v-else>{{ row.unit }}</span>
              </template>
            </el-table-column>
          </template>

          <template v-else-if="uc.activeSegment.value === 'consumption'">
            <el-table-column label="标准单耗" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.standardConsumption" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { standardConsumption: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="实际单耗" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.actualConsumption" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { actualConsumption: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="差异率%" width="88" align="right">
              <template #default="{ row }">
                <span :class="devClass(row)">{{ row.deviationPct.toFixed(1) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="材料单价" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.materialUnitPrice" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { materialUnitPrice: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="金额影响" width="105" align="right">
              <template #default="{ row }">
                <span class="formula">{{ fmtMoney(row.amountImpact) }}</span>
              </template>
            </el-table-column>
          </template>

          <template v-else-if="uc.activeSegment.value === 'io'">
            <el-table-column label="本期投入量" width="100">
              <template #default="{ row }">
                <el-input-number :model-value="row.inputQty" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { inputQty: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="本期产出量" width="100">
              <template #default="{ row }">
                <el-input-number :model-value="row.outputQty" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { outputQty: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="投入产出比" width="100" align="right">
              <template #default="{ row }">
                <span :class="ioClass(row)">{{ row.outputQty ? row.ioRatio.toFixed(3) : '—' }}</span>
              </template>
            </el-table-column>
          </template>

          <template v-else-if="uc.activeSegment.value === 'history'">
            <el-table-column label="上期单耗" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.priorConsumption" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { priorConsumption: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="单耗变动率" width="100" align="right">
              <template #default="{ row }">
                <span class="formula">{{ uc.fmtRate(row.consumptionChangeRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="T-1期单耗" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.consumptionT1" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { consumptionT1: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="T-2期单耗" width="95">
              <template #default="{ row }">
                <el-input-number :model-value="row.consumptionT2" size="small" :controls="false"
                  :disabled="isReadonly" class="compact-num"
                  @change="(v: number) => uc.updateRow(row.id, { consumptionT2: v ?? 0 })" />
              </template>
            </el-table-column>
          </template>

          <template v-else>
            <el-table-column label="合理性说明" min-width="140">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.rationalityNote" size="small"
                  @update:model-value="(v: string) => uc.updateRow(row.id, { rationalityNote: v })" />
                <span v-else>{{ row.rationalityNote }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审计关注" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.auditFocus" size="small"
                  @change="(v: string) => uc.updateRow(row.id, { auditFocus: v })" />
                <span v-else>{{ row.auditFocus }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                  @change="(v: string) => uc.updateRow(row.id, { remark: v })" />
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>
          </template>

          <el-table-column label="" width="52" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="uc.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </main>
    </div>

    <!-- 分组折叠浏览 -->
    <div v-else-if="uc.viewMode.value === 'group'" class="group-view">
      <el-collapse v-model="expandedGroups">
        <el-collapse-item
          v-for="g in uc.filteredProductGroups.value"
          :key="g.productName"
          :name="g.productName"
        >
          <template #title>
            <div class="group-title">
              <span class="group-name">{{ g.productName }}</span>
              <el-tag size="small" type="info">{{ g.materialCount }} 材料</el-tag>
              <el-tag v-if="g.abnormalCount" size="small" type="warning">{{ g.abnormalCount }} 异常</el-tag>
              <span class="group-impact">金额影响 {{ fmtMoney(g.totalAmountImpact) }}</span>
            </div>
          </template>
          <el-table :data="g.rows" border size="small" :row-class-name="rowClassName" @row-dblclick="onRowDblClick">
            <el-table-column prop="materialName" label="材料" width="110" />
            <el-table-column prop="spec" label="规格" width="80" />
            <el-table-column label="标准/实际" width="110">
              <template #default="{ row }">{{ row.standardConsumption }} / {{ row.actualConsumption }}</template>
            </el-table-column>
            <el-table-column label="差异率%" width="80" align="right">
              <template #default="{ row }"><span :class="devClass(row)">{{ row.deviationPct.toFixed(1) }}</span></template>
            </el-table-column>
            <el-table-column label="投入产出比" width="95" align="right">
              <template #default="{ row }"><span :class="ioClass(row)">{{ row.ioRatio.toFixed(3) }}</span></template>
            </el-table-column>
            <el-table-column label="金额影响" width="100" align="right">
              <template #default="{ row }">{{ fmtMoney(row.amountImpact) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button link size="small" @click="uc.jumpToRow(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 虚拟滚动速览（232行） -->
    <div v-else class="flat-view">
      <div class="flat-hint">双击行进入聚焦编辑 · 共 {{ uc.flatRows.value.length }} 行 · 虚拟滚动已启用</div>
      <el-table-v2
        :columns="virtualColumns"
        :data="uc.flatRows.value"
        :width="flatWidth"
        :height="480"
        :row-height="36"
        :header-height="40"
        :row-event-handlers="flatRowHandlers"
        fixed
      />
    </div>

    <footer class="sheet-footer">
      <h4>分析结论</h4>
      <el-input v-model="uc.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly"
        placeholder="汇总单耗异常原因、投入产出失衡说明及审计结论…" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, toRef, h } from 'vue'
import { useF2UnitConsumption, type EnrichedUnitConsumptionRow } from '../../composables/useF2UnitConsumption'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const uc = useF2UnitConsumption({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const viewModes = [
  { label: '聚焦录入', value: 'focus' },
  { label: '分组折叠', value: 'group' },
  { label: '全部速览', value: 'flat' },
]

const segments = [
  { label: '基础信息', value: 'basic' },
  { label: '单耗分析', value: 'consumption' },
  { label: '投入产出', value: 'io' },
  { label: '历史对比', value: 'history' },
  { label: '审计说明', value: 'audit' },
]

const expandedGroups = ref<string[]>([])
const flatWidth = ref(1100)

function expandAllGroups(): void {
  expandedGroups.value = uc.filteredProductGroups.value.map((g) => g.productName)
}

function collapseAllGroups(): void {
  expandedGroups.value = []
}

function syncExpandedGroups(): void {
  if (expandedGroups.value.length === 0 && uc.viewMode.value === 'group') {
    expandedGroups.value = uc.filteredProductGroups.value.map((g) => g.productName)
  }
}

function fmtMoney(v: number): string {
  if (!v) return '0'
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function devClass(row: EnrichedUnitConsumptionRow): string {
  return row.isHighDeviation ? 'dev-warn' : 'formula'
}

function ioClass(row: EnrichedUnitConsumptionRow): string {
  return row.isIoImbalance ? 'io-warn' : 'formula'
}

function rowClassName({ row }: { row: EnrichedUnitConsumptionRow }): string {
  if (row.warningLevel === 'both') return 'row-both'
  if (row.warningLevel === 'deviation') return 'row-dev'
  if (row.warningLevel === 'io') return 'row-io'
  return ''
}

function onRowDblClick(row: EnrichedUnitConsumptionRow): void {
  uc.jumpToRow(row)
}

const flatRowHandlers = {
  onDblclick: ({ rowData }: { rowData: EnrichedUnitConsumptionRow }) => uc.jumpToRow(rowData),
}

const virtualColumns = computed(() => [
  { key: 'productName', dataKey: 'productName', title: '产品', width: 100 },
  { key: 'materialName', dataKey: 'materialName', title: '材料', width: 100 },
  { key: 'spec', dataKey: 'spec', title: '规格', width: 80 },
  { key: 'standardConsumption', dataKey: 'standardConsumption', title: '标准单耗', width: 90, align: 'right' },
  { key: 'actualConsumption', dataKey: 'actualConsumption', title: '实际单耗', width: 90, align: 'right' },
  {
    key: 'deviationPct', dataKey: 'deviationPct', title: '差异率%', width: 80, align: 'right',
    cellRenderer: ({ rowData }: { rowData: EnrichedUnitConsumptionRow }) =>
      h('span', { class: devClass(rowData) }, rowData.deviationPct.toFixed(1)),
  },
  { key: 'inputQty', dataKey: 'inputQty', title: '投入量', width: 80, align: 'right' },
  { key: 'outputQty', dataKey: 'outputQty', title: '产出量', width: 80, align: 'right' },
  {
    key: 'ioRatio', dataKey: 'ioRatio', title: '投入产出比', width: 95, align: 'right',
    cellRenderer: ({ rowData }: { rowData: EnrichedUnitConsumptionRow }) =>
      h('span', { class: ioClass(rowData) }, rowData.outputQty ? rowData.ioRatio.toFixed(3) : '—'),
  },
  {
    key: 'amountImpact', dataKey: 'amountImpact', title: '金额影响', width: 100, align: 'right',
    cellRenderer: ({ cellData }: { cellData: number }) => h('span', {}, fmtMoney(cellData)),
  },
  {
    key: 'auditFocus', dataKey: 'auditFocus', title: '审计关注', width: 120,
  },
])

function updateFlatWidth(): void {
  const el = document.querySelector('.f2-unit-consumption')
  if (el) flatWidth.value = Math.max(900, el.clientWidth - 24)
}

onMounted(() => {
  updateFlatWidth()
  window.addEventListener('resize', updateFlatWidth)
  syncExpandedGroups()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateFlatWidth)
})
</script>

<style scoped>
.f2-unit-consumption {
  padding: 12px 16px;
  font-size: 13px;
  background: linear-gradient(180deg, #f8fafc 0%, #fff 120px);
  border-radius: 8px;
}

.sheet-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.header-text h3 { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.sheet-code {
  font-size: 12px; color: #909399; background: #f0f2f5;
  padding: 2px 8px; border-radius: 4px; margin-left: 8px;
}

.stat-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.stat-card {
  min-width: 88px; padding: 8px 14px; border-radius: 8px;
  background: #fff; border: 1px solid #ebeef5;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
  display: flex; flex-direction: column; align-items: center;
}
.stat-card.warn { border-color: #faecd8; background: #fffbf0; }
.stat-card.impact { border-color: #d9ecff; background: #f0f9ff; }
.stat-val { font-size: 18px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-label { font-size: 11px; color: #909399; margin-top: 2px; }

.toolbar {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  margin-bottom: 12px; padding: 8px 10px;
  background: #fff; border-radius: 8px; border: 1px solid #ebeef5;
}
.search { width: 200px; }

.focus-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  min-height: 520px;
}

.product-nav {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}
.nav-title {
  padding: 10px 12px;
  font-weight: 600;
  font-size: 12px;
  color: #606266;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}
.product-item {
  display: flex; flex-direction: column; align-items: flex-start;
  width: 100%; padding: 10px 12px; border: none; background: transparent;
  border-bottom: 1px solid #f2f3f5; cursor: pointer; text-align: left;
  transition: background .15s;
}
.product-item:hover { background: #f5f7fa; }
.product-item.active {
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  padding-left: 9px;
}
.product-name { font-weight: 500; color: #303133; margin-bottom: 4px; }
.product-meta { font-size: 11px; color: #909399; display: flex; gap: 6px; align-items: center; }

.focus-main {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}
.product-banner {
  margin-bottom: 10px; padding: 8px 12px;
  background: linear-gradient(90deg, #ecf5ff, #fff);
  border-radius: 6px; border-left: 3px solid #409eff;
}
.banner-stats { margin-left: 12px; font-size: 12px; color: #606266; }
.segment-bar { margin-bottom: 10px; }

.group-view :deep(.el-collapse-item__header) { font-size: 13px; }
.group-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.group-name { font-weight: 600; }
.group-impact { font-size: 12px; color: #909399; margin-left: auto; }

.flat-view { background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 8px; }
.flat-hint { font-size: 12px; color: #909399; margin-bottom: 6px; padding: 0 4px; }

.formula { text-decoration: underline dotted #909399; }
.dev-warn { color: #e6a23c; font-weight: 600; background: #fdf6ec; padding: 0 4px; border-radius: 2px; }
.io-warn { color: #f56c6c; font-weight: 600; background: #fef0f0; padding: 0 4px; border-radius: 2px; }

:deep(.row-dev) { background: #fdf6ec !important; }
:deep(.row-io) { background: #fef0f0 !important; }
:deep(.row-both) { background: #fde2e2 !important; }

:deep(.compact-num) { width: 100%; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 6px; }

.sheet-footer { margin-top: 16px; }
.sheet-footer h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }

@media (max-width: 960px) {
  .focus-layout { grid-template-columns: 1fr; }
  .product-nav { max-height: 200px; }
}
</style>
