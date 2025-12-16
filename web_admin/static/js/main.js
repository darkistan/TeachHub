// Main JS for Schedule Bot Admin Panel

// ========== THEME TOGGLE ==========
document.addEventListener('DOMContentLoaded', function() {
    // Завантажуємо збережену тему (за замовчуванням - темна)
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
    
    // Обробник перемикача (перевіряємо наявність елемента)
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-bs-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            setTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
});

function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    document.body.setAttribute('data-bs-theme', theme);
    
    const icon = document.getElementById('theme-icon');
    if (icon) {
        if (theme === 'dark') {
            icon.className = 'bi bi-sun-fill';
        } else {
            icon.className = 'bi bi-moon-stars-fill';
        }
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
    // Перевіряємо наявність елемента статусу тривоги
    if (document.getElementById('alert-status')) {
        updateAlertStatus();
        setInterval(updateAlertStatus, 60000); // Кожну хвилину
    }
});

// ========== ACTIVE NAVIGATION HIGHLIGHTING ==========
document.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        // Перевіряємо точне співпадіння або початок шляху
        if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        }
    });
    
    // Також перевіряємо dropdown items
    const dropdownItems = document.querySelectorAll('.dropdown-item');
    dropdownItems.forEach(item => {
        const href = item.getAttribute('href');
        if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
            item.classList.add('active');
            // Підсвічуємо батьківський dropdown
            const dropdown = item.closest('.dropdown');
            if (dropdown) {
                const dropdownToggle = dropdown.querySelector('.dropdown-toggle');
                if (dropdownToggle) {
                    dropdownToggle.classList.add('active');
                }
            }
        }
    });
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

// ========== FORM LOADING INDICATORS ==========
document.addEventListener('DOMContentLoaded', function() {
    // Знаходимо всі форми
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitBtn && !form.classList.contains('no-loading')) {
                // Додаємо індикатор завантаження
                const originalText = submitBtn.innerHTML;
                submitBtn.disabled = true;
                submitBtn.classList.add('btn-loading');
                
                // Додаємо spinner
                if (!submitBtn.querySelector('.spinner-border')) {
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ' + originalText;
                }
                
                // Додаємо клас до форми для візуального ефекту
                form.classList.add('form-loading');
                
                // Якщо форма не відправляється (помилка валідації), повертаємо стан
                setTimeout(() => {
                    if (!form.dataset.submitted) {
                        submitBtn.disabled = false;
                        submitBtn.classList.remove('btn-loading');
                        submitBtn.innerHTML = originalText;
                        form.classList.remove('form-loading');
                    }
                }, 100);
            }
            
            // Позначаємо форму як відправлену
            form.dataset.submitted = 'true';
        });
    });
});

// ========== KEYBOARD SHORTCUTS ==========
document.addEventListener('keydown', function(e) {
    // Esc - закрити модальні вікна
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
        });
    }
    
    // Ctrl+K або Cmd+K - фокус на пошук (якщо є)
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="Пошук"], input[id*="search"]');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }
    
    // / - фокус на пошук (якщо не в input/textarea)
    if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="Пошук"], input[id*="search"]');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }
});
