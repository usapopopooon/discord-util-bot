"use client";

import { useEffect, useState, useCallback } from "react";
import type { ActivitySettings } from "@/lib/types";
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

const ACTIVITY_TYPES = [
  { value: "playing", label: "Playing" },
  { value: "listening", label: "Listening" },
  { value: "watching", label: "Watching" },
  { value: "competing", label: "Competing" },
];

export default function ActivityPage() {
  const [activityType, setActivityType] = useState("playing");
  const [activityText, setActivityText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/proxy/api/v1/activity");
      if (res.ok) {
        const data: ActivitySettings = await res.json();
        setActivityType(data.activity_type || "playing");
        setActivityText(data.activity_text || "");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/api/v1/activity", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          activity_type: activityType,
          activity_text: activityText,
        }),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Activity updated successfully." });
      } else {
        setMessage({ type: "error", text: "Failed to update activity." });
      }
    } catch {
      setMessage({ type: "error", text: "Failed to update activity." });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Bot Activity</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Bot Activity</h1>

      <Card>
        <CardHeader>
          <CardTitle>Activity Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSave} className="space-y-4 max-w-md">
            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Activity Type
              </label>
              <Select value={activityType} onValueChange={setActivityType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ACTIVITY_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Activity Text
              </label>
              <Input
                value={activityText}
                onChange={(e) => setActivityText(e.target.value)}
                placeholder="Enter activity text..."
              />
            </div>
            {message && (
              <p
                className={
                  message.type === "success"
                    ? "text-sm text-green-500"
                    : "text-sm text-destructive"
                }
              >
                {message.text}
              </p>
            )}
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
