(() => {
    'use strict';
    const root = document.querySelector('[data-resposta-pronta]');
    if (!root) return;
    const select = root.querySelector('select');
    const form = root.closest('form');
    const textarea = form.querySelector('textarea[name=texto]');
    const submit = form.querySelector('[type=submit]');
    const feedback = root.querySelector('[role=status]');
    select.addEventListener('change', async () => {
        const option = select.selectedOptions[0];
        if (!option?.dataset.url) return;
        const disabled = submit.disabled;
        select.disabled = true;
        submit.disabled = true;
        feedback.textContent = 'Carregando resposta…';
        try {
            const response = await fetch(option.dataset.url, {credentials: 'same-origin', mode: 'same-origin', redirect: 'error'});
            if (!response.ok) throw new Error('unavailable');
            const data = await response.json();
            if (typeof data.texto !== 'string' || typeof data.nome !== 'string') throw new Error('invalid');
            const draft = textarea.value;
            const separator = draft.endsWith('\n\n') ? '' : draft.endsWith('\n') ? '\n' : '\n\n';
            textarea.value = draft.trim() ? draft + separator + data.texto : data.texto;
            textarea.dispatchEvent(new Event('input', {bubbles: true}));
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
            feedback.textContent = `“${data.nome}” inserida. Revise o texto antes de enviar.`;
        } catch (_) {
            feedback.textContent = 'Não foi possível carregar o modelo. O rascunho foi mantido. Selecione novamente para tentar outra vez.';
        } finally {
            select.value = '';
            select.disabled = false;
            submit.disabled = disabled;
        }
    });
})();
