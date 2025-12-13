// Main JS for Schedule Bot Admin Panel

// ========== THEME TOGGLE ==========
document.addEventListener('DOMContentLoaded', function() {
    // Завантажуємо збережену тему (за замовчуванням - темна)
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
    
    // Обробник перемикача
    document.getElementById('theme-toggle').addEventListener('click', function() {
        const currentTheme = document.documentElement.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
        localStorage.setItem('theme', newTheme);
    });
});

function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    document.body.setAttribute('data-bs-theme', theme);
    
    const icon = document.getElementById('theme-icon');
    if (theme === 'dark') {
        icon.className = 'bi bi-sun-fill';
    } else {
        icon.className = 'bi bi-moon-stars-fill';
    }
}

// ========== AIR ALERT STATUS ==========
async function updateAlertStatus() {
    try {
        const response = await fetch('/api/alert-status');
        const data = await response.json();
        
        const statusElement = document.getElementById('alert-status');
        if (data.alert) {
            // Активна тривога
            statusElement.innerHTML = `
                <span class="badge bg-danger pulse-animation">
                    <i class="bi bi-exclamation-triangle-fill"></i> ${data.message}
                </span>
            `;
        } else {
            // Тихо
            statusElement.innerHTML = `
                <span class="badge bg-success">
                    <i class="bi bi-shield-check"></i> ${data.message}
                </span>
            `;
        }
    } catch (error) {
        document.getElementById('alert-status').innerHTML = `
            <span class="badge bg-secondary">
                <i class="bi bi-question-circle"></i> Статус недоступний
            </span>
        `;
    }
}

// Оновлюємо статус при завантаженні та кожну хвилину
document.addEventListener('DOMContentLoaded', function() {
    updateAlertStatus();
    setInterval(updateAlertStatus, 60000); // Кожну хвилину
});

// ========== AUTO-DISMISS ALERTS ==========
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
