\version "2.24.1"
\language "english"
\header{
    title= "Nimrod Enigma Variations"
    subtitle = " Edward Elgar"
    tagline = "Sandbells"
}

#(set-global-staff-size 48)

\paper {
  #(set-paper-size "a4landscape")
}


nimrod = \relative c'{
  \numericTimeSignature \time 3/4
  \key f \major
  {
   r2 a'4  
   f4   bf4 r4 |      
   g2 c4  |
   r4 g4 bf|      
   a4   c4  f4 |
   f4 g,2  |
   e'2 f,4  |   
   f4  g  bf4|
   a  c a |
   a bf2 | 
   g  a4  |
   a4  bf4 d4 |  
   f  a,  g  |
   r2 bf4  |
   d f  a, |
   g  r2 |
   bf4  d  f, | 
   a  g2|
   r 2 a4 
   f bf2 g2 |
   f2. |
  }
} 
  \score{
\nimrod
}
  %% MIDI SCORE
\score {
    \unfoldRepeats { 
        \nimrod
    } 
  
  \midi {
    \tempo 4=100
     }
   } 