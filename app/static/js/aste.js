/**
 * Aste: paginazione delle aste concluse.
 *
 * A differenza del listone e dei movimenti, qui il server continua a disegnare
 * le schede: la pagina pesa pochi kilobyte compressi, quindi non c'e' niente da
 * alleggerire. Il problema e' solo la lunghezza dell'elenco, che cresce di
 * stagione in stagione, e per quello basta mostrarne una parte alla volta.
 *
 * Le schede che si impaginano sono quelle gia' presenti nel documento: il
 * componente le toglie e le rimette, non le ricostruisce. Non c'e' quindi
 * markup duplicato in JavaScript, e non c'e' modo che diverga dal template.
 *
 * Le aste in corso e quelle aperte alle iscrizioni restano intere: sono poche
 * per natura, e nasconderne una parte sarebbe un danno, non un aiuto.
 */

const ASTE_PER_PAGINA = 25;

document.addEventListener('DOMContentLoaded', function () {
    const elenco = document.getElementById('asteConcluse');
    const barra = document.getElementById('paginazione');
    const schede = Array.from(elenco.querySelectorAll('.asta-conclusa'));

    // Senza aste concluse l'elenco contiene solo il messaggio di elenco vuoto:
    // non e' una scheda, non va impaginato, e la barra non deve comparire.
    if (schede.length === 0) {
        barra.classList.add('hidden');
        return;
    }

    creaPaginazione({
        contenitore: barra,
        perPagina: ASTE_PER_PAGINA,
        disegna: (dellaPagina) => elenco.replaceChildren(...dellaPagina),
        risaliA: elenco,
    }).mostra(schede);
});
