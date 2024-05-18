
const bells = new Howl(
  {
    "src": ["/static/ogg/Rounds_on_8_10_Bpm.ogg"],
    "sprite" : {
      // offset, duration
        bell1: [693, 1507],
        bell2: [2225, 1475],
        bell3: [3700, 1500],
        bell4: [5200, 1500],
        bell5: [6700, 1500],
        bell6: [8200, 1500],
        bell7: [9680, 1500],
        bell8: [11180, 1500]
      }
  }
);



const drumkit = document.querySelector('.drumkit');
// const change = document.querySelector('.frontpage_table_display');


 function playDrum(event){
   if (event.target.classList.contains('pad')){
     event.preventDefault();     /* prevent double click  */
     let soundToPlay = event.target.dataset.sound;
     bells.play(soundToPlay);
   }
 }

function handleEvent(event) {
  if (event.type === "mousedown") {
    console.log('Ouch!', event);
    var target = event.target;
    var changebody = target.querySelectorAll(".changebody");
    console.log(changebody.innerText);

  } else {
    console.log('Stroke!', event.type);
  }
}

function playString(event){
  if (event.target.classList.contains('changebody')){
    let bellstring = event.target.innerText;
  }
} 

// function setViewportHeight(){
//   let vh = window.innerHeight * 0.01;
//   document.documentElement.style.setProperty('--vh', `${vh}px`);
// }

// setViewportHeight();
// window.addEventListener('resize', () => {
//   setTimeout(setViewportHeight, 100);
// });

drumkit.addEventListener('click', playDrum);
drumkit.addEventListener('touchstart', playDrum);   /* ipad  */

//  change.addEventListener('mousedown', handleEvent);
//  change.addEventListener('click', handleEvent);
//  change.addEventListener('touchstart', handleEvent);   /* ipad  */

// const table = document.getElementsByClassName('frontpage_table_display')[0];
// const rows = table.getElementsByTagName('tr');
// console.log(rows);

// Array.from(rows).forEach((row, index) => {
//   console.log('Adding Events', index);
//   row.addEventListener('click', () =>{
//     const cells = row.getElementsByTagName('td');
//     const content1 = cells[1].innerText;
//     console.log(content1);
//   })
// });

// const table_element = document.querySelector('.frontpage_table_display');
// table_element.addEventListener("click", tableElementClick, false);

// function tableElementClick(event) {
//   console.log("Turning it off...");
//   event.preventDefault();
// }


// const rows = document.querySelectorAll('#frontpage_table_display_1 button');
// console.log(rows); // 👉️ NodeList(3) [tr, tr, tr]

// Array.from(rows).forEach((row, index) => {
//   console.log(row, index);
//   row.addEventListener('onmousedown', handleEvent);
// });


// $('#frontpage_table_display_1').on('click', 'tr', function(e){
//   tableText($(this).html());
// });

// function tableText(tableRow) {
//   var myJSON = JSON.stringify(tableRow);
//   console.log(myJSON);
// }



// d3.selectAll('.frontpage_table_display')
//     .on("click", (event)=> console.log(this));

d3.selectAll(".ring_button")
   .on("click", function(d, i ,e) {
       console.log("BANG!!!!!:-", this.getAttribute("dataring"));
   }
);

console.log('Run Thru');
