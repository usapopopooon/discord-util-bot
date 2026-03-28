'use client'

import { useEffect, useState } from 'react'
import { API_BASE } from '@/lib/constants'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from '@/components/ui/dialog'
import { toast } from 'sonner'

interface MaintenanceStats {
  guild_count: number
  lobbies: {
    total: number
    orphaned: number
  }
  bump_configs: {
    total: number
    orphaned: number
  }
  stickies: {
    total: number
    orphaned: number
  }
  role_panels: {
    total: number
    orphaned: number
  }
}

interface CleanupResult {
  ok: boolean
  deleted: {
    lobbies: number
    bump_configs: number
    stickies: number
    role_panels: number
  }
}

export default function MaintenancePage() {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<MaintenanceStats | null>(null)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  async function fetchStats() {
    try {
      const res = await fetch(`${API_BASE}/maintenance`)
      if (!res.ok) return
      const data: MaintenanceStats = await res.json()
      setStats(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  async function handleCleanup() {
    setCleaning(true)
    setCleanupResult(null)
    setDialogOpen(false)
    try {
      const res = await fetch(`${API_BASE}/maintenance/cleanup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      if (!res.ok) {
        const body = await res.text()
        let msg: string
        try {
          msg = JSON.parse(body).detail || body
        } catch {
          msg = body
        }
        toast.error(`Cleanup failed: ${msg}`)
        return
      }
      const result: CleanupResult = await res.json()
      setCleanupResult(result)
      toast.success('Cleanup completed successfully')
      // Refresh stats
      fetchStats()
    } catch {
      toast.error('Cleanup failed')
    } finally {
      setCleaning(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Maintenance</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  const statCards = stats
    ? [
        { label: 'Active Guilds', value: stats.guild_count },
        { label: 'Voice Lobbies', value: stats.lobbies.total },
        { label: 'Orphaned Lobbies', value: stats.lobbies.orphaned },
        { label: 'Bump Configs', value: stats.bump_configs.total },
        { label: 'Orphaned Bump Configs', value: stats.bump_configs.orphaned },
        { label: 'Sticky Messages', value: stats.stickies.total },
        { label: 'Orphaned Stickies', value: stats.stickies.orphaned },
        { label: 'Role Panels', value: stats.role_panels.total },
        { label: 'Orphaned Role Panels', value: stats.role_panels.orphaned },
      ]
    : []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Maintenance</h1>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {statCards.map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Cleanup Action */}
      <Card>
        <CardHeader>
          <CardTitle>Database Cleanup</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Run cleanup to remove orphaned channels, expired join role assignments, and stale voice
            sessions.
          </p>

          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="destructive" disabled={cleaning}>
                {cleaning ? 'Running Cleanup...' : 'Run Cleanup'}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Confirm Cleanup</DialogTitle>
                <DialogDescription>
                  This will remove orphaned channels, expired assignments, and stale sessions from
                  the database. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button variant="destructive" onClick={handleCleanup}>
                  Confirm Cleanup
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Cleanup Results */}
          {cleanupResult && (
            <Card className="border-green-500/30 bg-green-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Cleanup Results</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  <li>
                    Orphaned lobbies removed:{' '}
                    <span className="font-medium">{cleanupResult.deleted.lobbies}</span>
                  </li>
                  <li>
                    Orphaned bump configs removed:{' '}
                    <span className="font-medium">{cleanupResult.deleted.bump_configs}</span>
                  </li>
                  <li>
                    Orphaned sticky messages removed:{' '}
                    <span className="font-medium">{cleanupResult.deleted.stickies}</span>
                  </li>
                  <li>
                    Orphaned role panels removed:{' '}
                    <span className="font-medium">{cleanupResult.deleted.role_panels}</span>
                  </li>
                </ul>
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
