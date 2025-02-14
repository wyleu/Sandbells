from operator import mod
from django.db import models
from django.db import utils
# from palletes.models import Pallete
from .functions import DifferingLength, IntegrityErrorUnique
from .functions import  sanity, db_process
#from midiutil import MIDIFile
from midiutil.MidiFile import MIDIFile

MIDI_ASCII_NOTE_OFFSET = 48


class Pattern(models.Model):
    name = models.CharField(max_length=200)
    pub_date = models.DateTimeField(auto_now=True)
    history = models.TextField(blank=True)
    pattern = models.CharField(max_length=100, blank=True, unique=True)
    order = models.SmallIntegerField(help_text="Ordering of patterns rounds should explicitly be 0",
                                      default=100)
    number = models.SmallIntegerField(editable=False, help_text ="Bells in Pattern (calculated)", default=0)
    count = models.SmallIntegerField(help_text="Number of changes in pattern", null=True,)
    enable = models.BooleanField(help_text="Enable this Pattern", default = True)

    class Meta:
        ordering = ["order"]

    def save(self, *args, **kwargs):
        self.number = len(self.pattern)
        super().save(*args, **kwargs)

    def midi_file(self, filename=None):
        if filename:
            self.filename = filename
        else:
            self.filename = ''.join(['sandbells_',self.name,'_', str(self.number),'.MID'])

        degrees  = [60, 62, 64, 65, 67, 69, 71, 72]  # MIDI note number
        track    = 0
        channel  = 0
        time     = 0    # In beats
        duration = 1    # In beats
        tempo    = 60   # In BPM
        volume   = 100  # 0-127, as per the MIDI standard

        MyMIDI = MIDIFile(1)  # One track, defaults to format 1 (tempo track is created
                            # automatically)
        MyMIDI.addTempo(track, time, tempo)

        for i, pitch in enumerate(str(self.pattern)):
            pitch = ord(pitch) - MIDI_ASCII_NOTE_OFFSET
            MyMIDI.addNote(track, channel, pitch, time + i, duration, volume)

        with open(self.filename, "wb") as output_file:
            MyMIDI.writeFile(output_file)

    def populate_count(self, count):
        if self.count is None:
            self.count = count
            self.save()

           
    def __str__(self):
        return " ".join([self.name,' On ',str(self.number)])
 
class Change(models.Model):
    from_pat = models.ForeignKey('Pattern', related_name="from_pattern",on_delete=models.PROTECT,)
    to_pat = models.ForeignKey('Pattern', related_name="to_pattern",on_delete=models.PROTECT,)
    number = models.SmallIntegerField(editable=False, default = 0, help_text="Number of Bells in Change")

    def __str__(self):
        return ''.join(['From:',self.from_pat.name,' To:', self.to_pat.name,'On ',str(self.number),])

    def save(self, *args, **kwargs):
        self.number = len(self.from_pat.pattern)
        super().save(*args, **kwargs)
    
    def express(self, build_reverse=False):
        " Render the patterns between the two identified patterns"
        # Fetch the from_pat and to_pat 
        # Are the pattern length the same ?
        if len(self.from_pat.pattern) != len(self.to_pat.pattern):
            raise DifferingLength('Express has detected differing lengths')
            return False
        calls, result, swappair = db_process(self.from_pat.pattern, self.to_pat.pattern)

        for step, call  in enumerate(calls):
            try:
                pat_obj = Pattern.objects.get(pattern = call[1])
            except(Pattern.DoesNotExist):
                pat_obj = Pattern(pattern = call[1],
                                  name = call[1],
                                  history = " Built from %s to %s" % ( self.from_pat.pattern, self.to_pat.pattern),
                                  order = 999
                                  )
                pat_obj.save()
            item_obj, item_created  = ChangeItem.objects.get_or_create(
                change = self,
                pattern = pat_obj,
                step = step+1 
            )
        
        if build_reverse:        
            calls, result, swappair = db_process(self.to_pat.pattern, self.from_pat.pattern)
            for step, call  in enumerate(calls):
                pat_obj, pat_created = Pattern.objects.get_or_create(
                    pattern = call[1],
                    name = call[1],
                    history = "Reverse to %s to %s" % (self.from_pat.pattern, self.to_pat.pattern,),
                    order = 300
                )
                item_obj, item_created  = ChangeItem.objects.get_or_create(
                    change = self,
                    pattern = pat_obj,
                    step = step+1 
                )

class ChangeItem(models.Model):
    change = models.ForeignKey('Change',on_delete=models.CASCADE)
    step = models.SmallIntegerField()
    pattern = models.ForeignKey('Pattern', on_delete=models.CASCADE)
    pattern_str = models.CharField(max_length= 100, default='', blank=True)

    def save(self, *args, **kwargs):
        self.pattern_str = self.pattern.pattern
        super().save(*args, **kwargs)

class TowerManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)

class Tower(models.Model):
    name = models.CharField(max_length=200)
    #pallete= models.ForeignKey(
    ##    Pallete,
    #    on_delete=models.PROTECT,
    #    help_text="The Colour Pallete used at this tower")
    
    objects = TowerManager()

    def natural_key(self):
        return (self.name,)

    def __str__(self):
        return self.name

    # def get_pallete(self):
    #     return self.pallete.colour_set.all()



class Bell(models.Model):
    tower = models.ForeignKey('Tower', on_delete=models.CASCADE, help_text= 'Tower bell is located in')
    bell = models.CharField(max_length=4, blank=True)
    weight = models.CharField(max_length= 10,help_text='Bell Weight', blank=True)
    nominal = models.CharField(max_length= 10, blank=True)
    note = models.CharField(max_length=3,help_text="Pitch of bell", blank=True)
    diameter = models.DecimalField(max_digits=6, decimal_places =3, blank=True)
    dated = models.CharField(max_length=6, blank=True)
    founder = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return ' '.join([self.bell, str(self.tower)])
    

class Function(models.Model):
    name = models.CharField(max_length=60, help_text="function Name", unique=True)
    order = models.PositiveSmallIntegerField(unique=True)
    active = models.BooleanField(default=True)
    function = models.CharField(max_length=255)

    def __str__(self):
        return ' '.join(self.name, str(self.order)) 
