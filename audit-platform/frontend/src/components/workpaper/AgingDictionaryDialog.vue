<!--
  AgingDictionaryDialog.vue — 账龄段枚举字典设置弹窗

  左侧预设方案选择 + 右侧可编辑段列表。
  - 预设：三年段/五年段/自定义
  - 右侧段列表：输入框+删除按钮，底部新增按钮
  - 实时校验：空名/重复名标红
  - 确认保存时若有已填金额，弹二次确认
  Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.10
-->

<template>
  <el-dialog
    :model-value="visible"
    title="账龄段设置"
    width="640px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="aging-dict-body">
      <!-- 左侧：预设方案 -->
      <div class="aging-presets">
        <div class="aging-presets-label">预设方案</div>
        <el-radio-group v-model="preset" @change="onPresetChange">
          <el-radio value="THREE_YEAR">三年段</el-radio>
          <el-radio value="FIVE_YEAR">五年段</el-radio>
          <el-radio value="CUSTOM">自定义</el-radio>
        </el-radio-group>
      </div>

      <!-- 右侧：段列表编辑 -->
      <div class="aging-segments">
        <div class="aging-segments-label">账龄段列表</div>
        <div class="aging-segment-list">
          <div
            v-for="(seg, idx) in segments"
            :key="idx"
            class="aging-segment-item"
          >
            <el-input
              v-model="segments[idx]"
              size="small"
              placeholder="输入段名"
              :class="{ 'is-error': hasError(idx) }"
              @input="onSegmentInput"
            />
            <el-button
              size="small"
              type="danger"
              link
              :disabled="segments.length <= 1"
              @click="removeSegment(idx)"
            >删除</el-button>
          </div>
        </div>
        <div v-if="errorTip" class="aging-error-tip">{{ errorTip }}</div>
        <el-button size="small" @click="addSegment" class="aging-add-btn">新增</el-button>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!!errorTip" @click="onConfirm">确认保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

const PRESETS: Record<string, string[]> = {
  THREE_YEAR: ['1年以内', '1-2年', '2-3年', '3年以上'],
  FIVE_YEAR: ['1年以内', '1-2年', '2-3年', '3-4年', '4-5年', '5年以上'],
}

const props = defineProps<{
  visible: boolean
  wpId: string
}>()

const emit = defineEmits<{
  (e: 'saved', segments: string[]): void
  (e: 'update:visible', val: boolean): void
}>()

const preset = ref<string>('THREE_YEAR')
const segments = reactive<string[]>([...PRESETS.THREE_YEAR])
const saving = ref(false)

// 加载已有配置
watch(() => props.visible, async (val) => {
  if (!val) return
  try {
    const config = await api.get(`/api/workpapers/${props.wpId}/bad-debt-rows/aging-segments`)
    if (config && config.segments && config.segments.length > 0) {
      preset.value = config.preset || 'CUSTOM'
      segments.splice(0, segments.length, ...config.segments)
    }
  } catch {
    // 不存在配置时使用默认
  }
})

function onPresetChange(val: string) {
  if (val !== 'CUSTOM' && PRESETS[val]) {
    segments.splice(0, segments.length, ...PRESETS[val])
  }
}

function onSegmentInput() {
  // 用户编辑后切换到自定义
  preset.value = 'CUSTOM'
}

function addSegment() {
  segments.push('')
  preset.value = 'CUSTOM'
}

function removeSegment(idx: number) {
  segments.splice(idx, 1)
  preset.value = 'CUSTOM'
}

// 校验逻辑
const errorIndices = computed<Set<number>>(() => {
  const set = new Set<number>()
  const seen = new Map<string, number>()
  for (let i = 0; i < segments.length; i++) {
    const name = segments[i].trim()
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

const errorTip = computed<string>(() => {
  for (let i = 0; i < segments.length; i++) {
    if (!segments[i].trim()) return '段名不能为空'
  }
  const names = segments.map(s => s.trim())
  const unique = new Set(names)
  if (unique.size < names.length) return '段名不能重复'
  return ''
})

function hasError(idx: number): boolean {
  return errorIndices.value.has(idx)
}

async function onConfirm() {
  if (errorTip.value) return
  saving.value = true
  try {
    // 检查是否有已填金额
    const { has_amounts } = await api.get(
      `/api/workpapers/${props.wpId}/bad-debt-rows/aging-segments/has-amounts`
    )
    if (has_amounts) {
      await ElMessageBox.confirm(
        '当前账龄段已有填写的金额数据，修改账龄段将清空这些数据。是否继续？',
        '警告',
        { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' }
      )
    }
    // 保存
    const trimmed = segments.map(s => s.trim())
    await api.put(`/api/workpapers/${props.wpId}/bad-debt-rows/aging-segments`, {
      preset: preset.value,
      segments: trimmed,
    })
    ElMessage.success('账龄段配置已保存')
    emit('saved', trimmed)
    emit('update:visible', false)
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      // 不是用户取消
      if (e?.response?.data?.detail) {
        ElMessage.error(e.response.data.detail)
      }
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.aging-dict-body {
  display: flex;
  gap: 24px;
  min-height: 260px;
}
.aging-presets {
  flex: 0 0 140px;
}
.aging-presets-label,
.aging-segments-label {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
  color: #333;
}
.aging-presets .el-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.aging-segments {
  flex: 1;
}
.aging-segment-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
}
.aging-segment-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.aging-segment-item .el-input.is-error :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
.aging-error-tip {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
}
.aging-add-btn {
  margin-top: 8px;
}
</style>
