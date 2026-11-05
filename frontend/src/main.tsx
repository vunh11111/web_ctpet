import React, {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {API,PUBLIC_PREVIEW,ApiError,apiFetch,getJob,getModels,resumeInput,upload,type Job,type Model} from './api';
import {AuthGate} from './AuthGate';
import './styles.css';
const MprViewer=lazy(()=>import('./MprViewer'));
const VolumeViewer=lazy(()=>import('./VolumeViewer'));


function Icon({name,size=24}:{name:'upload'|'file'|'check'|'arrow'|'download'|'close'|'refresh'|'scan',size?:number}) {
  const paths={upload:<><path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 15v5h16v-5"/></>,file:<><path d="M14 3H5v18h14V8Z"/><path d="M14 3v5h5M8 13h8m-8 4h5"/></>,check:<path d="m5 12 4 4L19 6"/>,arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>,download:<><path d="M12 3v12m-5-5 5 5 5-5"/><path d="M4 16v5h16v-5"/></>,close:<path d="m6 6 12 12M6 18 18 6"/>,refresh:<><path d="M20 11a8 8 0 1 0-2 7M20 4v7h-7"/></>,scan:<><path d="M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5"/><path d="M7 12h10m-5-5v10"/></>};
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Steps({step}:{step:number}) {
  return <ol className="steps" aria-label="Các bước xử lý">{['Tải CT lên','Tạo ảnh PET','Xem kết quả'].map((label,i)=><li key={label} className={i===step?'current':i<step?'done':''} aria-current={i===step?'step':undefined}><span className="step-number">{i<step?<Icon name="check" size={18}/>:i+1}</span><span>{label}</span></li>)}</ol>;
}

function ResultView({job,onNew}:{job:Job;onNew:()=>void}) {
  const [mode,setMode]=useState<'volume'|'fusion'|'mpr'>('mpr');
  const [downloadError,setDownloadError]=useState('');
  const [downloading,setDownloading]=useState(false);
  async function downloadPet(){
    setDownloading(true);setDownloadError('');
    try{
      const response=await apiFetch(`${API}/jobs/${job.id}/download`);
      if(!response.ok)throw new Error('PET chưa tải xuống được. Vui lòng thử lại.');
      const blob=await response.blob(),url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download=`PET_${job.id.slice(0,8)}.zip`;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
    }catch(error){setDownloadError(error instanceof Error?error.message:'Không tải được PET.');}
    finally{setDownloading(false);}
  }
  return <div className="results">
    <div className="result-heading"><div><span className="eyebrow success"><Icon name="check" size={18}/> Đã hoàn tất</span><h1>Ảnh PET đã sẵn sàng.</h1><p className="file-caption">{job.filename}</p></div><div className="result-actions"><button className="button primary" onClick={downloadPet} disabled={downloading}><Icon name="download"/>{downloading?'Đang tải PET…':'Tải PET (.zip)'}</button><button className="button secondary" onClick={onNew}>Tạo ca mới</button></div></div>
    {downloadError&&<div className="alert" role="alert">{downloadError}</div>}
    <div className="viewer-modes" role="group" aria-label="Chế độ xem ảnh">{([{id:'mpr',label:'MPR liên kết'},{id:'volume',label:'Xem 3D'},{id:'fusion',label:'Chồng CT–PET'}] as const).map(item=><button key={item.id} aria-pressed={mode===item.id} className={`button ${mode===item.id?'primary':'secondary'}`} onClick={()=>setMode(item.id)}>{item.label}</button>)}</div>
    <p className="research-notice">Chỉ dùng nghiên cứu, không dùng chẩn đoán. PET là ảnh tổng hợp từ CT, không phải phép đo hoạt tính phóng xạ.</p>
    {mode==='mpr'?<Suspense fallback={<p role="status">Đang mở MPR…</p>}><MprViewer key={job.id} jobId={job.id}/></Suspense>:<Suspense fallback={<p role="status">Đang mở trình xem 3D…</p>}><VolumeViewer key={`${job.id}-${mode}`} jobId={job.id} mode={mode}/></Suspense>}
    <div className="result-note"><span>{job.model_label} · {job.model_version.slice(0,8)}</span><span>Ảnh PET được sinh bởi mô hình. Thang hiển thị chưa quy đổi SUV.</span></div>
  </div>;
}

function SeriesPicker({job,onResume,onNew}:{job:Job;onResume:(uid?:string)=>Promise<void>;onNew:()=>void}){
  const [uid,setUid]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const options=job.result?.series_options||[];
  async function submit(){setBusy(true);setError('');try{await onResume(uid);}catch(e){setError(e instanceof Error?e.message:'Chưa chọn được series.');}finally{setBusy(false);}}
  return <section className="center-card series-card"><span className="eyebrow">ĐÃ ĐỌC FILE CT</span><h1>Chọn series CT.</h1><p>File có {options.length} series CT. Chọn vùng chụp cần dùng để tạo PET.</p>
    <fieldset className="series-list" disabled={busy}><legend className="sr-only">Series CT cần xử lý</legend>{options.map((o,i)=><label key={o.uid} className={`series-option ${uid===o.uid?'selected':''}`}><input type="radio" name="ct-series" value={o.uid} checked={uid===o.uid} onChange={()=>setUid(o.uid)}/><span><strong>{o.label || `Series CT ${i+1}`}</strong><small>Series {o.number||i+1} · {o.slices} lát · {o.columns} × {o.rows}{o.slice_thickness_mm?` · Độ dày ${o.slice_thickness_mm} mm`:''}</small></span></label>)}</fieldset>
    {!!job.result?.ignored_files&&<p className="quiet-note">Đã bỏ qua {job.result.ignored_files} file PET hoặc ảnh phụ. Chỉ series CT bạn chọn được dùng để sinh PET.</p>}
    {error&&<p role="alert" className="field-error">{error}</p>}<button className="button primary" disabled={!uid||busy} onClick={submit}>{busy?'Đang tiếp tục…':'Tạo PET từ series đã chọn'}</button><button className="text-button" disabled={busy} onClick={onNew}>Chọn file CT khác</button>
  </section>;
}

function App({onLogout}:{onLogout?:()=>void}){
  const [models,setModels]=useState<Model[]>([]),[modelId,setModelId]=useState('');
  const [file,setFile]=useState<File|null>(null),[job,setJob]=useState<Job|null>(null);
  const [uploading,setUploading]=useState(false),[uploadProgress,setUploadProgress]=useState(0);
  const [error,setError]=useState(''),[connectionError,setConnectionError]=useState(''),[modelError,setModelError]=useState('');
  const [loadingModels,setLoadingModels]=useState(true),[restoring,setRestoring]=useState(true),[dragging,setDragging]=useState(false);
  const inputRef=useRef<HTMLInputElement>(null),cancelRef=useRef<(()=>void)|null>(null);
  const ready=models.filter(m=>m.ready),selected=models.find(m=>m.id===modelId);
  async function refreshModels(){
    if(PUBLIC_PREVIEW){setLoadingModels(false);return;}
    setLoadingModels(true);setModelError('');
    try{const list=await getModels();setModels(list);setModelId(id=>list.some(m=>m.id===id&&m.ready)?id:list.find(m=>m.ready)?.id||'');}
    catch{setModelError('Chưa kết nối được dịch vụ. Vui lòng thử lại sau ít phút.');}
    finally{setLoadingModels(false);}
  }
  useEffect(()=>{refreshModels();if(PUBLIC_PREVIEW){setRestoring(false);return;}const saved=new URLSearchParams(window.location.search).get('job')||localStorage.getItem('ct-pet-current-job');if(saved){getJob(saved).then(next=>{setJob(next);localStorage.setItem('ct-pet-current-job',next.id);}).catch(error=>{if(error instanceof ApiError&&error.status===404){localStorage.removeItem('ct-pet-current-job');window.history.replaceState(null,'',window.location.pathname);}else setError('Chưa mở lại được lượt xử lý gần nhất. Vui lòng tải lại trang để thử lại.');}).finally(()=>setRestoring(false));}else setRestoring(false);return()=>cancelRef.current?.();},[]);
  useEffect(()=>{
    if(!job||job.status==='completed'||job.status==='failed')return;
    let stopped=false;const controller=new AbortController();
    const poll=async()=>{try{const next=await getJob(job.id,AbortSignal.any([controller.signal,AbortSignal.timeout(12000)]));if(!stopped){setJob(next);setConnectionError('');}}catch{if(!stopped)setConnectionError('Kết nối đang gián đoạn. Hệ thống sẽ tự kết nối lại.');}};
    const timer=setInterval(poll,2000);return()=>{stopped=true;controller.abort();clearInterval(timer);};
  },[job?.id,job?.status]);
  function chooseFile(next:File|undefined){
    setError('');if(!next)return;if(!next.name.toLowerCase().endsWith('.zip')){setError('Vui lòng chọn file ZIP chứa CT DICOM hoặc NIfTI.');return;}if(next.size>2048*1024**2){setError('File ZIP tối đa 2 GB. Vui lòng chọn một series CT.');return;}setFile(next);
  }
  async function start(){
    if(PUBLIC_PREVIEW)return;
    if(!file||!modelId||uploading)return;
    setError('');setUploading(true);setUploadProgress(0);
    const task=upload(file,modelId,setUploadProgress);cancelRef.current=task.cancel;
    try{const created=await task.promise;setJob(created);localStorage.setItem('ct-pet-current-job',created.id);window.history.replaceState(null,'',`${window.location.pathname}?job=${created.id}`);}
    catch(error){if(!(error instanceof DOMException&&error.name==='AbortError'))setError(error instanceof Error?error.message:'Không tải được file.');}
    finally{setUploading(false);cancelRef.current=null;}
  }
  function reset(){setJob(null);setFile(null);setError('');setConnectionError('');localStorage.removeItem('ct-pet-current-job');window.history.replaceState(null,'',window.location.pathname);window.scrollTo({top:0,behavior:'smooth'});refreshModels();}
  async function resume(uid?:string){if(job){const next=await resumeInput(job.id,uid);setJob(next);setError('');}}
  const result=job?.status==='completed'&&job.result;
  const processing=uploading||(job&&job.status!=='completed'&&job.status!=='failed');
  const step=result?2:processing||job?.status==='failed'?1:0;
  return <><header className="site-header"><div className="brand"><span className="brand-icon"><Icon name="scan" size={25}/></span><span>CT <span className="brand-arrow">→</span> PET</span></div><div className="header-session"><span className="site-tag">Điện Biên <span>·</span> Bản thử nghiệm</span>{onLogout&&<button className="text-button" onClick={onLogout}>Đăng xuất</button>}</div></header>
    <main className={result?'wide':''}><Steps step={step}/>
    {PUBLIC_PREVIEW&&<div className="preview-notice" role="status"><strong>Bản xem trước giao diện</strong><p>Backend đang giữ nội bộ. Bạn có thể thử chọn file; file không được tải lên và chức năng tạo PET chưa được bật trên bản public.</p></div>}
    {restoring?<div className="restore" role="status">Đang mở lại lượt xử lý gần nhất…</div>:result?<ResultView job={job!} onNew={reset}/>:job?.status==='awaiting_selection'?<SeriesPicker job={job} onResume={resume} onNew={reset}/>:job?.status==='failed'?<section className="center-card error-card"><span className="status-icon error-icon">!</span><h1>Chưa tạo được ảnh PET</h1><p role="alert">{job.message}</p>{job.error_code==='INVALID_CT'&&<><button className="button primary" onClick={()=>{void resume().catch(e=>setError(e.message));}}>Đọc lại CT đã tải</button>{error&&<p role="alert" className="field-error">{error}</p>}</>}<button className="button primary" onClick={reset}><Icon name="refresh"/>Chọn lại CT</button></section>:processing?<section className="center-card processing-card" aria-live="polite"><div className="processing-icon"><Icon name="scan" size={38}/></div><span className="eyebrow">{uploading?'ĐANG TẢI CT':'ĐANG XỬ LÝ'}</span><h1>{uploading?'Đang tải ảnh CT lên…':job?.status==='queued'?'CT đã được tiếp nhận.':'Đang tạo ảnh PET…'}</h1><p>{uploading?'Vui lòng giữ cửa sổ này mở đến khi tải xong.':job?.message}</p><div className="progress-label"><span>{uploading?'Tiến độ tải lên':'Tiến độ xử lý'}</span><strong>{uploading?uploadProgress:job?.progress}%</strong></div><progress max="100" value={uploading?uploadProgress:job?.progress} aria-label={uploading?'Tiến độ tải CT':'Tiến độ tạo PET'}/><div className="processing-file"><Icon name="file"/><span>{job?.filename||file?.name}</span></div>{connectionError&&<p className="connection-note" role="status">{connectionError}</p>}{uploading?<button className="text-button" onClick={()=>cancelRef.current?.()}>Hủy tải lên</button>:<span className="quiet-note">Kết quả sẽ tự hiển thị khi hoàn tất.</span>}</section>:<section className="upload-section"><div className="intro"><span className="eyebrow">TỪ ẢNH CT ĐẾN PET</span><h1>Tạo ảnh PET từ CT.</h1><p>Chọn ảnh CT. Hệ thống sẽ xử lý<br className="desktop-break"/> và hiển thị kết quả để đối chiếu.</p></div>
    <div className="upload-card">{modelError?<div className="alert" role="alert">{modelError}<button className="text-button" onClick={refreshModels}>Kết nối lại</button></div>:!PUBLIC_PREVIEW&&!loadingModels&&ready.length===0?<div className="alert" role="status">Mô hình chưa sẵn sàng. Vui lòng liên hệ người quản lý demo.<button className="text-button" onClick={refreshModels}>Kiểm tra lại</button></div>:null}
    {models.length>1&&<label className="model-select">Mô hình<select value={modelId} onChange={e=>setModelId(e.target.value)}>{models.map(m=><option key={m.id} value={m.id} disabled={!m.ready}>{m.label}{m.ready?'':' · chưa sẵn sàng'}</option>)}</select></label>}
    <input ref={inputRef} type="file" accept=".zip,application/zip,application/x-zip-compressed" id="ct-file" className="sr-only" onChange={e=>{chooseFile(e.target.files?.[0]);e.target.value='';}} aria-label="Chọn file ZIP ảnh CT"/>
    <button type="button" className={`dropzone ${dragging?'dragging':''} ${file?'has-file':''}`} onClick={()=>inputRef.current?.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);chooseFile(e.dataTransfer.files[0]);}}><span className="upload-symbol"><Icon name={file?'file':'upload'} size={32}/></span><strong>{file?'Đã chọn ảnh CT':'Chọn file CT (.zip)'}</strong><span>{file?file.name:'Nhấn để chọn hoặc kéo thả file vào đây'}</span><small>{file?`${(file.size/1024**2).toLocaleString('vi-VN',{maximumFractionDigits:1})} MB · Nhấn để đổi file`:'DICOM hoặc NIfTI · Tối đa 2 GB'}</small></button>
    {error&&<p className="field-error" role="alert">{error}</p>}
    <button className="button primary start-button" disabled={!file||!selected?.ready||loadingModels} onClick={start}>Tạo ảnh PET<Icon name="arrow"/></button>
    <p className="upload-help">ZIP có thể chứa nhiều series DICOM.<br/>Bạn sẽ chọn series CT sau khi tải lên.<br/>Hoặc dùng một ảnh NIfTI 3D (.nii, .nii.gz).</p></div>
    <p className="model-caption">{PUBLIC_PREVIEW?'Bản public chưa kết nối dịch vụ xử lý CT/PET':loadingModels?'Đang kiểm tra mô hình…':selected?.ready?<><span className="ready-dot"/> {selected.label}</>:'Chưa có mô hình sẵn sàng'}</p></section>}
    </main><footer className="site-footer"><span>CT → PET · Điện Biên</span><span>Demo tạo ảnh PET bằng mô hình AI</span></footer></>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><AuthGate>{onLogout=><App onLogout={onLogout}/>}</AuthGate></React.StrictMode>);
