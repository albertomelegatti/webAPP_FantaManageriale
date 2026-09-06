/**
 * Script per l'effetto nevicata utilizzando la libreria tsParticles Confetti.
 * Assicurarsi che la libreria sia caricata nel template base prima di questo script.
 */

(function () {
    // Funzione per generare numeri casuali in un range
    function randomInRange(min, max) {
        return Math.random() * (max - min) + min;
    }

    // Funzione principale dell'animazione
    function startSnowfall() {
        const duration = 15 * 1000;
        const animationEnd = Date.now() + duration;
        let skew = 1;

        function frame() {
            const timeLeft = animationEnd - Date.now();
            const ticks = Math.max(200, 500 * (timeLeft / duration));

            skew = Math.max(0.8, skew - 0.001);

            // Chiamata alla funzione confetti configurata come neve
            confetti({
                particleCount: 1,
                startVelocity: 0,
                ticks: ticks,
                origin: {
                    x: Math.random(),
                    y: Math.random() * skew - 0.2, // Fa partire i fiocchi dall'alto
                },
                colors: ["#ffffff"],
                shapes: ["circle"],
                gravity: randomInRange(0.4, 0.6),
                scalar: randomInRange(0.4, 1),
                drift: randomInRange(-0.4, 0.4),
            });

            // Continua l'animazione all'infinito (o finché la pagina è aperta)
            // Se vuoi che la neve non si fermi mai dopo 15 secondi, 
            // basta rimuovere il controllo del tempo o resettare animationEnd.
            if (timeLeft < 0) {
                // Reset per rendere la nevicata infinita
                startSnowfall(); 
                return;
            }

            requestAnimationFrame(frame);
        }

        requestAnimationFrame(frame);
    }

    // Avvio della nevicata al caricamento
    startSnowfall();
})();