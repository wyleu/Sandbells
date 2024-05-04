(function(){

	var currentTime = { hour : 0, minute : 0, second : 0 };

	var keyPressed = {};

	var clockPosition = { x : 0, y : 0, scale : 1.000000};

	var tick;
	var tock;

	var playtick = false;

	console.log("Hello Sandbells");

	createHourLabels();

	drawMarks();

	setCurrentTime();

	updateHoursMinutesSeconds();

	makeTick();
	makeTock();

	d3.select("body")
		.on("keydown", function(){
		keyCode = d3.event.keyCode;
		console.log("A key PRESSED:-"+d3.event.key+"-"+d3.event.keyCode+"-Ctrl-"+d3.event.ctrlKey+"-Shift-"+d3.event.shiftKey);
			
		keyPressed[keyCode] = true;      //Mute toggle clock noise.

		if (keyCode == 77){    // m key
			playtick = !playtick;
			}
					if (keyCode == 188){
			if ("16" in keyPressed && "17" in keyPressed){
						//console.log("188 & 16 SHIFT & 17 CONTROL recieved");
						updatedecYpos();
			}		      
					
			else if ("16" in keyPressed){
						//console.log("188 & 16 SHIFT recieved");
						updatedecXpos();
			}
			else if ("17" in keyPressed){
				//console.log("188 & 17 CONTROL recieved");
						updatedecYpos();
			}
			else {
				//console.log("188 recieved");
						updatedecScale();
			}
				}
		if (keyCode == 190){
			if ("16" in keyPressed && "17" in keyPressed){
						//console.log("190 & 16 SHIFT & 17 CONTROL recieved");
						updateincYpos();
			}		      
					
			else if ("16" in keyPressed){
						//console.log("190 & 16 SHIFT recieved");
						updateincXpos();
			}
			else if ("17" in keyPressed){
				//console.log("190 & 17 CONTROL recieved");
						updateincYpos();
			}
			else {
				//console.log("190 recieved");
						updateincScale();
			}
			}
			// console.dir(keyPressed);
		})
		.on('keyup', function(){
			keyup = d3.event.keyCode;
			delete keyPressed[keyup];
		//console.dir(keyPressed);
			//console.log("A key released:-"+d3.event.key+"-"+d3.event.keyCode+"-Ctrl-"+d3.event.ctrlKey+"-Shift-"+d3.event.shiftKey);
		})
		.on('resize', function(){
			const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
			const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;
			console.log(width, height);
		});


	setInterval(function(){
		updateHoursMinutesSeconds();
		if (playtick ==true){
			playTick();
		}
		
		//playTick();
                //console.log(clockPosition);
                // updateMovement();
	}, 1000);

	function updateHoursMinutesSeconds(){
		setCurrentTime();
		updateSeconds();
		updateMinutes();
		updateHours();
	}

	function degreesToRadians(degrees)
	{
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

	function updateHours(){
		var degree = currentTime.hour * 30 + 30 / 60 * currentTime.minute;
		d3.select(".hour").transition().attr("transform", "rotate("+degree+" 175 175)");
	}

	function updateMinutes(){
		var degree = currentTime.minute * 6;
		d3.select(".minute").transition().attr("transform", "rotate("+degree+" 175 175)");
	}

	function updateSeconds(){
		var degree = currentTime.second * 6;
		d3.select(".second").transition().attr("transform", "rotate("+degree+" 175 175)");
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

	function setCurrentTime(){
		currentTime.hour = new Date().getHours();
		currentTime.minute = new Date().getMinutes();
		currentTime.second = new Date().getSeconds();
	}
	function updateincScale(){
		clockPosition.scale = clockPosition.scale * 1.01;
		object = d3.select(".clockSvg")
	   .attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });

 	}
	function updateincXpos(){
			clockPosition.x = clockPosition.x + 1.0;
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });         
	}
	function updateincYpos(){
			clockPosition.y = clockPosition.y + 1.0;
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });         

	}

	function updatedecScale(){
			clockPosition.scale = clockPosition.scale * .99;
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });         

	}
	function updatedecXpos(){
			clockPosition.x = clockPosition.x - 1.0; 
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });         

	}
	function updatedecYpos(){
			clockPosition.y = clockPosition.y - 1.0;
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+clockPosition.x+" "+clockPosition.y+") scale("+clockPosition.scale+" "+ clockPosition.scale+")"  });
	}
	function makeTick(){
		tick = document.createElement("AUDIO");
		if (tick.canPlayType("audio/ogg")) {
			tick.setAttribute("src","/static/bells/tick.ogg");
		}
 		//tick.setAttribute("controls", "controls");
		document.body.appendChild(tick);
	}	
	function playTick(){
	tick.play();
	}
	function makeTock(){
		tock = document.createElement("AUDIO");
		if (tock.canPlayType("audio/ogg")) {
	tock.setAttribute("src","/static/bells/tock.ogg");
	}
	//tock.setAttribute("controls", "controls");
	document.body.appendChild(tock);

	}


	function updateMovement(){
			var degree = currentTime.second * 6;
			object = d3.select(".clockSvg")
		.attr("transform", function(d) { return "translate("+degree+"  160)"  });
	}

})();