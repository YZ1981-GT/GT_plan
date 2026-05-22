import type { Meta, StoryObj } from '@storybook/vue3'
import ProcedureTrimmingPanel from '@/components/workpaper/ProcedureTrimmingPanel.vue'

const meta = {
  title: 'Business/ProcedureTrimmingPanel',
  component: ProcedureTrimmingPanel,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: '程序适用性裁剪主面板：统计摘要 + 程序行列表 + 标记N/A + 恢复操作',
      },
    },
  },
} satisfies Meta<typeof ProcedureTrimmingPanel>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectId: 'proj-001',
    wpId: 'wp-001',
    sheetKey: 'd2a',
  },
}

export const DifferentCycle: Story = {
  args: {
    projectId: 'proj-001',
    wpId: 'wp-003',
    sheetKey: 'f2a',
  },
}
