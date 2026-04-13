<template>
  <div class="gt-plugin-mgmt">
    <div class="gt-page-header">
      <h2 class="gt-page-title">AI插件管理</h2>
      <el-button size="small" @click="loadPlugins" :loading="loading">刷新</el-button>
    </div>

    <PluginList :plugins="plugins" :loading="loading" @config="openConfig" @toggled="loadPlugins" />

    <el-divider />

    <div class="gt-plugin-sections">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="模型切换" name="model">
          <div class="gt-tab-content">
            <h4>LLM模型选择</h4>
            <ModelSwitcher v-model="selectedModel" style="width: 300px" @change="onModelChange" />
          </div>
        </el-tab-pane>
        <el-tab-pane label="外部API" name="api">
          <ExternalAPIConfig />
        </el-tab-pane>
      </el-tabs>
    </div>

    <PluginConfig v-model="showConfig" :plugin="configPlugin" @saved="loadPlugins" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import PluginList from '@/components/extension/PluginList.vue'
import PluginConfig from '@/components/extension/PluginConfig.vue'
import ModelSwitcher from '@/components/extension/ModelSwitcher.vue'
import ExternalAPIConfig from '@/components/extension/ExternalAPIConfig.vue'
import http from '@/utils/http'

const loading = ref(false)
const plugins = ref<any[]>([])
const showConfig = ref(false)
const configPlugin = ref<any>(null)
const activeTab = ref('model')
const selectedModel = ref('')

async function loadPlugins() {
  loading.value = true
  try {
    const { data } = await http.get('/api/ai-plugins')
    plugins.value = (data.data ?? data ?? []).map((p: any) => ({ ...p, _toggling: false }))
  } catch { plugins.value = [] }
  finally { loading.value = false }
}

function openConfig(plugin: any) {
  configPlugin.value = plugin
  showConfig.value = true
}

function onModelChange(model: string) {
  ElMessage.success(`已切换到模型: ${model}`)
}

onMounted(loadPlugins)
</script>

<style scoped>
.gt-plugin-mgmt { padding: var(--gt-space-4); }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-tab-content { padding: var(--gt-space-3) 0; }
</style>
