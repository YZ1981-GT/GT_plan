<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="64%"
    top="6vh"
    destroy-on-close
    append-to-body
    class="f2mu-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="form" class="f2mu-body">
      <div class="f2mu-main">
        <el-card shadow="never" class="f2mu-group">
          <template #header><span class="f2mu-gh">① 记账凭证（贷方）</span></template>
          <div class="f2mu-grid">
            <div class="f2mu-field"><label>凭证编号</label><el-input v-model="form.voucherNo" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>业务内容</label><el-input v-model="form.businessContent" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>存货名称</label><el-input v-model="form.itemName" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>单位</label><el-input v-model="form.unit" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>数量</label><el-input-number v-model="form.qty" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2mu-field"><label>贷方金额</label><el-input-number v-model="form.amount" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
            <div class="f2mu-field"><label>对方科目</label><el-input v-model="form.counterpartAccount" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>对方明细科目</label><el-input v-model="form.counterpartDetail" size="small" :disabled="readonly" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="f2mu-group">
          <template #header><span class="f2mu-gh">② 出库单 / 领料单</span></template>
          <div class="f2mu-grid">
            <div class="f2mu-field"><label>日期/编号</label><el-input v-model="form.docDateNo" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>领用部门</label><el-input v-model="form.party" size="small" :disabled="readonly" /></div>
            <div class="f2mu-field"><label>出库数量</label><el-input-number v-model="form.docQty" :controls="false" size="small" :disabled="readonly" style="width:100%" /></div>
          </div>
        </el-card>
      </div>

      <aside class="f2mu-side">
        <el-card shadow="never" class="f2mu-panel">
          <template #header>
            <span class="f2mu-gh">实时勾稽</span>
            <el-tag size="small" :type="autoAbnormal ? 'danger' : 'success'">
              {{ autoAbnormal ? '存在异常' : '暂未见异常' }}
            </el-tag>
          </template>
          <ul class="f2mu-checks">
            <li v-for="c in checks" :key="c.key" :class="'st-' + c.status">
              <span class="f2mu-check-icon">{{ ICON[c.status] }}</span>
              <span class="f2mu-check-label">{{ c.label }}</span>
              <span class="f2mu-check-detail">{{ c.detail }}</span>
            </li>
          </ul>
        </el-card>

        <el-card shadow="never" class="f2mu-panel">
          <template #header><span class="f2mu-gh">结论</span></template>
          <div class="f2mu-field"><label>索引号</label><el-input v-model="form.indexRef" size="small" :disabled="readonly" /></div>
          <div class="f2mu-field"><label>是否异常</label>
            <el-select v-model="abnormalChoice" size="small" :disabled="readonly" style="width:100%">
              <el-option label="自动判定" value="auto" />
              <el-option label="强制标记异常" value="yes" />
              <el-option label="强制标记正常" value="no" />
            </el-select>
          </div>
          <div class="f2mu-field"><label>备注</label>
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
 * F2MaterialUsageVoucherDialog — F2-34 材料领用「逐笔核对」引导式弹窗（对齐 F2-33）。
 */
import { computed, toRef } from 'vue'
import {
  evaluateMaterialUsageChecks,
  assessMaterialAbnormal,
  type MaterialUsageRow,
  type PurchaseCheckStatus,
} from '../../composables/useF2InspectionCheckFormulas'
import { useVoucherCheckDialog } from '../../composables/useVoucherCheckDialog'

const props = defineProps<{
  modelValue: boolean
  row: MaterialUsageRow | null
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<MaterialUsageRow> & { id: string }): void
}>()

const { form, abnormalChoice, buildSavePatch } = useVoucherCheckDialog<MaterialUsageRow>({
  modelValue: toRef(props, 'modelValue'),
  row: toRef(props, 'row'),
})

const dialogTitle = computed(() =>
  form.value ? `逐笔核对 · ${form.value.party || form.value.voucherNo || '第 ' + form.value.seq + ' 笔'}` : '逐笔核对',
)

const checks = computed(() => (form.value ? evaluateMaterialUsageChecks(form.value) : []))
const autoAbnormal = computed(() =>
  form.value ? assessMaterialAbnormal({ ...form.value, abnormalOverride: null }) : false,
)

const ICON: Record<PurchaseCheckStatus, string> = { ok: '✓', mismatch: '✗', missing: '!', pending: '…' }

function handleSave() {
  const patch = buildSavePatch()
  if (!patch) return
  emit('save', patch)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.f2mu-body { display: grid; grid-template-columns: 1fr 280px; gap: 12px; max-height: 70vh; }
.f2mu-main { overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 10px; }
.f2mu-side { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 0; }
.f2mu-group :deep(.el-card__header), .f2mu-panel :deep(.el-card__header) {
  padding: 8px 12px; display: flex; align-items: center; justify-content: space-between;
}
.f2mu-group :deep(.el-card__body), .f2mu-panel :deep(.el-card__body) { padding: 10px 12px; }
.f2mu-gh { font-size: 13px; font-weight: 600; }
.f2mu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.f2mu-field { display: flex; flex-direction: column; gap: 3px; }
.f2mu-field label { font-size: 12px; color: var(--el-text-color-secondary); }
.f2mu-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.f2mu-checks li { display: grid; grid-template-columns: 18px 1fr; gap: 4px; align-items: start; font-size: 12px; }
.f2mu-checks .f2mu-check-detail { grid-column: 2; color: var(--el-text-color-secondary); font-size: 11px; }
.f2mu-check-icon { font-weight: 700; text-align: center; }
.st-ok .f2mu-check-icon { color: var(--el-color-success); }
.st-mismatch .f2mu-check-icon, .st-missing .f2mu-check-icon { color: var(--el-color-danger); }
.st-mismatch .f2mu-check-label, .st-missing .f2mu-check-label { color: var(--el-color-danger); }
.st-pending .f2mu-check-icon { color: var(--el-text-color-placeholder); }
</style>
