<!--
  WpTemplateDetail.vue — 底稿模板详情面板 [template-library-coordination Task 4.7]

  需求 3.1-3.7, 15.1-15.4：
  - 基本信息（wp_code/wp_name/cycle_name/format/component_type/audit_stage/linked_accounts）
  - 主文件下载区（合并后的 xlsx 文件）
  - 合并 sheets 列表（从 prefill_formula_mapping 提取该 wp_code 的 sheet 名称）
  - 源文件参考下载（折叠区，展示 source_file_count 个源文件清单）
  - 预填充公式配置展示
  - 跨底稿引用关系（incoming + outgoing）
  - 项目使用情况

  D8 ADR：数字列统一 .gt-amt
  D11 ADR：子表收敛 — 一 wp_code 一节点，主文件 1 个 + sheets 列表 + 源文件折叠区
  D14 ADR：不依赖 WpTemplateMetadata.subtable_codes（不存在）
-->
<template>
  <div v-if="wpCode" v-loading="loading" class="gt-wpd">
    <!-- 1. 基本信息卡 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><InfoFilled /></el-icon>基本信息
      </div>
      <div class="gt-wpd-meta">
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">底稿编码</span>
          <span class="gt-wpd-meta-value">
            <span class="gt-wpd-code">{{ template?.wp_code || wpCode }}</span>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">底稿名称</span>
          <span class="gt-wpd-meta-value">{{ template?.wp_name || '—' }}</span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">所属循环</span>
          <span class="gt-wpd-meta-value">
            <el-tag size="small" effect="plain" round>{{ template?.cycle_name || '—' }}</el-tag>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">格式</span>
          <span class="gt-wpd-meta-value">
            <span class="gt-wpd-format-icon">{{ formatIcon(template?.format) }}</span>
            <span>{{ template?.format || 'xlsx' }}</span>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">组件类型</span>
          <span class="gt-wpd-meta-value">
            <el-tag
              v-if="template?.component_type"
              size="small"
              :class="`gt-wpd-comp--${template.component_type}`"
              effect="light"
            >
              {{ template.component_type }}
            </el-tag>
            <span v-else class="gt-wpd-empty">—</span>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">审计阶段</span>
          <span class="gt-wpd-meta-value">
            <el-tag v-if="template?.audit_stage" size="small" type="info" effect="plain">
              {{ auditStageLabel(template.audit_stage) }}
            </el-tag>
            <span v-else class="gt-wpd-empty">—</span>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">关联科目</span>
          <span class="gt-wpd-meta-value">
            <template v-if="template?.linked_accounts && template.linked_accounts.length > 0">
              <el-tag
                v-for="acc in template.linked_accounts"
                :key="acc"
                size="small"
                effect="plain"
                round
                class="gt-wpd-acc-tag"
              >
                {{ acc }}
              </el-tag>
            </template>
            <span v-else class="gt-wpd-empty">—</span>
          </span>
        </div>
        <div v-if="noteSection" class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">关联附注</span>
          <span class="gt-wpd-meta-value">
            <el-tag size="small" type="warning" effect="plain">{{ noteSection }}</el-tag>
          </span>
        </div>
      </div>
    </div>

    <!-- 2. 主文件下载区 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><Download /></el-icon>主文件下载（合并后）
      </div>
      <div class="gt-wpd-main-file">
        <div class="gt-wpd-main-file-info">
          <div class="gt-wpd-main-file-name">
            <span class="gt-wpd-format-icon">{{ formatIcon(template?.format) }}</span>
            <strong>{{ template?.filename || `${wpCode}.${template?.format || 'xlsx'}` }}</strong>
          </div>
          <div class="gt-wpd-main-file-meta">
            <span>共 <span class="gt-amt">{{ sheetCount }}</span> 个 sheets</span>
            <span class="gt-wpd-divider">·</span>
            <span>合并自 <span class="gt-amt">{{ sourceFileCount }}</span> 个源文件</span>
          </div>
        </div>
        <el-button
          type="primary"
          size="default"
          :disabled="!projectId"
          @click="onDownloadMain"
        >
          <el-icon style="margin-right: 4px"><Download /></el-icon>下载主文件
        </el-button>
      </div>
    </div>

    <!-- 3. 合并 sheets 列表 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><Files /></el-icon>合并后 sheets 列表
        <el-tag size="small" type="info" effect="plain" round style="margin-left: 8px">
          <span class="gt-amt">{{ mergedSheets.length }}</span>
        </el-tag>
      </div>
      <el-table
        v-if="mergedSheets.length > 0"
        :data="mergedSheets"
        size="small"
        :header-cell-style="{ background: '#f8f6fb', color: '#606266', fontWeight: '600' }"
      >
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column label="Sheet 名称" prop="name" min-width="220">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag
              v-if="row.has_formula"
              size="small"
              type="primary"
              effect="plain"
              round
              style="margin-left: 6px"
            >
              ✦ 含公式
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="公式单元格" width="120" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ row.cell_count || 0 }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-else
        :image-size="60"
        description="暂无 sheet 元数据（可能由模板复制时动态合并产生）"
      />
    </div>

    <!-- 4. 源文件参考下载（折叠区） -->
    <div class="gt-wpd-card">
      <el-collapse v-model="sourcesExpanded">
        <el-collapse-item name="sources">
          <template #title>
            <span class="gt-wpd-card-title gt-wpd-card-title--inline">
              <el-icon><FolderOpened /></el-icon>源文件参考下载（保留对原始模板的访问）
              <el-tag size="small" type="warning" effect="plain" round style="margin-left: 8px">
                <span class="gt-amt">{{ sourceFiles.length }}</span> 个源文件
              </el-tag>
            </span>
          </template>
          <el-table
            v-if="sourceFiles.length > 0"
            :data="sourceFiles"
            size="small"
            :header-cell-style="{ background: '#f8f6fb', color: '#606266', fontWeight: '600' }"
          >
            <el-table-column type="index" label="#" width="60" align="center" />
            <el-table-column label="源文件名" prop="filename" min-width="320" show-overflow-tooltip />
            <el-table-column label="编码" prop="wp_code" width="120">
              <template #default="{ row }">
                <span class="gt-wpd-code-small">{{ row.wp_code }}</span>
              </template>
            </el-table-column>
            <el-table-column label="格式" prop="format" width="80" align="center">
              <template #default="{ row }">
                <span class="gt-wpd-format-icon">{{ formatIcon(row.format) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="大小(KB)" width="100" align="right">
              <template #default="{ row }">
                <span class="gt-amt">{{ row.size_kb ?? '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="60" description="暂无源文件清单" />
          <div v-if="sourceFiles.length > 0" class="gt-wpd-source-hint">
            源文件不提供单独下载，所有内容已合并到主文件。
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 5. 预填充公式配置 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><DataAnalysis /></el-icon>预填充公式配置
        <el-tag size="small" type="info" effect="plain" round style="margin-left: 8px">
          <span class="gt-amt">{{ prefillCells.length }}</span> 单元格
        </el-tag>
      </div>
      <el-table
        v-if="prefillCells.length > 0"
        :data="prefillCells"
        size="small"
        :header-cell-style="{ background: '#f8f6fb', color: '#606266', fontWeight: '600' }"
      >
        <el-table-column label="Sheet" prop="sheet" min-width="180" show-overflow-tooltip />
        <el-table-column label="单元格" prop="cell_ref" width="140" />
        <el-table-column label="公式" prop="formula" min-width="240">
          <template #default="{ row }">
            <code class="gt-wpd-formula">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="类型" prop="formula_type" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :class="`gt-wpd-fmtype--${(row.formula_type || '').toLowerCase()}`"
              effect="light"
            >
              {{ row.formula_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" prop="description" min-width="220" show-overflow-tooltip />
      </el-table>
      <el-empty
        v-else
        :image-size="60"
        description="该底稿无预填充公式配置"
      />
    </div>

    <!-- 6. 跨底稿引用关系 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><Connection /></el-icon>跨底稿引用关系
        <el-tag size="small" type="info" effect="plain" round style="margin-left: 8px">
          引入 <span class="gt-amt">{{ incomingRefs.length }}</span> · 引出 <span class="gt-amt">{{ outgoingRefs.length }}</span>
        </el-tag>
      </div>

      <div v-if="outgoingRefs.length > 0" class="gt-wpd-xref-section">
        <div class="gt-wpd-xref-section-title">
          引出（本底稿数据被以下底稿引用）→
        </div>
        <div class="gt-wpd-xref-list">
          <div
            v-for="ref in outgoingRefs"
            :key="ref.ref_id"
            class="gt-wpd-xref-item"
          >
            <el-tag size="small" :type="severityType(ref.severity)" effect="light">
              {{ ref.ref_id }}
            </el-tag>
            <span class="gt-wpd-xref-arrow">→</span>
            <span
              v-for="t in (ref.targets || [])"
              :key="t.wp_code"
              class="gt-wpd-xref-target"
            >
              <span class="gt-wpd-code-small">{{ t.wp_code }}</span>
            </span>
            <span class="gt-wpd-xref-desc">{{ ref.description }}</span>
          </div>
        </div>
      </div>

      <div v-if="incomingRefs.length > 0" class="gt-wpd-xref-section">
        <div class="gt-wpd-xref-section-title">
          ← 引入（本底稿引用以下底稿数据）
        </div>
        <div class="gt-wpd-xref-list">
          <div
            v-for="ref in incomingRefs"
            :key="ref.ref_id"
            class="gt-wpd-xref-item"
          >
            <span class="gt-wpd-code-small">{{ ref.source_wp }}</span>
            <span class="gt-wpd-xref-arrow">→</span>
            <el-tag size="small" :type="severityType(ref.severity)" effect="light">
              {{ ref.ref_id }}
            </el-tag>
            <span class="gt-wpd-xref-desc">{{ ref.description }}</span>
          </div>
        </div>
      </div>

      <el-empty
        v-if="incomingRefs.length === 0 && outgoingRefs.length === 0"
        :image-size="60"
        description="暂无跨底稿引用关系"
      />
    </div>

    <!-- 7. 项目使用情况 -->
    <div class="gt-wpd-card">
      <div class="gt-wpd-card-title">
        <el-icon><DataLine /></el-icon>项目使用情况
      </div>
      <div class="gt-wpd-usage">
        <div class="gt-wpd-usage-stat">
          <span class="gt-wpd-usage-label">当前项目</span>
          <el-tag
            :type="template?.generated ? 'success' : 'info'"
            size="default"
            effect="light"
            round
          >
            {{ template?.generated ? '✓ 已生成底稿' : '尚未生成' }}
          </el-tag>
        </div>
        <div class="gt-wpd-usage-note">
          全局使用率统计将在后续 Sprint 落地（需后端聚合 working_paper × wp_code 跨项目数据）
        </div>
      </div>
    </div>
  </div>

  <el-empty v-else description="未选择底稿模板" />
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  InfoFilled,
  Download,
  Files,
  FolderOpened,
  DataAnalysis,
  Connection,
  DataLine,
} from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import {
  templateLibraryMgmt as P_tlm,
  workpapers as P_wp,
} from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  wpCode: string
  projectId: string
}

const props = defineProps<Props>()

// ─── 类型 ─────────────────────────────────────────────────────────────────

interface TemplateItem {
  wp_code: string
  wp_name: string
  cycle: string
  cycle_name: string
  filename?: string
  format?: string
  component_type?: string | null
  audit_stage?: string | null
  linked_accounts?: string[]
  procedure_steps?: any[]
  has_formula?: boolean
  source_file_count?: number
  sheet_count?: number
  generated?: boolean
}

interface SourceFileEntry {
  wp_code: string
  filename: string
  relative_path?: string
  format?: string
  size_kb?: number
  category?: string
}

interface PrefillCellRow {
  sheet: string
  cell_ref: string
  formula: string
  formula_type: string
  description?: string
}

interface PrefillMappingRaw {
  wp_code: string
  wp_name: string
  sheet: string
  cells?: Array<{
    cell_ref: string
    formula: string
    formula_type: string
    description?: string
  }>
}

interface CrossWpRefTarget {
  wp_code: string
  sheet?: string
  cell?: string
  formula?: string
}

interface CrossWpReference {
  ref_id: string
  description: string
  source_wp: string
  source_sheet?: string
  source_cell?: string
  targets?: CrossWpRefTarget[]
  category?: string
  severity?: string
}

interface MergedSheetEntry {
  name: string
  has_formula: boolean
  cell_count: number
}

// ─── State ────────────────────────────────────────────────────────────────

const loading = ref(false)
const template = ref<TemplateItem | null>(null)
const sourceFiles = ref<SourceFileEntry[]>([])
const prefillCells = ref<PrefillCellRow[]>([])
const incomingRefs = ref<CrossWpReference[]>([])
const outgoingRefs = ref<CrossWpReference[]>([])
const noteSection = ref<string>('')
const sourcesExpanded = ref<string[]>([])

// ─── 衍生 ─────────────────────────────────────────────────────────────────

const sheetCount = computed(() => template.value?.sheet_count ?? 1)
const sourceFileCount = computed(() => template.value?.source_file_count ?? 0)

// 合并 sheets 列表（从 prefill cells 提取去重 + 标注公式数）
const mergedSheets = computed<MergedSheetEntry[]>(() => {
  if (prefillCells.value.length === 0) {
    // 退化展示：按 sheet_count 生成 N 个占位 sheet
    if (sheetCount.value > 1) {
      return Array.from({ length: sheetCount.value }, (_, i) => ({
        name: `Sheet ${i + 1}`,
        has_formula: false,
        cell_count: 0,
      }))
    }
    return []
  }
  const map = new Map<string, MergedSheetEntry>()
  for (const c of prefillCells.value) {
    if (!c.sheet) continue
    if (!map.has(c.sheet)) {
      map.set(c.sheet, { name: c.sheet, has_formula: true, cell_count: 0 })
    }
    map.get(c.sheet)!.cell_count += 1
  }
  return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
})

// ─── 工具函数 ─────────────────────────────────────────────────────────────

function formatIcon(format?: string | null): string {
  const f = (format || '').toLowerCase()
  if (f === 'docx' || f === 'doc') return '📝'
  if (f === 'xlsm') return '⚙️'
  if (f === 'xlsx' || f === 'xls') return '📊'
  return '📄'
}

function auditStageLabel(stage: string): string {
  const map: Record<string, string> = {
    preliminary: '初步业务',
    risk_assessment: '风险评估',
    control_test: '控制测试',
    substantive: '实质性程序',
    completion: '完成阶段',
    specific: '特定项目',
  }
  return map[stage] || stage
}

function severityType(s?: string): 'danger' | 'warning' | 'info' {
  if (s === 'blocking') return 'danger'
  if (s === 'warning') return 'warning'
  return 'info'
}

// ─── 数据加载 ─────────────────────────────────────────────────────────────

async function loadTemplate() {
  if (!props.projectId || !props.wpCode) {
    template.value = null
    return
  }
  try {
    const data = await api.get(P_wp.templateList(props.projectId))
    const items = (Array.isArray(data) ? data : (data?.items || [])) as TemplateItem[]
    template.value = items.find(t => t.wp_code === props.wpCode) || null
  } catch (e: any) {
    handleApiError(e, '加载底稿模板信息')
    template.value = null
  }
}

async function loadSourceFiles() {
  // 从 _index.json 通过 /list 端点已聚合到 source_file_count，但需明细列表
  // 复用 GET /api/projects/{pid}/wp-templates/list 拿不到子文件名细节
  // 因此直接读取后端 _index.json 资源文件（前端无端点暴露此清单）
  // 退化策略：从 /list items 中筛选 wp_code 与本主编码匹配/前缀匹配的（如有）
  if (!props.projectId || !props.wpCode) {
    sourceFiles.value = []
    return
  }
  try {
    // 后端 _index.json 不直接暴露端点，使用本主编码的占位（数量与 source_file_count 一致）
    // 真实场景：可由后端新增 /api/projects/{pid}/wp-templates/{wp_code}/source-files 端点
    // 当前 fallback：构造单条主文件占位条目
    const tpl = template.value
    if (!tpl) {
      sourceFiles.value = []
      return
    }
    const cnt = tpl.source_file_count || 0
    if (cnt <= 1) {
      // 单文件场景，主文件即源文件
      sourceFiles.value = tpl.filename ? [{
        wp_code: tpl.wp_code,
        filename: tpl.filename,
        format: tpl.format,
      }] : []
    } else {
      // 多文件场景：暂仅展示数量，文件名详情待后端补充端点
      sourceFiles.value = Array.from({ length: cnt }, (_, i) => ({
        wp_code: i === 0 ? tpl.wp_code : `${tpl.wp_code}-${i + 1}`,
        filename: i === 0 ? (tpl.filename || `${tpl.wp_code}.${tpl.format || 'xlsx'}`) : `${tpl.wp_code} 子文件 ${i + 1}（详情待后端补充端点）`,
        format: tpl.format,
      }))
    }
  } catch {
    sourceFiles.value = []
  }
}

async function loadPrefillFormulas() {
  try {
    const data = await api.get(P_tlm.prefillFormulas)
    const allMappings = (data?.mappings || []) as PrefillMappingRaw[]
    const matched = allMappings.filter(m => m.wp_code === props.wpCode)
    const flat: PrefillCellRow[] = []
    for (const m of matched) {
      for (const c of m.cells || []) {
        flat.push({
          sheet: m.sheet,
          cell_ref: c.cell_ref,
          formula: c.formula,
          formula_type: c.formula_type,
          description: c.description,
        })
      }
    }
    prefillCells.value = flat
  } catch {
    prefillCells.value = []
  }
}

async function loadCrossWpReferences() {
  try {
    const data = await api.get(P_tlm.crossWpReferences)
    const allRefs = (data?.references || []) as CrossWpReference[]
    incomingRefs.value = allRefs.filter(r => r.source_wp !== props.wpCode
      && (r.targets || []).some(t => t.wp_code === props.wpCode))
    outgoingRefs.value = allRefs.filter(r => r.source_wp === props.wpCode)
  } catch {
    incomingRefs.value = []
    outgoingRefs.value = []
  }
}

async function loadAll() {
  if (!props.wpCode || !props.projectId) {
    return
  }
  loading.value = true
  try {
    await loadTemplate()
    // template 加载完成后并行加载其他数据
    await Promise.all([
      loadSourceFiles(),
      loadPrefillFormulas(),
      loadCrossWpReferences(),
    ])
    // note_section 从 procedure_steps 或后续后端字段提取（暂从 prefill 中没有）
    noteSection.value = (template.value as any)?.note_section || ''
  } finally {
    loading.value = false
  }
}

// ─── 主文件下载 ───────────────────────────────────────────────────────────

function onDownloadMain() {
  if (!props.projectId || !props.wpCode) return
  // 直接通过浏览器跳转到下载端点（带 token 由 axios 拦截器或 cookie 处理；
  // 这里使用 window.open 简化处理；如需 blob 下载可改 api.get blob）
  const url = P_wp.templateDownload(props.projectId, props.wpCode)
  window.open(url, '_blank')
}

// ─── 生命周期 ─────────────────────────────────────────────────────────────

onMounted(loadAll)

watch(
  () => [props.wpCode, props.projectId] as [string, string],
  () => loadAll(),
  { deep: false },
)
</script>

<style scoped>
.gt-wpd {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

/* D8 ADR：数字列 */
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.gt-wpd-card {
  background: var(--gt-color-bg-white);
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 16px;
}

.gt-wpd-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin-bottom: 12px;
}
.gt-wpd-card-title--inline { margin-bottom: 0; }

/* 基本信息 */
.gt-wpd-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.gt-wpd-meta-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}
.gt-wpd-meta-label {
  color: var(--gt-color-info);
  min-width: 80px;
  flex-shrink: 0;
}
.gt-wpd-meta-value {
  color: var(--gt-color-text-primary);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-wpd-empty { color: var(--gt-color-text-placeholder); }
.gt-wpd-code {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
  padding: 2px 8px;
  border-radius: 3px;
}
.gt-wpd-code-small {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
  padding: 1px 6px;
  border-radius: 3px;
}
.gt-wpd-format-icon { font-size: var(--gt-font-size-md); margin-right: 2px; }
.gt-wpd-acc-tag { margin-right: 4px; margin-bottom: 4px; }
.gt-wpd-comp--univer { background: var(--gt-bg-info); color: var(--gt-color-teal); border-color: #c2dafc; }
.gt-wpd-comp--form { background: var(--gt-color-success-light); color: var(--gt-color-success); border-color: #b6e3b6; }
.gt-wpd-comp--word { background: var(--gt-bg-warning); color: var(--gt-color-wheat); border-color: #f5d4a8; }
.gt-wpd-comp--hybrid { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); border-color: #d8b8ee; }

/* 主文件下载区 */
.gt-wpd-main-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg);
  border: 1px solid #e0d7ed;
  border-radius: 6px;
}
.gt-wpd-main-file-info { display: flex; flex-direction: column; gap: 6px; }
.gt-wpd-main-file-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
}
.gt-wpd-main-file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.gt-wpd-divider { color: var(--gt-color-text-placeholder); }

/* 公式 */
.gt-wpd-formula {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  background: var(--gt-color-bg);
  padding: 1px 6px;
  border-radius: 3px;
  color: var(--gt-color-primary);
}
.gt-wpd-fmtype--tb { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.gt-wpd-fmtype--tb_sum { background: var(--gt-bg-info); color: var(--gt-color-teal); }
.gt-wpd-fmtype--adj { background: var(--gt-bg-warning); color: var(--gt-color-wheat); }
.gt-wpd-fmtype--prev { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.gt-wpd-fmtype--wp { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }

/* 跨底稿引用 */
.gt-wpd-xref-section {
  margin-top: 8px;
}
.gt-wpd-xref-section:first-of-type { margin-top: 0; }
.gt-wpd-xref-section-title {
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  margin-bottom: 6px;
}
.gt-wpd-xref-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-wpd-xref-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gt-font-size-xs);
  padding: 4px 8px;
  background: var(--gt-color-bg);
  border-radius: 3px;
}
.gt-wpd-xref-arrow { color: var(--gt-color-info); }
.gt-wpd-xref-target { display: inline-flex; gap: 2px; }
.gt-wpd-xref-desc { color: var(--gt-color-text-regular); margin-left: 4px; }

/* 源文件提示 */
.gt-wpd-source-hint {
  margin-top: 8px;
  padding: 6px 10px;
  background: var(--gt-bg-warning);
  color: var(--gt-color-wheat);
  font-size: var(--gt-font-size-xs);
  border-radius: 3px;
  border-left: 3px solid #e6a23c;
}

/* 项目使用 */
.gt-wpd-usage {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-wpd-usage-stat {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--gt-font-size-sm);
}
.gt-wpd-usage-label { color: var(--gt-color-info); }
.gt-wpd-usage-note {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-placeholder);
  font-style: italic;
}
</style>
