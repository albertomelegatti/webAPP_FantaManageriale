document.addEventListener('DOMContentLoaded', function () {
    const selectModulo = document.getElementById('selectModulo');
    const formModulo = document.getElementById('formModulo');
    if (selectModulo && formModulo) {
        selectModulo.addEventListener('change', function () {
            formModulo.submit();
        });
    }

    const campo = document.getElementById('campoFormazione');
    if (!campo) return;

    const linee = JSON.parse(campo.dataset.linee);
    const rosa = JSON.parse(campo.dataset.rosa);
    const MAX_RISERVE = Number(campo.dataset.maxRiserve) || 4;
    const inputNascosti = document.getElementById('inputNascosti');
    const panchinariEl = document.getElementById('panchinari');
    const avviso = document.getElementById('avvisoTrascina');
    const overlay = document.getElementById('overlayPosto');
    const btnChiudi = document.getElementById('btnChiudiPicker');
    const pickerTitolo = document.getElementById('pickerTitolo');
    const pickerLista = document.getElementById('pickerLista');

    // Stesso schema colore per ruolo della macro ruolo_colorato in _macros.html:
    // va tenuto allineato se quella cambia.
    const COLORE_RUOLO = {
        por: '#e0951b',
        dd: '#22a558', ds: '#22a558', dc: '#22a558', b: '#22a558',
        e: '#3f7fff', m: '#3f7fff', c: '#3f7fff',
        w: '#a855f7', t: '#a855f7',
        a: '#ef4444', pc: '#ef4444',
    };
    // etichetta e' "/"-separata per gli slot (slot_label in app/domini/moduli.py,
    // es. "W/A") ma ","-separata per il ruolo di un giocatore (pulisci_ruolo,
    // es. "Dd,Dc"): stessa funzione per entrambi, split su entrambi i separatori.
    const coloreEtichetta = (etichetta) => COLORE_RUOLO[etichetta.split(/[,/]/)[0].trim().toLowerCase()] || '#5a6570';

    const perId = new Map(rosa.map((g) => [g.id, g]));
    const slots = new Map();
    for (const riga of linee) {
        for (const slot of riga) {
            slots.set(slot.indice, slot);
        }
    }
    const ammessi = new Map([...slots.values()].map((s) => [s.indice, new Set(s.ammessi)]));
    const compatibile = (id, indice) => ammessi.get(indice).has(id);
    const schierabile = (id) => [...ammessi.values()].some((a) => a.has(id));

    // Stato corrente lato client: per ogni slot il titolare e la panchina
    // (lista di id, in ordine di chiamata). Parte da quanto renderizzato dal
    // server: la formazione salvata, vuota o la proposta di "Ottimizza".
    const tit = new Map();
    const ris = new Map();
    for (const slot of slots.values()) {
        tit.set(slot.indice, slot.selezionati.tit);
        ris.set(slot.indice, slot.selezionati.ris.slice());
    }

    // --- Operazioni sullo stato ------------------------------------------

    function dove(id) {
        for (const [indice, t] of tit) {
            if (t === id) return { slot: indice, posto: 'tit' };
            const i = ris.get(indice).indexOf(id);
            if (i >= 0) return { slot: indice, posto: 'ris', idx: i };
        }
        return null;
    }

    function togli(id) {
        const d = dove(id);
        if (!d) return null;
        if (d.posto === 'tit') tit.set(d.slot, null);
        else ris.get(d.slot).splice(d.idx, 1);
        return d;
    }

    // Uno slot senza titolare non tiene riserve in attesa: la prima sale
    // in campo (stessa regola del Campetto Lega).
    function promuovi() {
        for (const [indice, panchina] of ris) {
            if (tit.get(indice) == null && panchina.length) tit.set(indice, panchina.shift());
        }
    }

    const nome = (id) => (perId.get(id) || {}).nome || '?';

    // Sposta un giocatore: bersaglio {tipo: 'tit'|'ris', slot} o {tipo: 'fuori'}.
    // Ritorna un messaggio se la mossa non e' ammessa, altrimenti null.
    function sposta(id, bersaglio) {
        if (bersaglio.tipo === 'fuori') {
            togli(id);
            promuovi();
            return null;
        }

        const T = bersaglio.slot;
        const etichetta = slots.get(T).etichetta;
        if (!compatibile(id, T)) return nome(id) + ' non gioca in ' + etichetta + '.';
        const da = dove(id);

        if (bersaglio.tipo === 'tit') {
            if (da && da.posto === 'tit' && da.slot === T) return null;
            const occupante = tit.get(T);
            togli(id);
            tit.set(T, id);
            // Chi occupava il disco prende il posto lasciato libero, se il
            // ruolo glielo consente (scambio); altrimenti va fra i panchinari.
            if (occupante != null && da && compatibile(occupante, da.slot)) {
                if (da.posto === 'tit') tit.set(da.slot, occupante);
                else ris.get(da.slot).splice(da.idx, 0, occupante);
            }
            promuovi();
            return null;
        }

        if (da && da.posto === 'ris' && da.slot === T) return null;
        if (ris.get(T).length >= MAX_RISERVE) return 'La panchina di ' + etichetta + ' è piena (max ' + MAX_RISERVE + ').';
        togli(id);
        ris.get(T).push(id);
        promuovi();
        return null;
    }

    function esegui(id, bersaglio) {
        const errore = sposta(id, bersaglio);
        if (errore) mostraAvviso(errore);
        render();
    }

    let timerAvviso = null;
    function mostraAvviso(testo) {
        avviso.textContent = testo;
        avviso.classList.add('visibile');
        clearTimeout(timerAvviso);
        timerAvviso = setTimeout(() => avviso.classList.remove('visibile'), 2600);
    }

    // --- Trascinamento -----------------------------------------------------
    // Pointer events, cosi' funziona uguale con mouse e dito. Sotto i 6px di
    // movimento e' un tocco e resta al click normale del bottone (che cosi'
    // funziona anche da tastiera); oltre diventa un trascinamento e il click
    // che il browser genera al rilascio viene ignorato.

    let drag = null;
    let appenaTrascinato = false;
    const PRIORITA = { tit: 0, ris: 1, fuori: 2 };

    function bersaglioSotto(x, y) {
        const zone = [];
        for (const el of document.elementsFromPoint(x, y)) {
            const z = el.closest && el.closest('[data-drop]');
            if (z && !zone.includes(z)) zone.push(z);
        }
        if (!zone.length) return null;
        zone.sort((a, b) => PRIORITA[a.dataset.drop] - PRIORITA[b.dataset.drop]);
        const z = zone[0];
        return { el: z, tipo: z.dataset.drop, slot: z.dataset.slot != null ? Number(z.dataset.slot) : null };
    }

    function pulisciEvidenza() {
        if (drag && drag.bersaglio) drag.bersaglio.el.classList.remove('drop-ok', 'drop-no');
    }

    function rendiTrascinabile(nodo, id) {
        nodo.classList.add('trascinabile');
        nodo.addEventListener('pointerdown', function (e) {
            if (e.button > 0) return;
            drag = { id, nodo, x0: e.clientX, y0: e.clientY, mosso: false, fantasma: null, bersaglio: null };
            try { nodo.setPointerCapture(e.pointerId); } catch (_) { /* nodo gia' staccato */ }
        });
        nodo.addEventListener('pointermove', function (e) {
            if (!drag || drag.nodo !== nodo) return;
            if (!drag.mosso) {
                if (Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) < 6) return;
                drag.mosso = true;
                document.body.classList.add('trascinando');
                drag.fantasma = document.createElement('div');
                drag.fantasma.className = 'campetto-fantasma';
                drag.fantasma.textContent = nome(id);
                document.body.appendChild(drag.fantasma);
            }
            drag.fantasma.style.left = e.clientX + 'px';
            drag.fantasma.style.top = e.clientY + 'px';
            pulisciEvidenza();
            drag.bersaglio = bersaglioSotto(e.clientX, e.clientY);
            if (drag.bersaglio) {
                const ok = drag.bersaglio.slot == null || compatibile(id, drag.bersaglio.slot);
                drag.bersaglio.el.classList.add(ok ? 'drop-ok' : 'drop-no');
            }
        });
        const fine = function (applica) {
            if (!drag || drag.nodo !== nodo) return;
            pulisciEvidenza();
            const d = drag;
            drag = null;
            document.body.classList.remove('trascinando');
            if (d.fantasma) d.fantasma.remove();
            if (!d.mosso) return;
            appenaTrascinato = true;
            setTimeout(() => { appenaTrascinato = false; }, 0);
            if (applica && d.bersaglio) esegui(id, { tipo: d.bersaglio.tipo, slot: d.bersaglio.slot });
        };
        nodo.addEventListener('pointerup', () => fine(true));
        nodo.addEventListener('pointercancel', () => fine(false));
    }

    // Riordino verticale di una lista (titolare e riserve nel picker): la
    // riga segue il dito, una linea indica dove verra' inserita e al rilascio
    // si chiama applica(nuovaPosizione). La ✕ dentro la riga resta un bottone
    // normale: da li' non parte il trascinamento.
    function rendiOrdinabile(li, da, righe, applica) {
        li.classList.add('ordinabile');
        let stato = null;
        const pulisci = () => righe.forEach((r) => r.classList.remove('inserisci-sopra', 'inserisci-sotto'));
        li.addEventListener('pointerdown', function (e) {
            if (e.button > 0 || e.target.closest('.campetto-azione')) return;
            stato = { y0: e.clientY, mosso: false, a: da };
            try { li.setPointerCapture(e.pointerId); } catch (_) { /* riga gia' staccata */ }
        });
        li.addEventListener('pointermove', function (e) {
            if (!stato) return;
            const dy = e.clientY - stato.y0;
            if (!stato.mosso && Math.abs(dy) < 4) return;
            stato.mosso = true;
            li.classList.add('in-spostamento');
            li.style.transform = 'translateY(' + dy + 'px)';
            // la nuova posizione: quante righe (esclusa questa) hanno il
            // centro sopra il puntatore
            let a = 0;
            righe.forEach(function (r, i) {
                if (i === da) return;
                const box = r.getBoundingClientRect();
                if (e.clientY > box.top + box.height / 2) a++;
            });
            stato.a = a;
            pulisci();
            if (a !== da) {
                const altre = righe.filter((_, i) => i !== da);
                if (a < altre.length) altre[a].classList.add('inserisci-sopra');
                else altre[altre.length - 1].classList.add('inserisci-sotto');
            }
        });
        const fine = function (conferma) {
            if (!stato) return;
            const s = stato;
            stato = null;
            pulisci();
            li.classList.remove('in-spostamento');
            li.style.transform = '';
            if (conferma && s.mosso && s.a !== da) applica(s.a);
        };
        li.addEventListener('pointerup', () => fine(true));
        li.addEventListener('pointercancel', () => fine(false));
    }

    // --- Picker (tocco su dischetto o riserva) -----------------------------

    function descriviPosizione(id) {
        const d = dove(id);
        if (!d) return '';
        const etichetta = slots.get(d.slot).etichetta;
        return d.posto === 'tit' ? 'titolare ' + etichetta : 'riserva ' + etichetta;
    }

    function voce(testo, classi, azioni) {
        const li = document.createElement('li');
        li.className = 'campetto-candidato ' + (classi || '');
        const principale = document.createElement('span');
        principale.className = 'min-w-0 flex-1 truncate';
        principale.textContent = testo;
        li.appendChild(principale);
        for (const a of azioni) li.appendChild(a);
        return li;
    }

    function azione(testo, titolo, fn) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'campetto-azione';
        b.textContent = testo;
        b.title = titolo;
        b.addEventListener('click', function (e) {
            e.stopPropagation();
            fn();
        });
        return b;
    }

    function apriPicker(indice) {
        const slot = slots.get(indice);
        pickerTitolo.textContent = slot.etichetta + ' · titolare e panchina';
        pickerLista.innerHTML = '';
        const dopo = (fn) => () => { fn(); apriPicker(indice); };

        // Chi c'e' ora: titolare e riserve, ciascuno con la ✕ per mandarlo
        // fra i panchinari. Si possono trascinare per cambiare l'ordine di
        // chiamata: chi finisce in cima diventa titolare.
        const attuali = [tit.get(indice), ...ris.get(indice)].filter((id) => id != null);
        const righe = attuali.map(function (id, i) {
            const etichetta = (i === 0 ? 'Titolare: ' : i + 'ª riserva: ') + nome(id);
            const li = voce(etichetta, 'attuale', [
                azione('✕', 'Togli dal campo', dopo(() => esegui(id, { tipo: 'fuori' }))),
            ]);
            if (attuali.length > 1) {
                const maniglia = document.createElement('span');
                maniglia.className = 'campetto-maniglia';
                maniglia.textContent = '⠿';
                maniglia.setAttribute('aria-hidden', 'true');
                li.insertBefore(maniglia, li.firstChild);
                li.title = 'Trascina per cambiare l\'ordine';
            }
            pickerLista.appendChild(li);
            return li;
        });
        if (attuali.length > 1) {
            righe.forEach((li, da) => rendiOrdinabile(li, da, righe, function (a) {
                const ordine = attuali.slice();
                ordine.splice(a, 0, ordine.splice(da, 1)[0]);
                tit.set(indice, ordine[0]);
                ris.set(indice, ordine.slice(1));
                render();
                apriPicker(indice);
            }));
        }
        if (attuali.length) {
            const sep = document.createElement('li');
            sep.className = 'campetto-picker-separatore';
            pickerLista.appendChild(sep);
        }

        const candidati = rosa.filter((g) => compatibile(g.id, indice) && !attuali.includes(g.id));
        if (!candidati.length) {
            const li = document.createElement('li');
            li.className = 'campetto-candidato italic text-muted';
            li.textContent = 'Nessun altro giocatore in rosa per ' + slot.etichetta + '.';
            pickerLista.appendChild(li);
        }
        for (const g of candidati) {
            const posizione = descriviPosizione(g.id);
            const li = voce(g.nome + (posizione ? ' · ' + posizione : ''), posizione ? 'altrove' : '', [
                azione('+ ris', 'Aggiungi in panchina', dopo(() => esegui(g.id, { tipo: 'ris', slot: indice }))),
            ]);
            const ruolo = document.createElement('span');
            ruolo.className = 'text-xs font-semibold';
            ruolo.style.color = coloreEtichetta(g.ruolo);
            ruolo.textContent = g.ruolo;
            li.insertBefore(ruolo, li.lastChild);
            li.title = 'Metti titolare';
            li.addEventListener('click', function () {
                esegui(g.id, { tipo: 'tit', slot: indice });
                chiudiPicker();
            });
            pickerLista.appendChild(li);
        }

        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    }

    function chiudiPicker() {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }

    // --- Render ------------------------------------------------------------

    function bottone(genitore, classi, testo, indice) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = classi + ' campetto-editabile';
        b.textContent = testo;
        b.addEventListener('click', function () {
            if (!appenaTrascinato) apriPicker(indice);
        });
        genitore.appendChild(b);
        return b;
    }

    function renderSlot(slot) {
        const slotEl = document.createElement('div');
        slotEl.className = 'campetto-slot';
        const indice = slot.indice;

        // Il dischetto: stesso markup della macro disco_campetto in
        // _macros.html, qui bersaglio per il titolare e tasto del picker.
        const titolare = tit.get(indice) != null ? perId.get(tit.get(indice)) : null;
        const lung = slot.etichetta.length;
        const disco = bottone(slotEl, 'campetto-disco' + (titolare ? ' pieno' : '') +
            (lung >= 6 ? ' campetto-disco-xs' : lung >= 4 ? ' campetto-disco-sm' : ''), '', indice);
        disco.dataset.drop = 'tit';
        disco.dataset.slot = indice;
        disco.setAttribute('aria-label', slot.etichetta + ' · ' + (titolare ? titolare.nome : 'scegli il titolare'));
        const sigla = document.createElement('span');
        sigla.className = 'campetto-sigla';
        sigla.textContent = slot.etichetta;
        disco.appendChild(sigla);
        if (!titolare) return slotEl;

        disco.style.setProperty('--ruolo', coloreEtichetta(titolare.ruolo));
        disco.title = titolare.nome + ' (' + titolare.ruolo + ')';
        if (titolare.campioncino) {
            disco.classList.add('con-foto');
            const foto = document.createElement('img');
            foto.alt = '';
            foto.draggable = false;
            foto.onerror = function () { disco.classList.remove('con-foto'); foto.remove(); };
            foto.src = titolare.campioncino;
            disco.insertBefore(foto, sigla);
        }
        rendiTrascinabile(disco, titolare.id);
        rendiTrascinabile(bottone(slotEl, 'campetto-nome', titolare.nome, indice), titolare.id);

        // La panchina: tutta l'area sotto il nome e' bersaglio per le
        // riserve; il posto libero invita ad aggiungerne una.
        const panca = document.createElement('div');
        panca.className = 'campetto-panca';
        panca.dataset.drop = 'ris';
        panca.dataset.slot = indice;
        for (const id of ris.get(indice)) {
            rendiTrascinabile(bottone(panca, 'campetto-riserva', '(' + nome(id) + ')', indice), id);
        }
        if (ris.get(indice).length < MAX_RISERVE) {
            bottone(panca, 'campetto-riserva campetto-aggiungi', '+ riserva', indice);
        }
        slotEl.appendChild(panca);
        return slotEl;
    }

    function renderPanchinari() {
        panchinariEl.innerHTML = '';
        const titolo = document.createElement('span');
        titolo.className = 'campetto-panchinari-titolo';
        titolo.textContent = 'Panchinari';
        panchinariEl.appendChild(titolo);

        const fuori = rosa.filter((g) => !dove(g.id));
        if (!fuori.length) {
            const vuoto = document.createElement('span');
            vuoto.className = 'campetto-panchinari-vuoto';
            vuoto.textContent = 'tutta la rosa è schierata - trascina qui per togliere un giocatore';
            panchinariEl.appendChild(vuoto);
        }
        for (const g of fuori) {
            const ok = schierabile(g.id);
            const chip = document.createElement('span');
            chip.className = 'campetto-panchinaro' + (ok ? ' schierabile' : '');
            chip.title = g.nome + ' (' + g.ruolo + ')' + (ok ? ' - trascinalo su un dischetto o sotto' : ' - nessuno slot per il suo ruolo in questo modulo');
            const ruolo = document.createElement('i');
            ruolo.textContent = g.ruolo;
            chip.appendChild(ruolo);
            chip.appendChild(document.createTextNode(' ' + g.nome));
            if (ok) rendiTrascinabile(chip, g.id);
            panchinariEl.appendChild(chip);
        }
    }

    function renderInput() {
        inputNascosti.innerHTML = '';
        const aggiungi = (nomeCampo, valore) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = nomeCampo;
            input.value = valore == null ? '' : valore;
            inputNascosti.appendChild(input);
        };
        for (const indice of slots.keys()) {
            aggiungi('slot_' + indice + '_tit', tit.get(indice));
            // un input per riserva, stesso nome: il server li legge con getlist
            for (const id of ris.get(indice)) aggiungi('slot_' + indice + '_ris', id);
        }
    }

    function render() {
        campo.innerHTML = '';
        for (const riga of linee) {
            const rigaEl = document.createElement('div');
            rigaEl.className = 'campetto-riga';
            for (const slot of riga) rigaEl.appendChild(renderSlot(slot));
            campo.appendChild(rigaEl);
        }
        renderPanchinari();
        renderInput();
    }

    // "Svuota": tutti fra i panchinari, modulo invariato. Come ogni altra
    // modifica resta da confermare con "Salva formazione".
    const btnSvuota = document.getElementById('btnSvuota');
    if (btnSvuota) {
        btnSvuota.addEventListener('click', function () {
            for (const indice of slots.keys()) {
                tit.set(indice, null);
                ris.set(indice, []);
            }
            render();
        });
    }

    btnChiudi.addEventListener('click', chiudiPicker);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) chiudiPicker(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') chiudiPicker(); });

    promuovi();
    render();
});
