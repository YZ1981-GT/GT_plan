<template>
  <div class="gt-tree-node">
    <!-- 当前节点 -->
    <div
      class="gt-node-row"
      :class="{
        'gt-node-row--active': selectedId === node.id,
        'gt-node-row--consolidated': node.report_scope === 'consolidated',
      }"
      :style="{ paddingLeft: depth * 20 + 8 + 'px' }"
    >
      <!-- 展开/收起按钮 -->
      <span
        v-if="hasChildren"
        class="gt-node-toggle"
        @click.stop="expanded = !expanded"
      >{{ expanded ? '−' : '+' }}</span>
      <span v-else class="gt-node-toggle gt-node-toggle--leaf" />

      <!-- checkbox -->
      <el-checkbox
        :model-value="checkedIds.includes(node.id)"
        size="small"
        class="gt-node-check"
        @change="(val: boolean) => $emit('toggle-check', node.id, val)"
        @click.stop
      />

      <!-- 状态色条 -->
      <div class="gt-node-status" :class="'gt-status--' + (node.status || 'created')" />

      <!-- 内容区 -->
      <div class="gt-node-body" @click="$emit('select', node)">
        <div class="gt-node-title">
          <el-icon v-if="node.report_scope === 'consolidated'" :size="13" style="color: var(--gt-color-primary); margin-right: 4px"><FolderOpened /></el-icon>
          {{ node.name || node.client_name || '未命名项目' }}
        </div>
        <div class="gt-node-meta">
          <span>{{ node.client_name || '-' }}</span>
          <span class="gt-node-meta-right">
            <el-tag v-if="node.status !== 'created'" :type="statusTagType(node.status)" size="small" round>
              {{ statusLabel(node.status) }}
            </el-tag>
            <el-button
              class="gt-node-action-inline"
              :icon="EditPen"
              size="small"
              text
              @click.stop="$emit('edit', node)"
            />
            <el-button
              class="gt-node-action-inline gt-node-action--danger"
              type="danger"
              :icon="Delete"
              size="small"
              text
              @click.stop="$emit('delete', node)"
            />
          </span>
        </div>
      </div>
    </div>

    <!-- 子节点（递归） -->
    <div v-if="hasChildren && expanded" class="gt-node-children">
      <ProjectTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :selected-id="selectedId"
        :checked-ids="checkedIds"
        @select="(p: any) => $emit('select', p)"
        @toggle-check="(id: string, v: boolean) => $emit('toggle-check', id, v)"
        @delete="(p: any) => $emit('delete', p)"
        @edit="(p: any) => $emit('edit', p)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { FolderOpened, Delete, EditPen } from '@element-plus/icons-vue'

interface ProjectNode {
  id: string
  name: string | null
  client_name: string
  status: string
  report_scope: string | null
  children?: ProjectNode[]
}

const props = defineProps<{
  node: ProjectNode
  depth: number
  selectedId: string | null
  checkedIds: string[]
}>()

defineEmits<{
  (e: 'select', project: any): void
  (e: 'toggle-check', id: string, checked: boolean): void
  (e: 'delete', project: any): void
  (e: 'edit', project: any): void
}>()

const expanded = ref(true)
const hasChildren = computed(() => (props.node.children?.length ?? 0) > 0)

function statusTagType(s: string) {
  const m: Record<string, string> = { created: 'info', planning: 'warning', execution: '', completion: 'success', archived: 'info' }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = { created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档' }
  return m[s] || s || '-'
}
</script>

<style scoped>
.gt-tree-node { user-select: none; }

.gt-node-row {
  display: flex;
  align-items: center;
  margin-bottom: 2px;
  border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg-white);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--gt-transition-fast);
  min-height: 38px;
  padding-right: 4px;
}
.gt-node-row:hover {
  border-color: rgba(75, 45, 119, 0.1);
  background: #faf8fd;
  box-shadow: 0 1px 4px rgba(75, 45, 119, 0.06);
}
.gt-node-row--active {
  border-color: var(--gt-color-primary) !important;
  background: var(--gt-color-primary-bg) !important;
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12) !important;
}
.gt-node-row--consolidated {
  border-left: 2px solid var(--gt-color-primary-lighter);
}

.gt-node-toggle {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--gt-color-text-secondary);
  cursor: pointer;
  flex-shrink: 0;
  border-radius: 2px;
  transition: background var(--gt-transition-fast);
}
.gt-node-toggle:hover { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.gt-node-toggle--leaf { visibility: hidden; }

.gt-node-check { flex-shrink: 0; margin: 0 2px; }

.gt-node-status { width: 3px; flex-shrink: 0; align-self: stretch; border-radius: 2px; margin: 4px 2px; }
.gt-status--created { background: var(--gt-color-text-tertiary); }
.gt-status--planning { background: linear-gradient(180deg, #FFC23D, #e6a817); }
.gt-status--execution { background: var(--gt-gradient-primary); }
.gt-status--completion { background: linear-gradient(180deg, #28A745, #1e8a38); }
.gt-status--archived { background: var(--gt-color-border); }

.gt-node-body { padding: 3px 6px; flex: 1; min-width: 0; }
.gt-node-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text);
  word-break: break-all;
  line-height: 1.3;
  display: flex;
  align-items: flex-start;
}
.gt-node-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1px;
  font-size: 11px;
  color: var(--gt-color-text-secondary);
  word-break: break-all;
}
.gt-node-meta-right {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.gt-node-action-inline {
  opacity: 0;
  transition: opacity var(--gt-transition-fast);
  flex-shrink: 0;
  padding: 2px !important;
  height: 18px !important;
  width: 18px !important;
}
.gt-node-row:hover .gt-node-action-inline { opacity: 1; }
.gt-node-action--danger { margin-right: 2px; }

.gt-node-children {
  border-left: 1px dashed var(--gt-color-border);
  margin-left: 14px;
}
</style>
