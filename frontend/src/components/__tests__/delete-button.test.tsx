import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeleteButton } from '../delete-button'

const mockRefresh = vi.fn()
const mockPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: mockRefresh,
    push: mockPush,
    back: vi.fn(),
    forward: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}))

describe('DeleteButton', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockRefresh.mockClear()
    global.fetch = vi.fn().mockResolvedValue({ ok: true })
  })

  it('renders the delete button with default label', () => {
    render(<DeleteButton endpoint="/api/test/1" />)
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('renders the delete button with custom label', () => {
    render(<DeleteButton endpoint="/api/test/1" label="Remove" />)
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })

  it('opens confirmation dialog on click', async () => {
    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(screen.getByText('Confirm Deletion')).toBeInTheDocument()
    expect(
      screen.getByText('Are you sure you want to delete this item? This action cannot be undone.')
    ).toBeInTheDocument()
  })

  it('shows custom confirm message', async () => {
    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" confirmMessage="Really delete?" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(screen.getByText('Really delete?')).toBeInTheDocument()
  })

  it('closes dialog on cancel', async () => {
    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByText('Confirm Deletion')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => {
      expect(screen.queryByText('Confirm Deletion')).not.toBeInTheDocument()
    })
  })

  it('calls fetch with DELETE method on confirm', async () => {
    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    // Click the Delete button inside the dialog (not the trigger)
    const dialogButtons = screen.getAllByRole('button', { name: 'Delete' })
    const confirmButton = dialogButtons[dialogButtons.length - 1]
    await user.click(confirmButton)

    expect(global.fetch).toHaveBeenCalledWith('/api/test/1', {
      method: 'DELETE',
    })
  })

  it('calls router.refresh after successful delete', async () => {
    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const dialogButtons = screen.getAllByRole('button', { name: 'Delete' })
    await user.click(dialogButtons[dialogButtons.length - 1])

    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled()
    })
  })

  it("shows 'Deleting...' text while loading", async () => {
    let resolvePromise!: () => void
    global.fetch = vi.fn().mockReturnValue(
      new Promise<{ ok: boolean }>((resolve) => {
        resolvePromise = () => resolve({ ok: true })
      })
    )

    const user = userEvent.setup()
    render(<DeleteButton endpoint="/api/test/1" />)

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const dialogButtons = screen.getAllByRole('button', { name: 'Delete' })
    await user.click(dialogButtons[dialogButtons.length - 1])

    expect(screen.getByText('Deleting...')).toBeInTheDocument()

    resolvePromise()
    await waitFor(() => {
      expect(mockRefresh).toHaveBeenCalled()
    })
  })
})
