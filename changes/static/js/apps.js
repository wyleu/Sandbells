
console.log('Top of /static/js/apps.js');

const bells = new Howl(
  {
    "src": ["/static/ogg/Rounds_on_8_10_Bpm.webm","/static/ogg/Rounds_on_8_10_Bpm.ogg"],
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

console.log('Top of /static/js/apps.js after bells');

var bellnumbers = ["bell1", "bell2","bell3", "bell4","bell5", "bell6", "bell7", "bell8"];

console.log('Top of /static/js/apps.js after bellnumbers');

const drumkit = document.querySelector('.drumkit');
// const change = document.querySelector('.frontpage_table_display');


 function playBellEvent(event){
   if (event.target.classList.contains('pad')){
     event.preventDefault();     /* prevent double click  */
     let soundToPlay = event.target.dataset.sound;
     console.log('Event Playing '+ soundToPlay);
     bells.play(soundToPlay);
   }
 }

 function playBellStr(bell_numberstring){
    soundToPlay = bellnumbers[Number(bell_numberstring) - 1];
    console.log('Playing '+ soundToPlay);
    bells.play(soundToPlay);
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

drumkit.addEventListener('click', playBellEvent);
drumkit.addEventListener('touchstart', playBellEvent);   /* ipad  */

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

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}


d3.selectAll(".ring_button")
   .on("click", function(d, i ,e) {
      var bellstring = this.getAttribute("dataring");
      console.log("BELLS:-", bellstring);

      Array.from(bellstring).forEach((elem, indx,array) => {
        console.log('Playing:-' + elem);
        ;
        setTimeout(() => { 
          playBellStr(elem); 
        }, 500 * indx);

      });

   }
);

console.log('Run Thru');
