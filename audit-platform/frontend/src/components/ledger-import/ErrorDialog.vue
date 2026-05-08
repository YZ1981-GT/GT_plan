<template>
  <el-dialog
    v-model="dialogVisible"
    title="导入错误详情"
    width="700px"
    append-to-body
    destroy-on-close
  >
    <!-- 按严重级别分 Tab -->
    <el-tabs v-model="activeTab">
      <el-tab-pane v-if="fatalErrors.length > 0" name="fatal">
        <template #label>
          <el-badge :value="fatalErrors.length" type="danger">
            致命错误
          </el-badge>
        </template>
      </el-tab-pane>
      <el-tab-pane v-if="blockingErrors.length > 0" name="blocking">
        <template #label>
          <el-badge :value="blockingErrors.length" type="warning">
            阻塞错误
          </el-badge>
        </template>
      </el-tab-pane>
      <el-tab-pane v-if="warningErrors.length > 0" name="warning">
        <template #label>
          <el-badge :value="warningErrors.length">
            警告
          </el-badge>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 错误列表 -->
    <div class="error-list">
      <div
        v-for="(error, idx) in currentErrors"
        :key="idx"
        class="error-item"
        :class="`severity-${error.severity}`"
      >
        <div class="error-header">
          <el-tag
            :type="getSeverityTagType(error.severity)"
            size="small"
            effect="dark"
          >
            {{ getSeverityLabel(error.severity) }}
          </el-tag>
          <span class="error-code">{{ error.code }}</span>
        </div>

        <div class="error-message">{{ error.message }}</div>

        <div v-if="error.file || error.sheet || error.row || error.column" class="error-location">
          <el-icon><Location /></el-icon>
          <span v-if="error.file">文件: {{ error.file }}</span>
          <span v-if="error.sheet"> / Sheet: {{ error.sheet }}</span>
          <span v-if="error.row"> / 行: {{ error.row }}</span>
          <span v-if="error.column"> / 列: {{ error.column }}</span>
        </div>

        <div v-if="error.suggestion" class="error-suggestion">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ error.suggestion }}</span>
        </div>
      </div>

      <el-empty v-if="currentErrors.length === 0" description="无错误" />
    </div>

    <template #footer>
      <el-button aria-label="关闭错误详情" @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Location, InfoFilled } from '@element-plus/icons-vue'
import type { ImportError } from './LedgerImportDialog.vue'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  errors: ImportError[]
  visible: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const activeTab = ref('fatal')

const dialogVisible = computed({
  get: () => props.visible,
  set: (val: boolean) => emit('update:visible', val),
})

// ─── Computed ───────────────────────────────────────────────────────────────

const fatalErrors = computed(() =>
  props.errors.filter(e => e.severity === 'fatal')
)

const blockingErrors = computed(() =>
  props.errors.filter(e => e.severity === 'blocking')
)

const warningErrors = computed(() =>
  props.errors.filter(e => e.severity === 'warning')
)

const currentErrors = computed(() => {
  switch (activeTab.value) {
    case 'fatal': return fatalErrors.value
    case 'blocking': return blockingErrors.value
    case 'warning': return warningErrors.value
    default: return props.errors
  }
})

// ─── Methods ────────────────────────────────────────────────────────────────

function getSeverityTagType(severity: string): 'danger' | 'warning' | 'info' {
  switch (severity) {
    case 'fatal': return 'danger'
    case 'blocking': return 'warning'
    default: return 'info'
  }
}

function getSeverityLabel(severity: string): string {
  switch (severity) {
    case 'fatal': return '致命'
    case 'blocking': return '阻塞'
    case 'warning': return '警告'
    default: return severity
  }
}
</script>

<style scoped>
.error-list {
  max-height: 400px;
  overflow-y: auto;
}

.error-item {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 4px;
  border-left: 4px solid;
}

.error-item.severity-fatal {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.error-item.severity-blocking {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.error-item.severity-warning {
  border-left-color: var(--el-color-info);
  background: var(--el-color-info-light-9);
}

.error-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.error-code {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.error-message {
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 6px;
}

.error-location {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.error-suggestion {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 12px;
  color: var(--el-color-primary);
  margin-top: 4px;
}
</style>
