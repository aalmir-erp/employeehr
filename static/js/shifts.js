// JavaScript for shift management and scheduler

document.addEventListener('DOMContentLoaded', function() {
    // Initialize color picker for shift color
    const colorPickers = document.querySelectorAll('.color-picker');
    colorPickers.forEach(picker => {
        picker.addEventListener('input', function() {
            const colorPreview = document.querySelector('.color-preview');
            if (colorPreview) {
                colorPreview.style.backgroundColor = this.value;
            }
        });
    });

    // Toggle overnight shift option to show warning
    const overnightCheckbox = document.getElementById('is_overnight');
    if (overnightCheckbox) {
        overnightCheckbox.addEventListener('change', function() {
            const warningElem = document.getElementById('overnight-warning');
            if (warningElem) {
                warningElem.style.display = this.checked ? 'block' : 'none';
            }
        });
    }

    // Shift assignment form validation
    const shiftAssignmentForm = document.getElementById('shift-assignment-form');
    if (shiftAssignmentForm) {
        shiftAssignmentForm.addEventListener('submit', function(event) {
            const startDate = document.getElementById('start_date').value;
            const endDate = document.getElementById('end_date').value;
            
            if (endDate && new Date(endDate) < new Date(startDate)) {
                event.preventDefault();
                alert('End date cannot be before start date');
            }
        });
    }

    // Employee-specific shift assignment handling
    const employeeSelector = document.getElementById('employee_id');
    if (employeeSelector) {
        employeeSelector.addEventListener('change', function() {
            if (this.value) {
                loadEmployeeShifts(this.value);
            }
        });
    }

    // Initialize shift scheduler if present
    initializeShiftScheduler();
});

function loadEmployeeShifts(employeeId) {
    // Get current shifts for the selected employee
    const startDateElem = document.getElementById('start_date');
    const endDateElem = document.getElementById('end_date');
    
    if (!startDateElem || !endDateElem) return;
    
    const startDate = startDateElem.value || new Date().toISOString().split('T')[0];
    const endDate = endDateElem.value || new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().split('T')[0];
    
    fetch(`/shifts/api/employee-assignments/${employeeId}?start_date=${startDate}&end_date=${endDate}`)
        .then(response => response.json())
        .then(data => {
            // Display current assignments in a list
            const assignmentsList = document.getElementById('current-assignments');
            if (!assignmentsList) return;
            
            assignmentsList.innerHTML = '';
            
            if (data.length === 0) {
                assignmentsList.innerHTML = '<div class="alert alert-info">No current shift assignments for this date range.</div>';
                return;
            }
            
            const list = document.createElement('ul');
            list.className = 'list-group';
            
            data.forEach(assignment => {
                const item = document.createElement('li');
                item.className = 'list-group-item d-flex justify-content-between align-items-center';
                
                // Create badge with shift color
                const badge = document.createElement('span');
                badge.className = 'badge rounded-pill';
                badge.style.backgroundColor = assignment.color;
                badge.textContent = assignment.shift_name;
                
                // Create text for date range
                const dateRange = document.createElement('span');
                dateRange.textContent = `${formatDate(assignment.start_date)} - ${assignment.end_date ? formatDate(assignment.end_date) : 'Indefinite'}`;
                
                // Create delete button
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn btn-sm btn-danger';
                deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
                deleteBtn.onclick = function() {
                    if (confirm('Are you sure you want to delete this shift assignment?')) {
                        deleteShiftAssignment(assignment.id);
                    }
                };
                
                item.appendChild(badge);
                item.appendChild(dateRange);
                item.appendChild(deleteBtn);
                
                list.appendChild(item);
            });
            
            assignmentsList.appendChild(list);
        })
        .catch(error => {
            console.error('Error loading employee shifts:', error);
        });
}

function deleteShiftAssignment(assignmentId) {
    // Create a form to submit the delete request
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/shifts/assignment/delete/${assignmentId}`;
    document.body.appendChild(form);
    form.submit();
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString();
}

function initializeShiftScheduler() {
    // Add drag and drop functionality to the shift scheduler
    enableDragAndDropShiftAssignment();
    
    // Add multi-select functionality for batch assignment
    enableMultiSelectForBatchAssignment();
    
    // Add batch deletion functionality
    enableBatchDeletion();
    
    // Add calendar navigation enhancements
    setupCalendarNavigation();
    
    // Add shift selector enhancements
    enhanceShiftSelectors();
}

function enableDragAndDropShiftAssignment() {
    // Make all shift-assignment-cell elements suitable for drop targets
    const assignmentCells = document.querySelectorAll('.shift-assignment-cell');
    if (assignmentCells.length === 0) return;
    
    assignmentCells.forEach(cell => {
        // Make the cell a valid drop target
        cell.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.add('drag-hover');
        });
        
        cell.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('drag-hover');
        });
        
        cell.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.remove('drag-hover');
            
            const shiftId = e.dataTransfer.getData('shift-id');
            const employeeId = this.dataset.employeeId;
            const date = this.dataset.date;
            
            if (shiftId && employeeId && date) {
                assignShiftViaAjax(shiftId, employeeId, date);
            }
        });
    });
    
    // Make the shift buttons in the legend draggable
    document.querySelectorAll('.badge[data-shift-id]').forEach(badge => {
        badge.setAttribute('draggable', true);
        badge.classList.add('draggable-shift');
        
        // Ensure the badge has a background color
        if (!badge.style.backgroundColor && badge.getAttribute('style')) {
            // Keep the existing style, it probably has the background-color
            console.log('Badge already has style: ' + badge.getAttribute('style'));
        } else if (!badge.style.backgroundColor) {
            // Set a default color if none is specified
            badge.style.backgroundColor = '#3498db';
            console.log('Setting default color for badge: ' + badge.textContent.trim());
        }
        
        badge.addEventListener('dragstart', function(e) {
            e.dataTransfer.setData('shift-id', this.dataset.shiftId);
            e.dataTransfer.setData('shift-name', this.textContent.trim());
            e.dataTransfer.setData('shift-color', this.style.backgroundColor);
            e.dataTransfer.effectAllowed = 'copy';
        });
    });
}

function enableMultiSelectForBatchAssignment() {
    // Add shift selection mode
    let isInSelectionMode = false;
    let selectedCells = [];
    let currentShiftId = null;
    
    // Add a batch assignment button to the legend section
    const legendSection = document.querySelector('.card-body .row .col-md-6:first-child');
    if (legendSection) {
        const batchAssignButton = document.createElement('button');
        batchAssignButton.className = 'btn btn-sm btn-outline-primary mt-2';
        batchAssignButton.innerHTML = '<i class="bi bi-grid"></i> Batch Assign Mode';
        batchAssignButton.id = 'batch-assign-mode';
        batchAssignButton.onclick = function() {
            isInSelectionMode = !isInSelectionMode;
            this.classList.toggle('active', isInSelectionMode);
            document.body.classList.toggle('selection-mode', isInSelectionMode);
            
            // Clear selection when toggling off
            if (!isInSelectionMode) {
                selectedCells.forEach(cell => cell.classList.remove('selected'));
                selectedCells = [];
                currentShiftId = null;
                
                // Hide the apply button if it exists
                const applyButton = document.getElementById('apply-shift-selection');
                if (applyButton) applyButton.remove();
            } else {
                // Show instruction
                alert('Select cells and then choose a shift to apply to all selected cells');
            }
        };
        legendSection.appendChild(batchAssignButton);
    }
    
    // Make cells selectable
    document.querySelectorAll('.shift-assignment-cell').forEach(cell => {
        cell.addEventListener('click', function(e) {
            if (!isInSelectionMode) return;
            
            // Toggle selection
            this.classList.toggle('selected');
            
            if (this.classList.contains('selected')) {
                selectedCells.push(this);
            } else {
                selectedCells = selectedCells.filter(c => c !== this);
            }
            
            // If we have selections, show the apply button
            if (selectedCells.length > 0) {
                let applyButton = document.getElementById('apply-shift-selection');
                if (!applyButton) {
                    applyButton = document.createElement('div');
                    applyButton.id = 'apply-shift-selection';
                    applyButton.className = 'position-fixed bottom-0 end-0 p-3';
                    applyButton.innerHTML = `
                        <div class="card shadow">
                            <div class="card-body">
                                <h6>Selected ${selectedCells.length} cell(s)</h6>
                                <div class="d-flex flex-wrap shift-selector mb-2">
                                    ${Array.from(document.querySelectorAll('.badge[data-shift-id]')).map(badge => 
                                        `<button type="button" class="btn btn-sm m-1 text-white apply-shift" 
                                                style="background-color: ${badge.style.backgroundColor || '#3498db'}" 
                                                data-shift-id="${badge.dataset.shiftId}">
                                            ${badge.textContent.trim()}
                                        </button>`
                                    ).join('')}
                                </div>
                                <button class="btn btn-sm btn-outline-secondary cancel-selection">Cancel</button>
                            </div>
                        </div>
                    `;
                    document.body.appendChild(applyButton);
                    
                    // Add click handlers for shift buttons
                    applyButton.querySelectorAll('.apply-shift').forEach(btn => {
                        btn.addEventListener('click', function() {
                            const shiftId = this.dataset.shiftId;
                            applyShiftToSelected(shiftId, selectedCells);
                        });
                    });
                    
                    // Add click handler for cancel button
                    applyButton.querySelector('.cancel-selection').addEventListener('click', function() {
                        selectedCells.forEach(cell => cell.classList.remove('selected'));
                        selectedCells = [];
                        applyButton.remove();
                    });
                } else {
                    // Update the count
                    applyButton.querySelector('h6').textContent = `Selected ${selectedCells.length} cell(s)`;
                }
            } else {
                // Remove the apply button if no cells selected
                const applyButton = document.getElementById('apply-shift-selection');
                if (applyButton) applyButton.remove();
            }
        });
    });
}

function applyShiftToSelected(shiftId, cells) {
    // Show loading indicator
    cells.forEach(cell => {
        cell.innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
    });
    
    // Process each cell
    const promises = cells.map(cell => {
        const employeeId = cell.dataset.employeeId;
        const date = cell.dataset.date;
        
        return fetch('/shifts/assignment/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: new URLSearchParams({
                'employee_id': employeeId,
                'shift_id': shiftId,
                'date': date
            })
        }).then(response => response.json());
    });
    
    // When all promises are resolved, refresh the page
    Promise.all(promises).then(() => {
        location.reload();
    }).catch(error => {
        console.error('Error in batch assignment:', error);
        alert('There was an error processing some assignments. Please refresh the page and try again.');
        location.reload();
    });
}

function enableBatchDeletion() {
    // Add batch deletion functionality for shift assignments
    const legendSection = document.querySelector('.card-body .row .col-md-6:first-child');
    if (!legendSection) return;
    
    // Create batch delete button
    const batchDeleteButton = document.createElement('button');
    batchDeleteButton.className = 'btn btn-sm btn-outline-danger mt-2 ms-2';
    batchDeleteButton.innerHTML = '<i class="bi bi-trash"></i> Batch Delete Mode';
    batchDeleteButton.id = 'batch-delete-mode';
    
    // Add to legend section
    legendSection.appendChild(batchDeleteButton);
    
    // Deletion mode state
    let isInDeletionMode = false;
    let selectedAssignments = [];
    
    // Toggle deletion mode
    batchDeleteButton.addEventListener('click', function() {
        isInDeletionMode = !isInDeletionMode;
        this.classList.toggle('active', isInDeletionMode);
        document.body.classList.toggle('deletion-mode', isInDeletionMode);
        
        // Toggle assignment selection mode
        document.querySelectorAll('.shift-assignment').forEach(assignment => {
            assignment.classList.toggle('deletable', isInDeletionMode);
        });
        
        // Clear selection when toggling off
        if (!isInDeletionMode) {
            selectedAssignments = [];
            document.querySelectorAll('.shift-assignment.selected-for-deletion').forEach(assignment => {
                assignment.classList.remove('selected-for-deletion');
            });
            
            // Remove delete action bar
            const deleteActionBar = document.getElementById('delete-action-bar');
            if (deleteActionBar) deleteActionBar.remove();
        } else {
            // Show instruction
            alert('Click on assigned shifts to select them for deletion');
        }
    });
    
    // Add click handlers to all assignments for selection
    document.querySelectorAll('.shift-assignment').forEach(assignment => {
        assignment.addEventListener('click', function(e) {
            if (!isInDeletionMode) return;
            
            // Only handle clicks in deletion mode
            e.stopPropagation();
            
            // Toggle selection
            this.classList.toggle('selected-for-deletion');
            
            const assignmentId = this.dataset.assignmentId;
            if (!assignmentId) return;
            
            if (this.classList.contains('selected-for-deletion')) {
                selectedAssignments.push(assignmentId);
            } else {
                selectedAssignments = selectedAssignments.filter(id => id !== assignmentId);
            }
            
            // Update UI for selections
            updateDeletionUI(selectedAssignments);
        });
    });
}

function updateDeletionUI(selectedAssignments) {
    // Update UI based on selected assignments for deletion
    let deleteActionBar = document.getElementById('delete-action-bar');
    
    if (selectedAssignments.length > 0) {
        if (!deleteActionBar) {
            deleteActionBar = document.createElement('div');
            deleteActionBar.id = 'delete-action-bar';
            deleteActionBar.className = 'position-fixed bottom-0 start-0 end-0 p-3 bg-light border-top';
            deleteActionBar.innerHTML = `
                <div class="container">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="selected-count">Selected <span class="badge bg-danger">${selectedAssignments.length}</span> shift assignments</span>
                        <div>
                            <button class="btn btn-sm btn-outline-secondary cancel-deletion me-2">Cancel</button>
                            <button class="btn btn-sm btn-danger confirm-deletion">Delete Selected</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(deleteActionBar);
            
            // Add click handlers
            deleteActionBar.querySelector('.cancel-deletion').addEventListener('click', function() {
                // Clear selections
                document.querySelectorAll('.shift-assignment.selected-for-deletion').forEach(assignment => {
                    assignment.classList.remove('selected-for-deletion');
                });
                selectedAssignments = [];
                deleteActionBar.remove();
            });
            
            deleteActionBar.querySelector('.confirm-deletion').addEventListener('click', function() {
                if (confirm(`Are you sure you want to delete ${selectedAssignments.length} shift assignments?`)) {
                    batchDeleteShiftAssignments(selectedAssignments);
                }
            });
        } else {
            // Update counter
            deleteActionBar.querySelector('.selected-count').innerHTML = `Selected <span class="badge bg-danger">${selectedAssignments.length}</span> shift assignments`;
        }
    } else if (deleteActionBar) {
        deleteActionBar.remove();
    }
}

function batchDeleteShiftAssignments(assignmentIds) {
    // Show loading state
    const deleteActionBar = document.getElementById('delete-action-bar');
    if (deleteActionBar) {
        deleteActionBar.querySelector('.confirm-deletion').disabled = true;
        deleteActionBar.querySelector('.confirm-deletion').innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
    }
    
    // Send delete request
    fetch('/shifts/assignments/batch-delete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            assignment_ids: assignmentIds
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success toast
            alert(data.message);
            // Reload the page to refresh the calendar
            location.reload();
        } else {
            // Show error message
            alert('Error: ' + data.message);
            console.error('Failed IDs:', data.failed_ids);
        }
    })
    .catch(error => {
        console.error('Error in batch deletion:', error);
        alert('There was an error processing your request. Please try again.');
    });
}

function setupCalendarNavigation() {
    // Add keyboard navigation for date selection
    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        const weekStartInput = document.getElementById('week_start');
        if (!weekStartInput) return;
        
        let currentDate = new Date(weekStartInput.value);
        
        switch (e.key) {
            case 'ArrowLeft':
                // Previous week
                currentDate.setDate(currentDate.getDate() - 7);
                break;
            case 'ArrowRight':
                // Next week
                currentDate.setDate(currentDate.getDate() + 7);
                break;
            case 'Home':
                // Current week
                const today = new Date();
                currentDate = new Date(today.setDate(today.getDate() - today.getDay() + 1));
                break;
            default:
                return;
        }
        
        // Update the input and submit the form
        weekStartInput.value = currentDate.toISOString().split('T')[0];
        document.getElementById('schedulerForm').submit();
    });
}

function enhanceShiftSelectors() {
    // Add quick access to shifts
    const tableHeaders = document.querySelectorAll('#scheduleTable th:not(:first-child)');
    if (tableHeaders.length === 0) return;
    
    // Create a floating toolbar for each day
    tableHeaders.forEach((header, index) => {
        const date = header.textContent.trim();
        
        // Add a small indicator button to show/hide shift selector
        const dayToolbar = document.createElement('div');
        dayToolbar.className = 'day-toolbar';
        dayToolbar.innerHTML = `<button class="btn btn-sm btn-outline-secondary show-day-shifts">+</button>`;
        header.appendChild(dayToolbar);
        
        // Create the day shift selector
        const dayShiftSelector = document.createElement('div');
        dayShiftSelector.className = 'day-shift-selector d-none';
        dayShiftSelector.innerHTML = `
            <div class="card shadow-sm">
                <div class="card-header bg-light">
                    <h6 class="mb-0">Apply to ${date}</h6>
                </div>
                <div class="card-body p-2">
                    <div class="d-flex flex-wrap">
                        ${Array.from(document.querySelectorAll('.badge[style*="background-color"]')).map(badge => 
                            `<button type="button" class="btn btn-sm m-1 text-white apply-day-shift" 
                                    style="background-color: ${badge.style.backgroundColor}" 
                                    data-shift-id="${badge.dataset.shiftId}" 
                                    data-day-index="${index + 1}">
                                ${badge.textContent.trim()}
                            </button>`
                        ).join('')}
                    </div>
                </div>
                <div class="card-footer p-2">
                    <button class="btn btn-sm btn-outline-secondary close-day-shifts">Close</button>
                </div>
            </div>
        `;
        header.appendChild(dayShiftSelector);
        
        // Toggle visibility of shift selector
        dayToolbar.querySelector('.show-day-shifts').addEventListener('click', function() {
            dayShiftSelector.classList.toggle('d-none');
        });
        
        // Close button
        dayShiftSelector.querySelector('.close-day-shifts').addEventListener('click', function() {
            dayShiftSelector.classList.add('d-none');
        });
        
        // Add click handlers for day shift buttons
        dayShiftSelector.querySelectorAll('.apply-day-shift').forEach(btn => {
            btn.addEventListener('click', function() {
                const shiftId = this.dataset.shiftId;
                const dayIndex = parseInt(this.dataset.dayIndex);
                
                // Apply this shift to all cells in this column
                const employeeCells = document.querySelectorAll(`#scheduleTable tr td:nth-child(${dayIndex + 1}) .shift-assignment-cell`);
                const selectedCells = Array.from(employeeCells);
                
                if (confirm(`Apply this shift to all ${selectedCells.length} employees for ${date}?`)) {
                    applyShiftToSelected(shiftId, selectedCells);
                }
            });
        });
    });
}

function assignShiftViaAjax(shiftId, employeeId, date) {
    // Show loading indicator
    const cell = document.querySelector(`.shift-assignment-cell[data-employee-id="${employeeId}"][data-date="${date}"]`);
    if (cell) {
        cell.innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
    }
    
    // Send AJAX request
    fetch('/shifts/assignment/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: new URLSearchParams({
            'employee_id': employeeId,
            'shift_id': shiftId,
            'date': date
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh the page to show updated data
            location.reload();
        } else {
            alert('Error: ' + (data.message || 'Failed to assign shift'));
            // Reset the cell
            if (cell) {
                cell.innerHTML = '<button type="button" class="btn btn-sm btn-outline-primary add-shift-btn"><i class="bi bi-plus"></i></button>';
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred. Please try again.');
        // Reset the cell
        if (cell) {
            cell.innerHTML = '<button type="button" class="btn btn-sm btn-outline-primary add-shift-btn"><i class="bi bi-plus"></i></button>';
        }
    });
}

function assignShift(shiftId, employeeId, date) {
    // Show loading indicator
    const cell = document.querySelector(`.schedule-cell[data-employee-id="${employeeId}"][data-date="${date}"]`);
    if (cell) {
        cell.innerHTML = '<div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
    }
    
    // Create a form to submit the assignment
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/shifts/assignment/add';
    
    // Add form fields
    const fields = {
        'employee_id': employeeId,
        'shift_id': shiftId,
        'start_date': date,
        'end_date': date  // Same day assignment by default
    };
    
    for (const [name, value] of Object.entries(fields)) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value;
        form.appendChild(input);
    }
    
    document.body.appendChild(form);
    form.submit();
}
