<template>
  <el-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)"
    title="合并附注明细映射" width="92%" top="3vh" append-to-body destroy-on-close>

    <!-- 顶部信息 -->
    <div style="display:flex;gap:16px;align-items:center;margin-bottom:12px">
      <span style="font-size:14px;font-weight:600">{{ sectionTitle }}</span>
      <el-tag v-if="preview" size="small" type="info">{{ preview.entity_count }} 家企业 · {{ preview.group_count }} 组结构</el-tag>
      <el-tag v-if="preview?.stale_count" size="small" type="warning">{{ preview.stale_count }} 家来源已变化</el-tag>
      <span style="flex:1" />
      <el-button size="small" @click="handleEditTemplate">📝 编辑模板</el-button>
      <el-button size="small" @click="loadPreview" :loading="loading">🔄 刷新预览</el-button>
    </div>

    <el-alert v-if="errorMsg" type="error" :title="errorMsg" :closable="false" show-icon style="margin-bottom:10px" />

    <!-- 来源分组映射表 -->
    <el-table v-loading="loading" :data="mappingRows" border size="small" max-height="50vh"
      :row-class-name="rowClassName" empty-text="请先点击"刷新预览"扫描来源数据">
      <el-table-column type="expand" width="44">
        <template #default="{ row }">
          <div style="padding:8px 16px">
            <p style="font-size:12px;color:var(--gt-color-text-secondary);margin:0 0 6px">涉及企业：</p>
            <el-tag v-for="e in row._entities" :key="e.node_key" size="small" style="margin:0 4px 4px 0">
              {{ e.company_name || e.node_key }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="来源名称" prop="source_label" min-width="180" show-overflow-tooltip />
      <el-table-column label="涉及企业" width="90" align="center">
        <template #default="{ row }">{{ row._entity_count }}</template>
      </el-table-column>
      <el-table-column label="建议目标" min-width="200">
        <template #default="{ row }">
          <div style="display:flex;align-items:center;gap:4px">
            <el-select v-model="row.target_row_id" size="small" style="flex:1" filterable clearable placeholder="请选择目标行">
              <el-option v-for="tr in templateRows" :key="tr.target_row_id" :label="tr.canonical_name" :value="tr.target_row_id" />
            </el-select>
            <el-tooltip v-if="targetMergeCount(row.target_row_id) > 1"
              :content="`${targetMergeCount(row.target_row_id)} 条来源行合并到此目标`" placement="top">
              <el-badge :value="targetMergeCount(row.target_row_id)" type="warning" style="margin-left:2px" />
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-select v-model="row.mapping_action" size="small" style="width:110px">
            <el-option label="映射" value="map" />
            <el-option label="合并映射" value="map_merge" />
            <el-option label="忽略" value="ignore" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row._status === 'ready' ? 'success' : row._status === 'stale' ? 'warning' : 'info'" size="small">
            {{ row._status === 'ready' ? '就绪' : row._status === 'stale' ? '已变化' : '待确认' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="置信度" width="100" align="center">
        <template #default="{ row }">
          <el-progress
            :percentage="Math.round(row._confidence * 100)"
            :stroke-width="14"
            :text-inside="true"
            :color="row._confidence >= 0.9 ? '#67c23a' : row._confidence >= 0.75 ? '#e6a23c' : '#f56c6c'"
            style="width:80px;display:inline-block"
          />
        </template>
      </el-table-column>
      <el-table-column label="匹配方式" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="matchTypeTagType(row._match_type)">{{ matchTypeLabel(row._match_type) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 忽略原因（当有 ignore 行时显示） -->
    <div v-if="hasIgnoredRows" style="margin-top:10px">
      <el-input v-model="ignoreReason" size="small" placeholder="忽略原因（所有忽略行共用）" style="width:360px" />
    </div>

    <template #footer>
      <div style="display:flex;justify-content:space-between;width:100%">
        <span style="font-size:12px;color:var(--gt-color-text-tertiary);line-height:32px">
          就绪 {{ readyCount }} / 待确认 {{ pendingCount }} / 忽略 {{ ignoredCount }}
        </span>
        <div>
          <el-button @click="$emit('update:visible', false)">取消</el-button>
          <el-button type="warning" @click="handleConfirmOnly" :loading="confirming"
            :disabled="pendingCount > 0 && !allMapped">确认映射</el-button>
          <el-button type="primary" @click="handleConfirmAndApply" :loading="applying"
            :disabled="pendingCount > 0 && !allMapped">确认并写入</el-button>
        </div>
      </div>
    </template>
  </el-dialog>

  <!-- 模板编辑器 -->
  <ConsolNoteDetailTemplateEditor
    v-model:visible="showTemplateEditor"
    :project-id="projectId" :section-id="sectionId" :year="year"
    :template-type="templateType" :template="currentTemplate"
    @saved="onTemplateSaved"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ConsolNoteDetailTemplateEditor from './ConsolNoteDetailTemplateEditor.vue'
import type {
  DetailTemplate, DetailTemplateRow, DetailRefreshPreview,
  MappingRuleItem, MappingSuggestion,
} from '@/services/consolidationApi'
import {
  previewDetailRefresh,
  confirmDetailMapping,
  applyDetailRefresh,
  getDetailTemplate,
  getDetailTemplateBinding,
  bindDetailTemplate,
  listDetailTemplates,
} from '@/services/consolidationApi'

interface MappingRow {
  source_label: string
  target_row_id: string
  mapping_action: 'map' | 'map_merge' | 'ignore'
  _entities: Array<{ node_key: string; company_name: string }>
  _entity_count: number
  _status: 'ready' | 'pending' | 'stale'
  _confidence: number
  _match_type: string
}

const props = defineProps<{
  visible: boolean
  projectId: string
  sectionId: string
  sectionTitle: string
  year: number
  templateType: 'soe' | 'listed'
  nodeKey?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied'): void
}>()

const loading = ref(false)
const confirming = ref(false)
const applying = ref(false)
const errorMsg = ref('')
const preview = ref<DetailRefreshPreview | null>(null)
const mappingRows = ref<MappingRow[]>([])
const templateRows = ref<DetailTemplateRow[]>([])
const ignoreReason = ref('不适用')
const showTemplateEditor = ref(false)
const currentTemplate = ref<DetailTemplate | null>(null)

const hasIgnoredRows = computed(() => mappingRows.value.some(r => r.mapping_action === 'ignore'))
const readyCount = computed(() => mappingRows.value.filter(r => r._status === 'ready' && r.mapping_action !== 'ignore').length)
const pendingCount = computed(() => mappingRows.value.filter(r => r._status === 'pending').length)
const ignoredCount = computed(() => mappingRows.value.filter(r => r.mapping_action === 'ignore').length)
const allMapped = computed(() => mappingRows.value.every(r =>
  r.mapping_action === 'ignore' || (r.target_row_id && r.mapping_action),
))

/** 统计某个目标行被多少条非忽略的来源行映射（>1 表示多条来源合并到同一目标） */
function targetMergeCount(targetRowId: string): number {
  if (!targetRowId) return 0
  return mappingRows.value.filter(r => r.target_row_id === targetRowId && r.mapping_action !== 'ignore').length
}

watch(() => props.visible, (v) => { if (v) loadPreview() })

async function loadPreview() {
  loading.value = true
  errorMsg.value = ''
  try {
    const result = await previewDetailRefresh(props.projectId, props.sectionId, props.year)
    preview.value = result
    templateRows.value = result.template_rows || []

    // 构建映射行（从建议中构建）
    const staleKeys = new Set((result.stale_entities || []).map(e => e.node_key))
    const groups = result.groups || []

    // 按来源标签→所属 group 的企业列表建索引（一个 label 可能出现在多个 group 中）
    const labelToEntities = new Map<string, Array<{ node_key: string; company_name: string }>>()
    for (const group of groups) {
      for (const sr of group.source_rows || []) {
        const label = (sr.label || '').trim()
        if (!label) continue
        const existing = labelToEntities.get(label) || []
        for (const ent of group.entities || []) {
          if (!existing.some(e => e.node_key === ent.node_key)) {
            existing.push({ node_key: ent.node_key, company_name: ent.company_name })
          }
        }
        labelToEntities.set(label, existing)
      }
    }

    const allEntities = groups.flatMap(g => g.entities)
    const rows: MappingRow[] = []

    for (const suggestion of result.suggestions || []) {
      // 精确匹配 group 的企业列表；找不到时降级为全部非 stale 企业
      const matched = labelToEntities.get(suggestion.source_label)
      const entities = (matched || allEntities).filter(e => !staleKeys.has(e.node_key))
      rows.push({
        source_label: suggestion.source_label,
        target_row_id: suggestion.suggested_target?.target_row_id || '',
        mapping_action: suggestion.match_type === 'manual' ? 'map' : 'map',
        _entities: entities,
        _entity_count: entities.length,
        _status: suggestion.suggested_target ? 'ready' : 'pending',
        _confidence: suggestion.confidence,
        _match_type: suggestion.match_type,
      })
    }
    mappingRows.value = rows
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail?.message || err?.message || '预览失败'
  } finally {
    loading.value = false
  }
}

function rowClassName({ row }: { row: MappingRow }) {
  if (row._status === 'stale') return 'gt-mapping-row-stale'
  if (row._status === 'pending' && !row.target_row_id) return 'gt-mapping-row-pending'
  if (row._confidence > 0 && row._confidence < 0.75) return 'gt-mapping-row-low-confidence'
  return ''
}

/** 匹配方式标签文字 */
function matchTypeLabel(matchType: string): string {
  const labels: Record<string, string> = {
    exact: '精确', alias: '别名', fuzzy: '模糊',
    history: '历史', rule_template: '模板', manual: '手动',
  }
  return labels[matchType] || matchType || '手动'
}

/** 匹配方式标签颜色 */
function matchTypeTagType(matchType: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (matchType === 'exact' || matchType === 'rule_template') return 'success'
  if (matchType === 'alias' || matchType === 'history') return ''
  if (matchType === 'fuzzy') return 'warning'
  return 'info'
}

function buildMappings(): MappingRuleItem[] {
  return mappingRows.value.map(r => ({
    source_label: r.source_label,
    target_row_id: r.target_row_id,
    mapping_action: r.mapping_action,
    ignore_reason: r.mapping_action === 'ignore' ? (ignoreReason.value || '不适用') : undefined,
  }))
}

async function handleConfirmOnlyInternal() {
  if (!preview.value) throw new Error('no preview')
  const groups = preview.value.groups || []
  for (const group of groups) {
    const mappings = buildMappings()
    await confirmDetailMapping(props.projectId, {
      section_id: props.sectionId,
      year: props.year,
      template_version_id: preview.value.template_version_id || '',
      source_structure_hash: group.hash,
      mappings,
      entity_node_keys: group.entities.map(e => ({ ...e, hash: group.hash })),
    })
  }
}

async function handleConfirmOnly() {
  if (!preview.value) return
  confirming.value = true
  try {
    await handleConfirmOnlyInternal()
    ElMessage.success('映射规则已确认')
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    if (err?.response?.status === 409) {
      ElMessage.warning(detail?.message || '来源数据已变化，请重新预览')
      await loadPreview()
    } else {
      ElMessage.error(detail?.message || '确认失败')
    }
  } finally {
    confirming.value = false
  }
}

async function handleConfirmAndApply() {
  let confirmOk = false
  confirming.value = true
  try {
    await handleConfirmOnlyInternal()
    confirmOk = true
  } catch {
    // handleConfirmOnlyInternal 已经处理了错误展示
  } finally {
    confirming.value = false
  }
  if (!confirmOk) return
  applying.value = true
  try {
    const result = await applyDetailRefresh(props.projectId, {
      section_id: props.sectionId,
      year: props.year,
      node_key: props.nodeKey,
    })
    if (result.status === 'applied') {
      ElMessage.success(`已写入：${result.filled_count || 0} 格填入，${result.kept_manual_count || 0} 格保留手工`)
      emit('applied')
      emit('update:visible', false)
    } else if (result.status === 'skipped_locked') {
      ElMessage.warning(result.reason || '该章节已锁定，未写入')
    }
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    ElMessage.error(detail?.message || '写入失败')
  } finally {
    applying.value = false
  }
}

async function handleEditTemplate() {
  // 加载当前绑定的模板——先查绑定，再从模板列表中匹配
  try {
    const binding = await getDetailTemplateBinding(props.projectId, props.sectionId)
    if (binding?.template_version_id) {
      // 列出该章节的模板，找到包含已绑定版本的那个
      const templates = await listDetailTemplates({
        template_type: props.templateType,
        section_id: props.sectionId,
      })
      const matched = templates.find(t =>
        t.latest_version?.id === binding.template_version_id
        || t.id === (t.latest_version as any)?.template_id,
      )
      currentTemplate.value = matched ?? null
    } else {
      currentTemplate.value = null
    }
  } catch {
    currentTemplate.value = null
  }
  showTemplateEditor.value = true
}

async function onTemplateSaved(tmpl: DetailTemplate) {
  // 自动绑定新版本
  if (tmpl.latest_version) {
    try {
      await bindDetailTemplate(props.projectId, props.sectionId, {
        template_version_id: tmpl.latest_version.id,
        confirm: true,
      })
    } catch { /* 绑定失败不阻断 */ }
  }
  // 刷新预览
  await loadPreview()
}
</script>

<style scoped>
:deep(.gt-mapping-row-stale) { background-color: #fef0e0 !important; }
:deep(.gt-mapping-row-pending) { background-color: #fafafa !important; }
:deep(.gt-mapping-row-low-confidence) { background-color: #fef0f0 !important; }
</style>
