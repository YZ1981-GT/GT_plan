<template>
  <div class="gt-plugin-mgmt">
    <div class="gt-page-header">
      <h2 class="gt-page-title">AI插件管理</h2>
      <el-button size="small" @click="loadPlugins" :loading="loading">刷新</el-button>
    </div>

    <PluginList :plugins="plugins" :loading="loading" :is-stub="isStubPlugin" @config="openConfig" @toggled="loadPlugins" @execute="executePlugin" />

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
import { listAIPlugins } from '@/services/commonApi'

const loading = ref(false)
const plugins = ref<any[]>([])
const showConfig = ref(false)
const configPlugin = ref<any>(null)
const activeTab = ref('model')
const selectedModel = ref('')

const STUB_PLUGIN_IDS = [
  'invoice_verify', 'business_info', 'bank_reconcile', 'seal_check',
  'voice_note', 'wp_review', 'continuous_audit', 'team_chat'
]
function isStubPlugin(id: string) { return STUB_PLUGIN_IDS.includes(id) }

async function loadPlugins() {
  loading.value = true
  try {
    plugins.value = (await listAIPlugins()).map((p: any) => ({ ...p, _toggling: false }))
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

function executePlugin(plugin: any) {
  if (isStubPlugin(plugin.plugin_id)) return
  ElMessage.info(`正在执行插件: ${plugin.plugin_name}`)
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
