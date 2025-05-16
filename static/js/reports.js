// Reports JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize date range pickers
    initializeDateRangePickers();
    
    // Initialize report charts
    initializeReportCharts();
    
    // Add event listeners for report filters
    setupReportFilters();
    
    // Add export button listeners
    setupExportButtons();
});

/**
 * Initialize date range pickers for reports
 */
function initializeDateRangePickers() {
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    if (startDateInput && endDateInput) {
        // When start date changes, update end date min attribute
        startDateInput.addEventListener('change', function() {
            endDateInput.min = this.value;
            if (endDateInput.value && new Date(endDateInput.value) < new Date(this.value)) {
                endDateInput.value = this.value;
            }
        });
        
        // When end date changes, update start date max attribute
        endDateInput.addEventListener('change', function() {
            startDateInput.max = this.value;
            if (startDateInput.value && new Date(startDateInput.value) > new Date(this.value)) {
                startDateInput.value = this.value;
            }
        });
        
        // Set initial values if not already set
        if (!startDateInput.value) {
            const today = new Date();
            const oneMonthAgo = new Date();
            oneMonthAgo.setMonth(today.getMonth() - 1);
            
            startDateInput.value = oneMonthAgo.toISOString().split('T')[0];
            endDateInput.value = today.toISOString().split('T')[0];
        }
    }
}

/**
 * Initialize charts for reports
 */
function initializeReportCharts() {
    // Daily attendance chart
    const dailyChartEl = document.getElementById('dailyAttendanceChart');
    if (dailyChartEl) {
        const date = dailyChartEl.dataset.date || new Date().toISOString().split('T')[0];
        
        fetch(`/reports/api/chart-data?type=daily&date=${date}`)
            .then(response => response.json())
            .then(data => {
                new Chart(dailyChartEl, {
                    type: 'pie',
                    data: data,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: {
                                    color: '#fff'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Daily Attendance',
                                color: '#fff',
                                font: {
                                    size: 16
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading daily chart data:', error);
                dailyChartEl.innerHTML = '<div class="alert alert-danger">Failed to load chart data</div>';
            });
    }
    
    // Monthly attendance chart
    const monthlyChartEl = document.getElementById('monthlyAttendanceChart');
    if (monthlyChartEl) {
        const year = monthlyChartEl.dataset.year || new Date().getFullYear();
        const month = monthlyChartEl.dataset.month || new Date().getMonth() + 1;
        
        fetch(`/reports/api/chart-data?type=monthly&year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => {
                new Chart(monthlyChartEl, {
                    type: 'bar',
                    data: data,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top',
                                labels: {
                                    color: '#fff'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Monthly Attendance Trend',
                                color: '#fff',
                                font: {
                                    size: 16
                                }
                            }
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Day of Month',
                                    color: '#fff'
                                },
                                ticks: {
                                    color: '#fff'
                                },
                                grid: {
                                    color: 'rgba(255, 255, 255, 0.1)'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Employee Count',
                                    color: '#fff'
                                },
                                ticks: {
                                    color: '#fff'
                                },
                                grid: {
                                    color: 'rgba(255, 255, 255, 0.1)'
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading monthly chart data:', error);
                monthlyChartEl.innerHTML = '<div class="alert alert-danger">Failed to load chart data</div>';
            });
    }
    
    // Employee attendance chart
    const employeeChartEl = document.getElementById('employeeAttendanceChart');
    if (employeeChartEl) {
        const employeeId = employeeChartEl.dataset.employeeId;
        const startDate = document.getElementById('start_date')?.value || '';
        const endDate = document.getElementById('end_date')?.value || '';
        
        if (employeeId) {
            const url = `/reports/api/chart-data?type=employee&employee_id=${employeeId}&start_date=${startDate}&end_date=${endDate}`;
            
            // For employee charts, we would need to implement this endpoint in the backend
            // This is a placeholder for demonstration
            const demoData = {
                labels: ['Present', 'Absent', 'Late', 'Leave'],
                datasets: [{
                    data: [15, 3, 2, 1],
                    backgroundColor: ['#28a745', '#dc3545', '#ffc107', '#17a2b8']
                }]
            };
            
            new Chart(employeeChartEl, {
                type: 'pie',
                data: demoData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                color: '#fff'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Attendance Summary',
                            color: '#fff',
                            font: {
                                size: 16
                            }
                        }
                    }
                }
            });
        }
    }
}

/**
 * Setup report filter form event listeners
 */
function setupReportFilters() {
    // Department filter
    const deptFilter = document.getElementById('department_filter');
    if (deptFilter) {
        deptFilter.addEventListener('change', function() {
            // Get the current URL and update the department parameter
            const url = new URL(window.location);
            url.searchParams.set('department', this.value);
            window.location = url.toString();
        });
    }
    
    // Date filter form
    const dateFilterForm = document.getElementById('date_filter_form');
    if (dateFilterForm) {
        dateFilterForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const params = new URLSearchParams();
            
            for (const [key, value] of formData.entries()) {
                params.append(key, value);
            }
            
            window.location = `${window.location.pathname}?${params.toString()}`;
        });
    }
    
    // Month/Year selector for monthly reports
    const monthSelector = document.getElementById('month_selector');
    const yearSelector = document.getElementById('year_selector');
    
    if (monthSelector && yearSelector) {
        const updateMonthlyReport = function() {
            const month = monthSelector.value;
            const year = yearSelector.value;
            window.location = `${window.location.pathname}?month=${month}&year=${year}`;
        };
        
        monthSelector.addEventListener('change', updateMonthlyReport);
        yearSelector.addEventListener('change', updateMonthlyReport);
    }
}

/**
 * Setup export buttons for reports
 */
function setupExportButtons() {
    const exportButtons = document.querySelectorAll('.export-report-btn');
    
    exportButtons.forEach(button => {
        button.addEventListener('click', function() {
            const reportType = this.dataset.reportType;
            const date = this.dataset.date;
            const month = this.dataset.month;
            const year = this.dataset.year;
            const format = this.dataset.format || 'csv';
            
            let url = `/reports/export/${format}?type=${reportType}`;
            
            if (date) {
                url += `&date=${date}`;
            }
            
            if (month && year) {
                url += `&month=${month}&year=${year}`;
            }
            
            window.location = url;
        });
    });
}

/**
 * Format a date for display
 */
function formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    return date.toLocaleDateString();
}

/**
 * Format a time for display
 */
function formatTime(timeString) {
    if (!timeString) return '';
    
    // Handle different time formats
    let time;
    if (timeString.includes('T')) {
        // ISO datetime format
        time = new Date(timeString);
    } else if (timeString.includes(':')) {
        // HH:MM:SS format
        const [hours, minutes] = timeString.split(':');
        time = new Date();
        time.setHours(hours);
        time.setMinutes(minutes);
    } else {
        return timeString;
    }
    
    return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Calculate work hours between two time strings
 */
function calculateWorkHours(startTime, endTime) {
    if (!startTime || !endTime) return 0;
    
    // Parse the time strings to Date objects
    const start = new Date(`2000-01-01T${startTime}`);
    let end = new Date(`2000-01-01T${endTime}`);
    
    // Handle overnight shifts
    if (end < start) {
        end = new Date(`2000-01-02T${endTime}`);
    }
    
    // Calculate the difference in hours
    const diffMs = end - start;
    const diffHours = diffMs / (1000 * 60 * 60);
    
    return diffHours.toFixed(2);
}
