<template>
  <el-dialog
    :model-value="modelValue"
    title="逐笔核对 — 预收账款凭证检查"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="hydrate"
  >
    <div v-if="form" class="d3-vc-dialog">
      <!-- ① 记账凭证基本信息 -->
      <el-card shadow="never" class="grp">
        <template #header><span class="grp-title">① 记账凭证</span></template>
        <div class="grid">
          <div class="fld"><label>客户名称</label>
            <el-input v-model="form.customerName" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>日期</label>
            <el-date-picker v-model="form.date" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%" /></div>
          <div class="fld"><label>凭证编号</label>
            <el-input v-model="form.voucherNo" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>业务内容</label>
            <el-input v-model="form.businessContent" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>对方科目</label>
            <el-input v-model="form.counterAccount" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>对方明细科目</label>
            <el-input v-model="form.counterDetailAccount" size="small" :disabled="isReadonly" /></div>
          <div v-if="section === 'current'" class="fld"><label>借方金额</label>
            <el-input v-model.number="form.debitAmount" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>贷方金额</label>
            <el-input v-model.number="form.creditAmount" size="small" :disabled="isReadonly" /></div>
        </div>
      </el-card>

      <!-- ② 支持性文件 + OCR -->
      <el-card shadow="never" class="grp">
        <template #header><span class="grp-title">② 支持性文件</span></template>
        <div class="doc-row">
          <el-input v-model="form.supportingDoc" size="small" :disabled="isReadonly"
            placeholder="支持性文件说明（合同/收款单/发票等）" style="flex:1" />
          <el-upload :show-file-list="false" :accept="OCR_ACCEPT" :before-upload="onOcrUpload" :disabled="isReadonly">
            <el-button size="small" :loading="ocrLoading" :disabled="isReadonly">📎 上传并OCR</el-button>
          </el-upload>
          <el-tag v-if="form.attachment" size="small" type="success">{{ form.attachment }}</el-tag>
        </div>
      </el-card>

      <!-- ③ 核对内容（5 项，源模板 R13） -->
      <el-card shadow="never" class="grp">
        <template #header>
          <span class="grp-title">③ 核对内容</span>
          <el-tag :type="checkedCount === 5 ? 'success' : 'warning'" size="small" class="hdr-tag">
            已核对 {{ checkedCount }}/5
          </el-tag>
        </template>
        <div class="check-list">
          <el-checkbox
            v-for="(label, i) in CHECK_ITEMS"
            :key="i"
            :model-value="form.checkItems[i]"
            :disabled="isReadonly"
            @change="(v: any) => setCheck(i, !!v)"
          >{{ i + 1 }}. {{ label }}</el-checkbox>
        </div>
      </el-card>

      <!-- 实时勾稽/校验面板 -->
      <el-alert
        v-for="a in liveChecks"
        :key="a.key"
        :type="a.type"
        :title="a.text"
        :closable="false"
        show-icon
        class="live-check"
      />

      <!-- ④ 检查结论 -->
      <el-card shadow="never" class="grp">
        <template #header><span class="grp-title">④ 检查结论</span></template>
        <div class="grid">
          <div class="fld"><label>索引号</label>
            <el-input v-model="form.indexRef" size="small" :disabled="isReadonly" /></div>
          <div class="fld"><label>是否异常</label>
            <el-select v-model="form.isAbnormal" size="small" clearable :disabled="isReadonly"
              placeholder="正常" style="width:100%">
              <el-option v-for="o in ABNORMAL_OPTIONS" :key="o" :value="o" :label="o" />
            </el-select></div>
          <div class="fld fld--wide"><label>备注说明</label>
            <el-input v-model="form.remark" type="textarea" :rows="2" :disabled="isReadonly" /></div>
        </div>
      </el-card>
    </div>

    <template #footer>
      <el-button size="small" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="onSave">保存核对</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * D3VoucherCheckDialog.vue — D3-7 预收账款凭证逐笔核对引导弹窗
 *
 * 分组卡片（记账凭证/支持性文件+OCR/核对内容/结论）+ 实时核对完成度与异常提示。
 * 本地 form 克隆编辑，保存时 emit 完整 patch 由父组件 updateRow 单次持久化。
 * 核对内容 5 项标签对齐源模板（D3_VOUCHER_CHECK_ITEMS）。
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  D3_VOUCHER_CHECK_ITEMS,
  mapOcrToVoucherFields,
  isAllowedAttachment,
  CONFIDENCE_THRESHOLD,
  type VoucherCheckRow,
} from '../composables/useD3VoucherCheck'

const props = defineProps<{
  modelValue: boolean
  row: VoucherCheckRow | null
  section: 'current' | 'postPeriod'
  isReadonly: boolean
  wpId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: VoucherCheckRow): void
}>()

const CHECK_ITEMS = D3_VOUCHER_CHECK_ITEMS
const ABNORMAL_OPTIONS = ['跨期疑点', '金额异常', '无原始凭证', '对方科目异常', '重复入账', '其他异常']
const OCR_ACCEPT = '.jpg,.jpeg,.png,.gif,.bmp,.webp,.pdf,image/*,application/pdf'

const form = ref<VoucherCheckRow | null>(null)
const ocrLoading = ref(false)

function hydrate() {
  if (!props.row) { form.value = null; return }
  form.value = {
    ...props.row,
    checkItems: [...(props.row.checkItems ?? [false, false, false, false, false])] as [boolean, boolean, boolean, boolean, boolean],
  }
}

function setCheck(i: number, v: boolean) {
  if (!form.value) return
  const items = [...form.value.checkItems] as [boolean, boolean, boolean, boolean, boolean]
  items[i] = v
  form.value.checkItems = items
}

const checkedCount = computed(() =>
  form.value ? form.value.checkItems.filter(Boolean).length : 0,
)

/** 实时校验：核对完成度 / 金额 / 异常标记提示 */
const liveChecks = computed(() => {
  const out: Array<{ key: string; type: 'warning' | 'info' | 'error'; text: string }> = []
  if (!form.value) return out
  if (checkedCount.value < 5) {
    const missing = CHECK_ITEMS
      .map((l, i) => (form.value!.checkItems[i] ? null : `${i + 1}.${l}`))
      .filter(Boolean)
      .join('、')
    out.push({ key: 'incomplete', type: 'warning', text: `尚有 ${5 - checkedCount.value} 项未核对：${missing}` })
  }
  const debit = Number(form.value.debitAmount) || 0
  const credit = Number(form.value.creditAmount) || 0
  if (debit === 0 && credit === 0) {
    out.push({ key: 'amount', type: 'info', text: '借方/贷方金额均为空，请确认凭证金额。' })
  }
  if (checkedCount.value < 5 && !form.value.isAbnormal) {
    out.push({ key: 'suggest', type: 'info', text: '存在未核对项，若核对发现问题请在「是否异常」中选择相应类型。' })
  }
  if (form.value.isAbnormal) {
    out.push({ key: 'abnormal', type: 'error', text: `已标记异常：${form.value.isAbnormal}（将计入异常汇总，可追溯至 A13 / D4）。` })
  }
  return out
})

async function onOcrUpload(file: File): Promise<boolean> {
  if (props.isReadonly || !form.value) return false
  if (!isAllowedAttachment(file)) {
    ElMessage.error('仅支持图片或 PDF 格式的附件')
    return false
  }
  if (!props.wpId) return false
  ocrLoading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    const fields: Record<string, any> = data?.extracted_fields || {}
    const confidence: number = data?.confidence ?? 0
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR 完成，未识别到可填充字段')
      return false
    }
    const { patch, lowConfidence } = mapOcrToVoucherFields(fields, confidence)
    // 仅填充当前为空的字段，保留已录入值
    const mergePatch: Partial<VoucherCheckRow> = {}
    for (const [k, v] of Object.entries(patch)) {
      const cur = (form.value as any)[k]
      const empty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
      if (empty) (mergePatch as any)[k] = v
    }
    if (!Object.keys(mergePatch).length) {
      ElMessage.info('OCR 识别字段均已有值，未覆盖')
      return false
    }
    const preview = Object.entries(mergePatch)
      .map(([k, v]) => `${k}: ${v}${lowConfidence.includes(k as keyof VoucherCheckRow) ? ' ⚠需复核' : ''}`)
      .join('<br/>')
    await ElMessageBox.confirm(
      `<div style="font-size:13px">整体置信度：${(confidence * 100).toFixed(0)}%<br/>${preview}</div>`,
      'OCR 识别结果',
      { confirmButtonText: '填入', cancelButtonText: '取消', dangerouslyUseHTMLString: true,
        type: confidence < CONFIDENCE_THRESHOLD ? 'warning' : 'info' },
    )
    form.value = { ...form.value, ...mergePatch, attachment: file.name }
    ElMessage.success('已填入 OCR 识别结果')
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString?.() !== 'cancel') ElMessage.warning('OCR 识别失败，请稍后重试')
  } finally {
    ocrLoading.value = false
  }
  return false
}

function onSave() {
  if (!form.value || props.isReadonly) return
  emit('save', { ...form.value })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.d3-vc-dialog { display: flex; flex-direction: column; gap: 12px; max-height: 66vh; overflow-y: auto; }
.grp :deep(.el-card__header) { padding: 8px 12px; }
.grp :deep(.el-card__body) { padding: 12px; }
.grp-title { font-weight: 600; font-size: 13px; color: #303133; }
.hdr-tag { margin-left: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
.fld { display: flex; flex-direction: column; gap: 4px; }
.fld--wide { grid-column: 1 / -1; }
.fld label { font-size: 12px; color: #606266; }
.doc-row { display: flex; align-items: center; gap: 8px; }
.check-list { display: flex; flex-direction: column; gap: 8px; }
.live-check { margin: 0; }
</style>
