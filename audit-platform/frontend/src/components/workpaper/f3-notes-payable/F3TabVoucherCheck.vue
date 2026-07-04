<script setup lang="ts">
/** F3TabVoucherCheck — F3-7 借方/贷方检查 | Task 6.5, 9.3, 14.5 */
import { computed, toRef, inject, type Ref } from 'vue'
import { useF3VoucherCheck } from '../composables/useF3VoucherCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3VoucherCheckTable from './F3VoucherCheckTable.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  creditRows, debitRows, creditTotal, debitTotal, creditAbnormal, debitAbnormal,
  auditConclusion, addRow, removeRow, updateCell, applySamplingResults,
} = useF3VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAiConclusion(side: 'credit' | 'debit') {
  if (props.isReadonly) return
  const section = side === 'credit' ? 'credit-check-conclusion' : 'debit-check-conclusion'
  const text = await generateAndConfirm(
    section,
    auditConclusion.value,
    {
      side: side === 'credit' ? '贷方(增加)' : '借方(减少)',
      sampleCount: side === 'credit' ? creditRows.value.length : debitRows.value.length,
      totalAmount: side === 'credit' ? creditTotal.value : debitTotal.value,
      abnormalCount: side === 'credit' ? creditAbnormal.value : debitAbnormal.value,
    },
    side === 'credit' ? 'AI 生成 · 贷方检查结论' : 'AI 生成 · 借方检查结论',
  )
  if (text) auditConclusion.value = text
}

const auditYear = computed(() => props.year ?? new Date().getFullYear() - 1)
const currentPhase = computed<Phase>(() => 'final')

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  applySamplingResults(payload.samples, payload.fillMode)
}

function onUpdateCell(side: 'credit' | 'debit', rowId: string, field: string, value: unknown): void {
  updateCell(side, rowId, field, value)
}
</script>

<template>
  <div class="f3-tab-voucher">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <p>贷方区(增加)与借方区(减少)独立检查。超过 50 行自动启用固定表头滚动。抽凭样本按借贷方向分配。</p>
    </details>

    <el-collapse class="sampling-engine-collapse">
      <el-collapse-item title="自动抽凭（科目 2201 应付票据）" name="auto-sampling">
        <GtVoucherSamplingEngine
          account-code="2201"
          :phase="currentPhase"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <h4>贷方检查区（增加）</h4>
    <div class="block-toolbar">
      <el-button size="small" :disabled="isReadonly" @click="addRow('credit')">+ 添加行</el-button>
      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-7-credit" :disabled="isReadonly" @imported="onImported" />
    </div>
    <F3VoucherCheckTable
      side="credit"
      :rows="creditRows"
      :is-readonly="isReadonly"
      @update-cell="(id, f, v) => onUpdateCell('credit', id, f, v)"
      @remove-row="(id) => removeRow('credit', id)"
    />
    <div class="subtotal">贷方小计 {{ fmt(creditTotal) }} | 异常 {{ creditAbnormal }} 笔</div>

    <h4>借方检查区（减少）</h4>
    <div class="block-toolbar">
      <el-button size="small" :disabled="isReadonly" @click="addRow('debit')">+ 添加行</el-button>
      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-7-debit" :disabled="isReadonly" @imported="onImported" />
    </div>
    <F3VoucherCheckTable
      side="debit"
      :rows="debitRows"
      :is-readonly="isReadonly"
      @update-cell="(id, f, v) => onUpdateCell('debit', id, f, v)"
      @remove-row="(id) => removeRow('debit', id)"
    />
    <div class="subtotal">借方小计 {{ fmt(debitTotal) }} | 异常 {{ debitAbnormal }} 笔</div>

    <el-card shadow="never" style="margin-top:12px">
      <template #header>
        <div class="audit-header">
          <span>审计结论</span>
          <div class="ai-btns">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion('credit')">AI 贷方</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion('debit')">AI 借方</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-voucher { font-size: 13px; }
.sampling-engine-collapse { margin-bottom: 12px; }
.block-toolbar { margin-bottom: 8px; }
h4 { margin: 12px 0 8px; font-size: 14px; }
.subtotal { text-align: right; font-weight: 600; margin: 4px 0 12px; }
.audit-header { display: flex; justify-content: space-between; align-items: center; }
.ai-btns { display: flex; gap: 6px; }
</style>
