function onLoad(){
    console.log("On Load of iframes");
};

function onError(){
    console.log("ERROR!! " + this.src);
};
function onPress(id, bellstring){

    console.log("PRESSED!!" + bellstring);
    d3.select("#ishow")
       .attr('src', bellstring);
}

function onPressButton(id){
    id.innerHTML = "Dont press me again!";
    onPress(id, "/display/6/queens/")
    
}