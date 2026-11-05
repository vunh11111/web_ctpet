import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:120000,expect:{timeout:15000},workers:1,use:{baseURL:process.env.E2E_BASE_URL||'http://127.0.0.1:3108',viewport:{width:1440,height:1000},screenshot:'only-on-failure'},reporter:'list'});
