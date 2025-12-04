// Main JS for Schedule Bot Admin Panel

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        let alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            let bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});

// Confirmation dialogs
function confirmDelete(itemName) {
    return confirm('Видалити ' + itemName + '? Цю дію не можна буде скасувати.');
}

// Format time input
function formatTimeInput(input) {
    let value = input.value.replace(/[^0-9]/g, '');
    if (value.length >= 4) {
        input.value = value.substring(0, 2) + ':' + value.substring(2, 4) + '-' + value.substring(4, 6) + ':' + value.substring(6, 8);
    }
}

// Validate time format
function validateTime(timeStr) {
    const regex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]-([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
    return regex.test(timeStr);
}

// Calculate weeks between dates
function calculateWeeks(startDate, endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffTime = Math.abs(end - start);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return Math.ceil(diffDays / 7);
}

// Auto-calculate weeks for academic periods
document.addEventListener('DOMContentLoaded', function() {
    const startDateInput = document.querySelector('input[name="start_date"]');
    const endDateInput = document.querySelector('input[name="end_date"]');
    const weeksInput = document.querySelector('input[name="weeks"]');
    
    if (startDateInput && endDateInput && weeksInput) {
        function updateWeeks() {
            if (startDateInput.value && endDateInput.value) {
                const weeks = calculateWeeks(startDateInput.value, endDateInput.value);
                weeksInput.value = weeks;
            }
        }
        
        startDateInput.addEventListener('change', updateWeeks);
        endDateInput.addEventListener('change', updateWeeks);
    }
});

// Search functionality
function searchTable(inputId, tableId) {
    const input = document.getElementById(inputId);
    const filter = input.value.toLowerCase();
    const table = document.getElementById(tableId);
    const rows = table.getElementsByTagName('tr');
    
    for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
    }
}

// Toast notifications
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.appendChild(container);
    return container;
}

console.log('Schedule Bot Admin Panel v2.0 loaded successfully');
