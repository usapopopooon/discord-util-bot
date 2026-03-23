"use client";

import { useEffect, useState, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import type { AutoModRule, GuildsMap, ChannelsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import Link from "next/link";

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

const ACTIONS = [
  { value: "ban", label: "Ban" },
  { value: "kick", label: "Kick" },
  { value: "timeout", label: "Timeout" },
];

export default function AutoModEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [rule, setRule] = useState<AutoModRule | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [action, setAction] = useState("");
  const [pattern, setPattern] = useState("");
  const [useWildcard, setUseWildcard] = useState(false);
  const [thresholdValue, setThresholdValue] = useState("");
  const [timeoutDurationMinutes, setTimeoutDurationMinutes] = useState("");
  const [requiredChannelId, setRequiredChannelId] = useState("");

  const fetchData = useCallback(async () => {
    const [ruleRes, guildsRes, channelsRes] = await Promise.all([
      fetch(`/api/v1/automod/rules/${id}`).then((r) => r.json()),
      fetch("/api/v1/guilds").then((r) => r.json()),
      fetch("/api/v1/channels").then((r) => r.json()),
    ]);
    setRule(ruleRes);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});

    if (ruleRes) {
      setAction(ruleRes.action ?? "");
      setPattern(ruleRes.pattern ?? "");
      setUseWildcard(ruleRes.use_wildcard ?? false);
      setRequiredChannelId(ruleRes.required_channel_id ?? "");

      if (ruleRes.rule_type === "account_age" && ruleRes.threshold_seconds) {
        setThresholdValue(String(Math.round(ruleRes.threshold_seconds / 60)));
      } else if (ruleRes.threshold_seconds) {
        setThresholdValue(String(ruleRes.threshold_seconds));
      }

      if (ruleRes.timeout_duration_seconds) {
        setTimeoutDurationMinutes(String(Math.round(ruleRes.timeout_duration_seconds / 60)));
      }
    }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading || !rule) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Edit AutoMod Rule</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const filteredChannels = rule.guild_id ? (channels[rule.guild_id] ?? []) : [];

  const showPattern = rule.rule_type === "username_match";
  const showAccountAge = rule.rule_type === "account_age";
  const showThreshold = ["role_acquired", "vc_join", "message_post"].includes(rule.rule_type);
  const showRequiredChannel = ["vc_without_intro", "msg_without_intro"].includes(rule.rule_type);
  const showTimeoutDuration = action === "timeout";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!action) return;
    setSubmitting(true);
    try {
      let thresholdSeconds: number | null = null;
      if (showAccountAge && thresholdValue) {
        thresholdSeconds = parseInt(thresholdValue, 10) * 60;
      } else if (showThreshold && thresholdValue) {
        thresholdSeconds = parseInt(thresholdValue, 10);
      }

      let timeoutSeconds: number | null = null;
      if (showTimeoutDuration && timeoutDurationMinutes) {
        timeoutSeconds = parseInt(timeoutDurationMinutes, 10) * 60;
      }

      const body: Record<string, unknown> = {
        action,
        pattern: showPattern ? pattern || null : null,
        use_wildcard: showPattern ? useWildcard : false,
        threshold_seconds: thresholdSeconds,
        timeout_duration_seconds: timeoutSeconds,
        required_channel_id: showRequiredChannel ? requiredChannelId || null : null,
      };

      await fetch(`/api/v1/automod/rules/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      router.push("/dashboard/automod");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/automod">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Edit AutoMod Rule</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Edit Rule #{id}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Input value={guilds[rule.guild_id] ?? rule.guild_id} disabled />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Rule Type</label>
              <Input value={RULE_TYPE_LABELS[rule.rule_type] ?? rule.rule_type} disabled />
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Action</label>
              <Select value={action} onValueChange={setAction}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select action" />
                </SelectTrigger>
                <SelectContent>
                  {ACTIONS.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {showPattern && (
              <>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Pattern</label>
                  <Input
                    value={pattern}
                    onChange={(e) => setPattern(e.target.value)}
                    placeholder="e.g. spam*bot"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="use_wildcard"
                    checked={useWildcard}
                    onCheckedChange={(checked) => setUseWildcard(checked === true)}
                  />
                  <label htmlFor="use_wildcard" className="text-sm">
                    Use wildcard matching
                  </label>
                </div>
              </>
            )}

            {showAccountAge && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Account Age Threshold (minutes, 1-20160)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={20160}
                  value={thresholdValue}
                  onChange={(e) => setThresholdValue(e.target.value)}
                />
              </div>
            )}

            {showThreshold && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Threshold (seconds, 1-3600)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={3600}
                  value={thresholdValue}
                  onChange={(e) => setThresholdValue(e.target.value)}
                />
              </div>
            )}

            {showRequiredChannel && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">Required Channel</label>
                <Select value={requiredChannelId} onValueChange={setRequiredChannelId}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select channel" />
                  </SelectTrigger>
                  <SelectContent>
                    {filteredChannels.map((ch) => (
                      <SelectItem key={ch.id} value={ch.id}>
                        {ch.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {showTimeoutDuration && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Timeout Duration (minutes, 1-40320)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={40320}
                  value={timeoutDurationMinutes}
                  onChange={(e) => setTimeoutDurationMinutes(e.target.value)}
                />
              </div>
            )}

            <Button type="submit" disabled={submitting || !action}>
              {submitting ? "Saving..." : "Save Changes"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
