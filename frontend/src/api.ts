export type Model = {id:string; label:string; version:string; ready:boolean; message:string};
export type Plane = 'axial'|'coronal'|'sagittal';
export type SeriesOption = {uid:string;label:string;number:string;slices:number;rows:number;columns:number;slice_thickness_mm:string};
export type Result = {series_options?:SeriesOption[];ignored_files?:number;preview_shape_xyz:[number,number,number]; default_indices:Record<Plane,number>; input_format:string; output_shape_xyz:[number,number,number]; model_label:string; model_version:string};
export type Job = {id:string; filename:string; status:'queued'|'preparing'|'running'|'completed'|'failed'|'awaiting_selection'; progress:number; message:string; model_label:string; model_version:string; result:Result|null; error_code:string|null};
export const PUBLIC_PREVIEW=import.meta.env.VITE_PUBLIC_PREVIEW==='true';
export const DIRECT_ACCESS=import.meta.env.VITE_AUTH_MODE==='guest';

const base = new URL(window.location.href);
base.pathname = '/api'; base.search=''; base.hash='';
export const API = ((import.meta as unknown as {env:{VITE_API_URL?:string}}).env.VITE_API_URL || base.toString()).replace(/\/$/,'');
export class ApiError extends Error {constructor(public status:number,message:string){super(message);}}
export const getToken=()=>sessionStorage.getItem('pet-demo-session')||localStorage.getItem('pet-demo-guest-session');
export function setToken(token:string|null){if(token)sessionStorage.setItem('pet-demo-session',token);else sessionStorage.removeItem('pet-demo-session');}
export function setGuestToken(token:string){setToken(token);localStorage.setItem('pet-demo-guest-session',token);}
export function expireSession(){setToken(null);window.dispatchEvent(new Event('pet-auth-expired'));}
export function logout(){setToken(null);localStorage.removeItem('pet-demo-guest-session');window.dispatchEvent(new Event('pet-auth-expired'));}
export async function apiFetch(url:string,init:RequestInit={}){
  const headers=new Headers(init.headers),token=getToken();if(token)headers.set('Authorization',`Bearer ${token}`);
  const response=await fetch(url,{...init,headers});
  if(response.status===401)expireSession();
  return response;
}

async function errorText(response:Response) {
  try {const body=await response.json();return typeof body.detail==='string'?body.detail:'Không thể thực hiện yêu cầu. Vui lòng thử lại.';}
  catch {return 'Không thể thực hiện yêu cầu. Vui lòng thử lại.';}
}
export async function getModels():Promise<Model[]> {
  const response=await apiFetch(`${API}/models`,{signal:AbortSignal.timeout(12000)});
  if(!response.ok) throw new ApiError(response.status,await errorText(response));
  return (await response.json()).models;
}
export async function getJob(id:string, signal?:AbortSignal):Promise<Job> {
  const response=await apiFetch(`${API}/jobs/${encodeURIComponent(id)}`,{signal:signal || AbortSignal.timeout(12000)});
  if(!response.ok) throw new ApiError(response.status,await errorText(response));
  return response.json();
}
export function upload(file:File, modelId:string, progress:(value:number)=>void):{promise:Promise<Job>;cancel:()=>void} {
  const controller=new AbortController();let current:XMLHttpRequest|null=null,id:string|null=null;
  async function json(url:string,init:RequestInit){const r=await apiFetch(url,{...init,signal:controller.signal});if(!r.ok)throw new ApiError(r.status,await errorText(r));return r.json();}
  const promise=(async()=>{
    const state=await json(`${API}/uploads`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,total_bytes:file.size,model_id:modelId})});
    id=state.id;let offset=state.offset;
    while(offset<file.size){
      const end=Math.min(offset+state.chunk_bytes,file.size);let answer:any;
      for(let attempt=0;attempt<3;attempt++){
        if(controller.signal.aborted)throw new DOMException('Đã hủy tải lên','AbortError');
        try{
          answer=await new Promise<any>((resolve,reject)=>{
            const request=new XMLHttpRequest();current=request;
            const abort=()=>request.abort();controller.signal.addEventListener('abort',abort,{once:true});
            const cleanup=()=>controller.signal.removeEventListener('abort',abort);
            request.open('PUT',`${API}/uploads/${id}`);request.setRequestHeader('Content-Type','application/octet-stream');
            request.setRequestHeader('Content-Range',`bytes ${offset}-${end-1}/${file.size}`);
            const token=getToken();if(token)request.setRequestHeader('Authorization',`Bearer ${token}`);
            request.upload.onprogress=e=>{if(e.lengthComputable)progress(Math.min(100,Math.round((offset+e.loaded)/file.size*100)));};
            request.onload=()=>{cleanup();let body;try{body=JSON.parse(request.responseText);}catch{reject(new Error('Không nhận được xác nhận tải lên.'));return;}if(request.status===401)expireSession();if(request.status>=200&&request.status<300)resolve(body);else reject(new ApiError(request.status,typeof body.detail==='string'?body.detail:'Không tải được CT.'));};
            request.onerror=()=>{cleanup();reject(new Error('Mất kết nối khi tải CT. Vui lòng thử lại.'));};
            request.onabort=()=>{cleanup();reject(new DOMException('Đã hủy tải lên','AbortError'));};
            request.send(file.slice(offset,end));
          });break;
        }catch(error){if(controller.signal.aborted||(error instanceof ApiError&&error.status<500)||attempt===2)throw error;await new Promise(r=>setTimeout(r,500*(attempt+1)));}
      }
      if(answer.offset<=offset||answer.offset>file.size)throw new Error('Tiến độ tải lên không hợp lệ.');
      offset=answer.offset;
    }
    progress(100);return json(`${API}/uploads/${id}/complete`,{method:'POST'});
  })();
  const cancel=()=>{controller.abort();current?.abort();if(id)void apiFetch(`${API}/uploads/${id}`,{method:'DELETE'}).catch(()=>{});};
  return {promise,cancel};
}

export async function resumeInput(id:string,uid?:string):Promise<Job>{
  const response=await apiFetch(`${API}/jobs/${encodeURIComponent(id)}/${uid?'select-series':'retry-input'}`,{
    method:'POST',headers:{'Content-Type':'application/json'},...(uid?{body:JSON.stringify({uid})}:{})});
  if(!response.ok)throw new ApiError(response.status,await errorText(response));
  return response.json();
}
