import os
import logging
import threading
from time import sleep
from datetime import datetime, timedelta
from pwnagotchi import plugins
from pwnagotchi.utils import StatusFile
from flask import render_template_string
from flask import jsonify

TEMPLATE = """
{% extends "base.html" %}
{% set active_page = "plugins" %}
{% block title %}
    Session Stats
{% endblock %}

{% block styles %}
    {{ super() }}
    <style>
        /* Session Stats Header */
        .stats-header {
            margin-bottom: 2rem;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
        }

        /* Session Selector */
        .session-selector {
            display: flex;
            gap: 1rem;
            align-items: center;
            margin-bottom: 1rem;
            background-color: var(--card-bg);
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            flex-wrap: wrap;
        }

        .session-selector label {
            display: inline;
            font-size: 0.9rem;
            color: var(--accent);
            font-weight: 600;
            text-transform: uppercase;
            margin: 0;
            font-family: var(--font-pixel);
            white-space: nowrap;
        }

        .session-controls {
            display: flex;
            gap: 1rem;
            align-items: center;
            flex: 1;
            min-width: 300px;
        }

        #session {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            cursor: pointer;
            z-index: 10;
            opacity: 0;
        }

        .session-display-wrapper {
            position: relative;
            flex: 1;
            min-width: 200px;
        }

        .session-display-box {
            flex: 1;
            padding: 0.5rem 0;
            color: #fff;
            font-size: 0.9rem;
            font-family: var(--font-pixel);
            cursor: pointer;
            min-width: 200px;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: space-between;
            user-select: none;
            pointer-events: none;
        }

        .session-text {
            flex: 1;
        }

        .session-arrow {
            width: 1.25em;
            height: 1.25em;
            margin-left: 0.5rem;
            background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'%3e%3cpath d='M7 10l5 5 5-5z'/%3e%3c/svg%3e");
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
        }

        #session option {
            background-color: #1a1a1a;
            color: #fff;
            padding: 0.75rem;
            font-weight: 600;
        }

        #session option:checked {
            background: linear-gradient(var(--accent), var(--accent));
            background-color: var(--accent);
            color: #000;
        }

        .storage-badge {
            font-family: var(--font-pixel);
            font-size: 0.85rem;
            color: var(--accent);
            padding: 0.25rem 0.75rem;
            background-color: rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.15);
            border-radius: 4px;
            border: 1px solid var(--accent);
            white-space: nowrap;
        }

        /* File Size Section */
        .file-size-section {
            margin-top: 2rem;
            padding: 1.5rem;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: var(--shadow-md);
        }

        .file-size-section h3 {
            margin: 0 0 1rem 0;
            color: var(--accent);
            font-family: var(--font-pixel);
            font-size: 1.1rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .size-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .size-stat {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .size-stat-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-transform: uppercase;
            font-family: var(--font-pixel);
        }

        .size-stat-value {
            font-size: 1.4rem;
            font-weight: bold;
            color: var(--accent);
            font-family: var(--font-pixel);
        }

        /* File Action Buttons */
        .file-actions {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .file-action-btn {
            padding: 0.5rem 1rem;
            background-color: rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.2);
            border: 1px solid var(--accent);
            border-radius: 4px;
            color: var(--accent);
            font-family: var(--font-pixel);
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .file-action-btn:hover {
            background-color: rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.3);
            transform: translateY(-2px);
        }

        .file-action-btn:active {
            transform: translateY(0);
        }

        .file-action-btn.danger {
            border-color: #f44336;
            color: #f44336;
            background-color: rgba(244, 67, 54, 0.1);
        }

        .file-action-btn.danger:hover {
            background-color: rgba(244, 67, 54, 0.2);
        }

        .file-action-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            background-color: rgba(255, 255, 255, 0.05);
            border-color: #666;
            color: #666;
        }

        /* Stats Container */
        .stats-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 3rem;
        }

        .stat-card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1.5rem;
            text-align: center;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-md);
        }

        .stat-card:hover {
            border-color: var(--accent);
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.1);
        }

        .stat-label {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-family: var(--font-pixel);
            font-weight: 600;
            margin-bottom: 0.5rem;
        }

        .stat-value {
            font-size: 2.2rem;
            font-weight: bold;
            color: var(--accent);
            font-family: var(--font-pixel);
            line-height: 1;
            letter-spacing: 1px;
        }

        /* Charts Container */
        .charts-section {
            margin-top: 3rem;
        }

        .charts-section h3 {
            margin: 0 0 2rem 0;
            color: var(--accent);
            font-family: var(--font-pixel);
            font-size: 1.4rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 2rem;
        }

        div.chart {
            height: 400px;
            width: 100%;
            position: relative;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0;
            box-shadow: var(--shadow-md);
            transition: all 0.3s ease;
        }

        div.chart:hover {
            border-color: var(--accent);
            box-shadow: 0 8px 25px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.1);
        }

        .chart-hint {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-align: center;
            margin-top: 0.5rem;
            font-family: var(--font-main);
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .stats-container {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }

            .stat-card {
                padding: 1rem;
            }

            .stat-value {
                font-size: 1.8rem;
            }

            .stat-label {
                font-size: 0.8rem;
            }

            .charts-grid {
                grid-template-columns: 1fr;
            }

            div.chart {
                height: 250px;
            }
        }

        @media (max-width: 480px) {
            .session-selector {
                flex-direction: column;
                align-items: stretch;
            }

            .session-selector label {
                display: block;
                margin-bottom: 0.5rem;
            }

            .session-controls {
                flex-direction: column;
                align-items: stretch;
                gap: 0.5rem;
            }

            .storage-badge {
                text-align: center;
            }

            #session {
                width: 100%;
            }

            .stats-container {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }

            .stat-card {
                padding: 0.75rem;
            }

            .stat-value {
                font-size: 1.5rem;
            }

            .stat-label {
                font-size: 0.75rem;
            }

            .charts-grid {
                gap: 1rem;
            }

            div.chart {
                height: 200px;
                padding: 0.75rem;
            }
        }
    </style>
{% endblock %}

{% block scripts %}
    {{ super() }}
    <script src="/js/plugins/echarts.min.js"></script>
    <script>
        const charts = {};

        async function fetchData(url) {
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                console.error(`Failed to fetch ${url}:`, error);
                return { values: [], labels: [] };
            }
        }

        function getChartColor(index) {
            // Get accent color from CSS root variables
            const root = document.documentElement;
            const r = getComputedStyle(root).getPropertyValue('--accent-r').trim();
            const g = getComputedStyle(root).getPropertyValue('--accent-g').trim();
            const b = getComputedStyle(root).getPropertyValue('--accent-b').trim();
            const accentColor = `rgb(${r},${g},${b})`;
            // Use accent color as first chart color, then secondary colors
            const colors = [accentColor, '#ff9800', '#2196f3', '#f44336', '#9c27b0', '#00bcd4'];
            return colors[index % colors.length];
        }

        function getRgbaColor(color, alpha = 0.2) {
            // Convert any color format to rgba with transparency
            if (color.startsWith('rgb(')) {
                // rgb(r,g,b) -> rgba(r,g,b,alpha)
                return color.replace('rgb(', 'rgba(').replace(')', `, ${alpha})`);
            } else if (color.startsWith('rgba(')) {
                // Already rgba, just update alpha
                return color.replace(/[\d.]+\)$/, `${alpha})`);
            } else if (color.startsWith('#')) {
                // Hex color - convert to rgba
                const hex = color.replace('#', '');
                const r = parseInt(hex.substring(0, 2), 16);
                const g = parseInt(hex.substring(2, 4), 16);
                const b = parseInt(hex.substring(4, 6), 16);
                return `rgba(${r},${g},${b},${alpha})`;
            }
            return color;
        }

        function createChart(elementId, title, data) {
            const container = document.getElementById(elementId);
            if (!container || !data.values || data.values.length === 0) return;

            const allLabels = new Set();
            data.values.forEach(values => {
                values.forEach(([ts]) => allLabels.add(ts));
            });
            const labels = Array.from(allLabels).sort();

            // Build series data for ECharts
            const series = data.values.map((values, index) => {
                const color = getChartColor(index);
                const valueMap = Object.fromEntries(values);
                const seriesData = labels.map(ts => valueMap[ts] ?? null);
                
                return {
                    name: data.labels[index],
                    type: 'line',
                    data: seriesData,
                    smooth: true,
                    symbol: 'none',
                    sampling: 'lttb',
                    itemStyle: { color: color },
                    lineStyle: { color: color, width: 2 },
                    areaStyle: { color: getRgbaColor(color, 0.2) }
                };
            });

            // Initialize chart if not exists
            if (!charts[elementId]) {
                charts[elementId] = echarts.init(container, null, { renderer: 'canvas' });
            }

            const chart = charts[elementId];
            const root = document.documentElement;
            const accentRGB = `rgb(${getComputedStyle(root).getPropertyValue('--accent-r').trim()},${getComputedStyle(root).getPropertyValue('--accent-g').trim()},${getComputedStyle(root).getPropertyValue('--accent-b').trim()})`;
            
            // Calculate zoom window: always show the most recent 20% of data
            // As data grows, the window automatically advances to the latest points
            const totalDataPoints = labels.length;
            const zoomPercentage = 20;
            const zoomStart = Math.max(0, 100 - zoomPercentage);  // 80% (start of last 20%)
            const zoomEnd = 100;  // 100% (end of data)
            
            const option = {
                tooltip: {
                    trigger: 'axis',
                    position: function (pt) {
                        return [pt[0], '10%'];
                    },
                    backgroundColor: '#000',
                    textStyle: { color: '#fff' },
                    borderColor: accentRGB,
                    borderWidth: 1
                },
                title: {
                    left: 'center',
                    text: title,
                    textStyle: { color: '#fff', fontSize: 14, fontWeight: 'bold' }
                },
                toolbox: {
                    feature: {
                        dataZoom: {
                            yAxisIndex: 'none'
                        },
                        restore: {},
                        saveAsImage: {}
                    },
                    iconStyle: {
                        borderColor: accentRGB
                    },
                    textStyle: {
                        color: '#fff'
                    }
                },
                legend: {
                    bottom: '5%',
                    textStyle: { color: '#fff', fontSize: 11 }
                },
                grid: {
                    left: '5%',
                    right: '5%',
                    top: '12%',
                    bottom: '20%',
                    containLabel: true
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: labels,
                    axisLine: { lineStyle: { color: '#333' } },
                    axisLabel: { 
                        color: '#999', 
                        fontSize: 10,
                        interval: Math.max(0, Math.floor(labels.length / 15))
                    },
                    splitLine: { show: false }
                },
                yAxis: {
                    type: 'value',
                    boundaryGap: [0, '100%'],
                    axisLine: { lineStyle: { color: '#333' } },
                    axisLabel: { color: '#999', fontSize: 10 },
                    splitLine: { lineStyle: { color: '#333' } }
                },
                dataZoom: [
                    {
                        type: 'inside',
                        start: zoomStart,
                        end: zoomEnd
                    },
                    {
                        start: zoomStart,
                        end: zoomEnd,
                        textStyle: {
                            color: '#999'
                        },
                        handleStyle: {
                            color: accentRGB,
                            opacity: 0.8
                        }
                    }
                ],
                series: series
            };

            chart.setOption(option);
        }

        // Create large area chart with zooming (Apache ECharts area-simple pattern)
        function createLargeAreaChart(elementId, title, dataKey) {
            const container = document.getElementById(elementId);
            if (!container) return;

            // Initialize chart if not exists
            if (!charts[elementId]) {
                charts[elementId] = echarts.init(container, null, { renderer: 'canvas' });
            }

            const chart = charts[elementId];
            const root = document.documentElement;
            const r = getComputedStyle(root).getPropertyValue('--accent-r').trim();
            const g = getComputedStyle(root).getPropertyValue('--accent-g').trim();
            const b = getComputedStyle(root).getPropertyValue('--accent-b').trim();
            const accentColor = `rgb(${r},${g},${b})`;

            // Build data from passed key
            const sessions = Array.isArray(window.latestStatsData) ? window.latestStatsData : [];
            const timestamps = Object.keys(sessions).sort();
            const seriesData = timestamps.map(ts => {
                const val = sessions[ts]?.[dataKey];
                return val !== undefined ? val : 0;
            });

            // Only proceed if we have data
            if (seriesData.length === 0) {
                chart.setOption({
                    title: { text: title },
                    xAxis: { type: 'category', data: [] },
                    yAxis: { type: 'value' },
                    series: []
                });
                return;
            }

            const option = {
                tooltip: {
                    trigger: 'axis',
                    position: function (pt) {
                        return [pt[0], '10%'];
                    },
                    backgroundColor: '#000',
                    textStyle: { color: '#fff' },
                    borderColor: accentColor,
                    borderWidth: 1
                },
                title: {
                    left: 'center',
                    text: title,
                    textStyle: { color: '#fff', fontSize: 14, fontWeight: 'bold' }
                },
                toolbox: {
                    feature: {
                        dataZoom: {
                            yAxisIndex: 'none'
                        },
                        restore: {},
                        saveAsImage: {}
                    },
                    iconStyle: {
                        borderColor: accentColor
                    },
                    textStyle: {
                        color: '#fff'
                    }
                },
                grid: {
                    left: '8%',
                    right: '8%',
                    top: '15%',
                    bottom: '15%',
                    containLabel: true
                },
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: timestamps,
                    axisLine: { lineStyle: { color: '#333' } },
                    axisLabel: { 
                        color: '#999', 
                        fontSize: 10,
                        interval: Math.max(0, Math.floor(timestamps.length / 10))
                    },
                    splitLine: { show: false }
                },
                yAxis: {
                    type: 'value',
                    boundaryGap: [0, '100%'],
                    axisLine: { lineStyle: { color: '#333' } },
                    axisLabel: { color: '#999', fontSize: 10 },
                    splitLine: { lineStyle: { color: '#333' } }
                },
                dataZoom: [
                    {
                        type: 'inside',
                        start: 0,
                        end: 100
                    },
                    {
                        start: 0,
                        end: 100,
                        handleIcon: 'M10.7,11.9v-1.5h-3v-3.5h1.5v2h3v1.5H10.7zM9.8,9.9h-3.3v3.3H9.8zM12.3,7.8H20V5.2h-7.7E-1v0.9h5.8v1.6h-7zm0,1.5h-2.7v3.3h10V9.3h-7.3zM7.1,13.4c-0.1,0-0.2,0.1-0.2,0.2v2.4c0,0.1,0.1,0.2,0.2,0.2h3.3c0.1,0,0.2-0.1,0.2-0.2v-2.4c0-0.1-0.1-0.2-0.2-0.2H7.1zM5.3,7.8c-0.1,0-0.2,0.1-0.2,0.2v2.4c0,0.1,0.1,0.2,0.2,0.2h3.3c0.1,0,0.2-0.1,0.2-0.2V8c0-0.1-0.1-0.2-0.2-0.2H5.3z',
                        handleSize: '100%',
                        handleStyle: {
                            color: accentColor,
                            opacity: 0.8
                        }
                    }
                ],
                series: [
                    {
                        name: title,
                        type: 'line',
                        smooth: 0.3,
                        symbol: 'none',
                        sampling: 'lttb',
                        itemStyle: {
                            color: accentColor
                        },
                        lineStyle: {
                            color: accentColor,
                            width: 2
                        },
                        areaStyle: {
                            color: getRgbaColor(accentColor, 0.3)
                        },
                        data: seriesData
                    }
                ]
            };

            chart.setOption(option);
        }

        async function updateStats() {
            const sessionSelect = document.getElementById("session");
            const session = sessionSelect?.options[sessionSelect.selectedIndex]?.text || 'Current';
            const params = session === 'Current' ? '' : '?session=' + encodeURIComponent(session);

            // Fetch summary stats
            const summary = await fetchData('/plugins/session-stats/summary' + params);
            if (summary.networks !== undefined) {
                const stat_networks = document.getElementById('stat_networks');
                const stat_handshakes = document.getElementById('stat_handshakes');
                const stat_deauths = document.getElementById('stat_deauths');
                const stat_duration = document.getElementById('stat_duration');
                const stat_temp = document.getElementById('stat_temp');
                const stat_mem = document.getElementById('stat_mem');
                const stat_cpu = document.getElementById('stat_cpu');
                
                if (stat_networks) stat_networks.textContent = summary.networks;
                if (stat_handshakes) stat_handshakes.textContent = summary.handshakes;
                if (stat_deauths) stat_deauths.textContent = summary.deauths;
                if (stat_duration) stat_duration.textContent = summary.duration;
                if (stat_temp) stat_temp.textContent = summary.temp || '0°C';
                if (stat_mem) stat_mem.textContent = summary.mem || '0%';
                if (stat_cpu) stat_cpu.textContent = summary.cpu || '0%';
            }

            // Fetch and display file sizes
            const fileSizes = await fetchData('/plugins/session-stats/file-sizes');
            if (fileSizes.total_size !== undefined) {
                // Find size of current session file
                let currentFileSize = '0 KB';
                if (fileSizes.files && fileSizes.files.length > 0) {
                    const currentFile = fileSizes.files.find(f => f.name.includes(session) || (session === 'Current' && fileSizes.files[fileSizes.files.length - 1]));
                    if (currentFile) {
                        currentFileSize = currentFile.size;
                    } else if (session === 'Current') {
                        // For current session, use the last file
                        currentFileSize = fileSizes.files[fileSizes.files.length - 1].size;
                    }
                }
                
                // Display as "current / total"
                const storage_display = document.getElementById('storage_display');
                const total_size = document.getElementById('total_size');
                const total_files = document.getElementById('total_files');
                const average_size = document.getElementById('average_size');
                
                if (storage_display) storage_display.textContent = currentFileSize + ' / ' + fileSizes.total_size;
                if (total_size) total_size.textContent = fileSizes.total_size;
                if (total_files) total_files.textContent = fileSizes.total_files;
                if (average_size) average_size.textContent = fileSizes.average_size;
                
                // Update button states
                const deleteCurrentBtn = document.getElementById('delete_current_btn');
                const clearAllBtn = document.getElementById('clear_all_btn');
                if (deleteCurrentBtn) deleteCurrentBtn.disabled = fileSizes.total_files <= 1;
                if (clearAllBtn) clearAllBtn.disabled = fileSizes.total_files === 0;
            }

            // Fetch chart data with session info in titles
            const chartConfigs = [
                { endpoint: 'networks', id: 'chart_networks', title: `Networks Captured (${session})` },
                { endpoint: 'handshakes', id: 'chart_handshakes', title: `Handshakes Captured (${session})` },
                { endpoint: 'deauths', id: 'chart_deauths', title: `Deauthentications Sent (${session})` },
                { endpoint: 'temp', id: 'chart_temp', title: `Temperature (${session})` },
                { endpoint: 'mem', id: 'chart_mem', title: `Memory Usage (${session})` },
                { endpoint: 'cpu', id: 'chart_cpu', title: `CPU Load (${session})` }
            ];

            for (const config of chartConfigs) {
                const data = await fetchData('/plugins/session-stats/' + config.endpoint + params);
                createChart(config.id, config.title, data);
            }
        }

        async function loadSessionFiles() {
            const data = await fetchData('/plugins/session-stats/sessions');
            const select = document.getElementById("session");
            
            // Clear existing options except the first one
            select.innerHTML = '';
            
            // Add Current as first option
            const currentOption = document.createElement("option");
            currentOption.value = "Current";
            currentOption.text = "Current";
            currentOption.selected = true;
            select.appendChild(currentOption);
            
            // Add other session files
            data.files?.forEach(file => {
                if (file !== "Current") { // Don't duplicate "Current"
                    const option = document.createElement("option");
                    option.value = file;
                    option.text = file;
                    select.appendChild(option);
                }
            });
            
            // Update display text when selection changes
            select.addEventListener('change', (e) => {
                const displayText = document.getElementById('session_display_text');
                if (displayText) {
                    displayText.textContent = e.target.options[e.target.selectedIndex].text;
                }
                updateStats();
            });
            
            // Set initial display text
            const displayText = document.getElementById('session_display_text');
            if (displayText) {
                displayText.textContent = select.options[select.selectedIndex].text;
            }
        }

        async function deleteCurrentFile() {
            const sessionSelect = document.getElementById("session");
            const session = sessionSelect?.options[sessionSelect.selectedIndex]?.text || 'Current';
            
            if (session === 'Current') {
                alert('Cannot delete the current active session file.');
                return;
            }
            
            if (!confirm(`Delete session file: ${session}?`)) {
                return;
            }
            
            try {
                const response = await fetch(`/plugins/session-stats/delete-file?file=${encodeURIComponent(session)}`, {
                    method: 'POST'
                });
                const result = await response.json();
                if (result.success) {
                    // Reload session list and update stats
                    loadSessionFiles();
                    updateStats();
                    alert('File deleted successfully.');
                } else {
                    alert('Error deleting file: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error deleting file:', error);
                alert('Error deleting file.');
            }
        }

        async function clearAllFiles() {
            if (!confirm('Delete ALL session files? This cannot be undone.')) {
                return;
            }
            
            if (!confirm('Are you sure? This will delete all session data.')) {
                return;
            }
            
            try {
                const response = await fetch('/plugins/session-stats/clear-files', {
                    method: 'POST'
                });
                const result = await response.json();
                if (result.success) {
                    // Reload and reset
                    location.reload();
                } else {
                    alert('Error clearing files: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error clearing files:', error);
                alert('Error clearing files.');
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            loadSessionFiles();
            updateStats();
            setInterval(updateStats, 30000);

            // Handle window resize for responsive charts
            window.addEventListener('resize', () => {
                Object.values(charts).forEach(chart => {
                    chart.resize();
                });
            });
        });
    </script>
{% endblock %}

{% block content %}
    <div class="stats-header">
        <h2>Session Statistics</h2>
        <p>Real-time monitoring of WiFi capture metrics and system performance</p>
    </div>

    <div class="session-selector">
        <label for="session">Session:</label>
        <div class="session-controls">
            <div class="session-display-wrapper">
                <div class="session-display-box">
                    <span class="session-text" id="session_display_text">Current</span>
                    <div class="session-arrow"></div>
                </div>
                <select id="session"></select>
            </div>
            <span class="storage-badge" id="storage_display">0 KB / 0 KB</span>
        </div>
    </div>
    
    <div class="stats-container">
        <div class="stat-card">
            <div class="stat-label">Networks Captured</div>
            <div class="stat-value" id="stat_networks">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Handshakes</div>
            <div class="stat-value" id="stat_handshakes">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Deauths Sent</div>
            <div class="stat-value" id="stat_deauths">0</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Session Duration</div>
            <div class="stat-value" id="stat_duration">0s</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Temperature</div>
            <div class="stat-value" id="stat_temp">0°C</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Memory Usage</div>
            <div class="stat-value" id="stat_mem">0%</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">CPU Load</div>
            <div class="stat-value" id="stat_cpu">0%</div>
        </div>
    </div>

    <div class="charts-section">
        <h3>Trend Charts</h3>
        <div class="charts-grid">
            <div id="chart_networks" class="chart"><canvas></canvas></div>
            <div id="chart_handshakes" class="chart"><canvas></canvas></div>
            <div id="chart_deauths" class="chart"><canvas></canvas></div>
            <div id="chart_temp" class="chart"><canvas></canvas></div>
            <div id="chart_mem" class="chart"><canvas></canvas></div>
            <div id="chart_cpu" class="chart"><canvas></canvas></div>
        </div>
    </div>

    <div class="file-size-section">
        <h3>JSON File Storage</h3>
        <div class="size-summary">
            <div class="size-stat">
                <div class="size-stat-label">Total Size</div>
                <div class="size-stat-value" id="total_size">0 KB</div>
            </div>
            <div class="size-stat">
                <div class="size-stat-label">Total Files</div>
                <div class="size-stat-value" id="total_files">0</div>
            </div>
            <div class="size-stat">
                <div class="size-stat-label">Average Size</div>
                <div class="size-stat-value" id="average_size">0 KB</div>
            </div>
        </div>
        <div class="file-actions">
            <button class="file-action-btn" id="delete_current_btn" onclick="deleteCurrentFile()">Delete Current</button>
            <button class="file-action-btn danger" id="clear_all_btn" onclick="clearAllFiles()">Clear All Files</button>
        </div>
    </div>
{% endblock %}
"""


class SessionStats(plugins.Plugin):
    __author__ = "33197631+dadav@users.noreply.github.com modified by wsvdmeer"
    __version__ = "0.2.0"
    __license__ = "GPL3"
    __description__ = (
        "Displays WiFi capture stats including networks, handshakes, and deauths."
    )
    DEFAULT_UPDATE_INTERVAL = 15  # RPi-friendly: 15 sec = 4 disk writes/min
    DEFAULT_SAVE_PATH = "/etc/pwnagotchi/sessions/"  # Standard location for user data

    def __init__(self):
        self.lock = threading.Lock()
        self.options = dict()
        self.stats = dict()
        self.initialized = False
        self.running = False
        self.agent = None
        self.realtime_thread = None

    def on_loaded(self):
        # Use default save path if not configured
        save_dir = self.options.get("save_directory", self.DEFAULT_SAVE_PATH)
        os.makedirs(save_dir, exist_ok=True)
        self.session_name = "stats_{}.json".format(
            datetime.now().strftime("%Y_%m_%d_%H_%M")
        )
        self.session = StatusFile(
            os.path.join(save_dir, self.session_name),
            data_format="json",
        )

        logging.info(f"Session-stats plugin loaded. Saving to: {save_dir}")

        # Try to load historical data from the most recent previous session
        try:
            session_files = sorted(
                [
                    f
                    for f in os.listdir(save_dir)
                    if f.startswith("stats_") and f.endswith(".json")
                ]
            )
            if len(session_files) > 1:  # More than just the current session
                last_session_file = session_files[
                    -2
                ]  # Second to last is the previous session
                last_session_path = os.path.join(save_dir, last_session_file)
                last_session = StatusFile(last_session_path, data_format="json")
                historical_data = last_session.data_field_or("data", default=dict())
                if historical_data:
                    self.stats.update(historical_data)
                    logging.info(
                        f"Loaded {len(historical_data)} historical data points from {last_session_file}"
                    )
        except Exception as e:
            logging.warning(f"Could not load historical session data: {e}")

        self.running = True
        self.realtime_thread = threading.Thread(
            target=self._realtime_loop, daemon=True, name="session-stats-realtime"
        )
        self.realtime_thread.start()
        logging.info("Session-stats realtime collection thread started.")

    def on_ready(self, agent):
        """Called when the agent is ready - store reference for realtime stats"""
        self.agent = agent
        logging.debug("Session-stats agent reference captured")

    def on_ui_setup(self, ui):
        """Get agent reference from UI when UI is set up"""
        if hasattr(ui, "_agent") and not self.agent:
            self.agent = ui._agent
            logging.debug("Session-stats agent reference captured from UI")

    def on_unload(self):
        self.running = False
        if self.realtime_thread and self.realtime_thread.is_alive():
            self.realtime_thread.join(timeout=5)
        logging.info("Session-stats plugin unloaded.")

    def _collect_stats(self):
        """Collect current stats from agent (called both from realtime loop and epochs)"""
        if not self.agent:
            return None

        try:
            networks = len(self.agent._access_points)
            handshakes = len(self.agent._handshakes)

            stats_entry = {
                "num_peers": networks,
                "num_handshakes": handshakes,
                "num_deauths": 0,  # Will be updated if on_epoch is called
                "temperature": 0,  # Will be updated from system or epoch data
                "mem_usage": 0,
                "cpu_load": 0,
            }
            return stats_entry
        except Exception as e:
            logging.warning(f"Could not collect stats: {e}")
            return None

    def _realtime_loop(self):
        """Background thread that collects stats periodically without waiting for epochs"""
        update_interval = self.options.get(
            "update_interval", self.DEFAULT_UPDATE_INTERVAL
        )
        agent_acquired = False

        while self.running:
            try:
                sleep(update_interval)

                if not self.agent:
                    if not agent_acquired:
                        logging.debug(
                            "Session-stats realtime loop: waiting for agent reference..."
                        )
                    continue

                if not agent_acquired:
                    logging.info(
                        "Session-stats realtime loop: agent acquired, starting stats collection"
                    )
                    agent_acquired = True

                with self.lock:
                    stats_entry = self._collect_stats()
                    if stats_entry:
                        # Use high-resolution timestamp
                        current_time = datetime.now()
                        timestamp = current_time.strftime("%H:%M:%S.%f")[:-3]

                        # Only update if this is new data or initialized
                        if not self.initialized:
                            self.stats[timestamp] = stats_entry
                            self.initialized = True
                            self.session.update(data={"data": self.stats})
                            logging.info(
                                f"Session-stats initialized (realtime): {stats_entry['num_peers']} networks, "
                                f"{stats_entry['num_handshakes']} handshakes"
                            )
                        else:
                            # Add to stats if data changed
                            last_stats = (
                                list(self.stats.values())[-1] if self.stats else None
                            )
                            if last_stats and (
                                stats_entry["num_peers"]
                                != last_stats.get("num_peers", 0)
                                or stats_entry["num_handshakes"]
                                != last_stats.get("num_handshakes", 0)
                            ):
                                self.stats[timestamp] = stats_entry
                                self.session.update(data={"data": self.stats})

            except Exception as e:
                logging.warning(f"Error in realtime stats loop: {e}")

    def _get_file_size(self):
        """Get current session file size in KB"""
        try:
            if (
                hasattr(self, "session")
                and self.session
                and hasattr(self.session, "_fp")
            ):
                file_path = self.session._fp
                if os.path.exists(file_path):
                    size_bytes = os.path.getsize(file_path)
                    size_kb = size_bytes / 1024
                    if size_kb > 1024:
                        return f"{size_kb / 1024:.2f} MB"
                    else:
                        return f"{size_kb:.2f} KB"
        except Exception as e:
            logging.debug(f"Could not determine file size: {e}")
        return "0 KB"

    def on_epoch(self, agent, epoch, epoch_data):
        # Store agent reference if not already set
        if not self.agent:
            self.agent = agent
            logging.debug("Session-stats agent reference captured from epoch callback")
        else:
            self.agent = agent

        with self.lock:
            # Store complete epoch_data dict (includes all metrics from pwnagotchi)
            # Also add access_points and handshakes count for backward compatibility
            stats_entry = dict(epoch_data)  # Start with all epoch_data
            stats_entry["num_peers"] = len(agent._access_points)
            stats_entry["num_handshakes"] = len(agent._handshakes)

            # Add epoch data with high-resolution timestamp
            current_time = datetime.now()
            timestamp = current_time.strftime("%H:%M:%S.%f")[:-3]
            self.stats[timestamp] = stats_entry
            self.session.update(data={"data": self.stats})

            if not self.initialized:
                self.initialized = True
                logging.info(
                    f"Session-stats epoch update: {len(agent._access_points)} networks, "
                    f"{len(agent._handshakes)} handshakes"
                )

    def on_webhook(self, path, request):
        if not path or path == "/":
            return render_template_string(TEMPLATE)

        session_param = request.args.get("session")
        save_dir = self.options.get("save_directory", self.DEFAULT_SAVE_PATH)

        with self.lock:
            data = self.stats
            if session_param and session_param != "Current":
                file_stats = StatusFile(
                    os.path.join(save_dir, session_param),
                    data_format="json",
                )
                data = file_stats.data_field_or("data", default=dict())

        if path == "summary":
            total_networks = len(set(d.get("num_peers", 0) for d in data.values()))
            total_handshakes = max(
                [d.get("num_handshakes", 0) for d in data.values()], default=0
            )
            total_deauths = max(
                [d.get("num_deauths", 0) for d in data.values()], default=0
            )
            duration = len(data) if data else 0
            temp = max([d.get("temperature", 0) for d in data.values()], default=0)
            mem = max([d.get("mem_usage", 0) for d in data.values()], default=0)
            cpu = max([d.get("cpu_load", 0) for d in data.values()], default=0)

            # Get file size for the correct session file
            file_size = "0 KB"
            try:
                if session_param and session_param != "Current":
                    file_path = os.path.join(save_dir, session_param)
                else:
                    file_path = (
                        self.session._fp if hasattr(self.session, "_fp") else None
                    )

                if file_path and os.path.exists(file_path):
                    size_bytes = os.path.getsize(file_path)
                    size_kb = size_bytes / 1024
                    if size_kb > 1024:
                        file_size = f"{size_kb / 1024:.2f} MB"
                    else:
                        file_size = f"{size_kb:.2f} KB"
            except Exception as e:
                logging.debug(f"Could not get file size: {e}")

            return jsonify(
                {
                    "networks": total_networks,
                    "handshakes": total_handshakes,
                    "deauths": total_deauths,
                    "duration": f"{duration}s",
                    "temp": f"{temp:.1f}°C",
                    "mem": f"{mem:.1f}%",
                    "cpu": f"{cpu:.1f}%",
                    "file_size": file_size,
                }
            )

        elif path == "networks":
            return jsonify(self._extract_key_values(data, ["num_peers"]))
        elif path == "handshakes":
            return jsonify(self._extract_key_values(data, ["num_handshakes"]))
        elif path == "deauths":
            return jsonify(self._extract_key_values(data, ["num_deauths"]))
        elif path == "temp":
            return jsonify(self._extract_key_values(data, ["temperature"]))
        elif path == "mem":
            return jsonify(self._extract_key_values(data, ["mem_usage"]))
        elif path == "cpu":
            return jsonify(self._extract_key_values(data, ["cpu_load"]))
        elif path == "sessions":
            return jsonify({"files": os.listdir(save_dir)})
        elif path == "file-sizes":
            return jsonify(self._get_all_file_sizes(save_dir))
        elif path == "delete-file":
            file_to_delete = request.args.get("file")
            if not file_to_delete or file_to_delete == "Current":
                return jsonify(
                    {"success": False, "error": "Cannot delete current session"}
                )

            try:
                file_path = os.path.join(save_dir, file_to_delete)
                if os.path.exists(file_path) and file_path.startswith(save_dir):
                    os.remove(file_path)
                    logging.info(f"Deleted session file: {file_to_delete}")
                    return jsonify({"success": True})
                else:
                    return jsonify({"success": False, "error": "File not found"})
            except Exception as e:
                logging.error(f"Error deleting file: {e}")
                return jsonify({"success": False, "error": str(e)})
        elif path == "clear-files":
            try:
                files = [
                    f
                    for f in os.listdir(save_dir)
                    if f.startswith("stats_") and f.endswith(".json")
                ]
                for file in files:
                    file_path = os.path.join(save_dir, file)
                    if file_path != (
                        self.session._fp if hasattr(self.session, "_fp") else None
                    ):
                        os.remove(file_path)

                logging.info(f"Cleared {len(files)} session files")
                return jsonify({"success": True})
            except Exception as e:
                logging.error(f"Error clearing files: {e}")
                return jsonify({"success": False, "error": str(e)})

        return jsonify({"error": "Unknown path"})

    @staticmethod
    def _format_size(size_bytes):
        """Convert bytes to human-readable format (KB or MB)"""
        size_kb = size_bytes / 1024
        if size_kb > 1024:
            return f"{size_kb / 1024:.2f} MB"
        else:
            return f"{size_kb:.2f} KB"

    def _get_all_file_sizes(self, save_dir):
        """Get all JSON file sizes with statistics"""
        try:
            files = [
                f
                for f in os.listdir(save_dir)
                if f.startswith("stats_") and f.endswith(".json")
            ]

            file_info = []
            total_size = 0

            for file in sorted(files):
                file_path = os.path.join(save_dir, file)
                try:
                    size_bytes = os.path.getsize(file_path)
                    total_size += size_bytes
                    file_info.append(
                        {
                            "name": file,
                            "size": self._format_size(size_bytes),
                            "size_bytes": size_bytes,
                        }
                    )
                except Exception as e:
                    logging.debug(f"Could not get size for {file}: {e}")

            average_size = total_size / len(file_info) if file_info else 0

            return {
                "total_size": self._format_size(total_size),
                "total_files": len(file_info),
                "average_size": self._format_size(average_size),
                "files": file_info,
            }
        except Exception as e:
            logging.debug(f"Error getting file sizes: {e}")
            return {
                "total_size": "0 KB",
                "total_files": 0,
                "average_size": "0 KB",
                "files": [],
            }

    @staticmethod
    def _extract_key_values(data, subkeys):
        result = {"values": [], "labels": subkeys}
        for plot_key in subkeys:
            v = [[ts, d.get(plot_key, 0)] for ts, d in data.items()]
            result["values"].append(v)
        return result
