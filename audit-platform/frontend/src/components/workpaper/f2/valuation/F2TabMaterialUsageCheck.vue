<template>
  <div class="f2-inspect">
    <header class="ic-hero">
      <div>
        <div class="ic-kicker">{{ ic.sheetCode }} · 账→单 · 材料领用</div>
        <h2 class="ic-title">{{ ic.title }}</h2>
        <p class="ic-sub">从原材料贷方记账凭证追查至出库单/领料单，测试发生/存在与成本归集。</p>
      </div>
      <div class="ic-actions">
        <GtIndexChip value="wp:F2-34" :context-project-id="projectId" />
        <F2ReviewChip section-id="F2-34-conclusion" />
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
        <li>关注超额领用、以领代耗、与生产/BOM 勾稽；检查比例偏低时应扩大样本。</li>
        <li>在「三、测试」中用抽凭引擎按存货贷方抽取领用凭证，或导入 Excel。</li>
      </ol>
    </details>

    <details class="ic-card ic-card--muted ic-objectives">
      <summary>一、审计目标</summary>
      <ul class="ic-list">
        <li>资产负债表中记录的存货是存在的，并计入了正确的会计科目</li>
        <li>所有应记录的存货均已记录，且相关信息已得到恰当披露</li>
        <li>存货以恰当金额列示，相关调整已记录</li>
      </ul>
    </details>

    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>二、样本选取标准与规模</h3>
          <p>描述原材料贷方测试总体、特定样本与抽样过程</p>
        </div>
      </header>
      <div class="ic-meta-grid">
        <div class="ic-field span2">
          <label>测试总体（原材料贷方） <span class="ic-field-hint">共 XX 笔、金额 XX</span></label>
          <el-input
            :model-value="ic.meta.value.populationDesc"
            :disabled="isReadonly"
            type="textarea"
            :rows="2"
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
            placeholder="大额、关联方、异常等"
            @update:model-value="(v: string) => ic.updateMeta({ specificSamples: v })"
          />
        </div>
        <div class="ic-field">
          <label>抽样总体</label>
          <el-input
            :model-value="ic.meta.value.samplingPopulation"
            :disabled="isReadonly"
            @update:model-value="(v: string) => ic.updateMeta({ samplingPopulation: v })"
          />
        </div>
        <div class="ic-field">
          <label>确定的抽样样本量</label>
          <el-input
            :model-value="ic.meta.value.sampleSize"
            :disabled="isReadonly"
            @update:model-value="(v: string) => ic.updateMeta({ sampleSize: v })"
          />
        </div>
        <div class="ic-field">
          <label>抽样方法</label>
          <el-input
            :model-value="ic.meta.value.samplingMethod"
            :disabled="isReadonly"
            @update:model-value="(v: string) => ic.updateMeta({ samplingMethod: v })"
          />
        </div>
        <div class="ic-field span3">
          <label>
            抽样过程
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="runAi('inspection-sampling-note')"
            >AI 填写抽样过程</el-button>
          </label>
          <el-input
            :model-value="ic.meta.value.samplingProcess"
            :disabled="isReadonly"
            type="textarea"
            :rows="3"
            @update:model-value="(v: string) => ic.updateMeta({ samplingProcess: v })"
          />
        </div>
      </div>
    </section>

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
            sheet="F2-34"
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
          <el-tag size="small" type="info">共 {{ ic.rows.value.length }} 行</el-tag>
          <el-tag size="small">合计 {{ ic.checkedTotal.value.toLocaleString() }}</el-tag>
        </div>
      </div>

      <div class="ic-table-wrap">
        <el-table :data="ic.rows.value" border size="small" max-height="520" :row-class-name="rowClass" style="min-width: 1200px">
          <el-table-column prop="seq" label="序号" width="52" fixed />
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
            <el-table-column label="贷方金额" width="110">
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
          <el-table-column label="出库单/领料单">
            <el-table-column label="日期/编号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.docDateNo" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { docDateNo: v })" />
              </template>
            </el-table-column>
            <el-table-column label="领用部门" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.party" size="small" :disabled="isReadonly" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
              </template>
            </el-table-column>
            <el-table-column label="数量" width="88">
              <template #default="{ row }">
                <el-input-number :model-value="row.docQty" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateRow(row.id, { docQty: v ?? 0 })" />
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
          <el-table-column width="48" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="ic-total">
        <span>合计贷方金额 {{ ic.checkedTotal.value.toLocaleString() }}</span>
      </div>
    </section>

    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>四、审计说明 · 检查比例</h3>
          <p>原材料贷方发生额检查比例偏低时应扩大样本</p>
        </div>
      </header>
      <el-table :data="ic.coverageLines.value" border size="small" class="coverage-table">
        <el-table-column prop="category" label="项目" min-width="140" />
        <el-table-column label="账面金额" width="150">
          <template #default>
            <el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => ic.updateBookTotal(v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="检查金额" width="130">
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
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('inspection-audit-note')"
          >AI 填写审计说明</el-button>
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

    <section class="ic-card conclusion-card">
      <header class="ic-card-head">
        <div><h3>五、审计结论</h3></div>
        <div class="ic-card-head-actions">
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('inspection-conclusion')"
          >AI 生成结论</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject, toRef, type Ref } from 'vue'
import { useF2MaterialUsageCheck } from '../../composables/useF2InspectionCheck'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import { F2_INVENTORY_ACCOUNT_CODES } from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode, SamplingMethod } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ic = useF2MaterialUsageCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const CONCLUSION_KEY = 'F2-34-audit-conclusion'
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

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)

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
    sheet: 'F2-34',
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
    'inspection-conclusion': 'AI 生成 · 材料领用检查结论',
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

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode; method?: SamplingMethod }) {
  ic.fillFromSampling(payload.samples, payload.fillMode, payload.method)
  samplingVisible.value = false
  samplingInfo.value = {
    method: METHOD_LABELS[payload.method || 'random'] || payload.method || '随机抽样',
    count: payload.samples.length,
  }
  if (!ic.meta.value.sampleSize) ic.updateMeta({ sampleSize: String(payload.samples.length) })
  if (!ic.meta.value.samplingMethod) ic.updateMeta({ samplingMethod: samplingInfo.value.method })
}

function rowClass({ row }: { row: { isAbnormal?: boolean } }) {
  return row.isAbnormal ? 'error-row' : ''
}
</script>

<style scoped src="./f2InspectSheetStyles.css"></style>
