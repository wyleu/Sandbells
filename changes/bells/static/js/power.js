/* power.js -- Reboot / Shut down for this machine (bells/power_controls.html).
 *
 * Press a button -> a confirm appears that names the machine and says what
 * will happen; it cancels itself after CONFIRM_S seconds.  Yes -> POST
 * /control/<name>/ with the CSRF token.  Sandbells answers at once and acts a
 * couple of seconds later.  After a reboot the page says so and polls
 * /control/ping/ until Sandbells is back on a new boot, then reloads.  After a
 * shut down it just says to wait for the green light.  No libraries, no confirm().
 *
 * The pure helpers are exported for the node tests (bells/js_tests/).
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SandbellsPower = api;
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", api.start);
    else api.start();
  }
})(this, function () {
  "use strict";

  var CONFIRM_S = 5;
  var POLL_MS = 2500;
  var POLL_TIMEOUT_MS = 3000;
  var SEND_TIMEOUT_MS = 8000;

  /* what the confirm says for an action on a machine */
  function confirmInfo(action, machine) {
    if (action === "reboot") {
      return { yes: "Yes, reboot " + machine + " now",
               note: "Reboots " + machine + " only. It is offline for about a minute." };
    }
    return { yes: "Yes, shut down " + machine,
             note: "Shuts " + machine + " down. It stays off until its power is switched off and on again." };
  }

  /* what the page says once Sandbells has accepted the action */
  function acceptedText(action, machine) {
    if (action === "reboot") return "Rebooting " + machine + "… reconnect shortly";
    return "Shutting down " + machine + "… wait for the green light to stop before unplugging.";
  }

  function secondsLeft(armedAt, now, limit) {
    return Math.max(0, Math.ceil(((limit === undefined ? CONFIRM_S : limit) * 1000 - (now - armedAt)) / 1000));
  }

  /* After a reboot: is Sandbells back?  startBoot: the boot id Sandbells
   * gave with its answer ("" if unknown); sawFail: some poll has already
   * failed since (so the machine really went away); res: the latest ping
   * reply, or null when the poll failed.  -> "wait" | "back". */
  function pollDecision(startBoot, sawFail, res) {
    if (!res || !res.ok) return "wait";
    if (startBoot && res.boot_id) return res.boot_id !== startBoot ? "back" : "wait";
    return sawFail ? "back" : "wait";
  }

  function errorText(d, status) {
    return "Not done: " + ((d && d.error) || ("HTTP " + status));
  }

  function start() {
    var box = document.getElementById("power");
    if (!box || box.getAttribute("data-started")) return;
    box.setAttribute("data-started", "1");
    var machine = box.getAttribute("data-machine");
    var idle = box.querySelector(".power-idle");
    var confirmBox = box.querySelector(".power-confirm");
    var yes = box.querySelector(".power-yes");
    var no = box.querySelector(".power-no");
    var note = box.querySelector(".power-note");
    var msg = box.querySelector(".power-msg");
    var armed = null, armedAt = 0, tick = null, busy = false;

    function csrf() {
      var input = box.querySelector("input[name=csrfmiddlewaretoken]");
      if (input) return input.value;
      var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    }
    function stopTick() { if (tick) { clearInterval(tick); tick = null; } }
    function show(text) { msg.textContent = text || ""; }

    function disarm() {
      stopTick();
      armed = null;
      confirmBox.hidden = true;
      idle.hidden = false;
    }
    function arm(action) {
      if (busy) return;
      armed = action;
      armedAt = Date.now();
      var info = confirmInfo(action, machine);
      yes.textContent = info.yes;
      show("");
      idle.hidden = true;
      confirmBox.hidden = false;
      function paint() {
        var left = secondsLeft(armedAt, Date.now());
        note.textContent = info.note + " Cancels in " + left + " s.";
        if (left <= 0) disarm();
      }
      paint();
      stopTick();
      tick = setInterval(paint, 250);
    }

    function send(action) {
      busy = true;
      var url = box.getAttribute("data-" + action + "-url");
      disarm();
      idle.hidden = true;
      show("Sending…");
      var ctl = window.AbortController ? new AbortController() : null;
      var guard = ctl ? setTimeout(function () { ctl.abort(); }, SEND_TIMEOUT_MS) : null;
      fetch(url, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() },
                   signal: ctl ? ctl.signal : undefined })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (d) { return { d: d, status: r.status }; });
        })
        .then(function (x) {
          if (guard) clearTimeout(guard);
          if (x.d && x.d.ok) accepted(action, x.d);
          else { busy = false; idle.hidden = false; show(errorText(x.d, x.status)); }
        })
        .catch(function () {
          if (guard) clearTimeout(guard);
          busy = false; idle.hidden = false;
          show("Not done: no reply from Sandbells");
        });
    }

    function accepted(action, d) {
      show(acceptedText(action, machine));
      if (action !== "reboot") return;       // shut down: nothing to wait for
      var startBoot = d.boot_id || "", sawFail = false;
      (function poll() {
        var ctl = window.AbortController ? new AbortController() : null;
        var guard = ctl ? setTimeout(function () { ctl.abort(); }, POLL_TIMEOUT_MS) : null;
        fetch(box.getAttribute("data-ping-url"), { cache: "no-store", signal: ctl ? ctl.signal : undefined })
          .then(function (r) { return r.ok ? r.json() : null; })
          .catch(function () { return null; })
          .then(function (res) {
            if (guard) clearTimeout(guard);
            if (!res) sawFail = true;
            if (pollDecision(startBoot, sawFail, res) === "back") { window.location.reload(); return; }
            setTimeout(poll, POLL_MS);
          });
      })();
    }

    Array.prototype.forEach.call(box.querySelectorAll(".power-btn"), function (b) {
      b.addEventListener("click", function () { arm(b.getAttribute("data-action")); });
    });
    yes.addEventListener("click", function () { if (armed) send(armed); });
    no.addEventListener("click", disarm);
  }

  return { confirmInfo: confirmInfo, acceptedText: acceptedText, secondsLeft: secondsLeft,
           pollDecision: pollDecision, errorText: errorText, start: start,
           CONFIRM_S: CONFIRM_S };
});
