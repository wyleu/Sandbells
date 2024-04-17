

var svg = d3.select("body").append("svg")
    .attr("class", 'fullscreen')
    .attr("viewBox", "100 -100 1000 500")
    .attr("preserveAspectRatio", "xMidYMid meet")
    .attr("display", "block")
    .attr("refX", 25)
    .attr("refY", 0)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto");
    
svg .append("path")
    .attr("d", "M0,-5L10,0L0,5 L10,0 L0, -5")
    .style("stroke", "#000")
    .style("opacity", "1");

svgElement = document.getElementsByTagName("svg")[0];

svgElement.style.border = "1px solid red";
svgElement.style.position = "relative";
svgElement.style.top = "50%";
svgElement.style.left = "50%";
svgElement.style.transform = "translate(-50%, -50%)";

svg. append("text")
    .text("Hello There !!")
    .attr("font-size","90")
    .attr("text-anchor","middle")
    .attr("dominant-baseline","middle")
    .attr("font-family","monospace")
    .attr("font-weight","bold")
    .attr("x","400")
    .attr("y","400")
    .attr("transform","rotate(-45)")
    .attr("transform-origin","400 400")
    .attr("fill","none")
    .attr("stroke","#FF574D")
    .attr("stroke-width","4");
