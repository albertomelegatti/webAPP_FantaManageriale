// Tempo di inattività prima dell'aggiornamento (in millisecondi).
const tempoInattivitaNecessario = 10000; 

// Variabile che conterrà l'ID del timer
let aggiornaTimer;

// --- Funzioni ---
/**
 * Resetta il timer di inattività.
 * Questa funzione viene chiamata ad ogni interazione dell'utente.
 */
function resettaTimer() {
    // 1. Cancella il timer precedente, se esiste.
    clearTimeout(aggiornaTimer); 
    
    // 2. Imposta un nuovo timer.
    // Se il tempo scade senza interazioni, la pagina si ricarica.
    aggiornaTimer = setTimeout(eseguiAggiornamento, tempoInattivitaNecessario); 
    
    // Console log (utile per il debugging, può essere rimosso)
    console.log("Timer di aggiornamento resettato.");
}
/**
 * Funzione che esegue l'aggiornamento della pagina.
 */
function eseguiAggiornamento() {
    // Prima di ricaricare, verifica se c'è un elemento che ha il focus (es. un campo di input)
    const elementoFocalizzato = document.activeElement;
    
    // Controlla se l'elemento focalizzato è un campo di input o un'area di testo
    const interazioneAttiva = elementoFocalizzato && 
                              (elementoFocalizzato.tagName === 'INPUT' || 
                               elementoFocalizzato.tagName === 'TEXTAREA' ||
                               elementoFocalizzato.tagName === 'SELECT');
    if (!interazioneAttiva) {
        console.log("Tempo scaduto. Ricarico la pagina...");
        window.location.reload();
    } else {
        // Se l'utente sta ancora scrivendo, aspetta un altro intervallo
        console.log("Interazione attiva rilevata. Riprogrammo l'aggiornamento.");
        resettaTimer(); 
    }
}
// --- Rilevamento Interazioni ---

// Array di eventi che indicano l'attività dell'utente
const eventiAttivita = [
    'mousemove',  // Movimento del mouse
    'mousedown',  // Click del mouse
    'keypress',   // Pressione di un tasto
    'scroll',     // Scroll della pagina
    'touchstart'  // Tocco (per dispositivi mobili)
];
// Collega la funzione resettaTimer a tutti gli eventi di attività
eventiAttivita.forEach(evento => {
    document.addEventListener(evento, resettaTimer, true);
});
// Avvia il timer al caricamento della pagina
resettaTimer(); 
