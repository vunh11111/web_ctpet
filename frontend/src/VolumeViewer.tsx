import vtkVolumeMapperConstants from '@kitware/vtk.js/Rendering/Core/VolumeMapper/Constants';
import {useEffect,useRef,useState} from 'react';
import {loadVolume} from './volumeData';
import {PetLegend} from './PetLegend';
import {RenderingEngine,Enums,volumeLoader,cache,init as initCore,type Types,type VolumeViewport3D} from '@cornerstonejs/core';
import {init as initTools,addTool,ToolGroupManager,TrackballRotateTool,PanTool,ZoomTool,Enums as ToolEnums} from '@cornerstonejs/tools';

export type ViewerMode='volume'|'fusion';
let initialization:Promise<void>|undefined;
function initialize(){return initialization??=(async()=>{await initCore();await initTools();[TrackballRotateTool,PanTool,ZoomTool].forEach(addTool);})().catch(e=>{initialization=undefined;throw e;});}
type Appearance={preset:'body'|'bone'|'soft'|'lung';petMax:number;opacity:number;petMode:'mip'|'volume'};
type Controller={appearance:(value:Appearance)=>void;reset:()=>void;zoom:(factor:number)=>void;rotate:(yaw:number,pitch?:number)=>void};

export default function VolumeViewer({jobId,mode}:{jobId:string;mode:ViewerMode}){
  const first=useRef<HTMLDivElement>(null),second=useRef<HTMLDivElement>(null);
  const control=useRef<Controller|null>(null);
  const [ready,setReady]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const [preset,setPreset]=useState<'body'|'bone'|'soft'|'lung'>('body'),[petMax,setPetMax]=useState(12000);
  const [opacity,setOpacity]=useState(.4),[petMode,setPetMode]=useState<'mip'|'volume'>('volume');
  const [spinning,setSpinning]=useState(false);
  useEffect(()=>{if(!spinning||!ready)return;let frame=0,last=0;const tick=(time:number)=>{if(last&&document.visibilityState==='visible'){control.current?.rotate(Math.min(time-last,80)*.015);}last=time;frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);},[spinning,ready]);
  const settings=useRef<Appearance>({preset,petMax,opacity,petMode});settings.current={preset,petMax,opacity,petMode};
  useEffect(()=>{control.current?.appearance({preset,petMax,opacity,petMode});},[preset,petMax,opacity,petMode]);
  useEffect(()=>{
    const abort=new AbortController();let disposed=false,engine:RenderingEngine|undefined,observer:ResizeObserver|undefined;
    const suffix=crypto.randomUUID(),groupId=`tools-${suffix}`,ids=[`ct-${suffix}`,`pet-${suffix}`],volumes:string[]=[];
    const cleanupListeners:(()=>void)[]=[];
    setReady(false);setError('');setSpinning(false);
    let released=false;
    const cleanup=()=>{if(released)return;released=true;control.current=null;observer?.disconnect();cleanupListeners.forEach(fn=>fn());const group=ToolGroupManager.getToolGroup(groupId);if(group){group.setToolDisabled(TrackballRotateTool.toolName);ToolGroupManager.destroyToolGroup(groupId);}engine?.destroy();for(const id of volumes){const volume=cache.getVolume(id);const images=volume?.imageIds?.slice()||[];cache.removeVolumeLoadObject(id);images.forEach(imageId=>{if(cache.getImage(imageId))cache.removeImageLoadObject(imageId,{force:true});});}};
    (async()=>{
      const probe=document.createElement('canvas');const gl=probe.getContext('webgl2');if(!gl)throw new Error('Máy này chưa hỗ trợ WebGL2. Vui lòng dùng MPR liên kết.');gl.getExtension('WEBGL_lose_context')?.loseContext();
      await initialize();if(disposed)return;
      const data=await Promise.all([loadVolume(jobId,'ct',abort.signal),loadVolume(jobId,'pet',abort.signal)]);if(disposed)return;
      const ct=data[0].header,pet=data[1].header;
      if(JSON.stringify([ct.dimensions,ct.spacing,ct.origin,ct.direction])!==JSON.stringify([pet.dimensions,pet.spacing,pet.origin,pet.direction]))throw new Error('CT và PET không cùng hệ tọa độ.');
      const volumeIds=data.map(({header,scalarData},i)=>{const volumeId=`local-${suffix}-${i}`;volumes.push(volumeId);volumeLoader.createLocalVolume(volumeId,{dimensions:header.dimensions,spacing:header.spacing,origin:header.origin,direction:header.direction,scalarData,metadata:{Modality:i===0?'CT':'PT',FrameOfReferenceUID:`frame-${suffix}`,BitsAllocated:32,BitsStored:32,HighBit:31,PixelRepresentation:1,PhotometricInterpretation:'MONOCHROME2',SamplesPerPixel:1,ImageOrientationPatient:Array.from(header.direction).slice(0,6),PixelSpacing:header.spacing.slice(0,2),Columns:header.dimensions[0],Rows:header.dimensions[1],voiLut:[],VOILUTFunction:'LINEAR'}});return volumeId;});
      engine=new RenderingEngine(`render-${suffix}`);
      const elements=mode==='fusion'?[first.current!]:[first.current!,second.current!];
      engine.setViewports(elements.map((element,i)=>({viewportId:ids[i],type:Enums.ViewportType.VOLUME_3D,element,defaultOptions:{background:[.025,.045,.055] as Types.Point3,orientation:Enums.OrientationAxis.CORONAL,parallelProjection:true}})));
      const viewports=elements.map((_,i)=>engine!.getViewport(ids[i]) as VolumeViewport3D);
      if(mode==='fusion')await viewports[0].setVolumes(volumeIds.map(volumeId=>({volumeId})),false);
      else await Promise.all(viewports.map((viewport,i)=>viewport.setVolumes([{volumeId:volumeIds[i]}],false)));
      if(disposed)return;
      const group=ToolGroupManager.createToolGroup(groupId)!;
      [TrackballRotateTool,PanTool,ZoomTool].forEach(tool=>group.addTool(tool.toolName,tool===ZoomTool?{configuration:{pinchToZoom:true}}:{}));
      group.setToolActive(TrackballRotateTool.toolName,{bindings:[{mouseButton:ToolEnums.MouseBindings.Primary},{numTouchPoints:1}]});
      group.setToolActive(PanTool.toolName,{bindings:[{mouseButton:ToolEnums.MouseBindings.Auxiliary}]});
      group.setToolActive(ZoomTool.toolName,{bindings:[{mouseButton:ToolEnums.MouseBindings.Secondary},{numTouchPoints:2}]});
      const stopSpin=()=>setSpinning(false);
      elements.forEach((element,i)=>{
        element.addEventListener('pointerdown',stopSpin);cleanupListeners.push(()=>element.removeEventListener('pointerdown',stopSpin));
        group.addViewport(ids[i],engine!.id);
        const wheel=(event:WheelEvent)=>{event.preventDefault();const camera=viewports[i].getCamera();viewports[i].setCamera({parallelScale:Math.max(.1,Math.min(10000,camera.parallelScale!*Math.exp(event.deltaY*.001)))});viewports[i].render();};
        const context=(e:Event)=>e.preventDefault();element.addEventListener('wheel',wheel,{passive:false});element.addEventListener('contextmenu',context);
        cleanupListeners.push(()=>{element.removeEventListener('wheel',wheel);element.removeEventListener('contextmenu',context);});
      });
      let syncing=false;
      if(mode==='volume')elements.forEach((element,i)=>{
        const synchronize=()=>{if(syncing||disposed)return;syncing=true;try{viewports[1-i].setCamera(viewports[i].getCamera());viewports[1-i].render();}finally{syncing=false;}};
        element.addEventListener(Enums.Events.CAMERA_MODIFIED,synchronize);cleanupListeners.push(()=>element.removeEventListener(Enums.Events.CAMERA_MODIFIED,synchronize));
      });
      const apply=(value:Appearance)=>{
        viewports.forEach((viewport,i)=>{
          viewport.getActors().forEach(entry=>{
            const isPet=mode==='fusion'?entry.referencedId===volumeIds[1]||entry.uid===volumeIds[1]:i===1;
            const actor=entry.actor as Types.VolumeActor,property=actor.getProperty();
            const color=property.getRGBTransferFunction(0),alpha=property.getScalarOpacity(0);color.removeAllPoints();alpha.removeAllPoints();
            if(isPet){
              [[0,0,0,0],[.15,.25,0,.4],[.4,.85,.12,.1],[.7,1,.65,0],[1,1,1,.8]].forEach(([x,r,g,b])=>color.addRGBPoint(x*value.petMax,r,g,b));
              const strength=mode==='fusion'?value.opacity:.85;
              alpha.addPoint(0,0);alpha.addPoint(value.petMax*.05,0);alpha.addPoint(value.petMax*.25,strength*.18);alpha.addPoint(value.petMax,strength);
            }else if(value.preset==='lung'){
              color.addRGBPoint(-1000,0,0,0);color.addRGBPoint(-850,.25,.45,.65);color.addRGBPoint(-500,.75,.85,.9);color.addRGBPoint(1000,1,.95,.85);
              alpha.addPoint(-1024,0);alpha.addPoint(-950,0);alpha.addPoint(-750,.025);alpha.addPoint(-450,.07);alpha.addPoint(-250,0);alpha.addPoint(200,0);alpha.addPoint(1000,.08);
            }else if(value.preset==='body'){
              color.addRGBPoint(-1024,0,0,0);color.addRGBPoint(-350,.58,.70,.76);color.addRGBPoint(-120,.82,.89,.90);color.addRGBPoint(150,.95,.96,.94);color.addRGBPoint(3000,1,1,.97);
              alpha.addPoint(-1024,0);alpha.addPoint(-400,0);alpha.addPoint(-240,.035);alpha.addPoint(-100,.12);alpha.addPoint(3071,.5);
            }else{
              const low=value.preset==='bone'?180:-150,high=value.preset==='bone'?1200:250;
              color.addRGBPoint(-1024,0,0,0);color.addRGBPoint(low,.35,.35,.35);color.addRGBPoint(high,1,1,1);
              alpha.addPoint(-1024,0);alpha.addPoint(low,0);alpha.addPoint(high,value.preset==='bone'?.85:.35);alpha.addPoint(3071,.95);
            }
            property.setScalarOpacityUnitDistance(0,3);property.setShade(!isPet);property.setAmbient(.25);property.setDiffuse(.75);property.setSpecular(.25);property.setSpecularPower(20);property.setInterpolationTypeToLinear();
            const mapper=actor.getMapper();mapper?.setSampleDistance(Math.min(...ct.spacing)*.4);mapper?.setMaximumSamplesPerRay(1000);mapper?.setAutoAdjustSampleDistances(false);mapper?.setBlendMode(isPet&&mode==='volume'&&value.petMode==='mip'?vtkVolumeMapperConstants.BlendMode.MAXIMUM_INTENSITY_BLEND:vtkVolumeMapperConstants.BlendMode.COMPOSITE_BLEND);
          });
          viewport.render();
        });
      };
      const rotate=(yaw:number,pitch=0)=>{
        const camera=viewports[0].getCamera(),center=Array.from(camera.focalPoint!),up=Array.from(camera.viewUp!);
        const cross=(a:number[],b:number[])=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
        const around=(vector:number[],axis:number[],degrees:number)=>{
          const length=Math.hypot(...axis);if(length<1e-8)return vector;
          const unit=axis.map(x=>x/length),angle=degrees*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
          const perpendicular=cross(unit,vector),dot=unit.reduce((sum,x,i)=>sum+x*vector[i],0);
          return vector.map((x,i)=>x*c+perpendicular[i]*s+unit[i]*dot*(1-c));
        };
        let offset=Array.from(camera.position!).map((x,i)=>x-center[i]);offset=around(offset,up,yaw);
        const right=cross(up,offset);offset=around(offset,right,pitch);
        const next={position:offset.map((x,i)=>x+center[i]) as Types.Point3,viewUp:around(up,right,pitch) as Types.Point3};
        viewports.forEach(viewport=>{viewport.setCamera(next);viewport.render();});
      };
      // Start from an oblique camera so the image is recognizably a spatial
      // volume. Keep a fixed home pose: reset must not compound rotations.
      viewports[0].resetCamera();rotate(30,12);
      const home=structuredClone(viewports[0].getCamera());home.parallelScale=home.parallelScale!*1.25;
      const reset=()=>{setSpinning(false);viewports.forEach(viewport=>{viewport.setCamera(home);viewport.render();});};
      observer=new ResizeObserver(()=>{if(!disposed){engine?.resize(true,false);viewports.forEach(v=>v.render());}});elements.forEach(el=>observer!.observe(el));
      const zoom=(factor:number)=>{const camera=viewports[0].getCamera();viewports[0].setCamera({parallelScale:Math.max(.1,Math.min(10000,camera.parallelScale!*factor))});viewports[0].render();};
      control.current={appearance:apply,reset,zoom,rotate};reset();apply(settings.current);setReady(true);
    })().catch(e=>{if(!disposed){setError(e instanceof Error?e.message:'Không dựng được ảnh 3D.');cleanup();}});
    return()=>{disposed=true;abort.abort();cleanup();};
  },[jobId,mode,attempt]);
  return <section className="volume-section" aria-label={mode==='fusion'?'Chồng CT–PET':'CT và PET 3D'}>
    <div className="volume-controls"><label>Hiển thị CT<select value={preset} onChange={e=>setPreset(e.target.value as 'body'|'bone'|'soft'|'lung')}><option value="body">Toàn khối cơ thể</option><option value="bone">Xương</option><option value="soft">Mô mềm</option><option value="lung">Phổi</option></select></label><label>Thang PET<select value={petMax} onChange={e=>setPetMax(Number(e.target.value))}><option value={5000}>0 – 5.000</option><option value={12000}>0 – 12.000</option><option value={32767}>Toàn thang</option></select></label>{mode==='volume'?<label>Dựng PET<select value={petMode} onChange={e=>setPetMode(e.target.value as 'mip'|'volume')}><option value="mip">MIP · cường độ tối đa</option><option value="volume">Khối 3D</option></select></label>:<label className="opacity-control">Độ đậm PET · {Math.round(opacity*100)}%<input aria-label="Độ đậm PET" type="range" min={0} max={1} step={.05} value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/></label>}<button className="button secondary" disabled={!ready} onClick={()=>control.current?.reset()}>Đặt lại góc nhìn</button></div>
    <div className="volume-zoom"><button className="small-button" disabled={!ready} aria-pressed={spinning} onClick={()=>setSpinning(value=>!value)}>{spinning?'Dừng xoay':'Xoay tự động'}</button><button className="small-button" disabled={!ready} onClick={()=>{setSpinning(false);control.current?.rotate(-30);}}>↶ Xoay trái</button><button className="small-button" disabled={!ready} onClick={()=>{setSpinning(false);control.current?.rotate(30);}}>↷ Xoay phải</button><button className="small-button" disabled={!ready} onClick={()=>{setSpinning(false);control.current?.rotate(0,20);}}>↥ Nghiêng khối</button><button className="small-button" disabled={!ready} onClick={()=>control.current?.zoom(.8)}>＋ Phóng to</button><button className="small-button" disabled={!ready} onClick={()=>control.current?.zoom(1.25)}>− Thu nhỏ</button></div>
    <PetLegend maximum={petMax}/><p className="volume-help">Khối 3D của toàn bộ vùng CT đã tải. Kéo trực tiếp lên khối để xoay trong không gian · Cuộn để phóng to · Chuột phải để zoom · Chuột giữa để di chuyển{mode==='volume'?' · Hai ảnh đồng bộ góc nhìn':''}.</p>
    {error?<div className="alert" role="alert">{error}<button className="text-button" onClick={()=>setAttempt(x=>x+1)}>Thử lại 3D</button></div>:!ready&&<p role="status">Đang tải CT/PET và dựng ảnh 3D…</p>}
    <div className={`volume-grid ${mode==='fusion'?'fusion-grid':''}`} data-ready={ready}>
      <div className="volume-panel"><h3>{mode==='fusion'?'CT + PET dự đoán':'CT gốc'}</h3><div className="volume-canvas" ref={first} aria-label={mode==='fusion'?'Khối chồng CT và PET':'Khối CT 3D'}/></div>
      {mode==='volume'&&<div className="volume-panel"><h3>PET dự đoán</h3><div className="volume-canvas" ref={second} aria-label="Khối PET 3D"/></div>}
    </div><p className="quiet-note">Volume xem trước, có thể giảm độ phân giải để hiển thị mượt. PET tổng hợp ở thang raw, chưa quy đổi SUV.</p>
  </section>;
}
