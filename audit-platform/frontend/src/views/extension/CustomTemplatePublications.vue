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
  useTemplatePublications,
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

function openInstantiate(pub: TemplatePublication) {
  instantiateTarget.value = pub
  instantiateResult.value = null
  workingPaperId.value = ''
  sheetRows.value = [{ sheetUid: '', wpCode: '', componentType: 'audit-sheet', projectionMode: 'editable_grid' }]
  instantiateOpen.value = true
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
  const sheets = sheetRows.value
    .filter((r) => r.sheetUid.trim() && r.wpCode.trim())
    .map((r) => ({
      sheetUid: r.sheetUid.trim(),
      wpCode: r.wpCode.trim(),
      componentType: r.componentType.trim() || 'audit-sheet',
      projectionMode: r.projectionMode.trim() || 'editable_grid',
    }))
  if (!sheets.length) {
    ElMessage.warning('至少填写一行 sheet 映射（sheetUid + wpCode）')
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
              <el-input v-model="row.sheetUid" placeholder="sheetUid（须在 preflight 报告里）" />
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
        sheetUid 必须是该 artifact preflight 报告里真实存在的；凭空填会被服务端拒绝（422）。
      </p>
      <template #footer>
        <el-button @click="instantiateOpen = false">取消</el-button>
        <el-button
          type="primary"
          :loading="!!busyKey"
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
