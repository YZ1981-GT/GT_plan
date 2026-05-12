<template>
  <div class="qc-rule-editor">
    <GtPageHeader title="规则编辑" :show-back="false">
      <template #actions>
        <el-button size="small" @click="goBack">← 返回列表</el-button>
      </template>
    </GtPageHeader>

    <!-- 编辑表单 -->
    <el-form
      v-loading="loading"
      :model="form"
      label-width="120px"
      style="max-width: 800px; margin: 24px auto;"
    >
      <el-form-item label="规则编号">
        <el-input v-model="form.rule_code" disabled />
      </el-form-item>

      <el-form-item label="标题">
        <el-input v-model="form.title" placeholder="请输入规则标题" />
      </el-form-item>

      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="规则描述" />
      </el-form-item>

      <el-form-item label="严重级别">
        <el-select v-model="form.severity" style="width: 200px;">
          <el-option label="阻断 (blocking)" value="blocking" />
          <el-option label="警告 (warning)" value="warning" />
          <el-option label="提示 (info)" value="info" />
        </el-select>
      </el-form-item>

      <el-form-item label="适用范围">
        <el-select v-model="form.scope" style="width: 200px;">
          <el-option label="底稿" value="workpaper" />
          <el-option label="项目" value="project" />
          <el-option label="提交复核" value="submit_review" />
          <el-option label="签字" value="sign_off" />
          <el-option label="导出归档" value="export_package" />
          <el-option label="EQCR审批" value="eqcr_approval" />
        </el-select>
      </el-form-item>

      <el-form-item label="表达式类型">
        <el-input v-model="form.expression_type" disabled />
      </el-form-item>

      <el-form-item label="表达式">
        <el-input
          v-model="form.expression"
          type="textarea"
          :rows="6"
          placeholder="规则表达式"
        />
      </el-form-item>

      <el-form-item label="启用状态">
        <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
      </el-form-item>

      <el-form-item label="准则引用">
        <div class="standard-ref-input">
          <el-tag
            v-for="(tag, idx) in form.standard_ref"
            :key="idx"
            closable
            @close="removeTag(idx)"
            style="margin-right: 6px; margin-bottom: 4px;"
          >
            {{ tag }}
          </el-tag>
          <el-input
            v-if="tagInputVisible"
            ref="tagInputRef"
            v-model="tagInputValue"
            size="small"
            style="width: 160px;"
            @keyup.enter="addTag"
            @blur="addTag"
          />
          <el-button v-else size="small" @click="showTagInput">+ 添加引用</el-button>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="saveRule" :loading="saving" :disabled="!hasRunDryRun">
          {{ hasRunDryRun ? '保存' : '请先试运行' }}
        </el-button>
        <el-button @click="dryRun" :loading="dryRunning">试运行</el-button>
        <el-button @click="showVersionDrawer = true">版本历史</el-button>
      </el-form-item>
    </el-form>

    <!-- 试运行结果对话框 -->
    <el-dialog v-model="dryRunDialogVisible" title="试运行结果" width="600px">
      <div v-if="dryRunResult">
        <p><strong>命中数量：</strong>{{ dryRunResult.hit_count }}</p>
        <el-divider />
        <p><strong>样本发现：</strong></p>
        <el-table :data="dryRunResult.sample_findings" stripe style="width: 100%;" max-height="300">
          <el-table-column label="对象" prop="object_ref" min-width="160" />
          <el-table-column label="详情" prop="detail" min-width="240" />
        </el-table>
      </div>
      <div v-else>
        <p>暂无结果</p>
      </div>
    </el-dialog>

    <!-- 版本历史抽屉 -->
    <el-drawer v-model="showVersionDrawer" title="版本历史" size="400px">
      <div style="padding: 16px;">
        <p><strong>当前版本：</strong>v{{ form.version || 1 }}</p>
        <el-timeline>
          <el-timeline-item
            v-for="v in versionHistory"
            :key="v.version"
            :timestamp="`版本 ${v.version}`"
          >
            {{ v.note || '规则更新' }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="!versionHistory.length" description="暂无历史版本" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getQcRule, updateQcRule, dryRunQcRule } from '@/services/qcRuleApi'
import { handleApiError } from '@/utils/errorHandler'

// ─── Types ──────────────────────────────────────────────────────────────────

interface RuleForm {
  rule_code: string
  title: string
  description: string
  severity: string
  scope: string
  expression_type: string
  expression: string
  enabled: boolean
  standard_ref: string[]
  version: number
}

interface DryRunResult {
  hit_count: number
  sample_findings: Array<{ object_ref: string; detail: string }>
}

// ─── State ──────────────────────────────────────────────────────────────────

const route = useRoute()
const router = useRouter()
const ruleId = route.params.ruleId as string

const loading = ref(false)
const saving = ref(false)
const dryRunning = ref(false)
const dryRunDialogVisible = ref(false)
const showVersionDrawer = ref(false)

const form = ref<RuleForm>({
  rule_code: '',
  title: '',
  description: '',
  severity: 'warning',
  scope: 'workpaper',
  expression_type: 'python',
  expression: '',
  enabled: true,
  standard_ref: [],
  version: 1,
})

const dryRunResult = ref<DryRunResult | null>(null)
const hasRunDryRun = ref(false)
const versionHistory = ref<Array<{ version: number; note: string }>>([])

// Tag input
const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref<any>(null)

// ─── Methods ────────────────────────────────────────────────────────────────

function goBack() {
  router.push('/qc/rules')
}

function removeTag(idx: number) {
  form.value.standard_ref.splice(idx, 1)
}

function showTagInput() {
  tagInputVisible.value = true
  nextTick(() => {
    tagInputRef.value?.focus()
  })
}

function addTag() {
  const val = tagInputValue.value.trim()
  if (val && !form.value.standard_ref.includes(val)) {
    form.value.standard_ref.push(val)
  }
  tagInputVisible.value = false
  tagInputValue.value = ''
}

async function loadRule() {
  loading.value = true
  try {
    const data = await getQcRule(ruleId)
    form.value = {
      rule_code: data.rule_code || '',
      title: data.title || '',
      description: data.description || '',
      severity: data.severity || 'warning',
      scope: data.scope || 'workpaper',
      expression_type: data.expression_type || 'python',
      expression: data.expression || '',
      enabled: data.enabled ?? true,
      standard_ref: (data.standard_ref || []) as any,
      version: data.version || 1,
    }
    // Build version history from current version
    versionHistory.value = []
    for (let i = 1; i <= (data.version || 1); i++) {
      versionHistory.value.push({ version: i, note: i === data.version ? '当前版本' : '历史更新' })
    }
  } catch (e: any) {
    handleApiError(e, '加载规则')
  } finally {
    loading.value = false
  }
}

async function saveRule() {
  saving.value = true
  try {
    await updateQcRule(ruleId, {
      title: form.value.title,
      description: form.value.description,
      severity: form.value.severity as any,
      scope: form.value.scope as any,
      expression: form.value.expression,
      enabled: form.value.enabled,
      standard_ref: form.value.standard_ref as any,
    })
    ElMessage.success('保存成功')
    await loadRule()
  } catch (e: any) {
    handleApiError(e, '保存')
  } finally {
    saving.value = false
  }
}

async function dryRun() {
  dryRunning.value = true
  try {
    const result = await dryRunQcRule(ruleId, { scope: 'all' })
    dryRunResult.value = result as any
    dryRunDialogVisible.value = true
    hasRunDryRun.value = true
  } catch (e: any) {
    handleApiError(e, '试运行')
  } finally {
    dryRunning.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadRule()
})
</script>

<style scoped>
.qc-rule-editor {
  padding: 0;
}

.standard-ref-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
</style>
