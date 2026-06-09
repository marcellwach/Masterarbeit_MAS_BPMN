"use client";

/**
 * BpmnViewer – BPMN-Anzeige und Bearbeitung in zwei Modi.
 *
 * Modus "view": bpmn-js NavigatedViewer, bpmn-auto-layout für Layout
 * Modus "edit": bpmn-js Modeler mit Palette und Bearbeitungswerkzeugen
 *
 * Viewport-Erhalt beim Moduswechsel:
 *   Der canvas.viewbox() wird vor dem Zerstören der alten Instanz gesichert
 *   und nach dem Import in der neuen Instanz wiederhergestellt.
 *   Bei neuen XML-Inhalten (anderes Modell) wird stattdessen fit-viewport verwendet.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

type Props = {
  bpmnXml: string | null;
  mode: "view" | "edit";
};

/**
 * Ref-Handle: erlaubt der Elternkomponente (page.tsx, ExportBar) kontrollierten
 * Zugriff auf bpmn-js-Instanz-Methoden ohne direkten State-Lift.
 */
export type BpmnViewerHandle = {
  saveSVG: () => Promise<{ svg: string }>;  // SVG-Export für den Download-Button
  getXML: () => Promise<string | null>;     // Aktuelles XML auslesen (bei manuellem Edit)
};

const BpmnViewer = forwardRef<BpmnViewerHandle, Props>(({ bpmnXml, mode }, ref) => {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const instanceRef = useRef<any>(null);    // aktive bpmn-js Instanz (NavigatedViewer oder Modeler)
  const [viewerVersion, setViewerVersion] = useState(0);  // Trigger für XML-Import nach Instanz-Neustart
  const [importError, setImportError] = useState<string | null>(null);

  // Viewport vor Moduswechsel speichern, um Zoom/Pan zu erhalten
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const savedViewportRef = useRef<any>(null);
  // Letztes XML – erkennt ob XML wirklich neu ist oder nur Modus wechselt
  const prevXmlRef = useRef<string | null>(null);

  useImperativeHandle(ref, () => ({
    saveSVG: () => instanceRef.current?.saveSVG() ?? Promise.reject("Nicht bereit"),
    getXML: async () => {
      if (!instanceRef.current) return null;
      try {
        const { xml } = await instanceRef.current.saveXML({ format: true });
        return xml ?? null;
      } catch {
        return null;
      }
    },
  }));

  // Moduswechsel: Viewport sichern, Instanz neu erstellen
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;

    // Viewport vor dem Zerstören der alten Instanz sichern
    if (instanceRef.current) {
      try {
        savedViewportRef.current = instanceRef.current.get("canvas").viewbox();
      } catch {
        savedViewportRef.current = null;
      }
    }

    // Lazy-Import: bpmn-js ist groß (~2 MB), wird erst beim ersten Rendern geladen
    const initLib = mode === "edit"
      ? import("bpmn-js/lib/Modeler")      // Palette + Bearbeitungswerkzeuge
      : import("bpmn-js/lib/NavigatedViewer"); // nur Zoom/Pan, kein Edit

    initLib.then(({ default: BpmnJS }) => {
      if (cancelled) return;
      instanceRef.current?.destroy();
      instanceRef.current = new BpmnJS({ container: containerRef.current! });
      setViewerVersion((v) => v + 1);
    });

    return () => {
      cancelled = true;
      instanceRef.current?.destroy();
      instanceRef.current = null;
    };
  }, [mode]);

  // XML importieren; Viewport nur bei neuem XML zurücksetzen
  useEffect(() => {
    if (!viewerVersion || !bpmnXml || !instanceRef.current) return;

    setImportError(null);
    const isNewXml = bpmnXml !== prevXmlRef.current;
    prevXmlRef.current = bpmnXml;

    const doImport = async (xml: string) => {
      try {
        let xmlToImport = xml;
        // Backend generiert kein DI – bpmn-auto-layout berechnet es im Browser
        const needsLayout = !xml.includes("BPMNDiagram");

        if (needsLayout || mode === "view") {
          const { layoutProcess } = await import("bpmn-auto-layout");
          xmlToImport = await layoutProcess(xml);
        }

        await instanceRef.current.importXML(xmlToImport);
        const canvas = instanceRef.current.get("canvas");

        if (isNewXml || !savedViewportRef.current) {
          // Neues Modell → Inhalt einpassen
          canvas.zoom("fit-viewport");
          savedViewportRef.current = null;
        } else {
          // Moduswechsel → Viewbox nach nächstem Frame wiederherstellen
          // (requestAnimationFrame: Canvas ist dann vollständig gerendert)
          const vb = savedViewportRef.current;
          savedViewportRef.current = null;
          // Zwei Frames warten: bpmn-js macht nach importXML intern noch Reflows
          requestAnimationFrame(() => requestAnimationFrame(() => {
            try {
              canvas.viewbox(vb);
            } catch {
              canvas.zoom("fit-viewport");
            }
          }));
        }
      } catch (err: unknown) {
        console.error("bpmn import error:", err);
        try {
          await instanceRef.current.importXML(xml);
          instanceRef.current.get("canvas").zoom("fit-viewport");
        } catch (e: unknown) {
          setImportError(e instanceof Error ? e.message : String(e));
        }
      }
    };

    doImport(bpmnXml);
  }, [viewerVersion, bpmnXml, mode]);

  return (
    <div className="relative w-full h-full bg-gray-900">
      <div className="absolute top-0 left-0 right-0 z-10 px-4 py-3 border-b border-gray-700 bg-gray-900">
        <h2 className="font-semibold text-base">BPMN-Viewer</h2>
        <p className="text-xs text-gray-400">
          {!bpmnXml
            ? "Noch kein Modell vorhanden"
            : mode === "edit"
            ? "Manueller Bearbeitungsmodus"
            : "Validiertes BPMN 2.0 Modell"}
        </p>
      </div>

      <div
        ref={containerRef}
        className="absolute inset-0 top-[57px]"
        style={{ background: "#f8f9fa" }}
      />

      {importError && (
        <div className="absolute inset-0 top-[57px] flex items-center justify-center z-20 pointer-events-none">
          <div className="bg-red-900/80 border border-red-500 rounded-lg p-4 max-w-lg text-sm text-red-200">
            <p className="font-bold mb-1">Import-Fehler:</p>
            <p className="font-mono break-all">{importError}</p>
          </div>
        </div>
      )}

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
});

BpmnViewer.displayName = "BpmnViewer";
export default BpmnViewer;
