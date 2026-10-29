import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { notificationTarget, playStaffNotificationSound, showStaffBrowserNotification } from '../src/staffBrowserNotifications.mjs';

const task = '11111111-1111-4111-8111-111111111111';
test('notification target allows only a staff assignment ID', () => {
  assert.equal(notificationTarget({taskId:task}), `/staff?task=${task}`);
  assert.equal(notificationTarget({taskId:'https://evil.example'}), '/staff');
});

test('new in-app alerts can play a short browser sound', async t => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window');
  t.after(() => { if (original) Object.defineProperty(globalThis, 'window', original); else delete globalThis.window; });
  let started = false;
  class AudioContext {
    currentTime = 1;
    destination = {};
    async resume() {}
    async close() {}
    createOscillator() {
      return {
        frequency: { setValueAtTime() {} },
        connect() {},
        start() { started = true; },
        stop() {},
        addEventListener() {},
      };
    }
    createGain() {
      return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} };
    }
  }
  globalThis.window = { AudioContext };
  assert.equal(await playStaffNotificationSound(), true);
  assert.equal(started, true);
});

test('native browser alerts never prompt permission and safely fall back without a service worker', async t => {
  const original = Object.getOwnPropertyDescriptors(globalThis);
  t.after(() => { for (const key of ['window','navigator','Notification']) { if (original[key]) Object.defineProperty(globalThis,key,original[key]); else delete globalThis[key]; } });
  const notices = [];
  class NativeNotification { static permission='default'; constructor(title,options) { this.title=title;this.options=options;notices.push(this); } close() {} }
  globalThis.Notification=NativeNotification;
  globalThis.window={Notification:NativeNotification,focus:()=>{},location:{assign:path=>{ window.target=path; }}};
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{}});
  const item={id:'notice-1',title:'New assignment',message:'Prepare villa',taskId:task};
  assert.equal(await showStaffBrowserNotification(item,'staff-1'),false);
  assert.equal(notices.length,0);
  NativeNotification.permission='granted';
  assert.equal(await showStaffBrowserNotification(item,'staff-1'),true);
  assert.equal(notices[0].options.tag,'villa-staff-staff-1-notice-1');
  notices[0].onclick();
  assert.equal(window.target,`/staff?task=${task}`);
});

test('notification worker rejects external paths and focuses only the staff portal', async () => {
  const source=await readFile(new URL('../public/staff-notifications-sw.js',import.meta.url),'utf8');
  for (const path of [`/staff?task=${task}`,`https://evil.example/staff?task=${task}`]) {
    let callback,waiting,navigated;
    const staffClient={url:'https://villa.example/staff',navigate:async url=>{navigated=url;},focus:async()=>{}};
    const self={location:{origin:'https://villa.example'},addEventListener:(name,fn)=>{callback=fn;},clients:{matchAll:async()=>[staffClient],openWindow:async()=>assert.fail('Should reuse staff tab')}};
    vm.runInNewContext(source,{self,URL,URLSearchParams});
    callback({notification:{data:{path},close:()=>{}},waitUntil:promise=>{waiting=promise;}});
    await waiting;
    assert.equal(navigated,path.startsWith('https://evil')?'https://villa.example/staff':`https://villa.example/staff?task=${task}`);
  }
});
