(function () {
  function sizeAndDraw() {
    var el = document.getElementById("bell-circle");
    if (!el || !window.BellBand) return;
    BellBand.draw(el, {
      width: 250,
      height: 250,
      bells: [1, 2, 3, 4, 5, 6, 7, 8]
    });
  }
  window.addEventListener("load", function () {
    setTimeout(sizeAndDraw, 150);
  });
})();
