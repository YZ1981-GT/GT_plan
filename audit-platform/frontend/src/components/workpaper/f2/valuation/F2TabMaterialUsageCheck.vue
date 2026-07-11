<template>
  <div class="f2-val-sheet">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表抽取样本核查材料领用（存货科目 1401~1411 贷方发生），逐笔核对领用部门、单号、品名、金额与凭证。</p>
        <p>2. 覆盖率＝已查金额 / 账面总额，覆盖率偏低时自动橙色提示，应扩大样本或说明抽样理由。</p>
        <p>3. 可通过下方"使用抽凭引擎"按方法（随机/分层/系统/MUS）选取存货贷方凭证，样本自动填入检查行。</p>
        <p>4. 依《企业会计准则第 1 号——存货》，关注材料领用是否真实、计价准确、有无跨期或人为调节成本。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证材料领用的真实性、完整性与计价准确性，确认发出存货成本结转正确、无跨期或异常调节。"
    />

    <header class="sheet-header">
      <div><h3>{{ ic.title }}</h3><span class="code">{{ ic.sheetCode }}</span></div>
      <span :class="['coverage', { warn: ic.isCoverageLow.value }]">覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%</span>
    </header>

    <div class="meta-bar">
      <span>账面总额<el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly" @change="(v: number) => ic.updateBookTotal(v ?? 0)" /></span>
      <span>已查 {{ ic.checkedTotal.value.toLocaleString() }}</span>
      <span v-if="samplingInfo" class="sampling-info">
        抽样方法: {{ samplingInfo.method }} | 样本量: {{ samplingInfo.count }}
      </span>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!isReadonly && wpId && projectId"
          size="small"
          type="primary"
          :icon="ElIconMagicStick"
          @click="samplingDialogVisible = true"
        >使用抽凭引擎</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ic.addRow()">+ 新增</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-34"
          :disabled="isReadonly"
          ai-section="inspection-conclusion"
          :existing-content="ic.auditNote.value"
          :related-context="{ coverageRatio: ic.coverageRatio.value }"
          ai-title="AI 生成 · 材料领用检查结论"
          review-section="F2-34-conclusion"
          @ai-filled="(t: string) => { ic.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ ic.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="ic.rows.value" border size="small" max-height="440">
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column label="领用部门" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.party" size="small" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
          <span v-else>{{ row.party }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.docNo" size="small" @change="(v: string) => ic.updateRow(row.id, { docNo: v })" />
          <span v-else>{{ row.docNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="row.sampleSource" placement="top">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </el-tooltip>
          <template v-else>
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">检查结论</span></div>
      </template>
      <el-input v-model="ic.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请输入材料领用检查结论..." />
    </el-card>

    <!-- 抽凭引擎 Dialog -->
    <el-dialog
      v-model="samplingDialogVisible"
      title="抽凭引擎 · 材料领用检查（存货科目 1401~1411 贷方发生）"
      width="900px"
      destroy-on-close
      append-to-body
    >
      <GtVoucherSamplingEngine
        :account-code="F2_INVENTORY_ACCOUNT_CODES"
        phase="final"
        default-method="random"
        :workpaper-id="wpId!"
        :project-id="projectId!"
        :year="auditYear"
        @filled="handleSamplingFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { MagicStick as ElIconMagicStick } from '@element-plus/icons-vue'
import { useF2MaterialUsageCheck } from '../../composables/useF2InspectionCheck'
import { F2_INVENTORY_ACCOUNT_CODES } from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode, SamplingMethod } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

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

const auditYear = computed(() => props.auditYear ?? new Date().getFullYear() - 1)

/** 抽凭引擎 dialog 可见性 */
const samplingDialogVisible = ref(false)

/** 抽样参数区展示信息（引擎返回后自动更新） */
const samplingInfo = ref<{ method: string; count: number } | null>(null)

/** 抽样方法中文映射 */
const METHOD_LABELS: Record<string, string> = {
  random: '随机抽样',
  stratified: '分层抽样',
  specific_item: '特定项目',
  systematic: '系统抽样',
  mus: '货币单位抽样',
}

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode; method?: SamplingMethod }) {
  ic.fillFromSampling(payload.samples, payload.fillMode, payload.method)
  // 自动更新抽样参数区
  samplingInfo.value = {
    method: METHOD_LABELS[payload.method || 'random'] || payload.method || '随机抽样',
    count: payload.samples.length,
  }
  // 关闭dialog
  samplingDialogVisible.value = false
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-val-sheet :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-val-sheet :deep(.el-table .cell) { font-size: 13px !important; }
/* 编制提示（蓝色） */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.meta-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; font-size: 13px; }
.coverage { font-weight: 600; }
.coverage.warn { color: #e6a23c; }
.sampling-info { font-size: 12px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); padding: 2px 8px; border-radius: 4px; }
/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
/* 审计意见卡片 */
.opinion-card { margin-top: 14px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
