<script setup lang="ts">
/**
 * 凭证层「这张凭证已挂 / 已抽于哪些底稿」标签（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5.2）
 *
 * 一条记录一个标签：「J1 · 挂凭 · 年审」「E1 · 抽凭 ×2 · 预审」；悬停看底稿名称与旧登记说明。
 * 挂凭（手工）用橙色、抽凭（引擎）用绿色，与凭证检查行上的来源标签同一套叫法。
 *
 * spec voucher-workflow-linkage-lineage-closure R3.3 / R3.4：有底稿的标签可点（键盘可达）打开该底稿；
 * 已挂查询失败显示「挂接状态未知」+ 重试；手工挂凭标签带「已导入 / 未导入」（判断不了时不写）。
 */
import { computed } from 'vue'
import { AUDIT_PHASE_LABEL } from '@/composables/useProjectAuditPhase'
import { LINK_SOURCE_LABEL, voucherLinkText, type VoucherLinkStatus, type VoucherTag } from './useVoucherLinkTags'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'

const props = withDefaults(defineProps<{
  links: VoucherTag[]
  evidenceStatus?: 'idle' | 'loading' | 'ready' | 'empty' | 'forbidden' | 'error'
  /** 已挂查询状态（spec voucher-workflow-linkage-lineage-closure R3.3）：失败时显示「挂接状态未知」，不说「尚未挂到底稿」 */
  linkStatus?: VoucherLinkStatus
}>(), { evidenceStatus: 'idle', linkStatus: 'ready' })
const emit = defineEmits<{
  retry: []
  /** 已挂查询失败后的「重试」 */
  'retry-links': []
  /** 点标签打开该底稿（底稿已删除 / 未指定底稿的标签不可点） */
  'open-wp': [workpaperId: string]
}>()

/** 手工挂凭的导入状态（R3.4）：判断不了（null / 缺省）不写 */
function importedText(link: VoucherTag): string {
  if (link.source !== 'manual' || typeof link.imported !== 'boolean') return ''
  return link.imported ? ' · 已导入' : ' · 未导入'
}

const items = computed(() => props.links.map(link => ({
  key: `${link.working_paper_id ?? '-'}|${link.source}|${link.phase ?? '-'}|${link.legacy}`,
  link,
  // 凭证证据条目（spec attachment-voucher-evidence-binding 需求 7）：「D2-4 · 凭证证据 2 份」，蓝色
  text: link.source === 'evidence'
    ? `${link.wp_code ?? '其他底稿'} · ${LINK_SOURCE_LABEL.evidence} ${link.count} 份`
    : [
        link.wp_code ?? (link.working_paper_id ? '底稿已删除' : '未指定底稿'),
        `${LINK_SOURCE_LABEL[link.source] ?? link.source}${link.count > 1 ? ` ×${link.count}` : ''}`,
        link.phase ? AUDIT_PHASE_LABEL[link.phase] : '阶段未标',
      ].join(' · ') + (link.legacy ? '（旧登记）' : '') + importedText(link),
  tip: voucherLinkText(link),
  type: link.source === 'evidence' ? 'primary' as const : link.source === 'manual' ? 'warning' as const : 'success' as const,
  /** 能打开的底稿：有 id、有编码、未删除 */
  openId: link.working_paper_id && link.wp_code && !link.wp_missing ? link.working_paper_id : null,
})))
</script>

<template>
  <span class="gt-voucher-links" data-testid="voucher-link-tags">
    <span class="gt-voucher-links__label">已挂底稿</span>
    <!-- 已挂查询失败优先：这张凭证挂没挂到底稿不知道，不能显示成「尚未挂到底稿」 -->
    <template v-if="linkStatus === 'error'">
      <span class="gt-voucher-links__error" role="alert" data-testid="voucher-links-unknown">挂接状态未知（查询失败）</span>
      <button type="button" class="gt-voucher-links__retry" @click="emit('retry-links')">重试</button>
    </template>
    <template v-else-if="evidenceStatus === 'error' || evidenceStatus === 'forbidden'">
      <span class="gt-voucher-links__error" role="alert">
        {{ evidenceStatus === 'forbidden' ? '无权查看凭证证据' : '凭证证据加载失败' }}
      </span>
      <button type="button" class="gt-voucher-links__retry" @click="emit('retry')">重试</button>
    </template>
    <span v-else-if="linkStatus === 'loading' && !items.length" class="gt-voucher-links__empty">查询中…</span>
    <template v-else-if="items.length">
      <span v-for="it in items" :key="it.key" class="gt-voucher-links__item">
        <button
          v-if="it.openId"
          type="button"
          class="gt-voucher-links__open"
          :aria-label="`打开底稿：${it.tip}`"
          data-testid="voucher-link-open"
          @click="emit('open-wp', it.openId)"
        >
          <el-tag size="small" effect="plain" :type="it.type" :title="`${it.tip}（点击打开底稿）`">{{ it.text }}</el-tag>
        </button>
        <el-tag
          v-else
          size="small"
          effect="plain"
          :type="it.type"
          :title="it.tip"
        >{{ it.text }}</el-tag>
        <AttachmentEyeButton
          v-for="attachment in it.link.source === 'evidence' ? (it.link.attachments ?? []) : []"
          :key="attachment.id"
          :attachment-id="attachment.id"
          :file-name="attachment.file_name"
          :file-type="attachment.file_type"
          :ocr-status="attachment.ocr_status"
        />
      </span>
    </template>
    <span v-else class="gt-voucher-links__empty">尚未挂到底稿</span>
  </span>
</template>

<style scoped>
.gt-voucher-links {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: var(--gt-font-size-xs);
}
.gt-voucher-links__item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.gt-voucher-links__label {
  color: var(--gt-color-text-tertiary);
}
/* 主题里没有 --gt-color-danger（错误色是珊瑚橙 coral），不带回退时失败文字显示成黑字 */
.gt-voucher-links__error { color: var(--gt-color-danger, var(--gt-color-coral)); }
.gt-voucher-links__retry {
  border: 0; background: transparent; padding: 0; cursor: pointer;
  color: var(--gt-color-primary); font-size: inherit;
}
.gt-voucher-links__open {
  border: 0; background: transparent; padding: 0; cursor: pointer; line-height: 1;
}
.gt-voucher-links__open:focus-visible {
  outline: 2px solid var(--gt-color-primary); outline-offset: 1px; border-radius: 3px;
}
.gt-voucher-links__empty {
  color: var(--gt-color-text-placeholder);
}
</style>
