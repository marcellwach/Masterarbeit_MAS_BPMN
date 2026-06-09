"use client";

/**
 * Validator-Seite – manuelle BPMN-XML-Prüfung für beliebige LLMs.
 *
 * Workflow:
 *   1. BPMN-XML in das Textarea einfügen (z.B. Output von GPT-4o, Gemini, etc.)
 *   2. Optionale Bezeichnung eingeben (z.B. "GPT-4o Versuch 1")
 *   3. "Prüfen" klicken → POST /api/validate
 *   4. Detaillierte Auswertung: Syntax, Soundness, Statistiken, Empfehlungen
 *   5. Ergebnisse können als JSON exportiert oder für Vergleiche gesammelt werden
 */

import { useState } from "react";
import Link from "next/link";

const BACKEND = "http://localhost:8000";

type Violation = {
  error_type: string;
  affected_elements: string[];
  description: string;
};

type ValidationResult = {
  label: string;
  is_valid: boolean;
  is_sound: boolean;
  validation_timestamp: string;
  duration_seconds: number;
  xml_stats: {
    start_events: number;
    end_events: number;
    tasks: number;
    gateways: number;
    sequence_flows: number;
    has_di: boolean;
  };
  violations: Violation[];
  syntax_violations_count: number;
  semantic_violations_count: number;
  summary: string[];
};

type HistoryEntry = ValidationResult & { id: number };

// Leserfreundliche Bezeichnungen für die ErrorType-Enum-Werte aus dem Backend
const ERROR_TYPE_LABELS: Record<string, string> = {
  syntax_xsd: "XSD-Syntaxfehler",
  syntax_metamodel: "Metamodell-Verletzung",
  semantic_soundness: "Soundness-Verletzung",
  semantic_deadlock: "Deadlock",
  semantic_unreachable: "Nicht erreichbarer Zustand",
};

export default function ValidatePage() {
  const [xml, setXml] = useState("");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  /**
   * Sendet das BPMN-XML an POST /api/validate und speichert das Ergebnis.
   * Fügt das Ergebnis außerdem dem lokalen Verlauf hinzu, damit mehrere
   * LLM-Outputs nebeneinander verglichen werden können.
   */
  const handleValidate = async () => {
    if (!xml.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${BACKEND}/api/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ xml: xml.trim(), label: label.trim() || "Ohne Bezeichnung" }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
      }

      const data: ValidationResult = await res.json();
      setResult(data);
      setHistory((prev) => [{ ...data, id: Date.now() }, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  /**
   * Exportiert alle Validierungsergebnisse der aktuellen Sitzung als JSON.
   * Nützlich für den Vergleich mehrerer LLM-Outputs in der Masterarbeit-Auswertung.
   */
  const downloadHistory = () => {
    const blob = new Blob([JSON.stringify(history, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "validation_results.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const statusBadge = (ok: boolean, label: string) => (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold ${
      ok ? "bg-green-900/60 text-green-300 border border-green-700"
         : "bg-red-900/60 text-red-300 border border-red-700"
    }`}>
      {ok ? "✓" : "✗"} {label}
    </span>
  );

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">

      {/* Navigation */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between bg-gray-900">
        <div>
          <h1 className="font-bold text-lg">BPMN Validator</h1>
          <p className="text-xs text-gray-400">Syntax- & Soundness-Prüfung für beliebige LLM-Outputs</p>
        </div>
        <Link href="/"
          className="text-sm px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors">
          ← Zurück zum Generator
        </Link>
      </header>

      <div className="flex flex-1 gap-0 overflow-hidden">

        {/* Linke Spalte: Input */}
        <div className="w-[45%] flex flex-col border-r border-gray-800 p-5 gap-4">

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-gray-400 mb-1 block">Bezeichnung (optional)</label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="z.B. GPT-4o Versuch 1, Claude direkt, ..."
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm
                           focus:outline-none focus:border-blue-500 placeholder-gray-500"
              />
            </div>
          </div>

          <div className="flex-1 flex flex-col gap-2">
            <label className="text-xs text-gray-400">BPMN 2.0 XML</label>
            <textarea
              value={xml}
              onChange={(e) => setXml(e.target.value)}
              placeholder={'<?xml version="1.0" encoding="UTF-8"?>\n<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" ...>\n  ...\n</definitions>'}
              className="flex-1 font-mono text-xs bg-gray-900 border border-gray-700 rounded-lg p-3
                         focus:outline-none focus:border-blue-500 resize-none text-gray-200
                         placeholder-gray-600"
              spellCheck={false}
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleValidate}
              disabled={loading || !xml.trim()}
              className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                         disabled:text-gray-500 rounded-lg font-semibold text-sm transition-colors"
            >
              {loading ? "Prüfung läuft..." : "Prüfen"}
            </button>
            <button
              onClick={() => { setXml(""); setResult(null); setLabel(""); setError(null); }}
              className="px-4 py-2.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
            >
              Leeren
            </button>
          </div>

          {/* Verlauf */}
          {history.length > 0 && (
            <div className="border-t border-gray-800 pt-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400 font-medium">
                  Verlauf ({history.length} Prüfungen)
                </span>
                <button onClick={downloadHistory}
                  className="text-xs px-2 py-1 bg-emerald-800 hover:bg-emerald-700 rounded-lg text-emerald-200">
                  JSON exportieren
                </button>
              </div>
              <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
                {history.map((h) => (
                  <button
                    key={h.id}
                    onClick={() => setResult(h)}
                    className="text-left px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs transition-colors"
                  >
                    <span className={h.is_valid && h.is_sound ? "text-green-400" : "text-red-400"}>
                      {h.is_valid && h.is_sound ? "✓" : "✗"}
                    </span>
                    <span className="ml-2 text-gray-200">{h.label}</span>
                    <span className="ml-2 text-gray-500">{h.duration_seconds}s</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Rechte Spalte: Ergebnis */}
        <div className="flex-1 p-5 overflow-y-auto">

          {error && (
            <div className="bg-red-900/40 border border-red-700 rounded-lg p-4 text-red-300 text-sm mb-4">
              <p className="font-bold mb-1">Fehler:</p>
              <p className="font-mono">{error}</p>
            </div>
          )}

          {!result && !error && !loading && (
            <div className="h-full flex items-center justify-center text-gray-600">
              <div className="text-center">
                <div className="text-5xl mb-3">⬡</div>
                <p className="text-lg">BPMN-XML links einfügen und prüfen</p>
                <p className="text-sm mt-1">Funktioniert mit Outputs von GPT-4o, Gemini, Llama, etc.</p>
              </div>
            </div>
          )}

          {loading && (
            <div className="h-full flex items-center justify-center">
              <div className="text-center text-gray-400">
                <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
                <p>Syntaxprüfung + Woflan Soundness läuft...</p>
              </div>
            </div>
          )}

          {result && !loading && (
            <div className="flex flex-col gap-5">

              {/* Status-Übersicht */}
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="font-bold text-lg">{result.label}</h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {new Date(result.validation_timestamp).toLocaleString("de-DE")} · {result.duration_seconds}s
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {statusBadge(result.is_valid, "Syntaktisch valide")}
                    {statusBadge(result.is_sound, "Semantisch sound")}
                  </div>
                </div>

                {/* Ampel-Gesamturteil */}
                <div className={`rounded-lg p-4 text-sm font-medium ${
                  result.is_valid && result.is_sound
                    ? "bg-green-900/30 border border-green-800 text-green-300"
                    : "bg-red-900/30 border border-red-800 text-red-300"
                }`}>
                  {result.is_valid && result.is_sound
                    ? "✓ Dieses BPMN-Modell ist vollständig korrekt – syntaktisch valide und semantisch sound."
                    : `✗ Das Modell enthält ${result.violations.length} Fehler und ist nicht produktionsreif.`}
                </div>
              </div>

              {/* Modell-Statistiken */}
              {result.xml_stats && Object.keys(result.xml_stats).length > 0 && (
                <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                  <h3 className="font-semibold mb-3 text-sm text-gray-300">Modell-Statistiken</h3>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      ["Start-Events", result.xml_stats.start_events],
                      ["End-Events", result.xml_stats.end_events],
                      ["Tasks", result.xml_stats.tasks],
                      ["Gateways", result.xml_stats.gateways],
                      ["Sequence Flows", result.xml_stats.sequence_flows],
                      ["DI vorhanden", result.xml_stats.has_di ? "Ja" : "Nein"],
                    ].map(([k, v]) => (
                      <div key={String(k)} className="bg-gray-800 rounded-lg px-3 py-2 text-center">
                        <p className="text-lg font-bold text-white">{v}</p>
                        <p className="text-xs text-gray-400 mt-0.5">{k}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Syntax-Prüfung */}
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-sm text-gray-300">Syntaxprüfung</h3>
                  {statusBadge(result.is_valid, result.is_valid ? "Bestanden" : "Fehlgeschlagen")}
                </div>
                <p className="text-xs text-gray-500 mb-3">
                  Geprüft: XML-Wohlgeformtheit · Referenzintegrität (sourceRef/targetRef)
                </p>
                {result.syntax_violations_count === 0 ? (
                  <p className="text-green-400 text-sm">Keine Syntaxfehler gefunden.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {result.violations
                      .filter(v => v.error_type.startsWith("syntax"))
                      .map((v, i) => (
                        <div key={i} className="bg-red-950/40 border border-red-900 rounded-lg p-3 text-xs">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-0.5 bg-red-800/60 text-red-300 rounded font-mono">
                              {ERROR_TYPE_LABELS[v.error_type] ?? v.error_type}
                            </span>
                            {v.affected_elements.length > 0 && (
                              <span className="text-gray-400">
                                Elemente: {v.affected_elements.join(", ")}
                              </span>
                            )}
                          </div>
                          <p className="text-red-200">{v.description}</p>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* Soundness-Prüfung */}
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-sm text-gray-300">Soundness-Prüfung (Woflan)</h3>
                  {statusBadge(result.is_sound, result.is_sound ? "Bestanden" : "Fehlgeschlagen")}
                </div>
                <p className="text-xs text-gray-500 mb-3">
                  Algorithmus: Woflan · Methode: BPMN→Petri-Netz (Dijkman et al. 2008) via pm4py<br/>
                  Prüft: Erreichbarkeit des Endzustands · Deadlock-Freiheit · Keine toten Transitionen
                </p>
                {!result.is_valid ? (
                  <p className="text-gray-500 text-sm italic">
                    Soundness-Prüfung übersprungen – Syntaxfehler müssen zuerst behoben werden.
                  </p>
                ) : result.semantic_violations_count === 0 ? (
                  <p className="text-green-400 text-sm">Prozess ist sound.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {result.violations
                      .filter(v => v.error_type.startsWith("semantic"))
                      .map((v, i) => (
                        <div key={i} className="bg-orange-950/40 border border-orange-900 rounded-lg p-3 text-xs">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-0.5 bg-orange-800/60 text-orange-300 rounded font-mono">
                              {ERROR_TYPE_LABELS[v.error_type] ?? v.error_type}
                            </span>
                          </div>
                          <p className="text-orange-200">{v.description}</p>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* Zusammenfassung */}
              {result.summary.length > 0 && (
                <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                  <h3 className="font-semibold text-sm text-gray-300 mb-3">Auswertung</h3>
                  <div className="font-mono text-xs text-gray-300 flex flex-col gap-1">
                    {result.summary.map((line, i) => (
                      <p key={i} className={line.startsWith("  ") ? "text-gray-500 pl-4" : ""}>{line}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* JSON-Export dieser Prüfung */}
              <button
                onClick={() => {
                  const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `validation_${result.label.replace(/\s+/g, "_")}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="w-full py-2.5 bg-gray-800 hover:bg-gray-700 rounded-xl text-sm
                           text-gray-300 font-medium transition-colors"
              >
                Diese Prüfung als JSON exportieren
              </button>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
