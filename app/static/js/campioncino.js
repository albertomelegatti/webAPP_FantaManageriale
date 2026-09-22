/**
 * Il campioncino nel modal di dettaglio giocatore: nascosto se il giocatore
 * non e' ancora abbinato, nascosto anche se il caricamento fallisce (stesso
 * comportamento del sito sorgente, vedi app/core/formato.py). Condiviso da
 * dashboard_squadra.js e listone.js, che aprono lo stesso modal.
 */
function mostraCampioncinoModal(elemento, url) {
    if (url) {
        elemento.onerror = function () {
            elemento.onerror = null;
            elemento.classList.add('hidden');
        };
        elemento.src = url;
        elemento.classList.remove('hidden');
    } else {
        elemento.removeAttribute('src');
        elemento.classList.add('hidden');
    }
}
