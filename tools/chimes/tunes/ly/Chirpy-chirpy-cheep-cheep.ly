\version "2.24.1"
\language "english"
#(set-global-staff-size 48)

\header{
    title = "Chirpy Chirpy Cheep Cheep" 
    tagline = "Sandbells"
}

\include "bell-colours.ily"


\paper {
  #(set-paper-size "a4landscape")
}


voiceooh = 
 % \transpose bf f' {
    \relative c' {
    \override NoteHead.color = #color-notehead
    % Music follows here.
    \numericTimeSignature \time 4/4
    \key f \major 
    
    { 
      \repeat volta 3 {
      d'4. f8 c4 f8   bf,8      |
      r4  f'8 f8 g,8 f'8 f4    |
      }
      \break
      bf,2 a4 g  g2. r4 |
      bf2  a4 g  g2. r4 |  
      \break
      \repeat volta 2 {
      bf4 bf8  c8 d8 c8  bf8 f8  |
      g8 f8 g8 f8 r2             |
      g4. a8 a4 r8 g8|
      g g g bf a4 a4 |
      }
      \break
      g4. a8 a4 r8 g8|
      g g g bf a4 a4 |
      bf1
    }
  }


\score {
  <<
  \new Staff = "staff" \with {
  instrumentName = "Bells"
  midiInstrument = "voice oohs"
  } \voiceooh
  
       \new Lyrics \with { alignAboveContext = "staff" } {
       \lyricsto "" {
         "3" "1" "4" "1" "5"            |
         "1" "1" "7" "1" "1"            |
         "5" "6" "7" "7"                | 
         "5" "6"  "7" "7"               |
         "5" "5" "4" "3" "4" "5" "8"    |
         "7" "8" "7" "8"                |
         "7" "6" "6" "7"            |
         "7" "7" "7"                    |
         "5" "6" "6"                    |
       
       
         "7" "6" "6" "7" "7" "7" "7" "5" "6" "6" "5"
       
       }
     }
  
  
  >>
  \layout { 
  }
}
\score {
    \unfoldRepeats { 
        \voiceooh
    } 
  
  \midi {
    \tempo 4=100
  }
}