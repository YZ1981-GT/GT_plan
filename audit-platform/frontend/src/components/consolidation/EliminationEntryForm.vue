<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑抵消分录' : '新建抵消分录'"
    width="800px"
    :close-on-click-modal="false"
    @closed="onClosed"
    class="gt-dialog"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" size="default">
      <!-- 基本信息行 -->
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="分录类型" prop="entry_type">
            <el-select v-model="form.entry_type" placeholder="请选择类型" style="width: 100%">
              <el-option label="投资类" value="investment" />
              <el-option label="往来类" value="ar_ap" />
              <el-option label="交易类" value="transaction" />
              <el-option label="内部收入类" value="internal_income" />
              <el-option label="其他" value="other" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="会计期间" prop="year">
            <el-date-picker
              v-model="form.year"
              type="year"
              placeholder="选择年份"
              value-format="YYYY"
              :clearable="false"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="币种" prop="currency">
            <el-select v-model="form.currency" placeholder="默认人民币" style="width: 100%">
              <el-option label="人民币 (CNY)" value="CNY" />
              <el-option label="美元 (USD)" value="USD" />
              <el-option label="港元 (HKD)" value="HKD" />
              <el-option label="欧元 (EUR)" value="EUR" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 关联公司 -->
      <el-form-item label="关联公司" prop="related_company_codes">
        <el-select
          v-model="form.related_company_codes"
          multiple
          placeholder="选择参与抵消的公司"
          style="width: 100%"
          collapse-tags
          collapse-tags-tooltip
        >
          <el-option
            v-for="c in companyOptions"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>
      </el-form-item>

      <!-- 分录说明 -->
      <el-form-item label="分录说明" prop="description">
        <el-input v-model="form.description" placeholder="简要描述此抵消分录的用途" />
      </el-form-item>

      <!-- 借贷行表格 -->
      <el-form-item label="借贷分录" required>
        <div class="lines-wrapper">
          <el-table
            :data="form.lines"
            border
            size="small"
            max-height="280"
            class="lines-table"
          >
            <el-table-column label="科目" min-width="200">
              <template #default="{ row }">
                <el-select
                  v-model="row.account_code"
                  filterable
                  remote
                  :remote-method="(q: string) => searchAccounts(q)"
                  placeholder="搜索科目"
                  style="width: 100%"
                  @change="onAccountChange(row)"
                >
                  <el-option
                    v-for="acc in accountOptions"
                    :key="acc.code"
                    :label="`${acc.code} - ${acc.name}`"
                    :value="acc.code"
                  />
                </el-select>
              </template>
            </el-table-column>

            <el-table-column label="借贷方向" width="100" align="center">
              <template #default="{ row }">
                <el-select v-model="row.direction" style="width: 80px">
                  <el-option label="借" value="debit" />
                  <el-option label="贷" value="credit" />
                </el-select>
              </template>
            </el-table-column>

            <el-table-column label="金额" width="150" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.amount"
                  :precision="2"
                  :min="0"
                  controls-position="right"
                  style="width: 130px"
                  placeholder="0.00"
                />
              </template>
            </el-table-column>

            <el-table-column label="币种" width="90" align="center">
              <template #default="{ row }">
                <el-select v-model="row.currency" style="width: 70px" size="small">
                  <el-option label="CNY" value="CNY" />
                  <el-option label="USD" value="USD" />
                  <el-option label="HKD" value="HKD" />
                  <el-option label="EUR" value="EUR" />
                </el-select>
              </template>
            </el-table-column>

            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-model="row.remark" placeholder="可选备注" size="small" />
              </template>
            </el-table-column>

            <el-table-column label="操作" width="70" align="center">
              <template #default="{ $index }">
                <el-button
                  type="danger"
                  size="small"
                  text
                  :disabled="form.lines.length <= 2"
                  @click="removeLine($index)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-button
            type="primary"
            plain
            size="small"
            @click="addLine"
            style="margin-top: 8px"
          >
            <el-icon><Plus /></el-icon> 添加行
          </el-button>
        </div>
      </el-form-item>

      <!-- 借贷平衡校验 -->
      <div class="balance-check">
        <span class="balance-item">
          <span class="balance-label">借方合计：</span>
          <span class="debit">{{ formatNum(totalDebit) }}</span>
        </span>
        <span class="balance-item">
          <span class="balance-label">贷方合计：</span>
          <span class="credit">{{ formatNum(totalCredit) }}</span>
        </span>
        <span class="balance-item">
          <span class="balance-label">差额：</span>
          <span :class="balanceClass">{{ formatNum(diff) }}</span>
        </span>
        <el-alert
          v-if="diff !== 0"
          type="error"
          title="借贷不平衡，无法保存"
          show-icon
          :closable="false"
          style="padding: 4px 8px; margin-top: 6px"
        />
      </div>

      <!-- 备注 -->
      <el-form-item label="备注" prop="remark" style="margin-top: 12px">
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="2"
          placeholder="补充说明（可选）"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="diff !== 0" @click="onSave">
        {{ isEdit ? '保存修改' : '创建分录' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  createEliminationEntry,
  updateEliminationEntry,
  type EliminationEntry,
  type EliminationEntryType,
  type EliminationEntryCreatePayload,
  type EliminationEntryUpdatePayload,
} from '@/services/consolidationApi'

// ─── Props & Emits ─────────────────────────────────────────────────────────
const props = defineProps<{
  visible: boolean
  entry?: EliminationEntry | null
  projectId: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  saved: [entry: EliminationEntry]
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const formRef = ref()
const saving = ref(false)

// 公司选项（静态，实际从接口获取）
const companyOptions = ref<Array<{ code: string; name: string }>>([])

// 科目选项（远程搜索）
const accountOptions = ref<Array<{ code: string; name: string }>>([])

interface LineForm {
  account_code: string
  account_name?: string
  direction: 'debit' | 'credit'
  amount: number
  currency: string
  remark?: string
}

const defaultForm = (): {
  entry_type: EliminationEntryType
  year: string
  currency: string
  description: string
  related_company_codes: string[]
  lines: LineForm[]
  remark: string
} => ({
  entry_type: 'transaction',
  year: String(new Date().getFullYear()),
  currency: 'CNY',
  description: '',
  related_company_codes: [],
  lines: [
    { account_code: '', direction: 'debit', amount: 0, currency: 'CNY', remark: '' },
    { account_code: '', direction: 'credit', amount: 0, currency: 'CNY', remark: '' },
  ],
  remark: '',
})

const form = ref(defaultForm())

// ─── Computed ────────────────────────────────────────────────────────────────
const isEdit = computed(() => !!props.entry?.id)

const totalDebit = computed(() =>
  form.value.lines
    .filter(l => l.direction === 'debit')
    .reduce((sum, l) => sum + (l.amount || 0), 0)
)

const totalCredit = computed(() =>
  form.value.lines
    .filter(l => l.direction === 'credit')
    .reduce((sum, l) => sum + (l.amount || 0), 0)
)

const diff = computed(() => totalDebit.value - totalCredit.value)

const balanceClass = computed(() => {
  if (Math.abs(diff.value) < 0.005) return 'balanced'
  return diff.value > 0 ? 'debit' : 'credit'
})

const visible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v),
})

// ─── Validation ──────────────────────────────────────────────────────────────
const rules = {
  entry_type: [{ required: true, message: '请选择分录类型', trigger: 'change' }],
  year: [{ required: true, message: '请选择会计期间', trigger: 'change' }],
  description: [
    { required: true, message: '请填写分录说明', trigger: 'blur' },
    { min: 2, max: 200, message: '说明长度 2-200 字符', trigger: 'blur' },
  ],
  related_company_codes: [
    { type: 'array', required: true, min: 2, message: '至少选择两个参与公司', trigger: 'change' },
  ],
}

// ─── Methods ─────────────────────────────────────────────────────────────────
function formatNum(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function addLine() {
  form.value.lines.push({
    account_code: '',
    direction: 'debit',
    amount: 0,
    currency: form.value.currency,
    remark: '',
  })
}

function removeLine(index: number) {
  if (form.value.lines.length > 2) {
    form.value.lines.splice(index, 1)
  }
}

function onAccountChange(line: LineForm) {
  const acc = accountOptions.value.find(a => a.code === line.account_code)
  if (acc) line.account_name = acc.name
}

async function searchAccounts(query: string) {
  if (!query) return
  // 模拟搜索，实际应调用 API
  // 这里使用静态数据演示
  const staticAccounts = [
    { code: '1002', name: '银行存款' },
    { code: '1122', name: '应收账款' },
    { code: '2202', name: '应付账款' },
    { code: '3103', name: '实收资本' },
    { code: '4001', name: '主营业务收入' },
    { code: '5001', name: '主营业务成本' },
    { code: '6001', name: '投资收益' },
    { code: '6101', name: '公允价值变动损益' },
    { code: '6301', name: '营业外收入' },
    { code: '6401', name: '其他业务成本' },
    { code: '6602', name: '销售费用' },
    { code: '6602', name: '管理费用' },
    { code: '6701', name: '资产减值损失' },
    { code: '6901', name: '所得税费用' },
  ]
  accountOptions.value = staticAccounts.filter(
    a => a.code.includes(query) || a.name.includes(query)
  )
}

function loadCompanyOptions() {
  // 从项目公司列表加载，简化处理
  companyOptions.value = [
    { code: '001', name: '母公司' },
    { code: '101', name: '子公司A' },
    { code: '102', name: '子公司B' },
    { code: '103', name: '子公司C' },
  ]
}

function loadEntryData() {
  if (props.entry) {
    const e = props.entry
    form.value = {
      entry_type: e.entry_type,
      year: String(e.year),
      currency: (e.lines[0]?.currency as string) || 'CNY',
      description: e.description,
      related_company_codes: e.related_company_codes || [],
      lines: e.lines.map(l => ({
        account_code: l.account_code,
        account_name: l.account_name,
        direction: (l.debit_amount || 0) > 0 ? 'debit' as const : 'credit' as const,
        amount: Math.abs((l.debit_amount || 0) || (l.credit_amount || 0)),
        currency: (l.currency as string) || 'CNY',
        remark: (l.remark as string) || '',
      })),
      remark: '',
    }
  } else {
    form.value = defaultForm()
  }
}

async function onSave() {
  try {
    await formRef.value?.validate()
  } catch {
    ElMessage.error('请检查表单填写')
    return
  }

  if (form.value.lines.length < 2) {
    ElMessage.error('至少需要两条分录')
    return
  }

  if (Math.abs(diff.value) > 0.005) {
    ElMessage.error('借贷不平衡，无法保存')
    return
  }

  saving.value = true
  try {
    const lines = form.value.lines.map(l => ({
      account_code: l.account_code,
      account_name: l.account_name || '',
      debit_amount: l.direction === 'debit' ? l.amount : 0,
      credit_amount: l.direction === 'credit' ? l.amount : 0,
      currency: l.currency,
      remark: l.remark,
    }))

    if (isEdit.value && props.entry?.id) {
      const payload: EliminationEntryUpdatePayload = {
        entry_type: form.value.entry_type,
        description: form.value.description,
        lines,
        related_company_codes: form.value.related_company_codes,
        currency: form.value.currency,
      }
      const result = await updateEliminationEntry(props.entry.id, props.projectId, payload)
      ElMessage.success('保存成功')
      emit('saved', result)
      visible.value = false
    } else {
      const payload: EliminationEntryCreatePayload = {
        project_id: props.projectId,
        year: Number(form.value.year),
        entry_type: form.value.entry_type,
        description: form.value.description,
        lines,
        related_company_codes: form.value.related_company_codes,
        currency: form.value.currency,
      }
      const result = await createEliminationEntry(props.projectId, payload)
      ElMessage.success('创建成功')
      emit('saved', result)
      visible.value = false
    }
  } catch (e: unknown) {
    ElMessage.error('保存失败')
    console.error(e)
  } finally {
    saving.value = false
  }
}

function onClosed() {
  formRef.value?.resetFields()
  form.value = defaultForm()
  accountOptions.value = []
}

watch(() => props.visible, v => {
  if (v) {
    loadCompanyOptions()
    loadEntryData()
  }
})
</script>

<style scoped>
.gt-dialog :deep(.el-dialog__header) {
  background: var(--gt-color-primary);
  color: #fff;
}

.lines-wrapper {
  width: 100%;
}

.balance-check {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--gt-space-4);
  padding: var(--gt-space-3);
  background: #f8f7fc;
  border-radius: var(--gt-radius-sm);
  margin-top: var(--gt-space-2);
}

.balance-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-1);
  font-size: 14px;
}

.balance-label {
  font-weight: 600;
  color: #333;
}

.debit { color: var(--gt-color-coral, #FF5149); font-weight: 600; }
.credit { color: var(--gt-color-teal, #0094B3); font-weight: 600; }
.balanced { color: var(--gt-color-success, #28A745); font-weight: 600; }
</style>
