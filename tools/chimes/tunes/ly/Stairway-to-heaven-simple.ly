\version "2.24.1"
\language "english"

#(set-global-staff-size 40)
#(ly:set-option 'midi-extension "mid")
\header{
    title = "Stairway to heaven" 
    tagline = "Sandbells"
}
\paper {
  #(set-paper-size "a4landscape")
}

#(define Ez_numbers_engraver
   (make-engraver
    (acknowledgers
     ((note-head-interface engraver grob source-engraver)
      (let* ((context (ly:translator-context engraver))
             (tonic-pitch (ly:context-property context 'tonic))
             (tonic-name (ly:pitch-notename tonic-pitch))
             (grob-pitch
              (ly:event-property (event-cause grob) 'pitch))
             (grob-name (ly:pitch-notename grob-pitch))
             (delta (modulo (- grob-name tonic-name) 7))
             (note-names
              (make-vector 7 (number->string (1+ delta)))))
        (ly:grob-set-property! grob 'note-names note-names))))))

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

#(set-global-staff-size 50)



\include "bell-colours.ily"



\paper { tagline = ##f }

\score {

  
  \layout{ 
  ragged-right = ##t
  \context {
    \Voice
    \consists Ez_numbers_engraver
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
     \repeat volta 2 {
      r4. c8 f4  e8  f8      | % Bar 1 
      d2 r2                  | % Bar 2
      r4. d8 g,4 f'8 d8      | % Bar 3
      c2 r2                  | % Bar 4
      r4. c8 f4  e8  f8      | % Bar 5
      d4  r8 bf8 bf  d d c   | % Bar 6
      c8 c8 c8 c8 bf4 bf8 a8 | % Bar 7
      a2 r2                  | % Bar 8 
     }
      
      
     %  Felix Navidad 4 1 2 1 3     3 7 1 3 4    4 1 2 1 3  5  3  4 4 5  6 7 8     
  } 
}