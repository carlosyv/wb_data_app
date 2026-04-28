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

// ── Indicator Cart ──────────────────────────────────────────────────────────

const Cart = {
    _key: (sid) => `wb_cart_${sid}`,
    get: (sid) => JSON.parse(localStorage.getItem(Cart._key(sid)) || '{}'),
    save: (sid, data) => localStorage.setItem(Cart._key(sid), JSON.stringify(data)),
    add(sid, code, name) {
        const c = Cart.get(sid); c[code] = name; Cart.save(sid, c);
    },
    remove(sid, code) {
        const c = Cart.get(sid); delete c[code]; Cart.save(sid, c);
    },
    clear(sid) { localStorage.removeItem(Cart._key(sid)); },
    size(sid) { return Object.keys(Cart.get(sid)).length; },
};

let _sourceId = null;

function initIndicatorsPage(sourceId) {
    _sourceId = sourceId;
    if (!sourceId) return;

    const cart = Cart.get(sourceId);

    document.querySelectorAll('.indicator-checkbox').forEach(cb => {
        if (cart[cb.dataset.code]) cb.checked = true;
        cb.addEventListener('change', () => {
            cb.checked
                ? Cart.add(sourceId, cb.dataset.code, cb.dataset.name)
                : Cart.remove(sourceId, cb.dataset.code);
            updateCartBar();
        });
    });

    const selectAll = document.getElementById('select-all');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            document.querySelectorAll('.indicator-checkbox').forEach(cb => {
                cb.checked = selectAll.checked;
                selectAll.checked
                    ? Cart.add(sourceId, cb.dataset.code, cb.dataset.name)
                    : Cart.remove(sourceId, cb.dataset.code);
            });
            updateCartBar();
        });
    }

    updateCartBar();
}

function updateCartBar() {
    const n = Cart.size(_sourceId);
    const bar = document.getElementById('cart-bar');
    const count = document.getElementById('cart-count');
    if (n > 0) {
        bar.classList.remove('hidden');
        count.textContent = `${n} indicator${n !== 1 ? 's' : ''} selected`;
    } else {
        bar.classList.add('hidden');
    }
}

function clearCart() {
    Cart.clear(_sourceId);
    document.querySelectorAll('.indicator-checkbox').forEach(cb => cb.checked = false);
    const sa = document.getElementById('select-all');
    if (sa) sa.checked = false;
    updateCartBar();
}

function openCheckoutModal() {
    const cart = Cart.get(_sourceId);
    const list = document.getElementById('modal-indicator-list');
    list.innerHTML = '';
    Object.entries(cart).forEach(([code, name]) => {
        const li = document.createElement('li');
        li.className = 'flex justify-between items-center gap-2';
        const safeName = name.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        li.innerHTML = `
            <span>
                <span class="font-mono text-blue-600 dark:text-blue-400">${code}</span>
                <span class="text-gray-500 dark:text-gray-400 ml-1">&mdash; ${safeName}</span>
            </span>
            <button data-remove="${code}"
                class="text-gray-400 hover:text-red-500 text-xs shrink-0 ml-2">&times;</button>`;
        list.appendChild(li);
    });
    list.querySelectorAll('button[data-remove]').forEach(btn => {
        btn.addEventListener('click', () => removeFromModal(btn.dataset.remove));
    });
    document.getElementById('modal-error').classList.add('hidden');
    document.getElementById('checkout-modal').classList.remove('hidden');
}

function removeFromModal(code) {
    Cart.remove(_sourceId, code);
    const cb = document.querySelector(`.indicator-checkbox[data-code="${CSS.escape(code)}"]`);
    if (cb) cb.checked = false;
    updateCartBar();
    if (Cart.size(_sourceId) === 0) {
        closeCheckoutModal();
    } else {
        openCheckoutModal();
    }
}

function closeCheckoutModal() {
    document.getElementById('checkout-modal').classList.add('hidden');
}

async function submitJob() {
    const codes = Object.keys(Cart.get(_sourceId));
    if (!codes.length) return;

    const rawCountries = document.getElementById('modal-countries').value.trim();
    const countryCodes = rawCountries === 'all'
        ? ['all']
        : rawCountries.split('\n').map(s => s.trim()).filter(Boolean);

    const yearStart = parseInt(document.getElementById('modal-year-start').value, 10);
    const yearEnd = parseInt(document.getElementById('modal-year-end').value, 10);

    const errEl = document.getElementById('modal-error');
    if (!countryCodes.length) {
        errEl.textContent = 'Enter at least one country code or "all".';
        errEl.classList.remove('hidden');
        return;
    }

    const btn = document.querySelector('#checkout-modal button[onclick="submitJob()"]');
    btn.disabled = true;
    btn.textContent = 'Submitting…';

    try {
        const res = await fetch('/api/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_id: _sourceId,
                indicator_codes: codes,
                country_codes: countryCodes,
                year_start: yearStart,
                year_end: yearEnd,
            }),
        });
        if (!res.ok) throw new Error(await res.text());
        Cart.clear(_sourceId);
        window.location.href = '/jobs';
    } catch (e) {
        errEl.textContent = `Error: ${e.message}`;
        errEl.classList.remove('hidden');
        btn.disabled = false;
        btn.textContent = 'Submit Job';
    }
}
