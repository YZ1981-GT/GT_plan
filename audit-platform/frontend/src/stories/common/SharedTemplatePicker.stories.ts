import type { Meta, StoryObj } from '@storybook/vue3'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'

const meta = {
  title: 'Common/SharedTemplatePicker',
  component: SharedTemplatePicker,
  tags: ['autodocs'],
} satisfies Meta<typeof SharedTemplatePicker>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    configType: 'report_mapping',
    projectId: 'proj-001',
    projectName: '示例集团 2025 年度审计',
    getConfigData: () => ({ mappings: [] }),
  },
}

export const FormulaConfig: Story = {
  args: {
    configType: 'formula_config',
    projectId: 'proj-002',
    projectName: 'XX 科技有限公司',
    getConfigData: () => ({ formulas: [], version: 1 }),
  },
}
