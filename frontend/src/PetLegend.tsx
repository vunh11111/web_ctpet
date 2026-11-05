// Shared piecewise-linear color map, identical to the volume transfer function.
export function petColor(t:number):number[]{
  const stops=[[0,0,0,0],[.15,.25,0,.4],[.4,.85,.12,.1],[.7,1,.65,0],[1,1,1,.8]];
  t=Math.max(0,Math.min(1,t));const end=stops.findIndex((s,i)=>i>0&&s[0]>=t),b=stops[end],a=stops[end-1];
  const f=(t-a[0])/(b[0]-a[0]);return a.slice(1).map((v,i)=>(v+(b[i+1]-v)*f)*255);
}
export function PetLegend({maximum}:{maximum:number}){return <div className="pet-legend" aria-label="Thang màu PET"><strong>PET · đơn vị tùy ý (không phải SUV)</strong><div className="pet-gradient"/><div className="pet-ticks"><span>0</span><span>{(maximum/2).toLocaleString('vi-VN')}</span><span>≥ {maximum.toLocaleString('vi-VN')}</span></div></div>;}
