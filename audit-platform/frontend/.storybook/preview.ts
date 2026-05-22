import type { Preview } from '@storybook/vue3'
import { setup } from '@storybook/vue3'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'

// 全局样式
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import '../src/styles/gt-tokens.css'
import '../src/styles/global.css'

// 全局 setup：注册 Pinia + Element Plus
setup((app) => {
  app.use(createPinia())
  app.use(ElementPlus)
})

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'light',
      values: [
        { name: 'light', value: '#ffffff' },
        { name: 'dark', value: '#1a1a2e' },
        { name: 'gray', value: '#f8f9fa' },
      ],
    },
    viewport: {
      viewports: {
        desktop: { name: 'Desktop', styles: { width: '1920px', height: '1080px' } },
        laptop: { name: 'Laptop', styles: { width: '1440px', height: '900px' } },
        tablet: { name: 'Tablet', styles: { width: '1024px', height: '768px' } },
      },
      defaultViewport: 'desktop',
    },
  },
}

export default preview
