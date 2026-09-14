<template>
  <div class="h5-tab-policy-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：逐项检查油气资产会计政策是否符合 CAS27《石油天然气开采》要求（折耗方法、资本化条件、储量估计变更）。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.items.value.length }} 项</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-5 会计政策检查（CAS27 石油天然气开采）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-5')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-progress :percentage="state.completionRate.value" :stroke-width="6" class="progress-bar" />

      <div class="policy-list">
        <div v-for="item in state.items.value" :key="item.id" class="policy-item" :class="{ 'non-compliant': item.compliant === 'no' }">
          <div class="clause-header">
            <el-tag size="small" type="info">{{ item.clause }}</el-tag>
            <span class="clause-desc">{{ item.description }}</span>
          </div>
          <div class="clause-body">
            <el-radio-group v-model="item.compliant" size="small" :disabled="isReadonly"
              @change="state.updateItem(item.id, 'compliant', $event)">
              <el-radio-button value="yes">合规</el-radio-button>
              <el-radio-button value="no">不合规</el-radio-button>
              <el-radio-button value="na">不适用</el-radio-button>
            </el-radio-group>
            <el-input v-model="item.evidence" size="small" placeholder="审计证据/备注" :disabled="isReadonly" class="evidence-input"
              @change="state.updateItem(item.id, 'evidence', $event)" />
          </div>
        </div>
      </div>
    </el-card>

    <!-- 不合规项汇总 -->
    <el-alert v-if="state.nonCompliantItems.value.length > 0" type="error" :closable="false" show-icon>
      <template #title>
        {{ state.nonCompliantItems.value.length }} 项不合规：
        {{ state.nonCompliantItems.value.map(i => i.clause).join(', ') }}
      </template>
    </el-alert>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }"
        placeholder="填写会计政策检查审计说明..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="会计政策检查结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS27《石油天然气开采》核心条款逐项合规勾选</li>
        <li>重点关注：折耗方法(单位产量法)、资本化条件、储量估计变更</li>
        <li>不合规项需说明原因及建议的调整方案</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5PolicyCheck } from '../../composables/useH5PolicyCheck'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5PolicyCheck({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
})

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h5-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.progress-bar { margin-bottom: 16px; }
.policy-list { display: flex; flex-direction: column; gap: 12px; }
.policy-item { padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.policy-item.non-compliant { border-color: var(--el-color-danger-light-5); background: var(--el-color-danger-light-9); }
.clause-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.clause-desc { font-size: var(--wp-font-size, 13px); }
.clause-body { display: flex; align-items: center; gap: 12px; }
.evidence-input { flex: 1; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
