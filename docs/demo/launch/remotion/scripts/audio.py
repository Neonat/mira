"""Original locally synthesized instrumental (105 BPM). No samples/models/network.
Author: Mira demo production; released CC0 1.0 for this project. Reproducible stems.
"""
from pathlib import Path
import wave,math,array
out=Path(__file__).resolve().parents[1]/'public';rate=22050;duration=180;n=rate*duration;mix=array.array('f',[0])*n;beat=60/105
# Sparse A-minor/F/C/G pulse, restrained harmonics, with 8-beat chord holds.
chords=[(220,261.6256,329.6276),(174.6141,220,261.6256),(130.8128,164.8138,195.9977),(195.9977,246.9417,293.6648)]
for bar in range(int(duration/(beat*8))+1):
 chord=chords[bar%4]
 for note in range(8):
  start=int((bar*8+note)*beat*rate);freq=chord[note%3]* (2 if note%4==3 else 1)
  for j in range(int(rate*1.7)):
   i=start+j
   if i>=n:break
   t=j/rate;env=min(1,t/.025)*math.exp(-t*2.8)
   mix[i]+=.075*env*(math.sin(2*math.pi*freq*t)+.18*math.sin(2*math.pi*2*freq*t))
pcm=array.array('h',(int(max(-1,min(1,v*min(1,i/rate/3,(n-i)/rate/4)))*32767) for i,v in enumerate(mix)))
with wave.open(str(out/'evidence-bed.wav'),'wb') as w:w.setparams((1,2,rate,0,'NONE','not compressed'));w.writeframes(pcm.tobytes())
click=array.array('h',(int(4000*math.exp(-i/rate*50)*math.sin(2*math.pi*920*i/rate)) for i in range(int(rate*.16))))
with wave.open(str(out/'action.wav'),'wb') as w:w.setparams((1,2,rate,0,'NONE','not compressed'));w.writeframes(click.tobytes())
print('Original 180-second 105 BPM instrumental and action cue written; CC0 1.0.')
