<template>
  <div class="f5-qty-recon">
    <div class="f5-qty-toolbar">
      <span class="f5-qty-title">F5-6 销售数量与结转成本数量核对</span>
      <div class="f5-qty-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 品种</el-button>
        <CycleImportExportDropdown v-if="importExportCtx" :wp-id="wpId" :api-prefix="importExportCtx.apiPrefix"
          :sheet="importExportCtx.sheet" :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
    </div>

    <el-table :data="recon.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="540">
      <el-table-column label="#" type="index" width="44" fixed />
      <el-table-column label="品种" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.product" size="small"
            @change="(v: string) => recon.updateCell(row.id, 'product', v)" />
          <span v-else>{{ row.product }}</span>
        </template>
      </el-table-column>
      <el-table-column label="规格" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.spec" size="small"
            @change="(v: string) => recon.updateCell(row.id, 'spec', v)" />
          <span v-else>{{ row.spec }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单位" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.unit" size="small"
            @change="(v: string) => recon.updateCell(row.id, 'unit', v)" />
          <span v-else>{{ row.unit }}</span>
        </template>
      </el-table-column>
      <el-table-column label="销售数量" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.salesQty" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'salesQty', v)" />
          <span v-else>{{ fmt(row.salesQty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结转成本数量" width="120" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.costQty" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'costQty', v)" />
          <span v-else>{{ fmt(row.costQty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="数量差异" width="100" align="right">
        <template #default="{ row }"><span class="f5-formula" title="销售-结转">{{ fmt(row.qtyVariance) }}</span></template>
      </el-table-column>
      <el-table-column label="差异率%" width="100" align="right">
        <template #default="{ row }">
          <span class="f5-formula" :class="hlClass(row)" title="数量差异/销售数量×100">{{ pct(row.varianceRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异原因" width="120">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.varianceReason" size="small" clearable
            @change="(v: string) => recon.updateCell(row.id, 'varianceReason', v)">
            <el-option v-for="opt in recon.varianceReasonOptions" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.varianceReason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初库存" width="100" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.openingInventory" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'openingInventory', v)" />
          <span v-else>{{ fmt(row.openingInventory) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期产量" width="100" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentProduction" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'currentProduction', v)" />
          <span v-else>{{ fmt(row.currentProduction) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期采购" width="100" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentPurchase" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'currentPurchase', v)" />
          <span v-else>{{ fmt(row.currentPurchase) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="可供销售量" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" title="期初+产量+采购">{{ fmt(row.availableForSale) }}</span></template>
      </el-table-column>
      <el-table-column label="期末库存" width="100" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.closingInventory" size="small"
            @change="(v: any) => recon.updateCell(row.id, 'closingInventory', v)" />
          <span v-else>{{ fmt(row.closingInventory) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="理论结转量" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" title="可供销售-期末">{{ fmt(row.theoreticalCostQty) }}</span></template>
      </el-table-column>
      <el-table-column label="理论差异" width="100" align="right">
        <template #default="{ row }"><span class="f5-formula" title="理论结转-结转">{{ fmt(row.theoreticalVariance) }}</span></template>
      </el-table-column>
      <el-table-column label="📎OCR" width="70" v-if="!isReadonly">
        <template #default="{ row }">
          <el-upload :show-file-list="false" accept="image/*,.pdf" :auto-upload="false"
            @change="(f: any) => onOcr(row.id, f)">
            <el-button size="small" link :loading="ocrLoadingId === row.id">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="recon.removeRow(row.id)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="f5-qty-summary">
      <span>总销售量：<b>{{ fmt(recon.summary.value.totalSales) }}</b></span>
      <span>总结转量：<b>{{ fmt(recon.summary.value.totalCost) }}</b></span>
      <span>总差异：<b>{{ fmt(recon.summary.value.totalVariance) }}</b></span>
      <span>异常品种数：<b class="warn">{{ recon.summary.value.abnormalCount }}</b></span>
      <span>红色警告品种数：<b class="danger">{{ recon.summary.value.redCount }}</b></span>
    </div>

    <el-card class="f5-qty-note" shadow="never">
      <template #header>
        <div class="f5-card-header">
          <span>审计说明</span>
          <el-button size="small" @click="openReview">💬 复核</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" autosize :disabled="isReadonly"
        placeholder="销售数量与结转成本数量核对说明..." @change="saveNote" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabQuantityRecon.vue — F5-6 数量核对（16列，81行）
 * >5%橙色/>10%红色 + 差异原因下拉 + 理论结转验证 + 📎OCR出库单数量识别 + 底部汇总
 */
import { ref, computed, inject, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/services/apiProxy'
import { useF5QuantityRecon } from '../composables/useF5QuantityRecon'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const NOTE_KEY = 'F5-6-audit-note'

const recon = useF5QuantityRecon({
  allResponses: props.allResponses,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const auditNote = ref(props.allResponses.value.get(NOTE_KEY)?.remark ?? '')
const ocrLoadingId = ref<string | null>(null)

const importExportCtx = computed(() =>
  isImportExportSheet('f5', 'F5-6') ? resolveImportExportSheet('f5', 'F5-6') : null,
)

function saveNote() {
  props.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', {
    detail: { items: [{ item_id: NOTE_KEY, conclusion: null, remark: auditNote.value }] },
  }))
}

async function onOcr(rowId: string, uploadFile: any) {
  const file: File | undefined = uploadFile?.raw ?? uploadFile
  if (!file) return
  ocrLoadingId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/f5/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    const qty = Number(fields.quantity ?? fields.qty ?? fields.出库数量)
    if (!Number.isFinite(qty)) {
      ElMessage.info('OCR完成，未识别到出库单数量')
      return
    }
    await ElMessageBox.confirm(`识别到出库单数量 ${qty}，是否填入销售数量？`, 'OCR识别结果', {
      confirmButtonText: '填入', cancelButtonText: '取消',
    })
    recon.mergeOcrQuantity(rowId, qty)
    window.dispatchEvent(new CustomEvent('f5:save-items', {
      detail: { items: [props.allResponses.value.get('F5-6-quantity-recon-rows')].filter(Boolean) },
    }))
    ElMessage.success('已填入')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingId.value = null
  }
}

async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '品种名称不能为空',
    })
    if (value) recon.addRow(value.trim())
  } catch { /* 取消 */ }
}

function rowClass({ row }: { row: any }): string {
  const lvl = recon.highlightLevel(row)
  return lvl === 'red' ? 'f5-row-red' : lvl === 'orange' ? 'f5-row-orange' : ''
}
function hlClass(row: any): string {
  const lvl = recon.highlightLevel(row)
  return lvl === 'red' ? 'is-danger' : lvl === 'orange' ? 'is-warn' : ''
}
function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function pct(v: number | 'N/A' | null | undefined): string {
  if (v == null || v === 'N/A') return 'N/A'
  return `${v.toFixed(2)}%`
}
function openReview() { openReviewDialog('F5-6-conclusion') }
</script>

<style scoped>
.f5-qty-recon { padding: 12px; font-size: 13px; }
.f5-qty-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.f5-qty-title { font-weight: 600; }
.f5-qty-actions { display: flex; gap: 8px; align-items: center; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
.f5-formula.is-danger { color: #f56c6c; font-weight: 700; }
.f5-qty-summary { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; flex-wrap: wrap; }
.f5-qty-summary .warn { color: #e6a23c; }
.f5-qty-summary .danger { color: #f56c6c; }
.f5-qty-note { margin-top: 12px; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.f5-row-orange) { background: #fdf6ec; }
:deep(.f5-row-red) { background: #fef0f0; }
</style>
