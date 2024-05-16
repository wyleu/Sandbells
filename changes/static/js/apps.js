// const drums =new Howl({
//     "src": [
//         "/static/drums/drums.webm",
//         "/static/drums/drums.mp3"
//       ],
//       "sprite": {
//         "clap": [
//           0,
//           734.2630385487529
//         ],
//         "closed-hihat": [
//           2000,
//           445.94104308390035
//         ],
//         "crash": [
//           4000,
//           1978.6848072562354
//         ],
//         "kick": [
//           7000,
//           553.0839002267571
//         ],
//         "open-hihat": [
//           9000,
//           962.7664399092968
//         ],
//         "snare": [
//           11000,
//           354.48979591836684
//         ]
//       }
// });

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

// function playDrum(event){
//   if (event.target.classList.contains('pad')){
//     event.preventDefault();     /* prevent double click  */
//     let soundToPlay = event.target.dataset.sound;
//     drums.play(soundToPlay);
//   }
// }

function playDrum(event){
  if (event.target.classList.contains('pad')){
    event.preventDefault();     /* prevent double click  */
    let soundToPlay = event.target.dataset.sound;
    bells.play(soundToPlay);
  }
}

function setViewportHeight(){
  let vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
}

setViewportHeight();
window.addEventListener('resize', () => {
  setTimeout(setViewportHeight, 100);
});

drumkit.addEventListener('click', playDrum);
drumkit.addEventListener('touchstart', playDrum);   /* ipad  */


