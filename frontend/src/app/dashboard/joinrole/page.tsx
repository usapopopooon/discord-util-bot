"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { JoinRoleConfig, GuildsMap, RolesMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
import { ToggleButton } from "@/components/toggle-button";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

function resolveRoleName(roles: RolesMap, guildId: string, roleId: string) {
  const list = roles[guildId] ?? [];
  const role = list.find((r) => r.id === roleId);
  return role ? `@${role.name}` : roleId;
}

export default function JoinRolePage() {
  const router = useRouter();
  const [configs, setConfigs] = useState<JoinRoleConfig[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [roles, setRoles] = useState<RolesMap>({});
  const [loading, setLoading] = useState(true);

  // Form state
  const [selectedGuild, setSelectedGuild] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [durationHours, setDurationHours] = useState("24");
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    const [configsRes, guildsRes, rolesRes] = await Promise.all([
      fetch("/api/v1/joinrole").then((r) => r.json()),
      fetch("/api/v1/guilds").then((r) => r.json()),
      fetch("/api/v1/roles").then((r) => r.json()),
    ]);
    setConfigs(configsRes ?? []);
    setGuilds(guildsRes ?? {});
    setRoles(rolesRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredRoles = selectedGuild ? (roles[selectedGuild] ?? []) : [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedGuild || !selectedRole || !durationHours) return;
    setSubmitting(true);
    try {
      await fetch("/api/v1/joinrole", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: selectedGuild,
          role_id: selectedRole,
          duration_hours: parseInt(durationHours, 10),
        }),
      });
      setSelectedGuild("");
      setSelectedRole("");
      setDurationHours("24");
      fetchData();
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<JoinRoleConfig>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Role",
      accessor: (row) => resolveRoleName(roles, row.guild_id, row.role_id),
    },
    {
      header: "Duration (hours)",
      accessor: (row) => row.duration_hours,
    },
    {
      header: "Status",
      accessor: (row) => (
        <Badge
          variant={row.enabled ? "default" : "secondary"}
          className={row.enabled ? "bg-green-600 hover:bg-green-600" : ""}
        >
          {row.enabled ? "Enabled" : "Disabled"}
        </Badge>
      ),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <ToggleButton
            endpoint={`/api/v1/joinrole/${row.id}/toggle`}
            enabled={row.enabled}
          />
          <DeleteButton endpoint={`/api/v1/joinrole/${row.id}/delete`} />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Join Roles</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Join Roles</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add Join Role</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v);
                  setSelectedRole("");
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
            <div className="flex-1">
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
            <div className="w-40">
              <label className="text-sm font-medium mb-1.5 block">Duration (hours)</label>
              <Input
                type="number"
                min={1}
                max={720}
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={submitting || !selectedGuild || !selectedRole}>
              {submitting ? "Adding..." : "Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Join Roles</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={configs} emptyMessage="No join roles configured" />
        </CardContent>
      </Card>
    </div>
  );
}
