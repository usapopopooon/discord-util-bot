"use client";

import { useEffect, useState, useCallback } from "react";
import type { AutoModConfig, GuildsMap, ChannelsMap } from "@/lib/types";
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
import { Slider } from "@/components/ui/slider";
import Link from "next/link";

export default function AutoModSettingsPage() {
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);

  // Form state
  const [selectedGuild, setSelectedGuild] = useState("");
  const [logChannelId, setLogChannelId] = useState("");
  const [introCheckMessages, setIntroCheckMessages] = useState(50);
  const [configLoading, setConfigLoading] = useState(false);

  const fetchData = useCallback(async () => {
    const [guildsRes, channelsRes] = await Promise.all([
      fetch("/api/v1/guilds").then((r) => r.json()),
      fetch("/api/v1/channels").then((r) => r.json()),
    ]);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const loadConfig = useCallback(async (guildId: string) => {
    if (!guildId) return;
    setConfigLoading(true);
    try {
      const res = await fetch(`/api/v1/automod/settings?guild_id=${guildId}`);
      if (res.ok) {
        const config: AutoModConfig = await res.json();
        setLogChannelId(config.log_channel_id ?? "");
        setIntroCheckMessages(config.intro_check_messages ?? 50);
      } else {
        setLogChannelId("");
        setIntroCheckMessages(50);
      }
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedGuild) {
      loadConfig(selectedGuild);
    }
  }, [selectedGuild, loadConfig]);

  const filteredChannels = selectedGuild ? (channels[selectedGuild] ?? []) : [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedGuild) return;
    setSubmitting(true);
    setSaved(false);
    try {
      await fetch("/api/v1/automod/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: selectedGuild,
          log_channel_id: logChannelId || null,
          intro_check_messages: introCheckMessages,
        }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">AutoMod Settings</h1>
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
        <h1 className="text-2xl font-bold">AutoMod Settings</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Guild Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v);
                  setLogChannelId("");
                  setIntroCheckMessages(50);
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

            {selectedGuild && !configLoading && (
              <>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Log Channel</label>
                  <Select value={logChannelId} onValueChange={setLogChannelId}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select channel (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">None</SelectItem>
                      {filteredChannels.map((ch) => (
                        <SelectItem key={ch.id} value={ch.id}>
                          {ch.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-sm font-medium mb-1.5 block">
                    Intro Check Messages: {introCheckMessages}
                  </label>
                  <div className="flex items-center gap-4">
                    <Slider
                      value={[introCheckMessages]}
                      onValueChange={([v]) => setIntroCheckMessages(v)}
                      min={0}
                      max={200}
                      step={1}
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      min={0}
                      max={200}
                      value={introCheckMessages}
                      onChange={(e) =>
                        setIntroCheckMessages(
                          Math.min(200, Math.max(0, parseInt(e.target.value, 10) || 0))
                        )
                      }
                      className="w-20"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button type="submit" disabled={submitting || !selectedGuild}>
                    {submitting ? "Saving..." : "Save Settings"}
                  </Button>
                  {saved && (
                    <span className="text-sm text-green-600">Settings saved successfully</span>
                  )}
                </div>
              </>
            )}

            {configLoading && <p className="text-muted-foreground">Loading settings...</p>}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
