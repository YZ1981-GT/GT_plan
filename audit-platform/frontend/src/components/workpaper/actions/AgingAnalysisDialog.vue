<template>
  <el-dialog
    v-model="visible"
    title="账龄分析取数"
    width="600px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="科目编码" prop="account_code">
        <el-select
          v-model="form.account_code"
          filterable
          allow-create
          placeholder="输入应收/应付科目编码"
          style="width: 100%"
        >
          <el-option
            v-for="code in commonAccountCodes"
            :key="code.value"
            :label="`${code.value} ${code.label}`"
            :value="code.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="基准日期" prop="base_date">
        <el-date-picker
          v-model="form.base_date"
          type="date"
          placeholder="选择账龄计算基准日"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="会计年度" prop="year">
        <el-input-number
          v-model="form.year"
          :min="2000"
          :max="2100"
          style="width: 200px"
        />
      </el-form-item>

      <el-form-item label="账龄区间">
        <div class="brackets-list">
          <div
            v-for="(bracket, idx) in form.aging_brackets"
            :key="idx"
            class="bracket-row"
          >
            <el-input
              v-model="bracket.label"
              placeholder="区间名称"
              style="width: 120px"
            />
            <el-input-number
              v-model="bracket.min_days"
              :min="0"
              placeholder="最小天数"
              style="width: 120px"
            />
            <span class="bracket-sep">~</span>
            <el-input-number
              v-model="bracket.max_days"
              :min="0"
              placeholder="最大天数"
              style="width: 120px"
            />
            <el-button
              type="danger"
              :icon="Delete"
              circle
              size="small"
              @click="removeBracket(idx)"
            />
          </div>
          <el-button type="primary" link @click="addBracket">
            + 添加区间
          </el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="executing" @click="handleConfirm">
        执行取数
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

interface AgingBracket {
  label: string
  min_days: number
  max_days: number | null
}

const props = defineProps<{
  modelValue: boolean
  executing?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [params: Record<string, any>]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()

const form = reactive({
  account_code: '',
  base_date: '',
  year: new Date().getFullYear() - 1,
  aging_brackets: [
    { label: '1年以内', min_days: 0, max_days: 365 },
    { label: '1-2年', min_days: 366, max_days: 730 },
    { label: '2-3年', min_days: 731, max_days: 1095 },
    { label: '3年以上', min_days: 1096, max_days: null },
  ] as AgingBracket[],
})

const rules: FormRules = {
  account_code: [{ required: true, message: '请选择科目编码', trigger: 'change' }],
  base_date: [{ required: true, message: '请选择基准日期', trigger: 'change' }],
}

const commonAccountCodes = [
  { value: '1122', label: '应收账款' },
  { value: '1123', label: '预付账款' },
  { value: '1221', label: '其他应收款' },
  { value: '2202', label: '应付账款' },
  { value: '2203', label: '预收账款' },
  { value: '2241', label: '其他应付款' },
]

function addBracket() {
  const last = form.aging_brackets[form.aging_brackets.length - 1]
  const minDays = last ? (last.max_days || last.min_days) + 1 : 0
  form.aging_brackets.push({
    label: `${Math.floor(minDays / 365) + 1}年以上`,
    min_days: minDays,
    max_days: null,
  })
}

function removeBracket(idx: number) {
  if (form.aging_brackets.length > 1) {
    form.aging_brackets.splice(idx, 1)
  }
}

async function handleConfirm() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('confirm', {
    account_code: form.account_code,
    base_date: form.base_date,
    year: form.year,
    aging_brackets: form.aging_brackets,
  })
}
</script>

<style scoped>
.brackets-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bracket-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bracket-sep {
  color: var(--el-text-color-secondary);
}
</style>
