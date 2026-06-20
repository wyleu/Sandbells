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


    createHourLabels();
    drawMarks();

    window.addEventListener('load', startClock);
    document.addEventListener('DOMContentLoaded', startClock);

    // Extra attempts for slow loading
    setTimeout(startClock, 500);
    setTimeout(startClock, 1200);
})();