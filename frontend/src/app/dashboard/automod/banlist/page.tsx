"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { AutoModBanListEntry, GuildsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";
import Link from "next/link";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

export default function AutoModBanListPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<AutoModBanListEntry[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [loading, setLoading] = useState(true);

  // Form state
  const [selectedGuild, setSelectedGuild] = useState("");
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    const [entriesRes, guildsRes] = await Promise.all([
      fetch("/api/v1/automod/banlist").then((r) => r.json()),
      fetch("/api/v1/guilds").then((r) => r.json()),
    ]);
    setEntries(entriesRes ?? []);
    setGuilds(guildsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedGuild || !userId) return;
    setSubmitting(true);
    try {
      await fetch("/api/v1/automod/banlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: selectedGuild,
          user_id: userId,
          reason: reason || null,
        }),
      });
      setSelectedGuild("");
      setUserId("");
      setReason("");
      fetchData();
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<AutoModBanListEntry>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "User ID",
      accessor: (row) => (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.user_id}</code>
      ),
    },
    {
      header: "Reason",
      accessor: (row) => row.reason ?? "-",
    },
    {
      header: "Created",
      accessor: (row) => new Date(row.created_at).toLocaleString(),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <DeleteButton endpoint={`/api/v1/automod/banlist/${row.id}/delete`} />
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">AutoMod Ban List</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/automod">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">AutoMod Ban List</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add to Ban List</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select value={selectedGuild} onValueChange={setSelectedGuild}>
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
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">User ID</label>
              <Input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="e.g. 123456789012345678"
                pattern="[0-9]*"
              />
            </div>
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Reason (optional)</label>
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for ban"
              />
            </div>
            <Button type="submit" disabled={submitting || !selectedGuild || !userId}>
              {submitting ? "Adding..." : "Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ban List Entries</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={entries} emptyMessage="No ban list entries" />
        </CardContent>
      </Card>
    </div>
  );
}
