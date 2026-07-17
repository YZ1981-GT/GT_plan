<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="70%"
    top="4vh"
    destroy-on-close
    append-to-body
    class="f2pv-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="form" class="f2pv-body">
      <!-- 左：分单据分组录入 -->
      <div class="f2pv-main">
        <!-- 基本信息 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header><span class="f2pv-gh">基本信息</span></template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>供应商名称</label>
              <el-input v-model="form.party" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>存货类别</label>
              <el-select v-model="form.invCategory" size="small" :disabled="readonly" style="width:100%">
                <el-option v-for="c in F2_INSPECTION_CATEGORIES" :key="c" :label="c" :value="c" />
              </el-select>
            </div>
          </div>
        </el-card>

        <!-- ① 记账凭证 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header><span class="f2pv-gh">① 记账凭证</span></template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>凭证编号</label><el-input v-model="form.voucherNo" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>业务内容</label><el-input v-model="form.businessContent" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>存货名称</label><el-input v-model="form.itemName" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>单位</label><el-input v-model="form.unit" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>数量</label><el-input-number v-model="form.qty" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2pv-field"><label>借方金额</label><el-input-number v-model="form.amount" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2pv-field"><label>对方科目</label><el-input v-model="form.counterpartAccount" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>对方明细科目</label><el-input v-model="form.counterpartDetail" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <!-- ② 入库单/验收单 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header>
            <span class="f2pv-gh">② 入库单 / 验收单</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg" :disabled="!!ocrLoadingId" @change="(f: any) => runOcr(f?.raw)">
              <el-button link size="small" :loading="!!ocrLoadingId">📎 上传识别</el-button>
            </el-upload>
          </template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>日期/编号</label><el-input v-model="form.recvDateNo" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>入库数量</label><el-input-number v-model="form.recvQty" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
          </div>
        </el-card>

        <!-- ③ 质检报告 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header><span class="f2pv-gh">③ 质检报告</span></template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>日期/编号</label><el-input v-model="form.inspectDateNo" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <!-- ④ 物流单/运输单 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header><span class="f2pv-gh">④ 物流单 / 运输单</span></template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>日期/编号</label><el-input v-model="form.logisticsDateNo" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>物流单位</label><el-input v-model="form.logisticsProvider" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <!-- ⑤ 采购发票 -->
        <el-card shadow="never" class="f2pv-group">
          <template #header>
            <span class="f2pv-gh">⑤ 采购发票</span>
            <el-upload v-if="canOcr" :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg" :disabled="!!ocrLoadingId" @change="(f: any) => runOcr(f?.raw)">
              <el-button link size="small" :loading="!!ocrLoadingId">📎 上传识别</el-button>
            </el-upload>
          </template>
          <div class="f2pv-grid">
            <div class="f2pv-field"><label>日期/编号</label><el-input v-model="form.invoiceDateNo" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>对手方名称</label><el-input v-model="form.invoiceParty" size="small" :disabled="readonly" /></div>
            <div class="f2pv-field"><label>发票数量</label><el-input-number v-model="form.invoiceQty" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2pv-field"><label>发票金额</label><el-input-number v-model="form.invoiceAmount" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
          </div>
        </el-card>
      </div>

      <!-- 右：实时勾稽 + 结论 -->
      <aside class="f2pv-side">
        <el-card shadow="never" class="f2pv-panel">
          <template #header>
            <span class="f2pv-gh">实时勾稽</span>
            <el-tag size="small" :type="autoAbnormal ? 'danger' : 'success'">
              {{ autoAbnormal ? '存在异常' : '暂未见异常' }}
            </el-tag>
          </template>
          <ul class="f2pv-checks">
            <li v-for="c in checks" :key="c.key" :class="'st-' + c.status">
              <span class="f2pv-check-icon">{{ ICON[c.status] }}</span>
              <span class="f2pv-check-label">{{ c.label }}</span>
              <span class="f2pv-check-detail">{{ c.detail }}</span>
            </li>
          </ul>
        </el-card>

        <el-card shadow="never" class="f2pv-panel">
          <template #header><span class="f2pv-gh">结论</span></template>
          <div class="f2pv-field"><label>索引号</label><el-input v-model="form.indexRef" size="small" :disabled="readonly" /></div>
          <div class="f2pv-field"><label>是否异常</label>
            <el-select v-model="abnormalChoice" size="small" :disabled="readonly" style="width:100%">
              <el-option label="自动判定" value="auto" />
              <el-option label="强制标记异常" value="yes" />
              <el-option label="强制标记正常" value="no" />
            </el-select>
          </div>
          <div class="f2pv-field"><label>备注</label>
            <el-input v-model="form.remark" type="textarea" :rows="2" size="small" :disabled="readonly" /></div>
        </el-card>
      </aside>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="handleSave">保存本笔</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * F2PurchaseVoucherDialog — F2-33 采购入库「逐笔核对」引导式弹窗。
 *
 * 一笔凭证 = 5 个分组卡片对齐 5 类单据（记账凭证/入库验收/质检/物流/采购发票），
 * 每组可 📎 上传 OCR 回填本组字段；右侧实时勾稽面板（evaluatePurchaseInboundChecks）
 * 逐项红黄提示，与主表「是否异常」同源。保存 emit 整行 patch 回父组件 updateRow。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { useF2PurchaseOcr } from '../../composables/useF2PurchaseOcr'
import {
  evaluatePurchaseInboundChecks,
  assessPurchaseAbnormal,
  F2_INSPECTION_CATEGORIES,
  type PurchaseInboundRow,
  type PurchaseCheckStatus,
} from '../../composables/useF2InspectionCheckFormulas'

const props = defineProps<{
  modelValue: boolean
  row: PurchaseInboundRow | null
  wpId?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<PurchaseInboundRow> & { id: string }): void
}>()

const form = ref<PurchaseInboundRow | null>(null)
const abnormalChoice = ref<'auto' | 'yes' | 'no'>('auto')

// 打开时克隆行，避免直接改父数据（保存才回写）
watch(
  () => [props.modelValue, props.row] as const,
  ([visible, row]) => {
    if (visible && row) {
      form.value = { ...row }
      abnormalChoice.value = row.abnormalOverride === null ? 'auto' : (row.abnormalOverride ? 'yes' : 'no')
    }
  },
  { immediate: true },
)

const dialogTitle = computed(() =>
  form.value ? `逐笔核对 · ${form.value.party || form.value.voucherNo || '第 ' + form.value.seq + ' 笔'}` : '逐笔核对',
)

const checks = computed(() => (form.value ? evaluatePurchaseInboundChecks(form.value) : []))
const autoAbnormal = computed(() =>
  form.value ? assessPurchaseAbnormal({ ...form.value, abnormalOverride: null }) : false,
)

const ICON: Record<PurchaseCheckStatus, string> = { ok: '✓', mismatch: '✗', missing: '!', pending: '…' }
const canOcr = computed(() => !!props.wpId && !props.readonly)

const { ocrLoadingId, uploadAndMerge } = useF2PurchaseOcr(
  computed(() => props.wpId || '') as Ref<string>,
)

function runOcr(file?: File) {
  if (!file || !form.value) return
  void uploadAndMerge(form.value.id, file, (_id, patch) => {
    if (form.value) Object.assign(form.value, patch)
  })
}

function handleSave() {
  if (!form.value) return
  const abnormalOverride = abnormalChoice.value === 'auto' ? null : abnormalChoice.value === 'yes'
  emit('save', { ...form.value, abnormalOverride })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.f2pv-body { display: grid; grid-template-columns: 1fr 300px; gap: 12px; max-height: 74vh; }
.f2pv-main { overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 10px; }
.f2pv-side { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 0; }
.f2pv-group :deep(.el-card__header), .f2pv-panel :deep(.el-card__header) {
  padding: 8px 12px; display: flex; align-items: center; justify-content: space-between;
}
.f2pv-group :deep(.el-card__body), .f2pv-panel :deep(.el-card__body) { padding: 10px 12px; }
.f2pv-gh { font-size: 13px; font-weight: 600; }
.f2pv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.f2pv-field { display: flex; flex-direction: column; gap: 3px; }
.f2pv-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.f2pv-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.f2pv-checks li { display: grid; grid-template-columns: 18px 1fr; gap: 4px; align-items: start; font-size: 12px; }
.f2pv-checks .f2pv-check-detail { grid-column: 2; color: var(--el-text-color-secondary); font-size: 11px; }
.f2pv-check-icon { font-weight: 700; text-align: center; }
.st-ok .f2pv-check-icon { color: var(--el-color-success); }
.st-mismatch .f2pv-check-icon, .st-missing .f2pv-check-icon { color: var(--el-color-danger); }
.st-mismatch .f2pv-check-label, .st-missing .f2pv-check-label { color: var(--el-color-danger); }
.st-pending .f2pv-check-icon { color: var(--el-text-color-placeholder); }
</style>
