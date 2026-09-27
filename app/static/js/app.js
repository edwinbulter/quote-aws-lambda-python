(function () {
    "use strict";

    // ---- Toast auto-dismiss -------------------------------------------------
    // Toast fragments are appended out-of-band into #toast-container by any
    // htmx response (see partials/toast.html). Watch for new children and
    // remove each one a few seconds after it appears.
    var toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) return;
                    setTimeout(function () {
                        node.classList.add("toast-fade-out");
                        setTimeout(function () {
                            node.remove();
                        }, 300);
                    }, 3000);
                });
            });
        });
        observer.observe(toastContainer, { childList: true });
    }

    // ---- Anonymous-visitor quote navigation ---------------------------------
    // Unauthenticated users browse a purely client-side history of quotes
    // seen this session (New Quote appends to it via the server response;
    // Previous/Next/First/Last replay from this local array with no extra
    // network round trip), mirroring the reference app's array-based nav
    // for logged-out visitors.
    var seenQuotes = [];
    var currentIndex = -1;

    function excludedIdsInput() {
        return document.getElementById("excluded-ids");
    }

    function quoteActionsEl() {
        return document.getElementById("quote-actions");
    }

    function renderQuoteDisplay(text, author) {
        var display = document.getElementById("quote-display");
        if (!display) return;
        display.innerHTML =
            '<p class="quote-text">“' + escapeHtml(text) + '”</p>' +
            '<p class="quote-author">' + escapeHtml(author) + "</p>";
    }

    function escapeHtml(value) {
        var div = document.createElement("div");
        div.textContent = value == null ? "" : value;
        return div.innerHTML;
    }

    function updateAnonButtons() {
        var prevBtn = document.getElementById("anon-previous-btn");
        var nextBtn = document.getElementById("anon-next-btn");
        var firstBtn = document.getElementById("anon-first-btn");
        var lastBtn = document.getElementById("anon-last-btn");
        if (!prevBtn) return; // authenticated layout - nothing to do

        var atStart = currentIndex <= 0;
        var atEnd = currentIndex < 0 || currentIndex >= seenQuotes.length - 1;
        prevBtn.disabled = atStart;
        firstBtn.disabled = atStart;
        nextBtn.disabled = atEnd;
        lastBtn.disabled = atEnd;
    }

    function syncAnonHistoryFromDom() {
        var actions = quoteActionsEl();
        if (!actions || actions.dataset.authenticated === "true") return;

        var quoteId = actions.dataset.quoteId;
        if (!quoteId) return;

        var existingIndex = seenQuotes.findIndex(function (q) {
            return q.id === quoteId;
        });
        if (existingIndex === -1) {
            seenQuotes.push({
                id: quoteId,
                text: actions.dataset.quoteText,
                author: actions.dataset.author,
            });
            currentIndex = seenQuotes.length - 1;
        } else {
            currentIndex = existingIndex;
        }

        var input = excludedIdsInput();
        if (input) {
            input.value = seenQuotes.map(function (q) { return q.id; }).join(",");
        }
        updateAnonButtons();
    }

    document.body.addEventListener("htmx:afterSettle", syncAnonHistoryFromDom);
    document.addEventListener("DOMContentLoaded", syncAnonHistoryFromDom);

    document.addEventListener("click", function (event) {
        var target = event.target;
        if (target.id === "anon-previous-btn" && currentIndex > 0) {
            currentIndex -= 1;
            var q = seenQuotes[currentIndex];
            renderQuoteDisplay(q.text, q.author);
            updateAnonButtons();
        } else if (target.id === "anon-next-btn" && currentIndex < seenQuotes.length - 1) {
            currentIndex += 1;
            var q2 = seenQuotes[currentIndex];
            renderQuoteDisplay(q2.text, q2.author);
            updateAnonButtons();
        } else if (target.id === "anon-first-btn" && seenQuotes.length > 0) {
            currentIndex = 0;
            var q3 = seenQuotes[0];
            renderQuoteDisplay(q3.text, q3.author);
            updateAnonButtons();
        } else if (target.id === "anon-last-btn" && seenQuotes.length > 0) {
            currentIndex = seenQuotes.length - 1;
            var q4 = seenQuotes[currentIndex];
            renderQuoteDisplay(q4.text, q4.author);
            updateAnonButtons();
        }
    });
})();
