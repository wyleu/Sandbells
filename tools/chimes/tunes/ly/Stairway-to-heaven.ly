\version "2.24.1"
\language "english"

#(set-global-staff-size 70)
#(ly:set-option 'midi-extension "mid")
\header{
    title = "Stairway to Heaven" 
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

#(set-global-staff-size 30)



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
  <<
  \new Staff {
    \new Voice = "melody" {
      \relative c'' {
      \easyHeadsOn
      \key f \major
      \numericTimeSignature \time 4/4
      \override NoteHead.color = #color-notehead
             \repeat volta 2 {
              r2 r4 g8 a16  bf16         | % Bar 1 
              bf8 bf8 a8 g16 a16         | % Bar 2
              g16 a16 bf16 bf16          | % Bar 3
              c4 bf8 a8 g8               | % Bar 4
              r4. bf8 c4  d8  c8         | % Bar 5
              bf4 a4 g8 f4 f4 g4  g4     | % Bar 6
           }
       
        bf4 d c c8 bf8 a8 g4             | % Bar 7
        r4 g 4 a bf c d c c bf8 a8 f4 f4 g4 
       }  % Relative
     }  % Voice
  }  % Staff
      \new Lyrics \with { alignAboveContext = "staff" } {
      \lyricsto "melody" {
        There's a la -- dy who's sure -- 
        all tha-t gli-ters is go-ld 
        and she's buy-ing a stair-way
        to hea-ven
      }
    }
  
  >>
}
