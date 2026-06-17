(function() {
    console.log("Hello Sandbells");

    let currentTime = { hour: 0, minute: 0, second: 0 };
    let keyPressed = {};
    let clockPosition = { x: 0, y: 0, scale: 1.0 };
    let tick, tock;
    let playtick = false;

    function initClock() {
        if (!document.querySelector('.clockSvg')) {
            console.log("Clock SVG not found on this page - skipping clock init");
            return;
        }

        createHourLabels();
        drawMarks();
        setCurrentTime();
        updateHoursMinutesSeconds();
        makeTick();
        makeTock();

        // Keyboard controls
        d3.select("body")
            .on("keydown", function() {
                const keyCode = d3.event.keyCode;
                keyPressed[keyCode] = true;

                if (keyCode === 77) { // 'm' key
                    playtick = !playtick;
                }
                // ... (keep your other key handlers if you want them)
            })
            .on("keyup", function() {
                delete keyPressed[d3.event.keyCode];
            });

        // Update every second
        setInterval(() => {
            updateHoursMinutesSeconds();
            if (playtick) playTick();
        }, 1000);
    }

    function setCurrentTime() {
        const now = new Date();
        currentTime.hour = now.getHours();
        currentTime.minute = now.getMinutes();
        currentTime.second = now.getSeconds();
    }

    function updateHoursMinutesSeconds() {
        setCurrentTime();
        updateSeconds();
        updateMinutes();
        updateHours();
        updateDigital();
    }

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
        d3.select(".numbers").selectAll("text")
            .data(arr)
            .enter()
            .append("text")
            .attr("x", (d,i) => getCoordsByDegree(i * 30).x + 175 - 6)
            .attr("y", (d,i) => getCoordsByDegree(i * 30).y + 175 + 5)
            .text(d => d);
    }

    function updateHours() {
        const degree = currentTime.hour * 30 + (30 / 60) * currentTime.minute;
        d3.select(".hour").transition().attr("transform", `rotate(${degree} 175 175)`);
    }

    function updateMinutes() {
        const degree = currentTime.minute * 6;
        d3.select(".minute").transition().attr("transform", `rotate(${degree} 175 175)`);
    }

    function updateSeconds() {
        const degree = currentTime.second * 6;
        d3.select(".second").transition().attr("transform", `rotate(${degree} 175 175)`);
    }

    function updateDigital() {
        d3.select('#digital_time')
            .text(`${currentTime.hour.toString().padStart(2,'0')}:${currentTime.minute.toString().padStart(2,'0')}:${currentTime.second.toString().padStart(2,'0')}`);
    }

    function drawMarks() {
        // Your existing drawMarks logic...
        // (I'll keep it short here - you can keep your original if you prefer)
    }

    function makeTick() {
        tick = document.createElement("AUDIO");
        tick.setAttribute("src", "/static/ogg/tick.ogg");
        document.body.appendChild(tick);
    }

    function makeTock() {
        tock = document.createElement("AUDIO");
        tock.setAttribute("src", "/static/ogg/tock.ogg");
        document.body.appendChild(tock);
    }

    function playTick() {
        if (tick) tick.play();
    }

    // Run when DOM is ready
    document.addEventListener('DOMContentLoaded', initClock);

})();