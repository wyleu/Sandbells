\version "2.24.1"
\language "english"
\header{
    title= "Congratulations"
    subtitle = " "
    tagline = "Sandbells"
}

#(set-global-staff-size 48)

\paper {
  #(set-paper-size "a4landscape")
}


congratulations = \relative c'{
  \numericTimeSignature \time 4/4
  \key f \major
  
  r4  f4  g4  a4  | 
  bf2     f2      |
  r4  bf4 a4  bf4 | 
  c2      g2      |
  r4  g   a   bf  |
  d   c   c   bf  |
  bf  a   g   a   |
  f1              |
  
  r4  f4  g4  a4  | 
  bf2     f2      |
  r4  bf4 a4  bf4 | 
  c2      g2      |
  r4  g   a   bf  |
  d   c   c   bf  |
  bf  a   g   a   |
  bf1             |
  
}



\score{
\congratulations
}