// Rende tutte le tabelle con classe 'smart-table' interattive
$(document).ready(function() {
    $('.smart-table').each(function() {
        $(this).DataTable({
            paging: true,        // paginazione
            searching: true,     // barra di ricerca
            ordering: true,      // ordinamento cliccando sulle colonne
            info: false          // mostra info (righe totali) opzionale
        });
    });
});
