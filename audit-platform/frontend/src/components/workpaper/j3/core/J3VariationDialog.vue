<script setup lang="ts">
/**
 * J3VariationDialog — J3-2「抽查本期增减变动的准确性」引导式录入弹窗
 *
 * 把 19 列超宽测算表拆成分组卡片，点点点录入 + 测算vs账面差异实时勾稽分析，
 * 内嵌 CAS 11 关注要点（雇员判断/条款一致/重大时间间隔）。
 */
import { reactive, computed, watch } from 'vue'

export interface VariationRow {
  id: number
  category: string; time: string; unitFV: number; unitCash: number
  totalPeople: number; leftPeople: number; exercisePeople: number; sharesPerPerson: number; serviceYears: number
  calcSalary: number; bookSalary: number; cashPaid: number
  calcExpense: number; bookExpense: number
  isEmployee: string; termsConsistent: string; bigTimeGap: string
}

const props = defineProps<{ modelValue: boolean; row: VariationRow | null; isReadonly?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; save: [row: VariationRow] }>()

const CATEGORY_OPTIONS = ['股票期权', '限制性股票', '股票增值权', '员工持股计划', '其他']
const YN_OPTIONS = ['是', '否']

function emptyRow(): VariationRow {
  return {
    id: 0, category: '', time: '', unitFV: 0, unitCash: 0,
    totalPeople: 0, leftPeople: 0, exercisePeople: 0, sharesPerPerson: 0, serviceYears: 0,
    calcSalary: 0, bookSalary: 0, cashPaid: 0, calcExpense: 0, bookExpense: 0,
    isEmployee: '', termsConsistent: '', bigTimeGap: '',
  }
}
const local = reactive<VariationRow>(emptyRow())
const isEdit = computed(() => !!props.row && props.row.id > 0)
watch(() => props.modelValue, (v) => { if (v) Object.assign(local, props.row ? { ...props.row } : emptyRow()) })

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number): string { if (!v) return '0.00'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
const diffSalary = computed(() => n(local.calcSalary) - n(local.bookSalary))
const diffExpense = computed(() => n(local.calcExpense) - n(local.bookExpense))

interface Hint { type: 'success' | 'warning' | 'info'; text: string }
const analysis = computed<Hint[]>(() => {
  const out: Hint[] = []
  if (Math.abs(diffSalary.value) >= 0.01) out.push({ type: 'warning', text: `应付职工薪酬测算数与账面数差异 ${fmt(diffSalary.value)} 元，需查明原因并考虑是否调整。` })
  else if (n(local.calcSalary) || n(local.bookSalary)) out.push({ type: 'success', text: '应付职工薪酬测算数与账面数一致。' })
  if (Math.abs(diffExpense.value) >= 0.01) out.push({ type: 'warning', text: `当期费用/公允价值变动测算数与账面数差异 ${fmt(diffExpense.value)} 元，需查明原因。` })
  else if (n(local.calcExpense) || n(local.bookExpense)) out.push({ type: 'success', text: '当期费用/公允价值变动测算数与账面数一致。' })
  if (local.isEmployee === '否') out.push({ type: 'warning', text: '存在非雇员且非提供类似服务人员的股份支付，应按 CAS 11 之外的相关准则处理，请复核分类。' })
  if (local.termsConsistent === '否') out.push({ type: 'warning', text: '主要条款及条件与股份支付工具不一致，需核对董事会决议/授权文件并查明差异。' })
  if (local.bigTimeGap === '是') out.push({ type: 'warning', text: '授权日与行权日之间存在重大时间间隔，关注是否存在日期倒签等获取不正当利益情形。' })
  return out
})
const canSave = computed(() => !!local.category.trim() || !!local.time.trim())

function onSave() { if (props.isReadonly || !canSave.value) return; emit('save', { ...local }); emit('update:modelValue', false) }
function onClose() { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog :model-value="modelValue" :title="isEdit ? '编辑增减变动测算' : '新增增减变动测算'" width="820px" top="6vh" append-to-body @update:model-value="onClose">
    <div class="var-dialog-body">
      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>① 基本信息</span><span class="grp-tip">按股份支付种类分别测算</span></div></template>
        <el-form label-width="170px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="12"><el-form-item label="股份支付种类">
              <el-select v-model="local.category" filterable allow-create default-first-option :disabled="isReadonly" placeholder="选择或输入" style="width:100%">
                <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item></el-col>
            <el-col :span="12"><el-form-item label="时间"><el-input v-model="local.time" :disabled="isReadonly" placeholder="如 2024年度 / 授予批次" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12"><el-form-item label="每股/份公允价值"><el-input-number v-model="local.unitFV" :controls="false" :precision="4" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="每股/份支付现金"><el-input-number v-model="local.unitCash" :controls="false" :precision="4" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
          </el-row>
        </el-form>
      </el-card>

      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>② 人数与股份</span><span class="grp-tip">按最佳估计的可行权数量测算</span></div></template>
        <el-form label-width="170px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="股份支付总人数"><el-input-number v-model="local.totalPeople" :controls="false" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="离职人数"><el-input-number v-model="local.leftPeople" :controls="false" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="行权人数"><el-input-number v-model="local.exercisePeople" :controls="false" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12"><el-form-item label="每人获得股份数量"><el-input-number v-model="local.sharesPerPerson" :controls="false" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="连续服务年限"><el-input-number v-model="local.serviceYears" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
          </el-row>
        </el-form>
      </el-card>

      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>③ 金额勾稽（测算 vs 账面）</span><span class="grp-tip">测算数与账面数比对，差异自动计算</span></div></template>
        <el-form label-width="170px" label-position="right" size="small">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="测算应付职工薪酬"><el-input-number v-model="local.calcSalary" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="账面应付职工薪酬"><el-input-number v-model="local.bookSalary" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="差异（自动）"><span class="diff-cell" :class="{ warn: Math.abs(diffSalary) >= 0.01 }">{{ fmt(diffSalary) }}</span></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="测算当期费用/公允价值变动"><el-input-number v-model="local.calcExpense" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="账面当期费用/公允价值变动"><el-input-number v-model="local.bookExpense" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="差异（自动）"><span class="diff-cell" :class="{ warn: Math.abs(diffExpense) >= 0.01 }">{{ fmt(diffExpense) }}</span></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="支付现金金额"><el-input-number v-model="local.cashPaid" :controls="false" :precision="2" :disabled="isReadonly" style="width:100%" /></el-form-item></el-col>
          </el-row>
        </el-form>
      </el-card>

      <el-card shadow="never" class="grp-card">
        <template #header><div class="grp-hd"><span>④ 合规判断</span><span class="grp-tip">要点1、8：雇员身份、条款一致性、授权日与行权日时间间隔</span></div></template>
        <el-form label-width="230px" label-position="right" size="small">
          <el-form-item label="是否为雇员或提供类似服务的人员">
            <el-radio-group v-model="local.isEmployee" :disabled="isReadonly"><el-radio v-for="o in YN_OPTIONS" :key="o" :value="o" border>{{ o }}</el-radio></el-radio-group>
          </el-form-item>
          <el-form-item label="主要条款及条件与工具是否一致">
            <el-radio-group v-model="local.termsConsistent" :disabled="isReadonly"><el-radio v-for="o in YN_OPTIONS" :key="o" :value="o" border>{{ o }}</el-radio></el-radio-group>
          </el-form-item>
          <el-form-item label="授权日与行权日是否存在重大时间间隔">
            <el-radio-group v-model="local.bigTimeGap" :disabled="isReadonly"><el-radio v-for="o in YN_OPTIONS" :key="o" :value="o" border>{{ o }}</el-radio></el-radio-group>
          </el-form-item>
        </el-form>
      </el-card>

      <div class="analysis-panel">
        <div class="analysis-hd">🔎 边录入边分析（差异勾稽与合规判断）</div>
        <el-alert v-for="(h, i) in analysis" :key="i" :type="h.type" :title="h.text" :closable="false" show-icon class="analysis-item" />
        <div v-if="analysis.length === 0" class="analysis-empty">填写测算与账面金额后，将在此显示差异勾稽与合规判断提示。</div>
      </div>
    </div>
    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" :disabled="isReadonly || !canSave" @click="onSave">{{ isEdit ? '保存修改' : '添加' }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.var-dialog-body { max-height: 68vh; overflow-y: auto; padding-right: 4px; }
.grp-card { margin-bottom: 12px; }
.grp-card :deep(.el-card__header) { padding: 8px 14px; background: #fafafa; }
.grp-card :deep(.el-card__body) { padding: 12px 14px; }
.grp-hd { display: flex; flex-direction: column; gap: 2px; }
.grp-hd > span:first-child { font-size: 13px; font-weight: 600; color: #303133; }
.grp-tip { font-size: 12px; color: #b88230; }
.diff-cell { font-weight: 600; color: #67c23a; }
.diff-cell.warn { color: #e6a23c; }
.analysis-panel { border: 1px dashed #e6a23c; border-radius: 6px; padding: 10px 12px; background: #fffdf8; }
.analysis-hd { font-size: 13px; font-weight: 600; color: #b88230; margin-bottom: 8px; }
.analysis-item { margin-bottom: 6px; }
.analysis-item:last-child { margin-bottom: 0; }
.analysis-empty { font-size: 12px; color: #909399; }
</style>
