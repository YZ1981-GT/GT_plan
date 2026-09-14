<!--
  GtA117CorrespondingData.vue — A1-17 对应数据程序表

  精美 HTML 专属组件：5 条审计程序步骤
  - 卡片式布局，每条步骤含：序号 + 程序描述 + 是否适用(Y/N/NA) + 执行人 + 执行情况说明 + 索引号
  - 自动保存到 checklist_responses
  - 自加载模式（仅需 wpId）
-->
<template>
  <div class="gt-a117">
    <!-- Loading -->
    <el-skeleton v-if="loading" :rows="6" animated />

    <!-- Error -->
    <div v-else-if="error" class="gt-a117__error">
      <el-icon :size="36" color="#f56c6c"><WarningFilled /></el-icon>
      <p>{{ error }}</p>
      <el-button type="primary" size="small" @click="loadData">重试</el-button>
    </div>

    <!-- Main Content -->
    <template v-else>
      <!-- Header -->
      <div class="gt-a117__header">
        <h3 class="gt-a117__title">对应数据程序表</h3>
        <span class="gt-a117__save-status">
          <template v-if="saving">
            <el-icon class="is-loading"><Loading /></el-icon> 保存中...
          </template>
          <template v-else-if="lastSavedAt">
            ○ 已保存 {{ savedAgoText }}
          </template>
        </span>
      </div>

      <p class="gt-a117__subtitle">考虑对应数据对审计报告的考虑：</p>

      <!-- Progress -->
      <div class="gt-a117__progress">
        <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
        <span class="gt-a117__progress-text">
          {{ filledCount }}/{{ STEPS.length }} 已完成
        </span>
      </div>

      <!-- Step Cards -->
      <div class="gt-a117__cards">
        <div
          v-for="step in STEPS"
          :key="step.id"
          :class="['gt-a117__card', getCardClass(step.id)]"
        >
          <div class="gt-a117__card-header">
            <span class="gt-a117__card-seq">{{ step.seq }}</span>
            <span class="gt-a117__card-desc">{{ step.description }}</span>
          </div>

          <div class="gt-a117__card-fields">
            <!-- 是否适用 -->
            <div class="gt-a117__field">
              <label class="gt-a117__field-label">是否适用</label>
              <div class="gt-a117__btn-group">
                <el-button
                  v-for="opt in ['Y', 'N', 'NA']"
                  :key="opt"
                  :type="getButtonType(step.id, opt)"
                  :plain="responses[step.id]?.applicable !== opt"
                  size="small"
                  :disabled="props.readonly"
                  @click="updateField(step.id, 'applicable', responses[step.id]?.applicable === opt ? '' : opt)"
                >
                  {{ opt === 'NA' ? '不适用' : opt === 'Y' ? '是' : '否' }}
                </el-button>
              </div>
            </div>

            <!-- 执行人 -->
            <div class="gt-a117__field">
              <label class="gt-a117__field-label">执行人</label>
              <el-input
                :model-value="responses[step.id]?.executor || ''"
                placeholder="执行人"
                size="small"
                :disabled="props.readonly"
                class="gt-a117__field-input"
                @blur="(e: FocusEvent) => updateField(step.id, 'executor', (e.target as HTMLInputElement)?.value || '')"
              />
            </div>

            <!-- 执行情况说明 -->
            <div class="gt-a117__field gt-a117__field--wide">
              <label class="gt-a117__field-label">执行情况说明</label>
              <el-input
                :model-value="responses[step.id]?.description || ''"
                type="textarea"
                :rows="2"
                placeholder="请填写执行情况"
                :disabled="props.readonly"
                @blur="(e: FocusEvent) => updateField(step.id, 'description', (e.target as HTMLInputElement)?.value || '')"
              />
            </div>

            <!-- 索引号 -->
            <div class="gt-a117__field">
              <label class="gt-a117__field-label">索引号</label>
              <el-input
                :model-value="responses[step.id]?.ref_index || ''"
                placeholder="索引号"
                size="small"
                :disabled="props.readonly"
                class="gt-a117__field-input gt-a117__field-input--short"
                @blur="(e: FocusEvent) => updateField(step.id, 'ref_index', (e.target as HTMLInputElement)?.value || '')"
              />
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

defineOptions({ name: 'GtA117CorrespondingData' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), { readonly: false })

// ─── Static Steps (from template) ───
interface Step {
  id: string
  seq: string
  description: string
}

const STEPS: Step[] = [
  { id: 'step-1', seq: '1', description: '如果以前针对上期财务报表发表了保留意见、无法表示意见或否定意见，且导致非无保留意见的事项仍未解决，对本期审计报告的影响。' },
  { id: 'step-1.1', seq: '1.1', description: '如果未解决事项对本期数据的影响或可能的影响是重大的，在导致非无保留意见事项段中同时提及本期数据和对应数据。' },
  { id: 'step-1.2', seq: '1.2', description: '如果未解决事项对本期数据的影响或可能的影响不重大，说明由于未解决事项对本期数据和对应数据之间的可比性可能产生的影响。' },
  { id: 'step-2', seq: '2', description: '如果已经获取上期财务报表存在重大错报的审计证据，而以前对该财务报表发表了无保留意见，且对应数据未经适当重述和充分披露，对本期审计报告的影响。' },
  { id: 'step-3', seq: '3', description: '如果上期财务报表未经审计，在审计报告的其他事项段中说明对应数据未经审计。' },
]

// ─── State ───
interface StepResponse {
  applicable: string  // 'Y' | 'N' | 'NA' | ''
  executor: string
  description: string
  ref_index: string
}

const loading = ref(false)
const error = ref<string | null>(null)
const saving = ref(false)
const lastSavedAt = ref<Date | null>(null)
const responses = ref<Record<string, StepResponse>>({})

// ─── Debounce Save ───
let saveTimer: ReturnType<typeof setTimeout> | null = null
const pendingIds = new Set<string>()

// ─── Load Data ───
async function loadData() {
  if (!props.wpId) return
  loading.value = true
  error.value = null
  try {
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=a1-17-corresponding-data`,
      { _silent: true } as any,
    )
    const htmlData = res?.sheets?.[0]?.html_data ?? res
    if (htmlData?.responses) {
      responses.value = htmlData.responses
    }
  } catch {
    // API 失败不阻塞渲染——步骤是静态的，仅 responses 为空态
  } finally {
    loading.value = false
  }
}

// ─── Update Field ───
function updateField(stepId: string, field: keyof StepResponse, value: string) {
  if (props.readonly) return
  if (!responses.value[stepId]) {
    responses.value[stepId] = { applicable: '', executor: '', description: '', ref_index: '' }
  }
  ;(responses.value[stepId] as any)[field] = value
  pendingIds.add(stepId)
  scheduleSave()
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
}

async function doSave(retryCount = 0) {
  if (pendingIds.size === 0) return
  const ids = [...pendingIds]
  pendingIds.clear()
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      items: ids.map(id => ({
        item_id: id,
        conclusion: responses.value[id]?.applicable || null,
        remark: JSON.stringify({
          executor: responses.value[id]?.executor || '',
          description: responses.value[id]?.description || '',
          ref_index: responses.value[id]?.ref_index || '',
        }),
        wp_ref: responses.value[id]?.ref_index || null,
      })),
    })
    lastSavedAt.value = new Date()
  } catch {
    if (retryCount < 3) {
      for (const id of ids) pendingIds.add(id)
      setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
      return
    }
  } finally {
    saving.value = false
  }
}

// ─── Computed ───
const filledCount = computed(() =>
  STEPS.filter(s => responses.value[s.id]?.applicable).length
)
const progressPercent = computed(() =>
  Math.round((filledCount.value / STEPS.length) * 100)
)

function getCardClass(stepId: string): string {
  const r = responses.value[stepId]
  if (!r?.applicable) return ''
  if (r.applicable === 'Y') return 'gt-a117__card--yes'
  if (r.applicable === 'N') return 'gt-a117__card--no'
  return 'gt-a117__card--na'
}

function getButtonType(stepId: string, opt: string): string {
  const r = responses.value[stepId]
  if (r?.applicable !== opt) return 'default'
  if (opt === 'Y') return 'success'
  if (opt === 'N') return 'danger'
  return 'info'
}

// ─── Save Indicator ───
const savedAgoText = ref('')
let savedAgoTimer: ReturnType<typeof setInterval> | null = null

function updateSavedAgo() {
  if (!lastSavedAt.value) { savedAgoText.value = ''; return }
  const diff = Math.floor((Date.now() - lastSavedAt.value.getTime()) / 1000)
  savedAgoText.value = diff < 60 ? `${diff}秒前` : `${Math.floor(diff / 60)}分钟前`
}

// ─── Lifecycle ───
onMounted(() => {
  loadData()
  savedAgoTimer = setInterval(updateSavedAgo, 1000)
})

onBeforeUnmount(() => {
  if (saveTimer) { clearTimeout(saveTimer); doSave() }
  if (savedAgoTimer) clearInterval(savedAgoTimer)
})

defineExpose({ reload: loadData })
</script>

<style scoped>
.gt-a117 {
  padding: 20px;
  max-width: 900px;
}

.gt-a117__error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 40px;
  color: #909399;
}

.gt-a117__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.gt-a117__title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.gt-a117__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a117__subtitle {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin: 0 0 12px;
}

.gt-a117__progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.gt-a117__progress .el-progress {
  flex: 1;
  max-width: 300px;
}

.gt-a117__progress-text {
  font-size: 12px;
  color: #909399;
}

.gt-a117__cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-a117__card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px 20px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.gt-a117__card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.gt-a117__card--yes {
  border-left: 4px solid #67c23a;
}

.gt-a117__card--no {
  border-left: 4px solid #f56c6c;
}

.gt-a117__card--na {
  border-left: 4px solid #909399;
  opacity: 0.7;
}

.gt-a117__card-header {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.gt-a117__card-seq {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #7c3aed;
  color: #fff;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.gt-a117__card-desc {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
}

.gt-a117__card-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
}

.gt-a117__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gt-a117__field--wide {
  flex: 1;
  min-width: 250px;
}

.gt-a117__field-label {
  font-size: 11px;
  color: #909399;
  font-weight: 500;
}

.gt-a117__btn-group {
  display: flex;
  gap: 4px;
}

.gt-a117__field-input {
  width: 120px;
}

.gt-a117__field-input--short {
  width: 80px;
}
</style>
