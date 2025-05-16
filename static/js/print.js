/**
 * Enhanced print functionality for MIR AMS reports
 */

document.addEventListener('DOMContentLoaded', function() {
    // Add print button event listeners
    const printButtons = document.querySelectorAll('.print-report-btn, [onclick*="window.print"]');
    
    printButtons.forEach(button => {
        button.addEventListener('click', function(event) {
            // If using onclick attribute, prevent default to use our enhanced version
            if (this.getAttribute('onclick') && this.getAttribute('onclick').includes('window.print')) {
                event.preventDefault();
            }
            
            // Prepare page for printing
            prepareForPrint();
            
            // Execute print
            window.print();
            
            // Restore page after print dialog closes
            window.onafterprint = function() {
                restoreAfterPrint();
            };
        });
    });
});

/**
 * Prepare the page for printing
 */
function prepareForPrint() {
    // Hide elements that shouldn't be printed
    document.querySelectorAll('header, nav, .sidebar, .no-print, .btn:not(.print-only), input[type="submit"], input[type="button"], button:not(.print-only)').forEach(el => {
        el.dataset.printHidden = true;
        el.style.display = 'none';
    });
    
    // Expand content to full width
    document.querySelectorAll('.col-md-9').forEach(el => {
        el.dataset.printClass = el.className;
        el.className = 'col-12';
    });
    
    // Hide sidebar columns
    document.querySelectorAll('.col-md-3').forEach(el => {
        el.dataset.printHidden = true;
        el.style.display = 'none';
    });
    
    // Ensure tables show all rows
    document.querySelectorAll('.dataTables_wrapper').forEach(wrapper => {
        try {
            // Find the DataTable instance
            const tableElement = wrapper.querySelector('table.dataTable');
            
            // Check if jQuery and DataTable are available
            if (typeof $ === 'undefined' || typeof $.fn.DataTable === 'undefined') {
                console.warn('DataTables library not available, skipping table preparation for print');
                return;
            }
            
            // Check if the element is a DataTable
            if (tableElement && $.fn.DataTable.isDataTable(tableElement)) {
                const dt = $(tableElement).DataTable();
                
                // Safely access DataTable methods with existence checks
                let currentPage = 0;
                let currentLength = 10;
                
                try {
                    // Check if these methods exist before calling them
                    if (typeof dt.page === 'function') {
                        currentPage = dt.page() || 0;
                    }
                    
                    if (typeof dt.page === 'object' && typeof dt.page.len === 'function') {
                        currentLength = dt.page.len() || 10;
                    }
                } catch (dtError) {
                    console.warn('Could not get DataTable pagination state:', dtError);
                }
                
                // Store current state
                wrapper.dataset.printState = JSON.stringify({
                    page: currentPage,
                    length: currentLength
                });
                
                // Show all rows - with safety checks
                try {
                    if (typeof dt.page === 'object' && typeof dt.page.len === 'function' && typeof dt.draw === 'function') {
                        dt.page.len(-1).draw(false); // Use false to avoid full redraw which can be expensive
                    }
                } catch (drawError) {
                    console.warn('Error showing all rows:', drawError);
                }
            }
        } catch (error) {
            console.error('Error preparing DataTable for print:', error);
        }
    });
}

/**
 * Restore the page after printing
 */
function restoreAfterPrint() {
    // Restore hidden elements
    document.querySelectorAll('[data-print-hidden="true"]').forEach(el => {
        el.style.display = '';
        delete el.dataset.printHidden;
    });
    
    // Restore original classes
    document.querySelectorAll('[data-print-class]').forEach(el => {
        el.className = el.dataset.printClass;
        delete el.dataset.printClass;
    });
    
    // Restore table state
    document.querySelectorAll('.dataTables_wrapper[data-print-state]').forEach(wrapper => {
        try {
            // Find the DataTable instance
            const tableElement = wrapper.querySelector('table.dataTable');
            if (tableElement && $.fn.DataTable.isDataTable(tableElement)) {
                const dt = $(tableElement).DataTable();
                
                // Get stored state
                const state = JSON.parse(wrapper.dataset.printState);
                
                // Restore pagination
                dt.page.len(state.length).page(state.page).draw();
            }
            
            delete wrapper.dataset.printState;
        } catch (error) {
            console.error('Error restoring DataTable after print:', error);
        }
    });
}