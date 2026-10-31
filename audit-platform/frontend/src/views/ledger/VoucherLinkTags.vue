<script setup lang="ts">
/**
 * 凭证层「这张凭证已挂 / 已抽于哪些底稿」标签（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5.2）
 *
 * 一条记录一个标签：「J1 · 挂凭 · 年审」「E1 · 抽凭 ×2 · 预审」；悬停看底稿名称与旧登记说明。
 * 挂凭（手工）用橙色、抽凭（引擎）用绿色，与凭证检查行上的来源标签同一套叫法。
 */
import { computed } from 'vue'
import { AUDIT_PHASE_LABEL } from '@/composables/useProjectAuditPhase'
import { LINK_SOURCE_LABEL, voucherLinkText, type VoucherTag } from './useVoucherLinkTags'

const props = defineProps<{ links: VoucherTag[] }>()

const items = computed(() => props.links.map(link => ({
  key: `${link.working_paper_id ?? '-'}|${link.source}|${link.phase ?? '-'}|${link.legacy}`,
  // 凭证证据条目（spec attachment-voucher-evidence-binding 需求 7）：「D2-4 · 凭证证据 2 份」，蓝色
  text: link.source === 'evidence'
    ? `${link.wp_code ?? '其他底稿'} · ${LINK_SOURCE_LABEL.evidence} ${link.count} 份`
    : [
        link.wp_code ?? (link.working_paper_id ? '底稿已删除' : '未指定底稿'),
        `${LINK_SOURCE_LABEL[link.source] ?? link.source}${link.count > 1 ? ` ×${link.count}` : ''}`,
        link.phase ? AUDIT_PHASE_LABEL[link.phase] : '阶段未标',
      ].join(' · ') + (link.legacy ? '（旧登记）' : ''),
  tip: voucherLinkText(link),
  type: link.source === 'evidence' ? 'primary' as const : link.source === 'manual' ? 'warning' as const : 'success' as const,
})))
</script>

<template>
  <span class="gt-voucher-links" data-testid="voucher-link-tags">
    <span class="gt-voucher-links__label">已挂底稿</span>
    <template v-if="items.length">
      <el-tag
        v-for="it in items"
        :key="it.key"
        size="small"
        effect="plain"
        :type="it.type"
        :title="it.tip"
      >{{ it.text }}</el-tag>
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
.gt-voucher-links__label {
  color: var(--gt-color-text-tertiary);
}
.gt-voucher-links__empty {
  color: var(--gt-color-text-placeholder);
}
</style>
