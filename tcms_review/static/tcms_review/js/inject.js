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

    // ─── Helpers ──────────────────────────────────────────────────────

    function getCsrfToken() {
        // CSRF_COOKIE_HTTPONLY = True in Kiwi, so the cookie is unreadable.
        // Every authenticated page has a {% csrf_token %} hidden input in
        // the logout form (navbar.html). Read it from there.
        var $input = $('input[name=csrfmiddlewaretoken]').first();
        return $input.length ? $input.val() : '';
    }

    function jsonRPC(method, params, callback) {
        if (!Array.isArray(params)) { params = [params]; }
        $.ajax({
            url: '/json-rpc/',
            data: JSON.stringify({
                jsonrpc: '2.0',
                method: method,
                params: params,
                id: 'tcms_review'
            }),
            type: 'POST',
            dataType: 'json',
            contentType: 'application/json',
            success: function (result) {
                if (result.error) {
                    // eslint-disable-next-line no-alert
                    alert(result.error.message);
                } else if (callback) {
                    callback(result.result);
                }
            },
            error: function (err, status, thrown) {
                console.log('*** tcms_review jsonRPC error:', err, status, thrown);
            }
        });
    }

    // ─── Page detection ───────────────────────────────────────────────

    function detectPageContext() {
        var pageId = (document.body && document.body.id) || '';

        if (pageId === 'page-testcases-get') {
            var $span = $('#test_case_pk');
            return { kind: 'testcase', pk: $span.data('pk') || null };
        }
        if (pageId === 'page-testplans-get') {
            var $container = $('[data-testplan-pk]');
            var pk = $container.data('testplan-pk') || pkFromUrl(/\/plan\/(\d+)/);
            return { kind: 'testplan', pk: pk };
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

    // ─── User typeahead picker ────────────────────────────────────────

    function buildUserPicker(inputId, hiddenId) {
        var $wrapper = $('<div class="review-user-picker"/>');

        var $input = $('<input type="text" class="form-control" autocomplete="off"/>')
            .attr('id', inputId)
            .attr('placeholder', 'Type username or email to search...');
        var $hidden = $('<input type="hidden"/>')
            .attr('id', hiddenId)
            .attr('name', 'reviewers');
        var $tags = $('<div class="review-user-tags" style="margin-top:6px;"/>');
        var $results = $('<ul class="dropdown-menu review-user-results" style="display:none; position:absolute; z-index:1060;"/>');

        var selectedUsers = {};

        function renderTags() {
            $tags.empty();
            $.each(selectedUsers, function (pk, username) {
                var $tag = $('<span class="label label-info" style="margin-right:4px; cursor:pointer;"/>')
                    .text(username + ' ✕')
                    .attr('title', 'Click to remove')
                    .on('click', function () {
                        delete selectedUsers[pk];
                        renderTags();
                    });
                $tags.append($tag);
            });
            var ids = Object.keys(selectedUsers);
            $hidden.val(ids.join(','));
        }

        var searchTimer;
        $input.on('input', function () {
            clearTimeout(searchTimer);
            var query = $.trim($input.val());
            if (query.length < 2) {
                $results.hide();
                return;
            }
            searchTimer = setTimeout(function () {
                jsonRPC('User.filter', { username__icontains: query }, function (data) {
                    $results.empty();
                    if (!data || !data.length) {
                        $results.hide();
                        return;
                    }
                    $.each(data, function (i, user) {
                        if (selectedUsers[user.id]) { return; }
                        var $li = $('<li><a href="#"></a></li>');
                        $li.find('a').text(user.username + ' (' + user.email + ')');
                        $li.on('click', function (e) {
                            e.preventDefault();
                            selectedUsers[user.id] = user.username;
                            renderTags();
                            $input.val('');
                            $results.hide();
                        });
                        $results.append($li);
                    });
                    $results.show();
                });
            }, 300);
        });

        $(document).on('click', function (e) {
            if (!$(e.target).closest('.review-user-picker').length) {
                $results.hide();
            }
        });

        $wrapper.append($input).append($results).append($hidden).append($tags);
        return $wrapper;
    }

    // ─── Send-for-review modal ────────────────────────────────────────

    function buildModal(ctx) {
        var $modal = $('<div class="modal fade" id="review-send-modal" tabindex="-1" role="dialog"/>');
        var $dialog = $('<div class="modal-dialog" role="document"/>');
        var $content = $('<div class="modal-content"/>');

        var formAction = PLUGIN_ROOT + '/new/?' + ctx.kind + '=' + ctx.pk;

        var $form = $('<form method="post"/>')
            .attr('action', formAction);
        $form.append('<input type="hidden" name="csrfmiddlewaretoken" value="' + getCsrfToken() + '">');

        // Header
        $form.append(
            '<div class="modal-header">' +
            '  <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
            '  <h4 class="modal-title">Send for review</h4>' +
            '</div>'
        );

        // Body
        var $body = $('<div class="modal-body"/>');

        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-title">Title</label>' +
            '  <input type="text" name="title" id="review-send-title" class="form-control" required>' +
            '</div>'
        );

        // Due date with datetimepicker
        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-due">Due date (optional)</label>' +
            '  <input type="text" name="due_date" id="review-send-due" class="form-control" autocomplete="off">' +
            '</div>'
        );

        // Reviewers — user typeahead picker
        var $reviewerGroup = $('<div class="form-group"/>');
        $reviewerGroup.append('<label>Reviewers</label>');
        $reviewerGroup.append(buildUserPicker('review-send-reviewer-search', 'review-send-reviewers'));
        $body.append($reviewerGroup);

        // Description
        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-description">Description (optional)</label>' +
            '  <textarea name="description" id="review-send-description" class="form-control" rows="3"></textarea>' +
            '</div>'
        );

        $form.append($body);

        // Footer
        $form.append(
            '<div class="modal-footer">' +
            '  <button type="button" class="btn btn-default" data-dismiss="modal">Cancel</button>' +
            '  <button type="submit" class="btn btn-primary">Create review request</button>' +
            '</div>'
        );

        $content.append($form);
        $dialog.append($content);
        $modal.append($dialog);

        // Initialize datetimepicker after DOM insertion
        $modal.on('shown.bs.modal', function () {
            if ($.fn.datetimepicker) {
                $('#review-send-due').datetimepicker({
                    format: 'YYYY-MM-DD HH:mm',
                    allowInputToggle: true,
                    showTodayButton: true,
                    locale: $('html').attr('lang') || 'en',
                    icons: { today: 'today-button-pf' }
                });
            }
        });

        return $modal;
    }

    function buildSendButton(ctx) {
        var $btn = $('<button type="button" class="btn btn-default review-send-btn"/>')
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

        if (ctx.kind === 'testcase') {
            // TestCase detail: inject after the <h1> heading
            var $h1 = $('h1.col-md-12').first();
            if ($h1.length) {
                var $btnWrap = $('<div class="col-md-12" style="margin-bottom:12px;"/>');
                $btnWrap.append(buildSendButton(ctx));
                $h1.after($btnWrap);
                return;
            }
        }

        if (ctx.kind === 'testplan') {
            // TestPlan detail: inject into the toolbar actions area
            var $toolbar = $('.toolbar-pf-actions').first();
            if ($toolbar.length) {
                var $group = $('<div class="form-group" style="margin-left:8px; display:inline-block;"/>');
                $group.append(buildSendButton(ctx));
                $toolbar.append($group);
                return;
            }
        }

        // Fallback
        var $heading = $('.card-pf-heading').first();
        if ($heading.length) {
            $heading.append(' ').append(buildSendButton(ctx));
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
                var $target = $('h1.col-md-12').first();
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

    // ─── Review detail page: add test case ────────────────────────────

    function wireAddCaseForm() {
        var $form = $('#review-add-case-form');
        if (!$form.length) { return; }

        var $input = $form.find('#review-add-case-input');
        var $results = $form.find('.review-add-case-results');
        var reviewPk = $form.data('review-pk');

        var searchTimer;
        $input.on('input', function () {
            clearTimeout(searchTimer);
            var query = $.trim($input.val());
            if (query.length < 2) { $results.hide(); return; }
            searchTimer = setTimeout(function () {
                var rpcQuery = {};
                if (!isNaN(query)) {
                    rpcQuery = { pk: parseInt(query, 10) };
                } else {
                    rpcQuery = { summary__icontains: query };
                }
                jsonRPC('TestCase.filter', rpcQuery, function (data) {
                    $results.empty();
                    if (!data || !data.length) {
                        $results.append('<li class="text-muted" style="padding:6px 12px;">No cases found</li>');
                        $results.show();
                        return;
                    }
                    $.each(data.slice(0, 20), function (i, tc) {
                        var $li = $('<li><a href="#"></a></li>');
                        $li.find('a').text('TC-' + tc.id + ': ' + tc.summary);
                        $li.on('click', function (e) {
                            e.preventDefault();
                            $results.hide();
                            $input.val('');
                            jsonRPC('ReviewRequest.add_case', [reviewPk, tc.id], function () {
                                window.location.reload();
                            });
                        });
                        $results.append($li);
                    });
                    $results.show();
                });
            }, 300);
        });

        $(document).on('click', function (e) {
            if (!$(e.target).closest('#review-add-case-form').length) {
                $results.hide();
            }
        });
    }

    // ─── Datepicker init for server-rendered forms ─────────────────────

    function initDatePickers() {
        if (!$.fn.datetimepicker) { return; }
        $('#id_due_date').datetimepicker({
            format: 'YYYY-MM-DD HH:mm',
            allowInputToggle: true,
            showTodayButton: true,
            locale: $('html').attr('lang') || 'en',
            icons: { today: 'today-button-pf' }
        });
    }

    // ─── Init ─────────────────────────────────────────────────────────

    $(function () {
        wireConfirmForms();
        wireAddCaseForm();
        initDatePickers();

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
