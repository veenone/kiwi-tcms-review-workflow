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

    // Map raw backend error messages to a user-friendly {title, body, hint}
    // tuple. Patterns are matched in order; the first match wins. Falls
    // through to a generic "Something went wrong" for unknown messages.
    var ERROR_PATTERNS = [
        {
            match: /TestCase status '([^']+)' is not allowed for review\. Allowed statuses: (.+)/,
            build: function (m) {
                return {
                    title: "That test case can't be sent for review yet",
                    body: "Test cases can only be sent for review while their status is: " + m[2] + ". This case is currently '" + m[1] + "'.",
                    hint: "Change the case status to one of the allowed values first, or ask an admin to extend REVIEW_ALLOWED_CASE_STATUSES."
                };
            }
        },
        {
            match: /Only the requester can cancel/i,
            build: function () {
                return {
                    title: "Only the requester can cancel this review",
                    body: "The review request can only be cancelled by the person who created it.",
                    hint: "Ask the requester to cancel, or contact an admin."
                };
            }
        },
        {
            match: /Only assigned reviewers can vote/i,
            build: function () {
                return {
                    title: "You are not a reviewer on this request",
                    body: "Voting is restricted to the reviewers listed on the request.",
                    hint: "Ask the requester to add you to the reviewers list."
                };
            }
        },
        {
            match: /Cannot vote on a cancelled review request/i,
            build: function () {
                return {
                    title: "This review request has been cancelled",
                    body: "Votes cannot be cast on a cancelled review request.",
                    hint: ""
                };
            }
        },
        {
            match: /approved and can no longer be modified/i,
            build: function () {
                return {
                    title: "This review is approved and locked",
                    body: "Once a review reaches the Approved state, its cases, reviewers, votes and decisions cannot be changed.",
                    hint: "Create a new review request to track follow-up work."
                };
            }
        },
        {
            match: /approved and can no longer be voted on/i,
            build: function () {
                return {
                    title: "This review is already approved",
                    body: "Further votes cannot be cast on an approved review.",
                    hint: ""
                };
            }
        },
        {
            match: /All cases must have a decision recorded/i,
            build: function () {
                return {
                    title: "Decide on every case first",
                    body: "Before you can cast your vote, each case listed under this review must have its decision set to Approve, Needs changes, or Reject.",
                    hint: "Use the inline buttons in the 'Cases under review' table."
                };
            }
        },
        {
            match: /Invalid decision: (.+)/,
            build: function (m) {
                return {
                    title: "Invalid decision value",
                    body: "'" + m[1] + "' isn't a recognised decision. Valid decisions are Pending, Approved, Rejected, and Needs changes.",
                    hint: ""
                };
            }
        },
        {
            match: /Approved review requests cannot be cancelled/i,
            build: function () {
                return {
                    title: "Approved reviews cannot be cancelled",
                    body: "Once a review is approved it becomes immutable — including its cancel action.",
                    hint: ""
                };
            }
        },
        {
            match: /Only cases marked 'Needs changes' or 'Rejected' can be resubmitted/i,
            build: function () {
                return {
                    title: "That case doesn't need re-review",
                    body: "Only cases that were marked 'Needs changes' or 'Rejected' by a reviewer can be resubmitted.",
                    hint: "If you want to update a case that's pending or already approved, ask a reviewer to mark it 'Needs changes' first."
                };
            }
        },
        {
            match: /cancelled and cannot be reopened/i,
            build: function () {
                return {
                    title: "This review request has been cancelled",
                    body: "Cancelled review requests cannot be reopened.",
                    hint: "Start a new review request for the updated case."
                };
            }
        }
    ];

    function humaniseError(raw) {
        if (!raw) {
            return {
                title: "Something went wrong",
                body: "The server did not return an error message.",
                hint: ""
            };
        }
        // Strip JSON-RPC's verbose prefix
        var msg = String(raw).replace(/^Internal error:\s*/i, '').trim();

        for (var i = 0; i < ERROR_PATTERNS.length; i++) {
            var p = ERROR_PATTERNS[i];
            var m = msg.match(p.match);
            if (m) { return p.build(m); }
        }

        return {
            title: "That action didn't work",
            body: msg,
            hint: ""
        };
    }

    function showError(rawMessage, title) {
        var $modal = ensureErrorModal();
        var $body = $modal.find('.modal-body');
        var $title = $modal.find('.modal-title');

        if (title) {
            // Explicit title override (used for generic errors)
            $title.html('<i class="pficon pficon-error-circle-o"></i> ' + title);
            $body.empty().append($('<p class="review-error-body"/>').text(rawMessage || ''));
        } else {
            var parsed = humaniseError(rawMessage);
            $title.html('<i class="pficon pficon-error-circle-o"></i> ' + parsed.title);
            $body.empty();
            $body.append($('<p class="review-error-body"/>').text(parsed.body));
            if (parsed.hint) {
                $body.append($('<p class="review-error-hint text-muted"/>').text(parsed.hint));
            }
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
                    // Let showError humanise the raw message; no explicit title.
                    showError(result.error.message || 'RPC error');
                } else if (callback) {
                    callback(result.result);
                }
            },
            error: function (err, status, thrown) {
                console.log('*** tcms_review jsonRPC error:', err, status, thrown);
                showError(
                    'The server could not be reached (' + status + '). ' +
                    'Check your connection and try again.',
                    'Something went wrong'
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

        // Header + tab nav — two modes: start a new review, or append
        // this case to one of the current user's already-open reviews.
        $content.append(
            '<div class="modal-header">' +
            '  <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
            '  <h4 class="modal-title">Send for review</h4>' +
            '  <ul class="nav nav-tabs" role="tablist" style="margin-top:12px;margin-bottom:-16px;">' +
            '    <li role="presentation" class="active"><a href="#review-send-tab-new" data-toggle="tab" role="tab">' +
            '      <i class="fa fa-plus" aria-hidden="true"></i> New review</a></li>' +
            '    <li role="presentation"><a href="#review-send-tab-existing" data-toggle="tab" role="tab" id="review-send-tab-existing-trigger">' +
            '      <i class="fa fa-folder-open-o" aria-hidden="true"></i> Add to existing</a></li>' +
            '  </ul>' +
            '</div>'
        );

        var $tabContent = $('<div class="tab-content"/>');

        // ── Tab 1: create a new review request (existing form) ────────
        var formAction = PLUGIN_ROOT + '/new/?' + ctx.kind + '=' + ctx.pk;
        var $form = $('<form method="post" class="tab-pane active" id="review-send-tab-new" role="tabpanel"/>')
            .attr('action', formAction);
        $form.append('<input type="hidden" name="csrfmiddlewaretoken" value="' + getCsrfToken() + '">');

        var $body = $('<div class="modal-body"/>');
        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-title">Title</label>' +
            '  <input type="text" name="title" id="review-send-title" class="form-control" required>' +
            '</div>'
        );
        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-due">Due date (optional)</label>' +
            '  <input type="text" name="due_date" id="review-send-due" class="form-control" autocomplete="off">' +
            '</div>'
        );
        var $reviewerGroup = $('<div class="form-group"/>');
        $reviewerGroup.append('<label>Reviewers</label>');
        $reviewerGroup.append(buildUserPicker('review-send-reviewer-search', 'review-send-reviewers'));
        $body.append($reviewerGroup);
        $body.append(
            '<div class="form-group">' +
            '  <label for="review-send-description">Description (optional)</label>' +
            '  <textarea name="description" id="review-send-description" class="form-control" rows="3"></textarea>' +
            '</div>'
        );
        $form.append($body);
        $form.append(
            '<div class="modal-footer">' +
            '  <button type="button" class="btn btn-default" data-dismiss="modal">Cancel</button>' +
            '  <button type="submit" class="btn btn-primary">Create review request</button>' +
            '</div>'
        );
        $tabContent.append($form);

        // ── Tab 2: add to an existing open review owned by the user ──
        var $existing = $('<div class="tab-pane" id="review-send-tab-existing" role="tabpanel"/>');
        var $existingBody = $('<div class="modal-body"/>');
        $existingBody.append(
            '<p class="text-muted" style="margin-bottom:12px;">' +
            'Attach this case to one of your open review requests. ' +
            'Only your own in-review requests are shown.</p>'
        );
        $existingBody.append(
            '<div class="review-send-existing-list">' +
            '  <div class="text-muted"><i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Loading your open reviews…</div>' +
            '</div>'
        );
        $existing.append($existingBody);
        $existing.append(
            '<div class="modal-footer">' +
            '  <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>' +
            '</div>'
        );
        $tabContent.append($existing);

        $content.append($tabContent);
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

        // Lazy-load the existing-reviews list the first time that tab
        // is activated, so the modal-open path doesn't pay an RPC cost
        // for users who only ever create new reviews.
        var loaded = false;
        $modal.on('shown.bs.tab', '#review-send-tab-existing-trigger', function () {
            if (loaded) { return; }
            loaded = true;
            loadExistingReviewsForCase($modal, ctx);
        });

        return $modal;
    }

    function loadExistingReviewsForCase($modal, ctx) {
        var userId = getCurrentUserId();
        var $list = $modal.find('.review-send-existing-list');
        if (userId === null) {
            $list.html('<div class="alert alert-warning">Could not detect the current user — please reload the page.</div>');
            return;
        }
        // Mirror is_locked / cancelled logic — only IN_REVIEW is a valid
        // target. Restrict to this user's own requests so the operator
        // doesn't accidentally expose cases into someone else's review.
        jsonRPC(
            'ReviewRequest.filter',
            { requester: userId, state: 'in_review' },
            function (data) {
                $list.empty();
                if (!data || !data.length) {
                    $list.append(
                        '<div class="review-blank-slate" style="padding:20px;">' +
                        '  <i class="fa fa-inbox" aria-hidden="true"></i>' +
                        '  <p class="text-muted">You have no open review requests.<br>' +
                        '  Switch to the <b>New review</b> tab to start one.</p>' +
                        '</div>'
                    );
                    return;
                }
                var $ul = $('<ul class="list-group"/>');
                $.each(data, function (i, r) {
                    var $li = $('<li class="list-group-item"/>').css({display: 'flex', alignItems: 'center'});
                    var $text = $('<div/>').css({flex: 1});
                    $text.append(
                        $('<a target="_blank" rel="noopener"/>')
                            .attr('href', PLUGIN_ROOT + '/' + r.id + '/')
                            .text('#' + r.id + ' · ' + r.title)
                    );
                    if (r.due_date) {
                        $text.append(
                            $('<div class="text-muted" style="font-size:12px;"/>')
                                .text('Due ' + r.due_date.replace('T', ' ').substring(0, 16))
                        );
                    }
                    var $btn = $('<button type="button" class="btn btn-primary btn-sm"/>')
                        .html('<i class="fa fa-plus" aria-hidden="true"></i> Add this case');
                    $btn.on('click', function () {
                        $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Adding…');
                        jsonRPC(
                            'ReviewRequest.add_case',
                            [r.id, parseInt(ctx.pk, 10)],
                            function () {
                                window.location.href = PLUGIN_ROOT + '/' + r.id + '/';
                            }
                        );
                    });
                    $li.append($text).append($btn);
                    $ul.append($li);
                });
                $list.append($ul);
            }
        );
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

    // Current user id injected by the middleware on every HTML response.
    function getCurrentUserId() {
        var tag = document.querySelector('script[data-source="tcms_review"]');
        if (!tag) { return null; }
        var raw = tag.dataset.currentUserId;
        if (!raw) { return null; }
        var parsed = parseInt(raw, 10);
        return isNaN(parsed) ? null : parsed;
    }

    function renderSendButton(ctx) {
        if (ctx.kind === 'testcase') {
            var $h1 = $('h1.col-md-12').first();
            if ($h1.length) {
                var $btnWrap = $('<div class="col-md-12" style="margin-bottom:12px;"/>');
                $btnWrap.append(buildSendButton(ctx));
                $h1.after($btnWrap);
                return;
            }
        }
        if (ctx.kind === 'testplan') {
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

    function injectSendButton(ctx) {
        if (!ctx.pk) { return; }

        // For testplans, any authenticated user with permission can send
        // the plan for review (no author concept at the plan level the same way).
        if (ctx.kind === 'testplan') {
            renderSendButton(ctx);
            return;
        }

        if (ctx.kind === 'testcase') {
            var currentUserId = getCurrentUserId();
            if (currentUserId === null) {
                // Anonymous / anonymous-ish — fail closed.
                return;
            }

            // Author-only: the Send-for-review button is only useful to the
            // case's author (or default tester). Fetch the case once and
            // compare against the current user id. Fail closed on RPC error.
            jsonRPC('TestCase.filter', { pk: parseInt(ctx.pk, 10) }, function (data) {
                if (!data || !data.length) { return; }
                var tc = data[0];
                var isAuthor = tc.author === currentUserId;
                var isTester = tc.default_tester === currentUserId;
                if (isAuthor || isTester) {
                    renderSendButton(ctx);
                }
            });
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

    // ─── Review detail page: decide with comment ──────────────────────

    function ensureItemCommentModal() {
        var $modal = $('#review-item-comment-modal');
        if ($modal.length) { return $modal; }
        $modal = $(
            '<div class="modal fade" id="review-item-comment-modal" tabindex="-1" role="dialog" aria-labelledby="review-item-comment-title">' +
            '  <div class="modal-dialog" role="document">' +
            '    <div class="modal-content">' +
            '      <form method="post" class="form-horizontal">' +
            '        <input type="hidden" name="csrfmiddlewaretoken">' +
            '        <div class="modal-header">' +
            '          <button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>' +
            '          <h4 class="modal-title" id="review-item-comment-title">' +
            '            <i class="fa fa-commenting-o" aria-hidden="true"></i> Decide with a comment' +
            '          </h4>' +
            '          <p class="modal-subtitle text-muted" style="margin:4px 0 0;"></p>' +
            '        </div>' +
            '        <div class="modal-body">' +
            '          <div class="form-group">' +
            '            <label class="col-sm-3 control-label">Decision</label>' +
            '            <div class="col-sm-9 review-item-comment-radios">' +
            '              <label class="radio-inline"><input type="radio" name="decision" value="approved"> <i class="pficon pficon-ok text-success"></i> Approve</label>' +
            '              <label class="radio-inline"><input type="radio" name="decision" value="needs_changes"> <i class="pficon pficon-warning-triangle-o text-warning"></i> Needs changes</label>' +
            '              <label class="radio-inline"><input type="radio" name="decision" value="rejected"> <i class="pficon pficon-error-circle-o text-danger"></i> Reject</label>' +
            '              <label class="radio-inline"><input type="radio" name="decision" value="pending"> <i class="fa fa-hourglass-half"></i> Pending</label>' +
            '            </div>' +
            '          </div>' +
            '          <div class="form-group">' +
            '            <label for="review-item-comment-text" class="col-sm-3 control-label">Comment</label>' +
            '            <div class="col-sm-9">' +
            '              <textarea id="review-item-comment-text" name="comment" class="form-control" rows="4" placeholder="Add a note explaining your decision (optional)"></textarea>' +
            '              <p class="help-block">Shown in the case row, the activity feed, and the wiki page (if wiki sync is enabled).</p>' +
            '            </div>' +
            '          </div>' +
            '        </div>' +
            '        <div class="modal-footer">' +
            '          <button type="button" class="btn btn-default" data-dismiss="modal">Cancel</button>' +
            '          <button type="submit" class="btn btn-primary"><i class="fa fa-save"></i> Save decision</button>' +
            '        </div>' +
            '      </form>' +
            '    </div>' +
            '  </div>' +
            '</div>'
        );
        $('body').append($modal);
        return $modal;
    }

    function wireItemCommentModal() {
        // Any button tagged with the review-item-decide-with-comment class
        // (rendered from get.html per case) opens the shared modal.
        $(document).on('click', '.review-item-decide-with-comment', function () {
            var $btn = $(this);
            var $modal = ensureItemCommentModal();
            var $form = $modal.find('form');

            // Fill the form from the button's data-* attributes.
            $form.attr('action', $btn.data('url'));
            $form.find('input[name=csrfmiddlewaretoken]').val(getCsrfToken());

            var currentDecision = $btn.data('item-decision') || 'pending';
            $form.find('input[name=decision]').prop('checked', false);
            $form.find('input[name=decision][value="' + currentDecision + '"]')
                .prop('checked', true);

            $form.find('textarea[name=comment]').val($btn.data('item-comment') || '');

            $modal.find('.modal-subtitle').text(
                'TC-' + $btn.data('item-case-id') + ' — ' +
                ($btn.data('item-case-summary') || '')
            );

            $modal.modal('show');
            setTimeout(function () {
                $form.find('textarea[name=comment]').focus();
            }, 250);
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

    // Cache for allowed case statuses + current user — fetched once per
    // page load. Both browsers filter cases to:
    //   - case_status.name ∈ allowed_case_statuses  (plugin config)
    //   - author = current user                      (show only mine)
    var _allowedStatusesPromise = null;
    function getAllowedStatuses() {
        if (_allowedStatusesPromise === null) {
            _allowedStatusesPromise = $.ajax({
                url: PLUGIN_ROOT + '/json/allowed-statuses/',
                dataType: 'json'
            }).then(function (resp) {
                return (resp && resp.allowed) || [];
            }, function () {
                return [];
            });
        }
        return _allowedStatusesPromise;
    }

    function buildBrowserCaseQuery(extra) {
        return $.when(getAllowedStatuses()).then(function (allowed) {
            var q = $.extend({}, extra || {});
            if (allowed && allowed.length) {
                q.case_status__name__in = allowed;
            }
            var userId = getCurrentUserId();
            if (userId !== null) {
                q.author = userId;
            }
            return q;
        });
    }

    function wireCaseBrowser() {
        var $form = $('#review-add-case-form');
        if (!$form.length) { return; }
        var reviewPk = $form.data('review-pk');

        function addCaseToReview(caseId) {
            jsonRPC('ReviewRequest.add_case', [reviewPk, caseId], function () {
                window.location.reload();
            });
        }

        // TestCase browser — filters by plugin-configured allowed statuses
        // AND by current user as author.
        $('#review-case-browser-load').on('click', function () {
            var filter = $.trim($('#review-case-browser-filter').val());
            var extra = filter ? { summary__icontains: filter } : {};
            buildBrowserCaseQuery(extra).then(function (rpcQuery) {
                jsonRPC('TestCase.filter', rpcQuery, function (data) {
                    var $tbody = $('#review-case-browser-table tbody').empty();
                    if (!data || !data.length) {
                        $tbody.append('<tr><td colspan="4" class="text-muted">No cases match — showing only cases authored by you with allowed status.</td></tr>');
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
        });

        // TestPlan browser — lists plans; expanding shows cases filtered
        // by the same allowed-statuses + author rule as the case browser.
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
                        buildBrowserCaseQuery({ plan: plan.id }).then(function (caseQuery) {
                            jsonRPC('TestCase.filter', caseQuery, function (cases) {
                                var $casesRow = $('<tr class="review-plan-cases-row"/>');
                                var $td = $('<td colspan="4" style="padding-left:30px;"/>');
                                if (!cases || !cases.length) {
                                    $td.append('<span class="text-muted">No matching cases in this plan — only your cases with an allowed status are shown.</span>');
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
                    });
                    $row.append($('<td/>').append($expandBtn));
                    $tbody.append($row);
                });
            });
        });
    }

    // ─── Activity feed: collapse-all / expand-all + thread pagination ──

    function wireActivityFeed() {
        var $wrapper = $('.review-activity-feed-wrapper');
        if (!$wrapper.length) { return; }

        var pageSize = parseInt($wrapper.data('page-size'), 10) || 5;
        var $threads = $wrapper.find('.review-activity-thread');
        var totalThreads = $threads.length;
        var totalPages = Math.max(1, Math.ceil(totalThreads / pageSize));
        var currentPage = 1;

        function renderPage() {
            $threads.each(function (i) {
                var pageIndex = Math.floor(i / pageSize) + 1;
                $(this).toggle(pageIndex === currentPage);
            });
            $wrapper.find('[data-review-activity-page-label]')
                .text(currentPage + ' / ' + totalPages);
            $wrapper.find('[data-review-activity-page="prev"]').parent()
                .toggleClass('disabled', currentPage <= 1);
            $wrapper.find('[data-review-activity-page="next"]').parent()
                .toggleClass('disabled', currentPage >= totalPages);
        }

        // Chevron rotation on Bootstrap collapse events
        $wrapper.on('show.bs.collapse', '.review-activity-thread-body', function () {
            $(this).siblings('.review-activity-thread-header')
                .find('.review-activity-chevron')
                .removeClass('review-activity-chevron-rotated');
        });
        $wrapper.on('hide.bs.collapse', '.review-activity-thread-body', function () {
            $(this).siblings('.review-activity-thread-header')
                .find('.review-activity-chevron')
                .addClass('review-activity-chevron-rotated');
        });

        // Expand-all / collapse-all
        $wrapper.on('click', '[data-review-activity-action]', function () {
            var action = $(this).data('review-activity-action');
            var $bodies = $wrapper.find('.review-activity-thread-body');
            if (action === 'expand-all') {
                $bodies.collapse('show');
            } else if (action === 'collapse-all') {
                $bodies.collapse('hide');
            }
        });

        // Keyboard support for collapse on thread headers
        $wrapper.on('keydown', '.review-activity-thread-header', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                $(this).trigger('click');
            }
        });

        // Pagination (only show if multiple pages)
        if (totalPages > 1) {
            $wrapper.find('.review-activity-pagination').show();
            $wrapper.on('click', '[data-review-activity-page]', function (e) {
                e.preventDefault();
                var direction = $(this).data('review-activity-page');
                if (direction === 'prev' && currentPage > 1) { currentPage--; }
                if (direction === 'next' && currentPage < totalPages) { currentPage++; }
                renderPage();
            });
            renderPage();
        }
    }

    // ─── Report hub export buttons ─────────────────────────────────────

    function wireReportHubExports() {
        $('[data-export-base][data-entity-input][data-fmt]').on('click', function () {
            var $btn = $(this);
            var base = $btn.data('export-base');
            var fmt = $btn.data('fmt');
            var entityId = $($btn.data('entity-input')).val();
            var start = $($btn.data('start-input')).val();
            var end = $($btn.data('end-input')).val();
            if (!entityId) {
                showError('Please select a value from the dropdown first.');
                return;
            }
            var params = [];
            if (start) { params.push('start=' + encodeURIComponent(start)); }
            if (end) { params.push('end=' + encodeURIComponent(end)); }
            var qs = params.length ? ('?' + params.join('&')) : '';
            var url = base + encodeURIComponent(entityId) + '/' + fmt + '/' + qs;
            window.location.href = url;
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
        wireActivityFeed();
        wireReportHubExports();
        wireItemCommentModal();
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
