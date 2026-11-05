import {test,expect} from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

async function openDemo(page:any){
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Tạo ảnh PET từ CT.'})).toBeVisible();
  await expect(page.getByLabel('Mật khẩu',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Đăng xuất',exact:true})).toHaveCount(0);
}

for(const format of ['nifti','dicom']){
  test(`real baseline: ${format} ZIP → preview → download`,async({page})=>{
    const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await openDemo(page);
    await expect(page.getByRole('heading',{name:'Tạo ảnh PET từ CT.'})).toBeVisible();
    if(format==='nifti')await page.screenshot({path:'../artifacts/screenshots/upload-desktop.png',fullPage:true});
    const action=page.getByRole('button',{name:'Tạo ảnh PET',exact:true});
    await expect(action).toBeDisabled();
    await page.locator('input[type=file]').setInputFiles(path.resolve(`../data/qa/ct_${format}.zip`));
    await expect(action).toBeEnabled();await action.click();
    await expect(page.getByRole('progressbar')).toBeVisible();
    if(format==='nifti')await page.screenshot({path:'../artifacts/screenshots/processing-desktop.png',fullPage:true});
    await expect(page.getByRole('heading',{name:'Ảnh PET đã sẵn sàng.'})).toBeVisible({timeout:100000});
    await expect(page).toHaveURL(/\?job=[0-9a-f-]+/);
    await expect(page.locator('.mpr-section')).toHaveAttribute('data-ready','true');
    await expect(page.locator('.mpr-panel canvas')).toHaveCount(9);
    await expect(page.getByRole('button',{name:'MPR liên kết',exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(page.getByRole('button',{name:'3 mặt cắt',exact:true})).toHaveCount(0);
    const slider=page.getByLabel('Lát MPR Axial',{exact:true}),next=Number(await slider.inputValue())+1;
    const probe=await page.locator('.mpr-probe').innerText();
    await slider.focus();await slider.press('ArrowRight');
    await expect(slider).toHaveValue(String(next));
    await expect(page.locator('.mpr-probe')).not.toHaveText(probe);
    const readyDownload=page.waitForEvent('download');await page.getByRole('button',{name:'Tải PET (.zip)'}).click();
    const download=await readyDownload;await download.saveAs(`../data/qa/download_${format}.zip`);
    await page.reload();await expect(page.getByRole('heading',{name:'Ảnh PET đã sẵn sàng.'})).toBeVisible();
    if(format==='nifti'){
      await page.screenshot({path:'../artifacts/screenshots/results-desktop.png',fullPage:true});
      await page.setViewportSize({width:390,height:844});
      await page.screenshot({path:'../artifacts/screenshots/results-mobile.png',fullPage:true});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    }
    expect(errors).toEqual([]);
  });
}

test('friendly invalid-file feedback and mobile upload layout',async({page})=>{
  await page.setViewportSize({width:390,height:844});await openDemo(page);
  await page.locator('input[type=file]').setInputFiles({name:'not-a-zip.txt',mimeType:'text/plain',buffer:Buffer.from('bad')});
  await expect(page.getByRole('alert')).toContainText('Vui lòng chọn file ZIP');
  await expect(page.getByRole('button',{name:'Tạo ảnh PET',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../artifacts/screenshots/upload-mobile.png',fullPage:true});
});

test('invalid ZIP and missing CT produce actionable errors',async({page})=>{
  await openDemo(page);
  await page.locator('input[type=file]').setInputFiles({name:'broken.zip',mimeType:'application/zip',buffer:Buffer.from('not a zip')});
  await page.getByRole('button',{name:'Tạo ảnh PET',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Không đọc được ZIP');
  await page.locator('input[type=file]').setInputFiles(path.resolve('../data/qa/invalid_ct.zip'));
  await page.getByRole('button',{name:'Tạo ảnh PET',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Chưa tạo được ảnh PET'})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Không tìm thấy CT');
  await page.getByRole('button',{name:'Chọn lại CT'}).click();
  await expect(page.getByRole('heading',{name:'Tạo ảnh PET từ CT.'})).toBeVisible();
});

test('no login screen; private cases belong to each browser session',async({page,request,browser})=>{
  const real=JSON.parse(fs.readFileSync('../data/qa/real_case.json','utf8'));
  const api=process.env.E2E_API_URL||'http://127.0.0.1:8108/api';
  for(const suffix of ['', '/download','/preview/ct/axial?index=0']){
    const response=await request.get(`${api}/jobs/${real.id}${suffix}`);
    expect(response.status()).toBe(401);
  }
  await openDemo(page);
  await page.locator('input[type=file]').setInputFiles(path.resolve('../data/qa/ct_nifti.zip'));
  await page.getByRole('button',{name:'Tạo ảnh PET',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Ảnh PET đã sẵn sàng.'})).toBeVisible({timeout:100000});
  const id=new URL(page.url()).searchParams.get('job')!;
  const other=await browser.newContext({baseURL:process.env.E2E_BASE_URL||'http://127.0.0.1:3108'});const visitor=await other.newPage();
  await openDemo(visitor);
  const token=await visitor.evaluate(()=>sessionStorage.getItem('pet-demo-session'));
  const headers={Authorization:`Bearer ${token}`};
  for(const suffix of ['', '/download','/preview/ct/axial?index=0']){
    expect((await request.get(`${api}/jobs/${id}${suffix}`,{headers})).status()).toBe(404);
  }
  expect((await request.get(`${api}/uploads/${id}`,{headers})).status()).toBe(404);
  expect((await request.get(`${api}/jobs/${real.id}`,{headers})).status()).toBe(404);
  await visitor.goto(`/?job=${id}`);
  await expect(visitor.getByRole('heading',{name:'Tạo ảnh PET từ CT.'})).toBeVisible();
  await expect(visitor.locator('.mpr-panel canvas')).toHaveCount(0);
  await other.close();
  await page.reload();await expect(page.getByRole('heading',{name:'Ảnh PET đã sẵn sàng.'})).toBeVisible();
});

test('mixed DICOM export: choose CT series, reload, infer and download',async({page,request})=>{
  await openDemo(page);
  await page.locator('input[type=file]').setInputFiles(path.resolve('../data/qa/ct_mixed_dicom.zip'));
  await page.getByRole('button',{name:'Tạo ảnh PET',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Chọn series CT.'})).toBeVisible({timeout:40000});
  await expect(page.getByRole('radio')).toHaveCount(2);
  await expect(page.getByText('Đã bỏ qua 2 file PET hoặc ảnh phụ.',{exact:false})).toBeVisible();
  const action=page.getByRole('button',{name:'Tạo PET từ series đã chọn'});
  await expect(action).toBeDisabled();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Chọn series CT.'})).toBeVisible();
  await page.getByRole('radio',{name:/CT QA abdomen/}).check();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../artifacts/screenshots/dicom-series-selection-mobile.png',fullPage:true});
  await action.click();
  await expect(page.getByRole('heading',{name:'Ảnh PET đã sẵn sàng.'})).toBeVisible({timeout:100000});
  await expect(page.locator('.mpr-section')).toHaveAttribute('data-ready','true');
    await expect(page.locator('.mpr-panel canvas')).toHaveCount(9);
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Tải PET (.zip)'}).click();
  expect((await pending).suggestedFilename()).toMatch(/^PET_.*\.zip$/);
});
