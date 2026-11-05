/* Detalhes flutuantes compartilhados pela coleção e pelo perfil. */
(() => {
    'use strict';
    let atual = null;
    let fixado = false;
    let fechamento = null;
    let quadro = null;
    let ignorarHover = false;
    let ponteiro = null;
    let suspenderFoco = false;
    const margem = 12;
    const cancelarFechamento = () => { clearTimeout(fechamento); fechamento = null; };

    function posicionar() {
        if (!atual) return;
        const resumo = atual.querySelector('summary');
        const painel = atual.querySelector('.medalha-popover');
        const rolagem = painel.scrollTop;
        const area = window.visualViewport;
        const esquerda = area ? area.offsetLeft : 0;
        const topo = area ? area.offsetTop : 0;
        const largura = area ? area.width : window.innerWidth;
        const altura = area ? area.height : window.innerHeight;
        painel.style.maxWidth = `${Math.max(1, largura - margem * 2)}px`;
        painel.style.maxHeight = `${Math.max(1, altura - margem * 2)}px`;
        painel.style.transform = 'none';
        const ancora = resumo.getBoundingClientRect();
        if (ancora.bottom < topo || ancora.top > topo + altura) { fechar(); return; }
        let tamanho = painel.getBoundingClientRect();
        const abaixo = Math.max(0, topo + altura - margem - ancora.bottom - 8);
        const acima = Math.max(0, ancora.top - topo - margem - 8);
        const usarAcima = tamanho.height > abaixo && acima > abaixo;
        // Limita o painel ao espaço livre, para não cobrir a própria medalha.
        const livre = usarAcima ? acima : abaixo;
        painel.style.maxHeight = `${Math.max(1, livre)}px`;
        tamanho = painel.getBoundingClientRect();
        let x = ancora.left;
        let y = usarAcima ? ancora.top - tamanho.height - 8 : ancora.bottom + 8;
        x = Math.max(esquerda + margem, Math.min(x, esquerda + largura - tamanho.width - margem));
        y = Math.max(topo + margem, Math.min(y, topo + altura - tamanho.height - margem));
        painel.style.left = `${Math.round(x)}px`;
        painel.style.top = `${Math.round(y)}px`;
        painel.scrollTop = rolagem;
    }

    function fechar() {
        cancelarFechamento();
        if (!atual) return;
        atual.querySelector('.medalha-popover').hidden = true;
        const resumo = atual.querySelector('summary');
        resumo.setAttribute('aria-expanded', 'false');
        resumo.removeAttribute('aria-describedby');
        atual.open = false;
        atual = null;
        fixado = false;
    }

    function abrir(medalha, fixar = false) {
        cancelarFechamento();
        if (atual !== medalha) {
            fechar();
            atual = medalha;
            fixado = false;
        }
        fixado = fixado || fixar;
        const resumo = medalha.querySelector('summary');
        const painel = medalha.querySelector('.medalha-popover');
        medalha.open = true;
        painel.hidden = false;
        resumo.setAttribute('aria-expanded', 'true');
        resumo.setAttribute('aria-describedby', painel.id);
        posicionar();
    }

    function agendarFechamento(medalha) {
        cancelarFechamento();
        fechamento = setTimeout(() => {
            if (atual === medalha && !fixado && !medalha.matches(':hover') && !medalha.contains(document.activeElement)) fechar();
        }, 180);
    }

    document.querySelectorAll('[data-medalha-flutuante]').forEach(medalha => {
        const resumo = medalha.querySelector('summary');
        const painel = medalha.querySelector('.medalha-popover');
        painel.hidden = true;
        resumo.setAttribute('aria-expanded', 'false');
        medalha.addEventListener('pointerenter', evento => {
            if (!ignorarHover && (evento.pointerType === 'mouse' || evento.pointerType === 'pen')) abrir(medalha);
        });
        medalha.addEventListener('pointerleave', () => agendarFechamento(medalha));
        painel.addEventListener('pointerenter', cancelarFechamento);
        painel.addEventListener('pointerleave', () => agendarFechamento(medalha));
        resumo.addEventListener('focus', () => { if (!suspenderFoco) abrir(medalha); });
        resumo.addEventListener('blur', () => agendarFechamento(medalha));
        resumo.addEventListener('click', evento => {
            evento.preventDefault();
            if (atual === medalha && fixado) { ignorarHover = true; fechar(); }
            else abrir(medalha, true);
        });
    });
    document.addEventListener('pointermove', evento => {
        const mudou = !ponteiro || Math.abs(evento.clientX - ponteiro.x) > 1 || Math.abs(evento.clientY - ponteiro.y) > 1;
        ponteiro = {x: evento.clientX, y: evento.clientY};
        if (ignorarHover && mudou && (evento.pointerType === 'mouse' || evento.pointerType === 'pen')) {
            ignorarHover = false;
            const medalha = evento.target.closest('[data-medalha-flutuante]');
            if (medalha) abrir(medalha);
        }
    }, {passive: true});
    document.addEventListener('pointerdown', evento => {
        if (atual && !atual.contains(evento.target)) fechar();
    });
    document.addEventListener('focusin', evento => {
        if (atual && !atual.contains(evento.target)) fechar();
    });
    document.addEventListener('keydown', evento => {
        if (evento.key === 'Escape' && atual) {
            const resumo = atual.querySelector('summary');
            const devolverFoco = atual.querySelector('.medalha-popover').contains(document.activeElement);
            ignorarHover = true;
            fechar();
            if (devolverFoco) {
                suspenderFoco = true;
                resumo.focus({preventScroll: true});
                suspenderFoco = false;
            }
            evento.preventDefault();
        }
    });
    function reposicionar(evento) {
        if (evento && evento.target instanceof Element && evento.target.closest('.medalha-popover')) return;
        if (!atual || quadro !== null) return;
        quadro = requestAnimationFrame(() => { quadro = null; posicionar(); });
    }
    window.addEventListener('scroll', reposicionar, {capture: true, passive: true});
    window.addEventListener('resize', reposicionar, {passive: true});
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', reposicionar, {passive: true});
        window.visualViewport.addEventListener('scroll', reposicionar, {passive: true});
    }
})();
