// Dashboard - Main Dashboard JavaScript
// 메인 대시보드 페이지 로직

let dailyTrendChart = null;
let zoneChart = null;

/**
 * Initialize dashboard
 */
document.addEventListener('DOMContentLoaded', function() {
    // Set default date range (last 30 days)
    const today = new Date();
    const thirtyDaysAgo = new Date(today.getTime() - (30 * 24 * 60 * 60 * 1000));
    
    document.getElementById('startDate').valueAsDate = thirtyDaysAgo;
    document.getElementById('endDate').valueAsDate = today;
    
    // Initialize global legal entity selector, then load data once
    initGlobalLegalEntity(function() {
        loadDashboardData();
    });
    
    // Setup filter form
    document.getElementById('filterForm').addEventListener('submit', function(e) {
        e.preventDefault();
        loadDashboardData();
    });
});

/**
 * Get current filters
 */
function getFilters() {
    return getFiltersWithGlobalEntity();
}

/**
 * Load all dashboard data
 */
async function loadDashboardData() {
    const filters = getFilters();
    
    // Load KPIs
    loadKPIs(filters);
    
    // Load charts
    loadDailyTrendChart(filters);
    loadZoneChart(filters);
    
    // Load table
    loadDCTable(filters);
}

/**
 * Load KPI cards - 7영역 통합 지표
 */
async function loadKPIs(filters) {
    try {
        const response = await tmsApi.getDashboardKPI(filters);
        
        if (response.success && response.data) {
            const data = response.data;
            
            // 영역1: Shipment
            document.getElementById('kpiShipmentCount').textContent = 
                formatNumber(data.total_shipment_cnt);
            
            // 영역2: CBM
            document.getElementById('kpiVolume').textContent = 
                formatNumber(data.total_cbm, 1) + ' m³';
            
            // 영역3: Load
            document.getElementById('kpiLoadCount').textContent = 
                formatNumber(data.total_load_cnt);
            
            // 영역6: 운임
            document.getElementById('kpiFreightCost').textContent = 
                '$' + formatNumber(data.total_freight_cost, 0);
            
            // 영역5: 출고 완료율
            const completionRate = data.completion_rate ? (data.completion_rate * 100).toFixed(1) : 0;
            document.getElementById('kpiCompletionRate').textContent = 
                completionRate + '%';
            
            // 영역4: Load per Shipment
            document.getElementById('kpiLoadPerShipment').textContent = 
                (data.load_per_shipment || 0).toFixed(2);
                
        } else {
            showKPIError();
        }
    } catch (error) {
        console.error('Error loading KPIs:', error);
        showKPIError();
    }
}

/**
 * Show KPI error state
 */
function showKPIError() {
    document.getElementById('kpiShipmentCount').textContent = 'N/A';
    document.getElementById('kpiLoadCount').textContent = 'N/A';
    document.getElementById('kpiFreightCost').textContent = 'N/A';
    document.getElementById('kpiVolume').textContent = 'N/A';
    document.getElementById('kpiCompletionRate').textContent = 'N/A';
    document.getElementById('kpiLoadPerShipment').textContent = 'N/A';
}

/**
 * Load daily trend chart
 */
async function loadDailyTrendChart(filters) {
    try {
        const response = await tmsApi.getShipmentDailyTrend(filters);
        
        if (response.success && response.data) {
            const data = response.data;
            
            // Prepare chart data
            const labels = data.map(row => row.ship_dt);
            const shipmentCounts = data.map(row => row.shipment_cnt);
            
            // Destroy existing chart
            if (dailyTrendChart) {
                dailyTrendChart.destroy();
            }
            
            // Create new chart
            const ctx = document.getElementById('dailyTrendChart').getContext('2d');
            dailyTrendChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Shipment 건수',
                        data: shipmentCounts,
                        borderColor: '#A50034',
                        backgroundColor: 'rgba(165, 0, 52, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: '#A50034',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                font: {
                                    size: 12,
                                    weight: '600'
                                },
                                color: '#222222'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(34, 34, 34, 0.9)',
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            borderColor: '#A50034',
                            borderWidth: 2,
                            padding: 12,
                            displayColors: true
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            },
                            ticks: {
                                font: {
                                    size: 11,
                                    weight: '500'
                                }
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                font: {
                                    size: 11,
                                    weight: '500'
                                }
                            }
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('Error loading daily trend chart:', error);
    }
}

/**
 * Load zone chart
 */
async function loadZoneChart(filters) {
    try {
        const response = await tmsApi.getShipmentByZone(filters);
        
        if (response.success && response.data) {
            const data = response.data.slice(0, 10); // Top 10 zones
            
            // Prepare chart data
            const labels = data.map(row => row.zone_name);
            const shipmentCounts = data.map(row => row.shipment_cnt);
            
            // Destroy existing chart
            if (zoneChart) {
                zoneChart.destroy();
            }
            
            // Create new chart
            const ctx = document.getElementById('zoneChart').getContext('2d');
            
            // LG 색상 팔레트
            const lgColors = [
                '#A50034', '#8B002A', '#C5003E', '#0F4C9C', '#00A651',
                '#FF6B00', '#1565C0', '#2E7D32', '#E65100', '#6A1B9A'
            ];
            
            zoneChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Shipment 건수',
                        data: shipmentCounts,
                        backgroundColor: lgColors.map(c => c + 'CC'), // 80% opacity
                        borderColor: lgColors,
                        borderWidth: 2,
                        borderRadius: 6,
                        borderSkipped: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                font: {
                                    size: 12,
                                    weight: '600'
                                },
                                color: '#222222'
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(34, 34, 34, 0.9)',
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            borderColor: '#A50034',
                            borderWidth: 2,
                            padding: 12,
                            displayColors: true
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            },
                            ticks: {
                                font: {
                                    size: 11,
                                    weight: '500'
                                }
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            },
                            ticks: {
                                font: {
                                    size: 11,
                                    weight: '500'
                                }
                            }
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('Error loading zone chart:', error);
    }
}

/**
 * Load DC table
 */
async function loadDCTable(filters) {
    try {
        const response = await tmsApi.getShipmentByDC(filters);
        
        if (response.success && response.data) {
            const data = response.data;
            const tbody = document.querySelector('#dcTable tbody');
            
            // Clear existing rows
            tbody.innerHTML = '';
            
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center">No data available</td></tr>';
                return;
            }
            
            // Add rows
            data.forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.warehouse_code || 'N/A'}</td>
                    <td>${row.LEGAL_ENTITY_NAME || 'N/A'}</td>
                    <td>${formatNumber(row.shipment_cnt)}</td>
                    <td>${formatNumber(row.destination_cnt)}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (error) {
        console.error('Error loading DC table:', error);
        const tbody = document.querySelector('#dcTable tbody');
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error loading data</td></tr>';
    }
}

/**
 * Format number with thousand separators
 */
function formatNumber(value, decimals = 0) {
    if (value === null || value === undefined || value === '') {
        return 'N/A';
    }
    
    const num = parseFloat(value);
    if (isNaN(num)) {
        return 'N/A';
    }
    
    return num.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}
