/**
 * Minimal JS for the WB Data Browser.
 * Most interactivity is handled by HTMX; this file provides helpers.
 */

// Theme toggle
function toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// Debounce helper for search inputs
function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

// Auto-submit search forms on input with debounce
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[data-auto-submit]').forEach(input => {
        input.addEventListener('input', debounce(() => {
            input.closest('form')?.submit();
        }, 400));
    });
});
