<template>
  <el-dialog
    :model-value="modelValue"
    title="上传本行单据"
    width="600px"
    append-to-body
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <template v-if="step === 'pick'">
      <div class="gt-alt-doc__label">单据类型</div>
      <el-radio-group v-model="docType" class="gt-alt-doc__types" data-testid="alt-doc-types">
        <el-radio v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</el-radio>
        <el-radio value="upload_only">仅上传，不识别</el-radio>
      </el-radio-group>
      <div class="gt-alt-doc__hint">{{ typeHint }}</div>
      <div class="gt-alt-doc__file">
        <el-upload :auto-upload="false" :show-file-list="false" :accept="accept" :on-change="onFileChange">
          <el-button size="small">选择文件</el-button>
        </el-upload>
        <span class="gt-alt-doc__file-name">{{ file?.name || '未选择文件' }}</span>
      </div>
    </template>

    <template v-else>
      <div class="gt-alt-doc__doc">
        <span>单据：{{ file?.name }}</span>
        <AttachmentEyeButton v-if="attachmentId" :attachment-id="attachmentId" :file-name="file?.name" />
      </div>
      <el-alert
        v-if="!plan.length"
        type="info"
        :closable="false"
        show-icon
        title="未识别到本区块可填的内容；单据已挂到本行，可点小眼睛核对原件"
      />
      <template v-else>
        <div class="gt-alt-doc__advisory">识别结果仅供参考，请对照原件核对后再填入；本行已有值的列不会被覆盖</div>
        <table class="gt-alt-doc__plan" data-testid="alt-doc-plan">
          <thead><tr><th /><th>列</th><th>识别值</th><th>本行现值</th></tr></thead>
          <tbody>
            <tr v-for="item in plan" :key="item.field" :data-field="item.field">
              <td><el-checkbox v-model="checked[item.field]" :disabled="!item.fillable" /></td>
              <td>{{ item.label }}</td>
              <td>{{ item.value }}</td>
              <td :class="{ 'gt-alt-doc__kept': !item.fillable }">{{ item.fillable ? '（空）' : `${item.current}（已有值，不覆盖）` }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>

    <template #footer>
      <template v-if="step === 'pick'">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" :disabled="!file" :loading="busy" data-testid="alt-doc-submit" @click="submit">
          {{ docType === 'upload_only' ? '上传' : '上传并识别' }}
        </el-button>
      </template>
      <template v-else>
        <el-button @click="emit('update:modelValue', false)">关闭</el-button>
        <el-button v-if="plan.length" type="primary" :disabled="!checkedCount" data-testid="alt-doc-fill" @click="fill">
          填入勾选的 {{ checkedCount }} 项
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 替代程序行内单据：选类型 → 选文件 → 识别 → 逐项勾选 → 只填本行空白列（spec attachment-confirmation-evidence-loop 需求 3.2、3.3）
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
import { EVIDENCE_MAX_UPLOAD_BYTES } from '@/components/attachment/workpaperEvidence'
import { handleApiError } from '@/utils/errorHandler'
import {
  ALT_DOC_TYPES,
  applicableDocTypes,
  buildFillPlan,
  type AltColumn,
  type AltDocType,
  type FillItem,
} from './alternativeDocMapping'
import { recognizeAlternativeDoc, uploadAlternativeEvidence, type AltRowTarget } from './alternativeDocOcr'

const props = defineProps<{
  modelValue: boolean
  target: AltRowTarget
  columns: AltColumn[]
  row: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'fill', patch: Record<string, string | number>): void
}>()

type Choice = AltDocType | 'upload_only'

const typeOptions = computed(() => {
  const usable = new Set(applicableDocTypes(props.columns))
  return ALT_DOC_TYPES.filter((t) => usable.has(t.value))
})
const docType = ref<Choice>(typeOptions.value[0]?.value ?? 'upload_only')
const typeHint = computed(() =>
  docType.value === 'upload_only'
    ? '只把文件挂到本行作为证据（可上传 PDF、图片、Word、Excel）'
    : `可识别：${ALT_DOC_TYPES.find((t) => t.value === docType.value)?.hint ?? ''}`)
const accept = computed(() =>
  docType.value === 'upload_only' ? '.pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx' : '.pdf,.png,.jpg,.jpeg')

const step = ref<'pick' | 'review'>('pick')
const file = ref<File | null>(null)
const busy = ref(false)
const attachmentId = ref('')
const plan = ref<FillItem[]>([])
const checked = reactive<Record<string, boolean>>({})
const checkedCount = computed(() => plan.value.filter((i) => i.fillable && checked[i.field]).length)

/** 每次打开从选类型开始（弹窗组件在本行第一次打开后常驻，状态不能带到下一次） */
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    step.value = 'pick'
    file.value = null
    attachmentId.value = ''
    plan.value = []
    for (const key of Object.keys(checked)) delete checked[key]
    docType.value = typeOptions.value[0]?.value ?? 'upload_only'
  },
)

function onFileChange(uploadFile: { raw?: File } | File) {
  const raw = (uploadFile as { raw?: File }).raw ?? (uploadFile as File)
  if (!raw) return
  if (raw.size > EVIDENCE_MAX_UPLOAD_BYTES) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }
  file.value = raw
}

async function submit() {
  if (!file.value) return
  busy.value = true
  try {
    if (docType.value === 'upload_only') {
      await uploadAlternativeEvidence(props.target, file.value)
      ElMessage.success('已挂到本行')
      emit('update:modelValue', false)
      return
    }
    const result = await recognizeAlternativeDoc(props.target, file.value, docType.value)
    attachmentId.value = result.attachment_id
    plan.value = buildFillPlan(props.columns, props.row, docType.value, result.extracted_fields || {})
    for (const item of plan.value) checked[item.field] = item.fillable
    step.value = 'review'
  } catch (e) {
    handleApiError(e, docType.value === 'upload_only' ? '上传单据' : '识别单据')
  } finally {
    busy.value = false
  }
}

function fill() {
  const patch: Record<string, string | number> = {}
  for (const item of plan.value) {
    if (item.fillable && checked[item.field]) patch[item.field] = item.value
  }
  emit('fill', patch)
  ElMessage.success(`已填入 ${Object.keys(patch).length} 项`)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.gt-alt-doc__label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
  margin-bottom: 6px;
}
.gt-alt-doc__types {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 0;
}
.gt-alt-doc__hint {
  margin: 6px 0 12px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-alt-doc__file {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-alt-doc__file-name {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-alt-doc__doc {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 13px;
}
.gt-alt-doc__advisory {
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
  margin-bottom: 6px;
}
.gt-alt-doc__plan {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.gt-alt-doc__plan th,
.gt-alt-doc__plan td {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  padding: 4px 6px;
  text-align: left;
}
.gt-alt-doc__kept {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
