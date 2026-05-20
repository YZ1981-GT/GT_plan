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

    <div class="gt-cutoff-toolbar">
      <span>截止日期：</span>
      <el-date-picker v-model="form.cutoff_date" type="date" size="small" value-format="YYYY-MM-DD" />
      <span>前后天数：</span>
      <el-input-number v-model="form.days_before" size="small" :min="1" :max="30" />
      <el-input-number v-model="form.days_after" size="small" :min="1" :max="30" />
      <el-button size="small" type="primary" plain :loading="autoSampling" @click="onAutoSample">📊 自动抽样</el-button>
    </div>

    <el-table :data="form.items" stripe height="450">
      <el-table-column label="#" type="index" width="50" />
      <el-table-column label="凭证号" prop="voucher_no" width="120" />
      <el-table-column label="日期" prop="voucher_date" width="110" />
      <el-table-column label="科目" prop="account_code" width="100" />
      <el-table-column label="金额" width="130">
        <template #default="{ row }">
          <span :class="{ 'gt-cutoff-credit': row.amount < 0 }">{{ formatAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期间正确" width="120">
        <template #default="{ row }">
          <el-checkbox v-model="row.period_correct" />
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.note" size="small" />
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
    </el-table>

    <div class="gt-cutoff-summary">
      <el-tag>抽样：{{ form.items.length }} 笔</el-tag>
      <el-tag type="warning">跨期：{{ crossPeriodCount }} 笔</el-tag>
      <el-tag type="success">期间正确：{{ correctCount }} 笔</el-tag>
    </div>

    <div class="gt-cutoff-conclusion">
      <span class="gt-cutoff-conclusion-label">结论：</span>
      <el-input
        v-model="form.conclusion"
        type="textarea"
        :rows="3"
        placeholder="请填写截止测试结论"
      />
      <AiConclusionButton
        :wp-id="wpId"
        scenario="cutoff_conclusion"
        :sheet-key="sheetKey"
        :context="{ items: form.items, cross_period: crossPeriodCount }"
        @apply="(t) => (form.conclusion = t)"
      />
    </div>

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
 * E1CutoffDialog — E1 类截止测试弹窗（Sprint 2 Task 2.10）
 *
 * 适用 sheet：E1-21/E1-22/E1-23 截止测试相关
 * - el-table 数据驱动 + 逐笔核对标记
 * - 自动从 ledger 抽样填充
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './AuditContextHeader.vue'
import ItemAnnotation from '../ItemAnnotation.vue'
import ItemAttachment from '../ItemAttachment.vue'
import AiConclusionButton from '../AiConclusionButton.vue'
import { confirmLeave } from '@/utils/confirm'

interface Props {
  modelValue: boolean
  projectId: string
  wpId: string
  sheetKey: string
  title?: string
  procedureCode?: string
  assertions?: string[]
  riskLevel?: string
  /** 抽样目标科目，默认现金 */
  sampleAccount?: string
}
const props = withDefaults(defineProps<Props>(), {
  title: 'E1 截止测试',
  procedureCode: '',
  assertions: () => [],
  riskLevel: '',
  sampleAccount: '1001',
})
const emit = defineEmits<{ 'update:modelValue': [v: boolean]; saved: [] }>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => (visible.value = v))
watch(visible, (v) => emit('update:modelValue', v))

const form = ref({
  cutoff_date: '',
  days_before: 5,
  days_after: 5,
  items: [] as any[],
  conclusion: '',
})
const saving = ref(false)
const autoSampling = ref(false)

const crossPeriodCount = computed(() => form.value.items.filter((it) => it.period_correct === false).length)
const correctCount = computed(() => form.value.items.filter((it) => it.period_correct === true).length)

function formatAmount(v: number | string): string {
  const n = Number(v) || 0
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadData() {
  try {
    const detail: any = await api.get(`/api/projects/${props.projectId}/working-papers/${props.wpId}`)
    const sheet = detail?.parsed_data?.[props.sheetKey] || {}
    form.value = {
      cutoff_date: sheet.cutoff_date || new Date().toISOString().slice(0, 10),
      days_before: Number(sheet.days_before) || 5,
      days_after: Number(sheet.days_after) || 5,
      items: Array.isArray(sheet.items) ? sheet.items : [],
      conclusion: sheet.conclusion || '',
    }
  } catch {
    /* 静默 */
  }
}
watch(visible, (v) => { if (v) loadData() })

async function onAutoSample() {
  autoSampling.value = true
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/ledger/cutoff-sample`, {
      params: {
        account_code: props.sampleAccount,
        cutoff_date: form.value.cutoff_date,
        days_before: form.value.days_before,
        days_after: form.value.days_after,
      },
    })
    const items = Array.isArray(data?.items) ? data.items : []
    form.value.items = items.map((it: any) => ({
      voucher_no: it.voucher_no,
      voucher_date: it.voucher_date,
      account_code: it.account_code,
      amount: it.amount || it.debit_amount || -(it.credit_amount || 0),
      period_correct: null,
      note: '',
      annotations: [],
    }))
    ElMessage.success(`已抽样 ${form.value.items.length} 笔`)
  } catch (err: any) {
    ElMessage.warning('自动抽样未配置（端点未实现），可手动添加')
  } finally {
    autoSampling.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await api.patch(`/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`, {
      sheet_key: props.sheetKey,
      data: {
        cutoff_date: form.value.cutoff_date,
        days_before: form.value.days_before,
        days_after: form.value.days_after,
        auto_sampled: form.value.items.length > 0,
        items: form.value.items,
        issues_found: crossPeriodCount.value,
        conclusion: form.value.conclusion,
      },
    })
    ElMessage.success('已保存')
    eventBus.emit('manual-refresh', { projectId: props.projectId, wpId: props.wpId })
    emit('saved')
    visible.value = false
  } catch (err: any) {
    ElMessage.error('保存失败：' + (err?.message || '请稍后重试'))
  } finally {
    saving.value = false
  }
}

async function onCancel() {
  try {
    await confirmLeave('E1 截止测试')
    visible.value = false
  } catch {
    /* user cancelled */
  }
}

function onCloseAttempt(_done: any) {
  onCancel()
}
</script>

<style scoped>
.gt-cutoff-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 4px;
  margin-bottom: 8px;
  font-size: 12px;
}
.gt-cutoff-summary {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 4px;
}
.gt-cutoff-conclusion {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 12px;
  margin-top: 8px;
}
.gt-cutoff-conclusion-label {
  white-space: nowrap;
  padding-top: 6px;
  color: var(--gt-color-text-secondary);
}
.gt-cutoff-conclusion :deep(.el-textarea) {
  flex: 1;
}
.gt-cutoff-credit {
  color: var(--gt-color-danger, #f56c6c);
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
