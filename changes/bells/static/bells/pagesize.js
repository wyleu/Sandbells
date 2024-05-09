( function(){

    const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    console.log(width, height);

function processChangePress(bellstring){
        d3.select("#ishow")
        .attr('src', bellstring);
    };

function processNumberPress(num){
    console.log('Number Press', num);

    d3.selectAll(".changenumberbutton")
    .filter(function(d){
        console.log('First Number Filter ',d,this.getAttribute("num"), num);
        return this.getAttribute("num") == num
    })
    .attr('disabled', "disabled");

    d3.selectAll(".changenumberbutton")
    .filter(function(d){
        console.log('Second Number Filter ',d,this.getAttribute("num"), num);
        return this.getAttribute("num") != num
    })
    .attr('disabled', null);

    d3.selectAll('.change_displayed')
    .filter(function(d){
         console.log('First Filter ',d,this.getAttribute("number"), num);
         return this.getAttribute("number") == num
         }
        )
    .attr("hidden",null);

    d3.selectAll('.change_displayed')
    .filter(function(d){
         console.log('Second Filter ',d,this.getAttribute("number"), num);
         return this.getAttribute("number") != num 
         }
        )
    .attr("hidden", 'hidden');


    d3.selectAll(".frontpage_td_select_first_char")
    .attr("class", "frontpage_td_select_other_char shadow");


    d3.selectAll(".frontpage_td_select_other_char")
    .filter(function(d){
        console.log('Light it up Filter ',d,this.getAttribute("number"), num);
        return this.getAttribute("number") == num 
        }
       )
    .attr("class", "frontpage_td_select_first_char shadow");
};



function establishChangePress(){
    console.log('EstablishChangePress');
    d3.selectAll('.changenamebutton')
    .on("click", function(d, i ,e){
        console.log(this.getAttribute('id'), d, i, e);
        processChangePress(this.getAttribute('id'));
        }
    );
    d3.selectAll(".changenumberbutton")
    .on("click", function(d, i, e){
        console.log('Number Change:-', this.getAttribute('id'), d, i, e);
        processNumberPress(this.getAttribute('number'));
        }
    );
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