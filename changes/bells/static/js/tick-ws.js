// tick-ws.js  – or inline in your template
const TICK_WS_URL = "ws://sandsense-tower.local/ws";   // or the numeric IP

// needs js/reconnect_delay.js loaded first (shared 1, 2, 4, 8, 15 s jittered delay)
let tickSocket = null;
const tickDelay = window.ReconnectDelay.create();

function connectTickSource() {
    if (tickSocket) {
        try { tickSocket.close(); } catch (e) {}
    }

    tickSocket = new WebSocket(TICK_WS_URL);

    tickSocket.onopen = () => {
        console.log("Escapement tick WebSocket connected");
        tickDelay.opened();
    };

    tickSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            // data.tick     → sequential number (never resets)
            // data.virtual  → true when PLL filled a miss
            // data.t        → Pico monotonic time
            // data.vel      → current MIDI velocity

            // === YOUR TRACKING / ANIMATION CODE HERE ===
            // e.g. advance a visual hand, flash a bell head, update phase offset…
            onEscapementTick(data);
        } catch (e) {
            console.warn("Bad tick payload", event.data);
        }
    };

    tickSocket.onclose = () => {
        const wait = tickDelay.closed();
        console.log("Tick WS closed – reconnecting in", wait, "ms");
        setTimeout(connectTickSource, wait);
    };

    tickSocket.onerror = (err) => {
        console.error("Tick WS error", err);
        tickSocket.close();
    };
}

// Call once the page is ready
document.addEventListener("DOMContentLoaded", connectTickSource);

// Stub – replace with your real handler
function onEscapementTick(data) {
    console.log("Tick", data.tick, data.virtual ? "(virtual)" : "(real)");
    // e.g. document.getElementById("tick-counter").textContent = data.tick;
}