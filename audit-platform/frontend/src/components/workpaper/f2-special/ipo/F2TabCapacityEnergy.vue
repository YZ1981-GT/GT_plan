<template>
  <div class="f2-val-sheet f2-capacity-energy f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>存货产量与产能、能耗分析表</h3>
        <span class="code">F2-63 · 产能利用 / 库存容量 / 能耗匹配三维验证</span>
      </div>
      <div class="stat-row">
        <span class="stat">已填 {{ ce.filledCount.value }} 行</span>
        <el-tag v-if="ce.abnormalCount.value" type="danger" size="small">
          异常 {{ ce.abnormalCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 第一部分比较各存货本年产量与全年产能，产能利用率自动计算，超 100% 标红须说明原因。</p>
        <p>2. 第二部分按仓库比较期末实际库存量与库存容量，同一仓库多行填写相同仓库名称即自动生成小计。</p>
        <p>3. 第三部分先对比水/电/燃气/蒸汽等能源本期与上期的采购数量、金额（单价自动计算），再按产品测算单位能耗并与上年比较，变动率超 ±20% 标红。</p>
        <p>4. 灰底列均为自动计算列；审计说明、审计结论支持 AI 起草。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ce.addCapacityRow()">+ 产能比较行</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="ce.addStorageRow()">+ 库存比较行</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="ce.addProductEnergyRow()">+ 产品能耗行</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-63"
          :disabled="isReadonly"
          review-section="F2-63-capacity"
        />
        <GtIndexChip value="wp:F2-63" />
      </div>
    </div>

    <!-- 一、实际产量与产能比较分析 -->
    <section class="analysis-section">
      <div class="major-title">
        <span>一、实际产量与产能比较分析</span>
        <el-button size="small" link type="primary" :disabled="isReadonly" @click="ce.addCapacityRow()">新增行</el-button>
      </div>
      <div class="table-scroll">
        <table class="matrix-table capacity-table">
          <thead>
            <tr>
              <th class="col-name">存货名称</th>
              <th>本年产量</th>
              <th>全年产能</th>
              <th class="calc-head">产能利用率</th>
              <th class="col-remark">备注</th>
              <th class="col-act" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in ce.capacityRows.value" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
              <td class="col-name">
                <el-input v-if="!isReadonly" :model-value="row.inventoryName" size="small" placeholder="存货名称"
                  @update:model-value="(v: string) => ce.updateCapacityRow(row.id, { inventoryName: v })" />
                <span v-else>{{ row.inventoryName || '—' }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.annualOutput" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateCapacityRow(row.id, { annualOutput: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.annualOutput) }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.annualCapacity" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateCapacityRow(row.id, { annualCapacity: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.annualCapacity) }}</span>
              </td>
              <td class="calc-cell" :class="{ 'val-warn': row.isAbnormal }">{{ fmtPct(row.utilizationRate) }}</td>
              <td class="col-remark">
                <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注"
                  @update:model-value="(v: string) => ce.updateCapacityRow(row.id, { remark: v })" />
                <span v-else>{{ row.remark || '—' }}</span>
              </td>
              <td class="col-act">
                <el-button v-if="!isReadonly && ce.capacityRows.value.length > 1" link type="danger" size="small"
                  @click="ce.removeCapacityRow(row.id)">删</el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 二、期末库存与库存容量比较 -->
    <section class="analysis-section">
      <div class="major-title">
        <span>二、期末库存与库存容量比较</span>
        <el-button size="small" link type="primary" :disabled="isReadonly" @click="ce.addStorageRow()">新增行</el-button>
      </div>
      <div class="table-scroll">
        <table class="matrix-table storage-table">
          <thead>
            <tr>
              <th class="col-name">仓库名称</th>
              <th class="col-name">存货名称</th>
              <th>实际库存量</th>
              <th>库存容量</th>
              <th class="calc-head">容量利用率</th>
              <th>已有订单数量</th>
              <th>已有订单金额</th>
              <th>期后销售数量</th>
              <th>期后销售金额</th>
              <th class="col-act" />
            </tr>
          </thead>
          <tbody>
            <template v-for="group in ce.storageGroups.value" :key="group.warehouseName">
              <tr v-for="row in group.rows" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
                <td class="col-name">
                  <el-input v-if="!isReadonly" :model-value="row.warehouseName" size="small" placeholder="仓库名称"
                    @update:model-value="(v: string) => ce.updateStorageRow(row.id, { warehouseName: v })" />
                  <span v-else>{{ row.warehouseName || '—' }}</span>
                </td>
                <td class="col-name">
                  <el-input v-if="!isReadonly" :model-value="row.inventoryName" size="small" placeholder="存货名称"
                    @update:model-value="(v: string) => ce.updateStorageRow(row.id, { inventoryName: v })" />
                  <span v-else>{{ row.inventoryName || '—' }}</span>
                </td>
                <td v-for="field in storageStockFields" :key="field">
                  <el-input-number v-if="!isReadonly" :model-value="row[field]" size="small" :controls="false" class="compact-num"
                    @change="(v: number | undefined) => ce.updateStorageRow(row.id, { [field]: v ?? 0 })" />
                  <span v-else class="num">{{ fmt(row[field]) }}</span>
                </td>
                <td class="calc-cell" :class="{ 'val-warn': row.isAbnormal }">{{ fmtPct(row.utilizationRate) }}</td>
                <td v-for="field in storageOrderFields" :key="field">
                  <el-input-number v-if="!isReadonly" :model-value="row[field]" size="small" :controls="false" class="compact-num"
                    @change="(v: number | undefined) => ce.updateStorageRow(row.id, { [field]: v ?? 0 })" />
                  <span v-else class="num">{{ fmt(row[field]) }}</span>
                </td>
                <td class="col-act">
                  <div class="act-cell">
                    <el-button v-if="!isReadonly" link type="primary" size="small"
                      @click="ce.addStorageRow(row.warehouseName)">增</el-button>
                    <el-button v-if="!isReadonly && ce.sheet.value.storageRows.length > 1" link type="danger" size="small"
                      @click="ce.removeStorageRow(row.id)">删</el-button>
                  </div>
                </td>
              </tr>
              <tr class="row-subtotal">
                <td colspan="2" class="subtotal-label">{{ group.warehouseName }}小计</td>
                <td class="num">{{ fmt(group.subtotal.actualStock) }}</td>
                <td class="num">{{ fmt(group.subtotal.storageCapacity) }}</td>
                <td class="calc-cell" :class="{ 'val-warn': (group.subtotal.utilizationRate ?? 0) > 1 }">
                  {{ fmtPct(group.subtotal.utilizationRate) }}
                </td>
                <td class="num">{{ fmt(group.subtotal.orderQty) }}</td>
                <td class="num">{{ fmt(group.subtotal.orderAmount) }}</td>
                <td class="num">{{ fmt(group.subtotal.postSaleQty) }}</td>
                <td class="num">{{ fmt(group.subtotal.postSaleAmount) }}</td>
                <td class="col-act" />
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 三、实际产量与能耗比较分析 -->
    <section class="analysis-section">
      <div class="major-title">
        <span>三、实际产量与能耗比较分析</span>
        <el-button size="small" link type="primary" :disabled="isReadonly" @click="ce.addEnergyRow()">新增能源项目</el-button>
      </div>

      <div class="sub-title">（一）能源采购本期与上期对比</div>
      <div class="table-scroll">
        <table class="matrix-table energy-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-name">采购项目</th>
              <th colspan="3">本期</th>
              <th colspan="3">上期</th>
              <th rowspan="2" class="calc-head">单价变动率</th>
              <th rowspan="2" class="col-act" />
            </tr>
            <tr>
              <th>采购数量</th>
              <th>采购金额</th>
              <th class="calc-head">单价</th>
              <th>采购数量</th>
              <th>采购金额</th>
              <th class="calc-head">单价</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in ce.energyRows.value" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
              <td class="col-name">
                <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" placeholder="如：水、电、燃气"
                  @update:model-value="(v: string) => ce.updateEnergyRow(row.id, { itemName: v })" />
                <span v-else>{{ row.itemName || '—' }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.currentQty" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateEnergyRow(row.id, { currentQty: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.currentQty) }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateEnergyRow(row.id, { currentAmount: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.currentAmount) }}</span>
              </td>
              <td class="calc-cell">{{ fmtPrice(row.currentUnitPrice) }}</td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.priorQty" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateEnergyRow(row.id, { priorQty: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.priorQty) }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateEnergyRow(row.id, { priorAmount: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.priorAmount) }}</span>
              </td>
              <td class="calc-cell">{{ fmtPrice(row.priorUnitPrice) }}</td>
              <td class="calc-cell" :class="{ 'val-warn': row.isAbnormal }">{{ fmtRate(row.priceChangeRate) }}</td>
              <td class="col-act">
                <el-button v-if="!isReadonly && ce.energyRows.value.length > 1" link type="danger" size="small"
                  @click="ce.removeEnergyRow(row.id)">删</el-button>
              </td>
            </tr>
            <tr class="row-subtotal">
              <td class="subtotal-label">合计</td>
              <td />
              <td class="num">{{ fmt(ce.energyTotals.value.currentAmount) }}</td>
              <td class="calc-cell" />
              <td />
              <td class="num">{{ fmt(ce.energyTotals.value.priorAmount) }}</td>
              <td class="calc-cell" />
              <td class="calc-cell" />
              <td class="col-act" />
            </tr>
          </tbody>
        </table>
      </div>

      <div class="sub-title with-action">
        <span>（二）产品单位能耗与上年比较</span>
        <el-button size="small" link type="primary" :disabled="isReadonly" @click="ce.addProductEnergyRow()">新增产品</el-button>
      </div>
      <div class="table-scroll">
        <table class="matrix-table product-energy-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-name">产品</th>
              <th rowspan="2">本年产量</th>
              <th colspan="3">耗用能耗</th>
              <th rowspan="2" class="calc-head">单位能耗</th>
              <th rowspan="2">上年单位能耗</th>
              <th rowspan="2" class="calc-head">变动</th>
              <th rowspan="2" class="calc-head">变动率</th>
              <th rowspan="2" class="col-act" />
            </tr>
            <tr>
              <th>水</th>
              <th>电</th>
              <th>燃气</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in ce.productEnergyRows.value" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
              <td class="col-name">
                <el-input v-if="!isReadonly" :model-value="row.productName" size="small" placeholder="产品名称"
                  @update:model-value="(v: string) => ce.updateProductEnergyRow(row.id, { productName: v })" />
                <span v-else>{{ row.productName || '—' }}</span>
              </td>
              <td v-for="field in productNumFields" :key="field">
                <el-input-number v-if="!isReadonly" :model-value="row[field]" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateProductEnergyRow(row.id, { [field]: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row[field]) }}</span>
              </td>
              <td class="calc-cell">{{ fmtPrice(row.unitEnergy) }}</td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.priorUnitEnergy" size="small" :controls="false" class="compact-num"
                  @change="(v: number | undefined) => ce.updateProductEnergyRow(row.id, { priorUnitEnergy: v ?? 0 })" />
                <span v-else class="num">{{ fmt(row.priorUnitEnergy) }}</span>
              </td>
              <td class="calc-cell">{{ fmtPrice(row.change) }}</td>
              <td class="calc-cell" :class="{ 'val-warn': row.isAbnormal }">{{ fmtRate(row.changeRate) }}</td>
              <td class="col-act">
                <el-button v-if="!isReadonly && ce.productEnergyRows.value.length > 1" link type="danger" size="small"
                  @click="ce.removeProductEnergyRow(row.id)">删</el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 四、审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计说明</span>
        </div>
      </template>
      <div class="note-block">
        <div class="note-label">
          <span>1. 实际产量与产能异常的原因，与同行业产能利用率差异的原因：</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('capacity-utilization-note')">AI 起草</el-button>
        </div>
        <el-input v-model="ce.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }"
          placeholder="说明产能利用率异常（超100%或过低）的原因及与同行业的差异……" :disabled="isReadonly" />
      </div>
      <div class="note-block">
        <div class="note-label">
          <span>2. 期末实际库存与库存容量比较异常的原因：</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('storage-capacity-note')">AI 起草</el-button>
        </div>
        <el-input :model-value="storageNote" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }"
          placeholder="说明库存量超出容量或利用率异常仓库的原因、监盘及期后核查情况……" :disabled="isReadonly"
          @update:model-value="(v: string) => saveExtraNote('storage', v)" />
      </div>
      <div class="note-block">
        <div class="note-label">
          <span>3. 能耗异常原因：</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('energy-consumption-note')">AI 起草</el-button>
        </div>
        <el-input :model-value="energyNote" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }"
          placeholder="说明能源采购单价及产品单位能耗变动异常的原因与核查过程……" :disabled="isReadonly"
          @update:model-value="(v: string) => saveExtraNote('energy', v)" />
      </div>
    </el-card>

    <!-- 五、审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('capacity-energy-conclusion')">AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        :disabled="isReadonly" @update:model-value="saveAuditConclusion" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <p v-for="(tip, i) in tips" :key="i">{{ tip }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, toRef, type Ref } from 'vue'
import { useF2CapacityEnergy } from '../../composables/useF2CapacityEnergy'
import { F2_63_OBJECTIVE, F2_63_TIPS } from '../../composables/useF2CapacityEnergyFormulas'
import {
  useF2SpecialAiGenerate,
  type F2SpeAiSection,
} from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ce = useF2CapacityEnergy({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_63_OBJECTIVE
const tips = F2_63_TIPS
const storageStockFields = ['actualStock', 'storageCapacity'] as const
const storageOrderFields = ['orderQty', 'orderAmount', 'postSaleQty', 'postSaleAmount'] as const
const productNumFields = ['annualOutput', 'waterUsage', 'elecUsage', 'gasUsage'] as const

// ─── 审计说明 2/3 与审计结论（组件级持久化，走 f2-spe:save-items） ────────
const STORAGE_NOTE_KEY = 'F2-63-note-storage'
const ENERGY_NOTE_KEY = 'F2-63-note-energy'
const CONCLUSION_KEY = 'F2-63-audit-conclusion'
const LEGACY_NOTE_KEY = 'F2-63-audit-note'

const storageNote = ref('')
const energyNote = ref('')
const auditConclusion = ref('')

function persistItem(key: string, value: string): void {
  const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

function saveExtraNote(kind: 'storage' | 'energy', value: string): void {
  if (props.isReadonly) return
  if (kind === 'storage') {
    storageNote.value = value
    persistItem(STORAGE_NOTE_KEY, value)
  } else {
    energyNote.value = value
    persistItem(ENERGY_NOTE_KEY, value)
  }
}

function saveAuditConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  persistItem(CONCLUSION_KEY, value)
}

onMounted(() => {
  storageNote.value = props.allResponses.get(STORAGE_NOTE_KEY)?.remark || ''
  energyNote.value = props.allResponses.get(ENERGY_NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
  // 旧页面独立“审计说明”迁入第1条说明，避免历史文本丢失。
  const legacyNote = props.allResponses.get(LEGACY_NOTE_KEY)?.remark
  if (!ce.auditNote.value && legacyNote) ce.auditNote.value = legacyNote
})

// ─── AI ───────────────────────────────────────────────────────────────
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-63',
    abnormalCount: ce.abnormalCount.value,
    capacityCompare: ce.capacityRows.value.slice(0, 20).map((r) => ({
      inventoryName: r.inventoryName,
      annualOutput: r.annualOutput,
      annualCapacity: r.annualCapacity,
      utilizationRate: r.utilizationRate,
      isAbnormal: r.isAbnormal,
      remark: r.remark,
    })),
    storageCompare: ce.storageGroups.value.slice(0, 10).map((g) => ({
      warehouseName: g.warehouseName,
      subtotal: g.subtotal,
      rows: g.rows.slice(0, 10).map((r) => ({
        inventoryName: r.inventoryName,
        actualStock: r.actualStock,
        storageCapacity: r.storageCapacity,
        utilizationRate: r.utilizationRate,
        orderQty: r.orderQty,
        postSaleQty: r.postSaleQty,
        isAbnormal: r.isAbnormal,
      })),
    })),
    energyPurchase: ce.energyRows.value.slice(0, 12).map((r) => ({
      itemName: r.itemName,
      currentUnitPrice: r.currentUnitPrice,
      priorUnitPrice: r.priorUnitPrice,
      priceChangeRate: r.priceChangeRate,
      isAbnormal: r.isAbnormal,
    })),
    productEnergy: ce.productEnergyRows.value.slice(0, 20).map((r) => ({
      productName: r.productName,
      annualOutput: r.annualOutput,
      unitEnergy: r.unitEnergy,
      priorUnitEnergy: r.priorUnitEnergy,
      changeRate: r.changeRate,
      isAbnormal: r.isAbnormal,
    })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const titleMap: Partial<Record<F2SpeAiSection, string>> = {
    'capacity-utilization-note': 'AI 起草 · 产能利用异常说明',
    'storage-capacity-note': 'AI 起草 · 库存容量比较说明',
    'energy-consumption-note': 'AI 起草 · 能耗异常说明',
    'capacity-energy-conclusion': 'AI 生成 · 审计结论',
  }
  const existing = section === 'capacity-utilization-note'
    ? ce.auditNote.value
    : section === 'storage-capacity-note'
      ? storageNote.value
      : section === 'energy-consumption-note'
        ? energyNote.value
        : auditConclusion.value
  const text = await generateAndConfirm(section, existing || '', aiContext(), titleMap[section] || 'AI 生成')
  if (!text) return
  if (section === 'capacity-utilization-note') ce.auditNote.value = text
  else if (section === 'storage-capacity-note') saveExtraNote('storage', text)
  else if (section === 'energy-consumption-note') saveExtraNote('energy', text)
  else saveAuditConclusion(text)
}

// ─── 格式化 ───────────────────────────────────────────────────────────
function fmt(value: number): string {
  if (!Number.isFinite(value) || value === 0) return '—'
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(2)}%`
}

function fmtRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2IpoSoftStyles.css"></style>
<style scoped>
.f2-capacity-energy { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }

.analysis-section { margin: 18px 0; }
.major-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: linear-gradient(90deg, #ede5f5, #faf8fc);
  border-left: 4px solid var(--gt-purple);
  color: #3f2465;
  font-size: 14px;
  font-weight: 700;
}
.sub-title {
  margin: 10px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #55347f;
}
.sub-title.with-action { display: flex; align-items: center; justify-content: space-between; }

.table-scroll { overflow-x: auto; max-width: 100%; }
.matrix-table {
  width: 100%;
  min-width: 860px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
}
.storage-table { min-width: 1100px; }
.energy-table { min-width: 980px; }
.product-energy-table { min-width: 1000px; }
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 4px 6px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}
.matrix-table thead th.calc-head { background: #6b4d8f; }
.col-name { min-width: 110px; text-align: left !important; }
.col-remark { min-width: 140px; text-align: left !important; }
.col-act { width: 62px; min-width: 62px; }
.act-cell { display: flex; gap: 2px; justify-content: center; }
.calc-cell {
  color: #4b2d77;
  font-weight: 500;
  background: #faf8fc !important;
  text-align: right !important;
  white-space: nowrap;
}
.num { text-align: right !important; white-space: nowrap; }
span.num { display: block; }
.row-subtotal td { background: #f0ebf5 !important; font-weight: 600; }
.subtotal-label { text-align: left !important; color: #3f2465; }
.row-error td { background: #fef0f0 !important; }
.val-warn { color: #c45656 !important; font-weight: 700; background: #fef0f0 !important; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 10px 14px; background: #faf8fc; border-bottom: 1px solid #e4dcee; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 700; color: #3f2465; }
.note-block { margin-bottom: 12px; }
.note-block:last-child { margin-bottom: 0; }
.note-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
  color: #55347f;
  font-weight: 600;
}

.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box p { margin: 0 0 4px; }

:deep(.compact-num) { width: 88px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 11px; }
</style>
