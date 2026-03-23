"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import type { AutoModRule, GuildsMap, ChannelsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";
import { ToggleButton } from "@/components/toggle-button";

const RULE_TYPE_LABELS: Record<string, string> = {
  username_match: "Username Match",
  account_age: "Account Age",
  no_avatar: "No Avatar",
  role_acquired: "Role Acquired",
  vc_join: "VC Join",
  message_post: "Message Post",
  vc_without_intro: "VC Without Intro",
  msg_without_intro: "Message Without Intro",
};

const ACTION_LABELS: Record<string, string> = {
  ban: "Ban",
  kick: "Kick",
  timeout: "Timeout",
};

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string | null) {
  if (!channelId) return "-";
  const list = channels[guildId] ?? [];
  const ch = list.find((c) => c.id === channelId);
  return ch ? `#${ch.name}` : channelId;
}

function formatDetails(rule: AutoModRule, channels: ChannelsMap): string {
  switch (rule.rule_type) {
    case "username_match":
      return `Pattern: ${rule.pattern ?? "-"}${rule.use_wildcard ? " (wildcard)" : ""}`;
    case "account_age":
      return rule.threshold_seconds ? `< ${Math.round(rule.threshold_seconds / 60)} min` : "-";
    case "no_avatar":
      return "-";
    case "role_acquired":
    case "vc_join":
    case "message_post":
      return rule.threshold_seconds ? `Within ${rule.threshold_seconds}s` : "-";
    case "vc_without_intro":
    case "msg_without_intro":
      return `Channel: ${resolveChannelName(channels, rule.guild_id, rule.required_channel_id)}`;
    default:
      return "-";
  }
}

export default function AutoModPage() {
  const [rules, setRules] = useState<AutoModRule[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [rulesRes, guildsRes, channelsRes] = await Promise.all([
      fetch("/api/v1/automod/rules").then((r) => r.json()),
      fetch("/api/v1/guilds").then((r) => r.json()),
      fetch("/api/v1/channels").then((r) => r.json()),
    ]);
    setRules(rulesRes ?? []);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const columns: Column<AutoModRule>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Type",
      accessor: (row) => (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          {RULE_TYPE_LABELS[row.rule_type] ?? row.rule_type}
        </code>
      ),
    },
    {
      header: "Action",
      accessor: (row) => {
        const colors: Record<string, string> = {
          ban: "bg-red-600 hover:bg-red-600",
          kick: "bg-orange-500 hover:bg-orange-500",
          timeout: "bg-yellow-500 hover:bg-yellow-500",
        };
        return (
          <Badge className={colors[row.action] ?? ""}>
            {ACTION_LABELS[row.action] ?? row.action}
          </Badge>
        );
      },
    },
    {
      header: "Details",
      accessor: (row) => formatDetails(row, channels),
    },
    {
      header: "Status",
      accessor: (row) => (
        <Badge
          variant={row.is_enabled ? "default" : "secondary"}
          className={row.is_enabled ? "bg-green-600 hover:bg-green-600" : ""}
        >
          {row.is_enabled ? "Enabled" : "Disabled"}
        </Badge>
      ),
    },
    {
      header: "Created",
      accessor: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <ToggleButton
            endpoint={`/api/v1/automod/rules/${row.id}/toggle`}
            enabled={row.is_enabled}
          />
          <Link href={`/dashboard/automod/${row.id}/edit`}>
            <Button variant="outline" size="sm">
              Edit
            </Button>
          </Link>
          <DeleteButton endpoint={`/api/v1/automod/rules/${row.id}/delete`} />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">AutoMod Rules</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">AutoMod Rules</h1>
        <div className="flex gap-2">
          <Link href="/dashboard/automod/new">
            <Button>+ Create Rule</Button>
          </Link>
          <Link href="/dashboard/automod/logs">
            <Button variant="outline">Logs</Button>
          </Link>
          <Link href="/dashboard/automod/banlist">
            <Button variant="outline">Ban List</Button>
          </Link>
          <Link href="/dashboard/automod/settings">
            <Button variant="outline">Settings</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configured Rules</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={rules} emptyMessage="No AutoMod rules configured" />
        </CardContent>
      </Card>
    </div>
  );
}
