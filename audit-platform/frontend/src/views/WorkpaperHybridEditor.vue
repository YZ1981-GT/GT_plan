<template>
  <div class="gt-hybrid-editor gt-fade-in">
    <EditorSharedToolbar
      :wp-code="wpDetail?.wp_code"
      :wp-name="wpDetail?.wp_name"
      :status="wpDetail?.status"
      component-type="hybrid"
      :dirty="dirty"
      :saving="saving"
      @back="goBack"
      @save="onSave"
      @export="onExport"
      @versions="$emit('show-versions')"
      @toggle-panel="$emit('toggle-panel')"
    />

    <div class="gt-hybrid-editor-body" v-loading="loading">
      <!-- 第一段：表单区 -->
      <section class="gt-hybrid-section">
        <h4 class="gt-hybrid-section-title">📝 基本信息</h4>
        <el-form :model="formData" label-width="140px" label-position="top" class="gt-hybrid-form">
          <el-form-item v-for="f in formFields" :key="f.key" :label="f.label">
            <el-input v-model="formData[f.key]" :placeholder="f.placeholder" @change="markDirty" />
          </el-form-item>
        </el-form>
      </section>

      <el-divider />

      <!-- 第二段：表格区 -->
      <section class="gt-hybrid-section">
        <div class="gt-hybrid-section-header">
          <h4 class="gt-hybrid-section-title">📊 明细数据</h4>
          <el-button size="small" type="primary" @click="onAddRow">+ 新增</el-button>
        </div>
        <el-table :data="tableRows" border stripe style="width: 100%" max-height="360px">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column
            v-for="col in tableColumns"
            :key="col.key"
            :prop="col.key"
            :label="col.label"
            :min-width="col.minWidth || 120"
          >
            <template #default="{ row }">
              <el-input v-model="row[col.key]" size="small" @change="markDirty" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" fixed="right">
            <template #default="{ $index }">
              <el-button size="small" text type="danger" @click="tableRows.splice($index, 1); markDirty()">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <el-divider />

      <!-- 第三段：附件区 -->
      <section class="gt-hybrid-section">
        <h4 class="gt-hybrid-section-title">📎 附件</h4>
        <div v-if="attachments.length" class="gt-hybrid-attachments">
          <div v-for="(att, i) in attachments" :key="i" class="gt-hybrid-attachment-item">
            <span>{{ att.name }}</span>
            <el-button size="small" text type="danger" @click="attachments.splice(i, 1); markDirty()">移除</el-button>
          </div>
        </div>
        <el-empty v-else description="暂无附件" :image-size="60" />
        <el-button size="small" style="margin-top: 8px" @click="onUploadAttachment">📤 上传附件</el-button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import EditorSharedToolbar from '@/components/workpaper/EditorSharedToolbar.vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import type { WorkpaperDetail } from '@/services/workpaperApi'

interface FormField { key: string; label: string; placeholder?: string }
interface TableColumn { key: string; label: string; minWidth?: number }
interface Attachment { name: string; url?: string; id?: string }

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
}>()

const emit = defineEmits<{
  'show-versions': []
  'toggle-panel': []
  saved: []
}>()

const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const formFields = ref<FormField[]>([])
const formData = reactive<Record<string, any>>({})
const tableColumns = ref<TableColumn[]>([])
const tableRows = ref<Record<string, any>[]>([])
const attachments = ref<Attachment[]>([])

function markDirty() { dirty.value = true }
function goBack() { window.history.back() }

function onAddRow() {
  const row: Record<string, any> = {}
  for (const col of tableColumns.value) row[col.key] = ''
  tableRows.value.push(row)
  markDirty()
}

function onUploadAttachment() {
  ElMessage.info('附件上传功能开发中')
}

async function loadData() {
  loading.value = true
  try {
    const detail = await httpApi.get(P_wp.detail(props.projectId, props.wpId))
    const parsed = detail?.parsed_data || {}
    // Form section
    formFields.value = parsed._formFields || [
      { key: 'subject', label: '主题' },
      { key: 'date', label: '日期' },
      { key: 'conclusion', label: '结论' },
    ]
    for (const f of formFields.value) formData[f.key] = parsed[f.key] ?? ''
    // Table section
    tableColumns.value = parsed._tableColumns || [
      { key: 'item', label: '项目' },
      { key: 'result', label: '结果' },
      { key: 'remark', label: '备注' },
    ]
    tableRows.value = parsed._tableRows || []
    // Attachments
    attachments.value = parsed._attachments || []
  } catch (e: any) {
    handleApiError(e, '加载混合视图')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload: Record<string, any> = {
      ...formData,
      _formFields: formFields.value,
      _tableColumns: tableColumns.value,
      _tableRows: tableRows.value,
      _attachments: attachments.value,
    }
    await httpApi.put(P_wp.detail(props.projectId, props.wpId), {
      parsed_data: payload,
    })
    dirty.value = false
    ElMessage.success('保存成功')
    emit('saved')
  } catch (e: any) {
    handleApiError(e, '保存')
  } finally {
    saving.value = false
  }
}

function onExport() {
  ElMessage.info('导出功能开发中')
}

watch(() => props.wpId, () => { if (props.wpId) loadData() })
onMounted(() => { if (props.wpId) loadData() })
</script>

<style scoped>
.gt-hybrid-editor { display: flex; flex-direction: column; height: 100%; }
.gt-hybrid-editor-body { flex: 1; overflow-y: auto; padding: 20px 28px; }
.gt-hybrid-section { margin-bottom: 8px; }
.gt-hybrid-section-title { margin-bottom: 12px; color: var(--gt-color-text, #333); font-size: 15px; }
.gt-hybrid-section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-hybrid-form { max-width: 700px; }
.gt-hybrid-attachments { display: flex; flex-direction: column; gap: 6px; }
.gt-hybrid-attachment-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; background: var(--gt-color-bg, #f8f7fc); border-radius: 4px;
}
</style>
