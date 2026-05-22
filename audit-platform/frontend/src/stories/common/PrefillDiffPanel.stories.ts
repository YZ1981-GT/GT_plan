import type { Meta, StoryObj } from '@storybook/vue3'
import PrefillDiffPanel from '@/components/workpaper/PrefillDiffPanel.vue'

const meta = {
  title: 'Common/PrefillDiffPanel',
  component: PrefillDiffPanel,
  tags: ['autodocs'],
} satisfies Meta<typeof PrefillDiffPanel>

export default meta
type Story = StoryObj<typeof meta>

const sampleChanges = [
  { sheet: '审定表D2-1', cell_ref: 'E5', formula: '=TB("6001","期末余额")', old_value: 1200000, new_value: 1350000, change_pct: 12.5, is_highlight: false },
  { sheet: '审定表D2-1', cell_ref: 'E8', formula: '=TB("6051","期末余额")', old_value: 500000, new_value: 680000, change_pct: 36.0, is_highlight: true },
  { sheet: '明细表D2-2', cell_ref: 'C3', formula: '=AUX("6001","客户","A公司","期末余额")', old_value: null, new_value: 250000, change_pct: null, is_highlight: false },
]

export const Default: Story = {
  args: {
    visible: true,
    changes: sampleChanges,
    summary: { total_changes: 3, new_cells: 1, modified_cells: 2, highlight_count: 1 },
  },
}

export const NoHighlights: Story = {
  args: {
    visible: true,
    changes: [
      { sheet: '审定表F2-1', cell_ref: 'D4', formula: '=TB("1403","期末余额")', old_value: 800000, new_value: 820000, change_pct: 2.5, is_highlight: false },
    ],
    summary: { total_changes: 1, new_cells: 0, modified_cells: 1, highlight_count: 0 },
  },
}
