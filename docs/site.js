/* Shared behaviour for every HO.ME page: hospital reference data, the external-link
   (feedback) modal, the hospital contact modal and the header search box. */
(function () {
    const FEEDBACK_URL = 'https://forms.cloud.microsoft/e/dCrxb4BRCq';

    const sectorLabels = {
        NC: 'North Central',
        NE: 'North East',
        NW: 'North West',
        SE: 'South East',
        SW: 'South West',
        TVW: 'Thames Valley and Wessex',
        KSS: 'Kent, Surrey and Sussex',
        EoE: 'East of England',
        Border: 'Border',
    };
    const levelNames = { 1: 'Special Care', 2: 'High Dependency', 3: 'NICU' };
    const levelShortNames = { 1: 'SCBU', 2: 'LNU', 3: 'NICU' };
    const hospitalDisplayNames = {
        'University Lewisham': 'Lewisham Hospital',
    };
    const hospitalPhones = {
        'Barnet Hospital': '020 8216 4600',
        'Chelsea & Westminster': '020 3315 8000',
        'Croydon University': '020 8401 3000',
        'Darent Valley': '01322 428 100',
        'East Surrey': '01737 768 511',
        'Epsom Hospital': '01372 735 735',
        "Evelina (St Thomas')": '020 7188 7188',
        'Hillingdon Hospital': '01895 238 282',
        'Homerton University': '020 8510 5555',
        'Kings College Hospital': '020 3299 9000',
        'Kingston Hospital': '020 8546 7711',
        'Newham General': '020 7476 4000',
        'North Middlesex': '020 8887 2000',
        'Northwick Park': '020 8864 3232',
        'Princess Royal (PRUH)': '01689 863 000',
        'Queen Elizabeth Woolwich': '020 8836 6000',
        "Queen Charlottes'": '020 3313 1111',
        'Queens Hospital': '0330 400 4333',
        'Royal Free Hospital': '020 7794 0500',
        'St Heliers Hospital': '020 8296 2000',
        'St Marys Hospital': '020 3312 6666',
        'St Peters Hospital': '01932 872000',
        'St. Georges Hospital': '020 8672 1255',
        'The Royal London': '020 7377 7000',
        'UCH (University College)': '020 3456 7890',
        'University Lewisham': '020 8333 3000',
        'Watford General': '01923 244 366',
        'West Middlesex': '020 8560 2121',
        'Whipps Cross': '020 8539 5522',
        'Whittington Hospital': '020 7272 3070',
        'Wexham Park': '0300 614 5000',
    };

    const ICON_CLOSE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    const ICON_PHONE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>';
    const ICON_EXTERNAL = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[ch]));
    }

    function displayHospitalName(name) {
        return hospitalDisplayNames[name] || name;
    }

    function normaliseNetwork(sector) {
        if (sector === 'South East') return 'SE';
        if (sector === 'South West') return 'SW';
        return sector || '';
    }

    function networkLabel(sector) {
        const key = normaliseNetwork(sector);
        return sectorLabels[key] || key || 'Network not listed';
    }

    function levelLabel(level) {
        return 'Level ' + level + ' — ' + (levelNames[level] || '');
    }

    function phoneHref(phone) {
        return 'tel:' + String(phone).replace(/[^\d+]/g, '');
    }

    /* ---------- Modal plumbing ---------- */
    let activeModal = null;

    function closeModal() {
        if (!activeModal) return;
        const { backdrop, opener } = activeModal;
        backdrop.remove();
        activeModal = null;
        if (opener && document.contains(opener)) opener.focus();
    }

    function openModal(innerHtml, labelledBy, focusSelector) {
        closeModal();
        const backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop';
        backdrop.innerHTML =
            '<div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="' + labelledBy + '">' +
            '<button type="button" class="modal-close" aria-label="Close dialog">' + ICON_CLOSE + '</button>' +
            innerHtml +
            '</div>';
        backdrop.addEventListener('click', e => { if (e.target === backdrop) closeModal(); });
        backdrop.querySelector('.modal-close').addEventListener('click', closeModal);
        activeModal = { backdrop, opener: document.activeElement };
        document.body.appendChild(backdrop);
        const target = backdrop.querySelector(focusSelector);
        if (target) target.focus();
    }

    document.addEventListener('keydown', e => {
        if (!activeModal) return;
        if (e.key === 'Escape') { closeModal(); return; }
        if (e.key !== 'Tab') return;
        const focusable = activeModal.backdrop.querySelectorAll('a[href], button');
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });

    function openFeedback(url) {
        openModal(
            '<h2 id="home-feedback-title">You’re leaving HO.ME</h2>' +
            '<p>The feedback form opens in Microsoft Forms, an external site.</p>' +
            '<a class="modal-action" id="home-feedback-continue" href="' + escapeHtml(url || FEEDBACK_URL) + '" target="_blank" rel="noopener">Continue ' + ICON_EXTERNAL + '</a>',
            'home-feedback-title',
            '#home-feedback-continue'
        );
        activeModal.backdrop.querySelector('#home-feedback-continue').addEventListener('click', () => {
            setTimeout(closeModal, 0);
        });
    }

    function openContact(hospital) {
        const name = displayHospitalName(hospital.name);
        const phone = hospital.phone || hospitalPhones[hospital.name] || '';
        const level = Number(hospital.level);
        const badges =
            (level ? '<span class="level-badge lvl-' + level + '">' + escapeHtml(levelLabel(level)) + '</span>' : '') +
            '<span class="network-pill">' + escapeHtml(networkLabel(hospital.sector)) + '</span>';
        openModal(
            '<h2 id="home-contact-title">' + escapeHtml(name) + '</h2>' +
            '<div class="modal-badges">' + badges + '</div>' +
            '<div class="modal-details"><div class="modal-detail-row"><span>Contact Number</span><span>' +
            escapeHtml(phone || 'Not listed') + '</span></div></div>' +
            (phone ? '<a class="modal-action" id="home-contact-call" href="' + phoneHref(phone) + '">' + ICON_PHONE + ' Call</a>' : ''),
            'home-contact-title',
            phone ? '#home-contact-call' : '.modal-close'
        );
    }

    /* Make a hospital card/row clickable and keyboard-operable. */
    function bindContactTrigger(el, getHospital) {
        el.classList.add('contact-trigger');
        el.setAttribute('tabindex', '0');
        el.setAttribute('aria-haspopup', 'dialog');
        el.addEventListener('click', () => openContact(getHospital()));
        el.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openContact(getHospital()); }
        });
    }

    /* ---------- Feedback links ---------- */
    document.addEventListener('click', e => {
        const link = e.target.closest('[data-feedback]');
        if (!link || e.defaultPrevented) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey) return;
        e.preventDefault();
        openFeedback(link.getAttribute('href'));
    });

    /* ---------- Header search (pages other than the lookup page hand off to it) ---------- */
    function initHeaderSearch() {
        if (window.HOME_LOOKUP_PAGE) return;
        const form = document.getElementById('headerSearchForm');
        const input = document.getElementById('headerPostcodeInput');
        const clear = document.getElementById('headerClearBtn');
        if (!form || !input || !clear) return;
        const sync = () => { clear.style.display = input.value ? 'flex' : 'none'; };
        input.addEventListener('input', sync);
        clear.addEventListener('click', () => { input.value = ''; sync(); input.focus(); });
        form.addEventListener('submit', e => {
            e.preventDefault();
            const value = input.value.trim();
            if (!value) { input.focus(); return; }
            window.location.href = 'index.html?postcode=' + encodeURIComponent(value.replace(/\s/g, '').toUpperCase());
        });
        sync();
    }
    initHeaderSearch();

    window.HOME = {
        FEEDBACK_URL,
        sectorLabels, levelNames, levelShortNames, hospitalPhones,
        escapeHtml, displayHospitalName, normaliseNetwork, networkLabel, levelLabel, phoneHref,
        openContact, openFeedback, closeModal, bindContactTrigger,
    };
})();
