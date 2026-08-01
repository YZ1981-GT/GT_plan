<template>
<div class="d6-tab-inspection">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表对合同资产（科目1141）本期增减变动及期后结转情况执行凭证级细节测试。</p>
      <p>2. 核对结果5项：①记账凭证与原始凭证核对 ②合同/协议存在性 ③履约进度是否恰当 ④计量是否准确 ⑤分类是否正确。绿色=通过，灰色=未核对。</p>
      <p>3. 抽样参数区记录测试总体、抽样方法与目标样本量，进度条实时反映已抽取比例。</p>
      <p>4. 检查比例汇总的账面金额取自 D6-2 期末审定合计（浅蓝背景为跨sheet自动取数），检查比例不足时需扩大样本。</p>
      <p>5. 对方科目为主营业务收入的可跳转 D4 收入循环交叉核对。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：通过凭证级细节测试验证合同资产本期增减变动及期后事项的真实、准确与截止恰当，确认检查比例充分覆盖账面金额。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addSample(1)">+ 添加本期样本</el-button>
      <el-button v-if="!isReadonly" size="small" @click="addSample(2)">+ 添加期后样本</el-button>
      <el-button v-if="!isReadonly" size="small" type="warning" @click="showSamplingDialog = true">🎲 抽凭引擎</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出(本期) ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="periodIe.exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="periodIe.exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportPeriodFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出(期后) ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="postIe.exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="postIe.exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportPostFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ sampleCount }} 样本</el-tag>
    </div>
  </div>

  <!-- 抽样参数区 -->
  <div class="sampling-params-card">
    <h4 class="card-title">样本选取标准与规模</h4>
    <div class="params-grid">
      <div class="param-item">
        <label>测试总体</label>
        <el-input v-model="samplingParams.testPopulation" :disabled="isReadonly" size="small" style="width:160px" />
      </div>
      <div class="param-item">
        <label>特定样本</label>
        <el-input v-model="samplingParams.specificSample" :disabled="isReadonly" size="small" style="width:160px" />
      </div>
      <div class="param-item">
        <label>抽样总体</label>
        <el-input v-model="samplingParams.samplingPopulation" :disabled="isReadonly" size="small" style="width:160px" />
      </div>
      <div class="param-item">
        <label>目标样本量</label>
        <el-input-number v-model="samplingParams.targetSampleSize" :controls="false" :disabled="isReadonly" size="small" style="width:120px" />
      </div>
      <div class="param-item">
        <label>抽样方法</label>
        <el-input v-model="samplingParams.samplingMethod" :disabled="isReadonly" size="small" style="width:180px" />
      </div>
      <div class="param-item">
        <label>抽样过程</label>
        <el-input v-model="samplingParams.samplingProcess" :disabled="isReadonly" size="small" style="width:180px" />
      </div>
    </div>
    <div class="progress-bar">
      <span>已抽取：{{ sampleCount }} / 目标：{{ samplingParams.targetSampleSize }}</span>
      <el-progress
        :percentage="samplingParams.targetSampleSize > 0 ? Math.min(100, Math.round(sampleCount / samplingParams.targetSampleSize * 100)) : 0"
        :stroke-width="10"
        style="width:200px"
      />
    </div>
  </div>

  <!-- (1) 本期增减变动检查 -->
  <div class="check-block">
    <h4 class="card-title">(1) 本期增减变动检查</h4>
    <el-table :data="block1Rows" size="small" border stripe max-height="460" style="width:100%">
      <el-table-column label="客户名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'customerName', v)" />
          <span v-else>{{ row.customerName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" placeholder="yyyy-mm-dd" @change="(v: string) => updateSampleCell(1, row.rowId, 'date', v)" />
          <span v-else>{{ row.date || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证编号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'counterAccount', v)" />
          <span v-else>{{ row.counterAccount || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方明细科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterDetail" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'counterDetail', v)" />
          <span v-else>{{ row.counterDetail || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSampleCell(1, row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发票/核实文件" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" placeholder="发票号/合同编号" @change="(v: string) => updateSampleCell(1, row.rowId, 'supportDoc', v)" />
          <span v-else>{{ row.supportDoc || '-' }}</span>
        </template>
      </el-table-column>
      <!-- 5项核对结果(点选色块) -->
      <el-table-column label="①凭证" width="52" align="center">
        <template #header>
          <el-tooltip content="①记账凭证与原始凭证核对" placement="top"><span>①</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check1 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(1, row.rowId, 'check1')">{{ row.check1 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="②合同" width="52" align="center">
        <template #header>
          <el-tooltip content="②合同/协议存在性" placement="top"><span>②</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check2 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(1, row.rowId, 'check2')">{{ row.check2 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="③履约" width="52" align="center">
        <template #header>
          <el-tooltip content="③履约进度是否恰当" placement="top"><span>③</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check3 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(1, row.rowId, 'check3')">{{ row.check3 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="④计量" width="52" align="center">
        <template #header>
          <el-tooltip content="④计量是否准确" placement="top"><span>④</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check4 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(1, row.rowId, 'check4')">{{ row.check4 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="⑤分类" width="52" align="center">
        <template #header>
          <el-tooltip content="⑤分类是否正确" placement="top"><span>⑤</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check5 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(1, row.rowId, 'check5')">{{ row.check5 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isAbnormal === '是'" type="danger" size="small">异常</el-tag>
          <span v-else class="normal-mark">-</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateSampleCell(1, row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSample(1, row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="block1Rows.length === 0" class="empty-hint">暂无本期样本，点击"添加本期样本"开始录入。</div>
  </div>

  <!-- (2) 期后结算检查 -->
  <div class="check-block">
    <h4 class="card-title">(2) 期后结算检查</h4>
    <el-table :data="block2Rows" size="small" border stripe max-height="420" style="width:100%">
      <el-table-column label="客户名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'customerName', v)" />
          <span v-else>{{ row.customerName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" placeholder="yyyy-mm-dd" @change="(v: string) => updateSampleCell(2, row.rowId, 'date', v)" />
          <span v-else>{{ row.date || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证编号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'counterAccount', v)" />
          <template v-else>
            <span>{{ row.counterAccount || '-' }}</span>
            <GtIndexChip v-if="row.counterAccount && row.counterAccount.includes('主营业务收入')" value="wp:D4" :context-project-id="projectId" style="margin-left:4px" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSampleCell(2, row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="支持性文件" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'supportDoc', v)" />
          <span v-else>{{ row.supportDoc || '-' }}</span>
        </template>
      </el-table-column>
      <!-- 5项核对结果(点选色块) -->
      <el-table-column label="①" width="44" align="center">
        <template #header><el-tooltip content="①记账凭证核对" placement="top"><span>①</span></el-tooltip></template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check1 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(2, row.rowId, 'check1')">{{ row.check1 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="②" width="44" align="center">
        <template #header><el-tooltip content="②合同/协议存在性" placement="top"><span>②</span></el-tooltip></template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check2 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(2, row.rowId, 'check2')">{{ row.check2 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="③" width="44" align="center">
        <template #header><el-tooltip content="③履约进度恰当" placement="top"><span>③</span></el-tooltip></template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check3 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(2, row.rowId, 'check3')">{{ row.check3 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="④" width="44" align="center">
        <template #header><el-tooltip content="④计量准确" placement="top"><span>④</span></el-tooltip></template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check4 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(2, row.rowId, 'check4')">{{ row.check4 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="⑤" width="44" align="center">
        <template #header><el-tooltip content="⑤分类正确" placement="top"><span>⑤</span></el-tooltip></template>
        <template #default="{ row }">
          <span class="check-dot" :class="row.check5 === '✓' ? 'on' : ''" @click="!isReadonly && toggleCheck(2, row.rowId, 'check5')">{{ row.check5 === '✓' ? '✓' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isAbnormal === '是'" type="danger" size="small">异常</el-tag>
          <span v-else class="normal-mark">-</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateSampleCell(2, row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSample(2, row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="block2Rows.length === 0" class="empty-hint">暂无期后样本，点击"添加期后样本"开始录入。</div>
  </div>

  <!-- 检查比例汇总 -->
  <div class="check-block">
    <h4 class="card-title">检查比例汇总</h4>
    <el-table :data="checkRatioSummary" size="small" border>
      <el-table-column prop="direction" label="方向" width="140" />
      <el-table-column label="账面金额" width="150" align="right">
        <template #default="{ row }">
          <span class="cross-sheet-cell" title="来源：D6-2期末审定合计">{{ fmtAmt(row.bookAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="检查金额" width="150" align="right">
        <template #default="{ row }">{{ fmtAmt(row.checkAmount) }}</template>
      </el-table-column>
      <el-table-column label="检查比例" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'ratio-low': row.ratio > 0 && row.ratio < 0.5 }">{{ fmtPct(row.ratio) }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 审计意见区 -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-actions">
          <GtIndexChip value="wp:D6-2" :context-project-id="projectId" />
          <GtReviewTrigger section-id="D6-6-note" label="💬" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">1. 审计说明</span>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="检查过程及发现（记录核对中发现的差异事项及原因）..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
      </div>
      <el-select
        v-if="!isReadonly"
        :model-value="undefined"
        placeholder="选择结论模板..."
        size="small"
        style="width: 100%; margin-bottom: 8px"
        @change="onConclusionTemplateSelect"
      >
        <el-option v-for="tpl in CONCLUSION_TEMPLATES" :key="tpl.value" :label="tpl.label" :value="tpl.label" />
      </el-select>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="检查结论..." />
    </div>
  </el-card>

  <!-- 抽凭引擎 -->
  <GtVoucherSamplingEngine
    v-if="showSamplingDialog"
    account-code="1141"
    phase="final"
    :workpaper-id="props.wpId"
    :project-id="props.projectId"
    :year="samplingYear"
    @filled="onSampleFilled"
    @close="showSamplingDialog = false"
  />
</div>
</template>

<script setup lang="ts">
/**
 * D6TabInspection.vue — 合同资产检查表 D6-6
 *
 * 凭证级检查表：双区块(本期+期后) + 5项核对结果(点选色块) + 检查比例汇总
 * 对齐源模板结构：客户/日期/凭证/对方科目/明细/金额/核实文件 + ①②③④⑤核对 + 索引/异常/备注
 */
import { computed, ref, inject, toRef, type Ref } from 'vue'
import { useD6Inspection } from '../composables/useD6Inspection'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import type { ChecklistResponse } from '../composables/useD6FormData'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  year?: number
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>

// ─── 导入导出 ─────────────────────────────────────────────────────────
const periodIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-6-period',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})
const postIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-6-post',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportPeriodFile(file: File) {
  await periodIe.importData(file)
  return false
}
async function onImportPostFile(file: File) {
  await postIe.importData(file)
  return false
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  samplingParams, block1Rows, block2Rows,
  addSample, removeSample, updateSampleCell,
  checkRatioSummary, auditNotes,
} = useD6Inspection({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const sampleCount = computed(() => block1Rows.value.length + block2Rows.value.length)

// ─── 抽凭引擎 ─────────────────────────────────────────────────────────
const samplingYear = computed(() => props.year || new Date().getFullYear())
const showSamplingDialog = ref(false)

function onSampleFilled(payload: any) {
  const samples: any[] = payload?.samples || []
  if (samples.length === 0) return
  const existingNos = new Set(block1Rows.value.map(r => r.voucherNo).filter(Boolean))
  const mapped = samples
    .filter((s: any) => s.voucherNo && !existingNos.has(s.voucherNo))
    .map((s: any) => ({
      rowId: `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
      customerName: s.counterpartAccount || '',
      date: s.voucherDate || '',
      voucherNo: s.voucherNo || '',
      businessContent: s.summary || '',
      counterAccount: '',
      counterDetail: '',
      debitAmount: s.debitAmount || 0,
      creditAmount: s.creditAmount || 0,
      supportDoc: '',
      check1: '', check2: '', check3: '', check4: '', check5: '',
      indexRef: '',
      isAbnormal: '否',
      remark: '',
    }))
  if (mapped.length > 0) {
    block1Rows.value = [...block1Rows.value, ...mapped]
    // Persist block1 rows
    props.debouncedSave('D6-6-block1-rows', { remark: JSON.stringify(block1Rows.value) })
  }
  showSamplingDialog.value = false
}

// ─── 核对结果切换(点选色块) ───────────────────────────────────────────
function toggleCheck(block: 1 | 2, rowId: string, field: string): void {
  const rows = block === 1 ? block1Rows.value : block2Rows.value
  const row = rows.find(r => r.rowId === rowId)
  if (!row) return
  const current = (row as any)[field]
  const newVal = current === '✓' ? '' : '✓'
  updateSampleCell(block, rowId, field, newVal)
}

// ─── 结论模板 ─────────────────────────────────────────────────────────
const CONCLUSION_TEMPLATES = [
  { value: 'no-issue', label: '经检查，所抽取样本的记账凭证与原始凭证一致，合同/协议真实存在，履约进度恰当，计量准确，分类正确，未发现重大异常。' },
  { value: 'adjusted', label: '经检查，发现差异已提请被审计单位调整，调整后合同资产列报恰当。' },
  { value: 'expand', label: '检查比例不足，建议扩大样本量后重新评估。' },
  { value: 'major-diff', label: '发现重大差异，建议提出审计调整分录。' },
  { value: 'other', label: '其他（请手动编写结论）。' },
]

function onConclusionTemplateSelect(val: string) {
  if (val) auditNotes.value.conclusion = val
}

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(ratio: number): string {
  if (!ratio) return '-'
  return `${(ratio * 100).toFixed(1)}%`
}
</script>

<style scoped>
.d6-tab-inspection { padding: 12px; }
.d6-tab-inspection :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-inspection :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.sampling-params-card {
  padding: 12px 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 16px;
  background: #fafafa;
}
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 10px; color: #303133; }
.params-grid { display: flex; flex-wrap: wrap; gap: 14px; }
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item label { font-size: 12px; color: #909399; }
.progress-bar { display: flex; align-items: center; gap: 12px; margin-top: 10px; font-size: 13px; }

.check-block { margin-bottom: 20px; }
.empty-hint { text-align: center; color: #909399; padding: 16px; font-size: 13px; }

/* 核对色块 */
.check-dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 4px;
  background: #f0f0f0; color: #c0c4cc;
  cursor: pointer; font-size: 14px; font-weight: 600;
  transition: all 0.15s;
  user-select: none;
}
.check-dot.on {
  background: #67c23a; color: #fff;
}
.check-dot:hover {
  transform: scale(1.1);
}
.normal-mark { color: #c0c4cc; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.ratio-low { color: #e6a23c; font-weight: 600; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
</style>
