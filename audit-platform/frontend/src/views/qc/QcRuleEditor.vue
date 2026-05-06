<template>
  <div class="qc-rule-editor">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>{{ isEdit ? '✏️ 编辑规则' : '➕ 新建规则' }}</h2>
        <span class="gt-banner-sub" v-if="isEdit">
          {{ form.rule_code }} · 版本 {{ form.version }}
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="router.back()">返回列表</el-button>
        <el-button
          v-if="isEdit"
          size="small"
          type="info"
          @click="showVersionDrawer = true"
        >
          📜 历史版本
        </el-button>
      </div>
    </div>

    <!-- 主体表单 -->
    <div class="editor-body" v-loading="loadingRule">
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="130px"
        label-position="right"
        class="rule-form"
      >
        <!-- 基本信息 -->
        <div class="form-section">
          <h3 class="section-title">基本信息</h3>

          <el-form-item label="规则编号" prop="rule_code">
            <el-input v-model="form.rule_code" placeholder="如 QC-CUSTOM-001" :disabled="isEdit" />
          </el-form-item>

          <el-form-item label="标题" prop="title">
            <el-input v-model="form.title" placeholder="规则标题" />
          </el-form-item>

          <el-form-item label="描述" prop="description">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="规则描述"
            />
          </el-form-item>

          <el-form-item label="严重级别" prop="severity">
            <el-select v-model="form.severity" style="width: 200px">
              <el-option label="阻断 (blocking)" value="blocking" />
              <el-option label="警告 (warning)" value="warning" />
              <el-option label="提示 (info)" value="info" />
            </el-select>
          </el-form-item>

          <el-form-item label="适用范围" prop="scope">
            <el-select v-model="form.scope" style="width: 200px">
              <el-option label="底稿 (workpaper)" value="workpaper" />
              <el-option label="项目 (project)" value="project" />
              <el-option label="合并 (consolidation)" value="consolidation" />
              <el-option label="审计日志 (audit_log)" value="audit_log" />
            </el-select>
          </el-form-item>

          <el-form-item label="分类" prop="category">
            <el-input v-model="form.category" placeholder="可选分类标签" />
          </el-form-item>

          <el-form-item label="启用" prop="enabled">
            <el-switch v-model="form.enabled" />
          </el-form-item>
        </div>

        <!-- 准则引用 -->
        <div class="form-section">
          <h3 class="section-title">准则引用</h3>

          <div
            v-for="(ref, idx) in form.standard_ref"
            :key="idx"
            class="standard-ref-row"
          >
            <el-input
              v-model="ref.code"
              placeholder="准则号 (如 1301)"
              style="width: 120px"
            />
            <el-input
              v-model="ref.section"
              placeholder="章节 (如 6.2)"
              style="width: 100px"
            />
            <el-input
              v-model="ref.name"
              placeholder="名称 (如 审计工作底稿)"
              style="width: 200px"
            />
            <el-button link type="danger" @click="removeStandardRef(idx)">删除</el-button>
          </div>
          <el-button size="small" @click="addStandardRef">+ 添加准则引用</el-button>
        </div>

        <!-- 规则表达式 -->
        <div class="form-section">
          <h3 class="section-title">规则表达式</h3>

          <el-form-item label="表达式类型" prop="expression_type">
            <el-select v-model="form.expression_type" style="width: 200px">
              <el-option label="Python 类" value="python" />
              <el-option label="JSONPath" value="jsonpath" />
              <el-option label="SQL (未实现)" value="sql" disabled />
              <el-option label="Regex (未实现)" value="regex" disabled />
            </el-select>
          </el-form-item>

          <el-form-item label="表达式" prop="expression">
            <el-input
              v-model="form.expression"
              type="textarea"
              :rows="4"
              :placeholder="expressionPlaceholder"
            />
          </el-form-item>

          <el-form-item label="参数 Schema">
            <el-input
              v-model="parametersSchemaText"
              type="textarea"
              :rows="3"
              placeholder='可选 JSON Schema，如 {"threshold": {"type": "number", "default": 100}}'
            />
          </el-form-item>
        </div>
      </el-form>

      <!-- 试运行区域 -->
      <div class="form-section dry-run-section">
        <h3 class="section-title">🧪 试运行（Dry-Run）</h3>
        <p class="dry-run-hint">
          发布前必须执行试运行，预览规则命中率，确认无误后方可保存。
        </p>

        <div class="dry-run-controls">
          <el-select v-model="dryRunScope" style="width: 160px" placeholder="范围">
            <el-option label="全部项目" value="all" />
            <el-option label="指定项目" value="project" />
          </el-select>

          <el-input-number
            v-model="dryRunSampleSize"
            :min="10"
            :max="500"
            :step="10"
            placeholder="采样数"
            style="width: 140px"
          />

          <el-button
            type="warning"
            :loading="dryRunLoading"
            :disabled="!canDryRun"
            @click="executeDryRun"
          >
            🚀 执行试运行
          </el-button>
        </div>

        <!-- 试运行结果 -->
        <div v-if="dryRunResult" class="dry-run-result">
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="检查总数">
              {{ dryRunResult.total_checked }}
            </el-descriptions-item>
            <el-descriptions-item label="命中数">
              <span class="hit-count">{{ dryRunResult.hits }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="命中率">
              <el-tag :type="hitRateTagType" size="small" effect="dark">
                {{ (dryRunResult.hit_rate * 100).toFixed(1) }}%
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag type="success" size="small">✅ 试运行完成</el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <!-- 命中样本 -->
          <div v-if="dryRunResult.sample_findings.length" class="findings-table">
            <h4>命中样本（前 {{ dryRunResult.sample_findings.length }} 条）</h4>
            <el-table :data="dryRunResult.sample_findings" size="small" stripe max-height="300">
              <el-table-column label="底稿编号" prop="wp_code" width="140" />
              <el-table-column label="消息" prop="message" min-width="300" show-overflow-tooltip />
              <el-table-column label="严重级别" prop="severity" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="severityTagType(row.severity)" size="small">
                    {{ row.severity }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="form-actions">
        <el-button @click="router.back()">取消</el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!canPublish"
          @click="handleSave"
        >
          {{ isEdit ? '💾 保存更新' : '🚀 发布规则' }}
        </el-button>
        <span v-if="!dryRunResult && isEdit" class="publish-hint">
          ⚠️ 请先执行试运行
        </span>
      </div>
    </div>

    <!-- 历史版本抽屉 -->
    <el-drawer
      v-model="showVersionDrawer"
      title="📜 历史版本"
      direction="rtl"
      size="450px"
    >
      <div v-loading="loadingVersions" class="version-list">
        <el-empty v-if="!versions.length && !loadingVersions" description="暂无历史版本" />
        <el-timeline v-else>
          <el-timeline-item
            v-for="ver in versions"
            :key="ver.version"
            :timestamp="ver.updated_at"
            placement="top"
          >
            <el-card shadow="hover" class="version-card">
              <div class="version-header">
                <el-tag size="small" type="info">v{{ ver.version }}</el-tag>
                <span class="version-title">{{ ver.title }}</span>
              </div>
              <div class="version-detail">
                <p><strong>表达式：</strong>{{ ver.expression }}</p>
                <p><strong>状态：</strong>{{ ver.enabled ? '启用' : '停用' }}</p>
                <p v-if="ver.updated_by"><strong>修改人：</strong>{{ ver.updated_by }}</p>
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  getQcRule,
  createQcRule,
  updateQcRule,
  dryRunQcRule,
  getQcRuleVersions,
  type QcRuleDefinition,
  type StandardRef,
  type DryRunResult,
  type QcRuleVersion,
} from '@/services/qcRuleApi'

const route = useRoute()
const router = useRouter()

// ─── State ──────────────────────────────────────────────────────────────────

const isEdit = computed(() => !!route.params.ruleId)
const ruleId = computed(() => route.params.ruleId as string)

const formRef = ref<FormInstance>()
const loadingRule = ref(false)
const saving = ref(false)

const form = reactive({
  rule_code: '',
  title: '',
  description: '',
  severity: 'warning' as 'blocking' | 'warning' | 'info',
  scope: 'workpaper' as 'workpaper' | 'project' | 'consolidation' | 'audit_log',
  category: '',
  enabled: true,
  expression_type: 'jsonpath' as 'python' | 'jsonpath' | 'sql' | 'regex',
  expression: '',
  standard_ref: [] as StandardRef[],
  version: 1,
})

const parametersSchemaText = ref('')

// ─── Dry-Run State ──────────────────────────────────────────────────────────

const dryRunScope = ref<'all' | 'project'>('all')
const dryRunSampleSize = ref(50)
const dryRunLoading = ref(false)
const dryRunResult = ref<DryRunResult | null>(null)

// ─── Version History ────────────────────────────────────────────────────────

const showVersionDrawer = ref(false)
const loadingVersions = ref(false)
const versions = ref<QcRuleVersion[]>([])

// ─── Form Validation ────────────────────────────────────────────────────────

const formRules: FormRules = {
  rule_code: [{ required: true, message: '请输入规则编号', trigger: 'blur' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  description: [{ required: true, message: '请输入描述', trigger: 'blur' }],
  severity: [{ required: true, message: '请选择严重级别', trigger: 'change' }],
  scope: [{ required: true, message: '请选择适用范围', trigger: 'change' }],
  expression_type: [{ required: true, message: '请选择表达式类型', trigger: 'change' }],
  expression: [{ required: true, message: '请输入表达式', trigger: 'blur' }],
}

// ─── Computed ───────────────────────────────────────────────────────────────

const expressionPlaceholder = computed(() => {
  switch (form.expression_type) {
    case 'python':
      return 'Python 类路径，如 app.services.qc_engine.ConclusionNotEmptyRule'
    case 'jsonpath':
      return 'JSONPath 表达式，如 $.parsed_data.conclusion[?(@.value == "")]'
    default:
      return '表达式'
  }
})

const canDryRun = computed(() => {
  // 编辑模式：规则已保存，可直接试运行
  if (isEdit.value) return true
  // 新建模式：需要先保存为草稿才能试运行（因为 dry-run 需要 rule_id）
  return false
})

const canPublish = computed(() => {
  // 编辑模式：必须先试运行
  if (isEdit.value) return !!dryRunResult.value
  // 新建模式：直接保存（保存后跳转到编辑页，再试运行再启用）
  return true
})

const hitRateTagType = computed(() => {
  if (!dryRunResult.value) return 'info'
  const rate = dryRunResult.value.hit_rate
  if (rate > 0.5) return 'danger'
  if (rate > 0.2) return 'warning'
  return 'success'
})

// ─── Helpers ────────────────────────────────────────────────────────────────

function severityTagType(severity: string): 'success' | 'warning' | 'danger' | 'info' {
  switch (severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'info'
  }
}

function addStandardRef() {
  form.standard_ref.push({ code: '', section: '', name: '' })
}

function removeStandardRef(idx: number) {
  form.standard_ref.splice(idx, 1)
}

function parseParametersSchema(): Record<string, any> | null {
  const text = parametersSchemaText.value.trim()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    ElMessage.warning('参数 Schema 不是有效的 JSON')
    return null
  }
}

function populateForm(rule: QcRuleDefinition) {
  form.rule_code = rule.rule_code
  form.title = rule.title
  form.description = rule.description
  form.severity = rule.severity
  form.scope = rule.scope
  form.category = rule.category || ''
  form.enabled = rule.enabled
  form.expression_type = rule.expression_type
  form.expression = rule.expression
  form.standard_ref = rule.standard_ref ? [...rule.standard_ref] : []
  form.version = rule.version
  if (rule.parameters_schema) {
    parametersSchemaText.value = JSON.stringify(rule.parameters_schema, null, 2)
  }
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadRule() {
  if (!isEdit.value) return
  loadingRule.value = true
  try {
    const rule = await getQcRule(ruleId.value)
    populateForm(rule)
  } catch {
    ElMessage.error('加载规则失败')
  } finally {
    loadingRule.value = false
  }
}

async function loadVersions() {
  if (!isEdit.value) return
  loadingVersions.value = true
  try {
    versions.value = await getQcRuleVersions(ruleId.value)
  } catch {
    ElMessage.warning('加载历史版本失败')
  } finally {
    loadingVersions.value = false
  }
}

// ─── Actions ────────────────────────────────────────────────────────────────

async function executeDryRun() {
  if (!isEdit.value) {
    ElMessage.info('新建规则请先保存，保存后可执行试运行')
    return
  }
  dryRunLoading.value = true
  dryRunResult.value = null
  try {
    const result = await dryRunQcRule(ruleId.value, {
      scope: dryRunScope.value,
      sample_size: dryRunSampleSize.value,
    })
    dryRunResult.value = result
    ElMessage.success(`试运行完成：命中 ${result.hits}/${result.total_checked}`)
  } catch (e: any) {
    ElMessage.error('试运行失败：' + (e?.response?.data?.detail || e.message || '未知错误'))
  } finally {
    dryRunLoading.value = false
  }
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 编辑模式必须先试运行
  if (isEdit.value && !dryRunResult.value) {
    ElMessage.warning('请先执行试运行，确认命中率后再保存')
    return
  }

  const parametersSchema = parseParametersSchema()
  if (parametersSchemaText.value.trim() && parametersSchema === null) return

  saving.value = true
  try {
    const payload: Partial<QcRuleDefinition> = {
      rule_code: form.rule_code,
      title: form.title,
      description: form.description,
      severity: form.severity,
      scope: form.scope,
      category: form.category || null,
      enabled: form.enabled,
      expression_type: form.expression_type,
      expression: form.expression,
      standard_ref: form.standard_ref.filter((r) => r.code),
      parameters_schema: parametersSchema,
    }

    if (isEdit.value) {
      await updateQcRule(ruleId.value, payload)
      ElMessage.success('规则已更新')
    } else {
      const created = await createQcRule(payload)
      ElMessage.success('规则已创建，请执行试运行后启用')
      // 跳转到编辑页以便执行试运行
      router.replace(`/qc/rules/${created.id}/edit`)
    }
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.response?.data?.detail || e.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadRule()
  if (isEdit.value) {
    loadVersions()
  }
})
</script>

<style scoped>
.qc-rule-editor {
  padding: 0;
}

.editor-body {
  padding: 20px;
  max-width: 900px;
}

.form-section {
  margin-bottom: 32px;
  padding: 20px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.section-title {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 8px;
}

.standard-ref-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.dry-run-section {
  border-color: #e6a23c;
  background: #fdf6ec;
}

.dry-run-hint {
  color: #e6a23c;
  font-size: 13px;
  margin-bottom: 12px;
}

.dry-run-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.dry-run-result {
  margin-top: 16px;
}

.hit-count {
  font-weight: 700;
  color: #f56c6c;
}

.findings-table {
  margin-top: 12px;
}

.findings-table h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #606266;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #ebeef5;
  background: #fafafa;
  border-radius: 0 0 8px 8px;
}

.publish-hint {
  color: #e6a23c;
  font-size: 13px;
}

/* Version drawer */
.version-list {
  padding: 0 8px;
}

.version-card {
  margin-bottom: 4px;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.version-title {
  font-weight: 600;
  color: #303133;
}

.version-detail p {
  margin: 4px 0;
  font-size: 13px;
  color: #606266;
}

.rule-form {
  margin: 0;
}
</style>
