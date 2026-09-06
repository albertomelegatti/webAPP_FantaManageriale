function applySavedTheme() {
    const root = document.documentElement;
    const toggle = document.getElementById('darkModeToggle');
    const saved = localStorage.getItem('darkMode');

    if (saved === 'enabled') {
        root.classList.add('dark');
        if (toggle) toggle.innerHTML = '<i class="bi bi-sun"></i>';
    } else if (saved === 'disabled') {
        root.classList.remove('dark');
        if (toggle) toggle.innerHTML = '<i class="bi bi-moon"></i>';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    applySavedTheme();

    const toggle = document.getElementById('darkModeToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            const root = document.documentElement;
            root.classList.toggle('dark');
            if (root.classList.contains('dark')) {
                localStorage.setItem('darkMode', 'enabled');
                toggle.innerHTML = '<i class="bi bi-sun"></i>';
            } else {
                localStorage.setItem('darkMode', 'disabled');
                toggle.innerHTML = '<i class="bi bi-moon"></i>';
            }
        });
    }
});

window.addEventListener('pageshow', function (event) {
    if (event.persisted) applySavedTheme();
});
