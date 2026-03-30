// Common
export interface GuildsMap {
  [guildId: string]: string
}
export interface ChannelsMap {
  [guildId: string]: { id: string; name: string }[]
}
export interface RolesMap {
  [guildId: string]: { id: string; name: string; color: number }[]
}

// Lobbies
export interface Lobby {
  id: number
  guild_id: string
  lobby_channel_id: string
  default_user_limit: number
  default_bitrate: number | null
}

// Sticky
export interface StickyMessage {
  id: number
  guild_id: string
  channel_id: string
  message_type: string
  title: string
  description: string
  color: number | null
  cooldown_seconds: number
}

// Bump
export interface BumpConfig {
  guild_id: string
  channel_id: string
  service_name: string
}
export interface BumpReminder {
  id: number
  guild_id: string
  channel_id: string
  service_name: string
  enabled: boolean
}

// JoinRole
export interface JoinRoleConfig {
  id: number
  guild_id: string
  role_id: string
  duration_hours: number
  enabled: boolean
}

// EventLog
export interface EventLogConfig {
  id: number
  guild_id: string
  event_type: string
  channel_id: string
  enabled: boolean
}

// Activity
export interface ActivitySettings {
  activity_type: string
  activity_text: string
}

// Health
export interface HealthConfig {
  id: number
  guild_id: string
  channel_id: string
  interval_seconds: number
  enabled: boolean
}

// AutoMod
export interface AutoModRule {
  id: number
  guild_id: string
  rule_type: string
  action: string
  pattern: string | null
  use_wildcard: boolean
  threshold_seconds: number | null
  timeout_duration_seconds: number | null
  required_channel_id: string | null
  is_enabled: boolean
  created_at: string
}
export interface AutoModLog {
  id: number
  guild_id: string
  user_id: string
  username: string
  action_taken: string
  reason: string
  rule_id: number
  created_at: string
}
export interface AutoModConfig {
  log_channel_id: string | null
  intro_check_messages: number
}
export interface AutoModBanListEntry {
  id: number
  guild_id: string
  user_id: string
  reason: string | null
  created_at: string
}
export interface BanLog {
  id: number
  guild_id: string
  user_id: string
  username: string
  reason: string | null
  is_automod: boolean
  created_at: string
}

// Role Panel
export interface RolePanel {
  id: number
  guild_id: string
  channel_id: string
  message_id: string | null
  panel_type: string
  title: string
  description: string | null
  color: number | null
  remove_reaction: boolean
  excluded_role_ids: string[]
  item_count: number
}
export interface RolePanelItem {
  id: number
  role_id: string
  emoji: string
  label: string | null
  style: string | null
  position: number
}
export interface RolePanelDetail extends RolePanel {
  items: RolePanelItem[]
}

// Ticket
export interface Ticket {
  id: number
  guild_id: string
  channel_id: string | null
  ticket_number: number
  user_id: string
  username: string
  status: string
  claimed_by: string | null
  closed_by: string | null
  created_at: string
  closed_at: string | null
}
export interface TicketDetail extends Ticket {
  transcript: string | null
}
export interface TicketCategory {
  id: number
  guild_id: string
  name: string
  description: string | null
}
export interface TicketPanel {
  id: number
  guild_id: string
  channel_id: string
  message_id: string | null
  title: string
  description: string | null
  color: number | null
  staff_role_id: string | null
  discord_category_id: string | null
  log_channel_id: string | null
}
export interface TicketPanelDetail extends TicketPanel {
  categories: TicketPanelCategory[]
}
export interface TicketPanelCategory {
  assoc_id: number
  category_id: number
  category_name: string
  button_emoji: string | null
  button_label: string | null
  button_style: string | null
}
