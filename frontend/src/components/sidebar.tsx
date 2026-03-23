'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const navItems = [
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

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center border-b border-border px-4">
        <h1 className="text-lg font-semibold">Bot Admin</h1>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href))
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
