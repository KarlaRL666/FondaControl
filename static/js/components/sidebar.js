const mobileMenuToggle = document.getElementById('mobileMenuToggle');
const sidebar = document.getElementById('sidebar');
const sidebarBackdrop = document.createElement('div');

sidebarBackdrop.className = 'sidebar-backdrop';
document.body.appendChild(sidebarBackdrop);

function closeSidebar() {
    if (!sidebar) {
        return;
    }
    sidebar.classList.remove('show');
    sidebarBackdrop.classList.remove('show');
    document.body.classList.remove('sidebar-open');
}

function openSidebar() {
    if (!sidebar) {
        return;
    }
    sidebar.classList.add('show');
    sidebarBackdrop.classList.add('show');
    document.body.classList.add('sidebar-open');
}

if (mobileMenuToggle && sidebar) {
    mobileMenuToggle.addEventListener('click', (event) => {
        event.preventDefault();
        if (sidebar.classList.contains('show')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });
}

// cerrar al hacer click fuera
document.addEventListener('click', (event) => {
    if (window.innerWidth <= 768 && sidebar && mobileMenuToggle) {
        const isClickInsideSidebar = sidebar.contains(event.target);
        const isClickOnToggle = mobileMenuToggle.contains(event.target);

        if (!isClickInsideSidebar && !isClickOnToggle) {
            closeSidebar();
        }
    }
});

sidebarBackdrop.addEventListener('click', closeSidebar);

document.querySelectorAll('#sidebar a.nav-link').forEach((link) => {
    link.addEventListener('click', () => {
        if (window.innerWidth <= 768) {
            closeSidebar();
        }
    });
});
