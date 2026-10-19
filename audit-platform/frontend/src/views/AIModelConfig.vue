<template>
  <div class="ai-model-config">
    <GtPageHeader title="AI 模型配置" :show-back="false">
      <template #actions>
        <el-button size="small" :loading="routesLoading" @click="refreshRoutes">
          <el-icon><Refresh /></el-icon>检测状态
        </el-button>
        <el-button size="small" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新增模型
        </el-button>
      </template>
    </GtPageHeader>

    <el-alert
      class="security-tip" type="info" :closable="false" show-icon
      title="已内置 qwen3.8、PaddleOCR-VL 1.6、PaddleOCR v6 三条企业预设；点击“录入 Key”即可，qwen3.8 的思考强度可在同一窗口选择（默认未指定）。Key 密文存储，服务端需先配置 ENCRYPTION_KEY。"
      description="调用按「本机 → 服务器」顺序：对话与 OCR 的本机、服务器模型各可启用一条，本机不可用时自动改用服务器模型；向量模型只启用一条，不跨模型兜底。"
    />

    <ModelRoutePanel :routes="routes" :loading="routesLoading" :checked-at="routesCheckedAt" />

    <el-tabs v-model="activeTab" class="ai-tabs">
      <el-tab-pane v-for="tab in tabs" :key="tab.name" :label="tab.label" :name="tab.name">
        <ModelTable
          :models="modelsByType[tab.name]" :loading="loading"
          :testing-id="testingId" :switching-id="switchingId" :provider-labels="providerLabels"
          @activate="onActivate" @deactivate="onDeactivate" @edit="onEdit" @delete="onDelete" @test="onTest"
        />
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="showDialog" append-to-body destroy-on-close width="560px"
      :title="editingModel?.preset_key ? '配置企业预设' : editingModel ? '编辑模型' : '新增模型'" @closed="resetDialog"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px">
        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="form.model_name" :disabled="!!editingModel?.preset_key" placeholder="如 deepseek-chat / qwen-plus" />
        </el-form-item>
        <el-form-item label="模型类型" prop="model_type">
          <el-select v-model="form.model_type" :disabled="!!editingModel" style="width:100%" @change="onModelTypeChange">
            <el-option label="对话模型" value="chat" /><el-option label="嵌入模型" value="embedding" />
            <el-option label="OCR 引擎" value="ocr" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商" prop="provider">
          <el-select v-model="form.provider" :disabled="!!editingModel?.preset_key" style="width:100%" @change="onProviderChange">
            <el-option v-for="item in availableProviders" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <div v-if="selectedProvider" class="form-help">{{ selectedProvider.description }}</div>
        </el-form-item>
        <template v-if="form.model_type === 'ocr'">
          <el-form-item label="部署方式">
            <el-select v-model="form.ocr_protocol" :disabled="!!editingModel?.preset_key" style="width:100%" @change="onOcrProtocolChange">
              <el-option label="本机 PaddleOCR" value="local" />
              <el-option label="远程 PaddleX JSON API" value="paddlex_json" />
            </el-select>
          </el-form-item>
          <el-form-item label="OCR 能力">
            <el-select v-model="form.ocr_capability" :disabled="!!editingModel?.preset_key" style="width:100%" @change="onOcrCapabilityChange">
              <el-option label="文字识别（/ocr）" value="ocr" />
              <el-option label="版面解析（/layout-parsing）" value="layout_parsing" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.ocr_protocol === 'paddlex_json'" label="接口路径">
            <el-input v-model="form.api_path" readonly />
          </el-form-item>
          <el-form-item v-if="form.ocr_protocol === 'paddlex_json'" label="认证方式">
            <el-select v-model="form.auth_scheme" :disabled="!!editingModel?.preset_key" style="width:100%">
              <el-option label="Authorization: Bearer" value="bearer" />
              <el-option label="X-API-Key" value="x_api_key" />
              <el-option label="api-key" value="api_key" />
              <el-option label="自定义 Header" value="custom_header" />
              <el-option label="无需认证" value="none" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.ocr_protocol === 'paddlex_json' && form.auth_scheme === 'custom_header'" label="Header 名称">
            <el-input v-model="form.auth_header_name" placeholder="如 X-Model-Token" />
          </el-form-item>
        </template>
        <el-form-item v-if="form.model_type !== 'ocr' || form.ocr_protocol === 'paddlex_json'" label="端点 URL" prop="endpoint_url">
          <el-input v-model="form.endpoint_url" :readonly="!!editingModel?.preset_key" placeholder="留空时使用供应商默认端点" />
        </el-form-item>
        <el-form-item v-if="form.model_type !== 'ocr' || form.ocr_protocol === 'paddlex_json'" label="API Key">
          <el-input v-model="form.api_key" type="password" show-password autocomplete="new-password"
            :placeholder="editingModel?.preset_key ? '请输入企业模型 API Key' : editingModel?.has_api_key ? '留空则保留现有 Key' : '本地无鉴权模型可留空'" />
          <div v-if="editingModel?.has_api_key" class="form-help">已配置加密凭证，服务端不会回显。</div>
        </el-form-item>
        <el-form-item v-if="editingModel?.has_api_key && (form.model_type !== 'ocr' || form.ocr_protocol === 'paddlex_json')" label="清除凭证">
          <el-checkbox v-model="form.clear_api_key">显式清除现有 API Key</el-checkbox>
        </el-form-item>
        <el-form-item v-if="form.model_type === 'chat'" label="思考强度">
          <!-- '' 是可选值「未指定」，不能被当成空值显示占位符 -->
          <el-select v-model="form.reasoning_effort" :empty-values="[null, undefined]" style="width:100%">
            <el-option :label="unsetReasoningLabel" value="" />
            <el-option v-for="item in reasoningOptions" :key="item" :label="REASONING_LABELS[item]" :value="item" />
          </el-select>
          <div class="form-help">{{ reasoningHelp }}</div>
        </el-form-item>
        <el-form-item v-if="form.model_type !== 'ocr'" label="上下文窗口"><el-input-number v-model="form.context_window" :disabled="!!editingModel?.preset_key" :min="1" :step="1024" style="width:100%" /></el-form-item>
        <el-form-item v-else-if="form.ocr_protocol === 'paddlex_json'" label="请求超时（秒）"><el-input-number v-model="form.request_timeout_seconds" :disabled="!!editingModel?.preset_key" :min="1" :max="600" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.performance_notes" :disabled="!!editingModel?.preset_key" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showDialog=false">取消</el-button><el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import ModelRoutePanel from '@/components/ai/ModelRoutePanel.vue'
import ModelTable from '@/components/ai/ModelTable.vue'
import { deactivateConsequence } from '@/components/ai/modelRouteView'
import { confirmDelete } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'
import { isRequestCancelled } from '@/utils/http'
import type {
  AIAuthScheme, AIModel, AIModelCreate, AIModelType, AIProvider,
  AIProviderOption, AIRoute, OCRCapability, OCRProtocol, ReasoningEffort,
} from '@/services/aiModelApi'
import {
  activateAIModel, createAIModel, deactivateAIModel, deleteAIModel, getAIModels,
  getAIProviders, getAIRoutes, testAIModel, updateAIModel,
} from '@/services/aiModelApi'

interface ModelForm {
  model_name: string
  model_type: AIModelType
  provider: AIProvider
  endpoint_url: string
  api_key: string
  clear_api_key: boolean
  reasoning_effort: ReasoningEffort | ''
  ocr_capability: OCRCapability
  ocr_protocol: OCRProtocol
  api_path: string
  auth_scheme: AIAuthScheme
  auth_header_name: string
  request_timeout_seconds: number
  context_window: number
  performance_notes: string
}

const tabs: Array<{ name: AIModelType; label: string }> = [
  { name: 'chat', label: '对话模型' }, { name: 'embedding', label: '嵌入模型' }, { name: 'ocr', label: 'OCR 引擎' },
]
const loading = ref(false)
const routesLoading = ref(false)
const submitting = ref(false)
const testingId = ref('')
const switchingId = ref('')
const models = ref<AIModel[]>([])
const providers = ref<AIProviderOption[]>([])
const routes = ref<AIRoute[]>([])
const routesCheckedAt = ref<string | null>(null)
const activeTab = ref<AIModelType>('chat')
const showDialog = ref(false)
const editingModel = ref<AIModel | null>(null)
const formRef = ref()

function emptyForm(): ModelForm {
  return {
    model_name: '', model_type: 'chat', provider: 'openai_compatible', endpoint_url: '', api_key: '',
    clear_api_key: false, reasoning_effort: '', ocr_capability: 'ocr', ocr_protocol: 'local',
    api_path: '/ocr', auth_scheme: 'bearer', auth_header_name: '', request_timeout_seconds: 60,
    context_window: 8192, performance_notes: '',
  }
}
const form = ref<ModelForm>(emptyForm())
const modelsByType = computed<Record<AIModelType, AIModel[]>>(() => ({
  chat: models.value.filter(item => item.model_type === 'chat'),
  embedding: models.value.filter(item => item.model_type === 'embedding'),
  ocr: models.value.filter(item => item.model_type === 'ocr'),
}))
const availableProviders = computed(() => providers.value.filter(item => item.supported_types.includes(form.value.model_type)))
const selectedProvider = computed(() => providers.value.find(item => item.value === form.value.provider) || null)
const providerLabels = computed<Partial<Record<AIProvider, string>>>(() =>
  Object.fromEntries(providers.value.map(item => [item.value, item.label])) as Partial<Record<AIProvider, string>>,
)
const REASONING_LABELS: Record<ReasoningEffort, string> = {
  low: '低（low）', medium: '中（medium）', high: '高（high）', xhigh: '极高（xhigh）',
}
const ALL_REASONING: ReasoningEffort[] = ['low', 'medium', 'high', 'xhigh']
// 企业预设登记了服务端实际支持的取值（如 qwen3.8 网关只接受 low/medium/xhigh），只展示这些。
const reasoningOptions = computed<ReasoningEffort[]>(() =>
  editingModel.value?.reasoning_effort_options?.length ? editingModel.value.reasoning_effort_options : ALL_REASONING,
)
const unsetReasoningLabel = computed(() => {
  const fallback = editingModel.value?.reasoning_effort_server_default
  return fallback ? `未指定（服务端默认 ${fallback}）` : '未指定（不发送 reasoning_effort）'
})
const reasoningHelp = computed(() =>
  editingModel.value?.reasoning_effort_options?.length
    ? `该模型支持：${editingModel.value.reasoning_effort_options.map(item => REASONING_LABELS[item]).join(' / ')}；强度越高越慢、消耗越多。`
    : '未指定时由模型服务端决定；若测试连接提示参数被拒绝，请改回「未指定」。',
)
const formRules = {
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  model_type: [{ required: true, message: '请选择模型类型', trigger: 'change' }],
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
}

async function fetchModels() {
  loading.value = true
  try {
    models.value = await getAIModels()
  } catch (error) {
    handleApiError(error, '加载模型列表')
    models.value = []
  } finally { loading.value = false }
}
async function fetchProviders() {
  try {
    providers.value = await getAIProviders()
  } catch (error) {
    handleApiError(error, '加载模型供应商')
    providers.value = []
  }
}
// refresh=false 复用 30~60 秒内的检测结果（未检测过的候选仍会探测）；「检测状态」强制重探。
async function fetchRoutes(refresh = false) {
  routesLoading.value = true
  try {
    const status = await getAIRoutes(refresh)
    routes.value = status?.routes ?? []
    routesCheckedAt.value = status?.checked_at ?? null
  } catch (error) {
    if (isRequestCancelled(error)) return
    handleApiError(error, '检测调用路由')
  } finally { routesLoading.value = false }
}
function refreshRoutes() { return fetchRoutes(true) }
function openCreate() {
  editingModel.value = null
  form.value = emptyForm()
  const profile = providers.value.find(item => item.value === form.value.provider)
  form.value.endpoint_url = profile?.default_endpoint || ''
  showDialog.value = true
}
function resetDialog() { editingModel.value = null; form.value = emptyForm(); formRef.value?.clearValidate?.() }
function onProviderChange(value: AIProvider) {
  const profile = providers.value.find(item => item.value === value)
  form.value.endpoint_url = profile?.default_endpoint || ''
  form.value.api_key = ''
  form.value.clear_api_key = false
}
function onModelTypeChange(value: AIModelType) {
  const first = providers.value.find(item => item.supported_types.includes(value))
  if (first) {
    form.value.provider = first.value
    form.value.endpoint_url = first.default_endpoint || ''
  }
  if (value === 'ocr') {
    form.value.ocr_protocol = 'local'
    form.value.ocr_capability = 'ocr'
    form.value.api_path = '/ocr'
    form.value.auth_scheme = 'bearer'
  }
}
function onOcrProtocolChange(value: OCRProtocol) {
  if (value === 'local') {
    form.value.endpoint_url = ''
    form.value.api_key = ''
  }
}
function onOcrCapabilityChange(value: OCRCapability) {
  form.value.api_path = value === 'layout_parsing' ? '/layout-parsing' : '/ocr'
  form.value.request_timeout_seconds = value === 'layout_parsing' ? 120 : 60
}
function onEdit(model: AIModel) {
  editingModel.value = model
  form.value = {
    model_name: model.model_name, model_type: model.model_type, provider: model.provider,
    endpoint_url: model.endpoint_url || '', api_key: '', clear_api_key: false,
    reasoning_effort: model.reasoning_effort || '',
    ocr_capability: model.ocr_capability || 'ocr',
    ocr_protocol: model.ocr_protocol || 'local',
    api_path: model.api_path || (model.ocr_capability === 'layout_parsing' ? '/layout-parsing' : '/ocr'),
    auth_scheme: model.auth_scheme || 'bearer', auth_header_name: model.auth_header_name || '',
    request_timeout_seconds: model.request_timeout_seconds || (model.ocr_capability === 'layout_parsing' ? 120 : 60),
    context_window: model.context_window || 8192, performance_notes: model.performance_notes || '',
  }
  showDialog.value = true
}
// 验证失败原因可能较长（含代理/内网 DNS 排查提示），3 秒的 ElMessage 来不及读完。
function notifyModelFailure(title: string, message: string) {
  ElNotification({ title, message, type: 'error', duration: 15000 })
}
// 后端验证失败返回 400 + {error_code, message}；其余状态仍走统一错误处理。
function validationFailureMessage(error: any): string {
  if (error?.response?.status !== 400) return ''
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail.trim()
  return typeof detail?.message === 'string' ? detail.message.trim() : ''
}
async function onTest(model: AIModel) {
  testingId.value = model.id
  try {
    const result = await testAIModel(model.id)
    if (result.status === 'ok') ElMessage.success(result.message)
    else notifyModelFailure('连接测试失败', result.message)
  } catch (error) {
    handleApiError(error, '测试模型连接')
  } finally { testingId.value = '' }
}
// 本机模型当前不可用但已启用 / 已保存：提示是否有服务器兜底（后端按实际启用情况给出）。
function notifyLocalUnavailable(title: string, warning: string) {
  ElNotification({ title, message: warning, type: 'warning', duration: 15000 })
}
async function onActivate(model: AIModel) {
  switchingId.value = model.id
  try {
    const result = await activateAIModel(model.id)
    if (result?.warning) notifyLocalUnavailable(`已启用：${model.model_name}`, result.warning)
    else ElMessage.success(`已启用：${model.model_name}`)
    await Promise.all([fetchModels(), fetchRoutes()])
  } catch (error) {
    const message = validationFailureMessage(error)
    if (message) notifyModelFailure('启用失败', message)
    else handleApiError(error, '启用模型')
  } finally { switchingId.value = '' }
}
async function onDeactivate(model: AIModel) {
  try {
    await ElMessageBox.confirm(
      deactivateConsequence(model, models.value), `停用「${model.model_name}」`,
      { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
    )
  } catch { return }
  switchingId.value = model.id
  try {
    await deactivateAIModel(model.id)
    ElMessage.success(`已停用：${model.model_name}`)
    await Promise.all([fetchModels(), fetchRoutes()])
  } catch (error) {
    handleApiError(error, '停用模型')
  } finally { switchingId.value = '' }
}
async function onDelete(model: AIModel) {
  try {
    await confirmDelete(`模型「${model.model_name}」`)
    await deleteAIModel(model.id)
    ElMessage.success('已移入回收状态')
    await fetchModels()
  } catch (error: any) {
    if (error === 'cancel' || error?.message === 'cancel') return
    handleApiError(error, '删除模型')
  }
}
async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.value.clear_api_key && form.value.api_key.trim()) {
    ElMessage.warning('不能同时替换并清除 API Key'); return
  }
  const reasoningChanged = !!editingModel.value && form.value.model_type === 'chat'
    && (editingModel.value.reasoning_effort || '') !== form.value.reasoning_effort
  if (editingModel.value?.preset_key && !editingModel.value.has_api_key && !form.value.api_key.trim() && !reasoningChanged) {
    ElMessage.warning('企业预设只需录入 API Key，请先填写 Key'); return
  }
  const destinationChanged = !!editingModel.value && (
    editingModel.value.provider !== form.value.provider
    || (editingModel.value.endpoint_url || '') !== form.value.endpoint_url.trim()
    || (editingModel.value.ocr_protocol || 'local') !== form.value.ocr_protocol
    || (editingModel.value.ocr_capability || 'ocr') !== form.value.ocr_capability
    || (editingModel.value.api_path || '') !== (form.value.ocr_protocol === 'paddlex_json' ? form.value.api_path : '')
    || (editingModel.value.auth_scheme || 'none') !== (form.value.ocr_protocol === 'paddlex_json' ? form.value.auth_scheme : 'none')
  )
  if (editingModel.value?.has_api_key && destinationChanged && !form.value.api_key.trim() && !form.value.clear_api_key) {
    ElMessage.warning('修改供应商或端点时，请重新输入 API Key 或显式清除旧凭证'); return
  }
  const remoteOcrNeedsKey = form.value.model_type === 'ocr'
    && form.value.ocr_protocol === 'paddlex_json'
    && form.value.auth_scheme !== 'none'
  if (remoteOcrNeedsKey && !editingModel.value?.has_api_key && !form.value.api_key.trim()) {
    ElMessage.warning('所选远程 OCR 认证方式必须配置 API Key'); return
  }
  if (form.value.auth_scheme === 'custom_header' && !form.value.auth_header_name.trim()) {
    ElMessage.warning('请填写自定义认证 Header 名称'); return
  }
  if (selectedProvider.value?.requires_api_key && !editingModel.value?.has_api_key && !form.value.api_key.trim()) {
    ElMessage.warning('该供应商必须配置 API Key'); return
  }
  const endpointRequired = form.value.model_type !== 'ocr' || form.value.ocr_protocol === 'paddlex_json'
  if (endpointRequired && !form.value.endpoint_url.trim() && !selectedProvider.value?.default_endpoint) {
    ElMessage.warning('请填写模型端点 URL'); return
  }
  submitting.value = true
  try {
    if (editingModel.value) {
      const payload: Parameters<typeof updateAIModel>[1] = editingModel.value.preset_key
        ? { clear_api_key: form.value.clear_api_key }
        : {
            model_name: form.value.model_name, provider: form.value.provider,
            endpoint_url: endpointRequired ? (form.value.endpoint_url || null) : null,
            context_window: form.value.model_type === 'ocr' ? null : form.value.context_window,
            performance_notes: form.value.performance_notes || null,
            clear_api_key: form.value.clear_api_key,
          }
      // 企业预设只在用户改了思考强度时才提交该字段（后端对预设只放行 Key 与思考强度）。
      if (form.value.model_type === 'chat' && (!editingModel.value.preset_key || reasoningChanged)) {
        payload.reasoning_effort = form.value.reasoning_effort || null
      }
      if (!editingModel.value.preset_key && form.value.model_type === 'ocr') {
        payload.ocr_capability = form.value.ocr_capability
        payload.ocr_protocol = form.value.ocr_protocol
        payload.api_path = form.value.ocr_protocol === 'paddlex_json' ? form.value.api_path : null
        payload.auth_scheme = form.value.ocr_protocol === 'paddlex_json' ? form.value.auth_scheme : 'none'
        payload.auth_header_name = form.value.auth_scheme === 'custom_header' ? form.value.auth_header_name : null
        payload.request_timeout_seconds = form.value.request_timeout_seconds
      }
      if (form.value.api_key.trim()) payload.api_key = form.value.api_key.trim()
      const saved = await updateAIModel(editingModel.value.id, payload)
      const savedText = !editingModel.value.preset_key ? '模型配置已更新'
        : form.value.api_key.trim() ? 'API Key 已安全保存' : '企业预设已更新'
      if (saved?.warning) notifyLocalUnavailable(savedText, saved.warning)
      else ElMessage.success(savedText)
    } else {
      const payload: AIModelCreate = {
        model_name: form.value.model_name, model_type: form.value.model_type, provider: form.value.provider,
        endpoint_url: endpointRequired ? (form.value.endpoint_url || null) : null,
        context_window: form.value.model_type === 'ocr' ? null : form.value.context_window,
        performance_notes: form.value.performance_notes || null,
      }
      if (form.value.model_type === 'chat') payload.reasoning_effort = form.value.reasoning_effort || null
      if (form.value.model_type === 'ocr') {
        payload.ocr_capability = form.value.ocr_capability
        payload.ocr_protocol = form.value.ocr_protocol
        payload.api_path = form.value.ocr_protocol === 'paddlex_json' ? form.value.api_path : null
        payload.auth_scheme = form.value.ocr_protocol === 'paddlex_json' ? form.value.auth_scheme : 'none'
        payload.auth_header_name = form.value.auth_scheme === 'custom_header' ? form.value.auth_header_name : null
        payload.request_timeout_seconds = form.value.request_timeout_seconds
      }
      if (form.value.api_key.trim()) payload.api_key = form.value.api_key.trim()
      await createAIModel(payload)
      ElMessage.success('模型配置已创建，请先测试连接再启用')
    }
    const wasActive = !!editingModel.value?.is_active
    showDialog.value = false
    await Promise.all([fetchModels(), wasActive ? fetchRoutes() : Promise.resolve()])
  } catch (error) {
    const message = validationFailureMessage(error)
    if (message) notifyModelFailure('保存失败', message)
    else handleApiError(error, '保存模型配置')
  } finally { submitting.value = false }
}

onMounted(async () => {
  await fetchProviders()
  await Promise.all([fetchModels(), fetchRoutes()])
})
</script>

<style scoped>
.ai-model-config { padding: var(--gt-space-4); height: 100%; overflow-y: auto; }
.security-tip { margin-bottom: var(--gt-space-4); }
.ai-tabs { margin-top: var(--gt-space-2); }
.form-help { margin-top: 4px; color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); line-height: 1.4; }
</style>
