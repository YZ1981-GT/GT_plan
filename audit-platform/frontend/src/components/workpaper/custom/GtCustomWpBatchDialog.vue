<!--
  GtCustomWpBatchDialog.vue — 批量创建自定义底稿

  spec: custom-workpaper-dual-mode-formula-and-batch Wave 6 Task 21

  两个入口（用户 2026-08-06 拍板「两种都要」）：
    「粘贴清单」textarea / 「上传 Excel」el-upload + SheetJS

  🔴 必须先预览再创建（R8.2）：预览走后端只读端点，因为**库内重号只有后端能判**。
  🔴 有错误行时「确认创建」前置为 disabled + tooltip 说明原因 ——
     不能点了才提示（平台既有铁律：门控类提示必须前置）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="批量创建自定义底稿"
    width="860px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="onClosed"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="粘贴清单" name="paste">
        <div class="gt-cwb__hint">
          每行一条，按 <b>Tab / 逗号 / 连续空格</b> 分列：<code>编号　名称　[审计循环]</code><br />
          可直接从 Excel 复制粘贴；首行若是表头会自动跳过；空行忽略。
        </div>
        <el-input
          v-model="pasteText"
          type="textarea"
          :autosize="{ minRows: 8, maxRows: 16 }"
          placeholder="X1&#9;自定义抽样底稿&#9;X&#10;X2&#9;自定义分析底稿"
          @input="onInputChanged"
        />
      </el-tab-pane>

      <el-tab-pane label="上传 Excel" name="excel">
        <div class="gt-cwb__hint">
          支持 .xlsx / .xls。表头含「编号」「名称」时<b>按列名映射</b>，否则按前三列位置读取。
        </div>
        <el-upload
          class="gt-cwb__upload"
          drag
          action="#"
          :auto-upload="false"
          :show-file-list="true"
          :limit="1"
          accept=".xlsx,.xls"
          :on-change="onExcelChange"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">把 Excel 拖到此处，或<em>点击选择文件</em></div>
        </el-upload>
        <div v-if="excelError" class="gt-cwb__err">{{ excelError }}</div>
      </el-tab-pane>
    </el-tabs>

    <div class="gt-cwb__actions">
      <el-button
        type="primary"
        size="small"
        :loading="previewing"
        :disabled="parsedItems.length === 0"
        @click="doPreview"
      >
        解析并预览（{{ parsedItems.length }} 条）
      </el-button>
      <span v-if="localErrors.length" class="gt-cwb__err">
        本地校验有 {{ localErrors.length }} 行格式错误，预览会一并标出
      </span>
    </div>

    <!-- 预览表格：逐行三态 -->
    <template v-if="previewRows.length">
      <div class="gt-cwb__summary">
        <el-tag type="success" size="small">可创建 {{ summary.ok }}</el-tag>
        <el-tag type="warning" size="small">已存在将跳过 {{ summary.duplicate_db }}</el-tag>
        <el-tag type="warning" size="small">清单内重复 {{ summary.duplicate_input }}</el-tag>
        <el-tag type="danger" size="small">错误 {{ summary.invalid }}</el-tag>
      </div>
      <el-table :data="previewRows" size="small" max-height="280" style="width: 100%">
        <el-table-column prop="wp_code" label="编号" width="130" />
        <el-table-column prop="wp_name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="audit_cycle" label="循环" width="70" />
        <el-table-column label="结论" width="150">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </template>

    <!-- 创建结果摘要 -->
    <template v-if="result">
      <el-divider />
      <div class="gt-cwb__summary">
        <el-tag type="success" size="small">成功 {{ result.created }}</el-tag>
        <el-tag type="warning" size="small">跳过 {{ result.skipped }}</el-tag>
        <el-tag type="danger" size="small">失败 {{ result.failed }}</el-tag>
      </div>
      <el-table
        v-if="failedItems.length"
        :data="failedItems"
        size="small"
        max-height="180"
        style="width: 100%"
      >
        <el-table-column prop="wp_code" label="编号" width="130" />
        <el-table-column prop="reason" label="失败原因" min-width="260" show-overflow-tooltip />
      </el-table>
    </template>

    <template #footer>
      <el-button size="small" @click="emit('update:modelValue', false)">关闭</el-button>
      <!-- 🔴 门控前置 disabled + tooltip 说明原因（禁「点了才提示」）-->
      <el-tooltip :content="blockedReason" :disabled="!blockedReason" placement="top">
        <span>
          <el-button
            type="primary"
            size="small"
            :loading="creating"
            :disabled="!canSubmit || creating"
            @click="doCreate"
          >
            确认创建
          </el-button>
        </span>
      </el-tooltip>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { readWorkbookAoa } from '@/composables/useExcelIO'
import { UploadFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import {
  canSubmitPreview,
  parseExcelRows,
  parseTextList,
  submitBlockedReason,
  validateItems,
  type ParsedItem,
  type PreviewRow,
  type PreviewStatus,
} from './customWpBatchParse'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  created: [payload: { created: number; skipped: number; failed: number }]
}>()

const activeTab = ref<'paste' | 'excel'>('paste')
const pasteText = ref('')
const excelItems = ref<ParsedItem[]>([])
const excelError = ref('')
const previewing = ref(false)
const creating = ref(false)
const previewRows = ref<PreviewRow[]>([])
const result = ref<{ created: number; skipped: number; failed: number } | null>(null)
const failedItems = ref<Array<{ wp_code: string; reason: string }>>([])

const parsedItems = computed<ParsedItem[]>(() =>
  activeTab.value === 'paste' ? parseTextList(pasteText.value) : excelItems.value
)

/** 本地校验（格式 + 清单内重号）；库内重号由后端 preview 判 */
const localErrors = computed(() => validateItems(parsedItems.value).errors)

const summary = computed(() => ({
  ok: previewRows.value.filter((r) => r.status === 'ok').length,
  duplicate_db: previewRows.value.filter((r) => r.status === 'duplicate_db').length,
  duplicate_input: previewRows.value.filter((r) => r.status === 'duplicate_input').length,
  invalid: previewRows.value.filter((r) => r.status === 'invalid').length,
}))

const canSubmit = computed(() => canSubmitPreview(previewRows.value))
const blockedReason = computed(() =>
  canSubmit.value ? '' : submitBlockedReason(previewRows.value)
)

function statusLabel(s: PreviewStatus): string {
  return (
    {
      ok: '可创建',
      duplicate_db: '已存在，将跳过',
      duplicate_input: '清单内重复',
      invalid: '错误',
    } as Record<PreviewStatus, string>
  )[s] ?? s
}
function statusTagType(s: PreviewStatus): string {
  return (
    { ok: 'success', duplicate_db: 'warning', duplicate_input: 'warning', invalid: 'danger' } as Record<
      PreviewStatus,
      string
    >
  )[s] ?? 'info'
}

/** 输入变化 → 作废上一次预览（否则用户改了清单却仍按旧预览创建） */
function onInputChanged() {
  previewRows.value = []
  result.value = null
}

async function onExcelChange(file: { raw?: File }) {
  excelError.value = ''
  onInputChanged()
  const raw = file?.raw
  if (!raw) return
  try {
    // 走 useExcelIO 单一入口（B7 批）。原先取第一个 sheet + sheet_to_json(header:1,
    // blankrows:false)。用 readWorkbookAoa 是为了保留「没有任何工作表」这个明确错误
    // —— readSheetAoa 在无 sheet 时不会给出可区分的信号。
    const { sheetNames, sheets } = await readWorkbookAoa(raw, { blankrows: false })
    const first = sheetNames[0]
    if (!first) {
      excelError.value = '该 Excel 没有任何工作表'
      return
    }
    const aoa = sheets[first]
    const rows = aoa as unknown[][]
    excelItems.value = parseExcelRows(rows)
    if (excelItems.value.length === 0) {
      excelError.value = '未从该 Excel 解析出任何清单行（请检查是否有「编号」「名称」两列）'
    }
  } catch (e) {
    // 🔴 解析失败必须可见（禁静默 catch）
    excelError.value = `解析 Excel 失败：${(e as Error)?.message || e}`
  }
}

async function doPreview() {
  previewing.value = true
  result.value = null
  try {
    const res = (await api.post(
      `/api/projects/${props.projectId}/working-papers/create-custom-batch/preview`,
      { items: parsedItems.value.map(toPayloadItem) }
    )) as { results?: PreviewRow[] }
    previewRows.value = Array.isArray(res?.results) ? res.results : []
    if (previewRows.value.length === 0) ElMessage.warning('预览结果为空，请检查清单内容')
  } catch (e) {
    handleApiError(e, '预览失败')
    previewRows.value = []
  } finally {
    previewing.value = false
  }
}

function toPayloadItem(it: ParsedItem) {
  return { wp_code: it.wp_code, wp_name: it.wp_name, audit_cycle: it.audit_cycle }
}

async function doCreate() {
  creating.value = true
  try {
    // 只提交预览判为可创建的行（已存在的由后端再次跳过，双重保险）
    const okCodes = new Set(
      previewRows.value.filter((r) => r.status === 'ok').map((r) => r.wp_code)
    )
    const items = parsedItems.value
      .filter((it) => okCodes.has(it.wp_code))
      .map(toPayloadItem)

    const res = (await api.post(
      `/api/projects/${props.projectId}/working-papers/create-custom-batch`,
      { items, year: props.year ?? new Date().getFullYear() }
    )) as {
      created?: number
      skipped?: number
      failed?: number
      failed_items?: Array<{ wp_code: string; reason: string }>
    }
    result.value = {
      created: res?.created ?? 0,
      skipped: res?.skipped ?? 0,
      failed: res?.failed ?? 0,
    }
    failedItems.value = Array.isArray(res?.failed_items) ? res.failed_items : []
    if (result.value.failed > 0) {
      ElMessage.warning(
        `已创建 ${result.value.created} 个，${result.value.failed} 个失败（见下方明细）`
      )
    } else {
      ElMessage.success(
        `已创建 ${result.value.created} 个，跳过 ${result.value.skipped} 个`
      )
    }
    emit('created', result.value)
    // 创建后作废预览，避免重复提交同一批
    previewRows.value = []
  } catch (e) {
    handleApiError(e, '批量创建失败')
  } finally {
    creating.value = false
  }
}

function onClosed() {
  pasteText.value = ''
  excelItems.value = []
  excelError.value = ''
  previewRows.value = []
  result.value = null
  failedItems.value = []
}
</script>

<style scoped>
.gt-cwb__hint {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  line-height: 1.7;
  margin-bottom: 8px;
}
.gt-cwb__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
}
.gt-cwb__summary {
  display: flex;
  gap: 8px;
  margin: 8px 0;
}
.gt-cwb__err {
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
}
.gt-cwb__upload {
  width: 100%;
}
</style>
