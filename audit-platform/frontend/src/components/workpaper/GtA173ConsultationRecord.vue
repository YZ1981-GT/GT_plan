<!--
  GtA173ConsultationRecord.vue — A17-3 业务咨询记录

  专属组件：元信息表 + 4 章卡片 + 双模式切换
  - 元信息：业务部门/客户名称(自动)/咨询类型(el-select)/审计期间(自动)
  - Section 一：咨询事项(业务概况+问题背景+相关文件tag) + AI按钮(disabled)
  - Section 二：项目组初步讨论意见(textarea)
  - Section 三：专业技术部反馈(准则依据+回复意见)
  - Section 四：专业技术委员会意见及所外咨询回复(textarea)
  - 双模式: 结构化视图 / 在线编辑(GtOnlyOfficeSheet)
-->
<template>
  <div class="gt-a173">
    <!-- Mode Switch -->
    <div class="gt-a173__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
      />
      <span class="gt-a173__save-status">
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
    <div v-if="mode === '结构化视图'" class="gt-a173__content">
      <!-- Loading -->
      <el-skeleton v-if="loading" :rows="10" animated />

      <template v-else>
        <!-- Meta Info Card -->
        <el-card class="gt-a173__card gt-a173__card--meta" shadow="never">
          <template #header>
            <span class="gt-a173__card-title">编制信息</span>
          </template>
          <div class="gt-a173__meta-grid">
            <div class="gt-a173__meta-item">
              <label>业务部门</label>
              <el-input
                :model-value="metaInfo.department"
                size="small"
                :disabled="props.readonly"
                placeholder="业务部门"
                @change="(v: string) => updateMeta('department', v)"
              />
            </div>
            <div class="gt-a173__meta-item">
              <label>客户名称</label>
              <el-input
                :model-value="metaInfo.client_name"
                size="small"
                :disabled="props.readonly"
                placeholder="客户名称（自动填充）"
                @change="(v: string) => updateMeta('client_name', v)"
              />
            </div>
            <div class="gt-a173__meta-item">
              <label>咨询类型</label>
              <el-select
                :model-value="metaInfo.consult_type"
                size="small"
                :disabled="props.readonly"
                placeholder="选择咨询类型"
                @change="(v: string) => updateMeta('consult_type', v)"
              >
                <el-option
                  v-for="opt in consultTypeOptions"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
            </div>
            <div class="gt-a173__meta-item">
              <label>审计期间</label>
              <el-input
                :model-value="metaInfo.period"
                size="small"
                :disabled="props.readonly"
                placeholder="审计期间（自动填充）"
                @change="(v: string) => updateMeta('period', v)"
              />
            </div>
          </div>
        </el-card>

        <!-- Section 一：咨询事项 -->
        <el-card class="gt-a173__card" shadow="never">
          <template #header>
            <div class="gt-a173__card-header">
              <span class="gt-a173__card-title">一、咨询事项描述</span>
              <el-tooltip content="AI 根据咨询问题自动查询相关准则即将上线" placement="top">
                <el-button size="small" type="primary" disabled>
                  <el-icon><MagicStick /></el-icon> AI 准则查询
                </el-button>
              </el-tooltip>
            </div>
          </template>

          <div class="gt-a173__fields">
            <!-- 业务概况 -->
            <div class="gt-a173__field">
              <label class="gt-a173__label">业务概况</label>
              <el-input
                :model-value="sections[1].overview"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 12 }"
                :disabled="props.readonly"
                placeholder="请描述被审计单位的业务概况及咨询事项背景"
                @change="(v: string) => updateSection(1, 'overview', v)"
              />
            </div>

            <!-- 问题背景 -->
            <div class="gt-a173__field">
              <label class="gt-a173__label">问题背景</label>
              <el-input
                :model-value="sections[1].background"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 12 }"
                :disabled="props.readonly"
                placeholder="请描述需要咨询的具体问题及背景"
                @change="(v: string) => updateSection(1, 'background', v)"
              />
            </div>

            <!-- 相关文件 (file tags) -->
            <div class="gt-a173__field">
              <label class="gt-a173__label">相关文件</label>
              <div class="gt-a173__file-tags">
                <el-tag
                  v-for="(file, idx) in sections[1].files"
                  :key="idx"
                  :closable="!props.readonly"
                  size="default"
                  @close="removeFileTag(idx)"
                >
                  {{ file }}
                </el-tag>
                <el-input
                  v-if="!props.readonly"
                  v-model="newFileTag"
                  size="small"
                  class="gt-a173__file-input"
                  placeholder="输入文件名后回车"
                  @keyup.enter="handleAddFileTag"
                />
              </div>
            </div>
          </div>
        </el-card>

        <!-- Section 二：项目组初步讨论意见 -->
        <el-card class="gt-a173__card" shadow="never">
          <template #header>
            <span class="gt-a173__card-title">二、项目组初步讨论意见</span>
          </template>

          <div class="gt-a173__fields">
            <div class="gt-a173__field">
              <el-input
                :model-value="sections[2].opinion"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 16 }"
                :disabled="props.readonly"
                placeholder="请填写项目组初步讨论意见"
                @change="(v: string) => updateSection(2, 'opinion', v)"
              />
            </div>
          </div>
        </el-card>

        <!-- Section 三：专业技术部反馈 -->
        <el-card class="gt-a173__card" shadow="never">
          <template #header>
            <span class="gt-a173__card-title">三、专业技术部反馈</span>
          </template>

          <div class="gt-a173__fields">
            <div class="gt-a173__field">
              <label class="gt-a173__label">准则依据</label>
              <el-input
                :model-value="sections[3].standards"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 12 }"
                :disabled="props.readonly"
                placeholder="引用的会计准则/审计准则条款"
                @change="(v: string) => updateSection(3, 'standards', v)"
              />
            </div>
            <div class="gt-a173__field">
              <label class="gt-a173__label">回复意见</label>
              <el-input
                :model-value="sections[3].reply"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 12 }"
                :disabled="props.readonly"
                placeholder="专业技术部回复意见"
                @change="(v: string) => updateSection(3, 'reply', v)"
              />
            </div>
          </div>
        </el-card>

        <!-- Section 四：专业技术委员会意见及所外咨询回复 -->
        <el-card class="gt-a173__card" shadow="never">
          <template #header>
            <span class="gt-a173__card-title">四、专业技术委员会意见及所外咨询回复</span>
          </template>

          <div class="gt-a173__fields">
            <div class="gt-a173__field">
              <el-input
                :model-value="sections[4].opinion"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 16 }"
                :disabled="props.readonly"
                placeholder="请填写专业技术委员会意见或所外咨询回复"
                @change="(v: string) => updateSection(4, 'opinion', v)"
              />
            </div>
          </div>
        </el-card>
      </template>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="props.wpId"
      sheet-name="A17-3"
      class="gt-a173__oo"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, MagicStick } from '@element-plus/icons-vue'
import {
  useA173ConsultationRecord,
  CONSULT_TYPE_OPTIONS,
} from './composables/useA173ConsultationRecord'

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA173ConsultationRecord' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), { readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const consultTypeOptions = CONSULT_TYPE_OPTIONS

const {
  loading,
  metaInfo,
  sections,
  saveStatus,
  lastSavedAt,
  loadData,
  updateMeta,
  updateSection,
  addFileTag,
  removeFileTag,
  flushPendingSaves,
} = useA173ConsultationRecord(wpIdRef)

// ─── File Tag Input ───
const newFileTag = ref('')

function handleAddFileTag() {
  if (newFileTag.value.trim()) {
    addFileTag(newFileTag.value)
    newFileTag.value = ''
  }
}

// ─── Lifecycle ───
onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a173 {
  padding: 16px;
  max-width: 900px;
}

.gt-a173__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a173__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a173__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a173__card {
  border-radius: 8px;
}

.gt-a173__card--meta :deep(.el-card__body) {
  padding: 12px 16px;
}

.gt-a173__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gt-a173__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a173__meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.gt-a173__meta-grid label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.gt-a173__fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a173__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-a173__label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.gt-a173__file-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.gt-a173__file-input {
  width: 200px;
}

.gt-a173__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}
</style>
