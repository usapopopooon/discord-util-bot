"use client";

import { useEffect, useState, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import type {
  RolePanelDetail,
  RolePanelItem,
  GuildsMap,
  ChannelsMap,
  RolesMap,
} from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import Link from "next/link";
import { toast } from "sonner";

const BUTTON_STYLES = [
  { value: "primary", label: "Primary (Blue)" },
  { value: "secondary", label: "Secondary (Grey)" },
  { value: "success", label: "Success (Green)" },
  { value: "danger", label: "Danger (Red)" },
];

function intToHex(n: number | null): string {
  if (n === null || n === undefined) return "#5865F2";
  return "#" + n.toString(16).padStart(6, "0");
}

function hexToInt(hex: string): number {
  return parseInt(hex.replace("#", ""), 16);
}

function resolveRoleName(
  roles: { id: string; name: string; color: number }[],
  roleId: string
): string {
  const role = roles.find((r) => r.id === roleId);
  return role ? role.name : roleId;
}

export default function RolePanelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const [panel, setPanel] = useState<RolePanelDetail | null>(null);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [roles, setRoles] = useState<RolesMap>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Edit form state
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState("#5865F2");
  const [removeReaction, setRemoveReaction] = useState(false);

  // Add item form state
  const [newEmoji, setNewEmoji] = useState("");
  const [newRoleId, setNewRoleId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newStyle, setNewStyle] = useState("primary");
  const [addingItem, setAddingItem] = useState(false);

  const fetchData = useCallback(async () => {
    const [panelRes, guildsRes, channelsRes, rolesRes] = await Promise.all([
      fetch(`/api/proxy/api/v1/rolepanels/${id}`).then((r) => r.json()),
      fetch("/api/proxy/api/v1/guilds").then((r) => r.json()),
      fetch("/api/proxy/api/v1/channels").then((r) => r.json()),
      fetch("/api/proxy/api/v1/roles").then((r) => r.json()),
    ]);
    setPanel(panelRes);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setRoles(rolesRes ?? {});

    if (panelRes) {
      setTitle(panelRes.title ?? "");
      setDescription(panelRes.description ?? "");
      setColor(intToHex(panelRes.color));
      setRemoveReaction(panelRes.remove_reaction ?? false);
    }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading || !panel) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Role Panel</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const guildName = guilds[panel.guild_id] ?? panel.guild_id;
  const channelList = channels[panel.guild_id] ?? [];
  const channelObj = channelList.find((c) => c.id === panel.channel_id);
  const channelName = channelObj ? `#${channelObj.name}` : panel.channel_id;
  const guildRoles = roles[panel.guild_id] ?? [];

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/proxy/api/v1/rolepanels/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim() || null,
          color: color ? hexToInt(color) : null,
          remove_reaction: removeReaction,
        }),
      });
      if (res.ok) {
        toast.success("Panel updated successfully");
        fetchData();
      } else {
        toast.error("Failed to update panel");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePost() {
    const res = await fetch(`/api/proxy/api/v1/rolepanels/${id}/post`, {
      method: "POST",
    });
    if (res.ok) {
      toast.success(
        panel?.message_id
          ? "Panel updated in Discord"
          : "Panel posted to Discord"
      );
      fetchData();
    } else {
      const err = await res.text();
      toast.error(`Failed to post panel: ${err}`);
    }
  }

  async function handleCopy() {
    const res = await fetch(`/api/proxy/api/v1/rolepanels/${id}/copy`, {
      method: "POST",
    });
    if (res.ok) {
      const data = await res.json();
      toast.success("Panel copied successfully");
      router.push(`/dashboard/roles/${data.id}`);
    } else {
      toast.error("Failed to copy panel");
    }
  }

  async function handleDelete() {
    setDeleteLoading(true);
    try {
      await fetch(`/api/proxy/api/v1/rolepanels/${id}`, {
        method: "DELETE",
      });
      setDeleteOpen(false);
      router.push("/dashboard/roles");
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleDeleteItem(itemId: number) {
    const res = await fetch(
      `/api/proxy/api/v1/rolepanels/${id}/items/${itemId}`,
      { method: "DELETE" }
    );
    if (res.ok) {
      toast.success("Item removed");
      fetchData();
    } else {
      toast.error("Failed to remove item");
    }
  }

  async function handleMoveItem(itemId: number, direction: "up" | "down") {
    const res = await fetch(
      `/api/proxy/api/v1/rolepanels/${id}/items/${itemId}/move`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      }
    );
    if (res.ok) {
      fetchData();
    }
  }

  async function handleAddItem(e: React.FormEvent) {
    e.preventDefault();
    if (!newRoleId || !panel) return;
    setAddingItem(true);
    try {
      const res = await fetch(`/api/proxy/api/v1/rolepanels/${id}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          emoji: newEmoji || null,
          role_id: newRoleId,
          label: newLabel || null,
          style: panel.panel_type === "button" ? newStyle : null,
          position: panel.items.length,
        }),
      });
      if (res.ok) {
        toast.success("Item added");
        setNewEmoji("");
        setNewRoleId("");
        setNewLabel("");
        setNewStyle("primary");
        fetchData();
      } else {
        toast.error("Failed to add item");
      }
    } finally {
      setAddingItem(false);
    }
  }

  const sortedItems = [...panel.items].sort((a, b) => a.position - b.position);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/roles">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Role Panel #{id}</h1>
        <Badge variant="secondary">
          {panel.panel_type === "button" ? "Button" : "Reaction"}
        </Badge>
        {panel.message_id ? (
          <Badge className="bg-green-600 hover:bg-green-600">Posted</Badge>
        ) : (
          <Badge variant="secondary">Not posted</Badge>
        )}
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Server: {guildName}</span>
        <span>|</span>
        <span>Channel: {channelName}</span>
      </div>

      {/* Panel Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Panel Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Title <span className="text-red-500">*</span>
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Description
              </label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Embed Color
              </label>
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
                  className="w-32"
                />
              </div>
            </div>

            {panel.panel_type === "reaction" && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="remove_reaction"
                  checked={removeReaction}
                  onCheckedChange={(checked) =>
                    setRemoveReaction(checked === true)
                  }
                />
                <label htmlFor="remove_reaction" className="text-sm">
                  Remove reaction on toggle (role removed when reaction removed)
                </label>
              </div>
            )}

            <Button type="submit" disabled={submitting || !title.trim()}>
              {submitting ? "Saving..." : "Save Changes"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader>
          <CardTitle>Items ({sortedItems.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead>Emoji</TableHead>
                <TableHead>Role</TableHead>
                {panel.panel_type === "button" && (
                  <>
                    <TableHead>Label</TableHead>
                    <TableHead>Style</TableHead>
                  </>
                )}
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedItems.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={panel.panel_type === "button" ? 6 : 4}
                    className="text-center text-muted-foreground py-8"
                  >
                    No items added yet
                  </TableCell>
                </TableRow>
              ) : (
                sortedItems.map((item: RolePanelItem, index: number) => (
                  <TableRow key={item.id}>
                    <TableCell className="text-muted-foreground">
                      {index + 1}
                    </TableCell>
                    <TableCell>{item.emoji || "-"}</TableCell>
                    <TableCell>
                      {resolveRoleName(guildRoles, item.role_id)}
                    </TableCell>
                    {panel.panel_type === "button" && (
                      <>
                        <TableCell>{item.label || "-"}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {item.style || "-"}
                          </Badge>
                        </TableCell>
                      </>
                    )}
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleMoveItem(item.id, "up")}
                          disabled={index === 0}
                        >
                          ↑
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleMoveItem(item.id, "down")}
                          disabled={index === sortedItems.length - 1}
                        >
                          ↓
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-500 hover:text-red-600"
                          onClick={() => handleDeleteItem(item.id)}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Add Item Form */}
          <form
            onSubmit={handleAddItem}
            className="mt-4 flex items-end gap-2 rounded-md border border-border p-3"
          >
            <div className="w-20">
              <label className="text-xs text-muted-foreground mb-1 block">
                Emoji
              </label>
              <Input
                value={newEmoji}
                onChange={(e) => setNewEmoji(e.target.value)}
                placeholder="🎮"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-muted-foreground mb-1 block">
                Role
              </label>
              <Select value={newRoleId} onValueChange={setNewRoleId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  {guildRoles.map((role) => (
                    <SelectItem key={role.id} value={role.id}>
                      {role.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {panel.panel_type === "button" && (
              <>
                <div className="flex-1">
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Label
                  </label>
                  <Input
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    placeholder="Button label"
                  />
                </div>
                <div className="w-40">
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Style
                  </label>
                  <Select value={newStyle} onValueChange={setNewStyle}>
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
            <Button type="submit" size="sm" disabled={addingItem || !newRoleId}>
              {addingItem ? "Adding..." : "+ Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Panel Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handlePost}>
              {panel.message_id ? "Update in Discord" : "Post to Discord"}
            </Button>
            <Button variant="outline" onClick={handleCopy}>
              Copy Panel
            </Button>
            <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
              <DialogTrigger asChild>
                <Button variant="destructive">Delete Panel</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Confirm Deletion</DialogTitle>
                  <DialogDescription>
                    Are you sure you want to delete this role panel? This action
                    cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setDeleteOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleDelete}
                    disabled={deleteLoading}
                  >
                    {deleteLoading ? "Deleting..." : "Delete"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
