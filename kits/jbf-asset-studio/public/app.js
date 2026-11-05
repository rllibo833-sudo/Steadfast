const form=document.querySelector('#form');
const promptInput=document.querySelector('#prompt');
const submit=document.querySelector('#generate');
const status=document.querySelector('#status');
const result=document.querySelector('#result');
const download=document.querySelector('#download');
let style='game';
fetch('/api/contact').then(response=>response.json()).then(contact=>{
  if(contact.email){const email=document.querySelector('#email-contact');email.href=`mailto:${contact.email}?subject=${encodeURIComponent('Paket aset JBF Asset Studio')}`;email.textContent=`Email: ${contact.email}`;email.style.display='block';}
  if(contact.whatsapp){const whatsapp=document.querySelector('#whatsapp-contact');whatsapp.href=contact.whatsapp;whatsapp.target='_blank';whatsapp.rel='noreferrer';whatsapp.textContent='Chat WhatsApp';whatsapp.style.display='block';}
}).catch(()=>{});
document.querySelectorAll('.style').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('.style').forEach(item=>item.classList.toggle('active',item===button));
  style=button.dataset.style;
}));
form.addEventListener('submit',async event=>{
  event.preventDefault();
  const prompt=promptInput.value.trim();
  if(prompt.length<4){status.textContent='Tulis deskripsi minimal 4 karakter.';status.className='status error';return;}
  submit.disabled=true;submit.textContent='Sedang membuat…';status.textContent='Membuat gambar. Biasanya perlu beberapa saat.';status.className='status';download.style.display='none';
  try{
    const response=await fetch('/api/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({prompt,style})});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||'Gagal membuat gambar. Coba lagi nanti.');}
    const blob=await response.blob();const objectUrl=URL.createObjectURL(blob);const image=document.createElement('img');image.alt='Gambar hasil generasi JBF Asset Studio';image.src=objectUrl;result.replaceChildren(image);download.href=objectUrl;download.style.display='block';status.textContent=`Selesai. Sisa gratis hari ini: ${response.headers.get('x-images-remaining')??'—'}.`;status.className='status ok';
  }catch(error){status.textContent=String(error.message||error);status.className='status error';}
  finally{submit.disabled=false;submit.textContent='Buat gambar gratis';}
});
