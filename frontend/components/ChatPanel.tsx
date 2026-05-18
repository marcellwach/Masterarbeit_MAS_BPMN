"use client";

/**
 * ChatPanel – linkes Panel der Split-Ansicht.
 *
 * Zeigt den Nachrichtenverlauf (Nutzer-Eingaben + Backend-Statusmeldungen)
 * und die Eingabebox für neue Prozessbeschreibungen.
 *
 * Nachrichtentypen:
 *   user    → blaue Bubble (rechts)
 *   system  → grauer Kursivtext (Statusmeldungen vom Backend via Socket.IO)
 *   error   → roter Hinweis
 *   success → grüner Hinweis (Generierung abgeschlossen)
 */

import { useEffect, useRef, useState } from "react";
import { Message } from "@/app/page";

type Props = {
  messages: Message[];
  isLoading: boolean;       // true während Backend generiert → Eingabe gesperrt
  onSend: (text: string) => void;
};

export default function ChatPanel({ messages, isLoading, onSend }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Automatisch zum neuesten Eintrag scrollen
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = () => {
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput("");
  };

  // Enter (ohne Shift) sendet; Shift+Enter fügt Zeilenumbruch ein
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Tailwind-Klassen je Nachrichtentyp
  const messageStyle: Record<Message["type"], string> = {
    user:    "self-end bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[85%]",
    system:  "self-start text-gray-400 italic text-sm px-2 py-1 max-w-[95%]",
    error:   "self-start bg-red-900/40 text-red-300 rounded-lg px-4 py-2 max-w-[90%] border border-red-700",
    success: "self-start bg-green-900/40 text-green-300 rounded-lg px-4 py-2 max-w-[90%] border border-green-700",
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-900">
        <h1 className="font-semibold text-base">BPMN-Generator</h1>
        <p className="text-xs text-gray-400">Multi-Agenten-System · Masterarbeit</p>
      </div>

      {/* Nachrichtenverlauf */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {messages.length === 0 && (
          <p className="text-gray-500 text-sm text-center mt-8">
            Beschreibe einen Geschäftsprozess, um ein BPMN-Modell zu generieren.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={messageStyle[msg.type]}>
            {msg.text}
          </div>
        ))}
        {/* Spinner während Backend-Verarbeitung */}
        {isLoading && (
          <div className="self-start flex items-center gap-2 text-gray-400 text-sm px-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full" />
            Agenten arbeiten...
          </div>
        )}
        {/* Unsichtbarer Anker für Auto-Scroll */}
        <div ref={bottomRef} />
      </div>

      {/* Eingabebereich */}
      <div className="px-4 py-3 border-t border-gray-700 bg-gray-900">
        <div className="flex gap-2 items-end">
          <textarea
            className="flex-1 bg-gray-800 text-gray-100 rounded-xl px-3 py-2 text-sm resize-none
                       border border-gray-600 focus:outline-none focus:border-blue-500
                       placeholder-gray-500 min-h-[44px] max-h-32"
            placeholder="Prozessbeschreibung eingeben… (Enter zum Senden)"
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <button
            onClick={handleSubmit}
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                       disabled:text-gray-500 text-white rounded-xl text-sm font-medium
                       transition-colors min-h-[44px]"
          >
            Senden
          </button>
        </div>
      </div>
    </div>
  );
}
