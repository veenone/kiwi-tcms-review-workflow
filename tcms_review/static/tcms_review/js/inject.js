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

    // ─── Error + confirm modals (replace browser alerts) ──────────────

    function ensureErrorModal() {
        var $modal = $('#review-error-modal');
        if ($modal.length) { return $modal; }
        $modal = $(
            '<div class="modal fade" id="review-error-modal" tabindex="-1" role="dialog" aria-labelledby="review-error-title">' +
            '  <div class="modal-dialog" role="document">' +
            '    <div class="modal-content">' +
            '      <div class="modal-header">' +
            '        <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
            '        <h4 class="modal-title" id="review-error-title"><i class="pficon pficon-error-circle-o"></i> Error</h4>' +
            '      </div>' +
            '      <div class="modal-body"><p class="review-error-body"></p></div>' +
            '      <div class="modal-footer">' +
            '        <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>' +
            '      </div>' +
            '    </div>' +
            '  </div>' +
            '</div>'
        );
        $('body').append($modal);
        return $modal;
    }

    function showError(message, title) {
        var $modal = ensureErrorModal();
        $modal.find('.review-error-body').text(message || 'An unexpected error occurred.');
        if (title) {
            $modal.find('.modal-title').html('<i class="pficon pficon-error-circle-o"></i> ' + title);
        }
        $modal.modal('show');
    }

    function ensureConfirmModal() {
        var $modal = $('#review-confirm-modal');
        if ($modal.length) { return $modal; }
        $modal = $(
            '<div class="modal fade" id="review-confirm-modal" tabindex="-1" role="dialog" aria-labelledby="review-confirm-title">' +
            '  <div class="modal-dialog" role="document">' +
            '    <div class="modal-content">' +
            '      <div class="modal-header">' +
            '        <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
            '        <h4 class="modal-title" id="review-confirm-title"><i class="pficon pficon-warning-triangle-o"></i> Confirm</h4>' +
            '      </div>' +
            '      <div class="modal-body"><p class="review-confirm-body"></p></div>' +
            '      <div class="modal-footer">' +
            '        <button type="button" class="btn btn-default" data-dismiss="modal">Cancel</button>' +
            '        <button type="button" class="btn btn-danger review-confirm-ok">Confirm</button>' +
            '      </div>' +
            '    </div>' +
            '  </div>' +
            '</div>'
        );
        $('body').append($modal);
        return $modal;
    }

    function showConfirm(message, onConfirm) {
        var $modal = ensureConfirmModal();
        $modal.find('.review-confirm-body').text(message);
        var $ok = $modal.find('.review-confirm-ok');
        $ok.off('click.review').on('click.review', function () {
            $modal.modal('hide');
            if (typeof onConfirm === 'function') { onConfirm(); }
        });
        $modal.modal('show');
    }

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
                    showError(result.error.message || 'RPC error', 'Request failed');
                } else if (callback) {
                    callback(result.result);
                }
            },
            error: function (err, status, thrown) {
                console.log('*** tcms_review jsonRPC error:', err, status, thrown);
                showError(
                    'The server rejected the request (' + status + '). ' +
                    'Open the browser console for details.',
                    'Request failed'
                );
            }
        });
    }

    // ─── Page detection ───────────────────────────────────────────────

    function detectPageContext() {
        var pageId = (document.body && document.body.id) || '';
        var path = window.location.pathname || '';

        if (pageId === 'page-testcases-get' || /^\/case\/\d+\//.test(path)) {
            var $span = $('#test_case_pk');
            var casePk = $span.data('pk') || pkFromUrl(/\/case\/(\d+)/);
            return { kind: 'testcase', pk: casePk };
        }
        if (pageId === 'page-testplans-get' || /^\/plan\/\d+\//.test(path)) {
            var $container = $('[data-testplan-pk]');
            var planPk = $container.data('testplan-pk') || pkFromUrl(/\/plan\/(\d+)/);
            return { kind: 'testplan', pk: planPk };
        }
        if (pageId === 'page-dashboard' || pageId === 'core-views-index' || path === '/') {
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
            var form = this;
            if ($(form).data('confirmed')) { return true; }
            event.preventDefault();
            var message = $(form).data('confirm');
            showConfirm(message, function () {
                $(form).data('confirmed', true);
                form.submit();
            });
            return false;
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

    // ─── Review detail: TestCase / TestPlan browser tabs ────────────────

    function wireCaseBrowser() {
        var $form = $('#review-add-case-form');
        if (!$form.length) { return; }
        var reviewPk = $form.data('review-pk');

        function addCaseToReview(caseId) {
            jsonRPC('ReviewRequest.add_case', [reviewPk, caseId], function () {
                window.location.reload();
            });
        }

        // TestCase browser
        $('#review-case-browser-load').on('click', function () {
            var filter = $.trim($('#review-case-browser-filter').val());
            var rpcQuery = filter ? { summary__icontains: filter } : {};
            jsonRPC('TestCase.filter', rpcQuery, function (data) {
                var $tbody = $('#review-case-browser-table tbody').empty();
                if (!data || !data.length) {
                    $tbody.append('<tr><td colspan="4" class="text-muted">No cases found</td></tr>');
                    return;
                }
                $.each(data.slice(0, 50), function (i, tc) {
                    var $row = $('<tr/>');
                    var $addBtn = $('<button class="btn btn-xs btn-default" title="Add to review"><i class="fa fa-plus"></i></button>');
                    $addBtn.on('click', function () { addCaseToReview(tc.id); });
                    $row.append($('<td/>').append($addBtn));
                    $row.append($('<td/>').text(tc.id));
                    $row.append($('<td/>').append($('<a/>').attr('href', '/case/' + tc.id + '/').text(tc.summary)));
                    $row.append($('<td/>').text(tc.case_status__name || tc.case_status || ''));
                    $tbody.append($row);
                });
            });
        });

        // TestPlan browser — load plans, then expand to show cases
        $('#review-plan-browser-load').on('click', function () {
            var filter = $.trim($('#review-plan-browser-filter').val());
            var rpcQuery = filter ? { name__icontains: filter } : {};
            jsonRPC('TestPlan.filter', rpcQuery, function (data) {
                var $tbody = $('#review-plan-browser-table tbody').empty();
                if (!data || !data.length) {
                    $tbody.append('<tr><td colspan="4" class="text-muted">No plans found</td></tr>');
                    return;
                }
                $.each(data.slice(0, 30), function (i, plan) {
                    var $row = $('<tr/>');
                    $row.append($('<td/>').text(plan.id));
                    $row.append($('<td/>').append($('<a/>').attr('href', '/plan/' + plan.id + '/').text(plan.name)));
                    $row.append($('<td/>').text('—'));
                    var $expandBtn = $('<button class="btn btn-xs btn-default" title="Show cases"><i class="fa fa-chevron-down"></i></button>');
                    $expandBtn.on('click', function () {
                        var $nextRow = $row.next('.review-plan-cases-row');
                        if ($nextRow.length) {
                            $nextRow.toggle();
                            return;
                        }
                        jsonRPC('TestCase.filter', { plan: plan.id }, function (cases) {
                            var $casesRow = $('<tr class="review-plan-cases-row"/>');
                            var $td = $('<td colspan="4" style="padding-left:30px;"/>');
                            if (!cases || !cases.length) {
                                $td.append('<span class="text-muted">No cases in this plan</span>');
                            } else {
                                var $ul = $('<ul class="list-unstyled" style="margin:0;"/>');
                                $.each(cases.slice(0, 50), function (j, tc) {
                                    var $li = $('<li style="padding:2px 0;"/>');
                                    var $btn = $('<button class="btn btn-xs btn-default" style="margin-right:6px;"><i class="fa fa-plus"></i></button>');
                                    $btn.on('click', function () { addCaseToReview(tc.id); });
                                    $li.append($btn).append('TC-' + tc.id + ': ' + tc.summary);
                                    $ul.append($li);
                                });
                                $td.append($ul);
                            }
                            $casesRow.append($td);
                            $row.after($casesRow);
                        });
                    });
                    $row.append($('<td/>').append($expandBtn));
                    $tbody.append($row);
                });
            });
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
        wireCaseBrowser();
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
