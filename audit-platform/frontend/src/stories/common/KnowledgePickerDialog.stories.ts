import type { Meta, StoryObj } from '@storybook/vue3'
import KnowledgePickerDialog from '@/components/common/KnowledgePickerDialog.vue'

const meta = {
  title: 'Common/KnowledgePickerDialog',
  component: KnowledgePickerDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof KnowledgePickerDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    visible: true,
  },
}

export const Closed: Story = {
  args: {
    visible: false,
  },
}
