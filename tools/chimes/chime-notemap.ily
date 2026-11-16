%% chime-notemap.ily -- record where every note head lands on the page.
%%
%% Loaded by chime-build with  lilypond -dinclude-settings=chime-notemap.ily
%% so the tune's own .ly file is not edited.  (Adding  \include
%% "chime-notemap.ily"  at the top of a .ly does the same.)
%%
%% Two parts:
%%  * an engraver in every Voice notes, for every NoteHead, the bar number,
%%    the position in the bar, the moment, the pitch and whether it is the
%%    tied-to end of a tie (printed, not played again);
%%  * the PostScript backend's grob-cause hook (called once per grob with the
%%    grob's offset on its page) is wrapped so each NoteHead's box on the page
%%    is written out with those facts.  The original hook still runs, so
%%    point-and-click links are unchanged.
%%
%% Output: one line per note head, tab separated, to the file named by the
%% environment variable CHIME_NOTEMAP_OUT (default: <output name>.notemap.tsv).
%% Columns: see chime-notemap-columns below.  chime-build turns it into JSON.

#(define chime-notemap-columns
   '("page" "paper_w" "paper_h" "x1" "x2" "y1" "y2"
     "moment" "bar" "bar_pos" "midi" "pitch" "staff" "length" "tied"))

#(define chime-notemap-facts (make-weak-key-hash-table))

#(define (chime-notemap-moment->string m)
   (let ((r (ly:moment-main m)))
     (format #f "~a/~a" (numerator r) (denominator r))))

#(define (chime-notemap-engraver context)
   ;; One per Voice.  A tie event comes with the note it starts from; the
   ;; next note heads of this voice at those pitches are the tied-to ones
   ;; (printed, not played again), marked tied=1.
   (let ((tie-started #f)
         (step-pitches '())
         (tied-pitches '()))
     (make-engraver
      ((start-translation-timestep engraver)
       (set! tie-started #f)
       (set! step-pitches '()))
      (listeners
       ((tie-event engraver event)
        (set! tie-started #t)))
      (acknowledgers
       ((note-head-interface engraver grob source-engraver)
        (let* ((cause (ly:grob-property grob 'cause))
               (pitch (and (ly:stream-event? cause)
                           (ly:event-property cause 'pitch #f)))
               (duration (and (ly:stream-event? cause)
                              (ly:event-property cause 'duration #f)))
               (staff (ly:context-find context 'Staff)))
          ;; a tie inside a chord (<c~ e>) rides on the note as an articulation
          (if (and (ly:stream-event? cause)
                   (any (lambda (a) (and (ly:stream-event? a)
                                         (ly:in-event-class? a 'tie-event)))
                        (ly:event-property cause 'articulations '())))
              (set! tie-started #t))
          (if (ly:pitch? pitch)
              (let ((semis (ly:pitch-semitones pitch)))
                (set! step-pitches (cons semis step-pitches))
                (hashq-set! chime-notemap-facts grob
                            (list (chime-notemap-moment->string
                                   (ly:context-current-moment context))
                                  (ly:context-property context 'currentBarNumber 0)
                                  (chime-notemap-moment->string
                                   (ly:context-property context 'measurePosition
                                                        ZERO-MOMENT))
                                  (+ 60 semis)
                                  (ly:pitch-notename pitch)
                                  (ly:pitch-alteration pitch)
                                  (ly:pitch-octave pitch)
                                  (if staff (ly:context-id staff) "")
                                  (if (ly:duration? duration)
                                      (chime-notemap-moment->string
                                       (ly:duration-length duration))
                                      "0/1")
                                  (if (member semis tied-pitches) 1 0))))))))
      ((stop-translation-timestep engraver)
       (if (pair? step-pitches)
           (set! tied-pitches (if tie-started step-pitches '())))))))

\layout {
  \context {
    \Voice
    \consists #chime-notemap-engraver
  }
}

#(define chime-notemap-out
   (let ((env (getenv "CHIME_NOTEMAP_OUT")))
     (if (and env (not (string-null? env)))
         env
         (string-append (ly:parser-output-name) ".notemap.tsv"))))

#(define chime-notemap-port #f)

#(define (chime-notemap-write grob offset)
   (let ((facts (hashq-ref chime-notemap-facts grob #f)))
     (if facts
         (let* ((layout (ly:grob-layout grob))
                (system (ly:grob-system grob))
                (page (ly:grob-property system 'page-number 0))
                (x-ext (ly:grob-extent grob grob X))
                (y-ext (ly:grob-extent grob grob Y)))
           (if (not chime-notemap-port)
               (begin
                 (set! chime-notemap-port (open-output-file chime-notemap-out))
                 (display (string-join chime-notemap-columns "\t") chime-notemap-port)
                 (newline chime-notemap-port)))
           (display
            (string-join
             (map (lambda (v) (if (string? v) v (format #f "~a" v)))
                  (list page
                        (ly:output-def-lookup layout 'paper-width)
                        (ly:output-def-lookup layout 'paper-height)
                        (+ (car offset) (car x-ext))
                        (+ (car offset) (cdr x-ext))
                        (+ (cdr offset) (car y-ext))
                        (+ (cdr offset) (cdr y-ext))
                        (list-ref facts 0)
                        (list-ref facts 1)
                        (list-ref facts 2)
                        (list-ref facts 3)
                        (format #f "~a:~a:~a" (list-ref facts 4)
                                (list-ref facts 5) (list-ref facts 6))
                        (list-ref facts 7)
                        (list-ref facts 8)
                        (list-ref facts 9)))
             "\t")
            chime-notemap-port)
           (newline chime-notemap-port)
           (force-output chime-notemap-port)))))

#(let* ((mod (resolve-module '(lily output-ps)))
        (alist (module-ref mod 'stencil-dispatch-alist))
        (original (assq-ref alist 'grob-cause)))
   (module-set! mod 'stencil-dispatch-alist
                (assq-set! (alist-copy alist) 'grob-cause
                           (lambda (offset grob)
                             (chime-notemap-write grob offset)
                             (original offset grob)))))
