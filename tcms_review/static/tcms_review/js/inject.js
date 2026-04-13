// Injects the "Send for review" button into TestCase / TestPlan detail pages
// without modifying Kiwi core templates. Loaded by including this file via
// a small loader hook (see README → "Loader" section).
//
// IMPORTANT: this IIFE must close with `})($)` — Kiwi ships two jQuery
// instances and only `$` has the Bootstrap plugins (`show.bs.modal` etc.).
(function ($) {
    'use strict';

    function detectPageContext() {
        // Kiwi sets `body[id]` per page; testcase detail uses "testcases-get",
        // testplan detail uses "testplans-get".
        const pageId = document.body && document.body.id;
        if (pageId === 'testcases-get') {
            const pk = document.body.dataset.testcasePk;
            return { kind: 'testcase', pk };
        }
        if (pageId === 'testplans-get') {
            const pk = document.body.dataset.testplanPk;
            return { kind: 'testplan', pk };
        }
        return null;
    }

    function buildButton(ctx) {
        const $btn = $('<button type="button" class="btn btn-default"/>')
            .text('Send for review')
            .attr('data-review-context', ctx.kind)
            .attr('data-review-pk', ctx.pk);
        $btn.on('click', function () {
            // Slice 1: redirect to the New view with the case prefilled.
            // Slice 2 will replace this with a Bootstrap modal.
            const url = '/reviews/new/?' + ctx.kind + '=' + encodeURIComponent(ctx.pk);
            window.location.href = url;
        });
        return $btn;
    }

    function wireConfirmForms() {
        // Any <form data-confirm="..."> on a plugin page gets a native
        // confirm dialog before submission. Bootbox would be nicer but
        // pulling it in cross-page is fragile in a plugin context.
        $('form[data-confirm]').on('submit', function (event) {
            const message = $(this).data('confirm');
            // eslint-disable-next-line no-alert
            if (!window.confirm(message)) {
                event.preventDefault();
                return false;
            }
            return true;
        });
    }

    $(function () {
        wireConfirmForms();

        const ctx = detectPageContext();
        if (!ctx || !ctx.pk) {
            return;
        }
        // Inject into the page's primary actions container.
        const $actions = $('.page-header .actions, .card-pf-heading .actions').first();
        if ($actions.length) {
            $actions.append(buildButton(ctx));
        }
    });
})($);
