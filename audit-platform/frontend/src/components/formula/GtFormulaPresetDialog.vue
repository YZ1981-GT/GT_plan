<!--
  GtFormulaPresetDialog.vue — 公式预设库入口弹窗（Req 25）

  从模板库（NoteTemplateTab / ReportConfigTab / WpTemplateDetail）的
  TemplateLibraryButton 所在区点击"公式预设库"入口后弹出。两块内容：

  1. 说明文档（Req 25.2/25.3）：渲染公式管理说明文档，经
     GET /api/formula-management/reporting-instructions 拉取**单一文档源**
     （与导出模板编报说明同源，避免两套漂移）。
  2. 预设浏览/编辑（Req 25.4）：展示 Preset Inventory 逐页登记 + 覆盖度，
     选中页可查看该页预设公式，点击可用统一 GtFormulaEditDialog 编辑/新建
     （复用 Req 8 的 Formula_Edit_Dialog 与 Req 22 的预设清单）。

  附加入口，无回归（Req 25.5）。

  Spec: .kiro/specs/formula-management-library/  Task: 14.6
  Requirements: 25.1, 25.2, 25.3, 25.4, 25.5
-->
<template>
  <el-dialog
    v-model="visible"
    title="公式预设库"
    width="900px"
    top="6vh"
    append-to-body
    destroy-on-close
    class="gt-formula-preset-dialog"
  >
    <el-tabs v-model="activeTab" class="gt-fpd-tabs">
      <!-- ─── 说明文档（单一源） ─── -->
      <el-tab-pane label="📖 公式管理说明" name="doc">
        <div v-loading="docLoading" class="gt-fpd-doc">
          <template v-if="doc">
            <div class="gt-fpd-doc-head">
              <span class="gt-fpd-doc-title">{{ doc.title }}</span>
              <el-tag size="small" type="info" effect="plain">版本 {{ doc.version }}</el-tag>
            </div>
            <section
              v-for="s in doc.sections"
              :key="s.key"
              class="gt-fpd-doc-section"
            >
              <h4 class="gt-fpd-doc-h4">{{ s.title }}</h4>
              <p v-for="(line, i) in s.lines" :key="i" class="gt-fpd-doc-line">{{ line }}</p>
            </section>
          </template>
          <el-empty v-else-if="!docLoading" description="说明文档暂不可用" />
        </div>
      </el-tab-pane>

      <!-- ─── 预设浏览/编辑 ─── -->
      <el-tab-pane label="🗂 预设浏览" name="browse">
        <div class="gt-fpd-browse">
          <!-- 左：页面清单 -->
          <div class="gt-fpd-pages" v-loading="pagesLoading">
            <div class="gt-fpd-pages-toolbar">
              <el-input
                v-model="pageSearch"
                size="small"
                placeholder="搜索页面键"
                clearable
              />
              <span v-if="coverageLabel" class="gt-fpd-coverage">{{ coverageLabel }}</span>
            </div>
            <el-scrollbar class="gt-fpd-pages-list">
              <div
                v-for="p in filteredPages"
                :key="p.page_key"
                class="gt-fpd-page-item"
                :class="{ 'is-active': p.page_key === selectedPageKey }"
                @click="selectPage(p.page_key)"
              >
                <span class="gt-fpd-page-key">{{ p.page_key }}</span>
                <el-tag size="small" effect="plain" round>{{ p.formula_count }}</el-tag>
              </div>
              <el-empty
                v-if="!pagesLoading && filteredPages.length === 0"
                :image-size="60"
                description="无匹配页面"
              />
            </el-scrollbar>
          </div>

          <!-- 右：所选页预设 -->
          <div class="gt-fpd-presets" v-loading="presetLoading">
            <div class="gt-fpd-presets-head">
              <span class="gt-fpd-presets-title">
                {{ selectedPageKey || '请选择左侧页面' }}
              </span>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="!selectedPageKey"
                @click="openEditor(null)"
              >
                ➕ 新建公式
              </el-button>
            </div>
            <el-table
              v-if="selectedPageKey"
              :data="presets"
              size="small"
              height="360"
              :header-cell-style="{ background: '#f0edf5', color: '#303133' }"
              empty-text="该页暂无预设公式"
            >
              <el-table-column prop="target_cell" label="目标单元" min-width="140" show-overflow-tooltip />
              <el-table-column label="类型" width="110">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain" :type="typeTagType(row.formula_type)">
                    {{ typeLabel(row.formula_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="expression" label="表达式" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  <code class="gt-fpd-expr">{{ row.expression }}</code>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openEditor(row)">编辑</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else :image-size="80" description="从左侧选择页面以浏览其预设公式" />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 统一公式编辑弹窗（复用 Req 8 Formula_Edit_Dialog / Req 22 预设清单） -->
    <GtFormulaEditDialog
      v-model="editorVisible"
      :initial="editorInitial"
      :scope="editorScope"
      @save="onEditorSave"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtFormulaEditDialog, {
  type FormulaEditPayload,
  type FormulaType,
  type FormulaDialogScope,
} from './GtFormulaEditDialog.vue'
import {
  useFormulaImportExport,
  type FormulaReportingDoc,
  type FormulaPresetPage,
  type FormulaPresetCoverage,
  type FormulaPresetEntry,
} from '@/composables/useFormulaImportExport'

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 入口所属作用域，用于默认过滤页面清单与新建公式的默认 scope */
  scope?: FormulaDialogScope
  /** 可选：默认选中的页面键（scope:key，如 workpaper:D2） */
  pageKey?: string
}>(), {
  scope: 'workpaper',
  pageKey: '',
})

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  /** 保存编辑后的公式（由宿主决定是否持久化；默认仅提示） */
  'edit-formula': [payload: FormulaEditPayload & { page_key: string }]
}>()

const ie = useFormulaImportExport()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeTab = ref<'doc' | 'browse'>('doc')

// ─── 说明文档（单一源） ───
const doc = ref<FormulaReportingDoc | null>(null)
const docLoading = ref(false)

async function loadDoc() {
  if (doc.value) return
  docLoading.value = true
  try {
    doc.value = await ie.getReportingInstructions('json')
  } finally {
    docLoading.value = false
  }
}

// ─── 预设浏览 ───
const pages = ref<FormulaPresetPage[]>([])
const coverage = ref<FormulaPresetCoverage | null>(null)
const pagesLoading = ref(false)
const pageSearch = ref('')
const selectedPageKey = ref('')
const presets = ref<FormulaPresetEntry[]>([])
const presetLoading = ref(false)

const filteredPages = computed(() => {
  const q = pageSearch.value.trim().toLowerCase()
  if (!q) return pages.value
  return pages.value.filter((p) => p.page_key.toLowerCase().includes(q))
})

const coverageLabel = computed(() => {
  if (!coverage.value) return ''
  const { presetted, pending } = coverage.value.by_status
  return `已预设 ${presetted} · 待预设 ${pending}`
})

async function loadPages() {
  if (pages.value.length) return
  pagesLoading.value = true
  try {
    const inv = await ie.getPresetInventory(props.scope)
    if (inv) {
      pages.value = inv.pages
      coverage.value = inv.coverage
    }
    // 默认选中：传入的 pageKey 优先，否则首页
    const target = props.pageKey || pages.value[0]?.page_key || ''
    if (target) await selectPage(target)
  } finally {
    pagesLoading.value = false
  }
}

async function selectPage(pageKey: string) {
  selectedPageKey.value = pageKey
  presetLoading.value = true
  try {
    const detail = await ie.getPresetPage(pageKey)
    presets.value = detail?.presets ?? []
  } finally {
    presetLoading.value = false
  }
}

const TYPE_LABEL: Record<FormulaType, string> = {
  auto_calc: '自动运算',
  logic_check: '逻辑判断',
  reasonability: '合理性',
}
function typeLabel(t: FormulaType): string {
  return TYPE_LABEL[t] ?? t
}
function typeTagType(t: FormulaType): 'primary' | 'warning' | 'success' {
  if (t === 'logic_check') return 'warning'
  if (t === 'reasonability') return 'success'
  return 'primary'
}

// ─── 编辑/新建（复用统一编辑弹窗） ───
const editorVisible = ref(false)
const editorInitial = ref<Partial<FormulaEditPayload> | null>(null)
const editorScope = computed<FormulaDialogScope>(() => {
  const s = (selectedPageKey.value || '').split(':', 1)[0]
  if (s === 'note') return 'note'
  if (s === 'report') return 'report'
  return 'workpaper'
})

function openEditor(row: FormulaPresetEntry | null) {
  editorInitial.value = row
    ? {
        formula_type: row.formula_type,
        target_cell: row.target_cell,
        expression: row.expression,
        refs: (row.refs || []).map((r) => (typeof r === 'string' ? r : JSON.stringify(r))),
      }
    : null
  editorVisible.value = true
}

function onEditorSave(payload: FormulaEditPayload) {
  const pageKey = selectedPageKey.value
  emit('edit-formula', { ...payload, page_key: pageKey })
  ElMessage.success('公式已编辑（可经导入或底稿保存持久化）')
}

// 打开弹窗时按当前 tab 懒加载
watch(visible, (v) => {
  if (!v) return
  loadDoc()
  loadPages()
})
watch(activeTab, (t) => {
  if (t === 'doc') loadDoc()
  else loadPages()
})
</script>

<style scoped>
.gt-formula-preset-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}

/* 说明文档 */
.gt-fpd-doc {
  max-height: 62vh;
  overflow: auto;
  padding-right: 6px;
}
.gt-fpd-doc-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.gt-fpd-doc-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-fpd-doc-section {
  margin-bottom: 14px;
}
.gt-fpd-doc-h4 {
  margin: 0 0 6px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #7b5ea7);
  border-left: 3px solid var(--gt-color-primary, #7b5ea7);
  padding-left: 8px;
}
.gt-fpd-doc-line {
  margin: 2px 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--gt-color-text-regular, #606266);
  white-space: pre-wrap;
}

/* 预设浏览 */
.gt-fpd-browse {
  display: flex;
  gap: 12px;
  min-height: 420px;
}
.gt-fpd-pages {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 8px;
  padding: 8px;
}
.gt-fpd-pages-toolbar {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-fpd-coverage {
  font-size: 12px;
  color: var(--gt-color-info, #909399);
}
.gt-fpd-pages-list {
  flex: 1;
  min-height: 0;
}
.gt-fpd-page-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.gt-fpd-page-item:hover {
  background: var(--gt-color-primary-bg, #f5f2fa);
}
.gt-fpd-page-item.is-active {
  background: var(--gt-color-primary-bg, #f5f2fa);
  font-weight: 600;
  color: var(--gt-color-primary, #7b5ea7);
}
.gt-fpd-page-key {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-fpd-presets {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-fpd-presets-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.gt-fpd-presets-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-fpd-expr {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
}
</style>
