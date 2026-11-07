import React from 'react';import {Sequence,useVideoConfig} from 'remotion';import {Screen} from './Screen';
const d='Synthetic review demonstration · Separate original and reviewed artifacts · Reading holds';
export const Artifacts:React.FC=()=>{const {fps}=useVideoConfig();return <>
<Sequence name="Original remains unchanged" durationInFrames={8*fps} premountFor={fps}><Screen title="The original draft stays unchanged" chapter="Synthetic review demonstration · Original" disclosure={d} asset="original.png" crop={[280,610,865,280]} note="The original file hash matches before and after review."/></Sequence>
<Sequence name="Reviewed artifact implements outcomes" from={8*fps} durationInFrames={10*fps} premountFor={fps}><Screen title="The reviewed artifact applies the decisions" chapter="Synthetic review demonstration · Reviewed" disclosure={d} asset="reviewed.png" crop={[280,610,865,280]} note="Amendment retained. Rejected fact and its dependent assessment excluded."/></Sequence>
</>};
