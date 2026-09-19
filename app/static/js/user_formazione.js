document.addEventListener('DOMContentLoaded', function () {
    const selectModulo = document.getElementById('selectModulo');
    const formModulo = document.getElementById('formModulo');
    if (selectModulo && formModulo) {
        selectModulo.addEventListener('change', function () {
            formModulo.submit();
        });
    }
});
