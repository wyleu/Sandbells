// Robust Clock for LuaKit
// File: clock_analogue.js
(function() {
    function degreesToRadians(degrees) {
        return degrees * (Math.PI / 180);
    }

    function getCoordsByDegree(theta) {
        const radius = 130;
        return {
            x: radius * Math.sin(degreesToRadians(theta)),
            y: radius * Math.cos(degreesToRadians(theta))
        };
    }

    function createHourLabels() {
        const arr = [6,5,4,3,2,1,12,11,10,9,8,7];
        const container = d3.select(".numbers");
        if (container.selectAll("text").size() > 0) return;

        container.selectAll("text").data(arr).enter().append("text")
            .attr("x", (d,i) => getCoordsByDegree(i*30).x + 175 - 6)
            .attr("y", (d,i) => getCoordsByDegree(i*30).y + 175 + 5)
            .text(d => d);
    }

    function drawMarks() {
        const container = d3.select(".marks");
        if (container.selectAll("text").size() > 0) return;

        const marks = [];
        for (let i = 1; i <= 60; i++) {
            if (i % 5 !== 0) marks.push(i);
        }

        container.selectAll("text").data(marks).enter().append("text")
            .attr("x", 175)
            .attr("y", 175)
            .attr("dy", "-128")
            .attr("transform", d => `rotate(${d*6} 175 175)`)
            .text("|");
    }

    // Element caches

    let digitalTimeEl = null;
    let digitalDateEl = null;
    let memoryValueEl = null;
    
    // Peak memory tracking
    let peakMemory = 0;

    // Memory display with peak
    function updateMemoryDisplay() {
        if (!memoryValueEl) return;

        let used = 0;
        let total = 0;
        let memText = "N/A";

        if (performance && performance.memory) {
            used = performance.memory.usedJSHeapSize / 1024 / 1024;
            total = performance.memory.totalJSHeapSize / 1024 / 1024;
            
            // Update peak
            if (used > peakMemory) {
                peakMemory = used;
            }

            memText = `${used.toFixed(1)} / ${total.toFixed(1)} MB (Pk: ${peakMemory.toFixed(1)})`;
        } else {
            memText = "LuaKit (monitor via Lua)";
        }

        memoryValueEl.textContent = memText;
    }

    function updateDate() {
        const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        const days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
        const d = new Date();
       
        const str = `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
        if (digitalDateEl) digitalDateEl.textContent = str;
    }

    function updateDigitalClock() {
        const now = new Date();
        const str = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
        if (digitalTimeEl) digitalTimeEl.textContent = str;
    }

    function updateClock() {
        const now = new Date();
        const h = now.getHours() % 12;
        const m = now.getMinutes();
        const s = now.getSeconds();

        // Update clock hands
        d3.select(".hour").attr("transform", `rotate(${h*30 + m*0.5} 175 175)`);
        d3.select(".minute").attr("transform", `rotate(${m*6} 175 175)`);
        d3.select(".second").attr("transform", `rotate(${s*6} 175 175)`);

        // Update displays
        updateDate();
        updateDigitalClock();
        updateMemoryDisplay();
    }

    function init() {
        createHourLabels();
        drawMarks();

        // Cache DOM elements
        digitalTimeEl = document.getElementById('digital_time');
        digitalDateEl = document.getElementById('digital_date');
        memoryValueEl = document.getElementById('memory_value');

        updateClock();                    // Initial update
        setInterval(updateClock, 1000);   // Update every second
    }

    // LuaKit compatible initialization
    window.addEventListener('load', init);
    document.addEventListener('DOMContentLoaded', init);
    
    // Extra safety
    setTimeout(init, 300);
    setTimeout(init, 1000);

})();