<!--
  GtA181RegulatorySubmission.vue — A18-1 向监管部门报送审计小结

  极简专属组件：3 区块（收件人 + 正文 + 签发）
  - 收件人: 固定前缀"致：" + bureau input + 固定后缀
  - 正文: 只读段落 + 自动填充 client/year + 联系人/电话
  - 签发: firm(只读) + partner input + date-picker
-->
<template>
  <div class="gt-a181">
    <div class="gt-a181__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-a181-regulatory-submission" />
      <span class="gt-a181__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <div v-if="mode === '结构化视图'" class="gt-a181__content">
      <el-skeleton v-if="loading" :rows="6" animated />
      <template v-else>
        <!-- 区块1: 收件人 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">收件人</span></template>
          <div class="gt-a181__recipient">
            <span class="gt-a181__prefix">致：</span>
            <el-input
              :model-value="recipient.bureau"
              size="small"
              :disabled="props.readonly"
              placeholder="请输入监管部门所在地"
              style="width: 160px"
              @change="(v: string) => updateField('recipient', 'bureau', v)"
            />
            <span class="gt-a181__suffix">财政局（证券监管局）</span>
          </div>
        </el-card>

        <!-- 区块2: 正文 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">正文</span></template>
          <div class="gt-a181__body">
            <p class="gt-a181__readonly-text">
              我们接受委托，审计了{{ projectContext.client_name || 'XX公司' }}{{ projectContext.audit_year || '202X' }}年度财务报表。
              按照有关规定，现将审计工作有关情况报送如下：
            </p>
            <p class="gt-a181__readonly-text gt-a181__readonly-text--muted">
              （正文内容按模板固定格式呈现，此处仅填写联系人信息）
            </p>
            <div class="gt-a181__body-fields">
              <div class="gt-a181__field">
                <label>项目联系人</label>
                <el-input
                  :model-value="body.contact_person"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="合伙人姓名"
                  @change="(v: string) => updateField('body', 'contact_person', v)"
                />
              </div>
              <div class="gt-a181__field">
                <label>联系电话</label>
                <el-input
                  :model-value="body.contact_phone"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="联系电话"
                  @change="(v: string) => updateField('body', 'contact_phone', v)"
                />
              </div>
            </div>
          </div>
        </el-card>

        <!-- 区块3: 签发 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">签发</span></template>
          <div class="gt-a181__issuance">
            <div class="gt-a181__field">
              <label>事务所</label>
              <el-input :model-value="projectContext.firm_name" size="small" disabled />
            </div>
            <div class="gt-a181__field">
              <label>签字合伙人</label>
              <el-input
                :model-value="issuance.partner"
                size="small"
                :disabled="props.readonly"
                placeholder="签字合伙人"
                @change="(v: string) => updateField('issuance', 'partner', v)"
              />
            </div>
            <div class="gt-a181__field">
              <label>日期</label>
              <el-date-picker
                :model-value="issuance.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="签发日期"
                @change="(v: string) => updateField('issuance', 'date', v || '')"
              />
            </div>
          </div>
        </el-card>
      </template>
    </div>

    <!-- Excel 在线编辑 — sync bridge -->
    <template v-else>
      <WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" class="gt-a181__oo" />
      <div v-else class="gt-a181__oo" style="display:flex;align-items:center;justify-content:center;color:#909399">正在打开同步编辑器…</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA181RegulatorySubmission } from './composables/useA181RegulatorySubmission'
import { useWorkpaperSyncBridge } from './sync/useWorkpaperSyncBridge'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { fetchOnlyOfficeHealthy } from './sync/onlyOfficeHealth'

import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'

const WorkpaperSyncEditorHost = defineAsyncComponent(() => import('./sync/WorkpaperSyncEditorHost.vue'))

defineOptions({ name: 'GtA181RegulatorySubmission' })

const props = withDefaults(defineProps<{ wpId: string; projectId?: string; readonly?: boolean }>(), { readonly: false, projectId: '' })

// ─── sync bridge（替代 legacy mode + GtOnlyOfficeSheet）───
const A181_ENTRY_ID = 'xlsx/gt-a181-regulatory-submission'
const A181_SHEET_KEY = 'a181-managed'

const wpIdRef = toRef(props, 'wpId')
const {
  loading, recipient, body, issuance, projectContext,
  saveStatus, lastSavedAt, loadData, updateField, flushPendingSaves,
} = useA181RegulatorySubmission(wpIdRef)

const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(A181_ENTRY_ID),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(A181_SHEET_KEY),
  capability: capabilityForEntry(A181_ENTRY_ID),
  flushHtml: async () => {
    flushPendingSaves()
    // 🔴 降级保护：本 entry capability 仍是 single_onlyoffice（后端无 per-entry
    //    adapter）⇒ readStoreProjection 会 404。捕获后返回空投影。
    try {
      const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: A181_ENTRY_ID })
      return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: A181_SHEET_KEY }
    } catch {
      return { expectedRevision: 0, projection: null, sheetKey: A181_SHEET_KEY }
    }
  },
  reloadHtml: async () => { await loadData(props.wpId) },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const mode = computed<string>({
  get: () => syncBridge.mode.value === 'oo' ? '在线编辑' : '结构化视图',
  set: (target) => {
    if (target === '在线编辑') { void syncBridge.switchToOnlyOffice() }
    else if (syncBridge.mode.value === 'oo') { void syncBridge.switchToHtml() }
  },
})
const modeOptions = computed(() => ['结构化视图', '在线编辑'].map(v => ({
  label: v, value: v,
  disabled: v === '在线编辑' && props.readonly,
})))

onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a181 { padding: 16px; max-width: 800px; }
.gt-a181__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a181__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }
.gt-a181__content { display: flex; flex-direction: column; gap: 16px; }
.gt-a181__card { border-radius: 8px; }
.gt-a181__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-a181__recipient { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-a181__prefix { font-size: 14px; font-weight: 500; color: #303133; }
.gt-a181__suffix { font-size: 14px; color: #606266; }
.gt-a181__readonly-text { font-size: 14px; color: #303133; line-height: 1.8; margin: 0 0 12px; }
.gt-a181__readonly-text--muted { color: #909399; font-size: var(--wp-font-size, 13px); font-style: italic; }
.gt-a181__body-fields { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a181__issuance { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a181__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
.gt-a181__field label { font-size: 12px; color: #909399; }
.gt-a181__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
