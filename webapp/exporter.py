"""Export user-facing product folders without downloading any network resources."""
from __future__ import annotations
import csv
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from .store import Store

PLATFORMS={'taobao':'淘宝','xianyu':'闲鱼'}
KINDS={'main':'封面','gallery':'商品图','sku':'SKU图','detail':'详情图'}
STATUSES={'pending':'未下载','failed':'下载失败','downloaded':'已下载'}


def folder_name(value: str, fallback: str) -> str:
    value=unicodedata.normalize('NFC',value)
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_',value).strip(' .')[:60].rstrip(' .')
    if not value: value=fallback
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',value,re.IGNORECASE): value='_'+value
    return value


def csv_cell(value: object) -> str:
    text=str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text


def write_archive(archive: Path, store: Store, products: list[dict]) -> None:
    used: set[str]=set()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for product in products:
            platform=folder_name(PLATFORMS.get(product['platform'],product['platform']),'未知平台')
            keyword=folder_name(product.get('keyword') or '', '未分类')
            title=folder_name(product.get('title') or '', '未命名商品')
            folder=f'{platform}/{keyword}/{title}'
            if folder.casefold() in used:
                folder=f'{folder}_{product["id"]}'
                while folder.casefold() in used: folder+='_'  # User titles may already contain the suffix.
            used.add(folder.casefold())
            manifest=[]
            copied: dict[str,str]={}
            for index,image in enumerate(store.gallery(product['id']),1):
                filename=''
                state=STATUSES.get(image['status'],'未知状态')
                error=image.get('error') or ''
                if image['status']=='downloaded' and image.get('path'):
                    source=(store.root/image['path']).resolve()
                    if source.is_relative_to(store.root/'images') and source.is_file() and source.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp'):
                        key=str(source)
                        if key in copied: filename=copied[key]
                        else:
                            filename=f'{index:03d}_{KINDS.get(image["kind"],"商品图")}{source.suffix.lower()}'
                            z.write(source,f'{folder}/{filename}')
                            copied[key]=filename
                    else:
                        state='本地文件缺失';error='请重新下载此图片后导出'
                if image['status']=='downloaded' and not image.get('path'):
                    state='本地文件缺失';error='请重新下载此图片后导出'
                manifest.append({'序号':index,'类型':KINDS.get(image['kind'],'商品图'),'状态':state,'文件名':filename,'来源地址':image['url'],'失败原因':error})
            info={'商品名称':product['title'],'来源平台':PLATFORMS.get(product['platform'],product['platform']),
                  '搜索关键词':product.get('keyword') or '', '分类依据':'搜索关键词，非平台官方类目',
                  '来源页面':product.get('source_url') or '', '来源页面名称':product.get('source_name') or '',
                  '商品ID':product['item_id'],'售价':product.get('current_price'),'原始链接':product.get('url') or '',
                  '采集时间':product.get('crawled_at'),'详情采集状态':product.get('detail_status'),
                  '详情采集提示':product.get('detail_error'),'商品介绍':product.get('description') or '',
                  '图片':manifest}
            lines=[f'商品名称：{info["商品名称"]}',f'来源平台：{info["来源平台"]}',f'搜索关键词：{info["搜索关键词"]}',
                   f'分类依据：{info["分类依据"]}',f'商品 ID：{info["商品ID"]}',
                   f'售价：{info["售价"] if info["售价"] is not None else "未获取"}',f'原始链接：{info["原始链接"]}',f'来源页面：{info["来源页面"]}',f'来源页面名称：{info["来源页面名称"]}',
                   f'采集时间：{info["采集时间"]}', '', '商品介绍：',info['商品介绍'] or '尚未获取到商品介绍，请先补采详情。',
                   '',f'已导出图片文件：{len(copied)}；已采集图片地址：{len(manifest)}。',
                   '导出不会自动下载图片；未下载、失败或缺失图片请查看图片清单。']
            if info['详情采集提示']: lines.extend(['详情提示：',info['详情采集提示']])
            z.writestr(f'{folder}/商品介绍.txt','\r\n'.join(lines).encode('utf-8-sig'))
            z.writestr(f'{folder}/商品信息.json',json.dumps(info,ensure_ascii=False,indent=2).encode('utf-8'))
            stream=io.StringIO(newline='')
            fields=['序号','类型','状态','文件名','来源地址','失败原因']
            writer=csv.writer(stream);writer.writerow(fields)
            for row in manifest: writer.writerow([csv_cell(row[f]) for f in fields])
            z.writestr(f'{folder}/图片清单.csv',stream.getvalue().encode('utf-8-sig'))
