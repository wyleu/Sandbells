( function(){

    const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    console.log(width, height);





function reportWindowSize() {

    var width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    var height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    d3.select('#height_value')
    .text(height);
    d3.select('#width_value')
    .text(width);
      };

reportWindowSize();
window.onresize = reportWindowSize
})();