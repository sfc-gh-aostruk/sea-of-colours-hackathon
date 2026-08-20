/* Circuit FX overlay — runs the circuit/pixel animation on #fx-cv.
   To revert: comment out the canvas + script tags in landing.html and
   the #fx-cv rule in landing.css. This file can stay untouched. */
(function(){
'use strict';

const cv=document.getElementById('fx-cv');
if(!cv)return;
const ctx=cv.getContext('2d');
const LIME='#ffffff', BLACK='#000';
let W,H;
function resize(){cv.width=W=innerWidth;cv.height=H=innerHeight;}
resize();
window.addEventListener('resize',resize);

const CC=10, CFONT='9px ui-monospace,"Cascadia Code",monospace';
const THIN=['·','│','│','│','─','┐','┘','┤','─','┌','└','├','─','┬','┴','┼'];
const BOLD=[' ','║','║','║','═','╗','╝','╣','═','╔','╚','╠','═','╦','╩','╬'];
const VIAS=['⊕','⊗','○','●','◉'];
const LBLS=['U','B','A','R','C','Q','G','V','D','F','H','I','J','K','L','M','N','P','S','T',
            '1','2','3','4','5','6','7','8','9','0','+','-','='];
const DX=[1,0,-1,0], DY=[0,1,0,-1];
const MY=[8,1,4,2], OPP=[4,2,8,1];

let ccSortedA, ccSortedB, ccSortedC, ccSortedD;

function buildOneLayer(){
  const ccCols=Math.floor(W/CC), ccRows=Math.floor(H/CC);
  const ccGrid=Array.from({length:ccRows*ccCols},()=>({rlud:0,time:1,bold:false,marked:false,dark:false,via:null,lbl:null}));
  function cc(r,c){return ccGrid[r*ccCols+c];}
  function ok(r,c){return r>=0&&r<ccRows&&c>=0&&c<ccCols;}
  const NK=4+Math.floor(Math.random()*5);
  const kernels=Array.from({length:NK},(_,i)=>({r:Math.floor(Math.random()*ccRows),c:Math.floor(Math.random()*ccCols),base:i*0.05}));
  function kTime(r,c){let best=0,bd=1e9;for(const k of kernels){const d=Math.abs(r-k.r)+Math.abs(c-k.c);if(d<bd){bd=d;best=k.base;}}return best+bd*0.0012;}
  function mark(r,c,rlud,bold,t,drk=false){
    if(!ok(r,c))return;
    const ce=cc(r,c);
    ce.rlud|=rlud; ce.bold=ce.bold||bold; ce.dark=ce.dark||drk;
    if(!ce.marked){ce.marked=true;ce.time=t;}else ce.time=Math.min(ce.time,t);
  }
  function routeH(r,c1,c2,bold,t,drk=false){
    const dc=c2>c1?1:-1,dir=dc>0?0:2;
    for(let c=c1;c!==c2;c+=dc){if(!ok(r,c)||!ok(r,c+dc))break;mark(r,c,MY[dir],bold,t,drk);mark(r,c+dc,OPP[dir],bold,t,drk);t+=0.00022;}
  }
  function routeV(r1,r2,c,bold,t,drk=false){
    const dr=r2>r1?1:-1,dir=dr>0?1:3;
    for(let r=r1;r!==r2;r+=dr){if(!ok(r,c)||!ok(r+dr,c))break;mark(r,c,MY[dir],bold,t,drk);mark(r+dr,c,OPP[dir],bold,t,drk);t+=0.00022;}
  }
  function routeL(r1,c1,r2,c2,bold,t,drk=false){
    if(r1===r2){routeH(r1,c1,c2,bold,t,drk);return;}
    if(c1===c2){routeV(r1,r2,c1,bold,t,drk);return;}
    if(Math.random()<0.5){routeH(r1,c1,c2,bold,t,drk);routeV(r1,r2,c2,bold,t,drk);}
    else{routeV(r1,r2,c1,bold,t,drk);routeH(r2,c1,c2,bold,t,drk);}
  }
  const N_IC=45+Math.floor(Math.random()*20);
  const icPins=[], placed=[];
  for(let attempt=0;placed.length<N_IC&&attempt<N_IC*6;attempt++){
    const h=2+Math.floor(Math.random()*4), w=3+Math.floor(Math.random()*5);
    const r0=1+Math.floor(Math.random()*(ccRows-h-2)), c0=1+Math.floor(Math.random()*(ccCols-w-2));
    if(placed.some(p=>r0<p.r1+2&&r0+h>p.r0-1&&c0<p.c1+2&&c0+w>p.c0-1))continue;
    placed.push({r0,c0,r1:r0+h-1,c1:c0+w-1,idx:placed.length});
    const t=kTime(r0+Math.floor(h/2),c0+Math.floor(w/2));
    const bold=Math.random()<0.3, isdark=Math.random()<0.35;
    mark(r0,c0,0b1001,bold,t,isdark); mark(r0,c0+w-1,0b0101,bold,t,isdark);
    mark(r0+h-1,c0,0b1010,bold,t,isdark); mark(r0+h-1,c0+w-1,0b0110,bold,t,isdark);
    for(let dc=1;dc<w-1;dc++){mark(r0,c0+dc,0b1100,bold,t,isdark);mark(r0+h-1,c0+dc,0b1100,bold,t,isdark);}
    for(let dr=1;dr<h-1;dr++){mark(r0+dr,c0,0b0011,bold,t,isdark);mark(r0+dr,c0+w-1,0b0011,bold,t,isdark);}
    {
      if(h<=2||w<=3){const ce=cc(r0+Math.floor(h/2),c0+1);if(ce&&!ce.lbl){ce.lbl=LBLS[Math.floor(Math.random()*20)];ce.marked=true;ce.dark=isdark;ce.time=t+0.02;}}
      else{const style=Math.floor(Math.random()*5),SIG='DACSQGNV',BITS='01011010110100101101';
        for(let dr=1;dr<h-1;dr++)for(let dc=1;dc<w-1;dc++){
          const ce=cc(r0+dr,c0+dc);if(!ce||ce.lbl)continue;
          let ch;
          if(style===0){ch=(dr+dc)%2===0?'+':'·';}
          else if(style===1){ch=BITS[(dr*(w-2)+dc)%BITS.length];}
          else if(style===2){ch='▪';}
          else if(style===3){ch=dc%2===1?SIG[(dr+dc)%8]:String(((dc-1)/2|0)%8);}
          else if(dc===1){ch=LBLS[Math.floor(Math.random()*20)];}
          else if(dc===2){ch=String(Math.floor(Math.random()*9)+1);}
          else continue;
          ce.lbl=ch;ce.marked=true;ce.dark=isdark;ce.time=t+0.02+dr*0.004+dc*0.001;
        }
      }
    }
    const icIdx=placed.length-1;
    for(let dr=1;dr<h-1;dr+=2){
      if(ok(r0+dr,c0-1)){mark(r0+dr,c0,0b0100,bold,t,isdark);mark(r0+dr,c0-1,0b1000,false,t+0.004,isdark);icPins.push({r:r0+dr,c:c0-1,icIdx,t:t+0.004,dark:isdark});}
      if(ok(r0+dr,c0+w)){mark(r0+dr,c0+w-1,0b1000,bold,t,isdark);mark(r0+dr,c0+w,0b0100,false,t+0.004,isdark);icPins.push({r:r0+dr,c:c0+w,icIdx,t:t+0.004,dark:isdark});}
    }
    for(let dc=1;dc<w-1;dc+=2){
      if(ok(r0-1,c0+dc)){mark(r0,c0+dc,0b0010,bold,t,isdark);mark(r0-1,c0+dc,0b0001,false,t+0.004,isdark);icPins.push({r:r0-1,c:c0+dc,icIdx,t:t+0.004,dark:isdark});}
      if(ok(r0+h,c0+dc)){mark(r0+h-1,c0+dc,0b0001,bold,t,isdark);mark(r0+h,c0+dc,0b0010,false,t+0.004,isdark);icPins.push({r:r0+h,c:c0+dc,icIdx,t:t+0.004,dark:isdark});}
    }
  }
  const N_STAMP=12+Math.floor(Math.random()*8);
  for(let si=0;si<N_STAMP;si++){
    const kind=Math.floor(Math.random()*4);
    const sh=kind===1?1:3+Math.floor(Math.random()*(kind===0?6:4));
    const sw=kind===1?8+Math.floor(Math.random()*14):5+Math.floor(Math.random()*9);
    const sr=1+Math.floor(Math.random()*(ccRows-sh-2)), sc=1+Math.floor(Math.random()*(ccCols-sw-2));
    const st=kTime(sr+sh/2,sc+sw/2)+0.10, sdark=Math.random()<0.35;
    for(let dr=0;dr<sh;dr++)for(let dc=0;dc<sw;dc++){
      if(!ok(sr+dr,sc+dc))continue;
      const ce=cc(sr+dr,sc+dc);if(ce.marked)continue;
      let ch;
      if(kind===0){ch='01'[(dr^dc)&1];if(dc%4===3)ch='·';}
      else if(kind===1){ch=dc%2===0?'▪':'·';}
      else if(kind===2){ch='0123456789ABCDEF'[Math.floor(Math.random()*16)];if(dc%3===2)ch='·';}
      else{ch=(dr+dc)%2===0?'╬':'·';}
      ce.lbl=ch;ce.marked=true;ce.dark=sdark;ce.time=st+dr*0.005+dc*0.001;
    }
  }
  const N_BUS=7+Math.floor(Math.random()*6);
  for(let bi=0;bi<N_BUS;bi++){
    const horiz=Math.random()<0.55, nLines=2+Math.floor(Math.random()*3), len=8+Math.floor(Math.random()*18);
    const br=1+Math.floor(Math.random()*(ccRows-nLines-1)), bc=1+Math.floor(Math.random()*(ccCols-len-1));
    const bt=kTime(br+nLines/2,bc+len/2)+0.06, bdark=Math.random()<0.3;
    for(let li=0;li<nLines;li++){
      if(horiz)routeH(br+li,bc,bc+len,false,bt+li*0.008,bdark);
      else routeV(br,br+len,bc+li,false,bt+li*0.008,bdark);
    }
  }
  const usedPins=new Set(), shuffled=[...icPins].sort(()=>Math.random()-0.5);
  for(let i=0;i<shuffled.length;i++){
    if(usedPins.has(i))continue;
    const p=shuffled[i];let bestJ=-1,bestD=30;
    for(let j=0;j<shuffled.length;j++){
      if(j===i||usedPins.has(j)||shuffled[j].icIdx===p.icIdx)continue;
      const d=Math.abs(p.r-shuffled[j].r)+Math.abs(p.c-shuffled[j].c);
      if(d<bestD&&d>2){bestD=d;bestJ=j;}
    }
    if(bestJ>=0){const q=shuffled[bestJ];routeL(p.r,p.c,q.r,q.c,false,Math.min(p.t,q.t)+0.025,p.dark||q.dark);usedPins.add(i);usedPins.add(bestJ);}
  }
  const allW=[];
  for(let i=0;i<shuffled.length;i++){
    if(usedPins.has(i))continue;
    const p=shuffled[i];if(!ok(p.r,p.c))continue;
    allW.push({r:p.r,c:p.c,dir:Math.floor(Math.random()*4),bold:false,dark:p.dark||false,maxLen:4+Math.floor(Math.random()*16),t:p.t+0.05,straight:0,minSt:3});
  }
  const N_EXTRA=80+Math.floor(Math.random()*50);
  for(let i=0;i<N_EXTRA;i++){const r=Math.floor(Math.random()*ccRows),c=Math.floor(Math.random()*ccCols);allW.push({r,c,dir:Math.floor(Math.random()*4),bold:false,dark:false,maxLen:6+Math.floor(Math.random()*18),t:kTime(r,c)+0.05,straight:0,minSt:3});}
  let step=0;const MAX=14000;
  while(allW.length&&step<MAX){
    step++;
    for(let wi=allW.length-1;wi>=0;wi--){
      const w=allW[wi];w.t+=0.00008;w.straight++;
      if(w.straight>=w.minSt){const rn=Math.random();if(rn<0.24){w.dir=(w.dir+1)&3;w.straight=0;}else if(rn<0.48){w.dir=(w.dir+3)&3;w.straight=0;}}
      const nr=w.r+DY[w.dir],nc=w.c+DX[w.dir];
      if(!ok(nr,nc)){w.dir=(w.dir+(Math.random()<.5?1:3))&3;w.straight=0;continue;}
      mark(w.r,w.c,MY[w.dir],w.bold,kTime(w.r,w.c)+w.t,w.dark);
      mark(nr,nc,OPP[w.dir],w.bold,kTime(nr,nc)+w.t,w.dark);
      w.r=nr;w.c=nc;
      if(--w.maxLen<=0){allW.splice(wi,1);continue;}
      if(Math.random()<0.018&&w.straight>3){const bd=(w.dir+(Math.random()<.5?1:3))&3;allW.push({r:w.r,c:w.c,dir:bd,bold:false,dark:w.dark,maxLen:4+Math.floor(Math.random()*12),t:w.t,straight:0,minSt:3});}
    }
    if(step%500===0&&step<MAX*.7){const r=Math.floor(Math.random()*ccRows),c=Math.floor(Math.random()*ccCols);allW.push({r,c,dir:Math.floor(Math.random()*4),bold:false,dark:false,maxLen:8+Math.floor(Math.random()*22),t:kTime(r,c),straight:0,minSt:3});}
  }
  for(let r=0;r<ccRows;r++)for(let c=0;c<ccCols;c++){
    const ce=cc(r,c);if(!ce.marked)continue;
    const bits=ce.rlud&0xF,n=(bits>>3&1)+(bits>>2&1)+(bits>>1&1)+(bits&1);
    if(n>=3&&Math.random()<0.25)ce.via=VIAS[Math.floor(Math.random()*VIAS.length)];
    if(n===2&&Math.random()<0.04&&!ce.lbl)ce.lbl=LBLS[20+Math.floor(Math.random()*13)];
  }
  let mx=0;for(const ce of ccGrid)if(ce.marked&&ce.time>mx)mx=ce.time;
  if(mx>0)for(const ce of ccGrid)if(ce.marked)ce.time/=mx;
  for(let r=0;r<ccRows;r++)for(let c=0;c<ccCols;c++){const ce=ccGrid[r*ccCols+c];ce._x=c*CC+CC*.5;ce._y=r*CC+CC*.62;}
  return ccGrid.filter(ce=>ce.marked).sort((a,b)=>a.time-b.time);
}

function buildCircuits(){
  ccSortedA=buildOneLayer(); ccSortedB=buildOneLayer();
  ccSortedC=buildOneLayer(); ccSortedD=buildOneLayer();
}

function drawCircuits(sorted,prog,ca,cb,bgColor){
  ctx.font=CFONT;ctx.textAlign='center';ctx.textBaseline='middle';
  const useBold=prog>0.40,useVia=prog>0.68;let cur=null;
  for(const ce of sorted){
    if(ce.time>prog)break;
    const col=ce.dark?cb:ca;
    if(bgColor&&col===bgColor)continue;
    if(col!==cur){ctx.fillStyle=cur=col;}
    if(ce.lbl){ctx.fillText(ce.lbl,ce._x,ce._y);continue;}
    ctx.fillText((useBold&&ce.bold?BOLD:THIN)[ce.rlud&0xF]||'\xB7',ce._x,ce._y);
    if(useVia&&ce.via)ctx.fillText(ce.via,ce._x,ce._y);
  }
}

const PX=[{sz:16,t0:0.10,t1:.46},{sz:8,t0:0.13,t1:.74},{sz:4,t0:0.16,t1:1}];
let pxBlocks,pxBlocksB,pxGlitch,BrightFn,BrightFn2;
const BrightPool=[];

function brightEarth(nx,ny){const ed=Math.sqrt((nx-.5)**2+((ny-.2)*1.5)**2);const earth=Math.exp(-ed*ed/0.052)*.88;const md=Math.sqrt((nx-.5)**2*.85+(ny-1.0)**2);const moon=md<0.9?Math.pow(Math.max(0,1-md/0.9),0.35)*.7:0;const s=Math.sin(nx*2311+ny*4271)*.5+.5;return Math.min(1,earth+moon+(s>.984?.5:0));}
function brightCross(nx,ny){const cx=Math.abs(nx-.5),cy=Math.abs(ny-.5);return Math.min(1,Math.max(0,1-Math.min(cx,cy)*9)*.9+Math.exp(-(cx*cx+cy*cy)*28)*.95);}
function brightVortex(nx,ny){const dx=nx-.5,dy=ny-.5,r=Math.sqrt(dx*dx+dy*dy),a=Math.atan2(dy,dx),sp=Math.pow(Math.max(0,1-r*1.6),.5);return Math.min(1,sp+(Math.sin(a*5-r*12)*.5+.5)*.6*sp);}
function brightRings(nx,ny){const dx=nx-.5,dy=ny-.5,r=Math.sqrt(dx*dx+dy*dy*1.3);return Math.pow(Math.max(0,Math.sin(r*18+.4)*.5+.5),1.5)*.92;}

const IMG_SKULL="data:image/jpeg;base64,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";
const IMG_HERO="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD//gAQTGF2YzYyLjI4LjEwMQD/2wBDAA4KCw0LCQ4NDA0QDw4RFiQXFhQUFiwgIRokNC43NjMuMjI6QVNGOj1OPjIySGJJTlZYXV5dOEVmbWVabFNbXVn/2wBDAQ8QEBYTFioXFypZOzI7WVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVlZWVn/wAARCABEAHgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDhYyF7A8d6VwAeAKgLEdKXeSeeau4rCEjcK6TzNL1TTrW2USpdxRhFIQKrOQB8x9MiuZqaEAOp9xUOHMKSvbyJL2zksrh4ZShZDglWyOmaq1ekj3ybgwwxxn0rRn8MyfZ/tFrcxXa7tu2EE0NqOkmOU4q1zAopxTZkN1FN70ymrEjj9wn1qOpX5gT61EKEJC4xSUGpYUO4P90Kc80xk9lbwMS90zqmMrsxkn3zRdy2zEi33FeOWUA1HMxl+X+6c59ai2Ed6AW4yilNFIQh60ClPWigYlORucZpBTh7U7ha5YWTauOvBGD2p8GoX1qmy3upo0zbarYGfWoUKjOfSmM2Bmqkk1qR6jCxJJY5JPU02ikqCyZ/9QlRVNIjC2jYqQCeCRwahIx9aEJbCd/WpEduhY4pgpc0xllFyOKHTAznvUccwXr/ACp0swbgfyq7qxGtyF6KaTRWZQHrSqCxwoJPoKQ9aASpypIPqKYGnDawx6dPLLcxiRSNsJyGfp0rODkM23gN2pCzN95ifqaAKVilKS6khI24xz65qI07PtTcGhDm7ig4p5bK/Qce1R4p4UkYHU0McG9jVkkuJNFtEljk8hSSjHoTz0rM3opwYiPbNXLmK9h0u1klZxbMxEY35Gee3as923tuIxSjaxjCWmnmK7hmBUbR780zNLRVF3uFFFFAgope1FIAPWkoPWjrQMKXNIRiigBQcUlAoNABTg2MY6im0UAnY0ZbUnToLiSaMiQnCK/zKeeo7VS2qkmJAxXH8NR9896mSUMNsh98k0LzErrcWaAKN0Zyo685NQYpySvGCEYqM0Eljk8k02MbiinU3FIGgNFKTRQJiHqaKKKAA0UUUAFL2oooGhKKKKBDifkUYH1ptFFAIKKKKACjNFFAwooooEf/2Q==";

function makeImgBrightness(dataUri){
  return new Promise(resolve=>{
    const img=new Image();
    img.onload=()=>{
      const SW=img.naturalWidth,SH=img.naturalHeight;
      const oc=Object.assign(document.createElement('canvas'),{width:SW,height:SH});
      oc.getContext('2d').drawImage(img,0,0,SW,SH);
      const d=oc.getContext('2d').getImageData(0,0,SW,SH).data;
      resolve((nx,ny)=>{const px=Math.min(SW-1,Math.floor(nx*SW)),py=Math.min(SH-1,Math.floor(ny*SH)),i=(py*SW+px)*4;return(d[i]*.299+d[i+1]*.587+d[i+2]*.114)/255;});
    };
    img.onerror=()=>resolve(null);
    img.src=dataUri;
  });
}

async function preloadBrightness(){
  BrightPool.push(brightEarth,brightCross,brightVortex,brightRings);
  for(const uri of [IMG_SKULL,IMG_HERO]){const fn=await makeImgBrightness(uri);if(fn)BrightPool.push(fn);}
}

function buildPixels(){
  pxBlocks=[];
  const bright=BrightFn||brightEarth;
  for(const{sz,t0,t1}of PX){
    const cols=Math.ceil(W/sz),rows=Math.ceil(H/sz),span=t1-t0;
    for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const br=bright((c+.5)/cols,(r+.5)/rows);const t=t0+span*(1-br*.94)+(Math.random()-.5)*.04;pxBlocks.push({x:c*sz,y:r*sz,sz,t:Math.max(0,Math.min(1,t))});}
  }
  pxBlocks.sort((a,b)=>a.t-b.t);
  pxBlocksB=[];
  const bright2=BrightFn2||brightCross;
  for(const{sz,t0,t1}of PX){
    const cols=Math.ceil(W/sz),rows=Math.ceil(H/sz),span=t1-t0;
    for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const br=bright2((c+.5)/cols,(r+.5)/rows);const t=t0+span*(1-br*.94)+(Math.random()-.5)*.04;pxBlocksB.push({x:c*sz,y:r*sz,sz,t:Math.max(0,Math.min(1,t))});}
  }
  pxBlocksB.sort((a,b)=>a.t-b.t);
  const maxRows=Math.ceil(H/4)+8;
  pxGlitch=new Float32Array(maxRows);
  let i=0;
  while(i<maxRows){const bh=1+Math.floor(Math.random()*12),extreme=Math.random()<0.12,mag=extreme?(30+Math.floor(Math.random()*32)):(2+Math.floor(Math.random()*22)),blocks=mag*(Math.random()<.5?1:-1);for(let j=0;j<bh&&i<maxRows;j++,i++)pxGlitch[i]=blocks;}
}

function drawPixels(blocks,prog,color){
  const gAmt=Math.max(0,1-prog/0.72);ctx.fillStyle=color;
  const epoch=Math.floor(Date.now()/190);
  function prng(a,b){const x=Math.sin(a*127.1+b*311.7)*43758.5453;return x-Math.floor(x);}
  for(const b of blocks){
    if(b.t>prog)break;
    const rowBand=Math.floor(b.y/b.sz),blockId=b.x/b.sz+rowBand*4096;
    if(gAmt>0.05&&prng(epoch*3+5,blockId)<gAmt*0.18)continue;
    const staticOff=Math.round(pxGlitch[rowBand]*gAmt)*b.sz,hasDyn=prng(epoch,rowBand)<0.12;
    const dynOff=hasDyn?Math.round((prng(epoch+1,rowBand)-.5)*6*gAmt)*b.sz:0;
    ctx.fillRect(((b.x+staticOff+dynOff)%W+W)%W,b.y,b.sz,b.sz);
  }
}

const T_BUILD=5500,T_ASCII_OUT=1000,T_HOLD=350,T_DECOMP=5000,T_CIRCUIT_OUT=1000;
const T_TOTAL=T_BUILD+T_ASCII_OUT+T_HOLD+T_DECOMP+T_CIRCUIT_OUT;
let animId=null,t0=null;

function tick(ts){
  if(t0===null)t0=ts;
  let e=ts-t0;
  if(e>=T_TOTAL){run();return;}  // loop seamlessly
  if(e<T_BUILD){
    const p=e/T_BUILD;
    ctx.fillStyle=BLACK;ctx.fillRect(0,0,W,H);
    drawPixels(pxBlocks,p,LIME);
    drawCircuits(ccSortedA,p,LIME,BLACK);
    drawCircuits(ccSortedB,p,BLACK,LIME);
  } else if((e-=T_BUILD)<T_ASCII_OUT){
    const p=e/T_ASCII_OUT;
    ctx.fillStyle=LIME;ctx.fillRect(0,0,W,H);
    drawCircuits(ccSortedB,1-p,BLACK,LIME,LIME);
  } else if((e-=T_ASCII_OUT)<T_HOLD){
    ctx.fillStyle=LIME;ctx.fillRect(0,0,W,H);
  } else if((e-=T_HOLD)<T_DECOMP){
    const p=e/T_DECOMP;
    ctx.fillStyle=LIME;ctx.fillRect(0,0,W,H);
    drawPixels(pxBlocksB,p,LIME);
    drawPixels(pxBlocks,p,BLACK);
    drawCircuits(ccSortedD,p,BLACK,LIME);
    drawCircuits(ccSortedC,p,LIME,BLACK);
  } else {
    e-=T_DECOMP;
    const p=e/T_CIRCUIT_OUT;
    ctx.fillStyle=LIME;ctx.fillRect(0,0,W,H);
    drawPixels(pxBlocksB,1.0,LIME);
    drawPixels(pxBlocks,1.0,BLACK);
    drawCircuits(ccSortedC,1-p,LIME,BLACK,BLACK);
  }
  animId=requestAnimationFrame(tick);
}

function run(){
  if(animId){cancelAnimationFrame(animId);animId=null;}
  resize();
  BrightFn=BrightPool.length?BrightPool[Math.floor(Math.random()*BrightPool.length)]:brightEarth;
  BrightFn2=BrightPool.length?BrightPool[Math.floor(Math.random()*BrightPool.length)]:brightCross;
  buildCircuits();
  buildPixels();
  t0=null;
  animId=requestAnimationFrame(tick);
}

window.addEventListener('load',async()=>{await preloadBrightness();run();});

})();
