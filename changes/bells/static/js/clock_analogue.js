// Robust Clock for Midori Kiosk
(function() {
    function updateClock() {
        const now = new Date();
        const h = now.getHours() % 12;
        const m = now.getMinutes();
        const s = now.getSeconds();

        d3.select(".hour").attr("transform", `rotate(${h*30 + m*0.5} 175 175)`);
        d3.select(".minute").attr("transform", `rotate(${m*6} 175 175)`);
        d3.select(".second").attr("transform", `rotate(${s*6} 175 175)`);
    }

    // Run aggressively
    function startClock() {
        updateClock();
        setInterval(updateClock, 1000);
    }

    window.addEventListener('load', startClock);
    document.addEventListener('DOMContentLoaded', startClock);

    // Extra attempts for slow loading
    setTimeout(startClock, 500);
    setTimeout(startClock, 1200);
})();