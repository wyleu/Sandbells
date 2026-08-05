( function(){

    const width  = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
    const height = window.innerHeight|| document.documentElement.clientHeight|| document.body.clientHeight;

    console.log(width, height);

function processChangePress(bellstring){
        d3.select("#ishow")
        .attr('src', bellstring);
    };


function processNumberPress(num) {
    num = String(num);

    // Never disable number buttons — they are always resets
    d3.selectAll(".changenumberbutton")
        .attr("disabled", null);

    // Show only methods for this bell count
    d3.selectAll(".change_displayed")
        .attr("hidden", function () {
            return String(this.getAttribute("number")) === num ? null : "hidden";
        });

    // Selected digit red; others black (method names untouched)
    d3.selectAll(".changenumberbutton span")
        .attr("class", "frontpage_td_select_other_char shadow");

    d3.selectAll(".changenumberbutton")
        .filter(function () {
            return String(this.getAttribute("number")) === num;
        })
        .select("span")
        .attr("class", "frontpage_td_select_first_char shadow");

    // Reset centre: Rounds → random (and second leg when random supports it)
    processChangePress("/random/" + num + "/rounds/");
}





function establishChangePress(){
    console.log('EstablishChangePress');
    d3.selectAll('.changenamebutton')
    .on("click", function(d, i ,e){
        //console.log(this.getAttribute('id'), d, i, e);
        processChangePress(this.getAttribute('id'));
        });
    d3.selectAll(".changenumberbutton")
    .on("click", function(d, i, e){
        //console.log('Number Change:-', this.getAttribute('id'), d, i, e);
        processNumberPress(this.getAttribute('number'));
        });
}



function processWindowSize() {
  var width  = window.innerWidth  || document.documentElement.clientWidth  || document.body.clientWidth;
  var height = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;

  d3.select('#height_value').text(height);
  d3.select('#width_value').text(width);

  // --- measured columns ---
  var clockEl = document.getElementById('clock');
  var menuEl  = document.querySelector('.frontpage_table_select');
  var iframe  = document.getElementById('ishow');

  var clockW = clockEl ? (clockEl.getBoundingClientRect().width || 250) : 250;
  var menuW  = menuEl  ? (menuEl.getBoundingClientRect().width  || 280) : 280;
  if (menuW > 260) menuW = 260;   // don't over-reserve for the menu

  var gap = 12;           // flex gap / margins between the three columns
  var safety = 4;        // small fudge so we never overflow

  var iframeW = Math.floor(width - clockW - menuW - (gap * 2) - safety);
  if (iframeW < 600) iframeW = 600;   // hard floor so tables never collapse

  var iframeH = height - 20;

  d3.select('#ishow')
    .attr('height', iframeH)
    .attr('width', iframeW);

  // expose numbers for status (optional, system_info already reads attrs)
  try {
    d3.select('#window_height_value').text(iframeH);
    d3.select('#window_width_value').text(iframeW);
  } catch (err) {
    console.log('BANG! ' + err.message);
  }

  // tell the iframe to scale its contents if needed (see step 2)
  if (iframe && iframe.contentWindow) {
    try {
      iframe.contentWindow.postMessage({
        type: 'sandbells-scale',
        iframeW: iframeW,
        iframeH: iframeH
      }, '*');
    } catch (e) { /* ignore cross-origin noise */ }
  }
}

establishChangePress();
processWindowSize();
window.onresize = processWindowSize

})();
