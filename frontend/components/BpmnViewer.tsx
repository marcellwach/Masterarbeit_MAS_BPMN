"use client";

/**
 * BpmnViewer – rechtes Panel der Split-Ansicht.
 *
 * Rendert BPMN-XML grafisch mit bpmn-js (NavigatedViewer, nur Anzeige, kein Editieren).
 * Vor dem Rendern wird bpmn-auto-layout angewendet, das automatisch ein
 * kollisionsfreies Layout mit orthogonalen Verbindungen berechnet.
 *
 * Technische Besonderheiten:
 *
 * 1. Dynamischer Import ("use client" verhindert SSR-Probleme, aber bpmn-js
 *    darf trotzdem nicht statisch importiert werden da es DOM voraussetzt).
 *
 * 2. viewerVersion-Zähler statt Boolean für viewerReady:
 *    React 18 StrictMode führt useEffect zweimal aus (mount → cleanup → mount).
 *    Ein Boolean-State würde beim zweiten setViewerReady(true) keinen Re-Render
 *    triggern → importXML wird nie aufgerufen. Ein Zähler (v => v + 1)
 *    ändert sich garantiert und triggert den XML-Import-Effect.
 *
 * 3. cancelled-Flag verhindert Race Conditions: falls cleanup vor dem
 *    async import() läuft, wird kein Viewer mehr erstellt.
 */

import { useEffect, useRef, useState } from "react";

type Props = {
  bpmnXml: string | null;
};

export default function BpmnViewer({ bpmnXml }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null);

  // Zähler: jede (Re-)Initialisierung des Viewers erhöht den Wert →
  // useEffect([viewerVersion, bpmnXml]) feuert garantiert auch beim zweiten Mount
  const [viewerVersion, setViewerVersion] = useState(0);
  const [importError, setImportError] = useState<string | null>(null);

  // Viewer einmalig initialisieren (dynamischer Import wegen DOM-Abhängigkeit)
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;  // verhindert späte Callbacks nach Cleanup

    import("bpmn-js/lib/NavigatedViewer").then(({ default: BpmnJS }) => {
      if (cancelled) return;
      viewerRef.current?.destroy();
      viewerRef.current = new BpmnJS({ container: containerRef.current! });
      setViewerVersion((v) => v + 1);
    });

    return () => {
      cancelled = true;
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
  }, []);

  // XML importieren wenn Viewer bereit UND neues XML vorhanden
  useEffect(() => {
    if (!viewerVersion || !bpmnXml || !viewerRef.current) return;

    setImportError(null);

    // bpmn-auto-layout berechnet DI (Positionen + Pfad-Routing) aus dem Prozess-XML
    import("bpmn-auto-layout").then(({ layoutProcess }) => {
      return layoutProcess(bpmnXml);
    }).then((laidOutXml: string) => {
      return viewerRef.current.importXML(laidOutXml);
    }).then(({ warnings }: { warnings: unknown[] }) => {
      if (warnings.length > 0) console.warn("bpmn-js warnings:", warnings);
      viewerRef.current.get("canvas").zoom("fit-viewport");
    }).catch((err: Error) => {
      console.error("bpmn layout/import error:", err);
      // Fallback: Original-XML ohne Auto-Layout direkt importieren
      viewerRef.current?.importXML(bpmnXml)
        .then(() => viewerRef.current?.get("canvas").zoom("fit-viewport"))
        .catch((e: Error) => setImportError(e.message));
    });
  }, [viewerVersion, bpmnXml]);

  return (
    <div className="relative w-full h-full bg-gray-900">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-10 px-4 py-3 border-b border-gray-700 bg-gray-900">
        <h2 className="font-semibold text-base">BPMN-Viewer</h2>
        <p className="text-xs text-gray-400">
          {bpmnXml ? "Validiertes BPMN 2.0 Modell" : "Noch kein Modell vorhanden"}
        </p>
      </div>

      {/* bpmn-js rendert sein SVG in diesen Container */}
      <div
        ref={containerRef}
        className="absolute inset-0 top-[57px]"
        style={{ background: "#f8f9fa" }}
      />

      {/* Fehlermeldung bei Layout- oder Parsing-Fehler */}
      {importError && (
        <div className="absolute inset-0 top-[57px] flex items-center justify-center z-20 pointer-events-none">
          <div className="bg-red-900/80 border border-red-500 rounded-lg p-4 max-w-lg text-sm text-red-200">
            <p className="font-bold mb-1">Layout-Fehler:</p>
            <p className="font-mono break-all">{importError}</p>
          </div>
        </div>
      )}

      {/* Placeholder solange noch kein Modell generiert wurde */}
      {!bpmnXml && (
        <div className="absolute inset-0 top-[57px] flex items-center justify-center pointer-events-none">
          <div className="text-center text-gray-400">
            <div className="text-5xl mb-4">⬡</div>
            <p className="text-lg font-medium">Hier wird Ihr BPMN-Modell angezeigt.</p>
            <p className="text-sm mt-1">Geben Sie links eine Prozessbeschreibung ein.</p>
          </div>
        </div>
      )}
    </div>
  );
}
