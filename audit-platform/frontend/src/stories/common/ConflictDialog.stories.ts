import type { Meta, StoryObj } from '@storybook/vue3'
import ConflictDialog from '@/components/ConflictDialog.vue'

const meta = {
  title: 'Common/ConflictDialog',
  component: ConflictDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof ConflictDialog>

export default meta
type Story = StoryObj<typeof meta>

export const LockConflict: Story = {
  args: {
    visible: true,
    conflictType: 'lock',
    lockHolder: '张经理',
  },
}

export const VersionConflict: Story = {
  args: {
    visible: true,
    conflictType: 'version',
  },
}
