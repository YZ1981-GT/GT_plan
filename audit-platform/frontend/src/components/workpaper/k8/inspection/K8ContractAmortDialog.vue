<template>
  <el-dialog
    :model-value="visible"
    :title="isNew ? '新增合同费用摊销' : '编辑合同费用摊销'"
    width="900px"
    top="5vh"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="amort-dialog-body">
      <!-- 左：分组卡片录入 -->
      <div class="form-col">
        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">① 基本信息</span></template>
          <div class="grp-grid">
            <div class="fld"><label>项目（费用性质）</label>
              <el-select v-model="form.projectName" filterable allow-create size="small" placeholder="律师费/咨询费/租赁费…" style="width:100%">
                <el-option v-for="o in PROJECT_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </div>
            <div class="fld"><label>对方单位</label><el-input v-model="form.counterparty" size="small" /></div>
            <div class="fld fld-full"><label>合同/协议内容</label><el-input v-model="form.contractContent" size="small" /></div>
            <div class="fld"><label>实际开票方</label><el-input v-model="form.invoiceParty" size="small" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">② 合同期间与金额</span></template>
          <div class="grp-grid">
            <div class="fld"><label>合同/协议金额</label><el-input-number v-model="form.contractAmount" :controls="false" :precision="2" size="small" style="width:100%" /></div>
            <div class="fld"><label>支付条件</label><el-input v-model="form.paymentTerm" size="small" /></div>
            <div class="fld"><label>支付时间</label><el-input v-model="form.paymentTime" size="small" placeholder="如 分季付/一次付" /></div>
            <div class="fld"><label>合同开始日期</label><el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" /></div>
            <div class="fld"><label>合同结束日期</label><el-date-picker v-model="form.endDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">③ 摊销计算</span></template>
          <div class="grp-grid">
            <div class="fld"><label>合同总月份（自动）</label><div class="calc-val">{{ totalMonths }} 月</div></div>
            <div class="fld">
              <label>本期应计月份
                <el-checkbox v-model="manualAccrual" size="small" style="margin-left:6px">手工覆盖</el-checkbox>
              </label>
              <el-input-number v-if="manualAccrual" v-model="form.accrualMonths" :controls="false" :precision="0" :min="0" size="small" style="width:100%" />
              <div v-else class="calc-val">{{ autoAccrual }} 月（合同期∩摊销期）</div>
            </div>
            <div class="fld"><label>本期应计损益（自动）</label><div class="calc-val strong">{{ fmtAmt(accruedPL) }}</div></div>
            <div class="fld"><label>本期已计损益（账面）</label><el-input-number v-model="form.bookedPL" :controls="false" :precision="2" size="small" style="width:100%" /></div>
          </div>
        </el-card>

        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">④ 索引与结论</span></template>
          <div class="grp-grid">
            <div class="fld"><label>合同索引</label><el-input v-model="form.contractIndex" size="small" /></div>
            <div class="fld"><label>凭证检查索引</label><el-input v-model="form.voucherIndex" size="small" /></div>
            <div class="fld fld-full"><label>审计结论</label><el-input v-model="form.conclusion" type="textarea" :autosize="{ minRows: 2 }" size="small" :placeholder="diffHint || '摊销核对结论…'" /></div>
          </div>
        </el-card>
      </div>

      <!-- 右：实时分析面板 -->
      <div class="analysis-col">
        <div class="an-title">实时摊销分析</div>
        <div class="an-row"><span>合同金额</span><b>{{ fmtAmt(form.contractAmount) }}</b></div>
        <div class="an-row"><span>合同总月份</span><b>{{ totalMonths }} 月</b></div>
        <div class="an-row"><span>本期应计月份</span><b>{{ effectiveAccrual }} 月</b></div>
        <div class="an-formula">应计损益 = 合同金额 ÷ 总月份 × 应计月份<br/>= {{ fmtAmt(form.contractAmount) }} ÷ {{ totalMonths || '—' }} × {{ effectiveAccrual }}</div>
        <div class="an-row hl"><span>本期应计损益</span><b>{{ fmtAmt(accruedPL) }}</b></div>
        <div class="an-row"><span>本期已计损益</span><b>{{ fmtAmt(form.bookedPL) }}</b></div>
        <div class="an-row" :class="{ 'an-danger': Math.abs(diff) > 1 }"><span>差异（应计−已计）</span><b>{{ fmtAmt(diff) }}</b></div>

        <el-alert v-if="totalMonths === 0 && (form.startDate || form.endDate)" type="warning" :closable="false" show-icon style="margin-top:10px;font-size:12px">
          <template #title>合同起止日期缺失或逆序，总月份为 0，无法摊销</template>
        </el-alert>
        <el-alert v-else-if="Math.abs(diff) > 1" type="error" :closable="false" show-icon style="margin-top:10px;font-size:12px">
          <template #title>{{ diffHint }}</template>
        </el-alert>
        <el-alert v-else-if="totalMonths > 0" type="success" :closable="false" show-icon style="margin-top:10px;font-size:12px">
          <template #title>应计与账面已计一致，摊销恰当</template>
        </el-alert>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="isReadonly" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * K8ContractAmortDialog — K8-5 合同费用摊销引导式录入弹窗（点点点）
 * 分组卡片 + 实时摊销计算 + 差异分析面板（宽表 17 列改引导式录入，仿 J3PlanDialog 范式）。
 */
import { ref, computed, watch } from 'vue'
import {
  monthsInclusive,
  accrualMonthsInPeriod,
  calcAccruedPL,
  type K8AmortRow,
} from '@/components/workpaper/composables/useK8ContractAmortization'

const props = defineProps<{
  visible: boolean
  row: K8AmortRow | null
  amortStart: string
  amortEnd: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', rowKey: string | null, patch: Partial<K8AmortRow> & { __manualAccrual?: boolean }): void
}>()

const PROJECT_OPTIONS = ['律师费', '咨询费', '租赁费', '修理费', '保险费', '物业费', '广告宣传费', '推广费', '运输费', '其他']

const isNew = computed(() => !props.row)

interface FormShape {
  projectName: string; counterparty: string; contractContent: string; contractAmount: number
  invoiceParty: string; paymentTerm: string; paymentTime: string
  startDate: string; endDate: string; accrualMonths: number; bookedPL: number
  contractIndex: string; voucherIndex: string; conclusion: string
}
function emptyForm(): FormShape {
  return {
    projectName: '', counterparty: '', contractContent: '', contractAmount: 0,
    invoiceParty: '', paymentTerm: '', paymentTime: '',
    startDate: '', endDate: '', accrualMonths: 0, bookedPL: 0,
    contractIndex: '', voucherIndex: '', conclusion: '',
  }
}
const form = ref<FormShape>(emptyForm())
const manualAccrual = ref(false)

watch(
  () => [props.visible, props.row],
  () => {
    if (!props.visible) return
    const r = props.row
    if (r) {
      form.value = {
        projectName: r.projectName, counterparty: r.counterparty, contractContent: r.contractContent,
        contractAmount: r.contractAmount, invoiceParty: r.invoiceParty, paymentTerm: r.paymentTerm,
        paymentTime: r.paymentTime, startDate: r.startDate, endDate: r.endDate,
        accrualMonths: r.accrualMonths, bookedPL: r.bookedPL,
        contractIndex: r.contractIndex, voucherIndex: r.voucherIndex, conclusion: r.conclusion,
      }
      manualAccrual.value = !!(r as any).__manualAccrual
    } else {
      form.value = emptyForm()
      manualAccrual.value = false
    }
  },
  { immediate: true },
)

const totalMonths = computed(() => monthsInclusive(form.value.startDate, form.value.endDate))
const autoAccrual = computed(() => accrualMonthsInPeriod(form.value.startDate, form.value.endDate, props.amortStart, props.amortEnd))
const effectiveAccrual = computed(() => (manualAccrual.value ? Number(form.value.accrualMonths) || 0 : autoAccrual.value))
const accruedPL = computed(() => calcAccruedPL(form.value.contractAmount, totalMonths.value, effectiveAccrual.value))
const diff = computed(() => accruedPL.value - (Number(form.value.bookedPL) || 0))
const diffHint = computed(() => {
  const d = diff.value
  if (Math.abs(d) <= 1) return ''
  return d > 0
    ? `应计损益 > 账面已计 ${fmtAmt(Math.abs(d))}：本期少计费用，建议调增销售费用`
    : `应计损益 < 账面已计 ${fmtAmt(Math.abs(d))}：本期多计费用，建议调减销售费用`
})

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleSave(): void {
  if (props.isReadonly) return
  const patch: Partial<K8AmortRow> & { __manualAccrual?: boolean } = {
    projectName: form.value.projectName,
    counterparty: form.value.counterparty,
    contractContent: form.value.contractContent,
    contractAmount: Number(form.value.contractAmount) || 0,
    invoiceParty: form.value.invoiceParty,
    paymentTerm: form.value.paymentTerm,
    paymentTime: form.value.paymentTime,
    startDate: form.value.startDate,
    endDate: form.value.endDate,
    bookedPL: Number(form.value.bookedPL) || 0,
    contractIndex: form.value.contractIndex,
    voucherIndex: form.value.voucherIndex,
    conclusion: form.value.conclusion,
    __manualAccrual: manualAccrual.value,
  }
  if (manualAccrual.value) patch.accrualMonths = Number(form.value.accrualMonths) || 0
  emit('save', props.row ? props.row.rowKey : null, patch)
  emit('update:visible', false)
}
</script>

<style scoped>
.amort-dialog-body { display: flex; gap: 16px; }
.form-col { flex: 1 1 auto; min-width: 0; }
.analysis-col { flex: 0 0 260px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; height: fit-content; position: sticky; top: 0; }
.grp-card { margin-bottom: 12px; }
.grp-card :deep(.el-card__header) { padding: 8px 14px; background: linear-gradient(90deg, #eef6ff 0%, #f8fbff 100%); }
.grp-card :deep(.el-card__body) { padding: 12px 14px; }
.grp-title { font-weight: 600; font-size: 13px; color: #303133; }
.grp-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 16px; }
.fld { display: flex; flex-direction: column; gap: 4px; }
.fld-full { grid-column: 1 / -1; }
.fld label { font-size: 12px; color: var(--el-text-color-secondary); }
.calc-val { font-size: 13px; font-family: 'JetBrains Mono', monospace; color: #303133; padding: 4px 0; }
.calc-val.strong { font-weight: 700; color: #2563eb; }
.an-title { font-weight: 600; font-size: 13px; margin-bottom: 10px; color: #303133; }
.an-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #606266; padding: 4px 0; border-bottom: 1px dashed #ebeef5; }
.an-row b { font-family: 'JetBrains Mono', monospace; color: #303133; }
.an-row.hl b { color: #2563eb; font-weight: 700; }
.an-row.an-danger b { color: #dc2626; }
.an-formula { font-size: 11px; color: #909399; margin: 8px 0; line-height: 1.6; background: #fff; border-radius: 4px; padding: 6px 8px; }
</style>
