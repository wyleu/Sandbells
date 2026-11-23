% bell-colours.ily -- Sandbells front-page colours for the 8 bells
%
% Source: changes/bells/static/js/bell_band.js  BELL_COLOURS
% (the front page, blank.html, loads that file).
% Colour by bell number: pitch and octave, so F5 (bell 1) and F4 (bell 8)
% are different.  Do not edit the numbers by hand; copy them from that file.
%
% In a tune, replace the old note-name x11-color block with:
%   \include "bell-colours.ily"
% chime-build puts this folder on LilyPond's include path.  For Frescobaldi,
% copy this file next to the tune (or add tools/chimes to the include path).

#(define color-mapping
   (list
    (cons (ly:make-pitch 1 3 NATURAL) (rgb-color (/ 255 255) (/ 32 255) (/ 32 255))) ; bell 1 F5 #ff2020
    (cons (ly:make-pitch 1 2 NATURAL) (rgb-color (/ 255 255) (/ 140 255) (/ 0 255))) ; bell 2 E5 #ff8c00
    (cons (ly:make-pitch 1 1 NATURAL) (rgb-color (/ 255 255) (/ 208 255) (/ 0 255))) ; bell 3 D5 #ffd000
    (cons (ly:make-pitch 1 0 NATURAL) (rgb-color (/ 34 255) (/ 192 255) (/ 34 255))) ; bell 4 C5 #22c022
    (cons (ly:make-pitch 0 6 FLAT) (rgb-color (/ 0 255) (/ 212 255) (/ 212 255))) ; bell 5 Bb4 #00d4d4
    (cons (ly:make-pitch 0 5 NATURAL) (rgb-color (/ 32 255) (/ 80 255) (/ 255 255))) ; bell 6 A4 #2050ff
    (cons (ly:make-pitch 0 4 NATURAL) (rgb-color (/ 224 255) (/ 0 255) (/ 224 255))) ; bell 7 G4 #e000e0
    (cons (ly:make-pitch 0 3 NATURAL) (rgb-color (/ 139 255) (/ 0 255) (/ 0 255))) ; bell 8 F4 #8b0000
    ))

#(define (pitch-to-color pitch)
   (let ((color (assoc pitch color-mapping equal?)))
     (if color (cdr color))))

#(define (color-notehead grob)
   (pitch-to-color
    (ly:event-property (event-cause grob) 'pitch)))
