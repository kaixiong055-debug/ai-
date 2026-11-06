"""SEO and deployment contracts; standard library only."""
import argparse
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

spec=importlib.util.spec_from_file_location('game_build',Path(__file__).resolve().parents[1]/'build.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.tags=[];self.feed(text)
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))

class BuildTests(unittest.TestCase):
    def test_preview_is_not_accidentally_indexable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);build.render('',root)
            parser=Page((root/'games/14545/index.html').read_text())
            self.assertIn(('meta',{'name':'robots','content':'noindex,follow'}),parser.tags)
            self.assertNotIn('rel="canonical"',(root/'games/14545/index.html').read_text())
            self.assertIn('Disallow: /',(root/'robots.txt').read_text())
            self.assertFalse((root/'sitemap.xml').exists())

    def test_production_has_crawlable_content_and_consistent_urls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);build.render('https://game.example',root)
            page=(root/'games/14545/index.html').read_text();parser=Page(page)
            self.assertEqual(sum(tag=='h1' for tag,_ in parser.tags),1)
            self.assertIn(('link',{'rel':'canonical','href':'https://game.example/games/14545/'}),parser.tags)
            self.assertIn('恐龙收集',page)
            self.assertIn('https://m.3387.com/s/a9oaMS8sm?d=1',page)
            self.assertNotIn('q-signature',page)
            for tag,attrs in parser.tags:
                for name in ('src','href'):
                    path=attrs.get(name,'')
                    if path.startswith('../../'):
                        self.assertTrue((root/'games/14545'/path).resolve().exists(),path)
            urls=[node.text for node in ET.parse(root/'sitemap.xml').findall('.//{*}loc')]
            self.assertEqual(urls,['https://game.example/','https://game.example/games/14545/'])
            self.assertIn('Sitemap: https://game.example/sitemap.xml',(root/'robots.txt').read_text())
            payload=page.split('<script type="application/ld+json">',1)[1].split('</script>',1)[0]
            graph=json.loads(payload)['@graph']
            self.assertNotIn('aggregateRating',graph[0]);self.assertNotIn('offers',graph[0])
            self.assertEqual(len(next(x for x in graph if x['@type']=='FAQPage')['mainEntity']),page.count('<details>'))

    def test_invalid_domain_is_rejected(self):
        for url in ('http://game.example','javascript:alert(1)','https://user:secret@game.example','https://game.example/subpath','https://game.example/?token=secret'):
            with self.subTest(url=url),self.assertRaises(argparse.ArgumentTypeError):build.site_url(url)
        self.assertEqual(build.site_url('https://game.example/'),'https://game.example')

if __name__=='__main__':unittest.main()
