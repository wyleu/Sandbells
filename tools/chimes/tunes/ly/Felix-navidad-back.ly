\version "2.24.1"
\language "english"

#(set-global-staff-size 40)
#(ly:set-option 'midi-extension "mid")
\header{
    title = "Felix Navidad" 
    tagline = "Sandbells"
}
\paper {
  #(set-paper-size "a4landscape")
}

#(define easyNamedHeads
  (make-engraver
    (acknowledgers
    ((note-head-interface engraver grob source-engraver)
      (let* (
      (grob-pitch
        (ly:event-property (event-cause grob) 'pitch))
      (grob-name (ly:pitch-notename grob-pitch))
      (octave-name (ly:pitch-octave grob-pitch))
      (note-names
        (make-vector
          7
          (string-append
            (string (integer->char (+ 65 (modulo (+ 2 grob-name) 7))))
            (number->string (+ 4 octave-name))))))
  (ly:grob-set-property! grob 'note-names note-names))))))

#(set-global-staff-size 26)



\include "bell-colours.ily"

\score {
  \layout{ 
  ragged-right = ##t
  \context {
    \Voice
    \consists \easyNamedHeads
  }
  }
  \midi{ }
  \new Staff 
    \relative c'' {
    \easyHeadsOn
    \key f \major
    \numericTimeSignature \time 4/4
    \override NoteHead.color = #color-notehead

%       f  e  d  c | % Bar 1     Rounds
%       bf a  g  f | % Bar 2
%      f'  e  d  c | % Bar 3     Rounds
%       bf a  g  f | % Bar 4
%      f'  d  bf g | % Bar 5     Queens
%      e'  c  a  f | % Bar 6
%      f'  d  bf g | % Bar 7     Queens
%      e'  c  a  f | % Bar 8
     
      r4. c8 f4  e8  f8      | % Bar 1 
      d2 r2                  | % Bar 2
      r4. d8 g,4 f'8 d8      | % Bar 3
      c2 r2                  | % Bar 4
      r4. c8 f4  e8  f8      | % Bar 5
      d4  r8 bf8 bf  d d c   | % Bar 6
      c8 c8 c8 c8 bf4 bf8 a8 | % Bar 7
      a2 r2                  | % Bar 8 
      
      r4. c8 f4  e8  f8      | % Bar 9 
      d2 r2                  | % Bar 10
      r4. d8 g,4 f'8 d8      | % Bar 11
      c2 r2                  | % Bar 12
      r4. c8 f4  e8  f8      | % Bar 13
      d4  r8 bf8 bf  d d c   | % Bar 14
      c8 c8 c8 c8 bf4 bf8 a8 | % Bar 15
      a2 r2                  | % Bar 16 
      
      
     %  Felix Navidad 4 1 2 1 3     3 7 1 3 4    4 1 2 1 3  5  3  4 4 5  6 7 8     
  } 
}