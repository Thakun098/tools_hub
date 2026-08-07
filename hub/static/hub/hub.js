'use strict';

// ── State ────────────────────────────────────────────────────────
let plugins = [];
let toastTimer;

// ── DOM helpers ──────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function showToast(message) {
    $('toast-message').textContent = message;
    $('toast').classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $('toast').classList.remove('show'), 2600);
}

// ── Theme ────────────────────────────────────────────────────────
const themeNames = ['terminal', 'editorial'];
const themeNotes = { terminal: 'Focused, compact, keyboard-friendly', editorial: 'Calm, considered, content-led' };
const themeButtons = [...document.querySelectorAll('[data-theme-choice]')];

function setTheme(theme) {
    document.body.dataset.theme = theme;
    themeButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.themeChoice === theme));
    $('theme-note').textContent = themeNotes[theme];
    localStorage.setItem('tools-hub-theme', theme);
}

themeButtons.forEach(btn => btn.addEventListener('click', () => setTheme(btn.dataset.themeChoice)));
$('theme-cycle').addEventListener('click', () => {
    const next = themeNames[(themeNames.indexOf(document.body.dataset.theme) + 1) % themeNames.length];
    setTheme(next); showToast('Switched to ' + next + ' theme');
});

// ── Search ───────────────────────────────────────────────────────
const search = $('search');
search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    const rows = [...document.querySelectorAll('.tool-row')];
    let visible = 0;
    rows.forEach(row => {
        const match = (row.dataset.tool || '').includes(query);
        row.style.display = match ? '' : 'none';
        if (match) visible++;
    });
    $('empty-state').style.display = visible ? 'none' : 'block';
});

// ── Nav tabs ─────────────────────────────────────────────────────
document.querySelectorAll('.nav-button[data-tab]').forEach(button => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.nav-button[data-tab]').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        $('crumb-label').textContent = button.querySelector('span')?.textContent || button.dataset.tab;
    });
});

// ── Plugin rendering ─────────────────────────────────────────────
const ICON_GRADIENTS = {
    free_srt: 'linear-gradient(135deg,#ee725d,#c83251)',
    free_tts: 'linear-gradient(135deg,#2cc6ae,#167b90)',
};
const ICON_FALLBACK = 'linear-gradient(135deg,#7d67ff,#3d22ae)';

function pluginShortName(name) {
    // Create 2-3 letter abbreviation from name
    return name.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 3);
}

function renderPlugins(list) {
    const container = $('tool-list');
    container.innerHTML = '';
    if (!list.length) {
        $('empty-state').style.display = 'block';
        $('panel-meta').textContent = 'No plugins found';
        return;
    }
    $('empty-state').style.display = 'none';
    const installed = list.filter(p => p.loaded).length;
    $('panel-meta').textContent = `${list.length} programs · ${installed} installed`;
    $('nav-update-count').textContent = '0';

    list.forEach(plugin => {
        const row = document.createElement('article');
        row.className = 'tool-row';
        row.dataset.tool = plugin.name.toLowerCase();
        row.dataset.installed = String(plugin.loaded);

        const gradient = ICON_GRADIENTS[plugin.id] || ICON_FALLBACK;
        const short = pluginShortName(plugin.name);
        const tags = plugin.loaded
            ? `<span class="tag green">Installed</span><span class="tag">v${plugin.version}</span>`
            : plugin.error
                ? `<span class="tag" style="color:var(--danger)">Error</span>`
                : `<span class="tag">v${plugin.version}</span>`;

        const statusText = plugin.loaded ? 'Ready' : (plugin.error ? 'Failed' : 'Available');
        const buttonHtml = plugin.loaded
            ? `<button class="button small ghost launch-btn" data-url="${plugin.url_prefix}/">Launch</button>`
            : plugin.error
                ? `<button class="button small" disabled title="${plugin.error}">Error</button>`
                : `<button class="button small" disabled>Not available</button>`;

        row.innerHTML = `
            <div class="tool-icon" style="background:${gradient}">${plugin.icon || short}</div>
            <div class="tool-info">
                <div class="tool-name">${plugin.name}</div>
                <div class="tool-desc">${plugin.description}</div>
                <div class="tool-tags">${tags}</div>
            </div>
            <div class="tool-actions">
                <div class="status">${statusText}</div>
                ${buttonHtml}
            </div>`;
        container.appendChild(row);
    });

    // Attach launch handlers
    document.querySelectorAll('.launch-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            showToast(`Launching ${btn.closest('.tool-row').querySelector('.tool-name').textContent}…`);
            setTimeout(() => { window.location.href = btn.dataset.url; }, 300);
        });
    });
}

// ── Fetch plugins from Hub API ───────────────────────────────────
async function fetchPlugins() {
    try {
        const response = await fetch('/api/hub/plugins');
        if (!response.ok) throw new Error('Failed to load plugins');
        plugins = await response.json();
        renderPlugins(plugins);
    } catch (error) {
        console.error('[hub]', error);
        $('panel-meta').textContent = 'Could not load plugin list';
        showToast('Failed to load plugins');
    }
}

// ── Init ─────────────────────────────────────────────────────────
(function init() {
    // Restore saved theme
    const saved = localStorage.getItem('tools-hub-theme');
    if (saved && themeNames.includes(saved)) setTheme(saved);

    // Hide update banner (no update system yet)
    const banner = $('update-banner');
    if (banner) banner.style.display = 'none';

    // Load plugins
    fetchPlugins();
})();
