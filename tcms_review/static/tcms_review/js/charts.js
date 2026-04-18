// kiwitcms-review — stats-page charts.
// Loaded from tcms_review/stats.html after c3.js and d3.js are in scope.
//
// Reads the JSON payload embedded in #review-stats-payload and renders
// three C3 charts: a donut of requests-by-state, a bar of top reviewers,
// and a bar of top requesters.
(function ($) {
    'use strict';

    function stateColor(label) {
        var l = (label || '').toLowerCase();
        if (l.indexOf('approved') > -1) return '#3f9c35';
        if (l.indexOf('rejected') > -1) return '#cc0000';
        if (l.indexOf('changes') > -1) return '#ec7a08';
        if (l.indexOf('cancel') > -1) return '#72767b';
        return '#39a5dc';
    }

    function drawStateDonut(data) {
        if (typeof c3 === 'undefined') { return; }
        var columns = Object.keys(data).map(function (k) { return [k, data[k]]; });
        var colors = {};
        Object.keys(data).forEach(function (k) { colors[k] = stateColor(k); });

        c3.generate({
            bindto: '#review-chart-state',
            data: {
                columns: columns,
                type: 'donut',
                colors: colors
            },
            donut: { title: 'By state' }
        });
    }

    function drawReviewerBar(rows) {
        if (typeof c3 === 'undefined' || !rows.length) { return; }
        var names = rows.map(function (r) { return r.name; });
        var counts = rows.map(function (r) { return r.count; });

        c3.generate({
            bindto: '#review-chart-reviewers',
            data: {
                columns: [['Votes cast'].concat(counts)],
                type: 'bar'
            },
            axis: {
                x: { type: 'category', categories: names },
                y: { label: { text: 'Votes', position: 'outer-middle' } }
            },
            bar: { width: { ratio: 0.6 } },
            color: { pattern: ['#39a5dc'] }
        });
    }

    function drawRequesterBar(rows) {
        if (typeof c3 === 'undefined' || !rows.length) { return; }
        var names = rows.map(function (r) { return r.name; });
        var counts = rows.map(function (r) { return r.count; });

        c3.generate({
            bindto: '#review-chart-requesters',
            data: {
                columns: [['Requests created'].concat(counts)],
                type: 'bar'
            },
            axis: {
                x: { type: 'category', categories: names },
                y: { label: { text: 'Requests', position: 'outer-middle' } }
            },
            bar: { width: { ratio: 0.6 } },
            color: { pattern: ['#3f9c35'] }
        });
    }

    function drawDailyLine(rows) {
        if (typeof c3 === 'undefined' || !rows.length) { return; }
        var dates = ['x'].concat(rows.map(function (r) { return r.date; }));
        var counts = ['Created'].concat(rows.map(function (r) { return r.count; }));

        c3.generate({
            bindto: '#review-chart-timeline',
            data: {
                x: 'x',
                columns: [dates, counts],
                type: 'area-spline'
            },
            axis: {
                x: {
                    type: 'timeseries',
                    tick: { format: '%Y-%m-%d' }
                }
            },
            color: { pattern: ['#0088ce'] },
            point: { show: false }
        });
    }

    $(function () {
        var $payload = $('#review-stats-payload');
        if (!$payload.length) { return; }
        var data;
        try { data = JSON.parse($payload.text()); }
        catch (e) { return; }

        drawStateDonut(data.by_state || {});
        drawReviewerBar(data.top_reviewers || []);
        drawRequesterBar(data.top_requesters || []);
        drawDailyLine(data.daily || []);
    });
})($);
