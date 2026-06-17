(function() {
    function processChangePress(bellstring) {
        const ishow = d3.select("#ishow");
        if (ishow.node()) {
            ishow.attr('src', bellstring);
        }
    }

    function processNumberPress(num) {
        d3.selectAll(".changenumberbutton")
            .filter(function() {
                return this.getAttribute("num") == num;
            })
            .attr('disabled', "disabled");

        d3.selectAll(".changenumberbutton")
            .filter(function() {
                return this.getAttribute("num") != num;
            })
            .attr('disabled', null);

        d3.selectAll('.change_displayed')
            .filter(function() {
                return this.getAttribute("number") == num;
            })
            .attr("hidden", null);

        d3.selectAll('.change_displayed')
            .filter(function() {
                return this.getAttribute("number") != num;
            })
            .attr("hidden", 'hidden');

        // Update active class on front page
        d3.selectAll(".frontpage_td_select_first_char")
            .attr("class", "frontpage_td_select_other_char shadow");

        d3.selectAll(".frontpage_td_select_other_char")
            .filter(function() {
                return this.getAttribute("number") == num;
            })
            .attr("class", "frontpage_td_select_first_char shadow");
    }

    function establishChangePress() {
        console.log('EstablishChangePress');

        d3.selectAll('.changenamebutton')
            .on("click", function() {
                processChangePress(this.getAttribute('id'));
            });

        d3.selectAll(".changenumberbutton")
            .on("click", function() {
                processNumberPress(this.getAttribute('number'));
            });
    }

    function processWindowSize() {
        const width = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
        const height = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;

        console.log(width, height);

        d3.select('#height_value').text(height);
        d3.select('#width_value').text(width);

        const ishow = d3.select('#ishow');
        if (ishow.node()) {
            ishow.attr('height', height - 20)
                 .attr('width', width - 575);
        }

        try {
            d3.select('#window_height_value').text(ishow.attr("height"));
            d3.select('#window_width_value').text(ishow.attr("width"));
        } catch (err) {
            console.log("BANG! " + err.message);
        }
    }

    // Run everything after DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        establishChangePress();
        processWindowSize();
    });

    // Handle resize
    window.onresize = processWindowSize;

})();