<script setup lang="ts">
/**
 * NoteContentTemplatePicker — 附注内容模板列表与版本选择（Task 46，AC-8.1~8.3）
 *
 * 列表只载元数据（后端 SQL 层按可见性过滤）；默认引用最新版本，也可展开历史不可变版本。
 * 选中后把「模板 + 固定版本（含 content_hash）」交给引用弹窗，预览 / 写入都钉在该版本上。
 * 版本说明含保存人 / 时间（AC-8.2）；本项目本年度引用过的模板提示「有新版本」，只提示不自动更新，
 * 由用户点「重新预览」核对后才写入（AC-8.4）。
 */
import { computed, ref, watch } from 'vue'
import {
  useNoteContentTemplate, type ContentTemplateItem, type ContentTemplateVersion,
} from '@/composables/useNoteContentTemplate'
import { appliedHint, REPORT_SCOPE_LABELS, savedByLabel, TEMPLATE_TYPE_LABELS } from './noteTextBatchLabels'

const props = defineProps<{ visible: boolean; projectId: string; year: number }>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'select': [template: ContentTemplateItem, version: ContentTemplateVersion]
}>()

const PAGE = 50
const tmpl = useNoteContentTemplate({ projectId: computed(() => props.projectId), year: computed(() => props.year) })
const expandedId = ref<string | null>(null)
/** AC-8.4：本项目（本年度）已引用的版本 vs 模板当前版本，只提示、不自动更新 */
const hints = computed(() => new Map(tmpl.templates.value.map(i => [i.id, appliedHint(i)])))
/** 加载失败必须显示失败与重试，不能落到「暂无模板」（会让用户以为没有模板） */
const loadFailed = computed(() => !!tmpl.lastError.value && !tmpl.templates.value.length)
const hasMore = computed(() => tmpl.templates.value.length < tmpl.total.value)

function reload() {
  expandedId.value = null
  return tmpl.fetchTemplates(PAGE, 0)
}
function loadMore() {
  return tmpl.fetchTemplates(PAGE, tmpl.templates.value.length, { append: true })
}

watch(() => props.visible, (v) => { if (v) reload() }, { immediate: true })

function describe(v: ContentTemplateVersion): string {
  const q = v.quality_summary ?? {}
  return [`v${v.version_no}`, `来源 ${v.source_project_name} ${v.source_year} 年`,
    TEMPLATE_TYPE_LABELS[v.template_type] ?? v.template_type, REPORT_SCOPE_LABELS[v.report_scope] ?? v.report_scope,
    `${q.total ?? 0} 章（有内容 ${q.with_content ?? 0}，高风险 ${q.high_risk ?? 0}）`,
    savedByLabel(v)].filter(Boolean).join(' · ')
}

async function toggleVersions(item: ContentTemplateItem) {
  if (expandedId.value === item.id) { expandedId.value = null; return }
  expandedId.value = null  // 版本列表各模板共用，先收起，避免显示上一个模板的版本
  await tmpl.fetchVersions(item.id)
  if (!tmpl.lastError.value) expandedId.value = item.id
}

function choose(item: ContentTemplateItem, version: ContentTemplateVersion) {
  emit('select', item, version)
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog :model-value="visible" title="📋 选择附注内容模板" width="760px" append-to-body destroy-on-close
    @update:model-value="(v: boolean) => emit('update:visible', v)">
    <div v-if="tmpl.loading.value && !tmpl.templates.value.length" class="gt-ntpk-empty">加载中…</div>
    <div v-else-if="loadFailed" class="gt-ntpk-empty">
      <el-alert type="error" :title="tmpl.lastError.value?.message" :closable="false" show-icon />
      <el-button size="small" type="primary" style="margin-top: 12px" @click="reload">重试</el-button>
    </div>
    <div v-else-if="!tmpl.templates.value.length" class="gt-ntpk-empty">暂无可用的附注内容模板（只显示本人个人模板与本集团模板）</div>
    <template v-else>
    <div v-for="item in tmpl.templates.value" :key="item.id" class="gt-ntpk-item">
      <div class="gt-ntpk-row">
        <strong>{{ item.name }}</strong>
        <el-tag size="small" :type="item.owner_scope === 'group' ? 'warning' : 'info'">{{ item.owner_scope === 'group' ? '集团' : '个人' }}</el-tag>
        <div style="flex: 1" />
        <el-button size="small" link type="primary" @click="toggleVersions(item)">{{ expandedId === item.id ? '收起版本' : '历史版本' }}</el-button>
        <el-button size="small" type="primary" :disabled="!item.current_version" @click="item.current_version && choose(item, item.current_version)">
          {{ hints.get(item.id)?.changed ? '重新预览' : '引用最新版本' }}</el-button>
      </div>
      <div v-if="item.description" class="gt-ntpk-muted">{{ item.description }}</div>
      <div class="gt-ntpk-muted">{{ item.current_version ? describe(item.current_version) : '暂无版本' }}</div>
      <div v-if="hints.get(item.id)" :class="['gt-ntpk-applied', { 'is-changed': hints.get(item.id)?.changed }]">
        {{ hints.get(item.id)?.text }}</div>
      <div v-if="expandedId === item.id" class="gt-ntpk-versions">
        <div v-for="v in tmpl.versions.value" :key="v.id" class="gt-ntpk-row">
          <span class="gt-ntpk-muted">{{ describe(v) }}</span>
          <el-tag v-if="item.last_applied?.version_id === v.id" size="small" type="success">本项目已引用</el-tag>
          <div style="flex: 1" />
          <el-button size="small" link type="primary" @click="choose(item, v)">引用此版本</el-button>
        </div>
      </div>
    </div>
    <div v-if="hasMore" class="gt-ntpk-more">
      <span class="gt-ntpk-muted">已显示 {{ tmpl.templates.value.length }} / 共 {{ tmpl.total.value }} 个</span>
      <el-button size="small" :loading="tmpl.loading.value" @click="loadMore">加载更多</el-button>
    </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.gt-ntpk-empty { text-align: center; padding: 40px; color: var(--el-text-color-placeholder); }
.gt-ntpk-item { padding: 12px; margin-bottom: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.gt-ntpk-row { display: flex; align-items: center; gap: 8px; }
.gt-ntpk-muted { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.gt-ntpk-versions { margin-top: 8px; padding-left: 12px; border-left: 2px solid var(--el-border-color-lighter); }
.gt-ntpk-applied { font-size: 12px; margin-top: 4px; color: var(--el-color-success); }
.gt-ntpk-applied.is-changed { color: var(--el-color-warning-dark-2); font-weight: 600; }
.gt-ntpk-more { display: flex; align-items: center; justify-content: center; gap: 12px; padding-top: 4px; }
</style>
