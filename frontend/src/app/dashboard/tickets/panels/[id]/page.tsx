'use client'

import { useEffect, useState, use } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { API_BASE } from '@/lib/constants'
import type { TicketPanelDetail, GuildsMap, ChannelsMap, RolesMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DeleteButton } from '@/components/delete-button'

const BUTTON_STYLES = [
  { value: 'primary', label: 'Primary (Blue)' },
  { value: 'secondary', label: 'Secondary (Gray)' },
  { value: 'success', label: 'Success (Green)' },
  { value: 'danger', label: 'Danger (Red)' },
]

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string | null) {
  if (!channelId) return '-'
  const list = channels[guildId] ?? []
  const ch = list.find((c) => c.id === channelId)
  return ch ? `#${ch.name}` : channelId
}

export default function TicketPanelDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  const [panel, setPanel] = useState<TicketPanelDetail | null>(null)
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [roles, setRoles] = useState<RolesMap>({})
  const [discordCategories, setDiscordCategories] = useState<ChannelsMap>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [posting, setPosting] = useState(false)

  // Edit form state
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('')
  const [staffRoleId, setStaffRoleId] = useState('')
  const [discordCategoryId, setDiscordCategoryId] = useState('')
  const [logChannelId, setLogChannelId] = useState('')

  // Button edit state per assoc_id
  const [buttonEdits, setButtonEdits] = useState<
    Record<number, { emoji: string; label: string; style: string; saving: boolean }>
  >({})

  async function fetchData() {
    const [panelRes, formDataRes] = await Promise.all([
      fetch(`${API_BASE}/tickets/panels/${id}`).then((r) => r.json()),
      fetch(`${API_BASE}/tickets/panels/form-data`)
        .then((r) => r.json())
        .catch(() => null),
    ])
    const p = panelRes?.panel as TicketPanelDetail | null
    setPanel(p)
    setGuilds(panelRes?.guilds ?? {})
    setChannels(panelRes?.channels ?? {})
    setRoles(formDataRes?.roles ?? {})
    setDiscordCategories(formDataRes?.discord_categories ?? {})

    if (p) {
      setTitle(p.title)
      setDescription(p.description ?? '')
      setColor(p.color ? `#${p.color.toString(16).padStart(6, '0')}` : '')
      setStaffRoleId(p.staff_role_id ?? '')
      setDiscordCategoryId(p.discord_category_id ?? '')
      setLogChannelId(p.log_channel_id ?? '')

      const edits: typeof buttonEdits = {}
      for (const cat of p.categories) {
        edits[cat.assoc_id] = {
          emoji: cat.button_emoji ?? '',
          label: cat.button_label ?? '',
          style: cat.button_style ?? 'primary',
          saving: false,
        }
      }
      setButtonEdits(edits)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Ticket Panel Detail</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  if (!panel) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Panel Not Found</h1>
        <Link href="/dashboard/tickets/panels">
          <Button variant="outline">Back to Panels</Button>
        </Link>
      </div>
    )
  }

  const filteredChannels = channels[panel.guild_id] ?? []
  const filteredRoles = roles[panel.guild_id] ?? []
  const filteredDiscordCategories = discordCategories[panel.guild_id] ?? []

  async function handleSave(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        title,
        description: description || null,
        color: color ? parseInt(color.replace('#', ''), 16) : null,
        staff_role_id: staffRoleId || null,
        discord_category_id: discordCategoryId || null,
        log_channel_id: logChannelId || null,
      }
      await fetch(`${API_BASE}/tickets/panels/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      router.refresh()
    } finally {
      setSubmitting(false)
    }
  }

  async function handlePost() {
    setPosting(true)
    try {
      await fetch(`${API_BASE}/tickets/panels/${id}/post`, {
        method: 'POST',
      })
      await fetchData()
    } finally {
      setPosting(false)
    }
  }

  async function handleButtonSave(assocId: number) {
    const edit = buttonEdits[assocId]
    if (!edit) return
    setButtonEdits((prev) => ({
      ...prev,
      [assocId]: { ...prev[assocId], saving: true },
    }))
    try {
      await fetch(`${API_BASE}/tickets/panels/${id}/buttons/${assocId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          button_emoji: edit.emoji || null,
          button_label: edit.label || null,
          button_style: edit.style || null,
        }),
      })
    } finally {
      setButtonEdits((prev) => ({
        ...prev,
        [assocId]: { ...prev[assocId], saving: false },
      }))
    }
  }

  function updateButtonEdit(assocId: number, field: 'emoji' | 'label' | 'style', value: string) {
    setButtonEdits((prev) => ({
      ...prev,
      [assocId]: { ...prev[assocId], [field]: value },
    }))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/tickets/panels">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Panel: {panel.title}</h1>
        <Badge
          className={
            panel.message_id ? 'bg-green-600 hover:bg-green-600' : 'bg-gray-500 hover:bg-gray-500'
          }
        >
          {panel.message_id ? 'Posted' : 'Not Posted'}
        </Badge>
      </div>

      {/* Panel Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>Panel Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-4 text-sm text-muted-foreground">
            Server: {resolveGuildName(guilds, panel.guild_id)} | Channel:{' '}
            {resolveChannelName(channels, panel.guild_id, panel.channel_id)}
          </div>

          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Title</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
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
              <Select value={staffRoleId} onValueChange={setStaffRoleId}>
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
              <Select value={discordCategoryId} onValueChange={setDiscordCategoryId}>
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
              <Select value={logChannelId} onValueChange={setLogChannelId}>
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

            <Button type="submit" disabled={submitting || !title}>
              {submitting ? 'Saving...' : 'Save Changes'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Category Buttons */}
      {panel.categories.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Category Buttons</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {panel.categories.map((cat) => {
                const edit = buttonEdits[cat.assoc_id]
                if (!edit) return null
                return (
                  <div key={cat.assoc_id} className="rounded-md border p-4 space-y-3">
                    <div className="font-medium">{cat.category_name}</div>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="text-sm font-medium mb-1 block">Emoji</label>
                        <Input
                          value={edit.emoji}
                          onChange={(e) => updateButtonEdit(cat.assoc_id, 'emoji', e.target.value)}
                          placeholder="e.g. ticket emoji"
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium mb-1 block">Label</label>
                        <Input
                          value={edit.label}
                          onChange={(e) => updateButtonEdit(cat.assoc_id, 'label', e.target.value)}
                          placeholder="Button label"
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium mb-1 block">Style</label>
                        <Select
                          value={edit.style}
                          onValueChange={(v) => updateButtonEdit(cat.assoc_id, 'style', v)}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {BUTTON_STYLES.map((s) => (
                              <SelectItem key={s.value} value={s.value}>
                                {s.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleButtonSave(cat.assoc_id)}
                      disabled={edit.saving}
                    >
                      {edit.saving ? 'Saving...' : 'Save Button'}
                    </Button>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Button onClick={handlePost} disabled={posting}>
              {posting ? 'Posting...' : panel.message_id ? 'Update in Discord' : 'Post to Discord'}
            </Button>
            <DeleteButton
              endpoint={`${API_BASE}/tickets/panels/${id}/delete`}
              label="Delete Panel"
              confirmMessage="Are you sure you want to delete this panel? This action cannot be undone."
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
