// =============================================
// Modern Sandbells Analogue + Digital Clock
// =============================================

(function() {
    'use strict';

    console.log("✅ Modern Clock Analogue Loaded");

    let tickAudio, tockAudio;
    let playTickSound = false;
    let clockInterval = null;

    // Initialize everything when DOM is ready
    document.addEventListener('DOMContentLoaded', initClock);

    function initClock() {
        // Skip if no clock on this page
        if (!document.querySelector('.clockSvg')) {
            console.log("No clock SVG on this page");
            return;
        }

        createHourLabels();
        drawMarks();
        makeTickTock();

        // Keyboard controls
        setupKeyboardControls();

        // Start the clock
        startClock();
    }

    function startClock() {
        if (clockInterval) clearInterval(clockInterval);
        
        clockInterval = setInterval(() => {
            updateClock();
        }, 1000);

        // Initial update
        updateClock();
    }

    function updateClock() {
        const now = new Date();
        
        const hours = now.getHours();
        const minutes = now.getMinutes();
        const seconds = now.getSeconds();

        updateAnalogueHands(hours, minutes, seconds);
        updateDigital(hours, minutes, seconds);

        if (playTickSound) {
            playTick();
        }
    }

    function updateAnalogueHands(hours, minutes, seconds) {
        // Hour hand
        const hourDegree = (hours % 12) * 30 + (minutes * 0.5);
        d3.select(".hour").transition().duration(500)
            .attr("transform", `rotate(${hourDegree} 175 175)`);

        // Minute hand
        const minuteDegree = minutes * 6;
        d3.select(".minute").transition().duration(500)
            .attr("transform", `rotate(${minuteDegree} 175 175)`);

        // Second hand
        const secondDegree = seconds * 6;
        d3.select(".second").transition().duration(200)
            .attr("transform", `rotate(${secondDegree} 175 175)`);
    }

    function updateDigital(hours, minutes, seconds) {
        const timeStr = 
            hours.toString().padStart(2, '0') + ":" +
            minutes.toString().padStart(2, '0') + ":" +
            seconds.toString().padStart(2, '0');

        const digitalEl = d3.select('#digital_time');
        if (digitalEl.node()) {
            digitalEl.text(timeStr);
        } else {
            const fallback = document.getElementById('digital_time');
            if (fallback) fallback.textContent = timeStr;
        }
    }

    function createHourLabels() {
        const arr = [6,5,4,3,2,1,12,11,10,9,8,7];
        d3.select(".numbers").selectAll("text").data(arr).enter().append("text")
            .attr("x", (d, i) => getCoordsByDegree(i * 30).x + 175 - 6)
            .attr("y", (d, i) => getCoordsByDegree(i * 30).y + 175 + 5)
            .text(d => d);
    }

    function drawMarks() {
        const marks = [];
        for (let i = 1; i <= 60; i++) {
            if (i % 5 !== 0) marks.push(i);
        }
        d3.select(".marks").selectAll("text").data(marks).enter().append("text")
            .attr("x", "175")
            .attr("y", "175")
            .attr("dy", "-128")
            .attr("transform", d => `rotate(${d * 6} 175 175)`)
            .text("|");
    }

    function getCoordsByDegree(theta) {
        const radius = 130;
        return {
            x: radius * Math.sin(theta * Math.PI / 180),
            y: radius * Math.cos(theta * Math.PI / 180)
        };
    }

    function makeTickTock() {
        tickAudio = new Audio("/static/ogg/tick.ogg");
        tockAudio = new Audio("/static/ogg/tock.ogg");
    }

    function playTick() {
        if (tickAudio) tickAudio.play().catch(() => {});
    }

    function setupKeyboardControls() {
        const keyPressed = {};

        d3.select("body")
            .on("keydown", function() {
                const keyCode = d3.event.keyCode;
                keyPressed[keyCode] = true;

                if (keyCode === 77) { // 'm' key
                    playTickSound = !playTickSound;
                    console.log("Tick sound:", playTickSound ? "ON" : "OFF");
                }
            })
            .on("keyup", function() {
                delete keyPressed[d3.event.keyCode];
            });
    }

    // Expose for debugging if needed
    window.sandbellsClock = { updateClock, startClock };

})();