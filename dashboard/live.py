"""
Store Intelligence — Live Terminal Dashboard
Polls the API every 5 seconds and displays real-time metrics in a rich table.

Usage:
    python dashboard/live.py --store ST1008 --api http://localhost:8000
"""
from __future__ import annotations
import argparse
import time
from datetime import datetime

import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.align import Align
from rich import box

console = Console()


def fetch_metrics(api_url: str, store_id: str) -> dict | None:
    try:
        r = requests.get(f"{api_url}/stores/{store_id}/metrics", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def fetch_anomalies(api_url: str, store_id: str) -> list:
    try:
        r = requests.get(f"{api_url}/stores/{store_id}/anomalies", timeout=5)
        r.raise_for_status()
        return r.json().get("anomalies", [])
    except Exception:
        return []


def fetch_funnel(api_url: str, store_id: str) -> list:
    try:
        r = requests.get(f"{api_url}/stores/{store_id}/funnel", timeout=5)
        r.raise_for_status()
        return r.json().get("funnel", [])
    except Exception:
        return []


def build_metrics_table(metrics: dict) -> Table:
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", width=25)
    table.add_column("Value", style="bold green", width=20)

    if "error" in metrics:
        table.add_row("❌ API Error", str(metrics["error"]))
        return table

    conv = metrics.get("conversion_rate", 0)
    abandon = metrics.get("abandonment_rate", 0)
    queue = metrics.get("queue_depth", 0)

    conv_style = "green" if conv >= 0.25 else "yellow" if conv >= 0.15 else "red"
    queue_style = "red" if queue >= 5 else "yellow" if queue >= 3 else "green"

    table.add_row("👥 Unique Visitors",  str(metrics.get("unique_visitors", 0)))
    table.add_row("💳 Conversion Rate",  Text(f"{conv:.1%}", style=conv_style))
    table.add_row("🛒 Queue Depth",      Text(str(queue), style=queue_style))
    table.add_row("🚪 Abandonment Rate", f"{abandon:.1%}")

    dwells = metrics.get("avg_dwell_per_zone", {})
    for zone, ms in list(dwells.items())[:4]:
        secs = round(ms / 1000)
        table.add_row(f"   ⏱ {zone}", f"{secs}s avg dwell")

    return table


def build_funnel_table(funnel: list) -> Table:
    table = Table(title="Conversion Funnel", box=box.SIMPLE, show_header=True,
                  header_style="bold blue")
    table.add_column("Stage",      style="cyan",  width=18)
    table.add_column("Sessions",   style="green", width=10)
    table.add_column("Drop-off",   style="red",   width=10)

    for stage in funnel:
        drop = stage.get("drop_off_pct", 0)
        drop_str = f"{drop:.1f}%" if drop > 0 else "—"
        table.add_row(
            stage.get("stage", "").upper(),
            str(stage.get("sessions", 0)),
            drop_str,
        )
    return table


def build_anomalies_panel(anomalies: list) -> Panel:
    if not anomalies:
        content = Text("✅ No active anomalies", style="bold green")
        return Panel(content, title="Anomalies", border_style="green")

    lines = []
    severity_icons = {"CRITICAL": "🔴", "WARN": "🟡", "INFO": "🔵"}
    for a in anomalies[:5]:
        icon = severity_icons.get(a.get("severity", "INFO"), "⚪")
        lines.append(f"{icon} [{a.get('severity')}] {a.get('type')}")
        lines.append(f"   {a.get('detail', '')}")
        lines.append(f"   💡 {a.get('suggested_action', '')[:80]}")
        lines.append("")

    content = Text("\n".join(lines))
    return Panel(content, title="⚠️ Active Anomalies", border_style="red")


def main():
    parser = argparse.ArgumentParser(description="Store Intelligence Live Dashboard")
    parser.add_argument("--store", default="ST1008", help="Store ID")
    parser.add_argument("--api",   default="http://localhost:8000", help="API URL")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval (seconds)")
    args = parser.parse_args()

    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            metrics   = fetch_metrics(args.api, args.store)
            anomalies = fetch_anomalies(args.api, args.store)
            funnel    = fetch_funnel(args.api, args.store)

            updated_at = datetime.now().strftime("%H:%M:%S")

            layout = Layout()
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=3),
            )
            layout["main"].split_row(
                Layout(name="metrics", ratio=1),
                Layout(name="right",   ratio=1),
            )
            layout["right"].split_column(
                Layout(name="funnel",    ratio=1),
                Layout(name="anomalies", ratio=1),
            )

            layout["header"].update(Panel(
                Align.center(
                    Text(f"🏪 {args.store} — Store Intelligence Dashboard", style="bold white"),
                    vertical="middle",
                ),
                style="bold purple",
            ))

            layout["metrics"].update(
                Panel(build_metrics_table(metrics), title="📊 Live Metrics",
                      border_style="magenta")
            )
            layout["funnel"].update(
                Panel(build_funnel_table(funnel), title="🔽 Funnel",
                      border_style="blue")
            )
            layout["anomalies"].update(build_anomalies_panel(anomalies))
            layout["footer"].update(Panel(
                Align.center(
                    Text(f"Last updated: {updated_at} | Refreshing every {args.interval}s | "
                         f"API: {args.api}", style="dim"),
                    vertical="middle",
                )
            ))

            live.update(layout)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
