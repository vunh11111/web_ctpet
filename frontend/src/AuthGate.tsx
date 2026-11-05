import {useEffect,useState,type ReactNode} from 'react';
import {API,PUBLIC_PREVIEW,DIRECT_ACCESS,getToken,logout,setToken,setGuestToken} from './api';

export function AuthGate({children}:{children:(onLogout?:()=>void)=>ReactNode}){
  const [checking,setChecking]=useState(true),[required,setRequired]=useState(!PUBLIC_PREVIEW&&!DIRECT_ACCESS),[allowed,setAllowed]=useState(PUBLIC_PREVIEW);
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  async function check(){
    setChecking(true);setError('');
    try{
      const response=await fetch(`${API}/auth/status`,{signal:AbortSignal.timeout(12000)});if(!response.ok)throw new Error();
      const state=await response.json();setRequired(state.required);
      if(!state.required){setAllowed(true);return;}
      if(state.mode==='guest'){
        setRequired(false);
        const token=getToken(),headers:Record<string,string>=token?{Authorization:`Bearer ${token}`}:{ };
        if(token){
          const previous=await fetch(`${API}/auth/session`,{headers,signal:AbortSignal.timeout(12000)});
          if(previous.ok){const info=await previous.json();if(!info.username.startsWith('guest:')){setAllowed(true);return;}}
        }
        const guest=await fetch(`${API}/auth/guest`,{method:'POST',headers,signal:AbortSignal.timeout(12000)});
        if(!guest.ok)throw new Error();
        const session=await guest.json();setGuestToken(session.access_token);setAllowed(true);return;
      }
      if(getToken()){
        const session=await fetch(`${API}/auth/session`,{headers:{Authorization:`Bearer ${getToken()}`},signal:AbortSignal.timeout(12000)});
        if(session.status===401){setToken(null);localStorage.removeItem('pet-demo-guest-session');}
        setAllowed(session.ok);
      }
    }catch{setError('Chưa kết nối được máy chủ. Vui lòng thử kết nối lại.');}
    finally{setChecking(false);}
  }
  useEffect(()=>{if(PUBLIC_PREVIEW)return;check();const expired=()=>{setAllowed(false);setPassword('');check();};window.addEventListener('pet-auth-expired',expired);return()=>window.removeEventListener('pet-auth-expired',expired);},[]);
  async function login(e:React.FormEvent){
    e.preventDefault();setBusy(true);setError('');
    try{
      const signal=AbortSignal.timeout(15000);let response:Response|undefined;
      for(let attempt=0;attempt<3;attempt++){
        try{
          response=await fetch(`${API}/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password}),signal});
          if(![502,503,504].includes(response.status)||attempt===2)break;
        }catch(error){if(attempt===2||signal.aborted)throw new Error('Kết nối đang gián đoạn. Vui lòng thử đăng nhập lại.');}
        await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)));
      }
      if(!response)throw new Error('Chưa kết nối được máy chủ. Vui lòng thử lại.');
      const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Chưa đăng nhập được.');
      setToken(body.access_token);setPassword('');setAllowed(true);
    }catch(error){setError(error instanceof Error?error.message:'Chưa đăng nhập được.');}
    finally{setBusy(false);}
  }
  if(allowed)return children(required?logout:undefined);
  if(checking||!required||DIRECT_ACCESS)return <><header className="site-header"><div className="brand"><span className="brand-icon">+</span><span>CT → PET</span></div><span className="site-tag">Điện Biên · Bản thử nghiệm</span></header><main><section className="center-card"><h1>CT → PET Điện Biên</h1><p role="status">{checking?'Đang kết nối máy chủ…':error}</p>{!checking&&<button className="button primary" onClick={check}>Kết nối lại</button>}</section></main></>;
  return <><header className="site-header"><div className="brand"><span className="brand-icon">+</span><span>CT → PET</span></div><span className="site-tag">Điện Biên · Bản thử nghiệm</span></header><main><section className="center-card login-card"><span className="eyebrow">CT → PET ĐIỆN BIÊN</span><h1>Đăng nhập</h1><p>Đăng nhập để tải CT và xem ảnh PET.</p>{checking?<p role="status">Đang kết nối máy chủ…</p>:<form onSubmit={login}><label>Tên đăng nhập<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required maxLength={64}/></label><label>Mật khẩu<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required maxLength={128}/></label>{error&&<p className="field-error" role="alert">{error}</p>}<button className="button primary" type="submit" disabled={busy||!username||!password}>{busy?'Đang đăng nhập…':'Đăng nhập'}</button><button className="text-button" type="button" onClick={check}>Kết nối lại máy chủ</button></form>}</section></main></>;
}
