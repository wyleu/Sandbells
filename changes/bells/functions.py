from midiutil.MidiFile import MIDIFile

class Error(Exception):
   # Constructor method
   def __init__(self, value):
      self.value = value
   # __str__ display function
   def __str__(self):
      return(repr(self.value))

class DifferingLength(Error):
    pass

class RepeatInCurrent(Error):
    pass

class RepeatInRequired(Error):
    pass

class SanityFailure(Error):
    pass

class IntegrityErrorUnique(Error):
    pass

class ZeroLengthChange(Error):
    pass

class NonIntegerBellCount(Error):
    pass

class NotFound(Error):
    pass

def sanity(current, required):
    if len(current) != len(required):
        raise(DifferingLength('Differing Lengths'))

    for item in current:
        if current.count(item) > 1:
            raise(RepeatInCurrent('Repeat in Current'))

    for item in required:
        if required.count(item) > 1:
            raise(RepeatInRequired('Repeat IN Required'))

    return True

def compare(current, required):
    # Finds and returns the differences betwennn two patterns as expressed rom the current pattern
    return "".join(
        [current[i] for i in range(len(current)) if current[i] != required[i]]
    )

def swap(current, pair):
    # Swap bell pair in current
    # Index error returns current
    index = int(pair)
    res = list(current)

    try:
        res[index-1] = current[index]
    except(IndexError):
        return current
    res[index]= current[index-1]
    return ''.join(res)


def correct(current, required):
    # How many bells are correct?
    total = 0 
    for c, i in enumerate(current):
        if current[c] == required[c]:
            total = total + 1 
    return total 

def incorrect(current, required):
    # How many bells are incorrect?
    total = 0 
    for c, i in enumerate(current):
        if current[c] != required[c]:
            total = total + 1 
    return total 

def frontcorrect(current, required):
    # How far from the front are the bells correct returns place.
    # or 0 if identical
    for count, item in enumerate(current):
        if current[count] != required[count]:
            return count + 1
    return 0

def size(current, required):
    if current and required: 
        if len(current) == len(required):
            return True
    return False

def same(current, required):
    if current == required:
        return True
    return False

def db_process(current, required, debug = False):
    " Runs process and passes process test but also generates calls for events to make."
    calls = []
    sanity_count = 0
    result = list(),list()
    swappair = []
    before_working = current
    current_pos = 0 
    sanity(current, required)
    working = current
    result[0].append(working)

    if current == required:  # Prime current to allow first step
        working = ' '* len(current)

    for pos in range(len(current)):
        while working[pos] != required[pos]:
            if debug:
                print('Working:-',working, 'Pos:-', pos, 'Result:-', result)
            sanity_count = sanity_count + 1

            if( current != required):
                try:
                    current_pos = working.index(required[pos])
                except ValueError:
                    print("OUch missing a bell!",pos, required, required[pos], working )
                    # The Arches, which is a ring of 7 without a 2 is caught here. . . IT's endlessly looking for bell 2, give it the bell beyond the last. . . 
                    working = required
                    current_pos = working.index(required[pos])

                except Exception as e:
                    print('Unknown error', e)
            else:  # Process pattern to itself...
                current_pos = current_pos + 1
                if current_pos == len(current):
                    current_pos = 1
                if working[0] == ' ':   # first pass, prime working
                    working = current

            if debug:
                print('wanted_bell:-', required[pos], 'Current Pos+1:-', current_pos+1)
                print('Before Swap:-', working)
                before_working = working
                

            working = swap(working, current_pos)

            calls.append((before_working, working, current_pos))
            if debug:
                print('After Swap:-', working, 'Current Pos+1:-', current_pos+1)
            if current_pos -2 < 0:
                c1 = working[current_pos-1] + ' Lead'
            else:
                c1 = working[current_pos-1] + ' to ' + working[current_pos-2]
            c2 = working[current_pos] + ' to ' + working[current_pos-1]
            swappair = "%s%s" % (working[current_pos],working[current_pos-1])
            
            if current_pos +1 == len(working):
                c3 = working[current_pos] + ' Back'
            else:
                c3 = working[current_pos+1] + ' to ' + working[current_pos]
            result[1].append([c1,c2,c3, swappair, sanity_count if not divmod(sanity_count,5)[1] else ''])
            if debug:
                print(c1)
                print(c2)
                print(c3)
                print('After Swap:-', working)
            result[0].append(working)
            if sanity_count == 200:
                raise SanityFailure('Sanity Failure No solution in 200 loops') # No solution in 30 loops

        if debug:
            print('Bell in Correct at Pos ',pos + 1, ' move To Next Bell...')
        
    result[1].append(['','',''])
    
    return calls, result, swappair

def midi_file(current: str, required: str = None):
    # Make a MIDI file from a change string

    # create your MIDI object
    midi_map = {
        '1' : 53,   # F3
        '2' : 52,   # E
        '3' : 50,   # D
        '4' : 48,   # C
        '5' : 46,   # Bb
        '6' : 45,   # A
        '7' : 43,   # G
        '8' : 41    # F2
    }


    mf = MIDIFile(1)     # only 1 track
    track = 0   # the only track
    time = 0    # start at the beginning
    channel = 10   # Bells go on MIDI 11
    volume = 100

    track_name = current
    if required:
        track_name = track_name + "-" + required

    mf.addTrackName(track, time, track_name)
    mf.addTempo(track, time, 120)

# add some notes
    if not required:
        for item, count  in enumerate(current, 1):
            pitch = midi_map[item]
            time = count             # on beat
            duration = 1         # 1 beat long
            mf.addNote(track, channel, pitch, time, duration, volume)


        # write it to disk
        with open("%s.mid" % (track_name,), 'wb') as outf:
            mf.writeFile(outf)