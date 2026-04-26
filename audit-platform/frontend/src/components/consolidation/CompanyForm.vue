<template>
  <el-dialog append-to-body
    :model-value="visible"
    :title="isEdit ? '编辑公司信息' : '新增公司'"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
    @closed="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="140px"
      size="default"
    >
      <!-- 公司名称 -->
      <el-form-item label="公司名称" prop="companyName">
        <el-input v-model="form.companyName" placeholder="请输入公司全称" />
      </el-form-item>

      <!-- 三码 -->
      <el-divider content-position="left">三码信息</el-divider>

      <el-form-item label="统一社会信用代码" prop="companyCode">
        <el-input
          v-model="form.companyCode"
          placeholder="统一社会信用代码（18位）"
          :disabled="isEdit"
          maxlength="18"
        />
      </el-form-item>

      <el-form-item label="纳税人识别号" prop="taxCode">
        <el-input v-model="form.taxCode" placeholder="税务登记号" maxlength="20" />
      </el-form-item>

      <el-form-item label="股票代码" prop="stockCode">
        <el-input v-model="form.stockCode" placeholder="沪深股票代码（选填）" maxlength="10" />
      </el-form-item>

      <!-- 股权信息 -->
      <el-divider content-position="left">股权信息</el-divider>

      <el-form-item label="持股比例" prop="ownershipPercentage">
        <el-input-number
          v-model="form.ownershipPercentage"
          :min="0"
          :max="100"
          :precision="2"
          placeholder="0-100"
          style="width: 100%"
        >
          <template #suffix>%</template>
        </el-input-number>
      </el-form-item>

      <el-form-item label="合并方法" prop="consolidationMethod">
        <el-select v-model="form.consolidationMethod" placeholder="请选择合并方法" style="width: 100%">
          <el-option
            v-for="item in consolMethodOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          >
            <div class="method-option">
              <span class="method-dot" :class="item.value"></span>
              {{ item.label }}
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- 期间信息 -->
      <el-divider content-position="left">合并期间</el-divider>

      <el-form-item label="收购日期" prop="acquisitionDate">
        <el-date-picker
          v-model="form.acquisitionDate"
          type="date"
          placeholder="选择收购日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="处置日期" prop="disposalDate">
        <el-date-picker
          v-model="form.disposalDate"
          type="date"
          placeholder="选择处置日期（留空表示未处置）"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          clearable
          style="width: 100%"
        />
      </el-form-item>

      <!-- 基本信息 -->
      <el-divider content-position="left">基本信息</el-divider>

      <el-form-item label="功能货币" prop="functionalCurrency">
        <el-select v-model="form.functionalCurrency" placeholder="选择功能货币" style="width: 100%">
          <el-option label="人民币 (CNY)" value="CNY" />
          <el-option label="美元 (USD)" value="USD" />
          <el-option label="港币 (HKD)" value="HKD" />
          <el-option label="欧元 (EUR)" value="EUR" />
          <el-option label="英镑 (GBP)" value="GBP" />
          <el-option label="日元 (JPY)" value="JPY" />
        </el-select>
      </el-form-item>

      <el-form-item label="注册资本" prop="registeredCapital">
        <el-input v-model="form.registeredCapital" placeholder="注册资本金额（选填）" />
      </el-form-item>

      <el-form-item label="注册地" prop="registrationCountry">
        <el-input v-model="form.registrationCountry" placeholder="注册国家/地区" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { createCompany, updateCompany, type CompanyCreatePayload, type CompanyUpdatePayload } from '@/services/consolidationApi'

// ─── Types ────────────────────────────────────────────────────────────────────
export interface CompanyFormData {
  companyName: string
  companyCode: string
  taxCode: string
  stockCode: string
  ownershipPercentage: number
  consolidationMethod: string
  acquisitionDate: string
  disposalDate: string | null
  functionalCurrency: string
  registeredCapital: string
  registrationCountry: string
}

interface Props {
  visible: boolean
  company?: {
    id?: string
    companyCode?: string
    companyName?: string
    shareholding?: number | null
    consolMethod?: string | null
    acquisitionDate?: string | null
    disposalDate?: string | null
    functionalCurrency?: string
  } | null
  parentId?: string | null
  parentCode?: string | null
  projectId?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'saved': []
}>()

// ─── State ────────────────────────────────────────────────────────────────────
const formRef = ref<FormInstance>()
const saving = ref(false)

const defaultForm: CompanyFormData = {
  companyName: '',
  companyCode: '',
  taxCode: '',
  stockCode: '',
  ownershipPercentage: 100,
  consolidationMethod: 'full',
  acquisitionDate: '',
  disposalDate: null,
  functionalCurrency: 'CNY',
  registeredCapital: '',
  registrationCountry: '',
}

const form = ref<CompanyFormData>({ ...defaultForm })

// ─── Computed ─────────────────────────────────────────────────────────────────
const isEdit = computed(() => !!props.company?.id)

const consolMethodOptions = [
  { value: 'full', label: '完全合并' },
  { value: 'proportional', label: '比例合并' },
  { value: 'equity', label: '权益法' },
  { value: 'exclude', label: '排除' },
]

// ─── Validation Rules ─────────────────────────────────────────────────────────
const rules: FormRules = {
  companyName: [
    { required: true, message: '请输入公司名称', trigger: 'blur' },
    { min: 2, max: 255, message: '公司名称长度 2-255', trigger: 'blur' },
  ],
  companyCode: [
    { required: true, message: '请输入统一社会信用代码', trigger: 'blur' },
    { min: 15, max: 18, message: '统一社会信用代码 15-18 位', trigger: 'blur' },
  ],
  ownershipPercentage: [
    { required: true, message: '请输入持股比例', trigger: 'blur' },
  ],
  consolidationMethod: [
    { required: true, message: '请选择合并方法', trigger: 'change' },
  ],
  functionalCurrency: [
    { required: true, message: '请选择功能货币', trigger: 'change' },
  ],
}

// ─── Watchers ─────────────────────────────────────────────────────────────────
watch(
  () => props.visible,
  (val) => {
    if (val) {
      if (props.company) {
        form.value = {
          companyName: props.company.companyName || '',
          companyCode: props.company.companyCode || '',
          taxCode: '',
          stockCode: '',
          ownershipPercentage: Number(props.company.shareholding ?? 100),
          consolidationMethod: props.company.consolMethod || 'full',
          acquisitionDate: props.company.acquisitionDate || '',
          disposalDate: props.company.disposalDate || null,
          functionalCurrency: props.company.functionalCurrency || 'CNY',
          registeredCapital: '',
          registrationCountry: '',
        }
      } else {
        form.value = { ...defaultForm }
      }
    }
  },
)

// ─── Submit ───────────────────────────────────────────────────────────────────
async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    saving.value = true
    try {
      const methodMap: Record<string, string | undefined> = {
        full: 'full',
        proportional: 'proportional',
        equity: 'equity',
        exclude: undefined,
      }

      const consolMethodVal = methodMap[form.value.consolidationMethod]

      if (isEdit.value && props.company?.id) {
        const payload: CompanyUpdatePayload = {
          company_name: form.value.companyName,
          shareholding: form.value.ownershipPercentage,
          consol_method: consolMethodVal as any,
          acquisition_date: form.value.acquisitionDate || null,
          disposal_date: form.value.disposalDate || null,
          functional_currency: form.value.functionalCurrency,
          is_active: true,
        }
        await updateCompany(props.company.id, props.projectId!, payload)
      } else {
        const payload: CompanyCreatePayload = {
          project_id: props.projectId!,
          company_code: form.value.companyCode,
          company_name: form.value.companyName,
          parent_code: props.parentCode || null,
          ultimate_code: props.parentCode || form.value.companyCode,
          consol_level: 0,
          shareholding: form.value.ownershipPercentage,
          consol_method: consolMethodVal as any,
          acquisition_date: form.value.acquisitionDate || null,
          disposal_date: form.value.disposalDate || null,
          functional_currency: form.value.functionalCurrency,
          is_active: true,
        }
        await createCompany(payload)
      }

      ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
      emit('update:visible', false)
      emit('saved')
    } catch (e: any) {
      ElMessage.error(e?.message || (isEdit.value ? '更新失败' : '创建失败'))
    } finally {
      saving.value = false
    }
  })
}

function resetForm() {
  formRef.value?.resetFields()
  form.value = { ...defaultForm }
}
</script>

<style scoped>
.method-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.method-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.method-dot.full { background: var(--gt-color-primary); }
.method-dot.proportional { background: var(--gt-color-success); }
.method-dot.equity { background: #e6a23c; }
.method-dot.exclude { background: #909399; }

:deep(.el-divider) {
  margin: 12px 0;
  font-size: 12px;
}
</style>
