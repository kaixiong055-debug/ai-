'use strict';
(() => {
  const $ = (selector, root=document) => root.querySelector(selector);
  const $$ = (selector, root=document) => [...root.querySelectorAll(selector)];
  const state = {view:'games', session:null, games:[], game:null, settings:null, dirty:false, q:'', status:'', page:1, loadId:0, busy:false, uploads:0};
  const content = $('#content');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const safeMedia = value => {
    const text=String(value || '').trim();
    if (/^\/media\/[a-zA-Z0-9._/-]+$/.test(text) && !text.includes('..')) return text;
    try { const u=new URL(text); return u.protocol==='https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; }
  };
  const gamePath = game => '/games/'+encodeURIComponent(game.slug || game.id)+'/';
  const previewPath = game => '/admin/preview/'+encodeURIComponent(game.id);
  function notify(message, kind='success') {
    const notice=$('#notice'); notice.textContent=message; notice.className='notice '+kind; notice.hidden=false;
    if(kind==='error') notice.scrollIntoView({block:'nearest',behavior:'smooth'});
  }
  function clearNotice(){ $('#notice').hidden=true; }
  function setDirty(value=true){state.dirty=value; const hint=$('#change-hint');if(hint)hint.textContent=value?'有未保存的修改':'已与服务器同步';}
  function leaveAllowed(){if(state.busy || state.uploads){notify('正在保存或上传，请等待完成后再切换页面。','error');return false;}return !state.dirty || window.confirm('有尚未保存的修改，确定离开当前页面吗？');}
  function lockForm(form){const controls=$$('input,textarea,select,button',form).map(element=>({element,disabled:element.disabled}));controls.forEach(({element})=>element.disabled=true);return ()=>controls.forEach(({element,disabled})=>{if(element.isConnected)element.disabled=disabled;});}
  async function api(path, options={}) {
    const opts={credentials:'same-origin',...options,headers:{...(options.headers||{})}};
    if(opts.body && !(opts.body instanceof FormData)){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body);}
    if(opts.method && opts.method!=='GET' && state.session) opts.headers[state.session.headerName]=state.session.token;
    let response;
    try {response=await fetch(path,opts);} catch {throw new Error('无法连接服务器，请检查网络后重试。未保存的修改仍保留在页面中。');}
    if(response.status===401 || (response.redirected && new URL(response.url).pathname==='/login')) {
      const error=new Error('登录已过期，请先保存好未提交的内容，再重新登录。');error.expired=true;throw error;
    }
    if(response.status===204)return null;
    const type=response.headers.get('content-type')||'';
    const data=type.includes('json')?await response.json():null;
    if(!response.ok){
      if(response.status===409)throw new Error(data?.message || '这份资料已被更新。当前修改尚未保存，请重新打开最新版本后再编辑。');
      if(response.status===403)throw new Error('安全验证失败或登录已过期，请重新登录后重试。当前修改尚未保存。');
      throw new Error(data?.message || data?.detail || `操作失败（${response.status}），请稍后重试。`);
    }
    if(data===null)throw new Error('服务器返回了无法识别的响应，请刷新后重试。');
    return data;
  }
  function report(error){
    notify(error.message || '操作失败，请稍后重试。','error');
    if(error.expired){const link=document.createElement('a');link.href='/login';link.target='_blank';link.rel='noopener';link.textContent=' 在新窗口重新登录';$('#notice').append(link);}
  }
  function setView(view, title){
    state.view=view; $('#view-title').textContent=title;document.title=title+' · 游选工作台';
    $$('.nav-item').forEach(button=>{const active=button.dataset.view===(view==='edit'?'games':view);button.classList.toggle('active',active);active?button.setAttribute('aria-current','page'):button.removeAttribute('aria-current');});
    $('#new-game').hidden=view!=='games';
  }
  function field(label,key,value,options={}){
    const id=options.id || 'field-'+key; const limit=options.max || ({name:150,subtitle:200,summary:500,description:30000,category:80,platform:80,version:80,slug:100,seoTitle:150,seoDescription:500,seoKeywords:500,alt:200,title:150,question:300,answer:3000,text:5000}[key]); const attr=`id="${esc(id)}" ${options.repeat?`data-array="${esc(options.repeat)}" data-index="${options.index}" data-key="${esc(key)}"`:`data-game-field="${esc(key)}"`} ${options.required?'required':''} ${options.readonly?'readonly':''} ${limit?`maxlength="${limit}"`:''} placeholder="${esc(options.placeholder||'')}"`;
    const input=options.area?`<textarea ${attr} rows="${options.rows||3}">${esc(value)}</textarea>`:`<input ${attr} type="${options.type||'text'}" value="${esc(value)}">`;
    return `<label class="field ${options.full?'full':''}" for="${esc(id)}"><span>${esc(label)}${options.required?' <span class="required">*</span>':''}</span>${input}${options.help?`<small>${esc(options.help)}</small>`:''}</label>`;
  }
  function mediaField(label,key,value,options={}){
    const id=options.id || 'field-'+key;const source=safeMedia(value);const attrs=options.repeat?`data-array="${options.repeat}" data-index="${options.index}" data-key="${key}"`:`data-game-field="${key}"`;
    return `<div class="media-preview"><label class="media-label" for="${esc(id)}">${esc(label)}</label><div class="media-row">${source?`<img class="media-thumb ${options.wide?'wide':''}" src="${esc(source)}" alt="${esc(label)}预览" data-preview-for="${esc(id)}" loading="lazy">`:`<img class="media-thumb ${options.wide?'wide':''}" alt="尚未设置图片" data-preview-for="${esc(id)}" hidden>`}<div class="media-controls"><div class="input-with-action"><input id="${esc(id)}" ${attrs} value="${esc(value)}" placeholder="HTTPS 图片地址，或上传至服务器" aria-label="${esc(label)}地址"><button type="button" class="button small" data-upload="${esc(id)}">上传图片</button><input type="file" data-media-input="${esc(id)}" accept="image/jpeg,image/png,image/gif" hidden></div><p class="help">上传支持 JPG、PNG、GIF（保存首帧）；更换后记得保存游戏。</p></div></div></div>`;
  }
  function section(id,title,description,body){return `<section id="${id}" class="panel"><div class="panel-heading"><div><h2>${title}</h2><p>${description}</p></div></div><div class="panel-body">${body}</div></section>`;}
  function emptyGame(){return {id:'',slug:'',name:'',subtitle:'',summary:'',description:'',category:'',platform:'Android',version:'',iconUrl:'',heroUrl:'',downloadUrl:'',introUrl:'',seoTitle:'',seoDescription:'',seoKeywords:'',ogImage:'',noindex:false,published:false,tags:[],screenshots:[],videos:[],features:[],benefits:[],faqs:[],revision:0,createdAt:'',updatedAt:''};}
  async function navigate(view){
    if(!leaveAllowed())return; state.dirty=false;clearNotice();
    if(view==='games')return loadGames();
    if(view==='import'){setView('import','素材导入');renderImport();return;}
    if(view==='settings'){setView('settings','站点设置');content.innerHTML='<div class="panel empty"><span class="loading-dot"></span><p>正在读取站点配置</p></div>';try{state.settings=await api('/api/admin/settings');renderSettings();}catch(error){report(error);} }
  }
  async function loadGames(){
    setView('games','游戏管理');const loadId=++state.loadId;
    content.innerHTML='<div class="panel empty"><span class="loading-dot"></span><p>正在读取游戏列表</p></div>';
    try {const games=await api('/api/admin/games?'+new URLSearchParams({q:state.q,status:state.status}));if(loadId!==state.loadId || state.view!=='games')return;state.games=games;renderGames();}catch(error){if(loadId===state.loadId)report(error);}
  }
  function renderGames(){
    const count=state.games.length;state.page=Math.max(1,Math.min(state.page,Math.ceil(count/20)||1));
    const rows=state.games.slice((state.page-1)*20,state.page*20).map(game=>`<tr><td><div class="game-cell">${safeMedia(game.iconUrl)?`<img src="${esc(safeMedia(game.iconUrl))}" alt="${esc(game.name)}图标" loading="lazy">`:'<span class="game-fallback" aria-hidden="true">◈</span>'}<div><strong>${esc(game.name||'未命名游戏')}</strong><small>${esc(game.category||'未设置分类')} ${game.version?'· '+esc(game.version):''}</small></div></div></td><td class="table-status"><span class="status-pill ${game.published?'live':'draft'}">${game.published?'已发布':'草稿'}</span><span class="status-text">${game.noindex?'禁止索引':'跟随站点索引设置'}</span></td><td class="table-meta">${esc(game.platform||'未设置平台')}</td><td class="table-hide">${esc(formatDate(game.updatedAt))}</td><td class="table-actions"><div class="row-actions"><a href="${previewPath(game)}" target="_blank" rel="noopener">预览 ↗</a>${game.published?`<a href="${gamePath(game)}" target="_blank" rel="noopener">页面 ↗</a>`:''}<button class="text-button danger" type="button" data-delete="${esc(game.id)}">删除</button><button class="button small" type="button" data-edit="${esc(game.id)}">编辑游戏</button></div></td></tr>`).join('');
    content.innerHTML=`<div class="intro-row"><div><h2>你的游戏内容库 <span class="count-label">${count} 款</span></h2><p>把素材整理成有吸引力的游戏页面，再发布给玩家。</p></div><button class="button quiet" type="button" data-view="import">从 JSON + ZIP 导入 ↗</button></div><section class="panel"><form id="filter-form" class="filters"><input class="search-input" name="q" value="${esc(state.q)}" placeholder="搜索游戏名称、介绍…" aria-label="搜索游戏"><select name="status" aria-label="发布状态"><option value="">全部状态</option><option value="published" ${state.status==='published'?'selected':''}>已发布</option><option value="draft" ${state.status==='draft'?'selected':''}>草稿</option></select><button class="button small" type="submit">筛选</button><span class="filter-meta">每个游戏，都有独立的展示页面</span></form>${rows?`<div class="table-wrap"><table><thead><tr><th>游戏</th><th>发布状态</th><th>平台</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table></div>`:`<div class="empty"><div class="empty-symbol">▦</div><h2>${state.q||state.status?'没有匹配的游戏':'从第一款游戏开始'}</h2><p>${state.q||state.status?'换一个关键词或状态，再试一次。':'上传素材包建立草稿，也可以直接新建游戏，配置图片、视频和独立 SEO。'}</p><button class="button primary" data-action="new" type="button">＋ 新建游戏</button></div>`}${count>20?`<div class="panel-heading"><span class="help">第 ${state.page} / ${Math.ceil(count/20)} 页</span><div class="row-actions"><button type="button" class="button small" data-page="${state.page-1}" ${state.page===1?'disabled':''}>上一页</button><button type="button" class="button small" data-page="${state.page+1}" ${state.page*20>=count?'disabled':''}>下一页</button></div></div>`:''}</section>`;
  }
  function formatDate(value){if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
  async function openEditor(id){
    if(!leaveAllowed())return; clearNotice();state.dirty=false;
    try{state.game=id?await api('/api/admin/games/'+encodeURIComponent(id)):emptyGame();setView('edit',id?'编辑游戏':'新建游戏');renderEditor();window.scrollTo({top:0});}catch(error){report(error);}
  }
  function renderEditor(){
    const game=state.game;
    const base=`<div class="field-grid">${field('游戏名称','name',game.name,{required:true,max:150,placeholder:'例如：小小驯龙师'})}${field('副标题','subtitle',game.subtitle,{max:200,placeholder:'例如：首充送霸王龙 · 渠道版本'})}${field('分类','category',game.category,{placeholder:'例如：卡牌 / 放置'})}${field('运行平台','platform',game.platform,{placeholder:'例如：Android'})}${field('版本号','version',game.version,{placeholder:'例如：1.0.0'})}${field('标签','tags',(game.tags||[]).join('，'),{help:'用逗号分隔，例如：恐龙收集，放置，竖版'})}${field('一句话介绍','summary',game.summary,{area:true,full:true,max:500,rows:2,placeholder:'放在首屏的游戏亮点，帮助玩家快速了解玩法。'})}${field('游戏介绍','description',game.description,{area:true,full:true,rows:6,placeholder:'描述游戏的玩法、养成与适合的玩家，可分段输入。纯文字会安全显示。'})}${field('游戏下载链接','downloadUrl',game.downloadUrl,{type:'url',full:true,placeholder:'https://…',help:'填写你的渠道推广下载链接，保留全部参数。'})}${field('游戏介绍页链接','introUrl',game.introUrl,{type:'url',full:true,placeholder:'https://…',help:'可选；访客可先前往渠道介绍页。'})}</div>`;
    const images=`<div class="stack">${mediaField('游戏图标','iconUrl',game.iconUrl)}${mediaField('首屏横幅','heroUrl',game.heroUrl,{wide:true})}</div><div class="separator"></div><div class="panel-heading inline-panel-heading"><h3>游戏画面</h3><span class="help">顺序与前台展示一致</span></div><div id="repeat-screenshots" class="repeat-list">${renderRepeat('screenshots')}</div><button class="button add-row" type="button" data-add="screenshots">＋ 添加图片</button>`;
    const videos=`<p class="help">填写服务器或对象存储提供的 HTTPS 视频直链（如 MP4），不支持视频分享网页。无需再次上传视频；访客点击后才开始加载。</p><div class="separator"></div><div id="repeat-videos" class="repeat-list">${renderRepeat('videos')}</div><button class="button add-row" type="button" data-add="videos">＋ 添加视频</button>`;
    const copy=`<h3>玩法亮点</h3><p class="help">卡片展示真实玩法；没有资料时可以留空。</p><div id="repeat-features" class="repeat-list">${renderRepeat('features')}</div><button class="button add-row" type="button" data-add="features">＋ 添加玩法亮点</button><div class="separator"></div><h3>游戏福利</h3><p class="help">写明实际条件，例如首充奖励需要付费激活。</p><div id="repeat-benefits" class="repeat-list">${renderRepeat('benefits')}</div><button class="button add-row" type="button" data-add="benefits">＋ 添加福利说明</button><div class="separator"></div><h3>常见问题</h3><p class="help">问答会同时用于页面内容与搜索引擎结构化数据。</p><div id="repeat-faqs" class="repeat-list">${renderRepeat('faqs')}</div><button class="button add-row" type="button" data-add="faqs">＋ 添加问题</button>`;
    const seo=`<button type="button" class="button primary" data-ai-seo>✦ AI 生成 SEO 和常见问题</button><p class="help">依据当前游戏资料调用 DeepSeek；会替换 SEO 和常见问题，检查后保存。资料将发送至 DeepSeek。</p><div class="field-grid">${field('页面地址','slug',game.slug,{full:true,readonly:game.published,placeholder:'留空自动生成；例如 xiaoxiaoxunlongshi',help:'仅限小写字母、数字和横线。首次发布后地址锁定，保持搜索链接稳定。'})}${field('SEO 标题','seoTitle',game.seoTitle,{full:true,placeholder:'留空自动生成：游戏名 + 下载与玩法介绍 + 站点名称',help:'建议约 25–35 个汉字，突出游戏名与玩家关心的内容。'})}${field('SEO 描述','seoDescription',game.seoDescription,{area:true,full:true,placeholder:'留空使用游戏简介自动生成',help:'建议约 70–120 个汉字；写清玩法与页面价值，避免重复堆词。'})}${field('关键词（可选）','seoKeywords',game.seoKeywords,{full:true,placeholder:'例如：小小驯龙师,手游下载,恐龙收集',help:'关键词仅作补充，收录与排名还取决于内容质量和搜索引擎。'})}</div><div class="separator"></div>${mediaField('分享封面（留空使用首屏横幅）','ogImage',game.ogImage,{wide:true})}<div class="separator"></div><label class="check"><input type="checkbox" data-game-field="noindex" ${game.noindex?'checked':''}><span><strong>禁止搜索引擎索引这个游戏</strong><small>仍可直接访问已发布页面，但不会加入站点地图。</small></span></label><div class="seo-preview"><div class="search-host" id="seo-preview-url"></div><div class="search-title" id="seo-preview-title"></div><p class="search-desc" id="seo-preview-description"></p></div><p class="seo-help">搜索展示预览；搜索引擎可能根据查询重新生成摘要。站点域名在「站点设置」中配置。</p>`;
    content.innerHTML=`<div class="editor-toolbar"><div><button class="text-button" type="button" data-view="games">← 返回游戏列表</button><span class="editor-path">${game.id?esc(gamePath(game)):'新游戏 · 尚未保存'}</span></div><div><span class="change-hint" id="change-hint">${state.dirty?'有未保存的修改':game.id?'已与服务器同步':'保存后生成独立页面地址'}</span>${game.id?`<a class="button small" href="${previewPath(game)}" target="_blank" rel="noopener">预览已保存内容 ↗</a>`:''}</div></div><form id="game-form"><div class="editor-layout"><div class="editor-main">${section('basic','基本信息','先把游戏的名字、介绍与下载入口说明白。',base)}${section('images','图片素材','清晰的图标、首屏横幅和游戏画面。',images)}${section('videos','视频展示','支持多个视频，自定义标题与封面。',videos)}${section('copy','玩法、福利与问答','让玩家愿意了解，也让页面拥有独特内容。',copy)}${section('seo','独立 SEO','自动生成基础 SEO，也可以逐项自定义。',seo)}</div><aside class="editor-aside"><section class="panel"><div class="panel-heading"><div><span class="mini-label">PUBLISH</span><h2>发布设置</h2></div><span class="status-pill ${game.published?'live':'draft'}">${game.published?'已发布':'草稿'}</span></div><div class="panel-body"><div><p class="help">${game.published?'修改保存后会立即更新公开页面。':'草稿仅管理员可预览。发布后，访客可通过独立链接查看。'}</p><nav class="section-menu" aria-label="编辑章节"><a href="#basic">01 · 基本信息</a><a href="#images">02 · 图片素材</a><a href="#videos">03 · 视频展示</a><a href="#copy">04 · 玩法与福利</a><a href="#seo">05 · 独立 SEO</a></nav></div><div class="save-buttons"><button class="button ${game.published?'primary':''}" type="submit" name="mode" value="current">${game.published?'保存并更新页面':'保存草稿'}</button>${game.published?'<button class="button quiet" type="submit" name="mode" value="unpublish">下线为草稿</button>':'<button class="button primary" type="submit" name="mode" value="publish">发布游戏 ↗</button>'}${game.published?`<a class="button quiet" href="${gamePath(game)}" target="_blank" rel="noopener">查看公开页面 ↗</a>`:''}</div>${game.id?`<dl class="aside-info"><dt>修订版本</dt><dd>${esc(game.revision)}</dd><dt>最近保存</dt><dd>${esc(formatDate(game.updatedAt))}</dd></dl>`:''}</div></section><p class="aside-note">每款游戏都有独立的页面地址、标题、描述与分享封面。已发布页面的文字可直接被搜索引擎读取。</p></aside></div></form>`;
    updateSeoPreview();
  }
  function renderRepeat(kind){
    const rows=state.game[kind]||[];if(!rows.length)return '<div class="empty-list">尚未添加内容。留空时前台自动隐藏这个模块。</div>';
    const name={screenshots:'图片',videos:'视频',features:'玩法',benefits:'福利',faqs:'问题'}[kind];
    return rows.map((row,index)=>{
      const opt={repeat:kind,index};let body='';
      if(kind==='screenshots')body=`${mediaField('图片地址','url',row.url,{...opt,id:kind+'-'+index+'-url'})}<div class="field-grid">${field('图片说明 / 替代文字','alt',row.alt,{...opt,id:kind+'-'+index+'-alt',full:true,placeholder:'描述这张图展示的玩法，帮助理解与图片搜索。'})}</div>`;
      else if(kind==='videos')body=`<div class="field-grid">${field('视频标题','title',row.title,{...opt,id:kind+'-'+index+'-title',full:true,placeholder:'例如：宣传视频 / 玩法演示'})}${field('视频直链','url',row.url,{...opt,id:kind+'-'+index+'-url',type:'url',full:true,placeholder:'https://你的服务器或存储域名/video.mp4'})}</div><div class="separator"></div>${mediaField('视频封面（可选）','poster',row.poster,{...opt,id:kind+'-'+index+'-poster',wide:true})}`;
      else if(kind==='faqs')body=`<div class="field-grid">${field('问题','question',row.question,{...opt,id:kind+'-'+index+'-question',full:true,placeholder:'玩家可能想知道什么？'})}${field('回答','answer',row.answer,{...opt,id:kind+'-'+index+'-answer',full:true,area:true})}</div>`;
      else body=`<div class="field-grid">${field('标题','title',row.title,{...opt,id:kind+'-'+index+'-title',full:true})}${field('说明','text',row.text,{...opt,id:kind+'-'+index+'-text',full:true,area:true})}</div>`;
      return `<div class="repeat-row"><div class="repeat-head"><span>${name} ${String(index+1).padStart(2,'0')}</span><div class="repeat-actions"><button type="button" data-move="${kind}:${index}:-1" ${index===0?'disabled':''} aria-label="上移${name}${index+1}">↑</button><button type="button" data-move="${kind}:${index}:1" ${index===rows.length-1?'disabled':''} aria-label="下移${name}${index+1}">↓</button><button type="button" data-remove="${kind}:${index}" aria-label="删除${name}${index+1}">移除</button></div></div>${body}</div>`;
    }).join('');
  }
  function readEditor(){
    if(state.view!=='edit')return state.game;const game=clone(state.game);
    $$('[data-game-field]', $('#game-form')).forEach(input=>{const key=input.dataset.gameField;game[key]=input.type==='checkbox'?input.checked:input.value.trim();});
    game.tags=String(game.tags||'').split(/[,，\n]/).map(tag=>tag.trim()).filter(Boolean);
    ['screenshots','videos','features','benefits','faqs'].forEach(key=>{game[key]=(game[key]||[]).map(row=>({...row}));});
    $$('[data-array]', $('#game-form')).forEach(input=>{game[input.dataset.array][Number(input.dataset.index)][input.dataset.key]=input.value.trim();});
    return game;
  }
  function updateSeoPreview(){
    if(state.view!=='edit')return;const game=readEditor();const settings=state.settings||{};
    $('#seo-preview-url').textContent=(settings.siteUrl || '你的站点域名')+'/games/'+(game.slug||game.id||'游戏地址')+'/';
    $('#seo-preview-title').textContent=game.seoTitle || (game.name?game.name+'下载与玩法介绍｜'+(settings.siteName||'游选'):'游戏名称下载与玩法介绍｜'+(settings.siteName||'游选'));
    $('#seo-preview-description').textContent=game.seoDescription || (game.summary||game.description||'填写游戏简介后，这里会显示自动生成的搜索描述。').slice(0,160);
  }
  async function saveGame(mode){
    if(state.busy)return;if(state.uploads){notify('图片仍在上传，请等待完成后再保存。','error');return;}
    if(mode==='unpublish'&&!confirm('下线后公开页面将无法访问，并从站点地图移除。确定下线吗？'))return;
    const game=readEditor();const existing=Boolean(game.id);if(!game.id && game._uploadGameId)game.id=game._uploadGameId;game.published=mode==='publish'?true:mode==='unpublish'?false:game.published;
    state.busy=true;const unlock=lockForm($('#game-form'));
    try{
      const saved=await api('/api/admin/games'+(existing?'/'+encodeURIComponent(game.id):''),{method:existing?'PUT':'POST',body:game});
      state.game=saved;setDirty(false);renderEditor();setView('edit','编辑游戏');
      notify(mode==='unpublish'?'已下线为草稿。':saved.published?'已保存并发布，公开页面已更新。':'草稿已保存，可以打开预览查看效果。');
      $('#notice').scrollIntoView({block:'nearest',behavior:'smooth'});
    }catch(error){report(error);}finally{state.busy=false;unlock();}
  }
  async function deleteGame(id){
    const game=state.games.find(item=>item.id===id);if(!game || !confirm(`确定删除「${game.name}」吗？游戏页面会移除，操作不可恢复。`))return;
    try{await api('/api/admin/games/'+encodeURIComponent(id)+'?revision='+game.revision,{method:'DELETE'});await loadGames();notify('游戏记录已删除。');}catch(error){report(error);}
  }
  function mutateRows(kind,operation,index,step){
    state.game=readEditor();const rows=state.game[kind];
    if(operation==='add'){const max={screenshots:40,videos:12,features:30,benefits:30,faqs:30}[kind];if(rows.length>=max){notify('此模块最多添加 '+max+' 项。','error');return;}rows.push(kind==='screenshots'?{url:'',alt:''}:kind==='videos'?{title:'',url:'',poster:''}:kind==='faqs'?{question:'',answer:''}:{title:'',text:''});}
    if(operation==='remove')rows.splice(index,1);
    if(operation==='move' && index+step>=0 && index+step<rows.length)[rows[index],rows[index+step]]=[rows[index+step],rows[index]];
    $('#repeat-'+kind).innerHTML=renderRepeat(kind);setDirty(true);
    if(operation==='add')$('#repeat-'+kind+' .repeat-row:last-child input')?.focus();
  }
  async function uploadImage(input){
    const file=input.files?.[0];if(!file)return;const target=document.getElementById(input.dataset.mediaInput);const button=$$('[data-upload]').find(item=>item.dataset.upload===input.dataset.mediaInput);
    if(!target)return;state.uploads++;if(button){button.disabled=true;button.textContent='上传中…';}
    try{const form=new FormData();form.append('file',file);if(!state.game.id&&!state.game._uploadGameId)state.game._uploadGameId=crypto.randomUUID();form.append('gameId',state.game.id||state.game._uploadGameId);const result=await api('/api/admin/media',{method:'POST',body:form});target.value=result.url;target.dispatchEvent(new Event('input',{bubbles:true}));notify('图片已上传到服务器，保存游戏后生效。');}catch(error){report(error);}finally{state.uploads--;input.value='';if(button){button.disabled=false;button.textContent='上传图片';}}
  }
  function renderImport(){
    content.innerHTML=`<div class="intro-row"><div><h2>把素材变成游戏页面</h2><p>上传游戏资料和素材包，自动建立可以继续编辑的草稿。</p></div></div><div class="import-layout"><section class="panel"><div class="panel-heading"><div><h2>JSON + ZIP 导入</h2><p>原有平台游戏列表 JSON 与对应游戏素材包。</p></div></div><div class="panel-body"><form id="import-form" class="stack"><label class="field">1 · 游戏资料 JSON<input id="import-json" type="file" name="json" accept=".json,.txt,application/json,text/plain" required><small>支持平台 result.data 格式和已整理的单游戏资料。</small></label><label class="field">2 · 选择对应游戏<select name="gameId" id="import-game-id" aria-label="对应游戏"><option value="">先选择 JSON 文件</option></select><small>JSON 内包含多款游戏时，请选中与素材包对应的一款。</small></label><label class="field">3 · 游戏素材 ZIP<input type="file" name="zip" accept=".zip,application/zip" required><small>按素材包目录识别图标、横幅、截图和介绍文字。</small></label><div class="form-note">图片会保存到服务器。ZIP 内视频不导入，请在游戏编辑页填写视频直链。导入先保存为草稿，预览满意后再发布。</div><button type="submit" class="button primary">导入并创建草稿 →</button><div id="import-status" class="import-status" role="status" hidden></div></form></div></section><section class="panel import-steps"><span class="eyebrow">HOW IT WORKS</span><div class="import-step"><span class="step-number">1</span><div><h3>提供真实资料</h3><p>名称、介绍与推广链接来自 JSON，图片和说明来自素材包。</p></div></div><div class="import-step"><span class="step-number">2</span><div><h3>检查草稿</h3><p>调整文案和图片顺序，补充视频链接，按需自定义 SEO。</p></div></div><div class="import-step"><span class="step-number">3</span><div><h3>发布独立页面</h3><p>每个游戏一个页面地址，发布后进入首页与站点地图。</p></div></div></section></div>`;
  }
  async function parseImportJson(input){
    const select=$('#import-game-id');select.innerHTML='<option value="">正在读取…</option>';
    try{
      const file=input.files?.[0];if(!file){select.innerHTML='<option value="">先选择 JSON 文件</option>';return;}
      if(file.size>2*1024*1024)throw new Error('JSON 文件过大，请提供游戏资料 JSON（2 MB 内）。');
      const source=JSON.parse((await file.text()).replace(/^\uFEFF/,''));
      const items=Array.isArray(source)?source:Array.isArray(source.result?.data)?source.result.data:[source];
      const choices=items.filter(game=>game && (game.game_id||game.id)).map(game=>({id:String(game.game_id||game.id),name:game.name||game.short_name||'未命名游戏'}));
      if(!choices.length)throw new Error('JSON 内没有找到游戏 ID，请检查是否为游戏资料文件。');
      select.innerHTML=(choices.length>1?'<option value="">请选择与素材包对应的游戏</option>':'')+choices.map(game=>`<option value="${esc(game.id)}">${esc(game.name)} · ${esc(game.id)}</option>`).join('');
      select.required=choices.length>1;setDirty(true);
    }catch(error){select.innerHTML='<option value="">无法识别 JSON，请重新选择</option>';report(new Error('读取 JSON 失败：'+error.message));}
  }
  async function importGame(form){
    if(state.busy)return;state.busy=true;const button=$('button[type=submit]',form);button.disabled=true;button.textContent='正在导入，请稍候…';const status=$('#import-status');status.hidden=false;status.textContent='正在上传并整理素材，请保持页面打开。';
    try{const game=await api('/api/admin/import',{method:'POST',body:new FormData(form)});state.game=game;state.dirty=false;setView('edit','编辑游戏');renderEditor();notify('已导入为草稿。请检查文案和图片，并按需填写视频直链后发布。');window.scrollTo({top:0});}catch(error){status.textContent='导入未完成，原文件仍保留，请检查错误提示后重试。';report(error);}finally{state.busy=false;button.disabled=false;button.textContent='导入并创建草稿 →';}
  }
  function settingsField(label,key,options={}){
    const value=state.settings[key]||'';const id='setting-'+key;const attrs=`id="${id}" name="${key}" ${options.required?'required':''} placeholder="${esc(options.placeholder||'')}"`;
    return `<label class="field ${options.full?'full':''}" for="${id}">${label}${options.area?`<textarea ${attrs} rows="3">${esc(value)}</textarea>`:`<input ${attrs} type="${options.type||'text'}" value="${esc(value)}">`}${options.help?`<small>${options.help}</small>`:''}</label>`;
  }
  function renderSettings(){
    const settings=state.settings;
    content.innerHTML=`<div class="intro-row"><div><h2>让网站拥有自己的名字</h2><p>这里的设置应用于全站；每款游戏仍可单独配置 SEO。</p></div></div><form id="settings-form" class="settings-form">${section('site-basics','站点信息','品牌、域名与页脚信息。',`<div class="field-grid">${settingsField('网站名称','siteName',{required:true,placeholder:'例如：游选'})}${settingsField('正式网站域名','siteUrl',{type:'url',placeholder:'https://你的域名.com',help:'仅填写 HTTPS 根域名，不带页面路径。'})}${settingsField('页脚说明','footerText',{area:true,full:true,placeholder:'关于网站和推广合作的简短说明'})}${settingsField('ICP备案号（可选）','icpNumber',{full:true,placeholder:'按实际备案情况填写'})}</div>`)}${section('site-seo','全站 SEO','首页展示与搜索引擎抓取设置。',`<div class="field-grid">${settingsField('首页 SEO 标题','seoTitle',{full:true,placeholder:'留空自动生成'})}${settingsField('首页 SEO 描述','seoDescription',{full:true,area:true,placeholder:'用一句话介绍这个游戏网站'})}</div><div class="separator"></div><label class="check"><input name="allowIndexing" type="checkbox" ${settings.allowIndexing?'checked':''}><span><strong>允许搜索引擎索引网站</strong><small>请先配置真实域名并部署 HTTPS。只将已发布且允许索引的游戏加入站点地图；草稿始终不公开。</small></span></label><p class="form-note">开启后自动提供 canonical、robots.txt 和 sitemap.xml。实际收录与排名由搜索引擎决定，建议上线后提交站点地图。</p><div class="row-actions settings-links"><a class="text-button" href="/sitemap.xml" target="_blank" rel="noopener">查看站点地图 ↗</a><a class="text-button" href="/robots.txt" target="_blank" rel="noopener">查看抓取规则 ↗</a></div>`)}<div class="settings-actions"><span class="change-hint" id="change-hint">已与服务器同步</span><button type="submit" class="button primary">保存站点设置</button></div></form>`;
  }
  async function saveSettings(form){
    if(state.busy)return;state.busy=true;const button=$('button[type=submit]',form);button.disabled=true;
    const data=Object.fromEntries(new FormData(form));data.allowIndexing=$('[name=allowIndexing]',form).checked;
    try{state.settings=await api('/api/admin/settings',{method:'PUT',body:data});setDirty(false);renderSettings();notify('站点设置已保存，公开页面与站点地图已更新。');}catch(error){report(error);}finally{state.busy=false;button.disabled=false;}
  }
  async function generateSeo(){
    if(state.busy||state.uploads)return;
    if(!confirm('将当前游戏文字资料发送给 DeepSeek，并替换编辑框中的 SEO 和常见问题。生成后仍需检查并保存，继续吗？'))return;
    const draft=readEditor();state.busy=true;
    const controls=$$('#game-form input, #game-form textarea, #game-form select, #game-form button');
    controls.forEach(el=>{el.dataset.aiDisabled=String(el.disabled);el.disabled=true;});
    notify('正在生成 SEO 和常见问题，请稍候…');
    try{const result=await api('/api/admin/ai/seo',{method:'POST',body:draft});state.game={...draft,...result};state.dirty=true;renderEditor();notify('AI 内容已填入，尚未保存。请检查事实和福利条件后保存。');}
    catch(error){report(error);}finally{state.busy=false;controls.forEach(el=>{el.disabled=el.dataset.aiDisabled==='true';delete el.dataset.aiDisabled;});}
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('[data-ai-seo]')){generateSeo();return;}

    const nav=event.target.closest('[data-view]');if(nav){event.preventDefault();navigate(nav.dataset.view);return;}
    const action=event.target.closest('[data-action]');if(action?.dataset.action==='new'){openEditor('');return;}
    const edit=event.target.closest('[data-edit]');if(edit){openEditor(edit.dataset.edit);return;}
    const del=event.target.closest('[data-delete]');if(del){deleteGame(del.dataset.delete);return;}
    const page=event.target.closest('[data-page]');if(page){state.page=Number(page.dataset.page);renderGames();return;}
    const add=event.target.closest('[data-add]');if(add){mutateRows(add.dataset.add,'add');return;}
    const remove=event.target.closest('[data-remove]');if(remove){const[kind,index]=remove.dataset.remove.split(':');mutateRows(kind,'remove',Number(index));return;}
    const move=event.target.closest('[data-move]');if(move){const[kind,index,step]=move.dataset.move.split(':');mutateRows(kind,'move',Number(index),Number(step));return;}
    const upload=event.target.closest('[data-upload]');if(upload){const input=$$('[data-media-input]').find(item=>item.dataset.mediaInput===upload.dataset.upload);input?.click();}
  });
  document.addEventListener('submit',event=>{
    const form=event.target;
    if(form.id==='logout-form' || form.id==='mobile-logout-form'){if(!leaveAllowed()){event.preventDefault();return;}state.dirty=false;return;}
    if(!['filter-form','game-form','import-form','settings-form'].includes(form.id))return;event.preventDefault();
    if(form.id==='filter-form'){state.q=form.q.value.trim();state.status=form.status.value;state.page=1;loadGames();}
    if(form.id==='game-form')saveGame(event.submitter?.value || 'current');
    if(form.id==='import-form')importGame(form);
    if(form.id==='settings-form')saveSettings(form);
  });
  document.addEventListener('input',event=>{
    const input=event.target;
    if(input.closest('#game-form')){
      setDirty(true);updateSeoPreview();
      const preview=$$('[data-preview-for]').find(image=>image.dataset.previewFor===input.id);if(preview){const url=safeMedia(input.value);if(url){preview.src=url;preview.hidden=false;}else{preview.removeAttribute('src');preview.hidden=true;}}
    }
    if(input.closest('#settings-form'))setDirty(true);
  });
  document.addEventListener('change',event=>{const input=event.target;if(input.matches('[data-media-input]'))uploadImage(input);else if(input.id==='import-json')parseImportJson(input);else if(input.closest('#import-form'))setDirty(true);else if(input.closest('#settings-form'))setDirty(true);});
  window.addEventListener('beforeunload',event=>{if(state.dirty||state.busy||state.uploads){event.preventDefault();event.returnValue='';}});
  async function start(){
    try{state.session=await api('/api/admin/session');$('#account-name').textContent=state.session.username;state.settings=await api('/api/admin/settings');await loadGames();}catch(error){content.innerHTML='<div class="panel empty"><h2>工作台暂时无法加载</h2><p>请检查登录状态和服务器连接。</p><a class="button" href="/login">重新登录</a></div>';report(error);}
  }
  start();
})();
