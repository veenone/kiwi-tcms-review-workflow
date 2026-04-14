// kiwitcms-review — client-side integration bundle.
//
// Grafts the plugin's UI elements into Kiwi core pages via DOM mutation.
// No Kiwi core template is ever modified.
//
// IMPORTANT: the IIFE MUST close with )($) — Kiwi ships two jQuery
// instances and only `$` has the Bootstrap plugins (show.bs.modal etc.).
(function ($) {
    'use strict';

    var PLUGIN_ROOT = '/reviews';

    // ─── Page detection ────────────────────────────────────────────────

    function detectPageContext() {
        var pageId = (document.body && document.body.id) || '';
        if (pageId === 'page-testcases-get' || pageId === 'testcases-get') {
            return { kind: 'testcase', pk: pkFromUrl(/\/case\/(\d+)/) };
        }
        if (pageId === 'page-testplans-get' || pageId === 'testplans-get') {
            return { kind: 'testplan', pk: pkFromUrl(/\/plan\/(\d+)/) };
        }
        if (pageId === 'page-dashboard' || pageId === 'core-views-index') {
            return { kind: 'dashboard' };
        }
        return null;
    }

    function pkFromUrl(re) {
        var m = (window.location.pathname || '').match(re);
        return m ? m[1] : null;
    }

    // ─── Confirm-dialog hook ──────────────────────────────────────────

    function wireConfirmForms() {
        $('form[data-confirm]').on('submit', function (event) {
            var message = $(this).data('confirm');
            // eslint-disable-next-line no-alert
            if (!window.confirm(message)) {
                event.preventDefault();
                return false;
            }
            return true;
        });
    }

    // ─── Send-for-review modal ────────────────────────────────────────

    function getCsrfToken() {
        var match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }

    function buildModal(ctx) {
        var html = ''
            + '<div class="modal fade" id="review-send-modal" tabindex="-1" role="dialog" aria-labelledby="review-send-modal-title">'
            + '  <div class="modal-dialog" role="document">'
            + '    <div class="modal-content">'
            + '      <form method="post" action="' + PLUGIN_ROOT + '/new/?' + ctx.kind + '=' + ctx.pk + '">'
            + '        <div class="modal-header">'
            + '          <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>'
            + '          <h4 class="modal-title" id="review-send-modal-title">Send for review</h4>'
            + '        </div>'
            + '        <div class="modal-body">'
            + '          <input type="hidden" name="csrfmiddlewaretoken" value="' + getCsrfToken() + '">'
            + '          <div class="form-group">'
            + '            <label for="review-send-title">Title</label>'
            + '            <input type="text" name="title" id="review-send-title" class="form-control" required>'
            + '          </div>'
            + '          <div class="form-group">'
            + '            <label for="review-send-due">Due date (optional)</label>'
            + '            <input type="text" name="due_date" id="review-send-due" class="form-control date-picker" placeholder="YYYY-MM-DD HH:MM">'
            + '          </div>'
            + '          <div class="form-group">'
            + '            <label for="review-send-reviewers">Reviewer user IDs (comma-separated)</label>'
            + '            <input type="text" name="reviewers" id="review-send-reviewers" class="form-control" required placeholder="12, 34, 56">'
            + '            <p class="help-block">Temporary simple input — phase 3 will replace with a typeahead picker.</p>'
            + '          </div>'
            + '          <div class="form-group">'
            + '            <label for="review-send-description">Description (optional)</label>'
            + '            <textarea name="description" id="review-send-description" class="form-control" rows="4"></textarea>'
            + '          </div>'
            + '        </div>'
            + '        <div class="modal-footer">'
            + '          <button type="button" class="btn btn-default" data-dismiss="modal">Cancel</button>'
            + '          <button type="submit" class="btn btn-primary">Open review request</button>'
            + '        </div>'
            + '      </form>'
            + '    </div>'
            + '  </div>'
            + '</div>';
        return $(html);
    }

    function buildSendButton(ctx) {
        var $btn = $('<button type="button" class="btn btn-default review-send-btn"/>')
            .attr('data-review-context', ctx.kind)
            .attr('data-review-pk', ctx.pk)
            .html('<i class="fa fa-paper-plane" aria-hidden="true"></i> Send for review');
        $btn.on('click', function () {
            var $modal = $('#review-send-modal');
            if ($modal.length === 0) {
                $modal = buildModal(ctx);
                $('body').append($modal);
            }
            $modal.modal('show');
        });
        return $btn;
    }

    function injectSendButton(ctx) {
        if (!ctx.pk) { return; }
        var $actions = $('.page-header .actions, .card-pf-heading .actions').first();
        if ($actions.length === 0) {
            $actions = $('.card-pf-heading').first();
        }
        if ($actions.length) {
            $actions.append(' ').append(buildSendButton(ctx));
        }
    }

    // ─── Per-case status badge ────────────────────────────────────────

    function badgeClassFor(state) {
        switch (state) {
            case 'approved': return 'label-success';
            case 'rejected': return 'label-danger';
            case 'changes_requested': return 'label-warning';
            case 'cancelled': return 'label-default';
            default: return 'label-info';
        }
    }

    function injectCaseBadge(casePk) {
        $.getJSON(PLUGIN_ROOT + '/json/case/' + casePk + '/latest/')
            .done(function (data) {
                if (!data || !data.item) { return; }
                var item = data.item;
                var cls = badgeClassFor(item.review_request.state);
                var $badge = $('<a class="label review-case-badge" role="status"></a>')
                    .addClass(cls)
                    .attr('href', item.review_request.url)
                    .attr('title', 'Review request #' + item.review_request.id)
                    .text(item.decision_display);
                var $target = $('.page-header h1, .card-pf-heading .card-pf-title').first();
                if ($target.length) {
                    $target.append(' ').append($badge);
                }
            })
            .fail(function () {
                // Silent — plugin must not disrupt core pages on failure
            });
    }

    // ─── Dashboard widget ─────────────────────────────────────────────

    function buildDashboardWidget(rows) {
        var $card = $('<div class="card-pf card-pf-view card-pf-view-select review-pending-card"/>');
        $card.append('<div class="card-pf-heading"><h2 class="card-pf-title"><i class="fa fa-gavel" aria-hidden="true"></i> Pending my review</h2></div>');
        var $body = $('<div class="card-pf-body"/>');

        if (rows.length === 0) {
            $body.append('<p class="text-muted">No review requests assigned to you.</p>');
        } else {
            var $list = $('<ul class="list-group"/>');
            rows.forEach(function (r) {
                var $item = $('<li class="list-group-item"/>');
                var $link = $('<a/>').attr('href', r.url).text('#' + r.id + ' ' + r.title);
                $item.append($link);
                $item.append('<br>');
                var due = r.due_date ? ' · Due ' + r.due_date.substring(0, 10) : '';
                $item.append($('<small class="text-muted"/>').text('By ' + r.requester + due));
                $list.append($item);
            });
            $body.append($list);
        }

        $card.append($body);
        return $card;
    }

    function injectDashboardWidget() {
        $.getJSON(PLUGIN_ROOT + '/json/pending-mine/')
            .done(function (data) {
                var rows = (data && data.results) || [];
                var $widget = buildDashboardWidget(rows);
                var $col = $('.row-cards-pf').first();
                if ($col.length === 0) {
                    $col = $('.container-fluid.container-cards-pf, .container-cards-pf').first();
                }
                if ($col.length) {
                    $col.prepend($widget);
                }
            })
            .fail(function () {
                // Silent
            });
    }

    // ─── Init ─────────────────────────────────────────────────────────

    $(function () {
        wireConfirmForms();

        var ctx = detectPageContext();
        if (!ctx) { return; }

        if (ctx.kind === 'testcase') {
            injectSendButton(ctx);
            injectCaseBadge(ctx.pk);
            return;
        }
        if (ctx.kind === 'testplan') {
            injectSendButton(ctx);
            return;
        }
        if (ctx.kind === 'dashboard') {
            injectDashboardWidget();
            return;
        }
    });
})($);
