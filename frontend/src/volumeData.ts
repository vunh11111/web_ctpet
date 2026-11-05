import type {Types} from '@cornerstonejs/core';
import {API,apiFetch} from './api';
export type Header={version:number;kind:string;dimensions:Types.Point3;spacing:Types.Point3;origin:Types.Point3;direction:Types.Mat3;coordinate_system:string;dtype:string;voxel_order:string;decimation:number};
export type Loaded={header:Header;scalarData:Float32Array};
export async function loadVolume(job:string,kind:'ct'|'pet',signal:AbortSignal):Promise<Loaded>{
  const response=await apiFetch(`${API}/jobs/${job}/volume/${kind}`,{signal});
  if(!response.ok)throw new Error('Chưa tải được volume. Vui lòng tải lại trang để thử lại.');
  const buffer=await response.arrayBuffer();if(buffer.byteLength<8)throw new Error('Volume không đầy đủ.');
  const size=new DataView(buffer).getUint32(0,true);
  if(size>16384||size+4>buffer.byteLength||size%4)throw new Error('Header volume không hợp lệ.');
  const header=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,4,size))) as Header;
  const count=header.dimensions?.reduce((a,b)=>a*b,1);
  if(header.version!==1||header.kind!==kind||header.dtype!=='float32-le'||header.coordinate_system!=='LPS'||header.voxel_order!=='x-fast'||!count||count>160**3||buffer.byteLength!==4+size+count*4)throw new Error('Dữ liệu 3D không hợp lệ.');
  return {header,scalarData:new Float32Array(buffer,4+size,count)};
}
