// Robust Clock for Midori Kiosk
(function() {
    function degreesToRadians(degrees){
	  return degrees * (Math.PI/180);
    }

    function getCoordsByDegree(theta){
		var radius = 130;
		return { x : radius * Math.sin(degreesToRadians(theta)), y : radius * Math.cos(degreesToRadians(theta)) }
    }

    function createHourLabels(){
	var arr = [6,5,4,3,2,1,12,11,10,9,8,7];

        d3.select(".numbers").selectAll("text").data(arr).enter().append("text")
         	.attr("x", function(d,i) { return getCoordsByDegree(i * 30).x + 175 - 6 ; })
         	.attr("y", function(d,i) { return getCoordsByDegree(i * 30).y + 175 + 5; })
         	.text(function(d) { return d; });
    }

    function drawMarks(){
	var clockMarks = [];

	for (var i = 1; i <= 61; i++) {
	   i % 5 != 0 ? clockMarks.push(i) : "";
	}

	d3.select(".marks").selectAll("text").data(clockMarks).enter()
		.append("text")
		.attr("x", "175")
		.attr("y", "175")
		.attr("dy", "-128")
		.attr("transform", function(d) { var degree = d * 6; return "rotate("+degree+" 175 175)" })
		.text("|");
    }

    function updateDate()  {

	var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
	var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

	var d = new Date();
	var day = days[d.getDay()];
	var date = d.getDate();
	var month = months[d.getMonth()];
	var year = d.getFullYear();

	const dateStr = day + " " + date + " " + month + " " + year; 

	const el = document.getElementById('digital_date');
	if (el) el.textContent = dateStr;

    }

    function updateClock() {
        const now = new Date();
        const h = now.getHours() % 12;
        const m = now.getMinutes();
        const s = now.getSeconds();

        d3.select(".hour").attr("transform", `rotate(${h*30 + m*0.5} 175 175)`);
        d3.select(".minute").attr("transform", `rotate(${m*6} 175 175)`);
        d3.select(".second").attr("transform", `rotate(${s*6} 175 175)`);


        createHourLabels();
        drawMarks();
	updateDate();

    }
    function updateDigitalClock() {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2,'0') + ":" +
                        now.getMinutes().toString().padStart(2,'0') + ":" +
                        now.getSeconds().toString().padStart(2,'0');

        const el = document.getElementById('digital_time');
        if (el) el.textContent = timeStr;
        }
        // setInterval(updateDigitalClock, 1000);
        // updateDigitalClock();

    // Run aggressively
    function startClock() {
        updateClock();
        setInterval(updateClock, 1000);
    }

    createHourLabels();
    drawMarks();

    window.addEventListener('load', startClock);
    document.addEventListener('DOMContentLoaded', startClock);

    // Extra attempts for slow loading
    setTimeout(startClock, 500);
    setTimeout(startClock, 1200);
})();