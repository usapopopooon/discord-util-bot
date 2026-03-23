'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { API_BASE } from '@/lib/constants'
import type { GuildsMap, ChannelsMap, RolesMap, TicketCategory } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface FormData {
  guilds: GuildsMap
  channels: ChannelsMap
  roles: RolesMap
  discord_categories: ChannelsMap
  categories: TicketCategory[]
}

export default function TicketPanelNewPage() {
  const router = useRouter()
  const [formData, setFormData] = useState<FormData | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  // Form state
  const [selectedGuild, setSelectedGuild] = useState('')
  const [channelId, setChannelId] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('')
  const [staffRoleId, setStaffRoleId] = useState('')
  const [discordCategoryId, setDiscordCategoryId] = useState('')
  const [logChannelId, setLogChannelId] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<number[]>([])

  useEffect(() => {
    async function fetchData() {
      const res = await fetch(`${API_BASE}/tickets/panels/form-data`).then((r) => r.json())
      setFormData(res ?? null)
      setLoading(false)
    }
    fetchData()
  }, [])

  if (loading || !formData) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Create Ticket Panel</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  const filteredChannels = selectedGuild ? (formData.channels[selectedGuild] ?? []) : []
  const filteredRoles = selectedGuild ? (formData.roles[selectedGuild] ?? []) : []
  const filteredDiscordCategories = selectedGuild
    ? (formData.discord_categories[selectedGuild] ?? [])
    : []
  const filteredCategories = selectedGuild
    ? formData.categories.filter((c) => c.guild_id === selectedGuild)
    : []

  function handleCategoryToggle(categoryId: number, checked: boolean) {
    setSelectedCategories((prev) =>
      checked ? [...prev, categoryId] : prev.filter((id) => id !== categoryId)
    )
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !channelId || !title) return
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        guild_id: selectedGuild,
        channel_id: channelId,
        title,
        description: description || null,
        color: color ? parseInt(color.replace('#', ''), 16) : null,
        staff_role_id: staffRoleId || null,
        discord_category_id: discordCategoryId || null,
        log_channel_id: logChannelId || null,
        category_ids: selectedCategories,
      }

      const res = await fetch(`${API_BASE}/tickets/panels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (data?.id) {
        router.push(`/dashboard/tickets/panels/${data.id}`)
      } else {
        router.push('/dashboard/tickets/panels')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/tickets/panels">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Create Ticket Panel</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New Panel</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v)
                  setChannelId('')
                  setStaffRoleId('')
                  setDiscordCategoryId('')
                  setLogChannelId('')
                  setSelectedCategories([])
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select server" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(formData.guilds).map(([id, name]) => (
                    <SelectItem key={id} value={id}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Channel</label>
              <Select value={channelId} onValueChange={setChannelId} disabled={!selectedGuild}>
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
              <label className="text-sm font-medium mb-1.5 block">Title</label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Support Tickets"
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Description</label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Panel description (optional)"
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Color (hex)</label>
              <Input
                type="color"
                value={color || '#000000'}
                onChange={(e) => setColor(e.target.value)}
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Staff Role</label>
              <Select value={staffRoleId} onValueChange={setStaffRoleId} disabled={!selectedGuild}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select staff role (optional)" />
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
              <label className="text-sm font-medium mb-1.5 block">Discord Category</label>
              <Select
                value={discordCategoryId}
                onValueChange={setDiscordCategoryId}
                disabled={!selectedGuild}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select category (optional)" />
                </SelectTrigger>
                <SelectContent>
                  {filteredDiscordCategories.map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Log Channel</label>
              <Select
                value={logChannelId}
                onValueChange={setLogChannelId}
                disabled={!selectedGuild}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select log channel (optional)" />
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

            {filteredCategories.length > 0 && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">Ticket Categories</label>
                <div className="space-y-2 rounded-md border p-3">
                  {filteredCategories.map((cat) => (
                    <div key={cat.id} className="flex items-center gap-2">
                      <Checkbox
                        id={`cat-${cat.id}`}
                        checked={selectedCategories.includes(cat.id)}
                        onCheckedChange={(checked) =>
                          handleCategoryToggle(cat.id, checked === true)
                        }
                      />
                      <label htmlFor={`cat-${cat.id}`} className="text-sm">
                        {cat.name}
                        {cat.description && (
                          <span className="text-muted-foreground ml-2">- {cat.description}</span>
                        )}
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <Button type="submit" disabled={submitting || !selectedGuild || !channelId || !title}>
              {submitting ? 'Creating...' : 'Create Panel'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
