<!--
  AgingConfigDialog.vue — 项目级账龄配置管理弹窗

  三种预设方案选择 + 自定义段编辑 + 科目级覆盖
  - 预设：3年段 / 5年段 / 自定义
  - 预设模式下展示只读段标签
  - 自定义模式下展示可编辑段列表 (add/remove 按钮, min 2 / max 10)
  - 实时校验：空名/重复名禁用确认按钮
  - subject-level override: D3/F1 可使用不同预设
  - 确认时检查段被移除是否导致数据丢失，弹确认警告
  - 保存成功后 dispatch EventBus + emit config-saved

  Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
-->

<template>
  <el-dialog
    :model-value="visible"
    title="账龄段配置"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @open="onDialogOpen"
  >
    <div v-loading="loading" class="aging-config-body">
      <!-- 左侧：预设方案选择 -->
      <div class="aging-presets-section">
        <div class="section-label">预设方案</div>
        <el-radio-group v-model="form.preset" @change="onPresetChange">
          <el-radio value="THREE_YEAR">3年段</el-radio>
          <el-radio value="FIVE_YEAR">5年段</el-radio>
          <el-radio value="CUSTOM">自定义</el-radio>
        </el-radio-group>

        <!-- 科目级覆盖 -->
        <div class="override-section">
          <div class="section-label" style="margin-top: 20px;">科目覆盖</div>
          <div class="override-tip">允许 D3(预收) / F1(预付) 使用不同预设</div>
          <div class="override-row">
            <span class="override-subject">D3 预收账款</span>
            <el-select
              v-model="form.subjectOverrides.D3"
              size="small"
              placeholder="跟随全局"
              clearable
              style="width: 120px;"
            >
              <el-option label="3年段" value="THREE_YEAR" />
              <el-option label="5年段" value="FIVE_YEAR" />
            </el-select>
          </div>
          <div class="override-row">
            <span class="override-subject">F1 预付款项</span>
            <el-select
              v-model="form.subjectOverrides.F1"
              size="small"
              placeholder="跟随全局"
              clearable
              style="width: 120px;"
            >
              <el-option label="3年段" value="THREE_YEAR" />
              <el-option label="5年段" value="FIVE_YEAR" />
            </el-select>
          </div>
        </div>
      </div>

      <!-- 右侧：段列表展示/编辑 -->
      <div class="aging-segments-section">
        <div class="section-label">
          账龄段列表
          <span v-if="form.preset !== 'CUSTOM'" class="readonly-badge">只读</span>
        </div>

        <!-- 预设模式：只读段标签 -->
        <div v-if="form.preset !== 'CUSTOM'" class="segment-readonly-list">
          <el-tag
            v-for="(seg, idx) in effectiveSegmentLabels"
            :key="idx"
            type="info"
            size="large"
            class="segment-tag"
          >
            {{ seg }}
          </el-tag>
        </div>

        <!-- 自定义模式：可编辑段列表 -->
        <div v-else class="segment-edit-list">
          <div
            v-for="(seg, idx) in form.customSegments"
            :key="idx"
            class="segment-edit-item"
          >
            <span class="segment-idx">{{ idx + 1 }}.</span>
            <el-input
              v-model="form.customSegments[idx]"
              size="small"
              placeholder="输入段名称"
              :class="{ 'is-error': errorIndices.has(idx) }"
              style="flex: 1;"
            />
            <el-button
              size="small"
              type="danger"
              link
              :disabled="form.customSegments.length <= 2"
              @click="removeSegment(idx)"
            >
              删除
            </el-button>
          </div>

          <!-- 错误提示 -->
          <div v-if="validationError" class="validation-error">{{ validationError }}</div>

          <!-- 新增按钮 -->
          <el-button
            size="small"
            :disabled="form.customSegments.length >= 10"
            class="add-segment-btn"
            @click="addSegment"
          >
            添加段
          </el-button>
          <div class="segment-count-tip">
            {{ form.customSegments.length }} / 10 段（最少 2 段）
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="!!validationError || saving"
        :loading="saving"
        @click="onConfirm"
      >
        确认保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  PRESET_SEGMENTS,
  invalidateAgingConfigCache,
  type AgingPreset,
} from '@/composables/useAgingConfig'

// ─── Props & Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'config-saved'): void
}>()

// ─── 内部状态 ─────────────────────────────────────────────────────────────────

const loading = ref(false)
const saving = ref(false)

/** 原始配置（用于变更检测） */
const originalSegmentLabels = ref<string[]>([])

const form = reactive({
  preset: 'FIVE_YEAR' as AgingPreset,
  customSegments: [] as string[],
  subjectOverrides: {} as Record<string, AgingPreset | ''>,
})

// ─── 计算属性 ─────────────────────────────────────────────────────────────────

/** 当前生效的段标签列表（预设模式下使用） */
const effectiveSegmentLabels = computed<string[]>(() => {
  if (form.preset === 'CUSTOM') {
    return form.customSegments
  }
  const presetSegs = PRESET_SEGMENTS[form.preset]
  return presetSegs ? presetSegs.map(s => s.label) : []
})

/** 校验错误索引集 */
const errorIndices = computed<Set<number>>(() => {
  if (form.preset !== 'CUSTOM') return new Set()
  const set = new Set<number>()
  const seen = new Map<string, number>()
  for (let i = 0; i < form.customSegments.length; i++) {
    const name = form.customSegments[i].trim()
    if (!name) {
      set.add(i)
    } else if (seen.has(name)) {
      set.add(i)
      set.add(seen.get(name)!)
    } else {
      seen.set(name, i)
    }
  }
  return set
})

/** 校验错误提示文本 */
const validationError = computed<string>(() => {
  if (form.preset !== 'CUSTOM') return ''
  if (form.customSegments.length < 2) return '至少需要 2 个账龄段'
  if (form.customSegments.length > 10) return '最多不超过 10 个账龄段'
  for (let i = 0; i < form.customSegments.length; i++) {
    if (!form.customSegments[i].trim()) return '段名称不能为空'
  }
  const names = form.customSegments.map(s => s.trim())
  if (new Set(names).size < names.length) return '段名称不能重复'
  return ''
})

// ─── 方法 ─────────────────────────────────────────────────────────────────────

/** 弹窗打开时加载当前配置 */
async function onDialogOpen() {
  loading.value = true
  try {
    const res = await api.get(
      `/api/projects/${props.projectId}/aging/config`,
      { _silent: true } as any,
    )
    form.preset = res.preset || 'FIVE_YEAR'
    // 设置 subject overrides
    form.subjectOverrides = { D3: '', F1: '', ...(res.subject_overrides || {}) }

    // 保存原始段标签（用于变更检测）
    if (res.effective_segments) {
      originalSegmentLabels.value = res.effective_segments.map((s: any) => s.label)
    }

    // 自定义段加载
    if (form.preset === 'CUSTOM' && res.effective_segments) {
      form.customSegments = res.effective_segments.map((s: any) => s.label)
    } else {
      // 预设模式下初始化自定义段为当前预设的段（方便切换到自定义时有默认值）
      const presetSegs = PRESET_SEGMENTS[form.preset]
      form.customSegments = presetSegs ? presetSegs.map(s => s.label) : []
    }
  } catch {
    // 加载失败：使用默认值
    form.preset = 'FIVE_YEAR'
    form.customSegments = PRESET_SEGMENTS.FIVE_YEAR.map(s => s.label)
    form.subjectOverrides = { D3: '', F1: '' }
    originalSegmentLabels.value = PRESET_SEGMENTS.FIVE_YEAR.map(s => s.label)
  } finally {
    loading.value = false
  }
}

/** 预设切换 */
function onPresetChange(val: AgingPreset) {
  if (val !== 'CUSTOM') {
    // 切换到预设时，同步自定义段列表为当前预设（便于后续切回自定义有默认值）
    const presetSegs = PRESET_SEGMENTS[val]
    if (presetSegs) {
      form.customSegments = presetSegs.map(s => s.label)
    }
  }
}

/** 添加段 */
function addSegment() {
  if (form.customSegments.length >= 10) return
  form.customSegments.push('')
}

/** 删除段 */
function removeSegment(idx: number) {
  if (form.customSegments.length <= 2) return
  form.customSegments.splice(idx, 1)
}

/** 构建保存 payload */
function buildPayload() {
  const overrides: Record<string, string> = {}
  if (form.subjectOverrides.D3) overrides.D3 = form.subjectOverrides.D3
  if (form.subjectOverrides.F1) overrides.F1 = form.subjectOverrides.F1

  const payload: any = {
    preset: form.preset,
    subject_overrides: overrides,
  }

  if (form.preset === 'CUSTOM') {
    // 为自定义段生成 key + dayFrom/dayTo（前端仅需保存 label，后端会生成完整字段）
    payload.custom_segments = form.customSegments.map((label, i) => ({
      key: `seg_custom_${i + 1}`,
      label: label.trim(),
      dayFrom: 0,
      dayTo: null,
    }))
  }

  return payload
}

/** 检测是否有段被移除（与原始配置对比） */
function hasRemovedSegments(): boolean {
  const newLabels = form.preset === 'CUSTOM'
    ? form.customSegments.map(s => s.trim())
    : (PRESET_SEGMENTS[form.preset]?.map(s => s.label) || [])

  const newSet = new Set(newLabels)
  return originalSegmentLabels.value.some(label => !newSet.has(label))
}

/** 确认保存 */
async function onConfirm() {
  if (validationError.value) return
  saving.value = true
  try {
    // 如果有段被移除，弹确认警告
    if (hasRemovedSegments()) {
      await ElMessageBox.confirm(
        '部分账龄段已被移除，对应的已填写数据将会丢失。是否继续保存？',
        '数据变更警告',
        {
          type: 'warning',
          confirmButtonText: '确认保存',
          cancelButtonText: '取消',
        },
      )
    }

    // 调用 PUT API
    const payload = buildPayload()
    await api.put(`/api/projects/${props.projectId}/aging/config`, payload)

    // 清除缓存
    invalidateAgingConfigCache(props.projectId)

    // 派发全局事件通知所有打开的底稿刷新
    window.dispatchEvent(new CustomEvent('aging-config:changed'))

    ElMessage.success('账龄段配置已保存')
    emit('config-saved')
    emit('update:visible', false)
  } catch (e: any) {
    if (e === 'cancel' || e?.toString() === 'cancel') {
      // 用户取消确认弹窗，不做处理
      return
    }
    // API 错误
    const detail = e?.response?.data?.detail || e?.response?.data?.data?.detail
    if (detail) {
      ElMessage.error(`保存失败：${detail}`)
    } else {
      ElMessage.error('保存失败，请重试')
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.aging-config-body {
  display: flex;
  gap: 28px;
  min-height: 320px;
}

/* 左侧预设选择区 */
.aging-presets-section {
  flex: 0 0 180px;
}

.section-label {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 10px;
  color: #303133;
}

.aging-presets-section .el-radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 科目覆盖区 */
.override-section {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.override-tip {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
}

.override-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.override-subject {
  font-size: 13px;
  color: #606266;
}

/* 右侧段列表区 */
.aging-segments-section {
  flex: 1;
  min-width: 0;
}

.readonly-badge {
  font-size: 11px;
  font-weight: normal;
  color: #909399;
  margin-left: 6px;
}

/* 只读段标签 */
.segment-readonly-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.segment-tag {
  font-size: 13px;
}

/* 可编辑段列表 */
.segment-edit-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.segment-edit-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.segment-idx {
  font-size: 12px;
  color: #909399;
  width: 20px;
  text-align: right;
}

.segment-edit-item .el-input.is-error :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

.validation-error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
}

.add-segment-btn {
  margin-top: 8px;
  align-self: flex-start;
}

.segment-count-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
