document.addEventListener('DOMContentLoaded', function () {
    const alerts = Array.from(document.querySelectorAll('#alerts-container .alert'));
    const seen = new Set();

    alerts.forEach((alert) => {
        const key = `${alert.dataset.category || ''}::${(alert.dataset.message || '').trim()}`;
        if (seen.has(key) || !(alert.dataset.message || '').trim()) {
            alert.remove();
            return;
        }
        seen.add(key);
    });

    const visibleAlerts = document.querySelectorAll('#alerts-container .alert');
    visibleAlerts.forEach((alert) => {
        setTimeout(() => {
            if (!alert || !alert.parentNode) {
                return;
            }
            alert.style.transition = 'all 0.35s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-8px)';
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 350);
        }, 5000);
    });
});