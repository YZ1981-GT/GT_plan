<template>
  <div class="f2-inspect">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <header class="ic-hero">
      <div>
        <div class="ic-kicker">{{ ic.sheetCode }} · 账→单 · 采购入库</div>
        <h2 class="ic-title">{{ ic.title }}</h2>
        <p class="ic-sub">从记账凭证追查至入库单、质检、物流与采购发票，测试发生/存在与计价。</p>
      </div>
      <div class="ic-actions">
        <GtIndexChip value="wp:F2-33" :context-project-id="projectId" />
        <F2ReviewChip section-id="F2-33-conclusion" />
        <el-tag size="small" :type="ic.isCoverageLow.value ? 'warning' : 'success'">
          覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%
        </el-tag>
        <el-tag v-if="ic.abnormalCount.value" size="small" type="danger">异常 {{ ic.abnormalCount.value }}</el-tag>
      </div>
    </header>

    <details class="ic-guide guidance-details">
      <summary>编制提示</summary>
      <ol>
        <li>测试内容：原始凭证是否齐全；记账凭证与原始凭证是否相符；会计处理是否正确；是否计入正确会计期间。</li>
        <li>覆盖率偏低时应扩大样本量或说明理由；关注三单匹配（入库/发票/账）与暂估跨期。</li>
        <li>在「三、测试」中用抽凭引擎抽取存货借方样本，或导入 Excel；行级 📎 可 OCR 回填单据。</li>
      </ol>
    </details>

    <!-- 一、审计目标（默认折叠，不占首屏） -->
    <details class="ic-card ic-card--muted ic-objectives">
      <summary>一、审计目标</summary>
      <ul class="ic-list">
        <li>资产负债表中记录的存货是存在的，且已经记录在恰当的账户中</li>
        <li>记录的存货由被审计单位拥有或控制</li>
        <li>存货以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述</li>
      </ul>
    </details>

    <!-- 二、样本选取标准与规模（对齐 Excel 六格） -->
    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>二、样本选取标准与规模</h3>
          <p>描述测试总体、特定样本与抽样过程；可用 AI 起草抽样过程说明</p>
        </div>
      </header>
      <div class="ic-meta-grid">
        <div class="ic-field span2">
          <label>测试总体 <span class="ic-field-hint">如借方发生额共 XX 笔、金额 XX</span></label>
          <el-input
            :model-value="ic.meta.value.populationDesc"
            :disabled="isReadonly"
            type="textarea"
            :rows="2"
            placeholder="如存货借方发生额所有凭证共 XX 笔金额 XX"
            @update:model-value="(v: string) => ic.updateMeta({ populationDesc: v })"
          />
        </div>
        <div class="ic-field">
          <label>特定样本</label>
          <el-input
            :model-value="ic.meta.value.specificSamples"
            :disabled="isReadonly"
            type="textarea"
            :rows="2"
            placeholder="大额、关联方、异常款项全部测试，共 XX 笔"
            @update:model-value="(v: string) => ic.updateMeta({ specificSamples: v })"
          />
        </div>
        <div class="ic-field">
          <label>抽样总体</label>
          <el-input
            :model-value="ic.meta.value.samplingPopulation"
            :disabled="isReadonly"
            placeholder="测试总体扣除特定样本以外的样本"
            @update:model-value="(v: string) => ic.updateMeta({ samplingPopulation: v })"
          />
        </div>
        <div class="ic-field">
          <label>确定的抽样样本量</label>
          <el-input
            :model-value="ic.meta.value.sampleSize"
            :disabled="isReadonly"
            placeholder="抽取 XX 笔"
            @update:model-value="(v: string) => ic.updateMeta({ sampleSize: v })"
          />
        </div>
        <div class="ic-field">
          <label>抽样方法</label>
          <el-input
            :model-value="ic.meta.value.samplingMethod"
            :disabled="isReadonly"
            placeholder="随机选样 / 系统选样 / MUS / 随意选样"
            @update:model-value="(v: string) => ic.updateMeta({ samplingMethod: v })"
          />
        </div>
        <div class="ic-field span3">
          <label>
            抽样过程
            <el-tooltip :content="aiTip" placement="top">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="runAi('inspection-sampling-note')"
              >🤖 AI辅助抽样过程</el-button>
            </el-tooltip>
          </label>
          <el-input
            :model-value="ic.meta.value.samplingProcess"
            :disabled="isReadonly"
            type="textarea"
            :rows="3"
            placeholder="使用 IDEA / 抽凭引擎选择样本的过程与结果索引"
            @update:model-value="(v: string) => ic.updateMeta({ samplingProcess: v })"
          />
        </div>
      </div>
    </section>

    <!-- 三、测试（主舞台） -->
    <section class="ic-card ic-card--stage">
      <header class="ic-card-head">
        <div>
          <h3>三、测试</h3>
          <p class="test-hint">核对：原始凭证齐全 · 账证相符 · 会计处理正确 · 期间正确</p>
        </div>
      </header>

      <div class="ic-stage-toolbar">
        <div class="ic-stage-toolbar-left">
          <CycleImportExportDropdown
            v-if="wpId"
            :wp-id="wpId"
            api-prefix="f2-val"
            sheet="F2-33"
            expanded
            :disabled="isReadonly"
            @imported="onImported"
          />
          <el-button
            v-if="!isReadonly && wpId && projectId"
            size="small"
            type="primary"
            plain
            @click="samplingVisible = true"
          >⚡ 自动抽凭</el-button>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="ic.addRow()">+ 明细行</el-button>
          <span v-if="samplingInfo" class="sampling-info">{{ samplingInfo.method }} · {{ samplingInfo.count }} 笔</span>
        </div>
        <div class="ic-stage-toolbar-right">
          <el-radio-group v-model="viewMode" size="small">
            <el-radio-button value="table">完整表格</el-radio-button>
            <el-radio-button value="card">逐笔核对</el-radio-button>
          </el-radio-group>
          <el-tag size="small" type="info">共 {{ ic.rows.value.length }} 行</el-tag>
          <el-tag size="small">合计 {{ ic.checkedTotal.value.toLocaleString() }}</el-tag>
        </div>
      </div>

      <div v-if="viewMode === 'table'" class="ic-table-wrap">
        <el-table :data="ic.rows.value" border size="small" max-height="520" :row-class-name="rowClass">
          <el-table-column prop="seq" label="序号" width="52" fixed />
          <el-table-column label="供应商名称" width="130" fixed>
            <template #default="{ row }">
              <el-input :model-value="row.party" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
            </template>
          </el-table-column>
          <el-table-column label="存货类别" width="110">
            <template #default="{ row }">
              <el-select :model-value="row.invCategory" size="small" :disabled="isReadonly" style="width:100%" @change="(v: string) => ic.updateRow(row.id, { invCategory: v })">
                <el-option v-for="c in F2_INSPECTION_CATEGORIES" :key="c" :label="c" :value="c" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="记账凭证">
            <el-table-column label="凭证编号" width="110">
              <template #default="{ row }">
                <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
              </template>
            </el-table-column>
            <el-table-column label="业务内容" min-width="140">
              <template #default="{ row }">
                <el-input :model-value="row.businessContent" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { businessContent: v })" />
              </template>
            </el-table-column>
            <el-table-column label="存货名称" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.itemName" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
              </template>
            </el-table-column>
            <el-table-column label="单位" width="64">
              <template #default="{ row }">
                <el-input :model-value="row.unit" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { unit: v })" />
              </template>
            </el-table-column>
            <el-table-column label="数量" width="88">
              <template #default="{ row }">
                <el-input-number :model-value="row.qty" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { qty: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="借方金额" width="110">
              <template #default="{ row }">
                <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="对方科目" width="110">
              <template #default="{ row }">
                <el-input :model-value="row.counterpartAccount" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { counterpartAccount: v })" />
              </template>
            </el-table-column>
            <el-table-column label="对方明细科目" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.counterpartDetail" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { counterpartDetail: v })" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="入库单/验收单">
            <el-table-column label="日期/编号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.recvDateNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { recvDateNo: v })" />
              </template>
            </el-table-column>
            <el-table-column label="数量" width="88">
              <template #default="{ row }">
                <el-input-number :model-value="row.recvQty" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { recvQty: v ?? 0 })" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="质检报告" class-name="optional-col">
            <el-table-column label="日期/编号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.inspectDateNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { inspectDateNo: v })" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="物流单（运输单）" class-name="optional-col">
            <el-table-column label="日期/编号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.logisticsDateNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { logisticsDateNo: v })" />
              </template>
            </el-table-column>
            <el-table-column label="物流单位" width="110">
              <template #default="{ row }">
                <el-input :model-value="row.logisticsProvider" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { logisticsProvider: v })" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="采购发票">
            <el-table-column label="数量" width="88">
              <template #default="{ row }">
                <el-input-number :model-value="row.invoiceQty" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { invoiceQty: v ?? 0 })" />
              </template>
            </el-table-column>
            <el-table-column label="日期/编号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.invoiceDateNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { invoiceDateNo: v })" />
              </template>
            </el-table-column>
            <el-table-column label="对手方名称" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.invoiceParty" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { invoiceParty: v })" />
              </template>
            </el-table-column>
            <el-table-column label="金额" width="110">
              <template #default="{ row }">
                <el-input-number :model-value="row.invoiceAmount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { invoiceAmount: v ?? 0 })" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="索引号" width="96">
            <template #default="{ row }">
              <el-input :model-value="row.indexRef" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { indexRef: v })" />
            </template>
          </el-table-column>
          <el-table-column label="是否异常" width="96">
            <template #default="{ row }">
              <el-select
                :model-value="row.isAbnormal ? '是' : '否'"
                size="small"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: string) => ic.updateRow(row.id, { abnormalOverride: v === '是' })"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column v-if="wpId && !isReadonly" label="📎" width="48" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg" :disabled="ocrLoadingId === row.id" @change="(f: any) => handleOcrUpload(row.id, f?.raw)">
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="92" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openVoucher(row)">核对</el-button>
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 卡片视图：一笔一卡，点「核对」进引导式弹窗 -->
      <div v-else class="ic-card-grid">
        <el-empty v-if="!ic.rows.value.length" description="暂无明细，请用抽凭引擎或「+ 明细行」新增" :image-size="72" />
        <div
          v-for="row in ic.rows.value"
          :key="row.id"
          class="ic-vcard"
          :class="{ abnormal: row.isAbnormal }"
          @click="openVoucher(row)"
        >
          <div class="ic-vcard-head">
            <span class="ic-vcard-title">{{ row.party || row.voucherNo || `第 ${row.seq} 笔` }}</span>
            <el-tag v-if="rowCheckSummary(row).bad" size="small" type="danger">{{ rowCheckSummary(row).bad }} 项不符</el-tag>
            <el-tag v-else-if="rowCheckSummary(row).pending" size="small" type="info">待补 {{ rowCheckSummary(row).pending }}</el-tag>
            <el-tag v-else size="small" type="success">核对通过</el-tag>
          </div>
          <div class="ic-vcard-body">
            <span>{{ row.invCategory }}</span>
            <span>凭证 {{ row.voucherNo || '—' }}</span>
            <span>金额 {{ (row.amount || 0).toLocaleString() }}</span>
          </div>
        </div>
      </div>

      <div class="ic-total">
        <span>合计借方金额 {{ ic.checkedTotal.value.toLocaleString() }}</span>
      </div>
    </section>

    <!-- 四、审计说明 -->
    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>四、审计说明 · 检查比例</h3>
          <p>本期发生额检查比例；比例偏低时应扩大样本量或说明原因</p>
        </div>
      </header>
      <el-table :data="ic.coverageLines.value" border size="small" class="coverage-table">
        <el-table-column prop="category" label="存货类别" min-width="120" />
        <el-table-column label="账面金额" width="150">
          <template #default="{ row }">
            <el-input-number
              :model-value="ic.bookByCategory.value[row.category] ?? row.bookAmount"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num"
              @change="(v?: number) => ic.updateBookByCategory(row.category, v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="checkedAmount" label="检查金额" width="130">
          <template #default="{ row }">{{ row.checkedAmount.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="检查比例" width="110">
          <template #default="{ row }">
            <span :class="{ warn: row.ratio > 0 && row.ratio < 50 }">{{ row.ratio.toFixed(1) }}%</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="ic-note-block">
        <div class="ic-note-head">
          <span>其他审计说明</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="runAi('inspection-audit-note')"
            >🤖 AI辅助说明</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="ic.auditNote.value"
          type="textarea"
          :rows="3"
          :disabled="isReadonly"
          placeholder="检查发现、覆盖率说明、扩大样本理由等"
        />
      </div>
    </section>

    <!-- 五、审计结论 -->
    <section class="ic-card conclusion-card">
      <header class="ic-card-head">
        <div>
          <h3>五、审计结论</h3>
        </div>
        <div class="ic-card-head-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="runAi('inspection-conclusion')"
            >🤖 AI辅助结论</el-button>
          </el-tooltip>
        </div>
      </header>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="A 未见异常 · B 除重大不符应调整外其余未见异常 · C 重大未调整或范围受限不可确认"
        @change="saveAuditConclusion"
      />
    </section>

    <!-- 抽凭引擎（弹窗承载，避免撑破工具条布局） -->
    <el-dialog
      v-model="samplingVisible"
      title="自动抽凭 · 存货科目（1401~1411）"
      width="82%"
      top="4vh"
      destroy-on-close
      append-to-body
    >
      <GtVoucherSamplingEngine
        v-if="samplingVisible && wpId && projectId"
        :account-code="F2_INVENTORY_ACCOUNT_CODES"
        phase="final"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="auditYear ?? new Date().getFullYear()"
        @filled="handleSamplingFilled"
      />
    </el-dialog>

    <!-- 逐笔核对引导式弹窗 -->
    <F2PurchaseVoucherDialog
      v-model="voucherDialogVisible"
      :row="voucherDialogRow"
      :wp-id="wpId"
      :readonly="isReadonly"
      @save="handleSaveVoucher"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, inject, toRef, type Ref } from 'vue'
import { useF2PurchaseInboundCheck } from '../../composables/useF2InspectionCheck'
import { useF2PurchaseOcr } from '../../composables/useF2PurchaseOcr'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import {
  F2_INVENTORY_ACCOUNT_CODES,
  F2_INSPECTION_CATEGORIES,
  evaluatePurchaseInboundChecks,
  type PurchaseInboundRow,
} from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode, SamplingMethod } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2PurchaseVoucherDialog from './F2PurchaseVoucherDialog.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ic = useF2PurchaseInboundCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const CONCLUSION_KEY = 'F2-33-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const { ocrLoadingId, uploadAndMerge } = useF2PurchaseOcr(
  toRef(() => props.wpId || '') as Ref<string>,
  toRef(() => props.projectId || '') as Ref<string>,
)
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)
// 与 D4 gold 标准一致的 AI 按钮提示
const aiTip = computed(() => (aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用'))

const samplingVisible = ref(false)
const samplingInfo = ref<{ method: string; count: number } | null>(null)
const METHOD_LABELS: Record<string, string> = {
  random: '随机抽样', stratified: '分层抽样', specific_item: '特定项目', systematic: '系统抽样', mus: '货币单位抽样',
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

async function onImported() {
  await reloadWorkpaperData?.()
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-33',
    coverageRatio: ic.coverageRatio.value,
    abnormalCount: ic.abnormalCount.value,
    checkedTotal: ic.checkedTotal.value,
    sampleSize: ic.meta.value.sampleSize,
    samplingMethod: ic.meta.value.samplingMethod,
    populationDesc: ic.meta.value.populationDesc,
    specificSamples: ic.meta.value.specificSamples,
    rowCount: ic.rows.value.length,
  }
}

async function runAi(section: F2ValAiSection) {
  const existing =
    section === 'inspection-sampling-note' ? (ic.meta.value.samplingProcess || '')
    : section === 'inspection-audit-note' ? (ic.auditNote.value || '')
    : (auditConclusion.value || '')
  const titles: Record<string, string> = {
    'inspection-sampling-note': 'AI 生成 · 抽样过程',
    'inspection-audit-note': 'AI 生成 · 审计说明',
    'inspection-conclusion': 'AI 生成 · 采购入库检查结论',
  }
  const text = await generateAndConfirm(section, existing, aiContext(), titles[section] || 'AI 生成')
  if (!text) return
  if (section === 'inspection-sampling-note') ic.updateMeta({ samplingProcess: text })
  else if (section === 'inspection-audit-note') ic.auditNote.value = text
  else {
    auditConclusion.value = text
    saveAuditConclusion(text)
  }
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'F2',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => {
    const item = { item_id: itemId, conclusion: null, remark }
    props.allResponses.set(itemId, item as never)
    window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
  },
  isReadonly: computed(() => props.isReadonly),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode; method?: SamplingMethod }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  ic.fillFromSampling(payload.samples, payload.fillMode, payload.method)
  samplingVisible.value = false
  samplingInfo.value = {
    method: METHOD_LABELS[payload.method || 'random'] || payload.method || '随机抽样',
    count: payload.samples.length,
  }
  if (!ic.meta.value.sampleSize) ic.updateMeta({ sampleSize: String(payload.samples.length) })
  if (!ic.meta.value.samplingMethod) ic.updateMeta({ samplingMethod: samplingInfo.value.method })
}

function handleOcrUpload(rowId: string, file?: File) {
  if (!file || !props.wpId) return
  void uploadAndMerge(rowId, file, (id, patch) => ic.updateRow(id, patch as any))
}

function rowClass({ row }: { row: { isAbnormal?: boolean } }) {
  return row.isAbnormal ? 'error-row' : ''
}

// ─── 视图切换 + 逐笔核对弹窗（引导式，宽表核对主路径）────────────────────────
const viewMode = ref<'table' | 'card'>('table')
const voucherDialogVisible = ref(false)
const voucherDialogRow = ref<PurchaseInboundRow | null>(null)

function openVoucher(row: PurchaseInboundRow) {
  voucherDialogRow.value = row
  voucherDialogVisible.value = true
}

function handleSaveVoucher(patch: Partial<PurchaseInboundRow> & { id: string }) {
  ic.updateRow(patch.id, patch)
}

/** 卡片视图状态色签：统计 mismatch/missing/pending 数 */
function rowCheckSummary(row: PurchaseInboundRow): { bad: number; pending: number } {
  const checks = evaluatePurchaseInboundChecks(row)
  return {
    bad: checks.filter((c) => c.status === 'mismatch' || c.status === 'missing').length,
    pending: checks.filter((c) => c.status === 'pending').length,
  }
}
</script>

<style scoped src="./f2InspectSheetStyles.css"></style>

<style scoped>
/* 卡片视图（逐笔核对） */
.ic-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  padding: 4px 0;
}
.ic-vcard {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
  background: var(--el-bg-color);
}
.ic-vcard:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.ic-vcard.abnormal {
  border-left: 3px solid var(--el-color-danger);
}
.ic-vcard-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.ic-vcard-title {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ic-vcard-body {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
