document.addEventListener('DOMContentLoaded', function () {
    const loghiBase = document.getElementById('paginaSquadra').dataset.loghiBase;
    const overlayGiocatore = document.getElementById('overlayGiocatore');
    const btnChiudiGiocatore = document.getElementById('btnChiudiGiocatore');
    const modalNome = document.getElementById('modalNome');
    const modalCampioncino = document.getElementById('modalCampioncino');
    const modalRuolo = document.getElementById('modalRuolo');
    const modalClub = document.getElementById('modalClub');
    const modalSquadra = document.getElementById('modalSquadra');
    const modalDetentoreRow = document.getElementById('modalDetentoreRow');
    const modalDetentore = document.getElementById('modalDetentore');
    const modalContratto = document.getElementById('modalContratto');
    const modalDataNascita = document.getElementById('modalDataNascita');
    const modalScadenzaContratto = document.getElementById('modalScadenzaContratto');
    const modalValoreMercato = document.getElementById('modalValoreMercato');
    const modalQuotazione = document.getElementById('modalQuotazione');
    const modalCosto = document.getElementById('modalCosto');

    // Placeholder per i dati non ancora sincronizzati da Transfermarkt: testo
    // attenuato e corsivo per distinguerli a colpo d'occhio da un valore reale.
    const impostaCampoTransfermarkt = (elemento, valore) => {
        const nonSincronizzato = String(valore).startsWith('Non sincronizzat');
        elemento.textContent = valore;
        elemento.classList.toggle('text-muted', nonSincronizzato);
        elemento.classList.toggle('italic', nonSincronizzato);
        elemento.classList.toggle('font-medium', !nonSincronizzato);
    };

    const logoUrl = (username) => loghiBase + (username || 'svincolato') + '.png';

    const squadraHtml = (nome, username) =>
        '<img src="' + logoUrl(username) + '" alt="" class="h-5 w-5 object-contain">' +
        '<span>' + (nome || 'Svincolato') + '</span>';

    const apriCardGiocatore = (info) => {
        modalNome.textContent = info.nome;
        if (info.campioncino) {
            // Non tutti i giocatori hanno la caricatura disegnata a mano (vedi
            // app/core/formato.py): se l'immagine non carica si nasconde,
            // niente ripiego su uno stile diverso (card statistica, sagoma
            // anonima) che stonerebbe col resto della rosa.
            modalCampioncino.onerror = function () {
                modalCampioncino.onerror = null;
                modalCampioncino.classList.add('hidden');
            };
            modalCampioncino.src = info.campioncino;
            modalCampioncino.classList.remove('hidden');
        } else {
            modalCampioncino.removeAttribute('src');
            modalCampioncino.classList.add('hidden');
        }
        modalRuolo.textContent = info.ruolo.split(',').map(r => r.trim()).join(', ');
        modalClub.textContent = info.club;
        modalSquadra.innerHTML = squadraHtml(info.squadra_att, info.squadra_username);
        if (info.detentore && info.detentore !== info.squadra_att) {
            modalDetentore.innerHTML = squadraHtml(info.detentore, info.detentore_username);
            modalDetentoreRow.classList.remove('hidden');
            modalDetentoreRow.classList.add('flex');
        } else {
            modalDetentoreRow.classList.add('hidden');
            modalDetentoreRow.classList.remove('flex');
        }
        modalContratto.textContent = info.tipo_contratto || '-';
        impostaCampoTransfermarkt(modalDataNascita, info.data_nascita);
        impostaCampoTransfermarkt(modalScadenzaContratto, info.scadenza_contratto_reale);
        impostaCampoTransfermarkt(modalValoreMercato, info.valore_mercato);
        modalQuotazione.textContent = info.quotazione;
        modalCosto.textContent = info.costo;

        overlayGiocatore.classList.remove('hidden');
        overlayGiocatore.classList.add('flex');
    };

    const chiudiCardGiocatore = () => {
        overlayGiocatore.classList.add('hidden');
        overlayGiocatore.classList.remove('flex');
    };

    // Delega unica per tutte le tabelle della pagina (rosa, primavera, prestiti
    // in entrata e in uscita, pick del draft gia' usate).
    document.addEventListener('click', function (e) {
        const row = e.target.closest('tr[data-info]');
        if (!row) return;
        apriCardGiocatore(JSON.parse(row.dataset.info));
    });

    btnChiudiGiocatore.addEventListener('click', chiudiCardGiocatore);
    overlayGiocatore.addEventListener('click', function (e) {
        if (e.target === overlayGiocatore) chiudiCardGiocatore();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') chiudiCardGiocatore();
    });

    // Menù a tab: Rosa / Primavera / Draft / Prestiti. Le quattro sezioni sono
    // già tutte renderizzate dal server (stesso dato, nessuna query in più): il
    // click mostra solo il pannello corrispondente e nasconde gli altri.
    const tab = document.querySelectorAll('.tab-squadra');
    const pannelli = document.querySelectorAll('.pannello-squadra');
    tab.forEach(function (btn) {
        btn.addEventListener('click', function () {
            tab.forEach(t => t.setAttribute('aria-selected', String(t === btn)));
            pannelli.forEach(p => p.classList.toggle('hidden', p.dataset.panel !== btn.dataset.tab));
        });
    });
});
