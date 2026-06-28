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
              <label>复核人</label>
              <el-input
                :model-value="metaInfo.reviewer"
                size="small"
                :disabled="props.readonly"
                placeholder="复核人"
                @change="(v: string) => updateMeta('reviewer', v)"
              />
            </div>
          </div>
        </el-card>

        <!-- Section 一: A17-3 引用 + 补充说明 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <div class="gt-a1731__section-header">
              <span class="gt-a1731__card-title">一、咨询事项描述</span>
              <GtIndexChip wp-code="A17-3" label="A17-3" />
            </div>
          </template>

          <!-- A17-3 Reference Area (read-only) -->
          <div class="gt-a1731__reference">
            <div class="gt-a1731__reference-label">A17-3 咨询事项摘要（只读）</div>
            <div class="gt-a1731__reference-content">
              <div v-if="a173Reference.overview" class="gt-a1731__reference-field">
                <span class="gt-a1731__reference-key">业务概况：</span>
                <span>{{ a173Reference.overview }}</span>
              </div>
              <div v-if="a173Reference.background" class="gt-a1731__reference-field">
                <span class="gt-a1731__reference-key">问题背景：</span>
                <span>{{ a173Reference.background }}</span>
              </div>
              <div v-if="!a173Reference.overview && !a173Reference.background" class="gt-a1731__reference-empty">
                暂无 A17-3 咨询事项数据
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

        <!-- Section 二: 执行情况 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <span class="gt-a1731__card-title">二、咨询结果</span>
          </template>
          <div class="gt-a1731__field">
            <el-input
              :model-value="sections[2].execution_details"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 15 }"
              :disabled="props.readonly"
              placeholder="请填写咨询结果"
              @change="(v: string) => updateSection(2, 'execution_details', v)"
            />
          </div>
        </el-card>

        <!-- Section 三: 执行结果 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <span class="gt-a1731__card-title">三、执行情况</span>
          </template>
          <div class="gt-a1731__field">
            <el-input
              :model-value="sections[3].results"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 15 }"
              :disabled="props.readonly"
              placeholder="请填写执行情况"
              @change="(v: string) => updateSection(3, 'results', v)"
            />
          </div>
        </el-card>

        <!-- Section 四: 后续跟进 -->
        <el-card class="gt-a1731__card" shadow="never">
          <template #header>
            <span class="gt-a1731__card-title">四、后续跟进</span>
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
  font-size: 13px;
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
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.gt-a1731__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}
</style>
