// La logica che deve essere eseguita sia al carico normale che al ripristino da BFCache.
function applySavedTheme() {
    const body = document.body;
    const toggleButton = document.getElementById("darkModeToggle");
    const savedMode = localStorage.getItem("darkMode");

    if (savedMode === "enabled") {
        // Applica Dark Mode
        body.classList.add("dark-mode");
        // Imposta icona su SOLE (per tornare a Light Mode)
        if (toggleButton) {
            toggleButton.innerHTML = '<i class="bi bi-sun"></i>';
        }
    } else if (savedMode === "disabled") {
        // Applica Light Mode (se disabilitata esplicitamente)
        body.classList.remove("dark-mode");
        // Imposta icona su LUNA (per attivare Dark Mode)
        if (toggleButton) {
            toggleButton.innerHTML = '<i class="bi bi-moon"></i>';
        }
    }
}

// 1. Esecuzione al Caricamento Standard del DOM (prima volta e refresh)
document.addEventListener("DOMContentLoaded", function() {
    applySavedTheme(); // Applica subito il tema

    const toggleButton = document.getElementById("darkModeToggle");
    const body = document.body;
    
    // 2. LOGICA al CLICK: Gestisce il cambio e il salvataggio
    if (toggleButton) {
        toggleButton.addEventListener("click", () => {
            // Alterna la classe CSS
            body.classList.toggle("dark-mode");

            // Salva la preferenza e aggiorna l'icona
            if (body.classList.contains("dark-mode")) {
                localStorage.setItem("darkMode", "enabled");
                toggleButton.innerHTML = '<i class="bi bi-sun"></i>';
            } else {
                localStorage.setItem("darkMode", "disabled");
                toggleButton.innerHTML = '<i class="bi bi-moon"></i>';
            }
        });
    }
});

// 3. Soluzione BFCache: Esecuzione al ripristino con tasto 'Indietro'/'Avanti'
window.addEventListener('pageshow', function(event) {
    // Se la pagina è stata ripristinata dalla cache (navigazione Back/Forward)
    if (event.persisted) {
        applySavedTheme(); 
    }
});