\version "2.14.0"
\language "english"
\header{
    title = "Sandbell Rounds"
}

\include "bell-colours.ily"

\score {
  \new Staff \relative c'' {
    \key f \major
    \numericTimeSignature \time 4/4
    \override NoteHead.color = #color-notehead
      f  e  d  c | % Bar 1
      bf a  g  f | % Bar 2
  } 
}