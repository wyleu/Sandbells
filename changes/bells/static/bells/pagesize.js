( function(){

    const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    console.log(width, height);

function establishChangePress(){
    console.log('EstablishChangePress');
    d3.selectAll('.changenamebutton')
    .on("click", function(d, i ,e){

        console.log(this.getAttribute('id'), d, i, e);
        }
    );
};


function processChangePress(bellstring){
    d3.select("#ishow")
    .attr('src', bellstring);
};

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

establishChangePress();
processWindowSize();
window.onresize = processWindowSize
})();