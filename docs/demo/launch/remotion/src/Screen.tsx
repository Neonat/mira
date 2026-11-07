import React from 'react';
import {AbsoluteFill,CanvasImage,staticFile,useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
export type ScreenProps={title:string;chapter:string;disclosure:string;asset:string;crop?:[number,number,number,number];note?:string;video?:boolean;trim?:number;sourceWidth?:number};
export const Screen:React.FC<ScreenProps>=({title,chapter,disclosure,asset,crop=[0,0,1440,900],note,video=false,trim=0,sourceWidth=1440})=>{const {fps}=useVideoConfig();const [x,y,w,h]=crop;const scale=Math.min(1728/w,640/h);const style:React.CSSProperties={position:'absolute',width:sourceWidth*scale,maxWidth:'none',left:-x*scale,top:-y*scale};return <AbsoluteFill style={{background:'#fff',color:'#222',fontFamily:'Arial,sans-serif'}}>
<div style={{position:'absolute',top:72,left:96,fontSize:28,fontWeight:700,letterSpacing:3,textTransform:'uppercase',color:'#60646B'}}>{chapter}</div>
<div style={{position:'absolute',top:122,left:96,right:96,fontSize:56,fontWeight:700,lineHeight:1.06}}>{title}</div>
<div style={{position:'absolute',left:96,top:242,width:1728,height:640,overflow:'hidden',background:'#f6f8f8',borderTop:'3px solid #E60028',boxShadow:'0 7px 28px #22222212'}}><div style={{position:'absolute',left:(1728-w*scale)/2,top:(640-h*scale)/2,width:w*scale,height:h*scale,overflow:'hidden'}}>{video?<Video src={staticFile(asset)} trimBefore={trim*fps} premountFor={fps} muted style={style}/>:<CanvasImage src={staticFile(asset)} premountFor={fps} style={style}/>}</div></div>
<div style={{position:'absolute',left:96,right:96,top:914,fontSize:30,lineHeight:1.25}}>{note}</div>
<div style={{position:'absolute',bottom:42,left:96,right:96,fontSize:28,color:'#60646B',borderTop:'1px solid #d9d9d9',paddingTop:16}}><span style={{display:'inline-block',width:10,height:10,background:'#E60028',marginRight:14}}/>{disclosure}</div>
</AbsoluteFill>};
