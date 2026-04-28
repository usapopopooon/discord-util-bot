'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE } from '@/lib/constants'
import type { ChatRoleConfig, GuildsMap, ChannelsMap, RolesMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DataTable, type Column } from '@/components/data-table'
import { DeleteButton } from '@/components/delete-button'
import { ToggleButton } from '@/components/toggle-button'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? []
  const ch = list.find((c) => c.id === channelId)
  return ch ? `#${ch.name}` : channelId
}

function resolveRoleName(roles: RolesMap, guildId: string, roleId: string) {
  const list = roles[guildId] ?? []
  const role = list.find((r) => r.id === roleId)
  return role ? `@${role.name}` : roleId
}

export default function ChatRolePage() {
  const router = useRouter()
  const [configs, setConfigs] = useState<ChatRoleConfig[]>([])
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [roles, setRoles] = useState<RolesMap>({})
  const [loading, setLoading] = useState(true)

  // Form state
  const [selectedGuild, setSelectedGuild] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [selectedRole, setSelectedRole] = useState('')
  const [threshold, setThreshold] = useState('10')
  const [durationHours, setDurationHours] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function fetchData() {
    const res = await fetch(`${API_BASE}/chatrole`).then((r) => r.json())
    setConfigs(res?.configs ?? [])
    setGuilds(res?.guilds ?? {})
    setChannels(res?.channels ?? {})
    setRoles(res?.roles ?? {})
    setLoading(false)
  }

  useEffect(() => {
    fetchData()
  }, [])

  const filteredChannels = selectedGuild ? (channels[selectedGuild] ?? []) : []
  const filteredRoles = selectedGuild ? (roles[selectedGuild] ?? []) : []

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !selectedChannel || !selectedRole || !threshold) return
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        guild_id: selectedGuild,
        channel_id: selectedChannel,
        role_id: selectedRole,
        threshold: parseInt(threshold, 10),
      }
      if (durationHours.trim()) {
        body.duration_hours = parseInt(durationHours, 10)
      }
      await fetch(`${API_BASE}/chatrole`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setSelectedGuild('')
      setSelectedChannel('')
      setSelectedRole('')
      setThreshold('10')
      setDurationHours('')
      fetchData()
      router.refresh()
    } finally {
      setSubmitting(false)
    }
  }

  const columns: Column<ChatRoleConfig>[] = [
    {
      header: 'Server',
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: 'Channel',
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: 'Role',
      accessor: (row) => resolveRoleName(roles, row.guild_id, row.role_id),
    },
    {
      header: 'Threshold',
      accessor: (row) => row.threshold,
    },
    {
      header: 'Duration',
      accessor: (row) => (row.duration_hours !== null ? `${row.duration_hours}h` : '—'),
    },
    {
      header: 'Status',
      accessor: (row) => (
        <Badge
          variant={row.enabled ? 'default' : 'secondary'}
          className={row.enabled ? 'bg-green-600 hover:bg-green-600' : ''}
        >
          {row.enabled ? 'Enabled' : 'Disabled'}
        </Badge>
      ),
    },
    {
      header: 'Actions',
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <ToggleButton endpoint={`${API_BASE}/chatrole/${row.id}/toggle`} enabled={row.enabled} />
          <DeleteButton endpoint={`${API_BASE}/chatrole/${row.id}/delete`} />
        </div>
      ),
    },
  ]

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Chat Roles</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Chat Roles</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add Chat Role</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v)
                  setSelectedChannel('')
                  setSelectedRole('')
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select server" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(guilds).map(([id, name]) => (
                    <SelectItem key={id} value={id}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Channel</label>
              <Select
                value={selectedChannel}
                onValueChange={setSelectedChannel}
                disabled={!selectedGuild}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select channel" />
                </SelectTrigger>
                <SelectContent>
                  {filteredChannels.map((ch) => (
                    <SelectItem key={ch.id} value={ch.id}>
                      #{ch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Role</label>
              <Select
                value={selectedRole}
                onValueChange={setSelectedRole}
                disabled={!selectedGuild}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  {filteredRoles.map((role) => (
                    <SelectItem key={role.id} value={role.id}>
                      {role.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Threshold (messages)</label>
              <Input
                type="number"
                min={1}
                max={10000}
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Duration (hours, blank = permanent)
              </label>
              <Input
                type="number"
                min={1}
                max={8760}
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={
                  submitting || !selectedGuild || !selectedChannel || !selectedRole || !threshold
                }
              >
                {submitting ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Chat Roles</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={configs} emptyMessage="No chat roles configured" />
        </CardContent>
      </Card>
    </div>
  )
}
