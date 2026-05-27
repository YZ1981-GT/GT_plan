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

    <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px" size="small" class="gt-bchk-form">
      <el-form-item label="检查日期">
        <el-date-picker v-model="form.check_date" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>

      <el-form-item label="检查清单">
        <el-table :data="form.items" stripe>
          <el-table-column label="#" type="index" width="50" />
          <el-table-column label="项目" prop="label" min-width="200">
            <template #default="{ row }">
              <el-input v-model="row.label" size="small" placeholder="检查项" />
            </template>
          </el-table-column>
          <el-table-column label="说明/账户" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.description" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="已验证" width="100">
            <template #default="{ row }">
              <el-checkbox v-model="row.verified" />
            </template>
          </el-table-column>
          <el-table-column label="批注" width="220">
            <template #default="{ $index }">
              <ItemAnnotation v-model="form.items[$index].annotations" />
            </template>
          </el-table-column>
          <el-table-column label="附件" width="180">
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
        <el-button text size="small" @click="addItem">+ 增加检查项</el-button>
      </el-form-item>

      <el-form-item label="结论">
        <div class="gt-bchk-conclusion-row">
          <el-input
            v-model="form.conclusion"
            type="textarea"
            :rows="4"
            placeholder="请填写检查结论"
          />
          <AiConclusionButton
            :wp-id="wpId"
            scenario="check_conclusion"
            :sheet-key="sheetKey"
            :context="{ items: form.items }"
            @apply="(t) => (form.conclusion = t)"
          />
        </div>
      </el-form-item>

      <el-form-item label="签字（审计员）">
        <SignatureBlock
          :project-id="projectId"
          :object-type="'workpaper_sheet'"
          :object-id="`${wpId}:${sheetKey}`"
          role="auditor"
          :signed="!!form.signature?.signed"
          @signed="onSigned"
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
 * BCheckListDialog — B 类检查清单弹窗（Sprint 2 Task 2.8 + 2.26 + 2.28）
 *
 * 适用 sheet：E1-10/E1-11/E1-18/E1-19 等检查清单类
 * - el-form + 逐项 verified
 * - ItemAnnotation 逐项批注
 * - ItemAttachment 逐项附件
 * - 单人签字（审计员，Task 2.28）
 * - AI 审计说明按钮（Task 2.30）
 * - 全屏 + ESC 两步退出（Task 2.12）
 */
import { ref, watch } from 'vue'
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
import { rules } from '@/utils/formRules'

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
  title: 'B 类检查清单',
  procedureCode: '',
  assertions: () => [],
  riskLevel: '',
})
const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  saved: []
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => (visible.value = v))
watch(visible, (v) => emit('update:modelValue', v))

const form = ref({
  check_date: '',
  items: [] as any[],
  conclusion: '',
  signature: null as any,
})
const saving = ref(false)
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  conclusion: [rules.required('结论')],
}

async function loadData() {
  try {
    const detail: any = await api.get(`/api/projects/${props.projectId}/working-papers/${props.wpId}`)
    const sheet = detail?.parsed_data?.[props.sheetKey] || {}
    form.value = {
      check_date: sheet.check_date || new Date().toISOString().slice(0, 10),
      items: Array.isArray(sheet.items) ? sheet.items : [],
      conclusion: sheet.conclusion || '',
      signature: sheet.signatures?.auditor || null,
    }
  } catch {
    /* 静默 */
  }
}
watch(visible, (v) => { if (v) loadData() })

function addItem() {
  form.value.items.push({ label: '', description: '', verified: false, annotations: [] })
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
        check_date: form.value.check_date,
        items: form.value.items,
        conclusion: form.value.conclusion,
        signatures: { auditor: form.value.signature },
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
    await confirmLeave('B 类检查清单')
    visible.value = false
  } catch {
    /* user cancelled close */
  }
}

function onCloseAttempt() {
  // ESC 两步退出 — 默认 fullscreen + close-on-press-escape=false 已防止首次 ESC
  // 此处由用户手动点关闭按钮触发，走 confirmLeave 流程
  onCancel()
}

function onSigned(payload: any) {
  form.value.signature = payload
}
</script>

<style scoped>
.gt-bchk-form { padding: 4px 12px; }
.gt-bchk-conclusion-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.gt-bchk-conclusion-row :deep(.el-textarea) {
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
