\version "2.24.1"
\language "english"
 #(set-global-staff-size 48)

\header{
    title = "Troika Sleigh Ride" 
    subtitle = " "
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
      r2          r4     c'4   |
      f8 e8 d8 e8 f4     d4    |
      c d a c                  |
      d8 c8 bf4 f'4 e8 f8      |
      \break
      
      c2.               bf8 a8 |
      g4 d'4 c4 bf4            |
      c8 bf8 a8 bf8 c4  f8 d8  |
      bf4  a8 bf8 c4 c         |
      <f, f'>1                 
      \break
      
      \repeat volta 2 {
      r2 r4        d'4          |
      a4.    d8 a8 d8 a8 bf8    |
      c4 bf8 a8 bf4 d4          |
      a1 | 
      }
    }
%  }
    }

\score {
  <<
  \new Staff="staff" \with {
  instrumentName = "Bells"
  midiInstrument = "voice oohs"
  } 
     \voiceooh
  
  \new Lyrics \with { alignBelowContext = "staff" } {
  \lyricsto "" {
                                     "4"|
         "1" "2" "3" "2" "1" "3"        |
         "4" "3" "6" "4"                |
         "3" "4" "5" "1" "2" "1"        |
         "4"                     "5" "6"|
         "7" "3" "4" "5"                |
         "4" "5" "6" "5" "4" "1" "3"    |
         "5" "6" "5" "4" "4"            | 
         "8/1"                               
         
         "3"                            |
         "6" "3" "6" "3" "6"  "5"       |
         "4" "5" "6" "5" "3"            |
         "6"                            |
       }
     }
  >>
  
  \layout { 
  }
}
  
  %% MIDI SCORE
\score {
    \unfoldRepeats { 
        \voiceooh
    } 
  
  \midi {
    \tempo 4=100
     }
   }        
 
