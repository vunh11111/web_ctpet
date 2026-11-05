import {useEffect,useRef,useState} from 'react';
import {loadVolume,type Loaded} from './volumeData';
import {PetLegend,petColor} from './PetLegend';
type Point=[number,number,number];
const planes=[{title:'Axial',axis:2,u:0,v:1,top:'A',bottom:'P',left:'R',right:'L'},
  {title:'Coronal',axis:1,u:0,v:2,top:'S',bottom:'I',left:'R',right:'L'},
  {title:'Sagittal',axis:0,u:1,v:2,top:'S',bottom:'I',left:'P',right:'A'}];
const offset=(p:number[],d:number[])=>p[0]+d[0]*(p[1]+d[1]*p[2]);
function Panel({data,point,setPoint,plane,kind,level,width,maximum,opacity}:{data:Loaded[];point:Point;setPoint:(p:Point)=>void;plane:typeof planes[number];kind:'CT'|'PET'|'Fusion';level:number;width:number;maximum:number;opacity:number}){
  const ref=useRef<HTMLCanvasElement>(null);const {dimensions:d,spacing}=data[0].header;
  const w=d[plane.u],h=d[plane.v],scale=Math.min(350/(w*spacing[plane.u]),350/(h*spacing[plane.v]));
  const dw=w*spacing[plane.u]*scale,dh=h*spacing[plane.v]*scale,ox=(384-dw)/2,oy=(384-dh)/2;
  useEffect(()=>{
    const ctx=ref.current!.getContext('2d')!,image=new ImageData(w,h);
    for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      const p=[...point];p[plane.u]=x;p[plane.v]=h-1-y;const index=offset(p,d);
      const gray=Math.max(0,Math.min(255,(data[0].scalarData[index]-level+width/2)/width*255));
      const t=Math.max(0,data[1].scalarData[index]/maximum),color=petColor(t),a=kind==='PET'?1:kind==='Fusion'?opacity*Math.min(1,t/.25):0;
      const i=(y*w+x)*4;for(let c=0;c<3;c++)image.data[i+c]=gray*(1-a)+color[c]*a;image.data[i+3]=255;
    }
    const temporary=document.createElement('canvas');temporary.width=w;temporary.height=h;temporary.getContext('2d')!.putImageData(image,0,0);
    ctx.fillStyle='#071018';ctx.fillRect(0,0,384,384);ctx.imageSmoothingEnabled=true;ctx.drawImage(temporary,ox,oy,dw,dh);
    const cx=ox+(point[plane.u]+.5)*dw/w,cy=oy+(h-.5-point[plane.v])*dh/h;
    ctx.strokeStyle='#39efcf';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(cx,oy);ctx.lineTo(cx,oy+dh);ctx.moveTo(ox,cy);ctx.lineTo(ox+dw,cy);ctx.stroke();
    ctx.font='14px sans-serif';ctx.fillStyle='white';ctx.textAlign='center';ctx.fillText(plane.top,192,15);ctx.fillText(plane.bottom,192,379);ctx.fillText(plane.left,10,192);ctx.fillText(plane.right,374,192);
    const mm=Math.min(50,Math.floor(w*spacing[plane.u]/3));ctx.strokeStyle='white';ctx.beginPath();ctx.moveTo(24,350);ctx.lineTo(24+mm*scale,350);ctx.stroke();ctx.textAlign='left';ctx.fillText(`${mm} mm`,24,343);
  },[data,point,plane,kind,level,width,maximum,opacity,d,w,h,dw,dh,ox,oy,scale,spacing]);
  function select(event:React.PointerEvent<HTMLCanvasElement>){const box=event.currentTarget.getBoundingClientRect(),x=(event.clientX-box.left)*384/box.width,y=(event.clientY-box.top)*384/box.height;if(x<ox||x>=ox+dw||y<oy||y>=oy+dh)return;const next=[...point] as Point;next[plane.u]=Math.min(w-1,Math.floor((x-ox)/dw*w));next[plane.v]=h-1-Math.min(h-1,Math.floor((y-oy)/dh*h));setPoint(next);}
  return <div className="mpr-panel"><h4>{kind==='Fusion'?'CT + PET':kind}</h4><canvas ref={ref} width={384} height={384} aria-label={`${plane.title} ${kind}`} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);select(e);}} onPointerMove={e=>{if(e.buttons===1)select(e);}}/></div>;
}
export default function MprViewer({jobId}:{jobId:string}){
  const [data,setData]=useState<Loaded[]|null>(null),[error,setError]=useState(''),[point,setPoint]=useState<Point>([0,0,0]);
  const [level,setLevel]=useState(40),[width,setWidth]=useState(400),[maximum,setMaximum]=useState(12000),[opacity,setOpacity]=useState(.4);
  useEffect(()=>{const abort=new AbortController();setData(null);setError('');Promise.all([loadVolume(jobId,'ct',abort.signal),loadVolume(jobId,'pet',abort.signal)]).then(value=>{
    if(abort.signal.aborted)return;const [ct,pet]=value.map(v=>v.header);
    if(JSON.stringify([ct.dimensions,ct.spacing,ct.origin,ct.direction])!==JSON.stringify([pet.dimensions,pet.spacing,pet.origin,pet.direction]))throw new Error('CT/PET khác hình học.');
    // The serving adapter provides axis-aligned RAS. Reject other orientations
    // instead of displaying misleading anatomical labels.
    if(ct.direction.some((n,i)=>Math.abs(n-[-1,0,0,0,-1,0,0,0,1][i])>1e-5))throw new Error('MPR cần dữ liệu xem trước chuẩn hóa RAS. Vui lòng liên hệ người quản lý demo để kiểm tra ca này.');
    setPoint(ct.dimensions.map(n=>Math.floor(n/2)) as Point);setData(value);
  }).catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();},[jobId]);
  if(error)return <p role="alert">{error}</p>;if(!data)return <p role="status">Đang tải MPR liên kết…</p>;
  const header=data[0].header,index=offset(point,header.dimensions),world=header.origin.map((n,i)=>n+point.reduce((sum,p,j)=>sum+p*header.spacing[j]*header.direction[j*3+i],0));
  return <section className="mpr-section" data-ready="true"><p>Chạm hoặc kéo trên ảnh để di chuyển crosshair đồng bộ CT, PET và ba mặt phẳng.</p>
    <div className="volume-controls"><label>Cửa sổ MPR<select aria-label="Cửa sổ MPR" defaultValue="soft" onChange={e=>{const [l,w]=({soft:[40,400],lung:[-600,1500],bone:[400,1800]} as Record<string,number[]>)[e.target.value];setLevel(l);setWidth(w);}}><option value="soft">Mô mềm</option><option value="lung">Phổi</option><option value="bone">Xương</option></select></label>
    <label>Level · {level} HU<input aria-label="Level HU" type="range" min={-1000} max={1500} value={level} onChange={e=>setLevel(+e.target.value)}/></label><label>Width · {width} HU<input aria-label="Width HU" type="range" min={1} max={4000} value={width} onChange={e=>setWidth(+e.target.value)}/></label>
    <label>Thang PET MPR<select value={maximum} onChange={e=>setMaximum(+e.target.value)}>{[5000,12000,32767].map(n=><option key={n} value={n}>{n.toLocaleString('vi-VN')}</option>)}</select></label><label>Độ đậm PET MPR<input aria-label="Độ đậm PET MPR" type="range" min={0} max={1} step={.05} value={opacity} onChange={e=>setOpacity(+e.target.value)}/></label></div>
    <PetLegend maximum={maximum}/><p className="mpr-probe" aria-live="polite">Crosshair: CT {data[0].scalarData[index].toFixed(1)} HU · PET {data[1].scalarData[index].toFixed(1)} đơn vị tùy ý · LPS ({world.map(n=>n.toFixed(1)).join(', ')}) mm</p>
    {planes.map(plane=><section key={plane.title}><h3>{plane.title} · lát {point[plane.axis]+1}/{header.dimensions[plane.axis]}</h3><div className="mpr-grid">{(['CT','PET','Fusion'] as const).map(kind=><Panel key={kind} {...{data,point,setPoint,plane,kind,level,width,maximum,opacity}}/>)}</div><input className="mpr-slice" aria-label={`Lát MPR ${plane.title}`} type="range" min={0} max={header.dimensions[plane.axis]-1} value={point[plane.axis]} onChange={e=>{const p=[...point] as Point;p[plane.axis]=+e.target.value;setPoint(p);}}/></section>)}
    <p className="quiet-note">MPR từ volume xem trước {header.spacing.map(n=>n.toFixed(1)).join(' × ')} mm; giá trị tại crosshair là mẫu preview, không phải dữ liệu gốc để định lượng. Nội suy hiển thị không khôi phục chi tiết đã mất.</p></section>;
}
