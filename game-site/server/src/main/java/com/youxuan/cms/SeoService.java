package com.youxuan.cms;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import java.net.URI;
import java.util.*;

/** SEO derives its origin only from the administrator's site setting, never a request Host. */
@Service
public class SeoService {
    private final ObjectMapper mapper;
    public SeoService(ObjectMapper mapper) { this.mapper = mapper; }

    public Map<String, String> game(Game game, SiteSettings settings, boolean preview) {
        String origin = origin(settings);
        String canonical = origin.isEmpty() ? "" : origin + "/games/" + game.slug + "/";
        String title = fallback(game.seoTitle, game.name + "下载与玩法介绍｜" + settings.siteName);
        String description = fallback(game.seoDescription, excerpt(fallback(game.summary, game.description), 160));
        String image = absolute(fallback(game.ogImage, game.heroUrl), origin);
        boolean index = indexable(settings) && !game.noindex && !preview;
        var graph = new ArrayList<Map<String, Object>>();
        var application = new LinkedHashMap<String, Object>();
        application.put("@type", List.of("VideoGame", "SoftwareApplication"));
        application.put("name", game.name);
        application.put("description", description);
        application.put("applicationCategory", "GameApplication");
        put(application, "operatingSystem", game.platform);
        put(application, "softwareVersion", game.version);
        put(application, "genre", game.category);
        put(application, "image", image);
        put(application, "url", canonical);
        if (!canonical.isEmpty()) application.put("@id", canonical + "#game");
        graph.add(application);
        if (game.faqs != null && !game.faqs.isEmpty()) {
            var questions = game.faqs.stream().filter(f -> !s(f.question()).isEmpty() && !s(f.answer()).isEmpty())
                .map(f -> Map.of("@type", "Question", "name", f.question(),
                    "acceptedAnswer", Map.of("@type", "Answer", "text", f.answer()))).toList();
            if (!questions.isEmpty()) graph.add(Map.of("@type", "FAQPage", "mainEntity", questions));
        }
        if (!canonical.isEmpty()) {
            graph.add(Map.of("@type", "BreadcrumbList", "itemListElement", List.of(
                Map.of("@type", "ListItem", "position", 1, "name", settings.siteName, "item", origin + "/"),
                Map.of("@type", "ListItem", "position", 2, "name", game.name, "item", canonical))));
            graph.add(Map.of("@type", "WebPage", "@id", canonical, "url", canonical, "name", title,
                "description", description, "mainEntity", Map.of("@id", canonical + "#game"), "inLanguage", "zh-CN"));
        }
        return values(title, description, s(game.seoKeywords), canonical, image, index,
            json(Map.of("@context", "https://schema.org", "@graph", graph)));
    }

    public Map<String, String> home(SiteSettings settings, boolean search) {
        String origin = origin(settings);
        String title = fallback(settings.seoTitle, settings.siteName + "｜发现下一款想玩的游戏");
        String description = fallback(settings.seoDescription, "浏览游戏画面、玩法介绍与版本信息，发现适合自己的游戏。");
        String canonical = origin.isEmpty() ? "" : origin + "/";
        var website = new LinkedHashMap<String, Object>();
        website.put("@context", "https://schema.org"); website.put("@type", "WebSite");
        website.put("name", settings.siteName); website.put("description", description);
        put(website, "url", canonical);
        return values(title, description, "", canonical, "", indexable(settings) && !search, json(website));
    }

    public boolean indexable(SiteSettings settings) { return settings.allowIndexing && !origin(settings).isEmpty(); }

    public String origin(SiteSettings settings) {
        String value = s(settings.siteUrl);
        if (value.isEmpty()) return "";
        try {
            URI uri = URI.create(value);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null
                || uri.getQuery() != null || uri.getFragment() != null
                || !(uri.getPath().isEmpty() || "/".equals(uri.getPath()))) return "";
            return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
        } catch (IllegalArgumentException e) { return ""; }
    }

    private Map<String, String> values(String title, String description, String keywords, String canonical,
            String image, boolean index, String jsonLd) {
        return Map.of("title", title, "description", description, "keywords", keywords, "canonical", canonical,
            "image", image, "robots", index ? "index,follow,max-image-preview:large" : "noindex,follow",
            "jsonLd", jsonLd);
    }
    private String json(Object value) {
        try {
            return mapper.writeValueAsString(value).replace("<", "\\u003c").replace(">", "\\u003e")
                .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029");
        } catch (JsonProcessingException e) { throw new IllegalStateException("无法生成页面元数据", e); }
    }
    private static String absolute(String url, String origin) {
        if (url.startsWith("/media/") && !origin.isEmpty()) return origin + url;
        return url.startsWith("https://") ? url : "";
    }
    private static String excerpt(String value, int limit) {
        String normalized = value.replaceAll("\\s+", " ").trim();
        return normalized.codePointCount(0, normalized.length()) > limit
            ? normalized.substring(0, normalized.offsetByCodePoints(0, limit)) : normalized;
    }
    private static void put(Map<String, Object> map, String key, String value) { if (!s(value).isEmpty()) map.put(key, value); }
    private static String fallback(String first, String second) { return s(first).isEmpty() ? s(second) : s(first); }
    private static String s(String value) { return value == null ? "" : value.trim(); }
}
