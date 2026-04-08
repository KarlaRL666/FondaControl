document.addEventListener('DOMContentLoaded', function() {
    // ==================== ELEMENTOS ====================
    const searchInput = document.getElementById('searchInput');
    const roleFilter = document.getElementById('roleFilter');
    const statusFilter = document.getElementById('statusFilter');
    const userTable = document.querySelector('table.data-table');

    if (!searchInput || !roleFilter || !statusFilter || !userTable) {
        console.error('❌ Elementos del filtro no encontrados. Revisa los IDs en el HTML.');
        return;
    }

    console.log('✅ Gestión de usuarios cargada correctamente');

    // ==================== FILTRADO ====================
    function filterTable() {
        const searchValue = searchInput.value.toLowerCase().trim();
        const roleValue = roleFilter.value;
        const statusValue = statusFilter.value;

        const rows = userTable.querySelectorAll('tbody tr.user-row');
        let visibleCount = 0;

        rows.forEach((row) => {
            const nombre = (row.getAttribute('data-nombre') || '').toLowerCase();
            const rol = (row.getAttribute('data-rol') || '').toLowerCase();
            const estado = row.getAttribute('data-estado') || '';

            const matchesSearch = nombre.includes(searchValue) || 
                                  row.textContent.toLowerCase().includes(searchValue);
            
            const matchesRole = roleValue === 'all' || rol === roleValue.toLowerCase();
            const matchesStatus = statusValue === 'all' || estado === statusValue;

            const shouldShow = matchesSearch && matchesRole && matchesStatus;

            row.style.display = shouldShow ? '' : 'none';
            
            if (shouldShow) visibleCount++;
        });

        updateCounter(visibleCount);
    }
    
    function updateCounter(count) {
        const totalCount = document.getElementById('totalCount');
        if (totalCount) totalCount.textContent = count;
    }

function submitAction(url, id, titulo, mensaje, colorConfirm) {
    Swal.fire({
        title: titulo,
        html: mensaje,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: colorConfirm,
        cancelButtonColor: '#6b7280',
        confirmButtonText: 'Sí, confirmar',
        cancelButtonText: 'Cancelar',
        reverseButtons: false
    }).then((result) => {
        if (result.isConfirmed) {
            // Obtener el token CSRF fresco cada vez
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

            if (!csrfToken) {
                Swal.fire('Error', 'No se pudo obtener el token de seguridad. Recarga la página.', 'error');
                return;
            }

            const form = document.createElement('form');
            form.method = 'POST';
            form.action = url;

            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = csrfToken;

            const idInput = document.createElement('input');
            idInput.type = 'hidden';
            idInput.name = 'id_usuario';
            idInput.value = id;

            form.appendChild(csrfInput);
            form.appendChild(idInput);
            document.body.appendChild(form);
            form.submit();
        }
    });
}

window.desactivarUsuario = function(id, nombre) {
    submitAction(
        '/usuarios/desactivar',
        id,
        '¿Desactivar usuario?',
        `¿Estás seguro de desactivar a <strong>${nombre}</strong>?`,
        '#ef4444'   // rojo
    );
};

// ==================== ACTIVAR ====================
window.activarUsuario = function(id, nombre) {
    submitAction(
        '/usuarios/activar',
        id,
        '¿Activar usuario?',
        `¿Deseas activar nuevamente a <strong>${nombre}</strong>?`,
        '#10b981'   // verde
    );
};

    // ==================== EVENT LISTENERS ====================
    searchInput.addEventListener('input', filterTable);
    roleFilter.addEventListener('change', filterTable);
    statusFilter.addEventListener('change', filterTable);

    // Filtro inicial
    filterTable();
});