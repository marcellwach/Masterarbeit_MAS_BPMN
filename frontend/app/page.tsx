"use client";

/**
 * Haupt-Seite – Split-Layout mit ChatPanel (links) und BpmnViewer (rechts).
 *
 * Verwaltet die Socket.IO-Verbindung zum Backend und leitet Events an
 * die Kindkomponenten weiter.
 *
 * Socket.IO-Ereignisfluss:
 *   Nutzer sendet Prompt
 *     → emit("generate_bpmn", { prompt, session_id, existing_bpmn_xml })
 *     ← on("status_update")    → ChatPanel zeigt Statusmeldungen
 *     ← on("bpmn_result")      → BpmnViewer rendert das BPMN-Diagramm
 *     ← on("generation_failed") → ChatPanel zeigt Fehlermeldung
 *
 * Iterative Modifikation:
 *   Bei Folge-Prompts (currentBpmnXml vorhanden) wird das bestehende XML
 *   mitgesendet → Backend modifiziert das Modell gezielt statt neu zu generieren.
 *   Die session_id bleibt gleich damit alle Iterationen im selben Trace-Log landen.
 */

import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import ChatPanel from "@/components/ChatPanel";
import BpmnViewer from "@/components/BpmnViewer";
import DebugPanel, { DebugEvent } from "@/components/DebugPanel";

export type Message = {
  type: "user" | "system" | "error" | "success";
  text: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentBpmnXml, setCurrentBpmnXml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([]);
  const socketRef = useRef<Socket | null>(null);
  // Session-ID: neu beim ersten Prompt, gleich bei Folge-Prompts (Modifikation)
  const sessionIdRef = useRef<string>(crypto.randomUUID());

  /** Fügt ein Debug-Event ins DebugPanel ein (nur sichtbar in development). */
  const addDebug = (event: string, data: unknown) => {
    setDebugEvents((prev) => [
      ...prev,
      { ts: new Date().toISOString().slice(11, 23), event, data },
    ]);
  };

  // Socket.IO-Verbindung aufbauen und Event-Handler registrieren
  useEffect(() => {
    const socket = io("http://localhost:8000", { transports: ["websocket"] });
    socketRef.current = socket;

    // Verbindungsstatus im Debug-Panel sichtbar machen
    socket.on("connect", () => addDebug("connect", { id: socket.id }));
    socket.on("disconnect", (reason) => addDebug("disconnect", { reason }));
    socket.on("connect_error", (err) => addDebug("connect_error", { message: err.message }));

    // Statusmeldungen während der Agenten-Ausführung (DP4)
    socket.on("status_update", (data: { message: string; iteration: number }) => {
      addDebug("status_update", data);
      setMessages((prev) => [...prev, { type: "system", text: data.message }]);
    });

    // Erfolgreich generiertes und validiertes BPMN-Modell
    socket.on("bpmn_result", (data: { bpmn_xml: string }) => {
      addDebug("bpmn_result", { xml_length: data.bpmn_xml.length, xml_preview: data.bpmn_xml.slice(0, 400) });
      setCurrentBpmnXml(data.bpmn_xml);
      setMessages((prev) => [
        ...prev,
        { type: "success", text: "Generierung abgeschlossen. Modell ist valide und sound." },
      ]);
      setIsLoading(false);
    });

    // Fehler (z.B. max_iterations erreicht ohne valides Modell)
    socket.on("generation_failed", (data: { reason: string }) => {
      addDebug("generation_failed", data);
      setMessages((prev) => [
        ...prev,
        { type: "error", text: `Generierung fehlgeschlagen: ${data.reason}` },
      ]);
      setIsLoading(false);
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const handleSend = (text: string) => {
    if (!text.trim() || isLoading || !socketRef.current) return;

    addDebug("emit:generate_bpmn", { prompt: text.slice(0, 60) + "...", has_existing: !!currentBpmnXml });
    setMessages((prev) => [...prev, { type: "user", text }]);
    setIsLoading(true);

    // Neue Session-ID nur beim ersten Prompt (Neugenerierung)
    // Bei Folge-Prompts bleibt die ID gleich → alle Iterationen im selben Trace-Log
    if (!currentBpmnXml) sessionIdRef.current = crypto.randomUUID();

    socketRef.current.emit("generate_bpmn", {
      prompt: text,
      session_id: sessionIdRef.current,
      existing_bpmn_xml: currentBpmnXml ?? "",  // "" = Neugenerierung, XML = Modifikation
    });
  };

  return (
    <main className="fixed inset-0 flex bg-gray-950 text-gray-100">
      {/* Linkes Panel: Eingabe + Statusmeldungen (~40% Breite) */}
      <div className="w-[40%] min-w-[320px] border-r border-gray-700 flex flex-col h-full">
        <ChatPanel messages={messages} isLoading={isLoading} onSend={handleSend} />
      </div>
      {/* Rechtes Panel: BPMN-Viewer (~60% Breite) */}
      <div className="flex-1 relative h-full">
        <BpmnViewer bpmnXml={currentBpmnXml} />
      </div>
      {/* Debug-Overlay: nur in development sichtbar */}
      <DebugPanel events={debugEvents} />
    </main>
  );
}
