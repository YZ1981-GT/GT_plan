<template>
  <div class="h1-dep-actions">
    <div class="actions-row">
      <el-button size="small" type="primary" :disabled="isReadonly || importing" @click="emit('import-detail')">
        从 H1-2 带入
      </el-button>
      <el-button size="small" type="success" :disabled="isReadonly || importing" :loading="importing" @click="triggerFile">
        一键导入企业台账并测算
      </el-button>
      <el-dropdown :disabled="isReadonly || !hasRows" @command="onLinkCmd">
        <el-button size="small">跨表联动 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="h18">从 H1-8 带入处置日</el-dropdown-item>
            <el-dropdown-item command="h14">从 H1-14 带入减值</el-dropdown-item>
            <el-dropdown-item command="h17">从 H1-7 带入折旧起算</el-dropdown-item>
            <el-dropdown-item command="branch">按减值联动切分支</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown :disabled="isReadonly || !hasRows" @command="onSampleCmd">
        <el-button size="small">抽样 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="80">按原值覆盖 80% 抽样</el-dropdown-item>
            <el-dropdown-item command="90">按原值覆盖 90% 抽样</el-dropdown-item>
            <el-dropdown-item command="clear">恢复全量测算</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" :disabled="isReadonly || !hasRows" @click="emit('recalc')">重新测算</el-button>
      <el-button size="small" :disabled="isReadonly || !hasRows" @click="emit('draft-note')">生成说明草稿</el-button>
      <el-button size="small" :disabled="isReadonly" @click="emit('add-row')">+ 行</el-button>
      <input ref="fileRef" type="file" accept=".xlsx,.xls,.csv" class="hidden-file" @change="onFile" />
    </div>

    <el-alert
      v-if="recommendation"
      :type="recommendation.recommended === currentBranch ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="branch-alert"
    >
      <template #title>
        分支联动：推荐 <b>{{ branchLabel(recommendation.recommended) }}</b>
        （当前 {{ branchLabel(currentBranch) }}）— {{ recommendation.reason }}
      </template>
    </el-alert>

    <div v-if="dashboard" class="dash-bar">
      <el-tag size="small" type="info">{{ dashboard.watermarkLine }}</el-tag>
      <el-tag v-if="dashboard.sampleMode" size="small" type="warning">
        抽样中 覆盖{{ (dashboard.sampleCoverage * 100).toFixed(0) }}%
      </el-tag>
      <el-tag v-if="dashboard.beginAccFailCount" size="small" type="danger">
        期初累计异常 {{ dashboard.beginAccFailCount }}
      </el-tag>
      <el-tag v-if="dashboard.materialDiffCount" size="small" type="danger">
        重大差异 {{ dashboard.materialDiffCount }}
      </el-tag>
      <el-tag v-if="dashboard.reviewDiffCount" size="small" type="warning">
        待复核差异 {{ dashboard.reviewDiffCount }}
      </el-tag>
      <el-tag v-if="dashboard.nonStraightCount" size="small">
        非直线法 {{ dashboard.nonStraightCount }}
      </el-tag>
      <el-tag v-if="dashboard.taxWarnCount" size="small" type="info">
        税法年限提示 {{ dashboard.taxWarnCount }}
      </el-tag>
      <el-tag v-if="dashboard.disposalLinkedCount" size="small" type="success">
        已勾稽处置 {{ dashboard.disposalLinkedCount }}
      </el-tag>
      <el-tag v-if="dashboard.impairLinkedCount" size="small" type="success">
        已勾稽减值 {{ dashboard.impairLinkedCount }}
      </el-tag>
      <el-tag v-if="dashboard.additionLinkedCount" size="small" type="success">
        已勾稽增加起算 {{ dashboard.additionLinkedCount }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AdvancedDashboard, BranchRecommendation, DepreciationBranch } from '../../composables/useH1Depreciation'

defineProps<{
  isReadonly: boolean
  importing?: boolean
  hasRows: boolean
  currentBranch: DepreciationBranch
  recommendation?: BranchRecommendation | null
  dashboard?: AdvancedDashboard | null
}>()

const emit = defineEmits<{
  (e: 'import-detail'): void
  (e: 'import-file', file: File): void
  (e: 'recalc'): void
  (e: 'apply-branch'): void
  (e: 'add-row'): void
  (e: 'sync-h18'): void
  (e: 'sync-h14'): void
  (e: 'sync-h17'): void
  (e: 'sample', coverage: number): void
  (e: 'clear-sample'): void
  (e: 'draft-note'): void
}>()

const fileRef = ref<HTMLInputElement | null>(null)

function triggerFile() {
  fileRef.value?.click()
}

function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('import-file', file)
  input.value = ''
}

function onLinkCmd(cmd: string) {
  if (cmd === 'h18') emit('sync-h18')
  else if (cmd === 'h14') emit('sync-h14')
  else if (cmd === 'h17') emit('sync-h17')
  else if (cmd === 'branch') emit('apply-branch')
}

function onSampleCmd(cmd: string) {
  if (cmd === 'clear') emit('clear-sample')
  else emit('sample', Number(cmd) / 100)
}

function branchLabel(b: DepreciationBranch): string {
  return b === 'A' ? '不含减值' : b === 'B' ? '含减值' : '多次减值'
}
</script>

<style scoped>
.h1-dep-actions { margin-bottom: 12px; }
.actions-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.hidden-file { display: none; }
.branch-alert { margin-top: 4px; }
.branch-alert b { margin: 0 2px; }
.dash-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
</style>
