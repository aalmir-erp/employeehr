// JavaScript for device management functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize device status polling
    refreshDeviceStatus();
    
    // Set up automatic refresh every 30 seconds
    setInterval(refreshDeviceStatus, 30000);
    
    // Initialize device log filters if present
    const logFilterForm = document.getElementById('log-filter-form');
    if (logFilterForm) {
        logFilterForm.addEventListener('submit', function(e) {
            e.preventDefault();
            filterLogs();
        });
    }
    
    // Add copy buttons for device API keys
    const apiKeyElements = document.querySelectorAll('.api-key-field');
    apiKeyElements.forEach(el => {
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn btn-sm btn-outline-secondary ms-2';
        copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
        copyBtn.setAttribute('data-bs-toggle', 'tooltip');
        copyBtn.setAttribute('title', 'Copy API Key');
        
        copyBtn.addEventListener('click', function() {
            const key = el.textContent || el.value;
            navigator.clipboard.writeText(key)
                .then(() => {
                    // Show success tooltip
                    this.setAttribute('title', 'Copied!');
                    const tooltip = bootstrap.Tooltip.getInstance(this);
                    if (tooltip) {
                        tooltip.dispose();
                    }
                    new bootstrap.Tooltip(this).show();
                    
                    // Reset tooltip after 1.5 seconds
                    setTimeout(() => {
                        this.setAttribute('title', 'Copy API Key');
                        const tooltip = bootstrap.Tooltip.getInstance(this);
                        if (tooltip) {
                            tooltip.dispose();
                        }
                        new bootstrap.Tooltip(this);
                    }, 1500);
                })
                .catch(err => {
                    console.error('Could not copy text: ', err);
                });
        });
        
        el.insertAdjacentElement('afterend', copyBtn);
    });
    
    // Initialize device type selector behavior
    const deviceTypeSelector = document.getElementById('device_type');
    if (deviceTypeSelector) {
        deviceTypeSelector.addEventListener('change', function() {
            updateDeviceFormFields(this.value);
        });
        
        // Call once on page load to set initial state
        if (deviceTypeSelector.value) {
            updateDeviceFormFields(deviceTypeSelector.value);
        }
    }
});

// Refresh device status from API
function refreshDeviceStatus() {
    fetch('/devices/api/status')
        .then(response => response.json())
        .then(data => {
            // Update overall stats
            updateDeviceStats(data);
            
            // Update individual device status indicators
            data.devices.forEach(device => {
                updateDeviceStatusIndicator(device);
            });
        })
        .catch(error => {
            console.error('Error refreshing device status:', error);
        });
}

// Update device statistics counters
function updateDeviceStats(data) {
    document.querySelectorAll('.device-stats-total').forEach(el => {
        el.textContent = data.total;
    });
    
    document.querySelectorAll('.device-stats-online').forEach(el => {
        el.textContent = data.online;
    });
    
    document.querySelectorAll('.device-stats-offline').forEach(el => {
        el.textContent = data.offline;
    });
    
    document.querySelectorAll('.device-stats-error').forEach(el => {
        el.textContent = data.error;
    });
    
    // Update progress bar if exists
    const progressBar = document.querySelector('.device-status-progress');
    if (progressBar && data.total > 0) {
        const onlinePercentage = (data.online / data.total) * 100;
        progressBar.style.width = `${onlinePercentage}%`;
        progressBar.setAttribute('aria-valuenow', onlinePercentage);
    }
}

// Update status indicator for a specific device
function updateDeviceStatusIndicator(device) {
    const statusElement = document.querySelector(`.device-status[data-device-id="${device.id}"]`);
    if (!statusElement) return;
    
    // Remove previous status classes
    statusElement.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-secondary');
    
    // Add appropriate status class
    const statusClasses = {
        'online': 'bg-success',
        'offline': 'bg-danger',
        'error': 'bg-warning'
    };
    
    statusElement.classList.add(statusClasses[device.status] || 'bg-secondary');
    statusElement.textContent = device.status;
    
    // Update last ping time if element exists
    const lastPingElement = document.querySelector(`.device-last-ping[data-device-id="${device.id}"]`);
    if (lastPingElement && device.last_ping) {
        const pingDate = new Date(device.last_ping);
        lastPingElement.textContent = formatDateTime(pingDate);
        
        // Highlight if recent
        const minutes = Math.floor((new Date() - pingDate) / 60000);
        lastPingElement.classList.remove('text-success', 'text-warning', 'text-danger');
        
        if (minutes < 5) {
            lastPingElement.classList.add('text-success');
        } else if (minutes < 30) {
            lastPingElement.classList.add('text-warning');
        } else {
            lastPingElement.classList.add('text-danger');
        }
    }
}

// Format a date for display
function formatDateTime(date) {
    if (!date) return 'Never';
    
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins} minutes ago`;
    } else if (diffMins < 1440) { // Less than a day
        const hours = Math.floor(diffMins / 60);
        return `${hours} hours ago`;
    } else {
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
}

// Filter device logs
function filterLogs() {
    const logType = document.getElementById('log_type').value;
    const dateFrom = document.getElementById('date_from').value;
    const dateTo = document.getElementById('date_to').value;
    
    // Build query string
    let queryParams = [];
    if (logType && logType !== 'all') {
        queryParams.push(`log_type=${encodeURIComponent(logType)}`);
    }
    if (dateFrom) {
        queryParams.push(`date_from=${encodeURIComponent(dateFrom)}`);
    }
    if (dateTo) {
        queryParams.push(`date_to=${encodeURIComponent(dateTo)}`);
    }
    
    // Get device ID from URL if present
    const urlParts = window.location.pathname.split('/');
    const deviceId = urlParts[urlParts.length - 1];
    
    // Redirect to filtered URL
    window.location.href = `/devices/logs/${deviceId}?${queryParams.join('&')}`;
}

// Update form fields based on device type selection
function updateDeviceFormFields(deviceType) {
    const ipAddressGroup = document.getElementById('ip-address-group');
    const portGroup = document.getElementById('port-group');
    const apiKeyGroup = document.getElementById('api-key-group');
    
    // Hide all fields initially
    [ipAddressGroup, portGroup, apiKeyGroup].forEach(group => {
        if (group) group.style.display = 'none';
    });
    
    // Show relevant fields based on device type
    switch (deviceType) {
        case 'biometric':
            if (ipAddressGroup) ipAddressGroup.style.display = 'block';
            if (portGroup) portGroup.style.display = 'block';
            break;
            
        case 'rfid':
            if (ipAddressGroup) ipAddressGroup.style.display = 'block';
            if (portGroup) portGroup.style.display = 'block';
            break;
            
        case 'mobile':
            if (apiKeyGroup) apiKeyGroup.style.display = 'block';
            break;
            
        case 'web':
            if (apiKeyGroup) apiKeyGroup.style.display = 'block';
            break;
    }
}
