// Robust Clock for Midori Kiosk - Optimized
(function() {
    // Helper functions
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

    // Create static hour labels (only once)
    function createHourLabels() {
        const arr = [6, 5, 4, 3, 2, 1, 12, 11, 10, 9, 8, 7];
        const numbersGroup = d3.select(".numbers");
        
        if (numbersGroup.selectAll("text").size() > 0) return;

        numbersGroup.selectAll("text")
            .data(arr)
            .enter()
            .append("text")
            .attr("x", function(d, i) {
                return getCoordsByDegree(i * 30).x + 175 - 6;
            })
            .attr("y", function(d, i) {
                return getCoordsByDegree(i * 30).y + 175 + 5;
            })
            .text(function(d) { return d; });
    }

    // Create static minute marks (only once)
    function drawMarks() {
        const marksGroup = d3.select(".marks");
        if (marksGroup.selectAll("text").size() > 0) return;

        const clockMarks = [];
        for (let i = 1; i <= 60; i++) {
            if (i % 5 !== 0) clockMarks.push(i);
        }

        marksGroup.selectAll("text")
            .data(clockMarks)
            .enter()
            .append("text")
            .attr("x", "175")
            .attr("y", "175")
            .attr("dy", "-128")
            .attr("transform", function(d) {
                return "rotate(" + (d * 6) + " 175 175)";
            })
            .text("|");
    }

    // Cache DOM elements
    let digitalTimeEl = null;
    let digitalDateEl = null;

    function updateDate() {
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        
        const d = new Date();
        const dateStr = days[d.getDay()] + " " + 
                       d.getDate() + " " + 
                       months[d.getMonth()] + " " + 
                       d.getFullYear();

        if (digitalDateEl) digitalDateEl.textContent = dateStr;
    }

    function updateDigitalClock() {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ":" +
                        now.getMinutes().toString().padStart(2, '0') + ":" +
                        now.getSeconds().toString().padStart(2, '0');

        if (digitalTimeEl) digitalTimeEl.textContent = timeStr;
    }

    function updateClock() {
        const now = new Date();
        const h = now.getHours() % 12;
        const m = now.getMinutes();
        const s = now.getSeconds();

        // Update analog hands
        d3.select(".hour").attr("transform", `rotate(${h * 30 + m * 0.5} 175 175)`);
        d3.select(".minute").attr("transform", `rotate(${m * 6} 175 175)`);
        d3.select(".second").attr("transform", `rotate(${s * 6} 175 175)`);

        // Update digital displays
        updateDate();
        updateDigitalClock();
    }

    // Initialize everything
    function initClock() {
        createHourLabels();
        drawMarks();

        // Cache digital elements
        digitalTimeEl = document.getElementById('digital_time');
        digitalDateEl = document.getElementById('digital_date');

        // Initial update (both analog + digital)
        updateClock();
        
        // Update every second
        setInterval(updateClock, 1000);
    }

    // Run on load events
    window.addEventListener('load', initClock);
    document.addEventListener('DOMContentLoaded', initClock);

})();