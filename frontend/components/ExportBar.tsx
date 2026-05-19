"use client";

/**
 * ExportBar – Toolbar mit Import, Export und Evaluations-Buttons.
 *
 * Import:
 *   - BPMN-Datei (.bpmn/.xml) aus lokalem Dateisystem laden
 *   - Wird als currentBpmnXml gesetzt → im Viewer angezeigt + per Chat modifizierbar
 *
 * Export:
 *   - XML: mit bpmn-auto-layout Layout → kompatibel mit bpmn.io, Camunda, Signavio
 *   - SVG: gerendertes Diagramm als Vektorgrafik
 *
 * Evaluation:
 *   - Report: GZ1/GZ2/GZ4-Metriken als JSON
 *   - Traces: alle Trace-Logs als ZIP
 */

import { useRef, useState } from "react";
import { BpmnViewerHandle } from "./BpmnViewer";

type Props = {
  bpmnXml: string | null;
  sessionId: string | null;
  viewerRef: React.RefObject<BpmnViewerHandle>;
  onImport: (xml: string) => void;
  mode: "view" | "edit";
  onModeChange: (mode: "view" | "edit") => void | Promise<void>;
};

const BACKEND = "http://localhost:8000";

export default function ExportBar({ bpmnXml, sessionId, viewerRef, onImport, mode, onModeChange }: Props) {
  const [xmlExporting, setXmlExporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** Öffnet den Datei-Dialog und liest die gewählte .bpmn/.xml Datei. */
  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const xml = ev.target?.result as string;
      if (xml?.includes("<definitions")) {
        onImport(xml);
      } else {
        alert("Keine gültige BPMN-Datei. Die Datei muss ein <definitions>-Element enthalten.");
      }
    };
    reader.readAsText(file, "utf-8");
    // Input zurücksetzen damit dieselbe Datei erneut geladen werden kann
    e.target.value = "";
  };

  /** Lädt einen String als Datei herunter. */
  const download = (content: string, filename: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  /**
   * BPMN-XML mit DI herunterladen.
   * bpmn-auto-layout wird ausgeführt damit das XML einen BPMNDiagram-Abschnitt
   * enthält und in externen Tools (bpmn.io, Camunda Modeler) geöffnet werden kann.
   */
  const handleDownloadXml = async () => {
    if (!bpmnXml) return;
    setXmlExporting(true);
    try {
      const { layoutProcess } = await import("bpmn-auto-layout");
      const laidOutXml = await layoutProcess(bpmnXml);
      const filename = sessionId ? `${sessionId.slice(0, 8)}.bpmn` : "model.bpmn";
      download(laidOutXml, filename, "application/xml");
    } catch (e) {
      console.error("XML-Export fehlgeschlagen:", e);
      // Fallback: rohes XML ohne DI
      download(bpmnXml, "model.bpmn", "application/xml");
    } finally {
      setXmlExporting(false);
    }
  };

  /** SVG-Export via bpmn-js saveSVG(). */
  const handleDownloadSvg = async () => {
    if (!viewerRef.current) return;
    try {
      const { svg } = await viewerRef.current.saveSVG();
      const filename = sessionId ? `${sessionId.slice(0, 8)}.svg` : "model.svg";
      download(svg, filename, "image/svg+xml");
    } catch (e) {
      console.error("SVG-Export fehlgeschlagen:", e);
    }
  };

  /** Evaluationsbericht (GZ1/GZ2/GZ4) vom Backend laden und herunterladen. */
  const handleDownloadReport = async () => {
    try {
      const res = await fetch(`${BACKEND}/api/export/report`);
      if (!res.ok) throw new Error(await res.text());
      const json = await res.json();
      download(JSON.stringify(json, null, 2), "evaluation_report.json", "application/json");
    } catch (e) {
      alert(`Report-Export fehlgeschlagen: ${e}`);
    }
  };

  /** Alle Trace-Logs als ZIP herunterladen. */
  const handleDownloadTraces = () => {
    window.open(`${BACKEND}/api/export/traces`, "_blank");
  };

  const btnBase =
    "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const btnPrimary = `${btnBase} bg-gray-700 hover:bg-gray-600 text-gray-100`;
  const btnGreen = `${btnBase} bg-emerald-800 hover:bg-emerald-700 text-emerald-100`;

  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700 bg-gray-900 flex-wrap">

      {/* Versteckter File-Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".bpmn,.xml"
        className="hidden"
        onChange={handleImport}
      />

      {/* Import */}
      <button
        onClick={() => fileInputRef.current?.click()}
        className={`${btnBase} bg-blue-800 hover:bg-blue-700 text-blue-100`}
        title="BPMN-Datei importieren (.bpmn oder .xml)"
      >
        Import
      </button>

      <span className="text-gray-600">|</span>

      {/* Modus-Toggle */}
      <button
        onClick={() => onModeChange(mode === "view" ? "edit" : "view")}
        disabled={!bpmnXml}
        className={`${btnBase} ${
          mode === "edit"
            ? "bg-orange-700 hover:bg-orange-600 text-orange-100 ring-1 ring-orange-400"
            : "bg-gray-700 hover:bg-gray-600 text-gray-100"
        }`}
        title={mode === "edit" ? "Zurück zum KI-Modus" : "Manuell bearbeiten (bpmn-js Modeler)"}
      >
        {mode === "edit" ? "✎ Manuell (aktiv)" : "✎ Manuell"}
      </button>

      <span className="text-gray-600">|</span>
      <span className="text-xs text-gray-500">Export:</span>

      <button
        onClick={handleDownloadXml}
        disabled={!bpmnXml || xmlExporting}
        className={btnPrimary}
        title="BPMN 2.0 XML mit Layout herunterladen (kompatibel mit bpmn.io, Camunda)"
      >
        {xmlExporting ? "..." : "XML (.bpmn)"}
      </button>

      <button
        onClick={handleDownloadSvg}
        disabled={!bpmnXml}
        className={btnPrimary}
        title="Diagramm als Vektorgrafik herunterladen"
      >
        SVG
      </button>

      <span className="text-gray-600">|</span>

      <button
        onClick={handleDownloadReport}
        className={btnGreen}
        title="GZ1/GZ2/GZ4-Metriken als JSON"
      >
        Eval-Report
      </button>

      <button
        onClick={handleDownloadTraces}
        className={btnGreen}
        title="Alle Trace-Logs als ZIP"
      >
        Traces (.zip)
      </button>
    </div>
  );
}
