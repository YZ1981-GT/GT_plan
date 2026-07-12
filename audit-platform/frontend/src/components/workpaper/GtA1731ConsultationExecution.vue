<!--
  GtA1731ConsultationExecution.vue — A17-3-1 业务咨询结果执行情况记录

  极简专属组件：5 区块卡片 + 双模式切换
  - 元信息：执行人/执行日期/复核日期/复核人（自动填充）
  - 第一节：引用 A17-3 咨询事项 (read-only gray区域 + GtIndexChip) + 补充说明 textarea
  - 第二节：执行情况 textarea
  - 第三节：执行结果 textarea
  - 第四节：后续跟进 textarea
  - 双模式: 结构化视图 / 在线编辑(GtOnlyOfficeSheet)
-->
<template>
  <div class="gt-a1731">
    <!-- Mode Switch -->
    <div class="gt-a1731__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
      />
      <span class="gt-a1731__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">
          ✓ 已保存
        </template>
        <template v-else-if="saveStatus === 'unsaved'">
          ○ 未保存
        </template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a1731__content">
      <!-- Loading -->
      <el-skeleton v-if="loading" :rows="8" animated />

      <template v-else>
        <!-- Meta Info Card -->
        <el-card class="gt-a1731__card gt-a1731__card--meta" shadow="never">
          <template #header>
            <span class="gt-a1731__card-title">编制信息</span>
          </template>
          <div class="gt-a1731__meta-grid">
            <div class="gt-a1731__meta-item">
              <label>执行人</label>
              <el-input
                :model-value="metaInfo.reviewer"
                size="small"
                :disabled="props.readonly"
                placeholder="复核人"
                @change="(v: string) => updateMeta('reviewer', v)"
              />
            </div>
            <div class="gt-a1731__meta-item">
              <label>复核日期</label>
              <el-date-picker
                :model-value="metaInfo.review_date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="选择日期"
                @change="(v: string) => updateMeta('review_date', v || '')"
              />
            </div>
            <div class="gt-a1731__meta-item">
              <label>执行人</label>
              <el-input
                :model-value="metaInfo.executor"
                size="small"
                :disabled="props.readonly"
                placeholder="执行人"
                @change="(v: string) => updateMeta('executor', v)"
              />
            </div>
            <div class="gt-a1731__meta-item">
              <label>执行日期</label>
              <el-date-picker
                :model-value="metaInfo.execution_date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="选择日期"
                @change="(v: string) => updateMeta('execution_date', v || '')"
              />
            </div>
          </div>
        </el-card>

        <!-- Section 一: A17-3 引用 + 补充说明 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <div class="gt-a1731__section-header">
              <span class="gt-a1731__card-title">一、咨询事项描述</span>
              <div class="gt-a1731__section-actions">
                <el-button size="small" type="primary" text @click="switchToA173Tab">A17-3 ↗</el-button>
                <el-button size="small" :loading="aiLoading === 1" @click="aiGenerate(1)">🤖 AI</el-button>
              </div>
            </div>
          </template>
          <details class="gt-a1731__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1731__guidance-body">需要说明咨询事项的业务背景，主要存在的疑问及管理层建议、本项目的初步判断。可引用业务咨询记录（A17-3）相关内容。</div>
          </details>

          <!-- A17-3 Reference Area (read-only) -->
          <div class="gt-a1731__reference">
            <div class="gt-a1731__reference-label">A17-3 咨询事项摘要（只读）<el-button size="small" text @click="refreshA173Reference">🔄</el-button></div>
            <div class="gt-a1731__reference-content">
              <div v-if="a173Reference.overview" class="gt-a1731__reference-field">
                <span class="gt-a1731__reference-key">业务概况：</span>
                <span>{{ a173Reference.overview }}</span>
              </div>
              <div v-if="a173Reference.background" class="gt-a1731__reference-field">
                <span class="gt-a1731__reference-key">问题背景：</span>
                <span>{{ a173Reference.background }}</span>
              </div>
              <div v-if="a173Reference.reply" class="gt-a1731__reference-field">
                <span class="gt-a1731__reference-key">回复意见：</span>
                <span>{{ a173Reference.reply }}</span>
              </div>
              <div v-if="!a173Reference.overview && !a173Reference.background" class="gt-a1731__reference-empty">
                暂无 A17-3 咨询事项数据（请先编制A17-3后刷新）
              </div>
            </div>
          </div>

          <!-- Supplementary Notes -->
          <div class="gt-a1731__field">
            <label class="gt-a1731__label">补充说明</label>
            <el-input
              :model-value="sections[1].supplementary"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 10 }"
              :disabled="props.readonly"
              placeholder="请填写补充说明（可选）"
              @change="(v: string) => updateSection(1, 'supplementary', v)"
            />
          </div>
        </el-card>

        <!-- Section 二: 咨询回复意见 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <div class="gt-a1731__section-header">
              <span class="gt-a1731__card-title">二、咨询回复意见</span>
              <el-button size="small" :loading="aiLoading === 2" @click="aiGenerate(2)">🤖 AI</el-button>
            </div>
          </template>
          <details class="gt-a1731__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1731__guidance-body">完整引用专业技术部、专业技术委员会或者所外咨询者的回复意见。</div>
          </details>
          <div class="gt-a1731__field">
            <el-input
              :model-value="sections[2].execution_details"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 15 }"
              :disabled="props.readonly"
              placeholder="完整引用专业技术部/委员会/所外咨询者的回复意见"
              @change="(v: string) => updateSection(2, 'execution_details', v)"
            />
          </div>
        </el-card>

        <!-- Section 三: 咨询结果的执行情况 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <div class="gt-a1731__section-header">
              <span class="gt-a1731__card-title">三、咨询结果的执行情况</span>
              <el-button size="small" :loading="aiLoading === 3" @click="aiGenerate(3)">🤖 AI</el-button>
            </div>
          </template>
          <details class="gt-a1731__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1731__guidance-body">
              (一) 项目组是否与咨询意见达成一致意见：是/否，如否需说明最终解决情况。<br/>
              (二) 咨询结果（结论）是否得到执行：是/否，如未得到执行需说明相关原因。<br/>
              (三) 具体执行情况表格：序号/实施该步骤或实施的审计程序/核照相关审计/审计人/实施日期/说明。
            </div>
          </details>

          <!-- (一) 是否一致 -->
          <div class="gt-a1731__sub-section">
            <div class="gt-a1731__sub-header">
              <span class="gt-a1731__sub-label">(一) 项目组是否与咨询意见达成一致意见</span>
              <el-radio-group :model-value="s3Agree" size="small" :disabled="props.readonly" @change="(v: string) => { s3Agree = v; saveS3() }">
                <el-radio-button value="Y">是</el-radio-button>
                <el-radio-button value="N">否</el-radio-button>
              </el-radio-group>
            </div>
            <el-input v-if="s3Agree === 'N'" :model-value="s3AgreeReason" type="textarea" :autosize="{minRows:2}" :disabled="props.readonly" placeholder="如否，最终解决情况说明（虽观点少出现，但需说明）" @change="(v: string) => { s3AgreeReason = v; saveS3() }" />
          </div>

          <!-- (二) 是否得到执行 -->
          <div class="gt-a1731__sub-section">
            <div class="gt-a1731__sub-header">
              <span class="gt-a1731__sub-label">(二) 咨询结果（结论）是否得到执行</span>
              <el-radio-group :model-value="s3Executed" size="small" :disabled="props.readonly" @change="(v: string) => { s3Executed = v; saveS3() }">
                <el-radio-button value="Y">是</el-radio-button>
                <el-radio-button value="N">否</el-radio-button>
              </el-radio-group>
            </div>
            <el-input v-if="s3Executed === 'N'" :model-value="s3ExecutedReason" type="textarea" :autosize="{minRows:2}" :disabled="props.readonly" placeholder="如未得到执行，说明相关原因（如未执行、部分执行、暂缓执行）" @change="(v: string) => { s3ExecutedReason = v; saveS3() }" />
          </div>

          <!-- (三) 具体执行情况 -->
          <div class="gt-a1731__sub-section">
            <span class="gt-a1731__sub-label">(三) 咨询结果（结论）执行具体情况</span>
            <el-input
              :model-value="sections[3].results"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 15 }"
              :disabled="props.readonly"
              placeholder="描述按照咨询回复意见实施的审计程序、执行过程的评价、会计问题的处理方式等"
              @change="(v: string) => updateSection(3, 'results', v)"
            />
          </div>
        </el-card>

        <!-- Section 四: 后续跟进 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <div class="gt-a1731__section-header">
              <span class="gt-a1731__card-title">四、后续跟进</span>
              <el-button size="small" :loading="aiLoading === 4" @click="aiGenerate(4)">🤖 AI</el-button>
            </div>
          </template>
          <div class="gt-a1731__field">
            <el-input
              :model-value="sections[4].follow_up"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 10 }"
              :disabled="props.readonly"
              placeholder="请填写后续跟进事项"
              @change="(v: string) => updateSection(4, 'follow_up', v)"
            />
          </div>
        </el-card>
      </template>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="props.wpId"
      sheet-name="A17-3-1"
      :project-id="props.projectId"
      class="gt-a1731__oo"
      @fallback="handleOOFallback"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useA1731ConsultationExecution } from './composables/useA1731ConsultationExecution'
import GtIndexChip from './GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA1731ConsultationExecution' })

const emit = defineEmits<{ 'switch-tab': [tabId: string] }>()

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>(), { projectId: '', readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const {
  loading,
  metaInfo,
  sections,
  a173Reference,
  saveStatus,
  lastSavedAt,
  loadData,
  updateMeta,
  updateSection,
  flushPendingSaves,
} = useA1731ConsultationExecution(wpIdRef)

// ─── Tab Switch (navigate to A17-3 within Bundle) ───
function switchToA173Tab() {
  emit('switch-tab', 'A17-3')
}

// ─── Section 三 Y/N State ───
const s3Agree = ref('Y')
const s3AgreeReason = ref('')
const s3Executed = ref('Y')
const s3ExecutedReason = ref('')

function saveS3() {
  // Persist Y/N state via composable's updateSection mechanism
  const combined = JSON.stringify({ agree: s3Agree.value, agreeReason: s3AgreeReason.value, executed: s3Executed.value, executedReason: s3ExecutedReason.value })
  updateSection(3, 'yn_state', combined)
}

// ─── AI Generate ───
const aiLoading = ref<number | null>(null)

async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '咨询事项描述', 2: '咨询回复意见', 3: '咨询结果执行情况', 4: '后续跟进事项',
  }
  const guidances: Record<number, string> = {
    1: '根据A17-3咨询事项，总结业务背景和问题要点。',
    2: '基于A17-3的回复意见，完整引用并整理要点。',
    3: '评估咨询结果的执行情况，说明是否一致、是否执行以及具体执行了哪些审计程序。',
    4: '根据执行情况，提出后续需要跟进的事项。',
  }
  aiLoading.value = section
  try {
    const { api } = await import('@/services/apiProxy')
    const existingContent = `A17-3摘要：${a173Reference.value?.overview || ''}\n问题：${a173Reference.value?.background || ''}`
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: section, chapter_title: titles[section] || '', guidance: guidances[section] || '',
      existing_content: existingContent, knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    switch (section) {
      case 1: updateSection(1, 'supplementary', content); break
      case 2: updateSection(2, 'execution_details', content); break
      case 3: updateSection(3, 'results', content); break
      case 4: updateSection(4, 'follow_up', content); break
    }
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

// ─── A17-3 Reference Refresh ───
async function refreshA173Reference() {
  if (!props.wpId) return
  try {
    await loadData(props.wpId)
    ElMessage.success('A17-3 数据已刷新')
  } catch { /* silent */ }
}

// ─── OO Health Check + Fallback ───
async function checkOOHealth() {
  try {
    const { default: http } = await import('@/utils/http')
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    const healthy = res?.data?.data?.healthy ?? res?.data?.healthy
    if (!healthy) modeOptions.value = ['结构化视图']
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

function handleOOFallback() {
  ElMessage.warning('OnlyOffice 编辑器加载失败，请尝试 docker restart audit-onlyoffice')
}

// ─── Lifecycle ───
onMounted(() => { checkOOHealth(); loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a1731 {
  padding: 16px;
  max-width: 900px;
}

.gt-a1731__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a1731__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a1731__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a1731__card {
  border-radius: 8px;
}

.gt-a1731__card--meta :deep(.el-card__body) {
  padding: 12px 16px;
}

.gt-a1731__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a1731__section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-a1731__meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.gt-a1731__meta-grid label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.gt-a1731__reference {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid #e4e7ed;
}

.gt-a1731__reference-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  font-weight: 500;
}

.gt-a1731__reference-content {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}

.gt-a1731__reference-field {
  margin-bottom: 4px;
}

.gt-a1731__reference-key {
  font-weight: 500;
  color: #303133;
}

.gt-a1731__reference-empty {
  color: #c0c4cc;
  font-style: italic;
}

.gt-a1731__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-a1731__label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
}

.gt-a1731__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}

/* 编制提示 */
.gt-a1731__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-a1731__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-a1731__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; }

/* Section actions */
.gt-a1731__section-actions { display: flex; align-items: center; gap: 8px; }

/* Sub-sections (三的子区块) */
.gt-a1731__sub-section { margin-bottom: 14px; padding-left: 12px; border-left: 3px solid #e4e7ed; }
.gt-a1731__sub-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.gt-a1731__sub-label { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; }
</style>
