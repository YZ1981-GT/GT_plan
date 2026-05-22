import type { Meta, StoryObj } from '@storybook/vue3'
import GtInfoBar from '@/components/common/GtInfoBar.vue'

const meta = {
  title: 'Common/GtInfoBar',
  component: GtInfoBar,
  tags: ['autodocs'],
} satisfies Meta<typeof GtInfoBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    badges: [
      { label: '科目', value: '128 个' },
      { label: '差异', value: '3 项' },
    ],
  },
}

export const WithSelectors: Story = {
  args: {
    showUnit: true,
    showYear: true,
    unitValue: '1',
    yearValue: 2025,
    unitOptions: [
      { id: '1', name: '致同会计师事务所' },
      { id: '2', name: '示例公司' },
    ],
    yearOptionsList: [2025, 2024, 2023],
    badges: [{ label: '状态', value: '已审定' }],
  },
}

export const WithTemplate: Story = {
  args: {
    showTemplate: true,
    templateValue: 'soe',
    templateOptions: [
      { label: '国企版', value: 'soe' },
      { label: '上市版', value: 'listed' },
    ],
    badges: [],
  },
}

export const WithScope: Story = {
  args: {
    showScope: true,
    scopeLabel: '合并口径',
    badges: [{ label: '行数', value: '56 行' }],
  },
}
