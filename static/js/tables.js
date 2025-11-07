$(document).ready(function() {

    const ruoloPriority = {
        'POR': 1,
        'DD,E': 2,
        'DD,DC': 3,
        'DC': 4,
        'DD,DS,DC': 5,
        'DS,DC': 6,
        'DS,E': 7,
        'B,DD,E': 8,
        'B,DD,DS': 9,
        'B,DS,E': 10,
        'DD,DS,E': 11,
        'M,C': 12,
        'E': 13,
        'E,M': 14,
        'E,C': 15,
        'E,W': 16,
        'C,T': 17,
        'C': 18,
        'C,W,T': 19,
        'C,W': 20,
        'W': 21,
        'W,T': 22,
        'W,A': 23,
        'W,T,A': 24,
        'T,A': 25,
        'T': 26,
        'A': 27,
        'PC': 28
    };

    $.fn.dataTable.ext.type.order['ruolo-mantra-pre'] = function(data) {
        const key = data.trim().toUpperCase().replace(/\s/g, '');
        
        return ruoloPriority[key] || 99;
    };


    $('.smart-table').each(function() {
        $(this).DataTable({
            paging: false,
            searching: false,
            ordering: true,
            info: false,

            order: [[ 2, 'asc']],

            columnDefs: [
                {
                    targets: 2,
                    type: 'ruolo-mantra'
                }
            ]
        });
    });
});