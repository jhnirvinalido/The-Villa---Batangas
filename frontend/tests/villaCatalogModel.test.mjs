import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeVillaCatalogRow } from '../src/villaCatalogModel.mjs';

test('saved photos survive repeated normalization when reopening the editor',()=>{
  const row={id:'villa-1',title:'Villa 1',image_url:'https://storage.test/cover.jpg',image_urls:['https://storage.test/cover.jpg','https://storage.test/room.jpg'],landing_title:'Pool Villa',guest_label:'8 guests',stay_hours:'22 hours',short_description:'Private villa',updated_at:'2026-10-20T12:00:00Z'};
  const saved=normalizeVillaCatalogRow(row);
  assert.deepEqual(normalizeVillaCatalogRow(saved),saved);
  assert.deepEqual(normalizeVillaCatalogRow(normalizeVillaCatalogRow(saved)).imageUrls,row.image_urls);
});
test('camelCase editor galleries and legacy single images are retained',()=>{
  assert.deepEqual(normalizeVillaCatalogRow({imageUrls:['one.jpg','two.jpg'],imageUrl:'one.jpg'}).imageUrls,['one.jpg','two.jpg']);
  assert.deepEqual(normalizeVillaCatalogRow({image_url:'cover.jpg'}).imageUrls,['cover.jpg']);
  assert.deepEqual(normalizeVillaCatalogRow({imageUrl:'cover.jpg'}).imageUrls,['cover.jpg']);
});
test('explicit removal of all photos stays empty instead of restoring the previous cover',()=>{
  for (const row of [{image_urls:[],image_url:'old.jpg'},{imageUrls:[],imageUrl:'old.jpg'}]) {
    const saved=normalizeVillaCatalogRow(row);
    assert.deepEqual(saved.imageUrls,[]);
    assert.equal(saved.imageUrl,'');
    assert.deepEqual(normalizeVillaCatalogRow(saved).imageUrls,[]);
  }
});
test('removing a photo preserves remaining photos and makes the first one the cover',()=>{
  const saved=normalizeVillaCatalogRow({imageUrls:['room.jpg','pool.jpg'],imageUrl:'removed-cover.jpg'});
  assert.equal(saved.imageUrl,'room.jpg');
  assert.deepEqual(normalizeVillaCatalogRow(saved).imageUrls,['room.jpg','pool.jpg']);
});
