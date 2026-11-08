(() => {
    'use strict';
    const root = document.getElementById('colunas-chamados');
    if (!root) return;
    const table = root.querySelector('.ticket-table');
    const controls = root.querySelector('.colunas-controles');
    const status = controls.querySelector('.colunas-estado');
    const reset = controls.querySelector('.colunas-restaurar');
    const retry = controls.querySelector('.colunas-repetir');
    const token = controls.querySelector('[name=csrfmiddlewaretoken]');
    const row = table.tHead.rows[0];
    const headers = new Map(Array.from(row.cells, cell => [cell.dataset.coluna, cell]));
    const labels = new Map(Array.from(headers, ([key, cell]) => [key, cell.textContent.trim()]));
    const defaults = JSON.parse(document.getElementById('colunas-padrao').textContent);
    const initial = JSON.parse(document.getElementById('colunas-salvas').textContent);
    const valid = value => Array.isArray(value) && value.length === headers.size &&
        new Set(value).size === headers.size && value.every(key => headers.has(key));
    if (!valid(defaults) || !valid(initial) || !token) return;
    const equal = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);
    let order = initial.slice();
    let desired = initial.slice();
    let saved = initial.slice();
    let saving = false;
    let failed = false;
    let session = null;
    let animation = 0;

    function buttons() {
        reset.disabled = equal(order, defaults) && !failed;
        retry.hidden = !failed || saving;
    }
    function apply(next) {
        order = next.slice();
        order.forEach(key => row.appendChild(headers.get(key)));
        for (const bodyRow of table.tBodies[0].rows) {
            const cells = new Map(Array.from(bodyRow.cells, cell => [cell.dataset.coluna, cell]));
            if (!order.every(key => cells.has(key))) continue; // Linha vazia com colspan.
            order.forEach(key => bodyRow.appendChild(cells.get(key)));
        }
        buttons();
    }
    async function persist() {
        if (saving) return;
        saving = true;
        failed = false;
        status.textContent = 'Salvando ordem…';
        buttons();
        try {
            // Uma requisição por vez; a última ordem sempre segue a anterior.
            while (!equal(saved, desired)) {
                const sent = desired.slice();
                const response = await fetch(root.dataset.salvarUrl, {
                    method: 'POST', credentials: 'same-origin', mode: 'same-origin', redirect: 'error',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': token.value},
                    body: JSON.stringify({ordem: sent})
                });
                if (!response.ok) throw new Error('save');
                const data = await response.json();
                if (!valid(data.ordem) || !equal(data.ordem, sent)) throw new Error('save');
                saved = sent;
            }
            if (!session?.dragging) status.textContent = 'Ordem salva.';
        } catch (_) {
            failed = true;
            status.textContent = 'Não foi possível salvar a ordem.';
        } finally {
            saving = false;
            buttons();
        }
    }
    function commit(next) {
        desired = next.slice();
        failed = false;
        if (equal(saved, desired) && !saving) {
            status.textContent = 'Ordem salva.';
            buttons();
        } else {
            void persist();
        }
    }
    function place(x) {
        if (!session?.dragging) return;
        let target = null;
        for (const key of order) {
            const rect = headers.get(key).getBoundingClientRect();
            if (x < rect.right) { target = key; break; }
        }
        if (target === null) target = order[order.length - 1];
        if (target === session.key) return;
        const rect = headers.get(target).getBoundingClientRect();
        const next = order.filter(key => key !== session.key);
        const index = next.indexOf(target) + (x >= rect.left + rect.width / 2 ? 1 : 0);
        next.splice(index, 0, session.key);
        if (!equal(order, next)) {
            apply(next);
            try { session.header.setPointerCapture(session.id); } catch (_) { /* Ponteiro já encerrado. */ }
        }
    }
    function scroll() {
        if (!session?.dragging) return;
        const viewport = table.parentElement;
        const rect = viewport.getBoundingClientRect();
        const direction = session.x < rect.left + 32 ? -1 : session.x > rect.right - 32 ? 1 : 0;
        if (direction) {
            viewport.scrollLeft += direction * 8;
            place(session.x);
        }
        animation = requestAnimationFrame(scroll);
    }
    function start() {
        if (!session || session.dragging) return;
        session.dragging = true;
        session.header.classList.add('coluna-em-movimento');
        root.classList.add('colunas-em-movimento');
        try { session.header.setPointerCapture(session.id); } catch (_) { /* Mantém eventos no documento. */ }
        status.textContent = 'Arraste até a posição desejada. Esc cancela.';
        animation = requestAnimationFrame(scroll);
    }
    function finish(cancel = false) {
        if (!session) return;
        const previous = session;
        session = null;
        clearTimeout(previous.timer);
        cancelAnimationFrame(animation);
        previous.header.classList.remove('coluna-em-movimento');
        root.classList.remove('colunas-em-movimento');
        try { previous.header.releasePointerCapture(previous.id); } catch (_) { /* Já liberado. */ }
        if (!previous.dragging) return;
        if (cancel) {
            apply(previous.original);
            status.textContent = 'Movimento cancelado.';
        } else if (!equal(order, previous.original)) {
            commit(order);
        } else {
            status.textContent = failed ? 'Não foi possível salvar a ordem.' : saving ? 'Salvando ordem…' : '';
        }
    }
    for (const [key, header] of headers) {
        header.tabIndex = 0;
        header.title = 'Arraste para reorganizar. No teclado, use Alt + setas para os lados.';
        header.setAttribute('aria-keyshortcuts', 'Alt+ArrowLeft Alt+ArrowRight');
        const grip = document.createElement('span');
        grip.className = 'bi bi-grip-vertical coluna-grip';
        grip.setAttribute('aria-hidden', 'true');
        header.appendChild(grip);
        header.addEventListener('pointerdown', event => {
            if (session || event.button !== 0 || event.isPrimary === false) return;
            header.focus({preventScroll: true});
            session = {key, header, id: event.pointerId, x: event.clientX, y: event.clientY,
                original: order.slice(), dragging: false, touch: event.pointerType === 'touch'};
            if (session.touch) session.timer = setTimeout(start, 400);
        });
        header.addEventListener('contextmenu', event => { if (session) event.preventDefault(); });
        header.addEventListener('keydown', event => {
            if (!event.altKey || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            if (session) return;
            const index = order.indexOf(key);
            const destination = index + (event.key === 'ArrowLeft' ? -1 : 1);
            if (destination < 0 || destination >= order.length) return;
            const next = order.slice();
            [next[index], next[destination]] = [next[destination], next[index]];
            apply(next);
            header.focus({preventScroll: true});
            commit(next);
        });
    }
    document.addEventListener('pointermove', event => {
        if (!session || session.id !== event.pointerId) return;
        const distance = Math.hypot(event.clientX - session.x, event.clientY - session.y);
        if (!session.dragging) {
            if (session.touch && distance > 8) { finish(true); return; }
            if (!session.touch && distance > 5) start();
        }
        if (session?.dragging) {
            event.preventDefault();
            session.x = event.clientX;
            place(event.clientX);
        }
    }, {passive: false});
    document.addEventListener('pointerup', event => { if (session?.id === event.pointerId) finish(); });
    document.addEventListener('pointercancel', event => { if (session?.id === event.pointerId) finish(true); });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && session) { event.preventDefault(); finish(true); }
    });
    window.addEventListener('blur', () => finish(true));
    document.addEventListener('visibilitychange', () => { if (document.hidden) finish(true); });
    reset.addEventListener('click', () => { finish(true); apply(defaults); commit(defaults); });
    retry.addEventListener('click', () => { desired = order.slice(); void persist(); });
    apply(initial);
    controls.hidden = false;
})();
