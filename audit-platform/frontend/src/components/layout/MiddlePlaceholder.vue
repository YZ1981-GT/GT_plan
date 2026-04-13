<template>
  <div class="gt-middle-placeholder">
    <div class="gt-mp-header">
      <el-icon :size="18"><component :is="moduleIcon" /></el-icon>
      <span class="gt-mp-title">{{ moduleLabel }}</span>
    </div>
    <div class="gt-mp-body">
      <el-empty :description="moduleDesc" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  User, Reading, Timer, Connection, Stamp, Box, Setting,
} from '@element-plus/icons-vue'

const props = defineProps<{ module: string }>()

const moduleConfig: Record<string, { label: string; desc: string; icon: any }> = {
  team: { label: '人员委派', desc: '人员列表和项目分配（开发中）', icon: User },
  knowledge: { label: '知识库', desc: '文档树和搜索（开发中）', icon: Reading },
  workhours: { label: '工时管理', desc: '工时录入和统计（开发中）', icon: Timer },
  consolidation: { label: '合并项目', desc: '合并树和抵消分录（开发中）', icon: Connection },
  confirmation: { label: '函证管理', desc: '函证清单和跟踪（开发中）', icon: Stamp },
  archive: { label: '归档管理', desc: '归档检查清单（开发中）', icon: Box },
  settings: { label: '系统设置', desc: '系统配置（开发中）', icon: Setting },
}

const config = computed(() => moduleConfig[props.module] || { label: props.module, desc: '功能开发中', icon: Setting })
const moduleLabel = computed(() => config.value.label)
const moduleDesc = computed(() => config.value.desc)
const moduleIcon = computed(() => config.value.icon)
</script>

<style scoped>
.gt-middle-placeholder { height: 100%; display: flex; flex-direction: column; }
.gt-mp-header {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-3); border-bottom: 1px solid var(--gt-color-border-light);
  color: var(--gt-color-primary); font-weight: 600; font-size: var(--gt-font-size-sm);
}
.gt-mp-body { flex: 1; display: flex; align-items: center; justify-content: center; }
</style>
