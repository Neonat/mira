import React from 'react';import {AbsoluteFill,Composition,Folder,Sequence,staticFile,useVideoConfig} from 'remotion';import {Audio} from '@remotion/media';import {Motion} from './Motion';import {Workflow} from './Workflow';import {SavedResearch} from './SavedResearch';import {Review} from './Review';import {Artifacts} from './Artifacts';
export const FollowTheEvidence:React.FC=()=>{const {fps}=useVideoConfig();return <AbsoluteFill>
<Sequence name="Opening · HyperFrames" durationInFrames={32*fps} premountFor={fps}><Motion id="opening"/></Sequence>
<Sequence name="Synthetic brief and optional approval" from={32*fps} durationInFrames={20*fps} premountFor={fps}><Workflow/></Sequence>
<Sequence name="Agents · HyperFrames" from={52*fps} durationInFrames={20*fps} premountFor={fps}><Motion id="agents"/></Sequence>
<Sequence name="Saved HK research · Separate historical run" from={72*fps} durationInFrames={36*fps} premountFor={fps}><SavedResearch/></Sequence>
<Sequence name="Synthetic authenticated review" from={108*fps} durationInFrames={44*fps} premountFor={fps}><Review/></Sequence>
<Sequence name="Synthetic artifact comparison" from={152*fps} durationInFrames={18*fps} premountFor={fps}><Artifacts/></Sequence>
<Sequence name="Ending · HyperFrames" from={170*fps} durationInFrames={10*fps} premountFor={fps}><Motion id="ending"/></Sequence>
<Audio name="Original CC0 instrumental · 105 BPM" src={staticFile('evidence-bed.wav')} durationInFrames={180*fps} volume={0.55} premountFor={fps}/>
<Audio name="Brief chapter cue" src={staticFile('action.wav')} from={32*fps} volume={0.35} premountFor={fps}/>
<Audio name="Saved research chapter cue" src={staticFile('action.wav')} from={72*fps} volume={0.35} premountFor={fps}/>
<Audio name="Review chapter cue" src={staticFile('action.wav')} from={108*fps} volume={0.35} premountFor={fps}/>
<Audio name="Reviewed artifact cue" src={staticFile('action.wav')} from={160*fps} volume={0.35} premountFor={fps}/>
</AbsoluteFill>};
export const RemotionRoot:React.FC=()=> <>
<Composition id="FollowTheEvidence" component={FollowTheEvidence} durationInFrames={5400} fps={30} width={1920} height={1080}/>
<Folder name="Chapters">
<Composition id="SyntheticWorkflow" component={Workflow} durationInFrames={600} fps={30} width={1920} height={1080}/>
<Composition id="SavedHKResearch" component={SavedResearch} durationInFrames={1080} fps={30} width={1920} height={1080}/>
<Composition id="SyntheticReview" component={Review} durationInFrames={1320} fps={30} width={1920} height={1080}/>
<Composition id="ReviewedArtifacts" component={Artifacts} durationInFrames={540} fps={30} width={1920} height={1080}/>
</Folder></>;
