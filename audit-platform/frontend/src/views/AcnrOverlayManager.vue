<template>
  <div class="acnr-overlay-manager">
    <!-- 头部（避免 GtPageHeader 拉伸裸按钮的坑，用普通 flex 行） -->
    <div class="page-head">
      <div class="head-title">
        <h2>ACNR 地址坐标名称库 · 项目 Overlay</h2>
        <p class="subtitle">
          项目级地址补丁（sheet 别名 / 绑定 / 自定义覆盖）。写入经乐观并发（CAS）保护，
          并发编辑冲突返回 409 → 刷新后重试，绝不静默覆盖。
        </p>
      </div>
      <div class="head-actions">
        <el-button :loading="loading" @click="reload">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增 Overlay</el-button>
      </div>
    </div>

    <el-card shadow="never" class="table-card" :body-style="{ padding: 0 }">
      <el-table :data="rows" v-loading="loading" size="small" empty-text="暂无 overlay">
        <el-table-column prop="addr_id" label="addr_id" min-width="160" />
        <el-table-column prop="overlay_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="typeTagColor(row.overlay_type)" size="small">{{ row.overlay_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="覆盖内容 (overrides)" min-width="240">
          <template #default="{ row }">
            <code class="overrides-preview">{{ preview(row.overrides) }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="120" show-overflow-tooltip />
        <el-table-column prop="owner" label="负责人" width="110" show-overflow-tooltip />
        <el-table-column prop="expires_at" label="到期" width="110">
          <template #default="{ row }">{{ row.expires_at || '—' }}</template>
        </el-table-column>
        <el-table-column prop="revision" label="版本" width="70" align="center" />
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑 Overlay' : '新增 Overlay'"
      width="620px"
      @closed="resetForm"
    >
      <el-form :model="form" label-width="120px" size="small">
        <el-form-item label="addr_id" required>
          <el-input
            v-model="form.addr_id"
            placeholder="如 D2/D2-2（父底稿码/sheet编码）"
            :disabled="editing"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.overlay_type" :disabled="editing" style="width: 100%">
            <el-option label="cust（自定义覆盖）" value="cust" />
            <el-option label="alias（sheet 别名）" value="alias" />
            <el-option label="binding（实例绑定）" value="binding" />
          </el-select>
        </el-form-item>

        <!-- alias 类型：便捷别名编辑 -->
        <template v-if="form.overlay_type === 'alias'">
          <el-form-item label="新增别名">
            <el-select
              v-model="aliasAdd"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="输入别名后回车"
              style="width: 100%"
            />
          </el-form-item>
        </template>

        <el-form-item label="overrides (JSON)">
          <el-input
            v-model="overridesText"
            type="textarea"
            :autosize="{ minRows: 4 }"
            placeholder='如 {"sheet_name_alias_add": ["别名A"]} 或 {"component_type": "d-form-table"}'
          />
          <div v-if="jsonError" class="json-error">JSON 解析失败：{{ jsonError }}</div>
        </el-form-item>

        <el-form-item label="原因">
          <el-input v-model="form.reason" placeholder="变更原因（审计留痕）" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="form.owner" placeholder="默认当前用户" />
        </el-form-item>
        <el-form-item label="到期日">
          <el-date-picker
            v-model="form.expires_at"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="留空则永久有效"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item v-if="editing" label="当前版本">
          <el-tag type="info">rev {{ form.expected_revision }}（保存时做 CAS 冲突检查）</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAcnr, type AcnrOverlay } from '@/services/acnr/useAcnr'

const route = useRoute()
const projectId = computed(() => String(route.params.projectId || ''))

const { listOverlays, applyOverlay, removeOverlay } = useAcnr()

const rows = ref<AcnrOverlay[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(false)
const aliasAdd = ref<string[]>([])
const overridesText = ref('{}')
const jsonError = ref('')

const form = reactive<{
  addr_id: string
  overlay_type: string
  reason: string
  owner: string
  expires_at: string | null
  expected_revision?: number
}>({
  addr_id: '',
  overlay_type: 'cust',
  reason: '',
  owner: '',
  expires_at: null,
  expected_revision: undefined,
})

function typeTagColor(t: string): 'success' | 'warning' | 'info' {
  if (t === 'alias') return 'success'
  if (t === 'binding') return 'warning'
  return 'info'
}

function preview(obj: Record<string, unknown>): string {
  try {
    const s = JSON.stringify(obj)
    return s.length > 80 ? s.slice(0, 80) + '…' : s
  } catch {
    return String(obj)
  }
}

async function reload() {
  if (!projectId.value) return
  loading.value = true
  try {
    rows.value = await listOverlays(projectId.value)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.addr_id = ''
  form.overlay_type = 'cust'
  form.reason = ''
  form.owner = ''
  form.expires_at = null
  form.expected_revision = undefined
  aliasAdd.value = []
  overridesText.value = '{}'
  jsonError.value = ''
  editing.value = false
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: AcnrOverlay) {
  resetForm()
  editing.value = true
  form.addr_id = row.addr_id
  form.overlay_type = row.overlay_type
  form.reason = row.reason || ''
  form.owner = row.owner || ''
  form.expires_at = row.expires_at || null
  form.expected_revision = row.revision
  overridesText.value = JSON.stringify(row.overrides ?? {}, null, 2)
  const add = (row.overrides as any)?.sheet_name_alias_add
  aliasAdd.value = Array.isArray(add) ? add.map(String) : []
  dialogVisible.value = true
}

function buildOverrides(): Record<string, unknown> | null {
  jsonError.value = ''
  let base: Record<string, unknown> = {}
  const txt = overridesText.value.trim()
  if (txt) {
    try {
      const parsed = JSON.parse(txt)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        base = parsed
      } else {
        jsonError.value = 'overrides 必须是 JSON 对象'
        return null
      }
    } catch (e: any) {
      jsonError.value = e?.message || '格式错误'
      return null
    }
  }
  // alias 便捷编辑：合并到 sheet_name_alias_add（去空 + 去重）
  if (form.overlay_type === 'alias' && aliasAdd.value.length) {
    const clean = Array.from(new Set(aliasAdd.value.map((s) => s.trim()).filter(Boolean)))
    base.sheet_name_alias_add = clean
  }
  return base
}

async function onSave() {
  if (!form.addr_id.trim()) {
    ElMessage.warning('请填写 addr_id')
    return
  }
  const overrides = buildOverrides()
  if (overrides === null) return

  saving.value = true
  try {
    await applyOverlay({
      project_id: projectId.value,
      addr_id: form.addr_id.trim(),
      overrides,
      overlay_type: form.overlay_type,
      reason: form.reason,
      owner: form.owner,
      expires_at: form.expires_at || null,
      expected_revision: editing.value ? form.expected_revision : undefined,
    })
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await reload()
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 409) {
      ElMessage.error('并发编辑冲突：该 overlay 已被他人修改，请刷新后基于最新版本重试')
      await reload()
    } else if (status === 403) {
      ElMessage.error('权限不足：仅项目经理 / 合伙人 / 管理员可变更 overlay')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

async function onDelete(row: AcnrOverlay) {
  try {
    await ElMessageBox.confirm(
      `确认删除 overlay「${row.addr_id}」(${row.overlay_type})？`,
      '删除确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await removeOverlay(projectId.value, row.addr_id, row.overlay_type)
    ElMessage.success('已删除')
    await reload()
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 403) {
      ElMessage.error('权限不足：仅项目经理 / 合伙人 / 管理员可删除 overlay')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '删除失败')
    }
  }
}

onMounted(reload)
</script>

<style scoped>
.acnr-overlay-manager {
  padding: 16px;
  font-size: 13px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.head-title h2 {
  margin: 0 0 4px;
  font-size: 18px;
}
.subtitle {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  max-width: 760px;
}
.head-actions {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
}
.table-card {
  border: 1px solid var(--el-border-color-lighter);
}
.overrides-preview {
  font-size: 12px;
  color: var(--el-text-color-regular);
  word-break: break-all;
}
.json-error {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-top: 4px;
}
</style>
