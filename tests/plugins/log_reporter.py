"""
log_reporter.py
===============
Plugin de pytest que genera logs separados por archivo de test
y un resumen general al finalizar la sesión.

Estructura de salida:
    tests/logs/
        summary.log                        ← resumen de toda la sesión
        functional/
            test_automation_engine.log     ← resultados de cada archivo
            test_campaign.log
            ...
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

# Raíz de logs relativa al directorio de tests
LOGS_ROOT = Path(__file__).parent.parent / "logs"


# ─────────────────────────────────────────────
# Modelo interno de resultado
# ─────────────────────────────────────────────
class _TestResult:
    def __init__(self, name: str, outcome: str, duration: float, error: str | None):
        self.name = name
        self.outcome = outcome       # PASSED | FAILED | ERROR | SKIPPED
        self.duration = duration
        self.error = error


# ─────────────────────────────────────────────
# Plugin principal
# ─────────────────────────────────────────────
class LogReporter:

    def __init__(self):
        # file_path (str) → lista de resultados
        self._results: Dict[str, List[_TestResult]] = defaultdict(list)
        self._session_start: datetime | None = None

    # ── Hooks ────────────────────────────────

    def pytest_sessionstart(self, session):
        self._session_start = datetime.now()
        LOGS_ROOT.mkdir(parents=True, exist_ok=True)
        (LOGS_ROOT / "functional").mkdir(parents=True, exist_ok=True)

    def pytest_runtest_logreport(self, report):
        """Captura el resultado de cada test (solo la fase 'call' o setup fallido)."""
        if report.when == "call" or (report.when == "setup" and report.failed):
            file_path, _, test_name = report.nodeid.partition("::")

            if report.passed:
                outcome = "PASSED"
            elif report.failed:
                outcome = "FAILED" if report.when == "call" else "ERROR"
            elif report.skipped:
                outcome = "SKIPPED"
            else:
                outcome = "UNKNOWN"

            duration = getattr(report, "duration", 0.0) or 0.0

            error_text = None
            if report.failed and report.longrepr:
                raw = str(report.longrepr)
                # Limitamos a las últimas 40 líneas para no inflar los logs
                lines = raw.splitlines()
                if len(lines) > 40:
                    lines = ["... (truncado, ver pytest output para detalle completo) ..."] + lines[-40:]
                error_text = "\n".join(lines)

            self._results[file_path].append(
                _TestResult(test_name, outcome, duration, error_text)
            )

    def pytest_sessionfinish(self, session, exitstatus):
        now = datetime.now()
        file_summaries = []

        total_passed = total_failed = total_skipped = 0

        # ── Logs individuales por archivo ────
        for file_path, results in sorted(self._results.items()):
            passed  = sum(1 for r in results if r.outcome == "PASSED")
            failed  = sum(1 for r in results if r.outcome in ("FAILED", "ERROR"))
            skipped = sum(1 for r in results if r.outcome == "SKIPPED")
            total   = len(results)

            total_passed  += passed
            total_failed  += failed
            total_skipped += skipped

            log_path = _resolve_log_path(file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            with open(log_path, "w", encoding="utf-8") as f:
                _write_file_header(f, file_path, now, passed, failed, skipped)

                for r in results:
                    icon = {"PASSED": "✓", "FAILED": "✗", "ERROR": "✗", "SKIPPED": "○"}.get(r.outcome, "?")
                    f.write(f"  {icon} [{r.outcome:<8}] {r.name}  ({r.duration:.3f}s)\n")
                    if r.error:
                        f.write("\n")
                        for line in r.error.splitlines():
                            f.write(f"      {line}\n")
                        f.write("\n")

                _write_file_footer(f, passed, failed, total)

            file_summaries.append({
                "file":    file_path,
                "log":     log_path,
                "passed":  passed,
                "failed":  failed,
                "skipped": skipped,
                "results": results,
            })

        # ── Summary global ───────────────────
        summary_path = LOGS_ROOT / "summary.log"
        duration_total = (now - self._session_start).total_seconds() if self._session_start else 0

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("  RESUMEN DE TESTS\n")
            f.write(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}  |  duración: {duration_total:.1f}s\n")
            f.write(f"  Total: {total_passed} pasaron  │  {total_failed} fallaron  │  {total_skipped} omitidos\n")
            f.write("=" * 70 + "\n\n")

            for s in file_summaries:
                total = s["passed"] + s["failed"] + s["skipped"]
                status_icon = "✓" if s["failed"] == 0 else "✗"
                status_label = "OK    " if s["failed"] == 0 else "FALLO "
                file_name = Path(s["file"]).name
                rel_log = s["log"].relative_to(LOGS_ROOT.parent)

                f.write(f"  {status_icon} {status_label}  {file_name:<48}  [{s['passed']:>3}/{total:<3}]  →  {rel_log}\n")

                # Detalle de los fallidos en el summary
                for r in s["results"]:
                    if r.outcome in ("FAILED", "ERROR"):
                        f.write(f"              ✗ {r.name}\n")

            f.write("\n" + "=" * 70 + "\n")

        # Imprimir ubicación al final de la corrida
        print(f"\n\n📋 Logs guardados en: {LOGS_ROOT}")
        print(f"   Resumen general : {summary_path}")


# ─────────────────────────────────────────────
# Helpers privados
# ─────────────────────────────────────────────

def _resolve_log_path(file_path: str) -> Path:
    """
    Convierte el nodeid de archivo a la ruta de log correspondiente.
    Ej: 'tests/functional/test_x.py' → LOGS_ROOT/functional/test_x.log
    """
    parts = Path(file_path).parts
    stem  = Path(file_path).stem  # 'test_x'

    if "functional" in parts:
        return LOGS_ROOT / "functional" / f"{stem}.log"
    else:
        return LOGS_ROOT / f"{stem}.log"


def _write_file_header(f, file_path, now, passed, failed, skipped):
    name = Path(file_path).name
    f.write("=" * 70 + "\n")
    f.write(f"  {name}\n")
    f.write(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"  {passed} pasaron  │  {failed} fallaron  │  {skipped} omitidos\n")
    f.write("=" * 70 + "\n\n")


def _write_file_footer(f, passed, failed, total):
    f.write("\n" + "-" * 70 + "\n")
    symbol = "✓" if failed == 0 else "✗"
    f.write(f"  {symbol}  {passed}/{total} tests pasaron\n")


# ─────────────────────────────────────────────
# Registro del plugin
# ─────────────────────────────────────────────

def pytest_configure(config):
    config.pluginmanager.register(LogReporter(), "log_reporter")
