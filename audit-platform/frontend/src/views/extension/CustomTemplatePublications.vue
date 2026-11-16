<script setup lang="ts">
/**
 * 自定义模板 publication 管理页。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20
 *
 * 展示 finalize 产出的 publication，支持：
 *   - 推进可见性（四 consumer 全 ACCEPTED 才 ACTIVE）；
 *   - 对 ACTIVE publication 实例化（需 sheet 映射，服务端按 preflight 校验）。
 *
 * 🔴 状态一律取服务端返回值，前端不按 state 自己推 `runtimeDiscoverable`。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  PUBLICATION_STATE_LABELS,
  REQUIRED_FINALIZE_CONSUMERS,
  toProjectionMode,
  useTemplatePublications,
  type PreflightSheet,
  type TemplatePublication,
} from '@/composables/useTemplatePublications'

const pubs = useTemplatePublications()
const busyKey = ref<string | null>(null)

/** 实例化弹窗状态 */
const instantiateOpen = ref(false)
const instantiateTarget = ref<TemplatePublication | null>(null)
const workingPaperId = ref('')
const sheetRows = ref<{ sheetUid: string; wpCode: string; componentType: string; projectionMode: string }[]>([])
const instantiateResult = ref<string | null>(null)
/** preflight 候选 sheet（下拉数据源；为空时禁用「确认实例化」并提示先跑预检）。 */
const preflightSheets = ref<PreflightSheet[]>([])
const preflightLoading = ref(false)

const stateLabel = (state: string) => PUBLICATION_STATE_LABELS[state] ?? state
const shortKey = (key: string) => (key.length > 34 ? `${key.slice(0, 34)}…` : key)

const hasPending = computed(() => pubs.pending.value.length > 0)

onMounted(() => {
  void pubs.load()
})

async function onCommit(pub: TemplatePublication) {
  const confirmed = await ElMessageBox.confirm(
    `将把四个必需 consumer（${REQUIRED_FINALIZE_CONSUMERS.join(' / ')}）全部标为 ACCEPTED，`
      + '并尝试把该 publication 推进到 ACTIVE。确认继续？',
    '推进可见性',
    { type: 'warning', confirmButtonText: '确认推进', cancelButtonText: '取消' },
  ).catch(() => null)
  if (!confirmed) return

  busyKey.value = pub.publicationKey
  try {
    const result = await pubs.acceptAllConsumers(pub.publicationKey)
    if (!result) {
      ElMessage.error(pubs.lastError.value ?? '推进可见性失败')
      return
    }
    if (result.runtimeDiscoverable) {
      ElMessage.success('已推进到 ACTIVE，可实例化')
    } else if (result.visibilityState === 'REJECTED') {
      ElMessage.warning('存在 REJECTED ACK，publication 已标记失败')
    } else {
      ElMessage.info('ACK 尚未收齐，publication 仍待确认')
    }
  } finally {
    busyKey.value = null
  }
}

async function openInstantiate(pub: TemplatePublication) {
  instantiateTarget.value = pub
  instantiateResult.value = null
  workingPaperId.value = ''
  preflightSheets.value = []
  sheetRows.value = [{ sheetUid: '', wpCode: '', componentType: 'audit-sheet', projectionMode: 'editable_grid' }]
  instantiateOpen.value = true

  // 从 publication 的 candidateId（= artifactId）拉 preflight 报告里的真实 sheet 列表。
  // 下拉是**唯一**可选来源 —— 手填的 sheetUid 服务端会 422。
  preflightLoading.value = true
  try {
    const sheets = await pubs.loadPreflightSheets(pub.candidateId)
    preflightSheets.value = sheets
    if (!sheets.length) {
      ElMessage.warning(pubs.lastError.value ?? '该产物没有 preflight sheet 报告，请先跑预检')
    }
  } finally {
    preflightLoading.value = false
  }
}

/** 可纳入的候选（隐藏页服务端会拒，这里直接不给选）。 */
const selectableSheets = computed(() =>
  preflightSheets.value.filter((s) => !s.state || s.state === 'visible'),
)

/** 已被其它行占用的 sheetUid（避免重复选）。 */
function takenSheetUids(exceptIndex: number): Set<string> {
  return new Set(
    sheetRows.value
      .filter((_, i) => i !== exceptIndex)
      .map((r) => r.sheetUid)
      .filter(Boolean),
  )
}

function optionsForRow(index: number): PreflightSheet[] {
  const taken = takenSheetUids(index)
  return selectableSheets.value.filter((s) => !taken.has(s.sheetUid))
}

/** 选中 sheet 后带出推荐 mode 与 wpCode 默认值（wpCode 仍可改）。 */
function onSheetPicked(index: number, sheetUid: string) {
  const sheet = preflightSheets.value.find((s) => s.sheetUid === sheetUid)
  if (!sheet) return
  const row = sheetRows.value[index]
  if (!row) return
  row.projectionMode = toProjectionMode(sheet.projectionRecommendation)
  if (!row.wpCode.trim()) {
    // 没有可靠来源推 wpCode，留空让用户填；不猜业务编码。
    row.wpCode = ''
  }
}

function addSheetRow() {
  sheetRows.value.push({ sheetUid: '', wpCode: '', componentType: 'audit-sheet', projectionMode: 'editable_grid' })
}

function removeSheetRow(index: number) {
  sheetRows.value.splice(index, 1)
}

async function submitInstantiate() {
  const pub = instantiateTarget.value
  if (!pub) return
  if (!workingPaperId.value.trim()) {
    ElMessage.warning('请填写目标底稿 ID')
    return
  }
  // 🔴 不在这里再查 preflightSheets.length：按钮已用 :disabled 挡住
  // （见模板 :disabled="!preflightSheets.length"）。两处并存会互相兜底，
  // 把任何一处的变异掩盖掉（已实测：删掉本检查时用例仍绿）。
  const sheets = sheetRows.value
    .filter((r) => r.sheetUid.trim() && r.wpCode.trim())
    .map((r) => ({
      sheetUid: r.sheetUid.trim(),
      wpCode: r.wpCode.trim(),
      componentType: r.componentType.trim() || 'audit-sheet',
      projectionMode: r.projectionMode.trim() || 'editable_grid',
    }))
  if (!sheets.length) {
    ElMessage.warning('至少选择一行 sheet 并填写 wpCode')
    return
  }
  // 前端先自查一遍：选的 uid 必须都在候选里（服务端仍会校验）
  const known = new Set(preflightSheets.value.map((s) => s.sheetUid))
  const unknown = sheets.filter((s) => !known.has(s.sheetUid))
  if (unknown.length) {
    ElMessage.warning(`sheetUid 不在 preflight 报告中：${unknown.map((u) => u.sheetUid).join(', ')}`)
    return
  }

  busyKey.value = pub.publicationKey
  try {
    const result = await pubs.instantiate(pub.publicationKey, workingPaperId.value.trim(), sheets)
    if (!result) {
      ElMessage.error(pubs.lastError.value ?? '实例化失败')
      return
    }
    instantiateResult.value = `已建册 ${result.workbookInstanceId}（${result.sheetCount} 个 sheet）`
    instantiateOpen.value = false
    ElMessage.success('实例化完成')
  } finally {
    busyKey.value = null
  }
}
</script>

<template>
  <div class="gt-pubs" data-testid="custom-template-publications">
    <header class="gt-pubs__head">
      <div>
        <h2>模板发布（publication）</h2>
        <p class="gt-pubs__hint">
          finalize 后进入「待确认可见性」；四个 consumer 全部 ACCEPTED 才 ACTIVE，ACTIVE 才能实例化。
        </p>
      </div>
      <el-button :loading="pubs.loading.value" data-testid="pubs-refresh" @click="pubs.load()">
        刷新
      </el-button>
    </header>

    <el-alert
      v-if="pubs.lastError.value"
      :title="pubs.lastError.value"
      type="error"
      show-icon
      :closable="false"
      class="gt-pubs__error"
    />

    <el-empty
      v-if="!pubs.loading.value && !pubs.publications.value.length"
      description="暂无 publication。先走「自定义模板摄取」完成 finalize。"
      data-testid="pubs-empty"
    />

    <el-table
      v-else
      :data="pubs.publications.value"
      row-key="publicationKey"
      size="small"
      data-testid="pubs-table"
    >
      <el-table-column label="Publication" min-width="240">
        <template #default="{ row }">
          <span :title="row.publicationKey">{{ shortKey(row.publicationKey) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag :type="row.state === 'ACTIVE' ? 'success' : row.state === 'FAILED' ? 'danger' : 'info'">
            {{ stateLabel(row.state) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可实例化" width="100">
        <template #default="{ row }">
          <span :data-testid="`discoverable-${row.publicationKey}`">
            {{ row.runtimeDiscoverable ? '是' : '否' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="Artifact" min-width="160">
        <template #default="{ row }">
          <span :title="row.artifactDigest">{{ shortKey(row.artifactDigest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.state === 'PENDING_VISIBILITY'"
            link
            type="primary"
            :loading="busyKey === row.publicationKey"
            :data-testid="`commit-${row.publicationKey}`"
            @click="onCommit(row)"
          >
            推进可见性
          </el-button>
          <el-button
            v-if="row.runtimeDiscoverable"
            link
            type="primary"
            :data-testid="`instantiate-${row.publicationKey}`"
            @click="openInstantiate(row)"
          >
            实例化
          </el-button>
          <span v-if="!row.runtimeDiscoverable && row.state !== 'PENDING_VISIBILITY'" class="gt-pubs__muted">
            不可操作
          </span>
        </template>
      </el-table-column>
    </el-table>

    <p v-if="instantiateResult" class="gt-pubs__result" data-testid="instantiate-result">
      {{ instantiateResult }}
    </p>

    <el-dialog v-model="instantiateOpen" title="实例化 publication" width="760px">
      <el-form label-width="120px">
        <el-form-item label="目标底稿 ID">
          <el-input v-model="workingPaperId" placeholder="WorkingPaper UUID" data-testid="wp-id-input" />
        </el-form-item>
        <el-form-item label="Sheet 映射">
          <div class="gt-pubs__sheets">
            <div v-for="(row, i) in sheetRows" :key="i" class="gt-pubs__sheet-row">
              <el-select
                v-model="row.sheetUid"
                :loading="preflightLoading"
                filterable
                clearable
                placeholder="选择 sheet（来自 preflight 报告）"
                :data-testid="`sheet-select-${i}`"
                @change="(v: string) => onSheetPicked(i, v)"
              >
                <el-option
                  v-for="s in optionsForRow(i)"
                  :key="s.sheetUid"
                  :label="`${s.order}. ${s.sheetName || s.sheetUid}`"
                  :value="s.sheetUid"
                />
              </el-select>
              <el-input v-model="row.wpCode" placeholder="wpCode" />
              <el-input v-model="row.componentType" placeholder="componentType" />
              <el-input v-model="row.projectionMode" placeholder="projectionMode" />
              <el-button link type="danger" @click="removeSheetRow(i)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addSheetRow">+ 增加一行</el-button>
          </div>
        </el-form-item>
      </el-form>
      <p class="gt-pubs__hint">
        可选 sheet 来自该产物的 preflight 报告（共 {{ selectableSheets.length }} 个可见页）；
        隐藏页不列出。wpCode / componentType 仍需人工填写，不猜业务编码。
      </p>
      <template #footer>
        <el-button @click="instantiateOpen = false">取消</el-button>
        <el-button
          type="primary"
          :loading="!!busyKey"
          :disabled="!preflightSheets.length"
          data-testid="instantiate-submit"
          @click="submitInstantiate"
        >
          确认实例化
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-pubs {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px 16px;
}
.gt-pubs__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.gt-pubs__head h2 {
  margin: 0 0 6px;
  font-size: 1.15rem;
}
.gt-pubs__hint {
  margin: 0;
  color: var(--el-text-color-secondary, #666);
  font-size: 0.85rem;
  line-height: 1.5;
}
.gt-pubs__error {
  margin-bottom: 12px;
}
.gt-pubs__muted {
  color: var(--el-text-color-placeholder, #a8abb2);
  font-size: 0.85rem;
}
.gt-pubs__result {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f0f9eb;
  border-radius: 6px;
  color: #529b2e;
}
.gt-pubs__sheets {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.gt-pubs__sheet-row {
  display: grid;
  grid-template-columns: 1.6fr 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: center;
}
</style>
