/* FondaControl – Main JavaScript */

// ── Live clock ──────────────────────────────────────
(function startClock() {
  function tick() {
    const el = document.getElementById('clock');
    if (el) {
      el.textContent = new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    }
  }
  tick();
  setInterval(tick, 30000);
})();

// ── Sidebar toggle ──────────────────────────────────
(function setupSidebar() {
  const btn = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if (!btn || !sidebar) return;

  btn.addEventListener('click', () => {
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
      sidebar.classList.toggle('open');
    } else {
      sidebar.classList.toggle('collapsed');
    }
  });

  // Close sidebar on mobile when clicking outside
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        e.target !== btn) {
      sidebar.classList.remove('open');
    }
  });
})();

// ── Auto-dismiss flash messages ─────────────────────
(function autoDismissAlerts() {
  setTimeout(() => {
    document.querySelectorAll('.alert.fade.show').forEach(alert => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    });
  }, 5000);
})();

// ── Confirm dangerous actions ────────────────────────
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', (e) => {
    if (!confirm(el.dataset.confirm)) e.preventDefault();
  });
});
