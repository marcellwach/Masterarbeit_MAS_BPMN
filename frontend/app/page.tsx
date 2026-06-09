"use client";

/**
 * Haupt-Seite – Split-Layout mit ChatPanel (links) und BpmnViewer (rechts).
 *
 * Socket.IO-Ereignisfluss:
 *   Nutzer sendet Prompt
 *     → emit("generate_bpmn", { prompt, session_id, existing_bpmn_xml })
 *     ← on("status_update")     → ChatPanel zeigt Statusmeldungen
 *     ← on("bpmn_result")       → BpmnViewer rendert das BPMN-Diagramm
 *     ← on("generation_failed") → ChatPanel zeigt Fehlermeldung
 *
 * Iterative Modifikation:
 *   Bei Folge-Prompts wird das bestehende XML mitgesendet. Die session_id
 *   bleibt gleich → alle Iterationen landen im selben Trace-Log.
 */

import { useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import Link from "next/link";
import ChatPanel from "@/components/ChatPanel";
import BpmnViewer, { BpmnViewerHandle } from "@/components/BpmnViewer";
import ExportBar from "@/components/ExportBar";

export type Message = {
  type: "user" | "system" | "error" | "success";
  text: string;
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentBpmnXml, setCurrentBpmnXml] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [viewerMode, setViewerMode] = useState<"view" | "edit">("view");
  const socketRef = useRef<Socket | null>(null);
  const sessionIdRef = useRef<string>(crypto.randomUUID());
  const bpmnViewerRef = useRef<BpmnViewerHandle>(null);

  // Socket.IO-Verbindung aufbauen – ein Socket pro Seitenaufruf, Cleanup beim Unmount
  useEffect(() => {
    const socket = io("http://localhost:8000", { transports: ["websocket"] });
    socketRef.current = socket;

    // Iterationsstatus: erscheint als grauer Systemtext im ChatPanel
    socket.on("status_update", (data: { message: string; iteration: number }) => {
      setMessages((prev) => [...prev, { type: "system", text: data.message }]);
    });

    // Erfolg: BPMN-XML im Viewer anzeigen, isLoading beenden
    socket.on("bpmn_result", (data: { bpmn_xml: string }) => {
      setCurrentBpmnXml(data.bpmn_xml);
      setMessages((prev) => [
        ...prev,
        { type: "success", text: "Generierung abgeschlossen. Modell ist valide und sound." },
      ]);
      setIsLoading(false);
    });

    // Fehler (max_iterations oder Backend-Exception): Fehlermeldung im Chat
    socket.on("generation_failed", (data: { reason: string }) => {
      setMessages((prev) => [
        ...prev,
        { type: "error", text: `Generierung fehlgeschlagen: ${data.reason}` },
      ]);
      setIsLoading(false);
    });

    return () => { socket.disconnect(); };
  }, []);

  /**
   * Sendet den Nutzer-Prompt ans Backend via Socket.IO.
   *
   * Wenn der Viewer sich im manuellen Bearbeitungsmodus befindet, wird zuerst
   * das aktuelle XML aus bpmn-js ausgelesen und synchronisiert — damit fließen
   * manuelle Änderungen in den nächsten Generierungsschritt ein.
   *
   * Neue Session (kein bestehendes XML): neue UUID erzeugen → neuer Trace-Log.
   * Folge-Prompt (bestehendes XML): selbe session_id → alle Iterationen im gleichen Trace.
   */
  const handleSend = async (text: string) => {
    if (!text.trim() || isLoading || !socketRef.current) return;

    // Manuellen Modus verlassen und aktuelles XML synchronisieren
    let xmlToSend = currentBpmnXml;
    if (viewerMode === "edit" && bpmnViewerRef.current) {
      const latestXml = await bpmnViewerRef.current.getXML();
      if (latestXml) {
        xmlToSend = latestXml;
        setCurrentBpmnXml(latestXml);
      }
      setViewerMode("view");
    }

    setMessages((prev) => [...prev, { type: "user", text }]);
    setIsLoading(true);

    // Neue Session wenn kein XML vorhanden (Erster Prompt oder nach Fehler)
    if (!xmlToSend) sessionIdRef.current = crypto.randomUUID();

    socketRef.current.emit("generate_bpmn", {
      prompt: text,
      session_id: sessionIdRef.current,
      existing_bpmn_xml: xmlToSend ?? "",
    });
  };

  return (
    <main className="fixed inset-0 flex bg-gray-950 text-gray-100">
      {/* Linkes Panel: Eingabe + Statusmeldungen */}
      <div className="w-[40%] min-w-[320px] border-r border-gray-700 flex flex-col h-full">
        <ChatPanel messages={messages} isLoading={isLoading} onSend={handleSend} />
      </div>

      {/* Rechtes Panel: BPMN-Viewer + Export-Toolbar */}
      <div className="flex-1 flex flex-col h-full">
        <div className="flex items-center justify-end px-3 py-1.5 border-b border-gray-800 bg-gray-950">
          <Link href="/validate"
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            → Validator-Seite
          </Link>
        </div>
        <ExportBar
          bpmnXml={currentBpmnXml}
          sessionId={currentBpmnXml ? sessionIdRef.current : null}
          viewerRef={bpmnViewerRef}
          mode={viewerMode}
          onModeChange={async (newMode) => {
            if (viewerMode === "edit" && newMode === "view" && bpmnViewerRef.current) {
              const latestXml = await bpmnViewerRef.current.getXML();
              if (latestXml) setCurrentBpmnXml(latestXml);
            }
            setViewerMode(newMode);
          }}
          onImport={(xml) => {
            setCurrentBpmnXml(xml);
            setViewerMode("view");
            setMessages((prev) => [
              ...prev,
              { type: "system", text: "BPMN-Datei importiert. Du kannst das Modell jetzt per Chat modifizieren." },
            ]);
            sessionIdRef.current = crypto.randomUUID();
          }}
        />
        <div className="flex-1 relative">
          <BpmnViewer ref={bpmnViewerRef} bpmnXml={currentBpmnXml} mode={viewerMode} />
        </div>
      </div>
    </main>
  );
}
