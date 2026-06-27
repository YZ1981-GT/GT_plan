<!--
  GtA176ClosingMeeting.vue — A17-6 总结会会议纪要

  极简专属组件：6 字段卡片 + 元信息区 + 双模式切换
  - 会议时间(datetime) / 参加人员(input) / 会议纪要(textarea 8行)
  - 结论(textarea 3行) / 附件(input)
  - 元信息：被审计单位/期间/编制人(自动) / 复核人 / 日期 / 索引号(A17-6只读)
  - 双模式: 结构化视图 / 在线编辑(GtOnlyOfficeSheet)
-->
<template>
  <div class="gt-a176">
    <!-- Mode Switch -->
    <div class="gt-a176__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
      />
      <span class="gt-a176__save-status">
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
    <div v-if="mode === '结构化视图'" class="gt-a176__content">
      <!-- Loading -->
      <el-skeleton v-if="loading" :rows="8" animated />

      <template v-else>
        <!-- Meta Info Card -->
        <el-card class="gt-a176__card gt-a176__card--meta" shadow="never">
          <template #header>
            <span class="gt-a176__card-title">编制信息</span>
          </template>
          <div class="gt-a176__meta-grid">
            <div class="gt-a176__meta-item">
              <label>被审计单位</label>
              <el-input
                :model-value="metaInfo.client_name"
                size="small"
                :disabled="props.readonly"
                placeholder="被审计单位"
                @change="(v: string) => updateMeta('client_name', v)"
              />
            </div>
            <div class="gt-a176__meta-item">
              <label>期间</label>
              <el-input
                :model-value="metaInfo.period"
                size="small"
                :disabled="props.readonly"
                placeholder="审计期间"
                @change="(v: string) => updateMeta('period', v)"
              />
            </div>
            <div class="gt-a176__meta-item">
              <label>编制人</label>
              <el-input
                :model-value="metaInfo.preparer"
                size="small"
                :disabled="props.readonly"
                placeholder="编制人"
                @change="(v: string) => updateMeta('preparer', v)"
              />
            </div>
            <div class="gt-a176__meta-item">
              <label>复核人</label>
              <el-input
                :model-value="metaInfo.reviewer"
                size="small"
                :disabled="props.readonly"
                placeholder="复核人"
                @change="(v: string) => updateMeta('reviewer', v)"
              />
            </div>
            <div class="gt-a176__meta-item">
              <label>日期</label>
              <el-date-picker
                :model-value="metaInfo.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="选择日期"
                @change="(v: string) => updateMeta('date', v || '')"
              />
            </div>
            <div class="gt-a176__meta-item">
              <label>索引号</label>
              <el-input model-value="A17-6" size="small" disabled />
            </div>
          </div>
        </el-card>

        <!-- Meeting Fields Card -->
        <el-card class="gt-a176__card" shadow="never">
          <template #header>
            <span class="gt-a176__card-title">总结会会议纪要</span>
          </template>

          <div class="gt-a176__fields">
            <!-- 会议时间 -->
            <div class="gt-a176__field">
              <label class="gt-a176__label">会议时间</label>
              <el-date-picker
                :model-value="fields.meeting_time"
                type="datetime"
                size="default"
                value-format="YYYY-MM-DD HH:mm"
                :disabled="props.readonly"
                placeholder="选择会议时间"
                style="width: 100%"
                @change="(v: string) => updateField('meeting_time', v || '')"
              />
            </div>

            <!-- 参加人员 -->
            <div class="gt-a176__field">
              <label class="gt-a176__label">参加人员</label>
              <el-input
                :model-value="fields.attendees"
                :disabled="props.readonly"
                placeholder="请填写参会人员"
                @change="(v: string) => updateField('attendees', v)"
              />
            </div>

            <!-- 会议纪要内容 -->
            <div class="gt-a176__field">
              <label class="gt-a176__label">会议纪要内容</label>
              <el-input
                :model-value="fields.minutes"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 20 }"
                :disabled="props.readonly"
                placeholder="请填写会议纪要内容"
                @change="(v: string) => updateField('minutes', v)"
              />
            </div>

            <!-- 结论 -->
            <div class="gt-a176__field">
              <label class="gt-a176__label">结论</label>
              <el-input
                :model-value="fields.conclusion"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 10 }"
                :disabled="props.readonly"
                placeholder="请填写结论"
                @change="(v: string) => updateField('conclusion', v)"
              />
            </div>

            <!-- 附件 -->
            <div class="gt-a176__field">
              <label class="gt-a176__label">附件</label>
              <el-input
                :model-value="fields.attachments"
                :disabled="props.readonly"
                placeholder="附件描述"
                @change="(v: string) => updateField('attachments', v)"
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
      sheet-name="A17-6"
      class="gt-a176__oo"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA176ClosingMeeting } from './composables/useA176ClosingMeeting'

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA176ClosingMeeting' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), { readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const {
  loading,
  metaInfo,
  fields,
  saveStatus,
  lastSavedAt,
  loadData,
  updateMeta,
  updateField,
  flushPendingSaves,
} = useA176ClosingMeeting(wpIdRef)

// ─── Lifecycle ───
onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a176 {
  padding: 16px;
  max-width: 900px;
}

.gt-a176__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a176__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a176__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a176__card {
  border-radius: 8px;
}

.gt-a176__card--meta :deep(.el-card__body) {
  padding: 12px 16px;
}

.gt-a176__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a176__meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.gt-a176__meta-grid label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.gt-a176__fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a176__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-a176__label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.gt-a176__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}
</style>
