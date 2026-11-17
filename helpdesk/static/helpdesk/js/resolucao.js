(() => {
    'use strict';
    const modal = document.querySelector('[data-resolucao-invalida]');
    if (!modal) return;
    const primeiroErro = modal.querySelector('[aria-invalid="true"]');
    if (window.bootstrap?.Modal) {
        modal.addEventListener('shown.bs.modal', () => primeiroErro?.focus(), {once: true});
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    } else {
        // Mantém o formulário de correção acessível se o recurso externo falhar.
        modal.classList.remove('modal', 'fade');
        modal.removeAttribute('aria-hidden');
        modal.querySelectorAll('[data-bs-dismiss]').forEach(button => { button.hidden = true; });
        primeiroErro?.focus();
    }
})();
