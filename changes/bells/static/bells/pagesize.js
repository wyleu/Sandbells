( function(){

    const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    console.log(width, height);





function processWindowSize() {

    var width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    var height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    d3.select('#height_value')
    .text(height);
    d3.select('#width_value')
    .text(width);
    d3.select("#posinfo")
    .attr('x', width + 200)
    .attr('y', height + 2000);
      };


processWindowSize();
window.onresize = processWindowSize
})();