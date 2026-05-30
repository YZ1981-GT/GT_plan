<template>
  <el-dialog
    v-model="visible"
    :title="title"
    :fullscreen="true"
    :close-on-press-escape="false"
    :close-on-click-modal="false"
    @close="onCloseAttempt"
    class="gt-fullscreen-dialog"
  >
    <AuditContextHeader
      :procedure-code="procedureCode"
      :assertions="assertions"
      :risk-level="riskLevel"
    />

    <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px" size="small" class="gt-dcount-form">
      <el-form-item label="盘点日期">
        <el-date-picker v-model="form.count_date" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>

      <el-form-item label="盘点明细">
        <el-table :data="form.items" stripe>
          <el-table-column label="#" type="index" width="50" />
          <el-table-column label="券别/规格" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.denomination" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="数量" width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" size="small" :min="0" :controls="false" />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120">
            <template #default="{ row }">
              <el-input-number v-model="row.amount" size="small" :min="0" :controls="false" :precision="2" />
            </template>
          </el-table-column>
          <el-table-column label="批注" width="180">
            <template #default="{ $index }">
              <ItemAnnotation v-model="form.items[$index].annotations" />
            </template>
          </el-table-column>
          <el-table-column label="附件" width="160">
            <template #default="{ $index }">
              <ItemAttachment
                :project-id="projectId"
                :wp-id="wpId"
                :sheet-key="sheetKey"
                :item-index="$index"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ $index }">
              <el-button text type="danger" size="small" @click="removeItem($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button text size="small" @click="addItem">+ 增加明细</el-button>
      </el-form-item>

      <el-form-item label="盘点合计">
        <el-input v-model="totalCounted" disabled size="small" />
      </el-form-item>

      <el-form-item label="账面余额">
        <el-input-number v-model="form.book_balance" size="small" :precision="2" />
      </el-form-item>

      <el-form-item label="差异">
        <el-tag :type="differenceTagType">{{ difference.toFixed(2) }}</el-tag>
      </el-form-item>

      <el-form-item label="结论">
        <div class="gt-dcount-conclusion-row">
          <el-input
            v-model="form.conclusion"
            type="textarea"
            :rows="3"
            placeholder="请填写盘点结论"
          />
          <AiConclusionButton
            :wp-id="wpId"
            scenario="audit_conclusion"
            :sheet-key="sheetKey"
            :context="{ items: form.items, total: totalCounted, book: form.book_balance, diff: difference }"
            @apply="(t) => (form.conclusion = t)"
          />
        </div>
      </el-form-item>

      <el-form-item label="附件区">
        <ItemAttachment
          :project-id="projectId"
          :wp-id="wpId"
          :sheet-key="sheetKey"
          :item-index="9999"
        />
      </el-form-item>

      <el-form-item label="审计员签字">
        <SignatureBlock
          :project-id="projectId"
          :object-type="'workpaper_sheet'"
          :object-id="`${wpId}:${sheetKey}`"
          role="auditor"
          :signed="!!form.signatures?.auditor?.signed"
          @signed="(s) => onSigned('auditor', s)"
        />
      </el-form-item>

      <el-form-item label="出纳签字">
        <SignatureBlock
          :project-id="projectId"
          :object-type="'workpaper_sheet'"
          :object-id="`${wpId}:${sheetKey}`"
          role="cashier"
          :signed="!!form.signatures?.cashier?.signed"
          @signed="(s) => onSigned('cashier', s)"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="gt-fullscreen-dialog-footer">
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * DCountDialog — D 类盘点弹窗（Sprint 2 Task 2.9 + 2.27）
 *
 * 适用 sheet：E1-7 库存现金盘点 / E1-8 外币盘点 / E1-9 银行存单盘点 等
 * - el-form + items 表格
 * - 双人签字（审计员 + 出纳）
 * - 附件区（ItemAttachment）
 * - AI 审计说明（Task 2.30）
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './AuditContextHeader.vue'
import ItemAnnotation from '../ItemAnnotation.vue'
import ItemAttachment from '../ItemAttachment.vue'
import AiConclusionButton from '../AiConclusionButton.vue'
import SignatureBlock from './SignatureBlock.vue'
import { confirmLeave } from '@/utils/confirm'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import { rules } from '@/utils/formRules'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  modelValue: boolean
  projectId: string
  wpId: string
  sheetKey: string
  title?: string
  procedureCode?: string
  assertions?: string[]
  riskLevel?: string
}
const props = withDefaults(defineProps<Props>(), {
  title: 'D 类盘点',
  procedureCode: '',
  assertions: () => [],
  riskLevel: '',
})
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [] }>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => (visible.value = v))
watch(visible, (v) => emit('update:modelValue', v))

const form = ref({
  count_date: '',
  items: [] as any[],
  book_balance: 0,
  conclusion: '',
  signatures: {} as any,
})
const saving = ref(false)
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  conclusion: [rules.required('结论')],
}
const { sum: decSum, sub: decSub } = useDecimalCalc()

const totalCounted = computed(() => {
  return decSum(...form.value.items.map(it => String(Number(it.amount) || 0)))
})

const difference = computed(() => {
  return Number(decSub(totalCounted.value, String(Number(form.value.book_balance) || 0)))
})
const differenceTagType = computed<'success' | 'warning' | 'danger'>(() => {
  const d = Math.abs(difference.value)
  if (d < 0.01) return 'success'
  if (d < 100) return 'warning'
  return 'danger'
})

async function loadData() {
  try {
    const detail: any = await api.get(`/api/projects/${props.projectId}/working-papers/${props.wpId}`)
    const sheet = detail?.parsed_data?.[props.sheetKey] || {}
    form.value = {
      count_date: sheet.count_date || new Date().toISOString().slice(0, 10),
      items: Array.isArray(sheet.items) ? sheet.items : [],
      book_balance: Number(sheet.book_balance) || 0,
      conclusion: sheet.conclusion || '',
      signatures: sheet.signatures || {},
    }
  } catch {
    /* 静默 */
  }
}
watch(visible, (v) => { if (v) loadData() })

function addItem() {
  form.value.items.push({ denomination: '', quantity: 0, amount: 0, annotations: [] })
}
function removeItem(idx: number) {
  form.value.items.splice(idx, 1)
}

async function onSave() {
  saving.value = true
  try {
    await api.patch(`/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`, {
      sheet_key: props.sheetKey,
      data: {
        count_date: form.value.count_date,
        items: form.value.items,
        book_balance: form.value.book_balance,
        total_counted: Number(totalCounted.value),
        difference: difference.value,
        conclusion: form.value.conclusion,
        signatures: form.value.signatures,
      },
    })
    ElMessage.success('已保存')
    eventBus.emit('manual-refresh', { projectId: props.projectId, wpId: props.wpId })
    emit('saved')
    visible.value = false
  } catch (err: any) {
    handleApiError(err, '保存')
  } finally {
    saving.value = false
  }
}

async function onCancel() {
  try {
    await confirmLeave('D 类盘点')
    visible.value = false
  } catch {
    /* user cancelled */
  }
}

function onCloseAttempt() {
  onCancel()
}

function onSigned(role: 'auditor' | 'cashier', payload: any) {
  form.value.signatures = {
    ...form.value.signatures,
    [role]: { ...payload, signed: true },
  }
}
</script>

<style scoped>
.gt-dcount-form { padding: 4px 12px; }
.gt-dcount-conclusion-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.gt-dcount-conclusion-row :deep(.el-textarea) {
  flex: 1;
}
.gt-fullscreen-dialog :deep(.el-dialog__body) {
  padding: 8px 16px;
  height: calc(100vh - 110px);
  overflow-y: auto;
}
.gt-fullscreen-dialog-footer {
  position: sticky;
  bottom: 0;
  background: var(--gt-color-bg-white, #fff);
  padding: 8px 0;
  border-top: 1px solid var(--gt-color-border-lighter, #ebeef5);
  text-align: right;
}
</style>
