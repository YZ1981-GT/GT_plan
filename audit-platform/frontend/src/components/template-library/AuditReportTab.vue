<!--
  AuditReportTab.vue — 审计报告模板 Tab [template-library-coordination Sprint 4.1]

  需求 9.1-9.6：
  - 卡片形式展示 8 种意见类型（unqualified/qualified/adverse/disclaimer × non_listed/listed）
  - 点击展示段落列表（审计意见段/形成基础段/关键审计事项段/其他信息段/管理层责任段/治理层责任段/CPA 责任段）
  - 显示占位符列表及说明
  - 段落完整性检查（必填段落缺失红色警告）

  数据源：GET /api/audit-report/templates
  D13 ADR：JSON 源只读 — backend/data/audit_report_templates_seed.json，UI 不提供编辑入口
  D8 ADR：数字列 .gt-amt class
-->
<template>
  <div class="gt-art" v-loading="loading">
    <!-- D13 ADR：JSON 源只读引导横幅（通过 useTemplateLibrarySource 统一管理文案） -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="gt-art-alert"
    >
      <template #title>
        <span class="gt-art-alert-title">
          <el-tag type="info" size="small" effect="plain" round style="margin-right: 6px">
            {{ readonlyBadge }}
          </el-tag>
          <el-tooltip :content="auditReadonlyHint" placement="top">
            <span>{{ auditReadonlyHint }}</span>
          </el-tooltip>
        </span>
      </template>
    </el-alert>

    <!-- 顶部统计 -->
    <div class="gt-art-stats">
      <span class="gt-art-stats-item">
        意见类型组合：
        <span class="gt-amt">{{ templates.length }}</span> /
        <span class="gt-amt">8</span>
      </span>
      <span class="gt-art-stats-item">
        段落总数：<span class="gt-amt">{{ totalSectionCount }}</span>
      </span>
      <span class="gt-art-stats-item gt-art-stats-warn" v-if="incompleteCount > 0">
        ⚠ 必填段落缺失：<span class="gt-amt">{{ incompleteCount }}</span> 个组合
      </span>
    </div>

    <!-- 8 种组合卡片网格（4 列 × 2 行） -->
    <el-empty
      v-if="!loading && templates.length === 0"
      description="暂无审计报告模板数据，请通过 reseed 加载"
    />
    <div v-else class="gt-art-grid">
      <div
        v-for="cell in cells"
        :key="`${cell.opinion_type}_${cell.company_type}`"
        class="gt-art-card"
        :class="{
          'gt-art-card--missing': !cell.template,
          'gt-art-card--incomplete': cell.template && cell.missingRequired.length > 0,
          'gt-art-card--selected': isSelected(cell),
        }"
        @click="onCardClick(cell)"
      >
        <div class="gt-art-card-header">
          <span class="gt-art-card-opinion" :class="`gt-art-opinion--${cell.opinion_type}`">
            {{ opinionLabel(cell.opinion_type) }}
          </span>
          <el-tag
            :type="cell.company_type === 'listed' ? 'warning' : 'info'"
            size="small"
            effect="plain"
            round
          >
            {{ cell.company_type === 'listed' ? '上市公司' : '非上市' }}
          </el-tag>
        </div>
        <div class="gt-art-card-body">
          <template v-if="cell.template">
            <div class="gt-art-card-stat">
              段落数 <span class="gt-amt">{{ cell.template.sections.length }}</span>
            </div>
            <div v-if="cell.missingRequired.length > 0" class="gt-art-card-warn">
              ⚠ 缺 {{ cell.missingRequired.length }} 必填段
            </div>
            <div v-else class="gt-art-card-ok">✓ 必填段落完整</div>
          </template>
          <template v-else>
            <div class="gt-art-card-missing-text">未加载</div>
          </template>
        </div>
      </div>
    </div>

    <!-- 段落详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerTitle"
      direction="rtl"
      size="50%"
      :destroy-on-close="false"
    >
      <div v-if="selectedCell?.template" class="gt-art-detail">
        <!-- 元信息 -->
        <div class="gt-art-detail-meta">
          <el-tag :type="selectedCell.company_type === 'listed' ? 'warning' : 'info'" size="small">
            {{ selectedCell.company_type === 'listed' ? '上市公司' : '非上市' }}
          </el-tag>
          <el-tag size="small" effect="plain">只读</el-tag>
          <span class="gt-art-detail-count">
            共 <span class="gt-amt">{{ selectedCell.template.sections.length }}</span> 个段落
          </span>
          <span v-if="selectedCell.missingRequired.length > 0" class="gt-art-detail-warn">
            ⚠ 缺失必填：{{ selectedCell.missingRequired.join('、') }}
          </span>
        </div>

        <!-- 段落列表 -->
        <el-collapse v-model="expandedSections" class="gt-art-sections">
          <el-collapse-item
            v-for="sec in sortedSections"
            :key="sec.section_name || sec.section_order"
            :name="sec.section_name"
          >
            <template #title>
              <span class="gt-art-section-title">
                <span class="gt-amt gt-art-section-order">#{{ sec.section_order }}</span>
                <span class="gt-art-section-name">{{ sec.section_name }}</span>
                <el-tag v-if="sec.is_required" type="danger" size="small" effect="plain" round>必填</el-tag>
                <el-tag v-else type="info" size="small" effect="plain" round>可选</el-tag>
              </span>
            </template>
            <div class="gt-art-section-body">
              <div class="gt-art-section-text">{{ sec.template_text }}</div>
              <!-- 占位符列表 -->
              <div v-if="getPlaceholders(sec.template_text).length > 0" class="gt-art-placeholders">
                <div class="gt-art-placeholders-title">占位符（{{ getPlaceholders(sec.template_text).length }}）</div>
                <div class="gt-art-placeholders-list">
                  <el-tooltip
                    v-for="ph in getPlaceholders(sec.template_text)"
                    :key="ph"
                    :content="placeholdersDoc[ph] || '（未知占位符）'"
                    placement="top"
                  >
                    <code class="gt-art-placeholder-tag">{{ ph }}</code>
                  </el-tooltip>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 缺失的必填段落（红色提示） -->
        <div v-if="selectedCell.missingRequired.length > 0" class="gt-art-missing">
          <h4 class="gt-art-missing-title">⚠ 缺失的必填段落</h4>
          <ul class="gt-art-missing-list">
            <li v-for="name in selectedCell.missingRequired" :key="name" class="gt-art-missing-item">
              {{ name }}
            </li>
          </ul>
        </div>
      </div>
      <el-empty v-else description="该组合模板未加载" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import { auditReport as P_ar } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useTemplateLibrarySource } from '@/composables/useTemplateLibrarySource'

// ─── D13 ADR：只读源统一文案管理 ───
const { getReadonlyHint, getReadonlyBadgeText } = useTemplateLibrarySource()
const auditReadonlyHint = getReadonlyHint('audit_report_templates')
const readonlyBadge = getReadonlyBadgeText()

// ─── 类型 ─────────────────────────────────────────────────────────────────
interface AuditReportSection {
  section_name: string
  section_order: number
  is_required: boolean
  template_text: string
}

interface AuditReportTemplate {
  id?: string
  opinion_type: 'unqualified' | 'qualified' | 'adverse' | 'disclaimer'
  company_type: 'listed' | 'non_listed'
  // 后端 /templates 返回扁平结构（一行一段落），需要按 (opinion_type, company_type) 聚合
  section_name?: string
  section_order?: number
  template_text?: string
  is_required?: boolean
  // 也可能后端返回嵌套（含 sections 数组）— 兼容两种格式
  sections?: AuditReportSection[]
}

interface CellTemplate {
  opinion_type: string
  company_type: string
  sections: AuditReportSection[]
}

interface Cell {
  opinion_type: string
  company_type: string
  template: CellTemplate | null
  missingRequired: string[]
}

// ─── State ────────────────────────────────────────────────────────────────
const loading = ref(false)
const templates = ref<CellTemplate[]>([])
const placeholdersDoc = ref<Record<string, string>>({})
const drawerVisible = ref(false)
const selectedCell = ref<Cell | null>(null)
const expandedSections = ref<string[]>([])

// 必填段落标准清单（按 spec 需求 9.4）— 与 audit_report_templates_seed.json 对齐
const REQUIRED_SECTIONS = [
  '审计意见段',
  '形成审计意见的基础段',
  '管理层对财务报表的责任段',
  '治理层对财务报表的责任段',
  '注册会计师对财务报表审计的责任段',
]

// ─── 8 种组合（4 意见 × 2 公司类型） ─────────────────────────────────────
const OPINION_TYPES = ['unqualified', 'qualified', 'adverse', 'disclaimer'] as const
const COMPANY_TYPES = ['non_listed', 'listed'] as const

const OPINION_LABELS: Record<string, string> = {
  unqualified: '无保留意见',
  qualified: '保留意见',
  adverse: '否定意见',
  disclaimer: '无法表示意见',
}

function opinionLabel(code: string): string {
  return OPINION_LABELS[code] || code
}

// ─── 数据加载 ─────────────────────────────────────────────────────────────
async function loadTemplates() {
  loading.value = true
  try {
    const data = await api.get(P_ar.templates)
    const list = Array.isArray(data) ? data : (data?.items || [])
    // 按 (opinion_type, company_type) 聚合段落（后端返回扁平结构，每行=一个段落）
    const groupMap = new Map<string, CellTemplate>()
    for (const row of list as AuditReportTemplate[]) {
      const ot = row.opinion_type
      const ct = row.company_type
      if (!ot || !ct) continue
      const key = `${ot}_${ct}`
      if (!groupMap.has(key)) {
        groupMap.set(key, { opinion_type: ot, company_type: ct, sections: [] })
      }
      const tpl = groupMap.get(key)!
      // 兼容嵌套 sections 数组
      if (Array.isArray(row.sections) && row.sections.length > 0) {
        for (const s of row.sections) {
          tpl.sections.push({
            section_name: s.section_name || '',
            section_order: s.section_order ?? 0,
            is_required: s.is_required !== false,
            template_text: s.template_text || '',
          })
        }
      } else if (row.section_name) {
        tpl.sections.push({
          section_name: row.section_name,
          section_order: row.section_order ?? 0,
          is_required: row.is_required !== false,
          template_text: row.template_text || '',
        })
      }
    }
    templates.value = Array.from(groupMap.values())

    // 尝试加载 placeholders_doc（从模板库管理端点；若不存在则使用内置默认值）
    placeholdersDoc.value = {
      '{entity_name}': '被审计单位全称',
      '{entity_short_name}': '被审计单位简称',
      '{audit_period}': '审计期间（如 2025年12月31日及当年）',
      '{audit_year}': '审计年度',
      '{report_scope}': '报表范围（合并/单体）',
    }
  } catch (e: any) {
    handleApiError(e, '加载审计报告模板')
    templates.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadTemplates)

// ─── 计算属性 ─────────────────────────────────────────────────────────────
const cells = computed<Cell[]>(() => {
  const result: Cell[] = []
  for (const ot of OPINION_TYPES) {
    for (const ct of COMPANY_TYPES) {
      const tpl = templates.value.find(t => t.opinion_type === ot && t.company_type === ct) ?? null
      const sectionNames = new Set((tpl?.sections || []).map(s => s.section_name))
      const missingRequired = tpl
        ? REQUIRED_SECTIONS.filter(req => !sectionNames.has(req))
        : []
      result.push({
        opinion_type: ot,
        company_type: ct,
        template: tpl,
        missingRequired,
      })
    }
  }
  return result
})

const totalSectionCount = computed(() =>
  templates.value.reduce((sum, t) => sum + t.sections.length, 0),
)

const incompleteCount = computed(() =>
  cells.value.filter(c => c.template && c.missingRequired.length > 0).length,
)

const sortedSections = computed<AuditReportSection[]>(() => {
  if (!selectedCell.value?.template) return []
  return [...selectedCell.value.template.sections].sort(
    (a, b) => (a.section_order ?? 0) - (b.section_order ?? 0),
  )
})

const drawerTitle = computed(() => {
  if (!selectedCell.value) return ''
  return `${opinionLabel(selectedCell.value.opinion_type)} · ${
    selectedCell.value.company_type === 'listed' ? '上市公司' : '非上市'
  }`
})

// ─── 交互 ─────────────────────────────────────────────────────────────────
function isSelected(cell: Cell): boolean {
  if (!selectedCell.value) return false
  return (
    selectedCell.value.opinion_type === cell.opinion_type &&
    selectedCell.value.company_type === cell.company_type &&
    drawerVisible.value
  )
}

function onCardClick(cell: Cell) {
  selectedCell.value = cell
  drawerVisible.value = true
  // 默认展开第一个段落
  if (cell.template && cell.template.sections.length > 0) {
    const first = [...cell.template.sections].sort(
      (a, b) => (a.section_order ?? 0) - (b.section_order ?? 0),
    )[0]
    expandedSections.value = [first.section_name]
  } else {
    expandedSections.value = []
  }
}

// 提取占位符（{xxx} 格式）
function getPlaceholders(text: string): string[] {
  if (!text) return []
  const matches = text.match(/\{[a-z_][a-z0-9_]*\}/gi) || []
  return Array.from(new Set(matches))
}
</script>

<style scoped>
.gt-art {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

/* ─── D13 只读引导横幅 ─── */
.gt-art-alert {
  flex-shrink: 0;
}
.gt-art-alert-title code {
  background: rgba(75, 45, 119, 0.08);
  color: var(--gt-color-primary);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: var(--gt-font-size-xs);
}

/* ─── 顶部统计 ─── */
.gt-art-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
  border-left: 3px solid var(--gt-color-primary);
  flex-shrink: 0;
}
.gt-art-stats-item {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-art-stats-warn {
  color: var(--gt-color-wheat);
  font-weight: 600;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

/* ─── 卡片网格（4 列 × 2 行） ─── */
.gt-art-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  flex-shrink: 0;
}
.gt-art-card {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  transition: all 0.18s ease;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-art-card:hover {
  border-color: var(--gt-color-primary);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-1px);
}
.gt-art-card--selected {
  background: rgba(75, 45, 119, 0.06);
  border-left: 3px solid var(--gt-color-primary);
  padding-left: 11px;
}
.gt-art-card--missing {
  background: var(--gt-color-bg);
  border-style: dashed;
  opacity: 0.7;
}
.gt-art-card--incomplete {
  border-color: var(--gt-color-border-warning);
}
.gt-art-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.gt-art-card-opinion {
  font-size: var(--gt-font-size-sm);
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.gt-art-opinion--unqualified { color: var(--gt-color-success); }
.gt-art-opinion--qualified { color: var(--gt-color-wheat); }
.gt-art-opinion--adverse { color: var(--gt-color-coral); }
.gt-art-opinion--disclaimer { color: var(--gt-color-info); }
.gt-art-card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-art-card-stat {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-primary);
}
.gt-art-card-warn {
  color: var(--gt-color-wheat);
  font-weight: 600;
  font-size: var(--gt-font-size-xs);
}
.gt-art-card-ok {
  color: var(--gt-color-success);
  font-size: var(--gt-font-size-xs);
}
.gt-art-card-missing-text {
  color: var(--gt-color-text-placeholder);
  font-style: italic;
  font-size: var(--gt-font-size-xs);
}

/* ─── 抽屉详情 ─── */
.gt-art-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 4px;
}
.gt-art-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 6px;
}
.gt-art-detail-count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-art-detail-warn {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-wheat);
  font-weight: 600;
}

.gt-art-sections {
  border-top: 1px solid var(--gt-color-border-lighter);
}
.gt-art-section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}
.gt-art-section-order {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-xs);
}
.gt-art-section-name {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-art-section-body {
  padding: 8px 16px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-art-section-text {
  background: var(--gt-color-bg);
  padding: 12px;
  border-radius: 4px;
  border-left: 3px solid var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
  line-height: 1.6;
  color: var(--gt-color-text-primary);
  white-space: pre-wrap;
}

/* ─── 占位符标签 ─── */
.gt-art-placeholders {
  border-top: 1px dashed var(--gt-color-border-lighter);
  padding-top: 8px;
}
.gt-art-placeholders-title {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  margin-bottom: 6px;
}
.gt-art-placeholders-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gt-art-placeholder-tag {
  display: inline-block;
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary-light);
  padding: 2px 8px;
  border-radius: 3px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  cursor: help;
}

/* ─── 缺失提示 ─── */
.gt-art-missing {
  background: var(--gt-bg-danger);
  border-left: 3px solid var(--gt-color-coral);
  border-radius: 4px;
  padding: 12px 16px;
}
.gt-art-missing-title {
  margin: 0 0 6px 0;
  color: var(--gt-color-wheat);
  font-size: var(--gt-font-size-sm);
}
.gt-art-missing-list {
  margin: 0;
  padding-left: 20px;
  color: var(--gt-color-wheat);
}
.gt-art-missing-item {
  font-size: var(--gt-font-size-xs);
  margin: 2px 0;
}

/* 响应式：窄屏 2 列 */
@media (max-width: 1100px) {
  .gt-art-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
