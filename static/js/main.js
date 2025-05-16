// Main JavaScript file for general functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme toggle functionality
    initThemeToggle();
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Initialize Select2 for all select elements
    initializeSearchableDropdowns();

    // Handle date picker inputs
    const datePickers = document.querySelectorAll('.datepicker');
    datePickers.forEach(function(el) {
        // Use native date input or flatpickr if available
        el.type = 'date';
    });

    // Handle time picker inputs
    const timePickers = document.querySelectorAll('.timepicker');
    timePickers.forEach(function(el) {
        // Use native time input
        el.type = 'time';
    });

    // Initialize DataTables where needed
    const tables = document.querySelectorAll('.datatable');
    tables.forEach(function(table) {
        if(typeof $.fn.DataTable !== 'undefined') {
            // Skip table if it's already initialized
            if ($.fn.dataTable.isDataTable(table)) {
                return;
            }
            
            // Only initialize if table has rows
            if ($(table).find('tbody tr').length > 0) {
                $(table).DataTable({
                    responsive: true,
                    lengthMenu: [[25, 50, 100, -1], [25, 50, 100, "All"]],
                    pageLength: 31,  // Show full month by default
                    language: {
                        search: "_INPUT_",
                        searchPlaceholder: "Search...",
                    }
                });
            } else {
                console.log('Table has no rows, skipping DataTable initialization:', table.id || 'unnamed table');
            }
        }
    });

    // Flash message auto-close
    window.setTimeout(function() {
        const alerts = document.querySelectorAll('.alert.alert-dismissible.fade');
        alerts.forEach(function(alert) {
            if(!alert.classList.contains('alert-danger')) {
                // Auto-dismiss non-error alerts after 5 seconds
                const bsAlert = new bootstrap.Alert(alert);
                setTimeout(() => {
                    bsAlert.close();
                }, 5000);
            }
        });
    }, 1000);

    // Device status indicator updates
    const deviceStatusElements = document.querySelectorAll('.device-status');
    if(deviceStatusElements.length > 0) {
        updateDeviceStatuses();
        // Update statuses every 30 seconds
        setInterval(updateDeviceStatuses, 30000);
    }

    // Report charts initialization
    initializeCharts();
});

// Function to update device statuses via API
function updateDeviceStatuses() {
    fetch('/devices/api/status')
        .then(response => response.json())
        .then(data => {
            // Update device status counters
            document.querySelectorAll('.device-count-total').forEach(el => {
                el.textContent = data.total;
            });
            document.querySelectorAll('.device-count-online').forEach(el => {
                el.textContent = data.online;
            });
            document.querySelectorAll('.device-count-offline').forEach(el => {
                el.textContent = data.offline;
            });
            document.querySelectorAll('.device-count-error').forEach(el => {
                el.textContent = data.error;
            });

            // Update individual device status indicators
            data.devices.forEach(device => {
                const statusEl = document.querySelector(`.device-status[data-device-id="${device.id}"]`);
                if(statusEl) {
                    statusEl.className = `device-status badge bg-${getStatusColor(device.status)}`;
                    statusEl.textContent = device.status;
                    
                    // Update last ping time if shown
                    const pingEl = document.querySelector(`.device-last-ping[data-device-id="${device.id}"]`);
                    if(pingEl && device.last_ping) {
                        const date = new Date(device.last_ping);
                        pingEl.textContent = formatDateTime(date);
                    }
                }
            });
        })
        .catch(error => {
            console.error('Error fetching device statuses:', error);
        });
}

// Helper function to get Bootstrap color class for status
function getStatusColor(status) {
    switch(status) {
        case 'online': return 'success';
        case 'offline': return 'danger';
        case 'error': return 'warning';
        default: return 'secondary';
    }
}

// Helper function to format date/time
function formatDateTime(date) {
    if(!(date instanceof Date)) {
        return '';
    }
    
    const options = { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    
    return date.toLocaleDateString(undefined, options);
}

// Initialize theme toggle functionality
function initThemeToggle() {
    const themeToggleBtn = document.getElementById('themeToggle');
    const lightThemeIcon = document.getElementById('lightThemeIcon');
    const darkThemeIcon = document.getElementById('darkThemeIcon');
    const htmlRoot = document.getElementById('htmlRoot');
    
    // Check if there's a theme preference saved in localStorage
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        setLightTheme();
    } else {
        setDarkTheme();
    }
    
    // Add click event to toggle button
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', function() {
            const currentTheme = htmlRoot.getAttribute('data-bs-theme');
            if (currentTheme === 'dark') {
                setLightTheme();
            } else {
                setDarkTheme();
            }
        });
    }
    
    // Helper function to set light theme
    function setLightTheme() {
        htmlRoot.setAttribute('data-bs-theme', 'light');
        lightThemeIcon.style.display = 'none';
        darkThemeIcon.style.display = 'inline';
        localStorage.setItem('theme', 'light');
    }
    
    // Helper function to set dark theme
    function setDarkTheme() {
        htmlRoot.setAttribute('data-bs-theme', 'dark');
        lightThemeIcon.style.display = 'inline';
        darkThemeIcon.style.display = 'none';
        localStorage.setItem('theme', 'dark');
    }
}

// Initialize all select dropdowns with search functionality
function initializeSearchableDropdowns() {
    if (typeof $.fn.select2 !== 'undefined') {
        // Common Select2 configuration
        const defaultConfig = {
            theme: 'bootstrap-5',
            width: 'style',
            placeholder: 'Select an option',
            allowClear: false,
            closeOnSelect: false,     // Prevents dropdown from closing after selection
            selectOnClose: false,     // Don't auto-select item on close
            openOnEnter: true,        // Open dropdown when Enter is pressed
            scrollAfterSelect: false, // Don't scroll to top after selection
            
            // Enable immediate focus in search field when dropdown opens
            // This is the key fix for requiring an extra click to search
            dropdownCssClass: 'select2-dropdown-open-search',
            language: {
                noResults: function() {
                    return "No results found";
                },
                searching: function() {
                    return "Searching...";
                }
            }
        };
        
        // Add CSS for automatic focus
        if (!document.getElementById('select2-autofocus-style')) {
            const style = document.createElement('style');
            style.id = 'select2-autofocus-style';
            style.textContent = `
                .select2-search--dropdown .select2-search__field { opacity: 1 !important; }
                .select2-selection { border-radius: 0 !important; }
                .select2-container--open .select2-dropdown { border-radius: 0 !important; }
            `;
            document.head.appendChild(style);
        }
        
        // This is a global handler for all Select2 opens
        $(document).on('select2:open', function() {
            // The delay is critical - a longer delay ensures it works more reliably
            setTimeout(function() {
                var searchField = $('.select2-container--open .select2-search__field');
                if (searchField.length > 0) {
                    searchField.focus();
                }
            }, 300); // Increased timeout for better reliability
        });
        
        // Initialize all standard select elements with search
        $('select:not(.no-select2)').each(function() {
            const minResultsForSearch = $(this).find('option').length > 10 ? 1 : Infinity;
            const config = {...defaultConfig};
            
            // Apply element-specific options
            config.width = $(this).data('width') ? $(this).data('width') : $(this).hasClass('w-100') ? '100%' : 'style';
            config.placeholder = $(this).data('placeholder') || defaultConfig.placeholder;
            config.allowClear = $(this).data('allow-clear') || defaultConfig.allowClear;
            config.minimumResultsForSearch = $(this).data('minimum-results-for-search') || minResultsForSearch;
            
            $(this).select2(config);
            
            // Automatically focus the search field when dropdown opens
            $(this).on('select2:open', function() {
                // This delay is critical - too short and it won't work
                setTimeout(function() {
                    $('.select2-search__field:visible').first().focus();
                }, 300); // Increased for better reliability
            });
        });
        
        // Special handling for employee select fields (always searchable)
        $('select.employee-select').each(function() {
            const config = {...defaultConfig};
            config.width = $(this).data('width') ? $(this).data('width') : $(this).hasClass('w-100') ? '100%' : 'style';
            config.placeholder = $(this).data('placeholder') || 'Select employee';
            config.allowClear = true;
            config.minimumResultsForSearch = 1;
            config.minimumInputLength = 0;
            config.language = {
                ...defaultConfig.language,
                inputTooShort: function() {
                    return "Please enter a name or ID to search";
                }
            };
            
            $(this).select2(config);
            
            // Auto-focus search field
            $(this).on('select2:open', function() {
                setTimeout(function() {
                    $('.select2-search__field:visible').first().focus();
                }, 300); // Increased for better reliability
            });
        });
        
        // Special handling for department select fields (always searchable)
        $('select.department-select').each(function() {
            const config = {...defaultConfig};
            config.width = $(this).data('width') ? $(this).data('width') : $(this).hasClass('w-100') ? '100%' : 'style';
            config.placeholder = $(this).data('placeholder') || 'Select department';
            config.allowClear = true;
            config.minimumResultsForSearch = 1;
            
            $(this).select2(config);
            
            // Auto-focus search field
            $(this).on('select2:open', function() {
                setTimeout(function() {
                    $('.select2-search__field:visible').first().focus();
                }, 300); // Increased for better reliability
            });
        });
        
        // Handle dynamically added select elements (e.g., in modals or AJAX loaded content)
        $(document).on('DOMNodeInserted', function(e) {
            const element = $(e.target);
            
            // If it's a select element that hasn't been initialized with Select2
            if (element.is('select') && !element.hasClass('select2-hidden-accessible') && !element.hasClass('no-select2')) {
                // Small delay to ensure the element is fully in the DOM
                setTimeout(function() {
                    const minResultsForSearch = element.find('option').length > 10 ? 1 : Infinity;
                    
                    const config = {...defaultConfig};
                    config.width = element.data('width') ? element.data('width') : element.hasClass('w-100') ? '100%' : 'style';
                    config.placeholder = element.data('placeholder') || defaultConfig.placeholder;
                    config.allowClear = element.data('allow-clear') || defaultConfig.allowClear;
                    config.minimumResultsForSearch = element.data('minimum-results-for-search') || minResultsForSearch;
                    
                    element.select2(config);
                    
                    // Auto-focus search field
                    element.on('select2:open', function() {
                        setTimeout(function() {
                            $('.select2-search__field:visible').first().focus();
                        }, 300); // Increased for better reliability
                    });
                }, 300); // Increased for better reliability
            }
        });
    } else {
        console.warn('Select2 library not loaded, searchable dropdowns not available');
    }
}

function initializeCharts() {
    // Daily attendance pie chart
    const dailyChartEl = document.getElementById('dailyAttendanceChart');
    if(dailyChartEl) {
        // Get date from element data attribute
        const selectedDate = dailyChartEl.dataset.date || new Date().toISOString().split('T')[0];
        
        fetch(`/reports/api/chart-data?type=daily&date=${selectedDate}`)
            .then(response => response.json())
            .then(data => {
                new Chart(dailyChartEl, {
                    type: 'pie',
                    data: data,
                    options: {
                        responsive: true,
                        plugins: {
                            legend: {
                                position: 'right',
                            },
                            title: {
                                display: true,
                                text: 'Attendance Status'
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading chart data:', error);
            });
    }
    
    // Monthly attendance chart
    const monthlyChartEl = document.getElementById('monthlyAttendanceChart');
    if(monthlyChartEl) {
        // Get year and month from element data attribute
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
                        plugins: {
                            legend: {
                                position: 'top',
                            },
                            title: {
                                display: true,
                                text: 'Monthly Attendance Trend'
                            }
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Day of Month'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Employee Count'
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading chart data:', error);
            });
    }
}
