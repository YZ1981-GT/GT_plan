<template>
  <el-dialog
    v-model="visible"
    title="附注公式管理"
    width="800px"
    append-to-body
    destroy-on-close
  >
    <div v-if="!currentNote" class="gt-nf-empty">
      请先选择一个附注章节
    </div>
    <template v-else>
      <div class="gt-nf-header">
        <span>{{ currentNote.note_section }} {{ currentNote.section_title }}</span>
        <el-tag size="small" type="info">{{ currentNote.content_type }}</el-tag>
      </div>

      <!-- 分类 Tab -->
      <el-tabs v-model="activeCategory" style="margin-top: 12px">
        <el-tab-pane label="⚡ 自动运算" name="auto_calc" />
        <el-tab-pane label="🔍 逻辑审核" name="logic_check" />
        <el-tab-pane label="💡 合理性" name="reasonability" />
      </el-tabs>

      <!-- 公式列表 -->
      <el-table v-loading="loading" :data="filteredFormulas" size="small" border max-height="350">
        <el-table-column prop="target" label="目标单元格" width="120" />
        <el-table-column label="公式" min-width="250">
          <template #default="{ row }">
            <el-input v-if="row._editing" v-model="row.formula" size="small">
              <template #append>
                <el-button size="small" @click="openRefPicker(row)">引用</el-button>
              </template>
            </el-input>
            <code v-else style="font-size: var(--gt-font-size-xs)">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="说明" width="160">
          <template #default="{ row }">
            <el-input v-if="row._editing" v-model="row.description" size="small" />
            <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
            <el-button v-else size="small" link type="success" :loading="persisting" @click="completeRow(row)">完成</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button size="small" @click="addFormula">新增公式</el-button>
      </div>
    </template>

    <template #footer>
      <el-button v-if="currentNote" @click="onRegenerate" :loading="regenerating">重新生成</el-button>
      <el-button type="primary" @click="onApply" :loading="applying">应用自动运算</el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 引用选择器 -->
    <FormulaRefPicker
      v-model="showRefPicker"
      :report-rows="refPickerData.reportRows"
      :tb-rows="refPickerData.tbRows"
      :note-rows="refPickerData.noteRows"
      @insert="onInsertRef"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { useAddressRegistry } from '@/stores/addressRegistry'
import FormulaRefPicker from './FormulaRefPicker.vue'

const props = defineProps<{
  modelValue: boolean
  currentNote: any
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'applied': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeCategory = ref('auto_calc')
const applying = ref(false)
const regenerating = ref(false)
const persisting = ref(false)
const loading = ref(false)
const showRefPicker = ref(false)
const editingRow = ref<any>(null)

// ACNR-backed 公式引用校验（Req 15.5 → Req 9）。
// store.validate 优先走 ACNR resolveFormula（与后端 Req 9 同源），
// 未命中/非 WP 域/infra 失败时 fail-open 回退 legacy 权威校验。
const addrStore = useAddressRegistry()

// 引用选择器数据（懒加载）
const refPickerData = ref<{ reportRows: any[], tbRows: any[], noteRows: any[] }>({
  reportRows: [], tbRows: [], noteRows: [],
})

async function openRefPicker(row: any) {
  editingRow.value = row
  // 加载引用数据
  try {
    if (!refPickerData.value.reportRows.length) {
      const [reportData, tbData] = await Promise.all([
        api.get(`/api/reports/${props.projectId}/${props.year}/balance_sheet`).catch(() => []),
        api.get(`/api/trial-balance/`, { params: { project_id: props.projectId, year: props.year } }).catch(() => []),
      ])
      refPickerData.value.reportRows = Array.isArray(reportData) ? reportData : (reportData || [])
      refPickerData.value.tbRows = Array.isArray(tbData) ? tbData : (tbData || [])
    }
  } catch { /* 静默 */ }
  showRefPicker.value = true
}

function onInsertRef(formula: string, _label: string) {
  if (editingRow.value) {
    editingRow.value.formula = (editingRow.value.formula || '') + formula
  }
}

// 附注公式列表（Req 15.1：onOpen 从后端加载已保存/预览集，替代此前空 ref）
const formulas = ref<any[]>([])

const filteredFormulas = computed(() => {
  return formulas.value.filter(f => f.category === activeCategory.value)
})

// ─── 加载当前公式集（Req 15.1） ───────────────────────────────
async function loadFormulas() {
  if (!props.currentNote || !props.projectId || !props.year) {
    formulas.value = []
    return
  }
  const noteSection = props.currentNote.note_section
  loading.value = true
  try {
    // GET 返回 { formulas: [...] }（http 拦截器已解包 {code,data} 信封）
    const resp = await api.get(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${noteSection}/formulas`
    )
    const list = resp?.formulas
    formulas.value = (Array.isArray(list) ? list : []).map((f: any) => ({ ...f, _editing: false }))
  } catch (e: any) {
    formulas.value = []
    handleApiError(e, '加载公式失败')
  } finally {
    loading.value = false
  }
  // 设置校验上下文（供 validate 的 legacy 回退按项目/年度解析非 WP 域引用）。
  // refresh 会同步写入 _projectId/_year，故无需 await 即可让后续 validate 生效。
  try { addrStore.refresh(props.projectId, props.year) } catch { /* 静默 */ }
}

// 弹窗打开 / 切换附注章节时加载（Req 15.1）
watch(() => props.modelValue, (val) => {
  if (val) loadFormulas()
})
watch(() => props.currentNote, () => {
  if (props.modelValue) loadFormulas()
})

// ─── 引用校验（Req 15.5 → Req 9，ACNR-backed，悬空引用不入库） ───
async function collectDanglingRefs(list: any[]): Promise<string[]> {
  const dangling: string[] = []
  for (const row of list) {
    const expr = (row?.formula || '').trim()
    if (!expr) continue
    try {
      const res = await addrStore.validate(expr)
      if (res && res.valid === false) {
        for (const iss of (res.issues || [])) {
          dangling.push(iss?.ref || expr)
        }
      }
    } catch {
      // infra 失败 fail-open：不因校验设施故障阻断保存（Req 9.3）
    }
  }
  return dangling
}

// ─── 持久化当前编辑集（Req 15.2/15.3） ────────────────────────
// 整体 PUT 用户编辑集（"这套就是最新集"语义）；空行由后端过滤。
// 保存前经 ACNR 校验，悬空引用提示且不入库（Req 15.5）。
async function persistFormulas(): Promise<boolean> {
  if (!props.currentNote || !props.projectId || !props.year) {
    ElMessage.warning('请先选择附注章节')
    return false
  }
  const dangling = await collectDanglingRefs(formulas.value)
  if (dangling.length) {
    ElMessage.error(`公式引用无法解析，未保存：${[...new Set(dangling)].join('；')}`)
    return false
  }
  const noteSection = props.currentNote.note_section
  // 剔除前端本地态字段（_editing），只送持久化 shape
  const payload = formulas.value
    .filter(f => (f?.formula || '').trim())
    .map(({ _editing, ...rest }) => rest)
  persisting.value = true
  try {
    await api.put(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${noteSection}/formulas`,
      { formulas: payload }
    )
    return true
  } catch (e: any) {
    handleApiError(e, '保存失败')
    return false
  } finally {
    persisting.value = false
  }
}

// 行「完成」：校验 + 持久化全集（Req 15.2）；成功才退出编辑态
async function completeRow(row: any) {
  const ok = await persistFormulas()
  if (ok) {
    row._editing = false
    ElMessage.success('已保存')
  }
}

// 新增公式：推入空可编辑行（Req 15.3，去掉硬编码 SUM 占位）
function addFormula() {
  formulas.value.push({
    target: '',
    formula: '',
    category: activeCategory.value,
    description: '',
    source: '手工',
    type: '',
    _editing: true,
  })
}

// ─── 应用自动运算（Req 15.4）：执行当前持久化/编辑集 ──────────────
// 先 PUT 持久化编辑集（保证跨重开不丢），再触发后端计算回填。
// 注：后端暂无"执行任意用户公式"端点，apply-formulas 按 check_presets 计算并
// 回填 auto 单元格；用户编辑集通过 PUT 持久化并在下次打开时重新加载（Req 15.2）。
async function onApply() {
  if (!props.projectId || !props.year || !props.currentNote) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  applying.value = true
  try {
    const saved = await persistFormulas()
    if (!saved) return
    const noteSection = props.currentNote.note_section
    const result = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${noteSection}/apply-formulas`
    )
    ElMessage.success(`公式已应用：执行 ${result?.executed || 0} 个，更新 ${result?.updated || 0} 个单元格`)
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '应用失败')
  } finally {
    applying.value = false
  }
}

// ─── 重新生成（Req 15.4）：显式从 check_presets 重生成预设公式 ─────
// 独立于 onApply，不持久化用户编辑集，仅触发后端按预设重生成并计算。
async function onRegenerate() {
  if (!props.projectId || !props.year || !props.currentNote) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  regenerating.value = true
  try {
    const noteSection = props.currentNote.note_section
    const result = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${noteSection}/apply-formulas`
    )
    ElMessage.success(`已重新生成：执行 ${result?.executed || 0} 个，更新 ${result?.updated || 0} 个单元格`)
    // 重新生成后刷新列表，展示最新预设公式
    await loadFormulas()
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '重新生成失败')
  } finally {
    regenerating.value = false
  }
}
</script>

<style scoped>
.gt-nf-empty { text-align: center; padding: 40px; color: var(--gt-color-text-tertiary); }
.gt-nf-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }
</style>
