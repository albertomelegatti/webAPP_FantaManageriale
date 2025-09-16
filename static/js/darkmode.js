document.addEventListener("DOMContentLoaded", function() {
    const toggleButton = document.getElementById("darkModeToggle");
    const body = document.body;

    // Recupera preferenza salvata
    if (localStorage.getItem("darkMode") === "enabled") {
        body.classList.add("dark-mode");
        toggleButton.innerHTML = '<i class="bi bi-sun"></i>';
    }

    toggleButton.addEventListener("click", () => {
        body.classList.toggle("dark-mode");

        if (body.classList.contains("dark-mode")) {
            localStorage.setItem("darkMode", "enabled");
            toggleButton.innerHTML = '<i class="bi bi-sun"></i>';
        } else {
            localStorage.setItem("darkMode", "disabled");
            toggleButton.innerHTML = '<i class="bi bi-moon"></i>';
        }
    });
});
