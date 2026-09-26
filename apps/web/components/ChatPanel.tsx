"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Card, CardBody } from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Spinner from "@/components/ui/Spinner";

interface Props {
  onSubmit: (text: string) => void;
  disabled: boolean;
  defaultValue: string;
}

export default function ChatPanel({ onSubmit, disabled, defaultValue }: Props) {
  const [text, setText] = useState(defaultValue);

  return (
    <Card className="mx-8">
      <CardBody className="py-5">
        <label className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <Sparkles className="h-3.5 w-3.5 text-brand-500" />
          Access Review Request
        </label>
        <textarea
          className="w-full resize-none rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
        />
        <div className="mt-3 flex justify-end">
          <Button disabled={disabled || !text.trim()} onClick={() => onSubmit(text.trim())}>
            {disabled && <Spinner className="h-4 w-4" />}
            {disabled ? "Analyzing…" : "Run Blast Radius Review"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
