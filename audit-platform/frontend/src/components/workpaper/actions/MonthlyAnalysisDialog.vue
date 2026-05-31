<template>
  <el-dialog
    v-model="visible"
    title="月度分析取数"
    width="480px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="科目编码" prop="account_code">
        <el-select
          v-model="form.account_code"
          filterable
          allow-create
          placeholder="输入或选择末级明细科目"
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

      <el-form-item label="会计年度" prop="year">
        <el-input-number
          v-model="form.year"
          :min="2000"
          :max="2100"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <div class="dialog-tip">
      <el-icon><InfoFilled /></el-icon>
      <span>将按月汇总该科目的借贷发生额及累计余额，填入月度分析底稿</span>
    </div>

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
import { InfoFilled } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

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
  year: new Date().getFullYear() - 1,
})

const rules: FormRules = {
  account_code: [{ required: true, message: '请选择科目编码', trigger: 'change' }],
  year: [{ required: true, message: '请输入会计年度', trigger: 'blur' }],
}

const commonAccountCodes = [
  { value: '6001', label: '主营业务收入' },
  { value: '6401', label: '主营业务成本' },
  { value: '6602', label: '管理费用' },
  { value: '6601', label: '销售费用' },
  { value: '6603', label: '财务费用' },
  { value: '1122', label: '应收账款' },
  { value: '2202', label: '应付账款' },
]

async function handleConfirm() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('confirm', { ...form })
}
</script>

<style scoped>
.dialog-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
