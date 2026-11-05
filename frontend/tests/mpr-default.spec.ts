import {test,expect} from '@playwright/test';

// Local synthetic fixtures exercise the result viewer without GPU inference,
// clinical uploads or changes to any running backend.
const jobId='11111111-1111-4111-8111-111111111111';
function volume(kind:string){
  const dimensions=[8,10,12],count=dimensions.reduce((a,b)=>a*b,1);
  const text=JSON.stringify({version:1,kind,dimensions,spacing:[3,3,3],origin:[0,0,0],direction:[-1,0,0,0,-1,0,0,0,1],coordinate_system:'LPS',dtype:'float32-le',voxel_order:'x-fast',decimation:1});
  const size=Math.ceil(Buffer.byteLength(text)/4)*4,buffer=Buffer.alloc(4+size+count*4,32);
  buffer.writeUInt32LE(size);buffer.write(text,4);
  for(let i=0;i<count;i++)buffer.writeFloatLE(kind==='ct'?-300+i:2000+i*10,4+size+i*4);
  return buffer;
}
async function openResult(page:any){
  const errors:string[]=[];page.on('pageerror',(e:Error)=>errors.push(e.message));
  await page.route('**/api/**',async(route:any)=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/auth/status'))return route.fulfill({json:{required:true,mode:'guest',upload_limit_mb:2048}});
    if(path.endsWith('/auth/guest'))return route.fulfill({json:{access_token:'synthetic-session'}});
    if(path.endsWith('/auth/session'))return route.fulfill({json:{username:'synthetic-browser'}});
    if(path.endsWith('/models'))return route.fulfill({json:{models:[{id:'qa',label:'Synthetic QA',version:'qa-version',ready:true,message:'OK'}]}});
    if(path.endsWith(`/jobs/${jobId}`))return route.fulfill({json:{id:jobId,filename:'synthetic-ct.zip',status:'completed',progress:100,message:'OK',model_label:'Synthetic QA',model_version:'qa-version',error_code:null,result:{preview_shape_xyz:[8,10,12],default_indices:{axial:6,coronal:5,sagittal:4},input_format:'NIfTI',output_shape_xyz:[8,10,12],model_label:'Synthetic QA',model_version:'qa-version'}}});
    if(path.includes('/volume/'))return route.fulfill({contentType:'application/octet-stream',body:volume(path.split('/').pop()!)});
    if(path.endsWith('/download'))return route.fulfill({contentType:'application/zip',body:Buffer.from('synthetic-download')});
    return route.fulfill({status:404,json:{detail:'Unexpected API route'}});
  });
  await page.goto(`/?job=${jobId}`);
  await expect(page.locator('.mpr-section')).toHaveAttribute('data-ready','true');
  return errors;
}

test('MPR is the only slice mode and opens by default; linked controls, download and reload',async({page})=>{
  const requests:string[]=[];page.on('request',r=>requests.push(r.url()));
  const errors=await openResult(page);
  const modes=page.getByRole('group',{name:'Chế độ xem ảnh'});
  await expect(modes.getByRole('button')).toHaveCount(3);
  await expect(modes.getByRole('button',{name:'MPR liên kết',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'3 mặt cắt',exact:true})).toHaveCount(0);
  await expect(page.locator('.mpr-panel canvas')).toHaveCount(9);
  const original=await page.locator('.mpr-probe').innerText();
  await page.getByLabel('Lát MPR Axial',{exact:true}).fill('2');
  await expect(page.locator('.mpr-probe')).not.toHaveText(original);
  const before=await page.getByLabel('Axial CT',{exact:true}).screenshot();
  await page.getByLabel('Cửa sổ MPR',{exact:true}).selectOption('lung');
  await expect.poll(async()=>Buffer.compare(before,await page.getByLabel('Axial CT',{exact:true}).screenshot())).not.toBe(0);
  await page.getByLabel('Độ đậm PET MPR',{exact:true}).fill('0');
  await expect.poll(()=>page.locator('.mpr-panel canvas').evaluateAll(elements=>{const [ct,,fusion]=elements as HTMLCanvasElement[];return ct.toDataURL()===fusion.toDataURL();})).toBeTruthy();
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Tải PET (.zip)'}).click();
  expect((await pending).suggestedFilename()).toMatch(/^PET_.*\.zip$/);
  await page.reload();await expect(page.locator('.mpr-section')).toHaveAttribute('data-ready','true');
  await page.screenshot({path:'../artifacts/screenshots/clinical-mpr-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'../artifacts/screenshots/clinical-mpr-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  expect(requests.filter(url=>url.includes('/preview/'))).toEqual([]);
  expect(errors).toEqual([]);
});

test('without WebGL2 the 3D and fusion modes direct users back to working linked MPR',async({page})=>{
  await page.addInitScript(()=>{
    const original=HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext=function(kind:string,...args:any[]){
      if(kind==='webgl2')return null;
      return (original as any).call(this,kind,...args);
    } as typeof original;
  });
  const errors=await openResult(page);
  for(const mode of ['Xem 3D','Chồng CT–PET']){
    await page.getByRole('button',{name:mode,exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('MPR liên kết');
    await page.getByRole('button',{name:'MPR liên kết',exact:true}).click();
    await expect(page.locator('.mpr-section')).toHaveAttribute('data-ready','true');
    await expect(page.locator('.mpr-panel canvas')).toHaveCount(9);
  }
  expect(errors).toEqual([]);
});


test('clinical theme: upload layout remains usable on desktop and mobile',async({page})=>{
  const errors=await openResult(page);
  await page.evaluate(()=>localStorage.removeItem('ct-pet-current-job'));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Tạo ảnh PET từ CT.'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Tạo ảnh PET',exact:true})).toBeDisabled();
  await page.screenshot({path:'../artifacts/screenshots/clinical-upload-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await expect(page.getByRole('button',{name:'Chọn file CT (.zip)',exact:false})).toBeVisible();
  await page.screenshot({path:'../artifacts/screenshots/clinical-upload-mobile.png',fullPage:true});
  await page.locator('input[type=file]').setInputFiles({name:'synthetic.zip',mimeType:'application/zip',buffer:Buffer.from('visual fixture only')});
  await expect(page.getByRole('button',{name:'Tạo ảnh PET',exact:true})).toBeEnabled();
  await expect(page.getByText('synthetic.zip',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});
