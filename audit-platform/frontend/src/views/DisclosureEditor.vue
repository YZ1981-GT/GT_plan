<template>
  <div class="gt-disclosure-editor gt-fade-in" :class="{ 'gt-fullscreen': deFullscreen }">
    <!-- 横幅 -->
    <GtPageHeader title="附注编辑" :show-sync-status="true" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :show-template="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :template-value="templateType"
        :template-options="deTemplateOptions"
        :badges="[
          { value: noteList.length + ' 个章节' },
          { label: '金额单位', value: displayPrefs.unitSuffix },
        ]"
        @unit-change="onProjectChange"
        @year-change="(v: number) => { selectedYear = v; onYearChange() }"
        @template-change="handleTemplateChange"
      />
      <template #actions>
        <GtToolbar
          :show-copy="true"
          :show-fullscreen="true"
          :is-fullscreen="deFullscreen"
          :show-export="true"
          export-label="导出Word"
          :show-import="true"
          :show-formula="true"
          @copy="copyNoteTable"
          @fullscreen="toggleDeFullscreen()"
          @export="onExportWord"
          @import="showNoteImport = true"
          @formula="showNoteFormulaManager = true"
        >
          <template #left>
            <el-button size="small" @click="onRefreshFromWP" :loading="refreshLoading">🔄 从底稿刷新</el-button>
            <el-button size="small" @click="onGenerate" :loading="genLoading">📝 生成附注</el-button>
            <el-button size="small" @click="onValidate" :loading="validateLoading">✅ 执行校验</el-button>
          </template>
          <template #right-extra>
            <SharedTemplatePicker
              config-type="note_template"
              :project-id="projectId"
              :get-config-data="getNoteTemplateConfigData"
              @applied="onNoteTemplateApplied"
            />
            <el-button size="small" @click="openStructureEditor">📐 表样编辑</el-button>
            <el-button size="small" @click="showNoteMappingDialog = true">🔄 转换规则</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- R8-S2-03：Stale 状态横幅 -->
    <div v-if="stale.isStale.value" class="gt-stale-banner">
      <span class="gt-stale-icon">⚠️</span>
      <span class="gt-stale-text">
        上游数据已变更（{{ stale.staleCount.value }} 张底稿待重算），附注数据可能过时
      </span>
      <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
        🔄 点击重算
      </el-button>
    </div>

    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <div class="gt-de-body">
      <!-- 左侧：目录树 -->
      <div class="gt-de-sidebar">
        <!-- 单位切换 -->
        <div class="gt-de-unit-bar">
          <span class="gt-de-unit-name">{{ currentProjectName || '—' }}</span>
          <el-select v-if="projectOptions.length > 1" v-model="selectedProjectIdLocal" size="small" style="width: 100%; margin-top: 4px" @change="onSwitchProjectLocal">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
        <!-- 视图切换 -->
        <div class="gt-de-view-toggle">
          <el-radio-group v-model="treeViewMode" size="small">
            <el-radio-button value="tree">树形</el-radio-button>
            <el-radio-button value="flat">平铺</el-radio-button>
          </el-radio-group>
          <el-button size="small" text @click="expandAll" title="全部展开">展开</el-button>
          <el-button size="small" text @click="collapseAll" title="全部收起">收起</el-button>
        </div>
        <el-input v-model="treeSearch" size="small" placeholder="搜索章节..." clearable class="gt-de-tree-search" />
        <div class="gt-de-tree-wrap">
          <!-- 树形视图 -->
          <el-tree
            v-if="treeViewMode === 'tree'"
            :data="filteredTreeData"
            :props="{ label: 'label', children: 'children' }"
            :indent="10"
            highlight-current
            node-key="id"
            @node-click="onNodeClick"
            :default-expanded-keys="['chapter_five']"
            ref="noteTreeRef"
          >
            <template #default="{ data }">
              <div v-if="data.isGroup" class="gt-de-tree-group">
                <span class="gt-de-tree-group-label">{{ data.label }}</span>
              </div>
              <div v-else class="gt-de-tree-node" :class="{ 'gt-de-tree-node-active': currentNote?.id === data.id }">
                <span class="gt-de-tree-label">{{ data.data?.section_title || data.label }}</span>
              </div>
            </template>
          </el-tree>
          <!-- 平铺视图 -->
          <div v-if="treeViewMode === 'flat'" class="gt-de-flat-list">
            <div
              v-for="note in flatNoteList" :key="note.note_section"
              class="gt-de-flat-item"
              :class="{ 'gt-de-flat-item--active': currentNote?.note_section === note.note_section }"
              @click="onFlatItemClick(note)"
            >
              <span class="gt-de-flat-item-title">{{ note.section_title }}</span>
              <el-tag v-if="(note as any).scope === 'consolidated_only'" size="small" type="warning" style="font-size: 10px">合并</el-tag>
            </div>
          </div>
          <div v-if="!filteredTreeData.length && !treeLoading" class="gt-de-empty-hint">
            暂无附注，点击"生成附注"
          </div>
        </div>
      </div>

      <!-- 中间：编辑区 -->
      <div class="gt-de-main" v-loading="detailLoading">
        <!-- 底稿同步失败提示 -->
        <el-alert
          v-if="syncError"
          type="error"
          title="底稿数据同步失败"
          description="无法自动从底稿刷新附注数据"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        >
          <template #default>
            <el-button size="small" @click="onManualRefresh">手动重试</el-button>
          </template>
        </el-alert>
        <template v-if="currentNote">
          <div class="gt-de-editor-header">
            <div>
              <h4 class="gt-de-section-title">
                {{ currentNote.section_title }}
                <transition name="el-fade-in">
                  <span v-if="justSaved" class="gt-de-saved-badge">✓ 已保存</span>
                </transition>
              </h4>
              <span class="gt-de-section-account">{{ currentNote.account_name }}</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <el-tag :type="currentNote.status === 'confirmed' ? 'success' : 'info'" size="small">
                {{ currentNote.status === 'confirmed' ? '已确认' : '草稿' }}
              </el-tag>
            </div>
          </div>

            <!-- 表格型（支持多表格Tab切换） -->
            <div v-if="currentNote.content_type === 'table' || currentNote.content_type === 'mixed'">
              <!-- 多表格Tab -->
              <el-tabs v-if="currentNoteTables.length > 1" v-model="activeTableTab" type="card" size="small" style="margin-bottom: 8px;">
                <el-tab-pane v-for="(tbl, ti) in currentNoteTables" :key="ti" :name="String(ti)" :label="getTableTabLabel(tbl, ti)" />
              </el-tabs>
              <!-- 当前表格 -->
              <el-table ref="deTableRef" v-if="activeTableData?.rows?.length || activeTableData?.headers?.length" :data="activeTableData.rows || []"
                border size="small" style="margin-bottom: 12px"
                :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
                :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap', padding: '4px 0' }"
                :row-style="{ height: '26px' }"
                :cell-style="{ padding: '2px 6px', fontSize: '12px', lineHeight: '20px' }"
                :cell-class-name="deCellClassName"
                @cell-click="onDeCellClick"
                @cell-contextmenu="onDeCellContextMenu">
                <el-table-column v-for="(h, hiRaw) in (activeTableData.headers || [])" :key="hiRaw"
                  :label="h" :min-width="Number(hiRaw) === 0 ? 160 : 120" :align="Number(hiRaw) === 0 ? 'left' : 'right'">
                  <template #default="{ row, $index }">
                    <template v-if="Number(hiRaw) === 0">
                      <span :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
                    </template>
                    <template v-else>
                      <CommentTooltip :comment="deComments.getComment(activeTableData?.section_id || currentNote?.note_section || 'default', $index, Number(hiRaw))">
                      <div class="gt-cell-wrapper">
                        <el-input-number v-if="editMode && !row.is_total"
                          v-model="row.values[Number(hiRaw) - 1]" :controls="false" :precision="2"
                          size="small" style="width: 100%; height: 22px"
                          @change="onCellValueChange($index, Number(hiRaw) - 1, $event)" />
                        <span v-else-if="row.is_total" :class="[{ 'gt-formula-mismatch': isFormulaMismatch(row, Number(hiRaw) - 1) }, displayPrefs.amountClass(getCellValue(row, Number(hiRaw) - 1))]">
                          {{ fmt(getCellValue(row, Number(hiRaw) - 1)) }}
                        </span>
                        <span v-else :class="[{ 'total-val': row.is_total }, displayPrefs.amountClass(getCellValue(row, Number(hiRaw) - 1))]">
                          {{ fmt(getCellValue(row, Number(hiRaw) - 1)) }}
                        </span>
                        <span v-if="getCellMode(row, Number(hiRaw) - 1) === 'auto'" class="gt-cell-source" title="自动提数">📊</span>
                        <span v-else-if="getCellMode(row, Number(hiRaw) - 1) === 'manual'" class="gt-cell-manual" title="手动编辑">✏️</span>
                      </div>
                      </CommentTooltip>
                    </template>
                  </template>
                </el-table-column>
              </el-table>
              <div v-else-if="activeTableData?.headers?.length" style="font-size: 12px; color: #999; padding: 10px; text-align: center; border: 1px dashed #e8e4f0; border-radius: 6px;">
                该表格暂无数据行（可在编辑模式下添加）
              </div>
            </div>

            <!-- 文字型 — TipTap 富文本编辑器 -->
            <div v-if="currentNote.content_type === 'text' || currentNote.content_type === 'mixed'" class="gt-de-tiptap-wrapper">
              <div v-if="editor" class="gt-de-tiptap-toolbar">
                <el-button-group size="small">
                  <el-button @click="editor.chain().focus().toggleBold().run()" :type="editor.isActive('bold') ? 'primary' : ''">B</el-button>
                  <el-button @click="editor.chain().focus().toggleItalic().run()" :type="editor.isActive('italic') ? 'primary' : ''">I</el-button>
                  <el-button @click="editor.chain().focus().toggleBulletList().run()">列表</el-button>
                  <el-button @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">H3</el-button>
                  <el-button @click="editor.chain().focus().undo().run()">撤销</el-button>
                  <el-button @click="editor.chain().focus().redo().run()">重做</el-button>
                </el-button-group>
                <span class="gt-de-toolbar-divider"></span>
                <el-button-group size="small">
                  <el-button @click="onAiContinueWrite" :loading="aiLoading" title="AI续写：在光标位置续写内容">✨ 续写</el-button>
                  <el-button @click="onAiRewriteOpen" :loading="aiLoading" title="AI改写：选中文本后点击改写">✏️ 改写</el-button>
                  <el-button @click="onAiGeneratePolicy" :loading="aiLoading" title="生成标准会计政策文本">📋 生成政策</el-button>
                  <el-button @click="onAiGenerateAnalysis" :loading="aiLoading" title="生成变动分析说明">📊 变动分析</el-button>
                  <el-button @click="onPickKnowledge" title="选择知识库文档作为AI参考上下文">📚 知识库</el-button>
                </el-button-group>
                <span v-if="knowledgeContextText" class="gt-de-ai-hint" style="color: var(--gt-color-teal, #36b37e)">
                  📎 已加载 {{ knowledgeDocCount }} 篇参考文档
                  <el-button size="small" link @click="clearKnowledgeContext" style="margin-left: 4px; font-size: 11px">清除</el-button>
                </span>
                <span class="gt-de-ai-hint">选中文本可改写，光标处可续写</span>
              </div>
              <editor-content :editor="editor" class="gt-de-tiptap-content" />
            </div>

            <!-- AI改写弹窗 -->
            <el-dialog v-model="aiRewriteDialogVisible" title="AI 改写" width="520px" append-to-body>
              <div style="margin-bottom: 12px;">
                <div style="font-size: 12px; color: #999; margin-bottom: 6px;">选中的文本：</div>
                <div style="background: #f9f7fd; padding: 10px; border-radius: 6px; font-size: 13px; line-height: 1.6; max-height: 120px; overflow-y: auto;">{{ aiSelectedText }}</div>
              </div>
              <el-input v-model="aiRewriteInstruction" type="textarea" :rows="2" placeholder="改写指令，如：使其更加专业规范 / 简化表述 / 补充细节" />
              <template #footer>
                <el-button @click="aiRewriteDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="onAiRewriteConfirm" :loading="aiLoading">确认改写</el-button>
              </template>
            </el-dialog>

            <!-- 搜索栏（Ctrl+F） -->
            <TableSearchBar
              :is-visible="deSearch.isVisible.value"
              :keyword="deSearch.keyword.value"
              :match-info="deSearch.matchInfo.value"
              :has-matches="deSearch.matches.value.length > 0"
              :case-sensitive="deSearch.caseSensitive.value"
              :show-replace="false"
              @update:keyword="deSearch.keyword.value = $event"
              @update:case-sensitive="deSearch.caseSensitive.value = $event"
              @search="deSearch.search()"
              @next="deSearch.nextMatch()"
              @prev="deSearch.prevMatch()"
              @close="deSearch.close()"
            />

            <!-- 选中区域状态栏 -->
            <SelectionBar :stats="deCtx.selectionStats()" />

            <div class="gt-de-editor-footer">
              <el-button v-if="!editMode" @click="enterEdit()">编辑</el-button>
              <template v-else>
                <el-button @click="exitEdit(true)">取消</el-button>
                <el-button type="primary" @click="onSave" :loading="saveLoading">保存</el-button>
                <el-button type="warning" @click="onClearAllFormulas">一键清除公式</el-button>
                <el-button @click="onRestoreAutoMode">恢复自动提数</el-button>
              </template>
            </div>
          </template>
          <div v-else class="gt-de-empty-hint">请从左侧目录选择章节</div>
      </div>

      <!-- 右侧：校验面板 -->
      <div class="gt-de-validation">
        <div class="gt-de-sidebar-title">校验结果</div>
        <div v-if="validationFindings.length === 0" class="gt-de-empty-hint">暂无校验结果</div>
        <div v-for="(f, fi) in validationFindings" :key="fi" class="gt-de-finding-item"
          :class="'gt-de-severity-' + f.severity">
          <div class="gt-de-finding-header">
            <el-tag :type="(severityTagType(f.severity)) || undefined" size="small">{{ f.severity }}</el-tag>
            <span class="gt-de-finding-type">{{ f.check_type }}</span>
          </div>
          <div class="gt-de-finding-section">{{ f.note_section }} {{ f.table_name }}</div>
          <div class="gt-de-finding-msg">{{ f.message }}</div>
          <div v-if="f.expected_value || f.actual_value" class="gt-de-finding-values">
            期望: {{ f.expected_value ?? '-' }} | 实际: {{ f.actual_value ?? '-' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 公式管理弹窗（与报表页统一） -->
    <FormulaManagerDialog
      v-model="showNoteFormulaManager"
      :rows="currentNoteFormulaRows"
      :project-id="projectId"
      :year="year"
      @saved="onFormulaApplied"
      @applied="onFormulaApplied"
    />

    <!-- 结构化编辑器弹窗 -->
    <el-dialog v-model="showStructureEditor" title="" width="90%" fullscreen append-to-body :show-close="true">
      <StructureEditor
        v-if="showStructureEditor && currentNote"
        :project-id="projectId"
        module="disclosure_note"
        :module-params="{ note_section: currentNote.note_section, year }"
        :project-name="currentProjectName"
        :template-type="templateType"
        :report-scope="'consolidated'"
        :year="year"
        @saved="onStructureEditorSaved"
      />
    </el-dialog>

    <!-- 附注转换规则弹窗（国企↔上市） -->
    <el-dialog v-model="showNoteMappingDialog" title="附注 国企版 ↔ 上市版 转换规则" width="75%" top="5vh" append-to-body destroy-on-close>
      <p style="font-size: 12px; color: #888; margin-bottom: 10px;">
        配置国企版与上市版附注章节的映射关系。切换模板类型时，系统将按此规则自动转换附注内容。
      </p>
      <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center;">
        <el-button size="small" @click="loadNoteMappingPreset" :loading="noteMappingLoading">一键加载预设</el-button>
        <el-button size="small" type="primary" @click="saveNoteMappingRules" :loading="noteMappingLoading">保存规则</el-button>
        <SharedTemplatePicker
          config-type="report_mapping"
          :project-id="projectId"
          :get-config-data="getNoteMappingData"
          @applied="onNoteMappingApplied"
        />
        <span style="flex: 1;" />
        <span style="font-size: 11px; color: #999;">{{ noteMappingRules.length }} 条规则</span>
      </div>
      <el-table :data="noteMappingRules" size="small" border max-height="55vh"
        :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap' }">
        <el-table-column label="国企版章节" min-width="200">
          <template #default="{ row }">
            <span style="font-size: 12px;">{{ row.soe_section }}</span>
          </template>
        </el-table-column>
        <el-table-column label="→" width="40" align="center">
          <template #default><span style="color: #ccc;">→</span></template>
        </el-table-column>
        <el-table-column label="上市版章节" min-width="200">
          <template #default="{ row }">
            <el-input v-if="row._editing" v-model="row.listed_section" size="small" />
            <span v-else style="font-size: 12px;">{{ row.listed_section || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="60" align="center">
          <template #default="{ row }">
            <span v-if="row.listed_section" style="color: #1e8a38;">✓</span>
            <span v-else style="color: #ccc;">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showNoteImport"
      import-type="disclosure_note"
      :project-id="projectId"
      :year="year"
      @imported="onNoteImported"
    />
  </div>

  <!-- 右键菜单（统一组件 + 查看相关底稿） -->
  <CellContextMenu
    :visible="deCtx.contextMenu.visible"
    :x="deCtx.contextMenu.x"
    :y="deCtx.contextMenu.y"
    :item-name="deCtx.contextMenu.itemName"
    :value="deCtx.selectedCells.value.length === 1 ? deCtx.selectedCells.value[0]?.value : undefined"
    :multi-count="deCtx.selectedCells.value.length"
    @copy="onDeCtxCopy"
    @formula="onDeCtxFormula"
    @sum="onDeCtxSum"
    @compare="onDeCtxCompare"
  >
    <!-- R8-S2-12：查看相关底稿 -->
    <div class="gt-ucell-ctx-item" @click="onDeCtxRelatedWp">
      <span class="gt-ucell-ctx-icon">📝</span> 查看相关底稿
    </div>
  </CellContextMenu>

  <!-- 知识库文档选择弹窗 [R3.7] -->
  <KnowledgePickerDialog v-model:visible="knowledgePickerVisible" />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onUnmounted, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useCellSelection } from '@/composables/useCellSelection'
import { useEditMode } from '@/composables/useEditMode'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { confirmLeave } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { fmtAmount } from '@/utils/formatters'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { ElMessage } from 'element-plus'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import StructureEditor from '@/components/formula/StructureEditor.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import { refreshDisclosureFromWorkpapers, getProjectWizardState, noteAiRewrite, noteAiContinueWrite, noteAiGeneratePolicy, noteAiGenerateAnalysis } from '@/services/commonApi'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import {
  generateDisclosureNotes, getDisclosureNoteTree, getDisclosureNoteDetail,
  updateDisclosureNote, validateDisclosureNotes, getValidationResults,
  type DisclosureNoteTreeItem, type DisclosureNoteDetail, type NoteValidationFinding,
} from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { useProjectStore } from '@/stores/project'
import { useKnowledge, knowledgePickerVisible } from '@/composables/useKnowledge'
import { useAutoSave } from '@/composables/useAutoSave'
import { withLoading } from '@/composables/useLoading'
import KnowledgePickerDialog from '@/components/common/KnowledgePickerDialog.vue'
import { useEditingLock } from '@/composables/useEditingLock'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { handleApiError } from '@/utils/errorHandler'
import { useProjectEvents } from '@/composables/useProjectEvents'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.projectId)
const year = computed(() => {
  const qy = Number(route.query.year)
  return (Number.isFinite(qy) && qy > 2000) ? qy : projectStore.year
})

// ─── 云协同：账套激活/回滚后自动刷新 ─────────────────────────────────────────
const { onDatasetActivated, onDatasetRolledBack } = useProjectEvents(projectId)
onDatasetActivated(() => fetchTree())
onDatasetRolledBack(() => fetchTree())

// R8-S2-03：Stale 状态追踪
import { useStaleStatus } from '@/composables/useStaleStatus'
const stale = useStaleStatus(projectId)
async function onStaleRecalc() {
  await stale.recalc()
  await fetchTree()
}

const editLock = useEditingLock({
  resourceId: computed(() => 'disclosure_' + (route.params.projectId as string || '')),
  resourceType: 'other',  // 附注无后端锁端点，降级为前端检测
  autoAcquire: false,
})

// 编辑锁联动：进入编辑时 acquire，退出时 release；他人持锁时强制退出
watch(() => editMode.value, async (editing) => {
  if (editing) await editLock.acquire()
  else editLock.release()
})
watch(() => editLock.isMine.value, (mine) => {
  if (!mine && editMode.value) exitEdit()
})

// R7-S2-05：后端定时自动保存（2 分钟间隔）
const autoSave = useWorkpaperAutoSave(async () => {
  await onSave()
}, 120_000)

// 单位切换 — 使用 projectStore
const selectedProjectId = ref('')
const projectOptions = computed(() => projectStore.projectOptions)
function onProjectChange(newId: string) {
  router.push({ path: `/projects/${newId}/disclosure-notes`, query: route.query })
}

// 年度切换
const selectedYear = ref(new Date().getFullYear() - 1)
const yearOptions = computed(() => projectStore.yearOptions)
function onYearChange() {
  projectStore.changeYear(selectedYear.value)
  fetchTree().then(() => {
    if (noteList.value.length === 0) onGenerate()
  })
  currentNote.value = null
}

// 转换规则弹窗
const showNoteMappingDialog = ref(false)
const noteMappingLoading = ref(false)
const noteMappingRules = ref<any[]>([])

function loadNoteMappingPreset() {
  // 从当前附注章节列表生成映射规则
  noteMappingRules.value = noteList.value.map(n => ({
    soe_section: `${n.note_section} ${n.section_title}`,
    listed_section: `${n.note_section} ${n.section_title}`,  // 默认同名
    _editing: false,
  }))
}

function saveNoteMappingRules() {
  ElMessage.success('转换规则已保存')
  showNoteMappingDialog.value = false
}

function getNoteMappingData(): Record<string, any> {
  return { note_mapping_rules: noteMappingRules.value }
}

function onNoteMappingApplied(data: Record<string, any>) {
  const rules = data?.note_mapping_rules || []
  if (rules.length) {
    noteMappingRules.value = rules
    ElMessage.success(`已引用 ${rules.length} 条映射规则`)
  }
}

// ── 附注模板保存/引用 ──
function getNoteTemplateConfigData(): Record<string, any> {
  return {
    template_type: templateType.value,
    note_sections: noteList.value.map(n => ({
      note_section: n.note_section,
      section_title: n.section_title,
    })),
  }
}

function onNoteTemplateApplied(data: Record<string, any>) {
  if (data?.template_type) {
    templateType.value = data.template_type
  }
  // 重新加载附注树以应用模板
  fetchTree()
  ElMessage.success('附注模板已应用')
}

// 当前项目名称
const currentProjectName = computed(() => {
  if (projectStore.clientName) return projectStore.clientName
  const p = projectOptions.value.find(o => o.id === projectId.value)
  return p?.name || ''
})

const treeLoading = ref(false)
const detailLoading = ref(false)
const genLoading = ref(false)
const showNoteImport = ref(false)
const validateLoading = ref(false)
const saveLoading = ref(false)
const refreshLoading = ref(false)
const exportLoading = ref(false)
const showNoteFormulaManager = ref(false)
const showStructureEditor = ref(false)

// 底稿保存事件防抖同步
let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null
const syncError = ref(false)
const { isEditing: editMode, isDirty: editDirty, enterEdit, exitEdit, markDirty: markEditDirty, clearDirty: clearEditDirty } = useEditMode()
const templateType = ref('soe')
const justSaved = ref(false)
const customTemplateId = ref('')
const customTemplateName = ref('')
const customTemplateVersion = ref('')

/** 附注模板选项（含自定义模板） */
const deTemplateOptions = computed(() => {
  const opts = [
    { label: '国企版', value: 'soe' },
    { label: '上市版', value: 'listed' },
  ]
  if (customTemplateId.value) {
    opts.push({ label: customTemplateName.value || '自定义', value: 'custom' })
  }
  return opts
})

const noteList = ref<DisclosureNoteTreeItem[]>([])
const currentNote = ref<DisclosureNoteDetail | null>(null)
const textContent = ref('')
const validationFindings = ref<NoteValidationFinding[]>([])
const priorYearNote = ref<any>(null)
// TipTap 编辑器
const editor = useEditor({
  extensions: [
    StarterKit,
    Placeholder.configure({ placeholder: '请输入附注文字内容...' }),
  ],
  content: '',
  onUpdate: ({ editor: e }) => { textContent.value = e.getHTML(); if (editMode.value) { markEditDirty(); autoSave.markDirty() } },
})

onBeforeUnmount(() => { editor.value?.destroy() })

// ── 自动保存/草稿恢复 [R3.8] ──
const autoSaveKey = computed(() => `disclosure_note_${projectId.value}_${currentNote.value?.note_section || 'none'}`)
const { clearDraft: clearAutoSaveDraft } = useAutoSave(
  autoSaveKey.value,
  () => {
    if (!currentNote.value) return null
    return {
      text_content: textContent.value,
      table_data: currentNote.value.table_data,
      note_section: currentNote.value.note_section,
    }
  },
  (data) => {
    if (!currentNote.value || !data) return
    if (data.text_content != null) {
      textContent.value = data.text_content
      editor.value?.commands.setContent(data.text_content)
    }
    if (data.table_data != null) {
      currentNote.value.table_data = data.table_data
    }
  },
  { enabled: editMode },
)

// ── LLM 辅助状态 ──
const aiLoading = ref(false)
const aiRewriteDialogVisible = ref(false)
const aiRewriteInstruction = ref('请改写以下文本，使其更加专业规范')
const aiSelectedText = ref('')

// ── 知识库上下文 [R3.7] ──
const { pickDocuments, buildContext } = useKnowledge()
const knowledgeContextText = ref('')
const knowledgeDocCount = ref(0)

async function onPickKnowledge() {
  const docs = await pickDocuments({ title: '选择参考文档（AI续写/改写时使用）', maxSelect: 5 })
  if (docs.length) {
    knowledgeContextText.value = await buildContext(docs)
    knowledgeDocCount.value = docs.length
    ElMessage.success(`已加载 ${docs.length} 篇参考文档`)
  }
}

function clearKnowledgeContext() {
  knowledgeContextText.value = ''
  knowledgeDocCount.value = 0
}

function getSelectedText(): string {
  if (!editor.value) return ''
  const { from, to } = editor.value.state.selection
  if (from === to) return ''
  return editor.value.state.doc.textBetween(from, to, ' ')
}

function getFullText(): string {
  return editor.value?.getText() || ''
}

async function onAiContinueWrite() {
  const text = getFullText()
  if (!text.trim()) { ElMessage.warning('请先输入一些内容再续写'); return }
  aiLoading.value = true
  try {
    const res = await noteAiContinueWrite(projectId.value, {
      text,
      section_number: currentNote.value?.note_section || '',
      year: year.value,
      knowledge_context: knowledgeContextText.value || undefined,
    })
    if (res.error) { ElMessage.warning(res.error); return }
    if (res.appended) {
      editor.value?.commands.insertContent(res.appended)
      ElMessage.success('续写完成')
    }
  } catch (e: any) {
    ElMessage.error('续写失败: ' + (e.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

function onAiRewriteOpen() {
  const sel = getSelectedText()
  if (!sel.trim()) { ElMessage.warning('请先选中要改写的文本'); return }
  aiSelectedText.value = sel
  aiRewriteInstruction.value = '请改写以下文本，使其更加专业规范'
  aiRewriteDialogVisible.value = true
}

async function onAiRewriteConfirm() {
  if (!aiSelectedText.value.trim()) return
  aiLoading.value = true
  try {
    const res = await noteAiRewrite(projectId.value, {
      text: aiSelectedText.value,
      instruction: aiRewriteInstruction.value,
      section_number: currentNote.value?.note_section || '',
      year: year.value,
      knowledge_context: knowledgeContextText.value || undefined,
    })
    if (res.error) { ElMessage.warning(res.error); return }
    if (res.rewritten && res.rewritten !== res.original) {
      // 替换选中文本
      const { from, to } = editor.value!.state.selection
      editor.value!.chain().focus().deleteRange({ from, to }).insertContent(res.rewritten).run()
      ElMessage.success('改写完成')
    }
  } catch (e: any) {
    ElMessage.error('改写失败: ' + (e.message || '未知错误'))
  } finally {
    aiLoading.value = false
    aiRewriteDialogVisible.value = false
  }
}

async function onAiGeneratePolicy() {
  aiLoading.value = true
  try {
    const res = await noteAiGeneratePolicy(projectId.value, {
      section_number: currentNote.value?.note_section || '',
      template_type: templateType.value || 'soe',
      year: year.value,
    })
    if (res.generated_text) {
      editor.value?.commands.setContent(res.generated_text)
      ElMessage.success(`会计政策已生成（参照${res.reference_count}篇文档）`)
    }
  } catch (e: any) {
    ElMessage.error('生成失败: ' + (e.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

async function onAiGenerateAnalysis() {
  aiLoading.value = true
  try {
    const res = await noteAiGenerateAnalysis(projectId.value, {
      section_number: currentNote.value?.note_section || '',
      year: year.value,
    })
    if (res.generated_text) {
      editor.value?.commands.insertContent('\n\n' + res.generated_text)
      ElMessage.success('变动分析已生成')
    }
  } catch (e: any) {
    ElMessage.error('生成失败: ' + (e.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}
interface TreeNode { id: string; label: string; data?: any; children?: TreeNode[]; isGroup?: boolean }

const treeSearch = ref('')
const noteTreeRef = ref<any>(null)
const treeViewMode = ref<'tree' | 'flat'>('tree')

// 单位切换（侧边栏）
const selectedProjectIdLocal = ref('')

function onSwitchProjectLocal(newId: string) {
  if (newId && newId !== projectId.value) {
    router.push(`/projects/${newId}/disclosure-notes`)
  }
}

function expandAll() {
  const tree = noteTreeRef.value
  if (!tree) return
  const nodes = tree.store?.nodesMap
  if (nodes) {
    Object.values(nodes).forEach((node: any) => { node.expanded = true })
  }
}

function collapseAll() {
  const tree = noteTreeRef.value
  if (!tree) return
  const nodes = tree.store?.nodesMap
  if (nodes) {
    Object.values(nodes).forEach((node: any) => { node.expanded = false })
  }
}

// 平铺视图数据
const flatNoteList = computed(() => {
  const kw = treeSearch.value.toLowerCase()
  let list = noteList.value
  if (kw) {
    list = list.filter(n => (n.section_title || '').toLowerCase().includes(kw) || (n.note_section || '').toLowerCase().includes(kw))
  }
  return list
})

function onFlatItemClick(note: any) {
  currentNote.value = note
}

// 按大类分组的树形结构
const CHAPTER_GROUPS = [
  { prefix: '一' },
  { prefix: '二' },
  { prefix: '三' },
  { prefix: '四' },
  { prefix: '五' },
  { prefix: '六' },
  { prefix: '七' },
  { prefix: '八' },
  { prefix: '九' },
  { prefix: '十' },
  { prefix: '十一' },
  { prefix: '十二' },
  { prefix: '十三' },
  { prefix: '十四' },
  { prefix: '十五' },
  { prefix: '十六' },
  { prefix: '十七' },
]

// 国企版14章标题
const SOE_LABELS: Record<string, string> = {
  '一': '公司基本情况', '二': '财务报表编制基础', '三': '遵循企业会计准则的声明',
  '四': '重要会计政策、会计估计', '五': '会计政策变更及差错更正', '六': '税项',
  '七': '企业合并及合并财务报表', '八': '财务报表主要项目注释',
  '九': '或有事项', '十': '资产负债表日后事项', '十一': '关联方关系及其交易',
  '十二': '母公司财务报表附注', '十三': '其他披露内容', '十四': '财务报表之批准',
}
// 上市版17章标题
const LISTED_LABELS: Record<string, string> = {
  '一': '公司基本情况', '二': '财务报表的编制基础', '三': '重要会计政策及会计估计',
  '四': '税项', '五': '合并财务报表项目附注', '六': '研发支出',
  '七': '在其他主体中的权益', '八': '政府补助', '九': '金融工具风险管理',
  '十': '公允价值', '十一': '关联方及关联交易', '十二': '股份支付',
  '十三': '承诺及或有事项', '十四': '资产负债表日后事项', '十五': '其他重要事项',
  '十六': '公司财务报表主要项目注释', '十七': '补充资料',
}

// 五章内按资产/负债/权益/损益/其他分组
const SECTION_GROUPS: Record<string, { label: string; range: [number, number] }> = {
  'asset': { label: '流动资产 + 非流动资产', range: [1, 15] },
  'liability': { label: '流动负债 + 非流动负债', range: [16, 23] },
  'equity': { label: '所有者权益', range: [24, 28] },
  'income': { label: '损益类', range: [29, 35] },
  'other': { label: '其他科目注释', range: [36, 79] },
  'disclosure': { label: '补充披露事项', range: [80, 199] },
}

const treeData = computed<TreeNode[]>(() => {
  const notes = noteList.value
  if (!notes.length) return []

  const result: TreeNode[] = []

  // 会计政策分组关键词
  const POLICY_GROUPS: Record<string, { label: string; keywords: string[] }> = {
    'basic': { label: '基础政策', keywords: ['会计期间', '记账本位币', '记账基础', '现金及现金等价物', '公允价值', '营业周期', '遵循'] },
    'consolidation': { label: '合并与合营', keywords: ['企业合并', '合并财务报表', '合营安排', '同一控制', '非同一控制', '控制的判断', '子公司'] },
    'financial': { label: '金融工具与外币', keywords: ['金融工具', '套期', '外币', '应付债券', '优先股', '永续债', '资产证券化'] },
    'asset': { label: '资产类政策', keywords: ['存货', '长期股权', '投资性房地产', '固定资产', '在建工程', '生物资产', '油气资产', '使用权资产', '无形资产', '研究开发', '长期待摊', '资产减值', '借款费用', '商誉'] },
    'liability_income': { label: '负债与收入', keywords: ['职工薪酬', '股份支付', '预计负债', '收入', '合同成本', '合同履约', '政府补助', '递延所得税', '安全生产', '应付债券'] },
    'lease_other': { label: '租赁与其他', keywords: ['租赁', '持有待售', '终止经营'] },
  }

  // 企业合并分组关键词
  const MERGE_GROUPS: Record<string, { label: string; keywords: string[] }> = {
    'scope': { label: '合并范围', keywords: ['纳入合并', '不再纳入', '新纳入', '子公司基本'] },
    'control': { label: '控制与表决权', keywords: ['表决权不足', '直接或通过', '非全资', '所有者权益份额'] },
    'transaction': { label: '合并交易', keywords: ['同一控制下企业合并', '非同一控制下企业合并', '吸收合并'] },
    'restriction': { label: '限制与结构化主体', keywords: ['重大限制', '结构化主体', '转移资金'] },
  }

  // 关联方分组关键词
  const RELATED_GROUPS: Record<string, { label: string; keywords: string[] }> = {
    'party': { label: '关联方情况', keywords: ['母公司', '子公司情况', '合营企业', '联营企业', '其他关联方'] },
    'transaction': { label: '关联交易', keywords: ['关联交易', '应收应付'] },
  }

  // 通用分组函数
  function buildGroupedChildren(items: typeof notes, groups: Record<string, { label: string; keywords: string[] }>, idPrefix: string): TreeNode[] {
    const children: TreeNode[] = []
    const used = new Set<string>()
    for (const [gk, gv] of Object.entries(groups)) {
      const matched = items.filter(n => gv.keywords.some(kw => (n.section_title || '').includes(kw)))
      if (matched.length) {
        matched.forEach(n => used.add(n.id))
        children.push({ id: `${idPrefix}_${gk}`, label: gv.label, isGroup: true,
          children: matched.map(n => ({ id: n.id, label: n.section_title, data: n })) })
      }
    }
    const ungrouped = items.filter(n => !used.has(n.id))
    if (ungrouped.length) {
      children.push({ id: `${idPrefix}_other`, label: '其他', isGroup: true,
        children: ungrouped.map(n => ({ id: n.id, label: n.section_title, data: n })) })
    }
    return children
  }

  for (const ch of CHAPTER_GROUPS) {
    const prefix = ch.prefix + '、'
    const items = notes.filter(n => n.note_section.startsWith(prefix))
    if (!items.length) continue  // 空章节不显示

    // 动态获取章节标题（根据模板类型）
    const labels = templateType.value === 'listed' ? LISTED_LABELS : SOE_LABELS
    const chLabel = `${ch.prefix}、${labels[ch.prefix] || items[0]?.section_title || ''}`

    // 会计政策（国企四/上市三）：>10个子章节时分组
    if ((ch.prefix === '三' || ch.prefix === '四') && items.length > 10) {
      result.push({ id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
        children: buildGroupedChildren(items, POLICY_GROUPS, `ch_${ch.prefix}`) })

    // 报表注释（国企八/上市五）：按资产/负债/权益/损益分组
    } else if ((ch.prefix === '五' || ch.prefix === '八') && items.length > 10) {
      const subChildren: TreeNode[] = []
      for (const [gKey, gInfo] of Object.entries(SECTION_GROUPS)) {
        const matched = items.filter(n => {
          const num = parseInt(n.note_section.replace(prefix, ''))
          return num >= gInfo.range[0] && num <= gInfo.range[1]
        })
        if (matched.length) {
          subChildren.push({ id: `group_${ch.prefix}_${gKey}`, label: gInfo.label, isGroup: true,
            children: matched.map(n => ({ id: n.id, label: n.section_title, data: n })) })
        }
      }
      result.push({ id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true, children: subChildren })

    // 企业合并（国企七）：>5个子章节时分组
    } else if (ch.prefix === '七' && items.length > 5) {
      result.push({ id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
        children: buildGroupedChildren(items, MERGE_GROUPS, 'ch7') })

    // 关联方（国企十一/上市十一）：>3个子章节时分组
    } else if (ch.prefix === '十一' && items.length > 3) {
      result.push({ id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
        children: buildGroupedChildren(items, RELATED_GROUPS, 'ch11') })

    // 其他章节：直接平铺
    } else {
      result.push({
        id: `chapter_${ch.prefix}`,
        label: items.length > 3 ? `${chLabel}（${items.length}）` : chLabel,
        isGroup: true,
        children: items.map(n => ({ id: n.id, label: n.section_title, data: n })),
      })
    }
  }

  return result
})

const filteredTreeData = computed(() => {
  const kw = treeSearch.value.toLowerCase()
  if (!kw) return treeData.value
  // 搜索时展平到叶子节点过滤
  return treeData.value.map(group => {
    if (!group.children?.length) return group
    const filtered = group.children.map(child => {
      if (child.children) {
        // 二级分组
        const subFiltered = child.children.filter(n =>
          (n.label || '').toLowerCase().includes(kw) || (n.data?.account_name || '').toLowerCase().includes(kw)
        )
        return subFiltered.length ? { ...child, children: subFiltered } : null
      }
      // 叶子节点
      return (child.label || '').toLowerCase().includes(kw) || (child.data?.account_name || '').toLowerCase().includes(kw) ? child : null
    }).filter(Boolean) as TreeNode[]
    return filtered.length ? { ...group, children: filtered } : null
  }).filter(Boolean) as TreeNode[]
})

const _templateTypeLabel = computed(() => {
  if (templateType.value === 'custom') {
    return customTemplateVersion.value && customTemplateName.value
      ? `自定义：${customTemplateName.value}（${customTemplateVersion.value}）`
      : customTemplateName.value || '自定义模板'
  }
  return templateType.value === 'listed' ? '上市版' : '国企版'
})

// 多表格支持
const activeTableTab = ref('0')

const currentNoteTables = computed(() => {
  if (!currentNote.value?.table_data) return []
  const td = currentNote.value.table_data
  // 新格式：_tables 数组
  if (td._tables && Array.isArray(td._tables) && td._tables.length > 0) {
    return td._tables
  }
  // 旧格式：单表格
  if (td.headers && td.rows) {
    return [{ name: currentNote.value.section_title, headers: td.headers, rows: td.rows }]
  }
  return []
})

const activeTableData = computed(() => {
  const idx = parseInt(activeTableTab.value) || 0
  return currentNoteTables.value[idx] || currentNoteTables.value[0] || null
})

// 切换章节时重置表格Tab
watch(() => currentNote.value?.note_section, () => {
  activeTableTab.value = '0'
})

// 表格Tab标签：避免显示无意义的"项 目"等表头值
const _GENERIC_NAMES = new Set(['项  目', '项 目', '项目', '类  别', '类别', ''])
function getTableTabLabel(tbl: any, idx: number): string {
  const name = (tbl.name || '').trim()
  if (!name || _GENERIC_NAMES.has(name)) {
    // 用 headers 中第二列（通常是"期末余额"/"本期金额"等）区分
    const headers = tbl.headers || []
    if (headers.length > 1) {
      const h1 = String(headers[1] || '').trim()
      if (h1 && h1.length <= 8) return `表${idx + 1}·${h1}`
    }
    return `表${idx + 1}`
  }
  // 有意义的名称但太长则截断
  return name.length > 12 ? name.slice(0, 12) + '…' : name
}

function getCellValue(row: any, colIdx: number): any {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.value ?? cell.manual_value ?? 0
  return cell
}

function getCellMode(row: any, colIdx: number): string {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.mode || 'auto'
  return ''
}

function _getPriorYearValue(_row: any, rowIndex: number): any {
  if (!priorYearNote.value?.table_data?.rows) return null
  const priorRow = priorYearNote.value.table_data.rows[rowIndex]
  if (!priorRow) return null
  const values = priorRow.values || priorRow.cells || []
  return values[0] ?? null
}

function onCellValueChange(rowIndex: number, colIndex: number, _newValue: number | undefined) {
  markEditDirty()
  autoSave.markDirty()
  if (!currentNote.value?.table_data?.rows) return
  const rows = currentNote.value.table_data.rows
  const totalRowIndex = rows.findIndex((r: any) => r.is_total)
  if (totalRowIndex < 0) return
  // 纵向合计：所有非合计行的同列求和
  let sum = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    sum += parseFloat(vals[colIndex]) || 0
  }
  if (!rows[totalRowIndex].values) rows[totalRowIndex].values = []
  rows[totalRowIndex].values[colIndex] = sum
  // 横向公式
  recalcHorizontalFormula(rowIndex)
}

function recalcHorizontalFormula(rowIndex: number) {
  const row = currentNote.value?.table_data?.rows?.[rowIndex]
  if (!row || !row.formula_type) return
  if (row.formula_type === 'opening_plus_changes') {
    const vals = row.values || []
    if (vals.length >= 3) {
      const opening = parseFloat(vals[0]) || 0
      let changes = 0
      for (let i = 1; i < vals.length - 1; i++) changes += parseFloat(vals[i]) || 0
      vals[vals.length - 1] = opening + changes
    }
  }
}

function isFormulaMismatch(row: any, colIdx: number): boolean {
  if (!row.is_total || !currentNote.value?.table_data?.rows) return false
  const rows = currentNote.value.table_data.rows
  let expected = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    expected += parseFloat(vals[colIdx]) || 0
  }
  const actual = parseFloat((row.values || [])[colIdx]) || 0
  return Math.abs(expected - actual) > 0.01
}

async function onRefreshFromWP() {
  refreshLoading.value = true
  try {
    await refreshDisclosureFromWorkpapers(projectId.value, year.value)
    ElMessage.success('已从底稿刷新数据')
    if (currentNote.value) await fetchDetail(currentNote.value.note_section)
  } catch (e) { handleApiError(e, '刷新附注') }
  finally { refreshLoading.value = false }
}

// ── 底稿保存事件监听（自动同步附注数据） ──────────────────────────────────────
function onWorkpaperSaved(payload: WorkpaperSavedPayload) {
  if (payload.projectId !== projectId.value) return
  if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
  syncDebounceTimer = setTimeout(async () => {
    syncError.value = false
    try {
      await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
    } catch {
      syncError.value = true
    }
  }, 1000)
}

async function onManualRefresh() {
  syncError.value = false
  try {
    await refreshDisclosureFromWorkpapers(projectId.value, year.value)
    if (currentNote.value) await fetchDetail(currentNote.value.note_section)
    ElMessage.success('手动刷新成功')
  } catch (e) {
    syncError.value = true
    handleApiError(e, '刷新附注')
  }
}

async function onFormulaApplied() {
  // 公式应用后刷新当前附注数据
  if (currentNote.value) await fetchDetail(currentNote.value.note_section)
}

// 将当前附注表格数据转为公式管理器需要的行格式
const currentNoteFormulaRows = computed(() => {
  if (!currentNote.value?.table_data?.rows) return []
  return currentNote.value.table_data.rows.map((r: any, i: number) => ({
    id: `note_row_${i}`,
    row_code: `${currentNote.value!.note_section}-R${i + 1}`,
    row_name: r.label || `第${i + 1}行`,
    formula: '',
    formula_category: r.is_total ? 'auto_calc' : '',
    formula_description: r.is_total ? '合计行' : '',
    indent_level: 0,
    is_total_row: r.is_total || false,
  }))
})

function openStructureEditor() {
  if (!currentNote.value) {
    ElMessage.warning('请先选择一个附注章节')
    return
  }
  showStructureEditor.value = true
}

async function onStructureEditorSaved() {
  // 结构化编辑器保存后刷新当前附注数据
  showStructureEditor.value = false
  if (currentNote.value) await fetchDetail(currentNote.value.note_section)
  ElMessage.success('表样编辑已同步')
}

async function onClearAllFormulas() {
  // 一键清除公式：将所有 auto 单元格切换为 manual 模式
  if (!currentNote.value?.table_data?.rows) return
  try {
    const { default: http } = await import('@/utils/http')
    await http.post(
      `/api/disclosure-notes/${projectId.value}/${year.value}/${currentNote.value.note_section}/clear-formulas`
    )
    ElMessage.success('公式已清除，所有单元格切换为手动编辑模式')
    await fetchDetail(currentNote.value.note_section)
  } catch {
    // 降级：前端直接修改模式标记
    for (const row of currentNote.value.table_data.rows) {
      if (row._cell_modes) {
        for (const key of Object.keys(row._cell_modes)) {
          if (row._cell_modes[key] === 'auto') {
            row._cell_modes[key] = 'manual'
          }
        }
      }
    }
    ElMessage.success('公式已清除（本地模式）')
  }
}

async function onRestoreAutoMode() {
  // 恢复自动提数：从底稿重新提取数据并恢复 auto 模式
  if (!currentNote.value) return
  try {
    await refreshDisclosureFromWorkpapers(projectId.value, year.value)
    ElMessage.success('已恢复自动提数模式')
    await fetchDetail(currentNote.value.note_section)
  } catch {
    ElMessage.error('恢复失败')
  }
}

async function onExportWord() {
  exportLoading.value = true
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.post(
      `/api/disclosure-notes/${projectId.value}/${year.value}/export-word`,
      {},
      { responseType: 'blob' }
    )
    // 下载 blob
    const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `附注_${year.value}.docx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('附注 Word 导出成功')
  } catch (e: any) {
    handleApiError(e, '导出附注 Word')
  } finally { exportLoading.value = false }
}

function severityTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { error: 'danger', warning: 'warning', info: 'info' }
  return m[s] || 'info'
}

const fetchTree = withLoading(treeLoading, async () => {
  try { noteList.value = await getDisclosureNoteTree(projectId.value, year.value) }
  catch { noteList.value = [] }
})

async function loadProjectTemplateConfig() {
  try {
    const state = await getProjectWizardState(projectId.value)
    const basicInfo = state?.steps?.basic_info?.data || state?.basic_info?.data || {}
    customTemplateId.value = basicInfo.custom_template_id || ''
    customTemplateName.value = basicInfo.custom_template_name || ''
    customTemplateVersion.value = basicInfo.custom_template_version || ''
    templateType.value = basicInfo.template_type || 'soe'
    if (templateType.value === 'custom' && !customTemplateId.value) {
      templateType.value = 'soe'
    }
  } catch {
    templateType.value = 'soe'
    customTemplateId.value = ''
    customTemplateName.value = ''
    customTemplateVersion.value = ''
  }
}

async function onNodeClick(node: TreeNode) {
  // 分组节点不加载详情
  if (node.isGroup || !node.data?.note_section) return
  await withLoading(detailLoading, async () => {
    editMode.value = false
    editDirty.value = false
    try {
      await fetchDetail(node.data.note_section)
    } catch { currentNote.value = null }
  })()
}

async function fetchDetail(noteSection: string) {
  currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
  textContent.value = currentNote.value.text_content || ''
  if (editor.value) {
    // 将纯文本段落转为HTML段落供TipTap渲染
    const raw = textContent.value
    if (raw && !raw.startsWith('<')) {
      const html = raw.split(/\n\n+/).filter(Boolean).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
      editor.value.commands.setContent(html)
    } else {
      editor.value.commands.setContent(raw)
    }
  }
  // 并行加载上年数据
  try {
    priorYearNote.value = await api.get(
      `/api/disclosure-notes/${projectId.value}/${year.value}/${noteSection}/prior-year`
    )
  } catch { priorYearNote.value = null }
}

function onNoteImported() {
  showNoteImport.value = false
  fetchTree()
}

async function onGenerate() {
  if (templateType.value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    return
  }
  const { showGuide } = await import('@/composables/useWorkflowGuide')
  const tplLabel = templateType.value === 'listed' ? '上市版' : '国企版'
  const ok = await showGuide(
    'note_generate',
    '📝 生成附注',
    `<div style="line-height:1.8;font-size:13px">
      <p>将根据 <b>${tplLabel}</b> 模板生成全部附注章节。</p>
      <p style="color:#909399;font-size:12px;margin-top:6px">请确认以下准备工作已完成：</p>
      <ul style="padding-left:18px;margin:4px 0">
        <li><span style="color:#e6a23c">⚠</span> 已选择正确的模板类型（当前：${tplLabel}）</li>
        <li><span style="color:#e6a23c">⚠</span> 建议先完成报表生成，附注表格将自动从试算表取数</li>
        <li><span style="color:#e6a23c">⚠</span> 如有上年附注，建议先上传到知识库供 AI 参照</li>
      </ul>
      <p style="color:#67c23a;font-size:12px;margin-top:6px">✓ 将生成 170+ 个附注章节（含表格和正文），已有数据将被重新生成</p>
      <p style="color:#909399;font-size:12px">💡 生成后可使用 AI 续写/改写功能辅助编写会计政策等文字内容</p>
    </div>`,
    '开始生成',
  )
  if (!ok) return
  await withLoading(genLoading, async () => {
    try {
      await generateDisclosureNotes(projectId.value, year.value, templateType.value)
      ElMessage.success('附注生成完成')
      await fetchTree()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.response?.data?.message || e?.message || ''
      if (msg) ElMessage.warning('附注生成：' + msg)
    }
  })()
}

async function handleTemplateChange(value: string) {
  if (value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    templateType.value = 'soe'
    return
  }
  await onGenerate()
}

const onValidate = withLoading(validateLoading, async () => {
  await validateDisclosureNotes(projectId.value, year.value)
  validationFindings.value = await getValidationResults(projectId.value, year.value)
  ElMessage.success(`校验完成，发现 ${validationFindings.value.length} 项`)
})

async function onSave() {
  if (!currentNote.value) return
  await withLoading(saveLoading, async () => {
    const body: Record<string, any> = {}
    if (currentNote.value!.content_type === 'text' || currentNote.value!.content_type === 'mixed') {
      body.text_content = textContent.value
    }
    if (currentNote.value!.content_type === 'table' || currentNote.value!.content_type === 'mixed') {
      body.table_data = currentNote.value!.table_data
    }
    await updateDisclosureNote(currentNote.value!.id, body)
    ElMessage.success('保存成功')
    editMode.value = false
    clearEditDirty()
    autoSave.clearDirty()
    clearAutoSaveDraft()
    currentNote.value!.status = 'confirmed'
    justSaved.value = true
    setTimeout(() => { justSaved.value = false }, 2500)
  })()
}

/** 快捷键保存：保存当前附注 */
function onShortcutSave() {
  if (currentNote.value && editMode.value) {
    onSave()
  }
}

onMounted(async () => {
  selectedProjectId.value = projectId.value
  selectedProjectIdLocal.value = projectId.value
  selectedYear.value = year.value
  projectStore.loadProjectOptions()
  eventBus.on('shortcut:save', onShortcutSave)
  eventBus.on('workpaper:saved', onWorkpaperSaved)
  await loadProjectTemplateConfig()
  await fetchTree()
  // 如果没有附注数据，自动从模板生成
  if (noteList.value.length === 0) {
    await onGenerate()
  }
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  eventBus.off('shortcut:save', onShortcutSave)
  eventBus.off('workpaper:saved', onWorkpaperSaved)
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
})

// R8-S2-14：未保存拦截
onBeforeRouteLeave(async (_to, _from, next) => {
  if (!editDirty.value && !autoSave.isDirty.value) { next(); return }
  try {
    await confirmLeave('附注')
    next()
  } catch {
    next(false)
  }
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (editDirty.value || autoSave.isDirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

// ─── 全屏与复制 ──────────────────────────────────────────────────────────────
const { isFullscreen: deFullscreen, toggleFullscreen: toggleDeFullscreen } = useFullscreen()

function copyNoteTable() {
  const note = currentNote.value
  if (!note?.table_data?.rows?.length) { ElMessage.warning('当前章节无表格数据'); return }
  const headers = note.table_data.headers || []
  const rows = note.table_data.rows || []
  const text = [headers.join('\t'), ...rows.map((r: any) => (r.values || []).join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map((h: string) => `<th>${h}</th>`).join('')}</tr>${rows.map((r: any) => `<tr>${(r.values || []).map((v: any) => `<td>${v ?? ''}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${rows.length} 行，可粘贴到 Word/Excel`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制') }
}

// ─── 单元格选中与右键菜单（统一 composable） ─────────────────────────────────
const deCtx = useCellSelection()
const deTableRef = ref<any>(null)
deCtx.setupTableDrag(deTableRef, (rowIdx: number, colIdx: number) => {
  const tableRows = activeTableData.value?.rows || []
  const row = tableRows[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.label || row[0]
  const values = row.values || row.cells || []
  return values[colIdx - 1] ?? null
})
const deComments = useCellComments(() => projectId.value, () => year.value, 'disclosure')

const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const deSearch = useTableSearch(
  computed(() => (activeTableData.value?.rows || []) as any[]),
  ['label']
)

function deCellClassName({ rowIndex, columnIndex }: any) {
  const classes: string[] = []
  const selClass = deCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  const sec = activeTableData.value
  const sheetKey = sec?.section_id || currentNote.value?.note_section || 'default'
  const ccClass = deComments.commentCellClass(sheetKey, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onDeCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  deCtx.closeContextMenu()
  const tableRows = activeTableData.value?.rows || []
  const rowIdx = tableRows.indexOf(row)
  const headers = activeTableData.value?.headers || []
  const colIdx = headers.indexOf(column.label)
  if (rowIdx < 0 || colIdx < 0) return
  const values = row.values || row.cells || []
  const value = values[colIdx] ?? ''
  deCtx.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
  deCtx.contextMenu.itemName = values[0] || `行${rowIdx + 1}`
}

function onDeCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const tableRows = activeTableData.value?.rows || []
  const rowIdx = tableRows.indexOf(row)
  const headers = activeTableData.value?.headers || []
  const colIdx = headers.indexOf(column.label)
  // 如果右键点击的单元格已在选区内，保持选区不变
  if (rowIdx >= 0 && colIdx >= 0 && !deCtx.isCellSelected(rowIdx, colIdx)) {
    const values = row.values || row.cells || []
    const value = values[colIdx] ?? ''
    deCtx.selectCell(rowIdx, colIdx, value, false)
    deCtx.contextMenu.itemName = values[0] || `行${rowIdx + 1}`
  }
  deCtx.openContextMenu(event, deCtx.contextMenu.itemName)
}

function onDeCtxCopy() {
  deCtx.closeContextMenu()
  deCtx.copySelectedValues()
  ElMessage.success('已复制')
}

function onDeCtxFormula() {
  deCtx.closeContextMenu()
  showNoteFormulaManager.value = true
}

function onDeCtxSum() {
  deCtx.closeContextMenu()
  const sum = deCtx.sumSelectedValues()
  ElMessage.info(`选中 ${deCtx.selectedCells.value.length} 格，合计：${fmtAmount(sum)}`)
}

function onDeCtxCompare() {
  deCtx.closeContextMenu()
  if (deCtx.selectedCells.value.length < 2) return
  const vals = deCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  ElMessage.info(`差异：${fmtAmount(diff)}`)
}

/**
 * R8-S2-12：查看附注行关联的底稿
 * 单底稿直接跳转，多底稿弹列表让用户选择
 */
async function onDeCtxRelatedWp() {
  deCtx.closeContextMenu()
  const note = currentNote.value
  if (!note?.note_section) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  // 用当前选中单元格所在行作为 row_code（简化：用行 index 或项目名）
  const sel = deCtx.selectedCells.value[0]
  if (!sel) return
  const rowCode = `row_${sel.row}`
  try {
    const data: any = await api.get(
      `/api/notes/${projectId.value}/${year.value}/${encodeURIComponent(note.note_section)}/row/${encodeURIComponent(rowCode)}/related-workpapers`,
      { validateStatus: (s: number) => s < 600 },
    )
    const wps = data?.workpapers || []
    if (!wps.length) {
      ElMessage.info('该附注行暂无关联底稿')
      return
    }
    if (wps.length === 1) {
      // 单底稿直接跳转
      const wp = wps[0]
      router.push({
        name: 'WorkpaperEditor',
        params: { projectId: projectId.value, wpId: wp.id },
      })
      return
    }
    // 多底稿：提示用户选择（简化弹 list）
    const list = wps.map((w: any) => `${w.wp_code} ${w.wp_name}`).join('\n')
    ElMessage.info(`该行关联 ${wps.length} 张底稿：\n${list}`)
  } catch (e: any) {
    handleApiError(e, '查看相关底稿')
  }
}
</script>

<style scoped>
.gt-disclosure-editor { padding: 16px; }

/* ── GtPageHeader 已替换横幅样式 ── */

/* ── 三栏布局 ── */
.gt-de-body {
  display: flex; gap: 12px; height: calc(100vh - 180px);
}
.gt-de-sidebar {
  width: 220px; flex-shrink: 0;
  background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex; flex-direction: column; overflow: hidden;
}
.gt-de-sidebar-title {
  padding: 10px 14px 6px; font-size: 12px; font-weight: 600; color: #666;
  text-transform: uppercase; letter-spacing: 1px;
}

/* 单位切换栏 */
.gt-de-unit-bar {
  padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
}
.gt-de-unit-name {
  font-size: 13px; font-weight: 600; color: var(--gt-color-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block;
}

/* 视图切换 */
.gt-de-view-toggle {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px;
}
.gt-de-view-toggle .el-radio-group { flex-shrink: 0; }
.gt-de-view-toggle .el-button { font-size: 11px; padding: 0 4px; }

/* 平铺视图 */
.gt-de-flat-list { flex: 1; overflow-y: auto; padding: 0 4px 8px; }
.gt-de-flat-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; font-size: 12px; cursor: pointer;
  border-radius: 4px; color: var(--gt-color-text);
  transition: background 0.15s;
}
.gt-de-flat-item:hover { background: #f5f0ff; }
.gt-de-flat-item--active { background: #ece6f5; font-weight: 600; color: var(--gt-color-primary); }
.gt-de-flat-item-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-de-tree-search { margin: 0 10px 8px; width: calc(100% - 20px); }
.gt-de-tree-wrap { flex: 1; overflow-y: auto; padding: 0 4px 8px; }
.gt-de-tree-wrap :deep(.el-tree) { background: transparent; --el-tree-node-hover-bg-color: #f5f0ff; }
.gt-de-tree-wrap :deep(.el-tree-node__content) { height: 32px; border-radius: 4px; }
.gt-de-tree-wrap :deep(.el-tree-node.is-current > .el-tree-node__content) { background: #ece6f5; }
.gt-de-tree-node {
  display: flex; align-items: center; gap: 6px; width: 100%; font-size: 12px; padding: 0 4px;
}
.gt-de-tree-num {
  font-size: 10px; color: #4b2d77; background: #f0ecf5; padding: 1px 5px;
  border-radius: 3px; font-weight: 600; min-width: 36px; text-align: center; white-space: nowrap;
}
.gt-de-tree-label { color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-de-tree-node-active .gt-de-tree-num { background: #4b2d77; color: #fff; }
.gt-de-tree-node-active .gt-de-tree-label { color: #4b2d77; font-weight: 600; }
.gt-de-tree-group {
  font-size: 12px; font-weight: 600; color: #555; padding: 2px 0;
}
.gt-de-tree-group-label { white-space: nowrap; }
.gt-de-tree-wrap :deep(.el-tree-node__children) { padding-left: 2px; }

/* ── 中间编辑区 ── */
.gt-de-main {
  flex: 1; min-width: 0;
  background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 16px; overflow-y: auto;
}
.gt-de-editor-header {
  display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;
  padding-bottom: 10px; border-bottom: 1px solid #f0ecf5;
}
.gt-de-section-title { margin: 0; font-size: 15px; font-weight: 600; color: #333; }
.gt-de-section-account { font-size: 11px; color: #999; margin-top: 2px; display: block; }
.gt-de-editor-footer { margin-top: 12px; text-align: right; padding-top: 10px; border-top: 1px solid #f0ecf5; }

/* ── 右侧校验 ── */
.gt-de-validation {
  width: 240px; flex-shrink: 0;
  background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow-y: auto; padding-bottom: 8px;
}
.gt-de-empty-hint { color: #bbb; font-size: 12px; text-align: center; padding: 30px 10px; }
.gt-de-finding-item { padding: 8px 12px; border-bottom: 1px solid #f5f3f8; font-size: 12px; }
.gt-de-finding-item.gt-de-severity-error { border-left: 3px solid #FF5149; }
.gt-de-finding-item.gt-de-severity-warning { border-left: 3px solid #e6a23c; }
.gt-de-finding-item.gt-de-severity-info { border-left: 3px solid #bbb; }
.gt-de-finding-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.gt-de-finding-type { font-size: 10px; color: #999; }
.gt-de-finding-section { font-size: 10px; color: #bbb; }
.gt-de-finding-msg { font-size: 12px; color: #555; margin-top: 2px; }
.gt-de-finding-values { font-size: 10px; color: #999; margin-top: 2px; }

/* ── 表格 ── */
.gt-de-main :deep(.el-table) { --el-table-border-color: #e8e4f0; }
.gt-de-main :deep(.el-table th.el-table__cell) {
  background: #f8f6fb !important; font-size: 12px; font-weight: 600; color: #555; white-space: nowrap;
}
.gt-de-main :deep(.el-table td.el-table__cell) { font-size: 12px; padding: 6px 0; }
.total-label { font-weight: 700; }
.total-val { font-weight: 700; }
.gt-cell-wrapper { display: flex; align-items: center; gap: 4px; }
.gt-cell-source { font-size: 10px; cursor: help; }
.gt-cell-manual { font-size: 10px; cursor: help; }
.gt-prior-year-val { color: #bbb; font-style: italic; font-size: 12px; }
.gt-formula-mismatch { color: #FF5149 !important; font-weight: 700; text-decoration: underline wavy #FF5149; }

/* ── TipTap ── */
.gt-de-tiptap-wrapper { border: 1px solid #e8e4f0; border-radius: 6px; margin-top: 10px; }
.gt-de-tiptap-toolbar { padding: 4px 8px; border-bottom: 1px solid #e8e4f0; background: #faf8fd; border-radius: 6px 6px 0 0; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.gt-de-toolbar-divider { width: 1px; height: 20px; background: #d8d0e8; margin: 0 6px; }
.gt-de-ai-hint { font-size: 11px; color: #b0a4c8; margin-left: 8px; white-space: nowrap; }
.gt-de-saved-badge { font-size: 11px; color: #67c23a; font-weight: 400; margin-left: 8px; background: #f0f9eb; padding: 1px 8px; border-radius: 10px; }
.gt-de-tiptap-content { padding: 12px; min-height: 200px; font-size: 13px; line-height: 1.8; }
.gt-de-tiptap-content :deep(.ProseMirror) { outline: none; min-height: 180px; }
.gt-de-tiptap-content :deep(.ProseMirror p) { margin-bottom: 10px; text-indent: 2em; }
.gt-de-tiptap-content :deep(.ProseMirror p.is-editor-empty:first-child::before) { color: #adb5bd; content: attr(data-placeholder); float: left; height: 0; pointer-events: none; text-indent: 0; }


</style>


