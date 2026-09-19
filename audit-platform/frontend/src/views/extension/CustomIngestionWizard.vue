<script setup lang="ts">
/**
 * 自定义模板摄取向导（Task 12）—— 三入口 + F-SHELL 门控。
 * candidate 仅静态预览；ACTIVE 后才注册 host facts。
 */
import { computed } from 'vue'
import {
  entrySuccessMessage,
  useCustomIngestionWizard,
  type IngestionEntryKind,
} from '@/composables/useCustomIngestionWizard'

const wizard = useCustomIngestionWizard()
const entries: { kind: IngestionEntryKind; title: string; desc: string }[] = [
  {
    kind: 'batch_blank',
    title: '批量空白底稿',
    desc: '不上传文件，仅建立批量编制入口；成功 ≠ 发布',
  },
  {
    kind: 'metadata_only',
    title: '仅元数据',
    desc: '登记模板说明，不进入正式摄取 / publication',
  },
  {
    kind: 'ingest_excel',
    title: '摄取 Excel',
    desc: 'multipart 进入隔离区；需 preflight / 审批 / finalize 后才 ACTIVE',
  },
]

const statusText = computed(() => {
  const s = wizard.state.value
  if (!wizard.fshell.ok) return 'F-SHELL 门控未通过'
  if (s.phase === 'active') return '已 ACTIVE（可注册 host facts）'
  if (s.phase === 'candidate_preview') return '候选静态预览（禁止生产 OO/WOPI）'
  if (s.phase === 'blocked') return '已阻断'
  if (s.entry) return entrySuccessMessage(s.entry)
  return '请选择入口'
})

function onSelect(kind: IngestionEntryKind) {
  wizard.selectEntry(kind)
  if (kind === 'ingest_excel') {
    wizard.markCandidatePreview()
  }
}
</script>

<template>
  <div class="gt-custom-ingestion-wizard" data-testid="custom-ingestion-wizard">
    <header class="gt-custom-ingestion-wizard__head">
      <h2>自定义模板摄取</h2>
      <p class="gt-custom-ingestion-wizard__status" data-testid="ingestion-status">{{ statusText }}</p>
    </header>

    <div v-if="!wizard.fshell.ok" class="gt-custom-ingestion-wizard__blocked" role="alert">
      <strong>无法启动向导</strong>
      <p>{{ wizard.state.value.blockers[0]?.messageZh }}</p>
    </div>

    <ul v-else class="gt-custom-ingestion-wizard__entries">
      <li v-for="e in entries" :key="e.kind">
        <button
          type="button"
          class="gt-custom-ingestion-wizard__entry"
          :data-testid="`entry-${e.kind}`"
          :aria-pressed="wizard.state.value.entry === e.kind"
          @click="onSelect(e.kind)"
        >
          <strong>{{ e.title }}</strong>
          <span>{{ e.desc }}</span>
        </button>
      </li>
    </ul>

    <section
      v-if="wizard.state.value.phase === 'candidate_preview'"
      class="gt-custom-ingestion-wizard__preview"
      data-testid="static-preview-banner"
    >
      当前为<strong>静态预览</strong>：不生成生产 OnlyOffice / WOPI 配置。
      hostFactsRegistered={{ wizard.state.value.hostFactsRegistered }}
    </section>

    <ul v-if="wizard.state.value.blockers.length" class="gt-custom-ingestion-wizard__blockers">
      <li v-for="b in wizard.state.value.blockers" :key="b.code">
        {{ b.messageZh }}
        <span v-if="b.recoverable">（可恢复）</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.gt-custom-ingestion-wizard {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px;
}
.gt-custom-ingestion-wizard__head h2 {
  margin: 0 0 8px;
  font-size: 1.25rem;
}
.gt-custom-ingestion-wizard__status {
  color: var(--el-text-color-secondary, #666);
  margin: 0 0 16px;
}
.gt-custom-ingestion-wizard__entries {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 12px;
}
.gt-custom-ingestion-wizard__entry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.gt-custom-ingestion-wizard__entry[aria-pressed='true'] {
  border-color: var(--el-color-primary, #4b2d77);
}
.gt-custom-ingestion-wizard__preview {
  margin-top: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.gt-custom-ingestion-wizard__blocked {
  padding: 12px;
  background: #fef0f0;
  color: #c45656;
  border-radius: 6px;
}
.gt-custom-ingestion-wizard__blockers {
  margin-top: 12px;
  color: #c45656;
}
</style>
