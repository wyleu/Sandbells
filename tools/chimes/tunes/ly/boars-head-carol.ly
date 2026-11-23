\version "2.24.1"
\language "english"
#(set-global-staff-size 48)

\header{
    title = "The Boars Head Carol" 
    subtitle = " "
    tagline = "Sandbells"
}

\include "bell-colours.ily"


\paper {
  #(set-paper-size "a4landscape")
}


tubularBells = 
  \transpose f bf, {
  \relative c'' {
  % Music follows here.
  \clef treble
  {c f f e c d d  c a bf d c a bf c f}  
  }
}

voiceooh = 
  % \transpose bf f' {
  \relative c''' {
  \override NoteHead.color = #color-notehead
  % Music follows here.
  \clef treble
  \key f \major 
  \numericTimeSignature \time 4/4
   { 
    r2       r4       c,4          |          
    f2       f4.      f8           |
    e4       f        c4.       a8 |
    bf4      bf       d4.       bf8|
    c4       c4       f     c      |
    f4       f8  f8   f4    f4     |
    e4       f4       c4.       a8 |
    bf4      bf4      d4.       bf8|
    c4.           c8 <f f,>2       |
    
    \repeat volta 2 {
    <a, f'>4   <a f'>4     <e' g,>4  <e g,>4  |
    <f bf,>4   <bf, f'>4   <c f>2             | 
    <bf f>4    d4          c4        a4       |
    bf4        d4          <f c f,>2            |
    }  
   }  
  }
% }

chorus = 
  \relative c'' {
    f4      f4       e4       e4   |
    f4      f4       c2            | 
    bf4     d4       c4       a4   |
    bf4     d4       f2            |
  }



\score {
  <<
%   \new Staff \with {
%     instrumentName = "Tubular bells"
%     midiInstrument = "tubular bells"
%   } \tubularBells
  
  \new Staff ="bells" \with {
  instrumentName = "Bells"
  midiInstrument = "voice oohs"
  }
  
 
  \voiceooh
       \new Lyrics \with { alignAboveContext = "bells" } {
       \lyricsto "" {\tiny
         "4"                 |
         "1" "1" "1"         |
         "2" "1" "4" "6"     |
         "5" "5" "3" "5"     |
         "4" "4" "1" "4"     |
         "1" "1" "1" "1" "1" |
         "2" "1" "4" "6"     |
         "5" "5" "3" "5"     |
         "6" "6" "8/1"       |
         

         \break
         \sectionLabel "Chorus"
         
         "1/6" "1/6"  "2/7"  "2/7" |
         "1/5" "1/5"  "1/4"        |
         "5/8" "3"    "4"    "6"   |
         "5"   "3 "    " 8/4/1"     |
         
         % The boars head in hand bear I |  
         % Be-deck'd with bays and rose-ma-ry,|
         % And I pray you, my masters, be merr-ry.|
         % Quot es-tis in con -vi vi o 
         
       }
       }
       \new Lyrics \with { alignBelowContext = "bells"
                         }
                         {
       \lyricsto "" {
         
                  " "
         " "" "" "
         " "" "" "" "
         " "" "" "" "
         " "" "" "" "
         " "" "" "" "" "
         " "" "" "" "
         " "" "" "" "
         " "" "" "
         \tiny
         "Ca-""pu" "Ap-""ri" "De-""fer-""ro"          %   The boar's head I bear
         "Red-""dens" "Lau-""des" "Do-""mi-""no"      %   Rendering praises to the Lord

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
