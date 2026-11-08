"""Run after Maven package: python src/test/browser/auto_publish.py.
Needs Python Playwright and /usr/bin/chromium. Only the AI HTTP response is mocked;
imports, images, persistence, validation and publishing use a temporary real server.
"""
import subprocess,os,secrets,time,urllib.request,tempfile,json,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
secret=secrets.token_urlsafe(24);base='http://127.0.0.1:8792';work=Path(tempfile.mkdtemp(prefix='auto-publish-'));folder=work/'素材';folder.mkdir()
games=[{'id':str(n),'name':name,'pkg_url':'https://example.com/download'} for n,name in [(101,'已导入'),(102,'正常游戏'),(103,'AI失败游戏'),(104,'缺图游戏'),(105,'后续游戏')]]
(work/'games.json').write_text(json.dumps({'result':{'data':games}},ensure_ascii=False))
def archive(path,missing=False):
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('游戏简介.txt','这是一个收集恐龙的游戏。')
  if not missing:
   z.write('src/main/resources/sample/icon.jpg','图标.jpg');z.write('src/main/resources/sample/hero.jpg','横幅.jpg')
for g in games:archive(folder/('《'+g['name']+'》游戏素材.zip'),g['id']=='104')
env=dict(os.environ,GAME_ADMIN_PASSWORD=secret,PORT='8792',CMS_DATA_DIR=str(work/'data'),CMS_DEMO_ENABLED='false');log=open(work/'server.log','w');proc=subprocess.Popen(['java','-jar','target/game-cms-1.0.0.jar'],env=env,stdout=log,stderr=log)
try:
 for _ in range(100):
  try:urllib.request.urlopen(base+'/login');break
  except Exception:time.sleep(.25)
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1440,'height':1000});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/login');page.locator('#username').fill('admin');page.locator('#password').fill(secret);page.get_by_role('button',name='登录工作台').click();expect(page).to_have_url(base+'/admin')
  calls=[];fail_ai=True
  def ai(route):
   data=route.request.post_data_json;calls.append(data['id'])
   if data['id']=='103' and fail_ai:route.fulfill(status=502,json={'message':'模拟 AI 暂时不可用'});return
   route.fulfill(json={'seoTitle':data['name']+'下载介绍','seoDescription':'恐龙收集玩法介绍','seoKeywords':'恐龙,收集','faqs':[{'question':'有什么玩法？','answer':'收集恐龙。'}]})
  page.route('**/api/admin/ai/seo',ai)
  session=ctx.request.get(base+'/api/admin/session').json();headers={session['headerName']:session['token']};assert ctx.request.post(base+'/api/admin/games',headers=headers,data={'id':'101','name':'保留的已编辑名称'}).status==201
  page.locator('.nav-item[data-view=import]').click();page.locator('#batch-json').set_input_files(work/'games.json');page.locator('#batch-folder').set_input_files(folder);page.locator('#batch-plan').click();expect(page.locator('#batch-start')).to_be_enabled();page.locator('#batch-start').click();expect(page.locator('#notice')).to_contain_text('批量处理完成',timeout=30000)
  expect(page.locator('#batch-summary')).to_contain_text('成功 2');expect(page.locator('#batch-summary')).to_contain_text('失败 / 未匹配 2');assert '101' not in calls
  def game(id):return ctx.request.get(base+'/api/admin/games/'+str(id)).json()
  for id in [102,105]:assert game(id)['published'] and game(id)['seoTitle'] and game(id)['faqs']
  assert not game(103)['published'];assert not game(104)['published'] and game(104)['seoTitle'];assert game(101)['name']=='保留的已编辑名称'
  fail_ai=False;page.locator('[data-retry-publish="2"]').click();expect(page.locator('#batch-summary')).to_contain_text('成功 3');assert game(103)['published']
  # Publication-only retry must not spend another AI call once its copy was saved.
  before=calls.count('104');page.locator('[data-retry-publish="3"]').click();expect(page.locator('[data-retry-publish="3"]')).to_be_enabled();assert calls.count('104')==before
  page.locator('#batch-plan').click();expect(page.locator('#batch-summary')).to_contain_text('跳过 5')
  # Single import runs the same complete workflow.
  single=work/'single.json';single.write_text(json.dumps({'id':'106','name':'单个游戏','pkg_url':'https://example.com/d'}));single_zip=work/'single.zip';archive(single_zip)
  page.locator('#import-json').set_input_files(single);expect(page.locator('#import-game-id')).to_have_value('106');page.locator('#import-form input[name=zip]').set_input_files(single_zip);page.locator('#import-form button[type=submit]').click();expect(page.locator('#notice')).to_contain_text('游戏已发布',timeout=30000);assert game(106)['published']
  assert not errors,errors;browser.close();print('PASS: batch/single auto SEO and publish; skip existing; AI failure and publish validation preserve drafts; retry; no duplicate AI on publish-only retry; no JS errors')
finally:proc.terminate();proc.wait(timeout=15);log.close()
