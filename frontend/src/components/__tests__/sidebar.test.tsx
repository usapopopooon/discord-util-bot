import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Sidebar } from '../sidebar'

const mockPathname = vi.fn().mockReturnValue('/dashboard')

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname(),
}))

const expectedNavItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/dashboard/settings', label: 'Settings' },
  { href: '/dashboard/automod', label: 'AutoMod' },
  { href: '/dashboard/banlogs', label: 'Ban Logs' },
  { href: '/dashboard/lobbies', label: 'Voice Lobbies' },
  { href: '/dashboard/sticky', label: 'Sticky Messages' },
  { href: '/dashboard/bump', label: 'Bump' },
  { href: '/dashboard/tickets', label: 'Tickets' },
  { href: '/dashboard/roles', label: 'Role Panels' },
  { href: '/dashboard/joinrole', label: 'Join Roles' },
  { href: '/dashboard/eventlog', label: 'Event Log' },
  { href: '/dashboard/activity', label: 'Bot Activity' },
  { href: '/dashboard/health', label: 'Health Check' },
  { href: '/dashboard/maintenance', label: 'Maintenance' },
]

describe('Sidebar', () => {
  it('renders the Bot Admin heading', () => {
    render(<Sidebar />)
    expect(screen.getByText('Bot Admin')).toBeInTheDocument()
  })

  it('renders all navigation links', () => {
    render(<Sidebar />)

    for (const item of expectedNavItems) {
      expect(screen.getByText(item.label)).toBeInTheDocument()
    }
  })

  it('all links point to correct paths', () => {
    render(<Sidebar />)

    for (const item of expectedNavItems) {
      const link = screen.getByText(item.label).closest('a')
      expect(link).toHaveAttribute('href', item.href)
    }
  })

  it('highlights the Dashboard link when on /dashboard', () => {
    mockPathname.mockReturnValue('/dashboard')
    render(<Sidebar />)

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink?.className).toContain('bg-accent text-accent-foreground')
  })

  it('highlights AutoMod link when on /dashboard/automod', () => {
    mockPathname.mockReturnValue('/dashboard/automod')
    render(<Sidebar />)

    const automodLink = screen.getByText('AutoMod').closest('a')
    expect(automodLink?.className).toContain('bg-accent text-accent-foreground')
  })

  it('highlights AutoMod link when on a sub-path like /dashboard/automod/new', () => {
    mockPathname.mockReturnValue('/dashboard/automod/new')
    render(<Sidebar />)

    const automodLink = screen.getByText('AutoMod').closest('a')
    expect(automodLink?.className).toContain('bg-accent text-accent-foreground')
  })

  it('does not highlight Dashboard for sub-paths', () => {
    mockPathname.mockReturnValue('/dashboard/settings')
    render(<Sidebar />)

    const dashboardLink = screen.getByText('Dashboard').closest('a')
    // The inactive class uses hover:bg-accent but not bg-accent as a standalone class
    expect(dashboardLink?.className).toContain('text-muted-foreground')
    expect(dashboardLink?.className).not.toContain('bg-accent text-accent-foreground')
  })

  it('does not highlight unrelated links', () => {
    mockPathname.mockReturnValue('/dashboard/automod')
    render(<Sidebar />)

    const settingsLink = screen.getByText('Settings').closest('a')
    expect(settingsLink?.className).toContain('text-muted-foreground')
    expect(settingsLink?.className).not.toContain('bg-accent text-accent-foreground')
  })
})
