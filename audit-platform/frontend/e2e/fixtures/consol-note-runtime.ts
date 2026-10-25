import { createApp, defineComponent, h, onMounted, ref } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '../../src/styles/global.css'
import ConsolNoteTab from '../../src/components/consolidation/ConsolNoteTab.vue'

const Host = defineComponent({
  setup() {
    const standard = ref('soe')
    const note = ref<InstanceType<typeof ConsolNoteTab> | null>(null)
    const snapshot = () => ({
      variant: standard.value, context: note.value?.loadedNoteContext || null,
      dirty: note.value?.noteDirty || false, sectionId: note.value?.selectedNoteSection?.section_id || null,
    })
    ;(window as any).__cp04NoteFixture = { snapshot, save: () => note.value?.saveNoteData() }
    onMounted(() => { void note.value?.onNoteNodeClick({ section_id: '五-5-2' }) })
    return () => h('main', { style: 'padding:16px;background:#fff;min-height:100vh' }, [
      h('div', { style: 'display:flex;gap:8px;margin-bottom:12px' }, [
        h('button', { 'data-testid': 'fixture-soe', onClick: () => { standard.value = 'soe' } }, '国企'),
        h('button', { 'data-testid': 'fixture-listed', onClick: () => { standard.value = 'listed' } }, '上市'),
      ]),
      h(ConsolNoteTab, {
        ref: note, projectId: 'cp04-offline-project', year: 2025, standard: standard.value,
        currentEntity: { nodeKey: 'G:consol', code: 'G', name: '合成集团' }, groupTree: [], consolNoteTree: [],
        'onRestore-note-context': (context: { variant: string }) => { standard.value = context.variant },
      }),
    ])
  },
})
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:pathMatch(.*)*', component: defineComponent({ render: () => null }) }],
})
// The synthetic route installer must run before this page can mount any API consumer.
if ((window as any).__CP04_SYNTHETIC_ROUTES__ === true) {
  createApp(Host).use(createPinia()).use(router).use(ElementPlus).mount('#app')
} else {
  document.querySelector('#app')!.textContent = '请通过隔离测试配置打开本页'
}
