'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE } from '@/lib/constants'
import type { GuildsMap, ChannelsMap, RolesMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { GuildChannelSelector } from '@/components/guild-channel-selector'
import Link from 'next/link'

const BUTTON_STYLES = [
  { value: 'primary', label: 'Primary (Blue)' },
  { value: 'secondary', label: 'Secondary (Grey)' },
  { value: 'success', label: 'Success (Green)' },
  { value: 'danger', label: 'Danger (Red)' },
]

interface ItemForm {
  emoji: string
  role_id: string
  label: string
  style: string
}

function emptyItem(): ItemForm {
  return { emoji: '', role_id: '', label: '', style: 'primary' }
}

export default function RolePanelNewPage() {
  const router = useRouter()
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [roles, setRoles] = useState<RolesMap>({})
  const [submitting, setSubmitting] = useState(false)

  // Form state
  const [selectedGuild, setSelectedGuild] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [panelType, setPanelType] = useState('button')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('#5865F2')
  const [items, setItems] = useState<ItemForm[]>([emptyItem()])

  useEffect(() => {
    async function fetchData() {
      const res = await fetch(`${API_BASE}/rolepanels/form-data`).then((r) => r.json())
      setGuilds(res?.guilds ?? {})
      setChannels(res?.channels ?? {})
      setRoles(res?.roles ?? {})
    }
    fetchData()
  }, [])

  const filteredRoles = selectedGuild ? (roles[selectedGuild] ?? []) : []

  function updateItem(index: number, field: keyof ItemForm, value: string) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, [field]: value } : item)))
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index))
  }

  function addItem() {
    setItems((prev) => [...prev, emptyItem()])
  }

  function hexToInt(hex: string): number {
    return parseInt(hex.replace('#', ''), 16)
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !selectedChannel || !title.trim()) return
    setSubmitting(true)
    try {
      const body = {
        guild_id: selectedGuild,
        channel_id: selectedChannel,
        panel_type: panelType,
        title: title.trim(),
        description: description.trim() || null,
        color: color ? hexToInt(color) : null,
        remove_reaction: false,
        items: items
          .filter((item) => item.role_id)
          .map((item, i) => ({
            emoji: item.emoji || null,
            role_id: item.role_id,
            label: item.label || null,
            style: panelType === 'button' ? item.style : null,
            position: i,
          })),
      }

      const res = await fetch(`${API_BASE}/rolepanels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const data = await res.json()
        router.push(`/dashboard/roles/${data.id}`)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/roles">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Create Role Panel</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New Panel</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <GuildChannelSelector
              guilds={guilds}
              channels={channels}
              selectedGuild={selectedGuild}
              selectedChannel={selectedChannel}
              onGuildChange={(v) => {
                setSelectedGuild(v)
                setSelectedChannel('')
                setItems([emptyItem()])
              }}
              onChannelChange={setSelectedChannel}
            />

            <div>
              <label className="text-sm font-medium mb-1.5 block">Panel Type</label>
              <RadioGroup value={panelType} onValueChange={setPanelType} className="flex gap-4">
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="button" id="type-button" />
                  <label htmlFor="type-button" className="text-sm">
                    Button
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="reaction" id="type-reaction" />
                  <label htmlFor="type-reaction" className="text-sm">
                    Reaction
                  </label>
                </div>
              </RadioGroup>
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Title <span className="text-red-500">*</span>
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Select your roles"
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Description</label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description for the panel embed"
                rows={3}
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Embed Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="h-10 w-14 cursor-pointer rounded border border-border bg-transparent"
                />
                <Input
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  placeholder="#5865F2"
                  className="w-32"
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium mb-3 block">Items</label>
              <div className="space-y-3">
                {items.map((item, index) => (
                  <div
                    key={index}
                    className="flex items-end gap-2 rounded-md border border-border p-3"
                  >
                    <div className="w-20">
                      <label className="text-xs text-muted-foreground mb-1 block">Emoji</label>
                      <Input
                        value={item.emoji}
                        onChange={(e) => updateItem(index, 'emoji', e.target.value)}
                        placeholder="🎮"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="text-xs text-muted-foreground mb-1 block">Role</label>
                      <Select
                        value={item.role_id}
                        onValueChange={(v) => updateItem(index, 'role_id', v)}
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
                    {panelType === 'button' && (
                      <>
                        <div className="flex-1">
                          <label className="text-xs text-muted-foreground mb-1 block">Label</label>
                          <Input
                            value={item.label}
                            onChange={(e) => updateItem(index, 'label', e.target.value)}
                            placeholder="Button label"
                          />
                        </div>
                        <div className="w-40">
                          <label className="text-xs text-muted-foreground mb-1 block">Style</label>
                          <Select
                            value={item.style}
                            onValueChange={(v) => updateItem(index, 'style', v)}
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
                      </>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeItem(index)}
                      disabled={items.length <= 1}
                      className="text-red-500 hover:text-red-600"
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
              <Button type="button" variant="outline" size="sm" onClick={addItem} className="mt-2">
                + Add Item
              </Button>
            </div>

            <Button
              type="submit"
              disabled={submitting || !selectedGuild || !selectedChannel || !title.trim()}
            >
              {submitting ? 'Creating...' : 'Create Panel'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
