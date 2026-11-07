'use strict';
const imageDialog=document.querySelector('#image-dialog');
const videoDialog=document.querySelector('#video-dialog');
const video=document.querySelector('#game-video');
const pictures=[...document.querySelectorAll('[data-lightbox]')];
let position=0;
function showImage(index){position=(index+pictures.length)%pictures.length;const link=pictures[position];document.querySelector('#large-image').src=link.href;document.querySelector('#large-image').alt=link.querySelector('img').alt;document.querySelector('#image-caption').textContent=link.dataset.caption;document.querySelector('#image-position').textContent=(position+1)+' / '+pictures.length;if(!imageDialog.open)imageDialog.showModal();}
pictures.forEach((link,index)=>link.addEventListener('click',event=>{event.preventDefault();showImage(index);}));
document.querySelector('#image-prev')?.addEventListener('click',()=>showImage(position-1));
document.querySelector('#image-next')?.addEventListener('click',()=>showImage(position+1));
imageDialog?.addEventListener('keydown',event=>{if(event.key==='ArrowRight'){event.preventDefault();showImage(position+1);}if(event.key==='ArrowLeft'){event.preventDefault();showImage(position-1);}});
document.querySelectorAll('[data-video]').forEach(button=>button.addEventListener('click',()=>{document.querySelector('#video-dialog-title').textContent=button.dataset.videoTitle;video.src=button.dataset.video;video.poster=button.dataset.videoPoster||'';document.querySelector('#video-fallback').href=button.dataset.video;document.querySelector('#video-error').hidden=true;videoDialog.showModal();video.play().catch(()=>{});}));
videoDialog?.addEventListener('close',()=>{video.pause();video.removeAttribute('src');video.load();});
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}}));
document.querySelectorAll('[data-scroll]').forEach(button=>button.addEventListener('click',()=>{const track=document.querySelector('#screenshot-track');track.scrollBy({left:track.clientWidth*.75*Number(button.dataset.scroll),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}));
if(/MicroMessenger/i.test(navigator.userAgent))document.querySelectorAll('.download-link').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();document.querySelector('#wechat-dialog').showModal();}));

video?.addEventListener('error',()=>{if(video.getAttribute('src'))document.querySelector('#video-error').hidden=false;});
