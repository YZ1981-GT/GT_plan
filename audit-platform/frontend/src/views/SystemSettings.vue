<template>
  <div class="gt-settings">
    <div class="gt-settings-header">
      <h2>系统设置</h2>
      <div class="gt-settings-actions">
        <el-switch
          v-model="expertMode"
          active-text="专家模式"
          inactive-text="简洁模式"
          size="small"
          style="margin-right: 12px"
        />
        <el-button size="small" @click="checkHealth" :loading="healthLoading">
          <el-icon><Monitor /></el-icon> 服务检测
        </el-button>
        <el-button size="small" type="primary" @click="loadSettings" :loading="loading">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <!-- 服务健康状态 -->
    <div v-if="healthResults" class="gt-health-bar">
      <span
        v-for="(info, name) in healthResults"
        :key="name"
        class="gt-health-item"
        :class="info.status === 'ok' ? 'gt-health-ok' : 'gt-health-err'"
        :title="info.error || info.url || ''"
      >
        <span class="gt-health-dot" />
        {{ name }}
      </span>
    </div>

    <!-- JWT 安全警告 -->
    <el-alert
      v-if="!jwtSecure && expertMode"
      title="JWT 密钥不安全"
      description="当前使用默认弱密钥，生产环境请在 .env 中设置至少 16 字符的强随机密钥"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    />

    <!-- 双栏主体：左侧配置 + 右侧说明 -->
    <div v-if="!loading" class="gt-settings-body">
      <!-- 左侧：配置列表 -->
      <div class="gt-settings-left">
        <el-collapse v-model="expandedGroups">
          <el-collapse-item
            v-for="(items, groupKey) in filteredGroups"
            :key="groupKey"
            :name="groupKey"
          >
            <template #title>
              <span>{{ groupLabels[groupKey] || groupKey }}</span>
              <span v-if="!expertMode" class="gt-group-count">{{ Object.keys(items).length }} 项</span>
            </template>
            <div class="gt-settings-table">
              <div
                v-for="(value, key) in items"
                :key="key"
                class="gt-settings-row"
                :class="{ 'gt-settings-row--active': selectedKey === key }"
                @click="selectKey(String(key))"
              >
                <div class="gt-settings-key">
                  <span class="gt-key-name">{{ friendlyName(String(key)) }}</span>
                  <span v-if="expertMode" class="gt-key-code">{{ key }}</span>
                  <el-tag v-if="editableKeys.includes(String(key))" size="small" type="success" class="gt-editable-tag">可编辑</el-tag>
                </div>
                <div class="gt-settings-value">
                  <template v-if="editingKey === key">
                    <el-input
                      v-if="typeof value === 'string' || typeof value === 'number'"
                      v-model="editingValue"
                      size="small"
                      style="width: 240px"
                      @keyup.enter="saveEdit(String(key))"
                      @keyup.escape="cancelEdit"
                    />
                    <el-switch v-else-if="typeof value === 'boolean'" v-model="editingValue" size="small" />
                    <el-button size="small" type="primary" @click="saveEdit(String(key))" :loading="saving">保存</el-button>
                    <el-button size="small" @click="cancelEdit">取消</el-button>
                  </template>
                  <template v-else>
                    <span class="gt-value-text" :class="{ 'gt-value-masked': String(value).includes('***') }">
                      {{ formatValue(value) }}
                    </span>
                    <el-button
                      v-if="editableKeys.includes(String(key))"
                      size="small"
                      @click.stop="startEdit(String(key), value)"
                      class="gt-edit-btn"
                    >
                      <el-icon><Edit /></el-icon> 编辑
                    </el-button>
                  </template>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 右侧：参数说明面板 -->
      <div class="gt-settings-right">
        <div v-if="selectedHelp" class="gt-help-panel">
          <div class="gt-help-title">
            <el-icon :size="16" style="color: var(--gt-color-primary)"><InfoFilled /></el-icon>
            {{ selectedKey }}
          </div>
          <div class="gt-help-desc">{{ selectedHelp.description }}</div>
          <div v-if="selectedHelp.recommend" class="gt-help-section">
            <span class="gt-help-label">推荐值</span>
            <code>{{ selectedHelp.recommend }}</code>
          </div>
          <div v-if="selectedHelp.warning" class="gt-help-section gt-help-warning">
            <span class="gt-help-label">⚠ 注意</span>
            {{ selectedHelp.warning }}
          </div>
          <div v-if="selectedHelp.example" class="gt-help-section">
            <span class="gt-help-label">示例</span>
            <code>{{ selectedHelp.example }}</code>
          </div>
          <div class="gt-help-section">
            <span class="gt-help-label">修改方式</span>
            {{ editableKeys.includes(selectedKey) ? '页面编辑（运行时生效，重启恢复 .env 值）' : '修改 .env 文件后重启服务' }}
          </div>
        </div>
        <div v-else class="gt-help-empty">
          <el-icon :size="40" style="color: #ddd"><InfoFilled /></el-icon>
          <p>点击左侧配置项查看说明</p>
        </div>
      </div>
    </div>

    <div v-else style="text-align: center; padding: 60px">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p style="color: #999; margin-top: 12px">加载配置中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Refresh, Edit, Loading, InfoFilled } from '@element-plus/icons-vue'
import { getSystemSettings, updateSystemSetting, getSystemHealth } from '@/services/commonApi'

const loading = ref(false)
const saving = ref(false)
const healthLoading = ref(false)

const groups = ref<Record<string, Record<string, any>>>({})
const editableKeys = ref<string[]>([])
const jwtSecure = ref(true)
const healthResults = ref<Record<string, any> | null>(null)

const expandedGroups = ref(['llm', 'security', 'services'])
const editingKey = ref('')
const editingValue = ref<any>('')
const selectedKey = ref('')
const expertMode = ref(false)

const groupLabels: Record<string, string> = {
  database: '数据库',
  security: '安全配置',
  llm: 'AI / LLM 模型',
  storage: '文件存储',
  ocr: 'OCR 识别',
  services: '外部服务',
  performance: '性能参数',
}

// 简洁模式下显示的分组
const simpleGroups = new Set(['llm', 'storage', 'services', 'performance'])

// 简洁模式下隐藏的配置项（太专业的）
const expertOnlyKeys = new Set([
  'DATABASE_URL', 'REDIS_URL', 'JWT_SECRET_KEY', 'JWT_ALGORITHM',
  'JWT_ACCESS_TOKEN_EXPIRE_MINUTES', 'JWT_REFRESH_TOKEN_EXPIRE_DAYS',
  'ENCRYPTION_KEY', 'CORS_ORIGINS', 'WOPI_BASE_URL',
  'CHROMADB_URL', 'ATTACHMENT_FALLBACK_TO_LOCAL', 'ATTACHMENT_LOCAL_STORAGE_ROOT',
  'OCR_TESSERACT_LANG', 'OCR_CONFIDENCE_THRESHOLD', 'MINERU_USE_CLI',
  'PAPERLESS_TIMEOUT',
])

// 配置项中文友好名
const friendlyNames: Record<string, string> = {
  DATABASE_URL: '数据库连接',
  REDIS_URL: 'Redis 地址',
  JWT_SECRET_KEY: '令牌密钥',
  JWT_ALGORITHM: '签名算法',
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES: '登录有效期（分钟）',
  JWT_REFRESH_TOKEN_EXPIRE_DAYS: '免登录天数',
  LOGIN_MAX_ATTEMPTS: '最大登录尝试次数',
  LOGIN_LOCK_MINUTES: '锁定时长（分钟）',
  ENCRYPTION_KEY: '加密密钥',
  LLM_BASE_URL: 'AI 服务地址',
  LLM_API_KEY: 'AI 密钥',
  DEFAULT_CHAT_MODEL: '对话模型',
  DEFAULT_EMBEDDING_MODEL: '向量模型',
  LLM_TEMPERATURE: '生成温度',
  LLM_MAX_TOKENS: '最大生成长度',
  LLM_ENABLE_THINKING: '思维链模式',
  OLLAMA_BASE_URL: 'Ollama 地址',
  STORAGE_ROOT: '存储目录',
  ATTACHMENT_PRIMARY_STORAGE: '附件存储方式',
  ATTACHMENT_FALLBACK_TO_LOCAL: '本地降级',
  ATTACHMENT_LOCAL_STORAGE_ROOT: '本地附件目录',
  MAX_UPLOAD_SIZE_MB: '上传限制（MB）',
  OCR_DEFAULT_ENGINE: 'OCR 引擎',
  OCR_PADDLE_ENABLED: 'PaddleOCR',
  OCR_TESSERACT_ENABLED: 'Tesseract',
  OCR_TESSERACT_LANG: 'OCR 语言',
  OCR_CONFIDENCE_THRESHOLD: 'OCR 置信度',
  ONLYOFFICE_URL: '在线编辑服务（已迁移至 Univer）',
  WOPI_BASE_URL: 'WOPI 地址',
  PAPERLESS_URL: '文档管理服务',
  PAPERLESS_TOKEN: '文档管理密钥',
  PAPERLESS_TIMEOUT: '文档管理超时',
  MINERU_ENABLED: 'MinerU PDF 解析',
  MINERU_API_URL: 'MinerU 地址',
  CHROMADB_URL: '向量数据库',
  EVENT_DEBOUNCE_MS: '事件合并窗口（毫秒）',
  FORMULA_EXECUTE_TIMEOUT: '公式超时（秒）',
  CORS_ORIGINS: '跨域白名单',
}

function friendlyName(key: string): string {
  return friendlyNames[key] || key
}

const filteredGroups = computed(() => {
  if (expertMode.value) return groups.value
  const result: Record<string, Record<string, any>> = {}
  for (const [groupKey, items] of Object.entries(groups.value)) {
    if (!simpleGroups.has(groupKey)) continue
    const filtered: Record<string, any> = {}
    for (const [key, val] of Object.entries(items)) {
      if (!expertOnlyKeys.has(key)) filtered[key] = val
    }
    if (Object.keys(filtered).length > 0) result[groupKey] = filtered
  }
  return result
})

// 配置项说明字典
const helpDocs: Record<string, { description: string; recommend?: string; warning?: string; example?: string }> = {
  DATABASE_URL: {
    description: 'PostgreSQL 异步连接字符串，格式为 postgresql+asyncpg://user:pass@host:port/dbname',
    recommend: 'postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform',
    warning: '修改后需重启服务。生产环境请使用强密码，不要用默认的 postgres/postgres',
    example: 'postgresql+asyncpg://audit_user:StrongP@ss@db-server:5432/audit_prod',
  },
  REDIS_URL: {
    description: 'Redis 连接地址，用于缓存、会话管理、登录锁定计数、事件队列等',
    recommend: 'redis://localhost:6379/0',
    warning: 'Docker 环境下端口可能映射为 6380，请确认与 docker-compose.yml 一致',
  },
  JWT_SECRET_KEY: {
    description: 'JWT 令牌签名密钥，用于用户认证。必须保密，泄露将导致任意用户伪造登录',
    recommend: '至少 32 字符的随机字符串',
    warning: '当前使用默认弱密钥！生产环境必须修改。可用 openssl rand -hex 32 生成',
    example: 'a1b2c3d4e5f6...（32+ 字符）',
  },
  JWT_ALGORITHM: {
    description: 'JWT 签名算法',
    recommend: 'HS256',
    warning: '除非有特殊需求，不要修改此项',
  },
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES: {
    description: 'Access Token 有效期（分钟）。过期后需用 Refresh Token 刷新',
    recommend: '120（2小时）',
    warning: '设置过短会频繁要求重新登录，过长会降低安全性',
  },
  JWT_REFRESH_TOKEN_EXPIRE_DAYS: {
    description: 'Refresh Token 有效期（天）。过期后需重新登录',
    recommend: '7（一周）',
  },
  LOGIN_MAX_ATTEMPTS: {
    description: '登录失败最大尝试次数，超过后账号锁定',
    recommend: '5',
    warning: '设置过小可能导致正常用户被误锁',
  },
  LOGIN_LOCK_MINUTES: {
    description: '账号锁定时长（分钟），锁定期间无法登录',
    recommend: '30',
  },
  ENCRYPTION_KEY: {
    description: 'Fernet 对称加密密钥，用于敏感数据加密存储（如 API Key）',
    warning: '为空时加密功能不可用。可用 python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 生成',
  },
  LLM_BASE_URL: {
    description: 'LLM 推理服务地址（OpenAI 兼容 API）。默认指向本地 vLLM',
    recommend: 'http://localhost:8100/v1',
    warning: '确保 vLLM 容器已启动（docker compose --profile gpu up vllm）',
    example: 'http://localhost:8100/v1 或 https://api.openai.com/v1',
  },
  LLM_API_KEY: {
    description: 'LLM API 密钥。本地 vLLM 不需要，使用云端 API 时必填',
    recommend: '本地 vLLM 填 not-needed',
    warning: '使用 OpenAI/DeepSeek 等云端 API 时需填入真实密钥',
  },
  DEFAULT_CHAT_MODEL: {
    description: '默认对话模型名称，需与 LLM 服务中已加载的模型一致',
    recommend: 'Kbenkhaled/Qwen3.5-27B-NVFP4',
    example: 'gpt-4o / deepseek-chat / Qwen/Qwen2.5-72B',
  },
  DEFAULT_EMBEDDING_MODEL: {
    description: '默认向量嵌入模型，用于知识库语义检索',
    recommend: '与对话模型相同（vLLM 统一服务）',
  },
  LLM_TEMPERATURE: {
    description: '生成温度（0-1）。越低越确定性，越高越有创造性',
    recommend: '0.3（审计场景需要准确性）',
    warning: '审计报告生成建议 0.1-0.3，创意写作可用 0.7-0.9',
  },
  LLM_MAX_TOKENS: {
    description: '单次生成最大 token 数',
    recommend: '4096',
    warning: '过大会增加响应时间和成本，过小可能截断输出',
  },
  LLM_ENABLE_THINKING: {
    description: 'Qwen3.5 思维链模式。开启后模型会先推理再回答，响应更慢但质量更高',
    recommend: '关闭（审计场景直接回答更高效）',
    warning: '开启后 token 消耗约增加 2-3 倍',
  },
  OLLAMA_BASE_URL: {
    description: 'Ollama 本地模型服务地址（备用，vLLM 不可用时降级）',
    recommend: 'http://localhost:11434',
  },
  STORAGE_ROOT: {
    description: '文件存储根目录，底稿、附件、导出文件等存放位置',
    recommend: './storage',
    warning: '确保目录存在且有读写权限',
  },
  ATTACHMENT_PRIMARY_STORAGE: {
    description: '附件主存储方式：paperless（Paperless-ngx 管理）或 local（本地磁盘）',
    recommend: 'paperless',
    warning: 'Paperless 未部署时自动降级为 local',
  },
  MAX_UPLOAD_SIZE_MB: {
    description: '文件上传大小限制（MB）',
    recommend: '100',
    warning: '大文件上传可能导致内存占用过高',
  },
  OCR_DEFAULT_ENGINE: {
    description: 'OCR 引擎选择：auto（自动选择）、paddle（PaddleOCR 高精度）、tesseract（Tesseract 快速）',
    recommend: 'auto',
  },
  OCR_PADDLE_ENABLED: {
    description: '是否启用 PaddleOCR 引擎（精度高但需要 GPU）',
    recommend: '开启',
    warning: '首次加载模型较慢（约 30 秒），需设置 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True 跳过连接检查',
  },
  OCR_TESSERACT_ENABLED: {
    description: '是否启用 Tesseract OCR 引擎（速度快，CPU 即可）',
    recommend: '开启',
  },
  ONLYOFFICE_URL: {
    description: '在线编辑服务地址（已迁移至 Univer 纯前端方案，此配置仅用于向后兼容）',
    recommend: 'http://localhost:8080',
    warning: '底稿在线编辑已使用 Univer 纯前端方案，不再依赖 ONLYOFFICE Docker 容器',
  },
  PAPERLESS_URL: {
    description: 'Paperless-ngx 文档管理服务地址',
    recommend: 'http://localhost:8010',
    warning: '为空时附件管理降级为本地磁盘存储',
  },
  PAPERLESS_TOKEN: {
    description: 'Paperless-ngx API 认证令牌',
    warning: '在 Paperless 管理后台生成',
  },
  EVENT_DEBOUNCE_MS: {
    description: '事件总线去重窗口（毫秒）。相同事件在此时间内合并为一次，避免批量操作触发 N 次重算',
    recommend: '500',
    warning: '设置过大会延迟事件响应，过小会失去去重效果',
  },
  FORMULA_EXECUTE_TIMEOUT: {
    description: '取数公式执行超时（秒）。超时后返回错误而非卡死',
    recommend: '10',
    warning: '复杂公式或数据量大时可适当增大',
  },
  CHROMADB_URL: {
    description: 'ChromaDB 向量数据库地址，用于知识库语义检索',
    recommend: 'http://localhost:8000',
  },
  WOPI_BASE_URL: {
    description: 'WOPI 协议基础 URL（向后兼容，底稿编辑已迁移至 Univer）',
    recommend: 'http://localhost:9980/wopi',
    warning: 'WOPI 端点保留用于向后兼容，新的底稿编辑通过 Univer API 直接读写',
  },
  ATTACHMENT_FALLBACK_TO_LOCAL: {
    description: 'Paperless 不可用时是否降级到本地磁盘存储',
    recommend: '开启',
  },
  ATTACHMENT_LOCAL_STORAGE_ROOT: {
    description: '本地附件存储目录',
    recommend: './storage/attachments',
  },
  OCR_TESSERACT_LANG: {
    description: 'Tesseract OCR 语言包',
    recommend: 'chi_sim+eng（简体中文+英文）',
  },
  OCR_CONFIDENCE_THRESHOLD: {
    description: 'OCR 识别置信度阈值（0-1），低于此值的结果被丢弃',
    recommend: '0.8',
  },
  MINERU_ENABLED: {
    description: '是否启用 MinerU GPU 加速 PDF 解析（表格/公式识别）',
    recommend: '有 GPU 时开启',
  },
  MINERU_API_URL: {
    description: 'MinerU 服务地址',
    recommend: 'http://localhost:8002',
  },
  PAPERLESS_TIMEOUT: {
    description: 'Paperless API 请求超时（秒）',
    recommend: '30',
  },
  CORS_ORIGINS: {
    description: '允许的跨域来源，逗号分隔。前端开发服务器地址需包含在内',
    recommend: 'http://localhost:3030,http://localhost:5173',
    warning: '生产环境应限制为实际域名',
  },
}

const selectedHelp = computed(() => {
  return selectedKey.value ? helpDocs[selectedKey.value] || null : null
})

function selectKey(key: string) {
  selectedKey.value = key
}

function formatValue(val: any): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? '✅ 开启' : '❌ 关闭'
  return String(val)
}

function startEdit(key: string, currentValue: any) {
  editingKey.value = key
  editingValue.value = currentValue
  selectedKey.value = key
}

function cancelEdit() {
  editingKey.value = ''
  editingValue.value = ''
}

async function saveEdit(key: string) {
  saving.value = true
  try {
    const res = await updateSystemSetting(key, editingValue.value)
    if (res.updated && Object.keys(res.updated).length > 0) {
      ElMessage.success(`${key} 已更新`)
      cancelEdit()
      await loadSettings()
    } else if (res.rejected && Object.keys(res.rejected).length > 0) {
      ElMessage.error(Object.values(res.rejected)[0] as string)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '更新失败')
  } finally {
    saving.value = false
  }
}

async function loadSettings() {
  loading.value = true
  try {
    const res = await getSystemSettings()
    groups.value = res.groups || {}
    editableKeys.value = res.editable_keys || []
    jwtSecure.value = res.jwt_secure !== false
  } catch (e: any) {
    ElMessage.error('加载配置失败: ' + (e.message || ''))
  } finally {
    loading.value = false
  }
}

async function checkHealth() {
  healthLoading.value = true
  try {
    const res = await getSystemHealth()
    healthResults.value = res.services || {}
  } catch {
    ElMessage.error('服务检测失败')
  } finally {
    healthLoading.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.gt-settings { padding: 20px; }
.gt-settings-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
}
.gt-settings-header h2 { margin: 0; font-size: 20px; color: #333; }
.gt-settings-actions { display: flex; gap: 8px; }

.gt-health-bar {
  display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px;
  padding: 12px 16px; background: #fafafa; border-radius: 8px; border: 1px solid #eee;
}
.gt-health-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #666; }
.gt-health-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.gt-health-ok .gt-health-dot { background: #67c23a; }
.gt-health-err .gt-health-dot { background: #f56c6c; }
.gt-health-err { color: #f56c6c; }

/* 双栏布局 */
.gt-settings-body { display: flex; gap: 20px; align-items: flex-start; }
.gt-settings-left { flex: 1; min-width: 0; }
.gt-settings-right {
  width: 320px; flex-shrink: 0; position: sticky; top: 20px;
}

.gt-settings-table { display: flex; flex-direction: column; }
.gt-settings-row {
  display: flex; align-items: center; padding: 10px 8px;
  border-bottom: 1px solid #f5f5f5; cursor: pointer; border-radius: 4px;
  transition: background 0.15s;
}
.gt-settings-row:hover { background: #fafafa; }
.gt-settings-row--active { background: #f5f0ff !important; border-left: 3px solid var(--gt-color-primary, #4b2d77); }
.gt-settings-row--active .gt-value-text { color: #222; }
.gt-settings-row--active .gt-editable-tag { background: #fff !important; }

/* 编辑按钮：白底+深色文字+边框，任何背景下都清晰 */
.gt-edit-btn {
  background: #fff !important;
  color: #333 !important;
  border: 1px solid #ccc !important;
  font-size: 12px;
}
.gt-edit-btn:hover {
  color: var(--gt-color-primary, #4b2d77) !important;
  border-color: var(--gt-color-primary, #4b2d77) !important;
}
.gt-settings-row:last-child { border-bottom: none; }
.gt-settings-key {
  width: 280px; flex-shrink: 0; font-size: 13px; color: #555;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.gt-key-name { font-weight: 500; color: #333; }
.gt-key-code { font-size: 11px; color: #999; font-family: 'Consolas', 'Monaco', monospace; }
.gt-group-count { font-size: 12px; color: #999; margin-left: 8px; font-weight: 400; }
.gt-settings-value { flex: 1; font-size: 13px; display: flex; align-items: center; gap: 8px; }
.gt-value-text { color: #333; word-break: break-all; }
.gt-value-masked { color: #999; font-style: italic; }
.gt-editable-tag { transform: scale(0.8); }

/* 右侧说明面板 */
.gt-help-panel {
  background: #fafbfc; border: 1px solid #e8e8e8; border-radius: 8px;
  padding: 20px; font-size: 13px; line-height: 1.8;
}
.gt-help-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: var(--gt-color-primary, #4b2d77);
  font-family: 'Consolas', 'Monaco', monospace;
  margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #eee;
}
.gt-help-desc { color: #333; margin-bottom: 14px; }
.gt-help-section { margin-bottom: 10px; }
.gt-help-label {
  display: inline-block; font-weight: 600; color: #666; margin-right: 8px;
  min-width: 56px;
}
.gt-help-section code {
  background: #f0f0f0; padding: 2px 6px; border-radius: 3px;
  font-size: 12px; color: #c7254e; word-break: break-all;
}
.gt-help-warning { color: #e6a23c; background: #fef8e8; padding: 8px 10px; border-radius: 4px; }
.gt-help-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 200px; color: #ccc; font-size: 14px; gap: 12px;
  background: #fafbfc; border: 1px dashed #e0e0e0; border-radius: 8px;
}
.gt-help-empty p { margin: 0; }

:deep(.el-collapse-item__header) {
  font-size: 15px; font-weight: 600; color: var(--gt-color-primary, #4b2d77);
}
</style>
