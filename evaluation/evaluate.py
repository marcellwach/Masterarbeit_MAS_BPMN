"""
Evaluationsskript – liest Trace-Logs aus traces/ und berechnet GZ1/GZ2/GZ4.

Aufruf:
    python evaluation/evaluate.py --traces-dir traces/ --output report.json
"""

import argparse
import json
from pathlib import Path
from datetime import datetime


def load_traces(traces_dir: Path) -> list[dict]:
    logs = []
    for path in sorted(traces_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_file"] = path.name
            logs.append(data)
        except Exception as e:
            print(f"  Warnung: {path.name} konnte nicht geladen werden: {e}")
    return logs


def eval_gz1(logs: list[dict]) -> dict:
    """GZ1 – Syntaktische Konformität: Anteil syntaktisch valider Outputs."""
    total_syntax_checks = 0
    passed_syntax_checks = 0

    for log in logs:
        for entry in log.get("validation_entries", []):
            if entry.get("validation_type") == "syntax":
                total_syntax_checks += 1
                if entry.get("passed"):
                    passed_syntax_checks += 1

    rate = passed_syntax_checks / total_syntax_checks if total_syntax_checks > 0 else None
    return {
        "metric": "GZ1 – Syntaktische Konformität",
        "total_syntax_checks": total_syntax_checks,
        "passed": passed_syntax_checks,
        "rate": round(rate, 4) if rate is not None else None,
        "target": "1.0 (100% durch DP2)"
    }


def eval_gz2(logs: list[dict]) -> dict:
    """GZ2 – Semantische Korrektheit: Anteil sounder Modelle nach Abschluss."""
    total_sessions = len(logs)
    sound_sessions = 0
    success_sessions = 0

    for log in logs:
        process = log.get("process_entry")
        if not process:
            continue
        if process.get("termination_reason") == "success":
            success_sessions += 1
            if process.get("final_status") == "valid_and_sound":
                sound_sessions += 1

    rate = sound_sessions / total_sessions if total_sessions > 0 else None
    convergence = success_sessions / total_sessions if total_sessions > 0 else None
    return {
        "metric": "GZ2 – Semantische Korrektheit",
        "total_sessions": total_sessions,
        "sound_sessions": sound_sessions,
        "convergence_rate": round(convergence, 4) if convergence is not None else None,
        "soundness_rate": round(rate, 4) if rate is not None else None,
    }


def eval_gz4(logs: list[dict]) -> dict:
    """GZ4 – Traceability: Vollständigkeit der Logs (alle drei Ebenen vorhanden)."""
    total = len(logs)
    complete = 0
    missing_details = []

    for log in logs:
        has_output = len(log.get("output_entries", [])) > 0
        has_validation = len(log.get("validation_entries", [])) > 0
        has_process = log.get("process_entry") is not None

        if has_output and has_validation and has_process:
            complete += 1
        else:
            missing = []
            if not has_output: missing.append("output_entries")
            if not has_validation: missing.append("validation_entries")
            if not has_process: missing.append("process_entry")
            missing_details.append({"file": log.get("_file"), "missing": missing})

    rate = complete / total if total > 0 else None
    result = {
        "metric": "GZ4 – Traceability",
        "total_sessions": total,
        "complete_logs": complete,
        "completeness_rate": round(rate, 4) if rate is not None else None,
        "target": "1.0 (alle drei Ebenen vollständig)"
    }
    if missing_details:
        result["incomplete"] = missing_details
    return result


def avg_iterations(logs: list[dict]) -> dict:
    """Durchschnittliche Iterationszahl bis zur Konvergenz."""
    iterations = []
    for log in logs:
        process = log.get("process_entry")
        if process and process.get("termination_reason") == "success":
            iterations.append(process.get("total_iterations", 0))

    if not iterations:
        return {"avg_iterations_on_success": None, "min": None, "max": None}
    return {
        "avg_iterations_on_success": round(sum(iterations) / len(iterations), 2),
        "min": min(iterations),
        "max": max(iterations),
        "samples": len(iterations)
    }


def markdown_table(results: list[dict]) -> str:
    lines = [
        "# Evaluationsbericht – MAS BPMN Generator",
        f"\nErstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Sessions ausgewertet: {results[0]['gz1']['total_syntax_checks']} Syntax-Checks, "
        f"{results[0]['gz2']['total_sessions']} Sessions\n",
        "| Metrik | Wert | Zielwert |",
        "|--------|------|----------|",
        f"| GZ1 Syntaktische Konformität | {_fmt(results[0]['gz1']['rate'])} | 1.0 |",
        f"| GZ2 Konvergenzrate | {_fmt(results[0]['gz2']['convergence_rate'])} | – |",
        f"| GZ2 Soundness-Rate | {_fmt(results[0]['gz2']['soundness_rate'])} | – |",
        f"| GZ4 Log-Vollständigkeit | {_fmt(results[0]['gz4']['completeness_rate'])} | 1.0 |",
        f"| Ø Iterationen (Erfolg) | {results[0]['iterations']['avg_iterations_on_success']} | ≤5 |",
    ]
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return "–"
    return f"{v * 100:.1f}%"


def main():
    parser = argparse.ArgumentParser(description="MAS BPMN Evaluationsskript")
    parser.add_argument("--traces-dir", default="traces/", help="Verzeichnis mit Trace-JSON-Dateien")
    parser.add_argument("--output", default="report.json", help="Ausgabedatei (JSON)")
    args = parser.parse_args()

    traces_dir = Path(args.traces_dir)
    if not traces_dir.exists():
        print(f"Fehler: Verzeichnis '{traces_dir}' nicht gefunden.")
        return

    logs = load_traces(traces_dir)
    if not logs:
        print(f"Keine Trace-Logs in '{traces_dir}' gefunden.")
        return

    print(f"Auswertung von {len(logs)} Session(s)...\n")

    gz1 = eval_gz1(logs)
    gz2 = eval_gz2(logs)
    gz4 = eval_gz4(logs)
    iters = avg_iterations(logs)

    report = {
        "generated_at": datetime.now().isoformat(),
        "sessions_evaluated": len(logs),
        "gz1": gz1,
        "gz2": gz2,
        "gz4": gz4,
        "iterations": iters,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = markdown_table([report])
    md_path = output_path.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")

    print(md)
    print(f"\nJSON-Report: {output_path}")
    print(f"Markdown-Report: {md_path}")


if __name__ == "__main__":
    main()
