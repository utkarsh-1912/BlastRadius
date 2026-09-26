"use client";

import { useState } from "react";

interface Props {
  onSubmit: (text: string) => void;
  disabled: boolean;
  defaultValue: string;
}

export default function ChatPanel({ onSubmit, disabled, defaultValue }: Props) {
  const [text, setText] = useState(defaultValue);

  return (
    <section className="border-b border-gray-200 bg-white px-6 py-5">
      <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-500">
        Access Review Request
      </label>
      <textarea
        className="w-full resize-none rounded-md border border-gray-300 p-3 text-sm text-gray-800 focus:border-gray-500 focus:outline-none"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
      />
      <div className="mt-3 flex justify-end">
        <button
          className="rounded-md bg-gray-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={disabled || !text.trim()}
          onClick={() => onSubmit(text.trim())}
        >
          {disabled ? "Analyzing…" : "Run Blast Radius Review"}
        </button>
      </div>
    </section>
  );
}
