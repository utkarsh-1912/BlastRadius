"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ChatPanel from "@/components/ChatPanel";
import PageHeader from "@/components/ui/PageHeader";
import { createReview } from "@/lib/api";

const DEMO_REQUEST = "Review IAM access for the data-pipeline-role role over the last 90 days.";

export default function Home() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (text: string) => {
    setLoading(true);
    setError(null);
    try {
      const run = await createReview(text);
      router.push(`/reviews/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  };

  return (
    <main className="flex flex-col pb-10">
      <PageHeader
        title="Start a Blast Radius Review"
        description="Describe which role (or roles) to review. Blast Radius reads the real IAM policy and CloudTrail history, replays every candidate permission through two independent evaluators, and stops for your approval before anything is revoked."
      />
      <ChatPanel onSubmit={handleSubmit} disabled={loading} defaultValue={DEMO_REQUEST} />
      {error && <p className="mx-8 mt-3 text-sm text-accent">{error}</p>}
    </main>
  );
}
