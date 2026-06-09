"use client";

/**
 * ExportBar – Toolbar mit Import, Export und Evaluations-Buttons.
 *
 * Import:   BPMN-Datei (.bpmn/.xml) laden → im Viewer anzeigen + per Chat modifizierbar
 * Export:   XML (mit bpmn-auto-layout DI) und SVG
 * Eval:     Session-Stats der aktuellen Session als Popup (Iterationen, Validierungen)
 *           Traces-ZIP: alle Logs herunterladen
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

type SessionStats = {
  session_id: string;
  total_iterations: number;
  termination_reason: string;
  final_status: string;
  syntax_checks: { passed: number; total: number };
  soundness_checks: { passed: number; total: number };
  timestamp: string;
};

const BACKEND = "http://localhost:8000";

export default function ExportBar({ bpmnXml, sessionId, viewerRef, onImport, mode, onModeChange }: Props) {
  const [xmlExporting, setXmlExporting] = useState(false);
  const [sessionStats, setSessionStats] = useState<SessionStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /** Liest die ausgewählte BPMN-Datei als UTF-8-Text und gibt das XML an die Elternkomponente. */
  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const xml = ev.target?.result as string;
      // Minimale Validierung: BPMN-Datei muss <definitions>-Root-Element enthalten
      if (xml?.includes("<definitions")) {
        onImport(xml);
      } else {
        alert("Keine gültige BPMN-Datei. Die Datei muss ein <definitions>-Element enthalten.");
      }
    };
    reader.readAsText(file, "utf-8");
    e.target.value = "";  // Reset damit dieselbe Datei erneut importiert werden kann
  };

  /** Universelle Download-Hilfsfunktion via Blob-URL (kein Server-Roundtrip nötig). */
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
   * XML-Export: bpmn-auto-layout fügt DI-Koordinaten hinzu, damit die Datei
   * in externen Tools (bpmn.io, Camunda Modeler) korrekt gerendert wird.
   * Falls bpmn-auto-layout fehlschlägt, wird das rohe XML ohne DI exportiert.
   */
  const handleDownloadXml = async () => {
    if (!bpmnXml) return;
    setXmlExporting(true);
    try {
      const { layoutProcess } = await import("bpmn-auto-layout");
      const laidOutXml = await layoutProcess(bpmnXml);
      download(laidOutXml, sessionId ? `${sessionId.slice(0, 8)}.bpmn` : "model.bpmn", "application/xml");
    } catch {
      download(bpmnXml, "model.bpmn", "application/xml");
    } finally {
      setXmlExporting(false);
    }
  };

  /** SVG-Export direkt aus der bpmn-js Canvas-Instanz (Vektorgrafik für Masterarbeit-Anhang). */
  const handleDownloadSvg = async () => {
    if (!viewerRef.current) return;
    try {
      const { svg } = await viewerRef.current.saveSVG();
      download(svg, sessionId ? `${sessionId.slice(0, 8)}.svg` : "model.svg", "image/svg+xml");
    } catch (e) {
      console.error("SVG-Export fehlgeschlagen:", e);
    }
  };

  /** Session-Stats laden und als Popup anzeigen. */
  const handleShowSessionStats = async () => {
    if (sessionStats) { setSessionStats(null); return; }
    if (!sessionId) return;
    setStatsLoading(true);
    try {
      const res = await fetch(`${BACKEND}/api/export/traces/${sessionId}`);
      if (!res.ok) throw new Error(await res.text());
      const trace = await res.json();
      const validations: Array<{ validation_type: string; passed: boolean }> =
        trace.validation_entries ?? [];
      const syntax = validations.filter((v) => v.validation_type === "syntax");
      const soundness = validations.filter((v) => v.validation_type === "soundness");
      setSessionStats({
        session_id: trace.session_id,
        total_iterations: trace.process_entry?.total_iterations ?? "?",
        termination_reason: trace.process_entry?.termination_reason ?? "?",
        final_status: trace.process_entry?.final_status ?? "?",
        syntax_checks: { passed: syntax.filter((v) => v.passed).length, total: syntax.length },
        soundness_checks: { passed: soundness.filter((v) => v.passed).length, total: soundness.length },
        timestamp: trace.process_entry?.timestamp ?? "",
      } as unknown as SessionStats);
    } catch (e) {
      alert(`Stats konnten nicht geladen werden: ${e}`);
    } finally {
      setStatsLoading(false);
    }
  };

  const handleDownloadTraces = () => {
    window.open(`${BACKEND}/api/export/traces`, "_blank");
  };

  const btnBase = "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const btnGray = `${btnBase} bg-gray-700 hover:bg-gray-600 text-gray-100`;
  const btnGreen = `${btnBase} bg-emerald-800 hover:bg-emerald-700 text-emerald-100`;

  return (
    <div className="relative">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700 bg-gray-900 flex-wrap">

        <input ref={fileInputRef} type="file" accept=".bpmn,.xml" className="hidden" onChange={handleImport} />

        <button onClick={() => fileInputRef.current?.click()}
          className={`${btnBase} bg-blue-800 hover:bg-blue-700 text-blue-100`}
          title="BPMN-Datei importieren">
          Import
        </button>

        <span className="text-gray-600">|</span>

        <button
          onClick={() => onModeChange(mode === "view" ? "edit" : "view")}
          disabled={!bpmnXml}
          className={`${btnBase} ${mode === "edit"
            ? "bg-orange-700 hover:bg-orange-600 text-orange-100 ring-1 ring-orange-400"
            : "bg-gray-700 hover:bg-gray-600 text-gray-100"}`}
          title={mode === "edit" ? "Zurück zum KI-Modus" : "Manuell bearbeiten"}>
          {mode === "edit" ? "✎ Manuell (aktiv)" : "✎ Manuell"}
        </button>

        <span className="text-gray-600">|</span>
        <span className="text-xs text-gray-500">Export:</span>

        <button onClick={handleDownloadXml} disabled={!bpmnXml || xmlExporting}
          className={btnGray} title="BPMN 2.0 XML mit Layout (kompatibel mit bpmn.io, Camunda)">
          {xmlExporting ? "..." : "XML (.bpmn)"}
        </button>

        <button onClick={handleDownloadSvg} disabled={!bpmnXml}
          className={btnGray} title="Diagramm als Vektorgrafik">
          SVG
        </button>

        <span className="text-gray-600">|</span>

        {/* Eval-Report: Session-Stats Popup wenn Session aktiv, sonst deaktiviert */}
        <button
          onClick={handleShowSessionStats}
          disabled={!sessionId || statsLoading}
          className={`${btnGreen} ${sessionStats ? "ring-1 ring-emerald-400" : ""}`}
          title={sessionId ? "Statistiken der aktuellen Session anzeigen" : "Noch keine Session aktiv"}>
          {statsLoading ? "..." : "Eval-Report"}
        </button>

        <button onClick={handleDownloadTraces} className={btnGreen}
          title="Alle Trace-Logs als ZIP herunterladen">
          Traces (.zip)
        </button>
      </div>

      {/* Session-Stats Popup */}
      {sessionStats && (
        <div className="absolute top-full left-0 right-0 z-30 bg-gray-900 border border-emerald-700 rounded-b-lg shadow-xl p-4 text-xs">
          <div className="flex justify-between items-start mb-3">
            <span className="font-semibold text-emerald-400">Session-Statistiken</span>
            <button onClick={() => setSessionStats(null)} className="text-gray-500 hover:text-gray-200 text-base leading-none">✕</button>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-gray-300">
            <span className="text-gray-500">Session-ID</span>
            <span className="font-mono">{sessionStats.session_id.slice(0, 8)}…</span>

            <span className="text-gray-500">Iterationen</span>
            <span>{sessionStats.total_iterations}</span>

            <span className="text-gray-500">Abschluss</span>
            <span className={sessionStats.termination_reason === "success" ? "text-emerald-400" : "text-red-400"}>
              {sessionStats.termination_reason}
            </span>

            <span className="text-gray-500">Finaler Status</span>
            <span className={sessionStats.final_status === "valid_and_sound" ? "text-emerald-400" : "text-red-400"}>
              {sessionStats.final_status}
            </span>

            <span className="text-gray-500">Syntax-Checks</span>
            <span>{sessionStats.syntax_checks.passed}/{sessionStats.syntax_checks.total} bestanden</span>

            <span className="text-gray-500">Soundness-Checks</span>
            <span>{sessionStats.soundness_checks.passed}/{sessionStats.soundness_checks.total} bestanden</span>
          </div>
        </div>
      )}
    </div>
  );
}
