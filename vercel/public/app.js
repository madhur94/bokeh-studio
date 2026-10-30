'use strict';
const $ = id => document.getElementById(id);
let pair = null, originalURL = null, depthURL = null, busy = false, revision = 0;
let loadingRevision = 0;
const objectURLs = [];
const defaults = {focus:'.22',range:'.18',blur:'24',feather:'3',levels:'6',direction:'bright',preset:'Natural'};
function message(text, type='') { $('status').hidden = !text; $('status').textContent = text; $('status').className = type; }
function releaseURLs() { for (const u of objectURLs) URL.revokeObjectURL(u); objectURLs.length=0; }
function objectURL(blob) { const u = URL.createObjectURL(blob); objectURLs.push(u); return u; }
function updateLabels() { for(const id of ['focus','range','blur','feather']) $(id+'-value').textContent = ['focus','range'].includes(id) ? Number($(id).value).toFixed(2) : $(id).value; }
function invalidate() {
  revision++; $('download').hidden=true; $('analysis').hidden=true; $('comparison').hidden=true;
  $('analysis-hint').hidden=false; $('compare-hint').hidden=false; $('render-state').textContent='READY TO CREATE';
  if(originalURL) { $('result-image').src=originalURL; $('result-image').alt='Original image preview'; }
}
function settings() { return {focus_depth:+$('focus').value,focus_range:+$('range').value,blur_strength:+$('blur').value,feathering:+$('feather').value,levels:+$('levels').value,bright_is_near:$('direction').value==='bright',smooth:$('smooth').checked}; }
function info(width,height) {
  $('image-info').replaceChildren();
  for(const [label,value] of [['Resolution',`${width} × ${height}`],['Focus depth',Number($('focus').value).toFixed(2)],['Focus range',Number($('range').value).toFixed(2)],['Blur strength',`${$('blur').value} px`]]) {
    const div=document.createElement('div'),small=document.createElement('small');small.textContent=label;div.append(small,document.createTextNode(value));$('image-info').append(div);
  }
}
function showPair() { $('empty').hidden=true; $('workspace').hidden=false;document.body.classList.add('loaded');$('result-image').src=originalURL;$('before').src=originalURL;$('input-depth').src=depthURL; }
function base64(buffer) { const bytes=new Uint8Array(buffer);let result='';for(let i=0;i<bytes.length;i+=32768)result+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(result); }
function dataBlob(data,mime) { const decoded=atob(data),bytes=new Uint8Array(decoded.length);for(let i=0;i<decoded.length;i++)bytes[i]=decoded.charCodeAt(i);return new Blob([bytes],{type:mime}); }
async function validateImage(file) {
  if(!file || !file.size || file.size>20*1024*1024) throw new Error('Choose a non-empty JPG or PNG smaller than 20 MB.');
  const signature=new Uint8Array(await file.slice(0,8).arrayBuffer());
  const png=signature[0]===137 && signature[1]===80 && signature[2]===78 && signature[3]===71;
  const jpeg=signature[0]===255 && signature[1]===216;
  if(!png&&!jpeg)throw new Error('Only valid JPG and PNG images are supported.');
  const bitmap=await createImageBitmap(file);
  if(bitmap.width*bitmap.height>24000000){bitmap.close();throw new Error('This image exceeds 24 megapixels. Resize it before uploading.');}
  return {bitmap,png,signature};
}
async function prepare(file,isDepth=false) {
  const {bitmap,png}=await validateImage(file);
  const sourceSize=`${bitmap.width} × ${bitmap.height}`;
  // Small depth files stay byte-exact, preserving grayscale and 16-bit PNG values.
  if(isDepth && file.size<=1200000){bitmap.close();return {blob:file,sourceSize,preserved:true};}
  if(isDepth && png){
    const header=new Uint8Array(await file.slice(0,25).arrayBuffer());
    if(header[24]===16){bitmap.close();throw new Error('This 16-bit depth PNG is too large for the Vercel upload. Resize it to under 1.2 MB while keeping 16-bit precision.');}
  }
  const scale=Math.min(1,900/Math.max(bitmap.width,bitmap.height));
  const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
  const context=canvas.getContext('2d');context.fillStyle='#111512';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,isDepth?'image/png':'image/jpeg',.94));
  if(!blob)throw new Error('Unable to prepare this image. Try another JPG or PNG.');
  return {blob,sourceSize,preserved:false};
}
async function acceptPair(rgbFile,depthFile,isSample=false) {
  const loadId=++loadingRevision;pair=null;invalidate();
  if(!rgbFile||!depthFile){message(!rgbFile?'Please upload an RGB image to continue.':'Please upload the corresponding depth map.');return;}
  message('Preparing your image pair…','busy');
  try {
    const [rgb,depth]=await Promise.all([prepare(rgbFile),prepare(depthFile,true)]);
    const [rgbData,depthData]=await Promise.all([rgb.blob.arrayBuffer(),depth.blob.arrayBuffer()]);
    if(loadId!==loadingRevision)return;
    const nextPair={rgb:base64(rgbData),depth:base64(depthData)};
    if(new Blob([JSON.stringify({...nextPair,settings:settings()})]).size>4200000)throw new Error('The prepared pair is too large for Vercel. Choose a smaller depth map.');
    releaseURLs();pair=nextPair;originalURL=objectURL(rgb.blob);depthURL=objectURL(depth.blob);
    $('rgb-info').textContent=`✓ ${rgb.sourceSize} · optimized for web`;
    $('depth-info').textContent=`✓ ${depth.sourceSize}${depth.preserved?' · original depth retained':' · aligned during processing'}`;
    showPair();info('≤900','≤900');
    message(isSample?'Sample pair loaded. Select Generate Bokeh.':'Image pair ready. Processing uses a maximum side of 900 px; RGB is optimized as JPEG for upload.');
  } catch(error) {if(loadId===loadingRevision)message(error.message,'error');}
}
async function loadSample() {
  const sampleRevision=++loadingRevision;pair=null;invalidate();
  try {
    $('controls').reset();for(const [id,value] of Object.entries(defaults))$(id).value=value;updateLabels();
    const responses=await Promise.all([fetch('/sample_images/botanical_rgb.png'),fetch('/sample_images/botanical_depth.png')]);
    if(responses.some(r=>!r.ok))throw new Error('The sample is unavailable. Upload your own image pair.');
    const blobs=await Promise.all(responses.map(r=>r.blob()));if(sampleRevision!==loadingRevision)return;await acceptPair(...blobs,true);
  } catch(error){if(sampleRevision===loadingRevision)message(error.message,'error');}
}
for(const id of ['rgb','depth'])$(id).addEventListener('change',()=>acceptPair($('rgb').files[0],$('depth').files[0]));
for(const id of ['focus','range','blur','feather','levels','direction','smooth'])$(id).addEventListener('input',()=>{if(['range','blur','feather'].includes(id))$('preset').value='Custom';updateLabels();invalidate();if(pair)message('Settings changed. Generate Bokeh to update the result.');});
$('preset').addEventListener('change',()=>{const presets={Natural:[24,3,.18],Portrait:[32,4,.14],Strong:[40,5,.10]};const p=presets[$('preset').value];if(p){$('blur').value=p[0];$('feather').value=p[1];$('range').value=p[2];}updateLabels();invalidate();});
$('sample').addEventListener('click',loadSample);$('empty-sample').addEventListener('click',loadSample);
$('reset').addEventListener('click',()=>{loadingRevision++;pair=null;originalURL=null;depthURL=null;releaseURLs();$('controls').reset();updateLabels();invalidate();$('workspace').hidden=true;$('empty').hidden=false;document.body.classList.remove('loaded');$('rgb-info').textContent='JPG or PNG · up to 20 MB';$('depth-info').textContent='Grayscale or RGB depth';message('');});
for(const tab of document.querySelectorAll('[role=tab]'))tab.addEventListener('click',()=>{for(const t of document.querySelectorAll('[role=tab]')){const selected=t===tab;t.setAttribute('aria-selected',String(selected));$(t.getAttribute('aria-controls')).hidden=!selected;}});
$('controls').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;if(!pair){message('Please upload both an RGB image and its corresponding depth map.','error');return;}
  busy=true;const version=revision;const button=$('generate');button.disabled=true;button.textContent='Generating…';message('Generating depth-aware Bokeh… The first request may take longer while the image engine starts.','busy');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),90000);
  try {
    const response=await fetch('/api/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...pair,settings:settings()}),signal:controller.signal});
    let result;try{result=await response.json();}catch{throw new Error(response.status===413?'The image pair is too large. Try smaller inputs.':'The image service could not respond. Please retry in a moment.');}
    if(!response.ok)throw new Error(result.error||'Unable to generate Bokeh. Please try again.');
    if(version!==revision)return;
    const url=objectURL(dataBlob(result.result,'image/png'));$('result-image').src=url;$('result-image').alt='Generated depth-aware Bokeh image';$('after').src=url;$('download').href=url;$('download').hidden=false;
    for(const [id,key] of [['normalized-depth','normalized'],['interpreted-depth','depth'],['focus-mask','mask']])$(id).src=objectURL(dataBlob(result[key],'image/jpeg'));
    $('analysis').hidden=false;$('analysis-hint').hidden=true;$('comparison').hidden=false;$('compare-hint').hidden=true;$('render-state').textContent='RENDER COMPLETE';info(result.width,result.height);message(`✓ Bokeh generated successfully · ${result.width} × ${result.height} · ${result.seconds} s`);
  } catch(error){if(version===revision)message(error.name==='AbortError'?'Processing timed out. Please retry with smaller images or Fast quality.':error.message,'error');}
  finally{clearTimeout(timer);busy=false;button.disabled=false;button.textContent='Generate Bokeh';}
});
// A prepared sample has no FileList, so validation is handled by the submit handler.
$('controls').noValidate=true;updateLabels();
