(() => {
    'use strict';
    const editor = document.getElementById('editor-foto');
    if (!editor) return;
    const canvas = document.getElementById('previa-foto');
    const ctx = canvas.getContext('2d');
    const arquivo = document.getElementById('id_foto');
    const remover = document.getElementById('id_remover_foto');
    const estado = document.getElementById('estado-previa');
    const x = document.getElementById('id_foto_x');
    const y = document.getElementById('id_foto_y');
    const zoom = document.getElementById('id_foto_zoom');
    let imagem = null, urlLocal = null, geracao = 0, arraste = null;
    const limitar = valor => Math.max(0, Math.min(100, Math.round(valor)));
    function geometria() {
        const lado = Math.min(imagem.naturalWidth, imagem.naturalHeight) * 100 / Number(zoom.value);
        return {lado, sobraX: imagem.naturalWidth - lado, sobraY: imagem.naturalHeight - lado};
    }
    function desenhar() {
        ctx.clearRect(0, 0, 256, 256);
        ctx.fillStyle = '#dbe7fd'; ctx.fillRect(0, 0, 256, 256);
        if (!imagem || remover.checked) return;
        const g = geometria();
        ctx.drawImage(imagem, g.sobraX * Number(x.value) / 100, g.sobraY * Number(y.value) / 100,
                      g.lado, g.lado, 0, 0, 256, 256);
    }
    function centralizar() { x.value = 50; y.value = 50; zoom.value = 100; desenhar(); }
    function carregar(url) {
        const atual = ++geracao;
        imagem = null; desenhar();
        if (!url) { estado.textContent = 'Selecione uma foto para visualizar o enquadramento.'; return; }
        const nova = new Image();
        nova.onload = () => {
            if (atual !== geracao) return;
            imagem = nova;
            estado.textContent = 'Prévia do enquadramento. Salve o perfil para aplicar.';
            desenhar();
        };
        nova.onerror = () => {
            if (atual !== geracao) return;
            imagem = null; estado.textContent = 'Não foi possível exibir a prévia. Selecione outra foto.'; desenhar();
        };
        nova.src = url;
    }
    arquivo.addEventListener('change', () => {
        if (urlLocal) { URL.revokeObjectURL(urlLocal); urlLocal = null; }
        if (arquivo.files.length) {
            if (arquivo.files[0].size > 2 * 1024 * 1024) {
                carregar(null); estado.textContent = 'A foto deve ter no máximo 2 MB.'; return;
            }
            remover.checked = false;
            centralizar();
            urlLocal = URL.createObjectURL(arquivo.files[0]); carregar(urlLocal);
        } else carregar(editor.dataset.source || null);
    });
    [x, y, zoom].forEach(campo => campo.addEventListener('input', desenhar));
    remover.addEventListener('change', () => {
        estado.textContent = remover.checked ? 'A foto será removida ao salvar o perfil.' : 'Salve o perfil para aplicar o enquadramento.';
        desenhar();
    });
    document.getElementById('centralizar-foto').addEventListener('click', centralizar);
    canvas.addEventListener('pointerdown', evento => {
        if (!imagem || remover.checked || (evento.pointerType === 'mouse' && evento.button !== 0)) return;
        arraste = {id: evento.pointerId, inicioX: evento.clientX, inicioY: evento.clientY, x: Number(x.value), y: Number(y.value)};
        canvas.setPointerCapture(evento.pointerId);
    });
    canvas.addEventListener('pointermove', evento => {
        if (!arraste || evento.pointerId !== arraste.id || !imagem) return;
        const g = geometria();
        const escala = g.lado / canvas.getBoundingClientRect().width;
        x.value = g.sobraX > 0 ? limitar(arraste.x - (evento.clientX - arraste.inicioX) * escala * 100 / g.sobraX) : 50;
        y.value = g.sobraY > 0 ? limitar(arraste.y - (evento.clientY - arraste.inicioY) * escala * 100 / g.sobraY) : 50;
        desenhar();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(tipo => canvas.addEventListener(tipo, () => { arraste = null; }));
    window.addEventListener('pagehide', () => { if (urlLocal) URL.revokeObjectURL(urlLocal); });
    carregar(editor.dataset.source || null);
})();
