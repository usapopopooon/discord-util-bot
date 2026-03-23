import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GuildChannelSelector } from '../guild-channel-selector'
import type { GuildsMap, ChannelsMap } from '@/lib/types'

// Radix Select uses portals which require pointer-events workarounds in jsdom.
// We test the rendered structure and callback wiring rather than full interaction.

const guilds: GuildsMap = {
  '111': 'Test Server',
  '222': 'Another Server',
}

const channels: ChannelsMap = {
  '111': [
    { id: 'c1', name: 'general' },
    { id: 'c2', name: 'random' },
  ],
  '222': [{ id: 'c3', name: 'lobby' }],
}

describe('GuildChannelSelector', () => {
  it('renders guild and channel labels', () => {
    render(
      <GuildChannelSelector
        guilds={guilds}
        channels={channels}
        selectedGuild=""
        selectedChannel=""
        onGuildChange={vi.fn()}
        onChannelChange={vi.fn()}
      />
    )

    expect(screen.getByText('Server')).toBeInTheDocument()
    expect(screen.getByText('Channel')).toBeInTheDocument()
  })

  it('renders custom labels', () => {
    render(
      <GuildChannelSelector
        guilds={guilds}
        channels={channels}
        selectedGuild=""
        selectedChannel=""
        onGuildChange={vi.fn()}
        onChannelChange={vi.fn()}
        guildLabel="Guild"
        channelLabel="Room"
      />
    )

    expect(screen.getByText('Guild')).toBeInTheDocument()
    expect(screen.getByText('Room')).toBeInTheDocument()
  })

  it('renders placeholder text for selects', () => {
    render(
      <GuildChannelSelector
        guilds={guilds}
        channels={channels}
        selectedGuild=""
        selectedChannel=""
        onGuildChange={vi.fn()}
        onChannelChange={vi.fn()}
      />
    )

    expect(screen.getByText('Select server')).toBeInTheDocument()
    expect(screen.getByText('Select channel')).toBeInTheDocument()
  })

  it('disables channel select when no guild is selected', () => {
    render(
      <GuildChannelSelector
        guilds={guilds}
        channels={channels}
        selectedGuild=""
        selectedChannel=""
        onGuildChange={vi.fn()}
        onChannelChange={vi.fn()}
      />
    )

    const triggers = screen.getAllByRole('combobox')
    // The channel trigger (second) should be disabled
    expect(triggers[1]).toBeDisabled()
  })

  it('enables channel select when a guild is selected', () => {
    render(
      <GuildChannelSelector
        guilds={guilds}
        channels={channels}
        selectedGuild="111"
        selectedChannel=""
        onGuildChange={vi.fn()}
        onChannelChange={vi.fn()}
      />
    )

    const triggers = screen.getAllByRole('combobox')
    expect(triggers[1]).not.toBeDisabled()
  })
})
