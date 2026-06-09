"use client";

/**
 * DebugPanel – Socket.IO-Event-Monitor für die Entwicklungsumgebung.
 *
 * Wird ausschließlich im Entwicklungsmodus angezeigt (NODE_ENV !== "production").
 * In Production-Builds gibt die Komponente null zurück und hat keinen Einfluss
 * auf Rendering oder Bundle-Größe.
 *
 * Zeigt alle empfangenen Socket.IO-Events in umgekehrter chronologischer Reihenfolge
 * (neueste zuerst) mit Timestamp, Event-Name und den ersten 300 Zeichen der Payload.
 *
 * Verwendung: Events werden von der Elternkomponente (page.tsx) gesammelt
 * und als `events`-Prop übergeben.
 */

import { useState } from "react";

type DebugEvent = {
  ts: string;
  event: string;
  data: unknown;
};

type Props = {
  events: DebugEvent[];
};

export default function DebugPanel({ events }: Props) {
  const [open, setOpen] = useState(false);

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 font-mono text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="bg-yellow-400 text-black px-3 py-1 rounded shadow font-bold"
      >
        {open ? "▼ Debug" : "▶ Debug"} ({events.length})
      </button>

      {open && (
        <div className="mt-1 w-[480px] max-h-72 overflow-y-auto bg-gray-900 border border-yellow-400 rounded p-2 shadow-xl">
          {events.length === 0 && (
            <p className="text-gray-400">Noch keine Events empfangen.</p>
          )}
          {[...events].reverse().map((e, i) => (
            <div key={i} className="mb-2 border-b border-gray-700 pb-1">
              <span className="text-yellow-400">{e.ts}</span>{" "}
              <span className="text-green-400 font-bold">{e.event}</span>
              <pre className="text-gray-300 whitespace-pre-wrap break-all mt-0.5">
                {JSON.stringify(e.data, null, 2).slice(0, 300)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export type { DebugEvent };
