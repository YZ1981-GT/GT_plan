import type { Meta, StoryObj } from '@storybook/vue3'
import CycleProgressRing from '@/components/dashboard/CycleProgressRing.vue'
import type { CycleProgressItem } from '@/composables/useDashboardData'

const meta = {
  title: 'Business/CycleProgressRing',
  component: CycleProgressRing,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: '循环进度环形图网格：按循环显示完成率（<50% 红 / 50-99% 橙 / 100% 绿）',
      },
    },
  },
} satisfies Meta<typeof CycleProgressRing>

export default meta
type Story = StoryObj<typeof meta>

const sampleProgress: CycleProgressItem[] = [
  { cycle: 'D', cycle_name: '销售收入', total_procedures: 20, completed_procedures: 20, trimmed_procedures: 2, progress_rate: 100 },
  { cycle: 'E', cycle_name: '货币资金', total_procedures: 15, completed_procedures: 12, trimmed_procedures: 1, progress_rate: 80 },
  { cycle: 'F', cycle_name: '采购存货', total_procedures: 25, completed_procedures: 18, trimmed_procedures: 3, progress_rate: 72 },
  { cycle: 'G', cycle_name: '投资', total_procedures: 18, completed_procedures: 9, trimmed_procedures: 0, progress_rate: 50 },
  { cycle: 'H', cycle_name: '固定资产', total_procedures: 22, completed_procedures: 6, trimmed_procedures: 1, progress_rate: 27 },
  { cycle: 'I', cycle_name: '无形资产', total_procedures: 12, completed_procedures: 12, trimmed_procedures: 0, progress_rate: 100 },
  { cycle: 'J', cycle_name: '职工薪酬', total_procedures: 10, completed_procedures: 8, trimmed_procedures: 0, progress_rate: 80 },
  { cycle: 'K', cycle_name: '管理费用', total_procedures: 14, completed_procedures: 5, trimmed_procedures: 2, progress_rate: 36 },
]

export const Default: Story = {
  args: {
    cycleProgress: sampleProgress,
  },
}

export const AllComplete: Story = {
  args: {
    cycleProgress: sampleProgress.map(item => ({
      ...item,
      completed_procedures: item.total_procedures,
      progress_rate: 100,
    })),
  },
}

export const EarlyStage: Story = {
  args: {
    cycleProgress: sampleProgress.map(item => ({
      ...item,
      completed_procedures: Math.round(item.total_procedures * 0.2),
      progress_rate: 20,
    })),
  },
}
