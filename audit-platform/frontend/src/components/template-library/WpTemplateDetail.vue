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

    <!-- 1b. 模板来源与编辑（spec excel-template-override-layer Task 20） -->
    <div class="gt-wpd-card" data-testid="wpd-override-card">
      <div class="gt-wpd-card-title">
        <el-icon><EditPen /></el-icon>模板来源与编辑
        <div class="gt-wpd-ovr-actions">
          <el-tooltip
            :disabled="overrideEditable"
            :content="overrideResolution?.not_editable_reason || ''"
            placement="top"
          >
            <span>
              <el-button
                size="small"
                type="primary"
                :disabled="!overrideEditable"
                :loading="overrideBusy"
                data-testid="wpd-override-edit"
                @click="onEditTemplate"
              >
                在线编辑
              </el-button>
            </span>
          </el-tooltip>
          <el-button
            size="small"
            :loading="overrideBusy"
            data-testid="wpd-override-upload"
            @click="onPickReplacementFile"
          >
            上传替换
          </el-button>
          <el-button
            size="small"
            text
            data-testid="wpd-override-history"
            @click="onOpenVersionHistory"
          >
            版本历史
          </el-button>
        </div>
      </div>
      <div class="gt-wpd-meta">
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">当前来源</span>
          <span class="gt-wpd-meta-value">
            <el-tag
              v-if="overrideResolution"
              size="small"
              :type="originTagType"
              effect="light"
              data-testid="wpd-override-origin"
            >
              {{ overrideResolution.origin_label }}
            </el-tag>
            <span v-else class="gt-wpd-empty">—</span>
          </span>
        </div>
        <div class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">覆盖版本</span>
          <span class="gt-wpd-meta-value">
            <span v-if="overrideResolution?.version_id" class="gt-wpd-code">
              {{ shortVersion(overrideResolution.version_id) }}
            </span>
            <span v-else class="gt-wpd-empty">未覆盖，使用权威模板</span>
          </span>
        </div>
        <div v-if="overrideResolution && !overrideEditable" class="gt-wpd-meta-row">
          <span class="gt-wpd-meta-label">在线编辑</span>
          <span class="gt-wpd-meta-value gt-wpd-ovr-reason" data-testid="wpd-override-reason">
            不可用 —— {{ overrideResolution.not_editable_reason }}
            <br />可用「上传替换」产生覆盖版本，同样进版本表、同样可回滚。
          </span>
        </div>
      </div>
    </div>

    <!-- 上传替换的隐藏 file input（走与在线编辑同一条后端落盘路径，AC 5.5） -->
    <input
      ref="replacementInputRef"
      type="file"
      class="gt-wpd-hidden-file"
      data-testid="wpd-override-file-input"
      @change="onReplacementFileChosen"
    />

    <!-- 在线编辑弹窗：OnlyOffice 整本模式 -->
    <el-dialog
      v-model="editorOpen"
      :title="`在线编辑模板 · ${wpCode}`"
      width="92%"
      top="4vh"
      destroy-on-close
      :close-on-click-modal="false"
      @closed="onEditorClosed"
    >
      <div class="gt-wpd-ovr-editor-hint">
        全部 sheet 已展开，可直接查看与修改 sheet 间公式。保存后会生成一个新的覆盖版本，
        权威模板本身不被改动。
      </div>
      <div :id="editorContainerId" class="gt-wpd-ovr-editor"></div>
    </el-dialog>

    <!-- 版本历史 -->
    <el-drawer v-model="versionsOpen" title="模板覆盖版本历史" size="46%">
      <el-table
        :data="overrideVersions"
        size="small"
        :border="false"
        highlight-current-row
        empty-text="该作用域下还没有覆盖版本"
      >
        <el-table-column label="版本" width="120">
          <template #default="{ row }">
            <span class="gt-wpd-code">{{ shortVersion(row.version_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="作用域" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.scope_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_current" size="small" type="success" effect="light">当前</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">历史</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" width="120">
          <template #default="{ row }">
            <span class="gt-wpd-code">{{ row.sha256.slice(0, 10) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_current"
              size="small"
              text
              type="primary"
              @click="onPromoteVersion(row)"
            >
              回滚到此版本
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button
          v-if="overrideResolution?.version_id"
          type="danger"
          plain
          size="small"
          @click="onDeleteOverride"
        >
          删除覆盖（回落权威模板）
        </el-button>
      </template>
    </el-drawer>

    <!-- 1.5 高级查询入口按钮 (Req 14 AC 1) + 公式预设库入口 (Req 25.1) -->
    <div class="gt-wpd-card gt-wpd-card--actions">
      <TemplateLibraryButton
        :source="templateSource"
        :project-id="props.projectId"
      />
      <el-button
        type="primary"
        size="default"
        plain
        @click="presetDialogVisible = true"
      >
        🧮 公式预设库
      </el-button>
    </div>

    <!-- Req 25: 公式预设库弹窗（说明文档 + 预设浏览/编辑） -->
    <GtFormulaPresetDialog
      v-model="presetDialogVisible"
      scope="workpaper"
      :page-key="`workpaper:${props.wpCode}`"
    />

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
        <el-button
          v-if="canPreview"
          size="default"
          :disabled="!projectId || officeAvailable === false"
          :title="officeAvailable === false ? '服务器未安装 LibreOffice，无法在线预览' : ''"
          @click="onPreviewMain"
        >
          <el-icon style="margin-right: 4px"><View /></el-icon>在线预览
        </el-button>
      </div>
    </div>

    <!-- 预览抽屉：模板主文件转 PDF iframe -->
    <el-drawer
      v-model="previewOpen"
      :title="`预览 — ${template?.filename || wpCode}`"
      direction="rtl"
      size="60%"
      :close-on-click-modal="true"
      append-to-body
    >
      <iframe
        v-if="previewOpen && previewUrl"
        :src="previewUrl"
        class="gt-wpd-preview-frame"
      />
    </el-drawer>

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
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import {
  InfoFilled,
  Download,
  EditPen,
  Files,
  FolderOpened,
  DataAnalysis,
  Connection,
  DataLine,
  View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  templateLibraryMgmt as P_tlm,
  workpapers as P_wp,
  officePreview as P_office,
} from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import TemplateLibraryButton from './TemplateLibraryButton.vue'
import GtFormulaPresetDialog from '@/components/formula/GtFormulaPresetDialog.vue'

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

// 高级查询 source URI（Req 14 AC 1）
const templateSource = computed(() => `workpaper:${props.wpCode}`)

// Req 25.1: 公式预设库弹窗开关
const presetDialogVisible = ref(false)

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
      loadOverrideResolution(),
    ])
    // note_section 从 procedure_steps 或后续后端字段提取（暂从 prefill 中没有）
    noteSection.value = (template.value as any)?.note_section || ''
  } finally {
    loading.value = false
  }
}

// ─── 模板覆盖层（spec excel-template-override-layer Task 20）────────────────
//
// 🔴 来源与版本号**只**取后端下发的字段（Property 21）。
//    前端不得据文件名/路径推断来源 —— 那会在两处各写一份优先级规则，
//    而覆盖层的优先级（project > group_custom > firm_default > 权威）只有后端知道。

interface OverrideResolution {
  wp_code: string
  origin: string
  origin_label: string
  path_name: string
  extension: string
  sha256: string
  version_id: string | null
  editable_in_browser: boolean
  not_editable_reason: string | null
}

interface OverrideVersionRow {
  version_id: string
  wp_code: string
  authoritative_stem: string
  scope: string
  scope_label: string
  sha256: string
  is_current: boolean
  parent_version_id: string | null
  created_by: string | null
  created_at: string | null
}

const overrideResolution = ref<OverrideResolution | null>(null)
const overrideVersions = ref<OverrideVersionRow[]>([])
const overrideBusy = ref(false)
const editorOpen = ref(false)
const versionsOpen = ref(false)
const replacementInputRef = ref<HTMLInputElement | null>(null)
const editorContainerId = 'gt-wpd-ovr-editor-container'
let ooEditorInstance: any = null
let currentSessionId = ''

/** 是否可在浏览器内编辑 —— **取后端字段**，不在前端按扩展名判断。 */
const overrideEditable = computed(() => overrideResolution.value?.editable_in_browser === true)

/** 来源标签的配色。映射的是后端下发的 `origin` 值，不是文件名。 */
const originTagType = computed<'success' | 'warning' | 'primary' | 'info'>(() => {
  const origin = overrideResolution.value?.origin || ''
  if (origin === 'authoritative') return 'info'
  if (origin === 'override:project') return 'warning'
  if (origin === 'override:group_custom') return 'primary'
  return 'success'
})

function shortVersion(versionId: string): string {
  return versionId.length > 10 ? versionId.slice(0, 8) : versionId
}

async function loadOverrideResolution() {
  if (!props.wpCode) {
    overrideResolution.value = null
    return
  }
  try {
    const data = await api.get(P_tlm.overrideResolution(props.wpCode))
    overrideResolution.value = (data || null) as OverrideResolution | null
  } catch {
    // 模板库里没有该 wp_code（如自定义底稿）时后端返 404 —— 不是错误，只是没有可覆盖对象
    overrideResolution.value = null
  }
}

async function loadOverrideVersions() {
  if (!props.wpCode) return
  try {
    const data = await api.get(P_tlm.overrideVersions(props.wpCode))
    overrideVersions.value = (data || []) as OverrideVersionRow[]
  } catch (e) {
    handleApiError(e, '加载覆盖版本失败')
    overrideVersions.value = []
  }
}

async function onOpenVersionHistory() {
  versionsOpen.value = true
  await loadOverrideVersions()
}

function loadOnlyOfficeScript(baseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).DocsAPI) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = `${baseUrl}/web-apps/apps/api/documents/api.js`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('OnlyOffice api.js 加载失败'))
    document.head.appendChild(script)
  })
}

async function onEditTemplate() {
  if (!props.wpCode || !overrideEditable.value) return
  overrideBusy.value = true
  try {
    const data = await api.post(P_tlm.overrideEditSession(props.wpCode), {})
    currentSessionId = data?.session_id || ''
    const config = data?.onlyoffice_config
    if (!config) {
      ElMessage.error('后端未返回编辑器配置')
      return
    }
    editorOpen.value = true
    await nextTick()

    const baseUrl = (import.meta as any).env?.VITE_ONLYOFFICE_URL || ''
    if (!baseUrl) {
      ElMessage.error('未配置 OnlyOffice 服务地址（VITE_ONLYOFFICE_URL）')
      return
    }
    await loadOnlyOfficeScript(baseUrl)
    const DocsAPI = (window as any).DocsAPI
    if (!DocsAPI) {
      ElMessage.error('OnlyOffice 编辑器不可用')
      return
    }
    ooEditorInstance = new DocsAPI.DocEditor(editorContainerId, config)
  } catch (e) {
    handleApiError(e, '打开模板编辑器失败')
  } finally {
    overrideBusy.value = false
  }
}

function onEditorClosed() {
  if (ooEditorInstance?.destroyEditor) {
    try {
      ooEditorInstance.destroyEditor()
    } catch {
      // 编辑器已自行销毁
    }
  }
  ooEditorInstance = null
  currentSessionId = ''
  // 关闭后刷新来源 —— 保存是异步的（OO callback），此时可能已产生新版本
  void loadOverrideResolution()
}

function onPickReplacementFile() {
  replacementInputRef.value?.click()
}

/** 打印设置（纸张/缩放/方向…）与被替换的那份不一致时提示。
 *
 * 🔴 不是错误：换模板顺带调打印设置是合法操作。但它在 UI 上完全看不见，
 * 而审计底稿是要打印装订的 —— 悄悄从 A4 纵向变成 A3 横向，出片时才发现代价很大。
 * 后端只对 xlsx/xlsm 比对，其余格式恒空数组。
 */
function notifyPageSetupChanges(changes: unknown): void {
  if (!Array.isArray(changes) || changes.length === 0) return
  const failed = changes.find((c: any) => c?.sheet_part === '<比对失败>')
  if (failed) {
    ElMessage.warning('已保存，但打印设置比对未能完成，请自行核对纸张与缩放')
    return
  }
  const shown = changes
    .slice(0, 3)
    .map((c: any) => `${PAGE_SETUP_LABELS[c?.attribute] || c?.attribute}：${c?.before} → ${c?.after}`)
    .join('；')
  const more = changes.length > 3 ? ` 等 ${changes.length} 处` : ''
  ElMessage.warning(`已保存。打印设置与原模板不同 —— ${shown}${more}`)
}

/** `pageSetup` 属性名 → 中文（UI 全中文化铁律）。未登记的属性直接显示原名。 */
const PAGE_SETUP_LABELS: Record<string, string> = {
  paperSize: '纸张',
  scale: '缩放',
  orientation: '方向',
  fitToWidth: '横向页数',
  fitToHeight: '纵向页数',
  firstPageNumber: '起始页码',
  useFirstPageNumber: '使用起始页码',
  blackAndWhite: '黑白打印',
  draft: '草稿质量',
  copies: '打印份数',
  pageOrder: '打印顺序',
  cellComments: '批注打印',
  errors: '错误值打印',
}

async function onReplacementFileChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.wpCode) return

  const expected = overrideResolution.value?.extension || ''
  const actual = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (expected && actual !== expected) {
    ElMessage.error(`扩展名必须与权威模板一致（需要 ${expected}，选择的是 ${actual}）`)
    return
  }

  overrideBusy.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post(P_tlm.overrideUpload(props.wpCode), form)
    ElMessage.success('已上传并生成新的覆盖版本')
    notifyPageSetupChanges(data?.page_setup_changes)
    await loadOverrideResolution()
    if (versionsOpen.value) await loadOverrideVersions()
  } catch (e) {
    handleApiError(e, '上传替换失败')
  } finally {
    overrideBusy.value = false
  }
}

async function onPromoteVersion(row: OverrideVersionRow) {
  if (!props.wpCode) return
  try {
    await ElMessageBox.confirm(
      `将把版本 ${shortVersion(row.version_id)} 置为当前版本。历史版本不会被删除，之后仍可回滚。`,
      '回滚模板覆盖',
      { type: 'warning', confirmButtonText: '确认回滚', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  overrideBusy.value = true
  try {
    await api.post(P_tlm.overridePromote(props.wpCode, row.version_id), {})
    ElMessage.success('已回滚')
    await Promise.all([loadOverrideResolution(), loadOverrideVersions()])
  } catch (e) {
    handleApiError(e, '回滚失败')
  } finally {
    overrideBusy.value = false
  }
}

async function onDeleteOverride() {
  if (!props.wpCode) return
  try {
    await ElMessageBox.confirm(
      '删除覆盖后将回落到权威模板。版本记录不会被删除，之后仍可回滚到任一历史版本。',
      '删除模板覆盖',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  overrideBusy.value = true
  try {
    await api.delete(P_tlm.overrideDeleteCurrent(props.wpCode))
    ElMessage.success('已删除覆盖，现在使用权威模板')
    await Promise.all([loadOverrideResolution(), loadOverrideVersions()])
  } catch (e) {
    handleApiError(e, '删除覆盖失败')
  } finally {
    overrideBusy.value = false
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

// ─── 在线预览（LibreOffice 转 PDF）─────────────────────────────────────────
// 模块级缓存：health 探测结果，避免每次开抽屉都打后端
let officeHealthCache: boolean | null = null
const officeAvailable = ref<boolean | null>(officeHealthCache)
const previewOpen = ref(false)

const OFFICE_EXTS = ['xlsx', 'xls', 'xlsm', 'docx', 'doc', 'pptx', 'ppt']
const canPreview = computed(() => {
  const f = (template.value?.format || '').toLowerCase()
  return OFFICE_EXTS.includes(f)
})
const previewUrl = computed(() => {
  if (!props.projectId || !props.wpCode) return ''
  return P_wp.templatePreviewPdf(props.projectId, props.wpCode)
})

async function probeOfficeHealth() {
  if (officeHealthCache !== null) {
    officeAvailable.value = officeHealthCache
    return
  }
  try {
    const data: any = await api.get(P_office.health)
    officeHealthCache = !!data?.available
    officeAvailable.value = officeHealthCache
  } catch {
    officeHealthCache = false
    officeAvailable.value = false
  }
}

async function onPreviewMain() {
  if (officeAvailable.value === null) await probeOfficeHealth()
  if (officeAvailable.value === false) {
    handleApiError(new Error('服务器未安装 LibreOffice，无法在线预览'), '在线预览')
    return
  }
  previewOpen.value = true
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
/* ─── 模板覆盖层（Task 20）───────────────────────────────────────────────── */
.gt-wpd-ovr-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
}
.gt-wpd-hidden-file {
  display: none;
}
.gt-wpd-ovr-reason {
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.5;
}
.gt-wpd-ovr-editor-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  padding: 6px 10px;
  margin-bottom: 8px;
  line-height: 1.6;
}
.gt-wpd-ovr-editor {
  width: 100%;
  height: 72vh;
}

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
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 12px 16px;
}
.gt-wpd-card--actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
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
.gt-wpd-comp--univer { background: var(--gt-bg-info); color: var(--gt-color-teal); border-color: var(--gt-color-border-info); }
.gt-wpd-comp--form { background: var(--gt-color-success-light); color: var(--gt-color-success); border-color: var(--gt-color-border-success); }
.gt-wpd-comp--word { background: var(--gt-bg-warning); color: var(--gt-color-wheat); border-color: var(--gt-color-border-warning); }
.gt-wpd-comp--hybrid { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); border-color: var(--gt-color-border-purple-light); }

/* 主文件下载区 */
.gt-wpd-main-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg);
  border: 1px solid var(--gt-color-border-purple);
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
  border-left: 3px solid var(--gt-color-wheat);
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

/* 在线预览 iframe */
.gt-wpd-preview-frame {
  width: 100%;
  height: calc(100vh - 120px);
  border: none;
  border-radius: 4px;
}
</style>
