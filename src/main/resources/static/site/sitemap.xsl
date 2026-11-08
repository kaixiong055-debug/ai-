<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9">
<xsl:output method="html" encoding="UTF-8"/>
<xsl:template match="/"><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1"/><title>网站地图</title><link rel="stylesheet" href="/site/sitemap.css"/></head><body><main><a href="/">← 返回游戏网站</a><h1>网站地图</h1><p>这里是供搜索引擎读取的公开页面列表。已发布且允许索引的游戏会自动加入；修改后更新时间，下线后移除，无需手动生成。</p><p>当前共 <strong><xsl:value-of select="count(s:urlset/s:url)"/></strong> 个地址（含首页）。</p><table><thead><tr><th>页面地址</th><th>最近更新（UTC）</th></tr></thead><tbody><xsl:for-each select="s:urlset/s:url"><tr><td><a href="{s:loc}"><xsl:value-of select="s:loc"/></a></td><td><xsl:value-of select="s:lastmod"/></td></tr></xsl:for-each></tbody></table></main></body></html></xsl:template>
</xsl:stylesheet>
