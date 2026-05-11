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
          <el-link
            class="error-code"
            type="primary"
            :underline="false"
            @click="goToRule(error.code)"
          >
            {{ error.code }}
          </el-link>
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

        <!-- 6.13: 展示 hint 字段（title/description/suggestions from error_hints.py） -->
        <div v-if="error.hint" class="error-hint-block">
          <div v-if="error.hint.title" class="hint-title">
            <el-icon><InfoFilled /></el-icon>
            <strong>{{ error.hint.title }}</strong>
          </div>
          <div v-if="error.hint.description" class="hint-description">
            {{ error.hint.description }}
          </div>
          <div v-if="error.hint.suggestions?.length" class="hint-suggestions">
            <span class="hint-suggestions-label">建议操作：</span>
            <ul>
              <li v-for="(s, sIdx) in error.hint.suggestions" :key="sIdx">{{ s }}</li>
            </ul>
          </div>
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
import { useRouter } from 'vue-router'
import { Location, InfoFilled } from '@element-plus/icons-vue'
import type { ImportError } from './LedgerImportDialog.vue'

const router = useRouter()

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

function goToRule(code: string) {
  const route = router.resolve({ path: '/ledger-import/validation-rules', hash: `#${code}` })
  window.open(route.href, '_blank')
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
  cursor: pointer;
}

.error-code:hover {
  text-decoration: underline;
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

.error-hint-block {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
}

.hint-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}

.hint-description {
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  margin-bottom: 6px;
}

.hint-suggestions {
  font-size: 12px;
}

.hint-suggestions-label {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.hint-suggestions ul {
  margin: 4px 0 0 16px;
  padding: 0;
  list-style: disc;
}

.hint-suggestions li {
  color: var(--el-color-primary);
  line-height: 1.6;
}
</style>
