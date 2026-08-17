"""
OpenSearch Automation V2 - HTML Executive Dashboard Generator

Generates a standalone HTML dashboard embedding Chart.js interactive charts
and operational tables summarizing cleanup candidates and cluster metrics history.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
from jinja2 import Template

import config

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenSearch Automation V2 - Executive Dashboard</title>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="{{ chartjs_cdn }}"></script>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-card: rgba(30, 41, 59, 0.7);
            --border-card: rgba(255, 255, 255, 0.1);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-purple: #c084fc;
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-yellow: #fbbf24;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-main);
            padding: 24px;
            line-height: 1.5;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-card);
        }

        .header h1 {
            font-size: 26px;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header .meta {
            font-size: 13px;
            color: var(--text-muted);
        }

        .grid-2 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
            gap: 24px;
            margin-bottom: 28px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .card h2 {
            font-size: 16px;
            font-weight: 600;
            color: var(--accent-blue);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .chart-container {
            position: relative;
            height: 260px;
            width: 100%;
        }

        .table-responsive {
            width: 100%;
            overflow-x: auto;
            margin-top: 12px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }

        th {
            background-color: rgba(15, 23, 42, 0.6);
            color: var(--text-muted);
            font-weight: 600;
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-card);
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }

        td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            color: var(--text-main);
        }

        tr:hover {
            background-color: rgba(255, 255, 255, 0.03);
        }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-green { background: rgba(74, 222, 128, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .badge-yellow { background: rgba(251, 191, 36, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }
        .badge-red { background: rgba(248, 113, 113, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }
        .badge-blue { background: rgba(56, 189, 248, 0.2); color: var(--accent-blue); border: 1px solid var(--accent-blue); }

        .footer {
            margin-top: 36px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            padding-top: 16px;
            border-top: 1px solid var(--border-card);
        }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>OpenSearch Executive Dashboard</h1>
            <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Multi-Cluster Health, Cleanup Candidates & Metrics History</p>
        </div>
        <div class="meta">
            Generated: <strong>{{ generated_at }}</strong>
        </div>
    </div>

    <!-- Charts Section -->
    <div class="grid-2">
        <div class="card">
            <h2>📊 Cluster Storage (MB)</h2>
            <div class="chart-container">
                <canvas id="storageChart"></canvas>
            </div>
        </div>
        <div class="card">
            <h2>🧠 Heap Utilization (%)</h2>
            <div class="chart-container">
                <canvas id="heapChart"></canvas>
            </div>
        </div>
        <div class="card">
            <h2>💾 Disk Utilization (%)</h2>
            <div class="chart-container">
                <canvas id="diskChart"></canvas>
            </div>
        </div>
        <div class="card">
            <h2>🏆 Top Largest Indices Across Clusters</h2>
            <div class="chart-container">
                <canvas id="largestIndicesChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Tables Section -->
    <div class="card" style="margin-bottom: 28px;">
        <h2>🔍 Cleanup Candidates</h2>
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Cluster</th>
                        <th>Index</th>
                        <th>Size (MB)</th>
                        <th>Docs</th>
                        <th>Age (Days)</th>
                        <th>Reason</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in cleanup_rows %}
                    <tr>
                        <td><strong>{{ row['Cluster'] }}</strong></td>
                        <td><code>{{ row['Index'] }}</code></td>
                        <td>{{ row['Size (MB)'] }}</td>
                        <td>{{ row['Documents'] }}</td>
                        <td>{{ row['Age (Days)'] }}</td>
                        <td style="color: var(--text-muted);">{{ row['Reason'] }}</td>
                        <td>
                            {% if 'DELETE' in row['Action'] or 'DELETED' in row['Action'] %}
                                <span class="badge badge-red">{{ row['Action'] }}</span>
                            {% elif 'REPORT' in row['Action'] %}
                                <span class="badge badge-blue">{{ row['Action'] }}</span>
                            {% else %}
                                <span class="badge badge-yellow">{{ row['Action'] }}</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="7" style="text-align: center; color: var(--text-muted);">No cleanup candidates found.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <h2>🖥️ Cluster Metrics Overview</h2>
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Cluster</th>
                        <th>Status</th>
                        <th>Active Shards</th>
                        <th>Unassigned</th>
                        <th>Heap %</th>
                        <th>CPU %</th>
                        <th>Disk %</th>
                        <th>Total Storage (MB)</th>
                        <th>Largest Index</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in metrics_rows %}
                    <tr>
                        <td><strong>{{ row['Cluster'] }}</strong></td>
                        <td>
                            {% if row['Status'] == 'green' %}
                                <span class="badge badge-green">GREEN</span>
                            {% elif row['Status'] == 'yellow' %}
                                <span class="badge badge-yellow">YELLOW</span>
                            {% else %}
                                <span class="badge badge-red">{{ row['Status'] }}</span>
                            {% endif %}
                        </td>
                        <td>{{ row['Active Shards'] }}</td>
                        <td>{{ row['Unassigned Shards'] }}</td>
                        <td>{{ row['Heap Percent (%)'] }}%</td>
                        <td>{{ row['CPU Percent (%)'] }}%</td>
                        <td>{{ row['Disk Percent (%)'] }}%</td>
                        <td>{{ row['Total Storage (MB)'] }}</td>
                        <td><code>{{ row['Largest Index Name'] }}</code> ({{ row['Largest Index Size (MB)'] }} MB)</td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="9" style="text-align: center; color: var(--text-muted);">No cluster metrics recorded.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        OpenSearch Automation V2 &bull; Generated by Jenkins Pipeline
    </div>

    <script>
        const chartFont = { family: 'Inter', size: 11 };
        const gridColor = 'rgba(255, 255, 255, 0.08)';
        const textColor = '#94a3b8';

        // 1. Storage Chart
        new Chart(document.getElementById('storageChart'), {
            type: 'bar',
            data: {
                labels: {{ cluster_labels | tojson }},
                datasets: [{
                    label: 'Total Storage (MB)',
                    data: {{ storage_data | tojson }},
                    backgroundColor: 'rgba(56, 189, 248, 0.6)',
                    borderColor: '#38bdf8',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } },
                    y: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } }
                }
            }
        });

        // 2. Heap Chart
        new Chart(document.getElementById('heapChart'), {
            type: 'bar',
            data: {
                labels: {{ cluster_labels | tojson }},
                datasets: [{
                    label: 'Heap Used (%)',
                    data: {{ heap_data | tojson }},
                    backgroundColor: 'rgba(192, 132, 252, 0.6)',
                    borderColor: '#c084fc',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } },
                    y: { max: 100, ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } }
                }
            }
        });

        // 3. Disk Chart
        new Chart(document.getElementById('diskChart'), {
            type: 'bar',
            data: {
                labels: {{ cluster_labels | tojson }},
                datasets: [{
                    label: 'Disk Used (%)',
                    data: {{ disk_data | tojson }},
                    backgroundColor: 'rgba(251, 191, 36, 0.6)',
                    borderColor: '#fbbf24',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } },
                    y: { max: 100, ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } }
                }
            }
        });

        // 4. Top Largest Indices Chart
        new Chart(document.getElementById('largestIndicesChart'), {
            type: 'bar',
            data: {
                labels: {{ top_indices_labels | tojson }},
                datasets: [{
                    label: 'Size (MB)',
                    data: {{ top_indices_data | tojson }},
                    backgroundColor: 'rgba(248, 113, 113, 0.6)',
                    borderColor: '#f87171',
                    borderWidth: 1,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } },
                    y: { ticks: { color: textColor, font: chartFont }, grid: { color: gridColor } }
                }
            }
        });
    </script>
</body>
</html>
"""


def render_dashboard(
    cleanup_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    output_html_path: Path,
    generated_at: str
) -> Path:
    """
    Renders Jinja2 template and writes executive dashboard HTML to output_html_path.
    """
    output_html_path.parent.mkdir(parents=True, exist_ok=True)

    cleanup_rows = cleanup_df.to_dict(orient="records") if not cleanup_df.empty else []
    metrics_rows = metrics_df.to_dict(orient="records") if not metrics_df.empty else []

    # Chart Data Extraction
    cluster_labels = []
    storage_data = []
    heap_data = []
    disk_data = []

    for row in metrics_rows:
        cluster_labels.append(str(row.get("Cluster", "")))
        storage_data.append(float(row.get("Total Storage (MB)", 0)))
        heap_data.append(float(row.get("Heap Percent (%)", 0)))
        disk_data.append(float(row.get("Disk Percent (%)", 0)))

    # Extract Top Largest Indices from cleanup candidates or metrics
    top_indices_labels = []
    top_indices_data = []

    if cleanup_rows:
        sorted_cleanup = sorted(cleanup_rows, key=lambda x: float(x.get("Size (MB)", 0)), reverse=True)
        for item in sorted_cleanup[:config.MAX_LARGEST_INDICES]:
            top_indices_labels.append(f"{item.get('Cluster')}: {item.get('Index')}")
            top_indices_data.append(float(item.get("Size (MB)", 0)))
    else:
        for row in metrics_rows:
            if row.get("Largest Index Name") and row.get("Largest Index Name") != "N/A":
                top_indices_labels.append(f"{row.get('Cluster')}: {row.get('Largest Index Name')}")
                top_indices_data.append(float(row.get("Largest Index Size (MB)", 0)))

    template = Template(HTML_TEMPLATE)
    rendered_html = template.render(
        chartjs_cdn=config.CHARTJS_CDN,
        generated_at=generated_at,
        cleanup_rows=cleanup_rows,
        metrics_rows=metrics_rows,
        cluster_labels=cluster_labels,
        storage_data=storage_data,
        heap_data=heap_data,
        disk_data=disk_data,
        top_indices_labels=top_indices_labels,
        top_indices_data=top_indices_data,
    )

    output_html_path.write_text(rendered_html, encoding="utf-8")
    logger.info(f"Rendered executive dashboard HTML to {output_html_path}")
    return output_html_path
