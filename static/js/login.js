document.addEventListener("DOMContentLoaded", () => {
    const passwordField = document.getElementById('password-field');
    const togglePassword = document.getElementById('togglePassword');

    togglePassword.addEventListener('click', () => {
        const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordField.setAttribute('type', type);
        
        // Cambia icona
        togglePassword.classList.toggle('bi-eye');
        togglePassword.classList.toggle('bi-eye-slash');
    });
});
