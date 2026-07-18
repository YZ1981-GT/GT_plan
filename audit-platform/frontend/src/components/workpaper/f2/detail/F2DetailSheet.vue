<template>
  <div class="f2-detail-sheet">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">{{ config.categoryLabel }}明细表 {{ config.sheetCode }}</h3>
        <el-tag size="small" effect="plain">科目 {{ config.accountCode }}</el-tag>
      </div>
      <p class="hero-sub">{{ heroSub }}</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <template v-if="isDispatched">
          <p>1. 按购货单位列示发出商品：名称及规格、单位；期初 → 本期转入 → 本期转出 → 期末结存 → 期后结转。</p>
          <p>2. 灰色列为自动计算：期末 = 期初 + 转入 − 转出；单价 = 金额 ÷ 数量；库龄合计须等于期末金额。</p>
          <p>3. 「期后结转」登记资产负债表日后销售结转；页尾用销售台账出库数量与本期转出数量勾稽差异。</p>
          <p>4. 合计 − 跌价准备 = 发出商品净额；库龄较长与跌价项目须在审计说明中写明。</p>
        </template>
        <template v-else-if="isInTransit">
          <p>1. 按供货单位列示材料采购/在途物资：名称及规格、单位；期初 → 本期购进 → 本期转出 → 期末结存 → 期后结转。</p>
          <p>2. 灰色列为自动计算：期末 = 期初 + 购进 − 转出；单价 = 金额 ÷ 数量；库龄合计须等于期末金额。</p>
          <p>3. 「期后结转」登记资产负债表日后入库/结转情况，与审计说明第1问勾稽。</p>
          <p>4. 页尾合计 − 跌价准备 = 材料采购/在途物资净额；可用收发存/库龄/完整切换视图。</p>
        </template>
        <template v-else-if="hasSalesOrderCols">
          <p>1. 列示库存商品明细：编码/名称/规格/单位，期初 → 本期购进 → 本期发出 → 期末结存（数量·单价·金额）。</p>
          <p>2. 库龄与品质后填「是否有在手订单 / 订单编号 / 销售单价」；页尾用销售台账出库数量与本期发出数量勾稽差异。</p>
          <p>3. 合计 − 跌价准备 = 库存商品净额；计价方法、重大变动、库龄较长、跌价原因写入审计说明。</p>
          <p>4. 可用「收发存 / 库龄 / 完整」切换视图。</p>
        </template>
        <template v-else>
          <p>1. 列示{{ config.categoryLabel }}明细：编码/名称/规格/单位，期初 → 本期购进 → 本期发出 → 期末结存（数量·单价·金额）。</p>
          <p>2. 灰色列为自动计算：期末 = 期初 + 购进 − 发出；单价 = 金额 ÷ 数量；库龄各段合计须等于期末金额。</p>
          <p>3. 页尾「合计 − 跌价准备 = {{ config.categoryLabel }}净额」；库龄较长项目须在审计说明中写明原因。</p>
          <p>4. 可用「收发存 / 库龄 / 完整」切换视图；宽表建议先在收发存核对勾稽，再填库龄与品质。</p>
        </template>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      :title="auditObjective"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">
          {{ isPartyMode ? '新增明细' : '新增品名' }}
        </el-button>
        <el-input
          v-model="detail.searchText.value"
          size="small"
          clearable
          :placeholder="searchPlaceholder"
          class="search"
        />
        <span class="muted">库龄口径</span>
        <el-select
          v-model="agingPresetModel"
          size="small"
          class="aging-sel"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-radio-group v-model="detail.activeView.value" size="small">
          <el-radio-button value="movement">收发存</el-radio-button>
          <el-radio-button value="aging">库龄</el-radio-button>
          <el-radio-button value="full">完整</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="detail.totals.value.agingOk" type="success" size="small" effect="dark">库龄 OK</el-tag>
        <el-tag v-else type="danger" size="small">库龄与期末不匹配</el-tag>
        <el-tag v-if="detail.agingMismatch.value.length" type="warning" size="small">
          {{ detail.agingMismatch.value.length }} 行库龄异常
        </el-tag>
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          :sheet="sheetCode"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip :value="'wp:' + config.sheetCode" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="detail.filteredRows.value"
      border
      size="small"
      class="detail-table"
      :max-height="detail.useVirtualScroll.value ? 520 : undefined"
      :row-class-name="rowClass"
    >
      <!-- 身份列：存货 vs 对方单位（在途/发出） -->
      <template v-if="isPartyMode">
        <el-table-column :label="partyColumnLabel" width="140" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.supplier"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { supplier: v })"
            />
          </template>
        </el-table-column>
        <el-table-column :label="materialNameLabel" min-width="180" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.itemName"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { itemName: v })"
            />
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="存货编码" width="100" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.itemCode"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { itemCode: v })"
            />
          </template>
        </el-table-column>
        <el-table-column :label="itemNameLabel" min-width="140" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.itemName"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { itemName: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="规格" width="100">
          <template #default="{ row }">
            <el-input
              :model-value="row.spec"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { spec: v })"
            />
          </template>
        </el-table-column>
      </template>
      <el-table-column label="单位" width="72">
        <template #default="{ row }">
          <el-input
            :model-value="row.unit"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => detail.updateRow(row.id, { unit: v })"
          />
        </template>
      </el-table-column>

      <template v-if="showMove">
        <el-table-column label="期初库存" align="center">
          <el-table-column v-if="config.hasQuantity" label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openingQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { openingQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="config.hasQuantity" label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.openingUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openingAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { openingAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column :label="increaseGroupLabel" align="center">
          <el-table-column v-if="config.hasQuantity" label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.increaseQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { increaseQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="config.hasQuantity" label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.increaseUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.increaseAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { increaseAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column :label="decreaseGroupLabel" align="center">
          <el-table-column v-if="config.hasQuantity" label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decreaseQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { decreaseQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="config.hasQuantity" label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.decreaseUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decreaseAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { decreaseAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末结存" align="center">
          <el-table-column v-if="config.hasQuantity" label="数量" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.closingQty }}</span></template>
          </el-table-column>
          <el-table-column v-if="config.hasQuantity" label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.unitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closingAmt) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="hasPostPeriod" label="期后结转" align="center">
          <el-table-column v-if="config.hasQuantity" label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.postPeriodQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { postPeriodQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="config.hasQuantity" label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.postPeriodUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.postPeriodAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { postPeriodAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="config.extraColumnLabel" :label="config.extraColumnLabel" width="110">
          <template #default="{ row }">
            <el-input
              :model-value="row.extra"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { extra: v })"
            />
          </template>
        </el-table-column>
      </template>

      <template v-if="showAging">
        <el-table-column label="账龄" align="center">
          <el-table-column
            v-for="seg in detail.segments.value"
            :key="seg.key"
            :label="seg.label"
            width="100"
          >
            <template #default="{ row }">
              <el-input-number
                :model-value="Number(row.aging?.[seg.key] ?? 0)"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateAgingCell(row.id, seg.key, v ?? 0)"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="库龄合计" width="100" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="Math.abs(row.agingTotal - row.closingAmt) > 0.01 ? 'bad' : 'formula'">
              {{ fmtAmt(row.agingTotal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!showMove" label="期末金额" width="110" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closingAmt) }}</span></template>
        </el-table-column>
        <el-table-column label="品质状况" width="100">
          <template #default="{ row }">
            <el-select
              :model-value="row.qualityStatus"
              size="small"
              clearable
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { qualityStatus: v || '' })"
            >
              <el-option v-for="o in QUALITY" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
        <template v-if="hasSalesOrderCols">
          <el-table-column label="是否有在手订单" width="120">
            <template #default="{ row }">
              <el-select
                :model-value="row.hasOpenOrder"
                size="small"
                clearable
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { hasOpenOrder: v || '' })"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="订单编号" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.orderNo"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { orderNo: v })"
              />
            </template>
          </el-table-column>
          <el-table-column label="销售单价" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.salesUnitPrice === '' ? undefined : Number(row.salesUnitPrice)"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => detail.updateRow(row.id, { salesUnitPrice: v ?? '' })"
              />
            </template>
          </el-table-column>
        </template>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="detail.removeRow(row.id)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">合计（期末金额）</span>
        <span class="val">{{ fmtAmt(detail.totals.value.closingAmt) }}</span>
        <span v-if="showMove" class="muted tiny">
          期初 {{ fmtAmt(detail.totals.value.openingAmt) }}
          · {{ increaseShort }} {{ fmtAmt(detail.totals.value.increaseAmt) }}
          · {{ decreaseShort }} {{ fmtAmt(detail.totals.value.decreaseAmt) }}
          <template v-if="hasPostPeriod">
            · 期后结转 {{ fmtAmt(detail.totals.value.postPeriodAmt) }}
          </template>
        </span>
      </div>
      <div class="summary-row">
        <span class="lab">减：存货跌价准备</span>
        <el-input-number
          :model-value="detail.impairmentProvision.value"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @change="(v: number | undefined) => detail.persistImpairment(v ?? 0)"
        />
      </div>
      <div class="summary-row net">
        <span class="lab">{{ config.categoryLabel }}净额</span>
        <span class="val">{{ fmtAmt(detail.netAmt.value) }}</span>
      </div>
      <template v-if="hasSalesLedgerRecon">
        <div class="summary-row">
          <span class="lab">销售出库数量（销售台账）</span>
          <el-input-number
            :model-value="detail.salesLedgerQty.value"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => detail.persistSalesLedgerQty(v ?? 0)"
          />
          <span class="muted tiny">本期{{ decreaseShort }}数量合计 {{ detail.totals.value.decreaseQty }}</span>
        </div>
        <div class="summary-row">
          <span class="lab">差异</span>
          <span :class="Math.abs(detail.salesLedgerDiff.value) > 0.01 ? 'bad' : 'val'">
            {{ detail.salesLedgerDiff.value }}
          </span>
          <el-tag
            v-if="Math.abs(detail.salesLedgerDiff.value) <= 0.01"
            type="success"
            size="small"
            effect="dark"
          >OK</el-tag>
        </div>
      </template>
    </section>

    <section class="notes-panel">
      <h4>审计说明</h4>
      <div v-for="f in noteFields" :key="f.key" class="note-block">
        <div class="note-label">
          <span>{{ f.label }}</span>
          <el-button
            size="small"
            text
            type="primary"
            :disabled="isReadonly || !aiAvailable || aiBusyKey === f.key"
            :loading="aiBusyKey === f.key"
            @click="generateNote(f)"
          >AI</el-button>
        </div>
        <el-input
          type="textarea"
          :rows="2"
          :model-value="detail.notePack.value[f.packKey]"
          :disabled="isReadonly"
          :placeholder="f.placeholder"
          @change="(v: string) => detail.persistNotePack({ [f.packKey]: v })"
        />
      </div>
    </section>

    <section class="notes-panel conclusion">
      <div class="note-label">
        <span>审计结论</span>
        <el-button
          size="small"
          text
          type="primary"
          :disabled="isReadonly || !aiAvailable || aiBusyKey === 'conclusion'"
          :loading="aiBusyKey === 'conclusion'"
          @click="generateConclusion"
        >AI</el-button>
      </div>
      <el-input
        type="textarea"
        :rows="3"
        :model-value="detail.auditConclusion.value"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="(v: string) => detail.persistConclusion(v)"
      />
      <p v-if="isDispatched" class="muted tiny tip">
        审计提示：关注期后结转与销售确认是否一致；差异产品退换货情况应在说明中披露。
      </p>
    </section>

    <el-dialog v-model="showCustomDialog" title="自定义库龄段" width="420px" @close="cancelCustomAging">
      <p class="muted">每行一个库龄段名称</p>
      <el-input v-model="customInput" type="textarea" :rows="6" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, ref, type Ref } from 'vue'
import {
  useF2DetailSheet,
  type F2DetailRow,
} from '../../composables/useF2DetailSheet'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { F2DetailSheetConfig } from './f2DetailSheetConfigs'
import type { AgingPreset } from '@/composables/useAgingConfig'

const QUALITY = ['正常', '残次', '霉变', '毁损', '滞销', '积压']

const props = defineProps<{
  config: F2DetailSheetConfig
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const configRef = computed(() => props.config)
const sheetCode = computed(() => props.config.sheetCode)
const isInTransit = computed(
  () => props.config.identityMode === 'inTransit' || props.config.noteProfile === 'inTransit',
)
const isDispatched = computed(
  () => props.config.identityMode === 'dispatched' || props.config.noteProfile === 'dispatched',
)
const isPartyMode = computed(() => isInTransit.value || isDispatched.value)
const hasPostPeriod = computed(() => !!props.config.hasPostPeriod)
const hasSalesOrderCols = computed(() => !!props.config.hasSalesOrderCols)
const hasSalesLedgerRecon = computed(() => !!props.config.hasSalesLedgerRecon)
const decreaseGroupLabel = computed(() => props.config.decreaseGroupLabel || '本期发出')
const increaseGroupLabel = computed(() => props.config.increaseGroupLabel || '本期购进')
const itemNameLabel = computed(() => props.config.itemNameLabel || '存货名称')
const partyColumnLabel = computed(() =>
  props.config.partyColumnLabel || (isDispatched.value ? '购货单位' : '供货单位'),
)
const materialNameLabel = computed(() =>
  props.config.materialNameLabel
    || (isDispatched.value ? '发出商品名称及规格' : '采购物资名称及规格'),
)
const increaseShort = computed(() =>
  increaseGroupLabel.value.replace(/^本期/, '') || '购进',
)
const decreaseShort = computed(() =>
  decreaseGroupLabel.value.replace(/^本期/, '') || '发出',
)
const heroSub = computed(() => {
  if (isDispatched.value) return '购货单位 · 转入/转出 · 期后结转 · 销售台账勾稽 · 跌价净额'
  if (isInTransit.value) return '供货单位 · 收发存/转出 · 期后结转 · 库龄 · 跌价净额'
  if (hasSalesOrderCols.value) return '收发存 · 在手订单 · 销售台账勾稽 · 库龄 · 跌价净额'
  return '收发存勾稽 · 库龄分布 · 跌价净额 · 四问审计说明'
})
const auditObjective = computed(() => {
  if (isDispatched.value) {
    return '审计目标：核实发出商品期末余额的存在与准确，验证转入转出与期后结转，勾稽销售台账，评价库龄及跌价计提充分性。'
  }
  if (isInTransit.value) {
    return '审计目标：核实材料采购/在途物资期末余额的存在与准确，验证收发存与期后结转，评价库龄及跌价计提充分性。'
  }
  return `审计目标：核实${props.config.categoryLabel}明细期末余额的存在与准确，验证收发存勾稽及库龄分布合理性，识别长期积压与跌价风险。`
})
const searchPlaceholder = computed(() => {
  if (isDispatched.value) return '搜索购货单位 / 商品名称…'
  if (isInTransit.value) return '搜索供货单位 / 物资名称…'
  return '搜索编码 / 名称 / 规格…'
})

const detail = useF2DetailSheet({
  config: configRef,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const showMove = computed(() => detail.activeView.value === 'movement' || detail.activeView.value === 'full')
const showAging = computed(() => detail.activeView.value === 'aging' || detail.activeView.value === 'full')

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

const noteFields = computed(() => {
  const cat = props.config.categoryLabel
  if (isDispatched.value) {
    return [
      {
        key: 'valuation',
        packKey: 'valuationMethod' as const,
        section: 'detail-valuation' as F2AiSection,
        label: '1. 资产负债表日后销售情况：',
        placeholder: '资产负债表日后销售情况：',
      },
      {
        key: 'change',
        packKey: 'significantChange' as const,
        section: 'detail-change' as F2AiSection,
        label: '2. 本期重大变动原因：',
        placeholder: '发出商品本期发生重大变动的原因：',
      },
      {
        key: 'longAging',
        packKey: 'longAgingReason' as const,
        section: 'detail-long-aging' as F2AiSection,
        label: '3. 库龄较长的原因：',
        placeholder: '发出商品——库龄较长的原因：',
      },
      {
        key: 'impairment',
        packKey: 'impairmentReason' as const,
        section: 'detail-impairment' as F2AiSection,
        label: '4. 计提跌价准备的主要项目及原因：',
        placeholder: '计提跌价准备的主要项目及原因：',
      },
    ]
  }
  if (isInTransit.value) {
    return [
      {
        key: 'valuation',
        packKey: 'valuationMethod' as const,
        section: 'detail-valuation' as F2AiSection,
        label: '1. 在途物资资产负债表日后入库情况：',
        placeholder: '在途物资资产负债表日后入库情况：',
      },
      {
        key: 'change',
        packKey: 'significantChange' as const,
        section: 'detail-change' as F2AiSection,
        label: '2. 本期重大变动原因：',
        placeholder: '物资采购/在途物资本期发生重大变动的原因：',
      },
      {
        key: 'longAging',
        packKey: 'longAgingReason' as const,
        section: 'detail-long-aging' as F2AiSection,
        label: '3. 账龄较长的原因：',
        placeholder: '物资采购/在途物资账龄较长的原因：',
      },
      {
        key: 'impairment',
        packKey: 'impairmentReason' as const,
        section: 'detail-impairment' as F2AiSection,
        label: '4. 计提跌价准备的主要项目及原因：',
        placeholder: '计提跌价准备的主要项目及原因：',
      },
    ]
  }
  return [
    {
      key: 'valuation',
      packKey: 'valuationMethod' as const,
      section: 'detail-valuation' as F2AiSection,
      label: '1. 计价方法：',
      placeholder: `${cat}计价方法：`,
    },
    {
      key: 'change',
      packKey: 'significantChange' as const,
      section: 'detail-change' as F2AiSection,
      label: '2. 本期重大变动原因：',
      placeholder: `${cat}本期发生重大变动的原因：`,
    },
    {
      key: 'longAging',
      packKey: 'longAgingReason' as const,
      section: 'detail-long-aging' as F2AiSection,
      label: '3. 库龄较长的原因：',
      placeholder: `${cat}——库龄较长的原因：`,
    },
    {
      key: 'impairment',
      packKey: 'impairmentReason' as const,
      section: 'detail-impairment' as F2AiSection,
      label: '4. 计提跌价准备的主要项目及原因：',
      placeholder: '计提跌价准备的主要项目及原因：',
    },
  ]
})

async function generateNote(f: (typeof noteFields.value)[number]) {
  aiBusyKey.value = f.key
  try {
    const text = await generateAndConfirm(
      f.section,
      detail.notePack.value[f.packKey],
      {
        sheetCode: sheetCode.value,
        sheetName: props.config.categoryLabel,
        noteProfile: props.config.noteProfile || 'standard',
        noteHint: f.label,
        closingAmt: detail.totals.value.closingAmt,
        netAmt: detail.netAmt.value,
        agingOk: detail.totals.value.agingOk,
        postPeriodAmt: detail.totals.value.postPeriodAmt,
        rowCount: detail.rows.value.length,
      },
      `AI 生成 · ${sheetCode.value} ${f.label}`,
    )
    if (text) detail.persistNotePack({ [f.packKey]: text })
  } finally {
    aiBusyKey.value = null
  }
}

async function generateConclusion() {
  aiBusyKey.value = 'conclusion'
  try {
    const text = await generateAndConfirm(
      'detail-conclusion',
      detail.auditConclusion.value,
      {
        sheetCode: sheetCode.value,
        sheetName: props.config.categoryLabel,
        closingAmt: detail.totals.value.closingAmt,
        netAmt: detail.netAmt.value,
        agingOk: detail.totals.value.agingOk,
      },
      `AI · ${sheetCode.value} 审计结论`,
    )
    if (text) detail.persistConclusion(text)
  } finally {
    aiBusyKey.value = null
  }
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

function fmtAmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPrice(v: number | ''): string {
  if (v === '' || v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
function rowClass({ row }: { row: F2DetailRow }): string {
  const parts: string[] = []
  if (Math.abs(row.agingTotal - row.closingAmt) > 0.01) parts.push('warn-row')
  if (detail.isLongTermRow(row)) parts.push('long-term-row')
  return parts.join(' ')
}

const agingPresetModel = computed({
  get: () => detail.agingPreset.value,
  set: (v: AgingPreset) => { detail.agingPreset.value = v },
})
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  detail.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : detail.agingPreset.value,
)

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = detail.customSegments.value.length
      ? detail.customSegments.value.map((s) => s.label)
      : ['1年以内', '1-2年', '2-3年', '3年以上']
    customInput.value = labels.join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  detail.applyAgingPreset(val)
}
function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!detail.applyAgingPreset('CUSTOM', lines)) return
  showCustomDialog.value = false
}
function cancelCustomAging() {
  showCustomDialog.value = false
  if (!detail.customSegments.value.length) detail.applyAgingPreset(lastNonCustomPreset.value)
  else detail.agingPreset.value = 'CUSTOM'
}
</script>

<style scoped>
.f2-detail-sheet {
  --f2-ink: #1f2a37;
  --f2-muted: #6b7280;
  --f2-line: #e5e7eb;
  --f2-primary: #2563eb;
  --f2-soft: #f8fafc;
  padding: 12px 14px 28px;
  color: var(--f2-ink);
  font-size: var(--wp-font-size, 13px);
}
.hero {
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 55%, #ecfdf5 100%);
  border: 1px solid var(--f2-line);
}
.hero-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-title { margin: 0; font-size: 17px; font-weight: 650; }
.hero-sub { margin: 6px 0 0; color: var(--f2-muted); font-size: 13px; }
.guidance {
  margin-bottom: 10px;
  border-left: 3px solid var(--f2-primary);
  background: #eff6ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance summary { cursor: pointer; font-weight: 500; color: var(--f2-primary); }
.guidance-body { margin-top: 8px; color: #4b5563; line-height: 1.6; }
.guidance-body p { margin: 2px 0; }
.obj-alert { margin-bottom: 12px; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 200px; }
.aging-sel { width: 110px; }
.muted { color: var(--f2-muted); font-size: 12px; }
.tiny { font-size: 12px; margin-left: 8px; }
.chip { display: inline-flex; }
.detail-table { width: 100%; margin-bottom: 12px; }
.detail-table :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.formula { border-bottom: 1px dashed #c0c4cc; }
.bad { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fef6e8; }
:deep(.long-term-row) { background: #fdf6ec; }
.summary-panel {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid var(--f2-line);
  border-radius: 8px;
  background: var(--f2-soft);
}
.summary-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}
.summary-row .lab { min-width: 160px; color: #374151; }
.summary-row .val { font-weight: 600; font-variant-numeric: tabular-nums; }
.summary-row.net {
  border-top: 1px dashed var(--f2-line);
  margin-top: 4px;
  padding-top: 10px;
}
.summary-row.net .val { color: var(--f2-primary); font-size: 15px; }
.notes-panel { margin-top: 16px; }
.notes-panel h4 { margin: 0 0 10px; font-size: 14px; }
.note-block { margin-bottom: 10px; }
.note-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-weight: 500;
  color: #374151;
}
.conclusion { margin-top: 14px; }
</style>
