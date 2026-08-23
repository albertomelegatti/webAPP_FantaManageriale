document.addEventListener('DOMContentLoaded', function () {
    let activeTip = null;
    let pressTimer = null;

    function positionTip(tip, el) {
        const rect = el.getBoundingClientRect();
        const left = Math.min(
            Math.max(4, rect.left + rect.width / 2 - tip.offsetWidth / 2),
            window.innerWidth - tip.offsetWidth - 4
        );
        const top = Math.max(4, rect.top - tip.offsetHeight - 8);
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }

    function showTip(el) {
        hideTip();
        const text = el.getAttribute('data-tip');
        if (!text) return;
        const tip = document.createElement('div');
        tip.className = 'fixed z-50 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-sm font-semibold text-text shadow-lg';
        tip.textContent = text;
        document.body.appendChild(tip);
        positionTip(tip, el);
        activeTip = tip;
    }

    function hideTip() {
        if (activeTip) {
            activeTip.remove();
            activeTip = null;
        }
    }

    document.addEventListener('touchstart', function (e) {
        const el = e.target.closest('[data-tip]');
        if (!el) return;
        pressTimer = setTimeout(() => showTip(el), 400);
    }, { passive: true });

    document.addEventListener('touchend', function () {
        clearTimeout(pressTimer);
        setTimeout(hideTip, 3000);
    });

    document.addEventListener('touchmove', function () {
        clearTimeout(pressTimer);
        hideTip();
    });

    document.querySelectorAll('[data-tip]').forEach(function (el) {
        el.addEventListener('mouseenter', () => showTip(el));
        el.addEventListener('mouseleave', hideTip);
    });
});
